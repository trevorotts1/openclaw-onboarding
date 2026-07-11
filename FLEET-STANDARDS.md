# Fleet Standards

## Policy

The OpenClaw fleet enforces these mandatory standards on every installation and update:

### 1. Sub-Agents Fully Permitted

Sub-agents perform all labor operations (exec, file read/write, cross-agent spawns). They must never be permission-blocked. The canonical configuration enables:

- **Global sub-agent spawn**: `agents.defaults.subagents.allowAgents = ["*"]` (any target agent)
- **Per-agent override rule**: Every agent in `agents.list[]` that has an explicit `subagents.allowAgents` field must also be set to `["*"]`, OR that field must be deleted so it inherits the global default
- **Execution security**: `tools.exec.security = "full"` and `tools.exec.ask = "off"`
- **Sandbox mode**: Off (`agents.defaults.sandbox.mode = "off"` or undefined)

**Rationale**: The multi-agent orchestration model distributes labor across specialized agents. Blocking sub-agent spawns or tool access breaks the workflow automation that is the core value of a zero-human-company setup.

### 2. Telegram Media Limit 50 MB

Telegram bot API enforces a 50 MB hard ceiling on media uploads. The fleet standard sets:

```json
"channels": {
  "telegram": {
    "mediaMaxMb": 50
  }
}
```

This caps both **inbound and outbound** Telegram media to 50 MB per message. (Note: OpenClaw's documented default is 100 MB; 50 is a deliberate reduction to stay safely below the Telegram API hard limit.)

Can also be overridden per account via `channels.telegram.accounts.<account-id>.mediaMaxMb`.

### 3. WhatsApp — Permanently Banned (fleet-wide, non-negotiable)

WhatsApp is **permanently non-installable** on every box in the fleet. The OpenClaw
Hostinger wrapper auto-installs and auto-enables the WhatsApp plugin on every
gateway boot whenever `WHATSAPP_NUMBER` is present in the Docker `.env` file,
regardless of `openclaw.json`. An un-paired WhatsApp install causes an immediate
QR-scan crash-loop that takes the entire gateway down and does not self-recover.

**Fleet rule (enforced by `apply-fleet-standards.sh` and `install.sh` — hard failure):**

1. `plugins.entries.whatsapp.enabled` is locked to `false` in every `openclaw.json`.
2. `WHATSAPP_NUMBER` must **not** be set (or must be commented out) in the Hostinger
   Docker project `.env` file (`/docker/<project>/.env`). If the line is present and
   non-empty, `apply-fleet-standards.sh` comments it out automatically.
3. Any CI or QC check that finds `"whatsapp"` in the `plugins.entries` enabled list,
   or an un-commented `WHATSAPP_NUMBER=<value>` line in any `.env` committed to the
   repo, is a **hard-fail**.

**Why not just leave it uninstalled?** The auto-install path fires on every
restart — even after a clean `docker compose up -d --force-recreate`. The only
durable fix is (a) removing `WHATSAPP_NUMBER` from the env file **and** (b) explicitly
disabling the plugin in `openclaw.json` so the gateway never attempts to activate it.

**Root cause ref:** `KNOWN-ISSUES.md` issue #5 (WhatsApp auto-install boot loop).

### 4. Big Project Mode (universal operating standard)

Every client agent gets the **BIG PROJECT MODE** standard appended to its active
workspace `AGENTS.md`. It governs how the agent runs any large multi-part build
or document: the owner sends the project as a file; the orchestrator reads it
once and pastes the full text byte-identical at the top of every worker
sub-agent (assignment last), warms one worker before fanning out, keeps the
orchestrator skinny (ledger + deliverables on disk), and runs independent
numeric QC. On per-token caching models (DeepSeek direct, Anthropic, OpenAI)
this cuts input cost 80-95%; on flat-rate routes (Ollama Cloud) it is still
faster and cleaner.

The full client-universal reference is `BIG-PROJECT-MODE.md` at the repo root.
`apply-fleet-standards.sh` appends a compact version of the eight rules to the
agent's `AGENTS.md` idempotently (skipped if the `## BIG PROJECT MODE` heading
already exists).

