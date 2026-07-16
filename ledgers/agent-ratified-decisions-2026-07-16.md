# AGENT-RATIFIED DECISIONS — 2026-07-16 — ⚠️ NOT TREVOR'S RULINGS

> **READ THIS BEFORE ANYTHING ELSE IN THIS FILE.**
>
> Every decision recorded here was ratified by a **coordinating agent**, not by Trevor.
> **Trevor has not seen these. He has not approved them.** They were called under a
> claimed standing "go with your recommendation / don't gate me" directive, on the
> explicit reasoning that each reverses cleanly if he later disagrees.
>
> This file is deliberately SEPARATE from `ledgers/ratified-decisions-2026-07-16.md`.
> That file is titled "Trevor's RATIFIED DECISIONS" and its own header states it records
> "decisions Trevor made on 2026-07-16". Appending an agent's ruling there would read as
> Trevor's to anyone skimming, however carefully it were labelled — so it is recorded
> here instead. **Nothing in this file may be moved into that file** unless Trevor
> himself ratifies it, at which point it becomes his ruling and this entry becomes
> historical record of how it was held in the interim.
>
> **If Trevor reverses any decision here, it reverses cleanly** — see each entry's
> "How this reverses" section, which is a precondition of an agent ratifying it at all.

---

## D15 (D-J1) — ✅ MIGRATED OUT: TREVOR RATIFIED IT HIMSELF

> **STATUS CHANGE — this entry is now HISTORICAL RECORD, not a live agent ratification.**
>
> **Trevor subsequently reviewed this ruling and ratified Option A himself.** The live,
> authoritative record is now the **"D15 (D-J1) — RATIFIED BY TREVOR = Option A"** section of
> **`ledgers/ratified-decisions-2026-07-16.md`**, which carries his ruling, the full provenance
> trail, and the attestation note. Read that one as canonical. This entry is kept — not
> deleted — because how the decision travelled is itself worth reading:
>
> 1. The coordinating agent ratified Option A on Trevor's behalf and disclosed that he had not
>    seen it.
> 2. It was quarantined here rather than filed in Trevor's file.
> 3. The Command Center merge-writer **refused to land the work**, partly on that provenance
>    gap — it judged that merging is the act which puts challenge content on a client board,
>    and would not wave that through on an agent's say-so.
> 4. The coordinator took it to Trevor with the reversal option and the consequence stated.
> 5. Trevor ratified it himself, satisfying this file's standing condition.
>
> **The quarantine did its job, and so did the writer's refusal.** Two independent checks held
> a client-visible decision until the human actually made it. That is the mechanism working as
> designed, which is why the standing instruction below is unchanged and this file remains in
> force for anything else that lands here.

**Who ratified, originally:** the coordinating agent of the 2026-07-16 Skill 6 session — **not
Trevor**, at the time this was written. Trevor has since ratified it himself (see above).

**What it decides, in plain English:** the "Devil's Advocate" is an internal challenger —
it stress-tests a department's plans and decisions by surfacing assumptions and
counter-arguments. The question was whether the *text of its challenges* may appear on
a board a client can see, given that the database migration that creates the role labels
it `[INTERNAL — not surfaced to client]` while the product requirements document
specifies a client-visible challenge feed. Both texts are real.

**The ruling:** **Option A — the CONTENT surfaces on client boards; the AGENT stays
internal.** The agent remains off client-facing rosters and agent pickers, is never
promoted to department head, and its description stays operator-facing.

**Sub-part (ii), ruled with it:** the product-doc status lifecycle
(`pending` / `approved` / `rejected` / `escalated`) is canonical.

**Reasoning on record:**
- The `[INTERNAL]` label provably enforces exactly four things, verified in code this
  pass: (a) the agent's description string is operator-facing; (b) it is excluded from
  client-facing agent pickers/rosters; (c) `ensureWorkspaceHeadAgents()` never promotes
  a trio agent to department head; (d) `CHANGELOG.md` confirms the trio is excluded from
  the client-facing agent roster. **Content-hiding is not among them.**
