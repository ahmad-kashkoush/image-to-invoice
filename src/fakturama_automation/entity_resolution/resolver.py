"""Shared search-then-create resolution pattern.

Section 4 (entity_resolution). Every entity resolver (debtor, product, VAT
rate, payment method) follows the same shape: search Fakturama for an
exact match, return it if found, create a new record only if no exact
match exists. If the search is ambiguous (more than one exact match,
which should not happen but must be handled), route to error_handling
rather than picking one. This module holds both halves of that shape:

- resolve_exact_or_create: the zero/one/many decision, pure with respect
  to the search_by/create callables it's given.
- search_grid_exact: the shared "search Fakturama's own UI" half each
  entity's search_by is built from - type a key into a search box, read
  the (custom-rendered) results grid back via
  ui_automation.vision_grounding, and return its rows.

Despite composing ui_automation.controls/vision_grounding (which touch
live pywinauto/vision objects), this module never imports pywinauto
itself - callers pass in whatever duck-typed `parent`/`vision_client` they
hold - so it stays importable and unit-testable on macOS/Linux with fakes,
the same seam ui_automation.controls/waits already use (Doc/adr/0002).
debtor.py/product.py/vat_rate.py/payment_method.py compose both halves
with Fakturama's actual control identifiers (entity_resolution/config.py)
to implement each entity.
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
    search_edit_auto_id: str,
    grid_pane_auto_id: str,
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
    UIA-exposed rows (confirmed by probing every entity's list view -
    probes/probe-06-debitors.txt, probe-07-products.txt,
    probe-09-Payment.txt each show an empty results Pane). There is no UIA
    signal to poll for "the grid finished updating" the way
    ui_automation.waits.wait_for_stable_row_count does elsewhere, so this
    uses a short, fixed settle delay instead of polling - a deliberate,
    documented exception to this codebase's "poll, don't sleep" rule,
    justified because polling here would mean firing a vision API call per
    poll instead of once (see Doc/adr/0003-entity-resolution.md).

    `search_edit_auto_id`/`grid_pane_auto_id` select controls under
    `parent` by auto_id (controls.find_control) since these controls carry
    no accessible name in Fakturama's UI. `vision_client` is passed straight
    through to vision_grounding.read_grid_rows (injectable, defaults to a
    real anthropic.Anthropic() client there).
    """
    search_edit = controls.find_control(
        parent, "Edit", auto_id=search_edit_auto_id, timeout_seconds=timeout_seconds
    )
    search_edit.set_text(key)
    time.sleep(settle_seconds)

    grid_pane = controls.find_control(
        parent, "Pane", auto_id=grid_pane_auto_id, timeout_seconds=timeout_seconds
    )
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=vision_client)
