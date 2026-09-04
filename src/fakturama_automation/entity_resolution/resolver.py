"""Shared search-then-create resolution pattern.

Section 4 (entity_resolution). Every entity resolver (debtor, product, VAT
rate, payment method) follows the same shape: search Fakturama for an
exact match, return it if found, create a new record only if no exact
match exists. If the search is ambiguous (more than one exact match,
which should not happen but must be handled), route to error_handling
rather than picking one.

TODO(section 4): implement the generic search and create flow here so
debtor.py, product.py, vat_rate.py, and payment_method.py can share it,
using fakturama_automation.ui_automation.controls and fakturama_automation.ui_automation.waits to search Fakturama's
own UI and wait for result sets to stabilize.
"""

from __future__ import annotations

from typing import Any, Callable


def resolve_exact_or_create(
    search_by: Callable[[], list[Any]],
    create: Callable[[], Any],
) -> Any:
    """Search for an exact match; create only if none exists.

    TODO(section 4): implement. If search_by() returns exactly one result,
    return it. If it returns zero, call create(). If it returns more than
    one, raise for manual review (this indicates a data problem, not
    something to resolve by guessing).
    """
    raise NotImplementedError
