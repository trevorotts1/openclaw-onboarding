#!/usr/bin/env python3
"""factory.py: one CLI entrypoint, subcommands intake/preflight/next.

Envelope (directive 24.4/line 2215): schema_version, tool_version, command,
run_id, outcome, reason_code, next_action, evidence, data, state_version.
Exit codes: ok 0, waiting 2, parked 3, rejected 4, error 1. stdlib only.

`next` (manual 02 B1) reads the run's control/state.sqlite3 through
state_store.py and answers one question: which stage is next and what exact
command runs it. It prints the same envelope as intake/preflight (outcome
ok/error; waiting/parked/rejected never come out of `next`) and exits 0/1.

Stage IDs come from batch_mode.batch.STAGES verbatim (never a second list).
Command lines come from references/stage-runbook.md, parsed from its stage |
command | produces table. Lane counts come from scripts/core/lane_size.py
when that module is importable; otherwise the Part D fallback defaults below
are used (agents >= 1, kie_inflight <= 8, one machine-sized ffmpeg pool).

No automatic runner: the agent loops next -> run the command -> register ->
next (manual B1 step 5).
"""
import argparse
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path

try:
    from . import EXIT, SCHEMA_VERSION, TOOL_VERSION
    from . import intake as _intake
    from . import preflight as _preflight
except ImportError:  # direct script run: python3 factory.py ...
    import intake as _intake  # type: ignore
    import preflight as _preflight  # type: ignore
    _eval = _intake.evaluate
    _check = _preflight.check
    SCHEMA_VERSION = "blackceo.intake-preflight/envelope/v1"
    TOOL_VERSION = "0.2.0"
    EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
else:
    _eval = _intake.evaluate
    _check = _preflight.check

try:  # W2-A-U1's module, when the box has it; else Part D fallback below.
    from .. import lane_size as _lane_size
except Exception:  # noqa: BLE001 - package-or-module missing: try sibling
    try:
        _core = Path(__file__).resolve().parent.parent
        if str(_core) not in sys.path:
            sys.path.insert(0, str(_core))
        import lane_size as _lane_size_mod  # type: ignore
        _lane_size = _lane_size_mod
    except Exception:  # noqa: BLE001 - module missing: fallback stays
        _lane_size = None

#: Part D fallback when lane_size.py is not importable (W2-A-U1 not landed).
#: Same constants a live lane_size exposes; agents floor 1, never 0.
PART_D_DEFAULTS = {"agents": 1, "kie_inflight": 8, "ffmpeg_jobs": 1,
                   "ffmpeg_threads": 1, "source": "part_d_defaults"}


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def envelope(command, run_id, outcome, reason_code, next_action,
             data=None, evidence=None, state_version=None):
    return {"schema_version": SCHEMA_VERSION.replace(
                "intake-preflight", "intake-preflight", 1),
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "outcome": outcome, "reason_code": reason_code,
            "next_action": next_action, "evidence": evidence or [],
            "data": data or {},
            "state_version": state_version
            or {"expected": None, "current": run_id}}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def limit_from(doc):
    """Dollars (str) from a brief or intake summary/envelope, or None. Minor units,
    USD only (or no currency named); anything else is left for the client to type."""
    if not isinstance(doc, dict):
        return None
    doc = ((doc.get("data") or {}).get("summary") or doc.get("summary") or doc)
    ceil = doc.get("generation_ceiling") or {}
    minor = doc.get("budget_minor", doc.get("budget_amount_minor", ceil.get("amount_minor")))
    cur = str(doc.get("budget_currency") or doc.get("currency") or ceil.get("currency") or "usd").lower()
    if not isinstance(minor, int) or isinstance(minor, bool) or minor <= 0 or cur != "usd":
        return None
    return "%d.%02d" % divmod(minor, 100)


