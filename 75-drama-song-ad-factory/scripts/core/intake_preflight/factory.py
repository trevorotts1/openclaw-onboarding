#!/usr/bin/env python3
"""factory.py: one CLI entrypoint, subcommands intake/preflight (directive 24.1).

Envelope (directive 24.4/line 2215): schema_version, tool_version, command,
run_id, outcome, reason_code, next_action, evidence, data, state_version.
Exit codes: ok 0, waiting 2, parked 3, rejected 4, error 1. stdlib only.
"""
import argparse
import json
import sys
import uuid

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
    TOOL_VERSION = "0.1.0"
    EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
else:
    _eval = _intake.evaluate
    _check = _preflight.check


def envelope(command, run_id, outcome, reason_code, next_action,
             data=None, evidence=None, state_version=None):
    return {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
            "command": command, "run_id": run_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or [], "data": data or {},
            "state_version": state_version or {"expected": None, "current": run_id}}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
                                                "untrusted_fields", "next_stage")},
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
               "summary_digest": a.summary_digest}
    try:
        r = _check(payload)
    except Exception as e:
        return envelope("preflight", run_id, "error", "preflight-failed", str(e)[:200])
    return envelope("preflight", run_id, r["outcome"], r["reason_code"], r["next_action"],
                    data={k: r.get(k) for k in ("checks", "missing", "outside")},
                    state_version={"expected": a.summary_digest, "current": run_id})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factory.py",
                                 description="Drama-song factory control CLI (intake/preflight).")
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
    a = ap.parse_args(argv)
    env = cmd_intake(a) if a.cmd == "intake" else cmd_preflight(a)
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[env["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
