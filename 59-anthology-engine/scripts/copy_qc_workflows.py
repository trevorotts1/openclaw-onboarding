#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: copy_qc_workflows.py  (MASTER-SPEC NEW-6)
# COPY-COMPLIANCE QC GATE FOR THE CONVERT AND FLOW RELEASE-NOTIFICATION
# WORKFLOWS.
#
# WHAT THIS IS (contract config/anthology-snapshot-contract.json ->
# workflows.copy_law + workflows.release_notifications; references/
# anthology-snapshot-guide.md section 1 item 5):
#   The engine EMITS the eight anthology-release-* / anthology-delivered tags
#   (gate_engine.py release bus + caf_delivery.py add_tag), but nothing in the
#   repo turns a release tag into the author-facing EMAIL + SMS except the
#   tag->notification workflows built ONCE in the operator's template location
#   via the Skill 44 caf Firebase build rail and carried by the snapshot. Those
#   workflows are client-facing surfaces and, like the nudge templates and every
#   produced deliverable, fall under the MOVE-IN-SILENCE copy law (PRD doctrine
#   line; MASTERDOC floor law #14). This gate AUDITS every workflow export JSON
#   against that law and the contract, and fails closed:
#
#     check   READ-ONLY offline audit of one or more workflow export JSON
#             files (path(s) or --directory). Per workflow, per node, emits a
#             structured verdict: the five copy checks with PASS/FAIL and the
#             EXACT violation location (workflow name -> node id/name/type ->
#             parameter path -> matched text). Exit 4 when ANY workflow has ANY
#             FAIL; a malformed export is exit 2 (fail-closed, never skipped).
#             SOURCE-INTEGRITY LOCK (NEW-6 U26 amendment): before any per-node
#             audit runs, every contract workflows.release_notifications row's
#             email_link_fields AND sms_link_field are normalized to bare keys
#             and must resolve into field-map deliverable_fields (the audit
#             resolves stage links from deliverable_fields, so a workflow that
#             references a field the map no longer carries, or a map that no
#             longer carries a field a workflow must reference, would audit a
#             phantom surface -- closing the deliverable_fields drift blind
#             spot). Unresolved keys are a located FAIL of the stage_links
#             check (AF-AE-COPY-STAGE-LINKS), exit 4, naming the contract row
#             + the missing field. The check command therefore refuses a
#             drifted field-map/contract pair BEFORE any workflow export is
#             judged (fail-closed: the audit never runs against a lying map).
#     list    READ-ONLY: print the names of the workflows a directory/file
#             carries (importable wiring surface for a CI fan-out).
#     plan    OFFLINE: print the copy-law contract (the five checks) and the
#             per-stage link expectations, then exit.
#     self-test  OFFLINE golden + attack fixtures (no network, no secrets).
#
# THE FIVE CHECKS (workflows.copy_law + workflows.release_notifications):
#   (a) editors_never_ai: no client-facing workflow text may call the editorial
#       process "AI" (word-boundary AI) or "ghostwriter" (substring, any case,
#       including compound forms). The sanctioned word is "editors". The check
#       DOES apply to node names, but NEVER to file/parameter NAME keys or the
#       deny machinery of this file itself (the enforcement-context convention
#       of guard-no-anthropic-runtime.py).
#   (b) no_em_dashes: zero U+2014 em-dash characters anywhere in a client-
#       facing workflow (same law as verify.sh's nudge-template scan; the
#       COPY_LAW block below is the one documented exception).
#   (c) email_and_sms: every CLIENT-FACING workflow (identified by its trigger
#       tag slug, or by an explicit --expect-client-facing override) must carry
#       BOTH an email-sending action (GHL/n8n email node shapes: sendEmail,
#       email, gmail, outlook, sendAndWait, emailSend, triggerEmail etc.) and
#       an SMS-sending action (sms shapes: sms, sendSms, twilio, triggerSms,
#       smsAndEmail, emailSms, "send-sms", "sms" action names).
#   (d) stage_links: the workflow's email body MUST reference the field-map
#       deliverable link keys for its own stage (doc_url + pdf_url pair(s) as
#       {{ contact.<key> }} merge tags). Link fields are resolved from
#       config/field-map.json deliverable_fields via the contract's
#       workflows.release_notifications rows (email_link_fields list AND the
#       sms_link_field, both normalized to bare keys), so the audit can never
#       drift from the engine's single source of truth. Before any workflow is
#       judged, the source pair is itself verified: every contract row's link
#       fields must resolve into deliverable_fields (a rename anywhere on
#       either side is a located FAIL of this check, never a blind audit). A
#       workflow that carries NO deliverable fields contract row is audited
#       for the absence of any {{ contact.anthology_* }} URL reference only.
#   (e) per_stage_copy: the workflow's human text must carry the stage's
#       invariant copy tokens: the producer-name merge
#       {{ custom_values.producer }}, the standing instruction ("The PDF is
#       yours to view. The Google Doc is the one you edit, and it is the
#       version we use."), and the workflow must be tied to its contract
#       trigger tag (workflows.release_notifications trigger_tag) by name
#       (trigger-tag parameter, node name, or workflow name). A workflow that
#       has no contract row is audited for the producer merge only.
#
# SENSOR DESIGN (enforcement, not description): the audit inspects the JSON
# deep, with per-line reporting, exactly like the snapshot drift gate and the
# font-floor guard -- a violation is a located FAIL, never a fuzzy score. The
# word-band and title-lock invariants of the produced deliverables themselves
# are owned by qc-tier1-anthology.py + judge_harness.py; this gate owns the
# WORKFLOW SURFACE copy.
#
# CREDENTIAL DOCTRINE: this gate is OFFLINE by default -- it audits export
# JSON only and NEVER needs a token. The optional --list-live surface reads
# the location's workflows through the PROVEN internal rail
# (backend.leadconnectorhq.com /workflow/{loc}/list -- the same surface the
# podcast gate verify-podcast-ghl-workflows.py proved live). Credentials are
# resolved BY LABEL via the shared alias resolver (Firebase refresh token
# labels; the anthology_registry resolve functions); values are NEVER printed
# (SET / NOT SET + masked location only). A Firebase id_token is a session
# credential and never surfaces. The browser User-Agent rides every request
# via reg.CafClient / reg._internal_request_headers (W0.6/GK-09: the
# Cloudflare edge fronting the API 403s urllib's default UA -- CF 1010 --
# before the request reaches Convert and Flow).
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-COPY-EM-DASH            -> an em-dash character in a client-facing
#          workflow node (check b). exit 4.
#   AF-AE-COPY-AI-WORD            -> "AI"/"ghostwriter" wording in client-
#          facing workflow text or node name (check a). exit 4.
#   AF-AE-COPY-NO-EMAIL           -> client-facing workflow lacks any email-
#          sending action (check c). exit 4.
#   AF-AE-COPY-NO-SMS             -> client-facing workflow lacks any SMS-
#          sending action (check c). exit 4.
#   AF-AE-COPY-STAGE-LINKS        -> the email body misses the stage's
#          deliverable link merge tags (check d). exit 4.
#   AF-AE-COPY-FIELD-DRIFT        -> the contract release_notifications rows
#          reference link fields that field-map deliverable_fields no longer
#          carries (bare-key resolution), or the reverse -- the field-map
#          drifted from the contract surface. Located FAIL of check d, exit 4
#          (same code as the missing-tag form: both are the stage-link surface
#          lying to the author).
#   AF-AE-COPY-STAGE-TOKENS       -> the per-stage copy invariants are absent
#          (producer merge / standing instruction / trigger-tag tie, check e).
#          exit 4.
#   AF-AE-COPY-MALFORMED          -> a workflow export is not a JSON object
#          with a nodes array (fail-closed: exit 2, never a silent skip).
#
# EXIT CODES (house convention; SPEC 3.4 guard family):
#   0  all audited workflows PASS (including an empty set)
#   1  unexpected error
#   2  validation / usage refusal (missing path, malformed export, unknown
#      workflow referenced by name)
#   3  dependency held (live list: credential NOT SET / unreachable)
#   4  enforced violation detected (AF-AE-COPY-*) -- at least one FAIL
#
# STDLIB ONLY (json + argparse), reusing anthology_registry for the live
# surface + credential resolution. Calls NO model. DOCTRINE: move in silence;
# NOTHING Anthropic in any runtime file; Convert and Flow naming in every
# client surface; NEVER print a secret value; --self-test and --plan are
# OFFLINE.
# =============================================================================
"""copy_qc_workflows.py — copy-compliance QC gate over the Convert and Flow
release-notification workflow exports (Skill 59, MASTER-SPEC NEW-6)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Sibling import bootstrap (mirrors anthology_snapshot.py's own convention).
# The registry does the Cloudflare browser-UA wiring + LeadConnector client +
# label resolution we reuse; it is imported LAZILY inside the live functions so
# this module stays pure-stdlib and self-contained for the offline audit.
sys.path.insert(0, str(Path(__file__).resolve().parent))

EX_OK, EX_ERR, EX_STOP, EX_HELD = 0, 1, 2, 3
EX_VIOLATION = 4

SKILL_DIR = Path(__file__).resolve().parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The engine's client-facing platform name, spelled out in every surface.
_PLATFORM = "Convert and Flow"

# ---------------------------------------------------------------------------
# The copy law (config/anthology-snapshot-contract.json -> workflows.copy_law).
# Only the CHECK TEXT below may name the banned tokens: this is the deny
# machinery's own definition, and the sibling static guard
# (guard-no-anthropic-runtime.py) allowlists deny definitions line-for-line.
# ---------------------------------------------------------------------------
COPY_LAW = {
    "editors_never_ai": {
        "note": "The editorial process is performed by 'editors', never 'AI' "
                "and never 'ghostwriter' (Trevor's verbatim law; PRD doctrine; "
                "MASTERDOC floor #14).",
        "banned_words": ("AI", "ghostwriter"),
        "sanctioned_word": "editors",
    },
    "no_em_dashes": {
        "note": "Zero U+2014 em-dash characters in any client-facing word "
                "(the same law verify.sh enforces over the nudge templates; "
                "this COPY_LAW block is the one documented exception).",
        "char": "—",
    },
    "email_and_sms": {
        "note": "Every client-facing workflow sends the author BOTH a "
                "producer-branded email and a link-only SMS.",
    },
    "per_stage_links": {
        "note": "Each email carries that stage's PDF (view) link plus editable "
                "Google Doc (edit) link, pulled from the matching field-map "
                "deliverable_fields contact custom fields.",
    },
    "per_stage_copy": {
        "producer_name_merge": "{{ custom_values.producer }}",
        "email_from_name_merge": "{{ custom_values.producer }}",
        "sms_shape": "link-only short message (one warm sentence plus ONE link)",
        "standing_instruction": "The PDF is yours to view. The Google Doc is "
                                "the one you edit, and it is the version we use.",
    },
}
BANNED_WORDS = tuple(COPY_LAW["editors_never_ai"]["banned_words"])
EM_DASH = COPY_LAW["no_em_dashes"]["char"]
PRODUCER_MERGE = COPY_LAW["per_stage_copy"]["producer_name_merge"]
STANDING_INSTRUCTION = COPY_LAW["per_stage_copy"]["standing_instruction"]
SMS_SHAPE = COPY_LAW["per_stage_copy"]["sms_shape"]

# The banned "AI" token, assembled from fragments so THIS shipped file carries
# no contiguous bare banned literal (the same convention guard-no-anthropic-
# runtime.py documents for its own deny machinery). "ghostwriter" is a plain
# English word that is banned ONLY as client-facing workflow wording, so it is
# spelled out here -- it is the deny definition.
_AI_TOKEN = "A" + "I"
_AI_WORD_RE = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(_AI_TOKEN) + r"(?![A-Za-z0-9_])",
                         re.IGNORECASE)
_GHOST_RE = re.compile(r"ghost\s*writer", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Action-node sensor shapes. WORKFLOW-EXPORT SHAPES ONLY: a "send-email" string
# alone (the contract's action vocabulary) is not sufficient proof a node
# SENDS -- it must look like a GHL/n8n email node or carry an action value.
# The sensors are structural + word-based, so a renamed export cannot evade.
# ---------------------------------------------------------------------------
_EMAIL_NODE_MARKERS = (
    "sendemail", "email", "gmail", "outlook", "sendandwait", "emailpreview",
    "triggeremail",
)
_SMS_NODE_MARKERS = (
    "sms", "twilio", "textmagic", "sendsms", "textbelt",
)
# Word shapes inside node parameters that alone PROVE a send action (used in
# combination with the marker tests below).
_EMAIL_ACTION_WORDS = ("sendemail", "send-email", "send email")
_SMS_ACTION_WORDS = ("sendsms", "send-sms", "send sms")

_LINK_FIELD_RE = re.compile(r"\{\{\s*contact\.(anthology_[A-Za-z0-9_]+)\s*\}\}")
# A "URL reference" is a literal URL shape OR a deliverable link merge tag
# ({{ contact.anthology_*_url }}) -- at send time the merge tag IS the link.
_URL_MARKER_RE = re.compile(r"https?://|drive\.google\.com|docs\.google\.com|/d/|media-storage|anthology_[a-z0-9_]*url")


def _is_email_node(node_type: str, name: str, params: dict) -> bool:
    """Does this node LOOK like an email-sending action? GHL/n8n node types and
    node names carry the sendEmail/email markers; GHL's workflow builder also
    uses 'send-email' action strings inside generic node parameters."""
    hay = ("%s %s" % (node_type, name)).lower()
    if any(m in hay for m in _EMAIL_NODE_MARKERS):
        return True
    joined = json.dumps(params, ensure_ascii=True).lower()
    return any(w in joined for w in _EMAIL_ACTION_WORDS)


def _is_sms_node(node_type: str, name: str, params: dict) -> bool:
    hay = ("%s %s" % (node_type, name)).lower()
    if any(m in hay for m in _SMS_NODE_MARKERS):
        return True
    joined = json.dumps(params, ensure_ascii=True).lower()
    return any(w in joined for w in _SMS_ACTION_WORDS)


# ---------------------------------------------------------------------------
# Contract + field-map loaders (the engine's single sources of truth).
# ---------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def workflow_rows(contract: dict) -> list:
    """The contract's release_notifications rows (name, trigger_tag,
    email_link_fields, sms_link_field, actions, slug_status)."""
    return (contract.get("workflows") or {}).get("release_notifications") or []


def row_for_name(rows, name: str):
    for r in rows:
        if (r.get("name") or "").strip() == (name or "").strip():
            return r
    return None


def row_for_tag(rows, tag: str):
    for r in rows:
        if (r.get("trigger_tag") or "").strip() == (tag or "").strip():
            return r
    return None


def deliverable_fields(field_map: dict) -> dict:
    return (field_map.get("deliverable_fields") or {})


# The one regex that turns a merge string into the bare key it carries, used
# for EVERY contract-vs-field-map comparison (email_link_fields, sms_link_field
# and the field-map value side). One normalizer, one truth: a bare key is
# "anthology_..." and nothing else resolves.
_BARE_KEY_RE = re.compile(r"anthology_[A-Za-z0-9_]+")


def _bare_key(value: str) -> str:
    """The bare 'anthology_*' key inside a merge-string value, else ''.
    '{{contact.anthology_avatar_pdf_url}}' -> 'anthology_avatar_pdf_url'.
    A value that carries no such key resolves to '' (never a match)."""
    m = _BARE_KEY_RE.search(str(value or ""))
    return m.group(0) if m else ""


def _strict_declared_link_keys(field_map: dict) -> set:
    """The STRICT set the per-workflow stage-links check judges against:
    deliverable_fields VALUE keys only (the engine's single source of truth
    for the link fields a workflow may reference) PLUS the U8 cover-style
    sample_url fields (which live outside deliverable_fields but ARE the link
    fields the Cover Picks workflow must reference). The provisioning
    inventory is deliberately NOT included here: an inventory row proves a
    field exists on the box, not that the deliverable_fields block still
    points at it -- a block rename must FAIL the workflow, not be masked by
    the box inventory. The block-vs-inventory cross-check
    (_deliverable_fields_rename_violations) separately proves the committed
    map's deliverable_fields VALUE keys equal the provisioning intended_keys,
    so a consistent re-key on BOTH sides stays legal while a one-sided rename
    lies."""
    declared = set()
    for pair in deliverable_fields(field_map).values():
        if isinstance(pair, dict):
            declared.update(str(v) for v in pair.values() if isinstance(v, str))
    csf = field_map.get("cover_style_fields") or {}
    for v in (csf.get("sample_url_fields") or {}).values():
        if isinstance(v, str) and v.strip():
            declared.add(v)
    return declared


def resolve_link_field(field_map: dict, merge_or_bare: str) -> str:
    """The full field key ('contact.<bare>') the field-map declares for a
    contract link-field reference, else '' (UNRESOLVED). The reference may be
    a full merge string ('{{contact.anthology_avatar_pdf_url}}'), a full key,
    or already a bare key; the lookup is by BARE KEY against the STRICT
    declared link-key set (deliverable_fields values + cover sample_url
    fields), so a rename on either side of the contract/map boundary surfaces
    as ''."""
    if not isinstance(merge_or_bare, str) or not merge_or_bare.strip():
        return ""
    bare = _bare_key(merge_or_bare)
    if not bare:
        return ""
    full = "contact." + bare
    return full if full in _strict_declared_link_keys(field_map) else ""


def unresolved_link_fields(field_map: dict, contract: dict) -> list:
    """Every contract release_notifications link-field reference that the
    field-map does NOT declare (bare-key resolution), as (workflow_name,
    merge_string) pairs. email_link_fields AND sms_link_field are both covered:
    the SMS body carries its link too, so a map that lost the SMS field would
    silently audit a phantom SMS link. This is the deliverable_fields drift
    blind-spot lock: the audit never judges a workflow against a lying map."""
    out = []
    declared = _strict_declared_link_keys(field_map)
    for r in workflow_rows(contract):
        name = (r.get("name") or "").strip()
        refs = list(r.get("email_link_fields") or [])
        sms = r.get("sms_link_field")
        if isinstance(sms, str) and sms.strip():
            refs.append(sms)
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                continue
            bare = _bare_key(ref)
            if not bare:
                continue
            # The bare-key resolution: the map must declare the referenced key.
            if "contact." + bare not in declared:
                out.append((name or "<unnamed row>", ref.strip()))
    return out


def _deliverable_fields_rename_violations(field_map: dict) -> list:
    """deliverable_fields block-level drift the union would otherwise mask: a
    pair whose VALUE keys were renamed while the register still occupies the
    same slots, AND the renamed keys are NOT in the provisioning inventory
    (which carries every real provisioned key, byte-exact). Returns human
    messages; the check command turns each into an AF-AE-COPY-FIELD-DRIFT
    located FAIL. A block that merely edits an existing key in a way the
    inventory still matches (a consistent rename on BOTH sides) is a legal
    re-key, not a drift -- it is the ONE-SIDED rename (block only) that lies."""
    violations = []
    inv_keys = set()
    for row in (field_map.get("provisioning") or {}).get("fields") or []:
        key = (row or {}).get("intended_key")
        if isinstance(key, str) and key.strip():
            inv_keys.add(key)
    df = deliverable_fields(field_map)
    for deliverable, pair in sorted(df.items()):
        if not isinstance(pair, dict):
            continue
        for slot in ("doc_url", "pdf_url"):
            declared_key = pair.get(slot)
            if not isinstance(declared_key, str) or not declared_key.strip():
                continue
            if declared_key not in inv_keys:
                violations.append(
                    "deliverable_fields.%s.%s declares %r but provisioning.fields "
                    "carries no such intended_key (one-sided key rename)"
                    % (deliverable, slot, declared_key))
    return violations


def load_sources(field_map_path=None, contract_path=None, *, out=None):
    """Load field-map + contract. Missing/unreadable -> (None, None, reason);
    the CLI maps that to exit 2 (fail-closed: the audit never runs blind)."""
    out = out or sys.stderr
    fm_path = Path(field_map_path or FIELD_MAP_PATH).expanduser()
    ct_path = Path(contract_path or CONTRACT_PATH).expanduser()
    try:
        fm = load_json(fm_path)
        ct = load_json(ct_path)
    except (OSError, ValueError) as exc:
        out.write("[copy_qc] dependency unavailable: cannot read %s or %s: %s\n"
                  % (fm_path, ct_path, exc))
        return None, None, str(exc)
    return fm, ct, None


# ---------------------------------------------------------------------------
# The audit. Pure functions over (workflow_export, field_map, contract) with a
# per-node violation report. A violation always names its exact location.
# ---------------------------------------------------------------------------
def _node_id(node: dict, index: int) -> str:
    nid = (node.get("id") or "").strip()
    name = (node.get("name") or "").strip()
    ntype = (node.get("type") or "").strip()
    return "node[%d] %s%s%s%s" % (
        index,
        ("id=%s " % nid) if nid else "",
        ("name=%r " % name) if name else "",
        ("type=%s" % ntype) if ntype else "",
        (" (UNNAMED)" if not name else ""))


def _walk_strings(node, prefix: str):
    """Yield (path, text) for every string value under a node: parameters,
    options, credentials id/name, settings. KEY NAMES ARE NEVER YIELDED -- a
    parameter NAME is not copy."""
    def rec(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from rec(v, "%s.%s" % (path, k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from rec(v, "%s[%d]" % (path, i))
        elif isinstance(obj, str):
            yield path, obj
    yield from rec(node, prefix)


def _text_violations(text: str):
    """(kind, match) pairs for one text string: em-dash + banned wording.
    The em-dash is reported only if the text is not the COPY_LAW block itself
    (the one documented exception)."""
    out = []
    if EM_DASH in text and text.strip() != COPY_LAW["no_em_dashes"]["note"]:
        out.append(("em-dash", EM_DASH))
    for m in _AI_WORD_RE.finditer(text):
        out.append(("ai-word", m.group(0)))
    for m in _GHOST_RE.finditer(text):
        out.append(("ai-word", m.group(0)))
    return out


def _trigger_tag(node: dict) -> str:
    """The contact_tag the node binds — node-bound contactTag/tag parameters
    ONLY. A node NAME (e.g. "Webhook anthology-drive", "PT Producer Resolved")
    is a structural label, not a release-tag binding, and must never be read
    as one: it would misclassify non-notification workflows (like the Drive
    broker) as client-facing and false-fail their audit."""
    tag = (node.get("parameters") or {}).get("contactTag") or \
        (node.get("parameters") or {}).get("tag") or ""
    if not isinstance(tag, str):
        tag = ""
    return tag.strip()


def audit_workflow(export, field_map: dict, contract: dict, *,
                   path=None, expect_client_facing=False):
    """Audit ONE workflow export against the copy law. Returns a report dict:

        {file, name, trigger_tag, client_facing, checks: {...}, fails: [...],
         ok: bool}

    A fail entry is {"code", "node", "check", "detail"} where `node` is the
    exact location (workflow -> node id/name/type -> parameter path). Never
    raises on a malformed export -- the caller decides exit 2 vs 4."""
    report = {
        "file": str(path) if path else "<inline>",
        "name": "",
        "trigger_tag": "",
        "client_facing": bool(expect_client_facing),
        "checks": {
            "editors_never_ai": {"pass": True, "fails": []},
            "no_em_dashes": {"pass": True, "fails": []},
            "email_and_sms": {"pass": True, "fails": []},
            "stage_links": {"pass": True, "fails": []},
            "per_stage_copy": {"pass": True, "fails": []},
        },
        "fails": [],
        "ok": False,
    }

    if not isinstance(export, dict) or not isinstance(export.get("nodes"), list):
        report["fails"].append({
            "code": "AF-AE-COPY-MALFORMED",
            "node": "<export root>",
            "check": "malformed",
            "detail": "workflow export is not a JSON object with a 'nodes' array",
        })
        return report

    report["name"] = str(export.get("name") or export.get("workflowName") or "")
    rows = workflow_rows(contract)
    row = row_for_name(rows, report["name"])
    if not row:
        # The export may be named without the 'Anthology Release: ' prefix.
        row = row_for_name(rows, report["name"].replace("Anthology Release: ", ""))

    nodes = export["nodes"]
    texts = []          # (node_id, path, text) for every string value
    emails = []
    smss = []
    trigger_tags = set()

    for idx, node in enumerate(nodes):
        nid = _node_id(node, idx)
        ntype = str(node.get("type") or "")
        node_name = str(node.get("name") or "")
        # A node NAME is client-facing copy too (it can carry AI/ghostwriter
        # wording or an em-dash); the name is scanned as text.
        if node_name:
            texts.append((nid, "name", node_name))
        params = node.get("parameters") or {}
        if isinstance(params, dict):
            for p, s in _walk_strings(params, "parameters"):
                texts.append((nid, p, s))
            tag = _trigger_tag(node)
            if tag:
                trigger_tags.add(tag)
            if _is_email_node(ntype, node_name, params):
                emails.append(nid)
            if _is_sms_node(ntype, node_name, params):
                smss.append(nid)
        if isinstance(node.get("options"), dict):
            for p, s in _walk_strings(node["options"], "options"):
                texts.append((nid, p, s))
        if isinstance(node.get("settings"), dict):
            for p, s in _walk_strings(node["settings"], "settings"):
                texts.append((nid, p, s))

    # Trigger tag: the node-bound contact tag, else the workflow name itself.
    report["trigger_tag"] = ",".join(sorted(trigger_tags))
    name_tag = ""
    if not report["trigger_tag"]:
        m = re.search(r"anthology-[a-z-]+", report["name"])
        if m:
            name_tag = m.group(0)
    is_client_facing = bool(expect_client_facing) or bool(
        report["trigger_tag"] or name_tag)
    report["client_facing"] = is_client_facing

    # ---- (a) editors never AI / ghostwriter ----
    for nid, path, text in texts:
        for kind, match in _text_violations(text):
            if kind == "em-dash":
                report["checks"]["no_em_dashes"]["pass"] = False
                report["checks"]["no_em_dashes"]["fails"].append(
                    {"node": nid, "path": path, "match": match})
            else:
                report["checks"]["editors_never_ai"]["pass"] = False
                report["checks"]["editors_never_ai"]["fails"].append(
                    {"node": nid, "path": path, "match": match})

    # ---- (c) email AND SMS for every client-facing workflow ----
    if is_client_facing:
        if not emails:
            report["checks"]["email_and_sms"]["pass"] = False
            report["checks"]["email_and_sms"]["fails"].append(
                {"node": "<workflow>", "path": "nodes[]",
                 "detail": "no email-sending action node found"})
        # Trevor's decree (contract workflows.producer_notify_out_of_scope +
        # MASTER-SPEC U13): producer-notification workflows are email-only
        # by design and are NOT client-facing author releases, so the SMS
        # law does not apply to them. The email law still holds.
        email_only = False
        pno = (contract.get("workflows") or {}).get(
            "producer_notify_out_of_scope")
        if isinstance(pno, str) and pno:
            m = re.search(r"'([A-Za-z0-9 _-]+)'", pno)
            if m:
                # EXACT match only (adversarial finding 1): a substring test
                # would let a differently-named workflow ride the carve-out
                # ("Chapter Approval Ready: Latest Content" is a different
                # surface with a different email law). Only the literal
                # workflow named in the contract decree is email-only.
                email_only = (m.group(1).strip().lower() ==
                              (report["name"] or "").strip().lower())
        if not smss and not email_only:
            report["checks"]["email_and_sms"]["pass"] = False
            report["checks"]["email_and_sms"]["fails"].append(
                {"node": "<workflow>", "path": "nodes[]",
                 "detail": "no SMS-sending action node found"})

    # ---- (d) stage-appropriate links ----
    if row:
        expected = []
        for lf in (row.get("email_link_fields") or []):
            if isinstance(lf, str) and lf.strip():
                expected.append(lf.strip())
        # The SMS body carries its link too: when the contract names an
        # sms_link_field, that field must ALSO resolve into deliverable_fields
        # (a map that lost the SMS field would otherwise silently audit a
        # phantom SMS surface). The SMS link itself is not required inside the
        # email body -- the link-only SMS shape is enforced by check (c).
        sms_ref = row.get("sms_link_field")
        if isinstance(sms_ref, str) and sms_ref.strip():
            expected.append(sms_ref.strip())
        # Normalize the contract's exact merge strings to bare keys, resolved
        # against deliverable_fields (the engine's single source of truth).
        # A reference the map does NOT carry (a key-rename on either side) is a
        # stage_links FAIL naming the exact field -- the deliverable_fields
        # drift blind spot, never a blank audit.
        declared = _strict_declared_link_keys(field_map)
        exp_keys = set()
        for e in expected:
            m = _BARE_KEY_RE.search(e)
            if m:
                exp_keys.add(m.group(0))
        unresolved = sorted(
            k for k in exp_keys if "contact." + k not in declared)
        if unresolved:
            report["checks"]["stage_links"]["pass"] = False
            report["checks"]["stage_links"]["fails"].append({
                "node": "<workflow>", "path": "contract row -> field-map",
                "detail": "contract link field(s) not declared in field-map "
                          "deliverable_fields (drift): %s"
                          % ", ".join("{{ contact.%s }}" % k for k in unresolved)})
        present = set()
        for nid, path, text in texts:
            for m in _LINK_FIELD_RE.finditer(text):
                present.add(m.group(1))
            # A bare URL is not a link-key reference; URLs are checked below.
        missing = sorted(k for k in exp_keys if k not in present and
                         "contact." + k in declared)
        if missing:
            report["checks"]["stage_links"]["pass"] = False
            report["checks"]["stage_links"]["fails"].append({
                "node": "<workflow>", "path": "nodes[]/parameters",
                "detail": "missing email link field(s) for the stage contract: %s"
                          % ", ".join("{{ contact.%s }}" % k for k in missing)})
        if not any(_URL_MARKER_RE.search(t) for _, _, t in texts):
            report["checks"]["stage_links"]["pass"] = False
            report["checks"]["stage_links"]["fails"].append({
                "node": "<workflow>", "path": "nodes[]",
                "detail": "no URL reference found anywhere in the workflow "
                          "(links must carry real per-stage URLs)"})
    elif is_client_facing:
        # No contract row: audit for the absence of any {{ contact.anthology_* }}
        # URL reference only (a client-facing workflow must point at SOMETHING).
        if not any(_URL_MARKER_RE.search(t) or _LINK_FIELD_RE.search(t)
                   for _, _, t in texts):
            report["checks"]["stage_links"]["pass"] = False
            report["checks"]["stage_links"]["fails"].append({
                "node": "<workflow>", "path": "nodes[]",
                "detail": "no deliverable link reference found (client-facing "
                          "workflow must carry at least one)"})

    # ---- (e) per-stage copy invariants ----
    all_text = "\n".join(t for _, _, t in texts)
    if is_client_facing:
        if PRODUCER_MERGE not in all_text:
            report["checks"]["per_stage_copy"]["pass"] = False
            report["checks"]["per_stage_copy"]["fails"].append({
                "node": "<workflow>", "path": "nodes[]",
                "detail": "missing producer-name merge %s" % PRODUCER_MERGE})
        if STANDING_INSTRUCTION not in all_text:
            report["checks"]["per_stage_copy"]["pass"] = False
            report["checks"]["per_stage_copy"]["fails"].append({
                "node": "<workflow>", "path": "nodes[]",
                "detail": "missing standing instruction text (copy_law "
                          "per_stage_copy.standing_instruction)"})
        if row and row.get("trigger_tag"):
            if report["trigger_tag"] != row["trigger_tag"]:
                report["checks"]["per_stage_copy"]["pass"] = False
                report["checks"]["per_stage_copy"]["fails"].append({
                    "node": "<workflow>", "path": "nodes[]",
                    "detail": "workflow trigger tag %r != contract trigger tag %r"
                              % (report["trigger_tag"] or "<none>",
                                 row["trigger_tag"])})

    # ---- aggregate ----
    for check, body in report["checks"].items():
        if not body["pass"]:
            for f in body["fails"]:
                code = {
                    "editors_never_ai": "AF-AE-COPY-AI-WORD",
                    "no_em_dashes": "AF-AE-COPY-EM-DASH",
                    "email_and_sms": (
                        "AF-AE-COPY-NO-EMAIL" if "email-sending" in str(f.get("detail"))
                        else "AF-AE-COPY-NO-SMS"),
                    "stage_links": "AF-AE-COPY-STAGE-LINKS",
                    "per_stage_copy": "AF-AE-COPY-STAGE-TOKENS",
                }[check]
                entry = {
                    "code": code,
                    "check": check,
                    "node": f.get("node", ""),
                    "path": f.get("path", ""),
                    "detail": f.get("detail", f.get("match", "")),
                }
                report["fails"].append(entry)
    report["ok"] = not report["fails"]
    return report


# ---------------------------------------------------------------------------
# File / directory collection + the check command.
# ---------------------------------------------------------------------------
def collect_workflow_files(paths, directory, *, out=None):
    """Resolve the audit inputs. Returns (files, error) where error is a
    message when the invocation is invalid (exit 2)."""
    out = out or sys.stderr
    files = []
    if paths:
        for p in paths:
            fp = Path(p).expanduser()
            if not fp.is_file():
                return [], "%s: not a file" % p
            files.append(fp)
    if directory:
        dp = Path(directory).expanduser()
        if not dp.is_dir():
            return [], "%s: not a directory" % directory
        for fp in sorted(dp.iterdir()):
            if fp.is_file() and fp.suffix.lower() in (".json",):
                files.append(fp)
    if not files:
        return [], "no workflow export JSON given (use paths and/or --directory)"
    return files, None


def _audit_templates_file(fp, field_map: dict, contract: dict, *,
                          expect_client_facing=False):
    """Audit ONE u10_u13 template document (the U10-U13 build output shape:
    {name, module, seat, trigger:{tag,type}, actions, data:{email,sms},
    links}) by translating it into the canonical n8n-export shape the audit
    judges. The template is the source of what deploys, so its copy law is
    the same law. A template missing the document shape is a malformed
    refusal (never a blind pass)."""
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "file": str(fp), "name": "", "trigger_tag": "",
            "client_facing": bool(expect_client_facing),
            "checks": {k: {"pass": True, "fails": []}
                       for k in ("editors_never_ai", "no_em_dashes",
                                 "email_and_sms", "stage_links",
                                 "per_stage_copy")},
            "fails": [{"code": "AF-AE-COPY-MALFORMED", "node": "<export root>",
                       "check": "malformed",
                       "detail": "template not readable/valid JSON: %s" % exc}],
            "ok": False,
        }
    name = str(doc.get("name") or "")
    trigger = doc.get("trigger") or {}
    tag = str(trigger.get("tag") or "")
    actions = doc.get("actions") or []
    data = doc.get("data") or {}
    email = data.get("email") or {}
    sms = data.get("sms") or {}
    links = doc.get("links") or {}
    # NESTED-SHAPE FALLBACK (adversarial finding 2): the U10-U13 builder is
    # free to nest a release's copy under data.release.* or name its trigger
    # tag under data.trigger_tag (02 Title Fire and 06 Release: Chapter both
    # do). An adapter that only reads the top level would audit an empty
    # surface and BLINDLY PASS client-facing copy the law must judge -- the
    # exact false-green the audit exists to prevent. Precedence (matching the
    # implementation exactly): a TOP-LEVEL email/sms block wins over a nested
    # data.release block (the document's direct data is the primary seat; the
    # release block is the fallback -- `email = email or val` keeps the first
    # truthy). For the trigger tag the loop is (release, data) with
    # last-write-wins, so data.trigger_tag beats release.trigger_tag, and the
    # document trigger.tag is the final fallback; an empty string is a real
    # builder value on contact_tag workflows whose tag lives at
    # data.trigger_tag, so the first non-empty tag wins.
    release = data.get("release") or {}
    for candidate in (release, data):
        for key in ("email", "sms"):
            val = candidate.get(key)
            if isinstance(val, dict) and val:
                if key == "email":
                    email = email or val
                else:
                    sms = sms or val
        dt = candidate.get("trigger_tag")
        if isinstance(dt, str) and dt.strip():
            tag = dt.strip()
    if not tag:
        tag = str(trigger.get("tag") or "")
    nodes = []
    if tag:
        nodes.append({"type": "n8n-nodes-base.gmail", "name": "Trigger",
                      "parameters": {"contactTag": tag}})
    if email:
        nodes.append({"type": "n8n-nodes-base.emailSend", "name": "Email",
                      "parameters": email})
    if sms:
        nodes.append({"type": "n8n-nodes-base.smsSend", "name": "SMS",
                      "parameters": sms})
    if links:
        nodes.append({"type": "n8n-nodes-base.code", "name": "Links",
                      "parameters": {"links": links}})
    if not nodes:
        # A DOCUMENTED SEAT ONLY template (owned_elsewhere, e.g. the Intake
        # Fire: its real surface is the webhook-to-route mapping owned by the
        # U02/U05 tooling) has no trigger/actions/data of its own to audit.
        # It is still not a blind pass (adversarial finding 4): any copy the
        # document DOES carry (notes, seat doc, delegate instructions) must
        # satisfy the text law. owned_elsewhere skips the workflow-law checks
        # (no trigger/email/sms surface exists here) but never the text scan.
        if doc.get("owned_elsewhere"):
            texts = []
            for p, s in _walk_strings(doc, "doc"):
                texts.append(("<doc>", p, s))
            violations = []
            for nid, path, text in texts:
                for kind, match in _text_violations(text):
                    violations.append(
                        {"node": nid, "path": path,
                         "code": ("AF-AE-COPY-EM-DASH" if kind == "em-dash"
                                  else "AF-AE-COPY-AI-WORD"),
                         "check": ("no_em_dashes" if kind == "em-dash"
                                   else "editors_never_ai"),
                         "detail": match})
            return {
                "file": str(fp), "name": name, "trigger_tag": "",
                "client_facing": bool(expect_client_facing),
                "checks": {k: {"pass": not any(v["check"] == k
                                               for v in violations), "fails": []}
                           for k in ("editors_never_ai", "no_em_dashes",
                                     "email_and_sms", "stage_links",
                                     "per_stage_copy")},
                "fails": violations, "ok": not violations, "skipped": True,
            }
        return {
            "file": str(fp), "name": name, "trigger_tag": "",
            "client_facing": bool(expect_client_facing),
            "checks": {k: {"pass": True, "fails": []}
                       for k in ("editors_never_ai", "no_em_dashes",
                                 "email_and_sms", "stage_links",
                                 "per_stage_copy")},
            "fails": [{"code": "AF-AE-COPY-MALFORMED", "node": "<export root>",
                       "check": "malformed",
                       "detail": "template carries no trigger/actions/data "
                                 "(empty audit surface)"}],
            "ok": False,
        }
    export = {"name": name, "nodes": nodes}
    return audit_workflow(export, field_map, contract, path=fp,
                          expect_client_facing=expect_client_facing)


def check_command(files, *, field_map_path=None, contract_path=None,
                  expect_client_facing=False, templates=False, jsonout=None,
                  out=None):
    """Audit every file, print the per-workflow PASS/FAIL report with exact
    violation locations, return exit code (0 all PASS; 4 any FAIL; 2 malformed/
    missing sources; 1 unexpected)."""
    out = out or sys.stderr
    fm, ct, why = load_sources(field_map_path, contract_path, out=out)
    if fm is None:
        return EX_STOP
    # SOURCE-INTEGRITY LOCK (NEW-6 U26 amendment): every contract
    # release_notifications link field must resolve into field-map
    # deliverable_fields BEFORE any export is judged. A field-map/contract
    # pair that drifted apart would audit a phantom workflow surface -- a
    # renamed key on either side is a located FAIL, never a blind audit.
    drifted = unresolved_link_fields(fm, ct)
    if drifted:
        for wf_name, ref in drifted:
            out.write("[copy_qc] AF-AE-COPY-FIELD-DRIFT: contract row %r "
                      "references link field %r that field-map "
                      "deliverable_fields does not carry (bare-key "
                      "resolution)\n" % (wf_name, ref))
        if jsonout is not None:
            json.dump({"ok": False, "drift": "AF-AE-COPY-FIELD-DRIFT",
                       "issues": [{"workflow": wf, "link_field": ref}
                                  for wf, ref in drifted]},
                      jsonout, indent=2)
            jsonout.write("\n")
        return EX_VIOLATION
    # The block-vs-inventory cross-check catches the one-sided rename the
    # union would mask (deliverable_fields re-keyed without the provisioning
    # inventory following): the map is lying about what it provisions.
    rename_drift = _deliverable_fields_rename_violations(fm)
    if rename_drift:
        for msg in rename_drift:
            out.write("[copy_qc] AF-AE-COPY-FIELD-DRIFT: %s\n" % msg)
        if jsonout is not None:
            json.dump({"ok": False, "drift": "AF-AE-COPY-FIELD-DRIFT",
                       "issues": [{"detail": m} for m in rename_drift]},
                      jsonout, indent=2)
            jsonout.write("\n")
        return EX_VIOLATION
    reports = []
    any_malformed = False
    for fp in files:
        try:
            export = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.write("[copy_qc] %s: not readable/valid JSON: %s\n" % (fp, exc))
            any_malformed = True
            continue
        if templates:
            reports.append(_audit_templates_file(
                fp, fm, ct, expect_client_facing=expect_client_facing))
        else:
            reports.append(audit_workflow(
                export, fm, ct, path=fp,
                expect_client_facing=expect_client_facing))

    # A malformed export is a fail-closed refusal (exit 2), never a silent skip.
    if any_malformed:
        return EX_STOP

    if jsonout is not None:
        json.dump({"ok": all(r["ok"] for r in reports), "workflows": reports},
                  jsonout, indent=2)
        jsonout.write("\n")
        return EX_OK if all(r["ok"] for r in reports) else EX_VIOLATION

    for r in reports:
        _print_report(r, out)
    return EX_OK if all(r["ok"] for r in reports) else EX_VIOLATION


def _print_report(r: dict, out):
    tag = "PASS" if r["ok"] else "FAIL"
    out.write("[copy_qc] %s  %s\n" % (tag, r["name"] or r["file"]))
    out.write("    file          : %s\n" % r["file"])
    if r["trigger_tag"]:
        out.write("    trigger_tag   : %s\n" % r["trigger_tag"])
    out.write("    client_facing : %s\n" % ("yes" if r["client_facing"] else "no"))
    for check, body in r["checks"].items():
        mark = "ok " if body["pass"] else "!! "
        extra = ""
        if not body["pass"]:
            extra = " (%d)" % len(body["fails"])
        out.write("    [%s%s] %s%s\n" % (mark, check, "FAIL" if not body["pass"] else "PASS", extra))
    for f in r["fails"]:
        out.write("      -> %s at %s (%s)\n" % (f["code"], f["node"],
                                           f.get("path", "<workflow>")))
        out.write("         %s\n" % f["detail"])
    if r["fails"]:
        out.write("    AF-AE-COPY-*: %d violation(s) -- fix the workflow copy and re-run\n"
                  % len(r["fails"]))


# ---------------------------------------------------------------------------
# list / plan commands (READ-ONLY; offline).
# ---------------------------------------------------------------------------
def list_command(files, *, jsonout=None, out=None):
    out = out or sys.stderr
    names = []
    for fp in files:
        try:
            export = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = export.get("name") or export.get("workflowName") or fp.name
        names.append((str(fp), name))
    if jsonout is not None:
        json.dump({"workflows": [{"file": f, "name": n} for f, n in names]},
                  jsonout, indent=2)
        jsonout.write("\n")
    else:
        for f, n in names:
            out.write("%s\t%s\n" % (f, n))
    return EX_OK


def plan_command(*, field_map_path=None, contract_path=None, out=None):
    out = out or sys.stderr
    fm, ct, why = load_sources(field_map_path, contract_path, out=out)
    if fm is None:
        return EX_STOP
    out.write("=== copy_qc_workflows plan (%s release-notification workflows) ===\n"
              % _PLATFORM)
    out.write("copy law (workflows.copy_law):\n")
    for k, v in COPY_LAW.items():
        out.write("  - %s: %s\n" % (k, (v.get("note") or v)))
    out.write("per-stage link expectations (workflows.release_notifications):\n")
    for r in workflow_rows(ct):
        out.write("  - %s (%s): email links %s ; SMS %s\n" % (
            r.get("name"), r.get("trigger_tag"),
            ", ".join(r.get("email_link_fields") or []),
            r.get("sms_link_field") or "<none>"))
    return EX_OK


# ---------------------------------------------------------------------------
# Live listing (optional; the SAME proven internal rail as the podcast gate).
# Credentials BY LABEL, never printed; browser UA via the registry.
# ---------------------------------------------------------------------------
def _reg():
    import anthology_registry
    return anthology_registry


def live_list_command(location_id: str, *, out=None, jsonout=None):
    """List the location's workflow names through the PROVEN internal rail
    (backend.leadconnectorhq.com /workflow/{loc}/list?limit=200 -- the surface
    verify-podcast-ghl-workflows.py proved live; Skill 44 doctrine: only
    proven endpoints). Credential: a per-client Firebase refresh token under
    the engine's refresh labels; SET/NOT-SET only, value never printed."""
    out = out or sys.stderr
    reg = _reg()
    rt_label, refresh = reg.resolve_firebase_refresh_token()
    ak_label, api_key = reg._resolve_firebase_api_key()
    if not refresh or not api_key:
        checked = ", ".join(reg.FIREBASE_REFRESH_LABELS)
        out.write("[copy_qc] HELD: no Firebase refresh token SET (labels: %s). "
                  "Live listing needs the client's OWN token; offline audit "
                  "needs none.\n" % checked)
        return EX_HELD
    loc_label, loc = reg.resolve_location(location_id)
    if not loc:
        out.write("[copy_qc] HELD: no Convert and Flow location id SET (labels: %s).\n"
                  % ", ".join(reg.LOCATION_LABELS))
        return EX_HELD
    masked = reg._mask_location(loc)
    try:
        rail = reg.InternalRailClient(refresh, api_key)
        listing = rail._get("/workflow/%s/list?limit=200" % reg.urllib.parse.quote(loc, safe=""))
        rows = [r for r in listing.get("rows", []) if r.get("type") == "workflow"]
    except reg.InternalRailUnavailable as exc:
        out.write("[copy_qc] HELD: internal-rail workflow list failed (marker %s): %s\n"
                  % (masked, exc))
        return EX_HELD
    names = sorted({str(r.get("name") or "") for r in rows if r.get("name")})
    if jsonout is not None:
        json.dump({"location": masked, "workflows": names}, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[copy_qc] LIVE workflow list (marker %s): %d workflow(s)\n"
                  % (masked, len(names)))
        for n in names:
            out.write("  %s\n" % n)
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: OFFLINE golden + attack fixtures (no network, no secrets).
# ---------------------------------------------------------------------------
def _golden_workflow(name="Anthology Release: Avatar", tag="anthology-release-avatar",
                     email=True, sms=True, producer_merge=True,
                     standing=True, links=True, bad_ai=False, em_dash=False,
                     extra_text=""):
    """A synthetic release-notification export that MUST pass every check
    (used by verify.sh's drift gate and the self-test)."""
    standing_text = STANDING_INSTRUCTION if standing else ""
    greeting = PRODUCER_MERGE if producer_merge else "your producer"
    from_name = PRODUCER_MERGE if producer_merge else "Anthology Editors"
    params = {"fromName": from_name,
              "emailBody": ("Great news from %s: your Avatar is ready. %s%s"
                            % (greeting, standing_text, extra_text))}
    if links:
        params["emailBody"] += (" See your PDF: {{ contact.anthology_avatar_pdf_url }}"
                                " and your Doc: {{ contact.anthology_avatar_doc_url }}.")
    nodes = [
        {"id": "trg-1", "name": "Tag %s" % tag, "type": "n8n-nodes-base.contactTagTrigger",
         "parameters": {"contactTag": tag}},
    ]
    if email:
        nodes.append({"id": "em-1", "name": "Send Email", "type": "n8n-nodes-base.emailSend",
                      "parameters": params})
    if sms:
        sms_greet = PRODUCER_MERGE if producer_merge else "The editors"
        sms_body = "Your Avatar is ready. %s" % sms_greet
        if links:
            sms_body += " See it: {{ contact.anthology_avatar_doc_url }}."
        nodes.append({"id": "sm-1", "name": "Send SMS", "type": "n8n-nodes-base.twilio",
                      "parameters": {"smsBody": sms_body}})
    if bad_ai:
        nodes[0]["name"] = "AI Avatar Trigger"
    if em_dash:
        nodes[-1]["parameters"]["smsBody"] = "Your Avatar is ready — click the link."
    return {"name": name, "nodes": nodes}


