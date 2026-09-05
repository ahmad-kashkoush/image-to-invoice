"""Configuration for error handling / manual review.

Section 6 (error_handling). Kept deliberately small and env-driven,
mirroring extraction/config.py, normalization/config.py, and
verification/config.py, so the queue location can change without touching
manual_review.py and tests can override it without mutating global state
(manual_review.route_to_manual_review also accepts an `out_dir` argument
directly for that reason).
"""

from __future__ import annotations

import os

# The shared "out" folder from README's host/VM layout (an in folder for
# order images, an out folder for logs and the manual review queue).
OUT_DIR = os.environ.get("FAKTURAMA_ERROR_HANDLING_OUT_DIR", "out")

# A single append-only JSONL file: one manual-review entry per line. See
# Doc/adr/0005-error-handling.md for why this was chosen over per-entry
# files.
QUEUE_FILENAME = os.environ.get("FAKTURAMA_ERROR_HANDLING_QUEUE_FILE", "manual_review_queue.jsonl")
