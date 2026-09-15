"""Reading Fakturama's list screens: navigate, filter, vision-read the rows.

These grids are custom-rendered and invisible to UIA (see grid_columns.py), so
every list screen in the app - Debtors, Products, VATs, terms of payment and
Data > Documents - is read the same way: click the nav label, type a key into
the screen's own search box, screenshot the grid pane, and hand the picture to
a vision model.

This lived in entity_resolution/resolver.py until Data > Documents needed it
too. `verification` and `entity_resolution` are peers that never import each
other, so the shared mechanism belongs a layer down, next to the pixel and
screenshot code it is built on.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from fakturama_automation.ui_automation import (
    config,
    controls,
    grid_columns,
    locators,
    vision_grounding,
)

logger = logging.getLogger(__name__)


def open_list_screen(main_window: Any, nav_name: str) -> None:
    """Click a Navigation View entry by its visible label.

    The nav is not a tree: its entries are plain Text controls, clicked with a
    real mouse click. Fire and forget - nothing here confirms the screen
    opened, because the caller's own `find_control` for the grid pane is what
    catches a click that went nowhere.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=nav_name).click_input()


def search_grid_exact(
    parent: Any,
    *,
    grid_pane_name: str,
    key: str,
    columns: list[str],
    grid_pane_locator: Callable[[Any], Any] | None = None,
    widen_clipped: bool = True,
    vision_client: Any = None,
    settle_seconds: float = config.LIST_GRID_SETTLE_SECONDS,
    timeout_seconds: float = config.LIST_GRID_TIMEOUT_SECONDS,
) -> list[dict[str, str]]:
    """Filter a list screen by `key` and read the visible rows back.

    `grid_pane_locator` maps the Pane named `grid_pane_name` to the pane that
    is actually screenshotted. It exists for Data > Documents, whose named
    pane also holds a document-type tree; everywhere else the named pane *is*
    the grid and the default (identity) applies.
    """

    def find_grid_pane() -> Any:
        pane = controls.find_control(
            parent, "Pane", name=grid_pane_name, timeout_seconds=timeout_seconds
        )
        return grid_pane_locator(pane) if grid_pane_locator is not None else pane

    grid_pane = find_grid_pane()
    label = locators.search_label(parent, timeout_seconds=timeout_seconds)
    controls.set_text(locators.search_edit(label, timeout_seconds=timeout_seconds), key)
    time.sleep(settle_seconds)

    def read_rows() -> list[dict[str, str]]:
        controls.focus_foreground(parent)
        controls.move_pointer_away(parent)
        return vision_grounding.read_grid_rows(
            vision_grounding.capture_control_image(grid_pane), columns=columns, client=vision_client
        )

    rows = read_rows()
    # A column too narrow for its content renders clipped ("Northstar
    # Offic..."), and every comparison built on these rows is exact equality,
    # so a clipped cell can never match and the caller creates a duplicate
    # instead. Widths are persisted per profile, so this depends on saved UI
    # layout rather than on the data - it is why the same order matched on one
    # profile and duplicated on another. Widen once and re-read; if it is
    # still clipped the rows are returned as they are and the exact-match
    # comparison fails closed, which is the pre-existing behaviour.
    clipped = _clipped_columns(rows, columns)
    if clipped and widen_clipped:
        # Re-found, not reused: typing into the search box rebuilds the grid's
        # widget tree as it filters (the same thing
        # orchestrator/steps/pickers.py re-finds its dialog for), and a stale
        # pane captures as nothing, which measures as no columns and silently
        # declines to widen. That is what made the widen a no-op live.
        grid_pane = find_grid_pane()
        # Once, not once per clipped column: a drag here widens every column
        # at the same time, so a second drag only eats the space the far
        # columns need to stay on screen.
        widened = grid_columns.widen_column(
            grid_pane,
            column_index=columns.index(clipped[0]),
            by_pixels=config.COLUMN_WIDEN_PIXELS,
            expected_columns=len(columns),
        )
        logger.info(
            "%s column(s) render clipped %s - widening %s",
            len(clipped), clipped, "succeeded" if widened else "FAILED (layout not measurable)",
        )
        if widened:
            controls.focus_foreground(parent)
            controls.move_pointer_away(parent)
            time.sleep(settle_seconds)
            rows = read_rows()
    elif clipped:
        logger.info("%s column(s) render clipped %s - not widening this grid", len(clipped), clipped)
    return rows


def _clipped_columns(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    return [
        column
        for column in columns
        if any(grid_columns.is_clipped(row.get(column, "")) for row in rows)
    ]
