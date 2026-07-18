# SKILL 58 PODBEAN SERVER-SIDE PUBLISH — LEDGER — 2026-07-16

Update the INSTANT a unit changes state. Per unit, NEVER at wave-end. This is the
compaction/session-limit lifeline: if an agent dies, the next one resumes from here.

**Row format:** `id | desc | [Model xN] label | status | evidence | timestamp`
**Status vocabulary:** `pending` / `in_progress` / `verified` / `blocked`
**`verified` is a GIT state (repo legs: merge commit is an ancestor of origin/main +
annotated tag resolves on the remote) or a LIVE-API state (n8n legs: fresh API re-read).
Never prose. Never a subagent's claim.**

NO client names. NO emails. NO secrets. Unit status only.

Spec: `skill58-podbean-server-side-publish-SPEC-v1-2026-07-16.md` (Section 5 = units, Section 10 = D1-D5)

---

## CONCURRENCY MAP (one writer per n8n WORKFLOW; different workflows run in PARALLEL)

| Lock target | Units | Note |
|---|---|---|
| `TkL0rn2SH3q32SeB` | U4, U5, U6, U7, U8, U9, U10, U11, U12 | SERIALIZE — one queue, 9 units, one writer at a time |
| `NEW:podcast-standing-check` | U13 | Parallel-safe (new workflow) |
| `NEW:zz-scratch-write-probe` | U1 | Parallel-safe (creates + deletes its own scratch) |
| `DATATABLE:podcast_publish_roster` | U2 | Data table, not a workflow — no workflow lock |
| `DATATABLE:podcast_publish_ledger` | U3 | Data table, not a workflow — no workflow lock |
| Repo `openclaw-onboarding` | U12 (repo leg), U14, U15, U16, U17, U21 | ONE merge-writer, serial |

---

## UNIT ROWS

