# Changelog - 65 Rescue Receiver (65-rescue-receiver)

## [23.4.3] - 2026-09-14 - RR-028 final review: unobservable is not absent

Final independent review before promotion (Worker AD, `RR028-AD-REVIEW.md`)
returned APPROVE-WITH-CONCERNS and found (AD-2) that a NEW unqualified safety
claim added by 23.4.2 was FALSE, plus that the job-destruction class re-entered
through two more doors (AD-1, AD-7), one understated header sentence (AD-4), one
undocumented mirror cost (AD-5), one unguarded `cron rm` in the legacy cleanup
(AD-6), and two untested removal guards (AD-3). All are fixed at the cause; no
existing assertion was weakened, skipped or deleted. The batteries gained 59
assertions (49 -> 55, 46 -> 46, 82 -> 135) and every write path below is pinned
by a new case that fails when its effect is disabled.

- **AD-2 (MEDIUM, pre-existing) — "a job the operator switched off is never
  deleted" was FALSE when the `enabled` bit is unobservable.** When a row for the
  managed name was present and NEITHER view reported its `enabled` bit (the key
  absent, or `"disabled"` carrying a non-boolean such as the string `"true"`),
  the engine reported `enabled_unobservable` and then ran
  `cron edit` -> `cron rm` -> `cron add`: the operator's row was DELETED and
  replaced by a freshly minted ENABLED one, reported `SCHEDULED` with `wire.sh`
  rc 0 (reviewer scenario S). The 23.4.2 `SKILL.md` sentence that
  categorically denied this was therefore a false shipped safety claim — the
  third in this program.
  **Fix — unobservable is not absent, on every mutating rung:**
  * The readback now tracks whether ANY view reported a boolean `enabled` for
    the managed name. When none did, the reconciler REFUSES to edit, replace or
    remove that row: new state `enabled_unobservable`, **rc 8**, nothing
    mutated, nothing claimed — the same fail-closed family as the CLI
    blind-spot refusal, extended to the bit itself.
  * `rrr_cron_removable` now requires the row to have been OBSERVED with
    `enabled=true` as well as shown by the CLI's own listing and never observed
    DISABLED (AD-7: the `cron rm` half).
  * The verdict is a NAMED one: `ENROLLED_PENDING / cron_enabled_unobservable`,
    with the refusal spelled out on the failing surface.
- **AD-1 (MEDIUM, pre-existing) — the store still licensed one mutation and was
  reported `corroborated` without corroboration.** A store row the CLI's own
  listing never showed (scenarios G/G2/Q/Q2) licensed `cron edit <store-only-id>`
  and the report said `cron.store=corroborated` although the CLI had never
  confirmed the row.
  **Fix:** a store row the CLI's own listing does not show, and that is not
  provably contradictory, now makes the store `unconfirmed` — never
  `corroborated` — and is reported as `cron.store_note =
  store_row_omitted_by_cli(id=…)` (a coverage gap, deliberately NOT a
  `disagreement`). Combined with AD-2's guard the store licenses no edit, rm or
  add from such a row.
- **AD-7 (INFO) — closed by the same guard.** A row that is genuinely disabled
  but whose bit no view reports can no longer be `cron rm`'d on any rung
  (dedupe or replace), and the refusal is a named state rather than a silent
  skip.
- **AD-4 (INFO) — the engine header understated the residual.** It claimed a
  lying CLI build is "indistinguishable … by any input this engine has". That is
  wrong when a resolved store contradicts the lying CLI: the engine detects it
  (`store_diverged` / `cli_all_omits_disabled_row(id=…)`, rc 4, nothing
  mutated). The header now says "indistinguishable IN-BAND — by the CLI's own
  answers alone", which is true and is pinned by a new lying-CLI test
  (`RR028_MOCK_LIE_ALL=1` advertises `--all` and hides a disabled job anyway).
