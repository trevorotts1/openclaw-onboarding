# Skill 44 — Convert and Flow Operator: QC Checklist

The authoritative automated validator is `qc-convert-and-flow.sh`. This file is the
human-readable companion checklist. All items below are machine-asserted by the script.

---

## Section A: Installation

- [ ] `caf doctor` exits 0 (all checks green; Firebase WARN is acceptable)
- [ ] `caf` resolves on PATH inside the openclaw gateway
- [ ] `convertandflow` and `ghl` aliases resolve (symlinks present)
- [ ] venv exists at `~/.openclaw/tools/convert-and-flow-cli/.venv` (Mac) or `/data/.openclaw/tools/convert-and-flow-cli/.venv` (VPS)

## Section B: Credentials

- [ ] `GOHIGHLEVEL_API_KEY` is set and starts with `pit-`
- [ ] `GOHIGHLEVEL_LOCATION_ID` is set
- [ ] Canonical env mapping: wrapper passes `GHL_API_KEY` to engine (verify `caf contacts list --limit 1` returns data)
- [ ] Firebase token: present = PASS; absent = WARN (not FAIL)
- [ ] `GOHIGHLEVEL_DRAFT_ONLY=true` is set (write safety default)

## Section C: Standard ops

- [ ] `caf contacts list --limit 3` returns real contacts
- [ ] `caf workflows list` returns the workflow list
- [ ] `caf locations get` returns location info

## Section D: Write safety

- [ ] `--dry-run` flag recognized (does not fire live API call)
- [ ] Location whitelist enforced (cross-location write rejected)
- [ ] Snapshot dir exists at `~/.openclaw/tools/convert-and-flow-cli/data/snapshots/`
- [ ] Internal-write lock file mechanism present

## Section E: TRINITY and self-test

- [ ] `qc-trinity-registry.sh` called for any conversational build (hard gate)
- [ ] `24-self-test-hook.sh` invoked post-build for brain-containing workflows
- [ ] Self-test credential read alias-aware: accepts `GOHIGHLEVEL_API_KEY` OR `GHL_PRIVATE_INTEGRATION_TOKEN`

## Section F: Core files

- [ ] CORE_UPDATES.md sentinel `<!-- skill:44-convert-and-flow-operator:core-update-applied -->` present in AGENTS.md
- [ ] AGENTS.md has Tier 0 mention and disclosure format reference
- [ ] TOOLS.md has caf/convertandflow wrapper entry
- [ ] MEMORY.md has install record

## Section G: Platform overlay

- [ ] Platform overlay frontmatter `name: convert-and-flow-operator` matches SKILL.md
- [ ] Mac overlay: auto-re-grab recipe present in platform/mac/recipes/

## Section H: QC scope flags (document for Opus QC)

- Criterion 8 grep for old Rule 16 wording EXCLUDES historical CHANGELOG.md entries.
- Criterion 13/17 skill-35 grep EXCLUDES intentional deprecated-name guardrails in INSTALL.md/QC.md/qc-*.sh.
- Criterion 18 media test asserts `url` field non-empty/openable — does NOT hardcode CDN host.
- Criterion 11 Tier-2 de-registration was gated on context-overhead measurement: SHIP decision (see skill 36 CHANGELOG v1.1.0).

---

## Section I: Per-build PLAN/QC protocol (v1.0.15+)

These items document the PLAN MODE → BUILD → QC GATE protocol added in v1.0.15. They are
asserted by qc-convert-and-flow.sh Section S and verified by qc-built-workflow.sh at runtime.

### I-1: PLAN MODE (INSTRUCTIONS.md Step 0.5)

- [ ] Step 0.5 present in INSTRUCTIONS.md between Step 0 and Natural-language intents
- [ ] THINK steps A1 (desired result) + A2 (client expectations) + A3 (best approach) present
- [ ] DEPENDENCY PRE-CHECK (Step B) documented
- [ ] OUTLINE step (Step C) documented
- [ ] CHECKLIST instantiation (Step D) references workflow-build-checklist-template.md
- [ ] IMPROVEMENTS step (Step E) documented
- [ ] Gating question 1 (PUBLISH: draft vs live) documented verbatim
- [ ] Gating question 2 (RE-ENTRY: once vs allow-multiple) documented verbatim
- [ ] Binding rule "Rushing to a default build is NOT the best outcome and is a violation" present
- [ ] "Build a follow-up workflow" intent row re-pointed to PLAN MODE in the intents table
- [ ] Per-operation rule 2.0 (new build → PLAN MODE first) present before rule 2a/2b

