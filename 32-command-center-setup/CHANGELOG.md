# Changelog — 32-command-center-setup

## v12.9.21 — 2026-06-30 — DB-path reconciliation, GHL preflight, orphan wiring, Done-Gate enforcement

- **P0 — One DB resolver everywhere.** Reconciled every `mission-control.db` lookup to
  `shared-utils/resolve_db.py` (Mac `~/projects/command-center` first, then VPS
  `/data/projects/command-center`), killing the VPS-only `/data/...` hardcodes that broke Mac:
  - `scripts/ingest-sop-library.py` — imports the shared resolver for its default DB.
  - `scripts/ingest-sop-library.sh` — Mac-first candidate list (the "Mac mini variant" now
    resolves on a Mac instead of `exit 2`); `$MISSION_CONTROL_DB` override.
  - `scripts/ingest-template-libraries.py` — `_DEFAULT_DB` now resolver-backed.
  - `scripts/materialize-dept-agents.sh` Phase 3 — replaced the wrong
    `$OC_ROOT/workspaces/command-center` candidate list (which silently skipped install-time
    QC/Devil's-Advocate/Healer rows) with the shared resolver + add-department.sh fallback, so
    the trio/quad rows land in the SAME db `add-department.sh` writes to.
  - `INSTALL.md` — canonical-DB note + clone target corrected to `~/projects/command-center`;
    removed the false "`~/projects` is stale" claim and the misdirecting symlink instruction.
- **P0 — QC port.** `qc-command-center-setup.sh` fallback `CC_PORT` 3000 → 4000 (the dashboard
  is `:4000` everywhere else), so the CC-running check targets the right port.
- **P1 — GHL credential preflight.** New `run-full-install.sh` Phase 6g: presence-only check of
  `GOHIGHLEVEL_API_KEY` (PIT) + `GOHIGHLEVEL_LOCATION_ID` in `secrets/.env`. Operator-facing,
  non-blocking, never silent, never messages the client; records the verdict to state.
- **P1 — Wired the orphans into `run-full-install.sh`** (both full and `--update-only`,
  WARN-only + state-recorded): Phase 6e `seed-dashboard-content.py` (Kanban renders cards),
  Phase 6f `generate-kpi-rollup.py` (CEO Performance Board `kpi-rollup.json`).
- **P1 — Done-Gate is now enforced in code.** New `scripts/move-task.py` state machine: the only
  sanctioned way to change `tasks.status`; refuses Review→Complete unless a Devil's Advocate
  sign-off (verdict=pass) exists; writes a `task_status_audit` row per transition. CORE_UPDATES.md
  updated to point the Done-Gate prose at the tool.
- **P1 — Canary heartbeat.** Shipped `HEARTBEAT.md` (the block `heartbeat-canary-probe.py`'s
  docstring references) with the grounded `openclaw cron create` command. (Cron registration is
  documented, not auto-executed from the orchestrator — deliberate, to avoid fleet-wide cron/token
  risk; canary alerts are already gated on `RESCUE_RANGERS_HELP_CHAT_ID`.)
- **P2 — crm_platform from interview + verify PIT before stamping.** `ingest-sop-library.py` now
  derives `crm_platform` from the company-config `connectedSystems` (mirrors
  `create_role_workspaces.py`: GoHighLevel default, HubSpot/Salesforce override; `$CRM_PLATFORM`
  wins), keeping INSERT OR IGNORE. When stamping GoHighLevel without the PIT present it emits a
  non-blocking operator NOTE.
- **P2 — Tunnel hardening.** `create-tunnel.sh`: transport-only webhook retry/backoff (never
  re-POSTs a received response — the webhook is non-idempotent) and writes the tunnel token to the
  canonical `~/.openclaw/secrets/.env` (chmod 600) in addition to the legacy `~/.openclaw/.env`.
- **P2 — Hygiene.** `generate-kpi-rollup.py` `datetime.utcnow()` → `datetime.now(timezone.utc)`;
  reconciled version markers (`.skill` 1.0.0 → 12.9.21 to match `skill-version.txt`).

Functionality preserved: every existing phase, the interview gate, memory-bloat `extraPaths=[]`,
strict dept count (no 17-default), atomic writes + timestamped backups are untouched. No client
chatter introduced. No first-party-LLM model recommendation exists in this skill (model scrub:
0 found, 0 introduced); GoHighLevel credential var names already canonical (`GOHIGHLEVEL_API_KEY` /
`GOHIGHLEVEL_LOCATION_ID`).
