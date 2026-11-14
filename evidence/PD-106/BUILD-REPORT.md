# PD-106 — BUILD REPORT

Unit: **PD-106** — "Reading interview answers needs the confirmation code when one exists"
Lane: FL21 · Repository: trevorotts1/openclaw-onboarding · Branch: `pd/fl21-web-interview`
Builder: deepseek-chain (chain default) · QC (per ledger): opus-chain, thinking high
Date: 2026-11-13 (Eastern)

---

## 1. Spec rows (quoted)

### 1.1 `01-BUILD-SPEC.md` — unit table row (line 162)

```
| 41 | 5 | PD-106 | Moderate | needed by PD-081 | FL21 | logic | opus-chain high | PD-085 | none |
```

### 1.2 `01-BUILD-SPEC.md` — PD-106 section (line 3544)

```
### PD-106 — Reading interview answers needs the confirmation code when one exists

| Field | Value |
|---|---|
| Findings | PD-106 |
| Severity | Moderate |
| Builder | deepseek-chain — difficulty logic: worker reads, a bridge flag, paging |
| Quality control (finds and fixes) | suggested opus-chain at thinking level high (feeds a Critical unit or the minimum path, logic); re-check of any repair by a FRESH opus-chain agent at high or above; the orchestrator decides |
| Critical first | yes: prerequisite of PD-081 |
| Lane and repository | FL21 · trevorotts1/openclaw-onboarding |
| Wave | 1 |
| Depends on (must be ACCEPTED, that is QC-passed, first) | PD-085 |
| Held by decision | none |
| Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
| Live-action flag | The page and the hosted worker under `deployed-r2/` are live on Cloudflare. Merging changes the repository only. Deploying the worker or the page is a separate live action that needs Trevor's go; no builder or checker deploys. |
| Acceptance rows the checker must run | A1 |
```

Consolidation amendment (binding, quoted verbatim):

```
**Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**

No longer waits for PD-086 (held by decision D-19). It assumes nothing about per-box credentials.
```

Carried-over unit text (quoted verbatim):

```
- **Build unit PD-106 (Moderate, Sonnet; lane FL21).** When a session has a code, `GET …/answers`, `…/review` and `POST …/corrections` require it (header `x-confirm-code`), returning 401 otherwise; the page sends it. `cmd_new` gains `--confirm-code` (default off, so behavior is unchanged) and prints the code on its own line. `latestGrantFor` and `refreshRunIndexFor` follow `truncated`/`cursor`. Acceptance (worker tests): reads without the code → 401 when a code exists; 1,200 stored sessions → renew still finds the newest grant.
```

### 1.3 `01-BUILD-SPEC.md` — FL21 lane row (line 3441)

```
- **Repository:** trevorotts1/openclaw-onboarding · **Branch:** `pd/fl21-web-interview` · **Units in order:** PD-083, PD-084, PD-104, PD-085, PD-106, PD-081, PD-107, PD-086, PD-082a
```

### 1.4 `02-SWARM-PLAN.md` — stage row (line 113)

```
| 5 | PD-004c (FL02, mechanical), PD-048b (FL05, logic), PD-106 (FL21, logic), PD-216 (FL30, logic), PD-319a (FL35, mechanical) | RD-04, RD-05 |
```

### 1.5 `02-SWARM-PLAN.md` — lane table row (line 252)

```
| FL21 | openclaw-onboarding | `pd/fl21-web-interview` | the interview web application: page, hosted worker, bridge and question payload | PD-083 ◇, PD-084 ◇, PD-104 ◇, PD-085 ◇, PD-106 ◇, PD-081 ◆, PD-107, PD-086 [D-19], PD-082a [D-18] |
```

### 1.6 Dependency state at build time

`PD-085` phase `ACCEPTED`, `qc.verdict = PASS`. `PD-106` was READY, then claimed
(`phase: BUILDING`, ledger note: "build dispatched deepseek-chain in wf_3395b580-3b4 at 2026-11-13 10:38:22 EST").

---

## 2. Branch proof before editing

