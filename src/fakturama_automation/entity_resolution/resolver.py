"""Shared search-then-create resolution pattern.

Every entity resolver (debtor, product, VAT rate, payment method) follows
the same shape: search Fakturama for an exact match, return it if found,
create a new record only if none exists, route an ambiguous search to
manual review rather than picking one - and, once created, read the record
back to confirm the save actually took.

This module holds the parts that are the same for all four:

- resolve_exact_or_create: the zero/one/many decision, pure w.r.t. the
  search_by/create callables it is given.
- search_grid_exact: the "search Fakturama's own UI" half each entity's
  search_by is built from.
- verify_saved_fields: the read-back each create half ends with.
"""

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
    """Trimmed exact comparison - the same exact-match-only rule the search
    half applies to grid rows.
    """
    return expected.strip() == actual.strip()


def percent_matches(expected: str, actual: str) -> bool:
    """Numeric comparison for a percent field, so "19", "19.00" and "19 %"
    all agree. Fakturama re-renders what was typed into these, so the text
    that comes back is not necessarily the text that went in.
    """
    parsed = parse_percent_text(actual)
    return parsed is not None and parsed == parse_percent_text(expected)


def resolve_exact_or_create(
    search_by: Callable[[], list[ResolvedEntity]],
    create: Callable[[], ResolvedEntity],
    *,
    entity: str = "entity",
    step: str = "entity_resolution",
) -> ResolvedEntity:
    """Search for an exact match; create only if none exists.

    Calls search_by() once. Exactly one result is returned as-is. Zero
    results call create(). More than one is a data problem - an "exact"
    search should never be ambiguous - and is not resolved by guessing: it
    raises ManualReviewRequired instead.

    `entity`/`step` are context for that failure (e.g. entity="debtor 'Acme
    GmbH'", step="resolve_debtor") so a reviewer sees which lookup was
    ambiguous, not just a bare count - and they name the record in the log
    line below.
    """
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
    """Type `key` into a search Edit, let Fakturama's custom-rendered
    results grid re-render, then read its visible rows.

    Those grids are SWT/NatTable canvases with no UIA-exposed rows, and
    there is no UIA signal to poll for "the grid finished updating", so
    this uses a short fixed settle delay - a deliberate exception to this
    codebase's "poll, don't sleep" rule, since polling would fire a vision
    API call per poll.

    The search Edit is found structurally (ui_automation.locators), not by
    auto_id: this app's blank-named controls get a fresh auto_id on every
    process launch. The results grid's own container Pane has the same
    instability but a stable per-entity accessible name, so `grid_pane_name`
    locates it instead.

    The grid Pane is located FIRST, before the search box, even though it
    isn't read until the end. Callers reach here immediately after clicking
    a Navigation View item to switch lists, and that Pane is the only
    bounded-retry proof this list is the one actually on screen - "Search:"
    is not: several screens carry one, so typing into whichever happens to
    be exposed while the list is still coming up searches the wrong screen
    and reads an empty grid. Live consequence: a debtor that plainly existed
    came back as zero matches, the run created it, and Fakturama caught the
    duplicate with a modal that disabled the main window.
    """
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
    """Read a just-saved record's own form back and fail closed if any
    field did not persist as intended.

    Creating master data was the one mutation in this system with no
    verification, and it is the one that cost the most. `_create_vat_rate`
    silently saved Value as "0%" for every rate because that field comes
    pre-filled and was being typed into rather than replaced; the resolver
    could then never find its own records, so it created a fresh duplicate
    on every run, and the product catalog degraded until the "Select a
    product" picker misbehaved. The visible symptom - an order line added
    three times - was several layers away from the cause. Four lines of
    read-back here would have caught it at the source.

    Controls are re-found by name rather than reusing the references the
    create form filled: a save can rebuild the form's widget tree, and a
    stale wrapper reads a value that is no longer on screen. Confirmed live
    that a saved record's own editor stays open and readable - that is how
    the Company-field persistence bug was isolated in the first place.
    """
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
