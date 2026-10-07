---
name: local-embedder
description: >
  Infrastructure for client Macs: a free local embedder for OpenClaw memory
  search. Installs or reuses Ollama (0.36.0 or newer, headless, no GUI, no
  sudo), pulls embeddinggemma-2:740m with num_ctx 8192 pinned on its own tag,
  points memory.search at http://127.0.0.1:11434 and re-indexes each agent
  once. Never touches Ollama Cloud sign-in, chat-model config or OLLAMA_* env.
  Runs from the fleet roll; not a client-facing feature.
version: 1.0.0
priority: MEDIUM
---

# Local Embedder (Skill 76)

## What it does

Memory search on a client Mac stops paying a cloud embedding API. It runs on a
local Ollama model instead: `embeddinggemma-2:740m`, 768-dim vectors, context
pinned to 8192 on the original tag.

`wire.sh` runs on every fleet roll (update-skills.sh, once per onboarding
version, retried while it exits 1). Steps, in order:

1. **Guards.** Mac only (`detect_platform`), not `/data/.openclaw` (VPS), not
   Docker, Apple Silicon, macOS 14+, OpenClaw 2026.9+, 5 GB free disk,
   `proxy.loopbackMode` not `block`. Anything else exits 0 as SKIPPED or 1 as
   DEFERRED.
2. **Ollama.**
   - Running daemon 0.36.0 or newer: reused. Nothing installed, restarted or
     reconfigured.
   - Running daemon older than 0.36.0: upgraded in place by its own method
     (Homebrew cask, Homebrew formula, the app bundle swapped from the
     checksum-verified official zip with the old bundle moved to the Trash, or
     our own LaunchAgent), only when idle: no loaded models and no open
     connections, checked 3 times 60 seconds apart, else deferred.
   - Ollama installed but stopped: reported, not started.
   - No Ollama at all: the official headless CLI 0.40.0 tarball
     (sha256-verified) is extracted to `~/.openclaw/ollama/0.40.0/` and run by
     the LaunchAgent `com.blackceo.ollama-serve` with `OLLAMA_KEEP_ALIVE=3m`
     and `OLLAMA_MAX_LOADED_MODELS=2`. No GUI app, no sudo, no `install.sh`.
3. **Model.** Pull `embeddinggemma-2:740m` if absent, then re-create the SAME
   tag from its own Modelfile plus `PARAMETER num_ctx 8192`. Verified through
   `/api/show` (metadata only, nothing is loaded).
4. **Config.** Atomic JSON deep-merge of `memory.search` only: provider
   `ollama`, the model, `remote.baseUrl` on 127.0.0.1, multimodal off.
   Fallback `openai` when the client has an OpenAI key; otherwise the existing
   fallback is kept and reported. Then `openclaw config validate` (restores
   the backup on failure).
5. **Post-verify (fail closed).** Chat-model config fingerprint, the
   `~/.ollama/id_ed25519*` file metadata, the `OLLAMA_*` launchd env, the
   `/api/me` sign-in status and the cloud tag list must all be unchanged.
6. **Re-index.** `openclaw memory status --index --agent <id>` once per agent.
   A marker per agent in `~/.openclaw/local-embedder/reindexed/` makes it
   embed-once and resumable.

## Hard rules

- Never read, modify or remove `~/.ollama/id_ed25519*` (only `stat` metadata
  is compared). Never `ollama signout`. Never wipe `~/.ollama`.
- Never set `OLLAMA_CONTEXT_LENGTH`. Never change existing `OLLAMA_*` env, the
  Ollama app settings database or brew service definitions.
- Never write `models.providers.*`, `:cloud` refs, `contextWindow`, model
  primary or fallbacks. Automation writes only `memory.search.*`.
- Never two daemons on one port. Never run Ollama's own `install.sh`.
- Ornith (`ornith-1.5:9b`) is opt-in only: `wire.sh --with-ornith` (operator).

## Other skills that respect it

`install.sh`, `31-upgraded-memory-system/scripts/activate-memory-stack.sh` and
`update-skills.sh` skip memory-search re-pinning when memory search is on a
loopback Ollama. Skill 38 step O.6 accepts it without an OpenAI or Google key.
`shared-utils/embedding_health.py` checks it by metadata only (set
`EMBED_HEALTH_SMOKE=1` for a real embed).

Persona and Command Center SOP embeddings stay on the shipped Gemini assets.

## Commands

- `bash wire.sh --dry-run`: reads only and prints the plan.
- `bash wire.sh`: install or converge (idempotent, safe to re-run).
- `bash wire.sh --no-reindex`: skip step 6.
- `bash tests/test-local-embedder.sh`: offline tests with mocks.
