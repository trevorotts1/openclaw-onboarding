#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/workflows_check.py
# WORKFLOWS COUNT + FOLDER CHECK against the release-notification contract.
# Part of the U02 template re-verify tooling: reads the operator's OWN
# Anthology Convert and Flow TEMPLATE location back and asserts the EIGHT
# tag->notification release workflows (config/anthology-snapshot-contract.json
# workflows.release_notifications) live in ONE workflow folder named exactly
# "Anthology Engine" (workflows.template_folder) — the contract row the
# snapshot MUST carry, per MASTER-SPEC U02 item 4.
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW. The live check runs
# through the PROVEN internal rail (backend.leadconnectorhq.com /workflow/
# {loc}/list?limit=200 — the surface verify-podcast-ghl-workflows.py proved
# live; Skill 44 doctrine: only proven endpoints). Without a Firebase refresh
# token BY LABEL the live read is DEFERRED (fail-closed, never fabricated) —
# exactly the snapshot-cut doctrine. --self-test is OFFLINE (no network, no
# secrets).
#
# WHAT THIS ASSERTS (per contract row, byte-exact):
#   - FOLDER: every live workflow that is a contract release-notification name
#     must sit in a folder whose name is byte-equal to the contract
#     workflows.template_folder ("Anthology Engine"). A workflow row missing a
#     folder name is recorded as (none) and FAILS the folder check — never
#     assumed to be in the right folder.
#   - COUNT: the live workflow rows of type "workflow" in that folder are
#     counted and named; the EIGHT contract rows must ALL be present BY NAME,
#     each exactly once — never a blind "at least N". A contract workflow
#     ABSENT (a strict subset) fails closed (STOP); an EXTRA copy of a
#     contract name records a FAIL. Other workflows in the same folder are
#     reported (extra_names) — the operator owns the template — but never
#     judged and never a failure: the contract's U02 item is "the EIGHT
#     tag->notification release workflows in one folder", presence + folder,
#     not exclusivity.
#   - TRIGGERS (when the rail provides the workflow detail + trigger surface,
#     the same GETs live_verify_template.py already proved): each contract
#     workflow's trigger is type contact_tag and ACTIVE, bound to its contract
#     trigger_tag byte-exact. If the trigger surface is unreachable the whole
#     live check is HELD — never a partial pass.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The Firebase refresh token and API
# key resolve through anthology_registry (FIREBASE_REFRESH_LABELS /
# FIREBASE_API_KEY_LABELS) as SET/NOT-SET only; the location id is the
# contract source_template_location.template_location_id (operator
# infrastructure config, not a secret) with --location-id override for tests.
# BROWSER USER-AGENT: every request rides the registry clients (InternalRailClient
# -> _internal_request_headers carries the CAF_BROWSER_UA constant) — urllib's
# default "Python-urllib/x.y" is 403'd at the Cloudflare edge (CF 1010) before
# it ever reaches the API. NEVER print a token; never print a response body.
#
# RETURN: {ok, count, names} — ok True only when the live folder/count check
# (or the offline --check against a passed-in listing) PASSES in full; count
# is the live workflow count observed in the folder; names the live workflow
# names observed there, sorted. Any FAIL / HELD / DEFERRED -> ok False.
# Fail-closed: a missing contract section, an unreadable contract, a live
# check that could not be completed, or an exception is NEVER a pass.
#
# EXIT CODES (house convention, ENGINE-MANIFEST.json exit_code_house_convention):
#   0  all checks PASS (including --self-test)
#   1  unexpected error
#   2  validation / usage / missing or malformed contract (fail-closed STOP)
#   3  HELD (internal rail unavailable / transport) — retryable
#   4  self-test FAILED (an attack fixture was NOT refused)
#   5  data or read-back mismatch (workflow count / folder / trigger drift)
# =============================================================================
"""workflows_check.py — U02 workflows count + folder check (module form).

Imported BY NAME as u02_modules.workflows_check from the engine scripts, per
the u02_modules package contract (__init__.py: pure namespace container).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring + the LeadConnector clients + the label
# resolution contract (SET/NOT-SET only, never a value).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

# House exit-code convention (ENGINE-MANIFEST.json exit_code_house_convention):
# 0 success (including an idempotent no-op); 1 unexpected error; 2 validation
# or guard refusal; 3 dependency unavailable or held; 4 enforced violation
# detected; 5 data or read-back mismatch.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location — operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# Internal-rail endpoints proven live in this repo (Podcast gate; snapshot
# cut; live_verify_template.py U02): workflow list / get / trigger. All
# READ-ONLY GETs. The workflow-detail + trigger surfaces are used as the
# live_verify_template already proved them; an unreachable surface HELDs the
# live check, never a partial pass.
_RAIL_WORKFLOW_LIST = "/workflow/{loc}/list?limit=200"
_RAIL_WORKFLOW_GET = "/workflow/{loc}/{wid}"
_RAIL_WORKFLOW_TRIGGER = "/workflow/{loc}/trigger?workflowId={wid}"

# Workflow names that belong to the engine's operator surface, not the
# author-facing release-notification set: recorded when present in the folder,
# never judged against the eight-row contract (mirrors live_verify_template.py
# _OPERATOR_WF_MARKERS). The folder-count check EXCLUDES these so the count
# compares exactly against the contract rows BY NAME — a strict-subset absense
# still STOPS, an extra UNKNOWN workflow still FAILs.
OPERATOR_WF_MARKERS = ("Chapter Approval Ready",)


class WorkflowsCheckError(Exception):
    """A fail-closed verification refusal (STOP / mismatch family)."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is an error — never a pass).
