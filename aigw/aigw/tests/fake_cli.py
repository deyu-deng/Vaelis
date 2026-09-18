"""Fake `agy` stand-in for tests.

Mimics the contract the AntigravityCliProvider relies on:

    agy -p "<prompt>" [--model <model>]

It simply echoes the prompt back (wrapped) so the test can prove the spawn ->
capture -> OpenAI-translation pipeline without the real CLI or any vendor
account. This file is NOT shipped in the gateway runtime; it lives only under
aigw/tests/.
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    prompt = ""
    if "-p" in args:
        i = args.index("-p")
        if i + 1 < len(args):
            prompt = args[i + 1]
    # Mimic a CLI that prints its answer (with a little banner) to stdout.
    sys.stdout.write(f"FAKE_CLI<<{prompt}>>\n")


if __name__ == "__main__":
    main()
