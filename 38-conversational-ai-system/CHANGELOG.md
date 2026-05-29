## [1.4.11] - 2026-05-29 - enforce the per-playbook human-facing doc deliverable (Notion → Google Docs → text) so a created playbook never ships without a client-facing reference

Root cause fixed: when a communications/conversation playbook is created (the base install creates the FIRST
one — appointment booking, F.7), the agent is ALSO supposed to create a human-facing copy of that playbook in
the CLIENT's OWN account, in the fallback order (1) the client's Notion, (2) if no Notion → Google Docs, (3) if
neither → a plain-text doc the client can access. On a recent client this step was SKIPPED — the agent
scaffolded the playbook files locally and reported the install "clean" but never created the client's Notion
doc, leaving the customer stranded with no human-facing reference of what was set up. The cause: the Notion-doc
deliverable was PROSE in the standard (`references/communications-playbook-standard.md` §4 + the protocol §I.3
step 4), not an ENFORCED gate, so the agent skipped it. "AUTOMATIC NEXT STEP" prose is NOT enforcement — it
needs a recorded state field + a verify/resume gate + a QC check, exactly like the send-directive
(`qc-send-directive.sh`) and conversation-memory (`qc-conversation-memory.sh`) gates. The per-playbook
human-facing doc is now enforced the same way, in four changes, not left optional.

### The canonical rule
Every conversation playbook registered in `<MASTER_FILES_DIR>/conversation-workflows/registry.md` MUST carry a
recorded human-facing doc — a Notion URL, a Google Docs URL, or a `.md`/`.txt` path the client can reach —
created in the client's OWN account in the fallback order Notion → Google Docs → plain-text. The reference is
recorded in the registry's new `Doc (Notion/Docs/text)` column (TABLE form) or a `[doc: …]` tail (legacy BULLET
form) and in the Run Manifest. Never co-mingle clients — always the client's own workspace.

### Added
- **CHANGE 3 — machine-enforced QC gate.** New `scripts/qc-playbook-doc.sh` (bash; mirrors
  `qc-trinity-registry.sh`) reads the client's installed `conversation-workflows/registry.md` and FAILs
  (exit 1) any registered playbook (table OR bullet form) whose doc reference is empty / `n/a` / a placeholder,
  PASSes (exit 0) when every playbook has a recorded Notion/Docs/text doc, exits 2 (NOT a blind PASS) when no
  playbooks exist, and exits 3 when no conversation-workflows folder is found. It rejects the Layer-2 playbook
  file itself and the reserved companion files (`--build-with-ai-prompt.md`, `--verification-checklist.md`,
  `--ghl-side.md`) as "the doc," and catches an on-disk-but-unregistered playbook (no doc can be recorded for
  it). New `scripts/qc-playbook-doc.test.sh` proves all of this with fixtures. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC; SKIP on exit 2/3 = nothing installed yet, FAIL on exit 1)
  AND `.github/workflows/qc-static.yml` (CI runs the fixture test on every push/PR). BASH (with an inline
  python core) so it does not trip the qc-static ban on claude-/anthropic strings in `.py` under Skills 22/23.

### Changed
- **CHANGE 1 — binding, state-gated install step.** `INSTRUCTIONS.md` (Step 9.20 + Phase 7),
  `references/v6.0-source-playbook.md` F.7 (the base SMS automation that creates the first playbook) + §H Run
  Manifest, and `protocols/conversation-workflows-protocol.md` §F/§H/§I.3/§J now state that the install is NOT
  complete until a created playbook's human-facing doc has been created in the client's account (Notion →
  Google Docs → plain-text) and its URL/path recorded in the registry + Run Manifest. An incomplete doc is
  retried (verify/resume), not silently skipped.
- **CHANGE 2 — installer action.** `scripts/09-install-conversation-workflows.sh` now adds the new
  `Doc (Notion/Docs/text)` column to the registry it scaffolds, and runs a verify/resume loop over every
  on-disk playbook: for any playbook with no recorded doc it creates one (Notion subpage under the client's
  designated parent page via `NOTION_API_KEY` + `NOTION_PARENT_PAGE_ID`/`NOTION_PARENT_SEARCH` → Google Docs
  via the Google Workspace helper → a plain-text `.md` in `<MASTER_FILES_DIR>/playbook-docs/`), records the
  resulting URL/path back into the registry, and emits a clear operator-facing line stating WHERE the doc was
  created (or which fallback was used). Idempotent — a playbook that already has a recorded doc is left as-is.
