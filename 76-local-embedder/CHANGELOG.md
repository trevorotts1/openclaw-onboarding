# Changelog - Skill 76 Local Embedder

## [1.0.1] - 2026-10-07
- Fix (QC): a fresh install no longer fails after the config write. The first `ollama serve` creates `~/.ollama/id_ed25519*`; keys may now go from absent to present only when this run started our own daemon, pre-existing keys must stay identical. Every guard now passes BEFORE `memory.search` is written, and the write is the last mutating step before the re-index.
- Time limits: per-agent re-index (900 s), every brew call (1800 s), `ollama show`/`create`; bash 3.2 safe (perl alarm, background-and-kill fallback). update-skills.sh bounds the whole skill run (7200 s).
- `memory.search.fallback` defaults to `none` (knob `LOCAL_EMBEDDER_FALLBACK`), so no query runs in another vector space.
- The Ollama app is stopped with SIGTERM, never osascript; still running after the wait means the upgrade is deferred and the bundle is never replaced.
- Per-agent `memory.search` / `memorySearch` overrides are reported, skipped and never rewritten; the fingerprint now covers the whole `agents` block.
- The write keeps key order and indentation and re-reads the file right before the atomic replace (one retry).
- Tests: 65 checks, now executing the fresh-install path; mutation-proven against a no-op checksum, a removed `/api/show` verify, write-before-guards ordering, fresh-key acceptance, the re-index timeout and the fallback default.

## [1.0.0] - 2026-10-06
- New skill. Client Macs get a free local embedder for OpenClaw memory search: Ollama 0.36.0 or newer (reused, upgraded in place when idle, or the headless CLI 0.40.0 under the LaunchAgent `com.blackceo.ollama-serve`), `embeddinggemma-2:740m` with `num_ctx 8192` pinned on its own tag, `memory.search` switched to it, one resumable re-index per agent.
- Ollama Cloud protection: key files, sign-in status, cloud tags, `OLLAMA_*` env and the chat-model config are compared before and after; any change fails the run.
- Tests: `tests/test-local-embedder.sh` (mocks only; no install, no model load).
