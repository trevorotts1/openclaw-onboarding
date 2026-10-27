# T-23 WIRE — verification record for `monthly_manifest.py`

Lane `PBB-1705` (BUILD). Repo `trevorotts1/openclaw-onboarding`. Unit audited tip
`d5661d13bf139a0695a582896e5840ac45622ce1` on `pb/PBB-669/t-23-wire`, classified REBUILD.

| | |
|---|---|
| Base sha | `c994359d6329b6f958c217ee455b40cfb8a0543c` |
| Compared against | `origin/main` = `8cb74925ad94c05ce9eb639e7554d02fcd780e20` |
| This lane's branch | `pb/PBB-1705/t-23-wire`, cut from `origin/main` |
| Model that answered | `deepseek-flash`, read from this lane's own transcript `/Users/blackceomacmini/.claude-nine/projects/-Users-blackceomacmini/de7e2c56-8b71-4947-9a50-862acd71f889/subagents/workflows/wf_cac0afd5-a07/agent-ab438891c46f51c79.jsonl` (the session banner said `deepseek-chain`; both values are reported as observed, unreconciled) |
| Verdict | none of mine. This is evidence. An independent QC lane judges. |

---

## 1. What the audited tip actually added, and what main already had

`git merge-base origin/main d5661d13bf139a0695a582896e5840ac45622ce1` = `c994359d...`.
Diff `base..d5661d13bf139a0695a582896e5840ac45622ce1`, 274 insertions, 0 deletions, 3 files.

Every added line was then matched, line for line, against the same file's blob on the live
`origin/main` (`git show origin/main:<path>`), so "already present" means an identical line,
not a similar one.

| File | Added | Present on main | Absent |
|---|---|---|---|
| `.github/workflows/qc-static.yml` | 22 | 22 | 0 |
| `38-conversational-ai-system/tools/pb_contracts.py` | 26 | 26 | 0 |
| `evidence/PBB-669/T-23-WIRE.md` | 226 | 0 | 226 |

Control: `git merge-base --is-ancestor deadbeef origin/main` exits **128** (unresolvable object),
so the instrument discriminates. `git merge-base --is-ancestor d5661d13... origin/main` exits **1**
— the audited tip itself is not on main, but its code content already is.

**Conclusion drawn from the counts only:** none of the 48 added lines of working code is missing
from main. The wiring landed under `503577b39` — *T-23: wire joined monthly approval terms into
pb_contracts validate*. The one genuinely absent artifact is this evidence record, which is what
this lane rebuilt, together with fresh proof that the landed wiring still works and still bites.

---

## 2. Where the wiring lives on `origin/main`

```
38-conversational-ai-system/tools/pb_contracts.py
  764  def _approval_terms_errors(doc):
  791      if not errs and args.kind == "approval":
  792          errs = _approval_terms_errors(doc)

.github/workflows/qc-static.yml
 3403  - name: T-23 joined monthly approval manifest suite (explicit name)
 3409      t="shared-utils/manifest/tests/test_monthly_manifest.py"
 3418      echo "✓ T-23 joined monthly approval manifest suite ran and passed"
```

Both the module (`shared-utils/manifest/monthly_manifest.py`) and its suite
(`shared-utils/manifest/tests/test_monthly_manifest.py`) exist on main, so the workflow step
resolves to a real file rather than taking its loud-SKIP branch.

---

## 3. Instrument A — the suite the workflow names

```
python3 -I shared-utils/manifest/tests/test_monthly_manifest.py
```

| Run | rc | Result |
|---|---|---|
| As landed | **0** | `Ran 62 tests ... OK` |

Bite proof — break the subject, prove the suite notices, restore:

| Step | rc | Result |
|---|---|---|
| `terms_errors` patched to `return []` immediately | **1** | `Ran 62 tests ... FAILED (failures=30)` |
| Original restored from a saved copy | **0** | `OK`; sha256 back to `48481c8094c8...` and `git status --porcelain` empty |

A suite that stayed green with `terms_errors` gutted would have been decoration. It is not.

---

## 4. Instrument B — the wiring in `pb_contracts validate`

The suite above exercises the module. It does **not** exercise the call site the wiring commit
added inside `cmd_validate`. So the probe drives the real CLI, exactly as the wiring exposes it:

```
python3 -I pb_contracts.py validate --kind approval --file <case>
```

Three cases over one schema-valid manifest: `good` (must be accepted — proves the path runs),
`blank-cta` (`cta_text` is whitespace, passes the schema's `minLength` but carries no information),
`out-window` (`scheduled_at` past the joined 30-day window).

| Case | Wired rc / ok | Unwired control rc / ok |
|---|---|---|
| `good` | 0 / True — PASS | 0 / True — PASS |
| `blank-cta` | 1 / False — PASS, `$.placements[PL-probe-1].cta_text: an approved term must be present` | 0 / True — **accepted** |
| `out-window` | 1 / False — PASS, `$.placements[PL-probe-1].scheduled_at: '2026-12-20T15:00:00Z' is outside the joined campaign window 2026-11-02..2026-12-01` | 0 / True — **accepted** |
| Totals | **3 of 3 as required, rc 0** | **1 of 3, rc 1** |

The control is the same `pb_contracts.py` with the two-line call removed from `cmd_validate`, run
against an identical copy of `schemas/`. Removing it makes both refusals vanish while `good` still
passes — so the wiring, not the schema, is what refuses a thin manifest. The wiring is load-bearing.

An earlier version of this control failed with `rc=2 file not found: .../schemas/approval-manifest.schema.json`.
That was the control being broken, not the target; the schemas were copied in and the run repeated.
`rc=2` is never reported here as a result about behaviour.

---

## 5. Scope

Files this lane touched: `evidence/PBB-669/T-23-WIRE.md` only. No CHANGELOG, no skill-version file,
no CI workflow, no deletion, no change to `pb_contracts.py` or `monthly_manifest.py` — the code
under test is main's, unmodified, so the proof in sections 3 and 4 is a proof about main.

Probe and logs are lane scratch, held under
`Purple-Billboard-Client-System-Build/tmp/` and not committed:
`pbb1705-probe_validate.py`, `pbb1705-manifest-suite.log`, `pbb1705-bite-broken.log`,
`pbb1705-bite-restored.log`, `pbb1705-unwired/`.
