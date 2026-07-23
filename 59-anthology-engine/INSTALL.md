# Anthology Engine -- INSTALL.md

## Per-client GHL (Convert and Flow) authentication architecture

This document describes the per-client authentication architecture for the Anthology
Engine. Every Anthology engine instance authenticates to its OWN client's Convert and
Flow (GoHighLevel) account using that CLIENT'S OWN private integration token (PIT)
and Location ID. This is a BINDING CONSTRAINT -- no shared, operator, fleet, or
default credential ever drives a client box.

---

## 1. Credential pair

Every client box requires exactly one Convert and Flow credential PAIR:

| Label | Example prefix | What it is |
|-------|---------------|------------|
| `CONVERT_AND_FLOW_PIT` | `pit-...` | The CLIENT's own private integration token (also aliased as `CONVERT_AND_FLOW_API_KEY`, `GOHIGHLEVEL_API_KEY`, `GOHIGHLEVEL_PIT`, `GHL_API_KEY`) |
| `CONVERT_AND_FLOW_LOCATION_ID` | hex string | The CLIENT's own GoHighLevel Location (sub-account) ID (also aliased as `GOHIGHLEVEL_LOCATION_ID`, `GHL_LOCATION_ID`) |

These are documented by LABEL only. No value is ever printed, committed, or revealed.

---

## 2. Resolution chain (live-process-first)

Credentials are resolved at install time by `scripts/caf_credential_gate.py` (W2.3).
The resolution order is:

1. **Live process env** (`os.environ`) -- checked first. A SET value here is ground
   truth; no store is consulted further for that key.
2. **Three client env stores**, in order:
   - `~/.openclaw/secrets/.env`
   - `~/.openclaw/workspace/.env`
   - `~/clawd/secrets/.env`
3. **Extended set** (opt-in via `--extended-stores`):
   - `~/.openclaw/.env`
   - `~/.openclaw/workspace/secrets/.env`
   - `~/clawd/.env`
   - `~/.openclaw/service-env/ai.openclaw.gateway.env`

**FAIL CLOSED.** If the PIT or Location ID cannot be resolved from any store,
provisioning STOPS (exit 2). The engine NEVER falls back to an operator-level,
shared, fleet, or default credential. There is no "default GHL API key."

---

## 3. Anti-commingling fingerprint

The credential gate computes an **unsalted sha256 fingerprint** of the resolved PIT
and Location values and checks them against four collision classes:

| Class | Trigger | Exit code |
|-------|---------|-----------|
| (a) Operator/shared/fleet collision | Resolved value is byte-identical to a value under an `OPERATOR_*`, `SHARED_*`, `FLEET_*`, `MASTER_*`, `GLOBAL_*`, `DEFAULT_*`, `OPS_*`, `INTERNAL_*`, `TREVOR_*`, `COMPANY_*`, or `ORG_*` label | 4 (VIOLATION) |
| (b) Foreign-client collision | Resolved value is byte-identical to a value under a `CLIENT_*`, `TENANT_*`, `ACCT_*`, `ACCOUNT_*`, `CUSTOMER_*`, or `SUBACCOUNT_*` label | 4 (VIOLATION) |
| (c) Expected-own fingerprint mismatch | An expected fingerprint was recorded from a prior clean provisioning and the resolved value does not match | 4 (VIOLATION) |
| (d) Denylisted fingerprint | The resolved fingerprint matches a known operator or other-client fingerprint (supplied via `ANTHOLOGY_COMMINGLE_DENY_FPS` or `--deny-fp`) | 4 (VIOLATION) |

A clean verdict means the credential pair belongs to THIS client -- not the
operator and not another client.

---

## 4. PIT scope check (AF-AE-PIT-SCOPE)

The client's OWN PIT must be able to READ pipelines in the client's OWN Convert and
Flow Location. This is checked at provision time by `scripts/anthology_registry.py`.
A token that cannot read pipelines STOPS setup with `AF-AE-PIT-SCOPE`. Pipeline
FIND-AND-BIND always uses the CLIENT's OWN PIT -- never an operator token with
cross-tenant scope.

---

## 5. Model provider keys (per-client, per-box)

Model provider keys are ALSO per-client and parallel the GHL credential pattern:

| Label | Provider |
|-------|----------|
| `OLLAMA_API_KEY` / `OLLAMA_CLOUD_API_KEY` | Ollama Cloud |
| `OPENROUTER_API_KEY` | OpenRouter |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` / `GOOGLE_AI_STUDIO_API_KEY` | Gemini |
| `MINIMAX_API_KEY` | MiniMax |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `KIMI_API_KEY` / `MOONSHOT_API_KEY` | Kimi / Moonshot |
| `KIE_API_KEY` | Kie.ai (image generation) |

These are resolved per-box by `preflight.sh` against the CLIENT's OWN `openclaw.json`
-- never a shared or operator API key. Anthropic-family model ids are denied at
resolution time and again at call time.

**JUDGE tier independence** is enforced at resolution time (AF-AE-JUDGE-INDEPENDENCE):
the JUDGE tier cannot resolve to the same provider+model as HEAVY-WRITER. A single-model
client must configure at least one additional model for independent QC.

---

## 6. What is NEVER done

- **NEVER use a shared/fleet/operator GHL API key** for any client operation.
  Every request to the Convert and Flow API must use the CLIENT's own PIT.
- **NEVER hardcode a credential value** (PIT, Location ID, provider key) in any
  runtime file. Credentials live only in the client's env stores.
- **NEVER commit a resolved credential** or a resolved `model-map.json` to the
  repository. The repo carries only templates with `<CLIENT_*>` placeholders.
- **NEVER fall back to a default credential** when the client-specific credential
  is absent. Absence must fail closed (exit 2).
- **NEVER fall back to local-SA (service-account) Drive delivery on a client box.**
  Client boxes use the n8n Drive credential broker. Only the operator's own box
  legitimately holds the Google SA key.
- **NEVER print, echo, or log a credential value.** Credentials are reported SET
  or NOT SET only, plus their fingerprint status.

---

## 7. Verification

Run the credential gate as a standalone check:

```bash
# Basic check (CnF pair only)
python3 59-anthology-engine/scripts/caf_credential_gate.py

# Full check including model provider keys and inline-exposure scan
python3 59-anthology-engine/scripts/caf_credential_gate.py --all

# With the n8n Drive broker presence check
python3 59-anthology-engine/scripts/caf_credential_gate.py --all --require-delivery

# Self-test (every failure mode, offline, no real credentials)
python3 59-anthology-engine/scripts/caf_credential_gate.py --self-test
```

The install bootstrap runs the credential resolution as part of its bootstrap:

```bash
bash 59-anthology-engine/install.sh
```

---

## 8. Key files

| File | Role |
|------|------|
| `scripts/caf_credential_gate.py` | Credential resolution, pairing proof, anti-commingling fingerprint, inline-exposure scan |
| `scripts/anthology_registry.py` | PIT scope probe, pipeline FIND-AND-BIND, field create-or-verify |
| `scripts/provision-anthology-client.sh` | Full per-client provisioning orchestrator (w2.6) |
| `config/model-map.template.json` | Tier map template with `<CLIENT_*>` placeholders (never committed resolved) |
| `preflight.sh` | Per-box model resolution from the CLIENT's own `openclaw.json` |
| `config/field-map.json` | Convert and Flow custom field keys (single source of truth) |