- **AD-5 (LOW) — the mirror cost is now documented.** Because only the CLI's own
  listing may corroborate the store, a STALE or EMPTY resolved store reds a box
  that is genuinely scheduled: the CLI shows the one correct ENABLED job, the
  store carries no row for it, `store_missing_row` makes the readback
  `store_diverged`, the box reports `ENROLLED_PENDING /
  cron_source_disagreement` with rc 4, and NOTHING is mutated. Deliberate (a
  store that does not reflect the gateway licenses nothing), and the detail
  names the missing row and the remedy; it is stated here and in the engine
  header so a red roll is not mistaken for a broken box. Pinned by a new test.
- **AD-6 (INFO) — the last unguarded `cron rm` is now guarded.** `wire.sh`'s
  legacy cleanup (`rescue-rangers-poll`) used `cron list --json | grep` plus an
  UNCONDITIONAL `cron rm`: no full-status flag, and no look at the row's
  `enabled` bit. On a build whose DEFAULT listing includes disabled jobs it
  resolved the id of a job the operator had switched OFF and deleted it — the
  same destruction class as AD-2. It now asks the LADDER'S OWN question
  (`rrr_cron_removable` against the engine's two-view readback of the legacy
  name) and removes the row only when the CLI's own listing shows it with an
  observed `enabled=true`; otherwise it leaves it in place and says so. Without
  the engine there is no guarded readback, so no removal is attempted (wire.sh
  and the engine ship together). Pinned by a disabled case, an unobservable
  case, and an enabled control that IS still removed.
