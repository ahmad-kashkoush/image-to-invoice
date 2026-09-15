"""Standalone, live probe: why does the Product form's VAT combo read back
as zero options?

Background: ADR 0013 changed entity_resolution/combos.py to crop the combo
screenshot to the located popup instead of capturing the whole main_window
(the ADR 0006 behaviour). On 2026-09-15 a clean-profile run stopped at
`resolve_product` with

    no unique VAT option matching 19%; options were []

while a screenshot taken at that moment showed the popup open with exactly
one visible option, "19%". So the popup was on screen and the vision read
still came back empty - which points at the crop, not at the click.

This probe opens the VAT combo on whatever Product editor is already on
screen, locates the popup the way combos.py used to before it moved to
UIA selection, and then runs the same vision read twice: once on the popup
crop (ADR 0013) and once on the whole-window capture it replaced (ADR 0006). Printing both side by side is the whole point - it separates
"the model cannot see a 58x22 image" from "the capture is of the wrong
region".

Usage (Windows, with Fakturama running and a Product editor open with a
VAT combo visible):
    python spikes/uia_probe_combo_vat_read.py
    python spikes/uia_probe_combo_vat_read.py > probes/probe-14-combo-vat-read.txt

Writes the two PNGs it read next to the text output, under --outdir.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pywinauto import Application, Desktop

from fakturama_automation.entity_resolution import config
from fakturama_automation.ui_automation import screens, vision_grounding

APP_TITLE_RE = r"^Fakturama - "


def to_png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def locate_open_popup(before_handles, *, timeout_seconds, poll_interval=0.05, stable_reads=3):
    """The popup-locator entity_resolution/combos.py used to carry, inlined so
    this probe keeps working now that the production path selects through UIA
    and no longer needs it."""
    deadline = time.monotonic() + timeout_seconds
    popup = None
    while popup is None and time.monotonic() < deadline:
        for window in Desktop(backend="uia").windows():
            if window.handle not in before_handles:
                popup = window
                break
        if popup is None:
            time.sleep(poll_interval)
    if popup is None:
        return None
    last_rect, stable = None, 0
    while time.monotonic() < deadline:
        try:
            rect = popup.rectangle()
        except Exception:  # noqa: BLE001 - a torn-down popup is "not found"
            return None
        current = (rect.left, rect.top, rect.right, rect.bottom)
        if current == last_rect:
            stable += 1
            if stable >= stable_reads:
                return popup
        else:
            stable = 0
        last_rect = current
        time.sleep(poll_interval)
    return popup


def vision(image_bytes: bytes) -> str:
    try:
        options = vision_grounding.read_combo_options(image_bytes)
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not fail closed
        return f"FAILED {type(exc).__name__}: {exc}"
    if not options:
        return "[] (empty - this is the live failure)"
    return "\n".join(f"        {o.text!r}  bbox={o.bbox}" for o in options)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=Path("probes/probe_combo_vat_read_output"))
    parser.add_argument("--settle", type=float, default=config.SEARCH_SETTLE_SECONDS)
    parser.add_argument("--popup-timeout", type=float, default=1.5)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    load_dotenv()
    app = Application(backend="uia").connect(title_re=APP_TITLE_RE)
    main_window = app.window(title_re=APP_TITLE_RE)
    main_window.set_focus()
    time.sleep(0.5)

    combo = main_window.child_window(title=screens.PRODUCT_VAT_COMBO_NAME, control_type="ComboBox")
    if not combo.exists():
        print(f"No ComboBox named {screens.PRODUCT_VAT_COMBO_NAME!r} on screen.")
        print("Open a Product editor (Data > Products > new) and re-run.")
        return 2

    crect = combo.rectangle()
    print(f"combo {screens.PRODUCT_VAT_COMBO_NAME!r} rect={crect} {crect.width()}x{crect.height()}")
    print(f"combo current value: {combo.legacy_properties().get('Value')!r}")

    before = {w.handle for w in Desktop(backend="uia").windows()}
    combo.click_input()
    popup = locate_open_popup(before, timeout_seconds=args.popup_timeout)

    print()
    if popup is None:
        print("_locate_open_popup: NOT FOUND -> code falls back to the whole main_window")
    else:
        prect = popup.rectangle()
        print(f"_locate_open_popup: found handle={popup.handle} rect={prect} "
              f"{prect.width()}x{prect.height()}")

    print()
    print("=== A. popup crop (what combos.py does today, ADR 0013) ===")
    target = popup if popup is not None else main_window
    if popup is None:
        time.sleep(args.settle)
    crop = target.capture_as_image()
    crop_path = args.outdir / "a_popup_crop.png"
    crop.save(crop_path)
    print(f"    captured {crop.size} -> {crop_path}")
    print(f"    vision read:\n{vision(to_png(crop))}")

    print()
    print("=== B. whole main_window (the ADR 0006 behaviour it replaced) ===")
    whole = main_window.capture_as_image()
    whole_path = args.outdir / "b_whole_window.png"
    whole.save(whole_path)
    print(f"    captured {whole.size} -> {whole_path}")
    print(f"    vision read:\n{vision(to_png(whole))}")

    main_window.type_keys("{ESC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
