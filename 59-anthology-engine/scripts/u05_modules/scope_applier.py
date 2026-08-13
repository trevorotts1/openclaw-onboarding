#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/scope_applier.py  (U05 tooling)
# WORKFLOW TRIGGER-SCOPE APPLIER — the write surface of the U05 family: it
# corrects the trigger SCOPE FILTER of a release-notification workflow (the
# tag->notification automation that turns each anthology-release-* tag into
# the author-facing email + SMS) so the workflow fires ONLY on its contract
# contact_tag trigger — and it REFUSES to write unless the operator
# explicitly passes --execute. Without --execute the tool is a DRY-RUN: it
# reads the live workflow + trigger, proves the scope law, and prints exactly
# the PUT it WOULD send — nothing is written, ever. Fail-closed: any
# ambiguity is a refusal, never a guessed write.
#
# WHY A DEDICATED MODULE: the U02 family (workflows_check.py /
# live_verify_template.py) checks that each of the EIGHT release workflows
# carries a contact_tag trigger ACTIVE on its contract trigger_tag
# (config/anthology-snapshot-contract.json workflows.release_notifications —
# the contract row the snapshot MUST carry; MASTER-SPEC U02 item 4). When a
# filter drifts (fires on the wrong tag, or on extra tags), ONLY a
# controlled, verified, gated write may fix it. This module is the single
# place that write exists in the engine's Python — the checkers are
# READ-ONLY by doctrine.
#
# THE SCOPE LAW: a release workflow fires ONLY on its contract trigger tag.
# The trigger is type "contact_tag"; its FILTER lives in the trigger's
# "conditions" array as the "tagsAdded" condition (the exact shape the
# Skill 44 build rail ships: {"operator": "index-of-true", "field":
# "tagsAdded", "value": <tag>, "title": "Tag Added", "type": "select",
# "id": "tag-added"}). "In scope" means: the workflow exists BYTE-EXACT
# under a contract release-notification name, carries EXACTLY ONE contact_tag
# trigger, and that trigger's tagsAdded filter value IS the contract
# trigger_tag.
#
# THE WRITE SURFACE (proven-rail only): PUT /workflow/{loc}/trigger/
# {trigger_id} through the internal Firebase rail
# (backend.leadconnectorhq.com) — the SAME rail the Skill 44 build
# (44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/
# workflow_builder.py) creates and updates trigger scope with, and the same
# rail workflows_check.py reads through. The public LeadConnector references
# (29-ghl-convert-and-flow/references/campaigns.md — Module: workflows)
# document ONLY GET /workflows/; NO public trigger-write surface is
# documented, so by house doctrine (only proven endpoints) the internal rail
# PUT is the ONE write surface this module performs.
#
# THE PUT BODY IS A COMPLETE REPLACEMENT — the trigger record read back live
# is echoed byte-for-byte (every key, order preserved) with ONLY the
# tagsAdded condition's value corrected to the contract tag. The body is
# built ONLY from the live read-back — never from the contract — so the write
# touches the filter and nothing else. A trigger with no readable tagsAdded
# condition REFUSES the plan (a body that could invent a filter is never
# constructed, even in dry-run).
#
# FAIL-CLOSED SURFACES:
#   * the target must be one of the EIGHT contract release workflows, and the
#     live workflow must be byte-exact that name BEFORE any write — absent,
#     duplicate-named, or present under a different name STOPS (a filter
#     write to the wrong record must be impossible),
#   * the workflow must carry EXACTLY ONE contact_tag trigger — zero STOPS
#     (no trigger to scope), two+ STOPS (scoping the wrong one is a guess);
#     other trigger types on the workflow are REPORTED, never judged,
#   * the tagsAdded filter value must be a BARE STRING — a list/dict/number
#     value is a structural shape the applier must not guess into (an
#     over-scoped multi-tag list such as [<tag>, "<other>"] REFUSES; a list
#     that is EXACTLY [<contract tag>] is an idempotent no-op PASS),
#   * the POST-PUT read-back must show the same trigger id, workflow id,
#     name, type, masterType, and active state byte-exact, the tagsAdded
#     value byte-exact the contract tag, and every OTHER condition preserved
#     — any drift is exit 5 with a delta, never a reported success,
#   * a PUT that returned success but cannot be read back is HELD (exit 3)
#     with the live state UNDETERMINED — never reported as applied,
#   * a rail rejection (the rail answers a rejected PUT as a parsed JSON
#     "_error" body, never an HTTP error status) is a STOP, never a silent
#     skip — the body is never surfaced,
#   * already-in-scope is an idempotent no-op PASS — nothing is written.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail rides a Firebase refresh
# token + API key resolved via anthology_registry (ANTHOLOGY_GHL_FIREBASE_*
# / GOHIGHLEVEL_FIREBASE_* — live process env first, then the canonical
# client env stores) and the location id is the CONTRACT's template location
# (source_template_location.template_location_id — operator infrastructure
# config, not a secret; the eight workflows are BUILT there), overridable
# with --location-id. SET / NOT SET only on every operator surface; a value
# is NEVER printed. Location, workflow and trigger ids are markers (last 4
# chars) on any operator surface; the full ids ride only inside request
# bodies.
#
# BROWSER UA: every request rides the internal-rail headers built by
# anthology_registry._internal_request_headers — which carry the
# CAF_BROWSER_UA (W0.6 / GK-09 discipline) so the Cloudflare edge fronting
# backend.leadconnectorhq.com never 1010s the applier (the exact failure
# mode that 403s urllib's default UA before the request reaches the rail).
# A rail response body is never surfaced (it could echo a credential).
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — dry-run plan pass, idempotent no-op, or applied + verified
#   1  unexpected error
#   2  STOP refusal — credential labels NOT SET, invalid names, a target
#      workflow absent/duplicated/not-byte-exact a contract row, a workflow
#      without exactly one contact_tag trigger, an unplannable filter (no
#      tagsAdded condition / non-string filter value), a non-contract
#      target, or a rail rejection of the PUT
#   3  HELD — internal rail unreachable / edge-blocked / Firebase exchange
#      failure (retryable; the scope is UNDETERMINED here, never proven
#      absent), including an applied-but-unreadable PUT
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  read-back mismatch after the PUT (trigger id/type/active/name/filter
#      drift)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO token and NO network):
#   scope_applier.py plan [--contract PATH]            # offline plan
#   scope_applier.py apply --workflow-name NAME
#                          [--workflow-id ID] [--location-id ID]
#                          [--execute]                 # dry-run unless
#                                                       # --execute
#   scope_applier.py self-test                          # offline fixtures
#
# --execute is the ONLY flag that performs the PUT. Its absence makes the
# apply run a dry-run: live reads only, nothing written, applied:false in the
# report. apply (dry-run included) needs the rail credentials — a truthful
# plan requires the live read; an unread state is never fabricated.
#
# STDLIB ONLY (urllib + json via the registry and this module); calls NO
# model. Reuses anthology_registry (InternalRailClient, resolve_firebase_
# refresh_token, _resolve_firebase_api_key, _internal_request_headers, _stop,
# _mask_location, InternalRailUnavailable and its exception classes).
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""scope_applier.py — gated, verified workflow trigger-scope applier against
the Anthology Convert and Flow template location (U05 tooling). Writes ONLY
with --execute; every other invocation is a read-only dry-run."""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location — operator infrastructure config, not a
# secret; the EIGHT release workflows were BUILT there per the contract
# workflows.build_rail). --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# Internal-rail surfaces proven live in this repo (Podcast gate; snapshot
# cut; live_verify_template.py U02; workflows_check.py U02): workflow list /
# trigger GET — plus the trigger PUT that the Skill 44 build rail performs
# (workflow_builder.py: PUT /workflow/{loc}/trigger/{trigger_id}). House
# doctrine: only proven endpoints.
_RAIL_WORKFLOW_LIST = "/workflow/{loc}/list?limit=200"
_RAIL_WORKFLOW_TRIGGER = "/workflow/{loc}/trigger?workflowId={wid}"
_RAIL_WORKFLOW_TRIGGER_PUT = "/workflow/{loc}/trigger/{trg}"

# Keys the rail stamps on a trigger record that are VOLATILE across a PUT
# (timestamps, canvas meta, sync flags) or absent from the GET shape — the
# scope surface NEVER judges them, so the read-back compare never trips on
# them. The scope surface is identity + type + active + name + conditions.
_VOLATILE_TRIGGER_KEYS = (
    "date_added", "date_updated", "deleted", "advanceCanvasMeta",
    "triggersChanged", "oldTriggers", "newTriggers",
    "company_id", "company_age", "schedule_config",
)

def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)

def _mask_id(rid: str) -> str:
    """Non-reversible resource-id marker (last 4 chars) for operator surfaces.
    The full id rides inside request bodies only, never on a surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"

def _looks_real(value: str) -> bool:
    """Fail-closed id guard: a placeholder or a whitespace-laden value is not
    a real workflow/trigger id and never reaches a request."""
    value = (value or "").strip()
    if not value:
        return False
    if value.lower() in ("replace-me", "<id>", "<workflow-id>", "none", "null"):
        return False
    return not any(ch.isspace() for ch in value)

class WorkflowMissing(Exception):
    """A fail-closed refusal (STOP family): the scope target is absent,
    duplicated, or present under a different name — a filter write to the
    wrong record must be impossible."""

class TriggerScopeRefused(Exception):
    """A fail-closed refusal (STOP family): the live trigger state is
    unplannable — e.g. no contact_tag trigger, more than one contact_tag
    trigger, no readable tagsAdded filter condition, a non-string filter
    value, or a rail rejection of the PUT. A body that could guess a filter
    is never constructed."""

# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is an error — never a
# pass). Same laws as workflows_check.py, applied to the WRITE surface.
# ---------------------------------------------------------------------------
def _load_contract(path: Path) -> dict:
    """Read + parse the contract; a missing or malformed file is a STOP."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TriggerScopeRefused("cannot read contract %s: %s" % (path, exc)) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise TriggerScopeRefused("contract %s is malformed JSON: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise TriggerScopeRefused("contract %s is not a JSON object" % path)
    return data

def _contract_rows(contract: dict) -> list:
    """The eight tag->notification workflow rows, copied so callers can never
    mutate the loaded contract. Missing/empty/non-object rows are a STOP."""
    rows = ((contract.get("workflows") or {}).get("release_notifications") or [])
    if not isinstance(rows, list) or not rows:
        raise TriggerScopeRefused(
            "contract workflows.release_notifications is missing or empty: %s"
            % CONTRACT_PATH)
    out = []
    for w in rows:
        if not isinstance(w, dict):
            raise TriggerScopeRefused(
                "contract workflows.release_notifications carries a non-object row: %r"
                % (w,))
        if not isinstance(w.get("name"), str) or not w["name"].strip():
            raise TriggerScopeRefused(
                "contract workflows.release_notifications carries a row with a "
                "blank name — a blind name-match cannot scope it: %s"
                % CONTRACT_PATH)
        if not isinstance(w.get("trigger_tag"), str) or not w["trigger_tag"].strip():
            raise TriggerScopeRefused(
                "contract workflow %r carries a blank trigger_tag — the scope "
                "law has no tag to bind: %s" % (w["name"], CONTRACT_PATH))
        out.append(dict(w))
    return out

def _contract_template_location(contract: dict) -> str:
    """The operator's OWN template location id (contract
    source_template_location.template_location_id). Not a secret — operator
    infrastructure config. Missing is a STOP."""
    loc = ((contract.get("source_template_location") or {}).get("template_location_id") or "")
    if not isinstance(loc, str) or not loc.strip():
        raise TriggerScopeRefused(
            "contract source_template_location.template_location_id is missing or empty")
    return loc.strip()

def _contract_row_by_name(rows: list, name: str) -> dict:
    """Byte-exact contract-row lookup (the house bind law). A target that is
    not one of the EIGHT contract release workflows STOPS — the applier never
    writes outside the U05 scope surface."""
    want = (name or "").strip()
    match = next((w for w in rows if (w.get("name") or "").strip() == want), None)
    if match is None:
        names = ", ".join(w.get("name") for w in rows)
        raise TriggerScopeRefused(
            "%r is NOT a contract release workflow — the applier only scopes "
            "the EIGHT contract rows (contract release workflows: %s)"
            % (want, names))
    return dict(match)

# ---------------------------------------------------------------------------
# The internal-rail client for the U05 surface: the reads workflows_check.py
# proved (list / trigger GET) plus the ONE write this module performs (the
# trigger PUT). The mint + header stack is the registry's — same Firebase
# exchange, same CAF_BROWSER_UA, same InternalRailUnavailable classification.
# ---------------------------------------------------------------------------
class ScopeRailClient(reg.InternalRailClient):
    """Internal-rail client for the trigger-scope surface. A response body is
    never surfaced (it could echo a credential)."""

    def put_trigger(self, location_id: str, trigger_id: str, body: dict) -> dict:
        """PUT /workflow/{loc}/trigger/{trigger_id} — the ONLY write surface
        this module performs. `body` is the complete-replacement payload
        built by build_scope_body(); the response is never surfaced verbatim.

        The rail answers a REJECTED PUT as a parsed JSON body with
        "_error": True (never an HTTP error status — the Skill 44 builder
        proved this shape), so the response is CLASSIFIED here: an _error
        body raises TriggerScopeRefused (STOP family)."""
        tok = self._token()
        url = reg.INTERNAL_API_BASE + _RAIL_WORKFLOW_TRIGGER_PUT.format(
            loc=urllib.parse.quote(location_id, safe=""),
            trg=urllib.parse.quote(trigger_id, safe=""))
        headers = dict(reg._internal_request_headers(tok))
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                parsed = json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            raise reg.InternalRailUnavailable(
                "internal rail HTTP %s on trigger PUT" % exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise reg.InternalRailUnavailable(
                "internal rail transport error on trigger PUT: %s"
                % type(exc).__name__) from exc
        if isinstance(parsed, dict) and parsed.get("_error"):
            raise TriggerScopeRefused(
                "the internal rail REJECTED the trigger PUT (classified "
                "refusal; the body is never surfaced)")
        return parsed if isinstance(parsed, dict) else {}

# ---------------------------------------------------------------------------
# Scope law / plan primitives.
# ---------------------------------------------------------------------------
def _listing_workflow_rows(rail, location_id: str) -> list:
    """The listing's 'workflow' rows. A listing with no rows array is a STOP
    (fail-closed — the applier must never plan from an unreadable list)."""
    out = rail._get(_RAIL_WORKFLOW_LIST.format(loc=location_id))
    rows = out.get("rows") if isinstance(out, dict) else None
    if not isinstance(rows, list):
        raise TriggerScopeRefused(
            "internal rail workflow list returned no rows array (marker %s)"
            % _mask_location(location_id))
    return [r for r in rows if isinstance(r, dict) and r.get("type") == "workflow"]

def find_workflow_by_name(rail, location_id: str, want: str) -> dict:
    """Byte-exact find-by-name (the house bind law). Returns the workflow row
    or raises WorkflowMissing — absent AND duplicate-named refuse (a filter
    write must never guess which of several same-named records is the
    contract one, and never target an absent one)."""
    matches = [r for r in _listing_workflow_rows(rail, location_id)
               if (r.get("name") or "").strip() == (want or "").strip()]
    if not matches:
        names = sorted({r.get("name") for r in _listing_workflow_rows(rail, location_id)
                        if r.get("name")})
        raise WorkflowMissing(
            "the workflow %r is ABSENT from the template location (found: %s). "
            "A filter write cannot target an absent workflow."
            % (want, ", ".join(names) or "(none)"))
    if len(matches) > 1:
        raise WorkflowMissing(
            "the workflow name %r matches %d live workflows — a filter write "
            "must never guess which record is the contract one; resolve the "
            "duplicate in the Convert and Flow UI and re-run with --workflow-id."
            % (want, len(matches)))
    return dict(matches[0])

def find_workflow_by_id(rail, location_id: str, workflow_id: str, want: str) -> dict:
    """By-id target with the SAME identity law: the live record must be
    byte-exact the contract name — a workflow id that exists under any OTHER
    name is a write to the wrong record and STOPS."""
    row = next((r for r in _listing_workflow_rows(rail, location_id)
                if str(r.get("id") or "") == str(workflow_id)), None)
    if row is None:
        raise WorkflowMissing(
            "workflow id %s is ABSENT from the template location"
            % _mask_id(workflow_id))
    if (row.get("name") or "").strip() != (want or "").strip():
        raise WorkflowMissing(
            "workflow id %s is present but named %r — NOT byte-exact the "
            "contract name %r; a filter write to the wrong record must be "
            "impossible." % (_mask_id(workflow_id), row.get("name") or "", want))
    return dict(row)

def _read_triggers(rail, location_id: str, workflow_id: str) -> list:
    """GET the workflow's trigger list through the rail (the surface
    workflows_check.py proved). A non-list answer is a STOP — never planned
    from a shape we cannot read."""
    out = rail._get(_RAIL_WORKFLOW_TRIGGER.format(
        loc=location_id, wid=urllib.parse.quote(workflow_id, safe="")))
    if not isinstance(out, list):
        raise TriggerScopeRefused(
            "internal rail trigger read returned no list (workflow marker %s)"
            % _mask_id(workflow_id))
    return [t for t in out if isinstance(t, dict)]

def _contact_tag_trigger(triggers: list, workflow_name: str) -> tuple:
    """The workflow's contact_tag trigger — EXACTLY ONE. Zero is a refusal
    (no trigger to scope); two or more is a refusal (scoping the wrong one
    is a guess). Other trigger types on the workflow are returned alongside
    for REPORTING — never judged."""
    contact = [t for t in triggers if (t.get("type") or "") == "contact_tag"]
    other = sorted({t.get("type") for t in triggers if t.get("type")
                    and t.get("type") != "contact_tag"})
    if not contact:
        raise TriggerScopeRefused(
            "the workflow %r carries NO contact_tag trigger (types seen: %s) "
            "— there is no trigger to scope; build the trigger first"
            % (workflow_name, ", ".join(other) or "(none)"))
    if len(contact) > 1:
        raise TriggerScopeRefused(
            "the workflow %r carries %d contact_tag triggers — a filter write "
            "must never guess which one is the contract trigger; consolidate "
            "the triggers in the Convert and Flow UI and re-run"
            % (workflow_name, len(contact)))
    return dict(contact[0]), sorted(other)

def _tags_added_condition(trigger: dict, workflow_name: str) -> dict:
    """The trigger's "tagsAdded" filter condition — the exact field the
    Skill 44 build rail ships. Absent (or not a JSON object) is a refusal: a
    body that could INVENT a filter is never constructed — not even for the
    dry-run report."""
    conditions = trigger.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise TriggerScopeRefused(
            "the contact_tag trigger of %r carries no conditions array — "
            "there is no filter to correct; refusing to plan"
            % workflow_name)
    found = next((c for c in conditions
                  if isinstance(c, dict) and c.get("field") == "tagsAdded"), None)
    if found is None:
        fields = sorted({c.get("field") for c in conditions
                         if isinstance(c, dict) and c.get("field")})
        raise TriggerScopeRefused(
            "the contact_tag trigger of %r has NO tagsAdded filter condition "
            "(fields seen: %s) — a filter write must never invent the tag "
            "condition; refusing to plan" % (workflow_name, ", ".join(fields) or "(none)"))
    return dict(found)

def _filter_value(condition: dict, workflow_name: str) -> object:
    """The tagsAdded filter value, REFUSED unless it is a bare string or a
    single-element list. A dict/number/None value is a structural shape the
    applier must not guess into (it cannot prove what the filter means)."""
    value = condition.get("value")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], str):
            return list(value)
        raise TriggerScopeRefused(
            "the tagsAdded filter of %r carries a multi-value list — an "
            "over-scoped filter (fires on more tags than the contract row) "
            "needs an operator decision in the Convert and Flow UI, never a "
            "guessed write; refusing to plan" % workflow_name)
    raise TriggerScopeRefused(
        "the tagsAdded filter of %r carries a non-string value (type %s) — "
        "correcting a filter of unknown shape is a guessed write; refusing "
        "to plan" % (workflow_name, type(value).__name__))

def _in_scope(value: object, want_tag: str) -> bool:
    """True when the filter ALREADY binds exactly the contract tag: a bare
    string equal to it, or a list that is exactly [tag]. Anything else needs
    a write (or refuses)."""
    if isinstance(value, str):
        return value == want_tag
    return isinstance(value, list) and value == [want_tag]

def build_scope_body(trigger: dict, want_tag: str, workflow_name: str) -> dict:
    """The filter-only PUT body. FAIL-CLOSED: the trigger PUT is a COMPLETE
    REPLACEMENT — every read-back key is echoed verbatim (order preserved),
    and ONLY the tagsAdded condition's value is corrected to the contract
    tag. The body is built ONLY from the live read-back, never from the
    contract, so the write touches the filter and nothing else."""
    out = {}
    for key, val in trigger.items():
        if key == "conditions":
            continue
        out[key] = val
    conditions = []
    for c in (trigger.get("conditions") or []):
        if not isinstance(c, dict):
            conditions.append(c)
            continue
        cc = dict(c)
        if cc.get("field") == "tagsAdded":
            cc["value"] = want_tag  # the ONLY mutation in the entire body
        conditions.append(cc)
    out["conditions"] = conditions
    return out

def _scope_sig(trigger: dict) -> dict:
    """The stable post-state surface the read-back must equal byte-exact:
    identity + type + active + name + the conditions array — AS READ. No
    normalization: a drifted tagsAdded value stays drifted so the compare
    against the PUT body (which carries the corrected value) fails closed.
    Volatile rail keys (timestamps, canvas meta, sync flags) are outside
    this surface and never judged."""
    return {
        "id": trigger.get("id"),
        "workflowId": trigger.get("workflowId", trigger.get("workflow_id")),
        "name": trigger.get("name"),
        "type": trigger.get("type"),
        "masterType": trigger.get("masterType"),
        "active": bool(trigger.get("active")),
        "conditions": trigger.get("conditions"),
    }

# ---------------------------------------------------------------------------
# The apply runner — dry-run unless --execute. Returns the exit code; ONE
# JSON object lands on stdout; human notes go to stderr.
# ---------------------------------------------------------------------------
def _report(*, ok: bool, applied: bool, dry_run: bool, workflow_name: str,
            trigger_tag: str, trigger_active: bool, trigger_id_marker: str,
            other_trigger_types: list, delta: list, loc_marker: str,
            wf_marker: str, note: str = "") -> None:
    """Emit the ONE JSON object (machine surface, stdout) for an apply run."""
    sys.stdout.write(json.dumps({
        "contract": "anthology-engine-trigger-scope-apply",
        "schema_version": 1,
        "ok": ok,
        "applied": applied,
        "dry_run": dry_run,
        "location_marker": loc_marker,
        "workflow_id_marker": wf_marker,
        "workflow_name": workflow_name,
        "trigger_tag": trigger_tag,
        "trigger_id_marker": trigger_id_marker,
        "trigger_type": "contact_tag",
        "trigger_active": trigger_active,
        "other_trigger_types": other_trigger_types,
        "delta": delta,
        "note": note,
    }, indent=2, sort_keys=True) + "\n")

def run_apply(rail, location_id: str, workflow_id: str, workflow_name: str,
              contract_row: dict, *, execute: bool = False, out=None) -> int:
    """Apply (or dry-run) the trigger-scope correction.

    - dry-run (execute False, the default): reads the live workflow and its
      trigger, proves the scope law, prints exactly the PUT it would send;
      the write is NEVER invoked.
    - execute (True): same reads, then the PUT, then the fail-closed
      read-back verify.
    Returns the house exit code. `rail` is a ScopeRailClient (the proven
    internal rail with the mint + CAF_BROWSER_UA header stack)."""
    out = out or sys.stderr
    loc_marker = _mask_location(location_id)
    workflow_name = (workflow_name or "").strip()
    want_tag = (contract_row.get("trigger_tag") or "").strip()
    want_name = (contract_row.get("name") or "").strip()
    wf_marker = _mask_id(workflow_id)
    trg_marker = ""
    trigger_active = False
    other_types: list = []

    def _note_delta(delta, applied_now, note):
        _report(ok=False, applied=applied_now, dry_run=not execute,
                workflow_name=workflow_name, trigger_tag=want_tag,
                trigger_active=trigger_active, trigger_id_marker=trg_marker,
                other_trigger_types=other_types, delta=delta,
                loc_marker=loc_marker, wf_marker=wf_marker, note=note)

    # ---- guards, before ANY read -----------------------------------------
    if not workflow_name:
        reg._stop(out, "The scope target workflow name is EMPTY.",
                  ["--workflow-name is required for apply.",
                   "Nothing was written (dry-run unless --execute)."])
        return EX_STOP
    if want_name != workflow_name:
        reg._stop(out, "The scope target is NOT a contract release workflow.",
                  ["%r is not the byte-exact name of any contract row; the "
                   "applier only scopes the EIGHT contract release workflows."
                   % workflow_name,
                   "Nothing was written."])
        return EX_STOP
    if not want_tag:
        reg._stop(out, "The contract row carries no trigger_tag.",
                  ["contract workflows.release_notifications row %r is missing "
                   "its trigger_tag — the scope law has no tag to bind."
                   % workflow_name,
                   "Nothing was written."])
        return EX_STOP
    if workflow_id and not _looks_real(workflow_id):
        reg._stop(out, "--workflow-id does not look like a real workflow id.",
                  ["A placeholder or whitespace-laden id never reaches a request.",
                   "Nothing was written (dry-run unless --execute)."])
        return EX_STOP

    # ---- resolve the target workflow (reads only) ------------------------
    try:
        if workflow_id:
            workflow = find_workflow_by_id(rail, location_id, workflow_id, want_name)
        else:
            workflow = find_workflow_by_name(rail, location_id, want_name)
            workflow_id = str(workflow.get("id") or "")
            wf_marker = _mask_id(workflow_id)
    except WorkflowMissing as exc:
        reg._stop(out, "The scope target is NOT present or NOT unique.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        _note_delta([{"item": "workflow", "status": "FAIL",
                      "detail": "target absent or duplicated",
                      "expected": want_name, "live": None}], False,
                    "target absent or duplicated")
        return EX_STOP
    except reg.InternalRailUnavailable as exc:
        out.write("[scope-applier] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, loc_marker))
        return EX_HELD

    # ---- read the trigger + prove the scope law (reads only) -------------
    try:
        triggers = _read_triggers(rail, location_id, workflow_id)
    except reg.InternalRailUnavailable as exc:
        out.write("[scope-applier] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, loc_marker))
        return EX_HELD
    except TriggerScopeRefused as exc:
        reg._stop(out, "Cannot read the workflow's trigger surface.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        return EX_STOP
    try:
        trigger, other_types = _contact_tag_trigger(triggers, want_name)
        condition = _tags_added_condition(trigger, want_name)
        value = _filter_value(condition, want_name)
    except TriggerScopeRefused as exc:
        reg._stop(out, "The trigger scope is unplannable.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        return EX_STOP
    trigger_id = str(trigger.get("id") or "")
    trg_marker = _mask_id(trigger_id)
    trigger_active = bool(trigger.get("active"))
    if not _looks_real(trigger_id):
        reg._stop(out, "The contact_tag trigger carries no real trigger id.",
                  ["A trigger without a readable id cannot be the PUT target; "
                   "refusing to plan.",
                   "Location marker: %s" % loc_marker, "Nothing was written."])
        return EX_STOP

    if _in_scope(value, want_tag):
        # Idempotent no-op: the filter already binds exactly the contract tag.
        out.write("[scope-applier] idempotent no-op (marker %s): workflow %r "
                  "already fires ONLY on its contract tag %r. Nothing to "
                  "write.\n" % (loc_marker, want_name, want_tag))
        _report(ok=True, applied=False, dry_run=False,
                workflow_name=want_name, trigger_tag=want_tag,
                trigger_active=trigger_active, trigger_id_marker=trg_marker,
                other_trigger_types=other_types, delta=[],
                loc_marker=loc_marker, wf_marker=wf_marker,
                note="already in scope — no write performed")
        return EX_OK

    # ---- build the plan (never a body that guesses a filter) -------------
    try:
        body = build_scope_body(trigger, want_tag, want_name)
    except TriggerScopeRefused as exc:
        reg._stop(out, "Cannot plan the scope correction.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        return EX_STOP

    if not execute:
        out.write("[scope-applier] DRY-RUN (no --execute, marker %s): would "
                  "PUT /workflow/{loc}/trigger/%s for workflow %r — the "
                  "trigger record echoed byte-for-byte with ONLY the "
                  "tagsAdded filter value corrected %r -> %r. No write "
                  "performed.\n" % (loc_marker, trg_marker, want_name, value, want_tag))
        _report(ok=True, applied=False, dry_run=True,
                workflow_name=want_name, trigger_tag=want_tag,
                trigger_active=trigger_active, trigger_id_marker=trg_marker,
                other_trigger_types=other_types, delta=[],
                loc_marker=loc_marker, wf_marker=wf_marker,
                note="dry-run — pass --execute to apply the PUT")
        return EX_OK

    # ---- the write (--execute only) --------------------------------------
    try:
        rail.put_trigger(location_id, trigger_id, body)
    except TriggerScopeRefused as exc:
        reg._stop(out, "The internal rail REFUSED the trigger update.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "The filter was NOT corrected. A rejection is a data "
                   "contract problem — resolve it in the Convert and Flow UI "
                   "and re-run.", "AF-AE-TRIGGER-SCOPE-VALIDATION."])
        _note_delta([{"item": "trigger_filter", "status": "FAIL",
                      "detail": "rail rejection of the PUT",
                      "expected": want_tag, "live": value}], False,
                    "rail rejected the PUT")
        return EX_STOP
    except reg.InternalRailUnavailable as exc:
        out.write("[scope-applier] HELD: %s (marker %s). "
                  "The PUT was NOT confirmed.\n" % (exc, loc_marker))
        return EX_HELD

    # ---- read-back verify (fail-closed) ----------------------------------
    try:
        live_triggers = _read_triggers(rail, location_id, workflow_id)
        live, live_other = _contact_tag_trigger(live_triggers, want_name)
        other_types = sorted(set(other_types) | set(live_other))
    except reg.InternalRailUnavailable as exc:
        out.write("[scope-applier] HELD (marker %s): the PUT returned success "
                  "but the read-back FAILED (%s). The live filter is "
                  "UNDETERMINED — never reported as corrected. Re-run to "
                  "verify.\n" % (loc_marker, exc))
        return EX_HELD
    except TriggerScopeRefused as exc:
        out.write("[scope-applier] MISMATCH (marker %s): the PUT returned "
                  "success but the read-back trigger structure no longer "
                  "carries exactly one contact_tag trigger (%s). The live "
                  "state is NOT the verified scope.\n" % (loc_marker, exc))
        _note_delta([{"item": "trigger_structure", "status": "FAIL",
                      "detail": "read-back lost the single contact_tag trigger",
                      "expected": "exactly one contact_tag", "live": "drifted"}],
                    True, "read-back structure drifted")
        return EX_MISMATCH

    expected = _scope_sig(body)
    live_sig = _scope_sig(live)
    delta = []
    if live_sig != expected:
        if live_sig.get("id") != expected.get("id"):
            delta.append({"item": "trigger_id", "status": "FAIL",
                          "detail": "trigger id changed after the PUT",
                          "expected": _mask_id(str(expected.get("id") or "")),
                          "live": _mask_id(str(live_sig.get("id") or ""))})
        if live_sig.get("workflowId") != expected.get("workflowId"):
            delta.append({"item": "trigger_workflow", "status": "FAIL",
                          "detail": "workflow binding changed after the PUT",
                          "expected": _mask_id(str(expected.get("workflowId") or "")),
                          "live": _mask_id(str(live_sig.get("workflowId") or ""))})
        if live_sig.get("type") != expected.get("type"):
            delta.append({"item": "trigger_type", "status": "FAIL",
                          "detail": "trigger type changed after the PUT",
                          "expected": expected.get("type"), "live": live_sig.get("type")})
        if live_sig.get("active") != expected.get("active"):
            delta.append({"item": "trigger_active", "status": "FAIL",
                          "detail": "trigger active state changed after the PUT",
                          "expected": expected.get("active"), "live": live_sig.get("active")})
        if live_sig.get("name") != expected.get("name"):
            delta.append({"item": "trigger_name", "status": "FAIL",
                          "detail": "trigger name changed after the PUT",
                          "expected": expected.get("name"), "live": live_sig.get("name")})
        if live_sig.get("conditions") != expected.get("conditions"):
            delta.append({"item": "trigger_filter", "status": "FAIL",
                          "detail": "filter conditions drifted after the PUT "
                                    "(tagsAdded value must be byte-exact the "
                                    "contract tag; every other condition "
                                    "preserved)",
                          "expected": want_tag, "live": "read-back drift"})
    if delta:
        reg._stop(out, "The PUT succeeded but the read-back does NOT match.",
                  [json.dumps(delta, sort_keys=True),
                   "Location marker: %s" % loc_marker,
                   "The live state is NOT the verified scope — investigate "
                   "before any further filter write."])
        _report(ok=False, applied=True, dry_run=False,
                workflow_name=want_name, trigger_tag=want_tag,
                trigger_active=trigger_active, trigger_id_marker=trg_marker,
                other_trigger_types=other_types, delta=delta,
                loc_marker=loc_marker, wf_marker=wf_marker,
                note="applied but read-back mismatch")
        return EX_MISMATCH

    out.write("[scope-applier] OK (marker %s): workflow %r now fires ONLY on "
              "its contract tag %r, read-back verified byte-exact (trigger "
              "id/type/active preserved; every other condition preserved).\n"
              % (loc_marker, want_name, want_tag))
    _report(ok=True, applied=True, dry_run=False,
            workflow_name=want_name, trigger_tag=want_tag,
            trigger_active=trigger_active, trigger_id_marker=trg_marker,
            other_trigger_types=other_types, delta=[],
            loc_marker=loc_marker, wf_marker=wf_marker,
            note="applied and verified")
    return EX_OK

# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture is refused, the write gate is
# honored by the runner itself, and the PUT body is never built from anything
# but the live read-back.
# ---------------------------------------------------------------------------
def _golden_trigger(want_tag: str, value=None, active: bool = True,
                    ttype: str = "contact_tag", trigger_id: str = "trg-0001",
                    workflow_id: str = "wf-0001", name: str = "Anthology Release: Avatar",
                    conditions=None) -> dict:
    """The canonical contact_tag trigger record — the shape the Skill 44
    build rail ships and the rail GET echoes back."""
    conds = conditions
    if conds is None:
        conds = [{"operator": "index-of-true", "field": "tagsAdded",
                  "title": "Tag Added", "type": "select", "id": "tag-added",
                  "value": want_tag if value is None else value}]
    return {"id": trigger_id, "workflowId": workflow_id, "name": name,
            "type": ttype, "masterType": "highlevel", "active": active,
            "conditions": conds}

class _FakeRail:
    """Internal-rail stub serving the trigger-scope surface: list rows +
    per-workflow trigger GET + the trigger PUT (which APPLIES the echoed body
    to the served record so the read-back reflects the write). Records every
    read and every PUT so the self-test can prove the write gate."""

    def __init__(self, rows=None, triggers=None, outcome="ok",
                 put_outcome="ok", put_readback=None, readback_unavailable=False):
        self._rows = [dict(r) for r in (rows or [])]
        self._triggers = {k: [dict(t) for t in v] for k, v in (triggers or {}).items()}
        self._outcome = outcome
        self._put_outcome = put_outcome
        self._put_readback = dict(put_readback) if put_readback else None
        self._readback_unavailable = readback_unavailable
        self._reads_ok = True
        self.calls = []
        self.puts = []

    def _get(self, path):
        self.calls.append(path)
        if self._outcome == "unavailable" or not self._reads_ok:
            raise reg.InternalRailUnavailable("fixture: rail unavailable")
        if "/list" in path:
            return {"rows": [dict(r) for r in self._rows]}
        if "trigger?" in path:
            wid = path.rsplit("=", 1)[-1]
            return [dict(t) for t in self._triggers.get(wid, [])]
        return {}

    def put_trigger(self, location_id, trigger_id, body):
        self.puts.append((location_id, trigger_id, body))
        if self._put_outcome == "refused":
            # Mirror the REAL client contract (ScopeRailClient.put_trigger):
            # a rejected PUT comes back as a parsed "_error" body, which the
            # client CLASSIFIES and raises — the runner sees the exception.
            raise TriggerScopeRefused(
                "the internal rail REJECTED the trigger PUT (classified "
                "refusal; the body is never surfaced)")
        if self._put_outcome == "unavailable":
            raise reg.InternalRailUnavailable("fixture: rail unavailable on PUT")
        if self._put_readback is not None:
            self._triggers[body.get("workflowId") or "wf-0001"] = [dict(self._put_readback)]
            if self._readback_unavailable:
                self._reads_ok = False  # PUT confirmed; the verify read is dead
            return dict(body)
        # Apply the echoed body: the read-back now carries the corrected filter.
        self._triggers[body.get("workflowId") or "wf-0001"] = [dict(body)]
        return dict(body)

def _golden_rows(contract: dict) -> list:
    rows = []
    for i, w in enumerate(_contract_rows(contract)):
        rows.append({"id": "wf-%04d" % i, "name": w.get("name"),
                     "type": "workflow", "parentId": "dir-tmpl"})
    return rows

def _golden_triggers(contract: dict) -> dict:
    return {"wf-%04d" % i: [_golden_trigger(
        w.get("trigger_tag"), trigger_id="trg-%04d" % i,
        workflow_id="wf-%04d" % i, name=w.get("name"))]
        for i, w in enumerate(_contract_rows(contract))}

def _run_apply(*, rail, workflow_name="Anthology Release: Avatar",
               workflow_id="", execute=False):
    """Self-test helper: capture stdout/stderr and return (exit, report).
    A non-contract workflow name refuses at the contract-row resolve — the
    SAME path main() takes — and surfaces here as (EX_STOP, None), mirroring
    the production STOP surface."""
    import contextlib
    contract = _load_contract(CONTRACT_PATH)
    try:
        row = _contract_row_by_name(_contract_rows(contract), workflow_name)
    except TriggerScopeRefused:
        return EX_STOP, None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_apply(rail, "loc_tmpl", workflow_id, workflow_name, row,
                       execute=execute, out=io.StringIO())
    report = None
    try:
        report = json.loads(buf.getvalue())
    except ValueError:
        report = None
    return rc, report

def _self_test_body(dev) -> None:
    global ScopeRailClient  # test 19 patches the module global so the CLI
    # surface stays OFFLINE; restored in its finally block.
    contract = _load_contract(CONTRACT_PATH)
    rows = _contract_rows(contract)
    want = rows[0]
    assert len(rows) == 8, "contract must carry exactly 8 release workflows, got %d" % len(rows)
    assert _contract_template_location(contract) == DEFAULT_TEMPLATE_LOCATION, \
        "contract template location drifted from the U05 default"
    assert want["name"] == "Anthology Release: Avatar", \
        "the first contract row drifted from the U05 fixture"
    want_tag = want["trigger_tag"]
    assert want_tag == "anthology-release-avatar", \
        "the avatar contract tag drifted from the U05 fixture"
    g_rows = _golden_rows(contract)
    g_trigs = _golden_triggers(contract)

    # ---- golden DRY-RUN: the write gate is honored by the runner itself ----
    # 1. dry-run with a DRIFTED filter (fires on the wrong tag): PASS, applied
    #    False, and the PUT was NEVER invoked.
    drifted = _golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")
    rail = _FakeRail(rows=g_rows, triggers={"wf-0000": [drifted]})
    rc, report = _run_apply(rail=rail, workflow_id="wf-0000")
    assert rc == EX_OK, "golden dry-run must exit 0, got %s" % rc
    assert report and report["ok"] is True, "golden dry-run must carry ok true"
    assert report["applied"] is False and report["dry_run"] is True, \
        "dry-run must report applied false / dry_run true"
    assert rail.puts == [], "dry-run must NEVER invoke the PUT (write gate)"

    # 2. golden EXECUTE: one PUT whose body echoes the pre-write trigger
    #    byte-for-byte with ONLY the tagsAdded value corrected; read-back
    #    passes; exit 0.
    rail2 = _FakeRail(rows=g_rows, triggers={"wf-0000": [drifted]})
    rc2, report2 = _run_apply(rail=rail2, workflow_id="wf-0000", execute=True)
    assert rc2 == EX_OK, "golden execute must exit 0, got %s" % rc2
    assert report2 and report2["applied"] is True and report2["dry_run"] is False
    assert len(rail2.puts) == 1, "execute must PUT exactly once"
    _, pid, body = rail2.puts[0]
    assert pid == "trg-0001", "PUT must target the trigger id from the live read"
    assert body["id"] == "trg-0001" and body["workflowId"] == "wf-0000", \
        "PUT body must echo the live trigger identity"
    assert body["type"] == "contact_tag" and body["active"] is True, \
        "PUT body must preserve type and active state"
    conds = body["conditions"]
    assert len(conds) == 1 and conds[0]["field"] == "tagsAdded", \
        "PUT body must carry the tagsAdded condition"
    assert conds[0]["value"] == want_tag, \
        "PUT body must correct the filter to the contract tag"
    assert conds[0]["operator"] == "index-of-true" and conds[0]["id"] == "tag-added", \
        "PUT body must preserve every OTHER condition key"

    # 3. idempotent no-op: already in scope -> PASS, no write (even with
    #    --execute).
    rail3 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value=want_tag)]})
    rc3, report3 = _run_apply(rail=rail3, workflow_id="wf-0000", execute=True)
    assert rc3 == EX_OK and report3 and report3["ok"] is True
    assert report3["applied"] is False
    assert rail3.puts == [], "idempotent no-op must never invoke the PUT"

    # 3b. ... and the single-element-list form [<tag>] is ALSO a no-op pass.
    rail3b = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value=[want_tag])]})
    rc3b, _ = _run_apply(rail=rail3b, workflow_id="wf-0000", execute=True)
    assert rc3b == EX_OK and rail3b.puts == [], \
        "exact [tag] list must be an idempotent no-op"

    # ---- attack fixtures: every mutation REFUSED --------------------------
    # 4. workflow ABSENT -> STOP (exit 2), no write.
    rail4 = _FakeRail(rows=[], triggers={})
    rc4, report4 = _run_apply(rail=rail4, workflow_id="wf-0000", execute=True)
    assert rc4 == EX_STOP, "absent workflow must STOP, got %s" % rc4
    assert report4 and report4["ok"] is False and report4["applied"] is False

    # 5. DUPLICATED name in the listing -> STOP (never a guessed write).
    dup_rows = [dict(g_rows[0]), dict(g_rows[0], id="wf-dup")]
    rail5 = _FakeRail(rows=dup_rows, triggers=g_trigs)
    rc5, _ = _run_apply(rail=rail5, workflow_name=want["name"], execute=True)
    assert rc5 == EX_STOP, "duplicated name must STOP, got %s" % rc5

    # 6. by-id target whose live name is NOT byte-exact the contract name ->
    #    STOP (write to the wrong record must be impossible).
    rail6 = _FakeRail(rows=[{"id": "wf-0000", "name": "Something Else",
                             "type": "workflow"}], triggers={})
    rc6, _ = _run_apply(rail=rail6, workflow_id="wf-0000", execute=True)
    assert rc6 == EX_STOP, "name-mismatched target must STOP, got %s" % rc6
    assert rail6.puts == [], "name-mismatched target must never be written"

    # 7. NO contact_tag trigger -> STOP.
    rail7 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [{"id": "trg-0001", "type": "contact_changed", "active": True,
                     "conditions": [{"field": "tagsAdded", "value": want_tag}]}]})
    rc7, _ = _run_apply(rail=rail7, workflow_id="wf-0000", execute=True)
    assert rc7 == EX_STOP, "triggerless workflow must STOP, got %s" % rc7

    # 8. TWO contact_tag triggers -> STOP (scoping the wrong one is a guess).
    rail8 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, trigger_id="trg-0001"),
                    _golden_trigger("anthology-release-tone", trigger_id="trg-0002")]})
    rc8, _ = _run_apply(rail=rail8, workflow_id="wf-0000", execute=True)
    assert rc8 == EX_STOP, "two contact_tag triggers must STOP, got %s" % rc8

    # 9. NO tagsAdded condition -> STOP; a body that could invent a filter is
    #    NEVER constructed — not even in dry-run.
    rail9 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, conditions=[
            {"field": "contactTagAdded", "value": want_tag}])]})
    rc9, _ = _run_apply(rail=rail9, workflow_id="wf-0000", execute=True)
    assert rc9 == EX_STOP, "missing tagsAdded condition must STOP, got %s" % rc9
    rc9b, _ = _run_apply(rail=rail9, workflow_id="wf-0000")
    assert rc9b == EX_STOP, "missing tagsAdded condition must STOP in dry-run too"

    # 10. OVER-SCOPED multi-value list -> STOP (an operator decision, never a
    #     guessed write).
    rail10 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value=[want_tag, "anthology-release-tone"])]})
    rc10, _ = _run_apply(rail=rail10, workflow_id="wf-0000", execute=True)
    assert rc10 == EX_STOP, "over-scoped list must STOP, got %s" % rc10

    # 11. NON-STRING filter value (dict) -> STOP.
    rail11 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value={"tag": want_tag})]})
    rc11, _ = _run_apply(rail=rail11, workflow_id="wf-0000", execute=True)
    assert rc11 == EX_STOP, "non-string filter value must STOP, got %s" % rc11

    # 12. read-back filter drift after a successful PUT -> exit 5 with a delta.
    rail12 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")]},
        put_readback=_golden_trigger(want_tag, value="anthology-release-tone",
                                     workflow_id="wf-0000"))
    rc12, report12 = _run_apply(rail=rail12, workflow_id="wf-0000", execute=True)
    assert rc12 == EX_MISMATCH, "read-back drift must exit 5, got %s" % rc12
    assert report12 and report12["ok"] is False and report12["applied"] is True
    assert any("trigger_filter" in str(d.get("item")) for d in report12["delta"]), \
        "drift report must carry the filter delta"

    # 13. read-back active-state drift after a successful PUT -> exit 5.
    rail13 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")]},
        put_readback=_golden_trigger(want_tag, value=want_tag, active=False,
                                     workflow_id="wf-0000"))
    rc13, report13 = _run_apply(rail=rail13, workflow_id="wf-0000", execute=True)
    assert rc13 == EX_MISMATCH, "active-state drift must exit 5, got %s" % rc13
    assert any("trigger_active" in str(d.get("item")) for d in report13["delta"])

    # 14. PUT succeeded but read-back unreachable -> HELD (exit 3), applied
    #     state UNDETERMINED — never reported as corrected, never exit 0.
    #     (PUT confirmed, then the verify read dies.)
    rail14 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")]},
        put_readback=dict(_golden_trigger(want_tag, workflow_id="wf-0000")),
        readback_unavailable=True)
    rc14, _ = _run_apply(rail=rail14, workflow_id="wf-0000", execute=True)
    assert rc14 == EX_HELD, "applied-but-unreadable must be HELD, got %s" % rc14
    assert len(rail14.puts) == 1, "the PUT did happen — the HELD is about verify"

    # 15. rail REJECTION of the PUT (_error body) -> STOP (exit 2), never a
    #     silent skip.
    rail15 = _FakeRail(rows=g_rows, triggers={
        "wf-0000": [_golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")]},
        put_outcome="refused")
    rc15, report15 = _run_apply(rail=rail15, workflow_id="wf-0000", execute=True)
    assert rc15 == EX_STOP, "rail rejection must STOP, got %s" % rc15
    assert report15 and report15["applied"] is False

    # 16. rail unavailable on the READ -> HELD (exit 3), never a fabricated
    #     plan.
    rail16 = _FakeRail(rows=g_rows, triggers=g_trigs, outcome="unavailable")
    rc16, _ = _run_apply(rail=rail16, workflow_id="wf-0000")
    assert rc16 == EX_HELD, "unavailable rail must be HELD, got %s" % rc16

    # 17. placeholder workflow id -> STOP, never a request.
    rail17 = _FakeRail(rows=g_rows, triggers=g_trigs)
    rc17, _ = _run_apply(rail=rail17, workflow_id="REPLACE-ME", execute=True)
    assert rc17 == EX_STOP, "placeholder workflow id must STOP, got %s" % rc17
    assert rail17.calls == [], "placeholder id must never reach a request"

    # 18. a NON-CONTRACT workflow name -> STOP.
    rail18 = _FakeRail(rows=g_rows, triggers=g_trigs)
    rc18, _ = _run_apply(rail=rail18, workflow_name="Not A Contract Workflow",
                         execute=True)
    assert rc18 == EX_STOP, "non-contract target must STOP, got %s" % rc18

    # 19. CLI: apply WITHOUT --execute -> exit 0, dry_run true, applied false,
    #     and the PUT is never invoked (the gate holds at the CLI boundary
    #     too). The credential/client surface is monkeypatched so the
    #     self-test stays OFFLINE — no real token resolution, no network.
    import contextlib
    real_refresh = reg.resolve_firebase_refresh_token
    real_apikey = reg._resolve_firebase_api_key
    real_rail_cls = ScopeRailClient

    class _CliFakeRail(_FakeRail):
        def __init__(self, *a, **kw):
            super().__init__(rows=_golden_rows(contract),
                             triggers=_golden_triggers(contract))
            self._triggers["wf-0000"] = [
                _golden_trigger(want_tag, value="anthology-release-tone", workflow_id="wf-0000")]

    cli_rail = _CliFakeRail()
    reg.resolve_firebase_refresh_token = lambda: ("ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN", "tok-fake")
    reg._resolve_firebase_api_key = lambda: ("ANTHOLOGY_GHL_FIREBASE_API_KEY", "key-fake")
    ScopeRailClient = lambda refresh, api_key, timeout=15: cli_rail  # noqa: F811
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc19 = main(["apply", "--workflow-name", "Anthology Release: Avatar",
                         "--location-id", "loc_tmpl"])
    finally:
        reg.resolve_firebase_refresh_token = real_refresh
        reg._resolve_firebase_api_key = real_apikey
        ScopeRailClient = real_rail_cls  # noqa: F811
    assert rc19 == EX_OK, "CLI apply without --execute must exit 0, got %s" % rc19
    report19 = json.loads(buf.getvalue())
    assert report19["dry_run"] is True and report19["applied"] is False
    assert cli_rail.puts == [], "CLI dry-run must never invoke the PUT"

    dev.write("scope_applier self-test: OK (contract pinned to the 8 "
              "release workflows + template location; golden dry-run + golden "
              "execute + idempotent no-op PASS; 16 attack fixtures refused: "
              "absent / duplicated-name / name-mismatch / no-trigger / "
              "two-triggers / no-tagsAdded / over-scoped-list / non-string-"
              "value / read-back-filter-drift / read-back-active-drift / "
              "applied-unreadable-HELD / rail-rejection / rail-unavailable / "
              "placeholder-id / non-contract-target / CLI-write-gate; the PUT "
              "is never invoked without --execute, and the PUT body is never "
              "built from anything but the live read-back)\n")

def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[scope-applier] SELF-TEST FAILED "
                         "(U05 TRIGGER-SCOPE ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

# ---------------------------------------------------------------------------
# CLI — house shape: plan / apply / self-test subcommands; --execute is the
# ONLY write gate.
# ---------------------------------------------------------------------------
def _offline_plan(contract: dict) -> int:
    """Offline plan: the eight contract rows + the PUT surface and semantics
    — no network, no credential needed."""
    rows = _contract_rows(contract)
    print(json.dumps({
        "contract": "anthology-engine-trigger-scope-apply-plan",
        "schema_version": 1,
        "template_location": DEFAULT_TEMPLATE_LOCATION,
        "workflows": [{"name": w.get("name"), "trigger_tag": w.get("trigger_tag")}
                      for w in rows],
        "write_surface": "PUT /workflow/{locationId}/trigger/{triggerId} "
                         "(internal Firebase rail, backend.leadconnectorhq.com "
                         "— the SAME rail the Skill 44 build uses; the public "
                         "LeadConnector references document ONLY GET "
                         "/workflows/, so by house doctrine this proven rail "
                         "PUT is the one write surface)",
        "semantics": "the trigger record read back live is echoed byte-for-"
                     "byte with ONLY the tagsAdded condition's value "
                     "corrected to the contract trigger_tag — the PUT is a "
                     "complete replacement, so anything else in the record "
                     "is preserved verbatim",
        "write_gate": "the PUT is performed ONLY with --execute; without it "
                      "the apply run is a read-only dry-run",
        "verify": "post-PUT read-back must show the same trigger id/type/"
                  "active/name with the tagsAdded value byte-exact the "
                  "contract tag — any drift is exit 5, an unreadable "
                  "read-back is HELD (exit 3)",
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scope_applier.py",
        description="Workflow trigger-SCOPE APPLIER against the Anthology "
                    "Convert and Flow template location (U05): each release "
                    "workflow must fire ONLY on its contract contact_tag "
                    "trigger. PUT /workflow/{loc}/trigger/{id} through the "
                    "proven internal rail, applied ONLY with --execute. "
                    "Without --execute the run is a read-only dry-run that "
                    "prints exactly the PUT it would send — nothing is "
                    "written, ever. One JSON object on stdout; fail-closed; "
                    "never prints a secret (Skill 59).")
    ap.add_argument("--location-id", default="",
                    help="override the location id (default: the contract "
                         "source_template_location.template_location_id; "
                         "never printed)")
    ap.add_argument("--workflow-id", default="",
                    help="target workflow by id (default: resolve the "
                         "contract workflow BY NAME)")
    ap.add_argument("--workflow-name", default="",
                    help="the contract release workflow name to scope "
                         "(required for apply)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json (the "
                         "release workflow rows + template location)")
    ap.add_argument("--execute", action="store_true",
                    help="REQUIRED for the write: perform the PUT. Without it "
                         "the apply run is a read-only dry-run")
    ap.add_argument("cmd", nargs="?", choices=["plan", "apply", "self-test"],
                    default="apply")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        contract = _load_contract(Path(args.contract).expanduser())
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return _offline_plan(contract)

        # ---- apply (dry-run unless --execute) ----
        workflow_name = args.workflow_name.strip()
        if not workflow_name:
            reg._stop(sys.stderr, "--workflow-name is required for apply.",
                      ["Nothing was written (dry-run unless --execute)."])
            return EX_STOP
        try:
            row = _contract_row_by_name(_contract_rows(contract), workflow_name)
        except TriggerScopeRefused as exc:
            reg._stop(sys.stderr, "The scope target is NOT a contract "
                                  "release workflow.",
                      [str(exc), "Nothing was written."])
            return EX_STOP

        rt_label, refresh = reg.resolve_firebase_refresh_token()
        ak_label, api_key = reg._resolve_firebase_api_key()
        if not refresh or not api_key:
            checked = ", ".join(reg.FIREBASE_REFRESH_LABELS)
            reg._stop(sys.stderr, "No internal-rail credential is SET.",
                      ["The trigger read + write ride the internal rail "
                       "(Firebase refresh token + API key).",
                       "Checked (in order): %s — all NOT SET." % checked,
                       "Set the template location's OWN Firebase labels and "
                       "re-run.", "A truthful dry-run needs the live read."])
            return EX_STOP
        location_id = args.location_id.strip() or _contract_template_location(contract)
        rail = ScopeRailClient(refresh, api_key)

        return run_apply(rail, location_id, args.workflow_id.strip(),
                         workflow_name, row, execute=args.execute,
                         out=sys.stderr)

    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[scope-applier] HELD: internal rail unavailable: "
                         "%s\n" % exc)
        return EX_HELD
    except (WorkflowMissing, TriggerScopeRefused) as exc:
        sys.stderr.write("[scope-applier] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[scope-applier] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
