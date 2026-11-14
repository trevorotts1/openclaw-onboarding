# PD-928 — ffmpeg/ffprobe required-vs-optional: the decision and its proof

Unit PD-928 · lane FL01 · branch `pd/fl01-entry-door` · base tip `672b8989d`

## 1. What "required" actually controls at runtime

`presentation-deps.json` is the ONE dependency canon; every consumer reads it and
none keeps its own list. `required` is read in exactly one place in the readers —
`_pres_deps_rows` (update-skills.sh) and the two mirroring python inline readers
(qc-completeness.sh, the door) — where it selects which of two arrays a missing
row lands in: `required:true` → the `missing` array, `required:false` → the
`video_missing` array. Three gates then behave differently:

- **Door GATE 1 (`deps_check`, presentation-canonical-entry.sh:985-1128)** is the
  only *refusing* gate. `missing` non-empty → `PRESENTATION_DEPS_MISSING` and
  `return 6`, which the call site turns into `exit 6` unless an
  `owner_skip_approval "PRESENTATION_DEPS_MISSING"` token is present in the run's
  `process_manifest.json`. `video_missing` prints an advisory and returns 0. It
  runs on every build including `--plan` (documented at line 159: "print the
  canonical phase plan and exit (gates still run)") and it runs *before* any
  phase executes — so it can only decide by the box's tool inventory, never by
  what the deck will contain.
- **`converge_presentation_deps` (update-skills.sh:13187-13385)** is the
  update-time convergence + readiness receipt. `missing` non-empty → returns 2
  and writes `presentation-readiness.json` status `DEGRADED`; `video_missing`
  only writes `missing_optional_video`. Its rc is latched, never aborting.
- **`qc-completeness.sh`** (~line 143-259) is the install/update hard gate:
  `missing` non-empty → exit 6.

The word "optional" in the canon is therefore not a statement about the
deliverable — it is a statement about *which array a missing binary lands in*, and
thus about whether GATE 1 refuses.

## 2. What the six failing assertions were protecting

Measured baseline on this tip: `PASS=33 FAIL=0`. With a blanket flip:
`PASS=27 FAIL=6` — C1×3, C2×1, E2×2, exactly as the prior unit reported.

| Assertion | What it actually protects |
|---|---|
| C1 "returns 0" | That a video-only gap does not block **the converge rc** — i.e. that deck work survives. It encodes "optional" and nothing else. |
| C1 "video branch reported disabled" | That the `video_missing` array is reachable and the advisory prints. Mechanism coverage. |
| C1 "required PRESENTATION_DEPS_MISSING still fired" | Negative half of the same: the required string must NOT appear for a video-only gap. Encodes "optional". |
| C2 "optional video gap reported separately" | That the two arrays stay distinguishable when both fire. Encodes "optional". |
| E2 "video branch reported disabled" | Same mechanism, through the **door**. Encodes "optional". |
| E2 "required gate fired for optional-only gap" | That the door passes a video-only gap. Encodes "optional". |

**None of the six encodes a real fact about deck-only builds.** Every one of them
asserts the optional classification itself; they are the mirror image of the canon
row, not independent evidence about it. That is why they must move with the flip.

## 3. The decision: GLOBAL FLIP to `required:true` — and why the conditional answer was wrong

The brief's strong hint was a CONDITIONAL requirement (required when a build
produces `webinar_mp4`, optional for deck-only). The reading does not support it,
for four measured reasons:

1. **No gate can evaluate the condition where it matters.** GATE 1 runs before the
   phase plan exists and its input is `command -v`. There is no per-deck phase
   list at that point. A conditional rule would need a new intake-derived
   predicate plumbed into `deps_check` — a new mechanism, not a re-spec.
2. **`webinar_mp4` is NOT what makes ffmpeg required — `audio_mp3` is.**
   `audio_mp3` is in `build_bundle_files` **and** `client_package_files`, is NOT
   `produced_later`, and is produced by `synthesize_full_speech.py` (P9-SPEECH-
   WEBINAR-INTRO order 8.54 and P9-DELIVER order 9), which **hard-exits** without
   ffmpeg+ffprobe at line 540-543 (`sys.exit(f"FAIL: {tool} not found on PATH")`).
   Both phases have `defers_unless: None`. So the *first* thing that needs ffmpeg
   is the plain presenter audio, which every shipped bundle carries.