def cmd_intake(a):
    brief = _load(a.brief_file) if a.brief_file else json.loads(a.brief or "{}")
    settings = _load(a.settings_file) if a.settings_file else {}
    resume = _load(a.resume_file) if a.resume_file else None
    run_id = a.run_id or uuid.uuid4().hex[:12]
    try:
        r = _eval(brief, settings, resume, run_id)
    except Exception as e:
        return envelope("intake", run_id, "error", "intake-failed", str(e)[:200])
    return envelope("intake", run_id, r["outcome"], r["reason_code"], r["next_action"],
                    data={k: r.get(k) for k in ("questions", "question_message", "summary",
                                                "digest", "provenance", "auth_status",
                                                "approval_invalidated", "changes",
                                                "untrusted_fields", "next_stage", "mode", "notices")},
                    state_version={"expected": (resume or {}).get("digest") if resume else None,
                                   "current": r.get("digest")})


def cmd_preflight(a):
    run_id = a.run_id or uuid.uuid4().hex[:12]
    payload = {"tools": a.require_tool or [], "modules": a.require_module or [],
               "storage_dir": a.storage_dir, "min_free_bytes": a.min_free_bytes,
               "approved_root": a.root, "references": a.ref or [],
               "profile": a.profile, "allowed_profiles": json.loads(a.allowed_profiles or "[]") or None,
               "schema_version": a.schema_version,
               "allowed_schemas": json.loads(a.allowed_schemas or "[]") or None,
               "credentials": a.credential or [], "auth": _load(a.auth_file) if a.auth_file else None,
               "summary_digest": a.summary_digest,
               "run_state": _load(a.run_state_file) if a.run_state_file else None,
               "card_receipt": _load(a.card_receipt_file) if a.card_receipt_file else None}
    try:
        r = _check(payload)
    except Exception as e:
        return envelope("preflight", run_id, "error", "preflight-failed", str(e)[:200])
    return envelope("preflight", run_id, r["outcome"], r["reason_code"], r["next_action"],
                    data={k: r.get(k) for k in ("checks", "missing", "outside")},
                    state_version={"expected": a.summary_digest, "current": run_id})


# ── B1: the "what next" command ──────────────────────────────────────────────

#: Stage order, read from batch_mode/batch.py (never a second copy).
def _stages():
    try:
        from .batch_mode import batch as batch_mod   # package import
    except ImportError:
        core = None
        try:
            core = Path2 = __import__("pathlib").Path(__file__).resolve().parent.parent
            if str(core) not in sys.path:
                sys.path.insert(0, str(core))
            from batch_mode import batch as batch_mod  # type: ignore  # noqa: PLC0415
        except Exception:                              # noqa: BLE001
            return None
    return tuple(sid for sid, _title in batch_mod.STAGES)


def _runbook_rows():
    """{stage_id: {"command":…, "produces":…}} from references/stage-runbook.md.

    Table format (W2-A-U3): lines starting with '|' whose first cell matches a
    stage id win; the header/separator rows do not.
    """
    ref = Path(__file__).resolve()
    skill_root = ref.parent.parent.parent.parent   # core/intake_preflight -> skill root
    md = skill_root / "references" / "stage-runbook.md"
    rows = {}
    text = None
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return rows, str(md)
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        sid = cells[0]
        # U3's table: the command cell is wrapped in backticks; produces is
        # free prose. Header ("stage id") and separator ("---") never match.
        if re.fullmatch(r"[a-z0-9-]+", sid) and (
                cells[1].startswith("`") and cells[1].endswith("`")
                and cells[2]):
            rows[sid] = {"command": cells[1][1:-1],
                         "produces": cells[2]}
    return rows, str(md)


def lane_size_payload():
    """One sizing payload. Live module when importable; else Part D defaults."""
    if _lane_size is not None:
        try:
            line = _lane_size.size("claude-code", "openrouter")
            return {"agents": line["agents"],
                    "kie_inflight": line["kie_inflight"],
                    "ffmpeg_jobs": line["ffmpeg_jobs"],
                    "ffmpeg_threads": line["ffmpeg_threads"],
                    "source": "lane_size.module"}
        except Exception as exc:  # noqa: BLE001 - broken module: fall through
            _loud("warn", "LANE_SIZE_BROKEN",
                  "using Part D default lane sizes: %r" % (exc,))
    out = dict(PART_D_DEFAULTS)
    out["source"] = "part_d_defaults"
    return out


