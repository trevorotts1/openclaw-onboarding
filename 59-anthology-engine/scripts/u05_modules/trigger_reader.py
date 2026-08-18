#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/trigger_reader.py  (U05 tooling)
# TRIGGER FILTER-SET READER — the OFFLINE read that extracts the TRIGGER
# FILTER SET from the shipped n8n Drive-broker workflow asset
# (config/n8n/anthology-drive-broker.workflow.json): the webhook trigger
# gate, the Authorize & Dispatch filter law (token gate, action allowlist,
# probe / capabilities short-circuits), pinned byte-exact against the
# engine's OWN authority (drive_adapter.BROKER_REQUIRED_ACTIONS). OFFLINE
# plan + offline self-test always work; the read NEVER touches the network
# and NEVER resolves a credential value — the token env label is reported
# by STATE ONLY (SET / NOT SET), never by value.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u05_modules/ — an importable module under the U05
# package (pure namespace container per the u05 __init__.py: imported BY
# NAME, side-effect-free at import). It ships as the shared OFFLINE trigger
# surface the U05 verification family imports, so the filter-set semantics
# can NEVER drift between this reader and its callers — the delta_reporter.py
# single-implementation doctrine (a contract read once, in one module). It is
# the reader sibling of the U05 family: workflow_reader.py (the LIVE
# "Anthology Intake Fire" workflow finder, internal rail), scope_checker.py
# (the intake filter law), golden_scoped.py / attack_unscoped.py /
# attack_wrong_form.py (the fixtures). THIS module owns the n8n Drive-broker
# trigger path: what the webhook front door and its Authorize & Dispatch
# gate filter on, extracted byte-exact from the shipped asset.
#
# WHAT THE TRIGGER FILTER SET IS (the surface this module owns):
#   1. THE TRANSPORT GATE. The webhook trigger node ("n8n-nodes-base.webhook")
#      carries the gate parameters: httpMethod (POST), the path
#      ("anthology-drive" — the ONLY path the broker answers), and the
#      responseMode ("responseNode"). A drifted method or path is a filter
#      set that answers on the wrong door — never certified.
#   2. THE AUTH GATE (the filter law node). "Authorize & Dispatch" (the
#      n8n-nodes-base.code node whose parameters.jsCode implements the
#      broker's authorization + dispatch) reads the shared token BY LABEL
#      ($env.ANTHOLOGY_DRIVE_BROKER_TOKEN), accepts it from the header keys
#      x-anthology-broker-token / X-Anthology-Broker-Token or the body
#      `token` fallback, refuses broker_misconfigured (500) when the env
#      label is unset and unauthorized (401) when the presented token does
#      not equal the expected one, and refuses missing_action / unknown_action
#      (400) — the filter law of the front door.
#   3. THE ACTION ALLOWLIST. The closed set of implemented actions the gate
#      filters dispatch by: the DOC_ACTIONS / TREE_ACTIONS literals in the
#      jsCode, pinned BYTE-EXACT (as a set) against the engine authority
#      drive_adapter.BROKER_REQUIRED_ACTIONS — the same six actions the
#      broker-preflight probe requires BY NAME. An allowlist that drifted
#      (a renamed, missing, or extra action) is a filter set that cannot be
#      certified: af_code ALLOWLIST-DRIFT, exit 5 — never a pass.
#   4. THE SHORT-CIRCUITS. The capabilities probe ("action ===
#      'capabilities'", the broker-preflight ask) and the side-effect-free
#      probe ("body.probe === true") — the two filter exemptions the
#      preflight falls back on. An asset that lost them is a filter set the
#      preflight can no longer trust.
#
# THE READ LAW (fail-closed, the point): the extraction NEVER fabricates a
# filter set. A workflow that is not a JSON object, an asset with no nodes
# array, ZERO webhook trigger nodes (TRIGGER-MISSING), MORE than one
# (TRIGGER-AMBIGUOUS — a webhook path can be active on only one workflow, and
# one workflow carries one trigger), a trigger node whose gate parameters are
# absent or empty (STOP), an absent or duplicated Authorize & Dispatch node
# (AUTH-GATE-MISSING / AUTH-GATE-AMBIGUOUS), a jsCode that lost the token
# env label, the 401 unauthorized refusal, the action literals, or the
# probe / capabilities short-circuits (STOP), or an allowlist that drifted
# from the authority (ALLOWLIST-DRIFT, exit 5) — every one of those is a
# REFUSAL / MISMATCH, never a silent pass. A data mismatch is a RESULT
# (ok False + a named af_code, the fail-closed default); a shape that cannot
# be read faithfully raises TriggerReadError (STOP family, exit 2) exactly
# like form_reader's FormsReadError / workflow_reader's WorkflowReadError —
# reading on would fabricate a filter set.
#
# NEVER-A-TOKEN SURFACE: the token env label is resolved BY LABEL ONLY
# (os.environ key "ANTHOLOGY_DRIVE_BROKER_TOKEN"; state reported as SET /
# NOT SET, the value NEVER printed, echoed, or reflected — the same doctrine
# every U02..U05 surface carries). The jsCode body is the filter LAW, not
# reportable data: it is never echoed; only the extracted markers (the env
# label, the header keys, the refusal codes, the allowlist, the short-circuit
# flags) ride the report. Every emitted surface is scanned against the house
# credential shape (pit-<value>) before print — a hit REFUSES the whole
# surface rather than print it (the delta_reporter.py never-a-real-token
# doctrine). The shipped asset carries NO token value (the token comes from
# $env inside n8n); the reader still proves the never-print law offline.
#
# BROWSER UA (CF 1010 LAW): THIS module makes NO network request — it is the
# OFFLINE read of the shipped asset (the sibling that talks to the platform
# live, workflow_reader.py, rides reg.InternalRailClient / reg.CafClient,
# which apply CAF_BROWSER_UA on every request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge, CF error 1010, before the request ever reaches
# Convert and Flow). The self-test pins the house constant so a registry
# regression is caught HERE first.
#
# RETURN CONTRACT (the machine surface this module owns):
#   read_trigger(workflow=None, *, workflow_path=None) -> dict — {"contract",
#       "schema_version", "ok", "found", "workflow_name", "workflow_active",
#       "source", "trigger", "auth_gate", "actions", "short_circuits",
#       "filter_set", "delta", "af_code", "note"} — fail-closed:
#       - ok True ONLY when the webhook trigger node was found, its gate
#         parameters read, the Authorize & Dispatch filter law extracted,
#         and the allowlist byte-equals the engine authority,
#       - ok False carries a named af_code (TRIGGER-MISSING /
#         TRIGGER-AMBIGUOUS / AUTH-GATE-MISSING / AUTH-GATE-AMBIGUOUS /
#         ALLOWLIST-DRIFT) and NO filter set — never a filter set fabricated
#         from a broken read,
#       - a shape that cannot be read faithfully raises TriggerReadError
#         (STOP family, exit 2) — never a silent empty,
#       - every node id is reported by MASKED MARKER only (last 4 chars),
#         and the token env label by STATE ONLY (SET / NOT SET).
#   plan(*, out=sys.stdout) -> int — ONE JSON object, offline, no network,
#       no credential.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (reads the REAL committed asset as its strongest golden control;
#       needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers check / plan / self-test.
#
# EXIT CODES (house convention 0/1/2/4/5; this module is OFFLINE — the HELD
# family (3) does not apply: there is no network surface to hold):
#   0  PASS — the trigger filter set was extracted and certified (also plan
#      / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — the asset cannot be read (missing file, invalid JSON),
#      the workflow shape cannot be read faithfully, or a credential-shaped
#      string appeared on a surface
#   4  self-test FAILED (AF-AE-TEMPLATE-ATTACK family; a tamper NEVER
#      masquerades as exit 1)
#   5  MISMATCH — no webhook trigger node, an ambiguous trigger, a missing /
#      ambiguous auth-gate node, or an allowlist that drifted from the
#      engine authority (the fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   trigger_reader.py check [--workflow PATH]
#   trigger_reader.py plan
#   trigger_reader.py self-test
#
# STDLIB ONLY (json + re + pathlib + os.environ-by-label). Calls NO model.
# Reuses anthology_registry (exit-code constants, CAF_BROWSER_UA pin,
# _mask_location) and drive_adapter (BROKER_REQUIRED_ACTIONS — the ONE
# allowlist authority, never duplicated here). DOCTRINE: move in silence;
# NOTHING Anthropic in any runtime file; Convert and Flow naming in every
# client surface; NEVER print a secret value; a label state is SET / NOT SET
# only.
# =============================================================================
"""trigger_reader.py — OFFLINE reader of the n8n Drive-broker workflow's
trigger filter set (Skill 59, U05 tooling): the webhook trigger gate, the
Authorize & Dispatch filter law, and the action allowlist, extracted
byte-exact from the shipped asset and pinned to the engine authority."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to form_reader.py /
# workflow_reader.py): the registry owns the exit-code contract, the
# Cloudflare browser-UA constant, and the masking helper; drive_adapter owns
# the ONE allowlist authority (BROKER_REQUIRED_ACTIONS) — never duplicated.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import drive_adapter as da  # noqa: E402  (the action-allowlist authority)

EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
# The shipped n8n Drive-broker workflow asset — the ONE asset this reader
# exists for (config/n8n/, the sanctioned asset per the README: 54 nodes,
# webhook path "anthology-drive", ships INACTIVE — the import checklist
# activates it after wiring creds/env).
WORKFLOW_PATH = SKILL_DIR / "config" / "n8n" / "anthology-drive-broker.workflow.json"

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a trigger
# filter-set read (the self-test asserts the golden check carries the exact
# string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-trigger-read"
CONFIG_SCHEMA_VERSION = 1

# The webhook trigger node — the ONE trigger type the broker front door may
# carry (n8n webhook trigger; a webhook path can be active on only one
# workflow, and the shipped broker carries one trigger).
TRIGGER_NODE_TYPE = "n8n-nodes-base.webhook"
TRIGGER_NODE_NAME = "Webhook anthology-drive"

# The auth-gate node — the n8n code node whose jsCode implements the
# broker's filter law (token gate + action allowlist + short-circuits).
AUTH_GATE_NODE_NAME = "Authorize & Dispatch"
AUTH_GATE_NODE_TYPE = "n8n-nodes-base.code"

# The broker's OWN token env label inside the workflow (the value a client
# box holds as N8N_DRIVE_WEBHOOK_TOKEN — the da.N8N_WEBHOOK_TOKEN_ENV pairing;
# this reader reports the WORKFLOW's label by STATE ONLY, never a value).
BROKER_TOKEN_ENV_LABEL = "ANTHOLOGY_DRIVE_BROKER_TOKEN"

# The header keys (and the body fallback) the auth gate accepts the shared
# token from — the exact keys the jsCode reads (byte-exact; da.BROKER_TOKEN_
# HEADER is the canonical spelling).
BROKER_TOKEN_HEADER_KEYS = (
    "x-anthology-broker-token",
    "X-Anthology-Broker-Token",
)
BROKER_TOKEN_BODY_FALLBACK = "body.token"

# The refusal law the auth gate must implement — the error names and the
# HTTP codes the jsCode rejects with (fail-closed: a gate that lost a
# refusal answers without a filter).
AUTH_REFUSALS = {
    "broker_misconfigured": 500,
    "unauthorized": 401,
    "missing_action": 400,
    "unknown_action": 400,
}

# The short-circuit markers the auth gate must carry (the preflight asks
# "capabilities"; the side-effect-free probe is the preflight fallback).
CAPABILITIES_MARKER = "action === 'capabilities'"
PROBE_MARKER = "body.probe === true"

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "TOKEN" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways, and every emitted surface is scanned
# against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")

# The allowlist extraction law: the jsCode carries the action literals as
# "const DOC_ACTIONS = [...]" / "const TREE_ACTIONS = [...]" — the ONE shape
# the reader accepts (the shipped asset's own shape; a drifted literal shape
# is an unreadable allowlist, never a guess).
_ALLOWLIST_CONST_RE = re.compile(r"^const\s+(DOC_ACTIONS|TREE_ACTIONS)\s*=\s*\[([^\]]*)\]")
_ALLOWLIST_ITEM_RE = re.compile(r"'([^']*)'")


class TriggerReadError(Exception):
    """A fail-closed read refusal (STOP family): the workflow asset or the
    filter-law shape cannot be read faithfully, so reporting a filter set
    would be fabrication. Distinct from a data mismatch (no trigger node, a
    drifted allowlist) — that is a RESULT (ok False + af_code), never an
    exception."""


def mask_id(nid: str) -> str:
    """Non-reversible marker for a node id (last 4 chars) — the house
    surface shape for every operator-facing mention of a node id."""
    return reg._mask_location(nid)


# ---------------------------------------------------------------------------
# Extraction primitives — fail-closed: an unreadable shape raises
# TriggerReadError (STOP), never a silent empty.
# ---------------------------------------------------------------------------
def _extract_allowlist(js_code: str) -> list:
    """The action allowlist from the jsCode: the DOC_ACTIONS / TREE_ACTIONS
    array literals, in asset order, deduped (the runtime law is indexOf
    membership — a set). Fail-closed: a literal missing or unparseable is
    STOP (an allowlist that cannot be read is never certified by a guess)."""
    found = []
    for line in js_code.splitlines():
        m = _ALLOWLIST_CONST_RE.match(line.strip())
        if not m:
            continue
        items = _ALLOWLIST_ITEM_RE.findall(m.group(2))
        if not items:
            raise TriggerReadError(
                "the %s allowlist literal in the auth-gate jsCode is empty — "
                "the action filter set cannot be read faithfully"
                % m.group(1))
        for item in items:
            if item not in found:
                found.append(item)
    if not found:
        raise TriggerReadError(
            "the auth-gate jsCode carries no DOC_ACTIONS / TREE_ACTIONS "
            "literals — the action filter set cannot be read faithfully")
    return found


def _require_in(js_code: str, needle: str, what: str) -> None:
    """Fail-closed law pin: the needle must appear byte-exact in the jsCode.
    A missing marker means the auth gate lost a filter-law limb — STOP."""
    if needle not in js_code:
        raise TriggerReadError(
            "the auth-gate jsCode lost %s (%r) — the filter law is "
            "incomplete; refusing to certify the trigger filter set"
            % (what, needle))


def _trigger_nodes(workflow: dict) -> list:
    """The webhook trigger nodes of a workflow (fail-closed shape check: a
    workflow without a nodes array is STOP, never a silent empty)."""
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise TriggerReadError(
            "the workflow asset carries no 'nodes' array — the trigger "
            "filter set cannot be read faithfully")
    return [n for n in nodes
            if isinstance(n, dict)
            and str(n.get("type") or "") == TRIGGER_NODE_TYPE]


def _auth_gate_nodes(workflow: dict) -> list:
    """The auth-gate nodes of a workflow, by the ONE name the broker uses
    (fail-closed shape check: a nodes array is required; non-dict nodes are
    not candidate gates)."""
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise TriggerReadError(
            "the workflow asset carries no 'nodes' array — the auth-gate "
            "filter law cannot be read faithfully")
    return [n for n in nodes
            if isinstance(n, dict)
            and str(n.get("name") or "").strip() == AUTH_GATE_NODE_NAME]


def _gate_param(node: dict, key: str, what: str) -> str:
    """One webhook trigger gate parameter, fail-closed: a parameter that is
    missing, not a string, or empty is STOP — a gate that cannot be read is
    never certified by a guess."""
    params = node.get("parameters")
    if not isinstance(params, dict):
        raise TriggerReadError(
            "the webhook trigger node carries no parameters object — the "
            "trigger filter set cannot be read faithfully")
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TriggerReadError(
            "the webhook trigger node carries no non-empty %s — the trigger "
            "filter set cannot be read faithfully" % what)
    return value.strip()


def _auth_gate_js(node: dict) -> str:
    """The auth-gate jsCode, fail-closed: a gate node without a parameters
    object or without a non-empty jsCode string is STOP — the filter law is
    not readable."""
    params = node.get("parameters")
    if not isinstance(params, dict):
        raise TriggerReadError(
            "the auth-gate node carries no parameters object — the filter "
            "law cannot be read faithfully")
    js = params.get("jsCode")
    if not isinstance(js, str) or not js.strip():
        raise TriggerReadError(
            "the auth-gate node carries no non-empty jsCode — the filter "
            "law cannot be read faithfully")
    return js


def _token_env_label_state() -> str:
    """The broker token env label, BY LABEL ONLY: "SET" or "NOT SET". The
    value is NEVER read into any surface — the state is the whole report."""
    return "SET" if os.environ.get(BROKER_TOKEN_ENV_LABEL) else "NOT SET"


# ---------------------------------------------------------------------------
# The ONE read — read_trigger: extract the trigger filter set, fail-closed.
# ---------------------------------------------------------------------------
def read_trigger(workflow=None, *, workflow_path=None) -> dict:
    """Extract the trigger filter set from the n8n Drive-broker workflow.

    `workflow` is an already-loaded workflow dict (self-tests / callers);
    when None, `workflow_path` (default: the shipped asset) is read from
    disk. Fail-closed:
      - a workflow that is not a JSON object, an unreadable asset, or an
        unreadable shape raises TriggerReadError (STOP family) — never a
        fabricated filter set,
      - a data mismatch is a RESULT (never an exception): no webhook trigger
        node (TRIGGER-MISSING), more than one (TRIGGER-AMBIGUOUS), no
        auth-gate node (AUTH-GATE-MISSING), more than one
        (AUTH-GATE-AMBIGUOUS), or an allowlist that drifted from the engine
        authority (ALLOWLIST-DRIFT) — all ok False, none carry a filter set,
      - the returned surface reports node ids by MASKED MARKER (last 4
        chars) and the token env label by STATE ONLY (SET / NOT SET) — a
        token value is NEVER surfaced, and the jsCode body is NEVER echoed.
    """
    if workflow is None:
        path = Path(workflow_path) if workflow_path else WORKFLOW_PATH
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TriggerReadError(
                "cannot read the workflow asset %s: %s"
                % (path, exc)) from exc
        try:
            workflow = json.loads(raw)
        except ValueError as exc:
            raise TriggerReadError(
                "the workflow asset %s is not valid JSON: %s"
                % (path, exc)) from exc
        source = str(path)
    else:
        source = ("explicit (caller-supplied workflow dict)"
                  if not workflow_path else str(workflow_path))
    if not isinstance(workflow, dict):
        raise TriggerReadError(
            "the workflow asset does not parse to a JSON object — the "
            "trigger filter set cannot be read faithfully")

    # NEVER-A-TOKEN LAW, before anything is certified: the whole asset is
    # scanned against the house credential shape — a hit REFUSES the read
    # (a filter law or any field that carries a token-like literal can never
    # be certified; the value is never printed, the whole surface refuses).
    if _CREDENTIAL_SHAPE.search(json.dumps(workflow)):
        raise TriggerReadError(
            "the workflow asset carries a credential-shaped string — "
            "REFUSED without printing it (never-a-token law)")

    workflow_name = str(workflow.get("name") or "")
    workflow_active = bool(workflow.get("active"))
    triggers = _trigger_nodes(workflow)
    if not triggers:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_name": workflow_name,
            "workflow_active": workflow_active,
            "source": source,
            "filter_set": None,
            "delta": [{"item": "trigger",
                       "status": "FAIL",
                       "detail": "no %s webhook trigger node on the asset — "
                                 "the front door is not a webhook trigger"
                                 % TRIGGER_NODE_TYPE}],
            "af_code": "TRIGGER-MISSING",
            "note": "fail-closed: no trigger, no filter set — never a "
                    "fabricated read",
        }
    if len(triggers) > 1:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_name": workflow_name,
            "workflow_active": workflow_active,
            "source": source,
            "filter_set": None,
            "delta": [{"item": "trigger",
                       "status": "FAIL",
                       "detail": "%d webhook trigger nodes on the asset — a "
                                 "workflow carries exactly ONE trigger (a "
                                 "webhook path can be active on only one "
                                 "workflow)" % len(triggers)}],
            "af_code": "TRIGGER-AMBIGUOUS",
            "note": "fail-closed: an ambiguous trigger is not a filter set",
        }

    trigger = triggers[0]
    trigger_id = str(trigger.get("id") or "")
    http_method = _gate_param(trigger, "httpMethod", "httpMethod")
    path = _gate_param(trigger, "path", "path")
    response_mode = _gate_param(trigger, "responseMode", "responseMode")

    gates = _auth_gate_nodes(workflow)
    if not gates:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_name": workflow_name,
            "workflow_active": workflow_active,
            "source": source,
            "filter_set": None,
            "delta": [{"item": "auth-gate",
                       "status": "FAIL",
                       "detail": "no %r code node on the asset — the "
                                 "authorize filter law is absent"
                                 % AUTH_GATE_NODE_NAME}],
            "af_code": "AUTH-GATE-MISSING",
            "note": "fail-closed: no auth gate, no filter law — never a "
                    "fabricated read",
        }
    if len(gates) > 1:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_name": workflow_name,
            "workflow_active": workflow_active,
            "source": source,
            "filter_set": None,
            "delta": [{"item": "auth-gate",
                       "status": "FAIL",
                       "detail": "%d %r code nodes on the asset — exactly "
                                 "ONE authorize gate"
                                 % (len(gates), AUTH_GATE_NODE_NAME)}],
            "af_code": "AUTH-GATE-AMBIGUOUS",
            "note": "fail-closed: an ambiguous auth gate is not a filter law",
        }

    gate = gates[0]
    gate_id = str(gate.get("id") or "")
    js_code = _auth_gate_js(gate)

    # ---- the filter-law markers, each REQUIRED (fail-closed: a gate that
    #      lost a limb answers without a filter) ----
    _require_in(js_code, "$env." + BROKER_TOKEN_ENV_LABEL,
                "the token env label read")
    _require_in(js_code, BROKER_TOKEN_HEADER_KEYS[0], "the lower-case token header key")
    _require_in(js_code, BROKER_TOKEN_HEADER_KEYS[1], "the canonical token header key")
    _require_in(js_code, BROKER_TOKEN_BODY_FALLBACK, "the body token fallback")
    _require_in(js_code, CAPABILITIES_MARKER, "the capabilities short-circuit")
    _require_in(js_code, PROBE_MARKER, "the side-effect-free probe short-circuit")
    for error_name, code in AUTH_REFUSALS.items():
        _require_in(js_code, error_name, "the %s refusal (%d)" % (error_name, code))
        _require_in(js_code, str(code), "the %s refusal code %d"
                    % (error_name, code))

    allowlist = _extract_allowlist(js_code)
    law = list(da.BROKER_REQUIRED_ACTIONS)
    allowlist_matches = sorted(allowlist) == sorted(law)
    if not allowlist_matches:
        missing = sorted(set(law) - set(allowlist))
        extra = sorted(set(allowlist) - set(law))
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "workflow_name": workflow_name,
            "workflow_active": workflow_active,
            "source": source,
            "filter_set": None,
            "delta": [{"item": "action-allowlist",
                       "status": "FAIL",
                       "detail": "the auth-gate allowlist drifted from the "
                                 "engine authority (missing: %s; extra: %s) — "
                                 "an allowlist that cannot be certified is "
                                 "never certified"
                                 % (", ".join(missing) or "(none)",
                                    ", ".join(extra) or "(none)")}],
            "af_code": "ALLOWLIST-DRIFT",
            "note": "fail-closed: the filter set must equal the engine "
                    "authority (drive_adapter.BROKER_REQUIRED_ACTIONS) — "
                    "never a pass on a drifted allowlist",
        }

    auth_gate = {
        "node": AUTH_GATE_NODE_NAME,
        "node_id_masked": mask_id(gate_id) if gate_id else "",
        "token_env_label": BROKER_TOKEN_ENV_LABEL,
        "token_env_label_state": _token_env_label_state(),
        "header_keys": list(BROKER_TOKEN_HEADER_KEYS),
        "body_token_fallback": True,
        "refusals": dict(AUTH_REFUSALS),
    }
    trigger_record = {
        "node": str(trigger.get("name") or ""),
        "node_id_masked": mask_id(trigger_id) if trigger_id else "",
        "type": TRIGGER_NODE_TYPE,
        "http_method": http_method,
        "path": path,
        "response_mode": response_mode,
    }
    filter_set = {
        "transport": {
            "http_method": http_method,
            "path": path,
            "response_mode": response_mode,
        },
        "auth": auth_gate,
        "actions": {
            "allowlist": sorted(allowlist),
            "allowlist_in_asset_order": list(allowlist),
            "allowlist_matches_law": True,
            "law": "drive_adapter.BROKER_REQUIRED_ACTIONS",
        },
        "short_circuits": {
            "capabilities": True,
            "probe": True,
        },
    }
    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "found": True,
        "workflow_name": workflow_name,
        "workflow_active": workflow_active,
        "source": source,
        "trigger": trigger_record,
        "auth_gate": auth_gate,
        "actions": filter_set["actions"],
        "short_circuits": filter_set["short_circuits"],
        "filter_set": filter_set,
        "delta": [],
        "af_code": "OK",
        "note": "trigger filter set extracted and certified: webhook gate "
                "(%s %s), auth gate by label (state only), action allowlist "
                "byte-exact to the engine authority (%d actions), "
                "capabilities + probe short-circuits present"
                % (http_method, path, len(law)),
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the reader against
# the REAL committed asset (the strongest golden control: a drift in the
# shipped workflow breaks THIS battery first, fail-closed), then runs every
# attack fixture: missing / ambiguous trigger, missing / ambiguous auth
# gate, lost filter-law limbs, drifted allowlist, unreadable shapes, and the
# never-a-token law on every surface.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[trigger-reader] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _minimal_golden_workflow() -> dict:
    """A synthetic minimal golden workflow (the battery's second control, so
    the pass side does not depend on the real asset alone): the webhook
    trigger gate and an auth-gate jsCode carrying the full filter law."""
    js = (
        "const EXPECTED = $env.ANTHOLOGY_DRIVE_BROKER_TOKEN || '';\n"
        "const presented = headers['x-anthology-broker-token'] || "
        "headers['X-Anthology-Broker-Token'] || body.token || '';\n"
        "const DOC_ACTIONS = ['create_doc', 'upload_pdf', "
        "'share_doc_edit', 'pull_doc_text'];\n"
        "const TREE_ACTIONS = ['create_book_tree', "
        "'create_participant_tree'];\n"
        "const IMPLEMENTED = TREE_ACTIONS.concat(DOC_ACTIONS);\n"
        "if (!EXPECTED) return reject(500, 'broker_misconfigured');\n"
        "if (!presented || presented !== EXPECTED) return reject(401, "
        "'unauthorized');\n"
        "const action = (body.action || '').toString();\n"
        "if (!action) return reject(400, 'missing_action');\n"
        "if (action === 'capabilities') { return respond(200, {}); }\n"
        "if (IMPLEMENTED.indexOf(action) === -1) return reject(400, "
        "'unknown_action');\n"
        "if (body.probe === true) { return respond(200, {}); }\n"
    )
    return {
        "name": "Synthetic Broker",
        "active": False,
        "nodes": [
            {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
             "name": TRIGGER_NODE_NAME, "type": TRIGGER_NODE_TYPE,
             "parameters": {"httpMethod": "POST", "path": "anthology-drive",
                            "responseMode": "responseNode"}},
            {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
             "name": AUTH_GATE_NODE_NAME, "type": AUTH_GATE_NODE_TYPE,
             "parameters": {"jsCode": js}},
        ],
    }


def _real_asset() -> dict:
    """The REAL committed asset, fail-closed: an asset that vanished from
    the tree is a broken battery, never a skipped golden control."""
    if not WORKFLOW_PATH.is_file():
        raise AssertionError(
            "the shipped asset %s is missing — the golden control cannot "
            "run (fail-closed)" % WORKFLOW_PATH)
    try:
        data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssertionError(
            "the shipped asset %s cannot be read: %s"
            % (WORKFLOW_PATH, exc)) from exc
    if not isinstance(data, dict):
        raise AssertionError("the shipped asset is not a JSON object")
    return data


def _self_test_body(dev) -> None:
    # ---- 1. the REAL committed asset is the strongest golden control: a
    #      drift in the shipped workflow breaks this battery first ----
    asset = _real_asset()
    assert asset.get("name") == "Anthology Drive Broker", \
        "the shipped asset name drifted: %r" % asset.get("name")
    assert asset.get("active") is False, (
        "the shipped asset must ship INACTIVE (the import checklist "
        "activates after wiring creds/env)")
    res = read_trigger(asset)
    assert res["ok"] is True and res["found"] is True, \
        "the real asset must read clean: %s" % res
    assert res["af_code"] == "OK" and res["contract"] == CONFIG_CONTRACT
    assert res["trigger"]["http_method"] == "POST", \
        "the webhook gate must be POST, got %r" % res["trigger"]["http_method"]
    assert res["trigger"]["path"] == "anthology-drive", \
        "the webhook path must be anthology-drive, got %r" % res["trigger"]["path"]
    assert res["trigger"]["response_mode"] == "responseNode"
    assert res["auth_gate"]["node"] == AUTH_GATE_NODE_NAME
    assert res["auth_gate"]["token_env_label"] == BROKER_TOKEN_ENV_LABEL
    assert res["auth_gate"]["token_env_label_state"] in ("SET", "NOT SET")
    assert res["actions"]["allowlist"] == sorted(da.BROKER_REQUIRED_ACTIONS), \
        "the asset allowlist must byte-equal the engine authority"
    assert res["actions"]["allowlist_matches_law"] is True
    assert res["short_circuits"] == {"capabilities": True, "probe": True}
    assert res["actions"]["law"] == "drive_adapter.BROKER_REQUIRED_ACTIONS"
    # the never-a-token scan over the FULL emitted surface (the asset itself
    # must carry no credential-shaped string; the report must carry none)
    asset_dump = json.dumps(asset)
    assert not _CREDENTIAL_SHAPE.search(asset_dump), \
        "the shipped asset carries a credential-shaped string — REFUSED"
    assert "pit-" not in asset_dump, \
        "the shipped asset must carry no token value (token comes from $env)"
    report_dump = json.dumps(res, indent=2, sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(report_dump), \
        "the read surface must never carry a credential-shaped string"
    assert "pit-" not in report_dump and "Bearer" not in report_dump, \
        "the read surface must never carry a token shape"
    assert "$env." not in report_dump or BROKER_TOKEN_ENV_LABEL in report_dump, \
        "the read surface carries the env LABEL only — never a value"

    # ---- 2. the synthetic golden control: the pass side is not asset-bound
    #      (a builder regression or a tree move must not flip the battery) --
    res = read_trigger(_minimal_golden_workflow())
    assert res["ok"] is True and res["af_code"] == "OK", \
        "the synthetic golden workflow must read clean: %s" % res
    assert res["actions"]["allowlist"] == sorted(da.BROKER_REQUIRED_ACTIONS)

    # ---- 3. the CLI: check on the real asset exits 0 and emits the ONE
    #      contract-carrying JSON object; the surface carries labels/states
    #      only ----
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_check(asset, out=io.StringIO())
    assert rc == EX_OK, "run_check on the golden asset must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["contract"] == CONFIG_CONTRACT
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["actions"]["allowlist"] == sorted(da.BROKER_REQUIRED_ACTIONS)
    assert parsed["auth_gate"]["token_env_label_state"] in ("SET", "NOT SET")
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the check surface must never carry a token shape"
    assert "$env." not in blob and "jsCode" not in blob, (
        "the check surface must never echo the jsCode body (the filter law "
        "is extracted, never echoed)")

    # ---- 4. attack fixtures: every drift REFUSED or MISMATCHED ----
    # 4a. a workflow that is not a dict -> STOP
    try:
        read_trigger(["not", "a", "dict"])
        raise AssertionError("a non-dict workflow was NOT refused")
    except TriggerReadError:
        pass
    # 4b. no nodes array -> STOP
    try:
        read_trigger({"name": "No Nodes"})
        raise AssertionError("a workflow without nodes was NOT refused")
    except TriggerReadError:
        pass
    # 4c. zero webhook triggers -> TRIGGER-MISSING result, no filter set
    res = read_trigger({"name": "No Trigger", "active": False,
                        "nodes": [{"id": "x1", "name": "Plain Node",
                                   "type": "n8n-nodes-base.if"}]})
    assert res["ok"] is False and res["af_code"] == "TRIGGER-MISSING", \
        "a trigger-less workflow must be TRIGGER-MISSING, got %s" % res["af_code"]
    assert res["filter_set"] is None, \
        "a failed read must never carry a filter set"
    # 4d. two webhook triggers -> TRIGGER-AMBIGUOUS
    both = dict(_minimal_golden_workflow())
    both["nodes"].append({"id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                          "name": "Second Webhook", "type": TRIGGER_NODE_TYPE,
                          "parameters": {"httpMethod": "POST", "path": "other",
                                         "responseMode": "responseNode"}})
    res = read_trigger(both)
    assert res["ok"] is False and res["af_code"] == "TRIGGER-AMBIGUOUS", \
        "two webhook triggers must be TRIGGER-AMBIGUOUS"
    # 4e. a trigger without the gate parameters -> STOP
    broke = dict(_minimal_golden_workflow())
    broke["nodes"][0] = {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                         "name": TRIGGER_NODE_NAME, "type": TRIGGER_NODE_TYPE,
                         "parameters": {}}
    try:
        read_trigger(broke)
        raise AssertionError("a trigger without gate parameters was NOT refused")
    except TriggerReadError:
        pass
    # 4f. an empty httpMethod -> STOP
    broke = dict(_minimal_golden_workflow())
    broke["nodes"][0]["parameters"] = {"httpMethod": "", "path": "anthology-drive",
                                       "responseMode": "responseNode"}
    try:
        read_trigger(broke)
        raise AssertionError("an empty httpMethod was NOT refused")
    except TriggerReadError:
        pass
    # 4g. no auth-gate node -> AUTH-GATE-MISSING
    no_gate = dict(_minimal_golden_workflow())
    no_gate["nodes"] = [no_gate["nodes"][0]]
    res = read_trigger(no_gate)
    assert res["ok"] is False and res["af_code"] == "AUTH-GATE-MISSING", \
        "a workflow without the auth gate must be AUTH-GATE-MISSING"
    # 4h. two auth-gate nodes -> AUTH-GATE-AMBIGUOUS
    two_gates = dict(_minimal_golden_workflow())
    two_gates["nodes"].append({"id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                               "name": AUTH_GATE_NODE_NAME,
                               "type": AUTH_GATE_NODE_TYPE,
                               "parameters": {"jsCode": "// clone"}})
    res = read_trigger(two_gates)
    assert res["ok"] is False and res["af_code"] == "AUTH-GATE-AMBIGUOUS", \
        "two auth gates must be AUTH-GATE-AMBIGUOUS"
    # 4i. an auth gate without jsCode -> STOP
    no_js = dict(_minimal_golden_workflow())
    no_js["nodes"][1] = {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                         "name": AUTH_GATE_NODE_NAME, "type": AUTH_GATE_NODE_TYPE,
                         "parameters": {}}
    try:
        read_trigger(no_js)
        raise AssertionError("an auth gate without jsCode was NOT refused")
    except TriggerReadError:
        pass
    # 4j. a jsCode that lost the token env label -> STOP
    lost_label = _minimal_golden_workflow()
    lost_label["nodes"][1]["parameters"]["jsCode"] = (
        lost_label["nodes"][1]["parameters"]["jsCode"].replace(
            "$env.ANTHOLOGY_DRIVE_BROKER_TOKEN", "$env.SOME_OTHER_LABEL"))
    try:
        read_trigger(lost_label)
        raise AssertionError("a jsCode without the token env label was NOT refused")
    except TriggerReadError:
        pass
    # 4k. a jsCode that lost the 401 unauthorized refusal -> STOP
    lost_401 = _minimal_golden_workflow()
    lost_401["nodes"][1]["parameters"]["jsCode"] = (
        lost_401["nodes"][1]["parameters"]["jsCode"].replace(
            "'unauthorized'", "'forbidden'"))
    try:
        read_trigger(lost_401)
        raise AssertionError("a jsCode without the 401 refusal was NOT refused")
    except TriggerReadError:
        pass
    # 4l. an allowlist that drifted (an action renamed) -> ALLOWLIST-DRIFT,
    #      never a pass, and never an exception (a data mismatch is a result)
    drifted = _minimal_golden_workflow()
    drifted["nodes"][1]["parameters"]["jsCode"] = (
        drifted["nodes"][1]["parameters"]["jsCode"].replace(
            "'pull_doc_text'", "'pull_doc_body'"))
    res = read_trigger(drifted)
    assert res["ok"] is False and res["af_code"] == "ALLOWLIST-DRIFT", \
        "a drifted allowlist must be ALLOWLIST-DRIFT, got %s" % res["af_code"]
    assert res["filter_set"] is None, \
        "a drifted allowlist must never carry a filter set"
    # 4m. an allowlist with an EXTRA action -> ALLOWLIST-DRIFT
    extra = _minimal_golden_workflow()
    extra["nodes"][1]["parameters"]["jsCode"] = (
        extra["nodes"][1]["parameters"]["jsCode"].replace(
            "const TREE_ACTIONS = ['create_book_tree', ",
            "const TREE_ACTIONS = ['create_book_tree', 'delete_everything', "))
    res = read_trigger(extra)
    assert res["ok"] is False and res["af_code"] == "ALLOWLIST-DRIFT", \
        "an extra action must be ALLOWLIST-DRIFT"
    # 4n. an allowlist whose literals vanished -> STOP (never a guess);
    #      BOTH const literals must go — a surviving literal is a read
    #      allowlist, not the attack shape
    no_literals = _minimal_golden_workflow()
    no_literals["nodes"][1]["parameters"]["jsCode"] = (
        no_literals["nodes"][1]["parameters"]["jsCode"]
        .replace("const DOC_ACTIONS = ['create_doc', 'upload_pdf', "
                 "'share_doc_edit', 'pull_doc_text'];", "// allowlist gone")
        .replace("const TREE_ACTIONS = ['create_book_tree', "
                 "'create_participant_tree'];", "// allowlist gone"))
    try:
        read_trigger(no_literals)
        raise AssertionError("a jsCode without the allowlist literals was NOT "
                             "refused")
    except TriggerReadError:
        pass
    # 4o. a jsCode carrying a credential-shaped string -> STOP (never printed)
    poisoned = _minimal_golden_workflow()
    poisoned["nodes"][1]["parameters"]["jsCode"] += (
        "\nconst LEAK = 'pit-abc123def456';\n")
    try:
        read_trigger(poisoned)
        raise AssertionError("a credential-shaped string must REFUSE the read")
    except TriggerReadError:
        pass
    # 4p. a missing asset file -> STOP (never a fabricated read)
    try:
        read_trigger(workflow_path="/nonexistent/nope.json")
        raise AssertionError("a missing asset was NOT refused")
    except TriggerReadError:
        pass
    # 4q. an unparseable asset file -> STOP
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write("{ not json")
        tmp_name = tmp.name
    try:
        read_trigger(workflow_path=tmp_name)
        raise AssertionError("an unparseable asset was NOT refused")
    except TriggerReadError:
        pass
    finally:
        try:
            Path(tmp_name).unlink()
        except OSError:
            pass

    # ---- 5. run_check on a drifted allowlist exits 5 (mismatch family) ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_check(drifted, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "run_check on a drifted allowlist must exit 5, got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "FAIL"

    # ---- 6. the BROWSER UA law is pinned (CF 1010) — this module makes no
    #      network call, but the sibling live surface rides the constant ----
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- 7. plan: offline, no network, exact sources ----
    plan_buf = io.StringIO()
    rc = plan(out=plan_buf)
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(plan_buf.getvalue())
    assert p["contract"] == CONFIG_CONTRACT + "-plan"
    assert p["allowlist"] == sorted(da.BROKER_REQUIRED_ACTIONS)
    assert p["dry_run"] is True

    dev.write("[trigger-reader] self-test PASS: real committed asset "
              "certified (webhook gate POST anthology-drive responseNode, "
              "auth-gate filter law by label, allowlist byte-exact to "
              "drive_adapter.BROKER_REQUIRED_ACTIONS (%d actions), "
              "capabilities + probe short-circuits, ships INACTIVE); "
              "synthetic golden control; run_check exits 0 on golden and 5 "
              "on a drifted allowlist; 17 attack fixtures refused "
              "(non-dict / no-nodes / TRIGGER-MISSING / TRIGGER-AMBIGUOUS / "
              "gate-parameters-absent / empty-httpMethod / AUTH-GATE-MISSING "
              "/ AUTH-GATE-AMBIGUOUS / no-jsCode / lost-token-env-label / "
              "lost-401-refusal / ALLOWLIST-DRIFT-renamed / "
              "ALLOWLIST-DRIFT-extra / lost-literals / credential-shaped "
              "string / missing-asset / unparseable-asset); never a token "
              "value, never a jsCode echo, env label state only; "
              "CAF_BROWSER_UA pinned; plan offline\n" % len(da.BROKER_REQUIRED_ACTIONS))


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The read surface with its exact
# sources, printed as ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def plan(*, out=None) -> int:
    """Emit the ONE offline plan JSON object (no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    out = out or sys.stdout
    payload = {
        "contract": CONFIG_CONTRACT + "-plan",
        "schema_version": 1,
        "source": str(WORKFLOW_PATH),
        "webhook_gate": {"type": TRIGGER_NODE_TYPE, "name": TRIGGER_NODE_NAME,
                         "parameters": "httpMethod / path / responseMode "
                                       "(the transport gate)"},
        "auth_gate": {"name": AUTH_GATE_NODE_NAME,
                      "token_env_label": BROKER_TOKEN_ENV_LABEL,
                      "token_env_label_state": _token_env_label_state(),
                      "header_keys": list(BROKER_TOKEN_HEADER_KEYS),
                      "refusals": dict(AUTH_REFUSALS)},
        "allowlist": sorted(da.BROKER_REQUIRED_ACTIONS),
        "allowlist_law": "drive_adapter.BROKER_REQUIRED_ACTIONS (byte-exact, "
                         "as a set) — a drifted allowlist is ALLOWLIST-DRIFT, "
                         "exit 5, never certified",
        "short_circuits": {"capabilities": CAPABILITIES_MARKER,
                           "probe": PROBE_MARKER},
        "dry_run": True,
        "note": "offline read of the shipped n8n Drive-broker asset only — "
                "no network, no credential needed; the token env label is "
                "reported by STATE (SET / NOT SET), never by value; the "
                "jsCode body is extracted, never echoed",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise TriggerReadError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out.write(dumped)
    out.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# The check runner — the ONE machine surface the CLI (and self-test) ride on.
# ---------------------------------------------------------------------------
def run_check(workflow=None, *, workflow_path=None, out=None) -> int:
    """Run the trigger filter-set read and emit the ONE JSON report object
    on stdout. Returns the exit code: 0 PASS (certified), 5 MISMATCH (a
    named af_code result: TRIGGER-MISSING / TRIGGER-AMBIGUOUS /
    AUTH-GATE-MISSING / AUTH-GATE-AMBIGUOUS / ALLOWLIST-DRIFT), 2 STOP (the
    asset or the filter-law shape cannot be read faithfully). Human notes go
    to out (stderr)."""
    out = out or sys.stderr
    try:
        res = read_trigger(workflow, workflow_path=workflow_path)
    except TriggerReadError as exc:
        reg._stop(out, "The trigger filter set cannot be read faithfully.",
                  [str(exc), "The read is OFFLINE — the shipped asset "
                             "config/n8n/anthology-drive-broker.workflow.json "
                             "is the source; a shape that cannot be read is "
                             "never certified by a guess."])
        print(json.dumps({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "verdict": "STOP",
            "found": False,
            "filter_set": None,
            "af_code": "TRIGGER-UNREADABLE",
            "detail": str(exc),
            "fail_closed": True,
        }, indent=2, sort_keys=True))
        return EX_STOP
    ok = bool(res.get("ok"))
    print(json.dumps({
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "found": bool(res.get("found")),
        "workflow_name": res.get("workflow_name", ""),
        "workflow_active": bool(res.get("workflow_active")),
        "source": res.get("source", ""),
        "trigger": res.get("trigger"),
        "auth_gate": res.get("auth_gate"),
        "actions": res.get("actions"),
        "short_circuits": res.get("short_circuits"),
        "filter_set": res.get("filter_set"),
        "delta": res.get("delta", []),
        "af_code": res.get("af_code", ""),
        "fail_closed": True,
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[trigger-reader] check OK: %s\n" % res.get("note", ""))
        return EX_OK
    out.write("[trigger-reader] check FAIL: %s\n" % res.get("note", ""))
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: check / plan / self-test positional subcommands (with
# the --self-test / --selftest flag normalization of the U02..U05 families).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="trigger_reader.py",
        description="Offline-read the trigger filter set of the n8n "
                    "Drive-broker workflow asset (Skill 59, U05 tooling): "
                    "the webhook trigger gate, the Authorize & Dispatch "
                    "filter law (token gate by label, action allowlist "
                    "pinned byte-exact to drive_adapter.BROKER_REQUIRED_"
                    "ACTIONS, probe / capabilities short-circuits). "
                    "Fail-closed; never prints a token; the env label is "
                    "reported by state only. One JSON object on stdout.")
    ap.add_argument("--workflow", default="",
                    help="path to the workflow JSON asset (default: "
                         "config/n8n/anthology-drive-broker.workflow.json)")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"],
                    default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U02..U05 families use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan()

        # ---- check ----
        return run_check(workflow_path=args.workflow.strip() or None,
                         out=sys.stderr)

    except TriggerReadError as exc:
        sys.stderr.write("[trigger-reader] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[trigger-reader] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
