"""Standalone, live probe of the `Data > Documents` list screen.

This is the one screen in Fakturama with no probe at all (`TODo.md`), and
Tasks 4.5/5.5 make it the prescribed independent check on a saved Order and
its linked Invoice. Nothing about it can be pinned in
`ui_automation/screens.py` until three things are known, and none of them can
be guessed:

  1. the grid Pane's accessible name (the nav label and the pane name happen
     to be the same string for all four list screens already modelled - this
     probe confirms whether Documents follows that rule);
  2. the rendered, left-to-right column captions, because
     `grid_columns.widen_column` indexes into that list by position (ADR 0017)
     and the vision read keys on the captions themselves;
  3. the state vocabulary an Order row and a paid/unpaid Invoice row render
     ("open" / "paid" / ...), which Task 4.5's "open state" compares against.

The rows are expected to be UIA-invisible like every other Fakturama list
grid, so (2) and (3) come from the screenshots this writes, not from the tree
dump. Read the PNGs.

Read-only apart from the nav click and typing into the list's own search box
(which only filters the view).

Usage (Windows, Fakturama running, ideally with a saved Order and its linked
Invoice already in the workspace):
    python spikes/uia_probe_documents_list.py
    python spikes/uia_probe_documents_list.py --key PO000001 --key RE000001
    python spikes/uia_probe_documents_list.py > probes/probe-15-documents-list.txt
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pywinauto import Application

from fakturama_automation.ui_automation import controls, locators, vision_grounding

APP_TITLE_RE = r"^Fakturama - "
NAV_NAME = "Documents"


def dump_subtree(control, indent: int = 0) -> None:
    info = control.element_info
    prefix = "  " * indent
    auto_id = getattr(info, "automation_id", None) or ""
    rect = info.rectangle
    print(
        f"{prefix}{info.control_type} - {info.name!r}    "
        f"(L{rect.left}, T{rect.top}, R{rect.right}, B{rect.bottom})  auto_id={auto_id!r}"
    )
    for child in control.children():
        dump_subtree(child, indent + 1)


def rows_pane(container):
    """The grid itself, without the left type tree or the title/search strip.

    Every other list screen in this app can be captured by its named Pane
    directly; this one cannot - Pane 'Documents' also contains the
    Invoices/Orders tree, which a vision read would transcribe as extra
    columns and which grid_columns' pixel measurement would count as
    separators. Structural, because every Pane on the way down is blank-named:
      Pane 'Documents' > Pane > [Tree, Pane] > [title+search strip, GRID]
    """
    return container.children()[0].children()[1].children()[1]


def capture(main_window, pane, outdir: Path, name: str) -> None:
    # focus_foreground() needs the top-level window's handle, not the pane's.
    controls.focus_foreground(main_window)
    controls.move_pointer_away(main_window)
    for label, target in (("", pane), ("-rows", rows_pane(pane))):
        path = outdir / f"{name}{label}.png"
        path.write_bytes(vision_grounding.capture_control_image(target))
        rect = target.element_info.rectangle
        print(f"  wrote {path}  ({rect.width()}x{rect.height()} px)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key",
        action="append",
        default=[],
        help="document number to type into the list's search box, then re-capture "
        "(repeatable, e.g. --key PO000001 --key RE000001)",
    )
    parser.add_argument(
        "--tree",
        action="append",
        default=[],
        help="TreeItem to click before capturing (repeatable, e.g. --tree Orders "
        "--tree Invoices). The view opens on whatever filter it was last left on.",
    )
    parser.add_argument("--outdir", default="probes/probe_documents_output")
    parser.add_argument("--settle", type=float, default=1.5)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    app = Application(backend="uia").connect(title_re=APP_TITLE_RE)
    main_window = app.top_window()

    print(f"=== clicking the {NAV_NAME!r} nav item ===")
    controls.focus(main_window)
    nav = controls.find_control(main_window, "Text", name=NAV_NAME)
    print(f"  nav: {nav.element_info.control_type} - {nav.element_info.name!r} "
          f"auto_id={getattr(nav.element_info, 'automation_id', None)!r}")
    nav.click_input()
    time.sleep(args.settle)

    print()
    print(f"=== Panes named {NAV_NAME!r} in the main window ===")
    panes = controls.find_all_controls(main_window, "Pane", name=NAV_NAME)
    print(f"  {len(panes)} found")
    for pane in panes:
        rect = pane.element_info.rectangle
        print(f"  - (L{rect.left}, T{rect.top}, R{rect.right}, B{rect.bottom}) "
              f"auto_id={getattr(pane.element_info, 'automation_id', None)!r} "
              f"{len(pane.descendants())} descendant(s)")

    grid_pane = controls.find_control(main_window, "Pane", name=NAV_NAME)

    print()
    print(f"=== UIA subtree of Pane {NAV_NAME!r} ===")
    dump_subtree(grid_pane)

    print()
    print("=== search box ===")
    try:
        label = locators.search_label(grid_pane)
        edit = locators.search_edit(label)
        print(f"  found: label at {label.element_info.rectangle}, edit at {edit.element_info.rectangle}")
    except Exception as error:  # noqa: BLE001 - a probe reports, it does not fail
        label = edit = None
        print(f"  NOT found inside the grid pane: {error!r}")
        try:
            label = locators.search_label(main_window)
            edit = locators.search_edit(label)
            print(f"  found on main_window instead: edit at {edit.element_info.rectangle}")
        except Exception as fallback_error:  # noqa: BLE001
            print(f"  not on main_window either: {fallback_error!r}")

    def refind():
        # Re-found on purpose: clicking a tree node or typing in the search box
        # rebuilds the grid's widget tree, and a stale pane captures as nothing.
        return controls.find_control(main_window, "Pane", name=NAV_NAME)

    print()
    print("=== captures ===")
    capture(main_window, refind(), outdir, "documents-asfound")

    for tree_name in args.tree:
        print(f"  clicking TreeItem {tree_name!r}")
        controls.focus(main_window)
        controls.find_control(refind(), "TreeItem", name=tree_name).click_input()
        time.sleep(args.settle)
        if edit is not None:
            controls.set_text(edit, "")
            time.sleep(args.settle)
        capture(main_window, refind(), outdir, f"documents-{tree_name.replace(' ', '-')}")

        for key in args.key:
            if edit is None:
                print(f"  skipping --key {key!r}: no search Edit was found")
                continue
            controls.set_text(edit, key)
            time.sleep(args.settle)
            capture(
                main_window, refind(), outdir,
                f"documents-{tree_name.replace(' ', '-')}-{key}",
            )

    if not args.tree:
        for key in args.key:
            if edit is None:
                print(f"  skipping --key {key!r}: no search Edit was found")
                continue
            controls.set_text(edit, key)
            time.sleep(args.settle)
            capture(main_window, refind(), outdir, f"documents-{key}")


if __name__ == "__main__":
    main()
