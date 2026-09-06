"""Exceptions raised by fakturama_automation.ui_automation.

These should generally propagate up to error_handling rather than being
swallowed locally.
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


class WindowFocusError(Exception):
    """Raised by controls.focus_foreground when a window cannot be brought
    to the OS foreground within its timeout.

    Matters because every grid read in this codebase is a screen-region
    screenshot: an occluded window is captured as whatever is on top of it,
    which reads as a perfectly plausible - and completely wrong - grid
    rather than as an error.
    """


class DialogTimeoutError(Exception):
    """Raised by waits.wait_for_dialog / waits.wait_for_stable_row_count
    when polling for an expected dialog or window state does not succeed
    within the bounded timeout.
    """
