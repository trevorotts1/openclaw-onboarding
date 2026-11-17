# Rescue Rangers Department — Build Log

Repo-side build formalizing Rescue Rangers as an **operator-only** department
(Topic 4 of the Graphics/Furnace/Context/Rescue spec). No live n8n / VPS / client /
GHL was touched — repo/branch only.

## [next] - 2026-11-13 - Rescue Rangers reply loop repair

**RRX-008. The instructions pointed the runner at retired and drill-only tools.**
THE DEFECT. The role files told the AI that runs Rescue Rangers to use tools that were retired, or that exist only for drills, so a live case could be routed into a tool that does nothing.
THE FIX. Eleven exact replacements across `director-of-rescue-rangers.md` (six), `sops/SOP-RR-01-triage-and-dispatch.md` (three), `how-to-use-this-department.md` (one) and `65-rescue-receiver/SKILL.md` (one) remove the retired tool names and point at the command that replaced them.
Test: `bash scripts/check-doc-currency-guards.sh`, run by the quality-check agent.

**RRX-009. The runner was told the operator's SSH aliases reach every box; they reach Mac boxes only.**
THE DEFECT. `director-of-rescue-rangers.md`, `how-to-use-this-department.md` and `TOOLS.md` all said the SSH aliases are the roster and cover every fleet box, while the loop-triage SOP records that Mac-only routing fails against VPS and Contabo boxes.
THE FIX. Four exact replacements say plainly that the aliases reach Mac boxes only and that the fleet access resolver is the roster, so "not in the aliases" is never read as "box unreachable".
Test: `bash scripts/check-doc-currency-guards.sh`, run by the quality-check agent.

**RRX-015. Triage was done by matching words in the problem text.**
THE DEFECT. A list of words (`credential`, `api key`, `403`, and so on) forced a tier, and nothing recorded whether a case would be fixed on the operator's side or handed to the client's agent.
THE FIX. New `scripts/rr_step_gate.py`, new `scripts/decision-rules.json` and new `sops/SOP-RR-06-decision-rule-and-step-gate.md`: no case moves a step without a real artifact, and the route is a recorded decision whose rule id and route must match the rule file or the gate refuses with exit 20.
Test: `tests/rescue/RRX-RUNNER/test_step_gate.sh`.

**RRX-020. The escalation block was a 110-line copy-and-paste shell program with traps.**
THE DEFECT. The stamped section printed a literal `<run: openclaw --version>` as its version, wrote its request to fixed paths under the system temporary directory, and put the secret on the `curl` command line.
THE FIX. The whole V3 marked block is replaced with the new section, which calls `rr_escalate.py send` and keeps the secret in a private header file; the V3 marker pair is unchanged, the rescue-identity line is the second line, and the self-verify block now checks the daily intake check.
Test: `tests/rescue/RR-030/test_escalation_tpl_snippets.sh`.

**RRX-024a. The loop-triage runbook named an old version of the escalation section.**
THE DEFECT. `universal-sops/SOP-RR-LOOP-TRIAGE.md` named the V2 marker while the template carries V3, and it pointed at a raw webhook post rather than the command that replaced it.
THE FIX. Two literal replacements: the section is named V3, and the escalation step reads `rr_escalate.py send`, with `--loop` putting the `LOOP:` prefix on the problem field; `universal-sops/_content-manifest.json` is restamped to match.
Test: `bash scripts/check-doc-currency-guards.sh`, run by the quality-check agent.

**RRX-024b. The stamper never refreshed a section that was already present.**
THE DEFECT. `stamp-rescue-escalation-section.sh` looked for the heading and did nothing when it found one, so a box kept whatever older section it already had.
THE FIX. The stamper is one embedded Python program: it renders the template, takes the rendered block and tail, finds the existing start and end lines at any version, replaces the block and the tail when they differ, is a no-op when they are equal, appends when neither marker nor heading exists, and refuses any other combination.
Test: `stamp-rescue-escalation-section.sh --self-test` (four cases inside the same file).

**RRX-028. The escalation template existed as two files and nothing kept them identical.**
THE DEFECT. `scripts/rescue-escalation-section.md.tpl` and the role-library copy carried the same content with nothing in the repository keeping them that way, so a later edit to one would ship to boxes as the other.
THE FIX. The two copies are byte-identical at this commit and a guard now compares them, exiting 1 with the exact mismatch message on stderr.
Test: `tests/rescue/RRX-ESC/test_template_copies_identical.sh`.

**RRX-104b. Four other role files and two SOPs repeated the retired tools.**
THE DEFECT. `diagnostician`, `structured-fix-operator`, `ticket-clerk`, `qc-postmortem-specialist`, `SOP-RR-04` and `SOP-RR-05` still described the retired ledger script, counted caps by hand, treated the board as the store, and named access paths that do not exist.
THE FIX. Rules 1 to 10 applied across the six files: the ledger is read from the RR-04 tables on the Command Center page and never written by hand (drill and migration tooling only), the cap count is `rr_cap_counters` recorded as case step 2, the board is a view, delivery is the outbox plus the two-minute poll, and access goes through the fleet access resolver.
Test: `bash scripts/check-doc-currency-guards.sh`, run by the quality-check agent.

These units belong to neither skill's changelog:

- **RRX-046 — the agent-map tool** (`scripts/reconcile-rr-agent-map.sh`): a write run with no API key now exits 2 instead of reporting success, the write verdict comes from the Python exit code instead of a grep on a printed word, and the failure lines name the box whose write failed instead of the last box of the probe loop. Test: `tests/rescue/RRX-MAP/test_reconcile_truth.sh`.
- **RRX-100 — the root `AGENTS.md`**: the second, older set of escalation instructions that contradicted the stamped section is replaced by a short pointer to the stamped section, keeping the three outcomes and the "never leave the end user in the dark" line. Test: `tests/rescue/RRX-ROOT/test_root_agents_rescue.sh`.
- **RRX-105 — `install.sh`**: `_shared_write_ocjson` now leaves an unreadable or malformed `openclaw.json` byte-identical, warns on stderr and exits 3 instead of rewriting the file with an almost empty one; writes go temp, fsync, chmod and rename, and an already-set value is a no-op. Test: `tests/rescue/RRX-INSTALL/test_shared_write_ocjson.sh`.
- **RRX-121 — `install.sh`**: a fresh install now registers the receiver's poll job and the daily check at install time, after the podcast wiring block and inside Step 5, instead of copying the receiver and leaving it unscheduled. Test: `tests/rescue/RRX-INSTALL/test_install_wires_rescue.sh`.
- **RRX-123 — `rr-triage.sh`**: step 6 reads the log with python3 and reports UNDETERMINED when python3 is missing or the log is unreadable, instead of reading either as CLEAN and printing two zeros. Test: `tests/rescue/RRX-TRIAGE/test_step6_log_read.sh`.

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
