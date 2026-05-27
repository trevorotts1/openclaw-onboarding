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

## 3. KIE nano-banana-2 image slug is account/region-dependent (422)

**Symptom:** Skill 37 closeout Infographic #2 (the "How Work Flows" diagram)
fails on submit with a KIE 422 like `model name not supported` for
`nano-banana-2`, even though the same slug works on other KIE accounts.
Seen on Teresa Pelham's KIE account 2026-05-27; it had worked elsewhere in
a prior release.

**Root cause:** Model availability on KIE is gated per account/region.
`nano-banana-2` (Gemini 3.1 Flash Image) is not enabled for every KIE
account, so a request that is valid on one account returns 422 on another.
This is a KIE provisioning behavior, not a slug typo.

**Workaround (already wired into the repo):**
`37-zhc-closeout/scripts/generate-infographics.sh` keeps `nano-banana-2` as
the PRIMARY model and falls back to `gpt-image-2-text-to-image` (the proven
safety net) when the primary is rejected. As of v10.X.8 the retry loop also
detects a `model name not supported` / 422 submit error and switches to the
fallback EARLY instead of burning both primary attempts. Override the primary
explicitly with `ZHC_IMAGE_MODEL` if a given account has a different preferred
slug. Do NOT remove `nano-banana-2` as the primary; it works on most accounts
and renders text better than the fallback.

**Upstream ask:** none (KIE account provisioning, not an OpenClaw defect).
The fallback chain is the durable fix.

---

## Filing upstream

Both issues are core-runtime, not onboarding. File against the openclaw
project with the symptom log lines above. Until fixed, the workarounds here
keep the fleet responsive. The recommended fallback-embeddings and
agent-timeout values should be carried in the default onboarding config so
fresh installs are protected by default.
