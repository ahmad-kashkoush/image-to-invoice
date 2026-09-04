# Fakturama Automation

Takes a single order image, extracts and normalizes its data via a vision
LLM (with OCR as a low confidence fallback), and drives Fakturama's UI to
produce a saved Order, a linked Invoice, and the correct payment status.

Every important step is verified before the workflow moves on. Ambiguous
matches or failed verifications stop the flow for manual review rather
than continuing silently.

Out of scope: Delivery, Correction, and Dunning documents.

## Known gaps in this build

This is a pre-interview demo build, not a production deployment, so a
couple of things were deliberately scoped down for cost/time rather than
left as accidental gaps:

- **Vision model**: extraction uses Claude Haiku 4.5 rather than a larger
  model, chosen for cost. It is vision-capable and sufficient for reading a
  single order image, but a production build would likely default to a
  larger, more capable model.
- **OCR fallback**: `fakturama_automation.extraction.ocr_fallback` is a
  stub (a no-op pass-through), not a real Tesseract/OCR implementation.
  This doesn't weaken correctness - fields the vision pass reports as low
  confidence are still caught by
  `normalization.validators.check_confidence` and routed to manual review;
  real OCR would only have recovered some of those cases by cross-checking
  against a second source, not gated correctness.

## Platform

This runs inside a Windows 11 ARM VM (via VMware Fusion on Apple Silicon),
with Fakturama installed inside the same VM. Automation uses pywinauto's
uia backend (real Microsoft UI Automation), not coordinate based clicking
and not the macOS Accessibility API. The code in this repo assumes it runs
on Windows; `pywinauto` will not import on macOS or Linux.

## VM setup

1. Install VMware Fusion on the Apple Silicon Mac.
2. Create a Windows 11 ARM VM.
3. Inside the VM, download and install Fakturama from
   https://www.fakturama.info/downloads.
4. Set up a shared folder between the Mac host and the VM, used as:
   - an in folder for order images to process
   - an out folder for logs and the manual review queue (entries written
     by `fakturama_automation.error_handling.manual_review` when a match
     is ambiguous or a verification fails)
5. Install Python 3.11+ inside the VM, then install the project in
   editable mode so the `fakturama_automation` package (under `src/`) is
   importable: `pip install -e .`. Plain `pip install -r requirements.txt`
   only gets you the pywinauto dependency, not this package on the path.

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
  queue.
- `spikes/uia_probe.py` - standalone, read only script to confirm real
  UIA control types and names come back from a running Fakturama window.
  Run this first. Kept outside `src/` since it is a one off probe, not
  part of the installable package.

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

## Notes

- Entity resolution is exact match only, no fuzzy matching. A wrong match
  is worse than routing to creation or manual review.
- Line totals are recomputed from quantity, unit price, and discount and
  compared against the source line total, both during normalization and
  again immediately after each order line is entered.
