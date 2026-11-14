# PD-204 — BUILD REPORT

**Unit:** PD-204 — Grading never lands on the writing model
**Lane:** FL28 · trevorotts1/openclaw-onboarding
**Branch built on:** `pd/fl28-model-router--hold-d23`
**Branch action:** the worktree was already on `pd/fl28-model-router--hold-d23`; **no checkout and no creation was performed.** (Verified with `git branch --show-current` as the first command.)
**Base head recorded before any edit:** `1a476d2cb` — `Merge pull request #3163 from trevorotts1/batch/openclaw-onboarding/20261112-172032`
**Code + test commit:** `cadba0bb41e803cb73a128e80f0326ddde4fdbea`
**Hold:** D-23. Built and staged. **Not merged.**
**Runtime constants:** none touched (`ULTRA_OPERATOR_CEILING`, `STANDARD_MODE_CEILING`, `ECONOMY*` all untouched).

---

## 1. What changed (owned paths only)

### `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/model_router.py`

| Site | Change |
|---|---|
| after `_served_model` (new lines 310-329) | **`_model_family(model_id)`** — text after the last `/`, lower-cased, up to the first non-letter. Returns `""` for an id with no leading letters, and callers never treat two unknowns as a match. |
| after `DEFAULT_CAPABILITY` (new lines 393-406) | **`GRADER_OF`** — `{"P1Q-COPY-QC": "P4-COPY", "P-PROMPT-QC": "P4-PROMPT", "P-SPEECH-QC": "P9-SPEECH", "P-SHIFT-QC": "P4-COPY"}`. |
| `resolve_route`, new lines 2255-2270 | Resolves the **author** phase's route first with the same `profile`, `config_dir` and `mode`; stamps `author_phase` and `author_route` on the decision; derives `author_family`. The author phase is never itself a key of `GRADER_OF`, so the recursion terminates at depth 1. |
| `resolve_route`, candidate loop, new lines 2311-2321 | Skips any candidate whose **served** model id is in the author's family; the candidate row is kept with `eligible: False` and reason **`same model family as the author`**. Absence of a family on either side is never a match. |
| `resolve_route`, no-route branch, new lines 2421-2434 | When a grader is left with nothing because of family skips, the reason is the plain **`no independent model is available to grade this step`** instead of the generic park text. Every other class keeps its existing reason byte-for-byte. |

Because the client's declared `judge` model is prepended into the **same** candidate list before the loop, it is subject to the identical rule with no second code path (proved in probe C and in `test_declared_judge_in_the_author_family_is_refused`).

### `.../tests/test_pd_router_grader_independence.py` (new)

Seven tests covering the three acceptance probes plus the two guards (declared judge in the author's family refused; rule follows the author; non-grader phases untouched; `_model_family` itself).

No existing test was weakened, deleted or edited.

---

## 2. Acceptance row A1 — the PD-204 probe

Run: `python3 -I /Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-204/probe_pd204.py`
(profile passed as a dict; no network, no spend; `provider_key_resolves` stubbed True).

**A. DeepSeek-only client → `P1Q-COPY-QC` has no route and the plain reason.**

```
"author_phase": "P4-COPY",
"author_route": {"model": "deepseek-flash", "provider": "deepseek-direct"},
candidates: client:configured-default  deepseek-flash  eligible=false  "same model family as the author"
            text.fast                  deepseek-flash  eligible=false  "same model family as the author"
            glm-flash                  z-ai/glm-5.3-flash  eligible=false  "provider openrouter not owned by the client profile"
            glm-5.3                    z-ai/glm-5.3        eligible=false  "provider openrouter not owned by the client profile"
"reason": "no independent model is available to grade this step",
"route": null
```

**B. DeepSeek plus OpenRouter → the judge goes to the other family.**

```
"author_route": {"model": "deepseek-flash", "provider": "deepseek-direct"},
"route": {"model": "z-ai/glm-5.3-flash", "provider": "openrouter"},
"reason": "fallback: primary unavailable -- same model family as the author"
```

**C. Declared judge on another family → used.**

```
candidates[0]: client:judge  openrouter/z-ai/glm-5.3  eligible=true  "wired on openrouter"
candidates[1]: text.fast     deepseek-flash           eligible=false "same model family as the author"
"reason": "client model plan: judge slot declared openrouter/z-ai/glm-5.3",
"route": {"model": "z-ai/glm-5.3", "provider": "openrouter"}
```

All three pass exactly as written in the unit text.

---

## 3. Test evidence

**New file, on this branch with the change:**

```
$ python3 -m pytest tests/test_pd_router_grader_independence.py -q
7 passed in 0.55s
```

**The same file on the base commit (change stashed):** 6 of 7 fail (function/constant absent); the 7th — `test_non_grader_phase_is_untouched` — passes on the base, which is the intended control.

**Router blast radius:** every test file that imports `model_router` / calls `resolve_route` (27 files) was run with and without the change at the same commit and the failure sets diffed.

| | base (stash) | with change |
|---|---|---|
| failures | 76 | 71 |

- **New failures caused by this change: zero.** The single delta on the first pass was `test_auto_resume.py::test_a_refused_dispatch_gives_the_attempt_back_end_to_end`, and it is **pre-existing flake**: re-run 3× with the change → fail, fail, pass; 3× on the base → fail, pass, pass. It depends on the live notify/env store, not on the router.
- **Fixed by this change:** `tests/test_fix61_ultra_real.py::test_ultra_judge_routes_to_openrouter` — a pre-existing red test whose failure message on the base is `ultra judge should route to openrouter, got {'provider': 'deepseek-direct', 'model': 'deepseek-flash'}`, i.e. exactly the defect PD-204 exists to close.
- `tests/test_dispatcher_autospawn.py` and `tests/test_dispatcher_repeat_suppression.py`: **0 failures** with the change.

**Pre-existing failures on this branch (not caused, not touched, not mine to fix):** the ~70 remaining reds are the same on the base and are concentrated in `test_u3_standard_ceiling_restored.py`, `test_fix11_mode_axis.py`, `test_defect5_routing_stamp_provider_identity.py`, `test_u2_openrouter_ceiling.py`, `test_model_plan.py` and friends. They assert the "standard == 100 / axis cosmetic" state that FIX 61.5 reversed, and this branch is cut from `origin/main` **without** the accepted lane work PD-214 / PD-219b / PD-905 which updates those assertions on `pd/fl28-model-router`. Confirmed by `git merge-base --is-ancestor origin/pd/fl28-model-router HEAD` → false. Per the task note, those are **not** mine and were not reached across.

---

## 4. Notes for the checker

1. **Branch is the hold branch.** `pd/fl28-model-router--hold-d23`, not `pd/fl28-model-router`. The plain branch carries PD-214, PD-905 and PD-219b; this branch does not, by design of the task.
2. **Three residual stale text sites** at 1501, 1758 and 1277 are PD-219b follow-up work on the sibling branch. Not present here, not touched.
3. **`GRADER_OF` is data**, so PD-205a can import `_model_family` rather than writing a second one (as its unit text instructs).
4. **A configured default is also refused when it is the author's family.** Probe A shows `client:configured-default` prepended and skipped with the same reason. That is the rule applied uniformly, not a new rule.
5. **No runtime constant was changed.** `ULTRA_OPERATOR_CEILING = 400` and `STANDARD_MODE_CEILING = 25` were read, not edited.
