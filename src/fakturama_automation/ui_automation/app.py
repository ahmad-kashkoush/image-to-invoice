"""Connection to a running Fakturama application window.

Section 3 (ui_automation). This is the one module in ui_automation that
imports pywinauto directly (`from pywinauto import Application`), which
fails immediately on macOS/Linux (verified: the bare `import pywinauto`
succeeds there, but `Application` is not exposed off Windows). It can only
be exercised against a real running Fakturama window on the Windows 11 ARM
VM described in README.md - see spikes/uia_probe.py for the read only
discovery version of this.
"""

from __future__ import annotations

from typing import Any

from pywinauto import Application


class FakturamaApp:
    """Handle to a running Fakturama window, backed by pywinauto uia.

    main_window() and window() are deliberately generic rather than
    Fakturama-specific accessors (no order_editor()/debtor_editor()/...):
    Doc/Design.md's control discovery strategy is the same across every
    Fakturama editor and dialog, so callers (entity_resolution,
    verification, the orchestrator) compose window(title_re) with
    controls.find_control() for whichever screen they need, instead of this
    module hardcoding Fakturama's specific dialog titles.
    """

    def __init__(self) -> None:
        self._app: Application | None = None

    def connect(self, title_re: str) -> None:
        """Attach to the running Fakturama top level window."""
        self._app = Application(backend="uia").connect(title_re=title_re)

    def main_window(self) -> Any:
        """The main Fakturama window, once connected."""
        return self._app.top_window()

    def window(self, title_re: str) -> Any:
        """A lazy handle to any window/dialog/editor matching title_re,
        used by ui_automation.waits.wait_for_dialog.
        """
        return self._app.window(title_re=title_re)
