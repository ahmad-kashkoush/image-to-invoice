
# Fakturama Automation

See [Doc/Design.md](Doc/Design.md) for the architecture and design decisions,
and [Gaps and next steps](#gaps-and-next-steps) for what the build is missing
and what I would do with three more hours.

Takes a single order image, extracts and normalizes its data via a vision
LLM, and drives Fakturama's UI to produce a saved Order, a linked Invoice, and the correct payment status.
## Demo

The recording below shows the complete process, from the order image to a saved and verified invoice.

https://github.com/user-attachments/assets/2cf5215d-e279-4c58-830c-274da4966360

## Getting Started

### Prerequisites

* Windows.
* Python.

### Setup

If you're using Claude Code, run the `/setup` skill (`.claude/skills/setup/`) to create the virtual environment, install dependencies, and configure `.env`.

Otherwise:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp .env.example .env  # then fill in ANTHROPIC_API_KEY
```

### Running the Workflow

* Open the Fakturama application.
* Run this command:

```bash
python -m fakturama_automation.orchestrator <image_path>
```

## Project Structure

```
├── src/fakturama_automation/    the installable package
│   ├── extraction/              vision-LLM read of the order image
│   ├── normalization/           raw text → typed, validated values
│   ├── entity_resolution/       exact-match search-then-create for master data
│   ├── ui_automation/           pywinauto uia wrapper: locate, act, poll
│   ├── verification/            reads state back after every write
│   ├── orchestrator/            the state machine over all of the above
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

* **Order Date is not written or verified.** Extracted correctly, but `populate_order_fields` only writes Cust. Ref. → Write Order Date and verify it on read-back.
* **Currency is not verified.** Currency symbols are stripped before comparison → Compare the currency explicitly in `verification/comparisons.py`.
* **Verification reads the open editor instead of `Data > Documents`.** → Verify saved Orders and Invoices from the Documents list.
* **Addresses are not verified.** Cust. Ref., item lines, and totals are verified, but addresses are not → Read addresses back and compare them with the normalized record.

#### Hardening

* **Debtor matching does not follow task 2.3.** It currently relies on Fakturama's search returning exactly one row rather than verifying all five fields → Match using Customer ID for independent exact-match verification.
- Refactor the whole project.

#### Nice to have requirements

* **Debtor creation is incomplete.** E-Mail, Telephone, address roles, Miscellaneous fields, and Alias name are not populated.
* **Payment methods are incomplete.** Only the Name is set; Description and payment-code mapping are not configured.
* **VAT rates are incomplete.** Created as `19%` instead of `VAT 19%`; the E-Invoice VAT code is not set or verified.
* **Product creation is incomplete.** Description, cost price, and Stock are left at Fakturama defaults.
* **OCR fallback is not implemented.** Low-confidence fields go directly to manual review instead of being re-read with OCR.
