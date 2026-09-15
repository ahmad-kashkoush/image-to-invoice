# 0019. The Order's payment term is set by swapping the profile standard, because nothing else can

## Status

Accepted. Closes the open item named in
[0018](0018-clean-profile-ordering-and-app-errors.md)'s Consequences.

## Context

ADR 0018 guaranteed that *a* Payment record exists before an Order is
created - without one, creating the Invoice from that Order dies inside
Fakturama - but left the Order's own term as whatever the profile's standard
happened to be. The expectation was that this would be closed the way every
other order-level field is: find the control, write it in
`populate_order_fields`, verify it in `order_verification._field_problems`.

**There is no control.** Probed live 2026-09-15 on both an unsaved
`New Order` and a saved `PO000003`: 74 descendants each, three ComboBoxes
(the unnamed pricing-mode one, `VAT`, `Shipping`), no CheckBox, and nothing
anywhere in the editor whose name contains pay / term / paid. The only
"terms of payment" string in the whole window is the left-hand navigation
link. Fakturama exposes a payment section on Invoice-type documents
(`locators.payment_method_combo` drives it) and simply does not on Orders.

The Debtor is not a way round it either. `FKT_CONTACT` does carry
`FK_PAYMENT`, and the Northstar Debtor already held `Bank Transfer` - yet
the Order attached to it came out stamped `Cash On Delivery`. The Order is
constructed before `_attach_debtor_to_order` runs, and attaching does not
re-apply the contact's term.

The defect is real and silent. With the profile's standard set to
`Cash On Delivery` and the order specifying `Bank Transfer`, a run reported
`DONE` and wrote:

| document | `FK_PAYMENT` | |
|---|---|---|
| `PO000003` (Order) | 2 | Cash On Delivery - wrong |
| `INV000003` (Invoice) | 1 | Bank Transfer - correct |

The Invoice is right because `apply_payment` sets it explicitly and
`verify_payment_applied` checks it. Nothing looked at the Order.

## Decisions

- **Set the standard, create the Order, put the standard back.**
  `open_new_order` reads the current standard, makes the order's own term
  standard if it differs, creates the Order, and restores the previous one in
  a `finally`. Fakturama stamps the Order at construction, so this is the only
  moment that decides anything.

- **The swap is bounded rather than permanent.** Leaving the standard changed
  would be less code and has no restore-on-crash hole, but the standard
  Payment is a profile-wide default that a person using Fakturama alongside
  this relies on; silently repointing it at whatever the last processed order
  used is a worse trade than the `finally`. The `finally` runs even when
  Order creation fails.

- **`make_standard` verifies itself by reading the list back.** The
  "Set as standard" button gives no feedback, and live it does nothing at all
  when clicked on an unsaved record - exactly the silent no-op that produced
  the wrong term in the first place. A standard that did not take raises
  `ManualReviewRequired` rather than letting the Order inherit the wrong term.

- **`standard_payment_name` reads the list's own Standard column** rather
  than the Eclipse preference file. The preference is written on exit, so a
  force-killed app leaves it stale - observed while building this - and
  reading app state out of a config file is not something the rest of this
  codebase does.

- **No verification is added to `order_verification._field_problems`.** There
  is no control to read the Order's term from, so a check there would have to
  read some other surface and pretend. The guarantee lives where the value is
  actually set, in `make_standard`'s read-back.

## Consequences

- Verified live against a profile whose standard differs from the order:
  `PO000004` carries `Bank Transfer` where `PO000003` carried
  `Cash On Delivery`, and `standardpayment` is back to `2` after the run.

- **Two extra list round-trips per order** - reading the standard, and setting
  it twice. Each is a grid search plus a vision read, so this costs a few
  seconds and two API calls on every run, including the common case where the
  standard already matches (the read still happens; only the swap is skipped).

- **Concurrency is now unsafe in a way it was not.** Two runs against the
  same Fakturama profile would fight over the standard Payment. Nothing in
  this system runs concurrently today, and the Order editor gives no
  alternative, but it is a real constraint to know about.

- If the process is killed between the swap and the restore, the profile is
  left with the order's term as standard. The `finally` covers exceptions,
  not `SIGKILL`. The next run restores it to whatever it then finds, which is
  self-correcting but not immediately obvious.

- The Order's term is now correct at creation, so the Invoice inherits the
  right value before `apply_payment` sets it anyway - the two now agree
  rather than the Invoice silently overwriting a wrong inheritance.
