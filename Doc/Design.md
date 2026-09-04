---
share_link: https://share.note.sx/tnanzqu3
share_updated: 2026-09-04T14:58:57+03:00
---
## Objective

Build an automation system that takes a single order image, extracts and normalizes its data via OCR and/or an LLM, and drives Fakturama's UI to turn it into a saved Order, a linked Invoice, and the correct payment status. The automation must be robust to UI layout changes, relying on control discovery and semantic grounding rather than hardcoded coordinates, and each important operation must be verified before the next step so failures or ambiguous states are caught rather than silently ignored.

Starting from a single order image, the system produces a saved and verified Order containing the extracted order data, a saved and verified Invoice correctly linked to that Order, and the extracted payment status correctly reflected on the Invoice.

### Scope
1. In Scope:
	1. Extracting and normalizing order-level data, debtor and address details, payment information, and per-item SKU, quantity, price, VAT, and discount.
	2. Populating a new Order and resolving or creating the Debtor, Payment Method, and Products (with their VAT rates) as needed.
	3. Entering and verifying order lines and totals.
	4. Saving and verifying the Order.
	5. Creating a linked Invoice and applying the payment status.
	6. Stopping for manual review on any ambiguous match or failed verification. 
2. Out of Scope:
	1. Delivery, Correction, and Dunning documents are out of scope.
## System Architecture

The system is organized around six components connected by a single verify-before-advance loop: UI Automation drives Fakturama's UI one step at a time, hands off to Entity Resolution whenever a Debtor, Product, VAT rate, or Payment Method is required, and only advances once Verification confirms the result. Ambiguous matches or failed verification exit into a single Error Handling path rather than continuing silently.
![System Architecture overview](Diagrams/System%20Architecture%20overview.png)

### Components
- Image Extraction: OCR and/or an LLM read the source order image and produce raw structured data.
- Normalization & Validation: extracted fields are cleaned, typed, and checked for completeness before automation begins.
- UI Automation: drives Fakturama's UI via Microsoft UI Automation (UIA), locating and operating controls without hardcoded coordinates or a fixed layout.
- Entity Resolution & Creation: given a required Debtor, Product, VAT rate, or Payment Method, searches for an exact match and creates it only when none exists, then returns the resolved record to UI Automation.
- Verification: confirms the outcome of each save or selection before the workflow is allowed to proceed.
- Error Handling & Manual Review: the single stop point reached from any ambiguous match or failed verification.
### Data Flow
Normalized order data flows once into UI Automation, which then exchanges control with Entity Resolution repeatedly: automation reaches a selector, resolution finds or creates the record, automation continues, and Verification gates every completed step before the next one starts. 

Each pass through the workflow performs one unit of work (opening the Order, resolving the Debtor, resolving a product line, saving the Order, creating the linked Invoice, applying payment) and is checked by Verification immediately after; a failed check routes to Error Handling, and a confirmed step advances to the next until the full set has been confirmed.

## Image Extraction & Validation

This stage turns the order image into a structured, typed record that every later component can trust. A vision-capable LLM is used as the primary extractor rather than plain OCR alone, since it can read a full purchase order as one document (matching line items to their quantities and prices, associating an address block with the right role) rather than returning unstructured text that still needs to be re-assembled.

OCR is kept available as a secondary pass for fields the LLM reads with low confidence, such as a smudged SKU or a handwritten total, so the two methods can cross-check each other rather than relying on a single source of truth.

### Data to extract

1. Order date and external reference.
2. Debtor company name, contact name, alias, billing and delivery addresses, and payment details.
3. Payment method, payment status, and payment date when present.
4. For every item: SKU, description, quantity, unit net price, VAT percentage, discount, and the source line total.

### Normalization & Validation

Fields are converted into the types Fakturama's UI expects (dates to a canonical format, monetary values as rounded numbers, percentages as plain numbers, free text trimmed of extraction artifacts) before automation opens a New Order. Each line's extracted total is then recomputed from quantity, unit price, and discount and compared against the source total, since a mismatch signals a misread field; required fields such as the Debtor name or at least one item row are checked for presence. Any field that fails this recomputation, is missing, or carries a low confidence score stops the flow before it reaches Fakturama's UI and is surfaced for manual review, since an incorrect Debtor, price, or VAT rate at this stage would otherwise propagate into a saved financial record.

