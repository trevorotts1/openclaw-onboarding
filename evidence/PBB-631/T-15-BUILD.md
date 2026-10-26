# T-15 BUILD — PASS (built; independent QC required)

Unit: T-15 · lane PBB-631 · branch `pb/PBB-609/t-15-build` · worktree `worktrees/PBB-609`
Build commits: `8d60cbd83` (module + suite), `64b6e38e7` (call site + CI step + bookkeeping)
Dependency merge: `016ec2387` (T-14 `c6182220`) · Freshness merges: `1fd0e65cb` (main `108631851`), `c23a00236` (main `de85ac2f0`)
C-15 blocker cleared: **yes**. Rows satisfied at build level: **1 of 4 green, 3 pending focused-trace fixtures**.
Verdict: the unit is BUILT and reachable. It is **not self-approved** — it needs an independent QC lane.

---

## 1. C-15 re-answer, on evidence

The prior lane (PBB-609) blocked on row **C-15** because T-14 was `NOT_STARTED` and its decision
artifact was absent. That condition has changed, and this is the re-answer from the artifact itself,
located at T-14 head `c6182220934c3fb095a73afa56e169b4f565d132` (`pb/PBB-611/t-14-repair6`).

Artifact: `shared-utils/bonus/BONUS-ACCESS-CAPABILITY-DECISION.md`, with code
`shared-utils/bonus/access_capability.py`, suite `shared-utils/bonus/tests/test_access_capability.py`,
production call site `44-convert-and-flow-operator/tools/bonus_access_decision.py`. Verbatim:

> **Decision:** **BLOCKED** for every automated route. Supported path is **assisted/operator**.

> `request_bonus_access(unattended=True)` is **refused** — `route: "refused"`, reason code above, the
> five blocked steps named in the reason, and an explicit assisted offer. No silent downgrade, no fake success.

> **T-15** — the real bonus access adapter (identity/grant/credential/SMS/resource authorization,
> failed-step resume, return access, email-later same member). It is blocked by this decision and must
> not fabricate the route.

> The one-logical-SMS-ask contract (D-26: queued, dispatching, accepted, failed-not-sent, unknown or
> suppressed; one ask ID per sequence) is a **delivery** contract owned by T-15. It states the
> dependency instead of duplicating the state machine.

**Does it clear C-15? YES.** The blocker was the absence of any accepted capability decision, which
left "implement **selected** real bonus access" with no selection. The decision now exists at the T-14
head with per-step evidence (§2), the official route table (§3), and a chosen supported path:
`assisted_operator`, `available: false`, `api: null`, `reason_code: "BONUS_ACCESS_CAPABILITY_BLOCKED"`.
That is a selection T-15 can implement without fabricating a vendor route: the adapter separates the
five authorizations, resumes the failed step only, returns access and keeps email-later on the same
member — with `automated: false` and no grant claim anywhere. The decision's own §8 assigns exactly
this to T-15. C-15 is therefore answerable and is answered by the build in §3.

Honest caveat, measured: the artifact is present at the T-14 head (the bar this lane was given) and is
now carried in this branch by the recorded dependency merge `016ec2387`; it is **not yet on
`origin/main`** (ancestry probe `git merge-base --is-ancestor c6182220 origin/main` = rc 1, control
`origin/main`→`origin/main` = rc 0). Nothing here depends on a claim that it is.

## 2. Instrument proof, both polarities

Same shell, same git, same run as every row below. `127`/`128` are instrument aborts, never facts.

| probe | command | expected | result | rc |
|---|---|---|---|---|
| EXPECTED-PASS ancestry | `git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main` | 0 | 0 | 0 |
| EXPECTED-PASS control | `git merge-base --is-ancestor origin/main origin/main` | 0 | 0 | 0 |
| EXPECTED-FAIL path (known absent) | `git ls-tree -r --name-only origin/main -- shared-utils/ZZ_NO_SUCH_FILE_PBB631.md` | empty | empty | 0 |
| EXPECTED-FAIL path, second instrument | `test -f ZZ_NO_SUCH_FILE_PBB631.md` (worktree) | 1 | 1 | 1 |
| EXPECTED-PASS path control | `test -f README.md` (same worktree) | 0 | 0 | 0 |
| EXPECTED-FAIL unrelated sha (real, unmerged) | `git merge-base --is-ancestor 852fa3de06640a8714e1492270facb489df89ba4 origin/main` | 1 | 1 | 1 |
| instrument abort (NOT used as evidence) | `git cat-file -e origin/main:shared-utils/ZZ_NO_SUCH_FILE_PBB631.md` | — | fatal, rc 128 | 128 |

