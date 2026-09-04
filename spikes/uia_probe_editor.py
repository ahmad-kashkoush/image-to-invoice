"""Standalone, read only UIA discovery probe for a specific Fakturama
editor or dialog (Order editor, Invoice editor, search/entity-lookup
dialogs), rather than the whole main window.

uia_probe.py dumps the entire main window tree, which only shows the
dashboard/navigation view. Fakturama's editors open as new tabs or panes
inside that same Eclipse RCP window (occasionally as a separate dialog),
so this variant searches the live control tree for anything whose text
matches a keyword and prints just those subtrees - far smaller and easier
to read than the full window dump.

Usage (on the Windows 11 ARM VM, with Fakturama running and the target
editor/dialog already open on screen):
    python spikes/uia_probe_editor.py Order
    python spikes/uia_probe_editor.py Invoice
    python spikes/uia_probe_editor.py Debtor

If no keyword is given, "Order" is used. If nothing matches, this falls
back to dumping the full main window tree (like uia_probe.py) so you can
eyeball it and pick a better keyword.
"""

from __future__ import annotations

import argparse

from pywinauto import Application


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "keyword",
        nargs="?",
        default="Order",
        help="text to search for in control titles, e.g. Order, Invoice, Debtor",
    )
    args = parser.parse_args()

    app = Application(backend="uia").connect(title_re=".*Fakturama.*")

    print("Top-level windows:")
    for top in app.windows():
        print(f"  - {top.window_text()!r} ({top.element_info.control_type})")
    print()

    window = app.top_window()
    matches = window.descendants(title_re=f"(?i).*{args.keyword}.*")

    if not matches:
        print(
            f"No descendants matched {args.keyword!r}; "
            "dumping full main window tree instead.\n"
        )
        window.print_control_identifiers()
        return

    print(f"{len(matches)} control(s) matched {args.keyword!r}:")
    for control in matches:
        print(f"  - {control.window_text()!r} ({control.element_info.control_type})")
    print()

    for control in matches:
        print(f"Identifiers for: {control.window_text()!r}\n")
        control.print_control_identifiers()
        print()


if __name__ == "__main__":
    main()