**Implementation notes (`normalization/`):**
- The recomputation formula is `quantity x unit_net_price x (1 - discount / 100)`: discount is a plain percentage and VAT is excluded from the net line total, matching how Fakturama itself computes a line's net price. This single formula (`validators.recompute_line_total`) is shared by the normalizer, which fills in each line's `recomputed_total`, and by the check that compares it against the source total.
- Dates parse ISO (`YYYY-MM-DD`) first, with an unambiguous day-first fallback (`DD.MM.YYYY`) for the German-locale source documents this system targets; anything else (including an ambiguous slash date) fails closed rather than being guessed.
- Monetary and percentage fields tolerate both dot-decimal and European comma-decimal input, with currency symbols and thousands separators stripped, then round to 2 decimal places (half-up) for money.
- Confidence data lives on the raw extraction models (keyed by field name, per `extraction/models.py`), not on the normalized order, so the confidence check reads the `RawOrder` directly. It only evaluates fields the vision pass actually extracted (a non-empty raw value); a field the source document never had (e.g. a blank delivery address) is a completeness question for the required-fields check, not a confidence failure. A missing confidence key for an extracted field is treated as 0.0 (fail closed), never as high confidence.
- Every parse and validation failure on an order is collected and raised together as one `ManualReviewRequired`, rather than stopping at the first problem, so manual review sees the complete picture for that order in one pass.

See `Doc/adr/0001-normalization-and-validation.md` for the reasoning behind these choices.

## UI Control Discovery & Grounding

Fakturama exposes its controls through Microsoft UI Automation (UIA), used as the primary mechanism for locating and interacting with them. Controls are discovered by semantic properties and UI context rather than screen coordinates, which makes the automation resilient to window resizing, monitor changes, and other layout shifts; the same discovery strategy applies across the Order, Debtor, Product, VAT, and Payment Method editors even though their layouts differ.

### How controls are identified

Controls are resolved using multiple UIA properties and contextual relationships rather than a single identifier, since no individual property is guaranteed to be unique or stable across every dialog.

1. Control type (Button, ComboBox, Edit, Table) narrows the search to elements that support the expected interaction.
2. Accessible name or label (such as `Order` or `Save`) identifies the intended control within its UI context.
3. UI hierarchy and container scope the search to the expected window, dialog, or editor.
4. Relationships to surrounding controls disambiguate elements when name and type alone are insufficient, for example distinguishing the existing-contact selector from the create-contact button by its relationship to the `Addresses` section rather than screen position.

UI synchronization is treated as part of discovery rather than fixed sleep durations: after an action opens a new editor or dialog, the automation polls for the expected state, and for search-based selectors it also waits for the result set to stabilize before evaluating rows. UIA is the primary grounding mechanism, but OCR or visual inspection can disambiguate a control when UIA metadata is insufficient (for example, a custom-rendered element); the actual interaction still targets the corresponding UIA element rather than falling back to coordinate-based clicking.

Control discovery failures are treated as explicit workflow failures. The automation retries within a bounded timeout if the expected control is not yet available, applies additional hierarchy and contextual constraints if multiple candidates are found, and stops for manual review if candidates remain ambiguous or the UI enters an unexpected state. This preserves the system's central discover, act, verify, advance model: an action is only performed when the intended control can be confidently identified, and the workflow only advances after the resulting state has been verified.
![Workflow Loop](Diagrams/Workflow%20Loop.png)

**Implementation notes (`ui_automation/`):**
- `controls.find_control`/`find_all_controls` and `waits.wait_until`/`wait_for_dialog`/`wait_for_stable_row_count` never import `pywinauto` directly: they operate on whatever pywinauto object (`WindowSpecification`/`UIAWrapper`) the caller already holds, calling only its documented methods (`children(control_type=, title=)`, `window(title_re=)`, `exists()`). This is a deliberate testability seam - the same shape as extraction's injectable `client` parameter - and it keeps this half of the module importable and unit-testable on macOS/Linux, verified directly rather than assumed.
- `app.FakturamaApp` (and `spikes/uia_probe.py`) are the only places that `from pywinauto import Application`, which fails immediately off Windows (confirmed: the bare `import pywinauto` succeeds cross-platform, but the uia-backend symbols are not exposed). These can only be exercised against a real Fakturama window on the Windows 11 ARM VM.
- Ambiguity is raised the moment more than one candidate is seen, without waiting out the rest of the bounded timeout: an ambiguous match is a structural fact about the current search scope, not a timing race, so retrying the identical search would not resolve it - the caller narrows by passing a more specific parent instead (e.g. scoping to the `Addresses` section rather than the whole window).
- `FakturamaApp.window(title_re)` is a single generic dialog/editor accessor, not a named accessor per Fakturama screen (`order_editor()`, `debtor_editor()`, ...): the same discovery strategy applies across every editor and dialog, so Section 3 stays generic and Sections 4-6 compose `window(...)` with `find_control(...)` for whichever screen they need.

