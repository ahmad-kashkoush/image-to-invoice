## Objective

Build an automation system that takes a single order image, extracts and normalizes its data via OCR and/or an LLM, and drives Fakturama's UI to turn it into a saved Order, a linked Invoice, and the correct payment status. The automation must be robust to UI layout changes, relying on control discovery and semantic grounding rather than hardcoded coordinates, and each important operation must be verified before the next step so failures or ambiguous states are caught rather than silently ignored.
### Scope

1. Extracting and normalizing order-level data, debtor and address details, payment information, and per-item SKU, quantity, price, VAT, and discount.
2. Populating a new Order and resolving or creating the Debtor, Payment Method, and Products (with their VAT rates) as needed.
3. Entering and verifying order lines and totals.
4. Saving and verifying the Order.
5. Creating a linked Invoice and applying the payment status.
6. Stopping for manual review on any ambiguous match or failed verification. 

## System Architecture
The system processes an order image through extraction, normalization, UI automation, and verification. Ambiguous or failed operations are routed to manual review.

![System Architecture overview](Diagrams/System%20Architecture%20overview.png)

The architecture consists of six components, with UI Automation orchestrating the workflow. Each operation is verified before the workflow proceeds.
### Components
1. Image Extraction: OCR and/or an LLM read the source order image and produce raw structured data.
2. Normalization & Validation: extracted fields are cleaned, typed, and checked for completeness before automation begins.
3. UI Automation: drives Fakturama's UI via Microsoft UI Automation (UIA), locating and operating controls without hardcoded coordinates or a fixed layout.
4. Entity Resolution & Creation: given a required Debtor, Product, VAT rate, or Payment Method, searches for an exact match and creates it only when none exists, then returns the resolved record to UI Automation.
5. Verification: confirms the outcome of each save or selection before the workflow is allowed to proceed.
6. Error Handling & Manual Review: the single stop point reached from any ambiguous match or failed verification.
### Data Flow
Normalized order data flows once into UI Automation, which then exchanges control with Entity Resolution repeatedly: automation reaches a selector, resolution finds or creates the record, automation continues, and Verification gates every completed step before the next one starts. 

Each pass through the workflow performs one unit of work (opening the Order, resolving the Debtor, resolving a product line, saving the Order, creating the linked Invoice, applying payment) and is checked by Verification immediately after; a failed check routes to Error Handling, and a confirmed step advances to the next until the full set has been confirmed.

## Technical Details
### Image Extraction & Validation
This stage turns the order image into a structured, typed record that every later component can trust. A vision-capable LLM is used as the primary extractor rather than plain OCR alone, since it can read a full purchase order as one document (matching line items to their quantities and prices, associating an address block with the right role) rather than returning unstructured text that still needs to be re-assembled.

OCR is kept available as a secondary pass for fields the LLM reads with low confidence, such as a smudged SKU or a handwritten total, so the two methods can cross-check each other rather than relying on a single source of truth.

#### Data to extract
1. Order date and external reference.
2. Debtor company name, contact name, alias, billing and delivery addresses, and payment details.
3. Payment method, payment status, and payment date when present.
4. For every item: SKU, description, quantity, unit net price, VAT percentage, discount, and the source line total.

#### Normalization & Validation

Fields are converted into the types Fakturama's UI expects (dates to a canonical format, monetary values as rounded numbers, percentages as plain numbers, free text trimmed of extraction artifacts) before automation opens a New Order. Each line's extracted total is then recomputed from quantity, unit price, and discount and compared against the source total, since a mismatch signals a misread field; required fields such as the Debtor name or at least one item row are checked for presence. Any field that fails this recomputation, is missing, or carries a low confidence score stops the flow before it reaches Fakturama's UI and is surfaced for manual review, since an incorrect Debtor, price, or VAT rate at this stage would otherwise propagate into a saved financial record.

### UI Control Discovery & Grounding
Fakturama exposes its controls through Microsoft UI Automation (UIA), used as the primary mechanism for locating and interacting with them. Controls are discovered by semantic properties and UI context rather than screen coordinates, which makes the automation resilient to window resizing, monitor changes, and other layout shifts; the same discovery strategy applies across the Order, Debtor, Product, VAT, and Payment Method editors even though their layouts differ.

#### How controls are identified
Controls are resolved using multiple UIA properties and contextual relationships rather than a single identifier, since no individual property is guaranteed to be unique or stable across every dialog.
1. Control type (Button, ComboBox, Edit, Table) narrows the search to elements that support the expected interaction.
2. Accessible name or label (such as `Order` or `Save`) identifies the intended control within its UI context.
3. UI hierarchy and container scope the search to the expected window, dialog, or editor.
4. Relationships to surrounding controls disambiguate elements when name and type alone are insufficient, for example distinguishing the existing-contact selector from the create-contact button by its relationship to the `Addresses` section rather than screen position.

