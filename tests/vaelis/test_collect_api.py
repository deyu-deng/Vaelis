"""/api/collect: the board's first-run review and pending-queue endpoints (A7)."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vaelis.agenda.service import AgendaService
from vaelis.collectors.chatlog import collect_api, webhook as webhook_module
from vaelis.collectors.chatlog.config import CollectorConfig
from vaelis.collectors.chatlog.confirm import HeuristicConfirmer
from vaelis.collectors.chatlog.pipeline import ChatlogPipeline
from vaelis.collectors.chatlog.state import SeenStore, TalkerStore

NOW = datetime(2026, 8, 25, 10, 0)


class StubClient:
    def __init__(self, sessions: list[str]):
        self.sessions = sessions

    def fetch(self, talker, day=None):
        return []

    def list_talkers(self, keyword: str = "", limit: int = 10000) -> list[str]:
        return [t for t in self.sessions if keyword in t]

    def healthy(self):
        return True


@pytest.fixture()
def client(tmp_path):
    pipeline = ChatlogPipeline(
        config=CollectorConfig(mode="blacklist", enabled=True),
        client=StubClient(["班级群", "项目群", "广告群"]),
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        talkers=TalkerStore(tmp_path / "talkers.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )
    # collect_api wires to the webhook module's canonical pipeline instance.
    webhook_module.set_pipeline(pipeline)

    app = FastAPI()
    app.include_router(webhook_module.router, prefix="/api/chatlog")
    app.include_router(collect_api.router, prefix="/api/collect")

    with TestClient(app) as test_client:
        test_client.pipeline = pipeline  # type: ignore[attr-defined]
        yield test_client

    webhook_module.set_pipeline(None)
    collect_api.set_pipeline(None)


def test_list_starts_unreviewed_with_all_candidates_pending(client):
    body = client.get("/api/collect/talkers").json()

    assert body["reviewComplete"] is False
    # Every active session is offered for the first-run review; unreviewed
    # ones surface as pending without being written to the status table.
    by_id = {row["id"]: row["status"] for row in body["talkers"]}
    assert by_id == {"班级群": "pending", "项目群": "pending", "广告群": "pending"}
    assert client.pipeline.talkers.pending() == set()


def test_one_click_collect_marks_known(client):
    response = client.post("/api/collect/talkers/班级群/mode", json={"mode": "collect"})

    assert response.json() == {"id": "班级群", "status": "known"}
    assert client.pipeline.talkers.status_of("班级群") == "known"

    body = client.get("/api/collect/talkers").json()
    assert {r["id"] for r in body["talkers"] if r["status"] == "known"} == {"班级群"}


def test_one_click_exclude_marks_excluded(client):
    response = client.post("/api/collect/talkers/广告群/mode", json={"mode": "exclude"})

    assert response.json() == {"id": "广告群", "status": "excluded"}
    assert client.pipeline.talkers.status_of("广告群") == "excluded"


def test_bulk_decision_marks_many(client):
    response = client.post(
        "/api/collect/talkers/bulk",
        json={"talkers": ["项目群", "广告群"], "status": "excluded"},
    )

    assert response.json()["updated"] == 2
    assert client.pipeline.talkers.excluded() == {"项目群", "广告群"}


def test_review_complete_flips_the_gate(client):
    response = client.post("/api/collect/review-complete")

    assert response.json() == {"reviewComplete": True}
    assert client.pipeline.talkers.review_done() is True

    body = client.get("/api/collect/talkers").json()
    assert body["reviewComplete"] is True
