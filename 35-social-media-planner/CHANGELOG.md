# Changelog - Social Media Planner (Skill 35)

## v2.9.11 - 2026-07-15 — GK-20 regression proof: text_bearing_medium-band-floor-sized prompt clears pregen_prompt_gate.py on Ideogram V3 DESIGN

### Added
- **`scripts/test_pregen_prompt_gate.py` case 6.** Skill 45's `prompt-bands.json` gained a NEW
  `text_bearing_medium` band (GK-20 band<->routing reconciliation — the band the mandatory
  Ideogram V3 DESIGN quote-card/text-led route now resolves to). This gate's own routing logic
  (`TEXT_CAPABLE_MODELS`/`NON_TEXT_MODELS`) needed no code change — it already routes
  `ideogram-v3-design` correctly — but a new regression case proves the SAME reconciled-band-floor
  prompt (>=1,600 chars, the new GIP band's own floor) clears BOTH `diu_validator.py prompt-band`
  (Skill 45's `test_prompt_band_cli.py` case 5) AND this gate (exit 0), closing the loop on GK-20's
  BINARY acceptance criterion end-to-end rather than proving each gate in isolation.

### Version
- **Skill 35 independent line:** skill-version.txt v2.9.10 → v2.9.11; SKILL.md frontmatter version
  v2.9.10 → v2.9.11 (must match the frontmatter-version-guard).

## v2.9.10 - 2026-07-12 — P3-08 merge (renumbered v2.9.9→v2.9.10): QC-fix — CTA lockstep completed in example templates + comment-reader injection fencing

### Changed
- **CTA lockstep finished in residual example templates.** §12/§19/pitch-schedule were already DM-first, but example TEMPLATES still modeled comment-only CTAs that the new §19 checklist would REJECT (a post with only the comment directive and no DM CTA FAILS). Added the PRIMARY "send us a message" DM CTA (with the comment link as backup) to: carousel Slide 7 (§ Carousel Slide Structure), the canonical JSON post-body `summary` example, the carousel-caption and video-caption example placeholders, and the `caf social create-post --text` CLI example. Content generated from these templates no longer auto-fails §19.

### Security
- **Comment-reader injection fencing (`scripts/comment_reader.py`).** Public comments are the lowest-trust inbound surface, and Skill 38 consumes `conversational-logs/` as conversation history. The reader now sanitizes every field before writing: the comment BODY is wrapped in a clearly-delimited `UNTRUSTED-PUBLIC-COMMENT` block with line-leading markdown structure (`#`/`-`/`>`/`|`/code fences/…) escaped, and single-line fields (author, permalink, comment_id) are newline-collapsed — so a crafted comment can no longer forge a Skill-38 `### Inbound` turn or inject a `- text:` field / instructions. New fail-first tests (`test_comment_reader.py`): spoofed-turn, code-fence breakout, and field-injection are all neutralized.

## v2.9.9 - 2026-07-11 — P3-08 merge (renumbered v2.9.8→v2.9.9): Gap B — DM-first CTA + comment reader (comments become conversations); Gap C weekly-link automation

### Changed
- **DM-first two-channel CTA (playbook §12, §6 pitch examples).** The primary call-to-action is now "send us a message / DM" (which reaches an agent that answers via GHL Conversations → Skill 38's inbound pipeline), with "the link is in the comments" as the reach-preserving backup. Previously the highest-intent CTA funneled prospects to public comments, which NOTHING in the repo reads or replies to — a prospect who commented got no automated reply from anywhere.
- **§19 QC checklist updated in LOCKSTEP.** The comment-CTA check is replaced by two checks: the PRIMARY DM CTA must be present, and the BACKUP comment-link directive must be present; a post with only the comment directive and no DM CTA now FAILS QC.

### Added
- **Comment reader (playbook §12b, `scripts/comment_reader.py` + `scripts/test_comment_reader.py`).** Phase-4 Engagement Monitor sub-task: polls prospect comment REPLIES and surfaces each as a synthetic inbound handoff into Skill 38's `conversational-logs/`, tagged with post/permalink context. Per-channel honesty: a channel with no comment-read API surface is ledgered + skipped, never fabricated (`CHANNEL_COMMENT_SURFACE` registry; FB/IG wired, others None until proven live).
- **Cross-reference to Skill 38** (SKILL.md Phase 4): Skill 38 owns every inbound conversation Skill 35's CTAs generate; Skill 35 is the inbound SOURCE (DM-CTA + comment handoff). Reciprocal reference added in `38-conversational-ai-system/SKILL.md`.
- **Gap C — optional themed weekly landing page** (playbook Step 4): the weekly campaign step MAY invoke Skill 6's `funnel_matcher.py --match` when the client supplies no static link; a client-provided link ALWAYS wins (sovereignty). Optional-graded.

## v2.9.8 - 2026-07-12 — P3-05: PRE-generation prompt QC gate, Ideogram routing for text-overlay images, Skill-45 negative-prompting wiring, input-quality gate on graphics-department assets

### Added
- **`scripts/pregen_prompt_gate.py`** (stdlib-only, mirrors `diu_validator.py prompt-band`'s fail-closed exit-code discipline: 0 pass / 2 usage / 3 FORM failure `AF-SM-PROMPT-FORM` / 6 quality-or-routing failure `AF-SM-MODEL-ROUTING` / `AF-SM-INPUT-QC-GATE`). Gates every assembled image prompt BEFORE the paid kie.ai generation call: platform ratio + pixel spec present, brand colors named, a merged negative/avoid-list attached, the Section-18 on-image copy baked verbatim, the mandatory brand-safety clause present; then routing (a text-overlay prompt on a non-text-rendering model is refused outright) and, for graphics-department-sourced assets, a SOP-GIP-02 QC receipt scoring >= 8.5 is required or the asset is rejected, not posted.
- **`scripts/test_pregen_prompt_gate.py`** — real CLI-level (subprocess) fail-first tests: an under-specified prompt is refused (exit 3); a text-overlay prompt on Nano Banana is refused (exit 6) and the SAME prompt passes once re-routed to Ideogram V3 DESIGN; an ungated graphics-department asset is refused and a >=8.5-receipted one passes; a non-text prompt on Nano Banana passes (the routing rule is text-overlay-only).
- **playbook.md Section 8a** (PRE-generation prompt QC gate) and **Section 8b** (mandatory load of Skill 45's `NEGATIVE-PROMPTING-SOP.md` + `social-media-designs/_RULES.md` BEFORE writing any image prompt) — closes the P3-05 root-cause finding that Skill 35's only prompt-level check was one generic post-generation checklist line, with zero memory of prior failure classes.
- **playbook.md Section 19a** — the input-quality gate on Graphics-department-sourced assets (P3-05 step 4i): the planner rejects an asset lacking a SOP-GIP-02 receipt >= 8.5 instead of posting it.
- **INSTRUCTIONS.md Phase 2** — the Image Prompt Engineer step now states the load-before-write + gate-before-generate contract explicitly, and the Cross-references section names Skill 45 as the owner of the negative-prompting/category rules this skill must load.

### Changed
- **playbook.md Section 8 model table** — every Skill 35 image carries a baked text/headline overlay (Section 18), so the model table now routes ALL of them to **Ideogram V3 DESIGN** (per Skill 45's own documented routing rule) and reserves Nano Banana 2/Pro for non-text imagery only. This closes the root-cause gap the P3-05 investigation named: Nano Banana is not a text-rendering specialist, which plausibly drove the Section 18 "spelling errors on image text, retry up to 3x" loop.
- **playbook.md Section 18** ("If Image Text Has Spelling Errors") — the retry procedure now checks routing + gate compliance FIRST, before assuming the copy itself is the defect.
- **playbook.md Section 19 Image Checks** — added checks that the prompt passed the pre-generation gate, that text-overlay images were routed to Ideogram V3 DESIGN, and that any graphics-department-sourced asset carries a passing SOP-GIP-02 receipt.

## v2.9.5 - 2026-07-01 — Command Center token resolution: Mac/VPS-aware candidate paths, loud single skip warning

### Fixed
- **`_cc_resolve_token` (Command Center MC_API_TOKEN lookup) in `run-publishing-cycle.sh`** only
  checked the legacy `$HOME/command-center/app/.env.local` path, so a Command Center installed at
  the current `run-full-install.sh` `DASHBOARD_DIR` (`~/projects/command-center` on Mac,
  `/data/projects/command-center` on VPS) was invisible to the publishing cycle and every Kanban
  update silently skipped. Now checks 5 candidates in priority order — an already-set env var,
  `~/projects/command-center/.env.local`, `~/projects/command-center/.env`,
  `/data/projects/command-center/.env.local`, `/data/projects/command-center/.env` — with the
  legacy `command-center/app/.env.local` path checked last for backward compat.
- **De-duplicated the skip warning.** When no token is found, `_cc_resolve_token` now emits one
  `[CC-SKIP]` warning listing every path it checked (via a new `CC_TOKEN_SKIP_LOGGED` guard so it
  fires once per run), and `cc_call`'s own generic "Command Center skipped" warning is removed so
  callers no longer see two vague, redundant messages for the same condition. Board-update skip
  remains fail-soft — publishing continues unaffected.

## v2.9.4 - 2026-06-30 — GHL posting ladder, runtime preflight, 0-posts-as-error, Command Center Kanban, QC fix

### Added
- **Command Center Kanban lifecycle** in `scripts/run-publishing-cycle.sh` — the cycle now creates ONE board task (with a description so the Triad gate accepts it), PATCHes it `in_progress` at cycle start and `review` at hand-off. Promotion `review->done` is left to the independent QC scorer (the builder never self-grades; the script never sets `done`). Every Command Center call is **fail-soft**: `MC_API_TOKEN` unset or board unreachable => logs `Command Center skipped`, creates no task, and the run finishes exactly as before (manifest + READY file, exit 0). Token resolved from `$MC_API_TOKEN` or `~/command-center/app/.env.local`; never printed. New "Command Center" subsection added to `INSTRUCTIONS.md`.
- **Runtime GHL credential preflight (HARD-STOP)** in `run-publishing-cycle.sh` — missing `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` now STOPS the cycle (exit 3) with a plain-English, operator-facing reason instead of staging a manifest that cannot post. Opt-in live probe (`SKILL35_LIVE_PREFLIGHT=1`) additionally hard-stops on PIT 401/403 or **zero connected social accounts**, emitting a client-facing message; transient network errors only WARN.
- **Deterministic 0-posts-as-error gate** — new `--verify-receipts <path>` mode reads `publish-receipts.json` and HARD-FAILS (exit 6) when accounts are connected but 0 posts were created, or posts were planned but 0 created. Documents the `publish-receipts.json` contract (planned/created/connected counts + per-post platform/url/post_id/tier).

### Fixed
- **GHL posting ladder (playbook Section 17 rewrite):** Section 17 now leads with the Tier 0->3 ladder (Tier 0 `caf` -> Tier 1 official MCP -> Tier 2 community MCP -> Tier 3 raw REST as last resort) instead of "raw REST only / no external tool." Documents the **`CAF_APPROVAL_TOKEN` unblock** (caf's safety gate refuses every write unless an approval token is scoped to the social-post call — verified in `safety_gate.py`), the `caf --dry-run` preview, and caf's real body schema (`accountIds` + `media:[{url,type}]` + `scheduledAt`). Adds an explicit SCHEMA NOTE that caf's body differs from the Tier-3 `socialMediaAccountIds` + `mediaUrls` shape (verify against live GHL docs — not guessed).
- **3 GHL-call bugs:** (1) `caf social accounts --json` -> `caf --json social accounts` (`--json` is a group-level flag and must precede the subcommand — verified in `gohighlevel_cli.py`); (2) connection-check MCP call `get_platform_accounts` + `POST $MCP_URL/execute {"name","arguments"}` -> `get_social_accounts` + JSON-RPC `tools/call` (fixed in `INSTRUCTIONS.md`, `INSTALL.md`, `QC.md`, `qc-skill35.sh`); (3) get-accounts endpoint reconciled to the verified clean list `GET /social-media-posting/{locationId}/accounts` (what `caf` uses) instead of the per-platform get-ONE that needs an accountId you don't have. The comment `/posts/{id}/reply` route is flagged UNCONFIRMED (verify before use) rather than changed blindly.
- **Install-QC contradiction (P0):** `qc-skill35.sh` no longer asserts `--announce` is present on the `skill35-weekly-theme` cron — the gateway REJECTS `--announce --channel` on main-target crons, so that assert hard-failed install-QC every run. It now asserts the real invariant (registration on `sessionTarget=main`).
- **Duplicate QC script:** `qc-social-media-planner.sh` is now a thin shim that `exec`s `qc-skill35.sh` (single source of truth; ends the v2.2.0-vs-v2.3.0 drift while preserving the historical entry point).
- `scripts/register-weekly-cron.sh` — `echo "$(_existing_count) ..."` command-substitution bug -> `${_existing_count}`.
- `scripts/run-publishing-cycle.sh` — removed the dead `[ $# -lt 0 ]` check (never true).
- `scripts/merge_reel.sh` — duration QC float comparison now uses `awk` (already required) instead of `bc`, so the gate no longer crashes on minimal VPS images that lack `bc`.
- `scripts/weekly-batch.sh` — logs to persistent `~/.openclaw/data/skill35/logs/` instead of `/tmp` (which is cleared on reboot).
- `wire.sh` — now fail-soft: an `EXIT` trap logs and forces exit 0 so a wiring hiccup never aborts the fleet update run.
- VPS secrets path clarified to `/data/.openclaw/secrets/.env` (resolve from `/data/.openclaw`, not `~`) in `INSTALL.md`.
- ImageMagick 7 `magick`/`convert` fallback added to `INSTALL.md`, `QC.md`, and `CORE_UPDATES.md` so the carousel/cover steps work on IM7.

### Models (client-provider policy — NEVER Anthropic)
- `SKILL.md` Usage gained a per-role model-tiering table using client providers only: high-reasoning (Researcher/Strategist) -> DeepSeek v4 pro or GLM 5.2; content/HTML writing (Writer/Editor/Image-Prompt/Email) -> GLM 5.2; browser/tool-calls/QC (Publisher + 6 QC agents) -> MiniMax 3; mechanical -> client default. Ollama Cloud preferred, OpenRouter backup, reasoning effort HIGH. Explicit reminder never to recommend/hardcode an Anthropic/Claude model for a client agent. Removed the contradictory "does NOT require any external CLI tools" line.

### Doc reconciliation
- Publisher role + TOOLS.md now say "every channel connected in GHL (live-queried)" instead of a fixed "6/8 platforms" count.

## v2.9.3 - 2026-06-30 — docs fix: corrected `caf social` commands to the real CLI surface

### Fixed (documentation vs CLI drift)
- Corrected the documented `caf social` commands to the real CLI surface:
  `caf social create-post`, `caf social accounts`, and `caf social posts`, with the actual
  flags `--account-id` / `--text` / `--media-url` / `--schedule`.
- Removed the non-existent `caf social schedule`, `caf social list-accounts`, and
  `caf social status` commands from CORE_UPDATES.md, INSTALL.md, INSTRUCTIONS.md, and SKILL.md
  (the engine exposes no such subcommands — confirmed against
  `tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py`).

## v2.9.0 - 2026-06-15 — cron auto-install: fail-loud wiring + deduplication + QC assertion

### Root cause fixed
The `skill35-weekly-theme` cron was a MANUAL agent step that could be silently skipped.
`register-weekly-cron.sh` existed but had zero callers in any installer path. On any box
where the install agent skipped the INSTRUCTIONS.md activation block, the weekly trigger
was absent — discovered on a client box where the agent self-reported the gap in conversation.

### Changes
- `scripts/register-weekly-cron.sh` — hardened (was: basic idempotency guard + registration):
  - DEDUPLICATION: reads `openclaw cron list`, detects stale/erroring/duplicate entries for
    `skill35-weekly-theme`, deletes them all before registering a clean single entry. Handles
    a live duplicate situation (two entries: one erroring isolated, one new idle main).
  - FAIL-LOUD: exits non-zero on any registration failure; callers must check exit code.
  - POST-REGISTRATION QC ASSERTION: asserts exactly 1 entry, `sessionTarget=main`, after
    registration. Hard-fails with exit 3/4 if count != 1 or main target not confirmed.
  - MARKER PATH UNIFIED: `~/.openclaw/data/skill35/weekly-theme-last-run.json` only.
    Removed the `/tmp/skill35-weekly-theme-$(date +%Y%U).done` reference (not persistent
    across reboots — /tmp is cleared on restart, making idempotency unreliable Saturday-to-
    Saturday).
  - SESSION TARGET: `main` only (`isolated` + `--channel` is gateway-rejected — confirmed
    a client box 2026-06-15).
  - MODEL: cheap/free (flash or free OpenRouter fallback) — never the metered pro model.
    Documented via `SKILL35_CRON_AGENT` env var override.
- `INSTALL.md` Step 9 — replaced manual HEARTBEAT.md prose with automated, fail-loud call to
  `register-weekly-cron.sh`. Install MUST NOT proceed to Step 10 unless exit 0 confirmed.
  Added HEARTBEAT.md cleanup block (remove stale Saturday ungated entry if present).
- `INSTALL.md` Completion Checklist — replaced stale "HEARTBEAT.md updated with Saturday
  theme-request schedule" with:
  - `register-weekly-cron.sh` exited 0 (hard fail if not)
  - QC assert: exactly 1 cron entry, main target, `0 8 * * 6`
  - HEARTBEAT.md does NOT contain the ungated Saturday block
- `QC.md` — rubric row "Heartbeat scheduled" replaced with "Weekly theme cron registered
  (AUTO-FAIL)": programmatic check `openclaw cron list | grep -c skill35-weekly-theme == 1`.
  Hard-fails QC regardless of total score if absent/wrong. Added cron assertion bash block
  under "Cron presence assertion (AUTO-FAIL gate)" section.
- `INSTRUCTIONS.md` §"Activation — install the weekly theme cron" — replaced inline manual
  bash block with pointer to the script + break-glass inline for when script path unavailable.
  Documented the `--announce --channel last` rejection on main-target crons (confirmed live).
  Unified marker path in all documentation to `~/.openclaw/data/skill35/weekly-theme-last-run.json`.
- `skill-version.txt` — v2.7.1 → v2.9.0.

### Furnace safety confirmation
- Schedule: `0 8 * * 6` (Saturdays 8 AM only — weekly, never sub-daily).
- No retry loop on failure (single registration attempt, fail-loud).
- Model: cheap/free (cron message instructs the agent to use flash/free OpenRouter).
- Idempotency: marker file prevents double-fire within same ISO week.
- Fleet-wide: every new Skill 35 install now auto-registers the cron as a hard step.

### Coordination with PR #250 (fix/skill35-heartbeat-furnace)
PR #250 removes the ungated HEARTBEAT.md entry. This PR wires the cron registration as
the automated replacement. Together: HEARTBEAT entry gone + cron auto-installs = correct
weekly trigger, no furnace, no silent-skip.

---

## v2.8.1 - 2026-06-15 — complete-answer fix: enabled-channels model + Owner Q&A Playbook

### Problem
An owner asked "how do I use my social media planner skill?" and received an answer listing only "8 platforms: WordPress, Medium, Substack, LinkedIn, GHL blog, YouTube, X/Twitter, Facebook." This omitted Instagram, TikTok, Pinterest, Google Business Profile, Facebook carousels, and Reels — all of which are primary capabilities. Root cause: SKILL.md description, SKILL.md Purpose, SKILL.md Key Principles, and INSTRUCTIONS.md "What this skill does" all carried a stale fixed list. The agent read those files first (mandatory TYP read-order) and parroted the wrong list without triggering the live GHL check.

### Fix 1 — Replace stale platform list in SKILL.md (description + Purpose + Key Principles)
- Removed the stale "8 platforms (WordPress, Medium, Substack, LinkedIn, GHL blog, YouTube, X/Twitter, Facebook)" string from the frontmatter description, the Purpose section, and the Key Principles section.
- Replaced with the correct two-tier model: **primary GHL Social Planner channels** (Facebook incl. carousels/Stories/Reels, Instagram incl. Reels/carousels/Stories, LinkedIn incl. PDF carousels, X/Twitter, TikTok, Pinterest, Google Business Profile) + **optional add-on channels** (WordPress, Medium, Substack, YouTube).
- Added explicit statement that the enabled set is determined at runtime by a live GHL connected-accounts query, not a fixed list.
- Added full content-types list to Purpose: daily posts, Thursday carousels, Reels, comments with action link, blog post, email newsletter, podcast.

### Fix 2 — Add Owner Q&A Playbook to SKILL.md
- New "Owner Q&A Playbook" section in SKILL.md specifies the mandatory response protocol when an owner asks "what does the planner do?" or "how do I use it?".
- Mandatory steps: run live GHL check first, build enabled-platforms list from live result, answer with all required elements.
- Required elements enumerated: full platform list (from live query), content-types statement, scope statement ("I update every channel connected in GHL — currently: [live list]"), how-to-trigger, optional-add-ons note.
- Complete example answer provided (with [LIVE CHANNELS] placeholder that MUST be filled from the actual query).

### Fix 3 — Replace stale list in INSTRUCTIONS.md "What this skill does" section
- Removed "8 platforms: WordPress, Medium, Substack, LinkedIn articles, GHL blog, YouTube, X/Twitter, Facebook" from INSTRUCTIONS.md line 13.
- Replaced with the enabled-channels model matching SKILL.md (same primary + optional two-tier description).
- Added new "Owner scope question — LIVE CHECK MANDATORY" section immediately after — four rules: run check-social-connections first, answer with full picture, never answer from a fixed list, include all required answer elements. Scope answer that omits a connected platform fails QC.

### Fix 4 — Extend banned-failure rule to cover scope/capability questions
- Extended the existing INSTRUCTIONS.md banned-failure rule (previously scoped only to connection-status answers) to also cover scope/capability answers ("what does it do?", "what does it update?").
- Rule now explicitly names the failure pattern: answering with "8 platforms: WordPress, Medium, Substack..." when Instagram, TikTok, Pinterest, Google Business Profile, and carousels are connected.

### Fix 5 — QC.md auto-fail gate for documentation integrity
- New "SKILL DOCUMENTATION INTEGRITY" section in QC.md (hard auto-fail gate).
- 11 checkboxes guarding: stale string absent, correct primary channels named (incl. Instagram + TikTok), Owner Q&A Playbook present, INSTRUCTIONS.md scope-question rule present, cross-file consistency across SKILL.md/INSTRUCTIONS.md/README.md/CORE_UPDATES.md.
- Programmatic check commands included (grep for stale string, grep for required strings).

### Version bumps
- `SKILL.md` frontmatter version: v1.4.0 → v1.5.0
- `INSTRUCTIONS.md` version: v10.12.0 → v10.13.0
- `skill-version.txt`: v2.8.0 → v2.8.1

### Risk
Low-to-medium. All changes are additive documentation and a new QC gate. No GHL API calls, publish logic, scheduling, or webhook behavior altered. The live-check-first rule was already present for connection-status answers; this extends it to scope-question answers.

---

## v2.8.0 - 2026-06-15 — furnace root cause fix: ungated HEARTBEAT.md block removed + guard pattern + QC enforcement

### Changed (heartbeat-furnace fix, part of onboarding v12.14.0)

**Root cause eliminated:** INSTALL.md Step 9 previously appended an ungated `### Saturday 8:00 AM — Social Media Theme Request` block to the client's live HEARTBEAT.md. The agent reads HEARTBEAT.md on every heartbeat tick; without a day-of-week gate or idempotency marker, the full Skill-35 content pipeline fired on every tick.

- **INSTALL.md Step 9** — Replaced the ungated HEARTBEAT.md prose block with a FURNACE RULE hard-block directive. Provides the cron activation path (from INSTRUCTIONS.md §"Activation") and a removal script for existing installs.
- **INSTALL.md Completion Checklist** — Updated the `HEARTBEAT.md updated` item to `skill35-weekly-theme cron registered`.
- **INSTRUCTIONS.md §Weekly trigger** — Removed "informational context only" language; states the block MUST NOT exist.
- **INSTRUCTIONS.md §Guard pattern** — New section: reusable HEARTBEAT guard pattern (day-of-week gate + idempotency marker) for any future recurring task.
- **qc-skill35.sh / qc-social-media-planner.sh Section I** — Fix #3 hard-fail: INSTALL.md must not contain the ungated Saturday block.
- **skill-version.txt** — Bumped to v2.8.0.


## v2.7.1 - 2026-06-11 — route social posting through Skill 44 (Tier 0) first

### Changed (GHL skills integration review — Tier 0 routing gap)
- The social-posting routing chain previously named Tier 1 (Official MCP) → Tier 2 (Community MCP) → Tier 3 (raw API) but **omitted Tier 0 (Skill 44 / `caf`) entirely**, even though `caf` ships a `social` command group (`list-accounts`, `schedule`, `status`). Inserted Tier 0 as the first stop, matching skill 36's 6-tier chain, so a social post `caf` can schedule directly no longer routes the owner/agent to the MCP or raw API:
  - `CORE_UPDATES.md` — the routing header is now "6-tier GHL routing (Tier 0 = Skill 44, primary)"; the AGENTS.md posting-path bullets gained a "(if skill 44 installed — PRIMARY)" branch via `caf social schedule`.
  - `INSTALL.md` Step 4 — detects Skill 44 (Tier 0) ahead of Skill 36; routing list leads with `caf social schedule`.
  - `INSTRUCTIONS.md` `check-social-connections` — added a Tier 0 `caf social list-accounts` branch ahead of the MCP branch.
- Media upload kept as the documented Tier 3 exception (`POST /medias/upload-file` — `caf` has no media commands). n8n/Google-Sheets/Podbean planning steps are outside GHL and unchanged.

## v2.7.0 - 2026-06-10 — Appendix A: credential path + name cleanup (no behavior change)

### What changed
- INSTRUCTIONS.md: two table rows changed `~/.openclaw/credentials/.env` -> `~/.openclaw/secrets/.env`; `GHL_LOCATION_ID` -> `GOHIGHLEVEL_LOCATION_ID` in the path column. (`credentials/.env` goes to true zero in active instruction text.)
- SKILL.md: three occurrences of `[from secrets/.env: GHL_LOCATION_ID]` -> `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`.
- CORE_UPDATES.md: one credential row changed `GHL_PRIVATE_TOKEN + GHL_LOCATION_ID` -> `GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID`.
- `GHL_PRIVATE_TOKEN` and `GHL_LOCATION_ID` REMAIN in INSTALL.md/QC.md/qc-*.sh as DELIBERATE deprecated-name guardrails ("do not use these names") — those guardrails are intentionally protective and are NOT changed.
- wire.sh added: M4 migration checks for stray `GHL_PRIVATE_TOKEN=` and `GHL_LOCATION_ID=` entries in the box's secrets file and mirrors values to the canonical names (copy-not-delete, no value logged, chmod 600 preserved).

## v2.6.0 - June 9, 2026

### Fix — Wire row-logging to new social-planner-row-append webhook (fleet-wide planner bug fix)

**Why:** Content never landed in clients' Google Sheet planners. The only n8n webhook (`social-planner-sheet-create`) CREATES a new sheet on every call and has no row-append path. After produce → GHL upload → get CDN link, the row-log step had nowhere to write.

**What:**
- Built new n8n workflow `social-planner-row-append` (ID: `myXde6jbIIkaG5zW`) on `main.blackceoautomations.com`:
  - `POST /webhook/social-planner-row-append` with body `{sheetId, row: {Week Of, Theme of the Week, ..., Notes}}`
  - Code node maps `body.row.*` fields to the 20-column order of the **Weekly Overview** tab
  - HTTP Request node calls `sheets.googleapis.com/v4/spreadsheets/{sheetId}/values/Weekly%20Overview!A:T:append` with the operator's Google Sheets OAuth2 credential (`4IoTZHAybRblm172` — management blackceo Google Sheets account)
  - Returns `{success: true, sheetId, updatedRange}` on success
  - Workflow is ACTIVE; webhook path is production-ready
- **SKILL.md Media Delivery Contract step 4**: rewrote from vague "Log a row" to explicit `social-planner-row-append` curl call with full payload contract. Added clear note: `social-planner-sheet-create` is for first-time creation ONLY.
- **INSTALL.md Step 7 section 4f**: Clarified the two-webhook architecture — `sheet-create` (once, at install) vs `row-append` (every publish cycle). Explicit payload contract for each. No client Google credentials required — both run via operator service account.

**Verified:** Test row successfully appended to a client sheet `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c` Row 6 `'Weekly Overview'!A6:T6` — all 20 columns correctly populated.

**Risk:** Low. Additive webhook + documentation change. No existing publish, schedule, or GHL logic altered.

---

## v2.5.0 - June 9, 2026

### Fix 1 — Remove private operator tool reference; replace with OpenClaw subagent runtime
**Why:** SKILL.md instructed the agent to spawn via a private operator CLI tool (`node ~/.openclaw/workspace/.../cli.js workflow run content-publishing-engine ...`) that must not appear in client-facing skill files. The frontmatter also contained a `workflow_id` field with a comment explaining its origin in that private tool.
**What:**
- Removed all references to the private operator CLI tool from SKILL.md (both repos).
- Removed the `workflow_id: content-publishing-engine` frontmatter field and its private-tool comment. Replaced with `pipeline_id: content-publishing-engine` (neutral identifier, no private-tool language).
- Rewrote the `## Usage` section: primary path is now `sessions_spawn task="Run Content Publishing Engine on [topic]" runtime="subagent" model="ollama/minimax-m2.7:cloud"` (OpenClaw subagent runtime). Fallback model documented. Subagent pipeline behavior described.

### Fix 2 — Content sheet: agent always knows the link; graceful-degrade on Sheets write
**Why:** Agent responded "gws is not authenticated — can't create the Google Sheet content calendar" and "I don't have the social-media-planner spreadsheet link." Root cause: (a) no stored pointer to the content sheet, and (b) the skill tried to call Google Sheets API directly using an OAuth path it doesn't have credentials for.
**What:**
- Added `content_sheet_id` and `content_sheet_url` fields to the skill config contract in SKILL.md. Agent reads these before every run and can answer "what's my social media planner link?" instantly.
- INSTALL.md Step 7 rewritten: adopt-existing-sheet-first logic (check MEMORY.md → check onboarding-provided ID → create via webhook). Any pre-existing client sheet adopted if present, never duplicated.
- Step 7 now records `content_sheet_id` + `content_sheet_url` in MEMORY.md and wires them into `openclaw config env.vars.SKILL35_CONTENT_SHEET_ID/URL` so the agent has them at runtime.
- Added Step 7 sub-section 4f documenting the auth path: the agent does NOT call Google Sheets API directly and never needs `client_secret.json`. All sheet creation goes through the `https://main.blackceoautomations.com/webhook/social-planner-sheet-create` n8n webhook (BlackCEO Automations service account). If the webhook is unavailable the agent logs to a local `.jsonl` file and queues retry — never dead-ends with "gws is not authenticated."
- CORE_UPDATES.md MEMORY.md section: `content_sheet_id` and `content_sheet_url` fields added.
- Completion checklist: 4 new assertions covering sheet ID, sheet URL, link-answer test, and media delivery.
- Step 11 client confirmation message: "Content calendar sheet: [link]" replaces the generic "Google Sheet created" line.

### Fix 3 — Media delivery via GHL CDN public link (eliminates Telegram size-cap failures)
**Why:** Finished media (Reels, podcast MP3s, image sets) was being sent as raw Telegram attachments, hitting the Bot API size cap, or the agent said "stored locally, I don't have a URL." Clients received no usable media link.
**What:**
- Added `## Media Delivery Contract` section to SKILL.md (both repos) documenting the mandatory delivery path:
  1. Produce file locally.
  2. Upload to client's own GHL Media Library via `POST https://services.leadconnectorhq.com/medias/upload-file` with `Authorization: Bearer [GOHIGHLEVEL_API_KEY]`, `Version: 2021-07-28`, multipart form fields `file`, `hosted=true`, `fileProcessingOpts={"forceReprocess":true}`. Response contains a `url` field.
  3. CDN URL format: `https://assets.cdn.filesafe.space/[LOCATION_ID]/media/[filename]` — confirmed from Skill 28 (cinematic-forge) which documents the same endpoint and CDN format.
  4. Log row in content sheet: CDN link + title + type + platform + date + status.
  5. Reply to owner with CDN link only.
- 10 MB size threshold: files over 10 MB MUST go through GHL CDN; smaller files may only go direct if operator explicitly sets `direct_attach_under_10mb=true` in MEMORY.md.
- GHL upload failure handling: retry once after 30 s; if still failing, notify owner and do NOT fall back to raw attachment.
- Variable reference updated: `GOHIGHLEVEL_API_KEY` (canonical name) + `content_sheet_id`/`content_sheet_url` added.

**Risk:** Low. All changes are additive documentation + config contract. No existing publish schedule, GHL posting, or social API logic altered.

---

## v2.4.0 - June 9, 2026

### Fix — Autonomous podcast audio generation via Fish Audio S2-Pro; removes "record yourself" punt

Mirrors the same problem fixed for video in v2.3.0 — the podcast step had no autonomous audio generation pipeline, only a vague "Synthesize MP3 via Fish Audio" instruction that caused agents to punt with "audio generation didn't produce a file — you can record it yourself." Agent now executes the full pipeline end-to-end. Client self-recording is a hard last resort only.

**What:**
- **references/playbook.md Section 15** — Added "Autonomous Audio Generation Pipeline" subsection with:
  - Verified Fish Audio API facts (model `s2-pro`, endpoint `POST https://api.fish.audio/v1/tts`, auth `Authorization: Bearer`, model via header `model: s2-pro`, synchronous binary stream response — no polling).
  - Step-by-step pipeline: write script → tag heavily with S2-Pro emotion tags → select model (default s2-pro, check for newer) → generate via helper script → ffprobe verify (duration 600-900s, non-zero size, no errors) → retry/diagnose on failure → last-resort fallback message only after 3 attempts and operator notified.
  - Verified S2-Pro emotion tag syntax: [square brackets], 64+ categories, free-form natural language supported. S1 used parentheses — never mix syntax.
  - 4 concrete tagged-script examples demonstrating expressive delivery.
  - Client self-record fallback message to send only as last resort.
- **CORE_UPDATES.md — Podcast Publishing Process** — Rewrote the 14-step list to match the full autonomous pipeline (tag → model → generate → verify → retry → diagnose) with inline API call reference.
- **scripts/generate_podcast_audio.sh** (new, chmod +x) — Parameterized script: `bash generate_podcast_audio.sh <script_file> <voice_id> [model] [output_mp3]`. Sources `secrets/.env` if `FISH_AUDIO_API_KEY` not in env. Makes up to 3 attempts with per-failure diagnosis (401/403/404/422/429/503/network). ffprobe verifies duration (≥30s check; caller should confirm 600-900s). Exits 0 on success, 1 after 3 failures with diagnostic checklist, 2 on bad args/missing key.

**Risk:** Low. Additive documentation and new helper script. No scheduling, posting, or publish-webhook logic altered.

---

## v2.3.0 - June 9, 2026

### Fix — Multi-clip storyboard + FFmpeg merge for full-length Reels; removes false "record yourself" punt

**Why:** The previous video pipeline was ambiguous about how to handle the fact that AI video tools generate clips of at most 8-10 seconds. An agent could (and did) tell clients "the AI video tools have a hard limit of 8-12 seconds per clip, so a 55-60 second Reel can't be generated in one pass — you should record the video yourself." This is wrong behavior. The agent is capable of handling the full pipeline end-to-end.

**What:**

- **references/playbook.md Section 16** — Replaced the vague "generate 7-8 segments, merge with FFmpeg" instructions with a fully explicit, agent-followable pipeline:
  - **Step A: Storyboard** — compute `scene_count = ceil(target_seconds / clip_limit_seconds)` (e.g. ceil(60/8) = 8), write a visual prompt per scene with continuity cues (consistent subject, wardrobe, setting, color grade, camera style), and mark each scene's incoming transition as `cut` or `crossfade`.
  - **Step B: Generate clips** — one clip per scene via kie.ai Veo 3.1 Lite, retry any failed clip up to 3 times.
  - **Step C: Voiceover** — ONE continuous VO track from the full script via Fish Audio S2 (preferred for natural delivery).
  - **Step D: Normalize (mandatory)** — run every raw clip through a normalize pass (`scale=1080:1920, fps=30, libx264, yuv420p, aac 48kHz`) before any concat to prevent codec/resolution mismatch failures.
  - **Step E: Merge** — Recipe 2a (jump cuts via concat demuxer) or Recipe 2b (crossfades via xfade filter with `offset = clip_duration - xfade_duration`); storyboard declares the choice.
  - **Step F: VO overlay** — `ffmpeg -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest`.
  - **Step G: QC** — ffprobe checks duration (55-60s), resolution (1080x1920), codec (h264); retry failed clips before declaring failure.
  - Moved client self-recording to an explicit last-resort fallback (only after all clip retries exhausted), with a specific message the agent must send instead of a silent punt.

- **CORE_UPDATES.md — Video Production Process** — Rewrote the step list to match the new pipeline (storyboard → generate → normalize → merge → VO → QC), with inline FFmpeg commands and a reference to `merge_reel.sh`.

- **scripts/merge_reel.sh** (new, chmod +x) — Parameterized shell script implementing Steps D-G: normalizes all raw clips, merges (cut or crossfade), overlays voiceover, runs ffprobe QC checks. Usage: `bash merge_reel.sh clips_list.txt voiceover.mp3 final_reel.mp4 [cut|crossfade]`.

**Risk:** Low. Additive changes to documentation and a new helper script. No scheduling, posting, or API logic altered.

---

## v2.2.0 - June 8, 2026

follow-up: fixed QC accounts-grep false positive + added --announce delivery to weekly cron

### Fix #1 — Connection status: LIVE GHL check only (no guessing)
**Why:** An agent told a client "nothing is connected" when their GHL Social Planner had channels live. The root cause was reporting connection status from memory/vault absence rather than a live API call.
**What:** Added a `## Reporting connection status — LIVE GHL CHECK ONLY (no guessing)` section to INSTRUCTIONS.md with (a) an explicit ban on guessing/memory-based status, (b) a `check-social-connections` query block for both MCP-first and direct-API routing modes, and (c) clear notes that GHL Social Planner is the primary path, direct-platform tokens are optional add-ons, and Fish Audio / podcast is also optional and never blocks the skill. Added QC assertion in Section I of both `qc-skill35.sh` and `qc-social-media-planner.sh` to verify the rule is present in INSTRUCTIONS.md.
**Risk:** None — additive documentation change only. No existing publish logic altered.

### Fix #2 — Weekly trigger: CRON, not heartbeat (enforcement)
**Why:** A client's Saturday theme question never fired because the weekly trigger was implemented only as a HEARTBEAT.md prose entry. Heartbeat timing drifts and silently skips the prompt when the heartbeat cycle slips.
**What:** Added a `## Weekly trigger — CRON, not heartbeat (enforcement)` section to INSTRUCTIONS.md with (a) an explicit rule banning heartbeat-only weekly triggers, (b) a concrete `openclaw cron add` block for cron name `skill35-weekly-theme` on `0 8 * * 6` (Saturdays 8 AM) with idempotency via `~/.openclaw/data/skill35/weekly-theme-last-run.json`, and (c) a note that the HEARTBEAT.md entry from INSTALL.md Step 9 is informational context only — the cron is the enforcement mechanism. Added QC assertions in Section I of both QC scripts to verify the cron registration block is present and confirm the heartbeat-drift warning exists.
**Risk:** Low — the HEARTBEAT.md Step 9 entry is preserved (not deleted) and noted as informational. The cron is registered idempotently; existing installs that already have the cron name skip silently. No publishing logic altered.

---

## v2.1.0 - May 24, 2026 (Track M — mirror of VPS v10.14.33)

### Added — the three trigger paths INSTRUCTIONS.md has always referenced
- `scripts/run-publishing-cycle.sh` — single-topic orchestrator with full
  `--topic / --platforms / --schedule / --dry-run / --help` interface.
- `scripts/weekly-batch.sh` — cron-driven (`0 9 * * 1`) batch runner.
- `scripts/content-calendar.example.json` — schema starter.

Mirrors the VPS-side v10.14.33 PR. See the VPS CHANGELOG entry for the
full rationale + behavior contract.

---

## v1.4.0 - April 14, 2026

### Added/Updated
- Complete video production pipeline: kie.ai Veo 3.1 Lite generation + FFmpeg crossfade transitions and spec conformance (1080x1920, 9:16, H.264/AAC/30fps)
- Expanded to 8 platforms for video posts: Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest, Threads, X (Twitter)
- HTML email newsletters with embedded images/links
- Scaled production to 15 sub-agents + 6 dedicated QC agents
- Podbean podcast publishing webhook integration
- FFmpeg for all video post-processing (crossfades, specs, optimization)

## v1.3.0 - April 13, 2026

### Changed
- Updated all webhook payload examples to use explicit variable references from identity.md
- Google Sheet webhook: `brandName` now references "[from identity.md: brand name]"
- Google Sheet webhook: `clientEmail` now references "[from identity.md: owner email]"
- Skill 32 tunnel webhook: `clientName` now references "[company slug from identity.md, lowercase, no spaces]"
- Skill 32 tunnel webhook: `companyName` now references "[from identity.md: company display name]"
- Skill 32 tunnel webhook: `contactEmail` now references "[from identity.md: owner email]"

### Added
- Full Podbean Podcast Publishing webhook documentation in CORE_UPDATES.md TOOLS.md section
- Detailed payload example for podcast publishing with all required fields
- Google Sheet Creation Webhook section with payload documentation

## v1.1.0 - April 13, 2026

### Changed
- Google Sheet creation now uses n8n webhook instead of Google Workspace API
- Webhook endpoint: `POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`
- Fields: `brandName`, `clientEmail`
- Response: `sheetUrl`, `sheetId`, `sheetName`
- No client credentials required for sheet creation
- Added Google Sheet Verification checklist to QC.md

## v1.0.0 - April 13, 2026

Initial release.

- 7-part weekly content series across Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest
- Television Show Framework with pitch intensity scaling (4/10 to 10/10 over 7 days)
- 8 parallel sub-agents for content production
- 40+ item QC checklist across 8 categories (text, comments, images, scheduling, blog, podcast, audio, video)
- GoHighLevel (Convert and Flow) Social Planner API integration using Private Integration Token
- Image generation via kie.ai Nano Banana 2 at platform-correct ratios
- Video production via kie.ai Veo 3.1 Lite + FFmpeg merge
- Podcast production via Fish Audio S2 with inline emotion tags (depends on Skill 30)
- Blog post and email newsletter production
- Thursday carousel strategy with cross-platform image reuse (4:5 shared across FB, IG, LinkedIn)
- LinkedIn PDF carousel generation via ImageMagick/Pillow
- Google Sheet logging with 19 worksheets and horizontal 7-day storyboard layout
- Heartbeat-driven weekly theme request (Saturday 8AM, Noon, 6PM, Sunday 7AM)
- First Run Client Setup Protocol (reads core .md files, asks only for missing info)
- Persona integration with 5-layer alignment and client override option
- Memory-core integration for theme tracking, performance logging, and Dreaming insights (depends on Skill 31)
- Complete GHL API request body examples for regular posts, carousels, videos, and comments
- Image + content always bundled in one API call via mediaUrls field
- Comments always posted as separate call 1-2 minutes after parent post with action link
- Teach Yourself Protocol requirement
- Error handling with 3 retries and Telegram > Email > Text notification chain