| id | desc | [Model xN] label | status | evidence | timestamp |
|---|---|---|---|---|---|
| U1 | Prove n8n API WRITE capability (POST/GET/DELETE scratch workflow) or record manual-UI fallback | [Kimi x1] ledger truth-up U1 | verified | LIVE-PROVEN 2026-07-17, all three accept clauses, literal, per spec line 211. (a) POST to create a scratch workflow returned HTTP 200 with id `054kIrBCCErjOIe1`, active:false. (b) GET of that id returned HTTP 200, same id and name, 1 node. (c) DELETE returned HTTP 200; the immediate re-GET afterward returned HTTP 404. 'No other workflow touched' was proven by a full before/after metadata comparison across all 286 workflows on the instance (id, name, active state, last-updated time, node count): zero added, zero removed, zero changed, including a named watch-list of 5 sensitive workflow ids confirmed unchanged. A specific trap was checked and ruled out: n8n workflows can be soft-deleted ('archived') rather than truly deleted, which would also return HTTP 200 then 404 on re-GET as a false positive — settled by confirming the deleted probe id is absent even from an archive-inclusive listing, proving a genuine delete. No fallback path was needed; the write calls did not return an authorization error. | 2026-07-17T12:01:55Z |
| U2 | Create + seed `podcast_publish_roster` data table (6 cols, all good_standing=YES, + OPERATOR TEST row) | [Sonnet 5 x1] structure-mode re-read U2 | verified | STRUCTURE-MODE LIVE RE-READ 2026-07-18, both accept clauses confirmed, per this row's own spec text. Method: `n8n_manage_datatable` (`listTables` + `getRows`) only — no workflow node parameters or credentials were touched this pass (this pass was scoped structure-mode-only for workflow reads). Table `podcast_publish_roster` (id `UWjpksxU2b6TjKow`, created 2026-07-16T12:49:53.532Z, last updated 2026-07-17T08:35:24.004Z) now EXISTS with exactly 6 columns matching the requirement: `email`, `first_name`, `good_standing`, `last_name`, `notes`, `podbean_channel_id`. Fresh row-level re-read: 31/31 rows carry `good_standing = "YES"` — zero rows in any other status. One row (id 31 — the operator's own identity, not a client) carries the explicit marker `"OPERATOR TEST ROW for U19/U20 live proofs"` in its `notes` column, satisfying the OPERATOR TEST row requirement. Per this ledger's own NO-client-names/NO-emails convention, no client name, email, or channel ID from the roster is reproduced in this row — verification was performed by direct API read, only aggregate counts and the operator's own marker row are recorded here. | 2026-07-18T05:09:32Z |
| U3 | Create `podcast_publish_ledger` data table (8 cols), empty at creation | [Kimi x1] ledger truth-up U3 | verified | LIVE-PROVEN 2026-07-17, both accept clauses, per spec line 219. (a) Schema re-read confirmed the table (id `3anOzegbKtLcgVud`) has exactly 8 columns in the spec-exact order: idempotency_key, channel_id, episode_number, permalink_url, status, reason, source, completed_at. (b) 'Empty at creation' was affirmatively PROVEN, not merely assumed: the table's own earliest surviving row still holds row-id 1, created 7 minutes 23 seconds after the table itself was created. Because this database engine's row ids only increase and are never reused after a row is deleted, an earliest row that still holds id 1 proves no row could have been created and then deleted before it — the table genuinely held zero rows during that entire 7-minute window. | 2026-07-17T12:01:55Z |
| U4 | Snapshot workflow JSON, then add webhook header auth (`Podcast Publish Gate`, `X-Podcast-Publish-Token`) | — | pending | GREENFIELD — **LIVE SECURITY HOLE OPEN AND CARRYING REAL TRAFFIC**. Fresh API re-read of `TkL0rn2SH3q32SeB` webhook node: `authentication` key ABSENT, `credentials: NONE`, `path: podbean-publish`, `httpMethod: POST`. Webhook is publicly postable. Pattern source `aN6MrIJ4zLeKS047` still ACTIVE (2 nodes). **SEE THE LIVE-CALLER FINDING BELOW — execution 91115 published a real episode at 2026-07-16T12:38:08Z, DURING this bootstrap. U4 will 401 that caller unless it is provisioned first. This is now the central input to D1.** | 2026-07-16T12:41Z |
| U5 | Good-standing + identity gate (roster lookup; downstream uses roster's `effective_channel_id`) | — | pending | GREENFIELD. Fresh re-read: ZERO dataTable nodes in the 24-node graph. No roster lookup exists. | 2026-07-16T12:35Z |
| U6 | Extend entry field guard to contract v2 | [Kimi x1] ledger truth-up U6 | verified | LIVE-PROVEN 2026-07-17, per spec line 233. 21 live test requests were fired against the real webhook (each using a fake, non-client identity, so a missed rule could never have actually published anything). Every new v2-contract rule produced its own distinct refusal, each confirmed with the real HTTP 422 response body: a bad or missing contract-version field, a missing required identity field, a missing idempotency key, a non-secure (http:// instead of https://) audio or image address (tested individually and together), a title over 200 characters, and a description over 3,000 characters. All 7 of the older, pre-existing required-field checks were re-fired and still work correctly. The specific real-world failure that originally caused this guard to be built — a null image address, from an incident on 2026-07-12 — was replayed exactly and correctly refused before anything was sent to the podcast host, with zero podcast-publishing steps executed. A control case (a fully valid submission) was also fired to prove the guard is not simply refusing everything by accident — it correctly proceeded past this guard and was refused later for an unrelated, expected reason. Every temporary test row created during this testing was deleted afterward and confirmed gone; the real production data and the real production workflow were both confirmed unchanged before and after. | 2026-07-17T12:01:55Z |
| U7 | Synchronous response (`responseMode: responseNode`) returning permalink JSON | — | pending | GREENFIELD. Fresh re-read: webhook `responseMode` ABSENT (= default fire-and-forget); ZERO `respondToWebhook` nodes in the graph. Permalink cannot reach the caller today → Step 16 is starved. | 2026-07-16T12:35Z |
| U8 | Server-side idempotency via `podcast_publish_ledger` | — | pending | GREENFIELD. Depends on U3 (table absent). ZERO dataTable nodes live. | 2026-07-16T12:35Z |
| U9 | Scheduling-status truth check (`draft` vs `future`) proven live | [Kimi x1] ledger truth-up U9 | verified | LIVE-PROVEN 2026-07-17, per spec line 245 — this supersedes and closes out the row's previous note, which had flagged a real defect that has since been fixed. A real episode was scheduled about 10 minutes in the future on the operator's own private test show only (never a client's show). Immediately after scheduling, the podcast host's own records correctly showed the episode's status as 'future' (not the old, incorrect 'draft' status this system used to send) — proving the current code's status mapping is correct. Roughly 90 seconds after the scheduled time passed, a fresh check showed the status had correctly flipped to 'published' with a working public link. A follow-up check 15 minutes later confirmed it was still published, and an independent, ordinary web request to that public link returned HTTP 200 — genuinely live on the open internet. Cleanup: the podcast host's programming interface does not allow true deletion of an episode under the current access permissions (a real HTTP 403 error was returned on the delete attempt) — the episode was instead unpublished back to a private draft, and confirmed removed from the show's public list. One honest, disclosed leftover: that unpublished test episode still physically sits in the operator's own test show as a hidden draft — it could not be hard-deleted; the same limitation was independently hit by a second, separate test later in the same run (see S58-U20's evidence). No client show was touched at any point. | 2026-07-17T12:01:55Z |
| U10 | Notification routing for refusals → OPERATOR only | [Kimi x1] ledger truth-up U10 | verified | LIVE-PROVEN 2026-07-17, all three accept clauses plus the 'Do' clause, per spec line 248. Method used: reading the actual delivery address of each already-sent notification email directly (not just the workflow's configuration, which does not show where a message actually went). Every refusal path was tested using a fake, non-operator email address inside the test submission, specifically so a wrong delivery would be provable: the entry-guard refusal, the identity-unknown refusal, and the media-unreachable refusal were all confirmed to have actually landed in the operator's own mailbox despite a different address being submitted. A mailbox-wide search confirmed that zero notification emails were ever sent to any of the fake test addresses used across the whole testing run. The specific required wording for an 'identity mismatch' refusal (naming both the submitted and the on-file show identifiers) was confirmed present in the actual email body. The separate 'a successful publish still emails the real client' requirement was confirmed from mailbox history predating last night's testing (a message from an earlier real run went to a genuine outside address, not the operator) — proving the recipient is driven by the real submitted address, not hardcoded to the operator. This check required no changes to any live system — it was entirely a read of already-existing evidence. | 2026-07-17T12:01:55Z |
| U11 | Media preflight (HEAD audio_url + image_url before OAuth) | [Kimi x1] ledger truth-up U11 | verified | LIVE-PROVEN 2026-07-17, both accept clauses, per spec line 253. Clause 1 (a broken link is refused before any podcast-host steps run): three live tests were fired — an audio link that returns 404, both links broken, and a link with a non-existent internet address — and all three correctly returned an HTTP 422 refusal naming the exact failing link(s), with zero podcast-host connection, upload, or publish steps executed in any of the three (independently confirmed by reading the full list of steps that actually ran in each case). The check was confirmed to be a genuine lightweight existence check rather than a full download: the server-declared file size was present but zero actual bytes were transferred. A broken link was confirmed to be handled cleanly as an expected refusal, not a crash. Clause 2 (a working submission is unaffected): confirmed both from an existing, already-passing real submission on record that ran this exact check successfully end-to-end, and from today's own test where the one genuinely working link involved correctly passed the check and was not flagged. All temporary test data created during this testing was deleted and confirmed gone afterward; the real show and real workflow were confirmed unchanged. | 2026-07-17T12:01:55Z |
| U12 | Cutover + sanitized archive + gate-test cleanup (HYBRID: n8n leg + REPO leg) | [Sonnet 5 x1] correct U12 row (both legs confirmed) | verified | CORRECTED 2026-07-17 -- both legs now confirmed, git-independently re-derived this pass. **n8n leg**: unchanged from the prior evidence recorded above (live-API state, not re-read this pass) -- gate-test workflow `aN6MrIJ4zLeKS047` deleted, live `TkL0rn2SH3q32SeB` re-read confirmed active. **Repo leg**: PR #606 (branch `ledger/skill58-podbean-proxy`, tip `a5048fe0`) merged into `origin/main` via merge commit `28bca8dd`, `git merge-base --is-ancestor 28bca8dd origin/main` = true (fresh clone, re-fetched). PR #606's own check-run rollup: 22 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, state=SUCCESS, correctly excluded from the check-run tally) = 0 failures. No annotated tag has been cut covering `28bca8dd` yet (ONB's last tag is `v20.0.66`, this commit is 7 commits ahead of it, alongside 6 other untagged commits including S58-U14/U15/U16's own merges -- ancestor-of-main and CI are proven; tag coverage awaits the next release ripple). | 2026-07-17T04:15:32Z |
| U13 | NEW workflow `podcast-standing-check` (webhook + header cred + roster lookup + respond) | [Kimi x1] ledger truth-up U13 | verified | LIVE-PROVEN 2026-07-17, all four accept clauses, per spec line 263 — this corrects a stale tracking row; the underlying workflow already existed before last night, but nobody had actually run its required test battery until now. Six live test requests were fired at the real webhook: (1) no authorization header → HTTP 403 refusal; (2) a wrong authorization value → also HTTP 403, proving the actual secret value is checked, not merely its presence; (3) the operator's own real test identity → HTTP 200, correctly reports good standing as true; (4) the SAME correct email address but a WRONG last name (the specific two-part identity check this unit exists to prove) → HTTP 200, correctly refused as an unknown identity — proving the system checks BOTH the email and the last name together, not the email alone; (5) a fully unknown identity → correctly refused the same way; (6) the operator's own test row deliberately flipped to 'not in good standing,' same otherwise-correct identity → HTTP 200, correctly reports good standing as false with the reason given. Every one of the 4 authorized test requests left a matching log entry in the system's own record-keeping, confirmed by an exact before/after count. The test row's temporary 'not in good standing' flip was fully restored afterward, and independently re-confirmed as restored by a completely separate, later piece of testing that re-checked it fresh (see S58-U20's evidence) plus a system-wide check that zero rows anywhere are left in the wrong state. | 2026-07-17T12:01:55Z |
| U14 | `publish-proxy` transport in `podbean_publish.sh` (proxy → broker → local) | [Sonnet 5 x1] correct U14 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #609 (branch `feat/podbean-publish-proxy-s58-u14`, tip `7b207bcf`) merged into `origin/main` via merge commit `5020e2f0`, `git merge-base --is-ancestor 5020e2f0 origin/main` = true (fresh clone, re-fetched). PR #609's own check-run rollup: 23 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U15/U16 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U15 | Identity + endpoint provisioning (install.sh injection + credential checklist + validators) | [Sonnet 5 x1] correct U15 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #608 (branch `feat/s58-u15-podbean-publish-provisioning`, tip `9e115516`) merged into `origin/main` via merge commit `40a3ec32` -- this merge commit IS `origin/main`'s current tip, trivially an ancestor of itself, independently re-confirmed via `git rev-parse origin/main` = `40a3ec328b9186a39e8377e13272663872a3212f` (fresh clone, re-fetched). PR #608's own check-run rollup: 38 SUCCESS + 3 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U14/U16 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U16 | Pre-production standing gate in SKILL.md (Steps 0 + 1) + doctrine updates | [Sonnet 5 x1] correct U16 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #607 (branch `feat/s58-u16-standing-gate-proxy-doctrine`, tip `d2949984`) merged into `origin/main` via merge commit `58a59797`, `git merge-base --is-ancestor 58a59797 origin/main` = true (fresh clone, re-fetched). PR #607's own check-run rollup: 22 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U14/U15 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U17 | Repo tests for the new contract (payload-v2 builder, standing-block, identity-env-missing) | [Kimi x1] ledger truth-up U17 | verified | REPOSITORY-VERIFIED 2026-07-17 (this one is a code-and-automated-test proof, not a live-system test — the distinction matters for how it's phrased). Merge commit `c993f2b5` ('S58-U17 payload-v2 builder completeness tests,' scored 9.4) is confirmed to be a genuine ancestor of the current `main` branch (a repository comparison between that commit and the current tip of `main` shows zero commits are missing between them). Its own automated-test results, re-read directly from GitHub with pagination: 22 out of 22 checks passed, zero failures, including the version-bump check and the quality-control static-checks gate. The 9.4 quality score is stated directly in the merge commit's own message. | 2026-07-17T12:01:55Z |
| U18 | Fleet provisioning roll (ONE batch; OPERATOR'S OWN BOX FIRST) | — | pending | NOT STARTED. Gated on U14+U15. Operator box provisioned and proven BEFORE any client box. NO fleet roll outside this unit. | 2026-07-16T12:35Z |
| U19 | LIVE end-to-end proof, operator test channel (happy path) | — | pending | NOT STARTED. Requires all 5 QC 3.1 proofs incl. +1 on TEST channel AND +0 on two OTHER channels (never-comingle). | 2026-07-16T12:35Z |
| U20 | LIVE proof of the block (the money path) | — | pending | NOT STARTED. Requires all 6 QC 3.2 proofs + the pre-check leg. Flip ONLY the OPERATOR TEST row. | 2026-07-16T12:35Z |
| U21 | Release ripple + truth-gate close-out (ancestry + tags + ZERO integrity alarms + fresh n8n re-reads) | — | pending | NOT STARTED. Gates every `verified` row above. | 2026-07-16T12:35Z |

---

## BOOTSTRAP FINDING (2026-07-16T12:35Z) — NOTHING WAS ADOPTED

All three claimed in-flight workstreams were checked against primary sources and are
**ABSENT**. No unit is being rebuilt — there was nothing built to rebuild. Every unit
U1-U21 starts greenfield except U6 and U15, which EXTEND existing substrate (noted above).

`n8nWriterBusy = FALSE`. Most-recent workflow update across the whole instance is
`2026-07-15T05:51:00Z` (~30.7 h before this read). `TkL0rn2SH3q32SeB` updatedAt
`2026-07-14T01:28:11.384Z` (~59 h stale), versionId `808cd5cc-d4e3-4471-944a-6a54789b3a63`.
No workflow is being edited. The `TkL0rn2SH3q32SeB` queue is free to claim.

**Live security hole is OPEN right now:** `/webhook/podbean-publish` is ACTIVE and
UNAUTHENTICATED. This raises the urgency of D1 (auth-cutover window).

---

## LIVE-CALLER FINDING (2026-07-16T12:41Z) — SPEC SECTION 7's MIGRATION-RISK PREMISE IS FALSE

`GET /executions?workflowId=TkL0rn2SH3q32SeB` (fresh, HTTP 200) returned 3 retained executions:

| execution | startedAt | status | meaning |
|---|---|---|---|
| 91115 | 2026-07-16T12:38:08.877Z | success | **fired DURING this bootstrap pass, ~3 min after the survey began** |
| 87423 | 2026-07-14T01:28:23.054Z | success | prior live publish |
| 85051 | 2026-07-12T03:04:33.531Z | error | the `image_url = null` failure that spawned the GK-01 guard (matches spec 1.4) |

Execution 91115 node-run list (names only; no payload, no client data read) shows the
**FULL publish path ran to completion**: Webhook → Guard → IF passed → Compute Timestamp →
Podbean OAuth → Fetch Recent Episodes → Compute Next Episode Number → Set Config →
Download Audio → uploadAuthorize Audio → PUT Audio → Download Image → uploadAuthorize Image →
PUT Image → Set Upload Keys → **Podbean — Publish Episode** → IF Episode Created Successfully →
`lastNodeExecuted: Gmail — Success Notification`. Duration 12:38:08.877Z → 12:38:12.553Z.

**A real episode was published to Podbean minutes ago through an unauthenticated webhook,
with no standing gate, no identity check, and routing on the CALLER's raw `podcast_id`.**

Consequences the orchestrator must act on:
1. **Spec Section 7's "migration risk is near zero by construction" is CONTRADICTED.** Its
   reasoning covers Skill 58's `podbean_publish.sh` (which indeed publishes via no n8n
   transport). But the Skill 35 caller family fires `/webhook/podbean-publish` DIRECTLY and
   is demonstrably LIVE. There IS live client traffic to break.
2. **U4 (auth) is now a breaking change to a live, working caller.** Flipping auth without
   provisioning that caller first produces a 401 on a real episode publish. D1 is no longer a
   theoretical window — it is a live cutover. This is Trevor's decision (D1); do not self-decide.
3. **Executions are pruned** (only 3 retained), so this is a floor on traffic volume, not a
   census. A true caller census needs a retention-independent method.
4. Every episode published through this path today bypasses the entire security model this
   spec exists to build. That is the argument FOR flipping fast — and the reason the flip must
   be paired with same-session provisioning.

---

## FRESH LIVE RE-READ FINDING (2026-07-16T19:50Z) — U4-U11's GREENFIELD rows above are STALE

This pass's assignment was S58-U12-repo only (Lane 1 unit 1: the repo leg of U12). While
verifying U12's n8n leg (confirming the gate-test workflow's deletion), a fresh
`n8n_get_workflow(TkL0rn2SH3q32SeB, mode=structure)` then `mode=full` read (never
`mode=active`/`filtered`, and the two NEVER-PRINT workflows `BqRLOn8TP1wPaAzn` /
`COfgxe6HXRcWOleV` were not touched) shows the live workflow already carries, by node/graph
inspection: header-auth on the webhook (`Podcast Publish Gate` credential — U4 shape), a
"Standing Gate" node chain doing roster lookup + `effective_channel_id` routing (U5 shape), the
GK-01 guard extended with `contract_version`/`client_last_name`/`idempotency_key`/https-only/
length checks (U6 shape), `responseMode: responseNode` + four `Respond to Webhook` nodes on
every branch (U7 shape), an "Idempotency" node chain against a data table (U8 shape), a
`Podbean — Publish Episode` node whose status expression now reads
`publish_timestamp > now() ? 'future' : 'publish'` with an inline comment citing "U9 fix
2026-07-16" (U9 shape — supersedes the U9 row's "DEFECT CONFIRMED PRESENT" evidence, which
predates this), refusal-path Gmail nodes hardcoded to `trevor@blackceo.com` rather than the
client (U10 shape), and a "Media Preflight" HEAD-check node pair before the OAuth call (U11
shape). `versionCounter: 79` on the live read (i.e. 79 recorded edits) is consistent with a
completed multi-unit build, not a single edit.

**This is graph-shape evidence, not each unit's own accept-criteria proof** (e.g. U9's own
acceptance needs quoted before/after Podbean API reads of a real scheduled episode; U5's needs
three live refusal executions; U10's needs a refusal execution showing zero client email). The
rows above are deliberately left `pending` rather than flipped to `verified` — that determination
is each unit's own owner's job, done against its own numbered accept-criteria, not inferred from
this session's structural read. Flagging here only so the next agent does not re-build what
graph inspection shows already exists, and re-verifies against real executions before closing
any of U4-U11.

---

## N8N-LEG RE-READ ADVISORY (2026-07-17T05:45Z) — n8n-SIDE LEGS OF U2/U4/U5/U7/U8 REQUIRE OPERATOR-AUTHORIZED LIVE RE-READ

> **SUPERSEDED IN PART (2026-07-17):** this advisory was written before commit
> `25363b3f` (now on `origin/main`) verified the n8n-side legs of **U1, U3, U6, U9,
> U10, U11, U13** with real live-execution evidence — all seven rows read `verified`
> in the UNIT ROWS table above, which is the current status. The re-read requirement
> below now applies ONLY to **U2, U4, U5, U7, U8**. The original advisory text is
> kept for the audit trail; do not re-gate the seven already-verified rows on it.

The repo-leg truth-up for U12/U14/U15/U16 landed on `origin/main` via PR #614's merge
(commit `34dce869`, re-QC round 2, score 9.2): all four rows read `verified` with
merge-commit ancestry + per-PR check-run rollups cited in-row. This addendum survives
as its own note because one requirement is still open:

**No ledger pass since the live cutover has had live n8n API access in THIS lane.** The
n8n-side legs of U1..U11 and U13 — including the n8n-leg claims embedded in U12's row
above and the 19:50Z structural finding — MUST be re-read fresh from the live n8n API
by an operator-authorized session before any of those rows move. Graph-shape evidence
is not accept-criteria proof. **(As of commit `25363b3f` this re-read has happened for
U1, U3, U6, U9, U10, U11, U13; it remains open only for U2, U4, U5, U7, U8.)**

Rows deliberately left open: U2, U4, U5, U7, U8 (n8n-side legs pending the
operator-authorized re-read above), U18–U20 (operator-gated fleet provisioning and
live proofs), U21 (close-out). U17's row was flipped to `verified` by the ledger's
owning pass in commit `25363b3f` (repo tests merged via PR #613, merge `c993f2b5`,
scored 9.4).

---

## STRUCTURE-MODE RE-VERIFICATION PASS (2026-07-18T05:09:32Z) — U2 CLOSES, U4/U5/U7/U8 REMAIN OPEN

> **SUPERSEDED IN PART (2026-07-18):** this pass was scoped structure-mode-only for
> every n8n read (no workflow node parameters, no credential/OAuth fields, no live
> webhook-execution firing). Under that scope, **U2** — a data-table check, not a
> workflow node-parameter check — was fully re-provable and is now `verified` above.
> **U4, U5, U7, and U8 remain open.** Each one's accept text names a fact that only
> lives inside a workflow node's *parameters* (webhook `authentication`/`credentials`
> wiring for U4; the roster-lookup node's table target + the downstream
> `effective_channel_id` expression for U5; the webhook's `responseMode` setting +
> response-body shape for U7; the idempotency node chain's table target for U8) —
> `n8n_get_workflow(TkL0rn2SH3q32SeB, mode=structure)` returns node `id`/`name`/`type`/
> `position`/`disabled` and connections ONLY, never parameters, by design. A fresh
> structure-mode re-read this pass DID confirm, as topology (not as accept-criteria
> proof): a "Standing Gate" node chain (roster-lookup `dataTable` node → verdict →
> IF → refusal branch with Gmail + Respond + Idempotency-mark) sits in the live
> main path (U5 shape); an "Idempotency" node chain (lookup → verdict → two IFs →
> upsert/mark-in-flight/mark-refused/mark-completed/mark-failed, all `dataTable`
> nodes) sits first in the live main path (U8 shape); and 7 `respondToWebhook` nodes
> (`Respond — Entry Guard Refused`, `Respond — Standing Identity Gate Refused`,
> `Respond — Media Preflight Refused`, `Respond — Idempotent Replay`,
> `Respond — Idempotency In Flight`, `Respond — Publish Success`,
> `Respond — Publish Failure`) are wired as the terminal node of every branch (U7
> shape). This is graph-shape evidence only, per this ledger's own prior finding —
> it does not, by itself, prove any of U4/U5/U7/U8's specific named accept-criterion.
> Confirming those requires either a parameter-level workflow read (out of this
> pass's structure-mode-only scope) or a live-execution proof (also out of scope —
> no webhook test calls were fired this pass). **CANNOT-VERIFY this pass; rows left
> `pending`, unchanged.** `62EeUqT5Da63U4Kh` (2 real in-flight jobs), `BqRLOn8TP1wPaAzn`,
> and `COfgxe6HXRcWOleV` were not read in any mode. Channel `vN6EJlUKjf6G` was not
> encountered in this pass's roster read.
