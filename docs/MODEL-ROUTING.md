# MODEL-ROUTING — Skill 6 Role-Aware Fallback Doctrine

**Version:** v1.0.0
**Branch:** feat/ghl-survey-skill6-update
**Scope:** Fleet-wide fallback policy; first concrete implementation in
`06-ghl-install-pages/tools/model_router.py`. The CI guard added in this branch
enforces no banned model tokens in **code AND markdown**.
**Relation to N35:** This doc records the Skill 6 role map and hard rules. The
authoritative fleet-wide cascade policy is N35 (`AGENTS.md`) + `shared-utils/assert_model_sovereignty.py`.

> The canonical implementation is `model_router.py`. This file is the human-readable contract it satisfies; if they diverge, `model_router.py` is wrong.

---

## 1. Universal Fallback Order

Three tiers, strict priority — every role, every rung, no exceptions:

| Tier | Provider | Condition |
|---|---|---|
| **1 — Ollama Cloud** | `:cloud` suffix; `baseUrl=https://ollama.com`; client's own `id_ed25519` device key | Always attempt first |
| **2 — OpenRouter equivalent** | Same model family, OpenRouter open-weight route | Only if Ollama Cloud fails (capacity / key absent / ECONNREFUSED) |
| **Last — OpenRouter `google/gemini-3.5-flash`** | OpenRouter; no probe gate | Appended to every ladder; fires only when both Tier 1 and Tier 2 fail and credits are live |

`thinking=high` is mandatory on every rung of every role — no exceptions, no silently-lower overrides.

---

## 2. Skill 6 Role Map

| Role | Alias | Tier 1 (Ollama Cloud slug) | Tier 2 (OpenRouter slug) | Notes |
|---|---|---|---|---|
| `content` | — | `kimi-k2.6:cloud` | `moonshotai/kimi-k2.6` | Copy writing, welcome slides, prompts |
| `html` | `code` | `glm-5.2:cloud` | `z-ai/glm-5.2` | Code-block fix loop, HTML generation |
| `reasoning` | `funnel` | `glm-5.2:cloud` then `deepseek-v4-pro:cloud` | `z-ai/glm-5.2` then `deepseek/deepseek-v4-pro` | Funnel structure and planning; two Ollama Cloud rungs precede OpenRouter rungs |
| `execution` | — | `minimax-m3:cloud` (probe-gated) → `deepseek-v4-pro:cloud` | `minimax/minimax-m3` (probe-gated) → `deepseek/deepseek-v4-pro` | Browser-click drive loop; probe gate on M3 rungs only |
| `qc` | — | `minimax-m3:cloud` (probe-gated, vision) | `minimax/minimax-m3` (probe-gated, vision) | Vision QC on screenshots and DOM; text-only models excluded from this ladder |

**MiniMax M3 probe gate** (on `execution` and `qc`): a live tool-call (`echo_tool {ok:true}`)
must PASS before the model dispatches. On fail, one backoff retry, then the ladder
advances. DeepSeek is never probe-gated.

**DeepSeek v4 pro is the universal non-vision backup** appended to every ladder except `qc`.
DeepSeek and GLM have no confirmed vision capability; the `qc` ladder must remain
vision-capable throughout, so it runs only MiniMax M3 (probe-gated) and Gemini 3.5 Flash.

---

## 3. Hard Rules

**MiniMax M2 — BANNED everywhere.** MiniMax M2 is PURGED from every rung, table,
recommendation, and doc. The execution role uses MiniMax M3 only, falling back to
DeepSeek v4 pro if the probe fails. The M2 hyphenated slug form must never appear in
code or markdown; the CI step (section 4a) fails the build on any occurrence,
no exclusions.

**ollama/kimi-k2.6:cloud and openrouter/moonshotai/kimi-k2.6 — the only valid routes.**
The content model (ollama/kimi-k2.6:cloud on Tier 1; openrouter/moonshotai/kimi-k2.6
on Tier 2) is NEVER referenced with a bare, provider-less id. Any reference without
the `ollama/` or `openrouter/` prefix fails CI check (d).

**No Anthropic models anywhere in the client path — explicitly forbidden at two
independent gates.** `assert_model_sovereignty` (`shared-utils/assert_model_sovereignty.py`,
N35) blocks at dispatch-time; `model_router.py`'s `assert_no_anthropic()` blocks
at build-time. Claude model ids and anthropic-namespaced paths are forbidden on any
rung, any role, any box. Both gates must hold; AnthropicModelError is never caught
and silenced.

**`thinking=high` on every rung.** The `THINKING_EFFORT = "high"` constant in
`model_router.py` is applied across all role ladders and is verified by offline
self-test assertion 9 of 14 (`model_router.py --selftest`).

---

## 4. CI Guard

`.github/workflows/qc-static.yml` step **"No banned model tokens in GHL skill markdown
prose"** scans `05-ghl-setup`, `06-ghl-install-pages`, `29-ghl-convert-and-flow`,
`36-ghl-mcp-setup`, `44-convert-and-flow-operator`, and `docs/` across all `*.md` files
for four violation classes. A violation fails the build without a manual override:

**(a) M2 hyphenated slug form — BANNED.** The M2 generation model id token in its
dash-separated or path-separated slug form (separator between "minimax" and "m2", or
provider-prefixed variant). No ban-language exclusion applies; any occurrence in any
markdown or code file is a hard build failure.

**(b) Bare M2 in a rung or ladder context.** The `(MiniMax|minimax) M2` token pattern
on a line that does NOT contain `banned`, `PURGED`, `purge`, `do not`, `never use`,
`must not`, `supersede`, or `removed the stale`. Ban statements that name M2 are
explicitly excluded so the ban assertion does not self-trip.

**(c) Anthropic model identifier patterns.** Claude model ids and anthropic-namespaced
provider paths used as active model ids, on lines that do not carry explicit
`forbidden`, `rejected`, `never`, or `banned` phrasing.

**(d) Content-model slug without a provider prefix.** A `\bkimi\b` match
(case-insensitive) on a line that contains none of: `ollama/kimi`, `openrouter/kimi`,
`openrouter/moonshotai/kimi`, or `kimi-k2.6:cloud`. Valid qualified forms that pass:
ollama/kimi-k2.6:cloud (Tier 1), openrouter/moonshotai/kimi-k2.6 (Tier 2). This doc
is authored to remain clean against all four checks.

---

## 5. Enforcement Points

| Layer | File | What it enforces |
|---|---|---|
| Code (Skill 6) | `06-ghl-install-pages/tools/model_router.py` | Role-keyed ladders; `assert_no_anthropic()` at build-time; MiniMax M3 probe gate; `THINKING_EFFORT=high` |
| Shared gate | `shared-utils/assert_model_sovereignty.py` | Per-slug block at dispatch-time — no Anthropic, no free literal, modality check (N35) |
| CI | `.github/workflows/qc-static.yml` step "No banned model tokens..." | Banned token scan across code + markdown — checks (a)–(d) above; added in this branch |
| Offline self-test | `06-ghl-install-pages/tests/test_model_router.py` | 14 assertions: role rung-1 families, Ollama-before-OpenRouter order, last-rung Gemini 3.5 Flash, probe-gate flags, M2 absent |
| Fleet doctrine | `AGENTS.md` N35 (AF-MODEL-SOVEREIGNTY) | Universal cascade; Anthropic ban; modality gate; fleet-wide application |