UI synchronization is treated as part of discovery rather than fixed sleep durations: after an action opens a new editor or dialog, the automation polls for the expected state, and for search-based selectors it also waits for the result set to stabilize before evaluating rows. UIA is the primary grounding mechanism, but OCR or visual inspection can disambiguate a control when UIA metadata is insufficient (for example, a custom-rendered element); the actual interaction still targets the corresponding UIA element rather than falling back to coordinate-based clicking.

Control discovery failures are treated as explicit workflow failures. The automation retries within a bounded timeout if the expected control is not yet available, applies additional hierarchy and contextual constraints if multiple candidates are found, and stops for manual review if candidates remain ambiguous or the UI enters an unexpected state. This preserves the system's central discover, act, verify, advance model: an action is only performed when the intended control can be confidently identified, and the workflow only advances after the resulting state has been verified.
![Workflow Loop](Diagrams/Workflow%20Loop.png)

### Workflow & Verification

The workflow that turns a normalized order record into a saved Order, a linked Invoice, and a correct payment status is state-driven rather than a single linear script, applying the same discover, act, verify, advance model at the level of the whole order lifecycle. Each state has a known precondition, a UI Automation action, and a verification check; if a state's verification fails, the workflow does not attempt to infer what went wrong, it routes to Error Handling and leaves the current state as the last confirmed point. This pattern is deliberately uniform across very different actions (filling a field, selecting a Debtor, saving a document, creating a linked Invoice) so the same failure-handling logic applies everywhere instead of being reimplemented per step.

The Order is opened and its order-level fields populated from the normalized record, handing off to Entity Resolution wherever a Debtor or Payment Method is required. Order lines are added one at a time, resolving each Product by exact SKU (creating it and its VAT rate if necessary), and each line's calculated total is checked against the source line total immediately after entry, rather than deferring that check to the end, so a misapplied VAT rate or discount is caught at the line where it occurred. Once every line is verified, addresses, products, and the overall total are validated before the Order is saved; the save itself is its own verified state, confirming the Order was actually persisted (an assigned Order number, no unsaved changes) and that its key fields match the normalized record, since only a save that passes this check is treated as the source of truth for what follows.

![Debtor & Product resolution flow](Diagrams/Debtor%20%26%20Product%20resolution%20flow.png)

The Invoice is created directly from the saved Order, rather than independently populated, so the Order-Invoice relationship is preserved natively and the Invoice inherits already-verified line items and totals. It is nonetheless re-verified independently against the same normalized record, since Fakturama's own Invoice-generation step is itself a point where a mismatch could be introduced. Finally, the extracted payment method is applied, and when the record indicates the order was marked PAID, the automation also sets the payment date and full invoice value; this action is likewise followed by verification, re-reading the Invoice's payment fields before the workflow is treated as complete.
## Tradeoffs & Design Decisions

| Decision | Chosen Approach | Alternative | Trade-off | Rationale |
|---|---|---|---|---|
| **Control identification** | UI Automation (UIA) | Visual / coordinate-based automation | Requires usable accessibility metadata and handling ambiguous controls | More resilient to resizing and minor UI changes; coordinate-based automation is too fragile for a production workflow. |
| **Document extraction** | Vision-capable LLM + targeted OCR | OCR-only | Higher complexity/cost in exchange for better structural understanding | The task requires understanding relationships between fields, not just reading text. OCR remains a secondary pass for low-confidence fields. |
| **Decision making** | Deterministic rules | LLM-based reasoning | Less flexible, but substantially lower risk of silent data corruption | Financially significant decisions such as totals, Debtor matching, and save verification must be predictable and auditable. |
| **Exception handling** | Manual review for ambiguous/failed cases | Fully autonomous processing | Lower throughput in exchange for correctness | Incorrect financial records are more costly than orders requiring human intervention. |
| **Validation** | Verify critical operations after execution | Assume successful execution | Adds execution time and implementation complexity | Prevents the system from reporting success when Fakturama did not actually persist the intended state. |
| **Debtor matching** | Exact deterministic matching | Fuzzy / LLM-based matching | May produce more unmatched Debtors | A false positive can associate an order with the wrong customer; an unmatched Debtor can safely be routed to creation or manual review. |

The system deliberately favors **correctness, predictability, and recoverability over maximum automation and throughput**. Probabilistic methods are used where interpretation is required, while deterministic rules and verification are used wherever correctness can be objectively established.

## Deliverables

Starting from a single order image, the system produces:

1. A saved and verified Order containing the extracted order data.
2. A saved and verified Invoice correctly linked to that Order
3. The extracted payment status correctly reflected on the Invoice.

## Future work (out of scope now)

1. Delivery.
2. Correction.
3. Dunning documents.