# ---------------------------------------------------------------------------
def _contract_release_workflows(contract: dict) -> list:
    """The eight tag->notification workflow rows, copied so callers can never
    mutate the loaded contract. A missing/empty release_notifications block is
    a STOP — the check must never pass blind."""
    rows = ((contract.get("workflows") or {}).get("release_notifications") or [])
    if not isinstance(rows, list) or not rows:
        raise WorkflowsCheckError(
            "contract workflows.release_notifications is missing or empty: "
            "%s" % CONTRACT_PATH)
    out = []
    for w in rows:
        if not isinstance(w, dict):
            raise WorkflowsCheckError(
                "contract workflows.release_notifications carries a non-object row: %r"
                % (w,))
        if not isinstance(w.get("name"), str) or not w["name"].strip():
            raise WorkflowsCheckError(
                "contract workflows.release_notifications carries a row with a blank "
                "name — a blind name-match cannot judge it: %s" % CONTRACT_PATH)
        out.append(dict(w))
    return out


def _contract_template_folder(contract: dict) -> str:
    """The single workflow folder name the eight workflows must share,
    byte-exact. Missing or empty is a STOP."""
    folder = ((contract.get("workflows") or {}).get("template_folder") or "")
    if not isinstance(folder, str) or not folder.strip():
        raise WorkflowsCheckError(
            "contract workflows.template_folder is missing or empty: %s"
            % CONTRACT_PATH)
    return folder.strip()


def _contract_location_id(contract: dict) -> str:
    """The operator's OWN template location id (contract
    source_template_location.template_location_id). Not a secret — operator
    infrastructure config. Missing is a STOP."""
    loc = ((contract.get("source_template_location") or {}).get("template_location_id") or "")
    if not isinstance(loc, str) or not loc.strip():
        raise WorkflowsCheckError(
            "contract source_template_location.template_location_id is missing or empty")
    return loc.strip()


