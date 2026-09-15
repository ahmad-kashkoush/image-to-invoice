"""Standalone, live probe: find out *where* the Product price turns into
Arabic-Indic digits (TODo.md open item 14).

Symptom seen live (2026-09-14): after `_create_product` writes the gross
price, the Product form shows the price as e.g. Arabic-Indic "١٢٥"
instead of "125". Normalization only ever produces ASCII digit strings, so
the substitution happens somewhere between our string and the pixels.

UPDATE (2026-09-14, from a live screenshot of the Product form): layer 2
below is confirmed, and there was a second, worse bug underneath it. The
field rendered the gross price as Arabic-Indic digits *with an Arabic
currency symbol* rather than EUR - glyph shaping (layer 3) cannot change a
currency symbol, so Fakturama is formatting money with an Arabic format
locale. It also rendered 297,500.00 where 297.50 was written: the field is
pre-filled with a formatted 0.00 default and controls.type_text inserts at
the caret, so "297.50" + "0,00" became "297.500,00" = 297500.00. That part
is fixed (product.py now uses controls.replace_text). This probe remains
useful for confirming the pre-fill, for reading what the field actually
holds after a correct write, and for capturing the VM's locale state.

There are three candidate layers, and they need different fixes, so the
point of this probe is to tell them apart rather than to guess:

  (1) The keystrokes.  entity_resolution/product.py writes the price with
      controls.type_text() -> control.type_keys(), i.e. real keyboard input,
      while every other numeric field in this codebase uses
      controls.set_text() (UIA ValuePattern.SetValue, no keyboard at all).
      That difference alone matches "only the price is affected".  Note
      pywinauto's type_keys defaults to vk_packet=True, which injects each
      character as a KEYEVENTF_UNICODE codepoint and should therefore be
      immune to the active keyboard layout - so if this layer is guilty,
      something is re-mapping VK_PACKET input and that is worth knowing
      exactly.

  (2) The app's own re-render.  Fakturama is a Java/SWT application; a
      number field re-formats what was typed when focus leaves it (this
      codebase already knows that - see resolver.percent_matches).  A JVM
      whose default locale is an Arabic one formats numbers with
      Arabic-Indic digits.  If this layer is guilty, the text is genuinely
      Arabic-Indic and the fix is the VM's *format* locale (or a JVM flag),
      not our typing.

  (3) Windows glyph shaping.  Control Panel -> Region -> Additional
      settings -> Numbers -> "Use native digits" (HKCU\\Control Panel\\
      International\\NumShape: 0=never, 1=context, 2=national) makes
      Uniscribe *draw* ASCII digits as Arabic-Indic while the underlying
      text stays ASCII.  If this layer is guilty, every UIA read below
      comes back ASCII and the bug is cosmetic only.

For each write method the probe prints the read-back text as explicit
codepoints (U+0031 vs U+0661), from three different UIA reads, at three
moments (right after the write, after Tab commits the field, and after a
short settle).  That is enough to place the substitution in layer 1, 2 or
3 without a screenshot.

Usage (on the Windows 11 ARM VM, with Fakturama running):
  1. Open Products -> "Create a new product" and leave the empty form on
     screen.  The probe writes only into the "Price (gross)" field and
     never presses Save, so nothing is persisted.
  2. python spikes/uia_probe_digit_shaping.py
     python spikes/uia_probe_digit_shaping.py --value 1234.56 --env-only

Output: plain text to stdout - redirect to a probes/ file, e.g.
`> probes/probe-14-digit-shaping.txt`.
"""

from __future__ import annotations

import argparse
import locale
import sys
import time

from pywinauto import Application

# Mirrors ui_automation/screens.py - duplicated rather than imported, since
# every other spikes/*.py script is standalone (pywinauto only, no project
# imports), and this one is no exception.
APP_TITLE_RE = r"^Fakturama - "
PRODUCT_SKU_EDIT_NAME = "Item Number"
PRODUCT_PRICE_GROSS_LABEL_NAME = "Price (gross)"

