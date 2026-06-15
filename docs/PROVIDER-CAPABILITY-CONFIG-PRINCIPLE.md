# Provider Capability Config Principle

**Version:** v12.14.0  
**Scope:** Fleet-wide. Applies to every client box, every agent, every openclaw.json.

---

## The Principle

**Config must be derived from the client's REAL provider capabilities.**

Every provider-dependent feature in an agent config (embeddings, memory search,
multimodal input, fallback routing) must be verified against what the configured
provider can actually do on THIS box with THIS client's own API keys.

A config that looks valid in isolation but contradicts the provider's real
capabilities is a broken config. The break is usually silent — no startup error,
no warning — and surfaces as a runtime throw on every user message.

The specific bug class this guards against: setting
`memorySearch.multimodal.enabled=true` with a TEXT_ONLY embedding provider.
The memory-core multimodal adapter throws on every turn. Memory search goes dark
silently. The client sees a dysfunctional agent.

---

## Three Rules (enforced at every gate)

### Rule 1: Config is derived from real provider capabilities — never assumed

Before writing any provider-dependent feature into a client's openclaw.json, verify
the provider's actual capabilities:
- Does this provider support multimodal (image + text) embeddings?
- Can this provider serve as a memory-search fallback?
- Is this provider reachable on this box with this client's keys?

Do NOT copy a config that works on another box. Each client box has its own
credentials; a feature enabled on one box may silently fail on another.

### Rule 2: Every provider-dependent feature must have a safe fallback

`memorySearch.fallback` MUST NOT be set to `"none"`. A config with no fallback
has zero recovery when the primary embedding provider fails. Memory search silently
dies and the agent loses all memory retrieval.

Always set fallback to a working text-embedding provider. `"openai"` and
`"openrouter"` are safe defaults with wide text-embedding support.

### Rule 3: Failures must surface loudly — never degrade silently

A misconfigured provider feature must produce a loud, clear error at startup or at
the smoke-test gate, not a silent runtime exception on every user message.

The enforcement mechanism is the smoke test (on the client's box, with the client's
keys). If the smoke test fails, closeout is blocked. The operator gets a Telegram
alert. The build does not proceed until config matches reality.

---

## TEXT_ONLY Embedding Providers

These providers serve text-only embeddings. Setting
`memorySearch.multimodal.enabled=true` against any of them causes the memory-core
multimodal adapter to throw on every message.

| Provider ID     | Notes                                              |
|-----------------|----------------------------------------------------|
| openai          | text-embedding-* models are text-only              |
| openrouter      | proxies text-embedding-3-small and similar         |
| ollama          | local Ollama — text-only embedding models          |
| ollama-cloud    | Ollama Cloud — same text-only constraint applies   |
| gemini          | standard embedding API is text-only                |
| google          | alias for gemini family                            |
| cohere          | embed-english-* are text-only                      |
| mistral         | mistral-embed is text-only                         |
| anthropic       | no public embedding endpoint                       |
| groq            | no embedding endpoint                              |
| together        | text-only embeddings                               |
| fireworks       | text-only embeddings                               |
| perplexity      | no embedding endpoint                              |
| deepseek        | text-only embeddings                               |

**If you are adding a new provider:** assume TEXT_ONLY unless provider documentation
explicitly confirms multimodal embedding input. Update the list in:
- `scripts/smoke-test-provider-capabilities.sh` (TEXT_ONLY_PROVIDERS variable)
- `scripts/qc-assert-provider-capability-invariants.sh` (TEXT_ONLY_PROVIDERS set)

---

## Enforcement Gates

This principle is enforced at two independent gates. Both must pass.

### Gate 1 — Build-time static invariant (CI / QC harness)

`scripts/qc-assert-provider-capability-invariants.sh`

Checks openclaw.json on disk. Fails the build if:
- `agents.defaults.memorySearch.fallback = "none"`
- Any agent has `memorySearch.multimodal.enabled=true` while the resolved
  embedding provider is in the TEXT_ONLY list

Wired as Check X.8 in `scripts/qc-system-integrity.sh`.

### Gate 2 — Runtime smoke test (client box, client keys)

`scripts/smoke-test-provider-capabilities.sh`

Runs ON the client's box with the client's own API credentials. Fails loud on:
- (S1) `memorySearch.fallback = "none"`
- (S2) Multimodal enabled against a TEXT_ONLY provider (capability mismatch)
- (S3) Live agent probe returns no valid reply (4xx / ECONNREFUSED / 402 / model error)
- (S4) Memory search throws (multimodal adapter throw or embedding provider failure)

On any failure:
- Sets `closeoutStatus = blocked-provider-mismatch` in `.workforce-build-state.json`
- Sends a Telegram alert to the operator

Wired as Gate B7 in `37-zhc-closeout/scripts/run-closeout.sh` (runs before any
generation begins).

Also callable from the per-box embedding-health cron for periodic health polling.

---

## Why a live smoke test? Why not just static checking?

Static config analysis catches the obvious mismatches but cannot verify:
- Whether the API key is valid and the provider is reachable from this box
- Whether the provider account has quota / billing set up
- Whether the configured model exists in the provider's current catalog
- Whether the provider's embedding behavior matches what the config assumes

Only a live test on the client's box with the client's own keys proves the
config actually works. The static invariant catches obvious coding errors;
the smoke test catches runtime realities.

**The only proof that a config works is a successful live test on that specific box.**

---

## Remediation

If either gate fails:

1. Read the FATAL line from the script output — it names the exact invariant and agent.
2. Open `openclaw.json` on the client box.
3. Find `agents.defaults.memorySearch` (and any per-agent `memorySearch` blocks).
4. Fix the violation:
   - `fallback=none` → set to `"openai"` or `"openrouter"`
   - `multimodal.enabled=true` with text-only provider → set to `false`
5. Run the smoke test again: `bash scripts/smoke-test-provider-capabilities.sh`
6. Run the static check: `bash scripts/qc-assert-provider-capability-invariants.sh`
7. When both exit 0, retry closeout: `bash 37-zhc-closeout/scripts/run-closeout.sh`

---

## Version history

| Version  | Change                                                          |
|----------|-----------------------------------------------------------------|
| v12.14.0 | Initial — smoke test, static invariant, B7 closeout gate, docs |
