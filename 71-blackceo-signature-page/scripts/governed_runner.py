#!/usr/bin/env python3
"""governed_runner.py - the runner's admission caller (F14 items 1, 2, 3, 5, 7, 8, 9, 11).

WHY THIS EXISTS
---------------
LND-001 landed the admission CONTRACT (shared-utils/signature_launch/admission.py):
identity, evidence, verify_evidence, is_complete, require_units, denominator,
delivered, invalidate, admit_entry, done_standard. This module does NOT rebuild
any of that. It is the caller that makes the contract reachable from the one
Skill 71 runner and from Skill 49's dispatch seam.

WHAT IT ADDS, ITEM BY ITEM
--------------------------
1.  work_plan()          an executable work plan generated from the approved
                         launch (optional) and the canonical stage definitions
                         (references/stage-contract.json): contract version, run
                         identity, allowed operation, inputs, expected outputs,
                         prerequisites and the completion predicate, all bound and
                         hashed. Free-form "build and report" is not a plan.
2.  admit()              ONE admission call with an explicit entry kind, used by
                         initial launch, resume, scheduled checkpoint, delegated
                         worker, direct supported executor, installation,
                         publishing and the Complete transition.
3.  admit()               the existing stage gate `check` / `check-item` runs
                         BEFORE governed work begins, so an earlier unauthorised
                         paid call is refused before it is made, not after a
                         later package check.
4.  scan()               the out-of-pipeline detector (out_of_pipeline.py), which
                         compares exact normalised paths and content hashes.
5.  register_output()    legitimate in-progress outputs are registered before the
                         producer writes them.
6.  delivery()            unadmitted output is unverified and excluded from
                         delivery, progress credit, installation and publication.
7.  admit_authoring()    copy/prompt/map authoring is registered work whose output
                         is validated before the canonical stage is closed.
8.  canonical_entry_instructions()  resolved ONCE and injected into delegated and
                         scheduled work; it states that completion is evidence, not
                         file existence, and that a worker MUST read its declared
                         dependencies (this overrides conflicting general runner
                         guidance).
9.  blocked()            a blocked unit yields a concrete blocker and independent
                         work continues; an ungoverned alternative draft is refused
                         and quarantined instead of filling the progress report.
11. admit_conversation()  conditional conversational work is admitted only against
                         the selected mode's actual dependencies and authority; a
                         page-only launch never needs an unselected feature.

THE ENFORCEABLE GUARANTEE (F14 "Important limit")
-------------------------------------------------
A periodic scan alone cannot stop an agent that also bypasses the scan. What this
module guarantees is mandatory admission at the execution and acceptance
boundaries the system controls: paid dispatch, installation, publication and the
Complete transition. Those four refuse on a failed stage check, on ungoverned
output, and (for Complete) on unverified evidence. Preview and local placeholder
work is admitted and recorded but can never claim production completion.

Stdlib only. No network. No credentials. No execution of client work.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REPO_ROOT = HERE.parents[1]
SKILL = 71

SCHEMA = "signature-launch-runner/v1"
ENTRY_KINDS = ("entry", "resume", "checkpoint", "delegation", "direct_executor",
               "installation", "publishing", "complete")
# The boundaries under system control that REFUSE (F14 "Important limit").
AUTHORITATIVE_AUTHORITIES = ("paid_dispatch", "installation", "publishing", "complete")
AUTHORITIES = ("preview", "local") + AUTHORITATIVE_AUTHORITIES

# Preview composes and validates prompts and calls no provider; local writes
# placeholder bytes. Neither can ever be a production completion.
NON_PRODUCTION = ("preview", "local")

CONTRACT_PATH = SKILL_ROOT / "references" / "stage-contract.json"
GATE_PATH = SKILL_ROOT / "scripts" / "stage_gate.py"
WORK_PLAN_FILE = "private/run-work-plan.json"
GOVERNOR_FILE = "private/governor.json"
INSTRUCTIONS_FILE = "private/canonical-entry-instructions.json"

# The operation each canonical stage permits. Derived from the stage names in
# references/stage-contract.json -- never a second stage taxonomy.
STAGE_OPERATIONS = {
    "intake": "author",
    "copy": "author",
    "font-action-plan": "author",
    "desktop-wireframe": "generate",
    "mobile-tablet": "generate",
    "visual-mockup": "generate",
    "image-inventory-prompts": "author",
    "image-generation-qc": "generate",
    "image-map-upload": "publish_asset",
    "design-board": "generate",
    "final-mockups": "generate",
    "responsive-html": "author",
    "ghl-install-test": "install",
    "publish-verify": "publish",
    "automation-wiring": "wire",
}

# Where each governed stage's outputs land. A location, not a claim: the
# completion predicate still requires verified evidence with real hashes.
STAGE_OUTPUTS = {
    "desktop-wireframe": ["desktop-wireframe/", "review-pdfs/"],
    "mobile-tablet": ["mobile-tablet/", "review-pdfs/"],
    "visual-mockup": ["visual-mockup/", "review-pdfs/"],
    "final-mockups": ["final-mockups/", "review-pdfs/"],
    "design-board": ["design-board/"],
    "image-generation-qc": ["image-generation-qc/"],
    "responsive-html": ["site/"],
    "image-map-upload": ["image-map.json"],
}

# Files a stage consumes when they exist in the run; hashed into the work plan.
STAGE_INPUTS = ("intake.json", "page-request.json", "launch.json", "brand.json",
                "copy/internal-manuscript.md", "copy.json")


class AdmissionRefused(ValueError):
    """A fail-closed refusal carrying the concrete reason and its source."""

    def __init__(self, reason, *, kind=None, stage=None, source=None, detail=None,
                 decision=None):
        super().__init__(reason)
        self.decision = dict(decision) if decision else {
            "admitted": False, "reason": reason, "kind": kind, "stage": stage,
            "source": source, "detail": detail or []}
        self.decision.setdefault("admitted", False)
        self.decision.setdefault("reason", reason)


def _load(name, path, module_name):
    if not path.is_file():
        raise AdmissionRefused("%s is missing at %s" % (name, path), source="governed_runner")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission():
    """The one admission/completion service. Consumed, never reimplemented."""
    return _load("admission.py", REPO_ROOT / "shared-utils" / "signature_launch" / "admission.py",
                 "signature_launch_governed_admission")


def detector():
    return _load("out_of_pipeline.py", HERE / "out_of_pipeline.py",
                 "signature_launch_governed_out_of_pipeline")


def stage_contract():
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdmissionRefused("stage contract is unreadable: %s" % exc,
                               source="stage-contract.json")
    if not isinstance(contract, dict) or not contract.get("stage_order"):
        raise AdmissionRefused("stage contract declares no canonical stage order",
                               source="stage-contract.json")
    return contract


def canonical_order():
    return list(stage_contract()["stage_order"])


def stage_definition(stage):
    definition = stage_contract()["stages"].get(stage)
    if definition is None:
        raise AdmissionRefused(
            "stage %r is not a canonical stage; the contract has: %s"
            % (stage, ", ".join(canonical_order())), stage=stage, source="stage-contract.json")
    return definition


# --------------------------------------------------------------------------
# item 1 - the executable work plan
# --------------------------------------------------------------------------

def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_facts(run_dir):
    """Run identity facts taken from the run's own canonical documents.

    `installation` is derived from the launch location when the launch context
    was imported, else from the run directory name; it is never invented from a
    human-friendly launch name.
    """
    base = Path(run_dir).resolve()
    intake = _read_json(base / "intake.json")
    launch = _read_json(base / "launch.json")
    tenant = str(launch.get("tenant_id") or intake.get("tenant_id") or "").strip()
    location = str(launch.get("location_id") or intake.get("location_id") or "").strip()
    launch_id = str(launch.get("launch_id") or intake.get("launch_id") or base.name).strip()
    return {
        "run_dir": str(base),
        "tenant": tenant or "run:" + base.name,
        "installation": location or "run:" + base.name,
        "launch_id": launch_id,
        "page_key": str(intake.get("page_kind") or intake.get("copy_version") or "page").strip(),
        "copy_profile": str(intake.get("copy_version") or "").strip() or None,
        "page_kind": str(intake.get("page_kind") or "").strip() or None,
    }


def _declared_inputs(run_dir, extra=None):
    base = Path(run_dir).resolve()
    found = {}
    for rel in STAGE_INPUTS:
        target = base / rel
        if target.is_file():
            found[rel] = "sha256:" + _sha256_file(target)
    for rel, digest in (extra or {}).items():
        found[str(rel)] = digest if str(digest).startswith("sha256:") else "sha256:" + str(digest)
    return found


def work_plan(run_dir, *, plan=None, unit_id=None, stages=None, inputs=None,
              approved_plan_hash=None):
    """The runner's executable work plan (item 1).

    With an approved launch plan, the unit set and its dependencies come from
    ``admission.required_units`` / ``admission.admit_entry``. Without one the
    plan covers the canonical stage sequence of this single page run. Either way
    every item binds the nine things F14 names: contract version, run identity,
    allowed operation, inputs, expected outputs, prerequisites and the completion
    predicate.
    """
    run = run_facts(run_dir)
    contract = stage_contract()
    order = list(contract["stage_order"])
    chosen = [s for s in (stages or order) if s in order]
    unknown = [s for s in (stages or []) if s not in order]
    if unknown:
        raise AdmissionRefused("work plan names non-canonical stage(s): %s"
                               % ", ".join(sorted(unknown)), source="stage-contract.json")
    if not chosen:
        raise AdmissionRefused("work plan has no stage to run", source="stage-contract.json")

    service = admission()
    declared_inputs = _declared_inputs(run_dir, inputs)
    if not declared_inputs:
        raise AdmissionRefused(
            "no declared input exists in %s; a work plan binds the inputs it reads"
            % run["run_dir"], source="work-plan")

    unit_rows = {}
    plan_units = None
    if plan is not None:
        plan_units = service.required_units(plan)
        if unit_id is not None and unit_id not in {u["id"] for u in plan_units}:
            raise AdmissionRefused("unit %r is not in the approved plan" % unit_id,
                                   source="plan")
        for row in plan_units:
            unit_rows[row["id"]] = row
        chosen_unit = next((u for u in plan_units
                            if u["kind"] == "page" and (unit_id is None or u["id"] == unit_id)),
                           plan_units[0])
    else:
        chosen_unit = {"id": unit_id or "page:%s" % run["page_key"], "kind": "page",
                       "waits_for": []}

    plan_hash_value = (
        "sha256:" + approved_plan_hash if approved_plan_hash else None)
    if plan_hash_value is None and plan is not None:
        plan_hash_value = service._plan_hash_of(plan)
    if plan_hash_value is None:
        # No approved launch plan: the run's plan surrogate binds the canonical
        # stage contract version, the chosen stage order and the run identity.
        plan_hash_value = service.sha256_text(service.canonical({
            "schema": SCHEMA,
            "contract_version": service.CONTRACT_VERSION,
            "run": {k: run[k] for k in ("tenant", "installation", "launch_id")},
            "page_key": run["page_key"],
            "stages": chosen,
        }))

    ident = service.identity(
        tenant=run["tenant"], installation=run["installation"], skill=SKILL,
        launch_id=run["launch_id"], plan_revision=str(approved_plan_hash or "1"),
        plan_hash=plan_hash_value, unit_id=chosen_unit["id"],
        unit_kind=chosen_unit["kind"], contract_version=service.CONTRACT_VERSION,
        page_key=run["page_key"])

    predicate = service.completion_predicate()
    items = []
    previous = None
    for stage in order:
        if stage not in chosen:
            continue
        definition = contract["stages"][stage]
        prerequisites = []
        if previous is not None:
            prerequisites.append({"stage": previous, "requires": "closed"})
        for dependency in chosen_unit.get("waits_for") or []:
            row = unit_rows.get(dependency)
            if row and row.get("kind") == "page":
                prerequisites.append({"unit": dependency, "requires": "verified_complete"})
        items.append({
            "unit": chosen_unit["id"],
            "stage": stage,
            "operation": STAGE_OPERATIONS.get(stage, "author"),
            "itemized": bool(definition.get("itemized")),
            "inputs": dict(sorted(declared_inputs.items())),
            "expected_outputs": list(STAGE_OUTPUTS.get(stage, [])),
            "prerequisites": prerequisites,
            "completion_predicate": predicate,
            "contract_version": service.CONTRACT_VERSION,
        })
        previous = stage

    plan_doc = {
        "schema": SCHEMA,
        "contract_version": service.CONTRACT_VERSION,
        "identity": ident,
        "run": run,
        "approved_plan_hash": plan_hash_value,
        "stage_contract": str(CONTRACT_PATH),
        "stage_order": chosen,
        "denominator": (service.denominator(plan) if plan is not None else None),
        "items": items,
    }
    plan_doc["work_plan_hash"] = service.sha256_text(service.canonical(
        {k: v for k, v in plan_doc.items() if k != "denominator"}))
    return plan_doc


def write_work_plan(run_dir, **kwargs):
    doc = work_plan(run_dir, **kwargs)
    path = Path(run_dir).resolve() / WORK_PLAN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc, path


# --------------------------------------------------------------------------
# item 3 - the existing stage gate, before governed work begins
# --------------------------------------------------------------------------

def _gate(run_dir, *args):
    argv = [sys.executable, str(GATE_PATH), *[str(a) for a in args], str(Path(run_dir).resolve())]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800.0)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), argv
    except TypeError:
        # A harness may patch subprocess.run with a positional-only callable. The
        # stage check still runs; its exit code is still the verdict.
        try:
            proc = subprocess.run(argv)
        except Exception as exc:  # noqa: BLE001 - any failure is a refusal to run
            return 2, "stage gate could not run: %s" % exc, argv
        code = getattr(proc, "returncode", 1)
        return int(code if code is not None else 1), "", argv
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, "stage gate could not run: %s" % exc, argv


def stage_check(run_dir, stage, item=None):
    """Run the existing `check` / `check-item`. Returns (rc, output, argv)."""
    definition = stage_definition(stage)
    if item is not None and definition.get("itemized"):
        return _gate(run_dir, "check-item", stage, item)
    return _gate(run_dir, "check", stage)


def close_canonical_stage(run_dir, stage, item=None):
    """Close through the existing gate (item 7: close the canonical stage)."""
    definition = stage_definition(stage)
    if item is not None and definition.get("itemized"):
        return _gate(run_dir, "close-item", stage, item)
    return _gate(run_dir, "close", stage)


# --------------------------------------------------------------------------
# item 2 - one admission call for every entry
# --------------------------------------------------------------------------

def _governor(run_dir):
    path = Path(run_dir).resolve() / GOVERNOR_FILE
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("units"), dict):
            return data, path
    return {"schema": SCHEMA, "admitted": [], "refused": [], "units": {}}, path


def _save_governor(run_dir, record):
    path = Path(run_dir).resolve() / GOVERNOR_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _record_decision(run_dir, decision):
    record, path = _governor(run_dir)
    bucket = "admitted" if decision.get("admitted") else "refused"
    record[bucket].append(decision)
    record["decision_count"] = len(record["admitted"]) + len(record["refused"])
    _save_governor(run_dir, record)
    return decision


def record_entry(run_dir, *, kind, authority, owner="runner", stage=None, item=None):
    """Record an entry decision before the run's canonical inputs exist.

    A landing run is admitted the moment its root is created: the request, launch
    record and brand are staged next, and the intake is written by the pipeline.
    Requiring a finished work plan at that instant would refuse the pipeline's own
    first step. This records the decision (run key, contract version, scope) and
    says plainly that the executable work plan is generated when the canonical
    inputs exist. The authoritative boundaries (paid dispatch, install, publish,
    complete) still go through ``admit`` and still refuse.
    """
    if kind not in ENTRY_KINDS:
        raise AdmissionRefused("unknown entry kind %r" % kind, kind=kind)
    if authority not in AUTHORITIES:
        raise AdmissionRefused("unknown authority %r" % authority, kind=kind)
    base = Path(run_dir).resolve()
    if not base.is_dir():
        raise AdmissionRefused("run root does not exist: %s" % base, kind=kind)
    if stage is not None:
        stage_definition(stage)
    if authority in AUTHORITATIVE_AUTHORITIES:
        return admit(base, kind=kind, authority=authority, owner=owner,
                     stage=stage, item=item)
    service = admission()
    run = run_facts(base)
    ident = service.identity(
        tenant=run["tenant"], installation=run["installation"], skill=SKILL,
        launch_id=run["launch_id"], plan_revision="1",
        plan_hash=service.sha256_text(service.canonical(
            {"schema": SCHEMA, "run": {k: run[k] for k in
                                       ("tenant", "installation", "launch_id")}})),
        unit_id="page:%s" % run["page_key"], unit_kind="page",
        contract_version=service.CONTRACT_VERSION)
    decision = {
        "schema": SCHEMA, "kind": kind, "authority": authority, "owner": owner,
        "stage": stage, "item": item, "admitted": True,
        "production_completion": False, "contract_version": service.CONTRACT_VERSION,
        "run_key": ident["run_key"], "work_plan_hash": None,
        "reason": "entry recorded; the executable work plan is generated when the "
                  "run's canonical inputs exist",
    }
    _record_decision(base, decision)
    return decision


def admit(run_dir, *, kind, authority, owner="runner", stage=None, item=None,
          plan=None, unit=None, stages=None):
    """The one governed entry admission (item 2).

    `kind` names the entry that is being gated; `authority` says what the caller
    is about to be allowed to do. Preview and local work is recorded and can never
    claim production completion; paid dispatch, installation, publication and
    Complete REFUSE on a failed stage check, on ungoverned output, and -- for
    Complete -- on unverified evidence.
    """
    if kind not in ENTRY_KINDS:
        raise AdmissionRefused("unknown entry kind %r; expected one of %s"
                               % (kind, ", ".join(ENTRY_KINDS)), kind=kind)
    if authority not in AUTHORITIES:
        raise AdmissionRefused("unknown authority %r; expected one of %s"
                               % (authority, ", ".join(AUTHORITIES)), kind=kind)
    base = Path(run_dir).resolve()
    if not base.is_dir():
        raise AdmissionRefused("run root does not exist: %s" % base, kind=kind)

    service = admission()
    decision = {
        "schema": SCHEMA, "kind": kind, "authority": authority, "owner": owner,
        "stage": stage, "item": item, "unit": unit, "admitted": False,
        "production_completion": False,
        "contract_version": service.CONTRACT_VERSION,
    }
    plan_doc = work_plan(base, plan=plan, unit_id=unit, stages=stages)
    decision["work_plan_hash"] = plan_doc["work_plan_hash"]
    decision["run_key"] = plan_doc["identity"]["run_key"]
    if stage is not None:
        stage_definition(stage)  # a non-canonical stage is a refusal by name

    # --- unit-level dependencies, delegated to the contract -----------------
    if plan is not None:
        record, _path = _governor(base)
        for row in service.required_units(plan):
            unit_record = record["units"].get(row["id"]) or {
                "state": "pending", "waits_for": row["waits_for"], "verified": False,
                "attempts": 0}
            unit_record["waits_for"] = row["waits_for"]
            record["units"][row["id"]] = unit_record
        _save_governor(base, record)
        target = unit or plan_doc["identity"]["unit_id"]
        verdict = service.admit_entry(record, target, owner)
        decision["resumable_status"] = verdict.get("resumable_status")
        if not verdict.get("admitted"):
            decision["reason"] = verdict.get("reason")
            decision["source"] = "admission.admit_entry"
            _record_decision(base, decision)
            raise AdmissionRefused(verdict.get("reason") or "unit not admitted",
                                   kind=kind, stage=stage, source="admission.admit_entry",
                                   detail=[verdict], decision=decision)
        decision["attempt"] = verdict.get("attempt")

    # --- out-of-pipeline output is refused at an authoritative boundary ------
    scan_result = scan(base)
    decision["out_of_pipeline"] = {
        "ok": scan_result["ok"],
        "ungoverned": [e["path"] for e in scan_result["ungoverned"]],
        "registered_unfinished": [e["path"] for e in scan_result["registered_unfinished"]],
        "content_mismatch": [e["path"] for e in scan_result["content_mismatch"]],
    }

    # --- item 3: the existing stage check, before governed work begins ------
    if stage is not None:
        rc, output, argv = stage_check(base, stage, item)
        decision["stage_check"] = {"command": argv, "exit": rc,
                                   "output": output.strip()[:2000]}
        if authority in AUTHORITATIVE_AUTHORITIES and rc != 0:
            decision["reason"] = ("the canonical stage check refused stage %r (exit %d)"
                                 % (stage, rc))
            decision["source"] = "stage_gate"
            _record_decision(base, decision)
            raise AdmissionRefused(decision["reason"], kind=kind, stage=stage,
                                   source="stage_gate", detail=[output.strip()[:2000]],
                                   decision=decision)

    if authority in AUTHORITATIVE_AUTHORITIES and not scan_result["ok"]:
        names = [e["path"] for e in scan_result["ungoverned"] + scan_result["content_mismatch"]]
        decision["reason"] = ("out-of-pipeline output is present and cannot be admitted "
                              "for %s: %s" % (authority, ", ".join(names)))
        decision["source"] = "out_of_pipeline"
        _record_decision(base, decision)
        raise AdmissionRefused(decision["reason"], kind=kind, stage=stage,
                               source="out_of_pipeline", detail=names, decision=decision)

    decision["admitted"] = True
    decision["production_completion"] = False
    decision["reason"] = ("admitted for %s (%s)" % (kind, authority))
    _record_decision(base, decision)
    return decision


def complete(run_dir, *, evidence, unit=None, require_review=False, **kwargs):
    """The Complete transition (item 2 + item 6).

    A stage is complete only when the contract's `verify_evidence` accepts real
    evidence for this unit and plan. A nonempty file, a zero exit or a declared
    status never gets here.
    """
    service = admission()
    plan_doc = work_plan(run_dir, **{k: v for k, v in kwargs.items()
                                     if k in ("plan", "unit_id", "stages", "inputs")})
    ident = plan_doc["identity"]
    verdict = service.verify_evidence(
        evidence, identity_facts=ident, require_review=require_review,
        unit=unit or ident["unit_id"], plan_hash=plan_doc["approved_plan_hash"])
    if not verdict.get("ok"):
        raise AdmissionRefused(
            "the Complete transition needs verified evidence: %s"
            % "; ".join(verdict.get("reasons") or ["evidence was not accepted"]),
            kind="complete", source="admission.verify_evidence", detail=verdict.get("reasons"))
    decision = admit(run_dir, kind="complete", authority="complete",
                     unit=unit or ident["unit_id"],
                     **{k: v for k, v in kwargs.items()
                        if k in ("plan", "stages")})
    decision["evidence"] = verdict
    decision["production_completion"] = True
    return decision


# --------------------------------------------------------------------------
# items 5, 6 - registration and quarantined output
# --------------------------------------------------------------------------

def register_output(run_dir, path, *, stage, item=None, expected_sha256=None,
                    producer=None):
    return detector().register(run_dir, path, stage=stage, item=item,
                               expected_sha256=expected_sha256, producer=producer)


def close_output(run_dir, path, *, stage, sha256=None):
    return detector().close(run_dir, path, stage=stage, sha256=sha256)


def _declared_input_paths(run_dir):
    base = Path(run_dir).resolve()
    return tuple(rel for rel in STAGE_INPUTS if (base / rel).is_file())


def scan(run_dir, *, receipts=None, declared_native=None, inputs=None):
    base = Path(run_dir).resolve()
    return detector().scan(base, receipts=receipts, declared_native=declared_native,
                           inputs=_declared_input_paths(base) if inputs is None else inputs)


def delivery(run_dir, artifacts, *, receipts=None):
    """Item 6: unadmitted output is unverified and excluded; nothing is deleted."""
    result = scan(run_dir, receipts=receipts)
    split = detector().delivery(artifacts, result)
    split["scan_ok"] = result["ok"]
    split["ungoverned"] = [e["path"] for e in result["ungoverned"]]
    split["content_mismatch"] = [e["path"] for e in result["content_mismatch"]]
    return split


# --------------------------------------------------------------------------
# item 7 - authoring is governed work
# --------------------------------------------------------------------------

def admit_authoring(run_dir, *, kind, stage, item=None, output=None,
                    expected_sha256=None, validate=None):
    """Register authoring work, validate its output, close the canonical stage.

    `kind` is the authoring operation (`copy`, `prompt`, `map`, `plan`). A ban on
    hand-authoring must not make legitimate pipeline authoring impossible: the
    authoring is registered, its output is validated, and the gate closes it.
    """
    if kind not in ("copy", "prompt", "map", "plan"):
        raise AdmissionRefused("unknown authoring kind %r" % kind, kind="direct_executor",
                               stage=stage)
    base = Path(run_dir).resolve()
    decision = admit(base, kind="direct_executor",
                     authority="local", stage=stage, item=item)
    if output is None:
        decision["authoring"] = {"kind": kind, "registered": False,
                                 "note": "no output named; nothing to register"}
        return decision
    entry = register_output(base, output, stage=stage, item=item,
                            expected_sha256=expected_sha256, producer="authoring:%s" % kind)
    target = base / entry["path"]
    verdict = {"validated": False, "kind": kind, "path": entry["path"]}
    if target.is_file():
        raw = target.read_bytes()
        verdict["bytes"] = len(raw)
        if validate is None:
            verdict["validated"] = len(raw) > 0
        else:
            verdict["validated"] = bool(validate(raw))
    if not verdict["validated"]:
        raise AdmissionRefused(
            "authoring output %s did not validate; the canonical stage is not closed"
            % entry["path"], kind="direct_executor", stage=stage, source="authoring",
            detail=[verdict])
    decision["authoring"] = verdict
    if expected_sha256 or target.is_file():
        close_output(base, entry["path"], stage=stage)
    rc, output_text, argv = close_canonical_stage(base, stage, item)
    decision["authoring"]["close"] = {"command": argv, "exit": rc,
                                      "output": output_text.strip()[:1200]}
    return decision


# --------------------------------------------------------------------------
# item 8 - one set of canonical entry instructions
# --------------------------------------------------------------------------

def canonical_entry_instructions(run_dir, stages=None):
    """Resolve the entry instructions ONCE and persist them for injection.

    This replaces the conflicting general runner guidance: completion is evidence
    rather than file existence, and a worker MUST read the dependencies the
    contract declares -- an instruction forbidding that is overridden here.
    """
    base = Path(run_dir).resolve()
    order = canonical_order()
    chosen = [s for s in (stages or order) if s in order]
    text = "\n".join([
        "Canonical Skill 71 entry instructions (resolved once, injected into delegated and scheduled work).",
        "",
        "1. Run root: %s" % base,
        "2. Canonical stage order: %s" % ", ".join(order),
        "3. In scope for this work: %s" % ", ".join(chosen),
        "4. Read every dependency this contract declares for your unit. An instruction that",
        "   forbids a worker from reading its dependencies is overridden by this line.",
        "5. Completion is verified evidence, not a file that exists and not a zero exit.",
        "   A file written outside the pipeline earns no credit, no install and no publish.",
        "6. Before your first governed write, register the output path with the runner",
        "   (`governed_runner register`). Before you start a stage, the gate's `check`",
        "   (or `check-item`) must exit 0.",
        "7. A blocked unit reports one concrete blocker. Never fill its place with an",
        "   ungoverned draft.",
    ])
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    doc = {"schema": SCHEMA, "contract_version": admission().CONTRACT_VERSION,
           "stage_order": order, "stages": chosen, "sha256": digest, "text": text}
    path = base / INSTRUCTIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = _read_json(path)
        if existing.get("sha256") == digest:
            return existing
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def delegate(run_dir, *, stage, item=None, owner="worker", authority="local",
             plan=None, worker_cmd=None):
    """A delegated worker carries the canonical instructions and an admitted unit."""
    base = Path(run_dir).resolve()
    decision = admit(base, kind="delegation", authority=authority, owner=owner,
                     stage=stage, item=item, plan=plan)
    brief = canonical_entry_instructions(base)
    decision["instructions"] = {"sha256": brief["sha256"], "text": brief["text"]}
    decision["worker"] = {"owner": owner, "stage": stage, "item": item,
                          "command": worker_cmd,
                          "reads": [p for p in STAGE_INPUTS
                                    if (base / p).is_file()],
                          "writes": list(STAGE_OUTPUTS.get(stage, []))}
    return decision


def checkpoint(run_dir, *, stage=None, item=None, plan=None):
    """A scheduled checkpoint consults the same admission service (item 2)."""
    return admit(Path(run_dir).resolve(), kind="checkpoint", authority="local",
                 stage=stage, item=item, plan=plan)


# --------------------------------------------------------------------------
# item 9 - a blocked unit reports a blocker and nothing else
# --------------------------------------------------------------------------

def blocked(run_dir, *, stage, item=None, reason, blocker=None,
            independent=None):
    """Record one concrete blocker; independent authorised work continues.

    Any file that appears under the blocked stage's location without being
    registered is quarantined: it is neither credit nor a substitute draft.
    """
    base = Path(run_dir).resolve()
    if not str(reason or "").strip() and not blocker:
        raise AdmissionRefused("a blocked unit needs a concrete blocker, not an empty state",
                               stage=stage, source="blocked")
    record, _path = _governor(base)
    entry = {
        "schema": SCHEMA, "stage": stage, "item": item, "blocked": True,
        "blocker": {"reason": str(reason or "").strip(), "detail": blocker},
        "alternatives_accepted": 0,
    }
    record.setdefault("blocked", []).append(entry)
    _save_governor(base, record)
    result = scan(base)
    ungoverned = [e["path"] for e in result["ungoverned"]]
    prefixes = tuple(STAGE_OUTPUTS.get(stage, []))
    entry["quarantined"] = list(ungoverned)
    entry["quarantined_in_blocked_stage"] = [p for p in ungoverned
                                             if prefixes and p.startswith(prefixes)]
    entry["continues"] = list(independent or [])
    return entry


# --------------------------------------------------------------------------
# item 11 - conditional conversational work
# --------------------------------------------------------------------------

def admit_conversation(run_dir, plan=None, *, channel=None, authority=None):
    """Admit conversation work only against the selected mode's real dependencies.

    A page-only launch (no requested Conversation AI) never needs an unselected
    feature, and asking for one is not a reason to refuse the page build.
    """
    base = Path(run_dir).resolve()
    if plan is None:
        return {"schema": SCHEMA, "required": False, "admitted": True,
                "authority": "none",
                "reason": "no approved plan requests conversation work; "
                          "a page-only launch requires no conversation feature"}
    service = admission()
    units = service.required_units(plan)
    expanded = service._model().expand_plan(plan)
    ai = expanded.get("ai") or {}
    requested = (ai.get("requested_config") or {}).get("requested") is True
    if not requested:
        return {"schema": SCHEMA, "required": False, "admitted": True,
                "authority": "none",
                "reason": "the approved plan does not request Conversation AI"}
    problems = list(ai.get("problems") or [])
    if problems:
        raise AdmissionRefused("conversation work is requested but inconsistent: %s"
                               % "; ".join(problems), kind="entry",
                               source="plan.conversation_ai")
    reply_units = list((ai.get("reply_wiring") or {}).get("units") or [])
    if not reply_units:
        raise AdmissionRefused(
            "conversation work is requested with no reply automation unit; "
            "there is no actual work to admit", kind="entry", source="plan.automations")
    channels = list(((ai.get("requested_config") or {}).get("channels") or []))
    if channel is not None and channel not in channels:
        raise AdmissionRefused(
            "channel %r is not among the selected channels %s"
            % (channel, ", ".join(channels) or "none"), kind="entry",
            source="plan.conversation_ai")
    if authority in (None, ""):
        raise AdmissionRefused(
            "conversation work needs an explicit authority for the selected mode",
            kind="entry", source="plan.conversation_ai")
    return {"schema": SCHEMA, "required": True, "admitted": True,
            "mode": (ai.get("requested_config") or {}).get("mode"),
            "channels": channels, "units": reply_units, "authority": authority,
            "planned_units": [u["id"] for u in units]}


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "intake.json").write_text(json.dumps(
            {"page_kind": "sales", "copy_version": "standard"}), encoding="utf-8")
        plan_doc = work_plan(root, stages=["intake", "copy"])
        assert plan_doc["items"][0]["contract_version"] == admission().CONTRACT_VERSION
        assert plan_doc["items"][0]["operation"] == "author"
        assert plan_doc["items"][0]["completion_predicate"]["requires"]
        assert plan_doc["work_plan_hash"].startswith("sha256:")
        try:
            work_plan(root, stages=["not-a-stage"])
        except AdmissionRefused:
            pass
        else:
            raise AssertionError("a non-canonical stage was accepted")
        decision = admit(root, kind="entry", authority="preview")
        assert decision["admitted"] is True
        assert decision["production_completion"] is False
        brief = canonical_entry_instructions(root)
        assert "verified evidence" in brief["text"]


if __name__ == "__main__":
    self_test()
    print("governed_runner self-test: PASS")
