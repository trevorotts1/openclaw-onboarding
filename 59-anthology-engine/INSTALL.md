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
| `ANTHOLOGY_GATE_TOKEN_SECRET` | hex string | Per-client 64-char hex HMAC secret for minting and verifying scoped participant gate tokens/PINs (resolved from `~/.openclaw/secrets/secrets.env` by `caf_credential_gate.py`; gate_engine.py resolves it via live-process-env first) |

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

## 8. Airtable authoritative ledger (ANTHOLOGY_STATE_BASE_ID)

The Anthology Engine writes its durable state to an **Airtable base** (the
AUTHORITATIVE ledger -- SPEC Section 7.2 / 7.4) with a local SQLite mirror for
fast read paths and crash recovery. The Airtable base is ONE per deployment,
provisioned by the operator.

### Credential

| Label | What it is |
|-------|------------|
| `ANTHOLOGY_STATE_BASE_ID` | The Airtable base ID (e.g. `appXXXXXXXXXXXXXX`) |

### Airtable API key resolution (alias chain, live-process-first)

The Airtable personal access token or API key that authenticates to the base is
resolved from the first present, non-empty value among these labels, in order:

1. `ANTHOLOGY_STATE_AIRTABLE_KEY` -- dedicated per-engine label (preferred)
2. `AIRTABLE_API_KEY` -- conventional key
3. `AIRTABLE_TOKEN` -- token-style key
4. `AIRTABLE_PAT` -- personal access token

The values are resolved by `_env_first()` in `scripts/anthology_state.py` and
are **never printed** (reported SET / NOT SET only).

### Mirror-only fallback

When `ANTHOLOGY_STATE_BASE_ID` is NOT set (or no Airtable credential resolves
from the alias chain), the ledger runs in **mirror-only** mode: all writes
commit to the local SQLite mirror, no base operations are attempted, and the
engine exits 0 with an operator note. This is the default for an
un-provisioned box or a unit test.

An operator who never provisions the Airtable base will see the engine run
successfully but all state will be local-only (no multi-box reconciliation,
no base-wins conflict resolution).

### Recommended per-client env store

```
# In the client's env store (e.g. ~/.openclaw/secrets/.env):
ANTHOLOGY_STATE_BASE_ID=appXXXXXXXXXXXXXX
ANTHOLOGY_STATE_AIRTABLE_KEY=pat...    # or one of the aliases above
```

---

## 9. Hash-pin enforcement (ENGINE-PIN.sha256)

The Anthology Engine entry enforces a content-hash pin at Gate 3 (AF-AE-HASH-PIN).
The pin locks six enforcement candidates (the entry script, the manifest, and four
guard scripts in `scripts/`). When `ENGINE-PIN.sha256` is present the gate is
fail-closed: any mismatch exits 7. Without the pin file the hash is recorded but
not enforced.

### Stamping the pin

After all guard scripts land, stamp the pin with verify.sh:

```bash
bash 59-anthology-engine/verify.sh stamp-pin
```

This computes the sha256 of the six enforcement candidates in their canonical order
and writes `ENGINE-PIN.sha256`. Run `--plan` afterward to confirm:

```bash
bash 59-anthology-engine/anthology-engine-entry.sh --plan
# Should print: "OK: enforcement hash matches the pinned head"
```

### Updating the pin

When any enforcement candidate changes, re-stamp the pin:

```bash
bash 59-anthology-engine/verify.sh stamp-pin
```

The pin file must be committed alongside the enforcement candidates it covers.

## 10. Key files

| File | Role |
|------|------|
| `scripts/caf_credential_gate.py` | Credential resolution, pairing proof, anti-commingling fingerprint, inline-exposure scan |
| `scripts/anthology_registry.py` | PIT scope probe, pipeline FIND-AND-BIND, field create-or-verify |
| `scripts/provision-anthology-client.sh` | Full per-client provisioning orchestrator (w2.6) |
| `config/model-map.template.json` | Tier map template with `<CLIENT_*>` placeholders (never committed resolved) |
| `preflight.sh` | Per-box model resolution from the CLIENT's own `openclaw.json` |
| `config/field-map.json` | Convert and Flow custom field keys (single source of truth) |

## 11. Environment variables

Every engine variable is resolved env-first BY LABEL; values are never printed by any
script (SET / NOT SET only). "Absent" behavior below is the exact fail-soft contract.

### State layout

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `ANTHOLOGY_STATE_DIR` | Overrides the engine state directory (the SQLite ledger, gate nonce DB, and `runs/` tree) for `anthology_state.py`, `gate_engine.py`, `nudge_send.py`, `hold_queue.py`, the end-to-end self-test harness, and every sibling that resolves a state path. Highest-priority override, ahead of `--state-dir` fallbacks in some CLIs and always ahead of the data-dir default. | Falls back to `$OPENCLAW_DATA_DIR/anthology-engine/state`, then to `~/.anthology-engine/state`. Nothing fails; the state just lives at the default location. |
| `OPENCLAW_DATA_DIR` | The OpenClaw data root used as the second-level base for the engine state directory (`$OPENCLAW_DATA_DIR/anthology-engine/state`). | Skipped; resolution drops to `~/.anthology-engine/state` under the node user home. |

