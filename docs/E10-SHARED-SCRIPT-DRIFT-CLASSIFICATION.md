# E10 — Shared-script drift classification (podcast vs. anthology)

**Status:** binding classification (E10). Read this before touching any of the
four files below in either engine — it records WHY they diverged and WHAT is
and is not safe to unify, so a future edit does not re-litigate the question
from scratch or attempt a blind merge.

## The four pairs, by the numbers

| basename | 58 (podcast) lines | 59 (anthology) lines | shared `def`/`class` names |
|---|---|---|---|
| `alert-dedup.py` | 844 | 910 | `_emit`, `_load_state`, `_save_state`, `_empty_state`, `main` only |
| `guard-cron-inventory.py` | 686 | 947 | none (fully disjoint function sets) |
| `guard-no-anthropic-runtime.py` | 730 | 524 | none (fully disjoint function sets) |
| `delivery_report.py` | 487 | 866 | none (fully disjoint function sets) |

## Verdict: intentional divergent design, not drift from a shared origin

Diffing every pair shows near-total rewrites (e.g. `alert-dedup.py` is 791
insertions / 725 deletions out of ~850-900 lines) with almost no shared
function names. This is **not** a shared script that bit-rotted apart from one
canonical copy — each engine's author independently built a script serving an
analogous ROLE under the same filename, with a genuinely different
ARCHITECTURE, data model, and (for two of the four) a different problem scope
entirely. Per the fix mandate ("classify diff first; blind unification
forbidden"), full-file "extract a common core" is the WRONG move here: there
is no common core to extract without a lossy, high-risk rewrite of at least
one engine's safety-critical guard.

## Per-pair findings

### `alert-dedup.py` — different abstraction levels, same underlying invariant
- **58**: a FOUNDER-ALERT-SPECIFIC subsystem. Subcommands `raise` / `recover` /
  `flush-digest` / `status`; dedup key is `client|service|failure_class`;
  severity model is `status|decision|digest` with per-episode tracking and a
  daily digest cap.
- **59**: a GENERIC keyed dedup+delivery primitive. Subcommands `send` /
  `status` / `purge` / `selftest`; dedup key is any caller-supplied
  `dedup_key`; adds a storm cap (max N distinct deliveries per rolling window)
  58 has no equivalent of.
- **Verified, real, shared invariant** (proved by direct fixture call —
  see `shared-utils/test_e10_engine_drift_guard.py`): both correctly suppress
  a second alert fired on the SAME identity within their dedup window and
  correctly send a new alert for a DIFFERENT identity. This is the one
  invariant genuinely worth guarding against future drift, since it is exactly
  what E8's stale-job alerting depends on in both engines.
- **Not safe to unify**: the storm-cap concept and the episode-tracking
  severity model are real, load-bearing feature differences, not accidental
  drift.

### `guard-cron-inventory.py` — different data models, same policy
- **58**: static-scan mode PLUS an inventory-mode audit over free-form cron
  entries (`name`/`schedule`/`cron`/`kind` keys probed defensively), keyed by a
  regex-extracted client slug, allowing MULTIPLE clients per box (per-client
  exactly-one-cron).
- **59**: inventory-mode only, over a stricter `{name, schedule:{kind,expr},
  enabled, ...}` job shape, single-engine-per-box exactly-one-recurring-job
  policy with an explicit `expect="one"|"zero"` (churn) mode and a pinned
  `--tick-name` assertion 58 has no equivalent of.
- **Verified, real, shared invariant**: "exactly one recurring/engine-owned
  job passes; two or more fails" holds identically in both when driven with an
  equivalent one-job / two-job fixture (see the drift-guard test file).
- **Not safe to unify**: 58's multi-client-per-box model and 59's
  `expect="zero"` churn-proof mode are real policy differences.

### `guard-no-anthropic-runtime.py` — safety-critical; a real, verified division of labor
- **58**: single file does BOTH the model-id-shape scan (JOB 1, 8 explicit
  regex classes including `sk-ant-` key values and the `ANTHROPIC_API_KEY` env
  var name) AND a routing-config assertion (JOB 2: the shipped tier order is
  Ollama Cloud -> OpenRouter -> Gemini, monotonic, deny-armed) AND a stricter
  dashboard screen. No sibling secrets scanner exists in 58.
- **59**: a narrower, more recently hardened value-shape scanner (5 compound
  shapes, fragment-assembled `_A`/`_C` tokens so its own source carries no
  contiguous banned literal, an enforcement-context discriminator so the deny
  machinery itself never self-flags) — but it does **not** scan for
  `sk-ant-`/`ANTHROPIC_API_KEY` shapes. That responsibility lives in a
  **separate sibling script**, `scan-no-secrets.sh` (`sk- / sk-proj- / sk-ant-
  / sk-or-v1-` vendor key shapes, documented in its own header), which 58 has
  no equivalent of.
- **This is the pair most worth double-checking on every future edit**: it
  is genuinely safety-critical (client-skills-never-anthropic-models). The
  apparent "59 doesn't catch API keys" gap is **not** a coverage gap once you
  read both engines' FULL guard suite (58 folds it into one file; 59 splits it
  across two) — but this finding is exactly the kind of thing a shallow diff
  would misclassify as drift-to-fix. Verified by direct fixture call: both
  files' MODEL-ID-SHAPE detectors (the six shapes they DO share: `claude-<id>`,
  `anthropic/<id>`, the `us`-region cross-region inference-profile id form,
  `@anthropic-ai/`, the API host, and a bare `"provider":"anthropic"` scalar)
  agree on every positive and negative
  fixture tried (see the drift-guard test file) — this IS the safe subset to
  keep behavior-parity-tested going forward.
