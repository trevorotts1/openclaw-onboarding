# Trevor's RATIFIED DECISIONS — 2026-07-16

**Purpose:** this file is the permanent, durable record of decisions Trevor made on 2026-07-16 about the Skill 6 (blended-persona-kanban v2, 117-unit) build. It exists so **no agent ever re-litigates, re-asks, or re-opens any item below.** Where a decision here conflicts with older text in the master spec (`Downloads/skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md`) or the ledger's older evidence prose, **this file wins** — the master spec is NOT edited in place (it is a 552KB historical planning document; edits belong here and in the live ledger rows instead, per standing digest-first doctrine).

Glossary for anyone new to this build: **"U`<n>`"** = Unit `<n>` of the 117-unit Skill 6 decomposition (e.g. "U65" = Unit 65). **"D`<n>`"** = Decision `<n>` in the master spec's decision register (spec section E.3 / the "Other RATIFIED / BINDING decisions" list). **ONB** = the `trevorotts1/openclaw-onboarding` repo. **CC** = the `trevorotts1/blackceo-command-center` repo.

---

## D-U65 — Unit 65 is CLOSED / WON'T-DO, PERMANENTLY

**Trevor's ruling:** the plaintext Podbean OAuth `client_id`/`client_secret` in the live n8n Code nodes `BqRLOn8TP1wPaAzn` (`Podbean - GET CLIENT CHANNEL ID`) and `COfgxe6HXRcWOleV` (`Podbean Channel IDs to Google Doc`) **STAY in plaintext.** This is not "deferred" and not "accepted-risk-for-now" — it is **decided and closed.**

**Action taken:**
- `ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`, U65 row — status changed from `deferred (operator-gated)` to `closed / won't-do (PERMANENT — Trevor-ratified 2026-07-16)`; old evidence preserved verbatim inline for the audit trail; new evidence records this ruling.
- U65 removed from every open-risk / "waiting on Trevor" list in the Skill-6 tracking docs (see the Downloads-doc changes logged at the bottom of this file).
- **Standing instruction to every future agent:** treat `BqRLOn8TP1wPaAzn` and `COfgxe6HXRcWOleV` as **NEVER-PRINT, NEVER-VAULT, NEVER-ROTATE** workflows. Do not propose vaulting. Do not flag the plaintext secret as a finding. Do not re-open U65. This is closed.

---

## D-U74 — Unit 74 is UNBLOCKED / BUILDABLE

**Trevor's ruling (derived directly from D-U65 above):** U74's only blocker was the E.2 Ordering-rule collision note "U65 and U74 touch the same live workflow — serialize." Because U65 is now permanently closed (no further live-writer activity on that workflow will ever occur under U65), that serialization constraint no longer exists.

**Action taken:**
- U74 is marked **buildable** — no unit-level blocker remains. (U74's own unit spec still asks-and-answers its co-located decision GK-D4 — "which podcast pipeline is canonical" — as the first act of the unit's own build, per its spec's own "Deps: GK-D4 asked and answered BEFORE the run starts" language; that is normal in-unit build work, not an external blocker, and does not prevent dispatch.)
- U74's ledger row (`ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`) remains `pending` — accurate, since no build work has started; only the blocking constraint is lifted.
- Downstream cascade also recorded: **U73** ("Resolve the `Anthology Writer - Ben` monolith") was blocked on U64; since U64 is now `verified` (see D-U64 below), U73's prerequisite is satisfied and U73 is also unblocked/buildable. **U72** ("Remove the leftover live gate-test workflow") was blocked on U63 as an "excluded" unit; U63 is now `AUTHORIZED` (see D-U63 below) rather than indefinitely excluded — U72 remains blocked on U63's actual completion (a normal dependency wait, not an operator-gate exclusion) and is reframed accordingly in the tracking docs, not marked buildable.

---

## D-U64 — Unit 64 is CLOSED / VERIFIED

**Trevor's ruling:** Trevor accepted the functional proof already on record — broker `S8E6c41WfB8fAGiL` active, stub `F2X3SxZVhWRDxHOV` inactive, all 6 documented actions live-exercised across 10 real executions, all `status=success`. The previously-missing `kubectl` environment-variable read is **NOT a defect** — the token check and root-folder resolution provably read those variables on every successful live run (a missing/unset var would have 500'd `broker_misconfigured` or 401-rejected the call; neither happened, 10/10 times), which is direct functional proof the variables are SET and READABLE by the live process.

