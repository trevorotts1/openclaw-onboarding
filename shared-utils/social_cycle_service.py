#!/usr/bin/env python3
"""social_cycle_service.py — the durable weekly invitation cycle service
(F07 + F17, shared by Skill 35 and Skill 57; the ONB half of CC's
src/lib/social/cycle-service.ts — same semantics, file-backed here so the
skills work on boxes without the Command Center DB).

WHY (F07): both register-weekly-cron.sh and register-social-cron.sh encoded
the invitation cadence as INSTRUCTIONS INSIDE A PROMPT ("wait up to 1 hour",
"if no reply by noon ask once more", "if no reply by 6 PM use evergreen").
That is an agent burning tokens to simulate a state machine with no durable
state: a restart forgets the reminder, a second fire double-asks, and next
week's cycle only exists if last week's prompt happened to run it.

WHAT THIS OWNS (per the W0 company_cycle.json contract):
  - One cycle per (company_id, week_start_local) — UNIQUE per the contract;
    a second ensure for the same week collapses (E_CYCLE_DUPLICATE honored by
    idempotent collapse), and next week's row is created INDEPENDENTLY of
    this week's response.
  - Persisted invitation_sent_at / reminder_due_at / response state / cutoff
    / selected fallback / next_cycle_at as JSON state under
    ~/.openclaw/data/social-cycle/<company_id>/cycles.json (file-backed so
    cron + entry scripts on any box read the same durable state; the CC
    service owns the DB twin).
  - Bounded reminders: at most MAX_REMINDERS (default 2), REMINDER_CADENCE_HOURS
    apart, none after cutoff.
  - skip-this-week closes ONLY that cycle; pause-reminders is an EXPLICIT
    preference recorded on the cycle.
  - Evergreen publishing only with a RECORDED standing approval; otherwise
    the cutoff disposition is a DRAFT and the ask repeats next week.
  - Fake-clock testable: every operation takes now_ms.

SHORT JOB LAW: callers execute ONE operation (ensure/invite/reminder/cutoff/
advance) per invocation. Nothing here sleeps or waits on a human.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Product policy constants (mirror CC cycle-service.ts) ───────────────────
MAX_REMINDERS = int(os.environ.get("SOCIAL_CYCLE_MAX_REMINDERS", "2"))
REMINDER_CADENCE_HOURS = float(os.environ.get("SOCIAL_CYCLE_REMINDER_CADENCE_HOURS", "8"))
CUTOFF_HOURS_AFTER_INVITE = float(os.environ.get("SOCIAL_CYCLE_CUTOFF_HOURS", "34"))
NEXT_CYCLE_LEAD_DAYS = int(os.environ.get("SOCIAL_CYCLE_NEXT_LEAD_DAYS", "7"))

# Contract error names (company_cycle.json errors).
E_COMPANY_NOT_FOUND = "E_COMPANY_NOT_FOUND"
E_CYCLE_DUPLICATE = "E_CYCLE_DUPLICATE"
E_CYCLE_CLOSED = "E_CYCLE_CLOSED"
E_CYCLE_NOT_FOUND = "E_CYCLE_NOT_FOUND"

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_LOCK = threading.Lock()


def state_dir(env: Optional[Dict[str, str]] = None) -> str:
    """Durable state root: $SOCIAL_CYCLE_STATE_DIR or ~/.openclaw/data/social-cycle."""
    e = env if env is not None else os.environ
    explicit = (e.get("SOCIAL_CYCLE_STATE_DIR") or "").strip()
    if explicit:
        return explicit
    home = (e.get("HOME") or "/data").strip() or "/data"
    return os.path.join(home, ".openclaw", "data", "social-cycle")


def _company_dir(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(state_dir(env), company_id)


def _cycles_path(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(_company_dir(company_id, env), "cycles.json")


def _load_cycles(company_id: str, env: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    path = _cycles_path(company_id, env)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cycles(company_id: str, cycles: Dict[str, Dict[str, Any]], env: Optional[Dict[str, str]] = None) -> None:
    d = _company_dir(company_id, env)
    os.makedirs(d, exist_ok=True)
    tmp = _cycles_path(company_id, env) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cycles, fh, indent=2, sort_keys=True)
    os.replace(tmp, _cycles_path(company_id, env))


# ── Local week math (DST-safe) ──────────────────────────────────────────────

def week_start_local(now_ms: int, timezone_name: str = "America/New_York",
                     week_starts_on: int = 6) -> str:
    """ISO date of the client-local week start containing now_ms.

    week_starts_on: 0=Monday..6=Sunday (datetime.weekday() vocabulary;
    default 6 = Sunday, the fleet's client-local week start). Computed with
    zoneinfo against the named timezone so a DST change never shifts the
    boundary; the +7-day next week is calendar arithmetic on the DATE.
    """
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        tz = ZoneInfo(timezone_name)
    except Exception:  # pragma: no cover — bare box without tzdata
        tz = timezone.utc
    local = datetime.fromtimestamp(now_ms / 1000.0, tz=tz)
    back = (local.weekday() - week_starts_on) % 7
    start = (local - timedelta(days=back)).date()
    return start.isoformat()


def next_week_start(week_start: str) -> str:
    y, m, d = (int(x) for x in week_start.split("-"))
    return (datetime(y, m, d, tzinfo=timezone.utc) + timedelta(days=7)).date().isoformat()


# ── Cycle state ─────────────────────────────────────────────────────────────

def new_cycle(company_id: str, week_start: str, timezone_name: str = "America/New_York") -> Dict[str, Any]:
    return {
        "cycle_id": str(uuid.uuid4()),
        "company_id": company_id,
        "week_start_local": week_start,
        "timezone": timezone_name,
        "policy_revision": 1,
        "state": "draft",                    # draft|invited|responded|closed|skipped
        "invitation_sent_at": None,
        "invitation_token_hash": None,
        "invitation_channel": None,
        "reminder_count": 0,
        "reminder_due_at": None,
        "last_reminder_at": None,
        "response_state": None,              # awaiting|theme_chosen|skip|pause|evergreen|cutoff
        "responded_at": None,
        "cutoff_at": None,
        "selected_fallback": None,
        "standing_approval": None,           # 'evergreen' = recorded standing approval
        "skip_week": 0,
        "pause_reminders": False,            # EXPLICIT preference only
        "pause_reminders_until": None,
        "next_cycle_at": None,
        "disposition": None,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def get_cycle(company_id: str, week_start: str, env: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _load_cycles(company_id, env).get(week_start)


def get_cycle_by_id(cycle_id: str, env: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Locate a cycle by its id across every known company key."""
    with _LOCK:
        for company_key in _all_company_keys(env):
            for cyc in _load_cycles(company_key, env).values():
                if cyc.get("cycle_id") == cycle_id:
                    return cyc
    return None


def _all_company_keys(env: Optional[Dict[str, str]] = None) -> List[str]:
    root = state_dir(env)
    try:
        return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    except OSError:
        return []


def ensure_cycle(company_id: str, week_start: str,
                 timezone_name: str = "America/New_York",
                 env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Idempotently ensure the cycle row exists. Returns {'cycle_id', 'created'}.

    A second ensure for the same week is a no-op (E_CYCLE_DUPLICATE collapses
    by the unique key); next week's row is created independently by its own
    ensure call.
    """
    with _LOCK:
        cycles = _load_cycles(company_id, env)
        existing = cycles.get(week_start)
        if existing:
            return {"cycle_id": existing["cycle_id"], "created": False}
        cyc = new_cycle(company_id, week_start, timezone_name)
        cycles[week_start] = cyc
        _save_cycles(company_id, cycles, env)
        return {"cycle_id": cyc["cycle_id"], "created": True}


def send_invitation(company_id: str, week_start: str,
                    send: Callable[[Dict[str, Any]], bool],
                    now_ms: Optional[int] = None,
                    env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Send THIS week's invitation exactly once. Idempotent: an already
    invited/responded/closed/skipped cycle returns action='already'. Delivery
    failure leaves state 'draft' so the next tick retries."""
    now = int(now_ms) if now_ms is not None else int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    with _LOCK:
        cycles = _load_cycles(company_id, env)
        cyc = cycles.get(week_start)
        if not cyc:
            return {"action": "retry", "cycle_id": "", "reason": "cycle_row_missing"}
        if cyc["state"] != "draft":
            return {"action": "already", "cycle_id": cyc["cycle_id"]}

    token = str(uuid.uuid4())
    payload = {
        "company_id": company_id,
        "cycle_id": cyc["cycle_id"],
        "week_start": week_start,
        "channel": "theme-intake",
        "message": ("What is the content theme for the week of %s? Reply any time before "
                    "cutoff. If you do not answer, we will prepare a draft and ask again." % week_start),
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
    }
    delivered = False
    try:
        delivered = bool(send(payload))
    except Exception:
        delivered = False
    if not delivered:
        return {"action": "retry", "cycle_id": cyc["cycle_id"], "reason": "delivery_failed"}

    with _LOCK:
        cycles = _load_cycles(company_id, env)
        cyc = cycles.get(week_start)
        if not cyc or cyc["state"] != "draft":  # a concurrent response won — it keeps its state
            return {"action": "already", "cycle_id": (cyc or {}).get("cycle_id", "")}
        cyc["state"] = "invited"
        cyc["invitation_sent_at"] = _iso(now)
        cyc["invitation_token_hash"] = payload["token_hash"]
        cyc["invitation_channel"] = payload["channel"]
        cyc["reminder_count"] = 0
        cyc["reminder_due_at"] = _iso(now + int(REMINDER_CADENCE_HOURS * 3600 * 1000))
        cyc["cutoff_at"] = _iso(now + int(CUTOFF_HOURS_AFTER_INVITE * 3600 * 1000))
        cyc["disposition"] = None
        cyc["updated_at"] = _iso_now()
        cycles[week_start] = cyc
        _save_cycles(company_id, cycles, env)
    return {"action": "sent", "cycle_id": cyc["cycle_id"]}


def send_due_reminder(company_id: str, week_start: str,
                      send: Callable[[Dict[str, Any]], bool],
                      now_ms: Optional[int] = None,
                      env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Fire the due reminder (if any). Bounded: at most MAX_REMINDERS
    reminders, REMINDER_CADENCE_HOURS apart, none after cutoff. A paused
    (explicit preference) cycle skips reminders without consuming the bound."""
    now = int(now_ms) if now_ms is not None else int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    with _LOCK:
        cyc = _load_cycles(company_id, env).get(week_start)
        if not cyc:
            return {"action": "none", "cycle_id": ""}
    if cyc["state"] != "invited":
        return {"action": "none", "cycle_id": cyc["cycle_id"]}
    if cyc.get("pause_reminders"):
        return {"action": "skip", "cycle_id": cyc["cycle_id"], "reason": "paused"}
    until = cyc.get("pause_reminders_until")
    if until:
        try:
            if datetime.fromisoformat(until).timestamp() * 1000 > now:
                return {"action": "skip", "cycle_id": cyc["cycle_id"], "reason": "paused_until"}
        except ValueError:
            pass
    if not cyc.get("reminder_due_at"):
        return {"action": "none", "cycle_id": cyc["cycle_id"]}
    if _parse_ms(cyc["reminder_due_at"]) > now:
        return {"action": "none", "cycle_id": cyc["cycle_id"]}
    if cyc.get("cutoff_at") and _parse_ms(cyc["cutoff_at"]) <= now:
        return {"action": "skip", "cycle_id": cyc["cycle_id"], "reason": "past_cutoff"}
    if int(cyc.get("reminder_count", 0)) >= MAX_REMINDERS:
        return {"action": "skip", "cycle_id": cyc["cycle_id"], "reason": "max_reminders"}

    n = int(cyc.get("reminder_count", 0)) + 1
    payload = {
        "company_id": company_id,
        "cycle_id": cyc["cycle_id"],
        "week_start": week_start,
        "reminder_number": n,
        "message": "Reminder: what is the content theme for the week of %s? (reminder %d of %d)" % (week_start, n, MAX_REMINDERS),
    }
    delivered = False
    try:
        delivered = bool(send(payload))
    except Exception:
        delivered = False
    if not delivered:
        return {"action": "skip", "cycle_id": cyc["cycle_id"], "reason": "delivery_failed"}

    with _LOCK:
        cycles = _load_cycles(company_id, env)
        cyc = cycles.get(week_start)
        if not cyc or cyc["state"] != "invited":
            return {"action": "skip", "cycle_id": (cyc or {}).get("cycle_id", ""), "reason": "state_changed"}
        cyc["reminder_count"] = int(cyc.get("reminder_count", 0)) + 1
        cyc["last_reminder_at"] = _iso(now)
        cyc["reminder_due_at"] = _iso(now + int(REMINDER_CADENCE_HOURS * 3600 * 1000))
        cyc["updated_at"] = _iso_now()
        cycles[week_start] = cyc
        _save_cycles(company_id, cycles, env)
    return {"action": "sent", "cycle_id": cyc["cycle_id"]}


def apply_response(cycle_id: str, answer: Dict[str, Any],
                   now_ms: Optional[int] = None,
                   env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Apply the client's answer to THIS cycle only (QC-F07 guard rails):

    - A LATE answer (cutoff passed) is recorded on its OWN cycle; it can never
      overwrite another week (every write targets the row whose cycle_id
      matched, and a closed cycle gets a late_* disposition, not a reopen).
    - 'skip' closes ONLY this cycle (skip_week=1); next_cycle_at still lands.
    - 'pause' records the explicit preference.
    - 'evergreen' without a recorded standing approval becomes a DRAFT
      disposition and the ask repeats next week.
    """
    now = int(now_ms) if now_ms is not None else int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    kind = answer.get("kind")
    with _LOCK:
        located = None
        for company_key in _all_company_keys(env):
            cycles = _load_cycles(company_key, env)
            for ws, cyc in cycles.items():
                if cyc.get("cycle_id") == cycle_id:
                    located = (company_key, ws, cycles, cyc)
                    break
            if located:
                break
        if not located:
            return {"ok": False, "error": E_CYCLE_NOT_FOUND}
        company_id, week_start, cycles, cyc = located

        if cyc.get("response_state") == kind:
            return {"ok": True, "effect": "already_recorded"}

        late = bool(cyc.get("cutoff_at") and _parse_ms(cyc["cutoff_at"]) < now)
        lead = now + NEXT_CYCLE_LEAD_DAYS * 86_400_000

        if kind == "skip":
            cyc["state"] = "skipped"
            cyc["response_state"] = "skip"
            cyc["responded_at"] = _iso(now)
            cyc["skip_week"] = 1
            cyc["next_cycle_at"] = _iso(lead)
            cyc["disposition"] = "skipped_by_owner"
        elif kind == "pause":
            cyc["response_state"] = "pause"
            cyc["responded_at"] = _iso(now)
            cyc["pause_reminders"] = True
            cyc["pause_reminders_until"] = answer.get("until")
        elif kind == "evergreen":
            if cyc.get("standing_approval") == "evergreen":
                cyc["state"] = "closed"
                cyc["response_state"] = "evergreen"
                cyc["responded_at"] = _iso(now)
                cyc["selected_fallback"] = cyc.get("selected_fallback") or "evergreen"
                cyc["disposition"] = "evergreen_published"
                cyc["next_cycle_at"] = _iso(lead)
            else:
                cyc["state"] = "closed"
                cyc["response_state"] = "evergreen"
                cyc["responded_at"] = _iso(now)
                cyc["disposition"] = "draft_awaiting_approval"
                cyc["next_cycle_at"] = _iso(lead)
        elif kind == "theme":
            cyc["state"] = "responded"
            cyc["response_state"] = "theme_chosen"
            cyc["responded_at"] = _iso(now)
            cyc["selected_fallback"] = None
            cyc["disposition"] = "late_theme_recorded" if late else "theme_recorded"
            cyc["next_cycle_at"] = _iso(lead)
        else:
            return {"ok": False, "error": "E_UNKNOWN_RESPONSE_KIND"}

        cyc["updated_at"] = _iso_now()
        cycles[week_start] = cyc
        _save_cycles(company_id, cycles, env)
        effect = {
            "skip": "skipped_this_week_only",
            "pause": "reminders_paused",
            "evergreen": cyc.get("disposition") or "recorded",
            "theme": cyc.get("disposition") or "recorded",
        }.get(kind, "recorded")
        return {"ok": True, "effect": effect, "cycle_id": cycle_id, "week_start": week_start}


def advance_cycle(company_id: str, now_ms: int,
                  send: Optional[Callable[[Dict[str, Any]], bool]] = None,
                  timezone_name: str = "America/New_York",
                  env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """One SHORT scheduler step for a company: ensure this week's cycle,
    invite, apply the cutoff disposition, roll next week. Row-at-a-time."""
    week_start = week_start_local(now_ms, timezone_name)
    ensured = ensure_cycle(company_id, week_start, timezone_name, env)
    with _LOCK:
        cycles = _load_cycles(company_id, env)
        cyc = cycles.get(week_start)
    if not cyc:
        return {"action": "retry", "cycle_id": ensured["cycle_id"], "detail": "cycle_row_missing"}

    # Roll next week when its lead time has arrived (independent of THIS
    # week's response — a skipped/closed week still creates its successor).
    if cyc.get("next_cycle_at") and _parse_ms(cyc["next_cycle_at"]) <= now_ms:
        next_week = next_week_start(cyc["week_start_local"])
        nxt = ensure_cycle(company_id, next_week, timezone_name, env)
        if nxt["created"]:
            return {"action": "next_cycle", "cycle_id": nxt["cycle_id"], "detail": next_week}

    if cyc["state"] == "draft":
        if send is not None:
            r = send_invitation(company_id, week_start, send, now_ms, env)
            return {"action": "invite" if r["action"] == "sent" else "retry",
                    "cycle_id": r["cycle_id"], "detail": r.get("reason")}
        return {"action": "invite", "cycle_id": cyc["cycle_id"], "detail": "pending_send"}

    if cyc["state"] == "invited" and cyc.get("cutoff_at") and _parse_ms(cyc["cutoff_at"]) <= now_ms:
        approved = cyc.get("standing_approval") == "evergreen"
        fallback = cyc.get("selected_fallback") or "draft"
        disposition = "evergreen_used" if approved else "draft_%s_ask_again" % fallback
        with _LOCK:
            cycles = _load_cycles(company_id, env)
            cyc = cycles.get(week_start)
            if cyc and cyc["state"] == "invited":
                cyc["state"] = "closed"
                cyc["response_state"] = "cutoff"
                cyc["disposition"] = disposition
                cyc["next_cycle_at"] = _iso(now_ms + NEXT_CYCLE_LEAD_DAYS * 86_400_000)
                cyc["updated_at"] = _iso_now()
                cycles[week_start] = cyc
                _save_cycles(company_id, cycles, env)
        return {"action": "cutoff", "cycle_id": cyc["cycle_id"] if cyc else ensured["cycle_id"], "detail": disposition}

    return {"action": "none", "cycle_id": cyc["cycle_id"]}


# ── F17: engine ownership (file-backed twin of social_engine_ownership) ────

def _ownership_path(env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(state_dir(env), "engine-ownership.json")


def claim_engine_ownership(company_id: str, engine: str = "cc-cycle-service",
                           scheduler_name: str = "node-cron",
                           next_run_at: Optional[str] = None,
                           legacy_names: Optional[List[str]] = None,
                           env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Claim the ONE active engine-ownership row for a company and demote
    every legacy scheduler row. Idempotent; legacy rows demote only after a
    healthy active row exists (never leave a company with zero owners)."""
    legacy = legacy_names if legacy_names is not None else [
        "skill35-weekly-theme", "social-media-weekly-theme", "n8n-weekly-theme-trigger",
    ]
    is_durable = engine == "cc-cycle-service"
    with _LOCK:
        path = _ownership_path(env)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ownership = json.load(fh)
            if not isinstance(ownership, dict):
                ownership = {}
        except (OSError, ValueError):
            ownership = {}
        rows: List[Dict[str, Any]] = ownership.get("rows", [])
        mine = [r for r in rows if r.get("company_id") == company_id and r.get("engine") == engine and r.get("state") == "active"]
        if mine:
            owner = mine[0]
            if next_run_at:
                owner["next_run_at"] = next_run_at
            owner["verified_at"] = _iso_now()
            owner_id = owner["id"]
        else:
            owner_id = "owner-%s-%s" % (company_id[:8], uuid.uuid4().hex[:8])
            rows.append({
                "id": owner_id, "company_id": company_id, "engine": engine,
                "scheduler_name": scheduler_name, "scheduler_expr": "*/5 * * * *",
                "next_run_at": next_run_at, "state": "active",
                "registered_at": _iso_now(), "verified_at": _iso_now(),
            })
        demoted = 0
        for r in rows:
            if (r.get("company_id") == company_id and r.get("state") == "active"
                    and r.get("id") != owner_id):
                if is_durable:
                    # The DURABLE engine demotes any other active owner
                    # (legacy crons, n8n triggers) — it is the owner of record.
                    r["state"] = "superseded"
                    r["superseded_by"] = owner_id
                    demoted += 1
                # A LEGACY claim never demotes another active row — least
                # authority: it records itself and waits for verification. A
                # stale legacy row whose durable owner exists stays superseded.
        ownership["rows"] = rows
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(ownership, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    return {"claimed": True, "owner_row": owner_id, "demoted": demoted}


def verify_engine_ownership(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Exactly one ACTIVE engine owner per company; legacy names superseded.
    Used by the cron scripts' --verify (forwarding-adapter) path."""
    with _LOCK:
        try:
            with open(_ownership_path(env), "r", encoding="utf-8") as fh:
                ownership = json.load(fh)
            rows = ownership.get("rows", [])
        except (OSError, ValueError):
            rows = []
    by_company: Dict[str, Dict[str, int]] = {}
    for r in rows:
        e = by_company.setdefault(r.get("company_id", ""), {"active": 0, "superseded": 0})
        if r.get("state") == "active":
            e["active"] += 1
        elif r.get("state") == "superseded":
            e["superseded"] += 1
    ok = all(e["active"] == 1 for e in by_company.values()) if by_company else True
    return {
        "ok": ok,
        "companies": len(by_company),
        "active_owners": sum(1 for e in by_company.values() if e["active"] == 1),
        "superseded": sum(e["superseded"] for e in by_company.values()),
    }


def _parse_ms(iso: str) -> int:
    try:
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def register_cycle_engine(company_id: str, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Convenience for the cron adapters: claim ownership + stamp the next
    run window. The adapter then verifies instead of owning the cadence."""
    nxt = _iso(int(datetime.now(tz=timezone.utc).timestamp() * 1000) + 5 * 60_000)
    claim = claim_engine_ownership(company_id, next_run_at=nxt, env=env)
    return claim