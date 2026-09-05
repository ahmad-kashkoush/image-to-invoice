"""Manual review queue handling.

Section 6 (error_handling). This is the single stop point the orchestrator
should call into whenever a ManualReviewRequired is raised, from
entity_resolution ambiguity or a failed fakturama_automation.verification.

Implementation: each call appends one JSON object as a line to a single
queue file (`config.OUT_DIR`/`config.QUEUE_FILENAME`, the README's shared
"out" folder) - simplest durable, reviewable record; a human (or a future
tool) can `tail`/parse the file without per-entry file management. An entry
holds a timestamp, the source image path, and the failed step/reason -
everything the current route_to_manual_review(error, source_image_path)
signature can reach. ManualReviewRequired itself carries no richer partial
state yet (its own TODO invited extending it); if a caller does attach a
`details` attribute in the future, it is included automatically via
getattr below, so this function will not need to change again for that.
See Doc/adr/0005-error-handling.md for the reasoning, including what was
deferred (a `details` payload on the exception, a Decimal/date-aware
encoder for partial order state) to TODo.md's Future work.

route_to_manual_review is the terminal handler for a workflow run: it must
never raise. Any failure while writing the entry (an unwritable out_dir,
a serialization problem) is caught and reported to stderr as a last
resort instead of propagating, since there is nowhere further for this
function to route a failure of its own.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.error_handling import config


def route_to_manual_review(
    error: ManualReviewRequired,
    source_image_path: str,
    *,
    out_dir: str | Path | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> None:
    """Record error against source_image_path in the manual review queue.

    Appends one JSON line to `<out_dir>/<config.QUEUE_FILENAME>` (out_dir
    defaults to config.OUT_DIR). Never raises: a write failure is reported
    to stderr rather than propagated, since this is the terminal handler
    for a workflow run.
    """
    try:
        entry: dict[str, object] = {
            "timestamp": now().isoformat(timespec="seconds"),
            "source_image_path": source_image_path,
            "step": error.step,
            "reason": error.reason,
        }
        details = getattr(error, "details", None)
        if details:
            entry["details"] = details

        queue_dir = Path(out_dir) if out_dir is not None else Path(config.OUT_DIR)
        queue_dir.mkdir(parents=True, exist_ok=True)
        queue_path = queue_dir / config.QUEUE_FILENAME
        with queue_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:  # noqa: BLE001 - deliberate: this handler must not raise
        print(
            f"error_handling.manual_review: failed to record entry "
            f"(step={getattr(error, 'step', '?')!r}, "
            f"source_image_path={source_image_path!r}): {exc!r}",
            file=sys.stderr,
        )
