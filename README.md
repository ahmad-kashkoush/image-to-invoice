
# Fakturama Automation

See [Doc/Design.md](Doc/Design.md) for the architecture and design decisions.

Takes a single order image, extracts and normalizes its data via a vision
LLM (with OCR as a low confidence fallback), and drives Fakturama's UI to
produce a saved Order, a linked Invoice, and the correct payment status.

Every important step is verified before the workflow moves on. Ambiguous
matches or failed verifications stop the flow for manual review rather
than continuing silently.

Out of scope: Delivery, Correction, and Dunning documents.

## Demo

The recording below is this project's "annotated screenshots or short
recording" deliverable — one continuous run from the order image to a
saved, verified Invoice.

https://github.com/user-attachments/assets/2cf5215d-e279-4c58-830c-274da4966360


## Setup

If you're using Claude Code, run the `/setup` skill (`.claude/skills/setup/`)
to create the virtualenv, install dependencies, and configure `.env`.
Otherwise:

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # then fill in ANTHROPIC_API_KEY

```

Running the workflow against Fakturama
(`python -m fakturama_automation.orchestrator <image_path>`) only works on
Windows, with the Fakturama application already open — `pywinauto`'s `uia`
backend it depends on doesn't work on macOS/Linux.

## Project structure

This uses a src layout: everything importable lives under
`src/fakturama_automation/`, nested under one package name, so it cannot
collide with an unrelated top level import elsewhere on the path, and so
running code always exercises the installed package rather than an
accidental local copy.

- `src/fakturama_automation/extraction/` - vision LLM extraction of raw
  order data, with an OCR fallback pass for low confidence fields.
- `src/fakturama_automation/normalization/` - converts raw extraction
  output into the typed values Fakturama's UI expects, and validates
  before automation starts.
- `src/fakturama_automation/entity_resolution/` - exact match
  search-then-create for Debtor, Product, VAT rate, and Payment Method.
- `src/fakturama_automation/ui_automation/` - pywinauto uia backend
  wrapper: control location, polling waits, no coordinates and no fixed
  sleeps.
- `src/fakturama_automation/verification/` - confirms Order save, Invoice
  creation, and payment fields after each step, before the workflow
  proceeds.
- `src/fakturama_automation/orchestrator/` - the state machine that ties
  the above together, one verify before advance.
- `src/fakturama_automation/error_handling/` - the single stop point for
  ambiguous matches or failed verifications, routing to the manual review
  queue (`out/manual_review_queue.jsonl`, one JSON object per stuck run).
- `spikes/uia_probe.py` - standalone, read only script to confirm real
  UIA control types and names come back from a running Fakturama window.
  Run this first. Kept outside `src/` since it is a one off probe, not
  part of the installable package.

Supporting documents: [Doc/Design.md](Doc/Design.md) (architecture and
tradeoffs), [Doc/implementation-notes.md](Doc/implementation-notes.md) (what
the live app actually required, and why), [Doc/adr/](Doc/adr/) (one ADR per
decision not dictated by the design doc), and [TODo.md](TODo.md) (per-section
status and the live debugging history).

## Suggested build order

1. **UIA spike (go/no-go).** Run `spikes/uia_probe.py` against a running
   Fakturama window and inspect the printed control tree. If it comes
   back sparse (Java/Eclipse RCP apps sometimes do not expose a rich UIA
   tree by default), check Java Access Bridge: run `jabswitch.exe /enable`
   and relaunch Fakturama, then rerun the probe. This step decides
   whether pywinauto's uia backend is viable at all before anything else
   is built.
2. **Extraction and normalization**, developed and tested independently
   of Fakturama against sample order images. No UI automation needed for
   this step.
3. **ui_automation read only discovery** against a running Fakturama
   window: confirm the specific control types, names, and hierarchy for
   the Order editor, Invoice editor, and search dialogs.
4. **ui_automation single field fill plus verify**, on the easiest field,
   to prove the act then verify pattern before building out the rest of
   ui_automation.
5. **entity_resolution**, search then create against Fakturama's own UI,
   for Debtor, Product, VAT rate, and Payment Method.
6. **orchestrator and error_handling**, assembling the full state machine
   from the pieces above.
7. **Invoice creation and payment status**, last, since it depends on an
   already verified saved Order.

# Progress

## Done

- [x] Image Extraction
- [x] Normalization & Validation
- [x] UI Automation (control discovery)
- [x] Entity Resolution
- [x] Verification
- [x] Error Handling
- [x] Orchestrator
- [x] **Full live run, end to end** (2026-09-06, Windows 11 ARM VM): one
      continuous run from the order image through all ten workflow states
      to `DONE` — Debtor and both Products resolved, the Order saved and
      verified, the linked Invoice created from the Order's own follow-up
      action, payment method and PAID status applied, and the Invoice
      saved and verified as persisted (`INV000001`, `PAID=TRUE`,
      `PAYDATE='2026-07-18'`, `PAIDVALUE=678.3`). No manual-review entry.

## Known gaps

Listed rather than hidden — these are the points where the build does not
yet cover the task specification. None of them fail silently: anything the
automation cannot confirm routes to manual review.

- **Order Date (task 1.5) is never written.** It is extracted and
  normalized correctly, but `populate_order_fields` only fills Cust.Ref.,
  so a saved Order carries Fakturama's proposed date instead of the
  extracted one. Nothing verifies it either. The most visible gap, and the
  cheapest to close.
- **Verification reads the open editor, not `Data > Documents`** (tasks 4.5
  / 5.5). The Order and Invoice are confirmed by reading their own editor
  fields back after save, with the assigned document number as the
  persistence signal; the independent second look at the Documents list was
  never probed, so it is not implemented.
- **Debtor creation fills a subset of the form** (tasks 2.7–2.9): Company,
  First/Last Name, Street, ZIP, City, Country. E-Mail, Telephone, the
  Invoice/Delivery address role assignment, and the Miscellaneous tab
  (Alias name, Discount 0%, Net) are not set. The extracted alias is
  currently written to the address's "additional name" field rather than
  Miscellaneous > Alias name.
- **Payment methods are created with Name only** (task 2.10). Description
  is left blank and the payment-code mapping (Bank Transfer → Credit
  transfer, Credit Card → Credit card, SEPA Direct Debit → SEPA direct
  debit) is not applied; Cash discount / Discount Days / Net Days stay at
  their defaults, which are already 0.
- **VAT rates are created as `19%`, not `VAT 19%`** (tasks 3.5/3.6), and
  the VAT code (E-Invoice) field is neither set nor checked against
  `S (Standard rate)`. The rate's own Value is correct, and is what
  resolution matches on.
- **Product creation sets Item Number, Name, Price (gross), and VAT**
  (tasks 3.8–3.10). Description, cost price, and Stock are left at
  Fakturama's defaults rather than explicitly written. The gross price is
  derived from the extracted net price and VAT
  (`normalization.validators.gross_from_net`), per task 3.9.
- **The Debtor picker matches on "exactly one row after Fakturama's own
  search"**, not the five-field Company/First/Name/ZIP/City comparison of
  task 2.3. That dialog's Company column can render narrower than the value
  it holds (a real "Northstar Office GmbH" row read back clipped to
  "thstar Office ..."), so an exact-text check could never pass even on the
  correct row. Ambiguity still fails closed — two rows stop the run. See
  [Doc/adr/0007-orchestrator.md](Doc/adr/0007-orchestrator.md).
- **Populated addresses are never read back** against the source image
  (tasks 2.4 / 4.1 / 5.1). Cust.Ref., every item line, and the order-level
  totals are.
- **The OCR fallback is a documented no-op** (`extraction/ocr_fallback.py`).
  Fields the vision pass reads with low confidence are not re-read; they
  fail closed to manual review via `validators.check_confidence` instead.
- **Currency is not compared anywhere.** `parse_money_text` strips currency
  symbols before comparing, so a `$`-rendering Fakturama verifies a EUR
  order without complaint.

## Next Steps

If I had 3 more hours, in order of return:

1. **Write the Order Date** (task 1.5) and verify it on read-back — the one
   extracted field that never reaches Fakturama.
2. **Probe `Data > Documents` and verify there** (tasks 4.5/5.5), instead of
   relying on the editor read-back as the source of truth for "it
   persisted". Same reasoning that made saving the Invoice its own workflow
   state: an open editor is not the database.
3. **Complete the master-data forms** — Debtor E-Mail/Telephone, address
   roles, and the Miscellaneous tab; the payment-code mapping; `VAT 19%`
   naming plus the E-Invoice code check; Product Description/cost/Stock.
   Mechanical, and it is what makes the created records match what a human
   would have entered.
4. **Read the populated Invoice and Delivery addresses back** against the
   normalized record (tasks 2.4/4.1/5.1), closing the last unverified field
   group.
5. **Match the Debtor by Customer ID instead of company name** in the
   "Select the address" picker, restoring independent exact-match
   verification there — needs `resolve_debtor` to capture that identifier
   first (see [Doc/adr/0007-orchestrator.md](Doc/adr/0007-orchestrator.md)'s
   Future work).
6. **Compare currency** in `verification/comparisons.py`, so a mismatched
   currency fails closed like every other field.