3. **The prior unit's fourth reason ("a blanket flip would block deck-only
   builds") is measurably false as stated.** No deck-only build shape exists in
   the engine. `deliverable_set` / `WANT_AUDIO_DELIVERABLE` are captured by
   `resolve_intake.py` and never consumed by `presentation_job` — grep across the
   package returns only `resolve_intake.py:111` (capture) and no filter. Phase
   selection is `_phases_applicable_to_this_deck` (phases.py:1744) plus
   `phase_is_deferred`; the only route-arounds are converter, SP-only, and
   infographic (phases.py:1550/1589/1722). `P9-DELIVER` and
   `P9-SPEECH-WEBINAR-INTRO` and `P9.6-WEBINAR-VIDEO` carry no defer and no
   route-around. `fix_bundle_complete.REQUIRED_KEYS` (10 keys) includes
   `audio_mp3` and `webinar_mp4` unconditionally. Deployment has no "deck-only"
   mode either: `delivery_gate.CLIENT_PACKAGE_KEYS` hard-requires `webinar_mp4`
   with `CLIENT_PACKAGE_WARN_ONLY = frozenset()` (measured, not read from prose).
4. **`produced_later` is a TIMING flag, not an applicability flag.** Read where it
   is consumed: `build_deck.py:13423` `continue`s it out of the P8 postflight
   existence loop because the file does not exist *yet*; `build_deck.py:12725`
   initialises it `verified` for the same reason. It says "not present at
   P8-ASSEMBLE time", never "not needed for this deck". Treating it as an
   applicability signal — the prior unit's inference — is a misread of the flag.

So on this tree, every completed run needs ffmpeg and ffprobe. Declaring them
optional means the box's readiness verdict says READY on a box that cannot
produce any deliverable — a fail-open. The honest classification is
`required:true`.

### What "deck-only still works" means, and how it is proven

It is a **canon/composition** property, not a runtime predicate: a deployment whose
canon does not carry the video rows passes GATE 1 without ffmpeg. E3 proves that
mechanically (below). The `video_missing` / `PRESENTATION_VIDEO_DEPS_MISSING`
**mechanism is preserved, not deleted** — C1b proves it still classifies any
`required:false` row correctly with a fixture canon, so a future genuinely-optional
dep keeps a working branch.

## 4. The six assertions and how each moved

All six moved **in the same commit as the canon flip**.

| Before | After |
|---|---|
| C1 `returns 0 (deck work not blocked)` | C1 `returns 2 (readiness degraded)` — the required verdict for a required row |
| C1 `video branch reported disabled` | C1 `required missing list names ffmpeg AND ffprobe` |
| C1 `no required PRESENTATION_DEPS_MISSING for optional-only gap` | C1 `video gap never lands in the optional branch when the canon says required` |
| C2 `optional video gap reported separately` | C2 `video gap (ffmpeg) named in the required list alongside soffice` |
| E2 `optional video missing -> video branch reported disabled` | E2 `required video missing -> GATE 1 refuses and names ffmpeg (rc=6)` |
| E2 `optional-only gap did NOT trip required PRESENTATION_DEPS_MISSING` | E2 `GATE 1 exit code is 6` + `refusal names ONLY ffmpeg/ffprobe (cause isolated)` + `video gap never reported as an optional branch` |

Added (mechanism preserved + second proof direction):
- **C1b** — a fixture canon with a `required:false` row: converge returns 0, the
  row appears in the video branch, and it never leaks into the required list.
- **E3** — deck-only canon (video rows removed) + no ffmpeg on PATH: GATE 1 passes,
  `PRESENTATION_DEPS_MISSING` never fires.

No assertion was weakened. C2 went from "reported separately" to "named in the
required list AND still names soffice", which is stricter. E2 gained a cause-
isolation check that did not exist before.

### Two harness defects found and fixed while proving

- **Storage rule.** This file used 15 bare `mktemp -d` calls. On macOS/BSD
  `mktemp -d` **ignores `$TMPDIR`** (measured: with TMPDIR exported to the
  portable drive it still returned a path under the system temp directory). All
  15 now pass `-p "$TMPDIR_TEST"`, and the root itself uses `-p "${TMPDIR:-/tmp}"`.
  That is a pre-existing violation of the room's verbatim storage rule, not
  introduced here.
