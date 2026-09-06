"""Fakturama's main toolbar - the two buttons the workflow clicks.

Its own module so neither editor has to import the other for Save.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, screens


def click_new_order(main_window: Any) -> None:
    """Click "Create: New Order"."""
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.NEW_ORDER_BUTTON_TITLE).click_input()


def click_save(main_window: Any) -> None:
    """Click the shared "Save the current contents" button.

    Saves whichever editor is active, so the caller owns making that the
    right one - the whole difference between save_order and save_invoice.
    """
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()
