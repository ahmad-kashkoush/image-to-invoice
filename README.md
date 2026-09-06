
# Fakturama Automation

See [Doc/Design.md](Doc/Design.md) for the architecture and design decisions.

Takes a single order image, extracts and normalizes its data via a vision
LLM (with OCR as a low confidence fallback), and drives Fakturama's UI to
produce a saved Order, a linked Invoice, and the correct payment status.

Every important step is verified before the workflow moves on. Ambiguous
matches or failed verifications stop the flow for manual review rather
than continuing silently.

Out of scope: Delivery, Correction, and Dunning documents.

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

# Progress

**[Demo video — TODO: add link]**

## Done

- [x] Image Extraction
- [x] Normalization & Validation
- [x] UI Automation (control discovery)
- [x] Entity Resolution
- [x] Verification
- [x] Error Handling
- [x] Orchestrator
- [ ] Full live run through `ADD_ORDER_LINES` and beyond (blocked, see
      `TODo.md`'s "Not started" section)

## Next Steps

If I have 3 more hours I will:

- Fix `ADD_ORDER_LINES` on a multi-line
  order.
- Fix `vat_rate.py` such as `debtor.py`
- Probe the unprobed screens (Data > Documents, the linked Invoice
  editor, its payment controls) with `spikes/uia_probe_editor.py` and
  fill in `verification/config.py`'s empty placeholders.
- Run the full workflow end-to-end on the golden sample order
  (`WEB-2026-0714-A17`) and fix whatever the first live failure past
  `ADD_ORDER_LINES` turns out to be.
