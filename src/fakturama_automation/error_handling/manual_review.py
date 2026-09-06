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
