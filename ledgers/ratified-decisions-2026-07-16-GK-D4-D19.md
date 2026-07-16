# GK-D4 / D19 — ratification excerpt (U74 repo-half, 2026-07-16)

**Why this file exists.** `58-podcast-production-engine/config/n8n/README.md`
on this branch (`skill6-v2/U74`) points here for the GK-D4/D19 ratification
record. The full record was written to
`ledgers/ratified-decisions-2026-07-16.md` on a **different, still-unmerged**
branch, `chore/ratified-decisions-2026-07-16-d12-d4` (commit `41d2d1f9`), which
also carries six unrelated decision records (D12, D15 ×3, D20/U65 closure) not
reproduced here. That branch's merge timing relative to this one was
unresolved, so a pointer from this branch's README into that branch's commit
would dangle if this branch merged alone. This file is a **verbatim excerpt**
of the one section this README needs — the GK-D4/D19 ratification itself —
committed on this branch so the pointer resolves regardless of merge order.
If the fuller ledger lands on `main` first, the two files will overlap on this
section's content (not conflict in meaning); the merge-writer can fold this
excerpt away at that point.

**Provenance.** The text below is reproduced unedited in substance from commit
`41d2d1f9ff95e81500cac0d53a2e8ecd0f20ea8b` (`chore/ratified-decisions-2026-07-16-d12-d4`),
section "GK-D4 (D19) — RATIFIED BY TREVOR = Option A", authored 2026-07-16
16:46:36Z. Only self-references to other sections of that file that do not
exist here ("above") have been rewritten to point at the source ledger by
name, so the excerpt reads correctly standalone. No claim, evidence figure, or
ruling was altered.

---

## GK-D4 (D19) — RATIFIED BY TREVOR = Option A

**What this decides, in plain English:** the podcast engine (Skill 58) has
exactly one client-facing published-episode surface, but the live n8n
instance has **two** workflows that can each call the real Podbean publish
API and put an episode on a client's live feed: the gated, governed pipeline
Skill 58 actually calls, and a second, older workflow that duplicates the
same publish chain outside that governance. Two live paths that can both
write to the same client's feed is a double-publish risk. This decision names
exactly ONE of them canonical.

**Where this decision lives, and why it has two names.** A `D-U74` entry
(the source ledger, `ledgers/ratified-decisions-2026-07-16.md`, "Unit 74 is
UNBLOCKED / BUILDABLE") already flagged this exact question as U74's own
co-located decision, naming it **GK-D4** — *"which podcast pipeline is
canonical"* — and recorded that U74's own spec requires it to be "asked and
answered BEFORE the run starts." Separately, U74's ledger row
(`ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`, id U74) reads:
*"[GK-12] (n8n + ONB, P1) Canonicalize the podcast pipeline per **D19** (kill
the double-publish risk)."* The source ledger's "Correction to the 'genuinely
waiting on Trevor' list" section independently lists **D19** among the
fourteen master-spec decisions then formally unratified. Comparing the two
texts side by side — "which podcast pipeline is canonical" (GK-D4) and
"canonicalize the podcast pipeline... kill the double-publish risk" (D19) —
they are the same question under two labels: GK-D4 is the GK-track's own
in-unit name for it, D19 is the master spec's global decision number for it.
Independently confirmed stronger than either of the above: the master spec's
own decision crosswalk table, line 371, equates them outright: `D19 | GK-D4 |
Podcast pipeline canonicalization | The Skill-58-documented flow is
canonical; retire/re-scope the parallel n8n-internal pipeline`. **This entry
ratifies both labels together, as one decision, and closes both.**

