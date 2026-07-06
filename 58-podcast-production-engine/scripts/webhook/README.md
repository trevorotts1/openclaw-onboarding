# Podcast Production Engine :: Inbound Webhook Layer

Deterministic, per-client inbound path for the Podcast Production Engine. Scope is
exactly the design in `project-prds/podcast-engine/design/webhook-design.md`: from
"an intake survey was submitted somewhere upstream" to "the client's podcast agent
has a durable, deduplicated job and has started Step 1." Everything downstream
belongs to the pipeline. Public hostname and ingress belong to the Cloudflare
design. No language model and no Model Context Protocol anywhere in this path; it
is pure, deterministic, stdlib-only Python plus one authenticated loopback HTTP
call to the platform's own webhooks action API.

## Live-verified schema finding (schema drift is real; this layer matches the box)

Verified against the INSTALLED gateway on the operator box, OpenClaw 2026.6.11
(`dist/extensions/webhooks/index.js`, `dist/.../secret-input`). The installed
contract DIFFERS from the design document's illustrative sketch, so this layer
follows the installed contract:

- Config path is `plugins.entries.webhooks.config.routes` (a MAP keyed by
  routeId), not `plugins.webhooks.routes` (a list with an `id` field).
- Route object is strict: `{ enabled?, path?, sessionKey(required),
  secret(required), controllerId?, description? }`. `path` defaults to
  `/plugins/webhooks/<routeId>`.
- `secret` is a plain string OR a SecretRef with EXACTLY three keys
  `{ source, provider, id }`, `source` in `{ env, file, exec }`. For `source: env`
  the runtime resolves `process.env[id]`, so `id` is the ENV VAR NAME (must match
  `^[A-Z][A-Z0-9_]{0,127}$`) and `provider` is the `"default"` alias.
- `create_flow` accepts `goal(req), status?, notifyPolicy?, currentStep?,
  stateJson?, waitJson?, controllerId?` and the platform ASSIGNS the `flowId`
  (no client-supplied flow id, no idempotencyKey). Consequence: dedup is the
  intake ledger's exclusive-create claim (authoritative), and the `job_key` rides
  in the flow's `stateJson` so `get_flow` / `find_latest_flow` can map it back.
- Flow mutations (`resume_flow`, `finish_flow`, `fail_flow`, `set_waiting`) require
  `expectedRevision`; a stale revision returns HTTP 409 `revision_conflict`.

The route template encodes this verified schema. Validate again on any box whose
gateway version differs before shipping there.

## Files

- `route-template.json5` : the per-client Webhooks plugin route config (verified
  schema, env SecretRef, per-client `<client-slug>` placeholders).
