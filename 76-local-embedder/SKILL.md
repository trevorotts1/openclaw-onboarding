---
name: local-embedder
description: >
  Infrastructure for client Macs: a free local embedder for OpenClaw memory
  search. Installs or reuses Ollama (0.36.0 or newer, headless, no GUI, no
  sudo), pulls embeddinggemma-2:740m with num_ctx 8192 pinned on its own tag,
  points memory.search at http://127.0.0.1:11434 and re-indexes each agent
  once. Never touches Ollama Cloud sign-in, chat-model config or OLLAMA_* env.
  Runs from the fleet roll; not a client-facing feature.
version: 1.3.0
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
     connections, checked 3 times 60 seconds apart, else deferred. The app is
     stopped with SIGTERM (never osascript, which needs a consent prompt over
     SSH); if it is still running after the wait, the upgrade is deferred and
     the running bundle is never replaced. Every brew call is time-bounded.
   - Ollama installed but stopped: reported, not started.
   - No Ollama at all: the official headless CLI 0.40.0 tarball
     (sha256-verified) is extracted to `~/.openclaw/ollama/0.40.0/` and run by
     the LaunchAgent `com.blackceo.ollama-serve` with `OLLAMA_KEEP_ALIVE=3m`
     and `OLLAMA_MAX_LOADED_MODELS=2`. No GUI app, no sudo, no `install.sh`.
3. **Model.** Pull `embeddinggemma-2:740m` if absent, then re-create the SAME
   tag from its own Modelfile plus `PARAMETER num_ctx 8192`. Verified through
   `/api/show` (metadata only, nothing is loaded).
4. **Guards, all BEFORE any config write (fail closed).** The fingerprint of
   `models`, the whole `agents` block and `memory` minus `memory.search`, the
   `~/.ollama/id_ed25519*` file metadata (they may only appear, never change,
   and only when this run started our own daemon for the first time), the
   `OLLAMA_*` launchd env, the `/api/me` sign-in status and the cloud tag list
   must all be unchanged, and the pin must be confirmed by `/api/show`.
5. **Config, the last mutating step.** Deep-merge of `memory.search` only
   (provider `ollama`, the model, `remote.baseUrl` on 127.0.0.1, multimodal
   off, fallback from the knob below), key order and indentation kept. In the
   SAME write, one per-agent key may change: an agent that inherits the local
   provider (no own provider, model or remote) and has
   `memory.search.multimodal.enabled=true` (department and cc-* agents
   scaffolded that way) gets it set to false, because the local text embedder
   has no multimodal adapter and its re-index would fail. The fingerprint
   exempts exactly that key; an agent with its own provider is reported and
   untouched. The
   file is re-read right before the atomic replace (one retry if the gateway
   wrote it meanwhile), backed up, then `openclaw config validate` (restores
   the backup on failure). No failure can leave memory search pointing at a
   daemon or model that is not ready.
6. **Re-index.** `openclaw memory status --index --agent <id>` once per agent,
   each bounded (default 900 s); a timeout is retried next roll. A transient
   SQLite error ("did not stabilize", busy, locked) is retried 2 more times with
   a backoff (`LOCAL_EMBEDDER_REINDEX_RETRIES`, `LOCAL_EMBEDDER_REINDEX_BACKOFF`)
   before the agent is left for the next roll. A marker per
   agent in `~/.openclaw/local-embedder/reindexed/` makes it embed-once and
   resumable. Agents whose own `memory.search` / `memorySearch` override sets a
   provider, model or remote are reported and skipped, never rewritten.

## The fallback knob

`LOCAL_EMBEDDER_FALLBACK` (in `wire.sh`) sets `memory.search.fallback`.
**Default: `none`.** A 768-dim local index is then never queried or rebuilt
in another provider's vector space while local Ollama is down; memory search
pauses instead. Set it to a provider id only on purpose, for one box.

Time limits (seconds): `LOCAL_EMBEDDER_REINDEX_TIMEOUT` (900 per agent),
`LOCAL_EMBEDDER_BREW_TIMEOUT` (1800 per brew call),
`LOCAL_EMBEDDER_APP_STOP_WAIT` (30 after SIGTERM). update-skills.sh bounds the
whole run with `LOCAL_EMBEDDER_ROLL_TIMEOUT` (7200).

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
When the box has its own Google key, steps 5b and 5c also install the Gemini
fallback copies (persona index; SOP set via the Command Center's
`provision-gemini-fallback-sop-set.ts`, CC v7.6.108 or newer), used only while
local Ollama is down. Both are skipped without a key and never fatal.

## Commands

- `bash wire.sh --dry-run`: reads only and prints the plan.
- `bash wire.sh`: install or converge (idempotent, safe to re-run).
- `bash wire.sh --no-reindex`: skip step 6.
- `bash wire.sh --sop-fallback-only`: run only step 5c. update-skills.sh calls it
  after the Command Center refresh, so a CC that reaches 7.6.108 later in the
  same roll is still provisioned (idempotent).
- `bash tests/test-local-embedder.sh`: offline tests with mocks.
