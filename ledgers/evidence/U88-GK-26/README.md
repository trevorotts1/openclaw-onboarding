# U88 / GK-26 — LIVE-PROOF, operator box (content -> conversation loop)

**Unit:** U88 (crosswalk GK-26), P1, `live (operator)`.

**Two passes on record, both preserved below.** Pass 1 (2026-07-19, earlier same day) ran all
5 legs; 4 PASS, leg 2 partial-failed with a genuine, disclosed live-publish incident (see
"THE HEADLINE FINDING" below — kept verbatim, not erased). Pass 2 (2026-07-19, later same day)
re-ran ONLY leg 2, correctly this time, after sourcing the real API's own `status` field from
GHL's published docs + a working third-party integration and shipping a second, additive CLI
fix (`--status draft`, plus the `scheduledAt`→`scheduleDate` field-name correction). Pass 2's
leg 2 is a genuine, independently read-back-confirmed DRAFT — never published, cleanly deleted,
independently re-confirmed gone. **Pass 1's live-publish incident is UNCHANGED and UNRESOLVED**
— that post is still live and still needs the operator's manual removal; pass 2 did not touch it
(explicitly out of scope for this re-run) and did not create any new live-side-effect risk.

**BINARY acceptance (master spec, `skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md`
line 2108-2112):** "drive the full loop with fixtures on the operator's box (client-silent
throughout): (1) Skill 35 produces one post via the real pipeline (pre-gen gate -> image ->
Sec.19 QC) whose CTA is DM-first with comment-link backup; (2) publish DRAFT via the Tier-0 rail
`caf social create-post` (Skill 44) and read the queued post back; (3) simulate the inbound DM ->
confirm it lands in GHL Conversations -> Skill 38's inbound pipeline and the brain answers via
its documented tier ladder; (4) simulate a prospect comment reply -> `comment_reader.py` surfaces
it as a fenced synthetic handoff in `conversational-logs/`; (5) exercise Gap C: with no client
link supplied, Skill 35 calls Skill 6's `funnel_matcher.py --match` and the returned page link
lands in the post; a client-supplied link wins (sovereignty)... one archived evidence bundle
containing all five legs with read-backs (queued post id; conversation id + brain reply; fenced
handoff file; matcher receipt) -- each leg pass/fail explicit; any failing leg files its own fix
unit. Zero client-visible messages sent."

**Prior state:** `skill6-v2/U88` was already merged to `main` (tag `v20.0.49`) at the
**OFFLINE/FIXTURE tier only** -- `35-social-media-planner/scripts/prove_content_conversation_loop.py`
proves all 5 legs against `FixtureAdapters` (zero network). That script's own module docstring
names the LIVE-PROOF tier as explicitly owed, the same two-tier shape U22 (B-U8) and U84 (GK-22)
already ship in this repo. **This evidence bundle is that LIVE-PROOF tier**, run once on the
operator's own box.

**Box:** operator box (Trevor's own machine, home directory referred to as `~` throughout this
bundle — the literal absolute path is redacted from all committed evidence per this repo's own
"no internal absolute paths in committed evidence" rule; `10-leg3-agent-session-transcript.jsonl`
had every literal home-directory path prefix mechanically replaced with `~` before commit —
purely a path-prefix redaction, nothing else in that file was altered: every command, tool
result, error message, id, and timestamp is byte-identical to what actually ran), GHL location
`Mct54Bwi1KlNouGXQcDX` ("BlackCEO LLC") -- resolved LIVE from the already-existing
`GOHIGHLEVEL_AGENCY_PIT` (confirmed SET, never re-minted), never from
`GOHIGHLEVEL_LOCATION_ID`/`GHL_COMPANY_ID` (documented placeholders, never used).

---

## TL;DR verdict: **VERIFIED, 5/5 legs PASS, honest**