- **AD-3 (LOW) — the removal guards are now covered.** New cases drive a
  store-only stray through the dedupe arm (a row the CLI's own listing never
  showed, reviewer mutation `mutF2`'s target), a CLI-visible stray whose enabled
  bit is unobservable (AD-7), and the replace rung with a CLI that cannot edit
  (reviewer mutation `mutK`'s target). `mutK` is CAUGHT by the new replace-rung
  case; `mutF2` is reported honestly as structurally shadowed — see the test
  header: with the AD-1/AD-2 fixes in place, a CLI-invisible row is also
  refused by the enabled-observed guard and (when its bit IS observable) by the
  store-authority gate, so no input isolates that one check. The class it
  protects is pinned by the new cases and by a coarser mutation of the same
  guard, which IS caught.
- **Tests / harness.** `RR028_MOCK_LIST_ALL_DEFAULT=1` models a CLI whose
  DEFAULT listing includes disabled rows (the AD-6 fixture);
  `RR028_MOCK_LIE_ALL=1` models the lying build (advertises `--all`, hides a
  disabled job anyway); `rr028_mutating_argv` reports only MUTATING argv
  vectors, so a "nothing was mutated" assertion can no longer be satisfied or
  broken by the read-only `cron edit --help` probe.

Skill package version 23.4.2 -> 23.4.3. Gates (run serially): `tests/rescue/RR-028`
readiness states **55/0**, safe probe **46/0**, wire reconciliation **135/0**;
RR-027 credential gates 32/0 and 35/0 in BOTH bash and sh legs; RR-005 `FAILS=0`;
RR-016 `FAILS=0`; frontmatter gate PASS; RR-004 12/0; RR-025 39/0; RR-026 47/0.

## [23.4.2] - 2026-09-14 - RR-028 re-review fixes: the store may veto, never license

Independent re-review (Worker Z, `RR028-RE-REVIEW-Z.md`) confirmed both 23.4.1
HIGH fixes hold at the cause and found one MEDIUM hole the M-1 fix did not close
(Z-1), one FALSE claim in the 23.4.1 text (Z-2), one unreachable detail (Z-6),
and two test/harness defects (Z-3, Z-5). All five are fixed here, plus the M-3
limitation is now documented in the shipped artifacts. No test was weakened; the
three batteries gained 34 assertions (43->49, 42->46, 58->82).

- **Z-1 (MEDIUM, pre-existing — NOT a 23.4.1 regression) — a resolved gateway
  store licensed a mutation.** `rrr_cron_readback` upgraded
  `cron.visibility` to `full` whenever a state DB resolved, and the 23.4.1
  refusal guard only fired for `coverage=cli-only`; so on a box whose CLI
  cannot show DISABLED jobs AND whose resolved store does not actually hold the
  operator's job (an alternate/older candidate `ocd_state_db` accepts — it takes
  any readable sqlite with >=1 table), "nothing visible" was read as "absent":
  the ladder ADDED an enabled poller, the readback then saw both rows, and the
  dedupe pass DELETED the operator's disabled job and reported SCHEDULED with
  `wire.sh` rc 0. Identical on the parent revision.
  **Fix — the store may VETO, never LICENSE:**
  * `cron.visibility` is now a CLI fact only. Absence is proven ONLY by the
    CLI's own listing having been asked for a full-status flag and reporting
    nothing (`absent_proven_by_cli`); a resolved store never upgrades it.
  * The store is corroborated against the CLI's own listing for the managed
    name. Contradiction (`cli_hides_enabled_row`, `cli_all_omits_disabled_row`,
    `store_missing_row`) => `cron_source_disagreement`, nothing claimed, nothing
    mutated (rc 4). A store-only row with an unreadable CLI listing =>
    `cron_store_unconfirmed` (rc 3): it may veto, never establish.
  * REMOVAL now needs corroboration: `cron rm` may only touch an id the
    gateway's own listing shows AND that was never observed DISABLED.
    `duplicate_protected` / `replace_protected` (rc 4) refuse instead — this
    also closes the reachable path where a duplicate beside an operator-DISABLED
    job was "deduped" by deleting the operator's job.
  * Vocabulary: the dead `absent` state and the misleading `cli_only_absent`
    are replaced by `absent_proven_by_cli`; `cron.store`
    (`corroborated`/`diverged`/`unconfirmed`/`none`) is reported in the JSON.
  * Cost, stated plainly: a box whose CLI cannot list disabled jobs stays
    unregistered EVEN IF its store resolves, and says so — the remedy is a CLI
    that advertises the flag, never "make the state DB readable".
- **Z-2 — a FALSE safety claim in the 23.4.1 text, corrected in place.** The
  M-1 bullet claimed the refusal was "deliberately independent of whether the
  CLI's help ADVERTISES a full-status flag". The code does the opposite: it asks
  for the flag when the help advertises one and trusts the listing. The 23.4.1
  bullet now carries an explicit correction, and the engine header states the
  real rule and its residual: a CLI that advertises the flag and then hides a
  disabled job anyway is indistinguishable in-band — except when a resolved
  store contradicts it, which is now detected.
- **Z-6 / M-6 — the superseded-receipt detail is now OBSERVABLE.** In 23.4.1 the
  `stale` arm of `rrr_evaluate` substituted a fixed sentence and discarded
  `RRR_RECEIPT_DETAIL`, so "names the file / NEWEST superseded receipt" could not
  be seen anywhere. The stale detail now carries it, and a four-receipt test
  pins both the observable `receipt.at` (newest from the INTENDED runtime) and
  the named file.
- **Z-3 — the M-4 assertion checked the label, not the state.** It asserted only
  `cron.state=`; an empty or hard-coded value passed. It now pins the exact
  state (`readback cron.state=absent_proven_by_cli)`).
- **Z-5 — M-5's pgrep supplement could never fire.** It matched
  `"$WORK/receiver.py"` while every stub lives at `"$WORK/<box>/receiver.py"`, so
  the protection was single-mechanism (the batteries stayed green while 7
  receivers leaked with the registry disabled). The pattern is fixed and a new
  test proves BOTH mechanisms: the registry records both pids, then — with the
  registry neutered at runtime (no code touched) — the supplement alone reaps
  both receivers, 0 survivors. The batteries now honour a pre-exported
  `RR028_PIDFILE`, so a killed-battery run can be reproduced without patching.
- **M-3 honesty (documentation only).** A hand-written receipt is accepted as
  VERIFIED — there is no signing key on the box — and that limitation was
  nowhere in the shipped artifacts. The receipt contract and `SKILL.md` now state
  that a receipt is a plain unauthenticated file (local liveness attestation, not
  tamper-proof), and the VERIFIED detail no longer says a receipt "verified the
  intended runtime"; it says what was actually recorded.

Skill package version 23.4.1 -> 23.4.2. Gates (run serially): `tests/rescue/RR-028`
readiness states **49/0**, safe probe **46/0**, wire reconciliation **82/0**;
RR-027 credential gates 32/0 and 35/0 in BOTH bash and sh legs; RR-005 `FAILS=0`;
RR-016 `FAILS=0`; frontmatter gate PASS; RR-004 12/0; RR-025 39/0; RR-026 47/0.

## [23.4.1] - 2026-09-14 - RR-028 review fixes: fail-closed blind spot + honest exit codes

Independent review (Worker M, `RR028-REVIEW-M.md`) found two HIGH defects in
23.4.0, both reachable from the fleet-wide roll. Both are fixed at the cause;
no existing assertion was weakened (two were corrected because they encoded the
old, wrong behaviour — see below).

- **M-1 (HIGH) — an operator-DISABLED cron was re-enabled and then reported
  SCHEDULED.** The readback has two views: the CLI (`cron list --json`, which
  hides DISABLED jobs on builds with no full-status flag) and the gateway store
  (`cron_jobs.job_json`, the only view that shows them). `RRR_CRON_DISABLED_DIRECT`
  was set ONLY from an observed row, so when the CLI could not show a disabled
  job AND no state DB resolved, the visible set was empty, the ladder took the
  `add` arm, and the reconciler registered a **second, ENABLED** poller beside
  the operator's disabled one — then reported `SCHEDULED`. A later `--all`
  readback makes the box `cron_duplicate`, and the dedupe ladder deletes by
  first match, so the operator's own job could be the one destroyed.
  **Fix:** the engine now tracks and reports READBACK VISIBILITY
  (`cron.visibility` = `full` | `enabled_only` | `unknown`). Under CLI-only
  coverage with `enabled_only` visibility, "nothing visible" is no longer read as
  "absent": the new state `cli_visibility_insufficient` reports
  `ENROLLED_PENDING / cron_state_unverifiable`, and `rrr_cron_reconcile` returns
  a new **rc 8** WITHOUT mutating anything. Fail-closed: a box whose CLI cannot
  list disabled jobs and whose state DB is unreadable stays unregistered (and
  says so) instead of risking the operator's job.
  **CORRECTION (23.4.2, re-review Z-2 — the following sentence was FALSE as
  shipped here):** this bullet used to claim *"This is deliberately independent
  of whether the CLI's help ADVERTISES a full-status flag — advertising is not
  proof the flag works, and the whole point is that a hidden disabled job is
  never guessed away."* The code does the opposite: visibility is `full` exactly
  when the CLI's help advertises `--all` / `--include-disabled` /
  `--show-disabled`, the CLI IS then asked for that flag, and its listing IS
  trusted — advertising is taken as the proof. A hidden disabled job is still
  guessed away when a CLI advertises a flag it does not honour and nothing
  contradicts it. The other false half — that a resolved gateway store proves
  an absence — was removed in 23.4.2 (Z-1). The engine header now states the
  real rule and this residual.
- **M-2 (HIGH) — `wire.sh` exited 0 when its OWN readback failed.** Only
  reconcile rc 5/7 mapped to 1; rc 3 (readback unavailable) and rc 4 (desired job
  NOT proven, including `add_not_read_back`) fell through to `exit 0`, so
  `update-skills.sh` printed `✓ enrollment/cron reconciliation ran` over a box
  with NO cron at all. **Fix:** explicit mapping with no fall-through — 3/4/5/7
  (and any unexpected code) exit 1; rc 6 (tombstoned / disabled by owner) and
  rc 8 (fail-closed refusal) are DELIBERATELY 0, because in both the engine
  attempted no mutation and claims nothing, and neither is a wiring failure that
  a retry could fix. A genuinely un-enrolled or missing-secrets box still exits 0
  with zero CLI calls (RR-027 contract preserved; no pre-existing `exit 1`
  became `exit 0`).
- **M-4 (LOW)** — the probe printed "safe test claim verified in the intended
  runtime" even on a box with NO cron. The verdict was right; the line was not.
  It now says exactly what was verified (the receiver's transport-OK, structured,
  no-work, zero-turn/zero-ack ANSWER) and prints the schedule readback state, so
  it can no longer be grepped as "this box is ready".
- **M-5 (LOW, test harness)** — the batteries' EXIT trap was gated on
  `RR028_DONE` and tracked only the LAST receiver pid, so a battery killed
  mid-run leaked every receiver it had started (24 orphans were found alive on
  the review host; they caused a 41/2 flake). Every spawned pid is now recorded
  in a per-battery registry that the trap reads on EXIT/INT/TERM, with a bounded
  `pgrep` supplement; `RR028_DONE` no longer decides whether to reap.
- **M-6 (INFO)** — with several superseded receipts on a box, the stale-receipt
  detail named the first one in glob order, so its digest/at could belong to an
  unrelated receipt. It now reports the NEWEST superseded receipt from the
  INTENDED runtime, names the file, and says other superseded receipts may exist.
  **NOTE (23.4.2, re-review Z-6):** as shipped in 23.4.1 this bullet overstated —
  the `stale)` arm substituted a fixed sentence and DISCARDED that detail, so
  "names the file" was observable nowhere. 23.4.2 appends the detail to the
  stale verdict and pins it with a test.

Test-fixture corrections (each one ENCODED the old, wrong behaviour; every
assertion is kept or strengthened, none weakened):
- `test_wire_install_vs_ready.sh` asserted `wire.sh` rc 0 for a silent add
  (`add_not_read_back`). That is the M-2 defect stated as a requirement; it now
  asserts a NON-ZERO rc with a readable reason, keeping the original readback
  assertions unchanged, and adds the reviewer-requested blind-spot case
  (`RR028_MOCK_NO_ALL=1` with NO state DB, driven through `--reconcile`) plus two
  controls (readable DB → `cron_disabled_by_owner`; a fully read-back
  reconciliation → exit 0).
- the mock CLI's `cron list --help` advertised `--all` while its list HID
  disabled jobs under `RR028_MOCK_NO_ALL=1` — a CLI lying about itself. The two
  are now consistent, so the fixture genuinely exercises the blind spot the
  engine's fail-closed rule exists for.

Skill package version 23.4.0 -> 23.4.1. Gates: `tests/rescue/RR-028`
(readiness states 43 assertions, safe probe 35, wire reconciliation 58), plus
RR-027 credential gates, RR-005, RR-016, RR-004, RR-025 and RR-026 re-run green.
**CORRECTION (23.4.2):** the safe-probe count above was stale — as shipped in
23.4.1 that battery reports **42/0** (the M-4 success-line assertions were added
without updating this line).

## [23.4.0] - 2026-09-13 - RR-028 enrollment + cron reconciliation report REAL readiness

RR-W4-INSTALL. Enrollment and cron status were PROSE. `UNENROLLED` existed only
as a comment inside `wire.sh`; the four-state vocabulary did not exist anywhere
in this repo. A job registered with a stale poll path, the wrong cadence, or
client-facing delivery left ON was indistinguishable from a correct one,
because presence was decided by `cron list --json | grep '"name": ..."'` — a
text match that proves nothing about the job. And nothing separated "files were
installed" (the installer's claim) from "the receiver is READY" (a claim about
the intended runtime).

