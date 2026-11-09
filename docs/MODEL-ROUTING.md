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

| Tier | Resolution | Condition |
|---|---|---|
| **1. The client's selected model** | The model the client chose for this role, on the client's own provider and keys | Always attempt first |
| **2. The client's configured fallbacks** | The fallback chain in the client's own configuration, in the client's configured order | Only if the selected model fails (capacity / key absent / ECONNREFUSED) |
| **Last. The final configured fallback** | The last entry of the client's configured fallback chain; no probe gate | Fires only when every earlier rung fails and credits are live |

Recommendation: put a fast, low-cost model last in the fallback chain, because the last rung exists to keep the job moving when everything else has failed. The client still chooses which model that is.

`thinking=high` is mandatory on every rung of every role — no exceptions, no silently-lower overrides.

---

## 2. Skill 6 Role Map

Every role resolves the same way: ask the client which model they want to use for the role. If the client has already configured a default model, use the client's configured default model. Do not prescribe a specific model by name.

| Role | Alias | Model | Notes |
|---|---|---|---|
| `content` | - | The client's choice, or the client's configured default model | Copy writing, welcome slides, prompts |
| `html` | `code` | The client's choice, or the client's configured default model | Code-block fix loop, HTML generation |
| `reasoning` | `funnel` | The client's choice, or the client's configured default model | Funnel structure and planning. Recommendation: a strong reasoning model, because this role is planning work |
| `execution` | - | The client's choice, or the client's configured default model (probe-gated) | Browser-click drive loop. Recommendation: a model with reliable tool calling, because this role acts through tool calls |
| `qc` | - | The client's choice, or the client's configured default model (probe-gated, vision) | Vision QC on screenshots and DOM; text-only models excluded from this ladder. Recommendation: a vision-capable model, because the role checks screenshots |

**Tool-call probe gate** (on `execution` and `qc`): a live tool-call (`echo_tool {ok:true}`)
must PASS before the model dispatches, because these roles act through tool calls.
On fail, one backoff retry, then the ladder advances to the next configured fallback.

**The client's configured fallback chain is the backup** for every ladder. The `qc`
ladder must remain vision-capable throughout: every model the client configures for
`qc` must accept image input, because the role checks screenshots and DOM.

---

## 3. Hard Rules

**MiniMax M2 — BANNED everywhere.** MiniMax M2 is PURGED from every rung, table,
recommendation, and doc. The execution role uses the client's chosen model or their
configured default, advancing to the client's next configured fallback if the probe
fails. The M2 hyphenated slug form must never appear in
code or markdown; the CI step (section 4a) fails the build on any occurrence,
no exclusions.

**No named model is the only valid route.** Every role resolves to the model the
client selected, or the client's configured default model. Doctrine never
prescribes a specific model by name. A model id is always written with its
provider prefix (for example `provider/model-id`) so the route is unambiguous;
a bare, provider-less id is never a valid reference.

**No vendor rule.** There is NO rule against Anthropic / Claude models (Trevor order
2026-10-29). `assert_model_sovereignty` (`shared-utils/assert_model_sovereignty.py`, N35)
still blocks the free literal, a model missing from the client's inventory and a
modality mismatch, but `FORBIDDEN_PREFIXES` is empty and `model_router.py` has no
Anthropic guard. A client's own Anthropic model is routed like any other; nothing in
the update or repair path adds, strips or refuses one.

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

**(c) (retired)** The Anthropic model identifier scan was removed with the vendor rule
(Trevor order 2026-10-29).

**(d) Content-model slug without a provider prefix.** A `\bkimi\b` match
(case-insensitive) on a line that contains none of: `ollama/kimi`, `openrouter/kimi`,
`openrouter/moonshotai/kimi`, or `kimi-k2.6:cloud`. Valid qualified forms that pass:
ollama/kimi-k2.6:cloud (Tier 1), openrouter/moonshotai/kimi-k2.6 (Tier 2). This doc
is authored to remain clean against all four checks.

---

## 5. Enforcement Points

| Layer | File | What it enforces |
|---|---|---|
| Code (Skill 6) | `06-ghl-install-pages/tools/model_router.py` | Role-keyed resolution (client choice or configured default per role); tool-call probe gate on execution and qc; `THINKING_EFFORT=high` |
| Shared gate | `shared-utils/assert_model_sovereignty.py` | Per-slug block at dispatch-time — no free literal, inventory and modality check (N35); no vendor is blocked |
| CI | `.github/workflows/qc-static.yml` step "No banned model tokens..." | Banned token scan across code + markdown — checks (a)–(d) above; added in this branch |
| Offline self-test | `06-ghl-install-pages/tests/test_model_router.py` | Assertions on the role resolution: client choice and configured-default resolution order, probe-gate flags, an Anthropic-family default routed as configured, M2 absent |
| Fleet doctrine | `AGENTS.md` N35 (AF-MODEL-SOVEREIGNTY) | Universal cascade; modality gate; fleet-wide application |