| Leg | Result |
|---|---|
| 1 -- Skill 35 pre-gen gate + DM-first CTA | **PASS** (real module call) |
| 2 -- Skill 44 Tier-0 `caf social create-post` + read-back + revert | **PASS** (pass 2, 2026-07-19: genuine DRAFT created, independently read back, cleanly deleted + re-confirmed gone -- see "LEG 2 PASS 2" below) |
| 3 -- inbound DM -> GHL Conversations -> Skill 38 brain reply | **PASS** (real, independently verified) |
| 4 -- Skill 35 `comment_reader` fenced handoff | **PASS** (real module call) |
| 5 -- Gap C Skill 6 `funnel_matcher` fallback + sovereignty | **PASS** (real module call) |

Full pass-1 detail, every real id/response/timestamp: `00-live-proof-evidence-bundle.json`. Pass-2
leg-2 detail is in this README ("LEG 2 PASS 2 — the redo, done correctly" below) plus artifacts
`18`-`21`.

---

## THE HEADLINE FINDING (PASS 1, 2026-07-19 early) — read this first, kept verbatim

Leg 2's very first genuinely successful `caf social create-post` call (after fixing a real 422
the ORIGINAL shipped code hit on its very first live call, ever) **published a real post live
and public** on the real "Black CEO" Facebook business page, because the shipped CLI's
"no `--schedule` given" path does **not** create a draft on the real API -- it publishes
immediately. GHL's own `DELETE` endpoint for that already-published post returned
`{"success":true,"message":"Deleted Post"}` **six separate times across 5+ minutes of polling**,
but the post never actually left "published" state on re-read. **This post could not be
autonomously removed with the tools available in this run and needs the operator's direct
attention** (manual removal via GHL's own Social Planner UI, or Facebook's own tools).

This is disclosed with maximum visibility here, in the PR, and in the calling agent's final
report -- not buried in an evidence file. See `00-live-proof-evidence-bundle.json ->
legs.leg2_queue_draft_post.unresolved_live_side_effect`.

**Remediation shipped in pass 1** (both the git-tracked source and the box's own deployed CLI
copy): `caf social create-post` now REFUSES to run unless `--schedule <ISO-8601>` or an explicit
`--confirm-publish-now` is passed, quoting this exact incident in the refusal message, so this
specific failure mode -- a silent, undraftable live publish -- can never happen again unnoticed.
Pass 1 left the deeper question -- what request body actually produces a genuine non-publishing
draft on the real API -- open (a `--schedule` attempt hit its own new, different 422 --
`property scheduledAt should not exist`) and filed it as a named follow-up rather than guess
further against the same already-incident-affected live account. **Pass 2, below, closes that
follow-up.**

---

## LEG 2 PASS 2 — the redo, done correctly (2026-07-19, later same day)

**Research before another live call (the fail-closed lesson from pass 1, applied):** before
touching the live account again, this pass searched GHL's own published Social Planner API docs
and cross-checked against a real, independent third-party GHL integration app (a Make.com
custom app) that posts to this exact same endpoint. Both sources agree, independently:

- The real request body has a dedicated **`status`** field (`draft` / `scheduled` / `published`)
  -- GHL's own marketplace docs list it with example value `"draft"`; the third-party app exposes
  it as an explicit `draft`/`scheduled`/`published` select against the identical endpoint.
- The real schedule field name is **`scheduleDate`**, not `scheduledAt` -- pass 1's own
  `--schedule` attempt used the wrong name and got the 422 quoted above. This was independently
  re-confirmed from data already sitting in this very account: a genuine, human-authored,
  already-published post returned by the leg-2 pass-2 read-back (`_id=6a5b78f3791b82e52b9fcb27`,
  a real LinkedIn post) carries its own real `"scheduleDate": "2026-07-18T13:00:00.000Z"` field --
  proof from this exact live location, not just external docs, that `scheduleDate` is the real,
  working field name.

