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

## Net effect on the "buildable now" set

- **U65:** CLOSED (terminal state — not buildable, not pending; done).
- **U64:** VERIFIED (terminal state — done).
- **U74:** now BUILDABLE (blocker removed).
- **U73:** now BUILDABLE (downstream unblock — its blocker U64 is verified).
- **U93:** now BUILDABLE (decision gate D20 removed; only dep is already-merged U92).
- **U72:** still blocked on U63's actual completion — reframed from "operator-gated exclusion" to a normal pending-dependency wait, since U63 is authorized (not excluded) as of this ruling.
- **U22, U26, U63 live/activation legs:** AUTHORIZED — execution and evidence tracked by separate agents in this session, not claimed complete by this file.
- **Fleet roll / P4 / U84 fleet leg:** confirmed NOT a blocker anywhere; recorded solely as a separate operator-timed phase.

## Files touched recording these decisions

- `ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md` — U65 row, U64 row (edited in place, old evidence preserved verbatim).
- `ledgers/ratified-decisions-2026-07-16.md` — this file (new).
- `Downloads/skill6-SESSION-LOG-and-CHECKLIST.md`, `Downloads/skill6-HANDOFF-2026-07-16.md`, `Downloads/skill6-blended-persona-kanban-MGMT-DASHBOARD-2026-07-16.md` — "waiting on Trevor" / EXCLUDED / BLOCKED sections corrected to match every ruling above.

Recorded 2026-07-16T08:25:44-04:00 on branch `chore/ratified-decisions-2026-07-16` off `openclaw-onboarding` `origin/main` (e734ef6a). Not merged by this pass — lands via the standing one-merge-writer-per-repo serial train.
