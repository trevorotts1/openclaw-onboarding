# S75-W04-U2 — Capability-aware configuration and account failure control

Finding D30 (P0/P1), spec sections 7.5 and 15.3. Builder: MiMo 2.6 Pro
(`openrouter/xiaomi/mimo-v2.6-pro`). Nothing merged or published; no
self-approval. The QC lane writes the verdict.

## What this is

One resolved capability manifest plus the control code that keeps model
configuration honest and account failures contained:

| Module | Contract |
|---|---|
| `capability_control/runtime_schema.py` | Whole-config schema validation (unknown key = rejected) and owned-section merge. Refuses compiled runtime bundles and cache files as write targets. |
| `capability_control/manifest.py` | `resolve_manifest`: one manifest from the installed runtime schema + authoritative provider catalog, reconciling selectable models, allowlists, provider entries, role bindings, scheduler jobs and session/UI cache versions. Caches carry source revision, fetched time and a supported refresh path. A role is verified only by a host-dispatch receipt; a label is never proof. |
| `capability_control/config_stage.py` | stage -> validate the entire resulting configuration -> atomic apply -> verified reload. An invalid proposal is rejected before activation with the prior healthy configuration intact; unrelated department models, credentials, aliases, heartbeat policies and user preferences survive unchanged. Failed reload rolls back to the previous usable configuration. |
| `capability_control/effort.py` | Honest effort representation. A provider with reasoning but no effort selector is described exactly that way; a UI ladder cannot create provider support; a generic runtime `thinking=max` log is never proof of a model-specific parameter; an unsupported required parameter is refused, never silently stripped. |
| `capability_control/failures.py` | Hard quota / credit / suspension / authorization failures classified distinctly from temporary throttling and transient service errors. Shared `AccountBreaker`: one actionable event per opening, queued launches suppressed, deterministic observation/report scheduling never blocked, retry-at from authoritative responses or an explicit bounded policy (never an invented short reset for a monthly cap). |
| `tools/capture_fixtures.py` | The supported refresh path for every fixture cache (source revision + fetched time stamped on each capture). |
| `tools/probe_host_dispatch.py` | Minimal live dispatch through the installed host to prove the chosen model (smallest non-destructive probe; key never printed or saved). |
| `tools/verify_manifest_with_probe.py` | Integration: resolves the manifest from the captured fixtures and binds the real host-dispatch receipt. |

## Evidence levels (spec 15.2)

- **Unit/regression** (`tests/`, 42 tests, offline, controlled fixtures):
  every acceptance row has a failable check. See `TESTS.txt`.
- **Live host dispatch** (`evidence/host-dispatch-openrouter_xiaomi_mimo-v2.6-pro.json`):
  HTTP 200 through the installed 9Router at `127.0.0.1:20128`, response model
  echo `xiaomi/mimo-v2.6-pro` (provider-local echo of the bound route
  `openrouter/xiaomi/mimo-v2.6-pro`), gateway request receipt
  `gen-1792660961-qt4v5MU8JUOsHnY8JqvE`, thinking block present with **no
  effort parameter sent** (honest reasoning-without-selector). The router's
  `requestDetails` table holds no row for this probe (its captured rows end
  2026-10-14) — stated, not papered over.
- **Live reconciliation** (`evidence/manifest-reconciliation.json`): the
  builder role is `verified_by_host_dispatch`; the qc role stays UNVERIFIED in
  this unit (W00-U1 `route-receipts.json` carries the GLM high-effort
  end-to-end proof). The live router combos carry 20 fabricated effort
  annotations, including `openrouter/xiaomi/mimo-v2.6-pro(max)` on a model
  whose authoritative catalog entry exposes reasoning with **no** effort
  selector — flagged `UNSUPPORTED_EFFORT_CLAIM`, never emitted as a claim.

## Acceptance mapping

1. *Schema-invalid proposals rejected before activation, prior healthy
   configuration intact, unrelated settings unchanged* —
   `tests/test_config_stage.py` (all 6 cases) + `tests/test_runtime_schema.py`.
2. *Manifest reconciles catalog, allowlist, provider entries and cache
   versions with actual host dispatch proving the chosen model* —
   `tests/test_manifest.py` + `evidence/manifest-reconciliation.json` +
   `evidence/host-dispatch-*.json`.
3. *Unsupported effort never fabricated* — `tests/test_effort.py` +
   `UNSUPPORTED_EFFORT_CLAIM` findings on the live combos.
4. *Hard-cap failures classified distinctly with one actionable breaker
   event* — `tests/test_failures.py` (classification, single event under a
   26-failure swarm, suppressed launches, deterministic scheduling continues,
   no invented short reset for a monthly cap).

## Integration points (for the landing lanes — not done here)

- New files land under `75-drama-song-ad-factory/scripts/core/capability_control/`
  in both distributions (999-setup and openclaw-onboarding), consumed by the
  model-selection work of S75-W04-U1 (`ai_models.py`/`ai_models.json`, owned by
  that unit) and the scheduler/keepalive reconciliation lanes.
- The staged-config writer replaces ad hoc edits to model settings; the
  failure classifier plugs into the dispatcher boundary so hard caps open the
  shared breaker instead of killing parallel work.
- Compiled runtime bundles (e.g. the 9Router `app/.next-cli-build` chunks) are
  never edited; the guard in `runtime_schema.py` enforces it.

## Provenance

Every fixture in `fixtures/` was captured 2026-10-22 by
`tools/capture_fixtures.py` and carries `source_revision`, `fetched_at` and
`refresh_path`. Re-running that script is the supported refresh. No secret
value is stored in any fixture (key names and counts only).
