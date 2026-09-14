"""Standalone, live probe: locate the popup that appears when a combo opens
(Doc/adr/0006), and measure how long it takes to settle.

Background: ADR 0006 found that opening the Country combo (Debtor form) or
the VAT combo (Product form) renders a single, childless Pane that is *not*
a descendant of main_window's own UIA tree - so
entity_resolution.combos._read_open_combo_options currently screenshots the
whole main_window as a workaround, after a flat 1.0s
settle_seconds sleep (FAKTURAMA_ENTITY_RESOLUTION_SEARCH_SETTLE_SECONDS).
probes/probe-11 and probes/probe-12 each found one such Pane, once, by
hand - never repeated, never timed, and never checked for whether its
rectangle is reliably contained in main_window's own rectangle.

This script repeats combos.py's own open sequence (click + optional
type-ahead) several times per combo type, diffs the live top-level window
list before/after the click to find the new popup, polls its rectangle
until it stops changing to get a real settle time instead of a guess, and
saves screenshots to sanity-check that a crop to the popup's rectangle
actually contains the full visible option list.

Only two combo types are probed here: `country` (Debtor form) and `vat`
(Product form). There is no third "Payment Method" combo in this codebase's
ADR-0006 sense: entity_resolution/payment_method.py's own create form has
no combo at all (Name is its only field). The payment-method combo that
does exist is the Invoice editor's payment field
(orchestrator/steps/invoice_editor.py::apply_payment), which already
selects via plain `combo.select(...)` - it is UIA-selectable normally and
was never part of the "detached popup" problem this probe investigates.

Usage (on the Windows 11 ARM VM, with Fakturama running):
  1. For `country`: open the Debtor "New" form and leave it on screen.
     For `vat`: open the Product "New" form and leave it on screen.
  2. python spikes/uia_probe_combo_region.py country --repeats 5
     python spikes/uia_probe_combo_region.py vat --repeats 5

Each repeat: clicks the combo (+ type-ahead for `country`, mirroring
combos.py::select_exact_option's own call), polls for a newly-appeared
top-level window/Pane, polls that popup's rectangle until stable, saves a
full-main_window screenshot, a crop of it to the popup's rectangle, and a
direct capture of the popup control itself, then dismisses the popup
(Escape) before the next repeat.

Output: a plain-text summary to stdout (redirect to a probes/ file, e.g.
`> probes/probe-13-combo-region-settle.txt`) plus PNGs under --outdir
(default: probe_combo_region_output/).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pywinauto import Application, Desktop

# Mirrors ui_automation/screens.py's DEBTOR_COUNTRY_COMBO_NAME /
# PRODUCT_VAT_COMBO_NAME - duplicated rather than imported, since every
# other spikes/*.py script is standalone (pywinauto only, no project
# imports), and this one is no exception.
COMBOS = {
    "country": {"combo_name": "Country", "default_type_ahead": "Germany"},
    "vat": {"combo_name": "VAT", "default_type_ahead": None},
}


def _rect_tuple(control) -> tuple[int, int, int, int] | None:
    try:
        rect = control.rectangle()
    except Exception:  # noqa: BLE001 - a control mid-teardown reads as "gone"
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def _list_top_windows() -> list:
    # Desktop(backend="uia").windows() is pywinauto's own top-level
    # enumeration - already known (screens.py's picker-dialog comment) to
    # sometimes miss windows a raw win32gui.EnumWindows call would catch.
    # Used here anyway, first, because it is what makes handle/rectangle/
    # control_type directly available without a second wrapping step; the
    # win32gui cross-check below exists to catch it disagreeing.
    return list(Desktop(backend="uia").windows())


def _list_top_handles_win32() -> set[int]:
    import win32gui

    handles: list[int] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            handles.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return set(handles)


def _new_windows(before: list, after: list) -> list:
    before_handles = {w.handle for w in before}
    return [w for w in after if w.handle not in before_handles]


def _wait_for_new_popup(before: list, *, timeout: float, poll_interval: float):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        after = _list_top_windows()
        new = _new_windows(before, after)
        if new:
            return new, time.monotonic() - start
        time.sleep(poll_interval)
    return [], time.monotonic() - start


def _wait_for_stable_rect(control, *, timeout: float, poll_interval: float, stable_reads: int):
    start = time.monotonic()
    last: tuple[int, int, int, int] | None = None
    stable = 0
    while time.monotonic() - start < timeout:
        rect = _rect_tuple(control)
        if rect is not None and rect == last:
            stable += 1
            if stable >= stable_reads:
                return rect, time.monotonic() - start
        else:
            stable = 0
        last = rect
        time.sleep(poll_interval)
    return last, time.monotonic() - start


def _dismiss(main_window, combo) -> None:
    try:
        combo.type_keys("{ESC}")
    except Exception:  # noqa: BLE001 - best-effort cleanup between repeats
        pass
    time.sleep(0.3)


def _capture_png(control, path: Path) -> None:
    image = control.capture_as_image()
    image.save(path, format="PNG")


def _crop_and_save(full_image_path: Path, main_rect, popup_rect, out_path: Path) -> None:
    from PIL import Image

    with Image.open(full_image_path) as image:
        box = (
            popup_rect[0] - main_rect[0],
            popup_rect[1] - main_rect[1],
            popup_rect[2] - main_rect[0],
            popup_rect[3] - main_rect[1],
        )
        image.crop(box).save(out_path, format="PNG")


def _run_repeat(
    main_window,
    combo,
    combo_name: str,
    type_ahead: str | None,
    *,
    repeat_index: int,
    outdir: Path,
    settle_timeout: float,
    poll_interval: float,
) -> dict:
    main_window.set_focus()
    before_uia = _list_top_windows()
    before_descendants = set(main_window.descendants())

    click_time = time.monotonic()
    combo.click_input()
    if type_ahead:
        combo.type_keys(type_ahead)

    new_windows, found_after_seconds = _wait_for_new_popup(
        before_uia, timeout=settle_timeout, poll_interval=poll_interval
    )

    result: dict = {
        "repeat": repeat_index,
        "found": False,
        "ambiguous": False,
        "found_after_seconds": found_after_seconds,
    }

    if not new_windows:
        result["note"] = "no new top-level window appeared - popup may not be a separate window"
        _dismiss(main_window, combo)
        return result

    if len(new_windows) > 1:
        result["ambiguous"] = True
        result["candidate_rects"] = [_rect_tuple(w) for w in new_windows]
        # Still proceed with the first candidate so the run produces data,
        # but the ambiguity itself is the finding worth flagging.

    popup = new_windows[0]
    also_in_main_tree = popup in before_descendants  # False expected per ADR 0006

    stable_rect, settle_seconds = _wait_for_stable_rect(
        popup, timeout=settle_timeout, poll_interval=poll_interval, stable_reads=3
    )
    elapsed_from_click = time.monotonic() - click_time

    main_rect = _rect_tuple(main_window)
    result.update(
        {
            "found": True,
            "control_type": popup.element_info.control_type,
            "class_name": getattr(popup.element_info, "class_name", None),
            "popup_rect": stable_rect,
            "main_rect": main_rect,
            "relative_rect": (
                None
                if stable_rect is None or main_rect is None
                else (
                    stable_rect[0] - main_rect[0],
                    stable_rect[1] - main_rect[1],
                    stable_rect[2] - main_rect[0],
                    stable_rect[3] - main_rect[1],
                )
            ),
            "contained_in_main_window": (
                None
                if stable_rect is None or main_rect is None
                else (
                    stable_rect[0] >= main_rect[0]
                    and stable_rect[1] >= main_rect[1]
                    and stable_rect[2] <= main_rect[2]
                    and stable_rect[3] <= main_rect[3]
                )
            ),
            "was_descendant_of_main_window": also_in_main_tree,
            "settle_seconds_after_appearing": settle_seconds,
            "elapsed_click_to_settle_seconds": elapsed_from_click,
        }
    )

    win32_handles = _list_top_handles_win32()
    result["seen_by_win32_enum"] = popup.handle in win32_handles

    prefix = outdir / f"{combo_name}_rep{repeat_index}"
    full_path = prefix.with_name(prefix.name + "_full.png")
    direct_path = prefix.with_name(prefix.name + "_direct.png")
    crop_path = prefix.with_name(prefix.name + "_crop.png")
    _capture_png(main_window, full_path)
    _capture_png(popup, direct_path)
    if stable_rect is not None and main_rect is not None:
        _crop_and_save(full_path, main_rect, stable_rect, crop_path)
        result["screenshots"] = [str(full_path), str(direct_path), str(crop_path)]
    else:
        result["screenshots"] = [str(full_path), str(direct_path)]

    _dismiss(main_window, combo)
    return result


def _summarize(combo_key: str, results: list[dict]) -> None:
    found = [r for r in results if r["found"]]
    print(f"\n=== Summary: {combo_key} ({len(results)} repeats, {len(found)} found the popup) ===")
    if any(r.get("ambiguous") for r in results):
        print("WARNING: more than one new top-level window appeared on at least one repeat.")
    if not found:
        print("Popup never located via top-level window diff - no timing/geometry data.")
        return

    rel_rects = {r["relative_rect"] for r in found if r["relative_rect"] is not None}
    print(f"Distinct relative-to-main-window rectangles seen: {len(rel_rects)}")
    for rect in rel_rects:
        print(f"  {rect}")

    contained = [r["contained_in_main_window"] for r in found]
    print(f"contained_in_main_window: {contained}")

    descendant_flags = [r["was_descendant_of_main_window"] for r in found]
    print(f"was_descendant_of_main_window: {descendant_flags}")

    win32_flags = [r["seen_by_win32_enum"] for r in found]
    print(f"seen_by_win32_enum: {win32_flags}")

    elapsed = [r["elapsed_click_to_settle_seconds"] for r in found]
    print(
        "elapsed_click_to_settle_seconds: "
        f"min={min(elapsed):.3f} max={max(elapsed):.3f} mean={sum(elapsed) / len(elapsed):.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("combo", choices=sorted(COMBOS), help="which combo to probe")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--type-ahead", default=None, help="override the default type-ahead text")
    parser.add_argument("--outdir", default="probe_combo_region_output")
    parser.add_argument("--settle-timeout", type=float, default=5.0)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    args = parser.parse_args()

    spec = COMBOS[args.combo]
    combo_name = spec["combo_name"]
    type_ahead = args.type_ahead if args.type_ahead is not None else spec["default_type_ahead"]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    app = Application(backend="uia").connect(title_re=".*Fakturama.*")
    main_window = app.top_window()
    main_window.set_focus()

    combos = main_window.descendants(control_type="ComboBox", title=combo_name)
    if len(combos) != 1:
        raise SystemExit(
            f"expected exactly one ComboBox named {combo_name!r} in the currently open window, "
            f"found {len(combos)} - open the right form first (see this script's docstring)"
        )
    combo = combos[0]

    print(f"Probing combo={args.combo!r} (ComboBox name={combo_name!r}), type_ahead={type_ahead!r}")
    print(f"repeats={args.repeats}, outdir={outdir}\n")

    results = []
    for i in range(1, args.repeats + 1):
        print(f"-- repeat {i}/{args.repeats} --")
        result = _run_repeat(
            main_window,
            combo,
            args.combo,
            type_ahead,
            repeat_index=i,
            outdir=outdir,
            settle_timeout=args.settle_timeout,
            poll_interval=args.poll_interval,
        )
        print(result)
        results.append(result)
        time.sleep(0.5)

    _summarize(args.combo, results)


if __name__ == "__main__":
    main()
