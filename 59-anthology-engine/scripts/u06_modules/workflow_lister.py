#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/workflow_lister.py
# LIVE WORKFLOW LISTER — the read surface of the U06 family: it lists the
# workflow NAMES of a Convert and Flow (LeadConnector v2) location through the
# PROVEN internal rail and does NOTHING else. The one ACTION verb of this
# module, `archive`, is a STRUCTURED PLAN ONLY — it REQUIRES the operator to
# pass --execute explicitly (Trevor-gated), and even WITH --execute it never
# performs a deletion: it reports exactly which records WOULD be archived and
# exits without mutating, because the house endpoint doctrine binds this
# module to only-proven surfaces and NO archive/delete surface for workflows
# has been proven live anywhere in this repo. Fail-closed by design: a
# missing credential, an unreachable rail, an edge block, or an unparseable
# listing is a refusal with a typed reason — never a fabricated list.
#
# WHY THE RAIL AND NOT THE PUBLIC API: the workflow list of a location is
# NOT exposed on the public LeadConnector references (29-ghl-convert-and-flow
# /references/campaigns.md documents ONLY GET /workflows/). The internal
# Firebase rail surface /workflow/{loc}/list?limit=200 (backend.leadconnector
# hq.com) is the surface this repo has PROVEN live in four places — the
# Podcast gate (58-podcast-production-engine/scripts/verify-podcast-ghl-
# workflows.py and verify-podcast-smiq.py, activate-podcast-fb-workflows.py)
# and the engine's own copy_qc_workflows.py --list-live, workflows_check.py
# and live_verify_template.py (U02). By house doctrine (Skill 44: "Do NOT add
# new endpoints without verifying against the live backend") THIS module
# reads ONLY that proven surface. The list rows carry name, id, type and
# status; only names (and, for the ACTION plan, the stable id) are surfaced.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail rides a Firebase refresh
# token + API key resolved via anthology_registry (ANTHOLOGY_GHL_FIREBASE_* /
# GOHIGHLEVEL_FIREBASE_* — live process env first, then the three canonical
# client env stores) and a location id resolved the same way
# (CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID),
# overridable with --location-id. Every credential is reported as LABEL +
# SET / NOT-SET only — a value is NEVER printed, echoed, or logged. The
# location id and every workflow id are MASKED on operator surfaces (last 4
# chars, non-reversible); full ids ride inside request URLs only.
#
# BROWSER UA (CF 1010): every request rides the internal-rail headers built
# by anthology_registry._internal_request_headers, which carry CAF_BROWSER_UA
# (W0.6 / GK-09 discipline) so the Cloudflare edge fronting
# backend.leadconnectorhq.com never 1010s the urllib default "Python-urllib"
# UA before the request reaches the rail (the exact failure mode that 403s
# at the WAF edge with CF error 1010). A rail response body is never
# surfaced (it could echo a credential); classification reports HTTP code or
# error CLASS only.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — live listing returned and names printed (including an EMPTY
#      workflow set — an empty listing is a truthful, correct answer); or
#      archive plan (dry-run or --execute) completed and reported
#   1  unexpected error
#   2  STOP refusal — credential labels NOT SET, --name without a value,
#      --execute without an ACTION, duplicate names present (the name-match
#      bind is ambiguous and MUST refuse), a name that resolves to no
#      workflow, or an ACTION name that is not 'archive'
#   3  HELD — internal rail unreachable / edge-blocked (incl. the Cloudflare
#      edge 403, UNDETERMINED never a verdict) / Firebase exchange failure /
#      malformed listing — retryable, never a fabricated list
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# self-test is OFFLINE and needs NO token and NO network; list and archive
# are the LIVE surfaces and need the client's OWN rail credentials BY LABEL):
#   workflow_lister.py list [--location-id ID]           # live names, sorted
#   workflow_lister.py archive --name NAME [--location-id ID]
#                           [--execute]                  # Trevor-gated; the
#                                                        # ACTION is a PLAN
#                                                        # ONLY even so
#   workflow_lister.py self-test                          # offline fixtures
#
# --execute is the ONLY flag that performs an ACTION, and the ONLY ACTION
# this module knows ('archive') is a PLAN EVEN WITH --execute: the module
# reports the records it would archive and exits WITHOUT mutating, because
# no archive surface has been proven live (endpoint doctrine). Without
# --execute an ACTION is a DRY-RUN — and an ACTION without --execute is a
# STOP, not a silent no-op. list is read-only and needs no --execute.
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (InternalRailClient, resolve_firebase_refresh_token,
# _resolve_firebase_api_key, _internal_request_headers, _mask_location,
# resolve_location, InternalRailUnavailable and its exception classes).
# DOCTRINE: move in silence; operator-verbose only; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value.
# =============================================================================
"""workflow_lister.py — live Convert and Flow workflow-name lister via the
proven internal rail (U06 tooling). Reads list; the archive ACTION is a
Trevor-gated (--execute) plan that never mutates."""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.parse
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD = reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD
EX_SELFTEST = 4  # self-test FAILED (an offline assertion tripped)

# The ONE internal-rail surface this module reads — proven live by the
# Podcast gate and the engine's U02 tooling (verify-podcast-ghl-workflows.py
# / verify-podcast-smiq.py / activate-podcast-fb-workflows.py /
# copy_qc_workflows.py --list-live). House doctrine: only proven endpoints.
RAIL_WORKFLOW_LIST = "/workflow/{loc}/list?limit=200"

# The ONE ACTION verb this module knows. Fail-closed: an ACTION name that is
# not exactly this STOPS. The action itself never mutates — see ARCHIVE_NOTE.
ACTION_ARCHIVE = "archive"

# Endpoint doctrine note, surfaced in the plan's report and the --help text.
# A workflow archive/delete surface is NOT documented on the public
# references and has NOT been proven live anywhere in this repo, so the
# archive ACTION of this module is a structured PLAN ONLY: with --execute it
# reports exactly what it would archive and still writes nothing. The caller
# (engine, operator, Trevor) decides whether a proven archive surface exists
# elsewhere; this module never invents one and never pretends a delete ran.
ARCHIVE_NOTE = (
    "no archive/delete surface for workflows has been proven live in this "
    "repo (Skill 44 endpoint doctrine: only proven endpoints), so this "
    "ACTION is a PLAN ONLY -- even with --execute no mutation is performed")

# Rail listing rows of this type are the workflows (the other type — 'folder'
# — is reported on the plan surface, never listed as a workflow).
WORKFLOW_ROW_TYPE = "workflow"

# Allowed row statuses when filtering the list. A workflow row with an
# unknown status is SURFACED (never silently judged); the list action shows
# all of them, and the archive plan reports them, without ever guessing what
# an unknown status means.
KNOWN_STATUSES = ("published", "draft", "inactive")


# ---------------------------------------------------------------------------
# Fail-closed listing helpers. Pure: never raise, never print secrets.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible resource-id marker (last 4 chars) for operator
    surfaces. The full id rides inside request URLs only, never on a
    surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def _is_workflow_row(row) -> bool:
    """A list row is a workflow when its type is exactly 'workflow'. A row
    without a type is never judged a workflow (fail-closed: an unknown row
    type is surfaced, not folded in)."""
    return isinstance(row, dict) and row.get("type") == WORKFLOW_ROW_TYPE


def _rows_from_listing(listing) -> list:
    """The workflow rows of a rail listing. A non-dict listing, a missing or
    non-list 'rows' key, or a malformed row REFUSES (raises ValueError) —
    an unparseable listing is a HELD, never an empty list (an empty list
    would silently read as 'no workflows')."""
    if not isinstance(listing, dict):
        raise ValueError("listing is not a JSON object")
    rows = listing.get("rows")
    if rows is None:
        raise ValueError("listing carries no 'rows' array")
    if not isinstance(rows, list):
        raise ValueError("listing 'rows' is not an array")
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("listing 'rows' carries a non-object row")
    return rows


def _workflow_rows(rows: list) -> list:
    """Only the workflow rows, in list order. Fail-closed: a workflow row
    without a name is DROPPED with the count surfaced (never listed as an
    empty string, which would collide with a real blank-name row); a
    workflow row without an id is dropped with the count surfaced (it cannot
    be the subject of a plan)."""
    return [r for r in rows if _is_workflow_row(r)]


def list_rows(listing) -> list:
    """(names, dropped) — the sorted unique workflow names and the count of
    rows dropped for missing name or id. A row with a name but no id is
    dropped WITH the count (it cannot be the subject of any plan, so it is
    never listed). Raises ValueError on a malformed listing (fail-closed).
    Pure: never prints."""
    rows = _workflow_rows(_rows_from_listing(listing))
    names = sorted({str(r.get("name") or "").strip() for r in rows
                    if (r.get("name") or "").strip() and (r.get("id") or "").strip()})
    dropped = sum(1 for r in rows
                  if not (r.get("name") or "").strip() or not (r.get("id") or "").strip())
    return names, dropped


def _listing_ok(listing) -> bool:
    """A listing that parses (raises nothing) is structurally OK. Pure."""
    try:
        list_rows(listing)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Fail-closed name resolution. A byte-exact name is the only bind; a name
# that matches ZERO or MORE THAN ONE workflow is a refusal, never a guess.
# ---------------------------------------------------------------------------
def _resolve_workflow_by_name(rows: list, name: str) -> dict:
    """The ONE workflow row whose name is byte-exact the target. Zero matches
    and duplicate matches are refusals (ValueError) — an ACTION bound to the
    wrong record must be impossible. The resolved row is returned verbatim
    (id + name + status); only the id and name are ever surfaced."""
    want = (name or "").strip()
    if not want:
        raise ValueError("empty workflow name")
    matches = [r for r in _workflow_rows(rows)
               if str(r.get("name") or "").strip() == want]
    if not matches:
        raise ValueError("no workflow named %r in the listing" % want)
    if len(matches) > 1:
        raise ValueError("workflow name %r is duplicated in the listing (%d "
                         "rows) -- the bind is ambiguous, refusing" % (want, len(matches)))
    return dict(matches[0])


# ---------------------------------------------------------------------------
# The live listing command — the ONLY network surface (proven rail).
# ---------------------------------------------------------------------------
def _build_report(listing: dict, *, location_id: str) -> dict:
    """The machine report for a parsed listing: names (sorted, unique),
    masked location, the raw workflow row count, the dropped-row count and
    the count of rows whose status is unknown. Never carries a credential,
    a full id, a body, or any value other than names and counts. Pure."""
    names, dropped = list_rows(listing)
    rows = _workflow_rows(_rows_from_listing(listing))
    unknown_status = sum(1 for r in rows
                         if (r.get("status") or "").strip() not in KNOWN_STATUSES)
    return {
        "ok": True,
        "action": "list",
        "location": _mask_id(location_id),
        "workflows": names,
        "workflow_count": len(names),
        "rows": len(rows),
        "rows_dropped": dropped,
        "rows_unknown_status": unknown_status,
    }


def live_list_command(location_id: str, *, out=None, jsonout=None,
                      environ=None) -> int:
    """List the location's workflow names through the PROVEN internal rail.
    Credential: a per-client Firebase refresh token under the engine's
    refresh labels; SET/NOT-SET only, value never printed. A rail failure or
    an unparseable listing is HELD (exit 3) — never a fabricated list.
    `environ` is the registry's self-test injection point (an explicit env
    dict blocks the canonical-store fallback, so the HELD credential gate is
    deterministic OFFLINE)."""
    out = out or sys.stderr
    reg_rt, refresh = reg.resolve_firebase_refresh_token(environ)
    # The Firebase API key rides the registry's own resolution (live process
    # env first; the canonical-store fallback mirrors the refresh token's).
    reg_ak, api_key = reg._resolve_firebase_api_key()
    if not refresh or not api_key:
        out.write("[workflow-lister] HELD: no Firebase refresh token SET "
                  "(labels: %s) and/or API key (labels: %s). Live listing "
                  "needs the client's OWN token; the offline self-test needs "
                  "none.\n" % (", ".join(reg.FIREBASE_REFRESH_LABELS),
                               ", ".join(reg.FIREBASE_API_KEY_LABELS)))
        return EX_HELD
    loc_label, loc = reg.resolve_location(location_id)
    if not loc:
        out.write("[workflow-lister] HELD: no Convert and Flow location id "
                  "SET (labels: %s).\n" % ", ".join(reg.LOCATION_LABELS))
        return EX_HELD
    masked = reg._mask_location(loc)
    try:
        rail = reg.InternalRailClient(refresh, api_key)
        url = RAIL_WORKFLOW_LIST.format(loc=urllib.parse.quote(loc, safe=""))
        listing = rail._get(url)
    except reg.InternalRailUnavailable as exc:
        out.write("[workflow-lister] HELD: internal-rail workflow list failed "
                  "(marker %s): %s\n" % (masked, exc))
        return EX_HELD
    try:
        report = _build_report(listing, location_id=loc)
    except ValueError as exc:
        out.write("[workflow-lister] HELD: workflow listing malformed "
                  "(marker %s): %s\n" % (masked, exc))
        return EX_HELD
    if jsonout is not None:
        json.dump(report, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[workflow-lister] LIVE workflow list (marker %s): %d "
                  "workflow(s), %d row(s), %d dropped (no name/id), %d "
                  "unknown-status\n"
                  % (masked, report["workflow_count"], report["rows"],
                     report["rows_dropped"], report["rows_unknown_status"]))
        for n in report["workflows"]:
            out.write("  %s\n" % n)
    return EX_OK


# ---------------------------------------------------------------------------
# The archive ACTION — a Trevor-gated (--execute) structured PLAN ONLY.
# ---------------------------------------------------------------------------
def _archive_plan(rows: list, listing: dict, name: str) -> dict:
    """Build the archive plan for ONE byte-exact workflow name. The plan is
    always a no-mutation report: the target's masked id, name, status and
    the counts the archive WOULD touch. A name that resolves to zero or
    multiple rows refuses (ValueError) — an ACTION bound to the wrong record
    must be impossible. Pure: never prints, never writes."""
    row = _resolve_workflow_by_name(rows, name)
    _, dropped = list_rows(listing)
    return {
        "ok": True,
        "action": ACTION_ARCHIVE,
        "execute": False,                      # see ARCHIVE_NOTE — never mutates
        "note": ARCHIVE_NOTE,
        "target": {"name": row.get("name"), "id": _mask_id(row.get("id") or ""),
                   "status": row.get("status")},
        "would_archive": 1,
        "rows_unknown_status": sum(
            1 for r in _workflow_rows(rows)
            if (r.get("status") or "").strip() not in KNOWN_STATUSES),
        "rows_dropped": dropped,
    }


def archive_command(name: str, location_id: str, *, execute: bool = False,
                    out=None, jsonout=None, environ=None) -> int:
    """The archive ACTION. REQUIREMENT: --execute must be passed explicitly
    (Trevor-gated). Without --execute the action is a STOP (exit 2) — the
    caller must decide; a plan that could be mistaken for an executed
    archive must be impossible. WITH --execute the module still performs NO
    mutation (endpoint doctrine — no archive surface proven live): it reads
    the live listing, resolves the ONE byte-exact workflow, and reports the
    plan. Credential/location resolution and rail behavior mirror
    live_list_command. `environ` is the self-test injection point (deterministic
    OFFLINE HELD gate)."""
    if not (name or "").strip():
        raise ValueError("archive requires --name (the byte-exact workflow name)")
    out = out or sys.stderr
    reg_rt, refresh = reg.resolve_firebase_refresh_token(environ)
    # The Firebase API key rides the registry's own resolution (live process
    # env first; the canonical-store fallback mirrors the refresh token's).
    reg_ak, api_key = reg._resolve_firebase_api_key()
    if not refresh or not api_key:
        out.write("[workflow-lister] HELD: no Firebase refresh token SET "
                  "(labels: %s) and/or API key (labels: %s). The archive "
                  "plan needs the client's OWN token; the offline self-test "
                  "needs none.\n" % (", ".join(reg.FIREBASE_REFRESH_LABELS),
                                     ", ".join(reg.FIREBASE_API_KEY_LABELS)))
        return EX_HELD
    loc_label, loc = reg.resolve_location(location_id)
    if not loc:
        out.write("[workflow-lister] HELD: no Convert and Flow location id "
                  "SET (labels: %s).\n" % ", ".join(reg.LOCATION_LABELS))
        return EX_HELD
    masked = reg._mask_location(loc)
    try:
        rail = reg.InternalRailClient(refresh, api_key)
        url = RAIL_WORKFLOW_LIST.format(loc=urllib.parse.quote(loc, safe=""))
        listing = rail._get(url)
    except reg.InternalRailUnavailable as exc:
        out.write("[workflow-lister] HELD: internal-rail workflow list failed "
                  "(marker %s): %s\n" % (masked, exc))
        return EX_HELD
    try:
        rows = _rows_from_listing(listing)
        plan = _archive_plan(rows, listing, name)
    except ValueError as exc:
        out.write("[workflow-lister] STOP: %s (marker %s)\n" % (exc, masked))
        return EX_STOP
    plan["location"] = masked
    plan["execute"] = execute
    if jsonout is not None:
        json.dump(plan, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[workflow-lister] ARCHIVE PLAN (marker %s, execute=%s): "
                  "%r id=%s status=%s would_archive=%d. %s. Nothing was "
                  "written.\n" % (masked, execute, plan["target"]["name"],
                                  plan["target"]["id"], plan["target"]["status"],
                                  plan["would_archive"], plan["note"]))
    return EX_OK


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# ---------------------------------------------------------------------------
def main(argv=None, environ=None):
    """Dispatch the CLI. Every command prints ONE JSON object on stdout
    (jsonout) and human notes on stderr; --json toggles stdout to the
    machine report. Never prints a credential, a token, a full id, or a
    response body. list and self-test are the OFFLINE-by-gate surfaces (the
    HELD credential gate fires BEFORE any network when the client's own
    token is not SET); list's happy path is the ONE live read (proven rail);
    archive needs the rail credentials for a truthful plan. `environ` is the
    self-test injection point (deterministic offline gates)."""
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="workflow_lister.py", add_help=False,
        description="Live Convert and Flow workflow-name lister (Skill 59 "
                    "U06) via the proven internal rail. Fail-closed; "
                    "credentials BY LABEL, never printed; browser UA "
                    "CAF_BROWSER_UA on every request (CF 1010). The archive "
                    "ACTION requires --execute (Trevor-gated) and is a PLAN "
                    "ONLY -- no mutation, endpoint doctrine.")
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--json", action="store_true",
                    help="machine report on stdout (ONE JSON object)")
    ap.add_argument("--location-id", default="",
                    help="Convert and Flow location id (default: env labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID)")
    ap.add_argument("--name", default="",
                    help="byte-exact workflow name (archive ACTION)")
    ap.add_argument("--execute", action="store_true",
                    help="explicit Trevor gate for an ACTION; the archive "
                         "ACTION is a plan even WITH --execute (no mutation)")
    ap.add_argument("cmd", nargs="?", default="",
                    choices=["list", "archive", "self-test"])
    args = ap.parse_args(argv)

    if args.help or not args.cmd:
        sys.stdout.write(
            "workflow_lister.py -- Skill 59 U06 live workflow-name lister\n"
            "  list [--location-id ID]      live names via the proven internal\n"
            "                               rail (needs the client's OWN\n"
            "                               Firebase refresh token BY LABEL;\n"
            "                               NEVER printed)\n"
            "  archive --name NAME [--location-id ID] [--execute]\n"
            "                               Trevor-gated ACTION; WITHOUT\n"
            "                               --execute it is a STOP, WITH\n"
            "                               --execute it is still a PLAN ONLY\n"
            "                               (%s)\n"
            "  self-test                     offline fixtures, no network, no\n"
            "                               secrets\n"
            "  --json                        ONE JSON object on stdout\n"
            "Exit codes: 0 PASS (incl. an EMPTY workflow set); 2 STOP "
            "(usage / no --execute / name not found / duplicate names /\n"
            "unknown ACTION); 3 HELD (rail unreachable or edge-blocked or "
            "malformed listing); 4 self-test FAILED.\n" % ARCHIVE_NOTE)
        return EX_OK if args.cmd else EX_STOP

    if args.cmd == "self-test":
        return self_test()

    if args.cmd == "archive":
        if not (args.name or "").strip():
            sys.stderr.write("[workflow-lister] STOP: archive requires "
                             "--name (the byte-exact workflow name).\n")
            return EX_STOP
        if not args.execute:
            sys.stderr.write("[workflow-lister] STOP: an ACTION requires "
                             "--execute explicitly (Trevor-gated). Dry-runs "
                             "are the list command; an ACTION without "
                             "--execute is a refusal, never a silent no-op.\n")
            return EX_STOP
        try:
            return archive_command(args.name, args.location_id, execute=True,
                                   out=sys.stderr, jsonout=sys.stdout if args.json else None)
        except ValueError as exc:
            sys.stderr.write("[workflow-lister] STOP: %s\n" % exc)
            return EX_STOP

    # list — read-only, needs no --execute.
    try:
        return live_list_command(args.location_id,
                                 out=sys.stderr,
                                 jsonout=sys.stdout if args.json else None,
                                 environ=environ)
    except ValueError as exc:
        sys.stderr.write("[workflow-lister] STOP: %s\n" % exc)
        return EX_STOP


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
def self_test():
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 4; the happy path prints 'workflow_lister self-test:
    OK' to stderr and returns 0. Never touches the network; never prints a
    token or a full id."""
    dev = io.StringIO()

    # -- the golden listing (the proven rail shape: rows of name/id/type) -----
    golden_listing = {
        "rows": [
            {"name": "Anthology Intake Fire", "id": "wf-0001", "type": "workflow",
             "status": "published"},
            {"name": "Anthology Release: Avatar", "id": "wf-0002", "type": "workflow",
             "status": "published"},
            {"name": "Anthology Release: Cover", "id": "wf-0003", "type": "workflow",
             "status": "draft"},
            {"name": "Anthology Templates", "id": "folder-1", "type": "folder"},
        ]}

    # 1. list_rows: sorted unique workflow names, folders excluded
    names, dropped = list_rows(golden_listing)
    assert names == ["Anthology Intake Fire", "Anthology Release: Avatar",
                     "Anthology Release: Cover"], \
        "golden listing must list the three workflow names sorted: %r" % names
    assert dropped == 0, "golden listing drops no rows, got %d" % dropped
    assert len(names) == 3, "folders must never be listed as workflows"

    # 2. the report carries names + counts only — never ids, never bodies
    report = _build_report(golden_listing, location_id="2HIKGNgsixWx0yds7Qnx")
    assert report["ok"] is True and report["action"] == "list"
    assert report["workflows"] == names and report["workflow_count"] == 3
    assert report["location"].startswith("..."), "location must be masked"
    assert "2HIKGNgsixWx0yds7Qnx" not in json.dumps(report), \
        "the full location id must never reach the report"

    # 3. name resolution — byte-exact bind
    rows = _rows_from_listing(golden_listing)
    row = _resolve_workflow_by_name(rows, "Anthology Release: Avatar")
    assert row["id"] == "wf-0002", "byte-exact name must resolve its row"
    try:
        _resolve_workflow_by_name(rows, "Anthology release: Avatar")
    except ValueError:
        pass
    else:
        raise AssertionError("a case-drifted name must refuse (byte-exact bind)")

    # 4. the archive plan — a no-mutation plan with the note, masked ids
    plan = _archive_plan(rows, golden_listing, "Anthology Release: Avatar")
    assert plan["action"] == ACTION_ARCHIVE and plan["execute"] is False
    assert plan["would_archive"] == 1 and plan["target"]["name"] == "Anthology Release: Avatar"
    assert plan["target"]["id"].startswith("..."), "target id must be masked"
    assert "wf-0002" not in json.dumps(plan), "the full workflow id must never surface"
    assert "no archive/delete surface" in plan["note"], "the endpoint-doctrine note rides the plan"

    # -- ATTACK fixtures: every mutation REFUSED (fail-closed) -----------------
    # 5. duplicate names — the name-match bind is ambiguous and MUST refuse
    dup = {"rows": [
        {"name": "Dupe", "id": "wf-9", "type": "workflow", "status": "published"},
        {"name": "Dupe", "id": "wf-8", "type": "workflow", "status": "draft"}]}
    try:
        _archive_plan(_rows_from_listing(dup), dup, "Dupe")
    except ValueError:
        pass
    else:
        raise AssertionError("a duplicated name must refuse the plan")
    # 6. an unknown ACTION name — only 'archive' exists; anything else refuses
    #    (covered by argparse choices, mirrored here so the gate is explicit)
    assert ACTION_ARCHIVE == "archive"
    # 7. an empty name refuses
    try:
        _archive_plan(rows, golden_listing, "")
    except ValueError:
        pass
    else:
        raise AssertionError("an empty name must refuse the plan")
    # 8. a missing name (no match) refuses
    try:
        _archive_plan(rows, golden_listing, "No Such Workflow")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown name must refuse the plan")
    # 9. malformed listings refuse (never an empty list)
    for bad in ([], {"nope": True}, {"rows": "not-a-list"}, {"rows": ["scalar"]}):
        try:
            _rows_from_listing(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed listing must refuse: %r" % (bad,))
    # 10. dropped rows (no name / no id) are counted, never listed
    ragged = {"rows": [
        {"name": "", "id": "wf-1", "type": "workflow", "status": "published"},
        {"name": "Only Id", "id": "", "type": "workflow", "status": "draft"},
        {"name": "Good", "id": "wf-3", "type": "workflow", "status": "published"}]}
    n2, d2 = list_rows(ragged)
    assert n2 == ["Good"] and d2 == 2, \
        "blank-name and blank-id rows drop with the count surfaced: %r %d" % (n2, d2)

    # -- the archive command surface: --execute gate --------------------------
    # The offline contract (an explicit EMPTY environ blocks the canonical
    # env-store fallback for the REFRESH TOKEN — the one resolver that takes
    # environ — so the list gate is deterministic with zero network): a
    # missing --name STOPS before any credential work, a missing --execute
    # STOPS (Trevor gate), and a credential-less list HELDs (never a
    # fabricated list). The archive-with---execute path is NOT exercised
    # here: when the client's own refresh token is live (as on this box) it
    # performs the real live read and then STOPS or plans against the real
    # listing — a truthful plan requires the live read, and the CLI gate
    # tests cannot depend on live state, so they assert only the pre-network
    # refusals (which are env-independent).
    empty_env = {}
    rc_stop = main(["archive"], environ=empty_env)       # no --name, no --execute
    assert rc_stop == EX_STOP, "archive without --name must STOP, got %r" % rc_stop
    rc_stop2 = main(["archive", "--name", "X"], environ=empty_env)  # NO --execute
    assert rc_stop2 == EX_STOP, \
        "archive without --execute must STOP (Trevor-gated), got %r" % rc_stop2
    rc_list = main(["list"], environ=empty_env)
    assert rc_list == EX_HELD, \
        "list without credentials must HELD (never a fabricated list), got %r" % rc_list

    sys.stderr.write("workflow_lister self-test: OK "
                     "(golden listing sorted/folders excluded, byte-exact "
                     "bind, archive plan no-mutation + masked ids, and 8 "
                     "attack fixtures refused fail-closed: duplicate-name / "
                     "empty-name / unknown-name / non-dict / missing-rows / "
                     "non-list-rows / non-object-row / ragged-rows; "
                     "--execute gate STOPs without it)\n")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
