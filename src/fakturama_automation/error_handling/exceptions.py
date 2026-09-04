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

    TODO(section 6): carry enough context (which step, what was
    ambiguous or failed, and the relevant order/line identifiers) for
    manual_review.py to write a useful entry to the review queue.
    """

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"{step}: {reason}")
