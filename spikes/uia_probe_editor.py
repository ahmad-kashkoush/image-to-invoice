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


def _dump_subtree(control, indent: int = 0) -> None:
    # In the style of WindowSpecification.print_control_identifiers(), but that
    # method only exists on the lazy WindowSpecification proxy, not on the
    # already-resolved leaf wrappers window.descendants() returns - so this
    # uses only universally-available wrapper methods.
    info = control.element_info
    prefix = "  " * indent
    auto_id = getattr(info, "automation_id", None) or ""
    class_name = getattr(info, "class_name", None) or ""
    rect = info.rectangle
    print(
        f"{prefix}{info.control_type} - {info.name!r}    "
        f"(L{rect.left}, T{rect.top}, R{rect.right}, B{rect.bottom})"
    )
    print(f"{prefix}  auto_id={auto_id!r}, class_name={class_name!r}")
    for child in control.children():
        _dump_subtree(child, indent + 1)


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
    # UIAElementInfo.descendants() (what WindowSpecification.descendants()
    # delegates to) only accepts title/class_name/control_type/content_only -
    # title_re is a WindowSpecification/child_window()-only lazy-matching
    # kwarg, not supported here. Fetch every descendant unfiltered and do the
    # case-insensitive substring match ourselves via window_text() (the same
    # wrapper method already used below on each match).
    keyword = args.keyword.lower()
    matches = [control for control in window.descendants() if keyword in control.window_text().lower()]

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
        _dump_subtree(control)
        print()


if __name__ == "__main__":
    main()