- `aliases.json` : data-driven alias + enum-normalization tables (onboarding
  extends a client's pipeline aliases here without a code change).
- `mapper.py` : deterministic meaning-based mapper (container flattening, exact +
  fuzzy alias resolution, value-shape validation, hard tenant check, required-field
  gate, unknown-extras retention).
- `job_key.py` : canonical submission builder + job key
  `pd-<contact_id>-<first16hex(sha256(canonical_submission))>`.
- `ledger.py` : intake ledger with an atomic exclusive-create claim, the Section
  3.3 dedup decision, quarantine path, and a 90-day retention sweep.
- `flow_client.py` : Webhooks plugin TaskFlow client + the 409 read-check-reapply
  helper (idempotent finish/fail/set-waiting under the revision contract).
- `intake_handler.py` : the deterministic orchestrator implementing the fast-ACK
  contract; ties mapper, job_key, ledger, and flow_client together.
- `run-selftests.sh` : runs every module's built-in `--self-test` (fail-closed).

## Wiring contract (how the deterministic handler runs given the real plugin)

Because the installed plugin drives TaskFlows and has no pre-processing hook, the
deterministic handler runs as the FIRST step of the flow, invoked as a single Bash
tool call (a deterministic decision, never a model reasoning step, never Model
Context Protocol):

1. The upstream sender (Convert and Flow workflow action, Make.com, or n8n) is
   configured at onboarding to POST to
   `/plugins/webhooks/podcast-intake-<client-slug>` with
   `Authorization: Bearer <secret>` and body
   `{"action":"create_flow","goal":"Podcast intake","status":"queued",
   "notifyPolicy":"silent","stateJson":{"engine":"podcast","raw_submission":{...survey...}}}`.
2. The route's `controllerId` points at the podcast engine controller runbook
   (SKILL.md, a sibling slice). Its first step writes `stateJson.raw_submission`
   to a file and runs
   `python3 scripts/webhook/intake_handler.py handle --payload <file> --mode in-flow --flow-id <flowId>`.
3. `intake_handler` maps, tenant-checks, computes the job key, claims the ledger
   (dedup), persists, and returns a fast ACK. On a fresh accept it advances the
   flow to Step 1; on a duplicate / needs_input / test / wrong-tenant delivery it
   closes (or parks) the plugin-created flow via the 409 guard, so no redelivery
   ever runs the pipeline twice.

`--mode trigger-flow` is the degraded/direct path (a sender that cannot wrap the
survey in an `action`): the handler itself calls `create_flow` + `run_task` with a
pointer-based task instruction (never the payload inlined). `--mode no-flow` is the
pure fast-ACK used by fixtures and the T1-T9 onboarding verification harness.

## Fast-ACK response vocabulary

The response means "durably recorded," not "produced." A webhook request is never
held open for episode production (minutes to hours), so the platform's 8-concurrent
budget stays irrelevant.

- `accepted` (200) : fresh job claimed; flow fired.
- `duplicate` (200) : identical redelivery; `delivery_count` incremented; nothing
  re-runs. A duplicate is a SUCCESS response on purpose, so well-behaved upstreams
  stop retrying.
- `accepted-incomplete` (200) : required field missing; ledger `needs_input`;
  operator alert names the missing fields; never guessed, never client-spammed.
- `quarantined` (200) : `location_id` did not match this client's configured
  Location ID; raw payload quarantined; operator alerted; NOTHING processed. This
  single hard check makes cross-client contamination structurally impossible.
- test-gated `accepted` (200) with ledger `test` : `_test:true` from the designated
  test contact; short-circuits after ingest validation; never touches Podbean,
  custom fields, or workflows.

## Dedup and idempotency

`job_key = pd-<contact_id>-<first16hex(sha256(canonical_submission))>`. The
canonical submission is built AFTER meaning-mapping from canonical fields only
(the Section 3.1 set), volatile transport fields excluded, so the same submission
via different upstreams hashes identically. An identical redelivery collides
(dedup fires); a genuinely new survey (any hashed answer changed) makes a new job,
which is correct for a weekly Personal Podcast. The ledger's exclusive-create claim
(`O_CREAT|O_EXCL`) settles same-second races: exactly one delivery claims, the
other is a duplicate.

## State, persistence, and silence

The ledger lives at `~/.openclaw/state/podcast-engine/intake-ledger/` (durable, not
`/tmp`). The record file (0600) carries only safe metadata; answer text (potential
PII) lives only in the `.payload.json` sibling (0600), so a dashboard read never
sees answers. The ledger state enum IS the dashboard/kanban vocabulary; this file
ledger is the webhook layer's atomic claim mechanism and `podcast_state.py` (a
sibling slice) keeps it in lockstep with the SQLite database that the dashboard
queries.

This layer emits ZERO client-facing messages. Operator alerts (needs_input, tenant
mismatch, 409 exhaustion, ledger corruption) are written to
`~/.openclaw/state/podcast-engine/operator-alerts/alerts.ndjson` (0600, labels and
identifiers only, never a secret) for `alert-dedup.py` to route to the founder
through the gateway. Nothing here sends Telegram or bypasses the gateway.

## Configuration (environment; values never printed)

- `PODCAST_INTAKE_HOOK_SECRET` : the route secret (SecretRef `id`). Verify SET,
  never echo. Signed test request returns 200, unsigned returns 401.
- `PODCAST_CLIENT_LOCATION_ID` : the client's configured Convert and Flow Location
  ID for the hard tenant check. Compared only, never printed.
- `PODCAST_TEST_CONTACT_ID` : the designated onboarding test contact that gates the
  `_test` flag.
- `PODCAST_INTAKE_ROUTE_ID` : the route id (`podcast-intake-<client-slug>`) for the
  flow client.
- `PODCAST_INTAKE_SESSION_KEY`, `PODCAST_INTAKE_CONTROLLER_ID` : session and
  controller ids for trigger-flow dispatch.
- `PODCAST_GATEWAY_URL` : loopback gateway base (default `http://127.0.0.1:18789`).
- `PODCAST_ENGINE_STATE_DIR` : overrides the ledger base dir (tests use a temp dir).

## Verify

Run `bash run-selftests.sh` (no network, no live gateway, no real `~/.openclaw`
state, no secrets). Each module also has a standalone `--self-test`.

## Sibling slices (not built here)

- `T1-T9` onboarding verification executable (through the real public Cloudflare
  URL) and the recorded-payload fixture suite are separate slices; this layer's
  modules are the units they exercise.
- `podcast_state.py` (SQLite sole writer) bridges this file ledger to the dashboard
  database.
- `alert-dedup.py` consumes the operator-alert log and owns the founder routing.
