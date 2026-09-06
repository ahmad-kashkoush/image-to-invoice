"""Fail-closed ComboBox option selection via vision-grounded reads.

Replaces guessed `ComboBox.select(...)` literals (product.py's VAT combo,
debtor.py's Country combo): probing the combos directly found the dropdown
popup renders as a single, childless `Pane` with no `ComboBoxItem`/
`ListItem` entries, and isn't even a descendant of the main window - so
there's no UIA element to read or select on at all.

Design decision (Doc/adr/0006): screenshot `main_window` itself right
after opening the combo (a screen-rect grab captures the dropdown overlay
too), then ask `ui_automation.vision_grounding.read_combo_options` to both
name and locate (a bounding box) each visible option, and click the
matched option's own screen coordinate instead of selecting it via UIA.

Selection is exact-match only, fail-closed: zero or more than one option
matching the target raises ManualReviewRequired naming every option the
dropdown actually offered, never guessing a format or picking the first hit.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.entity_resolution import config, matching
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import controls, vision_grounding
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
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    """Open `combo`'s dropdown and click the option whose VAT percent
    (parsed numerically via matching.parse_vat_text, so "19", "19.00", and
    "19,00 %" all match Decimal("19")) equals `vat_percent`.

    Raises ManualReviewRequired if no option, or more than one, matches.
    """
    options = _read_open_combo_options(main_window, combo, client=client, settle_seconds=settle_seconds)
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
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    """Open `combo`'s dropdown and click the option whose text equals
    `target` exactly (case-sensitive - the same "exact match only, never
    fuzzy" rule matching.exact_text_matches applies to grid rows).

    Raises ManualReviewRequired if no option, or more than one, matches -
    for example if `target` is a normalized country code ("DE") but the
    combo's real options are full country names ("Germany"): that's
    correctly treated as "no match", not silently skipped or guessed.
    """
    options = _read_open_combo_options(
        main_window, combo, client=client, type_ahead=target, settle_seconds=settle_seconds
    )
    match = pick_option(options, match=lambda text: text == target)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique option matching '{target}'; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_option(main_window, match)


def _read_open_combo_options(
    main_window: Any,
    combo: Any,
    *,
    client: Any,
    type_ahead: str | None = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> list[ComboOption]:
    """Open `combo` and screenshot it for the vision read.

    `type_ahead`, when given, is sent as keystrokes to the just-opened
    combo before the screenshot: the Country combo has ~200 alphabetically
    sorted options, far more than fit in the visible popup, and opens
    scrolled to the *currently selected* option, which can be nowhere near
    the target. The *full* target string is sent, not just its first
    letter - SWT's native type-ahead accumulates each keystroke into a
    running prefix match, so the whole word scrolls to (or very near) the
    exact target instead of merely the first same-letter option. Not
    needed for select_vat_option's short VAT list, so that caller passes
    None.

    `settle_seconds` sleeps once, right before the screenshot, after both
    the click and (if given) the type-ahead keystroke: capturing the
    dropdown mid-open/mid-scroll, before SWT finished painting it, produced
    garbage options in a live run (confirmed - not a vision model
    hallucination).
    """
    controls.focus(main_window)
    combo.click_input()
    if type_ahead:
        combo.type_keys(type_ahead)
    time.sleep(settle_seconds)
    image_bytes = vision_grounding.capture_control_image(main_window)
    return vision_grounding.read_combo_options(image_bytes, client=client)


def _click_option(main_window: Any, option: ComboOption) -> None:
    """Convert `option.bbox` (pixel coords within the main_window
    screenshot) to an absolute screen point (main_window's own top-left +
    the bbox's center) and click there.

    Assumes the screenshot's pixels map 1:1 to screen coordinates (no DPI
    scaling) - unverified until tried against a live window; see
    .claude/plans/entity-resolution-residual.md's "known limitations".

    Calls controls.focus(main_window) immediately before the click:
    omitting this let every product's VAT combo selection silently fail
    (confirmed live - the combo stayed on its prior value) since
    read_combo_options just above is a real network call, long enough for
    OS foreground focus to drift away from Fakturama in between.
    """
    controls.focus(main_window)
    bounds = main_window.rectangle()
    x, y, width, height = option.bbox
    screen_point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    main_window.click_input(coords=screen_point, absolute=True)