- **Not safe to unify**: JOB 2 (routing assertion) and the dashboard screen
  are 58-only and load-bearing; the fragment-assembly self-scan discipline and
  enforcement-context discriminator are 59-only and load-bearing.

### `delivery_report.py` — different problems, same filename only
- **58**: a MARKDOWN FORMATTING guard for the podcast presentation-reproduce
  operator report (`assert_no_forbidden_glyphs` bans an em dash and a
  triple-backtick fence; `redact` scrubs client-facing tokens). Has nothing to
  do with Anthropic identifiers.
- **59**: an ANTHROPIC-IDENTIFIER-INJECTION guard plus a JSON
  delivery-report-and-process-certificate builder (`assert_no_anthropic_values`
  scans every caller-supplied dynamic value — participant_key, deliverable
  URLs, pipeline-stage fields — for a deny-shaped value before it is
  persisted).
- **Verdict**: these are two genuinely unrelated concerns that happen to
  share a filename and a rough "operator report" category. There is **no**
  shared invariant here worth a behavior-parity test; unifying them would be
  the textbook "blind unification" this fix explicitly forbids. Left to the
  structural baseline guard only (below).

## The chosen fix: baseline drift-guard + verified parity tests, not code unification

Given the above, "extract common cores into shared-utils/ with thin per-engine
wrappers" is the wrong instrument for three of the four pairs (would either be
a no-op wrapping nothing real, or a risky rewrite of safety-critical code for
marginal benefit). The fix actually shipped:

1. **`shared-utils/engine-script-drift-baseline.json`** — a sha256 + line-count
   + top-level `def`/`class`-name-set fingerprint of all eight files as of this
   classification, captured by `engine_script_drift_guard.py --update-baseline`.
2. **`shared-utils/engine_script_drift_guard.py`** — a checker (same
   convention as `verify_tone_core_sync.py`'s sha256 lockstep proof) that fails
   (exit 2) if a file's fingerprint has drifted from the recorded baseline
   WITHOUT a conscious `--update-baseline` re-run. This makes future drift a
   **reviewed, deliberate act** instead of silent, unreviewed rot — directly
   answering "so they don't rot apart" without pretending four independently-
   designed files are (or should become) one shared implementation.
3. **`shared-utils/test_e10_engine_drift_guard.py`** — pytest coverage for the
   baseline guard itself, PLUS the three verified cross-engine behavioral
   parity fixture batteries described above (anthropic-guard model-id shapes,
   cron-guard one-job/two-job invariant, alert-dedup same-key-suppressed/
   different-key-sent invariant) — real regression protection for the
   invariants that ARE genuinely shared, with zero changes to either engine's
   runtime files (so zero regression risk to either engine's own test suite
   or merge-gate guards).

Any future PR that wants to go further (e.g. genuinely extracting the
anthropic-guard's shared six value-shape patterns into one canonical
`shared-utils` data file both guards import) should treat this document as
its starting classification, not redo the diff from scratch — and should
budget real test time against BOTH engines' merge-gate guard self-tests
(58's `guard-no-anthropic-runtime.py self-test` and 59's own `self_test`),
since that guard rides the repo QC merge gate in both skills.
