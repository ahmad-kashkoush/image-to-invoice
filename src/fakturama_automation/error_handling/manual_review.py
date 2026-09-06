"""Manual review queue handling.

The single stop point the orchestrator calls into whenever a
ManualReviewRequired is raised. Each call appends one JSON line to a single
queue file (`config.OUT_DIR`/`config.QUEUE_FILENAME`) - a human or future
tool can tail/parse it without per-entry file management. See
Doc/adr/0005-error-handling.md for the reasoning.

Never raises: a write failure (unwritable out_dir, serialization problem)
is caught and reported to stderr instead, since this is the terminal
handler for a workflow run.
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
