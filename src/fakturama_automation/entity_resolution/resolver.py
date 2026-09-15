from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.parsing import parse_money_text, parse_percent_text
from fakturama_automation.ui_automation import (
    controls,
    grid_columns,
    locators,
    readers,
    vision_grounding,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SavedField:
    """One field to re-read after a save, and how to judge what comes back.

    `read` exists because several of these forms' fields have no accessible
    name: the Product price, and the Debtor ZIP/City and First/Last Name, are
    unnamed Edits reached through a label's sibling pane. Those cannot be
    found by `readers.read_field_text(name=...)`, so they supply their own
    reader, and `label` is then only what a failure message calls the field.
    """

    label: str
    expected: str
    compare: Callable[[str, str], bool]
    read: Callable[[Any], str] | None = None

    def read_actual(self, main_window: Any) -> str:
        if self.read is not None:
            return self.read(main_window)
        return readers.read_field_text(main_window, name=self.label)


def text_matches(expected: str, actual: str) -> bool:
    return expected.strip() == actual.strip()


def percent_matches(expected: str, actual: str) -> bool:
    # Numeric, not textual: Fakturama re-renders what was typed into a percent
    # field, so the text that comes back is not the text that went in.
    parsed = parse_percent_text(actual)
    return parsed is not None and parsed == parse_percent_text(expected)


def money_matches(expected: str, actual: str) -> bool:
    # Numeric for the same reason percent_matches is, and then some: a money
    # field reads back grouped, currency-suffixed and in the app's own locale
    # ("29.750,00 EUR"), so string comparison is meaningless. Comparing the
    # parsed numbers is what catches a separator the field read differently
    # than it was meant - the 100x bug of 2026-09-15.
    parsed = parse_money_text(actual)
    return parsed is not None and parsed == parse_money_text(expected)


def resolve_exact_or_create(
    search_by: Callable[[], list[ResolvedEntity]],
    create: Callable[[], ResolvedEntity],
    *,
    entity: str = "entity",
    step: str = "entity_resolution",
) -> ResolvedEntity:
    matches = search_by()
    if len(matches) == 1:
        logger.info("matched existing %s", entity)
        return matches[0]
    if not matches:
        logger.info("no exact match for %s - creating it", entity)
        created = create()
        logger.info("created %s", entity)
        return created
    raise ManualReviewRequired(
        step, f"{len(matches)} exact matches for {entity}; expected at most one"
    )


def search_grid_exact(
    parent: Any,
    *,
    grid_pane_name: str,
    key: str,
    columns: list[str],
    vision_client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> list[dict[str, str]]:
    grid_pane = controls.find_control(
        parent, "Pane", name=grid_pane_name, timeout_seconds=timeout_seconds
    )
    label = locators.search_label(parent, timeout_seconds=timeout_seconds)
    controls.set_text(locators.search_edit(label, timeout_seconds=timeout_seconds), key)
    time.sleep(settle_seconds)

    def read_rows() -> list[dict[str, str]]:
        return vision_grounding.read_grid_rows(
            vision_grounding.capture_control_image(grid_pane), columns=columns, client=vision_client
        )

    rows = read_rows()
    # A column too narrow for its content renders clipped ("Northstar
    # Offic..."), and every comparison built on these rows is exact equality,
    # so a clipped cell can never match and the caller creates a duplicate
    # instead. Widths are persisted per profile, so this depends on saved UI
    # layout rather than on the data - it is why the same order matched on one
    # profile and duplicated on another. Widen once and re-read; if it is
    # still clipped the rows are returned as they are and the exact-match
    # comparison fails closed, which is the pre-existing behaviour.
    clipped = _clipped_columns(rows, columns)
    if clipped:
        logger.info("%s column(s) render clipped in this grid - widening: %s", len(clipped), clipped)
        # Once, not once per clipped column: a drag here widens every column
        # at the same time, so a second drag only eats the space the far
        # columns need to stay on screen.
        widened = grid_columns.widen_column(
            grid_pane,
            column_index=columns.index(clipped[0]),
            by_pixels=config.COLUMN_WIDEN_PIXELS,
            expected_columns=len(columns),
        )
        if widened:
            controls.focus_foreground(parent)
            controls.move_pointer_away(parent)
            time.sleep(settle_seconds)
            rows = read_rows()
    return rows


def _clipped_columns(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    return [
        column
        for column in columns
        if any(grid_columns.is_clipped(row.get(column, "")) for row in rows)
    ]


def verify_saved_fields(
    main_window: Any,
    fields: Sequence[SavedField],
    *,
    entity: str,
    step: str,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # Creating master data was the one mutation here with no verification, and
    time.sleep(settle_seconds)
    problems = [
        f"{field.label}: expected '{field.expected}', the saved form shows '{actual}'"
        for field in fields
        for actual in [field.read_actual(main_window)]
        if not field.compare(field.expected, actual)
    ]
    if problems:
        raise ManualReviewRequired(
            step, f"{entity} did not save correctly: " + "; ".join(problems)
        )