```
$ git ls-remote --heads origin pd/fl21-web-interview
95d11a34706edb6470704ea2d9d103ca5bc4401b	refs/heads/pd/fl21-web-interview
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

Branch exists remotely (40 characters matched); the lane table and the ledger both name
`pd/fl21-web-interview`. No discrepancy — nothing was renamed or invented.

---

## 3. What changed (files + line counts)

| File | +/− |
|---|---|
| `…/interview-app/deployed-r2/src/index.js` | +45 / −9 |
| `…/interview-app/pages/index.html` | +4 / −0 |
| `…/interview-app/deployed-r2/public/index.html` | +4 / −0 |
| `…/interview-app/bridge/intake_bridge.py` | +7 / −0 |
| `…/interview-app/deployed-r2/test/test_pd106_confirm_code.mjs` (new) | +93 / −0 |
| `…/interview-app/deployed-r2/test/test_pd106_paging.mjs` (new) | +106 / −0 |
| `…/interview-app/test/test_pd_webapp_pd106_confirm_code.py` (new) | +124 / −0 |

Base path prefix for every row: `23-ai-workforce-blueprint/templates/role-library/presentations/intake/`.

Behavior implemented, mapped to the unit text:

1. **Reads require the code (header `x-confirm-code`).** `confirmCodeError(request, session)` returns a
   401 `confirmation code required or incorrect` when the session carries `confirm_code` and the header
   does not match (constant-time compare). Applied to `pollAnswers` (`GET …/answers`),
   `reviewAnswers` (`GET …/review`, signature widened to take the request) and `postCorrection`
   (`POST …/corrections`). A code-less session is untouched — the guard returns null.
2. **The page sends it.** `apiJson()` adds `x-confirm-code` from `SESSION.confirmCode`, so every session
   call (answers poll, review, corrections) carries it once the client has typed the code. Both page
   copies changed identically; `cmp` is clean.
3. **`cmd_new --confirm-code` (default off) prints the code on its own line.** The `new` parser gained
   `--confirm-code` (`store_true`); `cmd_new` now forwards `confirm_code=` into `_mint_session` (it did
   not before — `mint` did) and prints `confirm_code: <code>` as its own line only when a code was minted.
4. **Paging.** New `listAllKeys(bucket, prefix)` follows `truncated`/`cursor`; `latestGrantFor` and
   `refreshRunIndexFor` now use it instead of a single `list()` page.

---

## 4. Per-test results

### 4.1 Rows and their tests

| Row | Test | What it asserts |
|---|---|---|
| A1a | `deployed-r2/test/test_pd106_confirm_code.mjs` — "a coded session 401s every stored-answer read without x-confirm-code" | answers/review/corrections → 401 with no header and with a wrong header; 200 with the right one |
| A1b (control) | same file — "a code-less session is unchanged — reads need no header" | no code minted → all three reads succeed with no header |
| A1c | `deployed-r2/test/test_pd106_paging.mjs` — "1,200 stored sessions — renew still finds the newest grant" | 1,199 decoys + 2 target grants, newest on the last page → renew 201, same session_id, revision 3, run index rebuilt from every page |
| A1d (control) | same file — "an unpaged first-page-only bucket answers 404" | proves A1c discriminates: the pre-fix single-page scan answers 404 |
| A1e | `test/test_pd_webapp_pd106_confirm_code.py` — `test_a1e_…` | `new --confirm-code` sends `want_confirm_code: true` and prints `confirm_code: 123456` on its own line |
| A1f | same file — `test_a1f_…`, `test_a1f2_…` | no flag → `want_confirm_code: false`, no code line; the real parser defaults the flag off |
| A1g | same file — `test_a1g_…` | page sends `x-confirm-code` from `apiJson`; both page copies byte-identical (`filecmp`, shallow=False) |

### 4.2 HEAD (with the change) — my rows

```
$ node --test deployed-r2/test/test_pd106_confirm_code.mjs
✔ PD-106 A1a: a coded session 401s every stored-answer read without x-confirm-code
✔ PD-106 A1b: a code-less session is unchanged — reads need no header
ℹ tests 2  ℹ pass 2  ℹ fail 0

$ node --test deployed-r2/test/test_pd106_paging.mjs
✔ PD-106 A1c: 1,200 stored sessions — renew still finds the newest grant
✔ PD-106 A1d control: an unpaged first-page-only bucket answers 404
ℹ tests 2  ℹ pass 2  ℹ fail 0

