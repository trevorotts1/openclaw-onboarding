#!/usr/bin/env python3
"""R71H seam, producer side (S71-08 P1): the automation hand-off emitter.

  python3 scripts/automation_handoff.py <run_dir> --deploy-mode draft-only

references/automation-handoff.md (Item 31) specifies
handoff/automation-handoff.json and the stage gate verifies it at
ghl-install-test close (stage_gate.check_install_handoff), but the
contract had no producer: nothing wrote the file and nothing built the
dispatch to Skill 44. This module is the producer. stage_gate.py calls
emit_handoff() at ghl-install-test close, before the hand-off check, so
a close either produces the hand-off from the run's own records or
refuses, naming why.

What it does, per the R71H seam packet (S44 to S71, 2026-10-15):

1. EMIT. For a GHL publish target, the hand-off is derived from the
   run's records and from nowhere else:
   - forms: Item 32's ghl-install-test/funnel-completion.json forms
     array is the SOLE source of form IDs (form_id, form_name from the
     record's name, page_section from its attached_to_step; optin_fields
     copied only when the funnel record itself carries them, never
     invented);
   - funnel_id: the funnel-completion record's funnel.funnel_id;
   - page_id: the install receipt's install.target.page_id_or_url for
     a GHL target, cross-checked against the funnel steps' ghl_page
     bindings;
   - location_id: the VALUE of the environment variable intake records
     for the location credential (intake records presence and the
     variable name only, never the value; the value is read from the
     process environment at emit time, like write_intake.py's presence
     check). The Private Integration Token is never read.
   - conversational_requirements.triggers: the trigger classes the
     funnel creates, derived from the funnel-completion record (one
     opt-in class per form, purchase per bound order form, booking per
     booking/calendar step), mirroring stage_gate's derivation.
   A hand-off file the emitter itself wrote (proven by the emission
   record: origin "emitted" plus the recorded hash matching the file)
   is regenerated from current records. A hand-off file
   authored elsewhere is never overwritten: the emitter verifies it
   against the records and the close refuses on any disagreement, the
   form IDs first (both directions, named).

2. HASH-LOCK. The emitter computes the written file's SHA-256. The
   gate's record_close stores it in state (stages.ghl-install-test
   .handoff_sha256), publish-verify verifies the file is carried forward
   unchanged, and the dispatch envelope carries the same hash.

3. DISPATCH ENVELOPE. build_envelope() constructs the automation
   request envelope of packet section 3, field for field, and refuses
   anything the receiver would refuse: a deploy_mode other than
   "draft-only" (absent counts as refused at every entry point; it is
   never defaulted), an
   unknown field, a hand-off hash that does not match the written
   hand-off, a workflow spec that leaves a hand-off form uncovered or
   covers one twice, a contact_tag mechanism without its verbatim
   Phase-A tag string. The gate constructs and writes
   handoff/automation-request.json only when the run carries the launch
   wiring inputs (launch identity, the plan approval reference, and
   the per-form workflow spec) in page-request.json or launch.json:
   workflow behavior, re-entry semantics and tag strings are launch
   decisions (packet doc 02 section 7, doc 14 Phase B), not facts the
   page run's records contain, and this module does not invent them.
   handoff/emission-record.json records what was emitted, the hash,
   and, when no envelope was constructed, exactly what was missing.
   NOTHING is sent anywhere by this module: the envelope is a run
   artifact; the delegated dispatch is a separate act.

4. RECEIPT FILING (S71-08 P2). When a dispatch outcome is recorded
   in the run (the receiving side's return, or an operator-recorded
   refusal or failure), file_dispatch_receipt() files the stage-14
   receipt at private/receipts/automation-wiring.json, mapped field
   for field from packet section 4: request_id, request_version,
   handoff_sha256, the outcome, and per workflow workflow_id, name,
   the trigger (the declared origin {form_submitted, form_id} with
   the mechanism recorded alongside), build_method ("caf-cli" when
   the recorded execution provenance is tier 0 caf,
   "tier4-browser-backstop" when Tier 4 was used), the QC evidence
   (qc.script = qc-built-workflow.sh, its exit_code, the filled
   checklist instance filed under automation-wiring/,
   checklist_complete, and the WF item count carried verbatim), the
   read-back {exists, status}, the conversational array, and
   ghl_pack_version. The receipt is bound to the dispatch of record
   before anything is written: its handoff_sha256 must equal the
   hash locked in state at ghl-install-test close
   (stages.ghl-install-test.handoff_sha256) and the envelope's, and
   its request identity must match the envelope's; a disagreement is
   flagged by name and nothing is filed. Refusals are receipts too:
   a refused dispatch files with the refusal reason verbatim and
   leaves the automation-wiring stage open (the gate names the
   refusal at close). Credential hygiene is unchanged: outcomes
   carry identifiers, statuses, and hashes only, never values.

Exit codes for the CLI: 0 emitted or filed (or not applicable),
1 refused with the reasons printed, 2 usage error.
"""
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

HANDOFF_REL = "handoff/automation-handoff.json"
ENVELOPE_REL = "handoff/automation-request.json"
EMISSION_REL = "handoff/emission-record.json"
RECEIPT_REL = "private/receipts/automation-wiring.json"
STATE_REL = "private/state.json"
CHECKLIST_DIR = "automation-wiring"
QC_SCRIPT = "qc-built-workflow.sh"
OUTCOMES = ("accepted", "refused", "failed")
BUILD_METHODS = ("caf-cli", "tier4-browser-backstop")
# Packet section 4: the receipt's build_method is mapped from the
# execution provenance the receiver records. The provenance spellings
# are this seam's recording vocabulary for the receiver's return;
# a verbatim build_method in R71H's vocabulary is also accepted, and
# the two must agree when both are recorded.
PROVENANCE_BUILD_METHODS = {
    "tier0-caf": "caf-cli", "tier-0-caf": "caf-cli", "caf-cli": "caf-cli",
    "tier4-browser": "tier4-browser-backstop",
    "tier-4-browser": "tier4-browser-backstop",
    "tier4-browser-backstop": "tier4-browser-backstop",
}
TRIGGER_CLASSES = ("opt-in", "purchase", "booking")
ONLY_DEPLOY_MODE = "draft-only"
DEFAULT_LOCATION_VAR = "GHL_LOCATION_ID"
ENVELOPE_FIELDS = ("request_id", "request_version", "location_id",
                   "launch_id", "requesting_room", "deploy_mode",
                   "approval", "handoff_sha256", "plan", "workflows")
