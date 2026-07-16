# U59 (JM/U55) — Devil's Advocate end-to-end — ONB-side evidence

Unit: U59 (P1, both — `trevorotts1/openclaw-onboarding` half). Crosswalk: JM/U55.
Deps: U52/U56 (dept-detail contract-test harness pattern — **verified**, v6.0.13); D-J1
(challenge-content visibility + status-lifecycle canon — governs the CC-side U55c/U55e
surfaces, not the ONB half below). This evidence folder covers the **ONB-repo slice**
of U59 only: **U55a** (operator-box proof of the generator) and **U55d** (the thin
bridge). The CC-repo slice (U55b demo purge, U55c POST/PATCH write path, U55e
PRD-conform surfaces, U55f PRD fix) lands on its own `blackceo-command-center` train.

Repo pin: `trevorotts1/openclaw-onboarding` fresh clone at `origin/main`
`9f7d3e5c5945b25046ba134a65e442de5391d5a6` (2026-07-15). Branch `skill6-v2/U59` cut
from this commit.

## U55a — operator-box proof of the generator (this box, this pass)

Per spec: "run `python3 shared-utils/devils-advocate.py --trigger <t>
--context-json <ctx>` … for all five triggers with fixture contexts; record stdout
JSON + exit codes. Also exercise the documented template-only fallback (no LLM key
present) and record that it degrades honestly. If ANY trigger fails, fix the
generator FIRST."

Five fixture context files (`ctx-<trigger>.json`, this folder) were authored from the
RUNBOOK's own documented invocation shape (`23-ai-workforce-blueprint/RUNBOOK-v2.1.md`
lines 85-99) — one per trigger in `devils-advocate.py`'s own argparse `choices`
(`critical_task`, `strategic_decision`, `consecutive_approval`, `kpi_swing`,
`sensitive_dept`). Each was run for real, on this box, via:

```
$ python3 shared-utils/devils-advocate.py --trigger <t> --context-json ctx-<t>.json --format json
```

Results (`out-<t>.json` = stdout, `err-<t>.txt` = stderr, `exitcode-<t>.txt` = exit code):

| trigger | exit | schema-valid | path taken |
|---|---|---|---|
| critical_task | 0 | yes | template-only fallback |
| strategic_decision | 0 | yes | template-only fallback |
| consecutive_approval | 0 | yes | template-only fallback |
| kpi_swing | 0 | yes | template-only fallback |
| sensitive_dept | 0 | yes | template-only fallback |

**Five green runs — ALL PASS.** Independently re-validated by machine (not eyeballed):
every output JSON was parsed and asserted to carry all seven `generate_challenge()`
keys (`trigger_type`, `challenge`, `specific_concern`, `assumptions`, `severity`,
`confidence`, `raw_response`), `trigger_type` matching the `--trigger` argument,
`severity` one of `low|medium|high`, and non-empty `challenge`/`specific_concern`
text — see the validation run below. No trigger crashed, hung, or emitted invalid
JSON. Nothing in this pass required fixing the generator to reach five green runs.

## Template-only fallback — exercised and degrades honestly

All five runs took the `_fallback_response()` path (`shared-utils/devils-advocate.py`
lines 112-134), not the LLM-backed path — this is the exact "no LLM key present"
degrade the spec asks to prove. Root cause, traced this pass (not assumed): the
module-level guard at lines 26-31 —

```python
SELECT_MODEL_AVAILABLE = False
try:
    from select_model import call_model_with_fallback
    SELECT_MODEL_AVAILABLE = True
except Exception:
    pass
