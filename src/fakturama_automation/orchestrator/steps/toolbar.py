from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, screens


def click_new_order(main_window: Any) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.NEW_ORDER_BUTTON_TITLE).click_input()


def click_save(main_window: Any) -> None:
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()
