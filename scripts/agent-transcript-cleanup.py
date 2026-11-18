#!/usr/bin/env python3
"""agent-transcript-cleanup.py - daily pruning of old session windows in every agent database.

WHY. Each agent keeps one SQLite database at
<OPENCLAW_HOME>/agents/<agent>/agent/openclaw-agent.sqlite. Every cron or automation run on a
session key opens a NEW row in session_windows (session_nodes only remembers the newest one in
current_session_id), and old windows plus all their events are never removed. A busy
orchestrator database reached 1.8 GB with 33,881 windows for 38 session keys, and OpenClaw's
own integrity check on open took 89 seconds. `openclaw sessions cleanup` never touches these
rows and no command exists to prune them. This script is that command.

WHAT IT DOES, per agent database, while the gateway stays live:
  1. Refuses (exit 2, no writes at all) when the schema is not one it was proven against:
     user_version must be in ALLOWED_USER_VERSIONS, and every table that has a foreign key to
     session_windows (or, recursively, to any table that cascades from it) must say
     ON DELETE CASCADE. The descendant list is discovered at run time from
     PRAGMA foreign_key_list, never hardcoded, so a future OpenClaw schema change fails closed.
  2. Builds the KEEP set (never deleted): every session_nodes.current_session_id, every
     session_conversations.session_id, every window touched in the last --keep-days (default 3), every window
     of a session key whose session_nodes row is running, windows of unknown age, and the
     previous_session_id of any of those (one hop only; following the whole chain would keep
     everything). Delete candidates are all other windows.
  3. For each batch of candidates: copies every row that the cascade is about to remove (the
     window, every cascading descendant, plus the full-text rows and their text) into a
     per-agent archive database, verifies the copied counts equal the selected counts, and only
     then deletes the batch with foreign_keys=ON in its own short transaction. Any mismatch
     aborts that database with nothing further deleted.
  4. Stops after --max-seconds (resumes the next day), then runs incremental_vacuum in steps
     and a PASSIVE WAL checkpoint so the file actually shrinks.

Disk safety: before writing anything it needs free space on the archive filesystem of at least
max(2 GB, 2 x the bytes it expects to archive); otherwise it logs "skipped: low disk" and exits 0 with
zero writes. At the start of each run it deletes that agent's archive files older than the previous
month (logging each one). The archive mirrors the source columns with no per-row bookkeeping and no
extra indexes, so it costs no more than the bytes it frees.

It never sends a chat message, never touches session_nodes, session_transcript_archives or any
memory table, and skips virtual tables it cannot introspect (the sqlite-vec vec0 table cannot be
loaded by plain python).

Exit: 0 = ran or nothing to do; 1 = error (nothing unsafe was done); 2 = refused.
Python 3 standard library only; safe under `python3 -I`.
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys
import time

ALLOWED_USER_VERSIONS = {27}
DB_RELPATH = os.path.join("agent", "openclaw-agent.sqlite")
ROOT_TABLE = "session_windows"
FTS_TABLE = "session_transcript_fts"
FTS_ROWS_TABLE = "session_transcript_fts_rows"
# Tables this script must never delete from, even through a cascade. Refusal if one is a descendant.
PROTECTED_TABLES = {"session_nodes", "session_transcript_archives"}
PROTECTED_PREFIXES = ("memory",)
REQUIRED_COLUMNS = {
    "session_windows": {"session_id", "session_key", "previous_session_id", "created_at",
                        "updated_at", "transcript_updated_at"},
    "session_nodes": {"session_key", "current_session_id", "status"},
    "session_conversations": {"session_id"},
}
DAY_MS = 86400 * 1000
MIN_FREE_BYTES = 2 << 30       # archive filesystem must have at least this much free ...
FREE_MULTIPLE = 2              # ... and at least this many times the bytes about to be archived
ARCHIVE_KEEP_MONTHS = 2        # current and previous month's archive file are kept; older ones are deleted
DEFAULT_KEEP_DAYS = 3  # a busy orchestrator opens ~650 windows a day; 14 days kept 9,046 of them
INTEGRITY_MAX_BYTES = 1 << 30  # skip the post-removal quick_check on a database over 1 GB
INTEGRITY_MAX_SECONDS = 60     # and never let it run longer than this
SECONDS_LOOKING_EPOCH_MS = 100_000_000_000  # below this a "ms" timestamp is really seconds: refuse
VACUUM_STEP_PAGES = 5000
VACUUM_GRACE_SECONDS = 60

_now = time.monotonic  # tests replace this


class Refusal(Exception):
    """The database is not one this script may touch. Nothing was written."""


class Abort(Exception):
    """A safety check failed mid-run. Nothing further was deleted."""


def q(name):
    return '"' + name.replace('"', '""') + '"'


# ---------------------------------------------------------------------------- locations

def candidate_agent_dirs(cli_home):
    """Where the agents directory may be, in order. OPENCLAW_HOME is the .openclaw directory on some
    boxes and its PARENT on others (lib-shared.sh exports the parent), so both shapes are tried."""
    if cli_home:
        return [os.path.join(cli_home, "agents"), os.path.join(cli_home, ".openclaw", "agents")]
    out = []
    state = os.environ.get("OPENCLAW_STATE_DIR")
    if state:
        out.append(os.path.join(state, "agents"))
    for var in ("OPENCLAW_HOME", "OC_ROOT"):
        v = os.environ.get(var)
        if v:
            out += [os.path.join(v, "agents"), os.path.join(v, ".openclaw", "agents")]
    out += [os.path.join(os.path.expanduser("~"), ".openclaw", "agents"), "/data/.openclaw/agents"]
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def resolve_roots(cli_home):
    """Returns (home, agents_dir, tried). home is the directory that holds agents/, archives/ and logs/."""
    tried = candidate_agent_dirs(cli_home)
    for d in tried:
        if os.path.isdir(d):
            return os.path.dirname(d), d, tried
    return None, None, tried


def find_agent_dbs(agents_dir, only_agent=None):
    base = agents_dir
    out = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for name in names:
        if only_agent and name != only_agent:
            continue
        db = os.path.join(base, name, DB_RELPATH)
        if os.path.isfile(db):
            out.append((name, db))
    return out


def chown_like(path, ref_stat):
    """Give a new file the owner of the source database when running as root."""
    try:
        if os.geteuid() == 0:
            os.chown(path, ref_stat.st_uid, ref_stat.st_gid)
    except (AttributeError, OSError):
        pass


def makedirs_like(path, ref_stat):
    missing = []
    p = path
    while p and not os.path.isdir(p):
        missing.append(p)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    for d in reversed(missing):
        os.mkdir(d, 0o700)
        chown_like(d, ref_stat)


# ---------------------------------------------------------------------------- schema discovery

def introspect(conn):
    """Return (tables, skipped). tables[name] = {cols, pk, fks, virtual}.

    Every per-table pragma is wrapped: a virtual table whose module cannot load (sqlite-vec vec0)
    raises here and is skipped, never touched."""
    tables, skipped = {}, []
    rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'").fetchall()
    for name, sql in rows:
        virtual = bool(sql) and sql.lstrip().upper().startswith("CREATE VIRTUAL")
        try:
            info = conn.execute("PRAGMA table_info(%s)" % q(name)).fetchall()
            fkl = [] if virtual else conn.execute("PRAGMA foreign_key_list(%s)" % q(name)).fetchall()
        except sqlite3.Error as exc:
            skipped.append({"table": name, "reason": str(exc)})
            continue
        pk = [r[1] for r in sorted((r for r in info if r[5] > 0), key=lambda r: r[5])]
        fks = {}
        for r in fkl:  # id, seq, table, from, to, on_update, on_delete, match
            f = fks.setdefault(r[0], {"parent": r[2], "from": [], "to": [], "on_delete": r[6]})
            f["from"].append(r[3])
            f["to"].append(r[4])
        tables[name] = {"cols": [r[1] for r in info], "types": {r[1]: r[2] for r in info},
                        "pk": pk, "fks": list(fks.values()), "virtual": virtual}
    return tables, skipped


def discover_descendants(tables):
    """Fixpoint over foreign keys. Returns ordered list of descendant table names (root first)
    and the edges used to select their rows. Raises Refusal on any unsafe shape."""
    if ROOT_TABLE not in tables:
        raise Refusal("%s table not found" % ROOT_TABLE)
    desc = [ROOT_TABLE]
    members = {ROOT_TABLE}
    changed = True
    while changed:
        changed = False
        for name, t in sorted(tables.items()):
            for fk in t["fks"]:
                if fk["parent"] in members:
                    if fk["on_delete"].upper() != "CASCADE":
                        raise Refusal("foreign key %s(%s) -> %s is ON DELETE %s, not CASCADE"
                                      % (name, ",".join(fk["from"]), fk["parent"], fk["on_delete"]))
                    if name == fk["parent"]:
                        raise Refusal("self-referencing cascade on %s is not supported" % name)
                    if name not in members:
                        members.add(name)
                        desc.append(name)
                        changed = True
    for name in desc:
        if name in PROTECTED_TABLES or name.startswith(PROTECTED_PREFIXES):
            raise Refusal("protected table %s would be removed by the cascade" % name)
    return desc


def parent_cols(tables, fk):
    to = [c for c in fk["to"] if c]
    if to and len(to) == len(fk["from"]):
        return to
    return tables[fk["parent"]]["pk"]


def where_for(tables, members, name, stack=()):
    """SQL WHERE (on table `name`) selecting exactly the rows the cascade removes for temp.oc_batch."""
    if name == ROOT_TABLE:
        return "session_id IN (SELECT session_id FROM temp.oc_batch)"
    parts = []
    for fk in tables[name]["fks"]:
        p = fk["parent"]
        if p not in members or p in stack or p == name:
            continue
        inner = where_for(tables, members, p, stack + (name,))
        if not inner:
            continue
        frm = ", ".join(q(c) for c in fk["from"])
        to = ", ".join(q(c) for c in parent_cols(tables, fk))
        parts.append("(%s) IN (SELECT %s FROM main.%s WHERE %s)" % (frm, to, q(p), inner))
    return " OR ".join(parts)


def check_schema(conn):
    """All refusal checks. Returns the plan dict. Writes nothing."""
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    if uv not in ALLOWED_USER_VERSIONS:
        raise Refusal("user_version %s is not in the allowlist %s"
                      % (uv, sorted(ALLOWED_USER_VERSIONS)))
    tables, skipped = introspect(conn)
    for tname, cols in REQUIRED_COLUMNS.items():
        if tname not in tables:
            raise Refusal("required table %s is missing" % tname)
        missing = cols - set(tables[tname]["cols"])
        if missing:
            raise Refusal("%s lacks required column(s) %s" % (tname, ",".join(sorted(missing))))
    desc = discover_descendants(tables)
    members = set(desc)
    fts_rows = tables.get(FTS_ROWS_TABLE)
    if fts_rows is not None and not {"id", "session_id"} <= set(fts_rows["cols"]):
        raise Refusal("%s lacks id/session_id columns" % FTS_ROWS_TABLE)
    fts_present = any(r[0] == FTS_TABLE for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE name=?", (FTS_TABLE,)))
    plan = {
        "user_version": uv, "tables": tables, "skipped": skipped, "desc": desc,
        "wheres": {n: where_for(tables, members, n) for n in desc},
        "fts_rows": fts_rows is not None, "fts_present": fts_present,
        "fts_cols": tables.get(FTS_TABLE, {}).get("cols") if FTS_TABLE in tables else None,
    }
    if fts_rows is not None and fts_present and plan["fts_cols"] is None:
        raise Refusal("%s exists but cannot be read (module missing); the delete trigger would fail"
                      % FTS_TABLE)
    for n in desc:
        if n != ROOT_TABLE and not plan["wheres"][n]:
            raise Refusal("cannot derive the row selection for %s" % n)
    # Informational: tables that carry a session_id but are outside the cascade (left untouched).
    plan["uncovered"] = sorted(n for n, t in tables.items()
                               if "session_id" in t["cols"] and n not in members
                               and n not in (FTS_ROWS_TABLE, FTS_TABLE)
                               and n not in PROTECTED_TABLES and not t["virtual"])
    return plan


# ---------------------------------------------------------------------------- keep / candidates

def _tmax(a):
    return ("max(coalesce(%s.created_at,0), coalesce(%s.updated_at,0), coalesce(%s.transcript_updated_at,0))"
            % (a, a, a))


def _kept0(a):
    return ("(%(t)s = 0 OR %(t)s > :cutoff"
            " OR %(a)s.session_id IN (SELECT current_session_id FROM main.session_nodes WHERE current_session_id IS NOT NULL)"
            " OR %(a)s.session_id IN (SELECT session_id FROM main.session_conversations WHERE session_id IS NOT NULL)"
            " OR EXISTS (SELECT 1 FROM main.session_nodes n WHERE n.session_key = %(a)s.session_key AND n.status = 'running'))"
            % {"a": a, "t": _tmax(a)})


def compute_candidates(conn, cutoff):
    """Fill temp.oc_cand with the window ids that may be deleted right now. Returns (candidates, kept)."""
    conn.execute("DROP TABLE IF EXISTS temp.oc_prot")
    conn.execute("DROP TABLE IF EXISTS temp.oc_cand")
    conn.execute("CREATE TEMP TABLE oc_prot (session_id TEXT PRIMARY KEY)")
    conn.execute("INSERT OR IGNORE INTO temp.oc_prot SELECT k.previous_session_id FROM main.session_windows k "
                 "WHERE k.previous_session_id IS NOT NULL AND " + _kept0("k"), {"cutoff": cutoff})
    conn.execute("CREATE TEMP TABLE oc_cand (session_id TEXT PRIMARY KEY, ord INTEGER)")
    conn.execute("INSERT OR IGNORE INTO temp.oc_cand SELECT w.session_id, "
                 "max(coalesce(w.created_at,0), coalesce(w.updated_at,0), coalesce(w.transcript_updated_at,0)) "
                 "FROM main.session_windows w WHERE NOT " + _kept0("w") +
                 " AND w.session_id NOT IN (SELECT session_id FROM temp.oc_prot)", {"cutoff": cutoff})
    cand = conn.execute("SELECT count(*) FROM temp.oc_cand").fetchone()[0]
    total = conn.execute("SELECT count(*) FROM main.session_windows").fetchone()[0]
    return cand, total - cand


def check_timestamp_units(conn):
    bad = conn.execute(
        "SELECT count(*) FROM main.session_windows w WHERE " + _tmax("w") + " > 0 AND " + _tmax("w") + " < ?",
        (SECONDS_LOOKING_EPOCH_MS,)).fetchone()[0]
    if bad:
        raise Refusal("%d window(s) carry timestamps that look like seconds, not epoch milliseconds" % bad)


# ---------------------------------------------------------------------------- archive

def _free_bytes(path):
    """Free bytes on the filesystem that holds `path` (nearest existing ancestor)."""
    p = os.path.abspath(path)
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    import shutil
    return shutil.disk_usage(p).free


def _month_stems(now=None):
    now = now or datetime.datetime.now()
    prev = (now.replace(day=1) - datetime.timedelta(days=1))
    return now.strftime("%Y-%m"), prev.strftime("%Y-%m")


def prune_archives(home, agent, dry=False):
    """Delete this agent's archive files older than the previous month. Returns the paths (to be) removed."""
    import re
    root = os.path.join(home, "archives", "agent-transcripts")
    d = os.path.join(root, agent)
    cur, prev = _month_stems()
    removed = []
    real_d = os.path.realpath(d)
    if os.path.islink(d) or not real_d.startswith(os.path.realpath(root) + os.sep):
        if os.path.lexists(d):
            write_log(home, "%s agent=%s archive retention skipped: %s is a symlink or resolves outside %s"
                      % (_stamp_now(), agent, d, root))
        return removed
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return removed
    for name in names:
        m = re.fullmatch(r"(\d{4}-\d{2})\.sqlite(-journal|-wal|-shm)?", name)
        if not m or m.group(1) >= prev:
            continue
        path = os.path.join(d, name)
        if not dry:
            try:
                os.remove(path)
            except OSError as exc:
                write_log(home, "%s agent=%s archive retention could not remove %s: %s"
                          % (_stamp_now(), agent, path, exc))
                continue
        removed.append(path)
    return removed