New engine `shared-utils/rr-readiness.sh` + operator surface
`65-rescue-receiver/rr-readiness.sh`:

- **Four explicit states with explicit reasons** — `UNENROLLED`,
  `ENROLLED_PENDING`, `SCHEDULED`, `VERIFIED`; every outcome carries a
  machine-readable reason code and a detail that names NAMES, never values.
  Anything unproven is `ENROLLED_PENDING` naming exactly what is missing.
- **Version-independent** — no input to reconciliation is a software version.
  A `.wired-<version>` sentinel says "files were copied"; it is never evidence
  that a cron exists. `update-skills.sh` now runs this skill's reconciler on
  every pass, BEFORE the sentinel gate, so a cron an operator removed is
  repaired on the next roll instead of waiting for a version bump.
- **Keyed by a desired-config digest** — name, schedule, command, enabled bit,
  delivery mode, slug, URL and a SALTED token commitment (the token itself is
  never printed, logged or exported). A verified receipt is keyed by that
  digest AND by the runtime, so a changed desired config or a probe taken in a
  different runtime can never inherit an old verdict.
- **All required resolutions** — slug, token and URL from the store, plus the
  parser, curl, base64, the OpenClaw CLI and node. Anything unresolved is
  reported by name.
- **Readback, never assume** — two views (`cron list --json` and the gateway's
  stored `cron_jobs.job_json`, the only one that shows a DISABLED job);
  duplicates collapsed, command / schedule / enabled / delivery compared and
  repaired (`cron edit` in place, else replace), with a FRESH readback after
  every write. An operator-disabled cron or a tombstone is never resurrected.
