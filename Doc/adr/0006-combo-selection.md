# 0006. Combo selection: coordinate click on a vision-read option, screenshotting the main window instead of the undiscoverable popup

## Status

Accepted

## Context

Section 4's last open item (`.claude/plans/entity-resolution-residual.md`)
was the two guessed `ComboBox.select(...)` calls — product's VAT combo
(`product.py`) and debtor's Country combo (`debtor.py`) — left in place
since Doc/adr/0003 because neither combo's real option strings had been
confirmed. Probing them directly, with each dropdown actually held open
(`probes/probe-11-product-vat-combo-open.txt`,
`probes/probe-12-debito-country-combo-open.txt`), found:

- The opened popup renders as a **single, childless `Pane`** — no
  `ComboBoxItem`/`ListItem` entries, no readable option text via UIA. This
  is the same UIA-opacity signature the list grids have (Doc/adr/0003),
  which `ComboBox.select()`'s usual `.texts()` read depends on and can't
  use here.
- Unlike the list grids — which are at least UIA-visible-but-empty
  descendants of the main window — this popup **did not appear to be a
  descendant of the main window at all**. `ui_automation.controls.
  find_control(main_window, ...)` walks `main_window`'s own descendant
  tree, so it cannot locate this popup to begin with, regardless of what
  reading strategy is used once it's found.

Two option-reading strategies were available: enumerate the combo's
options a different way (type-ahead keystrokes into the combo's edit
part), or read the popup visually the way the list grids already are.
Once an option is identified, a second, distinct problem remains: there is
no UIA element to call `.select()` on, so *selecting* the matched option
needs its own answer too.

## Decisions

**1. Coordinate click on a vision-located option, not type-ahead.** Type-ahead
(`type_keys` into the combo's edit part to filter/highlight, then Enter)
was considered, but it requires the combo's edit part to be
editable/filterable — never probed either way, so choosing it would add a
new, unconfirmed probe dependency for no clear benefit over the
alternative. Coordinate click — screenshot wherever the dropdown is
visible, ask the vision model to both name and *locate* the option that
matches, click its screen coordinate — needs no new probe, and is
symmetric with how `ui_automation.vision_grounding.read_grid_rows` already
reads the UIA-invisible list grids: the same "screenshot a region, ask the
model to identify what's in it" pattern, extended to also ask for a
bounding box instead of just transcribed text.

**2. Screenshot `main_window` itself, not the popup, right after opening
the combo.** This is the decision that actually resolves the "popup isn't
a descendant of the main window" finding, rather than working around it.
`capture_as_image()` (already used by `vision_grounding.
capture_control_image`, reused unchanged here) is a screen-rect grab, not
a UIA-tree walk: it captures whatever is drawn on screen within a
control's bounding rectangle, including anything rendered on top of it by
the OS/toolkit. A combobox's dropdown normally renders within its parent
window's bounds, so screenshotting `main_window` right after
`combo.click_input()` captures the dropdown overlay too, without ever
needing a handle to the popup control itself — sidestepping the
UIA-tree-membership problem entirely instead of solving it (e.g. via a
`Desktop(backend="uia").windows()` top-level enumeration, which was
considered and rejected as a needless extra probe dependency when the
existing screenshot mechanism already reaches the pixels needed).

**3. `ui_automation.vision_grounding.read_combo_options` returns
`ComboOption(text, bbox)` pairs, not bare text.** `read_grid_rows` only
ever needed to return text, because its matches are filtered
(`entity_resolution.matching`) and returned as data, never clicked. Combo
options need to be *clicked*, and there is no UIA element left to click
via `.select()`/`click_input()` the normal way, so the vision model is
additionally asked to locate each option (a bounding box in image-pixel
coordinates) so the caller can convert it to an absolute screen point
(`main_window.rectangle()`'s top-left + the bbox's center) and click there
via `main_window.click_input(coords=..., absolute=True)`. This is the
first place in this codebase using a coordinate click rather than a UIA
selector — a deliberate, narrow exception to Doc/Design.md's stated
preference for UIA-grounded interaction, justified the same way the
grids' vision-grounded *read* fallback already is: "OCR or visual
inspection can disambiguate a control when UIA metadata is insufficient"
— extended here from disambiguating what to read to disambiguating where
to click, for a control class (popup lists) UIA cannot expose at all.

**4. Selection stays exact-match only, fail-closed.**
`entity_resolution.combos.pick_option` mirrors
`matching.exact_text_matches`/`exact_vat_matches`'s 0-or-more-than-one
counting: zero or ambiguous matches return `None`, and
`select_vat_option`/`select_exact_option` raise `ManualReviewRequired`
naming every option the dropdown actually offered, rather than picking the
first hit or falling back to a guess. VAT options are matched numerically
(`matching.parse_vat_text`, already public and reused unchanged); Country
options are matched by exact string equality, so a units mismatch (a
normalized ISO code like `"DE"` against a combo showing full names like
`"Germany"`) correctly fails closed instead of being silently treated as a
match.

## Consequences

- `entity_resolution/combos.py` (new) and
  `ui_automation/vision_grounding.py`'s new `read_combo_options` are fully
  unit-tested on macOS with duck-typed fakes and a fake vision client — no
  real window, no screenshot, no network — the same seam every other
  Section 4 module uses (Doc/adr/0003). `product.py`'s `_create_product`
  and `debtor.py`'s `_create_debtor` both gained a `client` keyword
  (threaded from `resolve_product`/`resolve_debtor`), since combo
  selection needs the same injectable vision client the grid search
  already threads through.
- Two assumptions are unverified until tried against a live window (both
  are known-limitation notes, not blockers — the code fails closed rather
  than guessing if either breaks): the captured screenshot's pixels map
  1:1 to screen coordinates (no DPI scaling), and the dropdown actually
  renders within `main_window`'s bounding rectangle rather than
  overflowing it (plausible for a combo near the very bottom edge of the
  window — no probe evidence either way, since neither probe pass tried a
  live click).
- This is the first coordinate-based click in an otherwise UIA-selector-
  driven codebase (Doc/Design.md's "the actual interaction still targets
  the corresponding UIA element rather than falling back to
  coordinate-based clicking" — written for the grids' *read* fallback, not
  anticipating a control UIA can't expose an element for at all). Any
  future control found to have the same "detached, childless popup"
  signature should reuse this same screenshot-main-window-and-click
  pattern rather than reinventing it.
- The Country-code-vs-name mismatch noted in Doc/adr/0003's Consequences
  is now a *confirmed*, not just guessed, failure mode:
  `select_exact_option` will raise `ManualReviewRequired` if Fakturama's
  Country combo turns out to show full names while normalized data holds
  ISO codes. A country-code-to-name mapping remains explicit future work
  (`TODo.md`).