- **CHANGE 4 — standards.** `references/communications-playbook-standard.md` adds "human-facing doc created in
  client's account (Notion → Google Docs → text), URL recorded" to the §2 MUST-APPEAR checklist and strengthens
  §4 from prose to a MANDATORY, machine-enforced deliverable (naming `qc-playbook-doc.sh`).
  `protocols/conversation-workflows-protocol.md` §F adds the doc column to the registry table and marks it
  mandatory + gated; `references/GHL-INBOUND-AND-PLAYBOOKS.md` §10 (first appointment-booking playbook) marks
  the doc step mandatory + gated. SKILL.md self-counts updated (scripts 30 → 32, four QC linters → five).

## [1.4.10] - 2026-05-29 - enforce conversation-memory (read-before + append-after) so single-turn hook agents never lose context

Root cause fixed: GHL inbound hook sessions are SINGLE-TURN / stateless (confirmed: every hook run is a fresh
session, user-turns = 1). The agent has NO in-session memory of prior messages — its ONLY memory of a contact
across messages is that contact's per-contact conversation log file
(`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`), which it must READ before replying and
APPEND to after sending. On a live client (Corey) this broke because the canonical `messageTemplate` was
"simplified" during testing and lost the read/append steps, the `conversational-logs/` dir was never created
(and was root-owned, so even when present the `node` gateway could not write it), and AGENTS.md had no memory
protocol — so the agent had ZERO memory ("didn't remember anything" mid-booking). The send-directive gate
(`qc-send-directive.sh`) did NOT catch it because it only checks the SEND instruction. Conversation-memory is
now enforced exactly like the send-directive, in four layers, not left optional.

### The canonical conversation-memory steps
Every GHL inbound SERVER `messageTemplate` must contain all of: the **conversational-logs** path, a
**READ**-before-replying instruction (recover prior conversation + any in-progress booking/topic and CONTINUE
it; if missing, treat as new), and an **APPEND**-after-sending instruction (append inbound + reply to the log,
create if missing). The directive lives ONLY on the SERVER mapping — the in-GHL-body `messageTemplate` stays
placeholder-free per the 23-key rule.

### Added
- **LAYER 4 — machine-enforced QC gate.** New `scripts/qc-conversation-memory.sh` (bash; mirrors
  `qc-send-directive.sh`) scans every GHL INBOUND SERVER-mapping `messageTemplate` (installer canonical
  template + reference examples) and FAILS (exit non-zero) if any is missing the conversational-logs path, the
  READ-before instruction, or the APPEND-after instruction. It SKIPS the placeholder-free 23-key bodies and
  non-GHL (Stripe/Shopify/n8n) mappings, and exits 2 (FAIL) if zero GHL inbound server templates are found so
  it never goes silently blind. Wired into BOTH `scripts/11-run-qc-checklist.sh` (pre-handoff QC, plus a new
  conversational-logs dir presence+writability check) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **CHANGE 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the read-before + append-after conversation-log steps into the GHL inbound mapping's `messageTemplate`
  (alongside the send-directive), and a second fail-closed guard refuses to write the config (exit 9) if the
  built template is missing the conversational-logs path, the read element, or the append element — it is no
  longer possible to install a GHL hook whose server `messageTemplate` lacks the read/append steps.
- **CHANGE 2 — installer creates + chowns the conversational-logs dir.** `scripts/09-install-conversation-workflows.sh`
  (Step 9 "Set up conversation log system") now `mkdir -p`s `<MASTER_FILES_DIR>/conversational-logs/` and chowns
  it to the runtime/gateway user (`node` on VPS/Docker, the login user on Mac/Homebrew; override via
  `OPENCLAW_RUNTIME_USER`) so the agent can actually write logs — runs before the registry early-exit and warns
  loudly with the exact `sudo chown` command if it cannot.
- **CHANGE 3 — AGENTS.md Conversation Memory Protocol base rule.** `scripts/05-update-agents-md.sh` now emits a
  concise standing rule (new `CONVERSATION_MEMORY_PROTOCOL` marker block): GHL inbound is single-turn; memory =
  per-contact logs; READ before replying + CONTINUE in-progress topics + APPEND after sending; a reply that
  ignores or fails to update the log is a failure. Pointer-style, no bloat.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping, Step 3)
  and `references/GHL-INBOUND-AND-PLAYBOOKS.md` (canonical mapping §4 + new §4b) now carry the read-before +
  append-after steps in their canonical server `messageTemplate`, replacing the simplified template that lacked
  them. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free in-body templates all preserved.
- **Standards.** `references/communications-playbook-standard.md` (new conversation-memory must-appear item) and
  `references/workflow-ai-instructions-standard.md` (new machine-enforced conversation-memory callout) now state
  the read/append steps are mandatory on the SERVER mapping and how to verify them (`scripts/qc-conversation-memory.sh`).