- **argv-safe** — every external command runs as an argv vector; no eval, no
  `sh -c`, no string re-splitting. The host/container identity comes from
  `shared-utils/oc-env-descriptor.sh`.
- **Installer success != ready** — `wire.sh` exit 0 means files installed and
  now prints `files-installed=1` plus the readiness line. `VERIFIED` requires a
  receipt from a capacity-0 `dry_run` probe that starts no agent turn, acks
  nothing, and is refused outright if the receiver hands it an instruction.

Skill package version 23.3.0 -> 23.4.0. Gates: `tests/rescue/RR-028`
(readiness states 43 assertions, safe probe 35, wire reconciliation 42), plus
RR-027 credential gates, RR-004, RR-015, RR-025 and RR-026 re-run green.

## [23.3.0] - 2026-09-10 - RR-025 claim envelope identity + RR-026 process/lock supervision (RECEIVER_VERSION 1.6.0)

RR-W3-RECEIVER. Two defect classes, both of which let the poller be *wrong* on a
live box rather than merely unavailable.

**RR-025 — the claim envelope had no identity, so a claim could not be tied to
the work it authorized.** A claim is now validated as a TYPED envelope against
the SPEC's canonical tuple (company, runtime, incident, attempt) plus the
instruction, session, capability, lease and schema members. Every member is
presence-checked and (when a JSON type reader is available) type-checked, so a
mistyped `lease_seconds` or a stringified `attempt_generation` is refused
instead of silently coerced. Identity is hashed over a LENGTH-PREFIXED encoding,
so `company="a/b"` and `company="a_b"` — or a shift at a member boundary — can no
longer collide into the same identity. An unknown `agent_id` is a ROUTING
decision: the local roster is read and the capability must actually exist, with
a recorded substitution when a declared fallback is used and an explicit refusal
when none is. A refused claim sends NO verdict ack (a verdict about a turn that
never ran would be a lie); it is recorded structurally with the member, reason
and taxonomy, the ticket stays non-terminal, and the next owner is named.

