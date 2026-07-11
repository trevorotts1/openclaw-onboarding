# Rescue Rangers Department — Build Log

Repo-side build formalizing Rescue Rangers as an **operator-only** department
(Topic 4 of the Graphics/Furnace/Context/Rescue spec). No live n8n / VPS / client /
GHL was touched — repo/branch only.

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
