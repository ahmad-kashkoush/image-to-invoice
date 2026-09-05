"""CLI entry point: `python -m fakturama_automation.orchestrator <image_path>`.

Section 7 (orchestrator). Thin wrapper around run_workflow so a single
order image from the shared "in" folder (README.md's host/VM layout) can
be processed without importing the package programmatically.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from fakturama_automation.orchestrator.state_machine import run_workflow


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Run the Fakturama order-to-invoice workflow for a single order image."
    )
    parser.add_argument("image_path", type=Path, help="Path to the order image to process.")
    args = parser.parse_args()
    run_workflow(args.image_path)


if __name__ == "__main__":
    main()
