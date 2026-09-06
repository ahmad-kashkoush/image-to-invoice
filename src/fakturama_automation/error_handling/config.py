"""Configuration for error handling / manual review."""

from __future__ import annotations

import os

# README's shared "out" folder: order-image logs plus the manual review queue.
OUT_DIR = os.environ.get("FAKTURAMA_ERROR_HANDLING_OUT_DIR", "out")

# Single append-only JSONL file - see Doc/adr/0005-error-handling.md.
QUEUE_FILENAME = os.environ.get("FAKTURAMA_ERROR_HANDLING_QUEUE_FILE", "manual_review_queue.jsonl")
