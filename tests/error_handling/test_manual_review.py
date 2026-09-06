from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.error_handling.manual_review import route_to_manual_review

SOURCE_IMAGE_PATH = "/orders/WEB-2026-0714-A17.png"


def _fixed_now() -> datetime:
    return datetime(2026, 9, 5, 14, 3, 22)


def test_writes_one_jsonl_line_with_expected_fields(tmp_path: Path) -> None:
    error = ManualReviewRequired("normalization", "debtor company name missing; line 1 total mismatch")

    route_to_manual_review(error, SOURCE_IMAGE_PATH, out_dir=tmp_path, now=_fixed_now)

    queue_path = tmp_path / "manual_review_queue.jsonl"
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry == {
        "timestamp": "2026-09-05T14:03:22",
        "source_image_path": SOURCE_IMAGE_PATH,
        "step": "normalization",
        "reason": "debtor company name missing; line 1 total mismatch",
    }


def test_two_calls_append_two_lines_not_overwrite(tmp_path: Path) -> None:
    route_to_manual_review(
        ManualReviewRequired("normalization", "first failure"),
        SOURCE_IMAGE_PATH,
        out_dir=tmp_path,
        now=_fixed_now,
    )
    route_to_manual_review(
        ManualReviewRequired("save_and_verify_order", "second failure"),
        SOURCE_IMAGE_PATH,
        out_dir=tmp_path,
        now=_fixed_now,
    )

    queue_path = tmp_path / "manual_review_queue.jsonl"
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["step"] == "normalization"
    assert json.loads(lines[1])["step"] == "save_and_verify_order"


def test_creates_out_dir_if_missing(tmp_path: Path) -> None:
    out_dir = tmp_path / "nested" / "out"
    assert not out_dir.exists()

    route_to_manual_review(
        ManualReviewRequired("entity_resolution", "ambiguous debtor match"),
        SOURCE_IMAGE_PATH,
        out_dir=out_dir,
        now=_fixed_now,
    )

    assert (out_dir / "manual_review_queue.jsonl").exists()


def test_unwritable_out_dir_does_not_raise(tmp_path: Path, capsys) -> None:
    # A regular file where a directory is expected: mkdir(parents=True)
    # fails with FileExistsError/NotADirectoryError depending on platform -
    # either way route_to_manual_review must swallow it, not propagate.
    blocked_path = tmp_path / "blocked"
    blocked_path.write_text("not a directory", encoding="utf-8")

    result = route_to_manual_review(
        ManualReviewRequired("payment_verification", "payment date invented"),
        SOURCE_IMAGE_PATH,
        out_dir=blocked_path,
        now=_fixed_now,
    )

    assert result is None
    captured = capsys.readouterr()
    assert "payment_verification" in captured.err


def test_details_attribute_is_forwarded_when_present(tmp_path: Path) -> None:
    error = ManualReviewRequired("verification", "total mismatch")
    error.details = {"expected_total": "570.00", "actual_total": "560.00"}

    route_to_manual_review(error, SOURCE_IMAGE_PATH, out_dir=tmp_path, now=_fixed_now)

    entry = json.loads((tmp_path / "manual_review_queue.jsonl").read_text(encoding="utf-8"))
    assert entry["details"] == {"expected_total": "570.00", "actual_total": "560.00"}


def test_plain_error_without_details_omits_the_key(tmp_path: Path) -> None:
    error = ManualReviewRequired("verification", "total mismatch")

    route_to_manual_review(error, SOURCE_IMAGE_PATH, out_dir=tmp_path, now=_fixed_now)

    entry = json.loads((tmp_path / "manual_review_queue.jsonl").read_text(encoding="utf-8"))
    assert "details" not in entry