def _load_contract(path: Path) -> dict:
    """Read + parse the contract; a missing or malformed file is a STOP
    (fail-closed, never a blind pass)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkflowsCheckError("cannot read contract %s: %s" % (path, exc)) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise WorkflowsCheckError("contract %s is malformed JSON: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise WorkflowsCheckError("contract %s is not a JSON object" % path)
    return data


# ---------------------------------------------------------------------------
# The check itself — {ok, count, names}.
# ---------------------------------------------------------------------------
def _is_operator_scope(name: str) -> bool:
    return any(m in name for m in OPERATOR_WF_MARKERS)


def _workflow_summary(wf: dict, triggers: list) -> dict:
    """The exact fields the check reads off the rail rows. A response body is
    never printed anywhere in this module — only these derived booleans."""
    t = triggers[0] if triggers else {}
    return {
        "name": wf.get("name") or "",
        "parent_id": str(wf.get("parentId") or ""),
        "status": wf.get("status") or "unknown",
        "trigger_type": t.get("type") or "",
        "trigger_active": bool(t.get("active")),
        "trigger_conditions": [c for c in (t.get("conditions") or []) if isinstance(c, dict)],
    }


def _rail_workflows(rail, location_id: str) -> tuple:
    """Fetch every listing row + workflow detail + trigger through the rail.
    Raises WorkflowsCheckError on a malformed listing (fail-closed) and lets
    reg.InternalRailUnavailable propagate (HELD by the caller). Returns
    (seen, listing_rows): `seen` maps workflow id -> summary; `listing_rows`
    is the raw rows array (its 'directory' rows carry the location's workflow
    folder names — the folder the live read proved is carried as a directory
    row, not on the workflow row)."""
    out = rail._get(_RAIL_WORKFLOW_LIST.format(loc=location_id))
    rows = out.get("rows") if isinstance(out, dict) else None
    if not isinstance(rows, list):
        raise WorkflowsCheckError(
            "internal rail workflow list returned no rows array (marker %s)"
            % reg._mask_location(location_id))
    seen = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "workflow":
            continue
        wid = row.get("id")
        if not wid:
            continue
        wf = rail._get(_RAIL_WORKFLOW_GET.format(loc=location_id, wid=wid))
        trigs = rail._get(_RAIL_WORKFLOW_TRIGGER.format(loc=location_id, wid=wid))
        if not isinstance(trigs, list):
            trigs = []
        if isinstance(wf, dict):
            seen[wid] = _workflow_summary(wf, trigs)
    return seen, rows


def _directory_names(rows: list) -> dict:
    """Index the listing's 'directory' rows (the location's workflow folders)
    by id -> name, byte-exact. Live-read, never guessed; a row with no id is
    skipped and its children then can never match the contract folder."""
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("type") == "directory" and r.get("id"):
            out[str(r["id"])] = r.get("name") or ""
    return out


def check_workflows_live(rail, location_id: str, contract: dict) -> dict:
    """Live workflows count + folder check. Returns {ok, count, names}.

    Every contract release workflow must be present BY NAME in ONE folder
    named byte-exact 'Anthology Engine', with a contact_tag trigger ACTIVE on
    its contract trigger_tag. The count reports the folder's workflow rows;
    the EIGHT contract names must all be among them exactly once (extra copies
    or absence -> ok False). Other workflows in the same folder are reported
    under extra_names (the operator owns the template) but never fail the
    check. A malformed listing raises WorkflowsCheckError (STOP, exit 2).
    """
    folder_want = _contract_template_folder(contract)
    want = _contract_release_workflows(contract)
    seen, listing_rows = _rail_workflows(rail, location_id)

    # The folder's live workflow rows: a workflow sits in the folder iff its
    # parentId is the id of a 'directory' row whose name is byte-equal to the
    # contract folder. The directory-name index comes from the same listing
    # (live-read, never guessed).
    directory_names = _directory_names(listing_rows)
    in_folder = [s for s in seen.values()
                 if directory_names.get(s["parent_id"]) == folder_want]
    in_folder_names = sorted({s["name"] for s in in_folder if s["name"]})
    # Other workflows in the same folder (operator-scope markers excluded from
    # the report; the rest are REAL observations). The contract's U02 item is
    # "the EIGHT tag->notification release workflows in ONE folder named
    # exactly 'Anthology Engine'" — presence + folder, not exclusivity — so
    # extras are REPORTED (the operator owns the template) but never fail the
    # check.
    extra_names = sorted({s["name"] for s in in_folder if s["name"]
                          and not any(w.get("name") == s["name"] for w in want)
                          and not _is_operator_scope(s["name"])})

    failures = []
    live_rows = []
    for w in want:
        name = w.get("name") or ""
        copies = [s for s in in_folder if s["name"] == name]
        summary = copies[0] if copies else None
        if len(copies) > 1:
            failures.append("%r DUPLICATED in folder %r (count %d)"
                            % (name, folder_want, len(copies)))
        live_rows.append({
            "name": name,
            "found": summary is not None,
            "folder": folder_want if summary else "(none)",
            "status": summary["status"] if summary else "",
            "trigger_type": summary["trigger_type"] if summary else "",
            "trigger_active": summary["trigger_active"] if summary else False,
        })
        if summary is None:
            failures.append("%r ABSENT from folder %r" % (name, folder_want))
            continue
        if summary["trigger_type"] != "contact_tag":
            failures.append("%r trigger type %r != contact_tag" % (name, summary["trigger_type"]))
        if not summary["trigger_active"]:
            failures.append("%r trigger not ACTIVE" % name)
        tag = w.get("trigger_tag") or ""
        if tag:
            cond_tags = set()
            for c in summary["trigger_conditions"]:
                val = c.get("value")
                if isinstance(val, str) and val:
                    cond_tags.add(val)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v:
                            cond_tags.add(v)
            if tag not in cond_tags:
                failures.append("%r trigger condition tag %r not bound (has: %s)"
                                % (name, tag, ", ".join(sorted(cond_tags)) or "(none)"))

    expected = {
        "folder": folder_want,
        "count": len(want),
        "names": [w.get("name") for w in want],
    }
    live = {
        "folder": folder_want,
        "count": len(in_folder_names),
        "names": in_folder_names,
        "rows": live_rows,
    }
    ok = not failures
    detail = ("all %d release workflows present in folder %r with contact_tag "
              "ACTIVE on the contract tag" % (len(want), folder_want)) if ok \
        else "; ".join(failures)
    if ok and extra_names:
        detail += ("; %d other workflow(s) in the same folder (reported, not "
                   "judged): %s" % (len(extra_names), ", ".join(extra_names)))
    return {
        "ok": ok,
        "count": len(in_folder_names),
        "names": in_folder_names,
        "extra_names": extra_names,
        "expected": expected,
        "live": live,
        "failures": failures,
        "detail": detail,
    }


def check_workflows_offline(rows: list, contract: dict) -> dict:
    """Offline folder/count check against a caller-supplied listing (tests,
    fixtures, a pasted rail listing) — the same fail-closed assertion set as
    the live path, with trigger checks skipped: rows carry no trigger surface
    here. Returns the same {ok, count, names, ...} shape."""
    folder_want = _contract_template_folder(contract)
    want = _contract_release_workflows(contract)
    listing_rows = [r for r in (rows or []) if isinstance(r, dict)]
    seen = {}
    for row in listing_rows:
        if row.get("type") != "workflow":
            continue
        wid = row.get("id")
        if not wid:
            continue
        seen[wid] = _workflow_summary(row, [])
    directory_names = _directory_names(listing_rows)
    in_folder = [s for s in seen.values()
                 if directory_names.get(s["parent_id"]) == folder_want]
    in_folder_names = sorted({s["name"] for s in in_folder if s["name"]})
    extra_names = sorted({s["name"] for s in in_folder if s["name"]
                          and not any(w.get("name") == s["name"] for w in want)
                          and not _is_operator_scope(s["name"])})
    failures = []
    for w in want:
        name = w.get("name") or ""
        copies = [s for s in in_folder if s["name"] == name]
        if not copies:
            failures.append("%r ABSENT from folder %r" % (name, folder_want))
        elif len(copies) > 1:
            failures.append("%r DUPLICATED in folder %r (count %d)"
                            % (name, folder_want, len(copies)))
    ok = not failures
    detail = ("all %d release workflows present in folder %r"
              % (len(want), folder_want)) if ok else "; ".join(failures)
    if ok and extra_names:
        detail += ("; %d other workflow(s) in the same folder (reported, not "
                   "judged): %s" % (len(extra_names), ", ".join(extra_names)))
    return {
        "ok": ok,
        "count": len(in_folder_names),
        "names": in_folder_names,
        "extra_names": extra_names,
        "expected": {
            "folder": folder_want,
            "count": len(want),
            "names": [w.get("name") for w in want],
        },
        "live": {
            "folder": folder_want,
            "count": len(in_folder_names),
            "names": in_folder_names,
        },
        "failures": failures,
        "detail": detail,
    }


def _run_check(*, location_id: str, contract: dict, out, jsonout=None) -> dict:
    """Resolve the rail credentials BY LABEL, fetch, and run the check.
    Never prints a credential; SET/NOT-SET only. Any unreachable surface or
    unavailable rail HELDs (ok False, never a pass)."""
    rt_label, refresh = reg.resolve_firebase_refresh_token()
    ak_label, api_key = reg._resolve_firebase_api_key()
    if not refresh or not api_key:
        out.write("[workflows_check] HELD: no Firebase refresh token SET "
                  "(labels: %s). Live count/folder check needs the template "
                  "location's OWN token; --self-test needs none.\n"
                  % ", ".join(reg.FIREBASE_REFRESH_LABELS))
        return {"ok": False, "count": None, "names": [],
                "detail": "HELD: Firebase refresh token NOT SET (labels: %s)"
                          % ", ".join(reg.FIREBASE_REFRESH_LABELS)}
    rail = reg.InternalRailClient(refresh, api_key)
    return check_workflows_live(rail, location_id, contract)


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets.
# ---------------------------------------------------------------------------
class _FakeRail:
    """Internal-rail stub: serves workflow list/get/trigger from summary
    fixtures; rows carry directory rows for the folder-name resolution.
    Records every path read so the self-test can prove the check reads,
    never writes."""

    def __init__(self, rows, outcome="ok"):
        self._rows = rows or []
        self._outcome = outcome
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        if self._outcome == "unavailable":
            raise reg.InternalRailUnavailable("fixture: rail unavailable")
        if "/list" in path:
            return {"rows": self._rows}
        if "trigger?" in path:
            wid = path.rsplit("=", 1)[-1]
            row = next((r for r in self._rows if r.get("id") == wid), {})
            return [{"type": "contact_tag", "active": True,
                     "conditions": [{"type": "tag", "value": [row.get("trigger_tag", "")]}]}]
        wid = path.rsplit("/", 1)[-1]
        row = next((r for r in self._rows if r.get("id") == wid), {})
        return {"name": row.get("name", ""), "parentId": row.get("parentId", ""),
                "status": row.get("status", "published")}


def _golden_contract_rows(contract: dict) -> list:
    return [dict(w) for w in _contract_release_workflows(contract)]


def _golden_rows(contract: dict) -> list:
    """A directory row naming the contract folder, plus one workflow row per
    contract workflow parented under it — the listing shape the live rail
    carries (proved: the folder is a 'directory' row; the workflows reference
    it by parentId). All contact_tag ACTIVE on their contract trigger_tag."""
    folder = _contract_template_folder(contract)
    rows = [{"id": "dir-tmpl", "name": folder, "type": "directory", "parentId": None}]
    rows += [{"id": "wf-%d" % i, "name": w.get("name"), "type": "workflow",
              "parentId": "dir-tmpl", "status": "published",
              "trigger_tag": w.get("trigger_tag")}
             for i, w in enumerate(_golden_contract_rows(contract))]
    return rows


def self_test(out=None) -> int:
    """OFDLINE self-test: golden + attack fixtures, mutation proof. A tamper
    NEVER masquerades as exit 1 — it is exit 4 (AF-AE-TEMPLATE-ATTACK family)."""
    out = out or sys.stderr
    import io
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        out.write("[workflows_check] SELF-TEST FAILED "
                  "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    contract = _load_contract(CONTRACT_PATH)
    folder = _contract_template_folder(contract)
    want = _contract_release_workflows(contract)

    # ---- contract coherence (same assertions as live_verify_template) ----
    assert len(want) == 8, "contract must carry exactly 8 release workflows, got %d" % len(want)
    assert folder == "Anthology Engine", "contract workflows.template_folder must be 'Anthology Engine'"
    assert _contract_location_id(contract) == DEFAULT_TEMPLATE_LOCATION, \
        "contract template location drifted from the U02 default"
    assert contract["workflows"]["built_in_template"] is True

    # ---- golden live state: EVERYTHING passes ----
    rail = _FakeRail(rows=_golden_rows(contract))
    result = check_workflows_live(rail, "loc_tmpl", contract)
    assert result["ok"] is True, "golden live check must pass: %s" % result["detail"]
    assert result["count"] == 8, "golden live count must be 8, got %s" % result["count"]
    assert result["names"] == sorted(w.get("name") for w in want), \
        "golden live names must match the contract set"
    # the check only READS — every call is a GET-shaped rail path
    assert rail.calls and all("/workflow/" in c for c in rail.calls), \
        "golden check must only read the rail: %s" % rail.calls

    # ---- offline check on the golden listing: same verdict ----
    offline = check_workflows_offline(_golden_rows(contract), contract)
    assert offline["ok"] is True and offline["count"] == 8, \
        "golden offline check must pass"

    # ---- attack fixtures: every mutation refused / recorded FAIL ----
    # 1. a contract workflow ABSENT (strict subset) -> FAIL, never a blind pass
    rows = _golden_rows(contract)
    rows.pop(0)
    res = check_workflows_live(_FakeRail(rows=rows), "loc_tmpl", contract)
    assert res["ok"] is False and "ABSENT" in res["detail"], \
        "missing workflow must fail closed: %s" % res["detail"]
    # 2. an EXTRA contract-name copy in the folder -> FAIL (multiplicity drift)
    rows = _golden_rows(contract)
    first_wf = next(r for r in rows if r.get("type") == "workflow")
    rows.append(dict(first_wf, id="wf-dup"))
    res = check_workflows_live(_FakeRail(rows=rows), "loc_tmpl", contract)
    assert res["ok"] is False and "DUPLICATED" in res["detail"], \
        "duplicate copy must fail closed on multiplicity: %s" % res["detail"]
    # 3. an UNKNOWN workflow parked in the folder -> reported, NOT a failure
    #    (the contract's U02 item is presence + folder, not exclusivity)
    rows = _golden_rows(contract)
    rows.append({"id": "wf-extra", "name": "Not An Anthology Workflow",
                 "type": "workflow", "parentId": "dir-tmpl", "status": "published"})
    res = check_workflows_live(_FakeRail(rows=rows), "loc_tmpl", contract)
    assert res["ok"] is True, "extra workflow must not fail the folder check: %s" % res["detail"]
    assert res["extra_names"] == ["Not An Anthology Workflow"], \
        "extra workflow must be reported: %s" % res["extra_names"]
    assert "reported, not judged" in res["detail"], "detail must mention the extras"
    # 4. the contract folder RENAMED on the live side -> FAIL
    rows = _golden_rows(contract)
    next(r for r in rows if r.get("type") == "directory")["name"] = "Anthology Engine RENAMED"
    res = check_workflows_live(_FakeRail(rows=rows), "loc_tmpl", contract)
    assert res["ok"] is False and "ABSENT" in res["detail"], \
        "folder-renamed must fail closed"
    # 5. trigger drifted: inactive, wrong type, wrong tag -> FAIL each
    rows = _golden_rows(contract)
    wid = next(r for r in rows if r.get("type") == "workflow")["id"]
    rail_bad = _FakeRail(rows=rows)
    orig_get = rail_bad._get

    def _bad_trigger(path):
        if "trigger?" in path and path.rsplit("=", 1)[-1] == wid:
            return [{"type": "contact_tag", "active": False,
                     "conditions": [{"type": "tag",
                                     "value": [next(r for r in rows if r.get("id") == wid)["trigger_tag"]]}]}]
        return orig_get(path)

    rail_bad._get = _bad_trigger
    res = check_workflows_live(rail_bad, "loc_tmpl", contract)
    assert res["ok"] is False and "not ACTIVE" in res["detail"], \
        "inactive trigger must fail: %s" % res["detail"]

    rows = _golden_rows(contract)
    rail_bad = _FakeRail(rows=rows)
    orig_get = rail_bad._get

    def _bad_type(path):
        if "trigger?" in path and path.rsplit("=", 1)[-1] == wid:
            return [{"type": "contact_changed", "active": True, "conditions": []}]
        return orig_get(path)

    rail_bad._get = _bad_type
    res = check_workflows_live(rail_bad, "loc_tmpl", contract)
    assert res["ok"] is False and "contact_tag" in res["detail"], \
        "wrong trigger type must fail: %s" % res["detail"]

    rows = _golden_rows(contract)
    rail_bad = _FakeRail(rows=rows)
    orig_get = rail_bad._get

    def _bad_tag(path):
        if "trigger?" in path and path.rsplit("=", 1)[-1] == wid:
            return [{"type": "contact_tag", "active": True,
                     "conditions": [{"type": "tag", "value": ["anthology-release-other"]}]}]
        return orig_get(path)

    rail_bad._get = _bad_tag
    res = check_workflows_live(rail_bad, "loc_tmpl", contract)
    assert res["ok"] is False and "not bound" in res["detail"], \
        "wrong trigger tag must fail: %s" % res["detail"]

    # 6. a malformed listing (no rows array) -> WorkflowsCheckError (STOP), never a pass
    rail_garbage = _FakeRail(rows=[], outcome="ok")

    def _garbage(path):
        if "/list" in path:
            return {"no_rows_here": True}
        return {"rows": []}

    rail_garbage._get = _garbage
    try:
        check_workflows_live(rail_garbage, "loc_tmpl", contract)
        raise AssertionError("malformed listing was NOT refused")
    except WorkflowsCheckError:
        pass

    # 7. the rail unavailable -> InternalRailUnavailable propagates (HELD by the caller)
    try:
        check_workflows_live(_FakeRail(rows=_golden_rows(contract), outcome="unavailable"),
                             "loc_tmpl", contract)
        raise AssertionError("unavailable rail was NOT held")
    except reg.InternalRailUnavailable:
        pass

    # 8. a contract row with a missing name -> STOP (fail-closed contract reader)
    bad_contract = dict(contract)
    bad_contract["workflows"] = dict(contract["workflows"])
    rows = [dict(w) for w in want]
    rows[0]["name"] = ""
    bad_contract["workflows"]["release_notifications"] = rows
    try:
        check_workflows_offline(_golden_rows(contract), bad_contract)
        raise AssertionError("blank contract workflow name was NOT refused")
    except WorkflowsCheckError:
        pass

    dev.write("[workflows_check] self-test PASS: golden + 8 attack fixtures "
              "(count / folder / trigger / malformed / held / contract) all held.\n")


# ---------------------------------------------------------------------------
# CLI — check / self-test. Module import is side-effect free.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="workflows_check.py",
        description="U02 workflows count + folder check (release-notification "
                    "contract) — {ok, count, names}, fail-closed.")
    ap.add_argument("--location-id", default="",
                    help="Override the contract template location id (tests only).")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="Path to anthology-snapshot-contract.json.")
    ap.add_argument("--self-test", action="store_true",
                    help="Offline golden + attack fixtures; needs no token, no network.")
    ap.add_argument("--json", action="store_true",
                    help="Emit the result object as JSON on stdout.")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        contract = _load_contract(Path(args.contract))
        location_id = args.location_id.strip() or _contract_location_id(contract)
        result = _run_check(location_id=location_id, contract=contract, out=sys.stderr)
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[workflows_check] HELD: internal rail unavailable "
                         "(marker %s): %s\n"
                         % (reg._mask_location(location_id if "location_id" in dir() else ""), exc))
        return EX_HELD
    except WorkflowsCheckError as exc:
        sys.stderr.write("[workflows_check] STOP: %s\n" % exc)
        return EX_STOP
    except Exception as exc:  # noqa: BLE001 -- never a token, never a body
        sys.stderr.write("[workflows_check] unexpected error: %s\n"
                         % type(exc).__name__)
        return EX_ERR

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    if result["ok"]:
        sys.stderr.write("[workflows_check] OK: %s\n" % result["detail"])
        return EX_OK
    sys.stderr.write("[workflows_check] FAIL: %s\n" % result["detail"])
    return EX_MISMATCH


if __name__ == "__main__":
    sys.exit(main())
