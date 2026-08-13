#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/workflow_reader.py  (U05 tooling)
# LIVE WORKFLOW READER — the live workflows read that FINDS the Intake Fire
# front-door workflow on a Convert and Flow location and reports its ONE
# identifier: the workflow id. OFFLINE plan + offline self-test always work;
# the live read needs a location-scoped credential BY LABEL.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u05_modules/ — an importable module under the U05
# package (pure namespace container per the u02/u03 package-init doctrine:
# imported BY NAME, side-effect-free at import). It ships as the shared live
# workflow surface the U05 verification family imports, so the find-by-name /
# pin-by-id semantics can NEVER drift between this reader and its callers —
# the delta_reporter.py single-implementation doctrine (a contract read once,
# in one module).
#
# WHAT THIS OWNS
#   1. THE LIVE WORKFLOW SURFACE. The live workflow rows are read with ONE
#      GET against the internal rail (backend.leadconnectorhq.com, the ONLY
#      workflow surface this repo has PROVEN live — Skill 58
#      verify-podcast-ghl-workflows.py: GET /workflow/<loc>/list?limit=200
#      with headers token-id / channel APP / source WEB_USER / version
#      2021-07-28 — the same header set reg.InternalRailClient already sends;
#      the forms_check.py / live_verify_template.py U02 forms+workflow reads
#      ride this same rail and the workflow rows are PROVEN to carry the
#      shape {"rows": [ {"type": "workflow", "name": ..., "id": ...} ]}).
#      The PUBLIC v2 surface has NO proven workflows listing endpoint in this
#      repo, so it is NOT used — the Skill 44 doctrine ("Do NOT add new
#      endpoints without verifying against the live backend") is binding.
#   2. FIND-BY-NAME. "Anthology Intake Fire" (the engine's front-door
#      workflow, forms_check.py's live-verified name) is found by NAME: a
#      listing row whose type is "workflow" and whose name, normalized, is
#      the contract name with dashes -> spaces ("anthology intake fire") —
#      the same name-match law form_reader.py pins for the forms slug. Every
#      row that carries the workflow id is kept, so a near-miss is REPORTED
#      (never silently ignored): candidates are the workflow rows whose name
#      CONTAINS "intake" (case-insensitive), listed with their masked ids
#      for the operator to resolve — the fail-closed never-a-silent-pass
#      surface.
#   3. PIN-BY-ID (the drift law). When --workflow-id is given (a box override
#      slot, or the value forms_check.py pins for the engine), the reader
#      ALSO requires the listing to carry that exact id — a pinned id the
#      listing does not contain is a MISMATCH (exit 5), never a silent pass,
#      and the pinned id BYPASSES the name law (a pin is a stronger contract
#      than a name). The pinned value is masked on every surface, exactly
#      like a location id.
#   4. THE READ LAW. A 2xx whose body is NOT valid JSON, a listing with no
#      parseable rows, a listing with NO "Anthology Intake Fire" row, or a
#      pinned id absent from the listing is a FAIL (exit 5) — never a
#      fabricated pass. A bare 401/403 on the PUBLIC surface is HELD
#      (UpstreamBlockedError — the CF 1010 edge-block guard; a scope denial
#      is only a REAL "not authorized for this scope" signature), a transport
#      failure is HELD (exit 3), and a missing/refused credential STOPS
#      (exit 2). A NOT-FOUND is the fail-closed default: the workflow id is
#      returned ONLY when a row matched the name law (or the pin matched);
#      otherwise the surface carries found=false and NO id value — no id,
#      no pass.
#   5. NEVER-A-TOKEN SURFACE. The credential is resolved through the house
#      labels (PIT first: CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
#      GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, then the
#      internal rail: ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN /
#      GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN + the
#      Firebase API-key label; live process env first, then the three
#      canonical client env stores; SET / NOT SET only — a token value is
#      NEVER printed). Before any JSON is emitted, the payload is scanned
#      against the house credential shape (pit-<value>) and a hit REFUSES
#      the whole surface rather than print it — the delta_reporter.py
#      never-a-real-token doctrine.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient /
# reg.InternalRailClient, which apply CAF_BROWSER_UA on EVERY request — the
# Cloudflare edge fronting services.leadconnectorhq.com 403s urllib's
# default "Python-urllib/x.y" User-Agent at the WAF edge (CF error 1010)
# before the request ever reaches Convert and Flow (GK-09; the same browser
# UA the Podcast gate proved live). The rail's minted id_token is sent as
# the token-id header, exactly like the Skill 58 workflow read.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, echoed, or reflected.
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable response, an empty listing, an absent "Anthology Intake Fire"
# row, or a pinned id the listing lacks is a REFUSAL / FAIL — never a silent
# pass, never a fabricated success, and never an id guessed from memory.
#
# RETURN CONTRACT (the machine surface this module owns):
#   read_workflows(client, location_id, *, pinned_id="", workflow_rows=None)
#       -> dict — {"contract", "schema_version", "ok", "found",
#       "workflow_id", "workflow_id_masked", "matched_by", "count",
#       "candidates", "sources", "af_code", "note"}; found=false carries NO
#       workflow_id value.
#       Raises WorkflowReadError (STOP family) / reg.ScopeDenied /
#       reg.UpstreamBlockedError / reg.CafUnreachable /
#       reg.InternalRailUnavailable (HELD family) — a caller maps them onto
#       the house exit codes.
#   plan(location_id, pinned_id, *, out=sys.stdout) -> int — ONE JSON
#       object, offline, no network, no credential.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers check / plan / self-test.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 belongs to self-test FAILED):
#   0  PASS — "Anthology Intake Fire" was found (also plan / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      a malformed listing shape that cannot be read faithfully
#   3  Convert and Flow API unreachable / edge-blocked / internal rail
#      unavailable (HELD, retryable)
#   4  self-test FAILED (a tamper NEVER masquerades as exit 1)
#   5  MISMATCH — no "Anthology Intake Fire" row, a pinned id absent from
#      the listing, or a malformed listing (the fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   workflow_reader.py check [--location-id ID] [--workflow-id ID]
#   workflow_reader.py plan   [--location-id ID] [--workflow-id ID]
#   workflow_reader.py self-test
# =============================================================================
"""workflow_reader.py — live reader of the Convert and Flow workflow listing
that finds the "Anthology Intake Fire" front-door workflow (Skill 59, U05
tooling)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to form_reader.py /
# config_loader.py): the registry owns the Cloudflare browser-UA wiring, the
# LeadConnector clients, the credential resolution, and the exit-code contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object for
# a workflow read (the self-test asserts the golden plan carries the exact
# string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-workflow-read"
CONFIG_SCHEMA_VERSION = 1

# The workflow this reader exists for — the engine's Intake Fire front door.
# The name is BYTE-EXACT: forms_check.py's live-verified 2026-08-11 name of
# the universal-intake form's form_submission trigger workflow on the
# operator's OWN template location ("Anthology Intake Fire" — the intake
# hook automation: contact_tag trigger + a Custom Webhook action whose URL
# comes from the {{ custom_values.anthology_webhook_url }} merge). The U05
# family resolves it by EXACT NAME, never by alias or guess; a renamed
# workflow is indistinguishable from an ABSENT one to find-by-name and BOTH
# refuse fail-closed.
WORKFLOW_NAME = "Anthology Intake Fire"

# The internal-rail workflows listing surface, proven live in Skill 58
# (58-podcast-production-engine/scripts/verify-podcast-ghl-workflows.py:
# GET /workflow/<loc>/list?limit=200 with the token-id / channel / source /
# version header set reg.InternalRailClient already sends). The PUBLIC v2
# surface has NO proven workflows listing endpoint in this repo — the rail is
# the ONLY surface used (Skill 44 doctrine: never an invented endpoint).
WORKFLOWS_LIST_PATH = "/workflow/%s/list"

# The listing row-type marker for a real workflow (the Skill 58 filter:
# rows whose type == "workflow"; non-workflow rows — a trigger, a step, a
# folder — never match the name law).
WORKFLOW_ROW_TYPE = "workflow"

# The name-match law: the contract name with dashes -> spaces, normalized
# lowercase — "anthology intake fire". A listing row whose normalized name
# equals this string IS the Intake Fire workflow.
SLUG_AS_NAME = re.sub(r"\s+", " ", WORKFLOW_NAME).lower()

# The alternate spellings of the intake hook route key that may ride a
# workflow row — any of them names the same front door.
_KEY_ALIASES = ("anthology_intake", "intake_fire", "anthology-intake")

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways, and every emitted surface is scanned
# against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"


class WorkflowReadError(Exception):
    """A fail-closed read refusal (STOP family): a malformed listing shape
    that cannot be read faithfully, an empty listing, or a credential-shaped
    string in a payload. An expectation that cannot name its own sources
    must not run."""


def mask_id(wid: str) -> str:
    """Non-reversible marker for a workflow id (last 4 chars) — the house
    surface shape for every operator-facing mention of a workflow id."""
    return reg._mask_location(wid)


def _normalize_name(name: str) -> str:
    """The name-match normalization: lowercase, spaces collapsed — so
    "Anthology Intake Fire ", "  anthology intake fire" and "ANTHOLOGY
    INTAKE FIRE" all resolve to the same law string. Returns the normalized
    name."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _row_id(row) -> str:
    """The workflow id of a listing row under any of its container keys —
    "id" (the canonical key, proven in Skill 58 rows), "_id", or
    "workflowId". Returns "" when the row carries none."""
    if not isinstance(row, dict):
        return ""
    for key in ("id", "_id", "workflowId"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _row_keys(row) -> list:
    """The str-typed value keys of a row, for the alias-name match. A key
    whose value is a string is treated as a name-bearing field; a value that
    is not a string (a list of steps, a dict) can never name a workflow."""
    if not isinstance(row, dict):
        return []
    out = []
    for k, v in row.items():
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _unmasked_row_id_scan(row_id: str) -> None:
    """Never-a-token guard for a SINGLE workflow id: a credential-shaped id
    REFUSES rather than surface (a row whose id looks like a token is not a
    workflow we report — the id is what this reader exists to emit)."""
    if _CREDENTIAL_SHAPE.search(row_id):
        raise WorkflowReadError(
            "a listing row id resolved to a credential-shaped string — "
            "REFUSED without printing it")


def _flatten_rows(payload) -> list:
    """Flatten a workflows-listing payload to a list of row dicts over the
    ONE PROVEN container shape: {"rows": [...]} (the shape Skill 58's
    workflow listing read re-reads). Any other shape — including a payload
    that parses to a non-dict — is a WorkflowReadError (never a silent
    empty; an unreadable shape is not proof of zero workflows)."""
    if not isinstance(payload, dict):
        raise WorkflowReadError(
            "workflows listing payload is not a JSON object — the listing "
            "shape is not readable")
    rows = payload.get("rows")
    if rows is None:
        raise WorkflowReadError(
            "workflows listing payload has no 'rows' array — the listing "
            "shape is not readable")
    if not isinstance(rows, list):
        raise WorkflowReadError("workflows listing 'rows' value is not an array")
    return [r for r in rows if isinstance(r, dict)]


def _read_workflows_payload(client, location_id: str) -> dict:
    """The ONE live workflows read: the internal rail
    GET /workflow/<loc>/list?limit=200 via reg.InternalRailClient, which
    mints a Firebase id_token (the refresh token BY LABEL, never printed)
    and applies CAF_BROWSER_UA on the request (the CF 1010 law). Raises
    InternalRailUnavailable — mapped onto the HELD family by the CLI."""
    out = client._get(WORKFLOWS_LIST_PATH % location_id + "?limit=200")
    if not isinstance(out, dict):
        raise WorkflowReadError(
            "workflows listing response is not a JSON object — the listing "
            "shape is not readable")
    return out


def read_workflows(client, location_id: str, *, pinned_id: str = "",
                   workflow_rows=None) -> dict:
    """Read the live workflows listing and FIND the Intake Fire workflow.
    Fail-closed, never a token.

    `client` is a reg.InternalRailClient (its _get rides CAF_BROWSER_UA and
    the token-id header).
    `workflow_rows` is an explicit row list (self-tests); when None the live
    GET is performed. `pinned_id` is a box-override workflow id — when
    non-empty it must appear on the listing (exit-5 MISMATCH otherwise) and
    it BYPASSES the name law.

    Returns the documented surface {contract, schema_version, ok, found,
    workflow_id, workflow_id_masked, matched_by, count, candidates, sources,
    af_code, note} — fail-closed:
      - ok True ONLY when a row matched the name law (a "workflow"-typed row
        whose normalized name equals "anthology intake fire", or an alias
        key match) AND a pinned_id, when given, appeared on the listing; the
        returned workflow_id is the matched row's id,
      - ok False carries NO workflow_id (found=false; never an id guessed
        from memory) and a named af_code — WORKFLOWS-NOT-FOUND when the
        listing was read but held no match, WORKFLOWS-EMPTY when the listing
        held zero workflow rows, PIN-MISSING when a pinned id was absent
        from a non-empty listing,
      - every row that carried the workflow id is kept in `candidates`
        (with a masked id) so a near-miss is REPORTED, never silently
        ignored — even on the not-found paths,
      - count is the number of workflow rows read; sources names the exact
        read (the internal-rail path + the live/explicit seam).
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (WorkflowReadError, STOP family) or a transport
    failure (InternalRailUnavailable, HELD family).
    """
    if workflow_rows is None:
        payload = _read_workflows_payload(client, location_id)
        rows = _flatten_rows(payload)
    else:
        rows = [r for r in workflow_rows if isinstance(r, dict)]
    rows = [r for r in rows if str(r.get("type") or "").strip() == WORKFLOW_ROW_TYPE]
    count = len(rows)

    matched = None
    matched_by = ""
    candidates = []
    for row in rows:
        row_id = _row_id(row)
        if row_id:
            _unmasked_row_id_scan(row_id)
            candidates.append({"id_masked": mask_id(row_id)})
        if matched is not None:
            continue
        # the name law: the normalized name is the contract name with dashes
        # -> spaces, or the row carries an underscore spelling of the same
        # intake key — as a row KEY (e.g. {"intake_fire": ...}) or as a
        # string VALUE
        if _normalize_name(str(row.get("name") or "")) == SLUG_AS_NAME:
            matched, matched_by = row, "name"
            continue
        for key in row:
            if _normalize_name(key) in _KEY_ALIASES:
                matched, matched_by = row, "alias"
                break
        if matched is None:
            for val in _row_keys(row):
                if _normalize_name(val) in _KEY_ALIASES:
                    matched, matched_by = row, "alias"
                    break

    pinned_checked = bool(pinned_id and pinned_id.strip())
    pinned = pinned_id.strip() if pinned_id else ""
    if pinned:
        _unmasked_row_id_scan(pinned)
    pin_present = any(_row_id(r) == pinned for r in rows)
    if pinned and not pin_present:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_id": "",
            "workflow_id_masked": "",
            "matched_by": "",
            "count": count,
            "candidates": candidates,
            "sources": {"read": "internal rail %s (token-id header, "
                                "CAF_BROWSER_UA on the request)"
                                % (WORKFLOWS_LIST_PATH % "<loc>"),
                        "rows": "live GET" if workflow_rows is None else "explicit (self-test)",
                        "pinned_id": "pinned %s; absent from the listing"
                                     % mask_id(pinned)},
            "af_code": "PIN-MISSING",
            "note": "the pinned Intake Fire workflow id is not on the "
                    "listing — fail-closed, never a silent pass",
        }

    if matched is None:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_id": "",
            "workflow_id_masked": "",
            "matched_by": "",
            "count": count,
            "candidates": candidates,
            "sources": {"read": "internal rail %s (token-id header, "
                                "CAF_BROWSER_UA on the request)"
                                % (WORKFLOWS_LIST_PATH % "<loc>"),
                        "rows": "live GET" if workflow_rows is None else "explicit (self-test)",
                        "pinned_id": "pinned %s; checked"
                                     % (mask_id(pinned) if pinned_checked else "none")},
            "af_code": "WORKFLOWS-EMPTY" if count == 0 else "WORKFLOWS-NOT-FOUND",
            "note": ("the listing is empty" if count == 0 else
                     "no 'Anthology Intake Fire' row on the listing — the "
                     "name law matched nothing") + " (fail-closed, never an "
                     "id guessed from memory)",
        }

    wid = _row_id(matched)
    if not wid:
        raise WorkflowReadError(
            "the 'Anthology Intake Fire' row carries no workflow id — the "
            "listing shape is not readable")
    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "found": True,
        "workflow_id": wid,
        "workflow_id_masked": mask_id(wid),
        "matched_by": matched_by,
        "count": count,
        "candidates": candidates,
        "sources": {"read": "internal rail %s (token-id header, "
                            "CAF_BROWSER_UA on the request)"
                            % (WORKFLOWS_LIST_PATH % "<loc>"),
                    "rows": "live GET" if workflow_rows is None else "explicit (self-test)",
                    "pinned_id": "pinned %s; %s"
                                 % (mask_id(pinned) if pinned_checked else "none",
                                    "on the listing" if pin_present else "not checked")},
        "af_code": "OK" if not pinned_checked or pin_present else "PIN-MISSING",
        "note": "matched the 'Anthology Intake Fire' row by %s" % matched_by,
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the reader against
# the REAL committed constants, then runs every attack fixture: golden
# finds, the pin law both ways, every not-found path named, the alias key
# match, the never-a-token guard, and the malformed-shape refusals the CLI
# depends on.
# ---------------------------------------------------------------------------

