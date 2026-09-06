"""CLI entry point: `python -m fakturama_automation.orchestrator <image_path>`.

Thin wrapper around run_workflow, reporting the outcome on the process exit
code. run_workflow routes a ManualReviewRequired to the queue and returns
the state it stopped at rather than raising, so without this the shell could
not tell a completed run from one that stopped: both exited 0 and printed
nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from fakturama_automation.error_handling import config as error_config
from fakturama_automation.orchestrator.state_machine import WorkflowState, run_workflow

EXIT_OK = 0
EXIT_MANUAL_REVIEW = 1


def main() -> int:
    """Run the workflow for one image. Returns the process exit code."""
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Run the Fakturama order-to-invoice workflow for a single order image."
    )
    parser.add_argument("image_path", type=Path, help="Path to the order image to process.")
    args = parser.parse_args()

    final_state = run_workflow(args.image_path)

    if final_state is WorkflowState.DONE:
        print(f"DONE: {args.image_path} - Order and linked Invoice saved and verified.")
        return EXIT_OK

    queue_path = Path(error_config.OUT_DIR) / error_config.QUEUE_FILENAME
    print(
        f"STOPPED for manual review at step '{final_state.value}' while processing "
        f"{args.image_path}.\nThe reason was appended to {queue_path}.",
        file=sys.stderr,
    )
    return EXIT_MANUAL_REVIEW


if __name__ == "__main__":
    sys.exit(main())