See `Doc/adr/0002-ui-automation-testability-boundary.md` for the reasoning behind this split.

## Workflow & Verification

The workflow that turns a normalized order record into a saved Order, a linked Invoice, and a correct payment status is state-driven rather than a single linear script, applying the same discover, act, verify, advance model at the level of the whole order lifecycle. Each state has a known precondition, a UI Automation action, and a verification check; if a state's verification fails, the workflow does not attempt to infer what went wrong, it routes to Error Handling and leaves the current state as the last confirmed point. This pattern is deliberately uniform across very different actions (filling a field, selecting a Debtor, saving a document, creating a linked Invoice) so the same failure-handling logic applies everywhere instead of being reimplemented per step.

The Order is opened and its order-level fields populated from the normalized record, handing off to Entity Resolution wherever a Debtor or Payment Method is required. Order lines are added one at a time, resolving each Product by exact SKU (creating it and its VAT rate if necessary), and each line's calculated total is checked against the source line total immediately after entry, rather than deferring that check to the end, so a misapplied VAT rate or discount is caught at the line where it occurred. Once every line is verified, addresses, products, and the overall total are validated before the Order is saved; the save itself is its own verified state, confirming the Order was actually persisted (an assigned Order number, no unsaved changes) and that its key fields match the normalized record, since only a save that passes this check is treated as the source of truth for what follows.

![Debtor & Product resolution flow](Diagrams/Debtor%20%26%20Product%20resolution%20flow.png)

The Invoice is created directly from the saved Order, rather than independently populated, so the Order-Invoice relationship is preserved natively and the Invoice inherits already-verified line items and totals. It is nonetheless re-verified independently against the same normalized record, since Fakturama's own Invoice-generation step is itself a point where a mismatch could be introduced. Finally, the extracted payment method is applied, and when the record indicates the order was marked PAID, the automation also sets the payment date and full invoice value; this action is likewise followed by verification, re-reading the Invoice's payment fields before the workflow is treated as complete.
## Tradeoffs & Design Decisions

**UIA vs. visual/coordinate-based automation.** UIA ties control identification to semantic properties that survive resizing and minor layout shifts, at the cost of requiring Fakturama's controls to expose usable accessibility metadata and handling cases where two controls share a name or type. That cost is accepted because a system that only works at one window size is not meaningfully more useful than a manual process.

**OCR vs. LLM/vision.** A vision-capable LLM is the primary extractor because the task is assembling structure (matching items to prices, addresses to roles), not just reading text; OCR alone would push that work into a brittle post-processing step instead of removing it. OCR is kept as a secondary, targeted pass for low-confidence fields rather than the sole method, balancing structural understanding against the ability to cross-check a genuinely ambiguous field.

**Deterministic rules vs. LLM reasoning.** Wherever a decision has a definite correct answer (a line total, an exact Debtor match, whether a save persisted), the system uses deterministic rules rather than LLM judgment, since a wrong answer there would silently corrupt a saved financial record. This costs some flexibility (an exact-match rule will not recognize "Acme Corp." and "Acme Corporation" as the same Debtor), which is traded away deliberately: a probabilistic match risks attaching an order to the wrong customer, a worse failure than routing an unmatched Debtor to creation or manual review.

**Automation vs. manual review.** The system stops and hands off to manual review whenever it encounters a low-confidence extraction, an ambiguous match, or a failed verification, rather than maximizing end-to-end completion. A fully autonomous system that occasionally guesses wrong would produce incorrect financial records that are more expensive to find and correct later than an order that simply waits for a person. This favors correctness and trust over throughput, and depends on ambiguous cases remaining the exception rather than the rule.