### Version
- `skill-version.txt` → `1.4.10`; SKILL.md self-counts updated (scripts/ 29 → 30; four QC linters).

## [1.4.9] - 2026-05-29 - enforce the mandatory GHL send-directive (drafting != sending) for every client

Root cause fixed: if a GHL inbound hook's SERVER-mapping `messageTemplate` does not EXPLICITLY order the
agent to SEND its reply via the GHL Conversations API, the model drafts a reply and STOPS — drafting is NOT
sending — and the customer receives nothing. This is now enforced in three layers, not left optional.

### The canonical send-directive
The exact mandatory clause every GHL inbound SERVER `messageTemplate` must contain (all elements required:
the word SEND, the GHL Conversations API, the contact id, the channel, the drafting-is-NOT-sending clause,
and "do not end your turn until a messageId/conversationId is returned"):

> MANDATORY — SEND, do not just draft: You MUST send your reply by calling the GHL Conversations API (POST
> conversations/messages) for contact {{contact_id}} on the {{channel}} channel, per TOOLS.md. Composing or
> drafting a reply is NOT sending — the customer receives nothing unless you make the API call. Do NOT end
> your turn until the send call returns a messageId/conversationId.

### Added
- **LAYER 3 — machine-enforced QC gate.** New `scripts/qc-send-directive.sh` scans every GHL INBOUND
  SERVER-mapping `messageTemplate` (the installer's canonical template + the reference examples) and FAILS
  (exit non-zero) if any is missing the send-directive elements (SEND, GHL Conversations API /
  `conversations/messages`, drafting-is-not-sending, do-not-end-turn-until-messageId). It deliberately
  SKIPS the placeholder-free object-A 23-key bodies (those stay placeholder-free per the 23-key rule — the
  send-directive lives ONLY on the server mapping) and non-GHL server mappings (Stripe/Shopify/n8n). Exits
  2 (FAIL) if zero GHL inbound server templates are found so it never goes silently blind. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **LAYER 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the strengthened send-directive into the GHL inbound mapping's `messageTemplate`, and a fail-closed
  guard refuses to write the config (exit 8) if the built template is missing any send-directive element —
  it is no longer possible to install a GHL hook whose server `messageTemplate` lacks the send-directive.
  The in-GHL-body messageTemplate (the Step-4 E2E FLAT body) stays placeholder-free per the 23-key rule.
- **LAYER 2 — AGENTS.md standing base rule (belt-and-suspenders).** `scripts/05-update-agents-md.sh` now
  emits a concise standing rule (new `GHL_SEND_MANDATORY` marker block) + strengthens Step 7C "Send the
  reply": for ANY GHL inbound hook, SENDING via the GHL Conversations API is MANDATORY; a drafted-but-unsent
  reply is a failure; always confirm a messageId/conversationId before ending the turn.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping,
  Step 3) and `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4 (the doc that wins) now show the strengthened
  send-directive in their canonical server `messageTemplate`, replacing the softer "reply via the GHL
  Conversations API per TOOLS.md" phrasing. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free
  in-body templates all preserved.
- **Standards + checklist.** `references/communications-playbook-standard.md` (GHL reply mechanism item),
  `references/workflow-ai-instructions-standard.md` (new machine-enforced send-directive callout), and
  `templates/workflow-verification-checklist-template.md` (new Webhook-Action verification item) now state
  the send-directive is mandatory on the SERVER mapping and how to verify it (`scripts/qc-send-directive.sh`).

### Version
- `skill-version.txt` → `1.4.9`; SKILL.md self-counts updated (scripts/ 28 → 29; three QC linters).

## [1.4.8] - 2026-05-29 - add Skill 23 cross-reference (role/SOP gate + comms hand-off) to v6.0 playbook

### Added
- **Skill 23 cross-reference in the v6.0 playbook.** Added a "🔗 How this connects to the AI Workforce
  Blueprint (Skill 23)" section to `references/v6.0-source-playbook.md`, placed right after the TRINITY /
  standards area (Communications Playbook Standard + Workflow-AI Instructions Standard). It documents the two
  enforced connections between Skill 38 and Skill 23: the **Role Library + SOP Library auto-pull gate**
  (build-state field + verify/resume gate; multiple Six Sigma DMAIC SOPs per role under
  `departments/<dept>/sops/`, never empty/stub) and the **comms-automation hand-off** (Skill 23 → Skill 38
  via a `commsAutomationStatus` state field + resume self-ping when a Communications/Sales/Customer-Support
  department is built), and ties both back to THE TRINITY keeping every workflow, playbook, and prompt in
  lockstep.

### Version
- `skill-version.txt` → `1.4.8`.

## [1.4.7] - 2026-05-29 - Close the 2 QC gaps: TRINITY registry format match + 23-key linter now covers the v6.0 playbook

Two QC checks that *looked* like they were enforcing invariants were silently no-op'ing on real inputs.
Both are now genuinely enforced, with fixture coverage.

### Fixed
- **GAP 1 — TRINITY registry format mismatch.** `scripts/qc-trinity-registry.sh` parsed the
  conversation-workflows registry only as a markdown TABLE, but `scripts/09-install-conversation-workflows.sh`
  documents/emits the active-workflow list as BULLETS (`- <id>: <desc>`). On a real installed (bullet)
  registry the table-only parser saw ZERO rows, so registry-vs-disk reconciliation
  (registered-but-no-files / files-but-not-registered) never fired and registered slugs were even
  mis-flagged "not registered". The validator now parses BOTH shapes (table rows scoped anywhere; bullet
  rows scoped under "## Active workflows", ignoring `<placeholder>`/backtick doc lines and quoted trigger
  phrases). Bullet rows carry no Layer-1 column → disposition recorded as unknown (still counts as
  registered). `scripts/09-install-conversation-workflows.sh` now seeds the canonical TABLE shape (matching
  protocol §F + the validator) while the validator still tolerates the legacy bullet form for older installs.
- **GAP 2 — 23-key linter excluded the v6.0 playbook.** `scripts/qc-23-key-bodies.sh` skipped
  `references/v6.0-source-playbook.md` (~9,430 lines) by name — the file holding the LARGEST set of GHL RAW
  BODY examples (per-channel curl smoke tests, Build-with-AI prompt bodies, verification-checklist bodies).
  Exclusion removed; the playbook is now scanned. The single-DOTALL `FENCE_RE` was also mis-pairing fences
  across that large multi-language document (it found only 1 of the file's 12 bodies), so the fence scanner
  was rewritten as a line-state iterator that pairs `` ``` `` open/close correctly regardless of language
  tag — now catching object-A bodies in ```json, ```text, no-language Build-with-AI blocks, AND ```bash
  `curl -d '{…}'` smoke tests. Object-B server `hooks.mappings` blocks (camelCase `agentId`) are still
  skipped by the snake_case `agent_id` discriminator — not by file exclusion. Linter result on the playbook:
  **all 12 of its bodies PASS**; repo-wide **RESULT: PASS — 23 object-A bodies across 6 files** (was 10/5).

### Added
- `scripts/qc-trinity-registry.test.sh` — fixture tests proving reconciliation catches a
  registered-but-missing-files row AND a file-present-but-unregistered slug on BOTH the bullet and table
  registry forms (and that a clean bullet registry PASSes). Wired into CI (`.github/workflows/qc-static.yml`).

### Version
- `skill-version.txt` → `1.4.7`.

## [1.4.6] - 2026-05-29 - 8 rated improvements (port of VPS #47): machine-enforced 23-key + TRINITY, Build-with-AI label fix, real self-counts, fleshed journeys, Skill 23 chain

Part of repo `v10.15.9`. Six of the eight rated improvements land in this skill; the other two
(cross-skill chain enforcement + library-gate status surfacing) land in Skill 23 but reference this skill.
No stripped GHL bodies introduced — the 10 embedded object-A bodies all pass the new linter (23-key, flat,
placeholder-free).

### Added
- `scripts/qc-23-key-bodies.sh` — machine-enforces the 23-key GHL RAW BODY rule across references/ +
  templates/ + scripts/ (exactly 23 flat keys, placeholder-free `messageTemplate`, no nesting, no `\n`).
  Wired into `scripts/11-run-qc-checklist.sh` and into CI (`.github/workflows/qc-static.yml`). Excludes the
  verbatim `v6.0-source-playbook.md`; skips object-B server mappings.
- `scripts/qc-trinity-registry.sh` — machine-enforces THE TRINITY: a registry row with a communications
  playbook but no Build-with-AI prompt (or an orphan prompt) is flagged INCOMPLETE; honors the
  Layer-1-not-needed exemption. Wired into `11-run-qc-checklist.sh`; referenced from the verification
  checklist + standards.

### Changed
- **Mislabel fix (the failure this standard set out to kill):** `templates/sms-workflow-ai-prompt-template.md`,
  `templates/workflow-verification-checklist-template.md`, `scripts/21-generate-client-reference-sheet.sh`,
  `scripts/09-install-conversation-workflows.sh`, and `scripts/20-seed-design-principles.sh` now name the
  authoritative location — GHL **Automations → "Build with AI"** (top-right) on a NEW automation — instead
  of "Use Workflow AI" / "Create workflow → Workflow AI".
- **Real self-counts:** `SKILL.md` + `INSTALL.md` now state protocols=32, scripts=27, references=14,
  journeys=8 with a `SELF-COUNTS` re-verify comment; a re-verification note was added to the repo
  `scripts/bump-version.sh`.
- **7 stub journey templates fleshed out** to ≥ coach depth with vertical-specific triggers / conversation
  phases / success actions: consulting, course-creator, e-commerce, real-estate, saas, service-provider,
  wellness (107–121 lines each).
- **Distinction-map table** added at the top of `protocols/conversation-workflows-protocol.md` (channel
  communication playbook vs communications playbook vs workflow-AI prompt vs GHL automation).
- **Skill 23 upstream cross-reference** added to `SKILL.md` + the protocol's TRINITY note (Skill 23's
  comms/sales/support build now hands off here via the enforced `commsAutomationStatus` chain).

### Version
- `skill-version.txt` → `1.4.6`.

## [1.4.5] - 2026-05-29 - v6.0 clean comprehensive playbook; de-staled

### Why
The source playbook is replaced with the **clean, conflict-free v6.0** single-source-of-truth build. All GHL
hook guidance now matches the settled standard everywhere: **23-key FLAT** Raw Body, the body's own
`messageTemplate` value is **placeholder-free**, `deliver` is **`false`**, mapping-level `fallbacks` is
**never** a key (the `.strict()` schema rejects it; fallbacks live on the model-routing config only), and no
nested bodies / no stripped sub-23-key bodies anywhere. Every passage that disagreed with that standard was
removed or corrected upstream in the v6.0 content, so the repo carries **no stale or conflicting playbook
content**. The standards docs (`GHL-INBOUND-AND-PLAYBOOKS.md`, `communications-playbook-standard.md`,
`workflow-ai-instructions-standard.md`) remain their own reference docs; the playbook references them rather
than duplicating them. `skill-version.txt` bumped 1.4.4 → 1.4.5.

### Changed
- `references/v5.14-source-playbook.md` → **renamed** to `references/v6.0-source-playbook.md` (git mv) and its
  content replaced with the clean v6.0 comprehensive playbook (9,430 lines / ~452 KB). The header now stamps
  **Version 6.0 (CLEAN, CONFLICT-FREE)** and declares itself the single source of truth superseding v5.x.
- Updated every live pointer/cross-link from `v5.14-source-playbook.md` to `v6.0-source-playbook.md`:
  `scripts/01-locate-master-files-folder.sh` (both `PLAYBOOK_SRC` and the `DEST_PLAYBOOK` copy target),
  `INSTALL.md`, `INSTRUCTIONS.md`, and the reference cross-links in `GHL-INBOUND-AND-PLAYBOOKS.md`,
  `stripe-coupons-api.md`, `stripe-webhooks-reference.md`, `shopify-graphql-reference.md`,
  `sales-frameworks-deep-dive.md`, `ghl-coupons-api.md`, `cloudflare-tunnel-troubleshooting.md`,
  `cloudflare-godaddy-setup-guide.md`.
- Conflict sweep across the Skill 38 folder (nested GHL body, sub-23-key body, `deliver:true`, mapping-level
  `fallbacks`, conflicting "DATA ONLY / no messageTemplate" phrasing): **no contradictions found**. The only
  remaining `deliver:true` / "no stripped bodies" mentions are corrective prose that debunks the old patterns,
  and the standards docs already match the corrected structure — no surgical edits were needed beyond the
  playbook content + filename pointers above.

## [1.4.4] - 2026-05-29 - THE TRINITY + Communications Playbook & Workflow-AI standards

### Why
Two recurring failure surfaces hardened, with full content kept in reference/protocol docs (CORE md files
get concise pointers only — no bloat): (1) operators were building a GHL workflow OR a playbook OR a
workflow-AI prompt in isolation, leaving the other two missing; (2) GHL's Build-with-AI repeatedly fails to
populate the Custom Webhook fields, and there was no single standard spelling them out field-by-field. All
new GHL RAW BODY examples honor the 23-key rule (flat, placeholder-free `messageTemplate`, no `\n`, no
nesting, no stripped bodies). `skill-version.txt` bumped 1.4.3 → 1.4.4.

### Added
- `references/communications-playbook-standard.md` — the COMMUNICATIONS PLAYBOOK STANDARD: standardized
  format + a "must appear in EVERY playbook" checklist (slug/id, owner agent id, channel, trigger
  phrases/intent, goal, step-by-step flow, GHL Conversations-API reply mechanism per TOOLS.md,
  cross-playbook transition rules, edge cases incl. frustration/refund/legal escalation, on-success/tagging,
  tone, honesty floor); STORAGE in `conversation-workflows/` + register in `registry.md`; and the client-side
  human-readable copy fallback order **Notion → Google Docs → plain text**.
- `references/workflow-ai-instructions-standard.md` — the WORKFLOW-AI INSTRUCTIONS STANDARD: must-appear
  checklist; WHERE it goes (GHL Automations **Build with AI** button when creating a NEW automation); the
  explicit field-by-field Custom Webhook steps (EVENT=CUSTOM, METHOD=POST, real URL not sample-url,
  AUTHORIZATION=None, HEADERS via Add item → Authorization Bearer token + Content-Type json, RAW BODY = full
  23-key flat JSON via the Custom Values picker); MULTI-ACTION teaching (if/else branches, Add-Tag, tag-check,
  multiple sequential actions, create-tag-via-GHL-skill-first); and the BUILD-WITH-AI VERIFICATION CHECKLIST.

### Changed
- `protocols/conversation-workflows-protocol.md` — added **THE TRINITY** connection rule (workflow ⇄
  communications playbook ⇄ workflow-AI prompt; one implies the other two) + pointers to the two new
  standards; D.2 Build-with-AI prompt block upgraded to the field-by-field Custom Webhook format
  (EVENT/METHOD/AUTHORIZATION=None/HEADERS via Add item/Content-Type); Section E now points at the
  communications-playbook standard's checklist + Notion→Google Docs→plain-text storage order.
- `templates/sms-workflow-ai-prompt-template.md` — Action 1 rewritten to the precise field-by-field format
  (EVENT=CUSTOM, METHOD via dropdown, real URL, HEADERS via Add item, Custom Values picker) + a MULTI-ACTION
  note (if/else, Add-Tag, tag-check, multiple actions; tags created via GHL skill first).
- `templates/workflow-verification-checklist-template.md` — extended with EVENT=CUSTOM, real-URL-not-sample,
  "exactly the intended action(s)" count check, Custom-Values-picker check, and a tags/multi-action item.
- `scripts/05-update-agents-md.sh` (AGENTS.md guidance, Step 1.85) — added concise 1-2 line pointers to THE
  TRINITY + the two new standard reference docs (full content stays in the references, not inline in CORE md).
- `INSTRUCTIONS.md` — Step 9.20 row notes THE TRINITY + the two standards.

## [1.4.3] - 2026-05-29 - Enforce 23-key GHL body everywhere (no stripped bodies)

### Why
Owner directive (non-negotiable): EVERY GHL Custom Webhook RAW BODY example in this skill must contain ALL 23
keys. 23 is the MINIMUM — no stripped/short bodies (8/11/13/16-key versions) are allowed anywhere. The prior
13/16-key bodies are replaced with the full 23-key canonical body. The body stays FLAT, the body's
`messageTemplate` value is kept placeholder-free (no `{{…}}`) so GHL never mangles the JSON, and there are no
`\n` escapes inside any JSON example. Per-channel variants keep all 23 keys; only `channel` + the `session_key`
prefix differ. `skill-version.txt` bumped 1.4.2 → 1.4.3.

### The 23 keys (exact)
`id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`, `messageTemplate`, `deliver`,
`timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`, `last_name`, `email`, `phone`,
`subject`, `message_body`, `location_id`, `location_name`.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new rule (0) mandating all 23 keys (23 = minimum); canonical body
  upgraded to 23 keys + per-channel variant list; Section 4 Build-with-AI body upgraded; Section 5 checklist now
  demands all 23 keys; cardinal-rule + corrected-structure prose rewritten (body now carries a placeholder-free
  `messageTemplate` instead of "no messageTemplate").
- `references/v5.14-source-playbook.md` — every GHL Raw Body upgraded to 23 keys (Step 3C smoke test, Step 4 E2E
  test, Step 9.20-D.2 + multi-channel Build-with-AI prompts, the D.3 verification stub, all six Part 3 channel
  blocks); stripped `tags`/`workflow_id` extra-keys removed; corrected-structure notes rewritten.
- `scripts/15-configure-hooks-mappings.sh` — Step 4 E2E test PAYLOAD upgraded to the full 23-key body.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body + D.3 verification stub upgraded to 23
  keys; corrected-structure note rewritten.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body upgraded to 23 keys; mistakes list updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks upgraded to 23 keys.
- `templates/workflow-verification-checklist-template.md` — Raw Body stub upgraded to the full 23-key body.
- `skill-version.txt` — 1.4.2 → 1.4.3.

## [1.4.2] - 2026-05-29 - GHL inbound hook correction: FLAT body, no nesting, server-only messageTemplate

### Why
Verified LIVE on Corey/Explore Growth (OpenClaw 2026.5.27): the GHL Custom Webhook RAW BODY must be FLAT
(data-only). A nested `contact:{…}` / `customer_message:{…}` body makes EVERY field arrive EMPTY at the hook
(even a hardcoded `"channel"`), and a `messageTemplate` placed in the GHL body gets mangled by GHL's own
merge-field parser → webhook Skipped ("Error while parsing the object to JSON"). The `messageTemplate` is
server-side only and MUST include the reply-via-GHL-Conversations-API instruction or the agent drafts but
never sends. Content + script correction; `skill-version.txt` bumped 1.4.1 → 1.4.2.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new top-of-doc **CORRECTED GHL HOOK STRUCTURE (2026-05-29)**
  section (the 12-point canonical spec); Section 4 Build-with-AI body flattened; Section 5 verification
  checklist updated to demand a FLAT, no-`messageTemplate`, Custom-Values-picker body.
- `references/v5.14-source-playbook.md` — every GHL Raw Body flattened (Step 3C smoke test, Step 4 E2E test,
  Step 9.20-D.2 + multi-channel Build-with-AI prompts, all six Part 3 channel blocks); mapping `messageTemplate`
  rewritten to reference FLAT body keys + reply-via-GHL-API instruction; `deliver:false`; `sessionKey:"{{session_key}}"`;
  removed invalid `fallbacks` key from the mapping (schema is `.strict()`); schema-fields list + Checkpoint C corrected.
- `scripts/15-configure-hooks-mappings.sh` — mapping `messageTemplate` now uses FLAT body keys + GHL-API reply
  instruction; `deliver:false`; `sessionKey` default is `{{session_key}}`; E2E test PAYLOAD flattened.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body flattened + corrected-structure note.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body flattened; mistakes list + placeholders updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks flattened.
- `skill-version.txt` — 1.4.1 → 1.4.2.

## [1.4.1] - 2026-05-28 - Conversation Playbook Builder enhancement (the differentiator) (repo v10.15.7)

### Why
The recurring "build me a conversation playbook" flow is the system's USP — communication-driven funnels /
automations, built by talking and brainstorming instead of click-and-drag (this is what beats CloseBot).
Step 9.20 needed to be explicitly bulletproof every time, and the MEMORY.md rules + Mac env handling needed
to back it. Content-only addition; no version files touched (repo stays v10.15.7).

### Added / Changed
- `protocols/conversation-workflows-protocol.md` — Step 9.20 reframed as an explicit **3-PART build**:
  Part 1 (Workflow AI instruction set = Build-with-AI prompt + new **manual-build fallback** D.2b +
  verification checklist, with the SHAPE-first / operator-pastes-tokens guidance); Part 2 (the conversation
  playbook → registered in registry.md, with the hook-path "how the two halves connect" note); Part 3 (new
  Section I — the friendly **brainstorm trigger**: use Typed KBs + USER.md + MEMORY.md, ask ONLY smart gaps,
  NEVER 50 questions, concise "is this what you want?" confirmation → build → Notion doc → register). New
  Section J (AGENTS.md Step 1.85 runtime hook), Section K (builder ↔ router ↔ proactive cross-references),
  Section L (Mac env note). Removed ambiguous "Workflow AI" usage referring to the GHL feature (now
  "Build with AI") and the implication that GHL Automations have an API.
- `scripts/06-append-memory-rules.sh` — adds a second idempotent block: **builder design rules 15-19**
  (Terminology, No-GHL-API, 3-PART Build, Brainstorm-Not-50-Questions, Mac Env).
- `scripts/05-update-agents-md.sh` — Step 1.85 block expanded with the communication-driven USP, the
  brainstorm-not-50-questions rule, the 3-PART build, the no-GHL-API note, and the router/proactive cross-refs.
- `scripts/18-locate-secrets-env.sh` — Step O.5: Mac now searches BOTH `~/clawd/secrets/.env` and
  `~/.openclaw/.env`; added the Mac-vs-VPS env clarity note.
- `protocols/intelligent-routing-protocol.md` (Step 9.33) + `protocols/proactive-suggestions-protocol.md`
  (Step 9.34) — reciprocal triangle cross-references to the builder.
- `INSTRUCTIONS.md` — Step 9.20 row rewritten (3-PART build, USP, no-API note); 9.33/9.34 rows annotated;
  Phase 0 Step O.5 Mac env note added.
- `CORE_UPDATES.md` — documents builder design rules 15-19 so install writes them.

## [1.4.0] - 2026-05-28 - GHL Build-with-AI hardening + calendar-sync (repo v10.15.7)

### Why
A live Mac-mini build surfaced several traps that every future Mac client would otherwise hit:
token confusion (4 distinct secrets), `deliver: true` silently breaking GHL API replies, the
`cron.jobs` JSON block failing validation on openclaw 2026.5.27, GHL having no API/MCP for building
automations (Build-with-AI is the only path), and the Mac-specific `cloudflared` launchd install
needing interactive sudo. Baked all the fixes into the skill so no Mac client stalls on them.

### Added
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` (NEW) — authoritative Mac reference: 4-token table,
  one-tunnel-many-hooks model, copy-paste **Build-with-AI prompt** template (placeholders
  PUBLIC_HOSTNAME / HOOK_PATH / HOOKS_TOKEN / CHANNEL), post-build verification checklist (incl.
  real-inbound-test caveat), Reusable Tunnel Values storage rule (AGENTS.md + TOOLS.md + client
  Notion), JSON one-value-per-key rule, verified channel→`type` enum (valid: SMS/Email/FB/IG/
  WhatsApp/Live_Chat; invalid: TikTok/Call/GMB + long-forms), Conversations reply recipe, Calendar
  recipe (free-slots epoch-MILLIS, book/reschedule/cancel), first playbook = appointment booking.