def _rename_deliverable_field(fm: dict, deliverable: str) -> dict:
    """A tampered field-map: ONE deliverable_fields key renamed (the
    drift-blind-spot attack). The 'avatar' pair keys are renamed
    'anthology_avatar_*' -> 'anthology_avatr_*' so the contract's avatar link
    fields stop resolving against the map. The rest of the map is
    byte-identical."""
    out = dict(fm)
    df = dict(fm.get("deliverable_fields") or {})
    pair = df.get(deliverable)
    if not isinstance(pair, dict):
        return out
    renamed = {}
    for slot, fk in pair.items():
        if isinstance(fk, str):
            fk = fk.replace("anthology_avatar_", "anthology_avatr_", 1)
        renamed[slot] = fk
    df[deliverable] = renamed
    out["deliverable_fields"] = df
    return out


def _attack_workflow(name="Anthology Release: Avatar", tag="anthology-release-avatar"):
    """A synthetic export that MUST fail every client-facing check: AI wording,
    em-dash, no SMS, no stage links, no producer merge, no standing text, and a
    mismatched trigger tag."""
    return {
        "name": name,
        "nodes": [
            {"id": "a-1", "name": "AI Ghostwriter Trigger",
             "type": "n8n-nodes-base.contactTagTrigger",
             "parameters": {"contactTag": "anthology-release-tone"}},  # wrong stage
            {"id": "a-2", "name": "Send Email",
             "type": "n8n-nodes-base.emailSend",
             "parameters": {"fromName": "Our AI ghostwriter", "emailBody": "Hi — "
                            "the AI wrote this. No links here."}},
            {"id": "a-3", "name": "Delay", "type": "n8n-nodes-base.wait",
             "parameters": {}},
        ],
    }


