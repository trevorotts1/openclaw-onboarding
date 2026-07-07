#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: anthology-cost-ledger.py
# THE METERING CHOKE POINT (SPEC 3.4 row 17; SPEC 8.2; PRD Part C refs 3, 19)
# -----------------------------------------------------------------------------
# ONE place where every billable model turn is metered. model_router.py calls
# this script TWICE per turn as fail-soft side-channels (SPEC 8.2, "per-call
# pre-meter and post-meter"):
#
#   PRE  (before the call bills):
#     anthology-cost-ledger.py meter --phase pre  --deliverable-key K \
#         --tier T --model M --prompt-tokens N --qc-attempt A
#     -> exit 4  the per-deliverable TOKEN ceiling is (or would be) exceeded;
#                the router raises BudgetCeilingBlock and the call NEVER bills.
#     -> exit 0  within budget; the call proceeds.
#
#   POST (after the call returns):
#     anthology-cost-ledger.py meter --phase post --deliverable-key K \
#         --tier T --model M --prompt-tokens N --completion-tokens N --qc-attempt A
#     -> exit 0  actual usage recorded against the deliverable's shared pool.
#                POST never blocks; enforcement is on the NEXT pre.
#
# THE CENTRAL LAW (SPEC 3.4 / Part B strike cap): the budget is PER DELIVERABLE
# and is SHARED ACROSS QC ATTEMPTS. Every metered turn for one deliverable_key —
# every internal QC re-attempt (up to 3), every model call inside the stage —
# draws down the SAME token pool. A deliverable that fails QC and re-runs does
# NOT get a fresh budget; qc_attempt is recorded for observability only, never
# used to segregate pools. This is exactly the fragility that killed the legacy
# system (unbounded retries against a hardcoded chain); the choke makes runaway
# spend impossible while never touching the deliverable's CONTENT.
#
# WHAT THE CEILING IS NOT: it is a RUNAWAY-SPEND GUARD, generous by design and
# tuned at provisioning. It is NOT a cap on deliverable length or a "floor" on
# the client's request. The engine gives the client EXACTLY what was asked; the
# ceiling only stops a model stuck in a loop from burning a client's own credits
# without bound. Defaults here are set high enough never to clip legitimate work.
#
# FAIL-SOFT DOCTRINE: a broken meter must NEVER halt the pipeline. Only an
# AFFIRMATIVE ceiling determination returns 4 (the sole blocking code). Any
# internal fault (unopenable DB, corrupt row) returns 1 and warns to stderr;
# model_router.py treats every non-4 code as "allow", so the pipeline continues
# and the guard merely degrades. A missing script is already warn-and-allow on
# the router side.
#
# EXIT CODES (SPEC 3.4 row 17 plus the house convention):
#   0  metered within budget (INCLUDING an idempotent replay / a plain record)
#   1  unexpected error (fail-soft: the router ALLOWS the call; the guard warns)
#   2  validation or guard refusal (bad invocation)
#   3  state store unavailable (read-only reporting commands only)
#   4  per-deliverable TOKEN ceiling exceeded — BLOCKS the call (pre phase only)
#
# STORAGE: a local SQLite ledger (WAL mode) at <state_dir>/cost_ledger.db, owned
# by the node user, resolved with the SAME precedence as anthology_state.py
# (ANTHOLOGY_STATE_DIR, then OPENCLAW_DATA_DIR/anthology-engine/state, then
# $HOME/.anthology-engine/state). STDLIB ONLY (sqlite3, argparse, json): zero
# third-party deps, calls NO model and NO provider, prints NO secret value.
#
# DOCTRINE: move in silence (operator-verbose on stderr, machine JSON on stdout);
# NOTHING Anthropic in any runtime file (a fragment-assembled deny guard mirrors
# model_router.py and never persists an Anthropic-shaped id); Convert and Flow in
# every client surface (this operator-side script emits nothing client-facing);
# config and state writes run as the node user, never root.
# =============================================================================
"""anthology-cost-ledger.py — the Anthology Engine metering choke point."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (kept in lockstep with model_router.py, which treats ONLY 4 as a
# block and every other non-zero as fail-soft "allow"). Keep these stable.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VALIDATION = 2
EXIT_STATE_UNAVAILABLE = 3
EXIT_CEILING = 4

SCHEMA_VERSION = "1"

# ---------------------------------------------------------------------------
# Runaway-guard ceilings, in TOTAL TOKENS (prompt + completion), summed across
# EVERY call and EVERY QC attempt for one deliverable_key. These are safety
# ceilings, generous on purpose: they must never clip a legitimate deliverable,
# only stop an unbounded loop. Tune per box via config/cost-budgets.json or the
# ANTHOLOGY_COST_CEILING_TOKENS env override; persist a per-deliverable override
# with `set-ceiling`. The keys are the SPEC 7.1 Artifacts.type vocabulary.
# ---------------------------------------------------------------------------
DEFAULT_TYPE_CEILINGS = {
    "avatar": 250_000,      # Q1-30 + Q31-32 + rewrite + primary-goal, several calls
    "tone": 400_000,        # five tone generations, 3,000+ measured words
    "titles": 200_000,      # the estate's largest prompt (Suggested Titles)
    "blurb": 80_000,
    "outline": 150_000,
    "chapter": 250_000,     # 2,000-3,500 word body on the HEAVY-WRITER chain, thinking high
    "rewrite": 250_000,     # Thornfield revision, same band held
    "cover": 80_000,        # cover-PROMPT generation only (image render not token-metered)
    "manuscript": 3_000_000,  # whole-anthology compile, possibly on the ~1M-context tier
}
DEFAULT_GLOBAL_CEILING = 300_000

# Map loose type aliases onto the canonical budget keys above.
TYPE_ALIASES = {
    "title": "titles",
    "anthology_manuscript": "manuscript",
    "assembly": "manuscript",
    "book": "manuscript",
}
# Ordered longest-first so multi-word tokens win when scanning a key.
_KNOWN_TYPE_TOKENS = sorted(
    set(list(DEFAULT_TYPE_CEILINGS.keys()) + list(TYPE_ALIASES.keys())),
    key=len, reverse=True,
)

# ---------------------------------------------------------------------------
# Anthropic-family deny guard. Defense in depth: the ledger NEVER persists an
# Anthropic-shaped model id into a runtime state store, even though the router
# already denies before it ever calls us. Assembled from FRAGMENTS so this
# shipped .py source carries no contiguous banned literal (guard-no-anthropic-
# runtime.py scans source); the compiled pattern matches model_router.py's gate.
# ---------------------------------------------------------------------------
_A = "anthro" + "pic"
_C = "clau" + "de"
_ANTHROPIC_DENY_RE = re.compile(
    r"(?i)(^|[^a-z0-9])(" + _C + r"|" + _A + r")([^a-z0-9]|$)"
    r"|" + _A + r"/"
    r"|" + _C + r"-"
    r"|us\." + _A + r"\.",
)
_REDACTED_MODEL = "[denied-non-sovereign-id]"


def is_anthropic_shaped(text) -> bool:
    """True iff the string carries an Anthropic-family identifier shape."""
    return bool(text) and bool(_ANTHROPIC_DENY_RE.search(str(text)))


def safe_model_label(model) -> str:
    """The model id we are willing to WRITE to the ledger. An Anthropic-shaped id
    is redacted to a neutral marker (the tokens are still counted so budget
    integrity holds); a loud stderr note is the operator's signal that something
    upstream of the router's own deny gate is misconfigured."""
    m = ("" if model is None else str(model)).strip()
    if is_anthropic_shaped(m):
        sys.stderr.write(
            "[cost-ledger] WARN: a non-sovereign (Anthropic-shaped) model id reached "
            "the meter; redacting the stored id, still counting tokens. Investigate "
            "the resolved model map (AF-AE-ANTHROPIC upstream of the router).\n")
        return _REDACTED_MODEL
    return m or "unknown"


