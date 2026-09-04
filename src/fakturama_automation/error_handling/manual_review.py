"""Manual review queue handling.

Section 6 (error_handling). This is the single stop point the orchestrator
should call into whenever a ManualReviewRequired is raised, from
entity_resolution ambiguity or a failed fakturama_automation.verification.

TODO(section 6): implement writing a manual review queue entry (per the
README's shared folder layout: an out folder for logs and the manual
review queue) with enough detail to act on: the source image, the step
that failed, the reason, and whatever partial state exists so far.
"""

from __future__ import annotations

from fakturama_automation.error_handling.exceptions import ManualReviewRequired


def route_to_manual_review(error: ManualReviewRequired, source_image_path: str) -> None:
    """Record error against source_image_path in the manual review queue.

    TODO(section 6): implement. This should not raise further; it is the
    terminal handler for the workflow run.
    """
    raise NotImplementedError