def _stamp_now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def archive_path(home, agent, ref_stat, stamp):
    d = os.path.join(home, "archives", "agent-transcripts", agent)
    makedirs_like(d, ref_stat)
    return os.path.join(d, stamp + ".sqlite")


def archive_tables(plan):
    """Every table the archive holds, each exactly once (fts_rows may or may not be a cascade table)."""
    names = list(plan["desc"])
    if plan["fts_rows"] and FTS_ROWS_TABLE not in names:
        names.append(FTS_ROWS_TABLE)
    return names


def ensure_archive_tables(conn, plan, page_size=None):
    """Create (or extend) the archive tables. Columns mirror the source exactly, with no extra per-row
    columns and no extra indexes, so the archive costs about what the rows cost in the source. Batch
    lineage lives in one small table (_archive_log) instead of two columns and an index on every table."""
    if page_size:
        try:
            conn.execute("PRAGMA arch.page_size=%d" % int(page_size))  # only takes effect on a new file
        except sqlite3.Error:
            pass
    tables = plan["tables"]
    for n in archive_tables(plan):
        _ensure_one(conn, n, tables[n]["cols"], tables[n]["types"])
    if plan["fts_rows"] and plan["fts_cols"] is not None:
        _ensure_one(conn, FTS_TABLE + "_text", ["rowid_src"] + plan["fts_cols"], {})
    conn.execute("CREATE TABLE IF NOT EXISTS arch._archive_log "
                 "(batch INTEGER, at INTEGER, tbl TEXT, first_rowid INTEGER, nrows INTEGER)")