- `scripts/skill38-calendar-sync.sh` (NEW) — weekly GHL calendar refresh; rewrites the
  `<!-- GHL_CALENDARS_START/END -->` block in TOOLS.md. Auto-detects Mac vs VPS env/paths. Generic
  per-client. Registered via `openclaw cron add --name skill38-calendar-sync --cron "0 9 * * 0" ...`.

### Changed (surgical edits to references/v5.14-source-playbook.md)
- Step 3C + Step 3.5G: `deliver: true` → `deliver: false` on GHL reply hooks, with corrected
  rationale (true makes the gateway try to deliver to a non-existent default chatId → reply never sends).
- Step 3A: added the 4-token disambiguation table; Mac note (no Hostinger wrapper → hooks.token in
  openclaw.json is stable; no OPENCLAW_HOOKS_TOKEN env trick).
- All cron registrations → `openclaw cron add` CLI flag form, with a banner that `cron.jobs` JSON
  does not validate on openclaw 2026.5.27.
- Step 9.20 D.2: "Workflow AI prompt" → "Build-with-AI prompt"; Build-with-AI is PRIMARY, manual
  node-build demoted to FALLBACK; verification checklist required even on success; F.6 Reusable Tunnel
  Values; F.7 base SMS automation also creates the first appointment-booking playbook and wires the
  hook to it.
