"""Fail-closed ComboBox option selection via vision-grounded reads.

Section 4 residual (entity_resolution). Replaces the two guessed
`ComboBox.select(...)` literals (product.py's VAT combo, debtor.py's
Country combo) that were never confirmed against Fakturama's real dropdown
contents (Doc/adr/0003, Consequences). Probing the combos directly
(probes/probe-11-product-vat-combo-open.txt,
probes/probe-12-debito-country-combo-open.txt, captured with each
dropdown actually open) found the popup renders as a single, childless
`Pane` - no `ComboBoxItem`/`ListItem` entries, the same UIA-opacity
signature the list grids have - and, unlike the list grids, that popup
did not appear to be a descendant of the main window at all, so
`controls.find_control(main_window, ...)` can't even locate it to read
its `.texts()`.

Design decision (Doc/adr/0006): rather than chase a handle to that
detached popup, this module screenshots `main_window` itself right after
opening the combo. `capture_as_image()` is a screen-rect grab, not a UIA
tree walk, so it captures whatever is drawn on screen within that
rectangle - including the dropdown overlay, which renders on top of (and
normally within the bounds of) the main window. `ui_automation.
vision_grounding.read_combo_options` then asks the vision model to both
name and locate (a bounding box) each visible option, mirroring how
`read_grid_rows` already reads UIA-invisible grid rows - the bbox is the
one extra thing needed here, since there's no UIA element left to
`.select()`: the matched option is instead clicked at its own screen
coordinate (`main_window`'s rectangle + the bbox).

Selection is exact-match only, fail-closed (CLAUDE.md): zero or more than
one option matching the target raises ManualReviewRequired naming every
option the dropdown actually offered, never guessing a format or picking
the first hit - the same shape entity_resolution.matching's row filters
already use for grid rows.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.entity_resolution import matching
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import vision_grounding
from fakturama_automation.ui_automation.vision_grounding import ComboOption


def pick_option(options: list[ComboOption], *, match: Callable[[str], bool]) -> ComboOption | None:
    """Return the single option whose text satisfies `match`, or None if
    zero or more than one do.

    Pure - no UI, no network - so the zero/one/many counting is unit
    tested directly against plain ComboOption lists.
    """
    hits = [option for option in options if match(option.text)]
    return hits[0] if len(hits) == 1 else None


def select_vat_option(
    main_window: Any,
    combo: Any,
    vat_percent: Decimal,
    *,
    client: Any = None,
    step: str = "entity_resolution.select_vat_option",
) -> None:
    """Open `combo`'s dropdown and click the option whose VAT percent
    (parsed numerically via matching.parse_vat_text, so "19", "19.00", and
    "19,00 %" all match Decimal("19")) equals `vat_percent`.

    Raises ManualReviewRequired if no option, or more than one, matches.
    """
    options = _read_open_combo_options(main_window, combo, client=client, step=step)
    match = pick_option(options, match=lambda text: matching.parse_vat_text(text) == vat_percent)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique VAT option matching {vat_percent}%; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_option(main_window, match)


def select_exact_option(
    main_window: Any,
    combo: Any,
    target: str,
    *,
    client: Any = None,
    step: str = "entity_resolution.select_exact_option",
) -> None:
    """Open `combo`'s dropdown and click the option whose text equals
    `target` exactly (case-sensitive - the same "exact match only, never
    fuzzy" rule matching.exact_text_matches applies to grid rows).

    Raises ManualReviewRequired if no option, or more than one, matches -
    for example if `target` is a normalized country code ("DE") but the
    combo's real options are full country names ("Germany"): that's
    correctly treated as "no match", not silently skipped or guessed.
    """
    options = _read_open_combo_options(main_window, combo, client=client, step=step)
    match = pick_option(options, match=lambda text: text == target)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique option matching '{target}'; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_option(main_window, match)


def _read_open_combo_options(main_window: Any, combo: Any, *, client: Any, step: str) -> list[ComboOption]:
    combo.click_input()
    image_bytes = vision_grounding.capture_control_image(main_window)
    return vision_grounding.read_combo_options(image_bytes, client=client, step=step)


def _click_option(main_window: Any, option: ComboOption) -> None:
    """Convert `option.bbox` (pixel coords within the main_window
    screenshot) to an absolute screen point (main_window's own top-left +
    the bbox's center) and click there.

    Assumes the screenshot's pixels map 1:1 to screen coordinates (no DPI
    scaling) - unverified until tried against a live window; see
    .claude/plans/entity-resolution-residual.md's "known limitations".
    """
    bounds = main_window.rectangle()
    x, y, width, height = option.bbox
    screen_point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    main_window.click_input(coords=screen_point, absolute=True)
