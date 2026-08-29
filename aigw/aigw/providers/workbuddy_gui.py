"""Workbuddy (desktop GUI) provider via Windows UI Automation.

Some Workbuddy builds are distributed as a desktop GUI with no CLI and no
inbound API. This provider drives the chat box the way a human would — the GUI
analog of spawn-CLI (see aigw/providers/gui.py for the engine + CAVEATS). All
control selectors are config-driven; run `aigw workbuddy-dump` on the target
Windows machine to discover them. See aigw/docs/GUI_AUTOMATION.md.
"""

from __future__ import annotations

from .gui import GuiProvider


class WorkbuddyGuiProvider(GuiProvider):
    name = "workbuddy_gui"
    display_name = "Workbuddy"
    served_models: tuple[str, ...] = ()
