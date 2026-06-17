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

## Source of Truth

Configuration verified against:
- docs.openclaw.ai/tools/subagents
- docs.openclaw.ai/gateway/security
- docs.openclaw.ai/tools/multi-agent-sandbox-tools
- docs.openclaw.ai/providers/ollama (Ollama "Cloud + Local" hybrid flow, §5)
- Live test on OpenClaw 2026.5.28 (Sheila Reynolds' Mac mini, session logs)

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

Last verified: 2026-06-17 (OpenClaw 2026.6.x, fleet-wide; §5 Ollama platform-branch added v12.21.0)