### 5. Ollama Provider — Platform-Branched (Mac local daemon vs VPS cloud-direct)

The `ollama` model provider is wired **by box type**. There is exactly ONE
`ollama` provider per box (never split into `ollama-local` + `ollama-cloud`).

- **Mac client** (Mac mini / laptop / any macOS): the LOCAL Ollama daemon is
  signed in (`ollama signin`, the client's own ollama.com account) and ONE
  `ollama` provider points at it — `baseUrl: "http://127.0.0.1:11434"`,
  `api: "ollama"`, `apiKey: "ollama-local"`. A signed-in daemon serves BOTH local
  models AND `:cloud` models through that one loopback endpoint (the documented
  "Cloud + Local" hybrid flow). Loopback baseUrl is REQUIRED on Mac.
- **VPS client** (Hostinger Docker / any Linux container, no local daemon): ONE
  `ollama` provider, cloud-direct — `baseUrl: "https://ollama.com"` + the client's
  own `OLLAMA_API_KEY`. A loopback baseUrl → `ECONNREFUSED` (HARD VIOLATION).
- **All boxes:** every `:cloud` model carries `maxTokens: 64000` (Ollama Cloud
  caps output at 65536). Always confirm a live PONG, not just config-valid.

**Enforced (hard-fail) by** `scripts/qc-assert-ollama-provider-platform.sh`
(single source of truth) via `scripts/qc-system-integrity.sh` CHECK X.9. Full
standard + setup + the migration path for legacy Mac clients on cloud-direct:
`docs/OLLAMA-PROVIDER-BY-PLATFORM.md`. Audio transcription (STT) is similarly
branched — Mac uses local `oc-faster-whisper` primary + OpenAI cloud fallback;
VPS uses cloud-only — see `docs/STT-TRANSCRIPTION.md`.

### 6. "TEMPLATE DEPLOYED" and "WORKSPACE INSTANTIATED" are two separate states (AF-WORKSPACE-SHELL)

Copying the shipped role-library **TEMPLATE** to disk (under the SKILLS tree,
`…/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/<dept>/`) is
**"TEMPLATE DEPLOYED."** It is a file copy. It does NOT make a client department.

A client department is **"WORKSPACE INSTANTIATED"** only when its WORKSPACE
directory —
`<workspace>/zero-human-company/<company>/departments/<dept>/` — is MATERIALIZED:

- **≥1 numbered role subdir** (`00-*` / `01-*` …),
- a director **`IDENTITY.md`**, and a director **`SOUL.md`**, and
- **≥1 real SOP** — a role `how-to.md` ≥ 3 KB (the same floor `verify-wiring.sh`
  enforces), or a substantive standalone `0[1-9]-*.md` ≥ 7 KB.

A dept dir that contains only `DREAMS.md` + `memory/` is a **SHELL**. A dept dir
with role subdirs but no `IDENTITY.md`/`SOUL.md` or no real SOP is **PARTIAL**.
A workspace dept dir whose real path resolves into the skills/role-library /
master-files template tree is treated as **not materialized**.

**Fleet rule (hard-fail; the rule that closes the false-"done" that cost real money):**

1. These are TWO SEPARATE STATES. Each is verified separately. **Never report one
   as the other.**
2. **Never** report a client / department "done / installed / updated / airtight"
   without the workspace gate passing **with raw counts** per department. A
   template on disk can NEVER satisfy the gate.
3. The required department set is the `department-floor.py` floor — the same
   single source of truth that gates the on-disk department count. The workspace
   gate goes one layer deeper: for EACH required dept it classifies FULL /
   PARTIAL / SHELL using RAW on-disk facts (never a build-state JSON).
4. ONE canonical department is materialized EXACTLY ONCE. Two sibling dirs under
   `departments/` that normalize to the same canonical slug (`billing` +
   `billing-finance`, `legal` + `legal-compliance`) are a PHANTOM DUPLICATE: the
   variant-aware presence check counts the pair as ONE department, so the floor
   gate cannot see the duplication while both trees diverge on disk. A `.bak`
   tree is never a department (it also poisons the SOP/substance gate). The
   workspace gate FAILS (`rc=5 AF-PHANTOM-DEPT-TREE`); remediation is
   `23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py --merge-duplicates
   [--apply]` (keeps the canonical winner, layers the loser's unique roles in,
   archives the loser OUT of `departments/` — never deletes).

This extends the `lib-onboarding-state.sh` onboarding-honesty philosophy
("installed" is a VERIFIED claim, never a file-copy claim) to the workspace
layer. See `AGENTS.md` N37.

**Enforced (fail-closed) by** `scripts/qc-assert-workspace-departments-built.sh`
(single source of truth) via `scripts/qc-system-integrity.sh` **CHECK X.11**
(rc=3 = `AF-WORKSPACE-SHELL` hard-fail; rc=5 = `AF-PHANTOM-DEPT-TREE` hard-fail),
the onboarding completion gate
`lib-onboarding-state.sh` `oc_overall_goal_check()` (criterion iii
`workspaceMaterialized`), the `scripts/watchdog-onboarding-loop.sh` kill
condition, and CI (`.github/workflows/qc-static.yml` runs
`scripts/test-workspace-departments-built.sh` + `scripts/test-watchdog-loop.sh`).

### 7. Repo consistency — one gate cross-checks floor / roster / library / SOP / persona

The Skill 23 workforce blueprint carries **six independent sources of truth** that
nothing used to cross-check, so a department / role / SOP / persona could ship
**inconsistent** (six departments once shipped UNBUILDABLE because no gate
compared the floor against the rosters):

1. **FLOOR** — `23-ai-workforce-blueprint/department-naming-map.json` `.mandatory`
   (22) + the 6 universal-primary vertical-pack depts = 28 (6 not 7 since
   naming-map v2.6.1 reclassified `listings` to a real-estate-only vertical,
   removing it from the universal_primary layer; enforced on-disk by
   `scripts/department-floor.py`). Keep the three tiers distinct — never
   re-conflate the floor with the total: **28** = guaranteed FLOOR (22 mandatory
   + 6 universal-primary); **34** = built departments (`role-library/_index.json`);
   **45** = full catalog union in `department-naming-map.json`. No client gets all
   34/45 — each gets the 28 floor plus keyword-matched industry verticals minus
   declines; always derive live, never restate a bare integer.
2. **ROSTERS** — `suggested-roles/<dept>-suggested-roles.md` (the proposed
   specialist menu, parsed by `create_role_workspaces.parse_roster`).
3. **ROLE LIBRARY** — `templates/role-library/_index.json` + the per-dept role
   template docs (resolved by `create_role_workspaces.library_lookup`).
4. **SOP SOURCE** — every floor dept's roles must resolve a real SOP source: the
   Skill-23 role-library copy path (canonical, guarded by
   `sop_boundary_gate.is_canonical_dept`) or, for `personal-assistant`, the
   Skill-42 specialist library.
5. **PERSONA DOMAINS** — `build-workforce.py` `create_governing_personas_md` /
   `generate_persona_matrix` `dept_to_domains`, and `create_role_workspaces.py`
   `write_governing_personas_md` `DEPT_DOMAIN_HINTS`. A floor dept MISSING from
   these maps silently falls back to the generic `['leadership']` pool.
6. **NO ORPHANS** — no roster without a floor/library home; no floor dept the
   library can't reach.

**The rule:** every floor department MUST be consistent across all six. When you
ADD or RENAME a department, role, SOP, or persona, you MUST update floor +
roster + library + SOP source + persona maps together. See
`23-ai-workforce-blueprint/ADDING-DEPARTMENTS-ROLES-SOPS.md` for the contributor
checklist.

**Enforced (fail-closed) by** `23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py`
(exit 5 on ANY drift; uses the SAME resolution functions the build uses so it can
never disagree with the build), via `scripts/qc-system-integrity.sh` **CHECK X.12**
(hard-fail), the build-start preflight `lib-onboarding-state.sh`
`oc_repo_consistency_ok()` (a client build REFUSES to run against a drifted
repo), and CI (`.github/workflows/qc-static.yml` runs the gate +
`23-ai-workforce-blueprint/scripts/test-repo-consistency.sh`, which proves the
gate fails on a removed roster / unresolvable role / missing persona-mapping /
corrupt library slug).

### 8. On-Demand MCP Tool Loading — `tools.toolSearch.mode = "directory"` (fleet-wide token-burn fix)

Every box loads MCP tool schemas **on demand** instead of injecting every tool's
full JSON schema into the model context on **every turn**. The fleet standard sets:

```json
"tools": {
  "toolSearch": {
    "mode": "directory"
  }
}
```

**What it does.** In `directory` mode the gateway keeps a bounded prompt *directory*
of available tool **names + descriptions** and exposes `search` / `describe` / `call`
operations. The model sees compact descriptors and hydrates a tool's full schema only
when it actually needs it (`openclaw.tools.describe` / `call`). Client-provided run
tools stay directly visible; the standing catalog (OpenClaw + plugin + **MCP**) is
compacted behind the directory.

**Why it's a fleet standard.** The full-schema-every-turn injection is the durable,
fleet-wide token burn. It is most acute on the **GHL community MCP**
(`ghl-community-mcp`, hundreds of tools) that `update-skills.sh` `wire_ghl_mcp`
re-registers on every update pass. Directory mode compacts that server **regardless
of how many tools/servers are registered**, so re-registration can never reintroduce
the full-schema cost — the fix is provider-agnostic and survives every update.

**Valid values** (`tools.toolSearch.mode`): `"code"` (gateway default) · `"tools"` ·
`"directory"` · or `false` to disable. The fleet pins `"directory"`.
Source: `docs.openclaw.ai/tools/tool-search`.

**Enforced + idempotent + override-preserving.** Written by
`scripts/apply-fleet-standards.sh` via the canonical deep-merge, which recurses into
any existing `toolSearch` block and enforces **only** `mode` — any per-box tuning
(`codeTimeoutMs` / `searchDefaultLimit` / `maxSearchLimit`) is preserved. Applied on
**both** new provision (`install.sh`) and every update (`update-skills.sh`), since both
invoke `apply-fleet-standards.sh`. `openclaw config validate` is the backstop: if a
gateway version ever rejects the key, the run rolls back to the pre-apply backup.

> **Per-turn token-burn — the full picture.** Fleet measurement (2026-07-09)
> showed the *dominant* driver is **prompt caching structurally OFF on the ollama /
> Ollama-Cloud path** (`cacheRead=0` on ~100% of ollama calls across every measured
> box — the whole payload re-billed every turn). Directory mode (§8) is only the
> **tool-schema** lever (it helps GHL-heavy boxes). The other two levers are §9
> (caching — reserved) and §10 (core-bootstrap size). Treat §8–§11 as one
> token-burn-control family.

### 9. Prompt caching on the ollama path — RESERVED (do NOT guess the key)

**Status: reserved slot, no config written yet.** The measured dominant per-turn
burn is that prompt caching is off on the ollama path, so the entire payload is
re-billed every turn. The durable fix is enabling prompt caching on that path —
**but the exact config key, and whether Ollama-Cloud even supports server-side
caching, are still being verified against the OpenClaw docs.** Until that returns,
**no key is written** (a wrong key fails `openclaw config validate` and rolls the
whole fleet-standards apply back, or silently no-ops).

`scripts/apply-fleet-standards.sh` carries a clearly-marked, idempotent slot —
grep sentinel `RESERVED-SLOT: PROMPT-CACHING-OLLAMA` — positioned inside the
validated config path. When the verified key/value returns, it is written into the
canonical deep-merge block (§ "2. Deep-merge the canonical fleet block") and is
then automatically covered by the `openclaw config validate` + rollback gate.
**Do not populate this slot by guessing.**

### 10. Core-bootstrap size guard (WARN-ONLY, ~150K-char target)

The gateway-injected core bootstrap (`AGENTS.md` + `MEMORY.md` + `TOOLS.md` +
`SOUL.md` + `IDENTITY.md` + `USER.md` + `HEARTBEAT.md` in the resolved workspace)
is re-injected on **every turn** — and, while §9 caching is off, re-billed every
turn. Measurement found several boxes at **190K–330K chars**. The fleet standard
sets a **target of ~150,000 chars** for the compiled core bootstrap per box.

`scripts/apply-fleet-standards.sh` measures the injected core-file set (the same
files the gateway reads — `shared-utils/resolve_injected_core_files.py`) and
**logs a WARN + per-file breakdown + the target** when the total exceeds it. This
is a **warning only — it never edits core-file content** (trimming is an operator
decision). Non-blocking and idempotent (pure measurement). Override the threshold
via `FLEET_CORE_BOOTSTRAP_TARGET_CHARS`.

### 11. Transcript / compaction cap — conservative default only

**Do not set an aggressive `softThresholdTokens`.** OpenClaw's compaction
`softThresholdTokens` is **subtractive**; setting it too low mis-configures
compaction and surfaces as *"context too large"* (the fix for that symptom is a
fresh session / `/new`, not a lower threshold). The fleet standard is therefore to
**leave the gateway's documented default in place** and tune compaction only
conservatively and per-box when genuinely needed. No aggressive cap is written by
the fleet-standards apply.

## Source of Truth

Configuration verified against:
- docs.openclaw.ai/tools/subagents
- docs.openclaw.ai/gateway/security
- docs.openclaw.ai/tools/multi-agent-sandbox-tools
- docs.openclaw.ai/tools/tool-search (§8 on-demand MCP tool loading — `tools.toolSearch.mode="directory"`)
- docs.openclaw.ai/providers/ollama (Ollama "Cloud + Local" hybrid flow, §5)
- Live test on OpenClaw 2026.5.28 (a Mac mini client box, session logs)

## Activation

Run `scripts/apply-fleet-standards.sh` during onboarding or update. The script:
1. Backs up `openclaw.json` with timestamp
2. Deep-merges the canonical fleet block
3. Validates with `openclaw config validate`
4. Appends the **BIG PROJECT MODE** section to the agent's active-workspace
   `AGENTS.md` (resolved the same way `install.sh` resolves it — per-agent
   `main` override, then `agents.defaults.workspace`, then the canonical
   `$OC_ROOT/workspace` default for Mac or VPS)
5. Reports before/after state and idempotent status

The script is idempotent: running it twice on an already-compliant box is a
no-op (config already canonical AND the `## BIG PROJECT MODE` heading already
present in `AGENTS.md`).

## Integration

- **Mac onboarding** (`openclaw-onboarding`): invoked from `install.sh` after core config is in place
- **VPS onboarding** (`openclaw-onboarding`, platform/vps/ overlay): invoked from the main setup flow
- **Updates**: both repos wire the script into their documented update paths so every `npm install -g openclaw@<ver>` run triggers standards reapplication

---

Last verified: 2026-07-09 (OpenClaw 2026.6.x, fleet-wide; §5 Ollama platform-branch added v12.21.0; §8 on-demand MCP tool loading `tools.toolSearch.mode="directory"` added — fleet-wide schema-every-turn token-burn fix; §9 prompt-caching RESERVED slot [awaiting verified key], §10 core-bootstrap size guard [warn-only ~150K], §11 conservative compaction-cap note added — per-turn token-burn-control family)
