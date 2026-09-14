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

    options, origin = _read_open_combo_options(main_window, combo, client=client, settle_seconds=settle_seconds)
    match = pick_option(options, match=wanted)
    if match is None:
        raise ManualReviewRequired(
            step,
            f"no unique VAT option matching {vat_percent}%; options were "
            f"{[option.text for option in options]!r}",
        )
    _click_and_confirm(
        main_window, combo, match, origin, wanted=wanted, target=f"{vat_percent}%",
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

    options, origin = _read_open_combo_options(
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
        main_window, combo, match, origin, wanted=wanted, target=target,
        step=step, settle_seconds=settle_seconds,
    )


def _top_level_windows() -> list[Any]:
    # Windows-only, imported locally like every other OS-specific name in
    # ui_automation.controls (e.g. win32gui in controls.focus_foreground).
    from pywinauto import Desktop

    return list(Desktop(backend="uia").windows())


def _locate_open_popup(
    before_handles: set[int],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.05,
    stable_reads: int = 3,
) -> Any | None:
    # The popup a combo opens renders as a separate top-level window, not a
    # main_window descendant (Doc/adr/0006) - confirmed reliably locatable
    # this way, for both combo types this pipeline uses, by
    # spikes/uia_probe_combo_region.py
    # (probes/probe-13-combo-region-settle-{country,vat}.txt). Polls its
    # rectangle until it stops changing rather than sleeping a guess, since
    # this is a cheap local UIA read, not a vision API call (contrast
    # config.SEARCH_SETTLE_SECONDS's docstring, which avoids polling
    # specifically to avoid firing one of those per poll).
    #
    # Returns None if nothing new appears, or its rectangle never
    # stabilizes, within timeout_seconds - the caller falls back to the
    # whole-window capture ADR 0006 originally chose rather than fail
    # closed on what is a performance optimization, not a correctness one.
    deadline = time.monotonic() + timeout_seconds
    popup = None
    while popup is None and time.monotonic() < deadline:
        for window in _top_level_windows():
            if window.handle not in before_handles:
                popup = window
                break
        if popup is None:
            time.sleep(poll_interval_seconds)
    if popup is None:
        return None

    last_rect = None
    stable = 0
    while time.monotonic() < deadline:
        try:
            rect = popup.rectangle()
        except Exception:  # noqa: BLE001 - a torn-down popup falls back, it does not fail closed
            return None
        current = (rect.left, rect.top, rect.right, rect.bottom)
        if current == last_rect:
            stable += 1
            if stable >= stable_reads:
                return popup
        else:
            stable = 0
        last_rect = current
        time.sleep(poll_interval_seconds)
    return popup


def _read_open_combo_options(
    main_window: Any,
    combo: Any,
    *,
    client: Any,
    type_ahead: str | None = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> tuple[list[ComboOption], tuple[int, int]]:
    controls.focus(main_window)
    before_handles = {window.handle for window in _top_level_windows()}
    combo.click_input()
    if type_ahead:
        combo.type_keys(type_ahead)

    popup = _locate_open_popup(before_handles, timeout_seconds=config.COMBO_POPUP_SETTLE_TIMEOUT_SECONDS)
    if popup is None:
        time.sleep(settle_seconds)
        capture_target = main_window
    else:
        capture_target = popup

    # `origin` is the capture_target's own screen top-left: ComboOption.bbox
    # is relative to whatever image was actually captured, so the caller
    # must offset against that control's rectangle, not always
    # main_window's, now that the popup (when found) is captured directly
    # instead of the whole window.
    bounds = capture_target.rectangle()
    origin = (bounds.left, bounds.top)
    image_bytes = vision_grounding.capture_control_image(capture_target)
    options = vision_grounding.read_combo_options(image_bytes, client=client)
    return options, origin


def _click_and_confirm(
    main_window: Any,
    combo: Any,
    option: ComboOption,
    origin: tuple[int, int],
    *,
    wanted: Callable[[str], bool],
    target: str,
    step: str,
    settle_seconds: float,
) -> None:
    controls.focus(main_window)
    x, y, width, height = option.bbox
    screen_point = (origin[0] + x + width // 2, origin[1] + y + height // 2)
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