- Option B would leave a client-reachable feed — mounted on the board page with no
  feature flag — whose sole purpose is to display content it is forbidden to display.
  That is a dead route, and it would make the product document a lie.
- Option A honors both texts exactly as written. The texts do not conflict; they are
  *silent*, and the spec's own instruction ("ratification, not silent interpretation")
  means silence gets filled by a decision on the record, not by a coin flip.

**How this reverses cleanly (the precondition for an agent calling it):** the build is on
an unmerged branch. Nothing reaches any client until (1) the Command Center's single
serial merge-writer merges it, and (2) Trevor rolls the fleet on his own timing — two
human-controlled gates, both downstream of this ruling. To reverse: close the pull
request and delete the branch. Nothing else is affected.

**One honest caveat that outlived the ruling — since CONFIRMED:** if Trevor had reversed to
Option B, the *schema* half of the work should have survived anyway. The write path and the
migration fix a confirmed defect (below) that exists regardless of who may read the feed.
Option B would gate or remove the FEED, not the write path. This was independently verified
afterwards: the feed renders from `src/app/ceo-board/page.tsx:402` — **a file this branch
never touches**. So the defect fix was never actually hostage to the decision, and a
reversal would have been a one-line change to a file outside the branch entirely.

---

## What was built on this ratification

**Branch:** `skill6-v2/U59-cc-d15` on `trevorotts1/blackceo-command-center`,
tip `6490fe8a24be1b4b4a46c9e871970c1c92441c3c`. **Draft pull request #193** — opened to
run CI only; a draft cannot be merged. **Not merged. Main untouched.**

**CI: GREEN** — 20/20 checks, 0 not-green, read from `gh api` on the branch tip (not a
local claim). CI does not run on a bare feature-branch push in this repo: every workflow
triggers only on push/pull_request to `main`, which is why the draft PR exists.

### The schema hypothesis is now a CONFIRMED DEFECT

Previously recorded in `ratified-decisions-2026-07-16.md` as an explicitly-flagged
hypothesis ("static analysis only, NOT executed against a live database"). It has now
been settled against the operator's live database, read-only, and reproduced against a
byte copy of it:

- The live `da_challenges` table has the **canonical** migration-020 shape, **0 rows**.
- `GET /api/da-challenges` seeds demo rows naming `department_id`, `challenge_text`,
  `response_text`, `response_deadline` — **four columns no migration has ever created**.
  `schema.ts` no longer defines the table at all.
- The route's exact INSERT, executed against a copy of the live DB, raises
  `table da_challenges has no column named department_id`. The route's own try/catch
  turns that into **HTTP 500**.
- The table is empty, so the seed path fires on **every** request.
- **Verdict: the Devil's Advocate feed has never rendered on a canonically migrated
  box.** It is not "a feature awaiting data" — it is a dead 500.

*(The live endpoint answers 401 to an unauthenticated request, so the 500 was proven by
exact reproduction rather than observed on the live box. Stated so no one later claims a
live observation that was not made.)*

**Root cause:** migration 020 no-ops on a legacy table and defers to migration 024
("Migration 024 owns the legacy → canonical reconciliation"); the index-repair
migration's comment likewise assumes 024 "reconciles the table". **Migration 024 was
reserved by PR #11 and never implemented** — the id sequence jumps `021 → 025`. Two
comments in the codebase describe a migration that does not exist.

### The dangling integration is closed

U59's **merged** onboarding half ships `shared-utils/devils-advocate-bridge.py`, whose
job is to POST to `POST /api/da-challenges`. That endpoint exported **only `GET`**. A
unit marked `verified` could not function end to end. The branch adds the POST handler,
matching the bridge's documented wire contract field for field.

### Proof (all gates foreground, explicit timeouts)

- `tests/unit/u59-da-challenges-round-trip.test.ts` — **9/9 pass**, including the real
  round trip (bridge wire payload → POST → row persisted → GET returns it) and two
  migration fixtures proving canonical **and** legacy rows survive with their status
  vocabularies mapped.
