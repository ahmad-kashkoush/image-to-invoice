from __future__ import annotations

import logging
import time
from typing import Any, Callable, Sequence

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.parsing import parse_percent_text
from fakturama_automation.ui_automation import controls, locators, readers, vision_grounding

logger = logging.getLogger(__name__)

# A saved field's expected value and how to compare it with what the form
# reads back: (control name, expected text, comparison).
SavedField = tuple[str, str, Callable[[str, str], bool]]


def text_matches(expected: str, actual: str) -> bool:
    return expected.strip() == actual.strip()


def percent_matches(expected: str, actual: str) -> bool:
    # Numeric, not textual: Fakturama re-renders what was typed into a percent
    # field, so the text that comes back is not the text that went in.
    parsed = parse_percent_text(actual)
    return parsed is not None and parsed == parse_percent_text(expected)


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
    locators.search_edit(label, timeout_seconds=timeout_seconds).set_text(key)
    time.sleep(settle_seconds)

    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=vision_client)


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
        f"{name}: expected '{expected}', the saved form shows '{actual}'"
        for name, expected, compare in fields
        for actual in [readers.read_field_text(main_window, name=name)]
        if not compare(expected, actual)
    ]
    if problems:
        raise ManualReviewRequired(
            step, f"{entity} did not save correctly: " + "; ".join(problems)
        )
