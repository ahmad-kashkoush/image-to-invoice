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

The click is then verified by reading the combo back, because clicking a
coordinate derived from a screenshot assumes those pixels map 1:1 to screen
coordinates - which is false under DPI scaling, and would leave the combo
silently on its previous value. This was the last mutation in the codebase
with no act/verify pair.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.entity_resolution import config
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.parsing import parse_percent_text
from fakturama_automation.ui_automation import controls, readers, vision_grounding
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
    (parsed numerically, so "19", "19.00" and "19,00 %" all match
    Decimal("19")) equals `vat_percent`.

    Raises ManualReviewRequired if no option, or more than one, matches.
    """
    def wanted(text: str) -> bool:
        return parse_percent_text(text) == vat_percent

    options = _read_open_combo_options(main_window, combo, client=client, settle_seconds=settle_seconds)
    match = pick_option(options, match=wanted)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique VAT option matching {vat_percent}%; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_and_confirm(
        main_window, combo, match, wanted=wanted, target=f"{vat_percent}%",
        step=step, settle_seconds=settle_seconds,
    )


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
    def wanted(text: str) -> bool:
        return text == target

    options = _read_open_combo_options(
        main_window, combo, client=client, type_ahead=target, settle_seconds=settle_seconds
    )
    match = pick_option(options, match=wanted)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique option matching '{target}'; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_and_confirm(
        main_window, combo, match, wanted=wanted, target=target,
        step=step, settle_seconds=settle_seconds,
    )


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


def _click_and_confirm(
    main_window: Any,
    combo: Any,
    option: ComboOption,
    *,
    wanted: Callable[[str], bool],
    target: str,
    step: str,
    settle_seconds: float,
) -> None:
    """Click the matched option, then read the combo back and confirm
    it took.

    The click converts `option.bbox` (pixel coords within the main_window
    screenshot) to an absolute screen point, which assumes those pixels map
    1:1 to screen coordinates - false under DPI scaling, and a mis-scaled
    click lands somewhere harmless and leaves the combo on its previous
    value with nothing raised. The read-back is what turns that from a
    silent wrong result into a stop.

    It is verified with the same predicate that chose the option, so the
    check means "the combo now holds something satisfying what was asked
    for" rather than assuming the widget echoes the dropdown row verbatim.

    controls.focus(main_window) immediately before the click: omitting it
    let every product's VAT selection silently fail (confirmed live), since
    the vision read beforehand is a real network call, long enough for OS
    foreground focus to drift away from Fakturama.
    """
    controls.focus(main_window)
    bounds = main_window.rectangle()
    x, y, width, height = option.bbox
    screen_point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    main_window.click_input(coords=screen_point, absolute=True)

    time.sleep(settle_seconds)
    selected = readers.field_value(combo)
    if not wanted(selected):
        raise ManualReviewRequired(
            step,
            f"selected the '{option.text}' option for {target}, but the combo reads back as "
            f"'{selected}' - the click did not take (screenshot pixels may not map 1:1 to "
            "screen coordinates under DPI scaling)",
        )
