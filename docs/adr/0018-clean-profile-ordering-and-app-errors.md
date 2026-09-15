# 0018. Resolve the payment term before the Order exists, and report Fakturama's own errors

## Status

Accepted.

## Context

The first clean-profile run (2026-09-15) created every entity correctly -
payment method, Debtor, VAT rate, both Products - saved and verified the
Order, and then stopped:

```
stopped at create_and_verify_invoice:
  no Edit control named 'Cust.Ref.' (auto_id=None) found within 5.0s
```

Which is not what happened. A `New Invoice` tab had opened with an empty body,
and Fakturama's own Error view held the real message. Its log had the cause:

```
Caused by: java.lang.NullPointerException: Cannot invoke
  "com.sebulli.fakturama.model.Payment.getNetDays()" because "parentPayment" is null
    at com.sebulli.fakturama.parts.DocumentEditor.copyFromSourceDocument(DocumentEditor.java:1271)
    at com.sebulli.fakturama.parts.DocumentEditor.init(DocumentEditor.java:1072)
```

Creating an Invoice *from* an Order copies the source document, including its
payment term. The Order had none, because of an ordering the pipeline had
never exercised: `OPEN_ORDER` created the Order editor, and only afterwards
did `POPULATE_ORDER_FIELDS` call `resolve_payment_method`. Fakturama gives a
new Order the standard Payment **at construction time**, so on a profile with
no Payment records at all the Order is built with a null one, and creating
the payment a few seconds later does not retro-fit it.

This could not reproduce on a populated profile - a Payment already exists
when the Order is opened - which is why every earlier run passed. It is a
good example of the class of bug the clean-profile condition exists to find.

Two false starts are worth recording, because both looked convincing:
the first hypothesis was editor accumulation (eight editor tabs were open,
and `entity_resolution` never closes what it opens), and the second was that
the Error surface was a modal. Neither survived contact with the log. The log
was the cheapest source of truth available and should have been the first
place checked, not the fourth.

## Decisions

- **`open_new_order` resolves the payment term before it clicks New Order.**
  The dependency lives in the function that has it, rather than being
  implied by state ordering in `state_machine.py`, and `populate_order_fields`
  carries a comment saying why the call is deliberately not there any more.
  `open_new_order` therefore takes the `NormalizedOrder`.

- **Report what the app says, at every failure.**
  `readers.app_error_text` checks the two surfaces Fakturama actually uses,
  neither of which is a top-level window and neither of which anything looked
  at before:
  - a **modal message box**, rendered as a *child* shell of the main window,
    so `app.top_level_window_by_title` cannot see it. It also disables the
    controls underneath, so the running step reports a dead control instead.
  - the **Eclipse "Error" view**, which opens as an *editor tab*. Its message
    sits in an unnamed read-only Edit, reachable only through the legacy
    value.

  `state_machine` appends it to the reason for every `ManualReviewRequired`
  and every UI-discovery error - one place, not per raise site. It is
  wrapped so that a failure to read diagnostics can never replace or mask the
  real failure.

- **It is not matched by dialog title.** Any modal is worth reporting and the
  set of titles this app uses is not known.

## Consequences

- The clean-profile run reaches `DONE`: payment method, Debtor (including the
  Country combo through UIA, ADR 0015's last unexercised path), VAT rate and
  both Products all created, Order and linked Invoice saved and verified,
  exit code 0. An immediate re-run against that end state also reaches `DONE`
  taking every match path, and the database holds exactly one Northstar
  contact and two Products at their correct net prices.

- Failure messages now name their cause. The same clean-profile stop reads:

  ```
  no Edit control named 'Cust.Ref.' ... [Fakturama reports: Error view: Unable
  to create class 'com.sebulli.fakturama.parts.DocumentEditor' ...]
  ```

  and the missing-Shipping stop quotes "No default value found for Shippings.
  Please set one from list!" instead of reporting a missing Pane. Each of
  those cost twenty minutes to diagnose the first time.

- **The Order's payment term is still never explicitly set** - it is whatever
  Fakturama defaults to. That is now guaranteed to exist, and the *Invoice's*
  payment is set and verified by `apply_payment` /
  `verify_payment_applied`, but an Order on a profile whose standard Payment
  is something other than the order's would carry the wrong term silently.
  Writing and verifying it on the Order editor is open work.
  **Addressed by [0019](0019-order-payment-term-via-the-standard.md)**, which
  found there is no such control on the Order editor at all and swaps the
  profile standard around Order creation instead.

- **`entity_resolution` still never closes the editors it opens.** A
  clean-profile run finishes with eight editor tabs. It was suspected here
  and cleared, but it remains untidy and is a plausible cause of some future
  resource failure.

- The default Shipping remains a documented profile precondition (README),
  not something the pipeline creates: unlike the payment term, a Shipping is
  not part of the order being read.