```

— sets `SELECT_MODEL_AVAILABLE = False` on this box because `select_model.py`
(`shared-utils/select_model.py`) does not export a symbol named
`call_model_with_fallback` (confirmed by direct import: `ImportError: cannot import
name 'call_model_with_fallback' from 'select_model'`; `select_model.py`'s real
public surface is `select_model_for_skill`/`select_task_model`/
`resolve_dept_default_model`/etc. — a model-ID *recommendation* API, not an
inference-calling one). `git log --all -S "call_model_with_fallback" --
shared-utils/` shows the reference was introduced once (commit `2b5ab1f9`) and never
paired with a definition anywhere in this repository's history. A second file,
`shared-utils/extract-behavioral-patterns.py`, imports the same non-existent symbol
the same way — this is a pre-existing, shared, cross-file dead-code path, not
something introduced by this pass.

**Scope call (recorded, not silently fixed):** this does not fail U55a's own binary
acceptance — the fallback path is a *documented, intended* degrade branch (the
module's own docstring: "Template-only response when no LLM is available"), and all
five CLI invocations returned exit 0 with schema-valid JSON, satisfying "five green
runs" literally. Implementing a real `call_model_with_fallback` in `select_model.py`
is a materially separate piece of work (provider/credential resolution + an actual
HTTP inference call, mirroring the established client-judge pattern in
`shared-utils/page_qc.py`'s `_load_model_router()`/`_call_chat()`) that would also
change behavior for `extract-behavioral-patterns.py`'s unrelated Skill-15/23 caller —
out of U59's stated scope (Devil's Advocate) and not attempted here to avoid
undertested scope creep on a shared dependency. Logged here as a real, reproducible
finding for a future dedicated unit; the generator's own degrade behavior in
response to it is correct and is exactly what this proof exercises.

## Machine validation of the five outputs (this pass)

```
$ python3 -c "
import json
triggers = ['critical_task','strategic_decision','consecutive_approval','kpi_swing','sensitive_dept']
required_keys = {'trigger_type','challenge','specific_concern','assumptions','severity','confidence','raw_response'}
for t in triggers:
    d = json.load(open(f'ledgers/evidence/U59-JM-U55/out-{t}.json'))
    missing = required_keys - set(d.keys())
    ok = (not missing) and d['trigger_type']==t and d['severity'] in ('low','medium','high') \
        and isinstance(d['confidence'], float) and len(d['challenge'])>0 and len(d['specific_concern'])>0
    print(t, 'OK' if ok else f'FAIL missing={missing}')
"
critical_task OK
strategic_decision OK
consecutive_approval OK
kpi_swing OK
sensitive_dept OK
```

## U55d — the thin bridge (build, this pass)

New file: `shared-utils/devils-advocate-bridge.py`. Invokes the generator in-process
(direct module load via `importlib`, same technique the repo's own
`tests/unit/*.test.py` files use for the hyphenated `devils-advocate.py` filename —
no subprocess dependency, no change to the generator itself, "single-purpose,
independently testable" per spec) and POSTs its JSON output to the CC-side
`POST /api/da-challenges` (U55c, other repo/train). Auth mirrors the repo's
established producer-bridge convention byte-for-byte
(`06-ghl-install-pages/tools/cc_board.py` `board_config()`/`_sign()`/`_post_json()`):
`Authorization: Bearer <MC_API_TOKEN>` (if set) + `x-webhook-signature:
HMAC-SHA256(WEBHOOK_SECRET or CC_WEBHOOK_SECRET, rawBody)` hex (if set), stdlib
`urllib` only, `MISSION_CONTROL_URL` absent ⇒ clean disabled no-op (exit code 2,
distinct from a real POST failure). See the bridge's own module docstring for the
full wire-payload CONTRACT (the field set the CC-side U55c route must accept) and
`tests/unit/u59-devils-advocate-bridge.test.py` for full offline proof (a real
loopback HTTP server, no network, no live credential) of the signed-header wire
format plus every FAIL-SOFT branch.

**Cross-repo leg owed, not faked:** a live POST against the real, merged CC-side
`POST /api/da-challenges` (spec binary-acceptance item 3 — "one documented generator
invocation through the bridge produces exactly one new `da_challenges` row … and
that challenge renders on the overview feed AND that department's
`/ceo-board/[dept]` feed") cannot be proven from this repo alone: it requires U55c
merged and live first. This pass proves the ONB-side write path is correct and
fully wire-tested against a local mock server standing in for the documented
contract; the live cross-repo integration proof is owed to the merge-writer pass
that lands both halves.
