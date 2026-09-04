"""Order save fakturama_automation.verification.

Section 5 (verification).

TODO(section 5): confirm saved Order state via an assigned order number
being present and a no unsaved changes flag (or equivalent UI state) being
clear. Read state back from the live UI via ui_automation, do not assume
success from the save action alone.
"""

from __future__ import annotations

from typing import Any


def verify_order_saved(order_window: Any) -> bool:
    """Confirm the Order in order_window was actually saved.

    TODO(section 5): implement. Should return False (or raise, routing to
    error_handling) rather than assume success.
    """
    raise NotImplementedError
