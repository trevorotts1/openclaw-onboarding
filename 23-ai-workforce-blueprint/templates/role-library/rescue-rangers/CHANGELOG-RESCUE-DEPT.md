# Rescue Rangers Department — Build Log

Repo-side build formalizing Rescue Rangers as an **operator-only** department
(Topic 4 of the Graphics/Furnace/Context/Rescue spec). No live n8n / VPS / client /
GHL was touched — repo/branch only.

## v1.2 — three-tier rescue order + access inventory (2026-08-10, repo-side)

**The doctrine rewrite (kills the "page the Operator first" default):** every
Rescue Rangers document now states the BINDING three-tier rescue order plainly:
(1) **Instruct the client's agent (outcome b)** — the PRIMARY route for
coaching/how-to classes and client-account actions (OAuth dashboard steps, billing
top-up, owner confirmation); never a page; (2) **the rescue AI self-fixes
infrastructure on a REACHABLE box using our access** — the operator's `~/.ssh/config`
`rescue-*` alias for every fleet box (Mac-via-Cloudflare-tunnel, Hostinger VPS,
Contabo) plus the provider env var NAMES from `~/.openclaw/secrets/.env`
(Hostinger, Contabo, Cloudflare, GoHighLevel, OpenRouter, per-client
`CF_ACCESS_<CLIENT>_SVC_*`) — referenced by NAME ONLY, values live in the secrets
env, NEVER printed into a doc/ticket/transcript, credential existence checked
BEFORE escalating; (3) **page the Operator ONLY after tiers 1-2 ran** — with what
was tried and why — or on a one-way-door class (credential-ACTION / DNS / deletion /
model sovereignty) that pages on the class alone.

**Routing table (new):** credential-ACTION (rotate/regenerate/revoke) → Operator;
client-account-action (OAuth dashboard, billing top-up, owner confirmation) →
client-instruction, outcome (b); infrastructure failure on a reachable box →
self-fix by the rescue AI; everything else → coach the client's agent first, then
self-fix; box genuinely UNREACHABLE after the rescue AI's own SSH attempts →
Operator, with the attempts and evidence.

**Outcome contract made explicit everywhere:** every rescue ends as (a) solved,
(b) here is what you should do, or (c) here is the answer — delivered by the
client's own agent. Outcome (b) is a complete dispatch, never a silent drop; a
ticket whose remedy is a client-account action closes as (b) without any page.

**Files updated (10):** `director-of-rescue-rangers.md` (three-tier order in §3,
decision-logic table rewrite, §6 access inventory, SOP 9.4/9.5 rewrite, KPIs),
`diagnostician--rescue-rangers.md` (unreachable-box row now tries the `rescue-*`
SSH alias first; §3/§6/SOP 9.5 tier order), `structured-fix-operator--rescue-rangers.md`
(never-auto = pages on the class alone; client-account = outcome (b); self-fix via
access; §4 table + SOPs), `ticket-clerk--rescue-rangers.md` (§6 + `blocked`
vocabulary), `qc-postmortem-specialist--rescue-rangers.md` (§6 + outcome-contract
audit), `how-to-use-this-department.md` (new §2 doctrine block, role table, §3
step 4), `TOOLS.md` (access inventory section — names only), `sops/SOP-RR-01`
(triage cap-check + SOP 9.4 rewrite), `sops/SOP-RR-03` (aging hand-off), and
`sops/SOP-RR-04` (three-tier preamble + never-auto/client-account split). SOP-RR-02
and SOP-RR-05 were reviewed and needed no doctrine change. Content manifest
re-stamped via the canonical `hash-content-manifest.py` pipeline.

## v1.0 — department formalized (FIX 4-A … 4-F, repo-side)

**Roles (5):** `director-of-rescue-rangers` (Dispatcher), `diagnostician--rescue-rangers`,
`structured-fix-operator--rescue-rangers`, `ticket-clerk--rescue-rangers`,
`qc-postmortem-specialist--rescue-rangers`. All carry the OPERATOR-ONLY banner (no
intent triggers; never in a client's routing catalog).

**Durable ticket ledger (FIX 4-A, kills R1):** `scripts/rescue_ledger.py` — the sole
SQLite-WAL writer (system of record) replacing the volatile n8n `workflowStaticData`
queue + per-client 25/day counters. Schema (`tickets`, `exchanges`, `meta`) +
accessors (open/answer/resolve/set-status/aging/count-today/digest/stamp-cc), all
idempotent, single-writer, `--self-test` green. `scripts/migrate-rescue-staticdata.py`
folds a staticData export into the ledger (idempotent).

**Relay Brain nine-field validation (FIX 4-B, kills R2):** `scripts/relay_brain_validation.js`
enforces the full nine-field contract at the edge (was only `missing_message`),
never drops a distress call (reject-to-sender + post-to-operator flagged INCOMPLETE),
whitelists the two sanctioned short forms, and adds the outbound-only `status` return
branch (FIX 4-D, kills R4). Pure/dep-free; `--self-test` green.

**Command Center Kanban integration (FIX 4-C, kills R3+R6):** `scripts/rescue_cc_board.py`
— fail-soft board caller (`department_slug:"rescue-rangers"`), status→column mapping,
movement receipts, and the durable aging sweep. Boarding is a VIEW, never a gate.

**Onboarding stamping (FIX 4-E, kills R5):** `scripts/stamp-rescue-escalation-section.sh`
renders the AGENTS.md escalation section idempotently (marker-guarded).

**Scaffolding:** `how-to-use-this-department.md`, `connection-manifest.json`
(posture-only env keys), `TOOLS.md`, `RELAY-BRAIN-PATCH.md`, five dept SOPs
(`sops/SOP-RR-01…05`), and the runnable operator installer
`scripts/install-rescue-ledger.sh` (never root, arms nothing).

**Wiring:** registered in `templates/role-library/_index.json` (5 roles + the
`rescue-rangers` department + 5 SOPs, content-hash stamped via the canonical
`hash-content-manifest.py` pipeline). `skill-department-map.json` is intentionally
NOT modified — its `skills[]` array is 1:1 with numbered skill folders on disk, and
Rescue Rangers has no numbered folder (adding a phantom entry would break the
map↔disk coverage gate). Registering rescue-rangers as a live department is
sufficient to make it a valid `dept_owner`.

## DEFERRED live steps (operator action — NOT executed here)
1. n8n Relay Brain redeploy (nine-field + status branch) — pre-change export + staging.
2. VPS outbound-only status-poll return leg armed on live VPS boxes (batched roll).
3. `add-department.sh rescue-rangers` on the live Command Center (board column/topic).
4. Aging/SLA cron scheduled beside the CC stale-task sweep.
5. `stamp-rescue-escalation-section.sh` wired into install.sh (client role) for fresh boxes.
