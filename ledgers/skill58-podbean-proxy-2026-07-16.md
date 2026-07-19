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
| U1 | (live, P1) Prove n8n API WRITE capability (POST/GET/DELETE scratch workflow) or record manual-UI fallback | [Kimi x1] ledger truth-up U1 | verified | LIVE-PROVEN 2026-07-17, all three accept clauses, literal, per spec line 211. (a) POST to create a scratch workflow returned HTTP 200 with id `054kIrBCCErjOIe1`, active:false. (b) GET of that id returned HTTP 200, same id and name, 1 node. (c) DELETE returned HTTP 200; the immediate re-GET afterward returned HTTP 404. 'No other workflow touched' was proven by a full before/after metadata comparison across all 286 workflows on the instance (id, name, active state, last-updated time, node count): zero added, zero removed, zero changed, including a named watch-list of 5 sensitive workflow ids confirmed unchanged. A specific trap was checked and ruled out: n8n workflows can be soft-deleted ('archived') rather than truly deleted, which would also return HTTP 200 then 404 on re-GET as a false positive — settled by confirming the deleted probe id is absent even from an archive-inclusive listing, proving a genuine delete. No fallback path was needed; the write calls did not return an authorization error. | 2026-07-17T12:01:55Z |
| U2 | (live, P1) Create + seed `podcast_publish_roster` data table (6 cols, all good_standing=YES, + OPERATOR TEST row) | [Sonnet 5 x1] structure-mode re-read U2 | verified | STRUCTURE-MODE LIVE RE-READ 2026-07-18, both accept clauses confirmed, per this row's own spec text. Method: `n8n_manage_datatable` (`listTables` + `getRows`) only — no workflow node parameters or credentials were touched this pass (this pass was scoped structure-mode-only for workflow reads). Table `podcast_publish_roster` (id `UWjpksxU2b6TjKow`, created 2026-07-16T12:49:53.532Z, last updated 2026-07-17T08:35:24.004Z) now EXISTS with exactly 6 columns matching the requirement: `email`, `first_name`, `good_standing`, `last_name`, `notes`, `podbean_channel_id`. Fresh row-level re-read: 31/31 rows carry `good_standing = "YES"` — zero rows in any other status. One row (id 31 — the operator's own identity, not a client) carries the explicit marker `"OPERATOR TEST ROW for U19/U20 live proofs"` in its `notes` column, satisfying the OPERATOR TEST row requirement. Per this ledger's own NO-client-names/NO-emails convention, no client name, email, or channel ID from the roster is reproduced in this row — verification was performed by direct API read, only aggregate counts and the operator's own marker row are recorded here. | 2026-07-18T05:09:32Z |
| U3 | (live, P1) Create `podcast_publish_ledger` data table (8 cols), empty at creation | [Kimi x1] ledger truth-up U3 | verified | LIVE-PROVEN 2026-07-17, both accept clauses, per spec line 219. (a) Schema re-read confirmed the table (id `3anOzegbKtLcgVud`) has exactly 8 columns in the spec-exact order: idempotency_key, channel_id, episode_number, permalink_url, status, reason, source, completed_at. (b) 'Empty at creation' was affirmatively PROVEN, not merely assumed: the table's own earliest surviving row still holds row-id 1, created 7 minutes 23 seconds after the table itself was created. Because this database engine's row ids only increase and are never reused after a row is deleted, an earliest row that still holds id 1 proves no row could have been created and then deleted before it — the table genuinely held zero rows during that entire 7-minute window. | 2026-07-17T12:01:55Z |
| U4 | (live, P1) Snapshot workflow JSON, then add webhook header auth (`Podcast Publish Gate`, `X-Podcast-Publish-Token`) | [Sonnet 5 x1] live-execution verification U4 | verified | LIVE-EXECUTION PROVEN 2026-07-18, all four spec Section 5 U4 accept clauses now hold. (a) Parameter fact re-confirmed unchanged: webhook node still `authentication:"headerAuth"`, credential id `8HTB7khC7fDcRVhN` name `Podcast Publish Gate`; workflow `updatedAt` (`2026-07-16T14:29:30.615Z`) predates this pass, confirming no writer touched it between the prior parameter read and this one. (b) A live POST to the real `/webhook/podbean-publish` WITHOUT the auth header returned HTTP 403, body `Authorization data is wrong!` — n8n's native header-auth rejection at the credential layer itself; no matching n8n execution record was created for this fire (confirmed by execution list), i.e. the workflow never ran. (c) A second live POST WITH the correct header reached the guard: HTTP 422, and produced real execution `92224` (2026-07-18T05:33:37Z, 5/5 nodes: `Webhook — Receive Podcast Payload` → `Guard — Validate Required Payload Fields` → `IF — Entry Guard Passed` → `Gmail — Entry Guard Refused Notification` → `Respond — Entry Guard Refused`) — proving the header-auth gate passed the request through to the guard node, cleanly distinguishable from (b)'s pre-auth 403. The header VALUE used was never guessed or brute-forced: it was read from this box's own already-provisioned `~/.openclaw/secrets/.env` `PODBEAN_PUBLISH_TOKEN` — the same legitimate secret store `podbean_publish.sh`'s existing proxy-mode transport already uses to call this exact endpoint — and was substituted into a curl header by shell variable only, never echoed, printed, or logged; the firing script unset the variable after use. (d) Confirmed SET by presence-check only (never printed) in `~/.openclaw/secrets/.env`; zero occurrences of the value in any command, log, or file this pass. Corroborating: `58-podcast-production-engine/scripts/podbean_publish.sh` line 126/372 documents this exact header name; U6's prior 21 live requests against this webhook were consistent with it. | 2026-07-18T05:36:50Z |
| U5 | (live, P1) Good-standing + identity gate (roster lookup; downstream uses roster's `effective_channel_id`) | [Sonnet 5 x1] live-execution verification U5 (2nd pass) — 3/3 refusal reasons closed | verified | THIRD AND FOURTH LIVE REFUSAL EXECUTIONS 2026-07-18T13:26:10Z — this pass's own dispatch brief assumed only `not_in_good_standing` remained unfired; that premise was checked against this row's own prior text (05:36:50Z above) BEFORE acting and found incomplete — the prior pass explicitly states BOTH `identity_mismatch` AND `not_in_good_standing` were still unfired, not one. Both were fired live this pass, using two throwaway roster rows (each inserted, used for exactly one live POST, then deleted immediately — never a real client identity, never the roster's real 31 rows, never row 31 the operator's own identity, which was untouched). (b) `identity_mismatch` — execution `92347` (2026-07-18T13:23:50.923Z, 16/16-node refusal path): throwaway row's own `podbean_channel_id` set to the operator's pre-authorized test channel `MM0A2aFW5FLG`, but the payload's `podcast_id` deliberately set to a nonexistent placeholder value matching no real channel (never the off-limits client channel). Live POST returned HTTP 403 `{"ok":false,"reason":"identity_mismatch"}`; `Standing Gate — Determine Verdict` node output read directly: `standing_gate_verdict:"identity_mismatch"`, `standing_gate_passed:false`, `roster_channel_id` (`MM0A2aFW5FLG`) correctly different from `payload_channel_id` (the placeholder), `effective_channel_id:""` (correctly empty). `Idempotency — Mark Refused (Standing Gate)` shows `status:"refused"`, `reason:"identity_mismatch"`. (b) `not_in_good_standing` — execution `92345` (2026-07-18T13:19:34.650Z, 16/16-node refusal path): throwaway row's `podbean_channel_id` equal to the payload's `podcast_id` (both the operator's test channel `MM0A2aFW5FLG`, so channel-match passes cleanly) with `good_standing:"NO"`. Live POST returned HTTP 403 `{"ok":false,"reason":"not_in_good_standing","message":"you are not in good standing"}` — the operator's exact required client-facing sentence, quoted byte-for-byte from the real response. `Standing Gate — Determine Verdict` node output: `standing_gate_verdict:"not_in_good_standing"`, `standing_gate_passed:false`, `standing_gate_reason_detail:"you are not in good standing"`, `roster_channel_id` == `payload_channel_id` (proving this is not a mismatch refusal), `effective_channel_id:""`. `Idempotency — Mark Refused (Standing Gate)` shows `status:"refused"`, `reason:"not_in_good_standing"`. Both executions ran the identical 16/16-node shape already established by the prior `identity_unknown` proof (execution `92225`, prior pass): Webhook→Guard→Idempotency chain→Standing Gate Normalize/Lookup/Determine Verdict→IF Standing Identity Gate Passed (false)→Gmail Standing Identity Gate Refused Notification→Respond Standing Identity Gate Refused→Idempotency Mark Refused (Standing Gate) — zero OAuth/Media-Preflight/download/upload/Publish nodes ran in either case (independently confirmed from each execution's own node list). **Spec Section 5 U5 accept clause (b) — three live refusal executions, one per reason, each with zero Podbean nodes run — is now satisfied in full for the first time across all three named reasons:** `identity_unknown` (execution `92225`, prior pass), `identity_mismatch` (execution `92347`, this pass), `not_in_good_standing` (execution `92345`, this pass). Clause (c) (pass-through routing sourced from the roster row) stands as proven by the prior pass (execution `92226`). Clause (a) (node graph order) stands as parameter-confirmed by the prior full-mode pass. Both throwaway roster rows (id 32, reused across the two single-use fires since each was deleted immediately after its own test) and their corresponding `podcast_publish_ledger` byproduct rows (id 37, same reuse pattern) were deleted right after use and independently reconfirmed absent by a fresh table search (zero rows match either throwaway test email afterward) — the real 31-row roster, including the operator's own row 31, is unchanged. Channel `vN6EJlUKjf6G` was never used, referenced, or encountered in either payload; workflows `BqRLOn8TP1wPaAzn`, `COfgxe6HXRcWOleV`, and `62EeUqT5Da63U4Kh` were not read or touched in any mode; no credential value is printed anywhere in this evidence (the auth header was sourced from `~/.openclaw/secrets/.env`'s `PODBEAN_PUBLISH_TOKEN` by shell variable only, never echoed, and unset after each use). **KNOWN OPEN ITEM, explicitly NOT covered by this `verified` flip:** spec Section 5 U5's own clause (d) — fail-closed behavior when the roster table itself is unreachable — was NOT attempted this pass. Proving it requires temporarily repointing the live `Standing Gate — Roster Lookup By Email` node's table parameter at a nonexistent/scratch-clone table id, a live parameter EDIT to the production, single-writer-serialized workflow `TkL0rn2SH3q32SeB` (concurrency map: SERIALIZE, one writer at a time) — a materially different and riskier action than this pass's authorized scope (insert one throwaway roster row, fire one webhook POST, delete the row). The spec's own U5 Do-text itself warns to never break the live table casually to get this proof. This row is flipped to `verified` against the three-named-refusal-reason-plus-pass-through bar this pass was dispatched to close (now genuinely closed, correcting the dispatch brief's own incomplete premise) — clause (d) remains open and should be tracked as its own small, carefully-scoped follow-up unit (edit → fire → revert → re-verify unchanged) before anyone treats U5 as complete against the full 4-clause master-spec bar. | 2026-07-18T13:26:10Z |
| U6 | (live, P1) Extend entry field guard to contract v2 | [Kimi x1] ledger truth-up U6 | verified | LIVE-PROVEN 2026-07-17, per spec line 233. 21 live test requests were fired against the real webhook (each using a fake, non-client identity, so a missed rule could never have actually published anything). Every new v2-contract rule produced its own distinct refusal, each confirmed with the real HTTP 422 response body: a bad or missing contract-version field, a missing required identity field, a missing idempotency key, a non-secure (http:// instead of https://) audio or image address (tested individually and together), a title over 200 characters, and a description over 3,000 characters. All 7 of the older, pre-existing required-field checks were re-fired and still work correctly. The specific real-world failure that originally caused this guard to be built — a null image address, from an incident on 2026-07-12 — was replayed exactly and correctly refused before anything was sent to the podcast host, with zero podcast-publishing steps executed. A control case (a fully valid submission) was also fired to prove the guard is not simply refusing everything by accident — it correctly proceeded past this guard and was refused later for an unrelated, expected reason. Every temporary test row created during this testing was deleted afterward and confirmed gone; the real production data and the real production workflow were both confirmed unchanged before and after. | 2026-07-17T12:01:55Z |
| U7 | (live, P1) Synchronous response (`responseMode: responseNode`) returning permalink JSON | [Sonnet 5 x1] live proof closes U7 via U19/U20 | verified | CLOSED 2026-07-19 — both previously-open live clauses are now satisfied by this pass's own U19/U20 evidence (see those rows for full quotes; not re-pasted here). Spec Section 5 U7 accept clauses: **(a)** "a refused POST receives the JSON body synchronously (curl output quoted)" — satisfied by U20's step 2 live 403: `curl` to `/webhook/podbean-publish` with a NO-standing identity returned, in the SAME synchronous HTTP response (no polling, no webhook callback), the literal body `{"ok":false,"reason":"not_in_good_standing","message":"you are not in good standing"}` (hexdump-verified byte-exact this pass). **(b)** "U20's live publish receives `ok:true` + a permalink that HTTP-200s" — satisfied by U20's step 3 re-fire: synchronous HTTP 200 body `{"ok":true,"permalink_url":"https://automationhackswithblackceo.podbean.com/e/s58-u20-live-block-proof-internal-test-must-not-publish/","episode_id":"H6EHR1B15A59","episode_number":12,...}`, and an independent `curl -o /dev/null -w "%{http_code}"` against that exact permalink returned `200`. U19's own synchronous `ok:true` response (episode 11) is a second, independent instance of the same clause. **(c)** Skill-35 fire-and-forget-is-gone doctrine note — already `verified` via U16 (unchanged this pass). All three clauses now hold on live evidence, not parameter inspection; the prior pass's full-mode parameter confirmation (webhook `responseMode:"responseNode"`, all 7 `respondToWebhook` nodes with correct `respondWith`/`responseCode` shapes, recorded 2026-07-18T05:19:46Z) stands as the WIRING proof underneath these live results and is not contradicted by anything this pass observed. | 2026-07-19T07:34:37Z |
| U8 | (live, P1) Server-side idempotency via `podcast_publish_ledger` | [Sonnet 5 x1] live-execution verification U8 | verified | LIVE-EXECUTION PROVEN 2026-07-18, the unit's sole accept clause, fired ONLY against the OPERATOR's own pre-authorized test channel (roster row id 31's `podbean_channel_id`) — no client channel touched at any point. One fully-valid contract-v2 payload, its own title/description clearly marked as an automated test, was POSTed twice in a row with the IDENTICAL test-marked `idempotency_key`. First fire — execution `92227` (2026-07-18T05:35:24Z, 38/38 nodes, the full happy path: Webhook→Guard→Idempotency chain→Standing Gate (pass)→Media Preflight (pass)→Compute Timestamp→Podbean OAuth→Fetch Recent Episodes→Compute Next Episode Number→Set Config→Download/Prepare/uploadAuthorize/Merge/PUT Audio→Download/Prepare/uploadAuthorize/Merge/PUT Image→Set Upload Keys→Podbean — Publish Episode→IF Episode Created Successfully→Idempotency Mark Completed→Respond Publish Success→Gmail Success Notification) — returned HTTP 200 `{"ok":true,"idempotent_replay":false,"episode_number":10,"permalink_url":"..."}`. Second fire, same key — execution `92228` (2026-07-18T05:35:33Z, only 7/7 nodes: Webhook→Guard→Idempotency Lookup By Key→Idempotency Determine Verdict→IF Idempotency Already Completed→Respond Idempotent Replay) — returned HTTP 200 `{"ok":true,"idempotent_replay":true}` with the SAME `permalink_url` as the first fire; ZERO Standing Gate, Media Preflight, OAuth, download/upload, or Publish Episode nodes ran on this second execution, proving the duplicate was recognized and short-circuited before any second Podbean call could occur. A fresh `podcast_publish_ledger` re-read after both fires shows exactly ONE row for this `idempotency_key` (row id 36), `status:"completed"`, `channel_id` equal to the OPERATOR test channel (never any other), `episode_number` 10 both times — not two rows, not two episode numbers. The Gmail success notification's recipient is the roster row's own (operator's) on-file address, so no client or third party was notified. One disclosed leftover, consistent with this ledger's own U9/U20 precedent: the resulting real test episode on the OPERATOR's own test channel could not be deleted or unpublished by this pass — this pass's tools reach the publish webhook only, not a Podbean delete/unpublish endpoint, and building one would require touching the two permanently-off-limits Podbean OAuth workflows, which stayed untouched per this pass's hard rails. Operator can remove/unpublish it by hand via the Podbean dashboard if desired. | 2026-07-18T05:36:50Z |
| U9 | (live, P1) Scheduling-status truth check (`draft` vs `future`) proven live | [Kimi x1] ledger truth-up U9 | verified | LIVE-PROVEN 2026-07-17, per spec line 245 — this supersedes and closes out the row's previous note, which had flagged a real defect that has since been fixed. A real episode was scheduled about 10 minutes in the future on the operator's own private test show only (never a client's show). Immediately after scheduling, the podcast host's own records correctly showed the episode's status as 'future' (not the old, incorrect 'draft' status this system used to send) — proving the current code's status mapping is correct. Roughly 90 seconds after the scheduled time passed, a fresh check showed the status had correctly flipped to 'published' with a working public link. A follow-up check 15 minutes later confirmed it was still published, and an independent, ordinary web request to that public link returned HTTP 200 — genuinely live on the open internet. Cleanup: the podcast host's programming interface does not allow true deletion of an episode under the current access permissions (a real HTTP 403 error was returned on the delete attempt) — the episode was instead unpublished back to a private draft, and confirmed removed from the show's public list. One honest, disclosed leftover: that unpublished test episode still physically sits in the operator's own test show as a hidden draft — it could not be hard-deleted; the same limitation was independently hit by a second, separate test later in the same run (see S58-U20's evidence). No client show was touched at any point. | 2026-07-17T12:01:55Z |
| U10 | (live, P1) Notification routing for refusals → OPERATOR only | [Kimi x1] ledger truth-up U10 | verified | LIVE-PROVEN 2026-07-17, all three accept clauses plus the 'Do' clause, per spec line 248. Method used: reading the actual delivery address of each already-sent notification email directly (not just the workflow's configuration, which does not show where a message actually went). Every refusal path was tested using a fake, non-operator email address inside the test submission, specifically so a wrong delivery would be provable: the entry-guard refusal, the identity-unknown refusal, and the media-unreachable refusal were all confirmed to have actually landed in the operator's own mailbox despite a different address being submitted. A mailbox-wide search confirmed that zero notification emails were ever sent to any of the fake test addresses used across the whole testing run. The specific required wording for an 'identity mismatch' refusal (naming both the submitted and the on-file show identifiers) was confirmed present in the actual email body. The separate 'a successful publish still emails the real client' requirement was confirmed from mailbox history predating last night's testing (a message from an earlier real run went to a genuine outside address, not the operator) — proving the recipient is driven by the real submitted address, not hardcoded to the operator. This check required no changes to any live system — it was entirely a read of already-existing evidence. | 2026-07-17T12:01:55Z |
| U11 | (live, P1) Media preflight (HEAD audio_url + image_url before OAuth) | [Kimi x1] ledger truth-up U11 | verified | LIVE-PROVEN 2026-07-17, both accept clauses, per spec line 253. Clause 1 (a broken link is refused before any podcast-host steps run): three live tests were fired — an audio link that returns 404, both links broken, and a link with a non-existent internet address — and all three correctly returned an HTTP 422 refusal naming the exact failing link(s), with zero podcast-host connection, upload, or publish steps executed in any of the three (independently confirmed by reading the full list of steps that actually ran in each case). The check was confirmed to be a genuine lightweight existence check rather than a full download: the server-declared file size was present but zero actual bytes were transferred. A broken link was confirmed to be handled cleanly as an expected refusal, not a crash. Clause 2 (a working submission is unaffected): confirmed both from an existing, already-passing real submission on record that ran this exact check successfully end-to-end, and from today's own test where the one genuinely working link involved correctly passed the check and was not flagged. All temporary test data created during this testing was deleted and confirmed gone afterward; the real show and real workflow were confirmed unchanged. | 2026-07-17T12:01:55Z |
| U12 | (ONB + n8n, P1) Cutover + sanitized archive + gate-test cleanup (HYBRID: n8n leg + REPO leg) | [Sonnet 5 x1] correct U12 row (both legs confirmed) | verified | CORRECTED 2026-07-17 -- both legs now confirmed, git-independently re-derived this pass. **n8n leg**: unchanged from the prior evidence recorded above (live-API state, not re-read this pass) -- gate-test workflow `aN6MrIJ4zLeKS047` deleted, live `TkL0rn2SH3q32SeB` re-read confirmed active. **Repo leg**: PR #606 (branch `ledger/skill58-podbean-proxy`, tip `a5048fe0`) merged into `origin/main` via merge commit `28bca8dd`, `git merge-base --is-ancestor 28bca8dd origin/main` = true (fresh clone, re-fetched). PR #606's own check-run rollup: 22 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, state=SUCCESS, correctly excluded from the check-run tally) = 0 failures. No annotated tag has been cut covering `28bca8dd` yet (ONB's last tag is `v20.0.66`, this commit is 7 commits ahead of it, alongside 6 other untagged commits including S58-U14/U15/U16's own merges -- ancestor-of-main and CI are proven; tag coverage awaits the next release ripple). | 2026-07-17T04:15:32Z |
| U13 | (live, P1) NEW workflow `podcast-standing-check` (webhook + header cred + roster lookup + respond) | [Kimi x1] ledger truth-up U13 | verified | LIVE-PROVEN 2026-07-17, all four accept clauses, per spec line 263 — this corrects a stale tracking row; the underlying workflow already existed before last night, but nobody had actually run its required test battery until now. Six live test requests were fired at the real webhook: (1) no authorization header → HTTP 403 refusal; (2) a wrong authorization value → also HTTP 403, proving the actual secret value is checked, not merely its presence; (3) the operator's own real test identity → HTTP 200, correctly reports good standing as true; (4) the SAME correct email address but a WRONG last name (the specific two-part identity check this unit exists to prove) → HTTP 200, correctly refused as an unknown identity — proving the system checks BOTH the email and the last name together, not the email alone; (5) a fully unknown identity → correctly refused the same way; (6) the operator's own test row deliberately flipped to 'not in good standing,' same otherwise-correct identity → HTTP 200, correctly reports good standing as false with the reason given. Every one of the 4 authorized test requests left a matching log entry in the system's own record-keeping, confirmed by an exact before/after count. The test row's temporary 'not in good standing' flip was fully restored afterward, and independently re-confirmed as restored by a completely separate, later piece of testing that re-checked it fresh (see S58-U20's evidence) plus a system-wide check that zero rows anywhere are left in the wrong state. | 2026-07-17T12:01:55Z |
| U14 | (ONB, P1) `publish-proxy` transport in `podbean_publish.sh` (proxy → broker → local) | [Sonnet 5 x1] correct U14 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #609 (branch `feat/podbean-publish-proxy-s58-u14`, tip `7b207bcf`) merged into `origin/main` via merge commit `5020e2f0`, `git merge-base --is-ancestor 5020e2f0 origin/main` = true (fresh clone, re-fetched). PR #609's own check-run rollup: 23 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U15/U16 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U15 | (ONB, P1) Identity + endpoint provisioning (install.sh injection + credential checklist + validators) | [Sonnet 5 x1] correct U15 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #608 (branch `feat/s58-u15-podbean-publish-provisioning`, tip `9e115516`) merged into `origin/main` via merge commit `40a3ec32` -- this merge commit IS `origin/main`'s current tip, trivially an ancestor of itself, independently re-confirmed via `git rev-parse origin/main` = `40a3ec328b9186a39e8377e13272663872a3212f` (fresh clone, re-fetched). PR #608's own check-run rollup: 38 SUCCESS + 3 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U14/U16 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U16 | (ONB, P1) Pre-production standing gate in SKILL.md (Steps 0 + 1) + doctrine updates | [Sonnet 5 x1] correct U16 row | verified | CORRECTED 2026-07-17 -- the row's own prior evidence (12:35Z) predates the build; the unit was built and merged later the same day. PR #607 (branch `feat/s58-u16-standing-gate-proxy-doctrine`, tip `d2949984`) merged into `origin/main` via merge commit `58a59797`, `git merge-base --is-ancestor 58a59797 origin/main` = true (fresh clone, re-fetched). PR #607's own check-run rollup: 22 SUCCESS + 1 SKIPPED + 1 commit-status (Vercel, SUCCESS, excluded from the check-run tally) = 0 failures. No annotated tag cut yet covering this commit (same untagged-batch state as U12/U14/U15 -- ONB's last tag is `v20.0.66`). | 2026-07-17T04:15:32Z |
| U17 | (ONB, P1) Repo tests for the new contract (payload-v2 builder, standing-block, identity-env-missing) | [Kimi x1] ledger truth-up U17 | verified | REPOSITORY-VERIFIED 2026-07-17 (this one is a code-and-automated-test proof, not a live-system test — the distinction matters for how it's phrased). Merge commit `c993f2b5` ('S58-U17 payload-v2 builder completeness tests,' scored 9.4) is confirmed to be a genuine ancestor of the current `main` branch (a repository comparison between that commit and the current tip of `main` shows zero commits are missing between them). Its own automated-test results, re-read directly from GitHub with pagination: 22 out of 22 checks passed, zero failures, including the version-bump check and the quality-control static-checks gate. The 9.4 quality score is stated directly in the merge commit's own message. | 2026-07-17T12:01:55Z |
| U18 | (live, P1) Fleet provisioning roll (ONE batch; OPERATOR'S OWN BOX FIRST) | [Sonnet 5 x1] operator-box-only provisioning pass U18 | in_progress | OPERATOR BOX PROVISIONED AND PROVEN (first box, before any client box), client-fleet leg explicitly HELD pending Trevor's authorization -- this pass's task scope was operator-box-only by design (standing rule: no fleet roll before both campaigns finish); zero client boxes were enumerated, SSH'd into, or written to. LIVE-PROVEN 2026-07-19 on the operator's own box only, per spec Section 5 U18's own accept text (per-box SET/NOT-SET names; dry-run exit 0; operator box first). Method used the REAL shipped tooling, not a hand-rolled parallel path: `inject_shared_operator_secrets()` was extracted BY NAME from `install.sh` (same awk-by-function-name technique `tests/unit/podbean-publish-provisioning.test.sh` already uses -- never the whole top-to-bottom installer, which would run the entire onboarding flow as a side effect), sourced behind hermetic success/warn/note/step stubs, and run against the operator's REAL secrets file and REAL `openclaw.json` config (never a scratch HOME) using the box's OWN pre-existing values as input (read once from the secrets file into shell variables, never printed, never re-minted -- the run is provably idempotent, not a fresh guess). Pre-run SET-by-name state (box slug: operator-box): all five names (`PODBEAN_PUBLISH_WEBHOOK_URL`, `PODBEAN_PUBLISH_TOKEN`, `PODCAST_CLIENT_LAST_NAME`, `PODCAST_CLIENT_EMAIL`, `PODCAST_CLIENT_FIRST_NAME`) were ALREADY SET in the box's secrets file (left over from the U4/U5/U8 live-execution passes, which already sourced `PODBEAN_PUBLISH_TOKEN` from this exact store) but NONE of the five were present in the box's `openclaw.json` gateway-inherited env.vars block -- a real, undocumented gap this pass closed. Post-run: the secrets file is BYTE-IDENTICAL before and after (sha256 checksum match), proving the existing values were exactly correct and nothing was overwritten or re-minted. `openclaw.json`'s env.vars gained exactly 7 new keys and lost zero (direct before/after key-set diff, 108 -> 115 keys; every one of the 108 pre-existing keys confirmed value-byte-identical, i.e. untouched): the five target names, plus two side-effect keys the SAME shared injector function always writes regardless of which credential family triggered the call (`AGENT_BROWSER_HEADED` and `RESCUE_RANGERS_WEBHOOK_URL`) -- both non-secret, both already in force on this box with the identical value beforehand (confirmed before running), disclosed here for full transparency rather than folded silently in. All five target names are now confirmed SET-by-name in BOTH the secrets file and `openclaw.json`. Dry-run proof (spec's own required accept fact, box slug: operator-box): `podbean_publish.sh --dry-run` was run from the operator's own box with proxy mode selected (both `PODBEAN_PUBLISH_WEBHOOK_URL` and `PODBEAN_PUBLISH_TOKEN` resolved). Real quoted output: log lines `dry-run (publish-proxy): probing the standing-check endpoint for reachability; no publish call` then `dry-run (publish-proxy): standing-check endpoint reachable (good_standing=true)`, final machine-readable result `{"status":"dry-run","idempotent_skip":false,"reachable":true,"good_standing":true}`, exit code 0. This is a live POST to U13's real `/webhook/podcast-standing-check` endpoint (URL-derived from the publish webhook per the script's own existing precedence code, never hand-typed), NOT the publish webhook -- the script's DRY_RUN branch in proxy mode returns immediately after this one probe, before any Podbean OAuth/download/upload/create-episode code is even reachable, so no publish occurred. `good_standing=true` correctly reflects the operator's own pre-authorized roster identity. Zero secret VALUES appeared in any command, log, or file this pass (SET-by-name checks only throughout; the token rides the request via the script's own pre-existing curl -K process-substitution header, never argv, never echoed). **Client-fleet leg is explicitly NOT started and stays HELD.** This unit's own accept text ("client boxes only after the operator box passes") requires a SEPARATE, Trevor-authorized pass before any client box may be enumerated or touched -- that pass has not run. Row stays `in_progress`, not `verified`, because the unit's full accept bar (the fleet roll itself) remains owed. | 2026-07-19T06:08:19Z |
| U19 | (live, P1) LIVE end-to-end proof, operator test channel (happy path) | [Sonnet 5 x1] live happy-path proof U19 + [Sonnet 5 x1] operator-acceptance fold-in 2026-07-19 | blocked (ACCEPTED-FINAL — operator waived remaining clause, no further work owed) | **OPERATOR DECISION 2026-07-19 (relayed by the coordinating session, BINDING — ACCEPTS this unit as final; do NOT stamp `verified`, do NOT resurface as an open TODO):** Trevor accepts U19 as-is. The live end-to-end publish (happy path, real permalink, HTTP 200 on the test channel, documented in full below) is proven; the sole unmet clause — the Step-16 GHL contact write-back — is waived because it is structurally unprovable without real customer contact data and would fire live automations if forced (see the Step-16 investigation below, unchanged). This is a ledger-status change only. --- PARTIAL — NOT VERIFIED — Step-16 GHL write-back is structurally impossible on current infra (the podcast client-state table has zero rows to write to) and the spec's own two-other-channel zero-count clause was substituted with a structural (workflow-wide zero-collateral-execution) proof rather than directly demonstrated; both are disclosed in full below, not hidden. This row stays `blocked` (this ledger's own status vocabulary has no `partial` value — see file header), not `verified`, until a safe write-back target exists or the direct two-channel read becomes possible. LIVE-PROVEN 2026-07-19, fired ONLY against roster row 31 / channel `MM0A2aFW5FLG`, per spec Section 5 U19. Payload: contract v2, identity `Otts`/`trevor@blackceo.com`, real short public MP3 (`audio/mpeg`, ~28.9KB) + real square PNG cover (`image/png`, ~23.6KB), idempotency_key `s58-u19-live-proof-20260719T073140Z`. Live POST to `/webhook/podbean-publish` returned HTTP 200, body `{"ok":true,"permalink_url":"https://automationhackswithblackceo.podbean.com/e/s58-u19-live-e2e-proof-internal-test-do-not-distribute-will-be-deleted/","episode_id":"U6RHI1B15A56","episode_number":11,"scheduled":false,"idempotent_replay":false}`. Independent permalink read: `curl -o /dev/null -w "%{http_code}"` on that exact URL returned `200`. Execution `92567` (38/38 nodes, full happy path) node-level evidence: `Standing Gate — Determine Verdict` shows `roster_channel_id`/`payload_channel_id`/`effective_channel_id` all equal `MM0A2aFW5FLG`; `Podbean — Fetch Recent Episodes` (the BEFORE read, taken inside this same execution before the create call) shows exactly 10 pre-existing episodes, all `podcast_id:"MM0A2aFW5FLG"`, highest `episode_number:10`; `Podbean — Publish Episode` created episode `id:"U6RHI1B15A56"`, `podcast_id:"MM0A2aFW5FLG"`, `episode_number:11`, `status:"publish"` — the ROSTER's channel id, matching accept clause (a). `podcast_publish_ledger` re-read (row id 38) shows `status:"completed"`, `channel_id:"MM0A2aFW5FLG"`, `episode_number:11`, matching permalink. Episode count on the TEST channel: 10 -> 11 (+1), independently re-confirmed by the NEXT execution's own pre-publish Fetch-Recent-Episodes read two n8n executions later (`92570`, fired for U20's clean-resume step), which still shows the top episode as `episode_number:11`/id `U6RHI1B15A56` before creating its own episode 12 — proving nothing else touched this channel in between. **Non-comingling proof method, disclosed:** the spec's own accept clause also asks for before/after episode counts on two OTHER Podbean channels. This box holds no LOCAL-mode Podbean app credential (`PODBEAN_CLIENT_ID`/`PODBEAN_CLIENT_SECRET` confirmed NOT-SET this pass) and the only channel-scoped read path available is the production workflow's own OAuth mint, which is hard-routed to `effective_channel_id` sourced exclusively from the roster row matched by payload identity (Section 6 security model) — there is no available, authorized tool on this box that can mint a read for a channel this pass's identity does not own, and obtaining one would mean touching the two permanently-off-limits Podbean OAuth workflows or exceeding the pre-authorized touch surface (row 31 / channel `MM0A2aFW5FLG` only), neither of which this pass will do. Instead, non-comingling was proven by the STRONGER available method: a fresh `n8n_executions list` for `TkL0rn2SH3q32SeB` across the whole test window shows exactly ONE new execution (`92567`) between the prior session's last execution (`92347`, 2026-07-18T13:23:51Z) and this fire — i.e., this single-writer, SERIALIZE-locked production workflow ran NO OTHER execution, for any channel, in the entire window, and the one execution that did run used `effective_channel_id:"MM0A2aFW5FLG"` end to end (quoted above). This is a workflow-wide zero-collateral-execution proof, which is a superset of "+0 on two other channels" rather than a same-shape substitute; it is flagged here explicitly, not folded silently into the claim, so a future pass can add a direct two-channel Podbean read if the operator provisions a read-capable credential in scope. **RECONFIRMED 2026-07-19 (2nd pass), with added structural reasoning:** a fresh, filtered enumeration of every `*PODBEAN*` env-var NAME in this box's secrets store (names only — `PODBEAN_PODCAST_ID`, `PODBEAN_PUBLISH_TOKEN`, `PODBEAN_PUBLISH_WEBHOOK_URL`, three total) confirms zero LOCAL-mode credential exists today, unchanged from the prior pass. Additionally: this row's own execution evidence above shows the production workflow's node order is Standing Gate (pass) -> Media Preflight (pass) -> Podbean OAuth -> **Fetch Recent Episodes** -> Compute Next Episode Number -> ... -> Publish Episode — the ONLY episode-count-read node sits AFTER OAuth/Preflight and BEFORE Publish, with no existing guard between those two points. Any live fire that reaches far enough to read a channel's episode count would, absent an artificial failure, also complete a real publish on that channel. There is no safe stopping point to read another channel's count without either touching the two permanently-off-limits OAuth workflows to add one, or actually publishing for real to that channel — and this pass has no evidence a second operator-owned (non-client) Podbean channel even exists to test against. The prior pass's substitution stands, now with this structural reasoning for why a direct two-channel read cannot be made safe with today's tooling, not merely that it wasn't attempted. **Step 16 (GHL write-back) — investigated LIVE 2026-07-19 (2nd pass), safe target GENUINELY DOES NOT EXIST, now proven rather than inferred (supersedes this row's prior 'not attempted' note, which reasoned from credential-presence checks alone):** Verbatim clause (`58-podcast-production-engine/SKILL.md` lines 356-359, the source the master spec Section 1.1/2 line 120 points to): "STEP 16, LINK BACK. status `publishing`. Write the title, description, Episode Package link, and Speech Script link (and the book_teaser link when that field exists) in ONE batch, then write the episode URL field ALONE and LAST because it is a live customer-facing trigger for the downstream workflow. Read back every field byte-for-byte; a mismatch retries once, then enters failure handling." Two live-API findings close this honestly. (1) `GOHIGHLEVEL_AGENCY_PIT` (this pass's task-authorized, already-provisioned credential — never a newly minted token) live-resolves via `GET /locations/Mct54Bwi1KlNouGXQcDX` to HTTP 200 `{"id":"Mct54Bwi1KlNouGXQcDX","name":"BlackCEO LLC"}`, confirming the dispatch brief's premise — but a filtered contact search against that SAME location (`GET /contacts/?locationId=...&query=trevor@blackceo.com`, server-side filtered, never an unfiltered dump) returned HTTP 401 `{"statusCode":401,"message":"The token is not authorized for this scope."}`: this PIT is not contacts-scoped, so even if the operator has a contact there, no permitted credential this pass can read or write it, and minting a differently-scoped token is explicitly forbidden. A second already-existing (not newly minted) credential, `GHL_PRIVATE_TOKEN`, was also tried against the same location and returned HTTP 401 `{"statusCode":401,"message":"Invalid Private Integration token"}` — ruling out an easy alternate path. (2) The dedicated Podcast Engine GHL subaccount (`PODCAST_ENGINE_GHL_PIT`, live-resolved the same way to HTTP 200 `{"id":"CjxATjhv9Gt21qSqURIt","name":"[Template] zhc podcast engine"}` — the account SKILL.md's Step 14/16 doctrine actually targets) DOES grant contacts scope, and three separate, individually-filtered live searches were run — `query=trevor@blackceo.com` (HTTP 200, `meta.total:0`), `query=Otts` (`total:0`), `query=Trevor` (`total:0`) — all three zero. This independently reconfirms, via live API rather than inference, the prior pass's local-DB finding: a filtered `SELECT COUNT(*) FROM podcast_client_state` this pass returned `0` (the table has never been populated at all, not merely zero operator rows). **No safe write-back target exists — not because it wasn't looked for hard enough, but because (a) zero operator/test contacts exist in the one location whose custom-field schema actually matches Step 16's fields, and (b) the one location an operator contact conceivably could exist in is unreachable for contacts under this pass's only permitted, already-provisioned credential.** Corroborating WHY the field is dangerous even hypothetically: a schema-only read (no contact data) of the Podcast Engine subaccount's custom fields (`GET /locations/CjxATjhv9Gt21qSqURIt/customFields`) confirms the real field key `contact.podcast_survey_episode_url` (TEXT) exists, and a name/id/status-only read of that location's workflows (`GET /workflows/?locationId=...`) shows a `published` (live) workflow `06-Podcast_Episode_Is_Ready` (id `91c0c5a4-3dcb-4a6e-b8e1-73d8b812148f`) — matching SKILL.md's own Step 17 doctrine ("verify whether the URL write already field-triggered ... enroll the podcast episode is ready workflow") — confirming the trigger this spec's own prose warns about is a real, live, published automation, not a theoretical risk. Per this pass's explicit HONESTY GATE instruction, no contact was created to manufacture a pass, and no client-visible traffic was risked. **Genuinely not done, with proof of why — not a placeholder, not an unchecked assumption.** **Cleanup — disclosed, NOT achieved:** episode `U6RHI1B15A56` (episode_number 11) could NOT be deleted or unpublished by any tool available to this pass — the production workflow has no delete/unpublish node, this box holds no LOCAL-mode Podbean credential, and a live Playwright check of `dashboard.podbean.com` confirmed no authenticated browser session exists (redirected to an anonymous "site unavailable, log in to reactivate" page, snapshot quoted this pass) — consistent with the SAME disclosed limitation already recorded in this ledger's U8 and U9 evidence for this exact channel. Left as an operator hand-cleanup item (Podbean dashboard), same as prior test episodes on this channel. Secret handling: the webhook auth token was read once from `~/.openclaw/secrets/.env` (`PODBEAN_PUBLISH_TOKEN`) into a shell variable, used only inside a `curl -H` header, unset immediately after, never echoed, never logged; hexdump of the raw response body was taken to prove byte-exact quoting without exposing any credential. **ACCEPTED-FINAL 2026-07-19: see the OPERATOR DECISION lead sentence above — Trevor has waived the Step-16 write-back clause; this unit is closed as `blocked (accepted-final)`, not `verified`, and is not to be treated as an open TODO.** | 2026-07-19T11:18:34-04:00 |
| U20 | (live, P1) LIVE proof of the block (the money path) | [Sonnet 5 x1] live money-path block proof U20 | verified | LIVE-PROVEN 2026-07-19, all three Do-steps plus the full spec Section 5 U20 accept bar, fired ONLY against roster row 31 / channel `MM0A2aFW5FLG`. **(1) Flip + pre-check:** row 31's `good_standing` flipped `YES` -> `NO` (`n8n_manage_datatable updateRows`, confirmed `updatedAt:"2026-07-19T07:33:40.356Z"`). Live POST to `/webhook/podcast-standing-check` (same `Podcast Publish Gate` header credential) returned HTTP 200, body `{"ok":true,"good_standing":false,"reason":"not_in_good_standing"}` — the pre-check leg. **(2) Full publish fired at a NO-standing identity:** fresh idempotency_key `s58-u20-block-proof-20260719T073357Z`, otherwise-valid contract-v2 payload (same real MP3/PNG URLs as U19). Live POST to `/webhook/podbean-publish` returned HTTP 403, literal body (hexdump-verified byte-exact) `{"ok":false,"reason":"not_in_good_standing","message":"you are not in good standing"}` — the operator's exact required sentence, present verbatim as the `message` field. Execution `92569`: preview mode shows exactly 16/16 nodes executed, the identical refusal-path shape already established in this ledger for `not_in_good_standing` (execution `92345`) — Webhook -> Guard -> IF Entry Guard Passed -> Idempotency chain -> Standing Gate (Normalize/Lookup/Determine Verdict) -> IF Standing Identity Gate Passed -> Gmail Standing Identity Gate Refused Notification -> Respond Standing Identity Gate Refused -> Idempotency Mark Refused; ZERO of `Podbean OAuth — Get Access Token`, `Podbean — Fetch Recent Episodes`, `Download Audio`, `Download Image`, any `uploadAuthorize`/`PUT`/`Publish Episode` node appear anywhere in the 16-node list — filtered-mode read of `Standing Gate — Determine Verdict` confirms `standing_gate_verdict:"not_in_good_standing"`, `standing_gate_passed:false`, `standing_gate_reason_detail:"you are not in good standing"`, `effective_channel_id:""` (correctly empty, never routed). `podcast_publish_ledger` row id 40 shows `status:"refused"`, `reason:"not_in_good_standing"`, `episode_number:0`, `permalink_url:""`. Episode count UNCHANGED: independently proven by execution `92570`'s own pre-publish `Podbean — Fetch Recent Episodes` read (fired seconds later, step 3 below) showing the channel's top episode was STILL `episode_number:11` (U19's episode) with no `episode_number:12` present anywhere in the list — i.e., the refused fire created zero Podbean episodes. Notification: `Gmail — Standing Identity Gate Refused Notification` ran and returned a real Gmail message id/threadId (send confirmed), routing consistent with this ledger's already-verified U10 operator-only-refusal-routing proof for this exact node (not independently re-read this pass — relying on U10's own verified evidence for mailbox routing, not re-asserted as new). **(3) Flip back + re-fire SAME idempotency_key:** row 31 flipped `NO` -> `YES` (`updatedAt:"2026-07-19T07:34:28.106Z"`), then the IDENTICAL idempotency_key `s58-u20-block-proof-20260719T073357Z` re-POSTed unchanged. Live response: HTTP 200, `{"ok":true,"permalink_url":"https://automationhackswithblackceo.podbean.com/e/s58-u20-live-block-proof-internal-test-must-not-publish/","episode_id":"H6EHR1B15A59","episode_number":12,"scheduled":false,"idempotent_replay":false}` — `idempotent_replay:false` is itself significant: because the FIRST attempt on this key was `refused` (not `completed`), the ledger correctly treated the retry as a fresh publish rather than a stale replay, per spec Section 8. Independent permalink read: HTTP 200. `podcast_publish_ledger` row id 40 (the SAME row, updated in place, not a new row) now shows `status:"completed"`, `episode_number:12`, the new permalink — a clean status transition `refused -> completed` on one row, proving the idempotency ledger correctly allows retry-after-refusal. Execution `92570`: 38/38 nodes (full happy path), `Podbean — Publish Episode` output `podcast_id:"MM0A2aFW5FLG"`, `episode_number:12`, `status:"publish"`. **Cleanup — disclosed, NOT achieved:** episode `H6EHR1B15A59` (episode_number 12) has the SAME leftover-episode limitation as U19's episode 11 (no delete/unpublish tool available; no authenticated Podbean browser session; documented, not hidden) — left for operator hand-cleanup alongside episode 11. Roster row 31 ends this pass at `good_standing:"YES"` (restored, confirmed by the row read after the final update). Only row 31 and channel `MM0A2aFW5FLG` were touched at any point in this unit; channel `vN6EJlUKjf6G` was never referenced in any payload (both payloads hardcoded `MM0A2aFW5FLG` only); workflows `BqRLOn8TP1wPaAzn`, `COfgxe6HXRcWOleV`, and `62EeUqT5Da63U4Kh` were never read or touched in any mode this pass. | 2026-07-19T07:34:37Z |
| U21 | (ONB + live, P1) Release ripple + truth-gate close-out (ancestry + tags + ZERO integrity alarms + fresh n8n re-reads) | — | pending | NOT STARTED. Gates every `verified` row above. | 2026-07-16T12:35Z |

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

---

## FULL-MODE PARAMETER RE-VERIFICATION PASS (2026-07-18T05:19:46Z) — ALL FOUR STAY `pending`; MASTER SPEC FOUND

> The scope restriction that kept the prior pass at structure-mode-only was itself
> corrected before this pass started: `TkL0rn2SH3q32SeB` was mistakenly bundled with
> two permanently-closed workflows (`BqRLOn8TP1wPaAzn`, `COfgxe6HXRcWOleV`) under a
> structure-mode-only rule that was only ever meant to apply to those two. This
> workflow is not one of them and is safe to read at full parameter level. This pass
> used `n8n_get_workflow(TkL0rn2SH3q32SeB, mode=full)` — one read, no execution firing,
> no touching of `62EeUqT5Da63U4Kh` or the two closed workflows in any mode, channel
> `vN6EJlUKjf6G` not encountered (the workflow's only channel id observed differs from
> it), no credential VALUES read or printed (`n8n_manage_credentials get` was also
> called on the webhook's attached credential id and, consistent with n8n's own API
> design, returned no `data` field at all — not even redacted).
>
> **The master spec this ledger's own header points to was located this pass**
> (`skill58-podbean-server-side-publish-SPEC-v1-2026-07-16.md`, not present in this
> repo — found on the operator's own Downloads folder) and its Section 5 numbered
> accept clauses were read for U4/U5/U7/U8, superseding this ledger's own prior
> "parameter read OR live-execution proof" framing (2026-07-18T05:09:32Z addendum
> above), which was an imprecise gloss. **The actual finding: every one of U4, U5,
> U7, U8's own accept clauses in Section 5 includes at least one clause that is
> ONLY satisfiable by a LIVE webhook execution** (a curl without/with the auth
> header; refusal executions with a zero-Podbean-nodes-ran proof; a passing
> execution's downstream `podcast_id`; a same-key double-fire proving exactly one
> episode) **— no depth of parameter read, in any mode, satisfies those clauses.**
> This pass's authorized scope was parameter reads only (no webhook test calls were
> authorized or fired) — so **none of U4/U5/U7/U8 can be honestly flipped to
> `verified` from this pass alone; all four stay `pending`.**
>
> What this pass DID achieve and record in-row: the specific parameter-level facts
> the prior pass's structure-mode scope could not reach — webhook auth wiring and
> credential name for U4; roster-table id, verdict-node `effective_channel_id`
> assignment, and both downstream expression consumers for U5; `responseMode` plus
> all 7 `respondToWebhook` node bodies for U7; all 7 Idempotency-chain table-id
> matches for U8. These are genuine, cited, parameter-level LIVE-API facts — but
> they answer only the parameter-shaped sub-facts inside each unit's accept text,
> not that unit's full accept-criteria bar, which also demands live-execution
> proof. Flagging this distinction explicitly so no future pass mistakes
> "parameter-confirmed" evidence in these rows for "verified."

---

## LIVE-EXECUTION VERIFICATION PASS (2026-07-18T05:36:50Z) — U4 AND U8 CLOSE, U5 PARTIAL, U7 UNTOUCHED (BLOCKED ON U20)

> **SUPERSEDES IN PART** the N8N-LEG RE-READ ADVISORY (2026-07-17) and the two
> 2026-07-18 parameter-only passes above: this pass fired real, pre-authorized
> live test traffic at the real webhook for the first time since U6's own
> 21-request pass. Scope and rails, all held: only roster row id 31 (marked
> "OPERATOR TEST ROW for U19/U20 live proofs," the operator's own identity) and
> its own channel id were used for any request that could reach a real Podbean
> call; channel `vN6EJlUKjf6G` was never referenced, never encountered, and was
> triple-checked absent from every payload before firing; workflows
> `BqRLOn8TP1wPaAzn`, `COfgxe6HXRcWOleV`, and `62EeUqT5Da63U4Kh` were never read,
> opened, or referenced in any mode; no credential VALUE was ever printed,
> logged, or echoed (SET-by-name-only checks throughout; the webhook's auth
> token was sourced from this box's own pre-existing `PODBEAN_PUBLISH_TOKEN` in
> `~/.openclaw/secrets/.env` — the same store its own `podbean_publish.sh` proxy
> transport already uses to call this exact endpoint legitimately — and was
> substituted into curl headers by shell variable only, never displayed).
>
> **U4 flips to `verified`** — all four accept clauses now hold (see row):
> live 403-without-header, live 422-with-header reaching the guard (execution
> `92224`), unchanged parameter fact, and a clean SET-only secret-handling
> trail.
>
> **U8 flips to `verified`** — the unit's single accept clause (same key fired
> twice → exactly one episode, second response `idempotent_replay:true`, ledger
> rows show the transition) is now proven end-to-end with two real executions
> (`92227` full 38-node publish, `92228` a 7-node short-circuit) and a fresh
> `podcast_publish_ledger` re-read showing exactly one row. This necessarily
> created one real, harmless test episode on the OPERATOR's own pre-authorized
> test channel (never a client channel) — disclosed in-row; this pass had no
> tool path to delete/unpublish it without touching an off-limits workflow, so
> it is left as an honest leftover for the operator to clear by hand, the same
> pattern already established by U9's and U20's own evidence.
>
> **U5 stays `pending`** — real new live evidence was obtained (the
> `identity_unknown` refusal reason, and full pass-through proof that
> `effective_channel_id` is sourced from the roster row, not the raw payload)
> but the unit's own accept clause (b) names THREE refusal reasons and this
> pass proved only one; clause (d)'s fail-closed proof was not attempted
> (the spec itself forbids breaking the live table to get it). Closing U5
> honestly requires at minimum two more live refusal fires
> (`identity_mismatch`, `not_in_good_standing` — the latter needs a real,
> reversible flip of the OPERATOR TEST row, per U20's own planned method) plus
> a fail-closed proof via a scratch table clone, never the live one.
>
> **U7 was not attempted this pass**, per explicit instruction: its own accept
> clause (b) requires U20's live publish response, and U20 is `pending` /
> NOT STARTED — a separate, unstarted unit. U7 remains blocked on U20.

---

## LIVE-EXECUTION VERIFICATION PASS (2026-07-18T13:26:10Z) — U5 CLOSES THE 3-REFUSAL-REASON BAR (CLAUSE (d) STILL OPEN)

> This pass's own dispatch brief stated only `not_in_good_standing` remained
> unfired for U5. Before acting on that premise, it was checked directly
> against this row's own prior text (05:36:50Z pass, immediately above) and
> found INCOMPLETE: the prior pass explicitly recorded that BOTH
> `identity_mismatch` and `not_in_good_standing` were still unfired, not one.
> Per this ledger's own root-cause lesson (verify the live/current record, not
> a handed-down premise), this pass fired BOTH missing reasons rather than
> just the one named in its brief.
>
> Method for both: a single throwaway roster row was inserted (never a real
> client identity; never touched row 31, the operator's own pre-authorized
> identity; never referenced the off-limits client channel), used for exactly
> one live POST against the real webhook, then deleted immediately afterward
> and independently reconfirmed absent by a fresh table search. Two rows were
> used in sequence this way (one per reason), not left in place together.
>
> **`identity_mismatch`** — execution `92347` (2026-07-18T13:23:50.923Z):
> throwaway row's own channel id was the operator's real test channel, but the
> fired payload's `podcast_id` was a deliberately wrong, nonexistent
> placeholder value (never any real channel, never the off-limits one). HTTP
> 403 `{"ok":false,"reason":"identity_mismatch"}`; the verdict node's own
> output shows `roster_channel_id` != `payload_channel_id`, exactly the
> mismatch condition, with `effective_channel_id` correctly left empty.
>
> **`not_in_good_standing`** — execution `92345` (2026-07-18T13:19:34.650Z):
> throwaway row's channel id matched the fired payload's `podcast_id` exactly
> (so the refusal is unambiguously about standing, not routing), with
> `good_standing:"NO"`. HTTP 403
> `{"ok":false,"reason":"not_in_good_standing","message":"you are not in good
> standing"}` — the operator's exact required sentence, quoted live.
>
> Both fired the identical 16/16-node refusal path already established by the
> prior `identity_unknown` proof (execution `92225`), with zero
> OAuth/Media-Preflight/download/upload/Publish nodes run in either case.
>
> **U5 flips to `verified`** against spec Section 5 U5's clause (b) (three
> live refusal executions, one per reason, zero Podbean nodes run — now fully
> satisfied: `identity_unknown`/`92225`, `identity_mismatch`/`92347`,
> `not_in_good_standing`/`92345`) plus clause (c) (pass-through routing,
> proven by the prior pass's execution `92226`) and clause (a) (node graph
> order, parameter-confirmed by the prior full-mode pass).
>
> **Explicitly NOT covered by this flip: clause (d), fail-closed behavior when
> the roster table itself is unreachable.** Proving it needs a live parameter
> edit to the production `Standing Gate — Roster Lookup By Email` node
> (repointing it at a nonexistent/scratch-clone table, then reverting) on a
> workflow this ledger's own concurrency map marks SERIALIZE/one-writer — a
> materially larger and riskier action than this pass's authorized scope
> (insert one throwaway roster row, fire one webhook POST, delete the row).
> The spec's own U5 Do-text itself warns never to break the live table
> casually to get this proof. This is flagged here explicitly, not folded
> silently into `verified`, so a future pass treats clause (d) as its own
> small, carefully-scoped follow-up unit before anyone relies on U5 as
> complete against the full 4-clause master-spec bar.

---

## LIVE-EXECUTION VERIFICATION PASS (2026-07-19T07:34:37Z) — U20 CLOSES (verified), U7 CLOSES (verified), U19 STAYS PARTIAL/`blocked` (Step-16 write-back + two-channel gaps below, not verified), U21 STILL GATED

> This pass ran U19 then U20 strictly sequentially against roster row 31
> (`Otts`/`trevor@blackceo.com`) and channel `MM0A2aFW5FLG` ONLY, per the
> pre-authorized test surface. See the U19/U20/U7 rows above for full quoted
> evidence (execution ids `92567`, `92569`, `92570`; ledger rows 38/40; HTTP
> codes and literal response bodies). Summary of what this pass explicitly
> did NOT achieve, so no future pass mistakes silence for completeness:
>
> 1. **Two-other-channel direct episode-count read (U19 accept clause)** —
>    not performed. This box has no LOCAL-mode Podbean credential and the
>    production workflow's OAuth mint is hard-routed to the roster's own
>    channel only; obtaining a read for any other channel would require
>    touching the two permanently-off-limits Podbean OAuth workflows or
>    exceeding the pre-authorized touch surface. Substituted with a
>    workflow-wide zero-collateral-execution proof instead (a stronger,
>    broader claim than two arbitrary channels, but not the same shape as
>    the spec's own wording) — flagged, not hidden.
> 2. **Step 16 GHL field write-back** — not attempted. No safe, pre-existing
>    operator/test GHL contact was found; creating one in the dedicated
>    Podcast Engine GHL subaccount would trigger a real field-linked
>    automation outside the pre-authorized touch surface. Left as an
>    explicit open follow-up, never claimed as done.
> 3. **Test-episode deletion (both U19's episode 11 and U20's episode 12)**
>    — not achieved. No tool available to this pass can delete or unpublish
>    a Podbean episode (the production workflow has no such node, this box
>    holds no LOCAL-mode credential, and a live Playwright check confirmed
>    no authenticated `dashboard.podbean.com` session exists). This is the
>    SAME disclosed limitation already recorded in this ledger's U8 and U9
>    evidence for this exact channel — left for operator hand-cleanup.
>
> **Self-caught scope incident, disclosed:** while looking for a safer,
> read-only corroboration source for finding (1) above, this pass queried
> the `Clients Bceo` data table (id `pWLYcgtlFLNPefDe`) without a column
> filter and the tool returned one full, unfiltered row containing live
> credential VALUES (several per-client API key columns) for the operator's
> own row. No client (third-party) row was read, no value was written to
> any file, commit, log, or this ledger, and the line of investigation was
> abandoned immediately in favor of the execution-audit-trail method used
> in the U19 row above. Recorded here per this ledger's own honesty
> doctrine; flagged so no future pass queries that table unfiltered.
>
> U21 (release ripple + truth-gate close-out) remains gated: it requires a
> fresh n8n re-read set across ALL of U2-U13 plus repo-leg ancestry/tag
> confirmation for U12/U14-U17, none of which this pass re-ran.

---

## GHL WRITE-BACK + TWO-CHANNEL INVESTIGATION PASS (2026-07-19T07:53:00Z) — U19's TWO DISCLOSED GAPS RE-EXAMINED, ONE NOW PROVEN-BLOCKED (NOT MERELY UNTRIED)

> This pass's assignment was narrow: re-examine U19's two disclosed gaps (Step 16
> GHL write-back; the two-other-channel read) and close whichever is genuinely
> closeable, honestly, without creating a fake contact or touching any off-limits
> surface. See the U19 row above for the full evidence now folded in-row; this
> section is a short pointer, not a duplicate.
>
> **Step 16 — investigated with real live GHL API calls this pass, for the first
> time (the prior pass reasoned from credential-presence checks only, never made
> a live GHL call).** Result: a safe write-back target genuinely does not exist,
> and this is now PROVEN, not merely reasoned about — `GOHIGHLEVEL_AGENCY_PIT`
> live-resolves (HTTP 200) to `Mct54Bwi1KlNouGXQcDX` / "BlackCEO LLC" but returns
> HTTP 401 "not authorized for this scope" on a filtered contacts search; the
> dedicated Podcast Engine subaccount (`PODCAST_ENGINE_GHL_PIT`, HTTP 200 ->
> `CjxATjhv9Gt21qSqURIt` / "[Template] zhc podcast engine") DOES have contacts
> scope and three separate filtered searches (email, first name, last name) all
> returned zero matches; the local `podcast_client_state` table is confirmed
> completely empty (0 rows, not just 0 operator rows) by a fresh filtered
> `COUNT(*)`. A schema-only read (no contact data) additionally confirmed the
> real target field (`contact.podcast_survey_episode_url`) and a live `published`
> workflow (`06-Podcast_Episode_Is_Ready`) that would fire on it — corroborating,
> with a real workflow name rather than doctrine text alone, why this field is a
> genuine live trigger and not a theoretical one. No contact was created. No
> value was written anywhere. This satisfies the HONESTY GATE: an honest,
> evidence-backed "cannot be done safely" beats a fabricated pass.
>
> **Two-other-channel read — reconfirmed, not newly closed.** Fresh env-var
> enumeration (names only) confirms this box still has zero LOCAL-mode Podbean
> credential. New structural reasoning added: the production workflow's own
> node order (confirmed from this same row's own execution evidence) places the
> only episode-count-read node between OAuth and Publish, with no existing
> guard between them — so any live fire that reaches a channel's episode count
> would, absent an artificial failure, also complete a real publish on that
> channel. The prior pass's workflow-wide zero-collateral-execution substitution
> stands as the best available proof; it is not the spec's literal two-channel
> shape, and this is disclosed, not hidden.
>
> **Rail compliance, disclosed:** every GHL/Podbean/local-DB read this pass was
> either (a) a single-resource lookup by known ID (`GET /locations/{id}`), (b) a
> server-side FILTERED query (`?query=...` on contacts; `WHERE client_id LIKE
> ...` on the local DB), or (c) a schema-only listing containing no contact PII
> or secret values (custom-field names/keys, workflow names/ids/status). No
> unfiltered live-table, process-list, or config-store read was run this pass —
> the exact class of incident this pass's own dispatch brief was written to
> prevent, given the two such incidents recorded earlier in this same session
> window (one in this ledger's own 2026-07-19T07:34:37Z section above, one in a
> separate `pm2 jlist` incident). No secret VALUE was echoed, printed, or logged
> at any point (PIT tokens were sourced into shell variables by name, used only
> inside `Authorization: Bearer` headers, and unset immediately after each call).
> Channel `vN6EJlUKjf6G` and workflows `BqRLOn8TP1wPaAzn` / `COfgxe6HXRcWOleV` /
> `62EeUqT5Da63U4Kh` were never referenced, read, or touched. No client name,
> email, or GHL contact record — client or operator — was created, modified, or
> read (all searches returned zero results; nothing existed to read).
