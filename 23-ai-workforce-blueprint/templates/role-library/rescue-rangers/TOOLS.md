# Rescue Rangers — TOOLS

**Department:** rescue-rangers (operator-only)
**Runtime seat:** the existing `rescue-rangers` OpenClaw agent on the operator Mac.

This department did not invent its runtime — it FORMALIZES the ad-hoc rescue tooling
that has run for months into a governed department. This file is the canonical
inventory of the tools the department operates. Repo-side deliverables live under
`departments/rescue-rangers/scripts/`; the live transports live on the operator Mac
and cloud (documented here, run by the operator — see "DEFERRED live steps").

---

## Repo-side tools (in this department's `scripts/`)

| Tool | Purpose | Self-test |
|---|---|---|
| `rescue_ledger.py` | The SOLE durable ticket-state writer. SQLite (WAL) at `~/clawd/fleet-heartbeat/rescue/tickets.db`. Replaces the volatile n8n `workflowStaticData` queue + per-client 25/day counters (kills R1). Schema + accessors: `open`/`answer`/`resolve`/`set-status`/`aging`/`count-today`/`digest`/`stamp-cc`. | `python3 rescue_ledger.py --self-test` |
| `rescue_cc_board.py` | Fail-soft Command Center board caller. Puts every ticket on the department Kanban (`department_slug:"rescue-rangers"`) via `POST /api/tasks/ingest`, advances status, records movement receipts, and runs the aging sweep off the ledger (kills R3, R6). A board outage NEVER blocks a rescue. | `python3 rescue_cc_board.py --self-test` |
| `relay_brain_validation.js` | The Relay Brain edge-validation patch: enforces the full nine-field escalation contract (was only `missing_message`; kills R2) and implements the outbound-only `status` return-leg branch (kills R4). Pure/dep-free — drops into the n8n Code node AND runs under plain `node` for its self-test. | `node relay_brain_validation.js --self-test` |
| `migrate-rescue-staticdata.py` | One-shot IDEMPOTENT migration: n8n staticData export → SQLite ledger (the FIX 4-A migration leg). Tolerant of the export's exact shape (confirm against a real export before the live cutover). | `python3 migrate-rescue-staticdata.py --self-test` |
| `stamp-rescue-escalation-section.sh` | Renders `scripts/rescue-escalation-section.md.tpl` with a box's real tokens and appends it to that box's AGENTS.md iff the marker is absent (idempotent; kills R5 template drift). Runnable now; install.sh wiring is DEFERRED. | `bash stamp-rescue-escalation-section.sh --self-test` |
| `install-rescue-ledger.sh` | Installs the ledger + tools onto the operator Mac (state dir 0700, schema bootstrap, optional migration). Runs as the box user, NEVER root. Arms nothing, touches no live box. | (installer; prints the two DEFERRED live steps) |
| `verify.sh` | The department's failable OFFLINE drill battery — runs every tool's self-test, exits non-zero on the first failure. The green gate for the department code. | `bash verify.sh` |

## Live transports (operator Mac + cloud — run by the operator, documented here)

| Tool | Where | What it does |
|---|---|---|
| **n8n "Rescue Rangers Relay"** | `main.blackceoautomations.com` | Webhook → Auth Check → Relay Brain (routing + transport-buffer queue) → posts to Rescue Rangers HQ Telegram (Fixer topic) → return leg. The Relay Brain is patched by `relay_brain_validation.js`. |
| **`rescue-receiver.mjs`** | operator Mac `127.0.0.1:8799` (launchd), CF tunnel `rescue-gw.zerohumanworkforce.com/rescue` | Push transport: authenticated POST runs ONE turn of the rescue agent; tier routing; structured `remediate.sh` fixer (DRY-RUN default); posts the answer back to the relay. |
| **`rescue-rangers-poller.sh`** | operator Mac cron `*/10` | Pull transport (fallback): drains `{action:"pending"}`, runs one agent turn per ticket, posts answers back; idempotent. |
| **`rescue-receiver-watchdog.sh`** | operator Mac cron (every minute) | Health-checks :8799, kickstarts, bounded at MAX_RESTARTS=5 (anti-crash-loop), one deduped alarm to the Fixer topic. |

Both live transports write ticket state THROUGH `rescue_ledger.py` (the durable
system of record) and board via `rescue_cc_board.py` — that is the wiring this
department adds on top of the existing transports.

---

## DEFERRED live steps (operator action — NOT executed by this repo build)

1. **n8n Relay Brain redeploy** — paste `relay_brain_validation.js` into the Relay
   Brain Code node (nine-field enforcement + `status` branch), following the
   pre-change JSON export ritual + staging test. See `RELAY-BRAIN-PATCH.md`.
2. **VPS outbound-only status-poll return leg** — arm the client AGENTS.md
   `{action:"status", ticketId}` poll on live VPS boxes (batched fleet roll).
3. **Ledger install on the operator Mac** — `bash install-rescue-ledger.sh`
   (optionally `--migrate <staticData-export.json>`).

## Environment (posture-only — see `connection-manifest.json`)

`RESCUE_RANGERS_WEBHOOK_URL`, `RESCUE_RANGERS_WEBHOOK_SECRET` (fleet-wide, seeded at
onboarding), `RESCUE_PUSH_SECRET` (operator box only). Never print a secret value;
confirm SET, never echo. The ledger stores ticket TEXT + status, never a credential.

## Access inventory (the three-tier rescue order's tooling — names only, never values)

The rescue AI self-fixes reachable boxes with the operator's access. Everything here
is referenced by NAME ONLY — the values live in the operator secrets env, never in
any doc, ticket, or transcript:

- **Box access:** the operator's `~/.ssh/config` provides a `rescue-<firstname>-
  <lastname>` alias for every fleet box (Mac-via-Cloudflare-tunnel), plus
  `contabo-host` for Contabo VPS. `ssh <alias> 'command'` is the reachability check;
  `ssh <alias> 'bash -lc "…"'` is the login-shell form. Headless only — never a
  command that opens a browser (Cloudflare Access would hang on a login prompt).
- **Provider credentials (env var NAMES in `~/.openclaw/secrets/.env`):**
  `HOSTINGER_API_KEY` / `HOSTINGER_EMAIL` / `HOSTINGER_PASSWORD`,
  `CONTABO_CLIENT_ID` / `CONTABO_CLIENT_SECRET` / `CONTABO_API_USERNAME` /
  `CONTABO_API_PASSWORD`, `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` /
  `CLOUDFLARE_ZONE_ID` / `CLOUDFLARE_TUNNEL_TOKEN`, `GOHIGHLEVEL_API_KEY` /
  `GHL_AGENCY_PIT` / `GOHIGHLEVEL_LOCATION_ID`, `OPENROUTER_API_KEY`, and the
  per-client `CF_ACCESS_<CLIENT>_SVC_*` tokens (sourced automatically by the
  `rescue-*` ProxyCommand). Source the env to use them; confirm SET, never echo a
  value. Check the credential EXISTS before escalating — a missing credential is a
  finding, not a page.
- **Canonical doctrine refs:** `~/.openclaw/AGENTS.md` (fleet agent doctrine) and
  `~/.openclaw/workspace/TOOLS.md` (operator tooling). Three-tier order: (1)
  instruct the client's agent (outcome b), (2) rescue-AI self-fix via this access,
  (3) page the Operator only after 1-2 ran — with what was tried and why.
- **Never-auto (pages on the class alone):** credential-ACTION
  (rotate/regenerate/revoke), DNS/Cloudflare changes, data/file deletion, model or
  provider swap. One-way doors are the Operator's.
