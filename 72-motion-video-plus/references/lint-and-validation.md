# Lint and validation: what a clean scan proves, and what it does not

MG-030 replaces fragile regex-only lint with engine-aware checks. Two
layers exist, with different input contracts:

- **Legacy layer: `scripts/lint-grammar.py`.** A Python linter for
  legacy `__setTime` scene HTML files. It keeps the MG-019
  choreography policy checks and the original determinism checks.
  MG-030 fixed its timer detection (defect D-LINT-TIMER) and nothing
  else about its behavior.
- **Engine-aware layer: `runtime/src/lint` (TypeScript).** Parses
  sources with the TypeScript compiler API and checks each source
  against the rules of the engine that will run it: `legacy`,
  `hyperframes`, or `remotion`. This is the layer new code uses.

## The one honesty rule

A lint result is a statement about **code validity only**. It is never
a statement about visual quality. Static analysis does not render a
single frame, so it cannot verify choreography, font size, or semantic
motion, and neither layer pretends otherwise:

- Every TS report carries a visual audit status. It is `pending`
  unless a caller attaches the path of a recorded visual audit
  produced by the review-evidence path (MG-031 coverage bundles,
  MG-034 QC), in which case it is `recorded` and names that evidence.
  The status is never `passed`, and attaching evidence changes no
  lint finding. The printed report says, in so many words:
  "visual audit: PENDING (static lint verifies code validity only; it
  does not verify choreography, font size, or semantic motion)".
- The Python linter prints "grammar lint clean" for the checks it
  runs; the choreography and determinism checks it owns are the whole
  of that claim.

Missing visual checks remain pending. That is a designed state, not a
gap to be papered over by a green syntax scan.

## Finding categories (TS layer)

| Category | Meaning | Example rules |
|---|---|---|
| `parser_error` | The source does not parse, so no rule may be grounded in it | `parse`, `html-structure` |
| `prohibited_clock` | Code reaches a clock or an unseeded source the frame clock does not own | `timer-call` (setTimeout, setInterval), `raf-call`, `wall-clock-now` (Date.now, performance.now), `unseeded-random` (Math.random) |
| `dynamic_timer_usage` | A timer, or code whose time behavior is unknowable, reached dynamically | `computed-timer-access`, `aliased-timer`, `dynamic-code` (eval, Function constructor) |
| `asset_readiness` | An asset or code path is not in place before frame 0 | `network-fetch`, `network-xhr`, `remote-asset`, `dynamic-import` |
| `composition_structure` | The file lacks the structure its engine requires, or animates outside its engine's mechanism | `missing-settime`, `missing-timeline-registration`, `timeline-not-paused`, `css-transition`, `gpu-layer` |

The Python linter's ids map onto the same classification for the
legacy corpus: `[timer]` is `prohibited_clock`, `[dynamic-timer]` is
`dynamic_timer_usage`. The parity corpus (below) holds both layers to
identical verdicts on identical files.

## Engine rules (summary)

The full rule sets live in `references/animation-contract.md`. The
lint layers enforce the machine-checkable parts:

- **Legacy `__setTime`:** requires `window.__setTime`,
  `window.__sceneDuration`, and a `window.__choreography`
  declaration (choreography policy itself is enforced by the Python
  linter, not re-implemented in TS). Forbids CSS transitions and
  animations, GPU-layer tricks (`translate3d`, `translateZ(0)`,
  `will-change`), timers, and unseeded randomness.
- **Remotion:** every animated value must be a function of the frame
  number. Forbids timers, wall clocks, unseeded randomness, and CSS
  transition/animation properties in style objects.
- **Hyperframes:** motion must live in a GSAP timeline that is
  created paused (or paused) and registered on `window.__timelines`
  under the composition id; the composition root must carry
  `data-composition-id`. Forbids timers, wall clocks, unseeded
  randomness, and CSS transitions/animations in style blocks
  (unregistered wall-clock animation).

No engine's rules are imposed on another: the TS layer takes the
engine as an explicit input and never requires `window.__setTime` of
a Remotion component or a Hyperframes composition.

## Timer detection and the dynamic category

D-LINT-TIMER had two halves. The shipped Python pattern
`set(TimeOut|Interval)` missed the ordinary spelling `setTimeout`
entirely; and any raw-text scan, however correct its pattern, cannot
tell a real call from the same text inside a string or a comment.
MG-030's answers:

- The Python timer family now reads **lexical views** of the source.
  The code view blanks string literals and comments to spaces
  (offsets preserved), so direct calls are searched where quoted or
  commented mentions cannot fire. Template literal `${ ... }`
  interpolations are code and stay visible. Dynamic forms (below)
  are searched in the comment view, where strings survive, because
  their evidence is a quoted timer name.
- The TS layer walks a real AST, so strings and comments are never
  call expressions in the first place.
- **Dynamic timers are findings, not passes.** Reaching a clock by
  computed access (`window["set" + "Timeout"]`, `window[name]`), by
  alias (`const st = window.setTimeout`, destructuring, a renamed
  import), or by runtime code construction (`eval`, `Function`) is
  classified `dynamic_timer_usage` in TS and `[dynamic-timer]` in
  Python. One deliberate boundary, identical in both layers: a call
  through the clock's own name (`setTimeout(...)`, including after a
  shorthand destructure) is a direct clock call, not a dynamic one.
  Renaming is what makes it dynamic.

## Parity corpus

`tests/fixtures/lint/` holds the shared corpus and
`tests/evidence/mg030/verdicts.json` records the expected verdicts.
`runtime/tests/run-lint.ts` runs every fixture through the TS layer
and every legacy fixture through the shipped Python linter, asserting
the recorded verdicts and cross-layer agreement;
`tests/unit/test_lint_timers.py` pins the same legacy verdicts from
the Python side. The corpus isolates one aspect per file: direct
timer, string mention, comment mention, computed-access timer,
aliased timer, plus one valid and several invalid engine fixtures.
`scripts/lint-grammar.py`'s input contract is legacy scene HTML, so
the Hyperframes and Remotion fixtures are the TS layer's corpus only.

## Known limits

- The Python view scanner does not lex JavaScript regex literals; a
  regex literal containing a quote or a comment opener can confuse
  the views. Legacy scene files in this skill do not use such
  literals; new code should use the TS layer, which parses real ASTs.
- Alias tracking is a single static pass over direct bindings
  (declarations, destructuring, imports). A timer passed through
  function parameters or stored in a data structure is beyond what
  either layer claims to prove; the dynamic category exists precisely
  so the borderline shapes are flagged rather than blessed.
- Asset readiness covers network behavior (fetches, remote URLs,
  dynamic imports). Whether a local asset file exists and is approved
  is the asset layer's job (`scripts/prepare_assets.py`, MG-011), not
  the linter's.
- CSS checks in HTML sources run over extracted style text; they
  mirror the legacy linter's CSS determinism rules. CSS-in-JS property
  checks apply to Remotion style objects and to imperative
  `element.style` assignments.

## Consumers

- MG-031 (visual review evidence) produces the coverage bundles
  whose paths callers attach as recorded visual audits.
- MG-034 (QC) consumes the structured findings (`LintReport`) and
  the category counts; a QC gate must treat `visualAudit.status`
  `pending` as an unmet visual gate, never as a pass.
- The adapter layer (MG-004) selects the engine; lint follows that
  selection rather than guessing from file contents.