The `git cat-file -e` absence probe returns `128` (fatal) rather than a clean negative; that run is
discarded as an instrument abort and the absence is carried by the two probes above it instead.

## 3. The build

**Reuse, not a rewrite.** `shared-utils/bonus/access_adapter.py` and
`shared-utils/bonus/tests/test_access_adapter.py` were restored byte-for-byte from commit `580a9638a`
(PBB-458's add commit; it was later deleted at `08cd289bd` and never reached main). Pre-patch sha256 of
the module: `23beb3810ca3064f4d064ed55dc3e440382ea18f51658dfba14d2459f5d506d3`, which matches the
hash recorded in `control/qc/T-15.ab3f4123...json`. (That receipt's hash for the test file is 63 hex
characters — impossible for sha256 — so byte-identity for the test is anchored to the git object at
`580a9638a`, not to that receipt.)

One docstring truth-up (the only change to the restored bytes): the stale candidate reference
(`origin/pb/PBB-356/t-14-repair3@dc5c25aa5`) is replaced with the landed T-14 decision; the two
slash-run decomposition comparisons and the padded citation pair are spelled as prose; the acceptance
quote is rendered as the reviewed-window sentence. Reason: T-14's closed-world API-shape scan
(`test_no_other_bonus_file_carries_an_api_shape`, `shared-utils/bonus/tests/test_access_capability.py:1309`)
scans every sibling file under `shared-utils/bonus/`, and it admits the glued run
`identity/grant/credential/SMS/resource` only inside its own reviewed window. With the docstring as
originally written the sibling scan failed 8 ways (`bare-path:identity/grant/credential/SMS/resource`,
`bare-path:D-28 / C-F07`, …); after the truth-up both suites are green. Final shas:
`access_adapter.py` `204a6f6ea9f96057453262712487c59bb1c4b7f11c8a57152094cb8917d653a7`,
`test_access_adapter.py` `ca207678a66ec921e264b937be81940cfa0b95e9f1076e3b26035a61ef4e2a60`.

**What the module is** (`shared-utils/bonus/access_adapter.py`):
- `DIMENSIONS = ("identity", "grant", "credential", "sms", "resource")` — five separate authorizations
  (`:75`), each verdict about its own dimension (`authorize()`, `:192`); a pass never mints a sibling,
  a denial never cascades; an expired credential is not expired guides.
- `AccessLedger` (`:243`): channel bindings that cannot move between members
  (`MemberContinuityError`), `record_failed_step` (`:291`) against the member the channel resolved to,
  `defer_to_email` (`:334`) — email-later is a deferral of the SAME member, never a second account —
  and `resume` (`:361`) that returns access only to the member the returning channel proves.
- No provider, no network, no URL, no verb: `BLOCK_REASON` and `automated: False` on every result; it
  imports no fulfillment module, so a blocked bonus lane cannot gate the original gift (D-28 / C-F07).

**Production call site, in an existing production entry point**
(`44-convert-and-flow-operator/tools/bonus_access_decision.py`, T-14's operator CLI — the same entry
point T-14 itself was accepted on): `from bonus import access_adapter as aa` (`:53`), five
subcommands — `access-authorize` (`:185`), `access-bind`, `access-fail`, `access-defer`,
`access-resume` (`:198`) — each driving the adapter through its public API. The adapter's ledger is in
memory by design (its docstring names the caller as owner of durability), so the CLI owns the state in
a `--state` JSON file and replays it through `bind` / `record_failed_step` / `defer_to_email` on every
invocation (`_ledger_load`, `:89`) — no second state machine. Refusals surface as
`AccessAdapterError`/`MemberContinuityError` through the CLI's existing error envelope (`:224`).

**Exactly one added CI step** (`.github/workflows/qc-static.yml:3239-3254`, appended after the T-14
step, no restructuring): `T-15 bonus access adapter suite (explicit name)`, naming
`shared-utils/bonus/tests/test_access_adapter.py` by explicit path (`:3245`), DRY-listing it,
SKIPping loudly on an absent checkout, then `python3 -I "$t"` (`:3253`) — the T-22 explicit-name
pattern this file already uses.

## 4. The two wiring proofs (before → after, controls in the same scans)

Scanner: `tmp/pbb631-scan.py`, file-level counts over `git archive` trees of `016ec2387` (before) and
`64b6e38e7` (after). Controls in the same runs: `canonical_contact_id` 46 → 46, `presentation_job`
421 → 421, `direct_fulfillment` 19 → 21, `access_capability` 8 → 9 (file counts; the two that moved
moved because the new module test and CHANGELOG name them — the controls are nonzero in both runs, so
the zeros below are discriminating).

| metric | before (`016ec2387`) | after (`64b6e38e7`) |
|---|---|---|
| importers of `access_adapter` (any) | **0** | **2** (`44-convert-and-flow-operator/tools/bonus_access_decision.py`, `shared-utils/bonus/tests/test_access_adapter.py`) |
| production call sites (non-test) | **0** | **1** (`44-convert-and-flow-operator/tools/bonus_access_decision.py`) |
| workflow files naming `test_access_adapter` | **0** of 66 | **1** (`.github/workflows/qc-static.yml`) |
| `qc-static` job steps (parsed) | 145 | 146 — delta **+1**, T-15 step index **146** (last) |

Before-tree raw `access_adapter` mentions = 1 file — PBB-609's own report prose, which is why the
metric is importers/call sites, not any mention.

## 5. Inverse control

Throwaway copy built with `git archive` of `64b6e38e7` into `tmp/pbb631-inverse/` (never inside a
worktree). Wiring reverted there — `bonus_access_decision.py` and `.github/workflows/qc-static.yml`
restored to their `016ec2387` content — and the same scanner re-run:

| metric | wired | wiring reverted |
|---|---|---|
| production call sites | 1 | **0** |
| workflow files naming the suite | 1 | **0** |
| `qc-static` job steps | 146 | **145** (T-15 step index None) |

Controls unchanged across the revert (46 / 421 / 21 / 9). Restored afterwards; all four files sha256
match the worktree exactly (`bonus_access_decision.py` `ebb33b46…`, `qc-static.yml` `9f65d800…`,
`access_adapter.py` `204a6f6e…`, `test_access_adapter.py` `ca207678…`) — the inverse experiment
changed nothing in the real tree.

## 6. Acceptance rows, quoted verbatim (revisions/v2.0/live-ledgers/checks.json), each marked

**C-15** — `type: focused_artifact_or_required_ci`, `required: true`, scope verbatim:
> "Separate identity/grant/credential/SMS/resource authorization; return access and email-later same member."

**PASS (built)** — the focused artifact exists and the required CI names its suite:
`shared-utils/bonus/access_adapter.py:75` (five separate dimensions), `:192` (`authorize`), `:334`
(email-later same member), `:361` (resume = return access);
`44-convert-and-flow-operator/tools/bonus_access_decision.py:53,185,198` (production call site);
`.github/workflows/qc-static.yml:3239-3254` (required CI). Suite green: 39 tests OK. Verification of
the row still belongs to an independent QC lane.

**C-F04** — `type: minimal_focused_trace`, scope verbatim:
> "Every-send gate STOP/rebind/window"

**PENDING (no heavy permit, MEMORY RED)** — the F-04 trace fixture was not run. T-15's contribution is
by design zero-surface: the adapter has no send path (`shared-utils/bonus/access_adapter.py:34-47`,
"WHAT THIS IS NOT"), and the every-send gate remains T-12's `outbound_gate.dispatch`. Same reading the
prior lane reached; the fixture itself is shared with T-12/T-13/T-20/T-21.

**C-F07** — `type: minimal_focused_trace`, scope verbatim:
> "Original gift while bonus unavailable"

**PENDING (no heavy permit, MEMORY RED)** — the F-07 trace fixture was not run. The independence
direction is pinned at unit level: `shared-utils/bonus/tests/test_access_adapter.py:351`
(`test_a_blocked_lane_offers_no_original_lane_field` — no original-lane field, no
`import direct_fulfillment` anywhere in the module) and `38-conversational-ai-system/tools/direct_fulfillment.py`
untouched by this branch. Green direction, fixture pending.

**C-F11** — `type: minimal_focused_trace`, scope verbatim:
> "Access failed-step/return/email identity"

**PENDING (no heavy permit, MEMORY RED)** — the F-11 trace fixture was not run. The behaviors are
built and pinned: 39 tests (classes `TestOneMemberAcrossBothChannels`, `TestEmailLaterIsTheSameMember`,
`TestResumeLandsOnTheSameMember`, `shared-utils/bonus/tests/test_access_adapter.py:172,228,260`) and
the production smoke below. Fixture trace belongs to the QC lane.

Production smoke through the call site (targeted, stdlib only):
`access-authorize --member m-1 … --resource authorized` → exactly one dimension authorized, the other
four blocked, `next_action: operator_grant_required`, `automated: false`;
`access-bind` → `access-fail --dimension identity` → `access-defer` → `access-resume --via sms_return`
→ `{"status": "resumed", "resumed_dimensions": ["identity"], "same_member": true}`;
resume over an unbound handle → refused, exit 1.

**This lane does not self-approve.** Every row above needs an independent QC lane; the three PENDING
rows additionally need the focused-trace fixtures under a heavy permit this memory tier does not have.

## 7. Staleness and merges (no stale sha quoted)

Measured immediately before the final report commit, against `origin/main` =
`de85ac2f0f0f5a09cb30e1af0d2db94eaffb7a62` (it moved twice during this run: `dfe9303f7` → `108631851`
→ `de85ac2f0`; `108631851` was current at the first freshness merge):

- after the final freshness merge `c23a00236`: **behind 0 / ahead 18** (`git rev-list --left-right
  --count origin/main...HEAD` → `0	18`); the report commit adds one more to the ahead side.
- Merge history on this branch, all real MERGE commits: `1fd0e65cb` merged main `108631851`
  (clean); `016ec2387` merged `pb/PBB-611/t-14-repair6` (`c6182220`, the T-15 build prerequisite) with
  three conflicts, each resolved and recorded in the commit message: `qc-static.yml` union (main's
  T-22/T-24 steps kept verbatim first, T-14's step verbatim after), `CHANGELOG.md` union (2.0.150
  entry above T-14's 2.0.148 entry), `skill-version.txt` kept main's `v2.0.150` (higher marker);
  `c23a00236` merged main `de85ac2f0` (clean, 11 files, all in `77-council-of-wise-elders`).

## 8. Suite status — honest

**PENDING (no heavy permit, MEMORY RED)** for anything that needs the full suite, an install, a build
or a browser run. None of those was run. Targeted single-file runs only, all re-run after the final
merge:

- `python3 -I shared-utils/bonus/tests/test_access_adapter.py` — **39 tests, OK**, rc 0 (T-15 suite)
- `python3 -I shared-utils/bonus/tests/test_access_capability.py` — **65 tests, OK**, rc 0 (T-14
  regression control; includes the sibling API-shape scan over this deliverable)
- `python3 -I shared-utils/bonus/access_adapter.py` — self-check rc 0
- CLI smoke of the five `access-*` commands — rc 0 / refusal rc 1 as designed
- `python3 -m py_compile 44-convert-and-flow-operator/tools/bonus_access_decision.py` — rc 0

## 9. Commit, push, readbacks, what was not touched

Commits on `pb/PBB-609/t-15-build`: `1fd0e65cb` (merge main), `016ec2387` (merge T-14, resolutions
recorded), `8d60cbd83` (module + suite), `64b6e38e7` (call site + CI step + bookkeeping: CHANGELOG
entry `[2.0.151]` and `38-conversational-ai-system/skill-version.txt` → `v2.0.151`, the repo-mandated
release bookkeeping every task commit carries), `c23a00236` (merge main), and this report
(`evidence/PBB-631/T-15-BUILD.md`). No ledger, census or DECISIONS file was edited. No merge to
`origin/main`, no force-push, no PR. Push and readbacks are recorded in
`control/qc/T-15.<head>.json` beside this report's numbers.

Deliverable summary (returned to the dispatch): verdict PASS (built, QC required); C-15 cleared yes;
branch `pb/PBB-609/t-15-build`; production call sites 0 → 1; workflow files naming the suite 0 → 1
(step count 145 → 146, step index 146); suite PENDING (no heavy permit, MEMORY RED) with 39 + 65
targeted tests green; report `worktrees/PBB-609/evidence/PBB-631/T-15-BUILD.md`.