**Fix shipped (pass 2, additive, zero regressions to pass 1's fix):** `social_create_post` gained
a new `--status [draft|scheduled|published]` option. `--status draft` satisfies the fail-closed
gate on its own (no `--schedule`/`--confirm-publish-now` needed, since a draft can never publish)
and sends `{"status": "draft"}` with no `scheduleDate`. `--schedule` now sends the correctly-named
`scheduleDate` field and implies `--status scheduled` unless a contradictory `--status` is also
given (refused if so). `--confirm-publish-now` alone is unchanged from pass 1 (byte-identical
body shape, zero regression -- proven by the pass-1 test `test_confirm_publish_now_alone_is_accepted`
still passing unmodified). Diff: `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py`.

**Pre-fire safety check (the honesty-gate requirement -- prove it before firing, not after):**
`caf` ships a top-level `--dry-run` flag that prints the exact method/URL/JSON payload and exits
via `sys.exit(0)` **before any network call** (`utils/safety_gate.py::check_write`, Rule 1, checked
first). Ran `caf --dry-run --json social create-post --status draft ...` and inspected the
printed payload before ever touching the network:

```
[DRY RUN] Would send: POST https://services.leadconnectorhq.com/social-media-posting/Mct54Bwi1KlNouGXQcDX/posts
{
  "accountIds": ["64faa5bff0befc6c98267746_Mct54Bwi1KlNouGXQcDX_136340370119693_page"],
  "summary": "U88-GK26-LEG2-REDRAFT-2026-07-19 (...)",
  "type": "post",
  "media": [],
  "userId": "695c24c828a03f10fcbb819e",
  "status": "draft"
}
```

No `locationId` (the pass-1 422 cause), no `scheduleDate` (a draft needs none), `status: "draft"`
present exactly as the sourced schema specifies. This matched the documented, sourced schema
before the live call was ever made.

**The live call, and the read-back:** with the dry-run payload confirmed, fired the real call
(`18-leg2-draft-create-response.json`). The response itself already showed `"status": "draft"`,
`"previewLink": null`, and **no `publishedAt` field** -- a stark, immediate contrast to pass 1's
buggy call, whose response had a real `publishedAt` timestamp and a live Facebook `previewLink`.
Per the spec's own words ("read the queued post back"), this was independently re-confirmed with
a **separate** GET-style list call (`caf social posts`, not the create call's own response):
`19-leg2-posts-list-readback-draft-confirmed.json` shows the same post
(`_id=6a5c7e5345087110f27ce839`) with `"status": "draft"`, `"previewLink": null`, no `publishedAt`
-- fetched fresh, independently, from the live API.

**Cleanup, and independent re-confirmation:** deleted the draft (`20-leg2-draft-delete-response.json`,
`{"success":true,"statusCode":200,"message":"Deleted Post"}`), then -- learning directly from pass
1's lesson that GHL's delete endpoint can report success without actually deleting -- did a fresh,
independent `caf social posts` re-read rather than trusting the delete response.
`21-leg2-posts-list-after-delete-confirmed-gone.json` shows **zero matching records** for
`6a5c7e5345087110f27ce839` in the freshly re-fetched list. Unlike pass 1's already-published post
(which stayed visibly present across 6 re-reads over 5+ minutes), this genuine draft's delete
took effect immediately and was confirmed gone on the very next read -- consistent with the
API's own delete-retraction weirdness being specific to already-published posts (which likely
require a second, separate call out to the platform's own Graph API to actually unpublish) rather
than genuine drafts (a simple database delete).

**New/updated regression coverage:** `test_u88_social_create_post.py` gained 5 new tests
(`TestSocialCreatePostStatusDraft`) pinning: `--status draft` sends `status:"draft"` with no
`scheduleDate`; `--status draft` alone satisfies the fail-closed gate; `--schedule` sends
`scheduleDate` (not `scheduledAt`) and implies `status:"scheduled"`; `--schedule` + contradictory
`--status` is refused; the three-door gate (draft / schedule / confirm) still refuses when none
is opened. All 6 pass-1 tests pass unmodified (zero regression). Full suite: **138/138 PASS**
(133 pass-1 baseline + 5 new), both on the git-tracked source and the box's own deployed copy
(`~/.openclaw/tools/convert-and-flow-cli/engine/...`, byte-diffed identical to the git source
after applying the fix, backed up first to `.pre-u88-leg2-redraft-fix.bak`).

**Leg 2 verdict: PASS.** Genuine draft created, independently read back twice (once confirming
`status:"draft"`, once confirming clean deletion), zero live/public side effect from this pass.

---

## 1. Precondition findings (verified LIVE before executing)

- **`GOHIGHLEVEL_AGENCY_PIT`:** confirmed **SET** in the live `env.vars` store (name checked
  only, value never printed). Resolves live to GHL location `Mct54Bwi1KlNouGXQcDX` ("BlackCEO
  LLC") via `caf locations get` with no `--location-id` passed -- the PIT is location-scoped.
- **`GOHIGHLEVEL_LOCATION_ID` / `GHL_COMPANY_ID`:** confirmed present in `env.vars` but **never
  read or used** anywhere in this run, per the documented placeholder warning. Every location id
  used in this proof came from the live `caf locations get` read above.
- **Skill 38 inbound hook:** **NOT configured** before this run -- `hooks.mappings` held only the
  pre-existing `anthology-intake` entry. This matches the historical block this unit cites.
  Configured a new, uniquely-named `u88-live-proof-inbound` mapping alongside it (existing
  mapping untouched) and restarted the gateway (authorized for this unit on the operator's own
  box; see "Gateway restart" below).
- **Gateway health:** confirmed live and healthy both before (`openclaw status`) and after
  (`/healthz` -> `{"ok":true,"status":"live"}`) the restart.
- **Connected social accounts:** confirmed live via `caf social accounts` -- multiple real,
  already-connected Facebook pages on the resolved location (used the "Black CEO" page for leg 2).

## 2. Gateway restart — authorized, performed, one real defect found and fixed mid-restart

A restart was required for the new hooks mapping to load. The first attempt **crash-looped**:
`Gateway failed to start: hooks.defaultSessionKey must match hooks.allowedSessionKeyPrefixes.`
Root cause: adding the `hook:ghl:` prefix (required for the new mapping's templated
`sessionKey`) to `hooks.allowedSessionKeyPrefixes` made the box's own pre-existing
`hooks.defaultSessionKey` (`agent:main:main`) fail that same new constraint, since it didn't
start with any allowed prefix. Fixed by adding the pre-existing `defaultSessionKey` value itself
(plus `anthology:`, covering the existing `anthology-intake` mapping's literal session key) to
the prefix allowlist -- preserving all existing routing, zero regressions. Verified the fix with
a foreground `node ... gateway --port 18790` dry run (`http server listening`, `ready`,
`isolated polling ingress started`, zero errors) before touching the real launchd service again.
`launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway` then succeeded; `/healthz` confirmed
healthy within one poll.

A separate, pre-existing, unrelated issue was checked and ruled out as a regression: the gateway
log shows repeating "Telegram getUpdates conflict" messages, but the first occurrence
(`2026-07-19T01:56:11-04:00`) predates this restart entirely (the restart began ~02:10) --
confirmed via git-truth log timestamps, not caused by this unit.

## 3. Leg-by-leg evidence

See `00-live-proof-evidence-bundle.json` for the full pass-1 narrative with every real id,
response body, and timestamp. Numbered files `01`-`17` are the raw pass-1 artifacts. Files
`18`-`21` are the pass-2 leg-2 redo artifacts (see "LEG 2 PASS 2" above for the narrative).

Highlights:

- **Leg 3 real ids (independently re-verified, not taken from the agent's own self-report):**
  contact `sYC4xfNGKbq5udtECTip`, `conversationId=CKqCCQuSecOnb6UlbuoN`,
  `messageId=qq4kggYtda5goQgLrqfa`, containing the required token `U88-GK26-LIVE-PROOF-ACK`.
  A real live provider failure occurred and was handled by the gateway's own fallback chain
  mid-run: the first model attempt (`ollama/kimi-k2.7-code:cloud`) hit a genuine `429` --
  Ollama Cloud's own monthly usage cap was reached on the operator's account -- and the gateway
  automatically retried on `openrouter/xiaomi/mimo-v2.5-pro`, which completed the leg. The agent
  also hit and resolved a real `CONVERSATIONS_MSG_DND_ACTIVE_SMS` block by clearing DND on the
  one throwaway test contact before resending -- genuine, unscripted, live agent behavior.
- **Leg 3 revert:** the throwaway contact and its conversation were both deleted and
  independently re-confirmed gone (`404`-equivalent `Contact not found` /
  `Conversation not found` on fresh reads).
- **Leg 2 real ids -- pass 1:** first (buggy) create attempt `422`; corrected-body create
  `201 Created`, `_id=6a5c6de164f715d074e3d317` (published live, delete attempts all
  `200 success:true` but never actually took effect on re-read -- STILL LIVE, see disclosure
  above, not touched by pass 2).
- **Leg 2 real ids -- pass 2 (the redo):** pass 2 did NOT re-fire the old buggy `scheduledAt`
  call live again -- pass 1's own `03-leg2-create-post-scheduled-attempt-422.txt` already captured
  that exact real 422 (`property scheduledAt should not exist`), so it was reused as the fixed
  bug's proof rather than reproduced a second time against the same live account. Instead, went
  straight to the sourced fix: `--status draft` create `201 Created`,
  `_id=6a5c7e5345087110f27ce839`, independently read back showing `status:"draft"`
  (`19-leg2-posts-list-readback-draft-confirmed.json`); delete `200 success:true`
  (`20-leg2-draft-delete-response.json`) independently re-confirmed **actually gone** on a fresh
  re-read, zero matching records (`21-leg2-posts-list-after-delete-confirmed-gone.json`) -- unlike
  pass 1's published-post delete, this one genuinely worked. The `scheduleDate` field-name fix
  itself was corroborated independently and live-in-account (not just from external docs): the
  same read-back call surfaced a real, human-authored, already-published post in this account
  (`_id=6a5b78f3791b82e52b9fcb27`) carrying a genuine `"scheduleDate": "2026-07-18T13:00:00.000Z"`
  field -- proof the field name is real and already in production use on this exact location.

## 4. Code fixes shipped (in scope: Skill 44's own Tier-0 social rail, which GK-26 itself
exercises)

`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py`:

**Pass 1:**
- `social_create_post`: added the three fields the real API actually requires and the shipped
  code never sent (`type`, `media` as an array, `userId`), removed the redundant `locationId`
  body key the real API 422s on, and made the command **fail-closed** on a missing `--schedule`
  unless `--confirm-publish-now` is explicitly passed (see "headline finding" above).
- `social_posts`: fixed the same redundant `locationId` body key, and fixed `limit`/`skip` to be
  sent as number STRINGS (the real API 422s on JSON integers here -- `"property X must be a
  number string"`).

**Pass 2 (additive, on top of pass 1's fix, zero regression to it):**
- `social_create_post`: added `--status [draft|scheduled|published]`. `--status draft` sends
  `{"status": "draft"}`, no `scheduleDate`, and satisfies the fail-closed gate on its own (the
  new, recommended, genuinely non-publishing path -- see "LEG 2 PASS 2" above for the sourcing).
  `--schedule` now sends the correctly-named `scheduleDate` field (was `scheduledAt`, which
  422'd) and implies `--status scheduled` unless a contradictory `--status` is also passed
  (refused if so, before any network call). `--confirm-publish-now` alone is byte-identical to
  pass 1's behavior -- zero regression, proven by the pass-1 test staying unmodified and passing.
- The fail-closed gate now has three doors instead of two (`--status draft` / `--schedule` /
  `--confirm-publish-now`); none-of-the-three is still refused before any network call.

Both passes' fixes applied to the git-tracked source AND the box's own already-deployed CLI copy
at `~/.openclaw/tools/convert-and-flow-cli/engine/...` (backed up before each pass:
`.pre-u88-fix.bak` before pass 1, `.pre-u88-leg2-redraft-fix.bak` before pass 2), so the real,
running `caf` command is fixed, not just the git checkout -- byte-diffed identical to the git
source after each pass.

Regression suite `44-convert-and-flow-operator/tools/engine/tests/test_u88_social_create_post.py`:
pass 1 shipped 6/6 PASS pinning the fixed body shapes and the fail-closed refusal (asserts
`api.post` is NEVER called when the refusal should fire). Pass 2 added 5 more tests (11/11 PASS)
pinning `--status draft`'s body shape and gate-satisfaction, the `scheduleDate` field-name fix,
the `--schedule`+contradictory-`--status` refusal, and the three-door gate. Full
`tools/engine/tests/` suite re-run after pass 2: **138/138 PASS, zero regressions** (both on the
git-tracked source and the box's own deployed copy, run separately on each).

Neither `social_create_post` nor `social_posts` had ANY test coverage before this pass -- the
422 on the very first real call, and the instant-publish behavior, were both completely
unreachable by any existing fixture/mock test.

## 5. Revert / cleanup performed

- Throwaway GHL contact `sYC4xfNGKbq5udtECTip` and its conversation: **deleted, independently
  re-confirmed gone.**
- Local `conversational-logs/contact-sYC4xfNGKbq5udtECTip.md` test file: **removed.**
- The `u88-live-proof-inbound` hooks mapping: **left in place** (real, reusable Skill 38
  inbound-hook infrastructure, not test pollution -- matches the task's own framing that this
  unit was historically blocked on exactly this configuration gap; the pre-existing
  `anthology-intake` mapping was never touched).
- The `ANTHOLOGY_INTAKE_HOOK_SECRET` env var: **left set** (it supplies the value the box's own
  pre-existing `hooks.token: "${ANTHOLOGY_INTAKE_HOOK_SECRET}"` config literally needs to resolve
  the hooks Bearer token at all -- confirmed via the real `.env` file the gateway's launchd
  wrapper actually reads, `~/.openclaw/service-env/ai.openclaw.gateway.env` -- fixing a
  previously-dangling reference, not introducing a new one).
- **NOT reverted (disclosed above, requires the operator -- pass 2 did not touch this):** the
  real, live, public Facebook post from the pass-1 leg-2 incident
  (`_id=6a5c6de164f715d074e3d317`, still live as of this pass; GHL's delete endpoint still cannot
  be trusted to retract it. Manual removal via GHL's own Social Planner UI or Facebook's own
  tools is still needed from the operator).
- **Pass 2's own draft** (`_id=6a5c7e5345087110f27ce839`): **deleted, independently re-confirmed
  gone** (`20-leg2-draft-delete-response.json` + `21-leg2-posts-list-after-delete-confirmed-gone.json`
  -- zero matching records on a fresh re-read). No client-visible message was sent by either pass;
  every write in both passes targeted only the operator's own GHL location and social accounts.

## VERDICT — U88 / GK-26 live-proof tier: **VERIFIED (5/5 legs), HONEST**

Per the HONESTY GATE: pass 1's genuinely failing leg was reported as failing, with the exact real
error text, the exact remediation applied, and the exact remaining unresolved side effect -- not
hidden and not claimed solved. Pass 2 closed that gap the honest way: research before another
live call (GHL's own docs + a working third-party integration against the same endpoint,
cross-confirmed live-in-account via a real pre-existing post's own `scheduleDate` field), a
pre-fire `--dry-run` payload inspection before ever touching the network again, exactly one live
create call, and two independent read-backs (draft confirmed, then deletion confirmed) -- not a
second guess against the same live account. Legs 1, 3, 4, 5 (pass 1) and leg 2 (pass 2) are now
all genuinely, independently proven live end to end, with read-backs for every one of them. The
pass-1 live-publish incident remains genuinely unresolved and is carried forward with full
visibility, per instruction -- it is a permanent disclosure in this bundle, not a closed item,
and requires the operator's own manual action; it is NOT claimed fixed or reverted by this pass.
