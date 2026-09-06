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
    # Case-sensitive: if `target` is a country code ("DE") but the combo offers
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
