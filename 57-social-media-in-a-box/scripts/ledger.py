#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: LOCAL SQLITE LEDGER
# -----------------------------------------------------------------------------
# Replaces the n8n data tables (Clients_BCEO + carousel image ledgers). NO n8n
# runtime dependency anywhere: state is a local SQLite file (stdlib sqlite3).
# One row per slide/media job; status transitions (pending -> generating ->
# qc -> complete | failed | timeout). The carousel fan-out drives 10 slides
# (9 LinkedIn) with a 30s poll and a >=10-complete or 120-poll timeout; the
# assembly floor is >=2 completed images (PRD 4.3 / 6). The ledger + manifest
# survive session limits: any mode can resume from ledger state.
#
# Every fail/timeout branch is expected to alert the configured channel; the
# ledger records the terminal state so the orchestrator can detect an
# unhandled/incomplete job (AF-SM-MEDIA-LEDGER).
#
# EXIT: 0 OK / 2 FLOOR-VIOLATION (assemble asserted with <2 images) / 3 USAGE.
# USAGE:
#   python3 ledger.py init   --db PATH --run RUN
#   python3 ledger.py add    --db PATH --run RUN --kind carousel-slide --slot 1
#   python3 ledger.py status --db PATH --id N --set complete --url URL
#   python3 ledger.py summary --db PATH --run RUN [--assert-floor N] [--json]
#   python3 ledger.py --self-test
# =============================================================================
"""Local SQLite media/carousel job ledger for Social Media in a Box (Skill 57)."""

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK = 0
EXIT_FLOOR = 2
EXIT_DOUBLE = 2  # AF-SM-DOUBLE-POST (same fail-closed exit as a floor violation)
EXIT_USAGE = 3

AF_DOUBLE = "AF-SM-DOUBLE-POST"
DEFAULT_LOOKBACK_DAYS = 90

TERMINAL = ("complete", "failed", "timeout")
STATES = ("pending", "generating", "qc", "edit", "complete", "failed", "timeout")
POLL_SECONDS = 30
POLL_TIMEOUT = 120
CAROUSEL_COMPLETE_TARGET = 10
ASSEMBLE_FLOOR = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  slot INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  url TEXT,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_run ON jobs(run_id);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  scheduled_slot TEXT,
  run_id TEXT NOT NULL,
  mode TEXT,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_loc ON posts(location_id, platform);
