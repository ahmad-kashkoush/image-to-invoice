"""Exceptions raised by fakturama_automation.ui_automation.

Section 3 (ui_automation). These should generally propagate up to
error_handling rather than being swallowed locally.
"""

from __future__ import annotations


class ControlNotFoundError(Exception):
    """Raised by controls.find_control when a control cannot be located
    within the bounded retry timeout.
    """


class AmbiguousControlError(Exception):
    """Raised by controls.find_control when more than one candidate
    control matches. This routes to error_handling rather than picking
    arbitrarily; resolving it means the caller passes a more specific
    parent, not that this gets retried.
    """


class DialogTimeoutError(Exception):
    """Raised by waits.wait_for_dialog / waits.wait_for_stable_row_count
    when polling for an expected dialog or window state does not succeed
    within the bounded timeout.
    """
