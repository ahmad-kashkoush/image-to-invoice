"""Exceptions that route the workflow to manual review.

Section 6 (error_handling). Any ambiguous match (entity_resolution) or
failed verification (verification) anywhere in the workflow should
ultimately surface as one of these, caught in one place by
manual_review.py rather than handled ad hoc at each call site.
"""

from __future__ import annotations


class ManualReviewRequired(Exception):
    """Raised when the workflow cannot safely proceed on its own and must
    stop for a human to look at it.

    Deliberately left carrying only step/reason for now: manual_review.py
    (Section 6) writes a useful entry from these two fields plus the
    source image path callers already pass separately. Attaching richer
    partial state (the NormalizedOrder, ambiguous candidates) here is
    deferred to TODo.md's Future work - manual_review.py already forwards
    a `details` attribute if a future caller sets one (see its docstring),
    so no signature change is needed here to add that later.
    """

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"{step}: {reason}")
