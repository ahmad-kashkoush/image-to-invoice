from __future__ import annotations

import time
from typing import Any, Callable

from fakturama_automation.ui_automation.exceptions import DialogTimeoutError


def wait_until(
    condition: Callable[[], bool],
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.25,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if condition():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_seconds)


def wait_for_dialog(app: Any, title_re: str, timeout_seconds: float = 5.0) -> Any:
    dialog = app.window(title_re=title_re)
    if not wait_until(dialog.exists, timeout_seconds=timeout_seconds):
        raise DialogTimeoutError(f"no dialog matching {title_re!r} appeared within {timeout_seconds}s")
    return dialog


def wait_for_stable_row_count(
    get_row_count: Callable[[], int],
    stable_polls: int = 2,
    timeout_seconds: float = 5.0,
) -> int:
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
