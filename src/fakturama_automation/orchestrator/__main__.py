"""CLI entry point: `python -m fakturama_automation.orchestrator <image_path>`.

Thin wrapper around the state machine, reporting the outcome on the process
exit code. run_workflow routes a ManualReviewRequired to the queue and
returns the state it stopped at rather than raising, so without this the
shell could not tell a completed run from one that stopped: both exited 0
and printed nothing.

`--dry-run` stops after normalization and prints the record, which is the
whole pipeline up to the point Fakturama is needed - so a change to
extraction or normalization can be checked in a second, on any machine,
without a VM or an open application.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from fakturama_automation.error_handling import config as error_config
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.orchestrator.state_machine import (
    WorkflowState,
    extract_and_normalize,
    run_workflow,
)
from fakturama_automation.verification.comparisons import order_level_totals

EXIT_OK = 0
EXIT_MANUAL_REVIEW = 1


def main() -> int:
    """Run the workflow for one image. Returns the process exit code."""
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Run the Fakturama order-to-invoice workflow for a single order image."
    )
    parser.add_argument("image_path", type=Path, help="Path to the order image to process.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and normalize only, print the record, and stop before touching Fakturama.",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Only report the outcome, not each step."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    if args.dry_run:
        return _dry_run(args.image_path)

    final_state = run_workflow(args.image_path)

    if final_state is WorkflowState.DONE:
        print(f"DONE: {args.image_path} - Order and linked Invoice saved and verified.")
        return EXIT_OK
    return _report_stopped(args.image_path, final_state.value)


def _dry_run(image_path: Path) -> int:
    """Extract and normalize, print what the run would have entered, stop."""
    try:
        order = extract_and_normalize(image_path)
    except ManualReviewRequired as error:
        return _report_stopped(image_path, error.step, reason=error.reason)
    print(_summarize(order))
    return EXIT_OK


def _report_stopped(image_path: Path, step: str, *, reason: str | None = None) -> int:
    queue_path = Path(error_config.OUT_DIR) / error_config.QUEUE_FILENAME
    message = f"STOPPED for manual review at step '{step}' while processing {image_path}."
    # A dry run never reaches the queue writer, so it carries its own reason.
    message += f"\n{reason}" if reason else f"\nThe reason was appended to {queue_path}."
    print(message, file=sys.stderr)
    return EXIT_MANUAL_REVIEW


def _summarize(order: NormalizedOrder) -> str:
    """The normalized record as a few readable lines - what a dry run is
    for, and the same figures verification will compare against the UI.
    """
    net_total, vat_total, gross_total = order_level_totals(order)
    lines = [
        f"Order date        {order.order_date}",
        f"Cust.Ref.         {order.external_reference}",
        f"Debtor            {order.debtor_company_name}",
        f"Contact           {order.contact_name}",
        f"Billing address   {_one_line(order)}",
        f"Payment           {order.payment_method} / {order.payment_status}"
        f"{f' on {order.payment_date}' if order.payment_date else ''}"
        f"  (paid={order.is_paid})",
        "",
        f"{'SKU':<16}{'Qty':>6}{'U.Price':>12}{'VAT%':>7}{'Disc%':>7}{'Net':>12}",
    ]
    for item in order.line_items:
        lines.append(
            f"{item.sku:<16}{item.quantity:>6}{item.unit_net_price:>12}"
            f"{item.vat_percent:>7}{item.discount:>7}{item.recomputed_total:>12}"
        )
    lines += [
        "",
        f"{'Net total':<16}{net_total:>44}",
        f"{'VAT':<16}{vat_total:>44}",
        f"{'Gross total':<16}{gross_total:>44}",
    ]
    return "\n".join(lines)


def _one_line(order: NormalizedOrder) -> str:
    address = order.billing_address
    parts = [address.street, f"{address.postal_code} {address.city}".strip(), address.country]
    return ", ".join(part for part in parts if part)


if __name__ == "__main__":
    sys.exit(main())
