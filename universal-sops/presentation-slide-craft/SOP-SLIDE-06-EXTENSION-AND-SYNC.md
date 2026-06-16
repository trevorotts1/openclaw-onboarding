# SOP-SLIDE-06 — PIPELINE EXTENSION & SYNC (the SOP-LOCKED maintenance procedure)

**Cluster:** Slide-Craft Rules
**Status:** BINDING. Enforced mechanically by `scripts/sync_check.py`.
**Single source of truth:** `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`
**Enforcer:** `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py`

---

## 0. WHY THIS SOP EXISTS

`build_deck.py` is the deterministic Phase-4 renderer + Phase-8 assembler. It hardcodes the
upstream-artifact preflight set (`PREFLIGHT_REQUIRED`, the `_chk_*` callables) and cites
auto-fail codes (`AF-P1`, `AF-P2`, `AF-R3`, `AF-RESEARCH-GATE`, `AF-COVERAGE-1`, `AF-DELIVER`,
`AF-DH1`, `AF-DELIVERY-COMPLETE`). The SOP/role stack (22 roles, the SOP clusters, the MASTER
QC auto-fail ruleset) grows on its own. Before this SOP, **nothing forced a matching Python
update and nothing failed when one was skipped** — a new role / SOP / phase / auto-fail could
ship while the renderer stayed stale, and the repo could not know.

`PIPELINE-MANIFEST.json` is now the one place that declares the pipeline (phases, autofails,
roles). `sync_check.py` reconciles FOUR inputs against it in BOTH directions and exits non-zero
(4) on any drift:

| Input | What it contributes |
|---|---|
| `PIPELINE-MANIFEST.json` | the declared truth: `phases[]`, `autofails[]`, `roles[]`, `manifest_version` |
| `scripts/build_deck.py` | AST: defined `def _chk_*` + module constants; regex: every `AF-...` string it cites |
| `MASTER-QC-AUTOFAIL-RULESET.md` | Section 5 (the machine-checkable summary table) → canonical AF-code set |
| `role-library/presentations/*.md` + `sops/*.md` | the deployed role roster + SOP file set |

**Doctrine:** a rule not auto-failed at a gate does not exist. Lockstep is itself a gate
(`AF-SYNC`), not a convention.

---

## 1. THE FOUR MANDATORY STEPS (adding ANY role / SOP / phase / gate)

> You MAY NOT add or modify a role, SOP, phase, or auto-fail in the Presentations stack
> without ALL FOUR steps below. `sync_check.py` fails the QC gate, the commit, and every
> onboarding deploy until all four are present. The step CANNOT be silently skipped.

| # | Step | File touched | sync_check assertion that enforces it |
|---|---|---|---|
| i | **Declare it in the manifest.** Add the `phases[]` / `autofails[]` / `roles[]` entry. **Bump `manifest_version`.** | `PIPELINE-MANIFEST.json` | A4 (ruleset AF not in manifest), A5 (role file not in manifest), A6 (owning_role not real), A7 (sop_ref not real) |
| ii | **Add the build_deck gate.** New pre-render artifact → write a `_chk_<x>` callable and add it to a phase's `preflight.checker` (or to an autofail's `py_symbol`). Render-time rule → add the constant and name it as the autofail's `py_symbol`. | `build_deck.py` | A1/A2 (manifest checker not defined), A3 (build_deck-enforced AF py_symbol missing), B1 (orphan `_chk_*`) |
| iii | **Add the AF code to the ruleset.** Add the Section-5 row (`Code \| Stage \| Level \| Trigger \| Detection`) to `MASTER-QC-AUTOFAIL-RULESET.md` and wire it into `qc-specialist-presentations(-sops).md`. | MASTER ruleset + qc-specialist | A4 (manifest needs every ruleset code), B2 (build_deck must not cite an unregistered code) |
| iv | **Add a test.** Add a case to `scripts/test_preflight.py`: artifact-present / artifact-missing for a new preflight phase, or a positive/negative fixture for a new AF. | `test_preflight.py` | the test suite (`python3 test_preflight.py`) must stay green; for build_deck-enforced gates the test references the new `_chk_`/symbol |