def _ensure_one(conn, name, cols, types):
    have = {r[1] for r in conn.execute("PRAGMA arch.table_info(%s)" % q(name))}
    if not have:
        conn.execute("CREATE TABLE arch.%s (%s)" % (q(name), ", ".join(
            "%s %s" % (q(c), types.get(c, "") or "") for c in cols)))
        return
    for c in cols:
        if c not in have:
            conn.execute("ALTER TABLE arch.%s ADD COLUMN %s %s" % (q(name), q(c), types.get(c, "") or ""))


def _copy(conn, batch_id, now_ms, dest, dest_cols, select_exprs, src_table, where, label):
    """INSERT..SELECT one table's rows and prove selected == inserted == newly present (by rowid range)."""
    want = conn.execute("SELECT count(*) FROM main.%s WHERE %s" % (q(src_table), where)).fetchone()[0]
    base = conn.execute("SELECT coalesce(max(rowid), 0) FROM arch.%s" % q(dest)).fetchone()[0]
    cur = conn.execute("INSERT INTO arch.%s (%s) SELECT %s FROM main.%s WHERE %s"
                       % (q(dest), ", ".join(q(c) for c in dest_cols), select_exprs, q(src_table), where))
    got = conn.execute("SELECT count(*) FROM arch.%s WHERE rowid > ?" % q(dest), (base,)).fetchone()[0]
    if not (want == cur.rowcount == got):
        raise Abort("archive count mismatch on %s: selected %d, inserted %d, present %d"
                    % (label, want, cur.rowcount, got))
    conn.execute("INSERT INTO arch._archive_log VALUES (?,?,?,?,?)", (batch_id, now_ms, dest, base + 1, want))
    return want