**Ruling: Option A.** `TkL0rn2SH3q32SeB` ("create podcast episode from
openclaw") is the single canonical publish path for the podcast engine. The
other live workflow, `COfgxe6HXRcWOleV` ("Podbean Channel IDs to Google
Doc"), is retired — **deactivated, never deleted.**

**Evidence, re-derived this pass from primary source (live n8n reads,
`mode=structure`/`mode=minimal` only — no Code/Set node body was ever read or
printed, per the standing NEVER-PRINT rule):**

- **`TkL0rn2SH3q32SeB` is the gated, evidence-bearing, furnace-governed
  path.** Live structure read (51 nodes) shows it carries all three
  hardening layers named in the dispatch, matching GK-05/U67's landing at
  repo tag `v20.0.43`: an **idempotency ledger** (`Idempotency — Lookup By
  Key` → `Determine Verdict` → `Mark In Flight` → terminal `Mark
  Completed`/`Mark Failed`/`Mark Refused (Standing Gate)`/`Mark Refused
  (Media Preflight)` nodes, with dedicated `IF — Idempotency Already
  Completed` / `IF — Idempotency In Flight` branches responding `Idempotent
  Replay` / `Idempotency In Flight` before any Podbean call), a
  **standing-gate identity check** (`Standing Gate — Normalize Lookup Keys`
  → `Roster Lookup By Email` → `Determine Verdict` → `IF — Standing Identity
  Gate Passed`, refusing and notifying before any publish work begins), and a
  **media preflight** (`Media Preflight — HEAD Check Audio URL` → `HEAD Check
  Image URL` → `Determine Verdict` → `IF — Media Preflight Passed`, refusing
  before the OAuth/upload/publish chain runs). `updatedAt =
  2026-07-16T14:29:30.615Z` — hardened same-day. `n8n_executions list`
  (100-row pull, `hasMore:false`) shows **37 executions today
  (2026-07-16, 12:38–14:31 UTC)**, all but two `status:success` (two isolated
  `error` rows, `91214` and `91131`, neither `waiting`/in-flight) — this is
  the "ran dozens of successful jobs today" claim, confirmed live, not
  relayed.
- **`COfgxe6HXRcWOleV` is dormant, ungoverned, and carries a structural
  double-publish entry point.** Live structure read (57 nodes) shows its own
  entry-point node, named `Start`, is type `n8n-nodes-base.executeWorkflowTrigger`
  — confirmed live: any other n8n workflow's "Execute Workflow" node, or a
  manual "Execute workflow" click in the n8n UI on this workflow itself,
  fires it directly, with no webhook auth, no idempotency ledger, no
  standing-gate identity check, and no media preflight anywhere in its graph.
  Its `Start` branch runs its **own** independent Podbean publish chain
  (`Podbean OAuth` → `Prepare Audio Upload` → `uploadAuthorize Audio` →
  `Merge Audio Binary` → `PUT Audio` → `Prepare Image Upload` →
  `uploadAuthorize Image` → `Merge Image Binary` → `PUT Image` → `Set Upload
  Keys` → `Publish Episode` → `Update n8n Table`) — a second, real, live path
  to the same Podbean account, entirely outside Skill 58's governance.
  `updatedAt = 2026-04-13T22:32:43.652Z` (no code change since April).
  `n8n_executions list` for this workflow returns **exactly 4 executions
  total** (`hasMore:false` — the complete history, not a windowed sample),
  **all on 2026-07-05**, none since: `83630` success, `83631` error, `83633`
  success, `83638` error — the "dormant since 2026-07-05, last four runs 2
  successes and 2 errors" claim, confirmed live. **None of the four carries
  `status:"waiting"` or any other in-flight state** — there was no live
  in-flight execution this pass found, and this pass's own read-only
  structure/execution reads were the only touches made to this workflow
  before the deactivation recorded below.

**Attestation, stated precisely, matching the source ledger's own standard.**
Trevor's ratification of Option A is recorded here on the dispatching agent's
attestation: it states Trevor was asked this exact question, this session,
with the options and the evidence above laid out directly, and that he
ratified Option A. The agent writing this entry did not witness that
exchange, has no direct channel to Trevor, and cannot independently verify it
— the same standard already applied to D15's provenance trail in the source
ledger. If this attribution is wrong, Trevor corrects it in one line, and this
note is what makes the error findable. Every other claim in this section
(workflow structure, `updatedAt`, execution history, node types) **was**
independently re-derived this pass from live primary source, not relayed.

**Effect:** GK-D4/D19's decision gate is REMOVED. U74/GK-12 ("Canonicalize
the podcast pipeline per D19") is no longer decision-blocked; the remaining
work is the mechanical act of canonicalizing (deactivating
`COfgxe6HXRcWOleV`, documenting the relationship in the Skill 58 config docs,
and proving single-publish via a before/after Podbean episode-count
read-back) — executed immediately following this entry, in this same pass,
and recorded in U74's own ledger row.

**Standing rule reaffirmed, unchanged by this ruling:** per `D-U65` (recorded
separately in the source ledger), the Podbean OAuth plaintext credentials on
both `BqRLOn8TP1wPaAzn` and `COfgxe6HXRcWOleV` remain **NEVER-PRINT,
NEVER-VAULT, NEVER-ROTATE** — permanent and closed. Deactivating
`COfgxe6HXRcWOleV`'s trigger does not touch, read, relocate, or "fix" that
credential; it changes only the workflow's `active` flag. This ruling is
about which workflow is allowed to fire, never about the credential inside
either one.

---

## Repo-half correction (added 2026-07-16, on `skill6-v2/U74`, post-QC)

QC (score 6.8, SEND BACK) found that the mechanical execution of this ruling
(commit `ce01769d` on this branch) documented the double-publish vector
correctly and then asserted the non-canonical workflow was flatly "retired"
without reconciling `active: false` against that vector, and without
discovering a live, active caller (`yXKQg61bbA0ufJ1L`, node "Trigger podcast
creator workflow 8") wired directly to `COfgxe6HXRcWOleV`. Nothing in the
ratification above is disputed or reopened by this correction — the ruling
itself (Option A, ratified) stands. What changed is the mechanical-execution
pass's own README claim about what deactivation accomplishes; see
`58-podcast-production-engine/config/n8n/README.md`, section "Deactivation
semantics and the live caller," for the corrected statement. Disposing of the
live caller node is live work, gated on the operator's decision (goal §5 Q1)
and tracked as `K6-U74-r2` — explicitly not done by this repo-only
correction.

**Evidence discipline for the original ratification pass:** every
load-bearing claim about the two n8n workflows (node structure, node types,
`active`/`updatedAt` metadata, execution history and status) was read live
that pass via `mcp__n8n-mcp__n8n_get_workflow` (`mode=structure` and
`mode=minimal` only) and `mcp__n8n-mcp__n8n_executions` (`action=list`) — no
Code/Set/HTTP-Request node body was fetched or printed on either workflow,
and no credential value was read, printed, or referenced beyond its name.
That entry was recorded **before** the deactivation it authorizes was
executed, per the standing instruction to record ratification first.
