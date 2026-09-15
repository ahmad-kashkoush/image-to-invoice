from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.entity_resolution import config
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.parsing import parse_percent_text
from fakturama_automation.ui_automation import controls, readers

# Both combos here are selected through UIA (`combo.select(text)`), not by
# clicking a vision-located pixel. ADR 0006 reached for vision because the
# popup a combo opens is a separate top-level window with an empty UIA
# subtree, so its options cannot be *read* from the tree - which is true, and
# still is. What it did not check is that the options can be *selected* by
# name anyway: the items are virtualized, and pywinauto's ComboBoxWrapper
# finds them through the ItemContainer pattern without them ever appearing as
# children. Live on 2026-09-15: the Debtor Country combo reports
# item_count()==252 with zero descendants, and select("Germany") lands
# correctly every time.
#
# Vision grounding was removed because it was measurably wrong in both
# capture modes (see probes/probe-14-combo-vat-read.txt): cropped to the
# popup (ADR 0013) the image is 66x27px and the model returns no options at
# all; captured whole-window (ADR 0006) it reads the text but returns a bbox
# ~130px off, which is what selected 'Ghana' for 'Germany' on 2026-09-14.
#
# `select()` fails loudly - IndexError, with the combo's value unchanged - so
# an option that is not there routes to manual review instead of silently
# selecting a neighbour. The read-back check below is kept regardless: it is
# the guarantee that the selection actually took, and it is the one part of
# the old implementation that was always doing its job.


def select_vat_option(
    main_window: Any,
    combo: Any,
    vat_percent: Decimal,
    *,
    step: str = "entity_resolution.select_vat_option",
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # `f"{vat_percent}%"` is not a guessed rendering: it is the exact string
    # entity_resolution/vat_rate.py writes into the VAT Name field when it
    # creates a rate, and the identity it returns for one it matched. A rate
    # stored under some other spelling is resolve_vat_rate's problem to
    # surface, not this function's to paper over.
    option_text = f"{vat_percent}%"

    def wanted(text: str) -> bool:
        return parse_percent_text(text) == vat_percent

    _select_and_confirm(
        main_window,
        combo,
        option_text,
        wanted=wanted,
        target=f"{vat_percent}%",
        step=step,
        settle_seconds=settle_seconds,
    )


def select_exact_option(
    main_window: Any,
    combo: Any,
    target: str,
    *,
    step: str = "entity_resolution.select_exact_option",
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # Case-sensitive and exact: if `target` is a country code ("DE") but the
    # combo offers full names ("Germany"), select() raises and this fails
    # closed rather than picking something that looks close. That mapping is
    # a separate, deliberate piece of work (TODo's country-code item).
    def wanted(text: str) -> bool:
        return text == target

    _select_and_confirm(
        main_window,
        combo,
        target,
        wanted=wanted,
        target=target,
        step=step,
        settle_seconds=settle_seconds,
    )


def _select_and_confirm(
    main_window: Any,
    combo: Any,
    option_text: str,
    *,
    wanted: Callable[[str], bool],
    target: str,
    step: str,
    settle_seconds: float,
) -> None:
    controls.focus(main_window)
    try:
        combo.select(option_text)
    except Exception as exc:  # noqa: BLE001 - pywinauto raises IndexError here, but
        # the backend is free to raise anything; every failure to select means
        # the same thing to the caller, and all of them must fail closed.
        raise ManualReviewRequired(
            step,
            f"could not select {option_text!r} for {target} in the combo "
            f"(it reads {readers.field_value(combo)!r}): {type(exc).__name__}: {exc}",
        ) from exc

    time.sleep(settle_seconds)
    selected = readers.field_value(combo)
    if not wanted(selected):
        raise ManualReviewRequired(
            step,
            f"selected {option_text!r} for {target}, but the combo reads back as "
            f"{selected!r} - the selection did not take",
        )
