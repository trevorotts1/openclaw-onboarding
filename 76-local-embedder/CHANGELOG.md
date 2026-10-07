# Changelog - Skill 76 Local Embedder

## [1.0.0] - 2026-10-06
- New skill. Client Macs get a free local embedder for OpenClaw memory search: Ollama 0.36.0 or newer (reused, upgraded in place when idle, or the headless CLI 0.40.0 under the LaunchAgent `com.blackceo.ollama-serve`), `embeddinggemma-2:740m` with `num_ctx 8192` pinned on its own tag, `memory.search` switched to it, one resumable re-index per agent.
- Ollama Cloud protection: key files, sign-in status, cloud tags, `OLLAMA_*` env and the chat-model config are compared before and after; any change fails the run.
- Tests: `tests/test-local-embedder.sh` (mocks only; no install, no model load).
