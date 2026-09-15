"""Task 4.5/5.5: confirm a saved Order/Invoice from `Data > Documents`.

The rest of this package reads the still-open editor's own fields back, which
proves the widgets hold what was typed - not that a row reached the database.
The Task Description asks for a second, independent look at the saved
document, and this is it. It is additive: an editor that reads back correctly
while Documents shows nothing is exactly the failure the editor read cannot
see.

Everything here is vision-read through `ui_automation.list_grids`, the same
mechanism entity_resolution uses for the Debtors/Products/VATs grids, because
this grid is UIA-invisible like all the others
(probes/probe-15-documents-list.txt).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import controls, grid_columns, list_grids, locators, screens
from fakturama_automation.verification import comparisons

logger = logging.getLogger(__name__)

# The State cell is an icon plus a word, and the vision read transcribes the
# icon inconsistently - the same paid Invoice came back as 'paid' on one read
# and as a check-mark glyph followed by 'paid' on the next. Comparing the word
# alone is what the check actually means; comparing the cell verbatim makes it
# a coin toss.
_NOT_A_STATE_WORD = re.compile(r"[^a-z ]+")


def _state_word(cell: str) -> str:
    return " ".join(_NOT_A_STATE_WORD.sub(" ", cell.lower()).split())


# What proves the row carries the searched number is Fakturama's own filter -
# the row came back from a search on that number. The transcribed cell is the
# least reliable text on the screen: a run of zeros miscounts, live, even in a
# one-row read ('INV000007' came back as 'INV0000007'), so comparing it
# verbatim manufactures false failures. What the comparison still has to catch
# is a filter that matched a *different* document, because the search is a
# substring match ('PO000007' would also match a hypothetical 'PO0000070'). So
# the two are compared with runs of zeros collapsed: the one thing this read
# demonstrably gets wrong is discarded, and every other difference still fails.
_ZERO_RUN = re.compile(r"0{2,}")


def _same_document_number(expected: str, shown: str) -> bool:
    return _ZERO_RUN.sub("0", expected.strip()) == _ZERO_RUN.sub("0", shown.strip())


def order_row_problems(
    main_window: Any, order: NormalizedOrder, *, number: str, client: Any = None
) -> list[str]:
    """Task 4.5 - one Order row, with its number, Date, Cust.Ref., open state
    and Total."""
    tree_item = screens.DOCUMENTS_ORDERS_TREE_ITEM
    row, problems = _document_row(main_window, tree_item=tree_item, number=number, client=client)
    if row is None:
        return problems

    problems.extend(
        _common_row_problems(
            main_window, row, order, number=number, tree_item=tree_item, client=client
        )
    )

    state = row.get(screens.DOCUMENTS_COL_STATE, "")
    if _state_word(state) != screens.DOCUMENT_STATE_OPEN:
        problems.append(
            f"Documents: Order {number} state is '{state}', "
            f"expected '{screens.DOCUMENT_STATE_OPEN}'"
        )
    return problems


def invoice_row_problems(
    main_window: Any,
    order: NormalizedOrder,
    *,
    number: str,
    order_number: str,
    client: Any = None,
) -> list[str]:
    """Task 5.5 - the Invoice row's state and Total, and the source Order row
    still open with the same Cust.Ref. and Total."""
    tree_item = screens.DOCUMENTS_INVOICES_TREE_ITEM
    row, problems = _document_row(main_window, tree_item=tree_item, number=number, client=client)
    if row is not None:
        problems.extend(
            _common_row_problems(
                main_window, row, order, number=number, tree_item=tree_item, client=client
            )
        )
        problems.extend(_invoice_state_problems(row, order, number=number))

    # "...while the source Order remains open with the same Cust.Ref. and
    # Total" (5.5). Re-read rather than trust the check made before the
    # Invoice existed: creating and paying an Invoice is the thing that could
    # have changed the Order.
    problems.extend(order_row_problems(main_window, order, number=order_number, client=client))
    return problems


def _invoice_state_problems(
    row: dict[str, str], order: NormalizedOrder, *, number: str
) -> list[str]:
    state = row.get(screens.DOCUMENTS_COL_STATE, "")
    if order.is_paid:
        if _state_word(state) == screens.DOCUMENT_STATE_PAID:
            return []
        return [
            f"Documents: Invoice {number} state is '{state}', "
            f"expected '{screens.DOCUMENT_STATE_PAID}'"
        ]
    # An unpaid Invoice has never been seen in any probed workspace, so the
    # word Fakturama renders for one is unknown. Asserting it is *not* the paid
    # word is the strongest claim the evidence supports; inventing a third
    # constant would be a guess, and a wrong guess here passes silently.
    if _state_word(state) == screens.DOCUMENT_STATE_PAID:
        return [f"Documents: Invoice {number} state is '{state}', but the order is not paid"]
    return []


def _common_row_problems(
    main_window: Any,
    row: dict[str, str],
    order: NormalizedOrder,
    *,
    number: str,
    tree_item: str,
    client: Any,
) -> list[str]:
    problems: list[str] = []

    shown_number = row.get(screens.DOCUMENTS_COL_NUMBER, "")
    if not _same_document_number(number, shown_number):
        problems.append(f"Documents: searched for {number} and the row shows '{shown_number}'")

    # The Date column carries whatever Fakturama proposed, because nothing
    # writes the Order Date yet (TODo.md: populate_order_fields writes only
    # Cust.Ref.). Comparing it to order.order_date would fail every run, so
    # this only asserts the cell holds a date at all. comparisons.date_equals
    # already exists for the real check and drops in here in one line once the
    # write side lands.
    date_text = row.get(screens.DOCUMENTS_COL_DATE, "")
    if comparisons.parse_ui_date(date_text) is None:
        problems.append(f"Documents: {number} has no readable Date ('{date_text}')")

    problems.extend(
        _customer_ref_problems(
            main_window, row, order, number=number, tree_item=tree_item, client=client
        )
    )

    _, _, gross_total = comparisons.order_level_totals(order)
    total_text = row.get(screens.DOCUMENTS_COL_TOTAL, "")
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Documents: {number} Total is '{total_text}', expected {gross_total}")
    return problems


def _customer_ref_problems(
    main_window: Any,
    row: dict[str, str],
    order: NormalizedOrder,
    *,
    number: str,
    tree_item: str,
    client: Any,
) -> list[str]:
    """Compare Cust.Ref., or prove it a way column width cannot defeat.

    This column renders clipped on a default profile - live, a 17-character
    reference comes back as 'WEB-2026-07...' - and this is the one grid the
    ADR 0017 widen does not fit (see `_search`). So when the cell is clipped,
    ask Fakturama's own filter instead of the pixels: its search box ANDs
    whitespace-separated terms (probed live - 'INV000002 WEB-2026-0714-A17'
    returns the row, 'INV000002 WEB-2026-0714-A99' returns nothing), so a
    single row surviving a filter on the number *and* the full reference is
    exact evidence that the document carries it.

    Deliberately still a one-row read. The first version of this compared the
    number against a multi-row read of everything sharing the reference, and
    the vision model transcribed 'INV000002' as 'INV0000002' in a four-row
    capture - a long run of zeros is exactly what an OCR-ish read miscounts.
    One row makes it rarer, not impossible (the same miscount later happened
    on a one-row read, hence `_same_document_number`), so nothing here depends
    on the transcribed number: this filter is what discriminates.
    """
    shown = row.get(screens.DOCUMENTS_COL_CUSTOMER_REF, "")
    if not grid_columns.is_clipped(shown):
        if comparisons.text_equals(order.external_reference, shown):
            return []
        return [
            f"Documents: {number} Cust.Ref. is '{shown}', "
            f"expected '{order.external_reference}'"
        ]

    logger.info(
        "Documents: %s Cust.Ref. renders clipped (%r) - re-filtering on number + reference",
        number,
        shown,
    )
    rows = _search(
        main_window,
        tree_item=tree_item,
        key=f"{number} {order.external_reference}",
        client=client,
    )
    if len(rows) == 1:
        return []
    return [
        f"Documents: filtering {tree_item} on '{number}' and Cust.Ref. "
        f"'{order.external_reference}' returned {len(rows)} rows; expected exactly one"
    ]


def _document_row(
    main_window: Any, *, tree_item: str, number: str, client: Any
) -> tuple[dict[str, str] | None, list[str]]:
    rows = _search(main_window, tree_item=tree_item, key=number, client=client)
    if not rows:
        # Never a skip. The whole point of this check is that the editor can
        # read back perfectly while nothing was written.
        return None, [f"Documents: no {tree_item} row for {number}"]
    if len(rows) > 1:
        return None, [f"Documents: {len(rows)} {tree_item} rows for {number}; expected exactly one"]
    return rows[0], []


def _search(main_window: Any, *, tree_item: str, key: str, client: Any) -> list[dict[str, str]]:
    list_grids.open_list_screen(main_window, screens.DOCUMENTS_NAV_NAME)
    _select_document_type(main_window, tree_item)
    return list_grids.search_grid_exact(
        main_window,
        grid_pane_name=screens.DOCUMENTS_GRID_PANE_NAME,
        key=key,
        columns=screens.DOCUMENTS_READ_COLUMNS,
        grid_pane_locator=locators.documents_grid_pane,
        # This grid measures 8 separators for its 9 rendered columns - no pane
        # border, no leading grid edge - where widen_column's arithmetic wants
        # n + 2 and indexes a column from separators[i + 2]. Handing it a
        # measurement shaped differently than it expects is how ADR 0017's own
        # worst failure happened (it resized the wrong column and squeezed the
        # one it was sent to fix), so this grid opts out, and
        # _customer_ref_problems deals with its one clipped column by
        # filtering instead of by pixels.
        widen_clipped=False,
        vision_client=client,
    )


def _select_document_type(main_window: Any, tree_item: str) -> None:
    # Mandatory, not cosmetic: the tree scopes the search box. Typing an
    # invoice number while Orders is selected returns no rows, which would read
    # as "the document was never saved" (captured:
    # probes/probe_documents_output/documents-Orders-INV000002-rows.png).
    controls.focus(main_window)
    pane = controls.find_control(main_window, "Pane", name=screens.DOCUMENTS_GRID_PANE_NAME)
    controls.find_control(pane, "TreeItem", name=tree_item).click_input()