Each step is enforced by a **different** assertion keyed on a **different** file, so omitting
any one step is caught from the side it was omitted on:
- new SOP merged, code unchanged → A4 / B2 block it;
- code changed, ruleset not updated → A4 / B2 block it (a `_chk_` orphan → B1);
- everything but the manifest → A2 / A4 / A5 block it;
- everything but the test → the test suite fails.

There is no path to a half-updated stack.

---

## 2. RUN IT

```
python3 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py
```

- exit `0` = in sync.
- exit `4` = drift; one block per failing check, grouped (A) stack-ahead-of-code / (B)
  code-ahead-of-stack, each line naming the exact offending symbol/code/file and the fix verb.
- exit `2` = sync_check could not run (an input missing/unparseable).
- `--json` emits `{"in_sync":bool,"drift":[{check,item,detail}]}` for CI / the manifest to record.
- `--explain` maps each drift to the EXTENSION-SOP step that was skipped.

---

## 3. WHERE IT RUNS (three gates — none optional)

1. **QC GATE (Phase 1Q):** the QC specialist's mechanical runner executes `sync_check.py`
   FIRST. Broken lockstep raises `AF-SYNC` (DECK-level meta-autofail) and **no deck QC even
   starts**. (See `qc-specialist-presentations.md` Phase-1Q gate.)
2. **PRE-COMMIT / CI on `openclaw-onboarding`:** any commit touching a Presentations role
   `.md`, a `sops/*.md`, the manifest, or `build_deck.py` runs `sync_check.py` and is blocked
   on drift. (The operator performs the actual commit/push — per the "only operator touches
   GitHub" rule — but CI is what *blocks* a drifted commit before they do.)
3. **EVERY ONBOARDING UPDATE:** the skills-updater runs `sync_check.py` as a deploy preflight
   (alongside `openclaw config validate`). A drifted stack is **never deployed** — the updater
   aborts with the drift report, so a half-updated stack never reaches a client box.

---

## 4. THE VERSION-BUMP DISCIPLINE

`manifest_version` is an integer that MUST increment on every manifest change. Bumping it is
step (i); deployed boxes detect the new stack by the version. Treat a manifest content change
without a version bump as a review failure.

---

## 5. WORKED EXAMPLE — adding a new pre-render phase

Say you add a "fact-check pass" phase that produces `working/research/factcheck.json` and is
gated by a new `AF-FACTCHECK-1`:

1. **manifest:** add a `phases[]` entry (`id`, `owning_role` = a real role stem, `sop_refs` =
   a real `sops/*.md`, `produces_artifact`, `gate_codes:["AF-FACTCHECK-1"]`,
   `preflight:{required:true, checker:"_chk_factcheck", label:"..."}`); add an `autofails[]`
   row (`code:"AF-FACTCHECK-1", enforced_by:"build_deck", py_symbol:"_chk_factcheck"`); bump
   `manifest_version`.
2. **build_deck.py:** write `def _chk_factcheck(path)` and add it to `PREFLIGHT_REQUIRED`.
3. **MASTER ruleset:** add the Section-5 row for `AF-FACTCHECK-1` and wire it into the QC role.
4. **test_preflight.py:** add a present/absent case for `factcheck.json`.

Run `sync_check.py` → exit 0. Skip any one of the four → it exits 4 and names exactly what is
missing.

---

## 6. RELATED

- `PIPELINE-MANIFEST.json` — the single source of truth this SOP maintains.
- `MASTER-QC-AUTOFAIL-RULESET.md` — Section 5 is the canonical AF registry (`AF-SYNC` lives here too).
- `SOP-SLIDE-05-PROCESS-MANIFEST.md` — the per-run attestation (`process_manifest.json`) uses
  the SAME phase ids / gate codes as this manifest, so a run can be checked against the stack
  it claims to follow.
- `scripts/build_deck.py`, `scripts/sync_check.py`, `scripts/test_preflight.py`.