def archive_batch(conn, plan, batch_id, now_ms):
    """Copy every row the cascade will delete. Returns {table: count}. Raises Abort on a mismatch."""
    tables, counts = plan["tables"], {}
    sel = "session_id IN (SELECT session_id FROM temp.oc_batch)"
    # Deferred BEGIN: this transaction only writes the archive file, so the live database is
    # read (snapshot) but never write-locked while rows are copied.
    conn.execute("BEGIN")
    try:
        for n in plan["desc"]:
            clist = ", ".join(q(c) for c in tables[n]["cols"])
            counts[n] = _copy(conn, batch_id, now_ms, n, tables[n]["cols"], clist, n, plan["wheres"][n], n)
        if plan["fts_rows"]:
            if FTS_ROWS_TABLE not in plan["desc"]:   # already copied above when it is a cascade table
                cols = tables[FTS_ROWS_TABLE]["cols"]
                counts[FTS_ROWS_TABLE] = _copy(conn, batch_id, now_ms, FTS_ROWS_TABLE, cols,
                                               ", ".join(q(c) for c in cols), FTS_ROWS_TABLE, sel, FTS_ROWS_TABLE)
            if plan["fts_cols"] is not None:
                fcols = plan["fts_cols"]
                src = "rowid IN (SELECT id FROM main.%s WHERE %s)" % (q(FTS_ROWS_TABLE), sel)
                counts[FTS_TABLE + "_text"] = _copy(
                    conn, batch_id, now_ms, FTS_TABLE + "_text", ["rowid_src"] + fcols,
                    "rowid, " + ", ".join(q(c) for c in fcols), FTS_TABLE, src, "fts text")
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return counts


