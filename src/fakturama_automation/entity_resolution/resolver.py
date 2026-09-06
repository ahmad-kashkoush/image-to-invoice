"""Shared search-then-create resolution pattern.

Every entity resolver (debtor, product, VAT rate, payment method) follows
the same shape: search Fakturama for an exact match, return it if found,
create a new record only if none exists, and route an ambiguous search
(more than one exact match) to error_handling rather than picking one.
This module holds both halves:

- resolve_exact_or_create: the zero/one/many decision, pure w.r.t. the
  search_by/create callables it's given.
- search_grid_exact: the shared "search Fakturama's own UI" half each
  entity's search_by is built from.

debtor.py/product.py/vat_rate.py/payment_method.py compose both halves
with Fakturama's actual control identifiers (entity_resolution/config.py).
"""

from __future__ import annotations

import time
from typing import Any, Callable

from fakturama_automation.entity_resolution import config
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import controls, vision_grounding


def resolve_exact_or_create(
    search_by: Callable[[], list[Any]],
    create: Callable[[], Any],
    *,
    entity: str = "entity",
    step: str = "entity_resolution",
) -> Any:
    """Search for an exact match; create only if none exists.

    Calls search_by() once. Exactly one result is returned as-is. Zero
    results call create() and return its result. More than one result is a
    data problem (an "exact" search should never be ambiguous) and is not
    resolved by guessing: it raises ManualReviewRequired instead.

    `entity`/`step` are keyword-only context for the ManualReviewRequired
    reason (e.g. entity="debtor 'Acme GmbH'", step="resolve_debtor") so a
    manual reviewer sees which lookup was ambiguous, not just a bare count.
    """
    matches = search_by()
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return create()
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
    results grid re-render, then read its visible rows via
    ui_automation.vision_grounding.

    Fakturama's list/search result grids are SWT/NatTable canvases with no
    UIA-exposed rows. There's no UIA signal to poll for "the grid finished
    updating", so this uses a short, fixed settle delay instead of polling
    - a deliberate exception to this codebase's "poll, don't sleep" rule,
    since polling here would mean firing a vision API call per poll.

    The search Edit is found structurally (the "Search:" Text, then the
    Edit under its parent Pane), not by auto_id: this app's blank-named
    controls get a fresh auto_id on every process launch. The results
    grid's own container Pane has the same auto_id instability but a
    stable per-entity accessible name, so `grid_pane_name` locates it
    instead.

    The grid Pane is located FIRST, before the search box, even though it
    isn't read until the end. Callers reach here immediately after clicking
    a Navigation View item to switch lists, and that Pane is the only
    bounded-retry proof this list is the one actually on screen - "Search:"
    is not: several screens carry one (the Order editor has its own), so
    typing into whichever one happens to be exposed while the list is still
    coming up searches the wrong screen and reads an empty grid. Live
    consequence: a debtor that plainly existed came back as zero matches,
    the run went on to create it, and Fakturama itself caught the duplicate
    with a modal warning - which disabled the main window and turned the
    next set_text into a raw COMError.
    """
    grid_pane = controls.find_control(
        parent, "Pane", name=grid_pane_name, timeout_seconds=timeout_seconds
    )
    search_label = controls.find_control(parent, "Text", name="Search:", timeout_seconds=timeout_seconds)
    search_edit = controls.find_control(search_label.parent(), "Edit", timeout_seconds=timeout_seconds)
    search_edit.set_text(key)
    time.sleep(settle_seconds)

    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=vision_client)
