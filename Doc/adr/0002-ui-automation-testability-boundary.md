# 0002. UI automation testability boundary (Section 3)

## Status

Accepted

## Context

`ui_automation/` is the first section that must eventually run against a
real Windows desktop app, but most of this project is developed on macOS
(the design/normalization/extraction work happened there, and this ADR
itself is being written there). The scaffold already types `find_control`'s
`parent` parameter as `Any` rather than a `pywinauto` type, which raised the
question of exactly what this module should and shouldn't import - and
whether any of it could be verified before ever touching the Windows VM.

Two things were confirmed empirically before deciding anything (not
assumed from the README's general "pywinauto will not import on
macOS/Linux" statement):

```
$ python -c "import pywinauto"                          # exit 0, succeeds
$ python -c "from pywinauto import Application"          # ImportError
```

So the bare package import is fine everywhere; it's specifically the
uia-backend-facing symbols (`Application`, and by extension anything built
on it) that are Windows-only.

## Decisions

**1. `controls.py` and `waits.py` never import `pywinauto`.** They take a
`parent`/`app`/`dialog` argument (already typed `Any` in the scaffold) and
call only the methods pywinauto's own `UIAWrapper`/`WindowSpecification`
objects document: `children(control_type=, title=)`, `window(title_re=)`,
`exists()`. Nothing here depends on `pywinauto` being importable - the
caller is responsible for handing in a real pywinauto object (via
`app.py`) or, in tests, a fake that duck-types the same three methods. This
mirrors `extraction/vision_extractor.py`'s injectable `client` parameter:
the seam that makes tests possible is a plain function argument, not a
mocking framework.

**2. `app.py` and `spikes/uia_probe.py` are the only places that
`from pywinauto import Application`.** This is unavoidable - something has
to actually connect to the OS-level window - and it is isolated to exactly
these two files. Confirmed by direct test: both fail to import on macOS
with the exact `ImportError` above; every other module in `ui_automation`
imports and unit-tests cleanly there.

**3. Ambiguity is not retried.** `find_control` raises `AmbiguousControlError`
as soon as more than one candidate is seen, rather than continuing to poll
until the timeout. An ambiguous match reflects the current search
scope (the `parent` and `control_type`/`name` given), not a transient UI
state - polling the identical query again cannot make it resolve to one.
Per `Doc/Design.md`, narrowing is the caller's job (pass a more specific
`parent`), not something `find_control` should attempt by itself.

**4. `FakturamaApp` exposes only generic accessors (`main_window()`,
`window(title_re)`), not one method per Fakturama dialog.** Section 3 is
the generic discovery layer; Design.md is explicit that the same strategy
applies across the Order, Debtor, Product, VAT, and Payment Method editors.
Adding `order_editor()`/`debtor_editor()`/... here would duplicate that
generic mechanism with Fakturama-specific knowledge that belongs in
Section 4/5 (`entity_resolution`, `verification`) and the orchestrator,
which are expected to compose `window(...)` with `find_control(...)`
themselves.

## Consequences

- `controls.py` and `waits.py` are fully unit tested on macOS
  (`tests/ui_automation/test_controls.py`, `test_waits.py`), using fake
  objects that implement only the three duck-typed methods above - no
  network, no real UI, no `pywinauto` import anywhere in the test files.
- `app.py` and `spikes/uia_probe.py` have **no unit tests** - they cannot
  even be imported outside Windows. They are implemented directly from
  pywinauto's documented API (`Application(backend="uia").connect(...)`,
  `.top_window()`, `.window(...)`, `.print_control_identifiers()`).
  **Verified on the Windows 11 ARM VM (2026-09-04):** `spikes/uia_probe.py`
  against a running Fakturama window returned a rich, fully named control
  tree on the first run (see `Archieve/uia-output.txt`) - no Java Access
  Bridge fallback needed. This was README's step-1 go/no-go gate; it passed,
  so `app.py`'s use of the same `Application(backend="uia")` API is no
  longer a live risk.
- `spikes/uia_probe_editor.py` was added after that run: it takes a keyword
  argument and prints only the descendant subtrees matching it (falling
  back to the full tree if nothing matches), since the main window dump
  doesn't show the Order/Invoice editors or the entity search dialogs -
  those only appear in the tree once opened. Same import boundary as
  `uia_probe.py`: `from pywinauto import Application`, no unit tests.
- Any future module that needs to talk to a live pywinauto object should
  follow the same pattern: accept it as a parameter typed `Any` rather than
  importing `pywinauto` itself, unless it is specifically the connection
  layer (like `app.py`).