ARABIC_INDIC = {chr(0x0660 + d) for d in range(10)} | {chr(0x06F0 + d) for d in range(10)}


def _codepoints(text: str | None) -> str:
    if text is None:
        return "<None>"
    if text == "":
        return "'' (empty)"
    shaped = "".join(ch for ch in text if ch in ARABIC_INDIC)
    flag = f"  <-- NON-ASCII DIGITS: {len(shaped)}" if shaped else ""
    return " ".join(f"U+{ord(ch):04X}" for ch in text) + flag


# --------------------------------------------------------------------------
# Layer 3 / layer 2 evidence: what locale is this VM actually running in?
# --------------------------------------------------------------------------


def dump_environment() -> None:
    print("=" * 72)
    print("ENVIRONMENT")
    print("=" * 72)

    print(f"python locale.getlocale()        : {locale.getlocale()}")
    try:
        print(f"python locale.getdefaultlocale() : {locale.getdefaultlocale()}")
    except Exception as exc:  # noqa: BLE001 - deprecated in 3.13, may vanish
        print(f"python locale.getdefaultlocale() : <unavailable: {exc}>")

    try:
        import winreg

        # NumShape is the "Use native digits" setting: 0=never, 1=context,
        # 2=national.  sNativeDigits names which digits "native" means.
        # A value of 1 or 2 here is layer 3 (glyph shaping only).
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as key:
            for name in (
                "LocaleName", "sCountry", "sLanguage", "sDecimal", "sThousand",
                "sCurrency", "NumShape", "sNativeDigits", "Locale",
            ):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    value = "<unset>"
                note = ""
                if name == "NumShape":
                    note = {"0": "  (never substitute - good)",
                            "1": "  (context - CAN shape digits)",
                            "2": "  (national - SHAPES digits)"}.get(str(value), "")
                print(f"HKCU International {name:<14}: {value!r}{note}")

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Keyboard Layout\Preload") as key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                # 0401 = Arabic (Saudi Arabia), 0407 = German, 0409 = en-US.
                print(f"HKCU Keyboard Preload {name:<10}: {value!r}")
                index += 1
    except Exception as exc:  # noqa: BLE001 - registry read is best-effort
        print(f"<registry read failed: {exc}>")

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        count = user32.GetKeyboardLayoutList(0, None)
        layouts = (wintypes.HKL * count)()
        user32.GetKeyboardLayoutList(count, layouts)
        print("active keyboard layouts (HKL): "
              + ", ".join(f"0x{hkl & 0xFFFFFFFF:08X}" for hkl in layouts))
        print(f"foreground thread layout (HKL): 0x{user32.GetKeyboardLayout(0) & 0xFFFFFFFF:08X}")
        print(f"GetUserDefaultLCID            : 0x{kernel32.GetUserDefaultLCID():04X}")
        print(f"GetThreadLocale               : 0x{kernel32.GetThreadLocale():04X}")

        buf = ctypes.create_unicode_buffer(85)
        kernel32.GetUserDefaultLocaleName(buf, 85)
        print(f"GetUserDefaultLocaleName      : {buf.value!r}")
    except Exception as exc:  # noqa: BLE001 - ctypes probe is best-effort
        print(f"<win32 locale read failed: {exc}>")
    print()


# --------------------------------------------------------------------------
# Layer 1 / layer 2 evidence: write the price three ways, read it three ways.
# --------------------------------------------------------------------------


def _reads(edit) -> list[tuple[str, str]]:
    # Three different UIA surfaces, because they can disagree: window_text()
    # is the Name/legacy caption, get_value() is the ValuePattern, and
    # legacy_properties() is the MSAA bridge.  If any of them is ASCII while
    # the screen shows Arabic-Indic, the substitution is layer 3 (drawing).
    out: list[tuple[str, str]] = []
    for label, getter in (
        ("window_text()", lambda: edit.window_text()),
        ("get_value()", lambda: edit.get_value()),
        ("legacy Value", lambda: edit.legacy_properties().get("Value")),
    ):
        try:
            out.append((label, _codepoints(getter())))
        except Exception as exc:  # noqa: BLE001 - not every control has each
            out.append((label, f"<{type(exc).__name__}: {exc}>"))
    return out