"""


def connect(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def init_db(db, run):
    con = connect(db)
    con.commit()
    con.close()
    return {"db": str(db), "run": run, "initialized": True}


def add_job(db, run, kind, slot=None, task_id=None):
    con = connect(db)
    cur = con.execute(
        "INSERT INTO jobs(run_id, kind, slot, status, task_id, updated_at) VALUES(?,?,?,?,?,?)",
        (run, kind, slot, "pending", task_id, time.time()))
    con.commit()
    jid = cur.lastrowid
    con.close()
    return jid


def set_status(db, job_id, status, url=None, note=None, bump_attempts=False):
    if status not in STATES:
        raise ValueError("unknown status %r" % status)
    con = connect(db)
    row = con.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        con.close()
        raise KeyError("no job %s" % job_id)
    attempts = row["attempts"] + (1 if bump_attempts else 0)
    con.execute("UPDATE jobs SET status=?, url=COALESCE(?,url), note=COALESCE(?,note), "
                "attempts=?, updated_at=? WHERE id=?",
                (status, url, note, attempts, time.time(), job_id))
    con.commit()
    con.close()
    return True


def summarize(db, run):
    con = connect(db)
    rows = con.execute("SELECT status, url FROM jobs WHERE run_id=?", (run,)).fetchall()
    con.close()
    total = len(rows)
    by = {s: 0 for s in STATES}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    complete = by.get("complete", 0)
    images_ready = sum(1 for r in rows if r["status"] == "complete" and (r["url"] or "").strip())
    pending = sum(by.get(s, 0) for s in STATES if s not in TERMINAL)
    return {
        "run": run, "total": total, "by_status": by,
        "complete": complete, "images_ready": images_ready, "pending": pending,
        "all_terminal": pending == 0 and total > 0,
        "assemble_ok": images_ready >= ASSEMBLE_FLOOR,
        "poll_seconds": POLL_SECONDS, "poll_timeout": POLL_TIMEOUT,
        "carousel_target": CAROUSEL_COMPLETE_TARGET,
    }


# =============================================================================
# §4.4 NO-DOUBLE-POST — content-fingerprint de-dup (AF-SM-DOUBLE-POST)
# -----------------------------------------------------------------------------
# Creative modes RAISE double-post risk (a reactive post colliding with the
# scheduled series; a client-copy post duplicating a queued one; an override
# re-run re-posting a day). De-dup is a NAMED fail-closed prover, not an emergent
# property. For each outgoing post:
#   (a) same (platform, content_sha256) already posted/scheduled within the
#       lookback window  -> BLOCK
#   (b) same (platform, scheduled_slot) already occupied by ANOTHER run's post
#       -> BLOCK with a labeled report (which run holds the slot)
#   (c) reconciled against the LIVE GHL post-listing (independent, not just the
#       local ledger - a re-imaged box must not double-post)
#   (d) a client's DELIBERATE identical re-post goes through ONLY via a logged
#       owner-approved re-post token (recorded on the certificate). The client CAN
#       re-post identically by saying so; the engine never does it by accident.
# =============================================================================
def record_post(db, location_id, platform, content_sha, slot=None, run_id="", mode=None):
    con = connect(db)
    con.execute("INSERT INTO posts(location_id, platform, content_sha256, scheduled_slot, "
                "run_id, mode, created_at) VALUES(?,?,?,?,?,?,?)",
                (location_id, platform, content_sha, slot, run_id, mode, time.time()))
    con.commit()
    con.close()
    return True


def _token_ok(token):
    if not isinstance(token, dict):
        return False
    return (token.get("approved") is True or token.get("owner_approved") is True) \
        and str(token.get("approved_by", "")).strip() and str(token.get("reason", "")).strip()


def check_dedup(db, location_id, platform, content_sha, slot=None, run_id="",
                lookback_days=DEFAULT_LOOKBACK_DAYS, live_listing=None, repost_token=None):
    """Return (blocks, cleared_by_token). blocks is a list of (code, message)."""
    blocks = []
    con = connect(db)
    cutoff = time.time() - (lookback_days * 86400)
    dup = con.execute(
        "SELECT run_id, created_at FROM posts WHERE location_id=? AND platform=? "
        "AND content_sha256=? AND created_at>=?",
        (location_id, platform, content_sha, cutoff)).fetchone()
    if dup is not None:
        blocks.append((AF_DOUBLE, "identical content already posted/scheduled for %s within %d days "
                       "(held by run %s)" % (platform, lookback_days, dup["run_id"])))
    if slot:
        occ = con.execute(
            "SELECT run_id FROM posts WHERE location_id=? AND platform=? AND scheduled_slot=? "
            "AND run_id!=?", (location_id, platform, slot, run_id)).fetchone()
        if occ is not None:
            blocks.append((AF_DOUBLE, "slot %s on %s already occupied by run %s (clean or reschedule)"
                           % (slot, platform, occ["run_id"])))
    con.close()
    # (c) reconcile against the live GHL post-listing (independent of the ledger)
    if isinstance(live_listing, list):
        for p in live_listing:
            if not isinstance(p, dict) or str(p.get("platform", "")) != platform:
                continue
            if p.get("content_sha256") == content_sha:
                blocks.append((AF_DOUBLE, "live GHL listing already has this content on %s" % platform))
            elif slot and str(p.get("scheduled_slot", "")) == str(slot):
                blocks.append((AF_DOUBLE, "live GHL listing already occupies slot %s on %s" % (slot, platform)))
    # (d) a logged owner-approved re-post token is the ONLY path through
    if blocks and _token_ok(repost_token):
        return blocks, True
    return blocks, False


def check_dedup_snapshot(existing, outgoing, lookback_days=DEFAULT_LOOKBACK_DAYS,
                         live_listing=None, repost_token=None):
    """Fixture-friendly, DB-free variant of check_dedup over an in-memory ledger
    snapshot (used by the P7 de-dup gate + the golden-week broken-variant). `existing`
    is a list of already posted/scheduled records {platform, content_sha256,
    scheduled_slot, run_id, age_days}; `outgoing` is the list of posts this run wants to
    publish {platform, content_sha256, scheduled_slot, run_id}. Returns
    (blocks, cleared_by_token)."""
    blocks = []
    existing = existing if isinstance(existing, list) else []
    for out in (outgoing if isinstance(outgoing, list) else []):
        if not isinstance(out, dict):
            continue
        plat = str(out.get("platform", ""))
        sha = out.get("content_sha256")
        slot = out.get("scheduled_slot")
        rid = str(out.get("run_id", ""))
        for ex in existing:
            if not isinstance(ex, dict) or str(ex.get("platform", "")) != plat:
                continue
            age = ex.get("age_days", 0)
            if ex.get("content_sha256") == sha and (not isinstance(age, (int, float)) or age <= lookback_days):
                blocks.append((AF_DOUBLE, "identical content already posted/scheduled for %s within %d "
                               "days (held by run %s)" % (plat, lookback_days, ex.get("run_id"))))
            elif slot and str(ex.get("scheduled_slot", "")) == str(slot) and str(ex.get("run_id", "")) != rid:
                blocks.append((AF_DOUBLE, "slot %s on %s already occupied by run %s (clean or reschedule)"
                               % (slot, plat, ex.get("run_id"))))
        for p in (live_listing if isinstance(live_listing, list) else []):
            if not isinstance(p, dict) or str(p.get("platform", "")) != plat:
                continue
            if p.get("content_sha256") == sha:
                blocks.append((AF_DOUBLE, "live GHL listing already has this content on %s" % plat))
            elif slot and str(p.get("scheduled_slot", "")) == str(slot):
                blocks.append((AF_DOUBLE, "live GHL listing already occupies slot %s on %s" % (slot, plat)))
    if blocks and _token_ok(repost_token):
        return blocks, True
    return blocks, False


def _emit(summary, as_json):
    if as_json:
        print(json.dumps(summary, indent=2))
        return
    print("== Social Media in a Box :: media ledger summary ==")
    print("run: %s  total: %d  complete: %d  images_ready: %d  pending: %d"
          % (summary["run"], summary["total"], summary["complete"],
             summary["images_ready"], summary["pending"]))
    print("all_terminal: %s  assemble_ok(>=%d): %s"
          % (summary["all_terminal"], ASSEMBLE_FLOOR, summary["assemble_ok"]))


# =============================================================================
# SELF-TEST — temp DB; drive 10 slides through states; check floor logic.
# =============================================================================
def self_test():
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="smib-ledger-")) / "ledger.db"
    run = "brand-one_2026-W27"
    init_db(tmp, run)

    ids = [add_job(tmp, run, "carousel-slide", slot=i) for i in range(1, 11)]
    ok = ok and (len(ids) == 10)
    print("  [%s] created 10 slide jobs" % ("PASS" if len(ids) == 10 else "MISS"))

    # 8 complete with urls, 1 failed, 1 timeout
    for i, jid in enumerate(ids, 1):
        if i <= 8:
            set_status(tmp, jid, "complete", url="https://cdn.example/%d.png" % i)
        elif i == 9:
            set_status(tmp, jid, "failed", note="qc-fail-after-fallback")
        else:
            set_status(tmp, jid, "timeout", note="120-poll timeout")

    s = summarize(tmp, run)
    checks = [
        ("total==10", s["total"] == 10),
        ("images_ready==8", s["images_ready"] == 8),
        ("all_terminal", s["all_terminal"] is True),
        ("assemble_ok(>=2)", s["assemble_ok"] is True),
        ("complete==8", s["complete"] == 8),
    ]
    for name, good in checks:
        ok = ok and good
        print("  [%s] %s" % ("PASS" if good else "MISS", name))

    # floor violation: a run with only 1 completed image must NOT assemble
    run2 = "brand-one_floorcheck"
    j = add_job(tmp, run2, "carousel-slide", slot=1)
    set_status(tmp, j, "complete", url="https://cdn.example/only.png")
    for k in range(2, 11):
        jj = add_job(tmp, run2, "carousel-slide", slot=k)
        set_status(tmp, jj, "failed", note="x")
    s2 = summarize(tmp, run2)
    good = s2["assemble_ok"] is False and s2["images_ready"] == 1
    ok = ok and good
    print("  [%s] floor-violation blocks assembly (1 image, assemble_ok False)" % ("PASS" if good else "MISS"))

    # incomplete run (a pending job left) -> all_terminal False (AF-SM-MEDIA-LEDGER trigger)
    run3 = "brand-one_incomplete"
    add_job(tmp, run3, "carousel-slide", slot=1)  # left pending
    s3 = summarize(tmp, run3)
    good = s3["all_terminal"] is False and s3["pending"] == 1
    ok = ok and good
    print("  [%s] incomplete run detected (pending job, all_terminal False)" % ("PASS" if good else "MISS"))

    # §4.4 de-dup snapshot: clean, dup-content, occupied-slot, live-listing, token-clear
    print("== self-test: AF-SM-DOUBLE-POST (de-dup) ==")
    existing = [{"platform": "facebook", "content_sha256": "aaa", "scheduled_slot": "2026-W27-Sun-10:00",
                 "run_id": "r1", "age_days": 3}]
    clean, _ = check_dedup_snapshot(existing, [{"platform": "facebook", "content_sha256": "zzz",
                                                "scheduled_slot": "2026-W27-Mon-10:00", "run_id": "r2"}])
    good = not clean
    ok = ok and good
    print("  [%s] distinct content + free slot -> CLEAR" % ("PASS" if good else "MISS"))
    dup, _ = check_dedup_snapshot(existing, [{"platform": "facebook", "content_sha256": "aaa",
                                              "scheduled_slot": "x", "run_id": "r2"}])
    good = any(c == AF_DOUBLE for c, _ in dup)
    ok = ok and good
    print("  [%s] identical content -> BLOCK (AF-SM-DOUBLE-POST)" % ("PASS" if good else "MISS"))
    occ, _ = check_dedup_snapshot(existing, [{"platform": "facebook", "content_sha256": "yyy",
                                 "scheduled_slot": "2026-W27-Sun-10:00", "run_id": "r2"}])
    good = any(c == AF_DOUBLE for c, _ in occ)
    ok = ok and good
    print("  [%s] occupied slot -> BLOCK (AF-SM-DOUBLE-POST)" % ("PASS" if good else "MISS"))
    live = [{"platform": "instagram", "content_sha256": "bbb", "scheduled_slot": "s"}]
    lv, _ = check_dedup_snapshot([], [{"platform": "instagram", "content_sha256": "bbb",
                                       "scheduled_slot": "s2", "run_id": "r2"}], live_listing=live)
    good = any(c == AF_DOUBLE for c, _ in lv)
    ok = ok and good
    print("  [%s] live GHL listing dup -> BLOCK (AF-SM-DOUBLE-POST)" % ("PASS" if good else "MISS"))
    tok = {"approved": True, "approved_by": "owner", "reason": "deliberate identical re-post"}
    blk, cleared = check_dedup_snapshot(existing, [{"platform": "facebook", "content_sha256": "aaa",
                                        "scheduled_slot": "x", "run_id": "r2"}], repost_token=tok)
    good = bool(blk) and cleared is True
    ok = ok and good
    print("  [%s] logged owner re-post token -> CLEARED" % ("PASS" if good else "MISS"))

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local SQLite media/carousel ledger (Skill 57).")
    ap.add_argument("cmd", nargs="?", choices=("init", "add", "status", "summary", "record",
                                               "dedup", "dedup-snapshot"))
    ap.add_argument("--input", help="dedup-snapshot: path to a JSON {existing,outgoing,lookback_days,live_listing,repost_token}")
    ap.add_argument("--db")
    ap.add_argument("--run")
    ap.add_argument("--kind", default="carousel-slide")
    ap.add_argument("--slot", type=int)
    ap.add_argument("--id", type=int)
    ap.add_argument("--set", dest="new_status", choices=STATES)
    ap.add_argument("--url")
    ap.add_argument("--note")
    ap.add_argument("--assert-floor", type=int)
    ap.add_argument("--location")
    ap.add_argument("--platform")
    ap.add_argument("--sha")
    ap.add_argument("--post-slot", dest="post_slot")
    ap.add_argument("--mode")
    ap.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    ap.add_argument("--live-listing", help="path to a JSON array of live GHL posts")
    ap.add_argument("--repost-token", help="path to a JSON owner-approved re-post token")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a command is required (init|add|status|summary|record|dedup|dedup-snapshot) or --self-test")

    if args.cmd == "dedup-snapshot":
        if not args.input or not Path(args.input).is_file():
            ap.error("dedup-snapshot needs --input FILE")
        try:
            snap = json.loads(Path(args.input).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("FATAL: cannot read --input: %s" % exc, file=sys.stderr)
            return EXIT_USAGE
        blocks, cleared = check_dedup_snapshot(
            snap.get("existing"), snap.get("outgoing"),
            lookback_days=snap.get("lookback_days", DEFAULT_LOOKBACK_DAYS),
            live_listing=snap.get("live_listing"), repost_token=snap.get("repost_token"))
        if args.json:
            print(json.dumps({"gate": "social-media-dedup", "pass": not blocks or cleared,
                              "cleared_by_token": cleared,
                              "failures": [{"code": c, "message": m} for c, m in blocks]}, indent=2))
        elif not blocks:
            print("DEDUP: clear (no duplicate content or occupied slot)")
        elif cleared:
            print("DEDUP: %d collision(s) CLEARED by a logged owner re-post token" % len(blocks))
        else:
            print("DEDUP: BLOCKED (fail-closed) — %d collision(s):" % len(blocks))
            for c, m in blocks:
                print("  [%s] %s" % (c, m))
        return EXIT_OK if (not blocks or cleared) else EXIT_DOUBLE

    if not args.db:
        ap.error("--db is required")

    if args.cmd == "init":
        if not args.run:
            ap.error("init needs --run")
        print(json.dumps(init_db(args.db, args.run)))
        return EXIT_OK
    if args.cmd == "add":
        if not args.run:
            ap.error("add needs --run")
        print(json.dumps({"id": add_job(args.db, args.run, args.kind, args.slot)}))
        return EXIT_OK
    if args.cmd == "status":
        if not args.id or not args.new_status:
            ap.error("status needs --id and --set")
        set_status(args.db, args.id, args.new_status, url=args.url, note=args.note,
                   bump_attempts=args.new_status in ("generating", "edit"))
        print(json.dumps({"id": args.id, "status": args.new_status}))
        return EXIT_OK
    if args.cmd == "summary":
        if not args.run:
            ap.error("summary needs --run")
        s = summarize(args.db, args.run)
        _emit(s, args.json)
        floor = args.assert_floor if args.assert_floor is not None else None
        if floor is not None and s["images_ready"] < floor:
            print("FLOOR VIOLATION: %d images ready, need >= %d (AF-SM-CAROUSEL-FLOOR)"
                  % (s["images_ready"], floor), file=sys.stderr)
            return EXIT_FLOOR
        return EXIT_OK
    if args.cmd == "record":
        if not (args.location and args.platform and args.sha):
            ap.error("record needs --location --platform --sha")
        record_post(args.db, args.location, args.platform, args.sha,
                    slot=args.post_slot, run_id=args.run or "", mode=args.mode)
        print(json.dumps({"recorded": True, "platform": args.platform}))
        return EXIT_OK
    if args.cmd == "dedup":
        if not (args.location and args.platform and args.sha):
            ap.error("dedup needs --location --platform --sha")
        live = None
        if args.live_listing and Path(args.live_listing).is_file():
            try:
                live = json.loads(Path(args.live_listing).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                live = None
        token = None
        if args.repost_token and Path(args.repost_token).is_file():
            try:
                token = json.loads(Path(args.repost_token).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                token = None
        blocks, cleared = check_dedup(args.db, args.location, args.platform, args.sha,
                                      slot=args.post_slot, run_id=args.run or "",
                                      lookback_days=args.lookback_days, live_listing=live,
                                      repost_token=token)
        if args.json:
            print(json.dumps({"gate": "social-media-dedup", "pass": not blocks or cleared,
                              "cleared_by_token": cleared,
                              "failures": [{"code": c, "message": m} for c, m in blocks]}, indent=2))
        else:
            if not blocks:
                print("DEDUP: clear (no duplicate content or occupied slot)")
            elif cleared:
                print("DEDUP: %d collision(s) CLEARED by a logged owner re-post token" % len(blocks))
            else:
                print("DEDUP: BLOCKED (fail-closed) — %d collision(s):" % len(blocks))
                for c, m in blocks:
                    print("  [%s] %s" % (c, m))
        return EXIT_OK if (not blocks or cleared) else EXIT_DOUBLE
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
