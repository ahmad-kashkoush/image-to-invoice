
# Fakturama Automation

See [Doc/Design.md](Doc/Design.md) for the architecture and design decisions,
and [Next Steps](#next-steps) for what the build is missing and what I would
do with three more hours.

Takes a single order image, extracts and normalizes its data via a vision
LLM, and drives Fakturama's UI to produce a saved Order, a linked Invoice, and the correct payment status.
## Demo

The recording below shows the complete process, from the order image to a saved and verified invoice.

https://github.com/user-attachments/assets/2cf5215d-e279-4c58-830c-274da4966360

## Getting Started

### Prerequisites

* Windows 10/11 — `pywinauto`'s `uia` backend is Windows-only, so the
  workflow cannot run on macOS or Linux. (Extraction and normalization are
  pure Python and do import there.)
* Python 3.11 or newer (`pyproject.toml`'s `requires-python`).
* [Fakturama](https://www.fakturama.info/download/), installed and running.
* An `ANTHROPIC_API_KEY` for the vision extraction pass.

### Setup

If you're using Claude Code, run the `/setup` skill (`.claude/skills/setup/`) to create the virtual environment, install dependencies, and configure `.env`.

Otherwise, from the repo root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"

copy .env.example .env   # then fill in ANTHROPIC_API_KEY
```

`pyproject.toml` is the authoritative dependency list — the command above
installs it. `requirements.txt` holds the same set with a comment per
dependency explaining why it's needed; it's there to be read, not installed
from.

### Running the Workflow

* Open the Fakturama application.
* Run this command (from the repo root, in PowerShell):

```powershell
.venv\Scripts\python -m fakturama_automation.orchestrator <image_path>
```

Or activate the environment first (`.venv\Scripts\Activate.ps1`) and drop the
`.venv\Scripts\` prefix.

## Project Structure

```
├── src/fakturama_automation/    the installable package
│   ├── extraction/              vision-LLM read of the order image
│   ├── normalization/           raw text → typed, validated values
│   ├── entity_resolution/       exact-match search-then-create for master data
│   ├── ui_automation/           pywinauto uia wrapper: locate, act, poll
│   │                            (screens.py: every selector, by screen)
│   ├── verification/            reads state back after every write
│   ├── orchestrator/            the state machine, plus steps/ (one
│   │                            module per Fakturama screen it drives)
│   └── error_handling/          stop point → out/manual_review_queue.jsonl
├── tests/                       pure-logic tests, mirroring the packages above
├── spikes/                      read-only UIA control-tree probes
├── probes/                      their captured output, one file per dialog
├── Doc/
│   ├── Design.md                architecture and tradeoffs
│   ├── implementation-notes.md  what the live app actually required, and why
│   ├── adr/                     one ADR per decision the design didn't dictate
│   ├── Diagrams/                architecture, resolution flow, workflow loop
│   └── Task Description.md      the original assessment brief
├── Assets/                      sample order image
├── out/                         run output, gitignored
├── .claude/                     Claude Code skills and saved plans
├── TODo.md                      per-section status and open work
├── pyproject.toml
└── .env.example
```


## Progress

### Done

- [x] Image Extraction
- [x] Normalization & Validation
- [x] UI Automation (control discovery)
- [x] Entity Resolution
- [x] Verification
- [x] Error Handling
- [x] Orchestrator
- [x] Full live run, end to end.

Per-section status, the files each section touched, and the open work behind
the list below are in [TODo.md](TODo.md).

### Next Steps

If I have 3 more hours, I'll work on the following:

#### Bugs & flaws

* **Order Date is not written or verified.** Extracted correctly, but `orchestrator/steps/order_editor.py::populate_order_fields` only writes Cust. Ref. → Write Order Date and verify it on read-back.
* **Currency is never extracted.** It is absent from the extraction schema and from both models, and both parsers strip currency symbols before comparing, so a `$` total verifies clean against a EUR order → Add `currency` to `RawOrder`/`NormalizedOrder` and compare it in `verification/comparisons.py`.
* **Verification reads the open editor instead of `Data > Documents`.** → Verify saved Orders and Invoices from the Documents list.
* **Addresses are not verified.** Cust. Ref., item lines, and totals are verified, but addresses are not → Read addresses back and compare them with the normalized record.

#### Hardening

* **Debtor matching does not follow task 2.3.** It currently relies on Fakturama's search returning exactly one row rather than verifying all five fields → Have `resolve_debtor` return the Customer ID (the `ResolvedEntity` it already builds is discarded by every caller) and match on it, which the Company column's clipping makes impossible today.
* **Master-data creation is the one mutation with no verification.** Order save, Invoice creation, payment and Invoice save each read back; creating a Debtor/Product/VAT rate/Payment Method does not → Read the record back after Save, per task 2.12/3.12.
* **Refactoring.** The P0 pass is done (`Doc/adr/0009`, `.claude/plans/refactoring-architecture-review.md`); P1 remains — one parsing module instead of three near-copies, and a golden-PNG test for `ui_automation/grid_geometry.py`.

#### Nice to have requirements

* **Debtor creation is incomplete.** E-Mail, Telephone, address roles, Miscellaneous fields, and Alias name are not populated.
* **Payment methods are incomplete.** Only the Name is set; Description and payment-code mapping are not configured.
* **VAT rates are incomplete.** Created as `19%` instead of `VAT 19%`; the E-Invoice VAT code is not set or verified.
* **Product creation is incomplete.** Description, cost price, and Stock are left at Fakturama defaults.
* **OCR fallback is not implemented.** Low-confidence fields go directly to manual review instead of being re-read with OCR.