**Compatible by design**: the deployed RR-07 does not send `attempt_id`,
`attempt_generation` or `lease_expires_at`, so the attempt member is DERIVED
(server value when present, else the session-key retry suffix, else `a0` for a
first handout) rather than hard-required — a hard requirement would have
rejected every claim on every live box.

**RR-026 — the poller's only bound was a stale constant, and its lock was
age-based.** v1.5.0 delegated its entire deadline to the CLI's own
`--timeout 600`; a CLI that ignores or mis-parses the flag hangs forever, and a
child that forks a grandchild leaves the grandchild running after the direct
child is signalled. And the lock was an age-only `mkdir` ("older than 20 minutes
is stale") — age is not ownership, so a still-running previous poll could have
its lock removed underneath it and a recycled PID looked like the original
owner. Neither was provable from the shell: `exit 0` after a kill is not proof
that anything exited.

Now a shared runtime adapter (`shared-utils/rescue-supervise.py`, stdlib,
Python 3.6+, Mac and Linux) supervises the turn in its own process group under
ONE monotonic budget measured from the claim and covering discovery, the model
turn, the unknown-agent fallback and the ACK margin. It TERMs the group, waits a
grace window, KILLs the group, reaps, and VERIFIES the group is gone — a killed
child is never read as a delivery. The lease the SERVER granted (900s live) is
the deadline; the 600 is only a per-turn cap. If discovery has already eaten the
window the poll STOPS without starting a turn, so RR-07 cannot re-hand a ticket
to a second poller while the first is still delivering.

The lock is now a RECORD, not a directory marker: owner token, the owning
process's START identity (so a recycled PID is reconciled as reused, never
mistaken for a live owner), the shared target/resource fence fields
(`target_key`, `generation`, `attempt_id`, `operation_id`) and the lease
deadline. A genuinely RUNNING incumbent is refused outright however old its
record is — age is deliberately never consulted. A lapsed record is not free
either: takeover requires `allowTakeover` + the observed generation + a note,
per the shared fence contract, and a stale owner can never release a newer
holder's lock.