$ python3 -I test/test_pd_webapp_pd106_confirm_code.py
test_a1e_flag_mints_a_code_and_prints_it_on_its_own_line ... ok
test_a1f2_cli_accepts_the_flag_and_defaults_to_off ... ok
test_a1f_default_is_off_and_changes_nothing ... ok
test_a1g_page_sends_the_header_and_copies_are_identical ... ok
Ran 4 tests … OK
```

### 4.3 Base commit (95d11a3, before the change) — same tests copied in

```
$ node --test deployed-r2/test/test_pd106_confirm_code.mjs deployed-r2/test/test_pd106_paging.mjs
✖ PD-106 A1a: a coded session 401s every stored-answer read without x-confirm-code
✔ PD-106 A1b: a code-less session is unchanged — reads need no header
✖ PD-106 A1c: 1,200 stored sessions — renew still finds the newest grant
✔ PD-106 A1d control: an unpaged first-page-only bucket answers 404
ℹ pass 2  ℹ fail 2

$ python3 -I test/test_pd_webapp_pd106_confirm_code.py
FAIL: test_a1e_flag_mints_a_code_and_prints_it_on_its_own_line
FAIL: test_a1g_page_sends_the_header_and_copies_are_identical
AssertionError: 'x-confirm-code' not found in '<!doctype html>…'
```

A1a/A1c/A1e/A1g are RED at base and GREEN at head; the two controls (A1b, A1d) are GREEN on both,
exactly as a discriminating pair must be.

---

## 5. Mutation proof

Three mutations, each applied to the head tree, run, then restored from a saved copy.

**M1 — remove the three `confirmCodeError` guards (3 occurrences) from `deployed-r2/src/index.js`:**

```
✖ PD-106 A1a: a coded session 401s every stored-answer read without x-confirm-code
✔ PD-106 A1b: a code-less session is unchanged — reads need no header
ℹ pass 1  ℹ fail 1        (rc=1)
```

Restored:

```
✔ PD-106 A1a …   ✔ PD-106 A1b …
ℹ pass 2  ℹ fail 0        (rc=0)
```

**M2 — replace both `listAllKeys(...)` calls with the old single-page list (2 occurrences):**

```
✖ PD-106 A1c: 1,200 stored sessions — renew still finds the newest grant
✔ PD-106 A1d control: an unpaged first-page-only bucket answers 404
ℹ pass 1  ℹ fail 1        (rc=1)
```

Restored:

```
✔ PD-106 A1c …   ✔ PD-106 A1d …
ℹ pass 2  ℹ fail 0        (rc=0)
```

**M3 — drop `confirm_code=getattr(args, "confirm_code", False)` from `cmd_new`:**

```
Ran 4 tests … FAILED (failures=1)     (test_a1e)
```

Restored:

```
Ran 4 tests … OK
```

Restoration verified: `cmp` of the restored `deployed-r2/src/index.js` against the saved good copy is
clean, and `node --check` passes.

---

## 6. Wider affected suite — base vs head

Same command both sides: `node --test test/*.mjs deployed-r2/test/*.mjs` in
`…/interview-app`, plus the bridge Python tests.

| Suite | Base 95d11a3 | Head c1d9f22 |
|---|---|---|
| node `test/*.mjs` + `deployed-r2/test/*.mjs` | tests 63 · pass 62 · fail 1 | tests 67 · pass 66 · fail 1 |
| `test_pd085_resume_company_id.py` | PASS | PASS |
| `test_intake_bridge_dispatch.py` | PASS | PASS |
| `test_pres009_bridge_and_migration.py` | PASS | PASS |
| `test_pres023_bridge_ack.py` | PASS | PASS |
| `test_email_help_contract_agreement.py` | PASS | PASS |
| `test_payload.py` | FAILED (failures=3) | FAILED (failures=3) |
| `test_pd_webapp_pd106_confirm_code.py` | (did not exist) | PASS (4 tests) |

**Pre-existing failures, proven at base — not asserted:**

- `test/test_dept_start_handoff.mjs` — module load throws
  `Error: CC_ROOT (or COMMAND_CENTER_ROOT) must point at a local Command Center checkout`
  at base 95d11a3 and identically at head. Environment precondition, not this unit's file.
- `test/test_payload.py` — 12 tests, 3 failures at base and 12 tests, 3 failures at head. This unit
  never touches `payload/build_questions_payload.py`.

The +4 tests at head are exactly the four new PD-106 tests; nothing else moved.

---

## 7. Hunk attribution

- Merge-base with `origin/main`: `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
- `origin/main` at build time: `ebf5c769a2ad5b2582bf2256588095cbef20cfac`
- Branch commits from the merge-base to head, by unit:

| Commit | Unit |
|---|---|
| `ae8033c81` | PD-083 |
| `5dc024a8a` | PD-084 |
| `76ccbfd4f` | PD-901 (unit id renamed on the branch) |
| `e24eeb63b` | PD-909 |
| `8c2ea57f8` | PD-911 |
| `dbcff4341` | PD-914 |
| `597e6c796` | PD-929 |
| `95d11a347` | PD-085 |
| `c1d9f2252` | **PD-106 (this unit)** |

This unit's commit touches 7 files, all inside PD-106's owned paths
(`pages/index.html`, `deployed-r2/**`, `bridge/intake_bridge.py`, `test/test_pd_webapp_*.py`).
No shared file was edited: `test/pres024_env.mjs` was **read and imported**, never modified, so
`test_pd106_confirm_code.mjs` and `test_pd106_paging.mjs` carry their own request driver and
paging shim instead of changing the shared harness.

---

## 8. Remote-head proof

```
PRE-PUSH  (local, before commit):  95d11a34706edb6470704ea2d9d103ca5bc4401b
NEW HEAD  (commit c1d9f2252):      c1d9f22526c32d265066b197de0620214d7606ad

$ git push origin HEAD:refs/heads/pd/fl21-web-interview
   95d11a347..c1d9f2252  HEAD -> pd/fl21-web-interview
(rc=0 — fast-forward, no rebase, no force)

$ git ls-remote --heads origin pd/fl21-web-interview
c1d9f22526c32d265066b197de0620214d7606ad	refs/heads/pd/fl21-web-interview
$ git rev-parse HEAD
c1d9f22526c32d265066b197de0620214d7606ad
```

Remote head equals local head, 40 characters, exact string match.

---

## 9. Unproved / out of scope (honest section)

1. **No live-worker proof.** The hosted worker under `deployed-r2/` and the page are live on
   Cloudflare; this unit changed the repository only. Nothing was deployed and no live endpoint was
   probed. The 401 behavior is proven against the real `src/index.js` on the in-memory R2 shim, not
   against production.
2. **`worker/src/index.js` (the D1 worker) was not changed.** The spec's owned-file list names
   `deployed-r2/**` and the page/bridge/payload files, not `worker/**`. The D1 worker has no
   `confirm_code` mint path at all (only `lib.js` exports `sixDigitCode`), so PD-106's "when a session
   has a code" clause is vacuous there today. If the D1 worker ever becomes production, it needs the
   same guard — that is a separate unit, not this one.
3. **`refreshRunIndexFor` cost is unchanged in kind.** It still reads every session object to rebuild
   the run index; paging fixes correctness, not the O(sessions) scan. A 1,201-object scan per renew is
   acceptable at today's volume but is a known ceiling. `ponytail:` the index could be maintained
   incrementally instead of rebuilt.
4. **`fetchIntake`'s tenant-prefix scan (`deployed-r2/src/index.js` line ~990) still reads one page.**
   It is an intake lookup, not a session read, and the unit does not name it. Left untouched and
   flagged here.
5. **`--confirm-code` on `new` has no companion on `resume`.** `renewSession` writes the fresh grant
   with `confirm_code: null`, so a renewed link no longer asks for the code. That is pre-existing
   worker behavior and the unit does not name it. Flagged, not changed.
6. **The page's review/corrections calls do not exist yet.** `pages/index.html` now sends the header
   from `apiJson`, which covers those paths when they are added, but today the page only exercises
   `GET /answers` after the code is typed. A1g asserts the header wiring in `apiJson`, not a browser
   click-through.