### Nudge delivery

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `NUDGE_DELIVERY_CMD` | Space-split argv template for the process that delivers gate nudges (Skill 50 email-engine or the gateway notification path). Supports `{recipient}` and `{subject}` placeholders; the body arrives on stdin. Config slots (`nudge_delivery_cmd`) win over this env value. | No delivery path resolves -> nudge_send exits 3 (`no_delivery_path`); it NEVER sends to a literal recipient or silently succeeds. |

### Smoke-test / cost metering

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `MINIMAX_API_HOST` | Regional MiniMax API host override for balance probing (e.g. `https://api.minimax.io`). Must be on the pinned allowlist; an off-allowlist host is ignored. | Both pinned hosts are tried in order: global (`api.minimax.io`) first, China regional (`api.minimaxi.com`) second, bounded retry, still zero-cost. |
| `ANTHOLOGY_COST_BUDGETS` | Path to a per-box budget config JSON (`type_ceilings`, `global_ceiling`, `prices`) consumed by `anthology-cost-ledger.py`; wins over the embedded `config/cost-budgets.json`. | The skill's own `cost-budgets.json` is used if present; otherwise the embedded defaults apply (fail-soft, never raises). |
| `ANTHOLOGY_COST_CEILING_TOKENS` | Integer global token ceiling override applied after any budget config loads. A non-integer value logs a WARN and is ignored. | The ceiling comes from the loaded budget config or its default; metering still runs. |

### Daily-tick arg overrides (JSON list of extra CLI args)

All three follow the same convention: a JSON array string of extra CLI args appended
to the respective subcommand, e.g. `ANTHOLOGY_HOLD_QUEUE_AGE_ARGS='["--json"]'`.

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `ANTHOLOGY_HOLD_QUEUE_AGE_ARGS` | Extra args for the hold-queue age tick (`hold_queue.py tick`) shelled by the daily smoke test. | The smoke test invokes `tick` with its default args. |
| `ANTHOLOGY_ALERT_ARGS` | Extra args for `alert-dedup.py` when the daily tick fires the ONE deduped founder Telegram alert. Supports `{payload}` and `{key}` placeholders substituted with the written record path and dedup key. | The documented default invocation contract is used (`--source/--dedup-key/--summary/--payload-file`). |
| `ANTHOLOGY_STALE_SWEEP_ARGS` | Extra args for the read-only stale-cursor sweep (`anthology_state.py stale-cursors`), e.g. `'["--default-hours","12"]'` (E8 detection: crashed/hung stage runners). | Default thresholds apply (24h machine cursors; 168h group-wait cursors). |

### Secrets and credentials (labels only; values never printed)

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `ANTHOLOGY_PROCESS_CERT_SECRET` | HMAC secret for the signed S8 process certificate (alias `ANTHOLOGY_CERT_SECRET` also accepted). Signs `content_sha256` so a certificate can be re-verified independently. | Certificates issue UNSIGNED (fail-soft): `signed:false` with a note; delivery is never blocked on signing. A signed certificate verified on a box without the secret reports ok=True with reason `UNVERIFIED (no secret)` plus a stderr warning -- content hash still binds the identity core. |
| `ANTHOLOGY_INTAKE_HOOK_SECRET` | Shared secret carried in the Authorization header of intake webhook calls; also minted into the registry custom value at provisioning. | Intake hook verification refuses unsigned/mismatched calls; snapshot provisioning records the custom value as SKIPPED until the secret is exported (step 7 of install), then re-run. |
| `ANTHOLOGY_GHL_FIREBASE_API_KEY` | Firebase Web API key for the Convert and Flow (GHL) internal identity rail token exchange (`securetoken.googleapis.com/v1/token`). Aliases: `GOHIGHLEVEL_FIREBASE_API_KEY`. | Internal-rail calls that need a fresh Firebase token cannot mint one; affected probes report the label NOT SET and skip/fail loudly per their contracts. |
| `ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN` | Long-lived refresh token exchanged (with the API key above) for short-lived internal-rail ID tokens. Aliases: `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`, `GHL_FIREBASE_REFRESH_TOKEN`. | Same as above: no token exchange possible; scripts resolve SET/NOT SET and degrade per-script (never print anything). |
| `KIE_API_KEY` | Kie.ai credential for live cover renders (S7) and the zero-cost credit pre-flight probe. Resolved BY LABEL from the client env stores; the per-box label may differ via model-map `<CLIENT_KIE_KEY_LABEL>`. | S7 renders HELD (exit 3, `credential_not_set`); the structural cover proofs stand and no paid generation is attempted. |

### Public hostname

| Variable | Purpose | When absent |
|----------|---------|-------------|
| `ANTHOLOGY_PUBLIC_HOSTNAME` | This box's public hostname for building absolute webhook URLs (intake T-battery, snapshot custom values). Aliases: `PUBLIC_HOSTNAME`, `OPENCLAW_PUBLIC_HOSTNAME`. CLI `--public-hostname` wins over all three. | Snapshot provisioning marks `anthology_webhook_url` SKIPPED with the exact remediation hint; relative URLs stay relative. |