def cmd_next(a):
    """next --run-dir <dir>: which stage, which command, how many lanes."""
    run_dir = Path(a.run_dir or ".").expanduser().resolve()
    db = run_dir / "control" / "state.sqlite3"
    sid = run_dir.name or "run"
    if not db.exists():
        env = envelope("next", str(sid), "error", "state-file-missing",
                       "Create the run first (factory.py intake, then "
                       "preflight); missing state file: %s" % db)
        env["data"] = {"missing_path": str(db)}
        evidence = None
        return env
    stages = _stages()
    if not stages:
        return envelope("next", str(sid), "error", "stage-list-unavailable",
                        "Could not read stage IDs from batch_mode/batch.py.")
    stages_source = "batch_mode STAGES (batch_mode/batch.py:112-125)"
    rows, runbook_path = _runbook_rows()
    # Read-only projection of the store: states already say what is eligible.
    try:
        import sqlite3
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=10)
        try:
            got = dict(con.execute(
                "SELECT stage, state FROM stages ORDER BY rowid").fetchall())
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return envelope("next", str(sid), "error", "state-unreadable",
                        "state file unreadable (%s): %s" % (db, str(e)[:120]))
    blocked = ("COMPLETE", "FAILED_BLOCKED", "PARKED")
    next_stage = None
    for s in stages:
        st = got.get(s)
        if st is None:                    # stage not initialized: still ahead
            next_stage = s
            break
        if st not in blocked:
            next_stage = s
            break
    if next_stage is None:
        return envelope("next", str(sid), "ok", "run-complete",
                        "Every stage is COMPLETE; the run is delivered. "
                        "Nothing left to run.")
    row = rows.get(next_stage) or {"command": "", "produces": ""}
    if not row["command"]:
        return envelope("next", str(sid), "error", "runbook-row-missing",
                        "No runbook row for stage %r in %s"
                        % (next_stage, runbook_path))
    lane = lane_size_payload()
    nxt = {"stage": next_stage, "command": row["command"],
           "produces": row.get("produces", ""), "lane_size": lane,
           "stages_source": stages_source}
    return envelope("next", str(sid), "ok", "next-stage",
                    "Run this command for stage %r; after it passes its QC "
                    "gate, run `next` again." % next_stage,
                    data=nxt, evidence=["%s" % db, runbook_path])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factory.py",
                                 description="Drama-song factory control CLI (intake/preflight/next).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("intake", help="Normalize brief, batch <=3 missing essentials.")
    i.add_argument("--brief", default=None, help="Brief as JSON string.")
    i.add_argument("--brief-file", default=None)
    i.add_argument("--settings-file", default=None)
    i.add_argument("--resume-file", default=None)
    i.add_argument("--run-id", default=None)
    p = sub.add_parser("preflight", help="NAMES-only dependency/auth checks; never generates.")
    p.add_argument("--run-id", default=None)
    p.add_argument("--root", default=None, help="Approved storage root.")
    p.add_argument("--storage-dir", default=None)
    p.add_argument("--ref", action="append", default=None)
    p.add_argument("--require-tool", action="append", default=None)
    p.add_argument("--require-module", action="append", default=None)
    p.add_argument("--profile", default=_preflight.DEFAULT_PROFILES[0],
                   help="Delivery profile; default is the version-2 "
                        "drama-9x16-60s (see preflight.DEFAULT_PROFILES).")
    p.add_argument("--allowed-profiles", default=None)
    p.add_argument("--schema-version", default="blackceo.campaign/v1")
    p.add_argument("--allowed-schemas", default=None)
    p.add_argument("--credential", action="append", default=None)
    p.add_argument("--auth-file", default=None)
    p.add_argument("--summary-digest", default=None)
    p.add_argument("--min-free-bytes", type=int, default=0)
    p.add_argument("--run-state-file", default=None,
                   help="Run-state JSON; must carry the recorded F15 choice-"
                        "card receipt before any paid job.")
    p.add_argument("--card-receipt-file", default=None,
                   help="The recorded choice-card receipt (answers, who, at); "
                        "overrides the run-state record.")
    n = sub.add_parser("next", help="Which stage is next, its exact command, and "
                                    "how many lanes may run (manual 02 B1).")
    n.add_argument("--run-dir", required=True,
                   help="Run dir that holds control/state.sqlite3.")
    c = sub.add_parser("card", help="Print the six-question intake card as raw "
                                    "text (not JSON), or as send payloads (H9).")
    c.add_argument("--format", default="text",
                   choices=("text", "openclaw-json", "telegram-json"))
    c.add_argument("--target", default="", help="Telegram chat id")
    c.add_argument("--client-dir", default="",
                   help="Client data folder; adds the saved-character question when it has saved characters (I6).")
    c.add_argument("--run-state-file", default="",
                   help="with --step and no replies: first call sends the one-time intro, next call question 1")
    c.add_argument("--price", default=None, help="card total in dollars, shown in the spend question")
    c.add_argument("--limit", default=None, help="spend limit in dollars; overrides the one found in the brief or summary")
    c.add_argument("--brief", default=None, help="Brief as JSON string; its budget_minor becomes spend option 1.")
    c.add_argument("--brief-file", default=None, help="Brief JSON file (or the planner's); same.")
    c.add_argument("--summary-file", default=None,
                   help="intake output (envelope or summary) JSON; its generation_ceiling becomes spend option 1.")
    c.add_argument("--step", action="store_true",
                   help="one question per message (I7): print only the next message")
    c.add_argument("--reply", action="append", default=[],
                   help="a client reply so far, in order (repeat the flag)")
    c.add_argument("--fit", action="store_true",
                   help="FU-U4: the fit STOP card for the client's own lines "
                        "(--brief-file, --packet-file); exit 2 when they do not fit")
    c.add_argument("--packet-file", default=None,
                   help="JSON list of client lines {id, speaker, text, scene}")
    ch = sub.add_parser("character", help="Per-client character library: ask / save / "
                                          "list / use / card (Part I, I6). Extra args pass through.")
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["character"]:      # own parser; passes --client-dir etc. through
        a = argparse.Namespace(cmd="character", rest=args[1:])
    else:
        a = ap.parse_args(argv)
    if a.cmd == "character":
        import os
        core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if core not in sys.path:
            sys.path.insert(0, core)
        from character_library import character_library as _cl  # noqa: PLC0415
        return _cl.main(a.rest)
    if a.cmd == "card":
        import os
        core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if core not in sys.path:
            sys.path.insert(0, core)
        from choice_card.intake_card import intake_card as _card  # noqa: PLC0415
        if a.fit:
            brief = _load(a.brief_file) if a.brief_file else {}
            packet = _load(a.packet_file) if a.packet_file else brief.get("packet_lines")
            card = _card.fit_card(brief, packet)
            sys.stdout.write(card["text"] + "\n")
            return EXIT[card["outcome"]]
        limit, from_brief = a.limit, False
        for doc in ((_load(a.summary_file) if a.summary_file else None),
                    (_load(a.brief_file) if a.brief_file else json.loads(a.brief) if a.brief else None)):
            if not limit:
                limit = limit_from(doc)
                from_brief = bool(limit)
        return _card.main(["--format", a.format, "--target", a.target]
                          + (["--client-dir", a.client_dir] if a.client_dir else [])
                          + (["--price", a.price] if a.price else [])
                          + (["--limit", limit] if limit else [])
                          + (["--limit-from-brief"] if limit and from_brief else [])
                          + (["--step"] if a.step else [])
                          + (["--run-state-file", a.run_state_file] if a.run_state_file else [])
                          + [x for r in a.reply for x in ("--reply", r)])
    if a.cmd == "intake":
        env = cmd_intake(a)
    elif a.cmd == "preflight":
        env = cmd_preflight(a)
    else:
        env = cmd_next(a)
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[env["outcome"]]


if __name__ == "__main__":
    sys.exit(main())