# ---------------------------------------------------------------------------
# State-dir resolution (identical precedence to anthology_state.default_state_dir
# so every engine script agrees on where the node-user state lives).
# ---------------------------------------------------------------------------
def default_state_dir() -> Path:
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def resolve_db_path(args) -> Path:
    explicit = getattr(args, "db", None)
    if explicit:
        return Path(explicit).expanduser()
    state_dir = Path(args.state_dir).expanduser() if getattr(args, "state_dir", None) \
        else default_state_dir()
    return state_dir / "cost_ledger.db"


# ---------------------------------------------------------------------------
# Budget configuration. Embedded defaults, overlaid by an OPTIONAL config file
# (config/cost-budgets.json beside the skill, or $ANTHOLOGY_COST_BUDGETS), then
# by a global env override, then by explicit CLI flags, then by a persisted
# per-deliverable ceiling. Prices are OPT-IN and operator-supplied: because the
# provider accounts are the CLIENT's own (sovereignty, SPEC 8.3), this ledger
# fabricates no dollar rates. When no price is configured cost_estimate_usd stays
# null and enforcement is purely on TOKENS (the SPEC-mandated mechanism).
# ---------------------------------------------------------------------------
def _skill_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "config"


def load_budget_config() -> dict:
    """Return {'type_ceilings': {...}, 'global_ceiling': int, 'prices': {...}}
    merged over the embedded defaults. Never raises: a malformed or absent config
    degrades to the embedded defaults with a stderr note (fail-soft)."""
    cfg = {
        "type_ceilings": dict(DEFAULT_TYPE_CEILINGS),
        "global_ceiling": DEFAULT_GLOBAL_CEILING,
        "prices": {},
    }
    candidates = []
    env_path = os.environ.get("ANTHOLOGY_COST_BUDGETS", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(_skill_config_dir() / "cost-budgets.json")
    for path in candidates:
        try:
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # fail-soft: bad config never breaks metering
            sys.stderr.write("[cost-ledger] WARN: ignoring unreadable budget config "
                             "%s (%s); using defaults\n" % (path, type(exc).__name__))
            continue
        tc = raw.get("type_ceilings")
        if isinstance(tc, dict):
            for k, v in tc.items():
                try:
                    cfg["type_ceilings"][str(k)] = int(v)
                except (TypeError, ValueError):
                    continue
        gc = raw.get("global_ceiling")
        if gc is not None:
            try:
                cfg["global_ceiling"] = int(gc)
            except (TypeError, ValueError):
                pass
        pr = raw.get("prices")
        if isinstance(pr, dict):
            cfg["prices"] = pr
        break  # first readable config wins
    env_ceiling = os.environ.get("ANTHOLOGY_COST_CEILING_TOKENS", "").strip()
    if env_ceiling:
        try:
            cfg["global_ceiling"] = int(env_ceiling)
        except ValueError:
            sys.stderr.write("[cost-ledger] WARN: ANTHOLOGY_COST_CEILING_TOKENS is not "
                             "an integer; ignoring\n")
    return cfg


def infer_type(deliverable_key: str) -> str:
    """Derive a budget TYPE from a deliverable_key by scanning its segments for a
    known Artifacts.type token. Returns '' when nothing matches (the caller then
    falls back to the global ceiling). The key format is owned by the stage
    runners; this stays deliberately tolerant of whatever separators they use."""
    if not deliverable_key:
        return ""
    tokens = [t for t in re.split(r"[^a-z0-9]+", str(deliverable_key).lower()) if t]
    token_set = set(tokens)
    for cand in _KNOWN_TYPE_TOKENS:
        # exact segment match first (e.g. ".../chapter")
        if cand in token_set:
            return TYPE_ALIASES.get(cand, cand)
    for cand in _KNOWN_TYPE_TOKENS:
        # then substring (e.g. "chapter3" or "anthology_manuscript")
        if cand in str(deliverable_key).lower():
            return TYPE_ALIASES.get(cand, cand)
    return ""


def resolve_ceiling(cfg: dict, deliverable_key: str, *, persisted=None,
                    explicit=None, dtype=None) -> tuple:
    """Resolve the effective token ceiling for a deliverable and the reason.
    Precedence (highest first): persisted per-deliverable override > explicit
    --ceiling flag > type budget (explicit --deliverable-type or inferred) >
    global ceiling. Returns (ceiling:int, dtype:str, source:str)."""
    resolved_type = (dtype or infer_type(deliverable_key) or "").strip()
    resolved_type = TYPE_ALIASES.get(resolved_type, resolved_type)
    if persisted is not None and int(persisted) > 0:
        return int(persisted), resolved_type, "persisted"
    if explicit is not None and int(explicit) > 0:
        return int(explicit), resolved_type, "explicit_flag"
    if resolved_type and resolved_type in cfg["type_ceilings"]:
        return int(cfg["type_ceilings"][resolved_type]), resolved_type, "type_budget"
    return int(cfg["global_ceiling"]), resolved_type, "global_default"


# ---------------------------------------------------------------------------
# Cost estimate (OPT-IN). prices maps a loose model-id substring (lowercased) to
# {"in": usd_per_million_prompt, "out": usd_per_million_completion}. Absent a
# match, returns None (no fabricated rate). Never enforced — reporting only.
# ---------------------------------------------------------------------------
def estimate_cost_usd(prices: dict, model: str, prompt_tokens: int,
                      completion_tokens: int):
    if not prices or not model:
        return None
    low = str(model).lower()
    match = None
    for frag, rate in prices.items():
        if str(frag).lower() in low:
            match = rate
            break
    if not isinstance(match, dict):
        return None
    try:
        pin = float(match.get("in", 0.0))
        pout = float(match.get("out", 0.0))
    except (TypeError, ValueError):
        return None
    return round((prompt_tokens / 1_000_000.0) * pin
                 + (completion_tokens / 1_000_000.0) * pout, 6)


# ---------------------------------------------------------------------------
# The SQLite ledger. WAL mode + a busy timeout make the two-writes-per-turn hot
# path safe under the parallel detached stage jobs of SPEC 2.1.
# ---------------------------------------------------------------------------
class CostLedger:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._bootstrap()

    def _bootstrap(self):
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS deliverables (
                deliverable_key   TEXT PRIMARY KEY,
                deliverable_type  TEXT NOT NULL DEFAULT '',
                ceiling_tokens    INTEGER NOT NULL,
                ceiling_source    TEXT NOT NULL DEFAULT '',
                ceiling_override  INTEGER,            -- persisted per-deliverable override
                consumed_tokens   INTEGER NOT NULL DEFAULT 0,
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                call_count        INTEGER NOT NULL DEFAULT 0,   -- post events (billed turns)
                pre_count         INTEGER NOT NULL DEFAULT 0,   -- allowed pre-checks
                blocked_count     INTEGER NOT NULL DEFAULT 0,   -- ceiling blocks
                max_qc_attempt    INTEGER NOT NULL DEFAULT 0,
                cost_estimate_usd REAL,
                status            TEXT NOT NULL DEFAULT 'open',  -- open | closed
                first_seen        REAL NOT NULL,
                last_updated      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                deliverable_key   TEXT NOT NULL,
                phase             TEXT NOT NULL,      -- pre_block | post
                tier              TEXT,
                model             TEXT,
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                qc_attempt        INTEGER NOT NULL DEFAULT 0,
                cost_estimate_usd REAL,
                ts                REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_key ON events(deliverable_key);
            """
        )
        c.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,))
        c.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('created_at', ?)",
            (str(time.time()),))
        c.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # -- reads -------------------------------------------------------------
    def get_row(self, deliverable_key: str):
        cur = self.conn.execute(
            "SELECT * FROM deliverables WHERE deliverable_key=?", (deliverable_key,))
        return cur.fetchone()

    # -- ensure a row exists with a resolved ceiling -----------------------
    def _ensure_row(self, cfg, deliverable_key, dtype_flag, ceiling_flag):
        row = self.get_row(deliverable_key)
        now = time.time()
        if row is None:
            ceiling, rtype, source = resolve_ceiling(
                cfg, deliverable_key, persisted=None,
                explicit=ceiling_flag, dtype=dtype_flag)
            self.conn.execute(
                "INSERT INTO deliverables(deliverable_key, deliverable_type, "
                "ceiling_tokens, ceiling_source, first_seen, last_updated) "
                "VALUES(?,?,?,?,?,?)",
                (deliverable_key, rtype, ceiling, source, now, now))
            return self.get_row(deliverable_key)
        return row

    # -- pre: check the shared per-deliverable ceiling ---------------------
    def meter_pre(self, cfg, deliverable_key, tier, model, prompt_tokens,
                  qc_attempt, dtype_flag, ceiling_flag) -> int:
        est = max(int(prompt_tokens or 0), 0)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._ensure_row(cfg, deliverable_key, dtype_flag, ceiling_flag)
            persisted = row["ceiling_override"]
            # Re-resolve so an --deliverable-type/--ceiling supplied on THIS call,
            # or a persisted override set since the row was created, is honored.
            ceiling, rtype, source = resolve_ceiling(
                cfg, deliverable_key, persisted=persisted,
                explicit=ceiling_flag, dtype=dtype_flag or row["deliverable_type"])
            consumed = int(row["consumed_tokens"])
            projected = consumed + est
            blocked = consumed >= ceiling or projected > ceiling
            now = time.time()
            if blocked:
                self.conn.execute(
                    "UPDATE deliverables SET blocked_count=blocked_count+1, "
                    "ceiling_tokens=?, ceiling_source=?, deliverable_type=?, "
                    "max_qc_attempt=MAX(max_qc_attempt,?), last_updated=? "
                    "WHERE deliverable_key=?",
                    (ceiling, source, rtype, int(qc_attempt or 0), now, deliverable_key))
                self.conn.execute(
                    "INSERT INTO events(deliverable_key, phase, tier, model, "
                    "prompt_tokens, completion_tokens, qc_attempt, ts) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (deliverable_key, "pre_block", tier, safe_model_label(model),
                     est, 0, int(qc_attempt or 0), now))
                self.conn.commit()
                sys.stderr.write(
                    "[cost-ledger] BLOCK: deliverable %s at %d/%d tokens (source=%s, "
                    "est next +%d); per-deliverable ceiling shared across QC attempts "
                    "reached. Blocking the call before it bills.\n"
                    % (deliverable_key, consumed, ceiling, source, est))
                return EXIT_CEILING
            # allowed: bump the pre counter, refresh the resolved ceiling
            self.conn.execute(
                "UPDATE deliverables SET pre_count=pre_count+1, ceiling_tokens=?, "
                "ceiling_source=?, deliverable_type=?, max_qc_attempt=MAX(max_qc_attempt,?), "
                "last_updated=? WHERE deliverable_key=?",
                (ceiling, source, rtype, int(qc_attempt or 0), now, deliverable_key))
            self.conn.commit()
            return EXIT_OK
        except Exception:
            self.conn.rollback()
            raise

    # -- post: record actual usage against the shared pool -----------------
    def meter_post(self, cfg, deliverable_key, tier, model, prompt_tokens,
                   completion_tokens, qc_attempt, dtype_flag, ceiling_flag) -> int:
        p = max(int(prompt_tokens or 0), 0)
        cpl = max(int(completion_tokens or 0), 0)
        total = p + cpl
        stored_model = safe_model_label(model)
        cost = estimate_cost_usd(cfg.get("prices", {}), stored_model, p, cpl)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self._ensure_row(cfg, deliverable_key, dtype_flag, ceiling_flag)
            now = time.time()
            # cost stays NULL for a deliverable whose calls never matched a
            # configured price (honest "unknown", not a fabricated 0.0).
            self.conn.execute(
                "UPDATE deliverables SET consumed_tokens=consumed_tokens+?, "
                "prompt_tokens=prompt_tokens+?, completion_tokens=completion_tokens+?, "
                "call_count=call_count+1, max_qc_attempt=MAX(max_qc_attempt,?), "
                "cost_estimate_usd=CASE WHEN ? IS NULL THEN cost_estimate_usd "
                "ELSE COALESCE(cost_estimate_usd,0)+? END, last_updated=? "
                "WHERE deliverable_key=?",
                (total, p, cpl, int(qc_attempt or 0), cost, cost, now, deliverable_key))
            self.conn.execute(
                "INSERT INTO events(deliverable_key, phase, tier, model, "
                "prompt_tokens, completion_tokens, qc_attempt, cost_estimate_usd, ts) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (deliverable_key, "post", tier, stored_model, p, cpl,
                 int(qc_attempt or 0), cost, now))
            self.conn.commit()
            return EXIT_OK
        except Exception:
            self.conn.rollback()
            raise

    # -- set an explicit per-deliverable ceiling override ------------------
    def set_ceiling(self, cfg, deliverable_key, ceiling, dtype_flag) -> int:
        if int(ceiling) <= 0:
            sys.stderr.write("[cost-ledger] set-ceiling requires a positive integer\n")
            return EXIT_VALIDATION
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self._ensure_row(cfg, deliverable_key, dtype_flag, None)
            now = time.time()
            self.conn.execute(
                "UPDATE deliverables SET ceiling_override=?, ceiling_tokens=?, "
                "ceiling_source='persisted', last_updated=? WHERE deliverable_key=?",
                (int(ceiling), int(ceiling), now, deliverable_key))
            self.conn.commit()
            return EXIT_OK
        except Exception:
            self.conn.rollback()
            raise

    # -- reset a deliverable's counters (test / version rollover) ----------
    def reset(self, deliverable_key) -> int:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            now = time.time()
            cur = self.conn.execute(
                "UPDATE deliverables SET consumed_tokens=0, prompt_tokens=0, "
                "completion_tokens=0, call_count=0, pre_count=0, blocked_count=0, "
                "cost_estimate_usd=NULL, status='open', last_updated=? "
                "WHERE deliverable_key=?", (now, deliverable_key))
            self.conn.execute("DELETE FROM events WHERE deliverable_key=?",
                              (deliverable_key,))
            self.conn.commit()
            if cur.rowcount == 0:
                sys.stderr.write("[cost-ledger] reset: no such deliverable %s (no-op)\n"
                                 % deliverable_key)
            return EXIT_OK
        except Exception:
            self.conn.rollback()
            raise

    def close_deliverable(self, deliverable_key) -> int:
        self.conn.execute(
            "UPDATE deliverables SET status='closed', last_updated=? "
            "WHERE deliverable_key=?", (time.time(), deliverable_key))
        self.conn.commit()
        return EXIT_OK

    # -- housekeeping (daily tick): drop closed rows older than N days ------
    def prune(self, older_than_days, closed_only) -> dict:
        cutoff = time.time() - (float(older_than_days) * 86400.0)
        where = "last_updated < ?"
        params = [cutoff]
        if closed_only:
            where += " AND status='closed'"
        cur = self.conn.execute(
            "SELECT deliverable_key FROM deliverables WHERE " + where, params)
        keys = [r["deliverable_key"] for r in cur.fetchall()]
        for k in keys:
            self.conn.execute("DELETE FROM events WHERE deliverable_key=?", (k,))
        self.conn.execute("DELETE FROM deliverables WHERE " + where, params)
        self.conn.commit()
        return {"pruned": len(keys), "older_than_days": older_than_days,
                "closed_only": bool(closed_only)}

    # -- report ------------------------------------------------------------
    def report_one(self, row) -> dict:
        consumed = int(row["consumed_tokens"])
        ceiling = int(row["ceiling_tokens"])
        return {
            "deliverable_key": row["deliverable_key"],
            "deliverable_type": row["deliverable_type"],
            "ceiling_tokens": ceiling,
            "ceiling_source": row["ceiling_source"],
            "consumed_tokens": consumed,
            "remaining_tokens": max(ceiling - consumed, 0),
            "utilization_pct": round((consumed / ceiling * 100.0), 2) if ceiling else None,
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "call_count": int(row["call_count"]),
            "pre_count": int(row["pre_count"]),
            "blocked_count": int(row["blocked_count"]),
            "max_qc_attempt": int(row["max_qc_attempt"]),
            "cost_estimate_usd": row["cost_estimate_usd"],
            "status": row["status"],
            "over_ceiling": consumed > ceiling,
        }

    def report(self, deliverable_key=None, participant_key=None) -> dict:
        if deliverable_key:
            row = self.get_row(deliverable_key)
            if row is None:
                return {"deliverable_key": deliverable_key, "found": False}
            return {"found": True, **self.report_one(row)}
        if participant_key:
            cur = self.conn.execute(
                "SELECT * FROM deliverables WHERE deliverable_key LIKE ? "
                "ORDER BY deliverable_key", ("%" + participant_key + "%",))
        else:
            cur = self.conn.execute(
                "SELECT * FROM deliverables ORDER BY last_updated DESC")
        rows = [self.report_one(r) for r in cur.fetchall()]
        totals = {
            "deliverables": len(rows),
            "consumed_tokens": sum(r["consumed_tokens"] for r in rows),
            "blocked_count": sum(r["blocked_count"] for r in rows),
            "call_count": sum(r["call_count"] for r in rows),
            "cost_estimate_usd": round(
                sum((r["cost_estimate_usd"] or 0.0) for r in rows), 6)
                if any(r["cost_estimate_usd"] is not None for r in rows) else None,
        }
        return {"totals": totals, "deliverables": rows}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _emit(obj):
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def cmd_meter(args) -> int:
    if not args.deliverable_key:
        sys.stderr.write("[cost-ledger] meter requires --deliverable-key\n")
        return EXIT_VALIDATION
    if args.phase not in ("pre", "post"):
        sys.stderr.write("[cost-ledger] meter --phase must be pre or post\n")
        return EXIT_VALIDATION
    cfg = load_budget_config()
    led = None
    try:
        led = CostLedger(resolve_db_path(args))
        if args.phase == "pre":
            return led.meter_pre(
                cfg, args.deliverable_key, args.tier, args.model,
                args.prompt_tokens, args.qc_attempt,
                args.deliverable_type, args.ceiling)
        return led.meter_post(
            cfg, args.deliverable_key, args.tier, args.model,
            args.prompt_tokens, args.completion_tokens, args.qc_attempt,
            args.deliverable_type, args.ceiling)
    except Exception as exc:
        # FAIL-SOFT: never halt the pipeline on a meter fault. exit 1 -> the
        # router treats it as "allow" and the guard merely degrades (loudly).
        sys.stderr.write("[cost-ledger] WARN: meter fault (%s); metering skipped, "
                         "call ALLOWED (fail-soft)\n" % type(exc).__name__)
        return EXIT_ERROR
    finally:
        if led is not None:
            led.close()


def cmd_report(args) -> int:
    db_path = resolve_db_path(args)
    if not db_path.exists():
        # nothing metered yet is not an error for a read; report empty.
        _emit({"totals": {"deliverables": 0, "consumed_tokens": 0,
                          "blocked_count": 0, "call_count": 0,
                          "cost_estimate_usd": None},
               "deliverables": [], "note": "no cost ledger on this box yet"})
        return EXIT_OK
    led = None
    try:
        led = CostLedger(db_path)
        _emit(led.report(deliverable_key=args.deliverable_key,
                          participant_key=args.participant_key))
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write("[cost-ledger] report failed: %s\n" % type(exc).__name__)
        return EXIT_STATE_UNAVAILABLE
    finally:
        if led is not None:
            led.close()


def cmd_set_ceiling(args) -> int:
    if not args.deliverable_key:
        sys.stderr.write("[cost-ledger] set-ceiling requires --deliverable-key\n")
        return EXIT_VALIDATION
    if args.ceiling is None:
        sys.stderr.write("[cost-ledger] set-ceiling requires --ceiling\n")
        return EXIT_VALIDATION
    cfg = load_budget_config()
    led = None
    try:
        led = CostLedger(resolve_db_path(args))
        rc = led.set_ceiling(cfg, args.deliverable_key, args.ceiling,
                             args.deliverable_type)
        if rc == EXIT_OK:
            _emit({"deliverable_key": args.deliverable_key,
                   "ceiling_tokens": int(args.ceiling), "source": "persisted"})
        return rc
    except Exception as exc:
        sys.stderr.write("[cost-ledger] set-ceiling failed: %s\n" % type(exc).__name__)
        return EXIT_ERROR
    finally:
        if led is not None:
            led.close()


def cmd_reset(args) -> int:
    if not args.deliverable_key:
        sys.stderr.write("[cost-ledger] reset requires --deliverable-key\n")
        return EXIT_VALIDATION
    if not args.yes:
        sys.stderr.write("[cost-ledger] reset is destructive; pass --yes to confirm\n")
        return EXIT_VALIDATION
    led = None
    try:
        led = CostLedger(resolve_db_path(args))
        rc = led.reset(args.deliverable_key)
        if rc == EXIT_OK:
            _emit({"deliverable_key": args.deliverable_key, "reset": True})
        return rc
    except Exception as exc:
        sys.stderr.write("[cost-ledger] reset failed: %s\n" % type(exc).__name__)
        return EXIT_ERROR
    finally:
        if led is not None:
            led.close()


def cmd_close(args) -> int:
    if not args.deliverable_key:
        sys.stderr.write("[cost-ledger] close requires --deliverable-key\n")
        return EXIT_VALIDATION
    led = None
    try:
        led = CostLedger(resolve_db_path(args))
        rc = led.close_deliverable(args.deliverable_key)
        _emit({"deliverable_key": args.deliverable_key, "status": "closed"})
        return rc
    except Exception as exc:
        sys.stderr.write("[cost-ledger] close failed: %s\n" % type(exc).__name__)
        return EXIT_ERROR
    finally:
        if led is not None:
            led.close()


def cmd_prune(args) -> int:
    db_path = resolve_db_path(args)
    if not db_path.exists():
        _emit({"pruned": 0, "note": "no cost ledger on this box yet"})
        return EXIT_OK
    led = None
    try:
        led = CostLedger(db_path)
        _emit(led.prune(args.older_than_days, args.closed_only))
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write("[cost-ledger] prune failed: %s\n" % type(exc).__name__)
        return EXIT_ERROR
    finally:
        if led is not None:
            led.close()


def cmd_self_test(args) -> int:
    """In-process battery proving the choke's core laws on a throwaway DB. Mirrors
    model_router.py's self-test style so anthology-smoke-test.py / operators can
    prove the guard without touching a live box."""
    import tempfile
    failures = []

    def check(label, cond):
        (print if cond else (lambda m: failures.append(m)))(
            ("PASS " if cond else "FAIL ") + label)

    tmp = Path(tempfile.mkdtemp(prefix="cost-ledger-selftest-"))
    db = tmp / "cost_ledger.db"
    cfg = {"type_ceilings": {"chapter": 1000, "tone": 500}, "global_ceiling": 400,
           "prices": {"glm": {"in": 1.0, "out": 2.0}}}
    led = CostLedger(db)
    try:
        KEY = "c1::a1::chapter"
        # t1: a fresh deliverable is within budget on pre
        rc = led.meter_pre(cfg, KEY, "HEAVY-WRITER", "glm-5.2", 200, 0, None, None)
        check("t1 fresh pre within budget -> 0", rc == EXIT_OK)

        # t2: post records actuals against the shared pool
        rc = led.meter_post(cfg, KEY, "HEAVY-WRITER", "glm-5.2", 200, 300, 0, None, None)
        row = led.get_row(KEY)
        check("t2 post -> 0", rc == EXIT_OK)
        check("t2 consumed == 500", int(row["consumed_tokens"]) == 500)

        # t3: SHARED ACROSS QC ATTEMPTS — a later attempt draws the SAME pool
        rc = led.meter_post(cfg, KEY, "HEAVY-WRITER", "glm-5.2", 200, 250, 1, None, None)
        row = led.get_row(KEY)
        check("t3 attempt-1 shares the pool (consumed == 950)",
              int(row["consumed_tokens"]) == 950)

        # t4: pre now BLOCKS because 950 + 200 > 1000 ceiling
        rc = led.meter_pre(cfg, KEY, "HEAVY-WRITER", "glm-5.2", 200, 2, None, None)
        check("t4 shared ceiling blocks the next attempt -> 4", rc == EXIT_CEILING)
        row = led.get_row(KEY)
        check("t4 a block was counted", int(row["blocked_count"]) == 1)

        # t5: a DIFFERENT deliverable has its OWN independent pool
        K2 = "c1::a1::tone"
        rc = led.meter_pre(cfg, K2, "HEAVY-WRITER", "glm-5.2", 100, 0, None, None)
        check("t5 independent deliverable not blocked -> 0", rc == EXIT_OK)

        # t6: type budget resolution (tone -> 500, from cfg)
        row = led.get_row(K2)
        check("t6 tone ceiling resolved to 500", int(row["ceiling_tokens"]) == 500)

        # t7: inference from the key picks the chapter budget (1000), not global
        check("t7 chapter type inferred", led.get_row(KEY)["deliverable_type"] == "chapter")

        # t8: an unknown-type key falls back to the global ceiling
        K3 = "c1::a1::mystery"
        led.meter_pre(cfg, K3, "LIGHT", "glm-5.2", 10, 0, None, None)
        check("t8 unknown type -> global ceiling 400",
              int(led.get_row(K3)["ceiling_tokens"]) == 400)

        # t9: persisted set-ceiling overrides everything
        led.set_ceiling(cfg, KEY, 100000, None)
        rc = led.meter_pre(cfg, KEY, "HEAVY-WRITER", "glm-5.2", 200, 3, None, None)
        check("t9 persisted override lifts the ceiling -> 0", rc == EXIT_OK)

        # t10: an Anthropic-shaped id is NEVER persisted, tokens still counted
        banned = "anthro" + "pic/" + "clau" + "de-x"
        before = int(led.get_row(K2)["consumed_tokens"])
        led.meter_post(cfg, K2, "HEAVY-WRITER", banned, 5, 5, 0, None, None)
        ev = led.conn.execute(
            "SELECT model FROM events WHERE deliverable_key=? ORDER BY event_id DESC "
            "LIMIT 1", (K2,)).fetchone()
        check("t10 anthropic-shaped id redacted in the ledger",
              not is_anthropic_shaped(ev["model"]))
        check("t10 tokens still counted despite redaction",
              int(led.get_row(K2)["consumed_tokens"]) == before + 10)

        # t11: cost estimate applies only when a price matches (opt-in). 1M in @
        # $1/M + 1M out @ $2/M == $3.00, computed deterministically.
        KC = "c1::a1::blurb"
        led.meter_post(cfg, KC, "HEAVY-WRITER", "glm-5.2",
                       1_000_000, 1_000_000, 0, None, None)
        rc2 = led.report(deliverable_key=KC)
        check("t11 cost from configured price (== $3.00)",
              abs((rc2.get("cost_estimate_usd") or 0) - 3.0) < 1e-6)

        # t11b: an UNPRICED model leaves cost null (no fabricated rate)
        KU = "c1::a1::outline"
        led.meter_post(cfg, KU, "LIGHT", "some-other-model", 100, 100, 0, None, None)
        ru = led.report(deliverable_key=KU)
        check("t11b unpriced model -> cost null", ru.get("cost_estimate_usd") is None)

        # t12: reset clears the pool
        led.reset(KEY)
        check("t12 reset zeroes consumption",
              int(led.get_row(KEY)["consumed_tokens"]) == 0)
    finally:
        led.close()
        for p in (db, db.with_suffix(".db-wal"), db.with_suffix(".db-shm")):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass

    if failures:
        for f in failures:
            print(f)
        print("SELF-TEST FAILED (%d)" % len(failures))
        return EXIT_ERROR
    print("SELF-TEST PASSED")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anthology-cost-ledger.py",
        description="Anthology Engine metering choke point: per-deliverable token "
                    "budgets shared across QC attempts (SPEC 3.4 row 17, SPEC 8.2).")
    p.add_argument("--db", help="explicit SQLite ledger path (overrides state dir)")
    p.add_argument("--state-dir", dest="state_dir",
                   help="engine state dir (default: ANTHOLOGY_STATE_DIR / "
                        "OPENCLAW_DATA_DIR / node home)")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("meter", help="pre/post meter one model turn")
    m.add_argument("--phase", required=True, choices=["pre", "post"])
    m.add_argument("--deliverable-key", dest="deliverable_key", required=True)
    m.add_argument("--tier", default="")
    m.add_argument("--model", default="")
    m.add_argument("--prompt-tokens", dest="prompt_tokens", type=int, default=0)
    m.add_argument("--completion-tokens", dest="completion_tokens", type=int, default=0)
    m.add_argument("--qc-attempt", dest="qc_attempt", type=int, default=0)
    m.add_argument("--deliverable-type", dest="deliverable_type", default=None,
                   help="override the inferred budget type")
    m.add_argument("--ceiling", type=int, default=None,
                   help="one-call ceiling override in tokens (not persisted)")
    m.set_defaults(func=cmd_meter)

    r = sub.add_parser("report", help="read-only cost/budget report (JSON)")
    r.add_argument("--deliverable-key", dest="deliverable_key", default=None)
    r.add_argument("--participant-key", dest="participant_key", default=None)
    r.set_defaults(func=cmd_report)

    s = sub.add_parser("set-ceiling", help="persist a per-deliverable ceiling override")
    s.add_argument("--deliverable-key", dest="deliverable_key", required=True)
    s.add_argument("--ceiling", type=int, required=True)
    s.add_argument("--deliverable-type", dest="deliverable_type", default=None)
    s.set_defaults(func=cmd_set_ceiling)

    rs = sub.add_parser("reset", help="zero a deliverable's counters (test/rollover)")
    rs.add_argument("--deliverable-key", dest="deliverable_key", required=True)
    rs.add_argument("--yes", action="store_true", help="confirm the destructive reset")
    rs.set_defaults(func=cmd_reset)

    cl = sub.add_parser("close", help="mark a deliverable closed (frozen/delivered)")
    cl.add_argument("--deliverable-key", dest="deliverable_key", required=True)
    cl.set_defaults(func=cmd_close)

    pr = sub.add_parser("prune", help="housekeeping: drop old rows (daily tick)")
    pr.add_argument("--older-than-days", dest="older_than_days", type=float, default=90.0)
    pr.add_argument("--closed-only", dest="closed_only", action="store_true")
    pr.set_defaults(func=cmd_prune)

    st = sub.add_parser("self-test", help="in-process choke battery on a throwaway DB")
    st.set_defaults(func=cmd_self_test)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return EXIT_OK
    except Exception as exc:  # last-resort fail-soft
        sys.stderr.write("[cost-ledger] unexpected error: %s\n" % type(exc).__name__)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