def source_counts(conn, plan):
    out = {}
    for n in plan["desc"]:
        out[n] = conn.execute("SELECT count(*) FROM main.%s WHERE %s" % (q(n), plan["wheres"][n])).fetchone()[0]
    if plan["fts_rows"]:
        if FTS_ROWS_TABLE not in plan["desc"]:
            out[FTS_ROWS_TABLE] = conn.execute(
                "SELECT count(*) FROM main.%s WHERE session_id IN (SELECT session_id FROM temp.oc_batch)"
                % q(FTS_ROWS_TABLE)).fetchone()[0]
        if plan["fts_cols"] is not None:
            out[FTS_TABLE + "_text"] = conn.execute(
                "SELECT count(*) FROM main.%s WHERE rowid IN (SELECT id FROM main.%s WHERE "
                "session_id IN (SELECT session_id FROM temp.oc_batch))" % (q(FTS_TABLE), q(FTS_ROWS_TABLE))
            ).fetchone()[0]
    return out


# ---------------------------------------------------------------------------- per database run

def open_rw(path):
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def file_bytes(path):
    total = 0
    for suffix in ("", "-wal"):
        try:
            total += os.path.getsize(path + suffix)
        except OSError:
            pass
    return total


def integrity(conn, max_seconds=None):
    deadline = None if max_seconds is None else _now() + max_seconds
    if deadline is not None:
        # Abort the pragma from inside sqlite when the time cap passes.
        conn.set_progress_handler(lambda: 1 if _now() >= deadline else 0, 1000)
    try:
        rows = conn.execute("PRAGMA quick_check(1)").fetchall()
    except sqlite3.Error as exc:
        if "interrupt" in str(exc).lower():
            return "integrity check skipped (time cap %ss)" % max_seconds
        return "integrity check skipped (vec0)"
    finally:
        if deadline is not None:
            conn.set_progress_handler(None, 0)
    return "ok" if rows and rows[0][0] == "ok" else "FAILED: %s" % (rows[0][0] if rows else "no result")


