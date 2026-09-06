from __future__ import annotations

from typing import Any

import win32gui
from pywinauto import Application

from fakturama_automation.ui_automation import waits
from fakturama_automation.ui_automation.exceptions import AmbiguousControlError, DialogTimeoutError


def _visible_window_handles(title: str) -> list[int]:
    handles: list[int] = []

    def _callback(hwnd: int, _: Any) -> None:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
            handles.append(hwnd)

    win32gui.EnumWindows(_callback, None)
    return handles


class FakturamaApp:

    def __init__(self) -> None:
        self._app: Application | None = None

    def connect(self, title_re: str) -> None:
        self._app = Application(backend="uia").connect(title_re=title_re)

    def main_window(self) -> Any:
        return self._app.top_window()

    def window(self, title_re: str) -> Any:
        return self._app.window(title_re=title_re)

    def top_level_window_by_title(self, title: str, timeout_seconds: float = 5.0) -> Any:
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
        return len(_visible_window_handles(title)) >= 1

    def wait_until_top_level_window_closed(self, title: str, timeout_seconds: float = 5.0) -> None:

        def _is_gone() -> bool:
            return len(_visible_window_handles(title)) == 0

        if not waits.wait_until(_is_gone, timeout_seconds=timeout_seconds):
            raise DialogTimeoutError(f"top-level window titled {title!r} did not close within {timeout_seconds}s")