- **False-pass risk in E2.** `pytesseract` resolves from the *user* site-packages
  (`$HOME/Library/Python/3.14/...`), so the old `HOME=` isolation made the
  pytesseract row fail for an unrelated reason and E2 could have "passed" on
  rc=6 without ffmpeg being the cause. E2 and E3 now pin a **measured healthy**
  interpreter (imports reportlab+pptx+pypdf+pytesseract), and E2 asserts the
  named gap set is exactly `{ffmpeg, ffprobe}`. If no healthy interpreter exists
  the check reports `UNPROVEN` rather than a green.

## 5. Files changed

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-deps.json` | ffmpeg + ffprobe `required:false` → `true` (the decision) |
| `tests/unit/presentation-readiness.test.sh` | the six assertions moved; C1b + E3 added; 15 `mktemp` calls brought under the storage rule; E2/E3 pin a healthy interpreter and isolate cause |
| `23-ai-workforce-blueprint/scripts/qc-completeness.sh` | the hardcoded optional ffmpeg/ffprobe probe is now gated on `_PRES_DEPS_CANON` being empty — without this a missing ffmpeg would be reported twice after the flip, once as a hard gap and once as an "optional branch, build can continue" advisory that contradicts it. Fallback path (canon unreadable) keeps the probe. |

`update-skills.sh` (shared, FL01-owned) is **untouched**: its two stale prose
comments still say "optional video-only", but it is canon-driven at runtime and
`pres_deps_verify_rows` reads `required` from the canon, so behaviour is already
correct. Flagging the prose for the shared-file owner rather than editing it.

## 6. Proofs

### Direction 1 — a build that needs video FAILS without ffmpeg

Real command (fixture canon = the real canon, PATH with no ffmpeg/ffprobe, healthy
pinned interpreter):

```
HOME=<isolated> PATH=<no ffmpeg> PRESENTATION_PIPELINE_INTERPRETER=<healthy> \
  SCRIPTS_DIR=<fixture> bash presentation-canonical-entry.sh --run-dir <run> ...
```

Result: `PRESENTATION_DEPS_MISSING: ffmpeg (ffmpeg not on PATH) ffprobe (ffprobe not on PATH)`,
**rc=6**. Asserted by E2, including that no other dep is named.

And at the source of truth for audio, `synthesize_full_speech.py:540-543`:
```
FAIL: ffmpeg not found on PATH. Install via 'brew install ffmpeg'.
```
(exit, not a warning) — reachable from P9-SPEECH-WEBINAR-INTRO (8.54) and
P9-DELIVER (9), neither of which defers.

### Direction 2 — a deck-only build still PASSES without ffmpeg

Fixture canon with the two video rows removed (the deck-only composition), PATH
with no ffmpeg/ffprobe, healthy pinned interpreter:

Result: `OK: all runtime deps present`, no `PRESENTATION_DEPS_MISSING`. Asserted
by E3.

### Negative control (the tests actually discriminate)

Reverting the canon to `required:false` reds **7** assertions
(`PASS=33 FAIL=7`), including `C1 returned 0, expected 2`,
`E2 GATE 1 exit code is 8, expected 6`, `E2 did NOT refuse naming ffmpeg`. With
the flip applied: `PASS=40 FAIL=0`.

### Suites

| Suite | Result |
|---|---|
| `tests/unit/presentation-readiness.test.sh` | **PASS=40 FAIL=0** |
| `tests/unit/presentation-deps-gate.test.sh` | **PASS=75 FAIL=0** |
| `presentations/scripts/tests/test_webinar_builder.py` | **26 passed** |
| baseline before this unit (readiness) | PASS=33 FAIL=0 |
| blanket flip, tests unedited | PASS=27 FAIL=6 (C1×3, C2×1, E2×2) |

## 7. Residual unknowns

- The E2/E3 proofs pin a healthy interpreter found on **this** box
  (`$HOME/.openclaw/.venv-presentations/bin/python`, then `python3`). On a box
  with neither, E2/E3 print `UNPROVEN` instead of passing; that is deliberate,
  but it means those two assertions are environment-dependent by construction.
- `update-skills.sh`'s prose (shared file, not edited here) still describes
  ffmpeg/ffprobe as "optional video-only". Behaviour is correct; the comment is
  stale. Owner of `update-skills.sh` should refresh it.
- Whether a genuine deck-only *product* should exist is a product decision, not
  this unit's. If one is ever added, it must come with a canon that omits the
  video rows (E3's shape) or a phase-level defer for
  P9-SPEECH-WEBINAR-INTRO/P9.6-WEBINAR-VIDEO/P9-DELIVER — both currently absent.