def _clear(edit) -> None:
    edit.click_input()
    edit.type_keys("^a{DELETE}")


def _report(stage: str, edit) -> None:
    for label, text in _reads(edit):
        print(f"    {stage:<22} {label:<14} {text}")


def probe_write(edit, value: str, *, method: str, settle: float) -> None:
    print(f"--- write method: {method} ---")
    _clear(edit)
    _report("after clear", edit)

    if method == "type_keys (vk_packet=True)":
        # Exactly what controls.type_text() does today.
        edit.click_input()
        edit.type_keys(value, with_spaces=True)
    elif method == "type_keys (vk_packet=False)":
        # Sends the real virtual key of each character instead of a unicode
        # packet - i.e. the path that *is* keyboard-layout dependent.  If
        # this one shapes and the vk_packet=True one does not, the active
        # layout is implicated; if both shape identically, it is not.
        edit.click_input()
        edit.type_keys(value, with_spaces=True, vk_packet=False)
    elif method == "set_text (ValuePattern)":
        # No keyboard involved at all.  If this still comes back shaped, the
        # substitution is the app's own formatter or the renderer, and
        # switching product.py away from type_text() would not fix anything.
        edit.set_text(value)
    else:  # pragma: no cover - argparse restricts the choices
        raise ValueError(method)

    _report("after write", edit)

    # Fakturama re-formats a number field when focus leaves it (the same
    # behaviour resolver.percent_matches exists for).  If the text is ASCII
    # here and Arabic-Indic after the Tab, the app's formatter is the source
    # and the fix is the VM/JVM locale, not our typing.
    edit.type_keys("{TAB}")
    time.sleep(settle)
    _report("after Tab + settle", edit)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--value", default="125.00", help="price text to write (default: 125.00)")
    parser.add_argument("--settle", type=float, default=1.0, help="seconds to wait after Tab (default: 1.0)")
    parser.add_argument("--env-only", action="store_true", help="dump locale state and exit, no app needed")
    args = parser.parse_args(argv)

    dump_environment()
    if args.env_only:
        return 0

    print("=" * 72)
    print(f"PRICE FIELD (writing {args.value!r})")
    print("=" * 72)

    app = Application(backend="uia").connect(title_re=APP_TITLE_RE)
    main_window = app.top_window()
    main_window.set_focus()

    # Mirrors locators.sibling_pane_after_label + product.py's own lookup.
    label = main_window.child_window(control_type="Text", title=PRODUCT_PRICE_GROSS_LABEL_NAME).wrapper_object()
    siblings = label.parent().children()
    price_pane = siblings[siblings.index(label) + 1]
    price_edit = price_pane.descendants(control_type="Edit")[0]

    # A control field: the SKU Edit is plain text, written the same way
    # (controls.type_text), and is *not* reported as shaped.  If a digit-only
    # SKU comes back shaped here too, the problem is not specific to the
    # number field - and entity resolution's exact SKU match would silently
    # start creating duplicate products.
    sku_edit = main_window.child_window(control_type="Edit", title=PRODUCT_SKU_EDIT_NAME).wrapper_object()

    # The form's untouched default, before anything is written. A non-empty
    # value here is what made the live bug: controls.type_text inserts at the
    # caret, so the typed price was concatenated with this default.
    print("--- untouched default ---")
    _report("initial (pre-fill)", price_edit)
    print()

    for method in (
        "type_keys (vk_packet=True)",
        "type_keys (vk_packet=False)",
        "set_text (ValuePattern)",
    ):
        probe_write(price_edit, args.value, method=method, settle=args.settle)

    print("=" * 72)
    print("SKU FIELD (control: plain text, same write path)")
    print("=" * 72)
    probe_write(sku_edit, "SKU-" + args.value.replace(".", ""), method="type_keys (vk_packet=True)", settle=args.settle)

    print("Reminder: nothing was saved. Close the Product form without saving.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
