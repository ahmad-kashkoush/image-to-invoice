# 0016. Number input follows the surface that parses it, and is read back

## Status

Accepted.

## Context

Every number this system types into Fakturama was written with `str(Decimal)`,
i.e. a `.` decimal separator. `TODo.md` item 17 had recorded that Fakturama
renders money in a locale the pipeline does not expect and left open "whether
the typed decimal separator must follow that locale". Live on 2026-09-15 it
must, and the consequences had been silent:

- **Product price, 100x too high.** `gross_from_net(250.00, 19) = 297.50`
  typed as `"297.50"` was stored as `29.750,00 EUR` - the `.` read as a
  thousands separator. Nothing caught it: `_create_product` verified only the
  SKU. The wrong price reached the Order as a wrong `U.Price` and was caught
  two states later by the Items grid's own row check, by which point a bad
  Product record had already been saved.
- **Invoice payment Value.** `"678.30"` became `67.830,00 EUR`, which
  `verify_payment_applied` did catch.

The obvious fix - one decimal separator for the whole app - is wrong, and
measuring rather than assuming is what found that. Fakturama is not
internally consistent, and the line does not run where it looks like it
should. It is not master data vs. documents:

| Surface | Kind | `"2,00"` / `"297.50"` is read as | Renders |
|---|---|---|---|
| Product form, Price (gross) | form Edit | `29750` for `"297.50"` | `29.750,00 EUR` |
| Invoice editor, payment Value | form Edit | `67830` for `"678.30"` | `67.830,00 EUR` |
| Order editor, Items grid Qty. | grid cell | `200` for `"2,00"` | `45,000.00 EUR` |

The Items grid - a custom-rendered NatTable typed into with raw
`type_keys` - parses and renders the *opposite* convention to the form Edits
around it. Both wrong guesses were made and corrected live: writing `","`
everywhere turned Qty. `2.00` into `200`, and writing `"."` everywhere turned
the payment Value into `67.830,00`.

## Decisions

- **The separator is a property of the surface, not of the app.**
  `ui_automation/config.py::DECIMAL_SEPARATOR` (default `","`, env
  `FAKTURAMA_UI_AUTOMATION_DECIMAL_SEPARATOR`) applies to **form Edits only**.
  Grid cells keep a plain `str()`. Both call sites carry a comment saying
  which they are and why, because the next person will otherwise "fix" the
  inconsistency in one direction and break the other.

- **One formatter, next to the parsing rule it inverts.**
  `normalization/parsing.py::format_decimal(value, *, decimal_separator)` is
  the inverse of `normalize_decimal_separators`, and lives beside it because
  this repo keeps the separator rule in one place. It emits no thousands
  separator: grouping is never required for input, and emitting it would mean
  encoding a second locale-specific rule with no way to verify it. The
  constant lives in `ui_automation/config.py` instead, because it describes
  the app being driven rather than the documents being read.

- **Read money back numerically.** `resolver.money_matches` parses both sides
  with `parse_money_text` and compares the numbers. String comparison is
  meaningless against a field that re-renders what it was given, grouped and
  currency-suffixed, in its own locale.

- **`verify_saved_fields` can read a field that has no name.**
  `SavedField` becomes a dataclass with an optional `read` callable.
  The Product price Edit is unnamed and its `auto_id` is session-unstable, so
  it is reached through its label's sibling pane - the same way it is
  written. Without this the price simply could not be verified, which is how
  it stayed silent. The other four call sites pass a control name as before.

- **The Product's gross price joins its SKU in `verify_saved_fields`.** The
  SKU is verified because a lost SKU makes the record unfindable; the price is
  verified because it is the one field the app re-parses, so it can persist as
  a plausible but wrong number.

## Consequences

- The golden sample reached `DONE` for the first time since 2026-09-06, and
  for the first time since the P0/P1 refactor: all ten states, Order and
  linked Invoice saved and verified, exit code 0. The saved Products carry
  `250.00` and `40.00` net - correct, where the same run previously stored
  `29750`.

- A mis-parsed price now fails closed at `resolve_product`, where it happens,
  instead of surfacing two states later as a confusing `U.Price` mismatch on
  an order line - or not at all.

- The table above is empirical, not exhaustive. Three surfaces were measured;
  the Debtor form's ZIP, the VAT Value and the payment *date* fields were not,
  and are assumed to follow the form-Edit rule because they are form Edits.
  Anything typed into a fourth kind of surface needs measuring, not assuming.

- `DECIMAL_SEPARATOR` is a single knob for a single-locale deployment. An
  installation whose forms are en-US would need it set to `"."`, and would
  then need the Items grid to become `","` - which no env var can express
  today. If that case ever arrives, the knob has to become per-surface rather
  than be re-pointed.
