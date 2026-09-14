# 0013. Combo popup crop: capture the located popup window directly, screenshot main_window only as a fallback

## Status

Accepted

## Context

Doc/adr/0006's Open item (`TODo.md` #6) left two assumptions about
`combos.py`'s coordinate-click design unverified: that screenshot pixels
map 1:1 to screen coordinates (no DPI scaling), and that a combo's popup
renders inside `main_window`'s own rectangle. Live use surfaced a second,
related problem ADR 0006 didn't anticipate: screenshotting the *whole*
main window and sending it to the vision model on every combo open is
slow, worst-case for the Country combo (~190 options) - reported live as
"takes too long until it selects the correct option."

`probes/probe-11`/`probe-12` had each found, once, that the opened popup
renders as a single, childless `Pane` - but never confirmed this
repeatably, never measured how long it takes to render, and never checked
whether it's actually a separate top-level window (locatable without
walking `main_window`'s own tree) rather than some other UIA relationship.
`spikes/uia_probe_combo_region.py` was written to answer exactly this, run
five times each against the two combo types this pipeline actually drives
through `combos.py` - Country (Debtor form) and VAT (Product form). (A
third "Payment Method" combo does not belong in this investigation:
`entity_resolution/payment_method.py`'s own create form has no combo at
all, and the Invoice editor's payment-method combo
(`orchestrator/steps/invoice_editor.py::apply_payment`) already selects via
plain `combo.select(...)` - it was never part of ADR 0006's "detached
popup" problem.)

Results (`probes/probe-13-combo-region-settle-{country,vat}.txt`), 5/5
repeats each:

- A new top-level window reliably appears on every open, for both combo
  types - `Desktop(backend="uia").windows()`, diffed before/after the
  click, found it every time, at an identical relative-to-main-window
  rectangle across all 5 repeats of each combo type. It confirmed absent
  from `main_window`'s own `descendants()` (`was_descendant_of_main_window:
  False` every time) - so ADR 0006's finding holds, but the window is
  locatable a different way than that ADR considered (`Desktop` top-level
  enumeration, which ADR 0006 rejected for the *production* screenshot path
  as "a needless extra probe dependency" - that reasoning applied when
  nothing had confirmed the enumeration was reliable; this probe is exactly
  that confirmation).
- Its `element_info.class_name` reads `"SysShadow"` for both combo types -
  Windows' own drop-shadow decoration class, not a Fakturama/SWT class.
  This looked at first like the probe had found the shadow effect rather
  than the actual popup content. Visual inspection of the saved screenshots
  (`_direct.png`, a capture of exactly this window) settled it: both show
  the real, complete option list (Germany...Hungary for Country, "19%" for
  VAT), matching what the corresponding region of the full-window
  screenshot (`_full.png`) shows. Whatever OS mechanism assigns this class
  name here, the window's rectangle and rendered pixels are the popup's
  real content, not a separate shadow layer - confirmed, not assumed.
- Rectangle contained in `main_window`'s own rectangle in all 10 repeats
  (`contained_in_main_window: True` throughout) - the second of ADR 0006's
  two open assumptions is now also confirmed, not just plausible.
- Real elapsed time from click to a stable popup rectangle: Country
  0.444-0.463s (mean 0.453s), VAT 0.361-0.409s (mean 0.383s) - well under
  the current flat 1.0s `SEARCH_SETTLE_SECONDS` sleep `combos.py` reused for
  this wait.

## Decisions

**1. Capture the located popup window directly, not a crop of a
main_window screenshot.** Both were considered; capturing the popup control
via the same `vision_grounding.capture_control_image` already used for
`main_window` needs no new code path and no coordinate arithmetic to turn a
popup rectangle into a crop box - `capture_as_image()` already grabs
whatever is on screen within a control's own rectangle, whichever control
that is.

**2. Locate the popup via `Desktop(backend="uia").windows()`, diffed
before/after the click - not `main_window.descendants()`.** ADR 0006 already
found the popup isn't in `main_window`'s own tree; this probe confirms that
finding and confirms the `Desktop`-level alternative it named (and set
aside, for the production path, as an unconfirmed extra dependency) is in
fact reliable for both combo types this pipeline drives. `_locate_open_popup`
polls this rather than sleeping a guess: unlike `SEARCH_SETTLE_SECONDS`'s
documented reason for preferring a flat sleep over polling (avoiding one
vision-API call per poll, Doc/adr/0003 Decision 2), polling a popup's own
`.rectangle()` is a local, free UIA read - there's no equivalent cost here
to avoid.

**3. Fall back to the whole-`main_window` capture (ADR 0006's original
behavior) if the popup can't be located or its rectangle never
stabilizes, rather than raising.** This is a performance optimization, not
a correctness one - the whole-window capture is already confirmed (this
probe, and originally ADR 0006) to contain the popup whenever one exists,
so degrading to it on a timeout costs speed, not correctness. Fail-closed
(`CLAUDE.md`) governs decisions with a right answer the system can get
wrong; "which control got screenshotted" isn't one of those once the
fallback is proven safe.

**4. `_read_open_combo_options` returns the capture origin alongside the
option list; `_click_and_confirm` clicks relative to that origin, not
always `main_window`'s.** `ComboOption.bbox` is defined (Doc/adr/0006
Decision 3) as relative to whatever image was captured. Before this
change that was always `main_window`, so the click math
(`main_window.rectangle()`'s top-left + bbox) was correct by construction.
Now that the captured image is sometimes the popup instead, using
`main_window`'s top-left unconditionally would silently miscompute the
click point on every run where the popup path is taken - the exact kind of
bug that fails *open* (a wrong-but-plausible screen coordinate) rather than
closed. Threading the real origin through closes that gap before it ships.

**5. A new `COMBO_POPUP_SETTLE_TIMEOUT_SECONDS` constant, not a new default
for `SEARCH_SETTLE_SECONDS`.** The task motivating this ADR asked for
`settle_seconds`'s default to reflect measured timing; `SEARCH_SETTLE_SECONDS`
is that same config value, but it's shared with grid-search settling
(`resolver.search_grid_exact`) and with `_click_and_confirm`'s
post-selection-confirm read - neither measured by this probe. Retargeting
its default from Country/VAT-popup-only data would apply a measurement to
uses it doesn't describe. The new constant governs only
`_locate_open_popup`'s poll ceiling, set to 1.5s - roughly 3x the slowest
measured settle (0.463s), a margin for a slower VM rather than the expected
wait; the poll returns as soon as the rectangle actually stabilizes; the
timeout is only a hard ceiling for the pathological case. `SEARCH_SETTLE_SECONDS`
itself is untouched.

## Consequences

- Combo option screenshots are now popup-sized instead of full-window-sized
  for both combo types - VAT's popup measured 66x27px vs. `main_window`'s
  ~1938x1048px in this probe run; Country's ~621x347px. Smaller images
  encode and transmit faster to the vision model, directly addressing the
  "takes too long" complaint for Country's ~190-option case, without
  touching `vision_grounding.read_combo_options`'s prompt or schema at all.
- `combos.py` gains its first hard, top-level `pywinauto.Desktop` dependency
  (imported locally inside `_top_level_windows`, matching every other
  OS-specific import in this codebase, e.g. `controls.focus_foreground`'s
  `win32gui`). This is fine: `combos.py` was already UI-writing code exempt
  from cross-platform unit tests (`CLAUDE.md`'s test conventions; its
  duck-typed test suite was already removed in the 2026-09-06 cleanup,
  before this change), so nothing that ran on macOS stops running there.
- `_read_open_combo_options` and `_click_and_confirm` both gained a new
  return value / parameter (the capture origin) purely to keep Decision 4's
  fix threaded through - a small, load-bearing signature change, not
  optional plumbing.
- `TODo.md` Open item #6 is resolved for both of ADR 0006's original
  unverified assumptions (DPI/pixel mapping was already implicitly
  confirmed by this probe's direct screenshots matching on-screen text with
  no visible offset; popup-in-main-window containment is directly
  confirmed). If a future combo type this pipeline drives turns out to
  render its popup differently (e.g. outside `main_window`'s rectangle, or
  never as a distinct top-level window), `_locate_open_popup`'s `None`
  fallback means it degrades to the pre-0013 whole-window behavior
  automatically rather than breaking - but that would still be worth a new
  probe before trusting it blind.