**Action taken:**
- `ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`, U64 row — status changed from `partial (env cluster-access unconfirmed via kubectl — live-proven functionally)` to `verified (Trevor-ratified 2026-07-16)`; original evidence preserved verbatim inline; new evidence records this reasoning.
- U64 removed from every "waiting on Trevor" / EXCLUDED list; moved to the MERGED/DONE bucket in the Downloads tracking docs.
- U73 is a downstream unblock of this decision (see D-U74 section above).

---

## D20 — RATIFIED = Option B (governs Unit 93)

**Where D20 lives:** the master spec's Section X.1.4 (crosswalked into `U93`'s own spec text as decision item "D-X1 (= master D20)"). Prior state: D20 was explicitly on the NOT-ratified list.

**Trevor's ruling:** **D20 = Option B**, split in two exactly as the spec's own recommendation described:
1. The doctrine-text scrub + CI guard (Option A's scope) — **already shipped as U92** (verified, QC 9.4, tag v20.0.40).
2. **PLUS** the file renames — the two remaining ONB files (`32-command-center-setup/scripts/heartbeat-canary-probe.py`, `scripts/loop-protection-canary.sh`), the live doctrine text (Skill 60/61 "law 8" wording, `HEARTBEAT.md` prose), and the two Command-Center comment-level occurrences (`migrations.ts:1522`, `gate-engine.ts:146`) — **with compatibility shims at the old paths for one release.** This is U93's own scope exactly as already drafted in its spec slice; U30 separately owns the four Skill-6-named files (unchanged, no double-rename).

**Action taken:**
- D20 recorded here as **RATIFIED = Option B.**
- **U93 is now buildable** — its decision gate is removed. U93's `deps:` become just "merged U92" (already true — U92 shipped, tag v20.0.40), no outstanding decision blocker.
- Downloads tracking docs' `U93 *(D20 open)*` annotations are corrected to drop the `(D20 open)` marker.

---

## D-U22 — Live run AUTHORIZED

**Trevor's ruling:** "Trevor's box is available; the capstone live tier is a go." U22's OFFLINE/CODE-MERGE tier is already merged both repos (ONB v20.0.35 / CC v6.0.20); the LIVE-PROOF tier (the one end-to-end operator-box run) is now authorized to execute.

**Action taken:** recorded as **AUTHORIZED** here. The actual live run and its ledger/evidence update are executed by a separate agent in this same work session — this file does not claim the live tier complete; only that Trevor's go-ahead is now on record and the item is no longer an open question for the operator.

---

## D-U26 — Activation AUTHORIZED

**Trevor's ruling:** turn the feature flag on. U26 (`runQCOnReview` QC-contract fix) has been code-`verified`/merged since 2026-07-13 (CC v6.0.3, QC 8.8); the previously-open question ("what live leg, if any, is owed") is now answered: activate the flag, operator-box only, explicitly NOT fleet-wide.

**Action taken:** recorded as **AUTHORIZED** here. Flag activation is executed by a separate agent in this same work session.

---

## D-U63 — Live publish AUTHORIZED

**Trevor's ruling:** operator-generated cover art + delivery email `trevor@blackceo.com`. This satisfies precondition (1) of U63's own two-branch operator gate ("real client-approved cover art for the episode image ... AND a verified ... email address for delivery") using Trevor's own operator-generated art and his own email as the authorized substitute — the live podcast-publish retry (image_url-null fix + fail-closed entry guard) may now proceed.

**Action taken:** recorded as **AUTHORIZED** here. The live retry itself is executed by a separate agent in this same work session; this file records only that the operator gate is now satisfied and the item is no longer a blocked "waiting on Trevor" question.

---

## FLEET-ROLL / P4 / U84-fleet-leg — REMOVED AS A COMPLETION BLOCKER

**Trevor's exact words:** *"I'm not fleet rolling stuff until we get all this shit done… I determine when the fleet gets rolled. Don't put that fucking fleet roll back in that spec document ever again."*

**Ruling, precisely:** the batched fleet roll (Phase P4 of the master spec's phasing, and the fleet-roll leg of U84 specifically) is **NOT a gate on completing Skill 6.** It must **never appear as a blocker, dependency, or "waiting-on" item** anywhere in the Skill-6 tracking artifacts. It is recorded **only** as a separate, operator-timed phase that Trevor alone schedules — it gates nothing else, and nothing else gates it.

**Action taken:**
- Every "waiting on Trevor" / EXCLUDED / BLOCKED list in the Downloads tracking docs (`skill6-SESSION-LOG-and-CHECKLIST.md`, `skill6-HANDOFF-2026-07-16.md`, `skill6-blended-persona-kanban-MGMT-DASHBOARD-2026-07-16.md`) has had the fleet roll / P4 / "U84 fleet leg" entries reframed from **blocker** language to a plain **"separate operator-timed phase — Trevor decides when, not a gate on anything else"** note.
- `ledgers/recovery-state.md` and the live ledger were checked — neither lists the fleet roll as a per-unit `deps:` blocker on any of the 117 units (U84's own row already correctly scopes `verified` to its operator-box leg only, with the fleet-roll leg named as a separate deferred sub-step, not a blocking dependency of U84's own status — this was already correctly scoped and needed no ledger-row edit).
- **U84 the unit is NOT deleted or altered** — its operator-box leg remains `verified` exactly as before. Only the framing of its fleet-roll leg (in the Downloads prose, never in a way that blocked anything) is corrected to match Trevor's instruction that it never reads as a blocker.
- No agent may reintroduce fleet-roll language as a blocker/dependency/gate in any Skill-6 tracking artifact going forward. Fleet timing is Trevor's alone, decided separately, at the time of his choosing.

---

## D12 (D-HL-3) — RATIFIED = crown `update.sh` as the ONE Command Center update executor

**What this decides, in plain English:** the Command Center (the web dashboard) can update itself from GitHub. Two separate pieces of code were each able to update the same copy of it — the Command Center's own `update.sh`, and the onboarding repo's Skill-32 refresh path. Two independent updaters racing on one checkout is exactly how you get a half-updated app that still reports success. This decision names exactly ONE of them as the only code allowed to do the updating.

**Ruling: `update.sh` is crowned.** With `CC_APP_DIR` pinned by the caller, it is the ONLY path permitted to mutate a Command Center checkout during any update or fleet roll. The onboarding repo's Skill-32 refresh path and the Sunday update-check cron both route through it.

**Why this, and not the alternative — decided from the code, not from the spec's prose:**

- `update.sh` already embeds the contract that makes a bad deploy fail loudly instead of silently: it routes the rebuild through `scripts/atomic-deploy.sh` and reads its exit codes explicitly (`update.sh:182-188` — `0` green / `1` rolled-back / `2` pre-flight-failed / `3` health-indeterminate). The competing path has no such contract, and the master spec itself records its internals as UNVERIFIED.
- The code in BOTH repos **already implements this ruling**, and is already regression-locked against drifting back:
  - `32-command-center-setup/scripts/run-full-install.sh:884` — `if CC_APP_DIR="$DASHBOARD_DIR" CC_PORT="$DASHBOARD_PORT" bash "$update_sh" >>"$LOG_FILE" 2>&1; then` — tier 1 delegates to the freshly-pulled Command Center's own `update.sh` with `CC_APP_DIR` pinned. That is D-HL-3's recommendation verbatim.
  - `.github/workflows/u53-crown-executor-single-path-guard.yml` — fails the build if either of `update-skills.sh`'s D5 call sites, or `run-full-install.sh`'s Phase 6, ever regresses into inlining its own npm/pm2/git mutation instead of delegating.
  - **Independently re-proven this pass** by running the probe against `origin/main` (not taken from the spec, not taken from a sub-agent claim): `tests/probe/test-u53-hl-u68-crown-executor-single-path.sh` → `Passed: 10   Failed: 0`, including the assertions *"D5 section contains ZERO direct npm/pm2/git mutation calls"* and *"tier 1 invokes update.sh with CC_APP_DIR (+ CC_PORT) pinned to the freshly-pulled checkout — matches D-HL-3's ruling verbatim"*.
- Crowning the other path instead would mean deleting a shipped CI guard, a passing 10-assertion probe, and the atomic-deploy exit-code contract — in order to adopt a path whose internals were never verified. There is no engineering case for it.

**Ratifying therefore costs zero code churn:** it makes the decision register match what is already shipped, guarded, and proven.

**Effect on Unit 53 (the self-updater unit):** its decision gate is REMOVED. Its code legs are merged in both repos (CC `c8086c7` on `origin/main`, near tag v6.0.36; ONB merged via `7b0e3a1b`, tag v20.0.57). Its remaining live leg is addressed immediately below.

---

## U53's live "prove the loop" run — NOT RUN this pass; blocked by CODE, not by a decision

Unit 53's acceptance criteria (a)-(c) are **PROVEN this pass, offline, on `origin/main` code**. Criterion (d) — the live proof run — is **BLOCKED by two newly-found code defects** that the proof attempt itself surfaced. This is recorded so no future agent re-asks the operator for a green light he has already effectively given: **the operator is not the blocker here; the code is.**

**Proven this pass (quoted, reproducible):**

- **(a) canonical-path detection — PASS.** Against a simulated canonical-layout box (sandboxed `HOME`), the fixed `check-updates.sh` returns `"install_dir": ".../projects/command-center"`, `"local_version": "v6.0.39"`, `"has_update": false` at HEAD. Negative control on the pre-fix script (`c8086c7^`), same fixture: `"install_dir": ""`, `"has_update": true` — the permanent false "update available" the unit set out to kill. The fix is what closes it.
- **(b) `CC_APP_DIR` override — PASS.** Pinned to a non-standard path, the fixed script targets it and writes its `.last-update-check` stamp there. The pre-fix script ignores `CC_APP_DIR` entirely (`install_dir=''`).
- **(c) AGENTS.md single-section — PASS.** Driving the merged `update.sh` Step-7 block (lines 279-304, extracted verbatim) three times over a fixture: `headers=1 bodies=1`, only the latest bump retained, stale prior bodies removed, and pre-existing operator content preserved.

**Blast radius of the live run — assessed honestly, read-only:**

- **It CANNOT reach a client box. Verified, not assumed:** neither `update.sh` (322 lines) nor `scripts/atomic-deploy.sh` (740 lines) contains a single remote-reach primitive (`ssh`/`scp`/`rsync`/remote-host iteration) in any executable line. `update.sh`'s only network egress is `git fetch origin main` to GitHub (line 102); every other call is localhost. Blast radius = the one box it runs on. **This is not a fleet risk.**
- **But the operator's own box is not the box this unit's code assumes.** The live Command Center runs from `~/command-center/app` under pm2 app `cc-prod` — a path matching **none** of `update.sh`'s six candidate layouts. Proven: a bare `check-updates.sh` run on this box today still returns `"install_dir": ""`, `"has_update": true` **even with the U53 fix merged**. The fix is correct but not sufficient here; this box needs `CC_APP_DIR` pinned.

**DEFECT 1 (new, blocks criterion (d)) — the pm2 app name is not overridable.** `update.sh:160` is a bare `CC_PM2_NAME="blackceo-command-center"` — unlike `CC_APP_DIR` (`update.sh:28`, `${CC_APP_DIR:-}`) and `CC_PORT` (`update.sh:175`, `${CC_PORT:-}`), which ARE env-overridable. The operator's live pm2 app is `cc-prod` (its own config file states: *"The operator's local Command Center runs under the pm2 app name `cc-prod`"*), while the repo's `ecosystem.config.cjs` declares `blackceo-command-center` the *"FLEET-CANONICAL PM2 APP NAME"*. So `update.sh` can be pointed at the right directory but never at the right process. This is the same defect class U53 already fixed for the install path, one field over.

**DEFECT 2 (new, more serious) — `atomic-deploy.sh`'s "zombie" killer selects by name keyword, never by port.** Lines 384-422 delete every pm2 app whose name contains `mission-control`, `command-center`, or `blackceo` and is not the canonical name. The comment calls these *"zombies that could fight for the port"*, but the selector **binds `port_str = sys.argv[2]` and never uses it** — it never checks port contention at all. Dry-running that exact selector verbatim against this box's live pm2 list (read-only, nothing killed) proves the consequence:

```
  canonical (what update.sh passes) = 'blackceo-command-center'
    cc-prod                          -> no CC keyword, LEFT RUNNING
    blackceo-cc-demo-interview       -> *** WOULD BE pm2 delete`d as a zombie ***
    blackceo-cc-demo-dashboard       -> *** WOULD BE pm2 delete`d as a zombie ***
  WOULD DELETE: ['blackceo-cc-demo-interview', 'blackceo-cc-demo-dashboard']
  canonical 'blackceo-command-center' present in pm2? False
```

So a live run today would: delete the two running demo processes; leave `cc-prod` running while `.next` is atomically swapped underneath it; then, finding no canonical app, `pm2 start` a **duplicate** `blackceo-command-center` fighting `cc-prod` for port 4000. Note this defect is **not** fixed by Defect 1 alone — with `CC_PM2_NAME=cc-prod` the two `blackceo-*` demo apps still match the keyword and still get deleted.

**Reversibility — the honest split:**

- **Code: reversible.** Live checkout `cdfc9090` (v6.0.25) is a clean fast-forward ancestor of `origin/main` (72 commits behind); revert path = `git -C ~/command-center/app reset --hard cdfc9090`, plus the pre-update backup dir `update.sh` prints each run. The untracked `ecosystem.cc-prod.config.cjs` survives (`reset --hard` does not touch untracked files).
- **Database: NOT reversible by the updater.** `update.sh`'s backup step (lines 79-87) copies `version`, `package.json`, `package-lock.json`, `CHANGELOG.md`, `ecosystem.config.cjs`, `src/`, and `config/` — **it does not back up the database.** Migrations run automatically and forward-only on app start. The live board currently has 102 migrations applied (highest `105`) and is serving `HTTP 200 / status: ok` right now.
  - *Mitigating fact found this pass:* `git diff cdfc9090 origin/main -- src/lib/db/migrations.ts` is **empty** — the migration file is unchanged across the entire v6.0.25 → v6.0.39 span, so this specific upgrade would apply **no new migrations**. The missing-DB-backup gap is real and should be fixed, but it is not what blocks this particular run.

**Conclusion recorded:** the run is operator-box-only and its code leg is reversible, but it would knock over the operator's currently-green Command Center and both demo surfaces via Defects 1 and 2. It is therefore **not run**. Fixing Defect 2 changes the behaviour of the deploy script that executes on **every** box during a fleet roll — that is a scoped build unit with its own quality-control gate, deliberately NOT freelanced here.

**Standing instruction to future agents:** do not re-ask the operator to green-light this run. D12 is ratified (above); the live tier is gated on Defects 1 and 2 being fixed, which is ordinary build work. Do not run `update.sh` against `~/command-center/app` until then.

---

## D4 (D-A4) — RATIFIED = Option A (additive section-map crosswalk)

**What this decides, in plain English:** the 99 persona "blueprint" documents were written in two different template generations. In one generation "Section 4" means *Key Principles*; in the other it means *Agent Governance Framework*. The instruction that tells a worker which part of a persona to read says "Internalize Section 4" — so the same instruction was loading **semantically different material** depending on which generation a persona happened to be written under. That silently degrades voice quality. This decision picks how to fix it: (A) ship an additive map that resolves the right section per generation, leaving the documents untouched; (B) rewrite all 67 legacy blueprints into the modern template; or (C) do nothing.

**Ruling: Option A** — the spec's own recommendation, and the option that already shipped.

**This decision is closed as ratify-the-default, and the record should be honest about why that is costless rather than claiming the options were equivalent.** They are not equivalent — Option B would require a materially different and vastly larger diff (a rewrite pass over 67+ blueprint files, 67 individually quality-controlled synthesis runs, and a real risk of perturbing Coaching-Mode behaviour clients already depend on). But Option A is already built, merged, and proven, so ratifying it costs nothing and reversing to Option B would mean deleting working, tested, CI-guarded code to buy churn. Unit 14 (A-U14) shipped Option A explicitly — its merge commit `c6f865fe` names it: *"blueprint-generation reconciliation (D-A4 Option A)"*.

**Proven this pass, independently (test executed against `origin/main`, not quoted from a sub-agent):**

- `python3 tests/unit/u14-blueprint-section-map.test.py` → **`Ran 18 tests` … `OK`**, including `test_total_is_99`, `test_every_blueprint_on_disk_has_a_map_entry`, `test_map_has_no_stale_entries`, `test_governance_section_resolves_for_98_of_99`, `test_four_em_dash_blueprints_inventoried_and_resolved`, and `test_committed_map_matches_generator_output` (a drift lock that fails the build if the committed map is hand-edited out of sync with the blueprints on disk).
- The map is at `22-book-to-persona-coaching-leadership-system/personas/_section-map.json` (2394 lines), covering **99/99** blueprints — an exact 1:1 set match with the persona directories on disk. `_meta` records `"decision": "D-A4 Option A (additive section-map crosswalk, ratified)"` and `template_counts: {"B": 71, "A": 28}`.
- **Option A is confirmed by absence of churn:** the U14 merge `c6f865fe` touched 6 files (`_section-map.json`, its generator, its test, a CI guard, `shared-utils/persona_for_job.py`, and Skill 23's `CHANGELOG.md`) — and **zero** `persona-blueprint.md` files. The 67 legacy blueprints were not rewritten. That is Option A by construction, and rules out B and C.
- The Section-4 hazard is resolved on the consumer side in `shared-utils/persona_for_job.py`: `_governance_section_number()` reads the map's `governance_section` per persona, and `section4_excerpt()` resolves the correct section per generation, keeping the old field name for consumer back-compat and falling back to the literal pre-U14 `## Section 4` grab when no map entry exists (additive and revertable, exactly as Option A promised).
- Skill 23's CHANGELOG backfill (the unit's third leg) is proven by the same suite: `test_persona_blend_named`, `test_w7_named`, `test_p4_01_named`, `test_p4_02_named` all pass.

**Two honest caveats recorded rather than smoothed over:**
1. The map classifies the 4 "off-template" blueprints as structurally template `B` (71 = 67 hyphen + 4 em-dash) by structural detection rather than title text, so the spec's "4 blueprints match neither" finding is *inventoried and resolved*, not left as a fifth bucket. A test pins this explicitly.
2. Coverage of the governance section is **98/99**, not 99/99: `butow-ultimate-guide-social-media-marketing` has `governance_section: null` because that blueprint genuinely has no A-D governance subsections. This is a documented edge case with an honest fallback — not a silent gap — and is pinned by `test_governance_section_resolves_for_98_of_99`.

**Effect:** D4's gate is removed. Unit 14 stays `verified` (merged `c6f865fe`, tag v20.0.51). No code change follows from this ruling.

---

## Net effect on the "buildable now" set

- **U65:** CLOSED (terminal state — not buildable, not pending; done).
- **U64:** VERIFIED (terminal state — done).
- **U74:** now BUILDABLE (blocker removed).
- **U73:** now BUILDABLE (downstream unblock — its blocker U64 is verified).
- **U93:** now BUILDABLE (decision gate D20 removed; only dep is already-merged U92).
- **U72:** still blocked on U63's actual completion — reframed from "operator-gated exclusion" to a normal pending-dependency wait, since U63 is authorized (not excluded) as of this ruling.
- **U22, U26, U63 live/activation legs:** AUTHORIZED — execution and evidence tracked by separate agents in this session, not claimed complete by this file.
- **Fleet roll / P4 / U84 fleet leg:** confirmed NOT a blocker anywhere; recorded solely as a separate operator-timed phase.
- **D12 (D-HL-3):** RATIFIED = crown `update.sh`. **U53's decision gate is REMOVED.** Zero code churn — the ruling matches what is already shipped and CI-guarded in both repos.
- **U53 live "prove the loop" tier:** NOT a decision item any more, and **not waiting on the operator**. It is gated on two newly-found code defects (`update.sh:160` pm2-name not overridable; `atomic-deploy.sh:384-422` kills pm2 apps by name keyword while ignoring the port it was passed). Ordinary build work — dispatch a scoped unit, do not re-ask the operator.
- **D4 (D-A4):** RATIFIED = Option A (additive section-map crosswalk). **U14's decision gate is REMOVED.** Zero code churn — Option A already shipped, merged (`c6f865fe`, tag v20.0.51), and re-proven this pass (18/18 tests pass on `origin/main`).

## Correction to the "genuinely waiting on Trevor" list (recorded 2026-07-16, second pass)

The tracking docs' summary sections claim **"U53's crown-decision tier only"** is waiting on Trevor. That summary undercounts. A full read of all three tracking documents this pass found **five further decision gates still annotated OPEN inline against individual units** that the summary line never counted:

- **D8 / D9** — annotated against U44 (`U44 ⚙️ *(D8/D9 open)*`, `skill6-SESSION-LOG-and-CHECKLIST.md:154`)
- **D15** — annotated against U59's sub-parts U55c/e (same line)
- **D21** — annotated against U96 (same line)
- **D22** — annotated against U97 (same line) — though the master spec's own phasing text says U107-U110 were "pulled IN per the **updated** D22", which reads as already-answered; the annotation may be stale.

Plus two non-Skill-6 operational items the handoff doc carries under "DECISIONS AWAITING TREVOR": the **Codex credits** top-up-vs-Claude-only call (parked until 2026-07-19 by Trevor's own instruction), and the **DeepSeek lane** (optional, research not started — reads as a not-yet-started task rather than a pending authorization).

The tracking docs' own framing of the five decision gates is *"an OPEN, non-unit DECISION gate (noted) — that's a ratification, not a build blocker"* (`skill6-SESSION-LOG-and-CHECKLIST.md:152`), and none of the three files attaches the phrase "waiting on Trevor" to any of them. **This file records the discrepancy rather than silently resolving it:** the correct count of open decision gates is not 1, and the summary tables saying otherwise should be corrected by whoever next touches them. These five are NOT ratified by this file — they are named here so they stop being invisible.

**The master register's own count is larger still.** Section E.3's controlling heading reads: *"D1 = BINDING RULING; D2, D3, D5 = RATIFIED 2026-07-14; D6, D23 = RATIFIED 2026-07-15 … remaining open items D4, D7–D22 = §0 questions, one at a time, BEFORE the run"*. Subtracting D4 and D12 (ratified above) and D20 (ratified earlier in this file) leaves **fourteen decisions still formally unratified: D7, D8, D9, D10, D11, D13, D14, D15, D16, D17, D18, D19, D21, D22.**

### The critical distinction — "ratify what shipped" does NOT apply to all of them

D4 and D12 were closable at zero cost because the recommended option was **already built and proven**. That is NOT true of every remaining decision. Verified from code on `origin/main` this pass:

| Decision | What it gates | Recommendation shipped? | Evidence (re-derived this pass) |
|---|---|---|---|
| **D8** (D-C2) | catch-all's client-facing name | **NO** | `src/lib/routing/departments.config.ts` on CC `origin/main` still ships display name **"General Task"**; the string "General Stuff" is absent. |
| **D9** (D-C3) | dedicated `funnels` department | **NO** | no `slug: 'funnels'` anywhere in that file — funnel cards still fall through to the catch-all (the INGEST-06 behaviour D9 exists to fix). |
| **D15** (D-J1) | Devil's Advocate content visibility + status lifecycle | **NO** | `src/app/api/da-challenges/route.ts` on CC `origin/main` ships the **legacy** enum (`open`/`responded`/`escalated`); the PRD lifecycle (`pending`/`approved`/`rejected`) is absent. That route predates U59 entirely (shipped by `8b7dc74`, `5bd9ba3`). |

**These three gate real, unbuilt work.** They cannot be closed by ratifying the status quo, because the status quo *contradicts* the recommendation.

### Integrity finding — two units read `verified` while only half-built (and the reconciler cannot see it)

**U44** and **U59** both carry `repo/surface: both` in the E.2 decomposition, meaning each owes an onboarding leg AND a Command Center leg. Both are recorded `verified` and both are merged **on the onboarding side only**:

- **U59** (Devil's Advocate): its own merged ONB commit `985935c4` states the split in its message — *"This commit covers the openclaw-onboarding half only: U55a (operator-box proof of the generator) and U55d (the thin bridge). The Command Center half (U55b demo purge, U55c POST/PATCH write path, U55e PRD-conform surfaces, U55f PRD fix) lands on its own blackceo-command-center train."* U55c and U55e are exactly the two sub-steps its dependency line gates on D15 (*"D-J1 ratified before U55c/U55e merge"*). **There is no U59 branch on the Command Center remote at all**, and the code above proves that half is not built.
- **U44** (catch-all conformance): **no U44 branch on the Command Center remote**, and its two CC-leg subjects (D8's display name, D9's funnels department) are both provably absent from `departments.config.ts`.

**Why the fail-closed alarm missed this:** `recovery-state.md`'s integrity check compares a branch's tip against `main` — it can only fire for a branch that **exists**. A second repo leg that was never started has no branch to compare, so the unit reads as fully `verified` off its first leg alone. This is a fail-OPEN blind spot in an otherwise fail-closed reconciler: it catches "verified but unmerged", never "verified but never started". A unit whose E.2 row says `both` should be checked against **both** remotes.

*Scope note:* this pass did not audit every `both` unit for the same defect — U44 and U59 surfaced because D8/D9/D15 pointed at them. Whoever next touches the reconciler should sweep all `both`-marked units against both remotes; the count above (fourteen open decisions) may itself be masking more half-built units.

### D15 in detail — the one decision that is a genuine operator call

A follow-up verification pass (findings below independently re-derived from `origin/main`, not accepted from the sub-agent that surfaced them) establishes D15's real state:

**1. The gated steps never merged — confirmed at the code.** `src/app/api/da-challenges/route.ts` on Command Center `origin/main` exports exactly one handler: `['GET']`. There is no `POST` and no `PATCH`. U55c *is* the POST/PATCH write path, so its absence is direct proof the D15-gated work did not land. The route predates the D-J1 spec entirely (`8b7dc74`, `5bd9ba3`).

**2. The onboarding half shipped a bridge with no landing pad — a dangling cross-repo integration.** U59's merged ONB slice includes U55d, `shared-utils/devils-advocate-bridge.py`, whose stated job is to POST the generator's JSON to the Command Center's `POST /api/da-challenges`. That endpoint accepts no POST. So the half of U59 that *is* merged and marked `verified` cannot function end-to-end today — it posts to a handler that does not exist. This is the concrete cost of the half-built-unit blind spot recorded above.

**3. The visibility question has real client blast radius — it is not theoretical.** `src/components/ceo-board/DevilsAdvocateFeed.tsx` fetches `GET /api/da-challenges` and is mounted directly in `src/app/ceo-board/page.tsx`. It is **default-on with no feature flag** gating it, and the Command Center *is* the client's own dashboard (per `src/middleware.ts`'s own doctrine: the dashboard is "the closeout reveal" to the client, not an operator-only console; there is no operator-vs-client role split inside the app). So if challenge content flows, it reaches a client-reachable surface by default.

**4. Migration 065's "[INTERNAL]" label does NOT settle the question.** What it provably enforces is: the agent's *description string* stays operator-facing; the agent is excluded from client-facing agent pickers/rosters; and `ensureWorkspaceHeadAgents()` never promotes a trio agent to department head. It does **not** state that challenge *content* must be hidden. The ambiguity D-J1 was written to resolve is real and unresolved — which is exactly why the spec says *"hence ratification, not silent interpretation."*

**5. Unproven-but-flagged (recorded honestly as a hypothesis, NOT a finding):** the GET route's own demo-seed `INSERT INTO da_challenges` names the columns `id, department_id, challenge_text, response_text, status, created_at, response_deadline, resolved_at`, while the only migration that creates that table (id `'020'`) creates `id, task_id, campaign_id, trigger_type, challenge, specific_concern, assumptions, severity, confidence, status, dismissal_reason, outcome, created_at, resolved_at`. Four of the insert's columns (`department_id`, `challenge_text`, `response_text`, `response_deadline`) do not exist in the schema; migration `024` is commented as "reserved" to reconcile this and was never implemented. **This is static analysis of code + migrations only — it was NOT executed against a live database this pass, so it is a hypothesis, not a proven runtime defect.** If correct, the feed would error rather than surface content. Whoever builds U55c must resolve this schema question first regardless of how D15 is ruled.

**Net:** D15 cannot be closed by ratifying the status quo (the status quo is the pre-spec state, and it contradicts the recommendation on the lifecycle sub-part). Both sub-parts gate unbuilt work. Sub-part (i) is a genuine product-policy call about what a client sees, on a surface that is client-reachable by default — the one item in this entire pass that is properly the operator's to decide rather than an agent's.

## Files touched recording these decisions

- `ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md` — U65 row, U64 row (edited in place, old evidence preserved verbatim).
- `ledgers/ratified-decisions-2026-07-16.md` — this file (new).
- `Downloads/skill6-SESSION-LOG-and-CHECKLIST.md`, `Downloads/skill6-HANDOFF-2026-07-16.md`, `Downloads/skill6-blended-persona-kanban-MGMT-DASHBOARD-2026-07-16.md` — "waiting on Trevor" / EXCLUDED / BLOCKED sections corrected to match every ruling above.

Recorded 2026-07-16T08:25:44-04:00 on branch `chore/ratified-decisions-2026-07-16` off `openclaw-onboarding` `origin/main` (e734ef6a). Not merged by this pass — lands via the standing one-merge-writer-per-repo serial train.

---

## Second pass — 2026-07-16 (D12 + D4 closure)

The **D12 (D-HL-3)** and **D4 (D-A4)** rulings above, the U53 live-run assessment, and the "genuinely waiting on Trevor" correction were appended on branch `chore/ratified-decisions-2026-07-16-d12-d4`, branched off `chore/ratified-decisions-2026-07-16` (`f7d97842`). Not merged by this pass — lands via the standing one-merge-writer-per-repo serial train.

**Evidence discipline for this pass:** every load-bearing claim was re-derived from primary source (git ancestry on the remotes, plus scripts executed in the foreground against `origin/main` code in a throwaway worktree). No sub-agent claim was accepted as fact; the two tests quoted (the U53 crown-executor probe, 10/10, and the U14 section-map suite, 18/18) were run directly. **No live box was mutated by this pass** — the only writes were to a scratch sandbox; `~/command-center/app` and `~/clawd/AGENTS.md` were read but never modified, and the operator's Command Center was left serving `HTTP 200 / status: ok` exactly as found.

`ledgers/recovery-state.md` was deliberately NOT edited this pass: it is machine-regenerated from git truth every 10 minutes by the reconciler cron, so any hand-edit there is overwritten. The permanent record lives in this file.
