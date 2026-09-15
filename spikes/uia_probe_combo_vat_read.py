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
screen, locates the popup the same way combos._locate_open_popup does, and
then runs the *same* vision read twice: once on the popup crop (what the
code does today) and once on the whole-window capture (what it did before
ADR 0013). Printing both side by side is the whole point - it separates
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

from fakturama_automation.entity_resolution import combos, config
from fakturama_automation.ui_automation import screens, vision_grounding

APP_TITLE_RE = r"^Fakturama - "


def to_png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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
    popup = combos._locate_open_popup(before, timeout_seconds=config.COMBO_POPUP_SETTLE_TIMEOUT_SECONDS)

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