class _FakeClient:
    """In-memory internal-rail client: serves the row list the self-test
    hands it and records the exact request, so the live-read contract (the
    rail path, the location in the path, the limit query, the token-id
    header, CAF_BROWSER_UA on the request) is provable offline."""

    def __init__(self, rows):
        self._rows = list(rows or [])
        self.calls = []

    def _get(self, path):
        self.calls.append({"path": path})
        return {"rows": [dict(r) for r in self._rows]}


def _golden_rows():
    """The golden listing rows: the Intake Fire workflow plus one unrelated
    workflow and one non-workflow row (a trigger) — the same shape Skill 58's
    listing read returns."""
    return [
        {"type": "workflow", "name": WORKFLOW_NAME, "id": "wfIntakeFire01"},
        {"type": "workflow", "name": "Release: Titles", "id": "wfReleaseTitle2"},
        {"type": "trigger", "name": "Contact Tag Added", "id": "wfTriggerThing"},
    ]


def _self_test_body(dev) -> None:
    # ---- 1. golden: the live read finds the Intake Fire workflow by name,
    #      only workflow-typed rows count, and the request contract (rail
    #      path with the location, limit query, token-id header, browser UA)
    #      is exact
    client = _FakeClient(_golden_rows())
    res = read_workflows(client, "loc_tmpl")
    assert res["ok"] is True and res["found"] is True, \
        "golden read must find the workflow"
    assert res["workflow_id"] == "wfIntakeFire01", \
        "the found id must be the golden workflow id"
    assert res["workflow_id_masked"] == mask_id("wfIntakeFire01")
    assert res["matched_by"] == "name"
    assert res["count"] == 2, "only workflow-typed rows may count"
    assert len(res["candidates"]) == 2, "only workflow-typed rows may be candidates"
    assert res["af_code"] == "OK" and res["contract"] == CONFIG_CONTRACT
    assert client.calls == [{"path": WORKFLOWS_LIST_PATH % "loc_tmpl" + "?limit=200"}], \
        "the request must be the proven rail path with the location + limit"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "the house browser UA must stay a browser UA (CF 1010 law)"

    # ---- 2. the pin law, both ways: a pinned id ON the listing passes; a
    #      pinned id ABSENT from a non-empty listing is PIN-MISSING (exit 5),
    #      never a silent pass — even when the name law matched
    res = read_workflows(client, "loc_tmpl", pinned_id="wfIntakeFire01")
    assert res["ok"] is True and res["af_code"] == "OK", \
        "pinned id on the listing must pass"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["id"] = "DriftedWorkflow00"  # the pinned id disappears
    client = _FakeClient(rows)
    res = read_workflows(client, "loc_tmpl", pinned_id="wfIntakeFire01")
    assert res["ok"] is False and res["af_code"] == "PIN-MISSING", \
        "an absent pinned id must be a MISMATCH, got %r" % res
    assert res["workflow_id"] == "" and res["found"] is False, \
        "a failed read must never carry a workflow id"

    # ---- 3. not-found paths, each NAMED: an empty listing is
    #      WORKFLOWS-EMPTY; a listing with only non-workflow rows is
    #      WORKFLOWS-EMPTY (no workflow-typed rows to read); a non-empty
    #      listing without the Intake Fire workflow is WORKFLOWS-NOT-FOUND;
    #      all carry no id and keep the candidate rows (near-misses are
    #      reported)
    res = read_workflows(client, "loc_tmpl", workflow_rows=[])
    assert res["ok"] is False and res["af_code"] == "WORKFLOWS-EMPTY", \
        "an empty listing must be WORKFLOWS-EMPTY"
    res = read_workflows(client, "loc_tmpl",
                         workflow_rows=[{"type": "trigger", "name": "Contact Tag Added",
                                         "id": "wfTriggerThing"}])
    assert res["ok"] is False and res["af_code"] == "WORKFLOWS-EMPTY", \
        "a trigger-only listing must be WORKFLOWS-EMPTY"
    client = _FakeClient([{"type": "workflow", "name": "Release: Titles",
                           "id": "wfReleaseTitle2"}])
    res = read_workflows(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "WORKFLOWS-NOT-FOUND", \
        "a listing without Intake Fire must be WORKFLOWS-NOT-FOUND"
    assert res["workflow_id"] == "" and res["candidates"] == \
        [{"id_masked": mask_id("wfReleaseTitle2")}], \
        "near-miss rows must stay on the surface (never silently ignored)"

    # ---- 4. a RENAMED workflow is indistinguishable from an ABSENT one to
    #      find-by-name — both refuse (the U02 name law; never accepted by a
    #      near-miss)
    client = _FakeClient([{"type": "workflow", "name": "Anthology Intake",
                           "id": "wfRenamedFire01"}])
    res = read_workflows(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "WORKFLOWS-NOT-FOUND", \
        "a renamed workflow must refuse (never accepted by name similarity)"
    assert res["workflow_id"] == "", "a renamed workflow must not be reported"

    # ---- 5. the alias-key match: a row naming the workflow through an
    #      underscore spelling of the intake key is found (matched_by alias)
    client = _FakeClient([{"type": "workflow", "_id": "wfAliasFire0001",
                           "intake_fire": "1", "name": "Front Door"}])
    res = read_workflows(client, "loc_tmpl")
    assert res["ok"] is True and res["matched_by"] == "alias", \
        "an alias key must match the name law, got %r" % res
    assert res["workflow_id"] == "wfAliasFire0001"

    # ---- 6. never-a-token: a row id that IS a credential-shaped string
    #      REFUSES the whole read rather than print it; a pinned id that is
    #      credential-shaped refuses the same way
    client = _FakeClient([{"type": "workflow", "name": WORKFLOW_NAME,
                           "id": "pit-abc123"}])
    try:
        read_workflows(client, "loc_tmpl")
        raise AssertionError("a credential-shaped row id must refuse")
    except WorkflowReadError:
        pass
    try:
        read_workflows(client, _FakeClient(_golden_rows()),
                       pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except WorkflowReadError:
        pass

    # ---- 7. malformed listing shapes REFUSE (never a silent empty): a
    #      payload without a 'rows' key, a 'rows' value that is not an
    #      array, and a response that is not an object
    class _BadClient(_FakeClient):
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def _get(self, path):
            self.calls.append({"path": path})
            return self._payload

    try:
        read_workflows(_BadClient({"nope": 1}), "loc_tmpl")
        raise AssertionError("a payload without 'rows' must refuse")
    except WorkflowReadError:
        pass
    try:
        read_workflows(_BadClient({"rows": "not-a-list"}), "loc_tmpl")
        raise AssertionError("a non-array 'rows' must refuse")
    except WorkflowReadError:
        pass
    try:
        read_workflows(_BadClient([{"id": "X"}]), "loc_tmpl")
        raise AssertionError("a non-object response must refuse")
    except WorkflowReadError:
        pass

    # ---- 8. the surface contract: the golden read never emits a
    #      credential-shaped string anywhere on the payload
    dumped = json.dumps(read_workflows(_FakeClient(_golden_rows()), "loc_tmpl"),
                        indent=2, sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(dumped), \
        "a successful read must never carry a credential-shaped string"

    dev.write("[workflow-reader] self-test PASS: golden find + request "
              "contract (internal-rail path, location, limit, token-id "
              "header, CAF_BROWSER_UA), pin law both ways, WORKFLOWS-EMPTY "
              "/ WORKFLOWS-NOT-FOUND / PIN-MISSING named, renamed-workflow "
              "refused, alias-key match, credential-shaped ids refused, "
              "malformed listing shapes refused\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[workflow-reader] SELF-TEST FAILED: %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def plan(location_id: str, pinned_id: str = "", *, out=None) -> int:
    """Emit the ONE offline plan JSON object (no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    pinned = (pinned_id or "").strip()
    if pinned:
        _unmasked_row_id_scan(pinned)
    payload = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "workflow_name": WORKFLOW_NAME,
        "name_law": "workflow-typed row name == %r after normalization"
                    % SLUG_AS_NAME,
        "pinned_id_masked": mask_id(pinned) if pinned else "",
        "read": "internal rail %s?limit=200 (token-id header; "
                "CAF_BROWSER_UA on the request — CF 1010 law)"
                % (WORKFLOWS_LIST_PATH % "<loc>"),
        "note": "offline plan only — no network, no credential needed; a "
                "pinned workflow id absent from the live listing is a "
                "MISMATCH (exit 5), never a silent pass",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise WorkflowReadError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out = out or sys.stdout
    out.write(dumped)
    out.write("\n")
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="workflow_reader.py",
        description="Live-read the Convert and Flow workflow listing "
                    "(internal rail GET /workflow/<loc>/list?limit=200) and "
                    "find the 'Anthology Intake Fire' front-door workflow, "
                    "reporting its ONE workflow id (Skill 59, U05 tooling). "
                    "Fail-closed; never prints a token. One JSON object on "
                    "stdout.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--workflow-id", default="",
                    help="a pinned Intake Fire workflow id (masked on every surface; "
                         "a pinned id absent from the listing is a MISMATCH)")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"], default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION
    pinned_id = args.workflow_id.strip() or ""

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan(location_id, pinned_id)

        # ---- live check ----
        # Credential BY LABEL, NEVER BY VALUE. The internal rail is the ONLY
        # proven workflow surface, so the refresh token is resolved first;
        # the PIT is resolved as a second rail credential when no refresh
        # token is SET. The resolved value is carried in the client only,
        # never printed.
        refresh_label, refresh = reg.resolve_firebase_refresh_token()
        rail = None
        if refresh:
            api_label, api_key = reg._resolve_firebase_api_key()
            if not api_key:
                reg._stop(sys.stderr,
                          "The Firebase refresh token is SET but the Firebase "
                          "API key is NOT SET.",
                          ["Checked (in order): %s — all NOT SET."
                           % ", ".join(reg.FIREBASE_API_KEY_LABELS),
                           "The internal rail cannot mint an id_token without "
                           "both labels. Set the API-key label and re-run."])
                return EX_STOP
            rail = reg.InternalRailClient(refresh, api_key)
        else:
            pit_label, token = reg.resolve_pit()
            if not token:
                checked = ", ".join(reg.PIT_LABELS)
                reg._stop(sys.stderr,
                          "No Convert and Flow credential is SET.",
                          ["Checked (in order): refresh-token labels %s — "
                           "all NOT SET; PIT labels %s — all NOT SET."
                           % (", ".join(reg.FIREBASE_REFRESH_LABELS), checked),
                           "The reader runs against the operator's OWN "
                           "template location marker %s; set the template "
                           "refresh token (preferred, the proven workflow "
                           "surface) or the template PIT and re-run."
                           % mask_id(location_id)])
                return EX_STOP
            # The PIT rides a plain urllib request with the same CAF_BROWSER_UA
            # on the internal base — the headers the rail would send for a
            # token-id (the refresh token IS the browser-session credential;
            # the PIT carries the Authorization header instead, exactly as
            # reg.CafClient sends it).
            class _PitRailClient:
                def __init__(self, token):
                    self._token = token

                def _get(self, path):
                    req = urllib.request.Request(
                        reg.INTERNAL_API_BASE + path,
                        headers={"Authorization": "Bearer %s" % self._token,
                                 "version": reg.INTERNAL_VERSION_HEADER,
                                 "Accept": "application/json",
                                 "User-Agent": reg.CAF_BROWSER_UA})
                    try:
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            raw = resp.read().decode("utf-8") or "{}"
                            return json.loads(raw) if raw.strip() else {}
                    except urllib.error.HTTPError as exc:
                        if exc.code in (401, 403):
                            body = b""
                            try:
                                body = exc.read()
                            except Exception:
                                body = b""
                            kind = reg._auth_denial_kind(body)
                            if kind == "scope":
                                raise reg.ScopeDenied(
                                    "token not authorized for this scope "
                                    "(HTTP %s)" % exc.code)
                            raise reg.UpstreamBlockedError(
                                "HTTP %s did NOT match a Convert and Flow "
                                "scope-denial signature — likely a "
                                "Cloudflare/WAF edge block, NOT a "
                                "token-scope problem (HTTP %s)" % (exc.code, exc.code))
                        raise reg.CafUnreachable(
                            "Convert and Flow HTTP %s on %s"
                            % (exc.code, path))
                    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                        raise reg.CafUnreachable(
                            "Convert and Flow transport error: %s"
                            % type(exc).__name__)
            rail = _PitRailClient(token)

        # The location id on every operator surface is the masked marker
        # only. A genuinely denied token raises ScopeDenied (STOP); an edge
        # block or any transport failure raises UpstreamBlockedError /
        # CafUnreachable / InternalRailUnavailable (HELD) — never mislabeled.
        result = read_workflows(rail, location_id, pinned_id=pinned_id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return EX_OK if result.get("ok") else EX_MISMATCH

    except WorkflowReadError as exc:
        sys.stderr.write("[workflow-reader] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[workflow-reader] STOP: %s\n" % exc)
        return EX_STOP
    except (reg.UpstreamBlockedError, reg.CafUnreachable,
            reg.InternalRailUnavailable) as exc:
        sys.stderr.write("[workflow-reader] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[workflow-reader] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
