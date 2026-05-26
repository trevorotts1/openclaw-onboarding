# Known OpenClaw Core Issues

These are defects in the OpenClaw core runtime that the onboarding repo
CANNOT patch directly (they live in the npm package, not in our skills or
scripts). Documented here so fleet operators recognize the symptoms fast,
apply the workaround, and file upstream. Last reviewed 2026-05-26 against
the openclaw dist installed on the fleet.

---

## 1. Memory embeddings stall blocks the agent loop

**Symptom:** Owner messages get no response. Logs show repeated
`embeddings rate limited; retrying`. The agent loop blocks BEFORE the LLM
call is ever made, because the memory-search embeddings step has no
timeout and sits in a retry spin while the embeddings provider rate-limits.

**Root cause:** The memorySearch embeddings call is awaited synchronously
ahead of the model call with no cap on retry/backoff. A throttled provider
therefore stalls the whole turn rather than degrading gracefully.

**Workaround (config knobs confirmed present in the running dist):**

- `memorySearch.fallback.provider`
- `memorySearch.fallback.model`
- `memorySearch.fallback.apiKey`

Configure a FAST fallback embeddings provider so a rate-limit on the
primary provider trips over to the fallback instead of spinning. Recommended:
point the fallback at a low-latency local or secondary-key provider distinct
from the primary. If the stall persists even with a fallback set, reduce
memory-search pressure by leaving caching on:

- `memorySearch.cache.enabled = true`
- `memorySearch.cache.maxEntries` (raise if the box has RAM headroom)

You can also disable memory search entirely as a last resort
(`memorySearch.enabled = false`) to confirm it is the cause.

**Upstream ask:** add an `embeddingTimeoutMs` (or equivalent) so the
embeddings step fails open to the LLM call after N ms instead of blocking
the turn indefinitely.

---

## 2. Stalled long-thinking-model session, recovery=none

**Symptom:** A session hangs with a log line like:

```
stalled session ... activeWorkKind=model_call lastProgress=model_call:started recovery=none
```

Seen with `deepseek-v4-pro` at `thinking=high` plus a deep message queue.
The model call starts, makes no further progress, and the StallWatchdog
reports `recovery=none` so nothing auto-recovers. The queue stays wedged.

**Root cause:** The stall watchdog detects the lack of progress but, for a
model call that has already entered the `model_call:started` state, it has
no recovery action wired (recovery=none), so it only observes the stall.

**Workaround (config knobs confirmed present in the running dist):**

- `agentTimeoutMs` / `agentTimeoutSeconds` -- set a bounded agent timeout so
  a wedged turn is force-ended instead of hanging forever. Pick a ceiling
  comfortably above your slowest legitimate deep-thinking turn (for high
  thinking on a heavy reasoning model, several minutes).
- When it happens live: `docker compose up -d --force-recreate` (or restart
  the container) to clear the wedged queue, OR swap the agent to a faster
  model (lower `thinking`, or a non-deep-reasoning model) until the backlog
  drains.

**Upstream ask:** wire a recovery action for `activeWorkKind=model_call`
stalls (cancel + requeue the turn) so the StallWatchdog can report a
non-`none` recovery instead of merely observing the wedge.

---

## Filing upstream

Both issues are core-runtime, not onboarding. File against the openclaw
project with the symptom log lines above. Until fixed, the workarounds here
keep the fleet responsive. The recommended fallback-embeddings and
agent-timeout values should be carried in the default onboarding config so
fresh installs are protected by default.