Fail-closed must not be fail-SILENT: a missing supervisor or an unusable lock
subsystem is RECORDED (`state/rr-receiver/rejected/degraded-*.json`), logged
with `next_owner=operator`, and returned as rc=2 — distinct from contention,
which stays quiet because it is normal. Folding the two together was how a box
went silently dark: every fire exited 0 having done nothing, forever, with no
trace. Timeout and cancellation outcomes are persisted with the next owner.

Skill package version 23.2.0 -> 23.3.0. Gates: `tests/rescue/RR-025` (claim
envelope, 39 assertions), `tests/rescue/RR-026` (process-group supervision,
lock fencing, lease budget, 47 assertions), plus RR-004 and the RR-027
credential gate re-run green.

## [23.2.0] - 2026-09-09 - RR-027 keep rescue credentials out of worker environments (RECEIVER_VERSION 1.5.0)

RR-W3-INSTALL RR-027. The secret store is PARSED, not executed: the shared
dotenv parser (`shared-utils/rescue-env.sh`) reads ONLY the three required
rescue values — no `.` sourcing of the store (arbitrary shell semantics gone),
no expansion of `$` inside values, quoting/space behavior preserved, malformed
lines FAIL VISIBLY (file + line + shape on stderr; values never printed).
Child-env scrub: every child (agent turn, default-agent probe) runs with the
rescue credential aliases REMOVED from its environment, so a synthetic
`export RR_BOX_TOKEN` from any upstream env file can no longer reach the child
agent (the CONFIRMED RCV05 leak); necessary authorized model/tool credentials
pass through untouched. Agent stderr is reduced to a failure CLASS (never
logged verbatim) so a stack-trace env echo cannot leak a credential into the
poll log. wire.sh no longer exports the store (`set -a; . file` removed) —
enrollment values are existence-checked then dropped, and the cron command
carries no credential. Skill package version 23.1.0 -> 23.2.0.

## [23.1.0] - 2026-09-09 - RR-004 additive lease/attempt fields (RECEIVER_VERSION 1.4.0)

RR-W2-CORE RR-004 pairing. ADDITIVE ONLY, no behavior change: the claim
response's new `attempt_id` / `attempt_generation` / `lease_expires_at` fields
are parsed and echoed verbatim on every ack, so the server can fence
acknowledgments against the current lease owner (rejecting stale generations,
expired leases and replaced owners). Fields are omitted when the server does
not send them (pre-RR-004 servers unaffected). Strict enforcement arrives
later, only after the additive server contract is confirmed fleet-wide
(SPEC shared rollout contract). Skill package version 23.0.0 -> 23.1.0.

## [23.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