### I-2: Workflow Build Checklist Template (references/workflow-build-checklist-template.md)

- [ ] File exists at references/workflow-build-checklist-template.md
- [ ] All 21 WF items present (WF-1 through WF-21)
- [ ] WF-4 trigger active flag (WF-ACTIVE GATE) present with explanation
- [ ] WF-12 SMS From-number gate present
- [ ] WF-20 hallucinated artifacts detector present
- [ ] WF-21 snapshot gate present
- [ ] Skill 41 cross-reference table present (superset mapping)
- [ ] Dual-purpose noted (agent self-check + client hand-over)

### I-3: QC GATE (INSTRUCTIONS.md Step 9)

- [ ] Step 9 QC GATE present in INSTRUCTIONS.md after workflow build instructions
- [ ] Verbatim client announce template present: "I've built the workflow. Before I call it
  done, I'm running an independent QC agent to verify it against the checklist item-by-item."
- [ ] Independent MiniMax sub-agent dispatch documented (sessions_send, minimax/minimax-2.7)
- [ ] Model-availability verification before spawn documented
- [ ] caf workflows export + qc-built-workflow.sh invocation documented
- [ ] Per-item PASS/FAIL verdict requirement documented
- [ ] "Done only after all-PASS + filled checklist handed to client" rule present
- [ ] Build-events ledger logging documented

### I-4: qc-built-workflow.sh (per-build QC script)

- [ ] File exists at qc-built-workflow.sh
- [ ] File is executable (chmod +x)
- [ ] Takes workflow-id as first argument
- [ ] --publish-intent flag (DRAFT/LIVE) documented
- [ ] --re-entry flag (ONCE/ALLOW-MULTIPLE) documented
- [ ] --json flag for machine-parseable output documented
- [ ] WF-3 trigger present asserted
- [ ] WF-4 trigger active vs publish-intent asserted (WF-ACTIVE GATE)
- [ ] WF-5 publish status vs publish-intent asserted
- [ ] WF-6 re-entry/allow-multiple asserted
- [ ] WF-7 action sequence (>=1 action node) asserted
- [ ] WF-12 SMS From-number non-empty asserted
- [ ] WF-15 delivery chain linkage asserted
- [ ] WF-18 + WF-21 snapshot existence asserted
- [ ] Build-events ledger append present
- [ ] Distinct from qc-convert-and-flow.sh (install-level QC)

### I-5: Hallucination escalation (INSTRUCTIONS.md Step 9 "If QC finds a HALLUCINATION")

- [ ] HALLUCINATION defined: build-agent-claimed==TRUE but QC-observed==FALSE/absent/different
- [ ] Fingerprints listed: fake link / wrong From-number / trigger said-active-but-inactive /
  cited id not found
- [ ] WF-20 named as the dedicated hallucination detector
- [ ] HARD STOP rule (do not let same build agent fix and continue) present
- [ ] reasoning-model-thinking-HIGH redo REQUIREMENT (not recommendation) stated
- [ ] Full re-QC from scratch (all 21 items, not just flagged ones) required
- [ ] Client disclosure template present ("QC caught that I reported something...")
- [ ] Ledger logging of hallucination event required
- [ ] Bidirectional link to Step 0 (Step 0 recommendation flipped to requirement) present

### I-6: CORE_UPDATES.md binding rules

- [ ] PLAN-MODE-before-build rule present in AGENTS.md block (think→outline→checklist→
  recommendations→gating questions)
- [ ] QC-GATE rule present in AGENTS.md block (independent MiniMax QC + checklist hand-over
  before done)
- [ ] Hallucination → reasoning-model-thinking-HIGH requirement present in AGENTS.md block
