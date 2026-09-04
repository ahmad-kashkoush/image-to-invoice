"""Polling helpers, used instead of fixed sleeps.

Section 3 (ui_automation). After actions that open a dialog, poll for the
expected state rather than sleeping. Wait for search result sets to
stabilize (same row count across consecutive polls) before reading rows.

No pywinauto import here: `app` and `get_row_count` are whatever duck-typed
objects the caller already holds, and only the documented pywinauto methods
used below (`.window(title_re=...)`, `.exists()`) are called on them. This
keeps this module (and its tests) importable on macOS/Linux, unlike
ui_automation.app.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from fakturama_automation.ui_automation.exceptions import DialogTimeoutError


def wait_until(
    condition: Callable[[], bool],
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.25,
) -> bool:
    """Poll condition() until it returns True or timeout_seconds elapses."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if condition():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_seconds)


def wait_for_dialog(app: Any, title_re: str, timeout_seconds: float = 5.0) -> Any:
    """Poll until a dialog matching title_re appears, or raise
    DialogTimeoutError.
    """
    dialog = app.window(title_re=title_re)
    if not wait_until(dialog.exists, timeout_seconds=timeout_seconds):
        raise DialogTimeoutError(f"no dialog matching {title_re!r} appeared within {timeout_seconds}s")
    return dialog


def wait_for_stable_row_count(
    get_row_count: Callable[[], int],
    stable_polls: int = 2,
    timeout_seconds: float = 5.0,
) -> int:
    """Poll get_row_count() until it returns the same value for
    stable_polls consecutive polls, or raise DialogTimeoutError.
    """
    deadline = time.monotonic() + timeout_seconds
    last_count: int | None = None
    consecutive = 0
    while True:
        count = get_row_count()
        if count == last_count:
            consecutive += 1
        else:
            last_count = count
            consecutive = 1
        if consecutive >= stable_polls:
            return count
        if time.monotonic() >= deadline:
            raise DialogTimeoutError(
                f"row count did not stabilize within {timeout_seconds}s (last count: {count})"
            )
        time.sleep(0.25)
