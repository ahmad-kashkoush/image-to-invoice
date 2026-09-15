# 0015. Select combo options through UIA, not by clicking a vision-located pixel

## Status

Accepted. Supersedes the coordinate-click half of
[0006](0006-combo-selection.md) and all of
[0013](0013-combo-popup-crop.md).

## Context

ADR 0006 established how `entity_resolution/combos.py` drives the two
combos this pipeline fills in — Country (Debtor form) and VAT (Product
form). Its central finding was correct and still is: the popup a combo
opens renders as a separate top-level window whose UIA subtree is **empty**,
so the options cannot be *read* out of the control tree. From that it
concluded the options had to be read by a vision model and then clicked by
screen coordinate. ADR 0013 kept that design and tried to make it accurate
by cropping the screenshot to the located popup instead of the whole window.

Live on 2026-09-15, the first post-refactor run of the golden sample stopped
at `resolve_product`:

```
no unique VAT option matching 19%; options were []
```

`spikes/uia_probe_combo_vat_read.py`
(`probes/probe-14-combo-vat-read.txt`) reproduced it and measured both
capture modes against the same on-screen popup:

- **Popup crop (ADR 0013).** `_locate_open_popup` found the popup correctly
  — rect `(532,528)-(598,555)`, directly below the combo at
  `(532,500)-(593,528)`. The region and the coordinate mapping were both
  right. But the crop is **66x27 px**, and the vision read of it returned
  `[]`. A one-option VAT combo is simply too small an image for the model to
  identify as an option list.
- **Whole window (ADR 0006).** The same screen, captured whole, *did* return
  `'19%'` — with `bbox=(420, 410, 451, 20)` for an option that really sits at
  `(541, 537, 66, 27)`: about 130px too high and seven times too wide.
  Clicking that lands in the Description field.

So neither mode works, and there is no third capture size that fixes both:
too small to read, or too large to ground. That single measurement also
explains the 2026-09-14 stop where the code selected `Germany` and the combo
read back `Ghana` — the same bad grounding, on a run where the popup was not
found and the code fell back to the whole window.

The failure message blamed DPI scaling. That is wrong, and was worth ruling
out explicitly: the display runs at 125% and a plain `python.exe` is
DPI-unaware, but `pywinauto` calls `SetProcessDpiAwareness` at import
(`win32functions.py:733-739`), so the orchestrator is per-monitor aware.
Measured on the live window, `rectangle()` and `capture_as_image()` are both
1938x1048 — exactly 1:1.

What ADR 0006 never tested is whether the options can be **selected** by name
even though they cannot be read. They can. The items are *virtualized*:
pywinauto's `ComboBoxWrapper.select()` resolves them through the
ItemContainer pattern, which finds an item by name without it ever appearing
as a child. Measured live on the Country combo: `item_count()` is 252 while
`descendants()` is empty, and `select("Germany")` / `select("Ghana")` move
between them correctly, verified by read-back every time.

Two combos in this codebase already selected this way and had never
failed — the pricing-mode combo (`orchestrator/steps/order_editor.py:58`)
and the Invoice payment-method combo
(`orchestrator/steps/invoice_editor.py:28`). ADR 0006 noted the second one
and set it aside as "not part of the detached-popup problem". It was in fact
the counter-example.

## Decisions

- **Select by name through UIA: `combo.select(option_text)`.** No
  screenshot, no vision call, no coordinate arithmetic. This removes
  `_locate_open_popup`, `_read_open_combo_options`, `_click_and_confirm`'s
  bbox math, `pick_option`, and the `client` parameter from both public
  functions.

- **Keep the read-back check, unchanged in spirit.** After selecting, sleep
  `settle_seconds`, re-read the combo and apply the same predicate the caller
  wanted (exact string for Country, numeric `parse_percent_text` for VAT).
  This was the one part of the old implementation that was always doing its
  job, and it is what makes the change safe to land on a mechanism that is
  itself only verified live.

- **Treat any exception from `select()` as fail-closed.** pywinauto raises
  `IndexError("item 'X' not found or can't be accessed")` and leaves the
  combo's value untouched — verified live. It is caught broadly rather than
  narrowly: the backend is free to raise something else, and every failure to
  select means the same thing to the caller. The reason string reports what
  was asked for and what the combo currently reads.

- **`f"{vat_percent}%"` is the VAT option string, and that is not a guess.**
  It is the exact text `entity_resolution/vat_rate.py` writes into the VAT
  Name field when it creates a rate, and the identity it returns for one it
  matched. Because options cannot be enumerated, the numeric tolerance that
  `select_vat_option` used to apply while *searching* now applies only while
  *verifying*. A rate stored under a different spelling fails closed here;
  surfacing that is `resolve_vat_rate`'s job, not this function's to paper
  over. This is the one real capability lost, and it is recorded below.

- **Keep `vision_grounding.read_combo_options` and `ComboOption`.** They are
  unused by the pipeline now, but they are correct *readers* — the text they
  returned was right; only the bbox was not — and
  `spikes/uia_probe_combo_vat_read.py` uses them to demonstrate exactly that.
  Deleting them would delete the evidence for this ADR.

- **Drop `COMBO_POPUP_SETTLE_TIMEOUT_SECONDS`** from
  `entity_resolution/config.py`. Nothing in the pipeline polls for a popup
  any more. The probe carries its own copy of the locator and its own
  default.

## Consequences

- The `resolve_product` stop is gone: live 2026-09-15, the same order that
  stopped at `no unique VAT option matching 19%; options were []` now logs
  `matched existing VAT rate 19%` and `created product SKU 'CHR-ERG-01'`.

- Two vision API calls per combo open disappear, along with a full-window
  PNG encode each. ADR 0013's performance complaint ("takes too long until
  it selects the correct option", worst on the 252-option Country combo) is
  answered by deletion rather than by tuning.

- **Options can no longer be enumerated, so a stop cannot list them.** The
  old reason string ended `options were [...]`, which was genuinely useful
  for diagnosis when the read worked. The new one reports the requested text
  and the combo's current value instead. If listing options becomes necessary
  again, the honest way to get them is the list *grid* behind the combo
  (`VATs`, and the country list), which `search_grid_exact` already reads
  reliably — not another screenshot of a popup.

- **Numeric VAT matching is now verify-only.** A profile whose VAT rate is
  named `19,00%` rather than `19%` will fail closed at
  `select_vat_option` instead of matching. That is the fail-closed direction,
  but it is a behaviour change and it is untested — the populated-profile run
  that would exercise it is still blocked behind the price-locale bug
  (`TODo.md` Open item 2).

- The Country combo's UIA selection is verified directly by probe (four
  selections, each read back) but has not yet run *in situ* inside
  `_create_debtor`, because the run that would do it now matches an existing
  Debtor rather than creating one. It needs a clean-profile run to be
  properly confirmed.

- ADR 0006's Open item — the country-code-to-name mapping (`TODo.md`) — is
  unchanged and still open. `select_exact_option` remains case-sensitive and
  exact by design.
