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
| U1 | Prove n8n API WRITE capability (POST/GET/DELETE scratch workflow) or record manual-UI fallback | [Opus 4.8 x1] bootstrap survey (unit unstarted) | pending | READ leg only proven this pass: `GET /api/v1/workflows/TkL0rn2SH3q32SeB` HTTP 200 and full 286-workflow paged listing HTTP 200, key by name `N8N_API_KEY` (SET, value never printed). WRITE capability still UNPROVEN — that is U1's actual job. | 2026-07-16T12:35Z |
| U2 | Create + seed `podcast_publish_roster` data table (6 cols, all good_standing=YES, + OPERATOR TEST row) | — | pending | GREENFIELD. Fresh `GET /api/v1/data-tables` HTTP 200 → 6 tables exist; `podcast_publish_roster` is ABSENT. Reuse pattern: `snapshot_provision_ledger` (FCb16RvM2l7f4HKl). | 2026-07-16T12:35Z |
| U3 | Create `podcast_publish_ledger` data table (8 cols), empty at creation | — | pending | GREENFIELD. Same live re-read: `podcast_publish_ledger` ABSENT from the 6 existing tables. | 2026-07-16T12:35Z |
| U4 | Snapshot workflow JSON, then add webhook header auth (`Podcast Publish Gate`, `X-Podcast-Publish-Token`) | — | pending | GREENFIELD — **LIVE SECURITY HOLE OPEN AND CARRYING REAL TRAFFIC**. Fresh API re-read of `TkL0rn2SH3q32SeB` webhook node: `authentication` key ABSENT, `credentials: NONE`, `path: podbean-publish`, `httpMethod: POST`. Webhook is publicly postable. Pattern source `aN6MrIJ4zLeKS047` still ACTIVE (2 nodes). **SEE THE LIVE-CALLER FINDING BELOW — execution 91115 published a real episode at 2026-07-16T12:38:08Z, DURING this bootstrap. U4 will 401 that caller unless it is provisioned first. This is now the central input to D1.** | 2026-07-16T12:41Z |
| U5 | Good-standing + identity gate (roster lookup; downstream uses roster's `effective_channel_id`) | — | pending | GREENFIELD. Fresh re-read: ZERO dataTable nodes in the 24-node graph. No roster lookup exists. | 2026-07-16T12:35Z |
| U6 | Extend entry field guard to contract v2 | — | pending | PARTIAL SUBSTRATE (unit still greenfield): live v1 guard `Guard — Validate Required Payload Fields` (Code) + `IF — Entry Guard Passed` EXIST (GK-01/U63 lineage, 7 required fields). U6 EXTENDS this code, does not rebuild it. Preserve the GK-01 header comment lineage (append, never rewrite). | 2026-07-16T12:35Z |
| U7 | Synchronous response (`responseMode: responseNode`) returning permalink JSON | — | pending | GREENFIELD. Fresh re-read: webhook `responseMode` ABSENT (= default fire-and-forget); ZERO `respondToWebhook` nodes in the graph. Permalink cannot reach the caller today → Step 16 is starved. | 2026-07-16T12:35Z |
| U8 | Server-side idempotency via `podcast_publish_ledger` | — | pending | GREENFIELD. Depends on U3 (table absent). ZERO dataTable nodes live. | 2026-07-16T12:35Z |
| U9 | Scheduling-status truth check (`draft` vs `future`) proven live | — | pending | GREENFIELD — **DEFECT CONFIRMED PRESENT ON LIVE**. Fresh re-read of `Podbean — Publish Episode` (httpRequest) body param: `status = ={{ $json.publish_timestamp > Math.floor(Date.now() / 1000) ? 'draft' : 'publish' }}` → future dates STILL send `draft`, while the repo script uses Podbean's documented `future`. Unfixed. Feeds D2 (drafts census). | 2026-07-16T12:35Z |
| U10 | Notification routing for refusals → OPERATOR only | — | pending | GREENFIELD. Live graph has `Gmail — Entry Guard Refused Notification` on the refusal path (emails the CLIENT today per spec 1.4) — U10 rewires it to the operator. | 2026-07-16T12:35Z |
| U11 | Media preflight (HEAD audio_url + image_url before OAuth) | — | pending | GREENFIELD. No preflight node in the 24-node graph; Download nodes fire without a HEAD check. | 2026-07-16T12:35Z |
| U12 | Cutover + sanitized archive + gate-test cleanup (HYBRID: n8n leg + REPO leg) | — | pending | GREENFIELD. `aN6MrIJ4zLeKS047` "Podbean Gate Test (TEMP - delete at cutover)" fresh re-read: HTTP 200, ACTIVE, 2 nodes, updatedAt 2026-07-10T17:42:54Z — NOT deleted. Repo leg target file not yet present. | 2026-07-16T12:35Z |
| U13 | NEW workflow `podcast-standing-check` (webhook + header cred + roster lookup + respond) | — | pending | GREENFIELD. Name scan across ALL 286 live workflows (paged, HTTP 200): no standing-check workflow exists. No Podbean broker workflow exists either (consistent with the dormant-asset history). | 2026-07-16T12:35Z |
| U14 | `publish-proxy` transport in `podbean_publish.sh` (proxy → broker → local) | — | pending | GREENFIELD — **THE "IN-FLIGHT" BRANCH DOES NOT EXIST**. `git for-each-ref refs/` over local + remote after `git fetch --prune`: ZERO refs matching `publish-proxy` / `for-real` / `skill58` / `proxy`. Content scan of `origin/main:58-podcast-production-engine/scripts/podbean_publish.sh` (594 lines) @ a2c425da: `PODBEAN_PUBLISH_WEBHOOK_URL`=0, `publish-proxy`=0, `publish_proxy`=0, `PODBEAN_PUBLISH_TOKEN`=0; `PODBEAN_BROKER_WEBHOOK_URL`=5, `PODBEAN_CLIENT_ID`=7 → transport chain is still broker → local ONLY. | 2026-07-16T12:35Z |
| U15 | Identity + endpoint provisioning (install.sh injection + credential checklist + validators) | — | pending | PARTIAL SUBSTRATE (unit still greenfield): the broker-pair injection at install.sh lines 1146-1169 + credential list lines 2086-2100 is the REUSE POINT per spec 1.3. New proxy vars not present (0 occurrences on origin/main). | 2026-07-16T12:35Z |
| U16 | Pre-production standing gate in SKILL.md (Steps 0 + 1) + doctrine updates | — | pending | GREENFIELD. Depends on U13 endpoint existing. Must carry the Section 0 sovereignty-exception wording verbatim + the exact sentence "you are not in good standing". | 2026-07-16T12:35Z |
| U17 | Repo tests for the new contract (payload-v2 builder, standing-block, identity-env-missing) | — | pending | GREENFIELD. Extends the existing 7-mock e2e suite + `tests/webhook/` fixtures. Tests must be PROVEN able to fail. | 2026-07-16T12:35Z |
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
