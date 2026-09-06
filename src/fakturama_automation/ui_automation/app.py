"""Connection to a running Fakturama application window.

The one module in ui_automation that imports pywinauto directly, so it
fails immediately on macOS/Linux and can only be exercised against a real
running Fakturama window on the VM (see README.md).
"""

from __future__ import annotations

from typing import Any

import win32gui
from pywinauto import Application

from fakturama_automation.ui_automation import waits
from fakturama_automation.ui_automation.exceptions import AmbiguousControlError, DialogTimeoutError


def _visible_window_handles(title: str) -> list[int]:
    """Every currently-visible top-level OS window handle titled exactly
    `title`, via raw win32gui.EnumWindows - the shared no-polling snapshot
    primitive behind FakturamaApp's top_level_window_by_title/
    top_level_window_is_open/wait_until_top_level_window_closed.
    """
    handles: list[int] = []

    def _callback(hwnd: int, _: Any) -> None:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
            handles.append(hwnd)

    win32gui.EnumWindows(_callback, None)
    return handles


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

    def top_level_window_by_title(self, title: str, timeout_seconds: float = 5.0) -> Any:
        """Locate a genuinely separate top-level OS window by its exact
        title, polling until it appears or raising DialogTimeoutError.

        For dialogs like the Order editor's "Select the address" picker:
        confirmed live these are real separate top-level windows, not
        reliably found by pywinauto's own window enumeration
        (`self._app.window()`/`Desktop().windows()` both miss them) - raw
        win32gui.EnumWindows finds them every time. Every other window/
        dialog lookup should keep using window()/waits.wait_for_dialog.

        Raises AmbiguousControlError if more than one visible window
        matches `title`, mirroring controls.find_control's fail-closed
        handling - a stale leftover window with the same title can
        otherwise get silently grabbed instead of the freshly-opened one.
        """
        handles: list[int] = []

        def _find() -> bool:
            handles[:] = _visible_window_handles(title)
            return len(handles) >= 1

        if not waits.wait_until(_find, timeout_seconds=timeout_seconds):
            raise DialogTimeoutError(f"no top-level window titled {title!r} appeared within {timeout_seconds}s")
        if len(handles) > 1:
            raise AmbiguousControlError(
                f"{len(handles)} top-level windows titled {title!r} found; expected exactly one"
            )

        dialog_app = Application(backend="uia").connect(handle=handles[0])
        return dialog_app.window(handle=handles[0])

    def top_level_window_is_open(self, title: str) -> bool:
        """True if a visible top-level window titled exactly `title` exists
        right now - a single no-polling snapshot, unlike
        top_level_window_by_title (which polls for it to appear).

        Needed because a picker dialog can flash open and close again
        within a fraction of a second of the toolbar click that opens it
        (confirmed live) - lets a caller re-check a beat later and re-click
        if the dialog it just "found" is already gone.
        """
        return len(_visible_window_handles(title)) >= 1

    def wait_until_top_level_window_closed(self, title: str, timeout_seconds: float = 5.0) -> None:
        """Poll until no top-level OS window with this exact title is
        visible, or raise DialogTimeoutError.

        Reopening a picker before it's actually finished closing can hand
        back a stale/half-torn-down UIA tree (confirmed live: a `.parent()`
        chain crashing with AttributeError instead of failing closed) -
        callers should wait for a picker to fully close before reopening it.
        """

        def _is_gone() -> bool:
            return len(_visible_window_handles(title)) == 0

        if not waits.wait_until(_is_gone, timeout_seconds=timeout_seconds):
            raise DialogTimeoutError(f"top-level window titled {title!r} did not close within {timeout_seconds}s")