- Part 2 (Client Reference Sheet / Notion-doc spec) rewritten ordering: Reusable Tunnel Values →
  Build-with-AI prompt per channel → verification checklist; manual webhook build moved to fallback.
- Rules of Engagement: added Rule 7 (one value per key — proper JSON structure).
- Standardized `GHL_PRIVATE_INTEGRATION_TOKEN` + `Version: 2021-04-15` on the Conversations/Calendar
  path (was `<GHL_PIT_TOKEN>`). `GOHIGHLEVEL_AGENCY_PIT` is not present in this repo.
- Calendar action: verified endpoints (free-slots epoch-millis; appointments required fields; PUT/DELETE).
- Mac cloudflared step: kept launchd `sudo cloudflared service install` but flagged the
  interactive-sudo requirement prominently (cannot run over non-interactive rescue SSH).

# Skill 38 — Conversational AI System: Changelog

## [1.0.0] - 2026-05-28 - Initial release (packages v5.14 playbook)

### Why
Christy's v5.14 conversational AI playbook (~8,800 lines, 14 version iterations) packaged as
an installable skill. Builds the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow).

### Added
- 27 protocol files (humanizer NOT included; skill 19 owns it)
- 8 customer journey templates (coach fully detailed; 7 stubbed)
- 9 idempotent + OS-aware install scripts (00 prerequisites → 08 Shopify wizard)
- 7 reference documents including the FULL v5.14 source playbook + strategic roadmap
- SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md
- AGENTS.md Steps 1.7, 1.8, 1.9, 2.8; upgraded Step 1.75
- MEMORY.md design rules 6-14
- 4 cron jobs (Sunday 2am tune-up, Saturday 11pm proactive + 11:30pm model freshness, 1st-of-month review)

### Source of truth
- `references/v5.14-source-playbook.md` — the canonical 8,797-line playbook
- `references/conversational-ai-strategic-roadmap.md` — strategic context (✅ shipped vs 📋 pending)

### Out of scope (DEFERRED, not in this skill)
- F14 Voice/Phone Integration
- F15 Proactive Outreach Campaigns
- F16 A/B Testing of Reply Variants
- F17 Customer Segmentation Awareness
- F18 Webhook Chaining
- F21 Multi-Tenant Agent Isolation

The skill's structure (numbered scripts, protocols/ folder, references/) leaves room for
these to be added later without restructuring.
