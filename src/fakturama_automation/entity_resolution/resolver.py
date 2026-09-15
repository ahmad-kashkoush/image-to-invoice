from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.parsing import parse_money_text, parse_percent_text
from fakturama_automation.ui_automation import readers
# Re-exported, not re-implemented: the four per-entity resolvers here call
# `resolver.search_grid_exact`, and it now lives a layer down so `verification`
# can read Data > Documents with the same mechanism without importing this
# package (they are peers - see Doc/adr/0009).
from fakturama_automation.ui_automation.list_grids import (  # noqa: F401
    open_list_screen,
    search_grid_exact,
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
