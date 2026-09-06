from __future__ import annotations

import pytest

from fakturama_automation.ui_automation.exceptions import DialogTimeoutError
from fakturama_automation.ui_automation.waits import wait_for_dialog, wait_for_stable_row_count, wait_until


class FakeDialog:
    def __init__(self, exists_after: int) -> None:
        self._calls = 0
        self._exists_after = exists_after

    def exists(self) -> bool:
        self._calls += 1
        return self._calls >= self._exists_after


class FakeApp:
    def __init__(self, dialog: FakeDialog) -> None:
        self._dialog = dialog

    def window(self, title_re: str):
        return self._dialog


# -- wait_until ---------------------------------------------------------


def test_wait_until_returns_true_once_condition_flips() -> None:
    calls = {"n": 0}

    def condition() -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    assert wait_until(condition, timeout_seconds=1.0, poll_interval_seconds=0.02) is True
    assert calls["n"] == 3


def test_wait_until_returns_false_on_timeout() -> None:
    assert wait_until(lambda: False, timeout_seconds=0.1, poll_interval_seconds=0.02) is False


# -- wait_for_dialog ------------------------------------------------------


def test_wait_for_dialog_returns_dialog_once_it_appears() -> None:
    dialog = FakeDialog(exists_after=2)
    result = wait_for_dialog(FakeApp(dialog), "Order", timeout_seconds=1.0)
    assert result is dialog


def test_wait_for_dialog_raises_timeout_when_dialog_never_appears() -> None:
    dialog = FakeDialog(exists_after=999)
    with pytest.raises(DialogTimeoutError):
        wait_for_dialog(FakeApp(dialog), "Order", timeout_seconds=0.3)


# -- wait_for_stable_row_count --------------------------------------------


def test_wait_for_stable_row_count_returns_once_stable() -> None:
    counts = iter([3, 5, 5, 5])

    def get_row_count() -> int:
        return next(counts)

    result = wait_for_stable_row_count(get_row_count, stable_polls=2, timeout_seconds=1.0)
    assert result == 5


def test_wait_for_stable_row_count_raises_timeout_if_never_stable() -> None:
    counter = {"n": 0}

    def get_row_count() -> int:
        counter["n"] += 1
        return counter["n"]  # always different, never stabilizes

    with pytest.raises(DialogTimeoutError):
        wait_for_stable_row_count(get_row_count, stable_polls=2, timeout_seconds=0.3)
