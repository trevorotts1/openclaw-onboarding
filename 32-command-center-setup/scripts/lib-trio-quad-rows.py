"""
lib-trio-quad-rows.py -- Reusable, idempotent trio/quad DB-row inserter.

Extracted from add-department.sh blocks 2b/2c/2d/2e.
Provides ensure_trio_quad_rows() which inserts the four per-department
sub-agent rows (qc, deep-research, devils-advocate, healer) if they do
not already exist.

Role-type values are the canonical lowercase tokens:
  qc | deep-research | devils-advocate | healer

Usage:
  from lib_trio_quad_rows import ensure_trio_quad_rows
  import sqlite3
  db = sqlite3.connect("mission-control.db")
  counts = ensure_trio_quad_rows(db, ws_id, dept_name, dept_slug, head_agent_id)
  db.commit()
  # counts is a dict: {"qc": 0|1, "deep-research": 0|1, "devils-advocate": 0|1, "healer": 0|1}
  # value is 1 if a new row was inserted, 0 if it already existed (idempotent).
"""

import secrets
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_agent_cols(db) -> list:
    """Return the column names for the agents table."""
    cur = db.execute("PRAGMA table_info(agents)")
    return [row[1] for row in cur.fetchall()]


def _row_exists(db, workspace_id: str, role_type: str) -> bool:
    """Return True if a row with this workspace_id + role_type already exists."""
    cur = db.execute(
        "SELECT id FROM agents WHERE workspace_id=? AND role_type=?",
        (workspace_id, role_type),
    )
    return cur.fetchone() is not None


def _insert_agent(db, ag_cols: list, ag_data: dict) -> None:
    insert_cols = [c for c in ag_data if c in ag_cols]
    sql = (
        "INSERT INTO agents ("
        + ",".join(insert_cols)
        + ") VALUES ("
        + ",".join("?" * len(insert_cols))
        + ")"
    )
    db.execute(sql, [ag_data[c] for c in insert_cols])


def ensure_trio_quad_rows(
    db,
    workspace_id: str,
    dept_name: str,
    dept_slug: str,
    head_agent_id: str,
) -> dict:
    """
    Ensure the four trio/quad sub-agent rows exist for the given department
    workspace.  Inserts only the rows that are missing (idempotent).

    Parameters
    ----------
    db           : open sqlite3 connection (caller commits)
    workspace_id : the workspace_id foreign key (matches workspaces.id)
    dept_name    : human-readable department name, e.g. "Marketing"
    dept_slug    : lowercase slug, e.g. "marketing"
    head_agent_id: the department-head agent's id (not currently FK'd but
                   kept for audit; pass empty string if unknown)

    Returns
    -------
    dict with keys "qc", "deep-research", "devils-advocate", "healer";
    value 1 = row was inserted now, 0 = row already existed.
    """
    ag_cols = _get_agent_cols(db)
    NOW = _now_iso()
    counts = {}

    # ---- 2b. QC specialist -------------------------------------------------
    role_type = "qc"
    if _row_exists(db, workspace_id, role_type):
        counts[role_type] = 0
    else:
        qc_agent_id = secrets.token_hex(8)
        qc_name = f"QC Specialist -- {dept_name}"
        qc_data = {
            "id": qc_agent_id,
            "workspace_id": workspace_id,
            "name": qc_name,
            "role": "QC Specialist",
            "role_type": role_type,
            "persona": f"qc-specialist-{dept_slug}",
            "description": (
                f"Quality control gate for the {dept_name} department. "
                f"Reviews all deliverables before sign-off."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "\U0001f50d",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        _insert_agent(db, ag_cols, qc_data)
        print(f"  + agent (QC)       {qc_agent_id}  ({qc_name})")
        counts[role_type] = 1

    # ---- 2c. Deep Research specialist --------------------------------------
    role_type = "deep-research"
    if _row_exists(db, workspace_id, role_type):
        counts[role_type] = 0
    else:
        research_agent_id = secrets.token_hex(8)
        research_name = f"Deep Research Specialist -- {dept_name}"
        research_data = {
            "id": research_agent_id,
            "workspace_id": workspace_id,
            "name": research_name,
            "role": "Deep Research Specialist",
            "role_type": role_type,
            "persona": f"deep-research-specialist-{dept_slug}",
            "description": (
                f"Deep research intelligence engine for the {dept_name} department. "
                f"Provides Tier-1-cited research (McKinsey, HBR, IBISWorld, Statista) "
                f"for all {dept_name.lower()} decisions."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "\U0001f52c",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        _insert_agent(db, ag_cols, research_data)
        print(f"  + agent (Research) {research_agent_id}  ({research_name})")
        counts[role_type] = 1

    # ---- 2d. Devils Advocate -----------------------------------------------
    role_type = "devils-advocate"
    if _row_exists(db, workspace_id, role_type):
        counts[role_type] = 0
    else:
        da_agent_id = secrets.token_hex(8)
        da_name = f"Devil's Advocate -- {dept_name}"
        da_data = {
            "id": da_agent_id,
            "workspace_id": workspace_id,
            "name": da_name,
            "role": "Devil's Advocate",
            "role_type": role_type,
            "persona": f"devils-advocate-{dept_slug}",
            "description": (
                f"Internal challenge mechanism for the {dept_name} department. "
                f"Auto-created. NEVER surfaced to the client. Surfaces blind "
                f"spots in high-stakes decisions before they cause real-world damage."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        _insert_agent(db, ag_cols, da_data)
        print(f"  + agent (DA)       {da_agent_id}  ({da_name}) [INTERNAL -- never shown to client]")
        counts[role_type] = 1

    # ---- 2e. Healer --------------------------------------------------------
    # role_type MUST be the literal "healer", NEVER "qc".
    # Heartbeat OFF: materialized Healer is dormant (zero standing token burn)
    # until a trigger fires. Cadence is DISABLED by the scaffolder.
    # On-demand triggers only: watchdog 2nd-consecutive-stall handoff,
    # QC loop-4 escalation, Phase-4 failCode event, operator bug report.
    role_type = "healer"
    if _row_exists(db, workspace_id, role_type):
        counts[role_type] = 0
    else:
        healer_agent_id = secrets.token_hex(8)
        healer_name = f"Healer -- {dept_name}"
        healer_data = {
            "id": healer_agent_id,
            "workspace_id": workspace_id,
            "name": healer_name,
            "role": "Healer",
            "role_type": role_type,
            "persona": f"healer-{dept_slug}",
            "description": (
                f"Department immune system for the {dept_name} department. "
                f"Receives watchdog stall handoffs, QC loop-4 escalations, "
                f"and API failCode events. Diagnoses root cause, fixes the run, "
                f"and patches the SOP so the same failure never recurs."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "\U0001fa79",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        _insert_agent(db, ag_cols, healer_data)
        print(f"  + agent (Healer)   {healer_agent_id}  ({healer_name})")
        counts[role_type] = 1

    return counts