def process_db(agent, dbpath, home, opts):
    res = {"agent": agent, "db": dbpath, "status": "ok", "candidates": 0, "kept": 0,
           "windows_removed": 0, "archived_rows": 0, "batches": 0, "stopped_early": False,
           "before_bytes": file_bytes(dbpath), "after_bytes": None, "pages_vacuumed": 0,
           "archive": None, "integrity": None, "detail": ""}
    ref_stat = os.stat(dbpath)
    start = _now()
    deadline = start + opts.max_seconds
    cutoff = int(time.time() * 1000) - int(opts.keep_days * DAY_MS)
    dry = opts.dry_run
    if dry:
        conn = sqlite3.connect("file:%s?mode=ro" % dbpath, uri=True, timeout=15, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=15000")
    else:
        conn = open_rw(dbpath)
    try:
        plan = check_schema(conn)
        res["skipped_virtual"] = [s["table"] for s in plan["skipped"]]
        res["uncovered_session_id_tables"] = plan["uncovered"]
        check_timestamp_units(conn)
        res["cascade_tables"] = plan["desc"]
        cand, kept = compute_candidates(conn, cutoff)
        res["candidates"], res["kept"] = cand, kept
        if dry:
            total_windows = cand + kept
            est = int(res["before_bytes"] * (cand / total_windows)) if total_windows else 0
            res["estimated_archive_bytes"] = est
            res["required_free_bytes"] = max(MIN_FREE_BYTES, FREE_MULTIPLE * est)
            res["free_bytes"] = _free_bytes(os.path.join(home, "archives"))
            res["would_skip_low_disk"] = cand > 0 and res["free_bytes"] < res["required_free_bytes"]
            conn.execute("CREATE TEMP TABLE oc_batch AS SELECT session_id FROM temp.oc_cand")
            res["would_remove_rows"] = source_counts(conn, plan)
            res["integrity"] = "not run (dry run)"
            res["after_bytes"] = res["before_bytes"]
            return res
        total_windows = cand + kept
        est = int(res["before_bytes"] * (cand / total_windows)) if total_windows else 0
        need = max(MIN_FREE_BYTES, FREE_MULTIPLE * est)
        free = _free_bytes(os.path.join(home, "archives"))
        res["estimated_archive_bytes"], res["required_free_bytes"], res["free_bytes"] = est, need, free
        if cand > 0 and free < need:
            res["status"] = "skipped"
            res["detail"] = "skipped: low disk (free %d bytes, need %d)" % (free, need)
            res["after_bytes"] = res["before_bytes"]
            return res
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise Abort("could not enable foreign_keys; refusing to delete")
        stamp = datetime.datetime.now().strftime("%Y-%m")
        removed_total, archived_total = 0, 0
        arch = None
        retries = 0
        while cand > 0:
            if _now() >= deadline:
                res["stopped_early"] = True
                break
            conn.execute("DROP TABLE IF EXISTS temp.oc_batch")
            conn.execute("CREATE TEMP TABLE oc_batch (session_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO temp.oc_batch SELECT session_id FROM temp.oc_cand "
                         "ORDER BY ord, session_id LIMIT ?", (opts.batch,))
            n_batch = conn.execute("SELECT count(*) FROM temp.oc_batch").fetchone()[0]
            if n_batch == 0:
                break
            if arch is None:
                arch = archive_path(home, agent, ref_stat, stamp)
                existed = os.path.exists(arch)
                conn.execute("ATTACH DATABASE ? AS arch", (arch,))
                conn.execute("PRAGMA arch.synchronous=FULL")
                ensure_archive_tables(conn, plan, conn.execute("PRAGMA main.page_size").fetchone()[0]
                                      if not existed else None)
                if not existed:
                    try:
                        os.chmod(arch, ref_stat.st_mode & 0o777)
                    except OSError:
                        pass
                chown_like(arch, ref_stat)
                res["archive"] = arch
            batch_id = res["batches"] + 1 + conn.execute(
                "SELECT coalesce(max(batch), 0) FROM arch._archive_log").fetchone()[0]
            counts = archive_batch(conn, plan, batch_id, int(time.time() * 1000))
            chown_like(arch, ref_stat)
            # Delete phase: one short write transaction. Re-evaluate KEEP inside it.
            conn.execute("BEGIN IMMEDIATE")
            try:
                compute_candidates(conn, cutoff)
                dropped = conn.execute("DELETE FROM temp.oc_batch WHERE session_id NOT IN "
                                       "(SELECT session_id FROM temp.oc_cand)").rowcount
                if dropped:
                    conn.execute("ROLLBACK")
                    retries += 1
                    if retries > 5:
                        raise Abort("windows keep changing under the cleanup; stopping for today")
                    cand, kept = _recount(conn, cutoff)
                    continue
                again = source_counts(conn, plan)
                if again != counts:
                    raise Abort("rows changed between archive and delete: archived %s, now %s" % (counts, again))
                if plan["fts_rows"]:
                    conn.execute("DELETE FROM main.%s WHERE session_id IN (SELECT session_id FROM temp.oc_batch)"
                                 % q(FTS_ROWS_TABLE))
                deleted = conn.execute("DELETE FROM main.%s WHERE session_id IN (SELECT session_id FROM temp.oc_batch)"
                                       % q(ROOT_TABLE)).rowcount
                if deleted != n_batch:
                    raise Abort("deleted %d windows, expected %d" % (deleted, n_batch))
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            removed_total += deleted
            archived_total += sum(counts.values())
            res["batches"] += 1
            res["windows_removed"] = removed_total
            res["archived_rows"] = archived_total
            cand, kept = _recount(conn, cutoff)
        res["candidates_remaining"] = cand
        # Vacuum: give the freed pages back, in steps, with a small grace beyond the delete budget.
        pre_vacuum_bytes = file_bytes(dbpath)
        res["pages_vacuumed"] = vacuum(conn, opts.vacuum_pages, deadline + VACUUM_GRACE_SECONDS)
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
        except sqlite3.Error:
            pass
        if not removed_total:
            res["integrity"] = "not run (nothing removed)"
        elif pre_vacuum_bytes > INTEGRITY_MAX_BYTES:
            res["integrity"] = "integrity check skipped (database over 1 GB before vacuum)"
        else:
            res["integrity"] = integrity(conn, INTEGRITY_MAX_SECONDS)
        if res["integrity"].startswith("FAILED"):
            res["status"] = "error"
            res["detail"] = res["integrity"]
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    res["after_bytes"] = file_bytes(dbpath)
    return res


def _recount(conn, cutoff):
    cand, kept = compute_candidates(conn, cutoff)
    return cand, kept


def vacuum(conn, max_pages, deadline):
    mode = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    if mode != 2:
        return 0
    done = 0
    while done < max_pages:
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        if free <= 0:
            break
        if done and _now() >= deadline:
            break
        step = min(VACUUM_STEP_PAGES, max_pages - done, free)
        conn.execute("PRAGMA incremental_vacuum(%d)" % step).fetchall()
        done += step
    return done


# ---------------------------------------------------------------------------- driver

def main(argv=None):
    ap = argparse.ArgumentParser(description="Prune old session windows from every agent database.")
    ap.add_argument("--home", help="OpenClaw home (default: OPENCLAW_HOME, OC_ROOT, /data/.openclaw, ~/.openclaw)")
    ap.add_argument("--agent", help="only this agent id")
    ap.add_argument("--keep-days", type=float, default=DEFAULT_KEEP_DAYS)
    ap.add_argument("--batch", type=int, default=200, help="windows deleted per transaction")
    ap.add_argument("--max-seconds", type=float, default=300)
    ap.add_argument("--vacuum-pages", type=int, default=50000)
    ap.add_argument("--dry-run", action="store_true", help="report only; no writes, no archive, no log")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    opts = ap.parse_args(argv)
    if opts.batch < 1 or opts.keep_days < 0 or opts.max_seconds < 0:
        print("invalid option value", file=sys.stderr)
        return 2
    quiet = opts.quiet or os.environ.get("OPENCLAW_MAINTENANCE") == "1" \
        or os.environ.get("OPENCLAW_MAINTENANCE_SILENT") == "1"
    home, agents_dir, tried = resolve_roots(opts.home)
    if agents_dir is None:
        msg = "no agent databases found at %s" % ", ".join(tried)
        print(json.dumps({"status": "none", "detail": msg}) if opts.json else msg)  # even in quiet mode
        return 0
    dbs = find_agent_dbs(agents_dir, opts.agent)
    if not dbs:
        msg = "no agent databases found at %s" % ", ".join(tried)
        print(json.dumps({"status": "none", "detail": msg}) if opts.json else msg)
        return 0
    results, worst = [], 0
    lock_fh = None
    if not opts.dry_run:
        try:
            lock_fh = acquire_lock(home, os.stat(dbs[0][1]))
        except OSError as exc:
            msg = "ERROR: cannot open or lock %s: %s" % (os.path.join(home, "logs", LOCK_NAME), exc)
            print(msg, file=sys.stderr)
            write_log(home, "%s agent=* status=ERROR detail=%s" % (_stamp_now(), msg), dbs[0][1])
            return 1
        if lock_fh is False:
            msg = "another agent-transcript-cleanup run holds the lock; nothing to do"
            print(json.dumps({"status": "locked", "detail": msg}) if opts.json else msg)
            return 0
    for agent, db in dbs:
        retention = []
        try:
            retention = prune_archives(home, agent, dry=opts.dry_run)
            for path in retention:
                if not opts.dry_run:
                    write_log(home, "%s agent=%s archive retention removed %s" % (_stamp_now(), agent, path), db)
            r = process_db(agent, db, home, opts)
            if r["status"] == "error":
                worst = max(worst, 1)
        except Refusal as exc:
            r = {"agent": agent, "db": db, "status": "refused", "detail": str(exc)}
            worst = max(worst, 2)
        except (Abort, sqlite3.Error, OSError) as exc:
            r = {"agent": agent, "db": db, "status": "error", "detail": "%s: %s" % (type(exc).__name__, exc)}
            worst = max(worst, 1)
        r["archive_retention_removed" if not opts.dry_run else "archive_retention_would_remove"] = retention
        results.append(r)
        if not opts.dry_run:
            write_log(home, summary_line(r), db)
    if lock_fh:
        lock_fh.close()
    if opts.json:
        print(json.dumps({"home": home, "dry_run": opts.dry_run, "agents": results}, indent=1, default=str))
    elif not quiet or worst:
        for r in results:
            print(summary_line(r))
    return worst


def summary_line(r):
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    if r["status"] in ("refused", "error", "skipped"):
        return "%s agent=%s status=%s detail=%s" % (ts, r["agent"], r["status"].upper(), r["detail"])
    return ("%s agent=%s status=%s before_bytes=%s after_bytes=%s windows_removed=%s archived_rows=%s "
            "candidates=%s kept=%s batches=%s stopped_early=%s pages_vacuumed=%s integrity=%s%s"
            % (ts, r["agent"], r["status"], r["before_bytes"], r["after_bytes"], r["windows_removed"],
               r["archived_rows"], r["candidates"], r["kept"], r["batches"], r["stopped_early"],
               r["pages_vacuumed"], r["integrity"], " dry_run" if r["integrity"] == "not run (dry run)" else ""))


LOCK_NAME = "agent-transcript-cleanup.lock"


def acquire_lock(home, ref_stat=None):
    """Returns the open lock file, or False ONLY when another process really holds the flock.
    Any open/permission failure raises OSError so the caller reports it loudly."""
    try:
        import fcntl
    except ImportError:
        return None
    d = os.path.join(home, "logs")
    if ref_stat is not None:
        makedirs_like(d, ref_stat)
    else:
        os.makedirs(d, exist_ok=True)
    path = os.path.join(d, LOCK_NAME)
    fh = open(path, "a+")
    if ref_stat is not None:
        chown_like(path, ref_stat)
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return False
    except OSError:
        fh.close()
        raise
    return fh


def write_log(home, line, db=None):
    try:
        d = os.path.join(home, "logs")
        ref = os.stat(db) if db else None
        if ref is not None:
            makedirs_like(d, ref)
        else:
            os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "agent-transcript-cleanup.log")
        with open(path, "a") as fh:
            fh.write(line + "\n")
        if ref is not None:
            chown_like(path, ref)
    except OSError as exc:
        print("ERROR: cannot write %s: %s" % (os.path.join(home, "logs", "agent-transcript-cleanup.log"), exc),
              file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
