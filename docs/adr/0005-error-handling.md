# 0005. Error handling: JSONL manual-review queue, fail-safe terminal handler, deferred partial state (Section 6)

## Status

Accepted

## Context

Sections 1-5 already raise `error_handling.exceptions.ManualReviewRequired`
whenever they cannot safely proceed (extraction failures, normalization's
aggregated validation problems, entity_resolution ambiguity, and each of
the three verification functions' aggregated mismatches) - all with a
`step`/`reason` pair built from CLAUDE.md's aggregate-then-raise fail-closed
principle. What was still missing was the terminal handler,
`manual_review.route_to_manual_review`, that actually records one of these
to disk so a stuck order becomes a durable, actionable record rather than
just a raised exception the orchestrator (not yet implemented) would need
to catch and immediately discard.

The README only specifies the location, not the shape: "an out folder for
logs and the manual review queue". Two forks needed a decision that
nothing upstream dictated:

1. What does one queue "entry" look like on disk - one file per entry, or
   one append-only log?
2. Does `ManualReviewRequired` need to carry more than `step`/`reason` (its
   own docstring TODO invited this - "carry enough context... for
   manual_review.py to write a useful entry"), and does `route_to_manual_review`
   need to capture partial workflow state (the in-flight `NormalizedOrder`,
   ambiguous candidates, etc.)?

The user's direction was explicit: take the simplest viable shape for both
and push anything requiring materially more effort to `TODo.md`'s Open
list, rather than over-build a section that has no orchestrator caller yet
to exercise it end to end.

## Decisions

**1. A single append-only JSONL file (`out/manual_review_queue.jsonl`),
not one file per entry.** Appending a line is a single open-append-close
with no filename scheme to design (no timestamp+image+step naming, no
collision handling for two failures on the same order). It is trivially
parseable by any future tool (`json.loads` per line) and trivially
tailable by a human. The tradeoff - entries aren't individually
"claimable"/deletable as a human works through them - is real but was
judged acceptable for a queue with no consumer yet; a per-entry-file
layout (each stuck order as its own movable/deletable artifact) is noted
in `TODo.md`'s Open list if the single-file queue proves insufficient
once a human/tool actually processes it.

**2. `ManualReviewRequired` is left unextended; the entry captures only
what the fixed `route_to_manual_review(error, source_image_path)` signature
can reach.** An entry holds `timestamp`, `source_image_path`, `step`
(`error.step`), and `reason` (`error.reason`). Capturing richer partial
state - the in-flight `NormalizedOrder`, which entities were ambiguous -
would require: extending the exception with an optional payload,
threading that payload through every one of the ~10 existing raise sites
across extraction/normalization/entity_resolution/verification (a change
to five modules' worth of already-implemented, already-tested code for a
consumer - the orchestrator - that doesn't exist yet), and a
`Decimal`/`date`-aware JSON encoder for `NormalizedOrder`'s typed fields.
That is a materially larger, riskier change than this section's own scope
(implement the one remaining stub) justifies right now, so it is deferred
(`TODo.md`'s Open list) rather than done speculatively.

As a forward-compatible hook that costs nothing today,
`route_to_manual_review` reads `getattr(error, "details", None)` and
includes it under a `details` key only if some future caller sets that
attribute - so adding richer state later needs no change to this
function, only to whichever call site wants to attach it.

**3. `route_to_manual_review` is fail-safe: it must never raise.** It is
documented (both in the original scaffold and here) as the terminal
handler for a workflow run - there is no further place to route a failure
of its own. All entry-building and file I/O is wrapped in a single
`try/except Exception`, falling back to a `stderr` print (the codebase has
no logging framework - confirmed no `import logging`/`getLogger` anywhere
in `src/`) rather than propagating. `route_to_manual_review` therefore has
no failure mode reachable through its public contract; the fail-safe path
is exercised directly in `tests/error_handling/test_manual_review.py` by
pointing `out_dir` at a path that is already a regular file.

**4. `out_dir` and `now` are injectable keyword-only arguments.** Rather
than mutate `os.environ` or monkeypatch `datetime.now` in tests, both are
overridable directly - the same seam `extraction.vision_extractor` uses
for its `client` parameter and Section 5 added for
`verify_order_saved`'s `normalized_order`. This keeps `error_handling/config.py`
(the env-driven `FAKTURAMA_ERROR_HANDLING_OUT_DIR`/`FAKTURAMA_ERROR_HANDLING_QUEUE_FILE`
defaults, mirroring every other section's `config.py`) as the single
source of truth for the *real* out-folder location, while tests never
touch it.

## Consequences

- `error_handling/manual_review.py` is fully unit-tested on macOS with no
  network, no UI, and no real `out` folder (`tests/error_handling/test_manual_review.py`,
  using `tmp_path` and a fixed clock) - the same testability bar every
  prior section met.
- The queue has no reader/consumer yet beyond a human opening the file:
  no dedup, no per-entry status (claimed/resolved), no rotation. Any of
  these would be premature to design before the orchestrator exists and
  before a real run has produced actual entries to learn from.
- `ManualReviewRequired`'s own TODO ("carry enough context... for
  manual_review.py to write a useful entry") is only partially resolved:
  the entry is useful (identifies the failing order image, step, and full
  aggregated reason string - already descriptive, since every producer
  aggregates its own problems into one reason), but does not yet let a
  reviewer see the actual field values that were wrong without re-opening
  the source image. This is the explicit tradeoff of Decision 2, tracked
  in `TODo.md`'s Open list rather than silently accepted.
- Because the `details` forwarding hook already exists, implementing the
  deferred richer-state capture later is additive (extend the exception,
  add an encoder, set `.details` at call sites) rather than requiring
  another change to `manual_review.py` itself.