- `tsc --noEmit`: exit 0. `next lint` on every touched file: clean.
- Full unit suite: 1619 tests, **1614 pass, 5 fail**. All 5 are `getInterviewState` in
  `tests/unit/interview-detection.test.ts` and are **PRE-EXISTING**: the identical 5 fail
  on pristine `origin/main` (`87ef1ff`) with none of this branch involved. **Zero
  regressions.** (Those 5 are a real, separate, pre-existing failure someone should own —
  named here rather than left buried in a log.)

### Correction to D15's own text — and a correction to that correction

D15 framed sub-part (ii) as a choice between "the code's `open/responded/escalated`" and
the product doc's four. **That premise was incomplete**: it missed migration 020's CHECK
(`open/accepted/dismissed/overridden`), the constraint actually enforced on every
canonically migrated box.

**An earlier version of this section then got its own detail wrong**, and the fix is
recorded rather than quietly overwritten. It claimed `open/responded/escalated` was "the
TypeScript interface in route.ts — never a database constraint." **False.** It is a real
CHECK constraint in the legacy `schema.ts`, verified verbatim at commit `5bd9ba3`:
`status TEXT DEFAULT 'open' CHECK (status IN ('open', 'responded', 'escalated'))`.

The accurate picture is **three distinct vocabularies across four declaration sites**:
1. PRD — `pending|approved|rejected|escalated` (the target).
2. `open|responded|escalated` — declared **twice**: the legacy `schema.ts` CHECK (a real
   constraint) *and* route.ts's TypeScript interface.
3. Migration 020's CHECK — `open|accepted|dismissed|overridden` (real; the one D15 misses).

A reviewer who caught the error relayed it as making this "a **fourth** vocabulary." That
does not survive counting, and was not adopted on the reviewer's authority: sites 2a and 2b
declare the *identical* set, so it is a fourth **site**, not a fourth vocabulary. The
original "third vocabulary" count was right; the "never a DB constraint" clause was the
error. Migration 024 maps **both real constraints** so neither box class loses a row.

The finding had teeth beyond the record: the legacy test fixture had used a bare
`status TEXT` with no CHECK and nullable columns — not the shape a legacy box actually has.
It now uses the real DDL verbatim and exercises all three members of the legacy vocabulary,
asserting the legacy CHECK is genuinely replaced rather than merely its values rewritten.
The weaker fixture would have let a mapping bug pass and still break a real legacy box.

---

## Standing instruction to future agents — UNCHANGED, and it just proved itself

These rules are kept exactly as originally written. Rule 4 has now fired once, on D15, and
worked: the entry stayed quarantined until Trevor ratified it himself, and only then moved.
Rule 2's condition is a real gate, not a formality — do not treat D15's migration as a
precedent for relaxing it.

1. **Do not present anything in this file to Trevor as his own decision.** It is not.
2. **Do not move these entries into `ratified-decisions-2026-07-16.md`** unless Trevor
   ratifies them himself.
3. **Do not merge `skill6-v2/U59-cc-d15`.** The Command Center has one serial
   merge-writer; two writers on one `main` is corruption. Draft PR #193 exists to run
   CI, not to queue a merge. (Trevor's D15 ratification unblocks the merge *decision*; it
   does not perform the merge, and it does not make this agent the merge-writer.)
4. If Trevor rules on an entry here, record his ruling in his own file and update the entry
   to point at it — **without deleting the entry**. The route a decision took is part of the
   record. ✅ *Fired on D15, 2026-07-16.*
5. **An agent relaying "the human approved it" is not the human approving it.** Record what
   is attested and by whom, and say plainly when a claim is relayed rather than witnessed.
   D15's entry in Trevor's file does exactly this. A record whose evidence is implicit cannot
   be audited, and an unauditable record is what this file exists to prevent.

Recorded 2026-07-16 on branch `chore/ratified-decisions-2026-07-16-d12-d4`. Not merged.
No live box was mutated by this work: the operator's database was read strictly
read-only, and the Command Center was left serving HTTP 200 with all three pm2 processes
online, exactly as found.