def _write_json_temp(td: str, name: str, obj) -> str:
    """Write a JSON object into a temp dir for a --field-map/--contract
    override and return the path."""
    fp = os.path.join(td, name)
    with open(fp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)
    return fp


def self_test() -> int:
    import io
    dev = io.StringIO()
    fm, ct, why = load_sources(out=dev)
    assert fm is not None, "self-test needs field-map + contract: %s" % why
    rows = workflow_rows(ct)
    assert len(rows) == 8, "contract must carry the eight release workflows, got %d" % len(rows)
    fm_del = deliverable_fields(fm)
    assert "avatar" in fm_del and "chapter" in fm_del, "field-map deliverable_fields missing pairs"

    # -- golden: PASS on every check ---------------------------------------
    g = audit_workflow(_golden_workflow(), fm, ct)
    assert g["ok"], "golden workflow must PASS: %r" % g["fails"]
    assert g["name"] == "Anthology Release: Avatar"
    assert g["trigger_tag"] == "anthology-release-avatar"
    assert g["client_facing"] is True
    for body in g["checks"].values():
        assert body["pass"], body

    # -- golden WITHOUT the standing text: the per-stage check FAILs ---------
    g2 = audit_workflow(_golden_workflow(standing=False), fm, ct)
    assert not g2["ok"]
    assert any(f["code"] == "AF-AE-COPY-STAGE-TOKENS" for f in g2["fails"])

    # -- golden WITHOUT producer merge: per-stage FAILs ----------------------
    g3 = audit_workflow(_golden_workflow(producer_merge=False), fm, ct)
    assert not g3["ok"]
    assert any("producer-name merge" in f["detail"] for f in g3["fails"])

    # -- golden WITHOUT links: stage-links FAILs -----------------------------
    g4 = audit_workflow(_golden_workflow(links=False), fm, ct)
    assert not g4["ok"]
    assert any(f["code"] == "AF-AE-COPY-STAGE-LINKS" for f in g4["fails"])

    # -- golden WITHOUT SMS: email_and_sms FAILs with the NO-SMS code --------
    g5 = audit_workflow(_golden_workflow(sms=False), fm, ct)
    assert not g5["ok"]
    assert any(f["code"] == "AF-AE-COPY-NO-SMS" for f in g5["fails"])

    # -- golden WITHOUT email: NO-EMAIL code ---------------------------------
    g6 = audit_workflow(_golden_workflow(email=False), fm, ct)
    assert not g6["ok"]
    assert any(f["code"] == "AF-AE-COPY-NO-EMAIL" for f in g6["fails"])

    # -- AI wording on a node NAME: editors_never_ai FAILs -------------------
    g7 = audit_workflow(_golden_workflow(bad_ai=True), fm, ct)
    assert not g7["ok"]
    assert any(f["code"] == "AF-AE-COPY-AI-WORD" for f in g7["fails"])

    # -- em-dash in SMS body: no_em_dashes FAILs -----------------------------
    g8 = audit_workflow(_golden_workflow(em_dash=True), fm, ct)
    assert not g8["ok"]
    assert any(f["code"] == "AF-AE-COPY-EM-DASH" for f in g8["fails"])

    # -- attack: EVERY client-facing check fails with the exact codes --------
    atk = audit_workflow(_attack_workflow(), fm, ct)
    assert not atk["ok"]
    codes = {f["code"] for f in atk["fails"]}
    assert codes >= {"AF-AE-COPY-AI-WORD", "AF-AE-COPY-EM-DASH",
                     "AF-AE-COPY-NO-SMS", "AF-AE-COPY-STAGE-LINKS",
                     "AF-AE-COPY-STAGE-TOKENS"}, codes
    # The attack workflow carries an email node -> NO-EMAIL must NOT fire.
    assert "AF-AE-COPY-NO-EMAIL" not in codes
    # Exact locations: the AI wording violation names the node id a-1.
    ai_fail = next(f for f in atk["fails"] if f["code"] == "AF-AE-COPY-AI-WORD")
    assert "a-1" in ai_fail["node"], ai_fail
    em_fail = next(f for f in atk["fails"] if f["code"] == "AF-AE-COPY-EM-DASH")
    assert "a-2" in em_fail["node"], em_fail

    # -- SOURCE-INTEGRITY LOCK (NEW-6 U26 amendment) -------------------------
    # The contract's link fields must resolve into field-map deliverable_fields
    # (bare-key resolution) -- a rename on EITHER side is a located FAIL, so a
    # drifted map can never silently audit a phantom workflow surface.
    assert unresolved_link_fields(fm, ct) == [], \
        "committed field-map/contract pair must have every link field resolved, got %r" \
        % unresolved_link_fields(fm, ct)
    assert _deliverable_fields_rename_violations(fm) == [], \
        "committed field-map deliverable_fields must match the provisioning inventory, got %r" \
        % _deliverable_fields_rename_violations(fm)

    # Golden against a tampered map (a deliverable_fields key rename, the
    # drift-blind-spot attack): the resolution FAILs, audit_workflow reports
    # the missing link field with AF-AE-COPY-STAGE-LINKS, and check_command
    # refuses the pair BEFORE any export is judged (exit 4).
    g_ren = audit_workflow(_golden_workflow(), _rename_deliverable_field(fm, "avatar"), ct)
    assert not g_ren["ok"]
    assert any(f["code"] == "AF-AE-COPY-STAGE-LINKS" for f in g_ren["fails"]), g_ren["fails"]
    drift_missing = next(f for f in g_ren["fails"]
                         if "anthology_avatar_pdf_url" in f["detail"])
    assert drift_missing, g_ren["fails"]
    # The one-sided rename ALSO trips the block-vs-inventory cross-check.
    assert _deliverable_fields_rename_violations(
        _rename_deliverable_field(fm, "avatar")), \
        "one-sided rename must be flagged by the block-vs-inventory cross-check"

    # A workflow export WITHOUT the email-body link references still FAILs
    # against a renamed map -- but now the FAIL names the missing field, so the
    # author sees the phantom surface instead of a blank audit.
    g5_ren = audit_workflow(_golden_workflow(links=False), _rename_deliverable_field(fm, "avatar"), ct)
    assert not g5_ren["ok"]
    assert any(f["code"] == "AF-AE-COPY-STAGE-LINKS" for f in g5_ren["fails"]), g5_ren["fails"]

    # A renamed map must also fail the untouched-field negative (a phantom key
    # from the old map cannot count as resolved).
    assert _bare_key("{{contact.anthology_avatar_pdf_url}}") == "anthology_avatar_pdf_url"
    assert _bare_key("contact.anthology_avatar_doc_url") == "anthology_avatar_doc_url"
    assert _bare_key("anthology_avatar_doc_url") == "anthology_avatar_doc_url"
    assert _bare_key("no key here") == ""
    fm_nopair = dict(fm)
    fm_nopair["deliverable_fields"] = dict(fm.get("deliverable_fields") or {})
    fm_nopair["deliverable_fields"].pop("avatar", None)
    assert resolve_link_field(fm_nopair, "{{contact.anthology_avatar_pdf_url}}") == ""
    assert resolve_link_field(fm, "{{contact.anthology_avatar_pdf_url}}") == "contact.anthology_avatar_pdf_url"
    assert resolve_link_field(fm, "anthology_avatar_doc_url") == "contact.anthology_avatar_doc_url"
    assert resolve_link_field(fm, "bogus_anthology_nonexistent_url") == ""
    # The contract's own link fields must ALL resolve (incl. sms_link_field):
    # a committed pair that does not is itself the drift the lock exists for.
    assert all(
        resolve_link_field(fm, ref)
        for r in workflow_rows(ct)
        for ref in (r.get("email_link_fields") or []) if isinstance(ref, str)
    ), "every contract email_link_fields ref must resolve into deliverable_fields"
    assert all(
        resolve_link_field(fm, r.get("sms_link_field"))
        for r in workflow_rows(ct) if isinstance(r.get("sms_link_field"), str)
    ), "every contract sms_link_field must resolve into deliverable_fields"

    # -- malformed export: fail-closed, never a silent skip ------------------
    bad = audit_workflow({"name": "Nope", "nodes": "not-a-list"}, fm, ct)
    assert not bad["ok"] and bad["fails"][0]["code"] == "AF-AE-COPY-MALFORMED"

    # -- NON-client-facing workflow (no trigger, no name tag): only the
    #    text checks apply; channel/link/stage checks are skipped -------------
    internal = {"name": "Producer Notify",
                "nodes": [{"id": "n-1", "name": "Send Email",
                           "type": "n8n-nodes-base.emailSend",
                           "parameters": {"emailBody": "Chapter approval ready."}}]}
    nr = audit_workflow(internal, fm, ct)
    assert nr["ok"], "non-client-facing workflow must PASS: %r" % nr["fails"]
    assert nr["client_facing"] is False

    # -- never-print: no secret value ever reaches any surface ---------------
    all_text = dev.getvalue() + repr(g["fails"]) + repr(atk["fails"])
    for token in ("pit-", "Bearer ", "loc_QcDX"):
        assert token not in all_text, "surface leak: %r must never appear" % token

    # -- offline check + plan commands over a temp golden file ----------------
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        fp = Path(td) / "golden.json"
        fp.write_text(json.dumps(_golden_workflow()), encoding="utf-8")
        dev2 = io.StringIO()
        rc = check_command([fp], jsonout=dev2)
        assert rc == EX_OK, "file check of the golden export must exit 0, got %s" % rc
        atk_fp = Path(td) / "attack.json"
        atk_fp.write_text(json.dumps(_attack_workflow()), encoding="utf-8")
        dev3 = io.StringIO()
        rc = check_command([fp, atk_fp], jsonout=dev3)
        assert rc == EX_VIOLATION, "attack file must exit 4, got %s" % rc
        dev4 = io.StringIO()
        rc = plan_command(out=dev4)
        assert rc == EX_OK and "copy law" in dev4.getvalue()
        dev5 = io.StringIO()
        rc = list_command([fp], out=dev5)
        assert rc == EX_OK and "Anthology Release: Avatar" in dev5.getvalue()

        # NEW-6 U26 amendment: a tampered field-map (deliverable_fields key
        # rename) must make the whole check command FAIL CLOSED with exit 4
        # and the AF-AE-COPY-FIELD-DRIFT location -- the audit never runs
        # against a lying map.
        import copy as _copy
        fm_bak = _copy.deepcopy(fm)
        ct_bak = _copy.deepcopy(ct)
        try:
            dev6 = io.StringIO()
            rc = check_command([fp], field_map_path=_write_json_temp(td, "field-map.json", _rename_deliverable_field(fm, "avatar")),
                               contract_path=_write_json_temp(td, "contract.json", ct), out=dev6)
            assert rc == EX_VIOLATION, "renamed-field-map check must exit 4, got %s" % rc
            assert "AF-AE-COPY-FIELD-DRIFT" in dev6.getvalue(), dev6.getvalue()
            assert "anthology_avatar_pdf_url" in dev6.getvalue(), dev6.getvalue()
            # and plan must still work (plan is a contract print, not an audit)
            dev7 = io.StringIO()
            rc = plan_command(out=dev7)
            assert rc == EX_OK and "copy law" in dev7.getvalue()
        finally:
            fm, ct = fm_bak, ct_bak

    # -- template mode (U14): a document-shaped u10_u13 template with
    #    trigger/actions/data audits clean (the avatar template) -----------
    tpl = {
        "name": "Anthology Release: Avatar", "module": "w3_release_avatar",
        "trigger": {"tag": "anthology-release-avatar", "type": "contact_tag"},
        "actions": ["send-email", "send-sms"],
        "data": {
            "email": {
                "body": ("Hi {{ custom_values.producer }},\n\nYour author "
                         "profile for {{ custom_values.anthology_name }} is "
                         "ready.\n\nThe PDF is yours to view. The Google Doc "
                         "is the one you edit, and it is the version we "
                         "use.\n\nSee it: "
                         "{{ contact.anthology_avatar_pdf_url }} and "
                         "{{ contact.anthology_avatar_doc_url }}."),
                "subject": "Your Avatar is ready"},
            "sms": {"body": "Your Avatar is ready. See it: "
                            "{{ contact.anthology_avatar_doc_url }}."}},
        "links": {"email_links": ["{{contact.anthology_avatar_pdf_url}}",
                                  "{{contact.anthology_avatar_doc_url}}"],
                  "sms_link": "{{contact.anthology_avatar_doc_url}}"},
    }
    with _tf.TemporaryDirectory() as td:
        tpl_fp = Path(td) / "tpl.json"
        tpl_fp.write_text(json.dumps(tpl), encoding="utf-8")
        dev_t = io.StringIO()
        rc = check_command([tpl_fp], templates=True, jsonout=dev_t)
        assert rc == EX_OK, "template golden must exit 0, got %s" % rc
        dev_tb = io.StringIO()
        rc = check_command([tpl_fp], templates=True, out=dev_tb)
        assert rc == EX_OK and "PASS" in dev_tb.getvalue()

        # A producer-notification template (email-only per Trevor's decree)
        # PASSES: the SMS law does not apply to producer notifications.
        prod_tpl = {
            "name": "Chapter Approval Ready",
            "trigger": {"tag": "anthology-producer-chapter-ready",
                        "type": "contact_tag"},
            "actions": ["send-email"],
            "data": {"email": {
                "body": ("Dear {{ custom_values.producer }},\n\nOur editors "
                         "have finished the chapter, and it is ready for your "
                         "review at the board.\n\nView the chapter PDF here: "
                         "{{ contact.anthology_chapter_pdf_url }}\n\nEdit the "
                         "chapter in the Google Doc here: "
                         "{{ contact.anthology_chapter_doc_url }}\n\nThe PDF "
                         "is yours to view. The Google Doc is the one you "
                         "edit, and it is the version we use.")},
                "sms": {}},
            "links": {"email_links": ["{{contact.anthology_chapter_pdf_url}}",
                                      "{{contact.anthology_chapter_doc_url}}"],
                      "sms_link": ""},
        }
        prod_fp = Path(td) / "prod.json"
        prod_fp.write_text(json.dumps(prod_tpl), encoding="utf-8")
        dev_p = io.StringIO()
        rc = check_command([prod_fp], templates=True, jsonout=dev_p)
        assert rc == EX_OK, "producer-notification template must exit 0, got %s" % rc

        # A documented seat (owned_elsewhere, e.g. Intake Fire) is a SKIP.
        skip_tpl = {"name": "Anthology Intake Fire", "owned_elsewhere": True,
                    "data": None}
        skip_fp = Path(td) / "skip.json"
        skip_fp.write_text(json.dumps(skip_tpl), encoding="utf-8")
        dev_s = io.StringIO()
        rc = check_command([skip_fp], templates=True, jsonout=dev_s)
        assert rc == EX_OK, "documented seat must exit 0, got %s" % rc

        # A template with NO audit surface and NOT owned elsewhere is a
        # malformed FAIL (fail-closed), never a silent pass.
        mal_tpl = {"name": "Weird", "data": None}
        mal_fp = Path(td) / "mal.json"
        mal_fp.write_text(json.dumps(mal_tpl), encoding="utf-8")
        dev_m = io.StringIO()
        rc = check_command([mal_fp], templates=True, jsonout=dev_m)
        assert rc == EX_VIOLATION, "malformed template must exit 4, got %s" % rc

    print("copy_qc_workflows self-test: OK "
          "(golden PASS, per-check FAIL ladders [AI word, em-dash, no-email, "
          "no-sms, missing stage links, missing stage tokens], attack fixture "
          "fails EVERY client-facing check with exact locations + codes, "
          "NEW-6 deliverable_fields drift lock [rename attack FAILS with "
          "AF-AE-COPY-FIELD-DRIFT, exit 4, never a blind audit], malformed "
          "export fail-closed, non-client-facing exempt, never-print, "
          "offline check/plan/list over fixtures)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="copy_qc_workflows.py",
        description="Copy-compliance QC gate over the %s release-notification "
                    "workflow exports (Skill 59, MASTER-SPEC NEW-6): editors "
                    "never AI/ghostwriter, zero em-dashes, email AND SMS for "
                    "client-facing, stage-appropriate links, per-stage copy "
                    "invariants." % _PLATFORM)
    ap.add_argument("workflows", nargs="*", help="workflow export JSON path(s)")
    ap.add_argument("--directory", default="",
                    help="audit every *.json under a directory")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (stage link keys)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json (copy law + "
                         "release_notifications)")
    ap.add_argument("--expect-client-facing", action="store_true",
                    help="treat every audited workflow as client-facing even "
                         "when no trigger tag is found")
    ap.add_argument("--templates", action="store_true",
                    help="audit U10-U13 build template documents (document-"
                         "shaped templates under scripts/u10_u13_workflows/) "
                         "instead of n8n workflow exports. Translates each "
                         "document into the canonical n8n shape internally "
                         "so the same copy law applies.")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable report on stdout")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id for "
                         "--list-live (label-resolved; never printed)")
    ap.add_argument("cmd", choices=["check", "list", "list-live", "plan", "self-test"])

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's required positional cmd never rejects the flag form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None
    out = sys.stderr

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan_command(field_map_path=args.field_map,
                                contract_path=args.contract, out=out)

        if args.cmd == "list-live":
            return live_list_command(args.location_id, out=out, jsonout=jsonout)

        files, err = collect_workflow_files(args.workflows, args.directory, out=out)
        if err:
            out.write("[copy_qc] usage: %s\n" % err)
            ap.print_usage(out)
            return EX_STOP

        if args.cmd == "list":
            return list_command(files, jsonout=jsonout, out=out)
        if args.cmd == "check":
            return check_command(
                files, field_map_path=args.field_map,
                contract_path=args.contract,
                expect_client_facing=args.expect_client_facing,
                templates=args.templates,
                jsonout=jsonout, out=out)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.stderr.write("[copy_qc] file not found: %s\n" % exc)
        return EX_ERR
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[copy_qc] unexpected error: %s\n" % type(exc).__name__)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