REQUEST_ID_RE = re.compile(r"^gxo_[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EnvelopeError(Exception):
    """The envelope cannot be constructed as specified; refusal, named."""


def load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def serialize(obj):
    """The run-artifact serialization the emitter writes (and hashes)."""
    return (json.dumps(obj, indent=2) + "\n").encode("utf-8")


def canonical_bytes(obj):
    """Canonical JSON for plan_hash: byte-identical to the receiver's
    plan_hash() (44-convert-and-flow-operator/tools/siglaunch/receiver/
    receiver.py: json.dumps(plan, sort_keys=True).encode()). Emitters
    hash identically to the receiver (R71H F2 cure 1)."""
    return json.dumps(obj, sort_keys=True).encode()


def derive_trigger_classes(fc):
    """Trigger classes the funnel creates, from Item 32's record (the
    same derivation stage_gate.derive_conversational_triggers performs,
    reduced to the class set R71H's hand-off records)."""
    classes = set()
    if isinstance(fc, dict) and fc.get("status") != "not_applicable":
        if any(isinstance(f, dict) and f.get("form_id")
               for f in fc.get("forms") or []):
            classes.add("opt-in")
        if any(isinstance(o, dict) and o.get("bound") is True
               and o.get("order_form_id")
               for o in fc.get("order_forms") or []):
            classes.add("purchase")
        if any(isinstance(s, dict)
               and s.get("type") in ("booking", "calendar")
               for s in fc.get("steps") or []):
            classes.add("booking")
    return [c for c in TRIGGER_CLASSES if c in classes]


def expected_handoff(run_dir, env):
    """Derive the hand-off from the run's records.

    Returns (handoff, write_problems, sourced, location_problem,
    record_problems): the derived dict (None when the stage does not
    apply); every named problem that prevents WRITING the hand-off;
    which fields were actually sourced from records (the verify path
    compares only sourced fields); the location-source problem
    separately, because it blocks writing (the value must come from
    the environment at emit time) but never blocks verifying a
    hand-off that already exists; and the funnel-record problems
    separately, because those are the ones that also block VERIFYING:
    without Item 32's record the mandated form-ID comparison cannot
    be performed at all, so verification fails closed."""
    intake = load_json(run_dir / "intake.json") or {}
    if intake.get("publish_target") != "ghl":
        return None, [], {}, None, []
    problems = []
    record_problems = []
    sourced = {}

    fc = load_json(run_dir / "ghl-install-test" / "funnel-completion.json")
    if fc is None:
        record_problems.append(
            "funnel-completion receipt ghl-install-test/funnel-completion.json "
            "is missing or unreadable; Item 32's record is the sole source "
            "of the hand-off's form IDs (fix plan Item 31)")
        fc = {}
    elif fc.get("status") == "not_applicable":
        record_problems.append(
            "funnel-completion recorded not_applicable but intake.publish_target "
            "is \"ghl\"; the funnel-completion sub-stage is required for every "
            "GHL publish target, and the hand-off is derived from its record")

    forms = []
    if fc:
        for f in fc.get("forms") or []:
            if not isinstance(f, dict):
                continue
            if not f.get("form_id"):
                record_problems.append(
                    f"funnel-completion form {f.get('name')!r} carries no "
                    f"form_id; a form without an ID cannot enter the hand-off "
                    f"and no other source may supply one (fix plan Item 31)")
                continue
            entry = {"form_id": f["form_id"],
                     "form_name": f.get("name"),
                     "page_section": f.get("attached_to_step")}
            if isinstance(f.get("optin_fields"), list):
                entry["optin_fields"] = f["optin_fields"]
            forms.append(entry)
    sourced["forms"] = forms

    funnel_id = (fc.get("funnel") or {}).get("funnel_id")
    if funnel_id:
        sourced["funnel_id"] = funnel_id
    else:
        record_problems.append(
            "funnel-completion.funnel.funnel_id is not recorded; the "
            "hand-off's funnel_id comes from Item 32's record")

    receipt = load_json(run_dir / "private" / "receipts" / "ghl-install-test.json") or {}
    target = (receipt.get("install") or {}).get("target") or {}
    page_id = None
    if target.get("kind") == "ghl" and target.get("page_id_or_url"):
        page_id = target["page_id_or_url"]
        bound = {s["binding"]["page_id"]
                 for s in fc.get("steps") or []
                 if isinstance(s, dict)
                 and (s.get("binding") or {}).get("kind") == "ghl_page"
                 and (s.get("binding") or {}).get("page_id")}
        if bound and page_id not in bound:
            problems.append(
                f"install receipt target page_id_or_url {page_id!r} is not one "
                f"of the funnel steps' ghl_page bindings {sorted(bound)}; the "
                f"hand-off's page_id must name the page the funnel binds")
    if page_id:
        sourced["page_id"] = page_id
    else:
        problems.append(
            "the install receipt (private/receipts/ghl-install-test.json) "
            "records no GHL target page_id_or_url; the hand-off's page_id "
            "comes from the install record")

    creds = intake.get("credentials") or {}
    var = (creds.get("location_id") or {}).get("variable") or DEFAULT_LOCATION_VAR
    location_id = (env.get(var) or "").strip()
    location_problem = None
    if location_id:
        sourced["location_id"] = location_id
    else:
        location_problem = (
            f"the location ID value is not available: intake records the "
            f"variable name {var} and its presence only, and {var} is not set "
            f"in the environment at emit time; supply it in this install's own "
            f"secrets.env and rerun (the hand-off carries IDs only, and the "
            f"value is never read from any other record)")

    handoff = {}
    for key in ("location_id", "funnel_id", "page_id"):
        if key in sourced:
            handoff[key] = sourced[key]
    handoff["forms"] = forms
    handoff["conversational_requirements"] = {
        "triggers": derive_trigger_classes(fc)}
    return (handoff, record_problems + problems, sourced, location_problem,
            record_problems)


def _agreement_failures(run_dir, current, expected, sourced):
    """Verify an externally authored hand-off against the records. Only
    sourced fields are compared; the form-ID equality is the seam's own
    refusal rule and is always checked, in both directions, by name."""
    failures = []
    cur_forms = current.get("forms")
    cur_ids = {f.get("form_id") for f in cur_forms if isinstance(f, dict)} \
        if isinstance(cur_forms, list) else set()
    exp_ids = {f["form_id"] for f in sourced.get("forms") or []}
    if cur_ids != exp_ids:
        failures.append(
            f"stage ghl-install-test: hand-off form IDs {sorted(map(str, cur_ids))} "
            f"do not equal funnel-completion.json form IDs "
            f"{sorted(map(str, exp_ids))}; Item 32's receipt is the sole "
            f"source of the hand-off's form IDs (fix plan Item 31)")
    for key in ("funnel_id", "page_id", "location_id"):
        if key in sourced and current.get(key) != sourced[key]:
            failures.append(
                f"stage ghl-install-test: hand-off {key} {current.get(key)!r} "
                f"disagrees with the run's records ({sourced[key]!r}); the "
                f"hand-off is a record of the install, not an independent "
                f"claim (fix plan Item 31)")
    return failures


def _launch_inputs(run_dir, intake):
    """The launch wiring inputs, when the run carries them: launch
    identity, the plan approval reference, and the automation spec
    (folder + per-form workflow entries) from page-request.json (doc 02
    section 6) or the canonical launch.json (doc 02 section 2). Returns
    (found_dict, missing_list)."""
    pr = load_json(run_dir / "page-request.json") or {}
    launch = load_json(run_dir / "launch.json") or {}
    identity = launch.get("identity") or {}
    approval = launch.get("approval") or {}
    found = {}
    found["launch_id"] = (pr.get("launch_id") or identity.get("launch_id")
                          or intake.get("launch_id"))
    found["approval_ref"] = (
        pr.get("plan_approval_ref") or pr.get("approval_ref")
        or (pr.get("approval") or {}).get("ref")
        or (pr.get("approval") or {}).get("launch_plan_approval_id")
        or approval.get("launch_plan_approval_id"))
    spec = pr.get("automation") or launch.get("automation") or {}
    found["folder"] = spec.get("folder")
    found["workflow_specs"] = spec.get("workflows")
    missing = []
    if not found["launch_id"]:
        missing.append("launch_id (page-request.json or launch.json identity)")
    if not found["approval_ref"]:
        missing.append("the plan approval reference (doc 02 section 9 approval "
                       "record, carried by the launch request)")
    if not found["folder"]:
        missing.append("the automation folder (launch automation spec)")
    if not isinstance(found["workflow_specs"], list) or not found["workflow_specs"]:
        missing.append("the per-form workflow spec (launch automation spec: "
                       "slug, expected_steps, allow_multiple, mechanism or "
                       "no_workflow_reason per hand-off form)")
    return found, missing


def build_envelope(handoff, handoff_sha256, *, launch_id, requesting_room,
                   approval_ref, folder, workflow_specs, deploy_mode,
                   request_id, request_version):
    """Construct the packet section 3 envelope, field for field, or
    raise EnvelopeError naming the refusal. deploy_mode is a required
    argument on purpose: absent is refused exactly like any other value
    that is not "draft-only"; nothing here defaults it."""
    if deploy_mode != ONLY_DEPLOY_MODE:
        raise EnvelopeError(
            f"deploy_mode must be exactly {ONLY_DEPLOY_MODE!r} in this seam; "
            f"got {deploy_mode!r}. Absent or any other value is refused, "
            f"never defaulted; no live activation exists in this seam")
    written = serialize(handoff)
    if not isinstance(handoff_sha256, str) or not SHA256_RE.match(handoff_sha256):
        raise EnvelopeError("handoff_sha256 is not a SHA-256 hex digest")
    if sha256_bytes(written) != handoff_sha256:
        raise EnvelopeError(
            "handoff_sha256 does not match the written hand-off's SHA-256; "
            "the envelope carries the hash of the hand-off it dispatches")
    if not REQUEST_ID_RE.match(request_id or ""):
        raise EnvelopeError(
            f"request_id {request_id!r} is not gxo_ + 12 hex (Item 33a "
            f"echo-binding convention)")
    if not isinstance(request_version, int) or request_version < 1:
        raise EnvelopeError("request_version must be a positive integer")
    if not launch_id:
        raise EnvelopeError("launch_id is required")
    if requesting_room not in ("S71", "S06"):
        raise EnvelopeError(
            f"requesting_room must be \"S71\" or \"S06\", got {requesting_room!r}")
    if not approval_ref:
        raise EnvelopeError("approval.ref is required (the launch plan "
                            "approval record this dispatch executes under)")
    if not folder:
        raise EnvelopeError("the wiring plan names no folder")
    if handoff.get("location_id") is None:
        raise EnvelopeError("the hand-off carries no location_id; the "
                            "envelope's location is the hand-off's")

    forms = handoff.get("forms") or []
    form_ids = [f.get("form_id") for f in forms if isinstance(f, dict)]
    by_form = {}
    for spec in workflow_specs or []:
        if not isinstance(spec, dict) or not spec.get("form_id"):
            raise EnvelopeError("every workflow spec entry must name its form_id")
        fid = spec["form_id"]
        if fid in by_form:
            raise EnvelopeError(f"form {fid} is covered twice in the workflow spec")
        if fid not in form_ids:
            raise EnvelopeError(
                f"workflow spec covers form {fid!r}, which is not in the "
                f"hand-off; specs bind to the hand-off's forms and nowhere else")
        by_form[fid] = spec
    uncovered = [fid for fid in form_ids if fid not in by_form]
    if uncovered:
        raise EnvelopeError(
            f"hand-off form(s) {uncovered} have no workflow spec entry: each "
            f"form is either a build entry or carries a no_workflow_reason")

    workflows = []
    plan = {"folder": folder}
    for fid in form_ids:
        spec = by_form[fid]
        reason = spec.get("no_workflow_reason")
        if isinstance(reason, str) and reason.strip():
            workflows.append({"form_id": fid, "no_workflow_reason": reason})
            continue
        slug = spec.get("slug")
        if not slug:
            raise EnvelopeError(f"form {fid}: build entry names no slug")
        if slug in plan:
            raise EnvelopeError(f"workflow slug {slug!r} is used twice")
        steps = spec.get("expected_steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
            raise EnvelopeError(
                f"form {fid}: expected_steps must be a positive integer, "
                f"got {steps!r}")
        allow = spec.get("allow_multiple")
        if not isinstance(allow, bool):
            raise EnvelopeError(
                f"form {fid}: allow_multiple (the re-entry contract) must be "
                f"recorded true or false, got {allow!r}")
        mech = spec.get("mechanism") or {}
        mtype = mech.get("type")
        if mtype == "contact_tag":
            if not isinstance(mech.get("tag"), str) or not mech["tag"].strip():
                raise EnvelopeError(
                    f"form {fid}: contact_tag mechanism requires the verbatim "
                    f"Phase-A tag string; a tag is never invented here")
            mechanism = {"type": "contact_tag", "tag": mech["tag"]}
        elif mtype == "native":
            if mech.get("build_method") != "tier4-browser-backstop":
                raise EnvelopeError(
                    f"form {fid}: native mechanism requires build_method "
                    f"\"tier4-browser-backstop\"")
            mechanism = {"type": "native",
                         "build_method": "tier4-browser-backstop"}
        else:
            raise EnvelopeError(
                f"form {fid}: mechanism.type must be \"contact_tag\" or "
                f"\"native\", got {mtype!r}")
        name = spec.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise EnvelopeError(
                f"form {fid}: name must be a non-empty string, got {name!r}")
        origin = {"type": "form_submitted", "form_id": fid}
        workflows.append({"slug": slug, "expected_steps": steps,
                          "allow_multiple": allow, "origin": origin,
                          "mechanism": mechanism})
        # R71H F2 cure 2: the receiver's plan contract requires a
        # "name" on every workflow definition before it hashes and
        # dispatches; the recorded slug is the fallback identity.
        plan[slug] = {"name": name or slug, "form_id": fid,
                      "origin": origin, "mechanism": mechanism,
                      "expected_steps": steps, "allow_multiple": allow}
    plan_hash = sha256_bytes(canonical_bytes(plan))
    return {
        "request_id": request_id,
        "request_version": request_version,
        "location_id": handoff.get("location_id"),
        "launch_id": launch_id,
        "requesting_room": requesting_room,
        "deploy_mode": deploy_mode,
        "approval": {"ref": approval_ref, "plan_hash": plan_hash},
        "handoff_sha256": handoff_sha256,
        "plan": plan,
        "workflows": workflows,
    }


def validate_envelope(envelope, handoff, handoff_sha256):
    """Receiver-mirror validation of a constructed envelope: exact field
    set, draft-only, hash and plan-hash agreement, full form coverage.
    Returns problem lines ([] = acceptable)."""
    problems = []
    if not isinstance(envelope, dict):
        return ["envelope is not an object"]
    unknown = sorted(set(envelope) - set(ENVELOPE_FIELDS))
    if unknown:
        problems.append(f"envelope carries unknown field(s) {unknown}; the "
                        f"receiver accepts exactly the section 3 fields")
    for field in ENVELOPE_FIELDS:
        if field not in envelope:
            problems.append(f"envelope is missing {field}")
    if problems:
        return problems
    if envelope["deploy_mode"] != ONLY_DEPLOY_MODE:
        problems.append(f"deploy_mode must be exactly {ONLY_DEPLOY_MODE!r}, "
                        f"got {envelope['deploy_mode']!r}")
    if envelope["handoff_sha256"] != handoff_sha256:
        problems.append("envelope handoff_sha256 does not match the hand-off "
                        "it dispatches")
    if envelope["location_id"] != handoff.get("location_id"):
        problems.append("envelope location_id does not match the hand-off's "
                        "location_id")
    plan = envelope.get("plan") or {}
    if (envelope.get("approval") or {}).get("plan_hash") != \
            sha256_bytes(canonical_bytes(plan)):
        problems.append("approval.plan_hash does not match the plan it "
                        "approves; a tampered plan is refused")
    covered = set()
    for w in envelope.get("workflows") or []:
        if not isinstance(w, dict):
            problems.append("workflow entry is not an object")
            continue
        if isinstance(w.get("no_workflow_reason"), str) \
                and w["no_workflow_reason"].strip():
            covered.add(w.get("form_id"))
        else:
            covered.add((w.get("origin") or {}).get("form_id"))
    form_ids = {f.get("form_id") for f in handoff.get("forms") or []
                if isinstance(f, dict)}
    if covered != form_ids:
        problems.append(f"envelope workflows cover {sorted(map(str, covered))} "
                        f"but the hand-off's forms are "
                        f"{sorted(map(str, form_ids))}")
    return problems


def emit_handoff(run_dir, *, deploy_mode, requesting_room, env=None):
    """Emit (or verify) the hand-off at ghl-install-test close and build
    the dispatch envelope when the launch wiring inputs are on record.
    Returns (failures, record): failure lines for the gate ([] = the
    close may proceed on this leg) and the emission record written.

    deploy_mode and requesting_room are required keyword arguments, on
    purpose: both are packet section 3 envelope values the caller
    supplies, and neither is ever defaulted here. deploy_mode must be
    exactly "draft-only" (any other value is refused below, and an
    absent one cannot be supplied silently); every call site passes
    the seam's only legal value explicitly, so its origin is visible
    in code."""
    run_dir = Path(run_dir)
    env = os.environ if env is None else env
    if deploy_mode != ONLY_DEPLOY_MODE:
        return [f"stage ghl-install-test: automation dispatch deploy_mode "
                f"must be exactly {ONLY_DEPLOY_MODE!r} in this seam; got "
                f"{deploy_mode!r}. Absent or any other value is refused, "
                f"never defaulted (R71H seam packet section 3)"], None
    intake = load_json(run_dir / "intake.json") or {}
    if intake.get("publish_target") != "ghl":
        return [], None

    expected, problems, sourced, location_problem, record_problems = \
        expected_handoff(run_dir, env)
    hp = run_dir / HANDOFF_REL
    prior = load_json(run_dir / EMISSION_REL) or {}
    failures = []

    current = None
    current_sha = None
    if hp.is_file():
        current_bytes = hp.read_bytes()
        current_sha = sha256_bytes(current_bytes)
        try:
            parsed = json.loads(current_bytes.decode("utf-8"))
            current = parsed if isinstance(parsed, dict) else None
        except Exception:
            current = None
    emitter_owned = bool(prior.get("handoff_origin") == "emitted"
                         and prior.get("handoff_sha256")
                         and prior["handoff_sha256"] == current_sha)

    if current is not None and not emitter_owned:
        # Externally authored hand-off: never overwritten. Verify it
        # against the records; the close refuses on disagreement. If
        # Item 32's record itself is blocked (missing, not_applicable,
        # a form without an ID, no funnel_id), the mandated comparison
        # cannot be performed: fail closed on those, and only those.
        # Fields the records do not source (for example a page_id when
        # the install receipt carries no target block) are not compared.
        failures.extend(f"stage ghl-install-test: {p}" for p in record_problems)
        failures.extend(_agreement_failures(run_dir, current, expected, sourced))
        handoff = current
        handoff_sha = current_sha
    else:
        if problems or location_problem:
            failures.extend(
                f"stage ghl-install-test: {p}"
                for p in problems + ([location_problem] if location_problem
                                     else []))
            return failures, None
        data = serialize(expected)
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_bytes(data)
        handoff = expected
        handoff_sha = sha256_bytes(data)

    if failures:
        return failures, None

    record = {
        "emitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "handoff": HANDOFF_REL,
        "handoff_sha256": handoff_sha,
        "handoff_origin": "emitted" if current is None or emitter_owned
                          else "verified_external",
        "envelope": None,
        "envelope_note": None,
    }
    found, missing = _launch_inputs(run_dir, intake)
    if missing:
        record["envelope_note"] = (
            "dispatch envelope not constructed; the launch wiring inputs "
            "are not on record in this run: " + "; ".join(missing) +
            ". The hand-off and its hash are emitted; the envelope is "
            "constructed when the launch supplies its spec (packet doc 02 "
            "section 7, doc 14 Phase B). Nothing is dispatched by the "
            "emitter.")
    else:
        request_id = prior.get("request_id")
        version = prior.get("request_version")
        if not (isinstance(request_id, str) and REQUEST_ID_RE.match(request_id)
                and isinstance(version, int) and version >= 1):
            request_id = "gxo_" + secrets.token_hex(6)
            version = 0
        try:
            envelope = build_envelope(
                handoff, handoff_sha,
                launch_id=found["launch_id"],
                requesting_room=requesting_room,
                approval_ref=found["approval_ref"],
                folder=found["folder"],
                workflow_specs=found["workflow_specs"],
                deploy_mode=deploy_mode,
                request_id=request_id,
                request_version=version + 1)
        except EnvelopeError as exc:
            return [f"stage ghl-install-test: dispatch envelope refused: {exc}"], None
        problems_env = validate_envelope(envelope, handoff, handoff_sha)
        if problems_env:
            return [f"stage ghl-install-test: dispatch envelope invalid: {p}"
                    for p in problems_env], None
        ep = run_dir / ENVELOPE_REL
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_bytes(serialize(envelope))
        record["envelope"] = ENVELOPE_REL
        record["request_id"] = envelope["request_id"]
        record["request_version"] = envelope["request_version"]
    ep_record = run_dir / EMISSION_REL
    ep_record.parent.mkdir(parents=True, exist_ok=True)
    ep_record.write_bytes(serialize(record))
    return [], record


# ---------------------------------------------------------------------------
# Receipt filing (S71-08 P2): the stage-14 receipt, packet section 4.
#
# The filer validates the outcome record's identity and binding (which
# dispatch it answers, under which hand-off hash) and the presence of
# the per-workflow evidence packet section 4 names; it does not judge
# execution quality (QC exit codes, read-back truth, set-level form and
# trigger coverage) — the gate judges those at automation-wiring close
# (stage_gate.check_automation_wiring). Nothing is written unless
# every filing check passes: a flagged record is refused whole, never
# silently filed.


def _outcome_reason(outcome, block):
    """The verbatim reason of a refusal / failure block, or None."""
    data = outcome.get(block)
    if isinstance(data, dict):
        reason = data.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason
    return None


def _build_method_for(wf, who):
    """Map a workflow's recorded execution provenance to the receipt's
    build_method (packet section 4). Returns (value, problems)."""
    provenance = wf.get("provenance")
    stated = wf.get("build_method")
    mapped = None
    problems = []
    if provenance is not None:
        mapped = PROVENANCE_BUILD_METHODS.get(provenance)
        if mapped is None:
            problems.append(
                f"{who}: execution provenance {provenance!r} is not a "
                f"recorded provenance of this seam (tier 0 caf or the "
                f"Tier 4 browser backstop); the receipt's build_method "
                f"is mapped from it and cannot be derived")
    if stated is not None and stated not in BUILD_METHODS:
        problems.append(
            f"{who}: build_method {stated!r} is not one of "
            f"{list(BUILD_METHODS)} (references/automation-handoff.md)")
        stated = None
    if mapped is not None and stated is not None and mapped != stated:
        problems.append(
            f"{who}: build_method {stated!r} disagrees with the "
            f"build_method {mapped!r} its recorded provenance maps to")
    value = mapped or stated
    if value is None and not problems:
        problems.append(
            f"{who}: no execution provenance (or build_method) is "
            f"recorded; packet section 4 maps the receipt's "
            f"build_method from the execution provenance")
    return value, problems


def _map_workflow(run_dir, wf, index, staged):
    """Map one recorded workflow result to the stage-14 receipt shape
    (packet section 4). Checklist instances are staged for filing
    under automation-wiring/ (appended to `staged` as (src, dest));
    the copy happens only when the whole receipt files. Returns
    (entry, problems)."""
    label = None
    if isinstance(wf, dict):
        label = wf.get("name") or wf.get("workflow_id")
    who = f"outcome workflows[{index}]" + (f" ({label})" if label else "")
    if not isinstance(wf, dict):
        return None, [f"{who} is not an object"]
    problems = []
    workflow_id = wf.get("workflow_id")
    name = wf.get("name")
    if not workflow_id:
        problems.append(f"{who}: records no workflow_id (packet "
                        f"section 4: from the build + export read-back)")
    if not name:
        problems.append(f"{who}: records no name (packet section 4: "
                        f"from the build + export read-back)")
    origin = wf.get("origin") or wf.get("trigger")
    if not isinstance(origin, dict) or origin.get("type") != "form_submitted" \
            or not origin.get("form_id"):
        problems.append(
            f"{who}: the declared origin must be "
            f"{{type: \"form_submitted\", form_id}} (packet section 4: "
            f"the receipt's trigger is the declared origin)")
        origin = None
    mech = wf.get("mechanism")
    mechanism = None
    if not isinstance(mech, dict):
        problems.append(
            f"{who}: records no mechanism alongside the origin; a "
            f"receipt naming only one side is incomplete (packet "
            f"section 4, S44-06 section 1.1)")
    elif mech.get("type") == "contact_tag":
        if not isinstance(mech.get("tag"), str) or not mech["tag"].strip():
            problems.append(
                f"{who}: contact_tag mechanism records no verbatim "
                f"Phase-A tag string")
        else:
            mechanism = {"type": "contact_tag", "tag": mech["tag"]}
    elif mech.get("type") == "native":
        if mech.get("build_method") != "tier4-browser-backstop":
            problems.append(
                f"{who}: native mechanism requires build_method "
                f"\"tier4-browser-backstop\"")
        else:
            mechanism = {"type": "native",
                         "build_method": "tier4-browser-backstop"}
    else:
        problems.append(
            f"{who}: mechanism.type must be \"contact_tag\" or "
            f"\"native\", got {mech.get('type')!r}")
    build_method, bm_problems = _build_method_for(wf, who)
    problems.extend(bm_problems)
    qc_in = wf.get("qc")
    qc = None
    if not isinstance(qc_in, dict):
        problems.append(
            f"{who}: records no QC evidence (packet section 4: "
            f"qc.script, its exit_code, the filled checklist instance, "
            f"checklist_complete, and the WF item count)")
    else:
        if qc_in.get("script") is not None and qc_in["script"] != QC_SCRIPT:
            problems.append(
                f"{who}: qc.script is {qc_in['script']!r}; the "
                f"receipt's QC evidence is Skill 44's {QC_SCRIPT} "
                f"(packet section 4)")
        for key in ("exit_code", "checklist_complete", "wf_items"):
            if key not in qc_in:
                problems.append(f"{who}: QC evidence records no {key} "
                                f"(packet section 4)")
        inst = qc_in.get("checklist_instance")
        filed_inst = None
        if not isinstance(inst, str) or not inst.strip():
            problems.append(
                f"{who}: QC evidence names no filled checklist "
                f"instance; the instance is filed under "
                f"{CHECKLIST_DIR}/ (packet section 4, R71H)")
        else:
            src = run_dir / inst
            if not src.is_file():
                problems.append(
                    f"{who}: checklist instance {inst!r} is not on "
                    f"disk; filing cannot record QC evidence that "
                    f"does not exist")
            else:
                filed_inst = f"{CHECKLIST_DIR}/{Path(inst).name}"
                if inst != filed_inst:
                    dest = run_dir / filed_inst
                    if dest.exists() \
                            and dest.read_bytes() != src.read_bytes():
                        problems.append(
                            f"{who}: {filed_inst} already exists with "
                            f"different bytes; a filed checklist "
                            f"instance is never overwritten")
                    else:
                        staged.append((src, dest))
        if not problems:
            qc = {"script": QC_SCRIPT,
                  "exit_code": qc_in.get("exit_code"),
                  "checklist_instance": filed_inst,
                  "checklist_complete": qc_in.get("checklist_complete"),
                  "wf_items": qc_in.get("wf_items")}
    rb = wf.get("readback")
    readback = None
    if not isinstance(rb, dict) or ("exists" not in rb and "status" not in rb):
        problems.append(
            f"{who}: records no read-back (packet section 4: the "
            f"receiver supplies readback {{exists, status}} per "
            f"workflow; success without a read-back judges UNVERIFIED "
            f"at the gate)")
    else:
        readback = {}
        for key in ("exists", "status"):
            if key in rb:
                readback[key] = rb[key]
    if problems:
        return None, problems
    return {
        "workflow_id": workflow_id,
        "name": name,
        "trigger": {"type": "form_submitted", "form_id": origin["form_id"]},
        "mechanism": mechanism,
        "build_method": build_method,
        "qc": qc,
        "readback": readback,
    }, []


def file_dispatch_receipt(run_dir, outcome):
    """File a recorded dispatch outcome as the stage-14 receipt at
    private/receipts/automation-wiring.json (packet section 4).
    Returns (failures, filed): failure lines ([] = filed) and the
    filed receipt dict (with a "filed" summary) on success.

    The outcome record is the receiving side's return (or an
    operator's record of a refusal or failure), recorded in the run:

        {"outcome": "accepted" | "refused" | "failed",
         "request_id": ..., "request_version": ...,
         "handoff_sha256": ...,            (each optional; when
         recorded, each must match the dispatch of record)
         "refusal": {"code": ..., "reason": "<verbatim>"},   (refused)
         "failure": {"code": ..., "reason": "<verbatim>"},   (failed)
         "workflows": [ {workflow_id, name, origin|trigger,
                          mechanism, provenance|build_method,
                          qc {exit_code, checklist_instance,
                              checklist_complete, wf_items},
                          readback {exists, status}} ],      (accepted)
         "form_exceptions": [{"form_id": ..., "no_workflow_reason": ...}],
         "conversational": [...], "conversational_overrides": [...],
         "conversational_not_present": [...], "ghl_pack_version": ...,
         "author_agent": ..., "author_session": ...,
         "started_at": ..., "finished_at": ...}

    Fields the outcome does not record are not invented: form
    exceptions default to the dispatch envelope's exception entries
    (the dispatch of record), and every other receipt field comes
    from the outcome itself or the envelope/state binding below."""
    run_dir = Path(run_dir)
    if not isinstance(outcome, dict):
        return ["the dispatch outcome record is not a JSON object; "
                "nothing was filed"], None
    intake = load_json(run_dir / "intake.json") or {}
    if intake.get("publish_target") != "ghl" \
            or intake.get("automation_scope") != "workflows":
        return [f"receipt filing refused: automation-wiring does not "
                f"run in this run (intake.publish_target="
                f"{intake.get('publish_target')!r}, "
                f"intake.automation_scope="
                f"{intake.get('automation_scope')!r}); the stage is "
                f"required only when publish_target is \"ghl\" and "
                f"automation_scope is \"workflows\" (fix plan Item 31)"], None
    state = load_json(run_dir / STATE_REL)
    if state is None:
        return [f"receipt filing refused: {STATE_REL} is missing or "
                f"unreadable; the receipt binds to the state the gate "
                f"locked at ghl-install-test close"], None
    stage_state = (state.get("stages") or {}).get("automation-wiring") or {}
    if stage_state.get("status") == "closed":
        return ["receipt filing refused: stage automation-wiring is "
                "already closed in state; a closed stage's receipt is "
                "not refiled"], None
    locked = (state.get("stages", {}).get("ghl-install-test") or {}) \
        .get("handoff_sha256")
    if not isinstance(locked, str) or not SHA256_RE.match(locked):
        return ["receipt filing refused: no hand-off hash is locked "
                "in state (stages.ghl-install-test.handoff_sha256 is "
                "absent); the stage-14 receipt echoes the hash locked "
                "at ghl-install-test close and cannot be filed unbound "
                "(R71H seam packet section 2, step 2)"], None
    envelope = load_json(run_dir / ENVELOPE_REL)
    if envelope is None:
        return [f"receipt filing refused: no dispatch envelope is on "
                f"record ({ENVELOPE_REL}); a dispatch outcome answers "
                f"a dispatch, and this seam dispatches only the "
                f"constructed envelope (packet section 3)"], None
    env_hash = envelope.get("handoff_sha256")
    if env_hash != locked:
        return [f"receipt filing refused: the dispatch envelope's "
                f"handoff_sha256 {env_hash!r} does not equal the hash "
                f"locked in state at ghl-install-test close {locked}; "
                f"the dispatch was made under a different hand-off "
                f"than the locked one, and its outcome is not filed "
                f"against this run's locked hand-off"], None
    failures = []
    out_hash = outcome.get("handoff_sha256")
    if out_hash is not None and out_hash != locked:
        failures.append(
            f"receipt filing refused: the outcome's handoff_sha256 "
            f"{out_hash} does not equal the hash locked in state at "
            f"ghl-install-test close {locked}; a receipt that "
            f"disagrees with the locked hash is flagged, never "
            f"silently filed (packet section 2, step 2)")
    env_rid = envelope.get("request_id")
    env_ver = envelope.get("request_version")
    if not (isinstance(env_rid, str) and REQUEST_ID_RE.match(env_rid)
            and isinstance(env_ver, int) and env_ver >= 1):
        failures.append(
            f"receipt filing refused: the dispatch envelope on "
            f"record carries no valid request_id / request_version "
            f"to bind the receipt to")
    out_rid = outcome.get("request_id")
    if out_rid is not None and out_rid != env_rid:
        failures.append(
            f"receipt filing refused: the outcome's request_id "
            f"{out_rid!r} does not match the dispatched envelope's "
            f"{env_rid!r}; the receipt answers the dispatch of record")
    out_ver = outcome.get("request_version")
    if out_ver is not None and out_ver != env_ver:
        failures.append(
            f"receipt filing refused: the outcome's request_version "
            f"{out_ver!r} does not match the dispatched envelope's "
            f"{env_ver!r}; a redispatch is a new version and its "
            f"outcome is filed against it, not against this one")
    if failures:
        return failures, None

    kind = outcome.get("outcome")
    if kind not in OUTCOMES:
        return [f"receipt filing refused: outcome must be one of "
                f"{list(OUTCOMES)}, got {kind!r}; an acceptance, a "
                f"refusal, or a failure is recorded (packet section 4: "
                f"refusals are receipts too)"], None

    receipt = {"stage": "automation-wiring", "outcome": kind,
               "request_id": env_rid, "request_version": env_ver,
               "handoff_sha256": locked}
    for key in ("author_agent", "author_session", "started_at",
                "finished_at"):
        if outcome.get(key) is not None:
            receipt[key] = outcome[key]
    staged = []
    if kind == "accepted":
        receipt["status"] = "pass"
        workflows_in = outcome.get("workflows")
        if not isinstance(workflows_in, list):
            return ["receipt filing refused: an accepted outcome "
                    "records the per-workflow results (packet "
                    "section 4); \"workflows\" is not a list"], None
        workflows = []
        for i, wf in enumerate(workflows_in):
            entry, problems = _map_workflow(run_dir, wf, i, staged)
            if problems:
                failures.extend(problems)
            else:
                workflows.append(entry)
        exceptions = None
        if outcome.get("form_exceptions") is not None:
            exceptions = []
            for e in outcome["form_exceptions"]:
                if isinstance(e, dict) and e.get("form_id") \
                        and isinstance(e.get("no_workflow_reason"), str) \
                        and e["no_workflow_reason"].strip():
                    exceptions.append(
                        {"form_id": e["form_id"],
                         "no_workflow_reason": e["no_workflow_reason"]})
                else:
                    failures.append(
                        "receipt filing refused: a form exception "
                        "must carry form_id and a non-empty "
                        "no_workflow_reason (R71H gate rule)")
        else:
            exceptions = [
                {"form_id": w["form_id"],
                 "no_workflow_reason": w["no_workflow_reason"]}
                for w in envelope.get("workflows") or []
                if isinstance(w, dict)
                and isinstance(w.get("no_workflow_reason"), str)
                and w["no_workflow_reason"].strip()]
        for key in ("conversational", "conversational_overrides",
                    "conversational_not_present"):
            if outcome.get(key) is not None \
                    and not isinstance(outcome[key], list):
                failures.append(
                    f"receipt filing refused: the outcome's {key} is "
                    f"not a list")
        if failures:
            return failures, None
        receipt["workflows"] = workflows
        receipt["form_exceptions"] = exceptions
        receipt["conversational"] = outcome.get("conversational") or []
        if outcome.get("conversational_overrides") is not None:
            receipt["conversational_overrides"] = \
                outcome["conversational_overrides"]
        if outcome.get("conversational_not_present") is not None:
            receipt["conversational_not_present"] = \
                outcome["conversational_not_present"]
        if outcome.get("ghl_pack_version"):
            receipt["ghl_pack_version"] = outcome["ghl_pack_version"]
    elif kind == "refused":
        reason = _outcome_reason(outcome, "refusal")
        if reason is None:
            return ["receipt filing refused: a refused outcome "
                    "records the refusal reason verbatim "
                    "(refusal.reason); a refusal without its reason "
                    "is not a receipt (packet section 4)"], None
        receipt["status"] = "blocked"
        refusal = {"reason": reason}
        code = (outcome.get("refusal") or {}).get("code")
        if isinstance(code, str) and code.strip():
            refusal["code"] = code
        receipt["dispatch_refusal"] = refusal
    else:  # failed
        reason = _outcome_reason(outcome, "failure")
        if reason is None:
            return ["receipt filing refused: a failed outcome "
                    "records the failure reason verbatim "
                    "(failure.reason)"], None
        receipt["status"] = "fail"
        failure = {"reason": reason}
        code = (outcome.get("failure") or {}).get("code")
        if isinstance(code, str) and code.strip():
            failure["code"] = code
        receipt["dispatch_failure"] = failure

    for src, dest in staged:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(src.read_bytes())
    rp = run_dir / RECEIPT_REL
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_bytes(serialize(receipt))
    filed = dict(receipt)
    filed["filed"] = {"receipt": RECEIPT_REL,
                      "checklists": sorted(
                          {f"{CHECKLIST_DIR}/{dest.name}"
                           for _src, dest in staged})}
    return [], filed


USAGE = ("usage: automation_handoff.py <run_dir> --deploy-mode draft-only\n"
         "       automation_handoff.py <run_dir> --outcome <outcome.json>")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    deploy_mode = None
    outcome_path = None
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--deploy-mode":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            deploy_mode = argv[i + 1]
            i += 2
        elif argv[i] == "--outcome":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            outcome_path = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if len(args) != 1 or (deploy_mode is None and outcome_path is None) \
            or (deploy_mode is not None and outcome_path is not None):
        # --deploy-mode is a required flag in emit mode: the seam's
        # only legal value must be named on the command line, never
        # defaulted (packet section 3). Omitting it is a usage error
        # and nothing emits. --outcome selects receipt-filing mode
        # instead; the two modes are distinct acts and are not mixed.
        print(USAGE)
        return 2
    run_dir = Path(args[0]).resolve()
    if not run_dir.is_dir():
        print(f"FAIL: run_dir does not exist: {run_dir}")
        return 2
    if outcome_path is not None:
        try:
            outcome = json.loads(
                Path(outcome_path).read_text(encoding="utf-8"))
        except Exception as exc:
            print("FAIL")
            print(f"- the dispatch outcome record {outcome_path} is "
                  f"unreadable: {exc}; nothing was filed")
            return 1
        failures, filed = file_dispatch_receipt(run_dir, outcome)
        if failures:
            print("FAIL")
            for line in failures:
                print(f"- {line}")
            return 1
        print(f"FILED: {RECEIPT_REL} (outcome {filed['outcome']}, "
              f"request {filed['request_id']} version "
              f"{filed['request_version']}, handoff_sha256 "
              f"{filed['handoff_sha256']})")
        for rel in filed["filed"]["checklists"]:
            print(f"FILED: {rel} (filled checklist instance)")
        return 0
    failures, record = emit_handoff(run_dir, deploy_mode=deploy_mode,
                                    requesting_room="S71")
    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    if record is None:
        print("NOT APPLICABLE: intake.publish_target is not \"ghl\"; "
              "no automation hand-off is emitted")
        return 0
    print(f"EMITTED: {HANDOFF_REL} sha256 {record['handoff_sha256']}")
    if record.get("envelope"):
        print(f"ENVELOPE: {record['envelope']} request "
              f"{record['request_id']} version {record['request_version']} "
              f"(artifact only; nothing dispatched)")
    else:
        print(f"ENVELOPE: not constructed ({record.get('envelope_note')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
