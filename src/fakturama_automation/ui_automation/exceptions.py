"""Exceptions raised by fakturama_automation.ui_automation.

Mechanical failures only - "the control isn't there", "the window never
appeared", "that screenshot doesn't measure as a grid". Whether a failure
means a human must look at the order is the workflow's decision, since only
it knows which step was running: state_machine converts every exception
below into a ManualReviewRequired named for the current state
(Doc/adr/0007 Decision 3).

These should propagate rather than being swallowed locally, except for the
bounded retries some callers wrap around a *read* - re-reading is safe in a
way re-writing is not.
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


class GridReadError(Exception):
    """Raised by vision_grounding when a grid or dropdown cannot be read
    back from its screenshot.

    Never degraded to an empty or partial row list: entity_resolution counts
    those rows to decide between matching and creating, so a failed read
    that looked like zero rows would create duplicates.
    """


class GridGeometryError(Exception):
    """Raised by grid_geometry when a grid screenshot cannot be measured:
    wrong column count, a scrolled view, no data area, uneven row pitch.

    Measuring wrongly is worse than not measuring: a click at a
    wrong-but-plausible coordinate types into the wrong cell exactly as
    convincingly as into the right one.
    """
