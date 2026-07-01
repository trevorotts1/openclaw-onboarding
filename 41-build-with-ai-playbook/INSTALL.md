# Skill 41 -- Build With AI Playbook Generator: Install Guide

## What this installs

The GoHighLevel / Convert and Flow Workflow AI Builder playbook generator:

- **Standardized Build With AI prompt template** (8 sections) -- every generated prompt follows the same canonical format so the operator can paste it directly into GHL's Workflow AI Builder.
- **Dependency-first protocol** -- tags, custom fields, and custom values are created BEFORE the workflow references them. The Workflow AI Builder inserts placeholder syntax but does NOT create the underlying objects.
- **GHL triggers catalog** -- 14 categories, 80+ triggers (references/ghl-triggers-catalog.md).
- **GHL actions catalog** -- 14 categories, 100+ actions (references/ghl-actions-catalog.md).
- **GHL conditions reference** -- If/Else logic + trigger filters (references/ghl-conditions-reference.md).
- **Webhook configuration protocol** -- Custom Webhook action deep-dive: method, URL, headers, raw JSON body, merge fields (protocols/webhook-configuration-protocol.md).
- **Verification checklist** -- 12-point post-build checklist (protocols/verification-checklist.md).
- **F52 data contract** -- build-with-ai-events.jsonl append-only event log (references/f52-data-contract.md).
- **Conversation playbook template** -- pairs with Skill 38 for workflow-triggered conversation playbooks (templates/conversation-playbook-template.md).
- **QC rubric** -- 10-category QC for every generated prompt (references/qc-rubric.md).

## Prerequisites (ALL required unless marked optional)

This skill REFUSES to proceed only if a MANDATORY prerequisite (jq, curl, supported OS) fails. GHL credentials and Skill 38 are runtime/recommended and surface as warnings, not blockers (00-verify-prerequisites.sh).

1. **jq on PATH** -- scripts parse JSON + append events.
2. **curl on PATH** -- GHL API calls.
3. **GOHIGHLEVEL_API_KEY (Location PIT)** -- needed at RUNTIME for creating tags, fields, values via GHL API v2 (a warning at install, not a blocker).
4. **GOHIGHLEVEL_LOCATION_ID** -- needed at RUNTIME for GHL API calls (a warning at install, not a blocker).
   00-verify-prerequisites.sh also detects and records the installed OpenClaw version and warns if it is older than the authored-against version; it exits 2 on an unsupported OS.
5. **Skill 38 (Conversational AI System)** -- RECOMMENDED but not strictly required. Skill 41 pairs with Skill 38 for conversation-playbook registration when a workflow triggers a conversation.
6. **MASTER_FILES_DIR** -- resolvable (Skill 38 Step O.2 or 01-locate-master-files-folder.sh). The event log lives there.

## What this does NOT do

- Does NOT build the workflow itself. The skill generates the prompt; the operator pastes it into GHL's Workflow AI Builder (Automations > Build using AI).
- Does NOT fabricate GHL capabilities. If a trigger or action is not available in the operator's plan tier, the agent reports the honest gap.
- Does NOT ship any GHL API key or PIT. All keys are operator-supplied via env.
- Does NOT modify Skill 38's own protocol files. The conversation-playbook template is an additive drop-in.

## Install order (run in this order; each is idempotent)

```bash
cd ~/.openclaw/skills/41-build-with-ai-playbook/scripts

./00-verify-prerequisites.sh           # jq, curl, GHL PIT, locationId; report env state
./01-locate-master-files-folder.sh     # resolve + persist MASTER_FILES_DIR
./02-seed-playbook-doc.sh              # create canonical build-with-ai-playbook.md in master files
./03-init-jsonl-sinks.sh               # create build-with-ai-events.jsonl + .schema.json sidecar
./04-update-core-files.sh              # append AGENTS.md / MEMORY.md / TOOLS.md pointers (idempotent markers)
./05-configure-executor-model.sh       # configure MiniMax M3 executor model (Ollama Cloud primary / OpenRouter fallback)
./06-verify-agent-browser.sh           # Agent Browser preflight: Node/npm, conditional install, headless Chrome CDP probe, vault check
```

After scripts run, follow INSTRUCTIONS.md for the runtime flows (brainstorm, dependency audit, prompt generation, verification) and the build-with-ai-events.jsonl schema.

The dependency-creation script (dependency-creation.sh) is called at runtime when the operator approves creating dependencies -- it is NOT part of the one-time install.

## Update self-heal (wire.sh)

The skill root ships `wire.sh`: an idempotent, fail-soft hook the canonical fleet updater runs
after a version-bump wipe-and-recopy. It re-applies the idempotent install steps 03--06 (jsonl
sinks, core-file blocks, executor-model config, agent-browser preflight). Every step is guarded
and the script always exits 0, so a single environment gap never blocks a fleet update. Steps
00--02 are first-install/locate concerns and are not re-run by `wire.sh`.

```bash
bash ~/.openclaw/skills/41-build-with-ai-playbook/wire.sh   # safe to run any time; idempotent
```

## OS support

darwin (Mac mini operators) and linux (VPS operators). All scripts detect OS at runtime via uname -s:

- **Darwin:** $HOME/.openclaw/skills
- **Linux:** /data/.openclaw/skills

## QC gates shipped with this skill

```bash
bash scripts/qc-no-personal-data.sh    # UNIVERSAL: zero client/personal identifiers
bash scripts/qc-no-fabrication.sh      # UNIVERSAL: no-fabrication floor + honest-gap path documented
bash scripts/qc-prompt-completeness.sh # Every generated prompt has all 8 required sections
bash scripts/qc-dependency-order.sh    # Dependencies created before the workflow build step
bash scripts/qc-zhc-tag-prefix.sh      # Agent-created tags use ZHC-, custom fields use ZHC_
bash scripts/qc-catalog-usecases.sh    # Triggers/actions carry use cases; If/Else + trigger-filter depth present
```

Each gate ships a paired negative test (scripts/qc-*.test.sh) that PASSES on the intact tree and FAILS
when its invariant is removed, so no gate can silently rot. Run the whole suite with the runner:

```bash
bash scripts/11-run-qc-checklist.sh    # composes every gate; refuses to seal on any failure
```

All gates must PASS before the skill is considered installed cleanly (per ../QC-PROTOCOL.md Rule 5).

## Where to read next

- INSTRUCTIONS.md -- runtime flows + the build-with-ai-events.jsonl schema
- protocols/build-with-ai-protocol.md -- the master protocol
- protocols/dependency-creation-protocol.md -- how to create tags/fields/values
- templates/build-with-ai-prompt-template.md -- the canonical 8-section prompt template
- protocols/trigger-filters-protocol.md -- how to set trigger filters correctly
- references/ghl-conditions-reference.md -- deep If/Else and filtering
- references/platform-differences.md -- Mac mini vs VPS (read this before a headless VPS install)
- ADD-TO-REPO.md -- how to add this skill to your repos
