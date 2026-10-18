"""S44-02 executable dispatch receiver (core).

Implements DESIGN-S44-02-03-05-v1.md section 1 against an injected
Executor (the engine adapter in production; a recording fake in tests).
The receiver is the component that makes a handoff EXECUTABLE: it
validates an automation request, drives the governed build, reads the
results back, and issues a receipt a consumer can judge mechanically.

Contract conventions adopted from the Item 33a template (DESIGN-NOTES
section 20): exact-echo binding (request_id, request_version, scope),
status_claimed vs judged verdicts, execution provenance on every
receipt, honest-omission notes, exit discipline (3 gate fail-closed,
4 validation failed, 5 named blocker; on refusal nothing is written).

Nothing in this module performs a live write by itself; the Executor
owns all engine contact.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional, Protocol

EXIT_OK = 0
EXIT_GATE = 3        # gate fail-closed (tenant/safety)
EXIT_VALIDATION = 4  # envelope/plan validation failed
EXIT_BLOCKED = 5     # named blocker (auth state)

SKILL44_VERSION = "siglaunch-s44-receiver-0.2"

_ENVELOPE_FIELDS = {
    "request_id", "request_version", "location_id", "launch_id",
    "requesting_room", "deploy_mode", "approval", "plan", "workflows",
    "notes",
    # R71H seam packet section 3: the hash-lock from the emitter travels
    # with the dispatch and is echoed into the receipt (packet section
    # 2 step 2 / section 4). Optional: only seam dispatches carry it.
    "handoff_sha256",
}
_REQUIRED = _ENVELOPE_FIELDS - {"notes", "handoff_sha256"}

_HEX = set("0123456789abcdef")


def _is_sha256_hex(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in _HEX for c in value.lower()))


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True).encode()).hexdigest()


class Executor(Protocol):
    """The governed engine surface the receiver drives."""
    def probe(self) -> dict:
        """Capability evidence: {"token_state": healthy|absent|revoked|
        degraded, "access_tier_used": str, ...}"""
    def dependencies_present(self, location_id: str,
                             workflow: dict) -> list[str]:
        """Names of missing Phase-A dependencies ([] = all present)."""
    def snapshot(self, location_id: str, workflow_slug: str) -> bool:
        """Pre-write snapshot rule (AC20): False = unreadable state."""
    def build(self, builder_plan: dict) -> dict:
        """Build ONE workflow. Returns {"exit_code", "workflow_id",
        "errors", "notes", "export", "qc_exit_code", "rubric"} where
        export carries triggers[]/allowMultiple/status/steps."""


class Receiver:
    def __init__(self, store, executor: Executor, configured_location: str):
        self.store = store
        self.executor = executor
        self.configured_location = configured_location

    # ── refusals write nothing (exit discipline) ─────────────────────────
    def _refuse(self, request: dict, exit_code: int, code: str,
                detail: str) -> tuple[int, dict]:
        """A refusal is a receipt too (artifact-contracts.md:664-666;
        automation-handoff.md:207-213): it echoes the dispatch binding and
        carries the verbatim reason in `dispatch_refusal`. Nothing is
        stored or written on this path (design 1.2 exit discipline)."""
        return exit_code, {
            "outcome": "refused",
            "status": "blocked",
            "request_id": request.get("request_id"),
            "request_version": request.get("request_version"),
            "handoff_sha256": request.get("handoff_sha256"),
            "refused": code,
            "detail": detail,
            "dispatch_refusal": {"code": code, "reason": detail},
        }

    def dispatch(self, request: dict) -> tuple[int, dict]:
        # 1. envelope shape
        unknown = set(request) - _ENVELOPE_FIELDS
        if unknown:
            return self._refuse(request, EXIT_VALIDATION, "UNKNOWN_FIELDS",
                                f"unknown envelope fields: {sorted(unknown)}")
        missing = _REQUIRED - set(request)
        if missing:
            return self._refuse(request, EXIT_VALIDATION, "MISSING_FIELDS",
                                f"missing envelope fields: {sorted(missing)}")
        # 1b. handoff hash-lock, when carried, must be a SHA-256 hex
        # string; a malformed lock is refused, never echoed downstream
        # (publish-verify compares against this value mechanically).
        handoff_sha = request.get("handoff_sha256")
        if handoff_sha is not None and not _is_sha256_hex(handoff_sha):
            return self._refuse(request, EXIT_VALIDATION,
                "HANDOFF_HASH_INVALID",
                "handoff_sha256 is present but is not a 64-character "
                "SHA-256 hex string")
        # 2. deploy mode: fail-closed, never defaulted
        if request["deploy_mode"] != "draft-only":
            return self._refuse(request, EXIT_VALIDATION, "DEPLOY_MODE",
                "deploy_mode must be exactly 'draft-only'; absent or any "
                "other value is refused, never defaulted")
        # 3. tenant gate: the request's location must be the configured one
        if request["location_id"] != self.configured_location:
            return self._refuse(request, EXIT_GATE, "WRONG_LOCATION",
                "request location is not this box's configured location; "
                "refused before any engine call")
        # 4. approval hash over the plan as received
        approval = request["approval"]
        if approval.get("plan_hash") != plan_hash(request["plan"]):
            return self._refuse(request, EXIT_VALIDATION, "PLAN_HASH_MISMATCH",
                                "approval plan_hash does not match the "
                                "plan in this request")
        # 5. prior state: idempotent redispatch / superseded version
        prior = self.store.get_request(request["request_id"])
        if prior is not None:
            if request["request_version"] < prior["request_version"]:
                return self._refuse(request, EXIT_VALIDATION, "SUPERSEDED",
                    "request_version is lower than the recorded version")
            if prior["state"] == "complete" and prior["receipt"] is not None:
                return EXIT_OK, prior["receipt"]
        # 6. capability probe (fresh evidence per dispatch attempt)
        probe = self.executor.probe()
        token_state = probe.get("token_state")
        if token_state != "healthy":
            receipt = self._receipt_shell(request, probe)
            receipt["outcome"] = "refused"
            receipt["status"] = "blocked"
            receipt["status_claimed"] = "blocked-auth"
            reason = (f"token_state={token_state}: no writes attempted; "
                      "remediation differs by state (absent vs revoked) and "
                      "is owned by the S06 auth entry point")
            receipt["dispatch_refusal"] = {
                "code": "BLOCKED_AUTH", "reason": reason}
            receipt["notes"].append(reason)
            self.store.put_request(request["request_id"],
                                   request["request_version"],
                                   request["location_id"], "blocked-auth",
                                   receipt)
            return EXIT_BLOCKED, receipt
        # 7. plan normalization: strip _meta, builder gets {folder, slug: wf}
        try:
            builder_plans, exceptions = self._normalize_plan(request)
        except ValueError as e:
            return self._refuse(request, EXIT_VALIDATION, "PLAN_INVALID", str(e))
        # 8. per-workflow execution with resume semantics
        receipt = self._receipt_shell(request, probe)
        prior_ops = {}
        if prior and prior["receipt"]:
            prior_ops = {op["slug"]: op
                         for op in prior["receipt"].get("operations", [])}
        all_ok = True
        for slug, builder_plan in builder_plans:
            if slug in prior_ops and prior_ops[slug].get("workflow_id"):
                op = prior_ops[slug]  # resume: never rebuild what exists
                op["status_claimed"] = "reused"
                receipt["operations"].append(op)
                continue
            op = self._execute_one(request, slug, builder_plan, probe)
            receipt["operations"].append(op)
            if op["status_claimed"] not in ("created", "reused"):
                all_ok = False
        # Packet-sanctioned exceptions (no_workflow_reason entries) are
        # recorded as skipped operations with the reason verbatim; they
        # build nothing and do not drag the request's verdict down.
        for entry in exceptions:
            receipt["operations"].append(
                self._exception_op(entry))
        # Top-level stage-14 form_exceptions (artifact-contracts.md:657):
        # the packet-sanctioned no_workflow_reason entries, verbatim.
        receipt["form_exceptions"] = [
            {"form_id": entry["form_id"],
             "no_workflow_reason": entry["no_workflow_reason"]}
            for entry in exceptions if entry.get("form_id")]
        receipt["outcome"] = "accepted" if all_ok else "failed"
        receipt["status_claimed"] = "verified" if all_ok else "partial" \
            if any(op["status_claimed"] in ("created", "reused")
                   for op in receipt["operations"]) else "failed"
        state = "complete" if all_ok else "partial"
        self.store.put_request(request["request_id"],
                               request["request_version"],
                               request["location_id"], state, receipt)
        # Exit discipline (design 1.2): a dispatch that executed but
        # whose operations failed their checks is a JUDGE failure (4),
        # not a named blocker (5). Exit 5 is reserved for the
        # blocked-auth path above, where nothing was built.
        return (EXIT_OK if all_ok else EXIT_VALIDATION), receipt

    @staticmethod
    def _exception_op(entry: dict) -> dict:
        op = {"slug": entry.get("slug") or entry.get("form_id")
              or "excepted-entry",
              "status_claimed": "skipped", "workflow_id": None,
              "expect": [], "readback": None, "errors": [],
              "no_workflow_reason": entry["no_workflow_reason"],
              "readback_summary": {"exists": False, "status": None}}
        if entry.get("form_id"):
            op["form_id"] = entry["form_id"]
        return op

    # ── internals ────────────────────────────────────────────────────────
    # Stage-14 fields the receiver cannot produce from its own state or
    # its executor contract. They are named in the receipt's notes on
    # seam dispatches (design 1.2: an omission that is not named is a
    # defect), never invented.
    _UNPRODUCIBLE_STAGE14 = (
        "conversational (the envelope carries no form roles, so the "
        "derived opt-in/purchase/booking trigger set cannot be computed "
        "receiver-side; it is derived by the stage-14 mapper from the "
        "handoff), conversational_overrides (owner-approved exceptions "
        "are not on the envelope), conversational_not_present (derived "
        "with the trigger set), ghl_pack_version (no executor surface "
        "reports it), qc.checklist_instance path, qc.checklist_complete "
        "and the WF item count (no checklist instance is created through "
        "the executor contract)")

    def _receipt_shell(self, request: dict, probe: dict) -> dict:
        notes = list(request.get("notes", []))
        if request.get("handoff_sha256") is not None:
            notes.append(
                "stage-14 fields not producible by the receiver: "
                + self._UNPRODUCIBLE_STAGE14)
        approval = request.get("approval") or {}
        return {
            "request_id": request["request_id"],
            "request_version": request["request_version"],
            "location_id": request["location_id"],
            "launch_id": request["launch_id"],
            # design 1.4 per-request fields
            "deploy_mode": request["deploy_mode"],
            "approval": {"ref": approval.get("ref"),
                         "plan_hash": approval.get("plan_hash")},
            # seam packet sections 2/4: the hash-lock echo (None when
            # the dispatch carried no handoff)
            "handoff_sha256": request.get("handoff_sha256"),
            # Stage-14 receipt fields (artifact-contracts.md:656-667).
            # outcome is set by the dispatch path; the four fields the
            # receiver cannot know stay None (explicitly absent, never an
            # empty string or an invented value) and are named in notes.
            "outcome": None,
            "form_exceptions": [],
            "conversational": None,
            "conversational_overrides": None,
            "conversational_not_present": None,
            "ghl_pack_version": None,
            "status_claimed": None,
            "operations": [],
            "notes": notes,
            "execution": {
                "execution_id": "exec_" + uuid.uuid4().hex[:12],
                "access_tier_used": probe.get("access_tier_used", "unknown"),
                "skill44_version": SKILL44_VERSION,
            },
        }

    @staticmethod
    def _partition_workflows(request: dict):
        """Split workflows[] into build entries (keyed by slug) and
        packet-sanctioned exception entries (carrying
        no_workflow_reason instead of a build entry, seam packet
        section 3). Malformed entries raise ValueError, which the
        caller turns into a recorded PLAN_INVALID refusal — a
        workflows[] entry must never crash the dispatch (GAP-2)."""
        entries = request["workflows"]
        if not isinstance(entries, list):
            raise ValueError("workflows must be a list")
        builds, exceptions = {}, []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("workflows[] entries must be objects")
            if "no_workflow_reason" in entry:
                if not isinstance(entry["no_workflow_reason"], str) \
                        or not entry["no_workflow_reason"]:
                    raise ValueError(
                        "no_workflow_reason must be a non-empty string")
                exceptions.append(entry)
                continue
            if not entry.get("slug"):
                raise ValueError(
                    "workflows[] entry carries neither 'slug' nor "
                    "'no_workflow_reason'; refusing")
            builds[entry["slug"]] = entry
        return builds, exceptions

    @staticmethod
    def _validate_trigger_contract(entry: dict) -> None:
        """Seam packet section 3 trigger contract: origin is the R71H
        trigger {form_submitted, form_id}; mechanism is how the native
        trigger is realized (verbatim contact tag, or the native
        trigger via the Tier-4 backstop). Shape errors are validation
        failures, raised before any build."""
        origin = entry.get("origin")
        if origin is not None:
            if not isinstance(origin, dict) \
                    or origin.get("type") != "form_submitted" \
                    or not isinstance(origin.get("form_id"), str) \
                    or not origin.get("form_id"):
                raise ValueError(
                    f"workflow {entry.get('slug')!r}: origin must be "
                    "{type: 'form_submitted', form_id: <non-empty "
                    "string>} (seam packet section 3)")
        mechanism = entry.get("mechanism")
        if mechanism is not None:
            if not isinstance(mechanism, dict):
                raise ValueError(
                    f"workflow {entry.get('slug')!r}: mechanism must "
                    "be an object")
            mtype = mechanism.get("type")
            if mtype == "contact_tag":
                if not isinstance(mechanism.get("tag"), str) \
                        or not mechanism.get("tag"):
                    raise ValueError(
                        f"workflow {entry.get('slug')!r}: contact_tag "
                        "mechanism requires the verbatim tag string")
            elif mtype == "native":
                if mechanism.get("build_method") != \
                        "tier4-browser-backstop":
                    raise ValueError(
                        f"workflow {entry.get('slug')!r}: native "
                        "mechanism requires build_method "
                        "'tier4-browser-backstop'")
            else:
                raise ValueError(
                    f"workflow {entry.get('slug')!r}: unknown "
                    f"mechanism type {mtype!r}")

    def _normalize_plan(self, request: dict):
        plan = request["plan"]
        if not isinstance(plan, dict):
            raise ValueError("plan must be an object")
        meta = plan.get("_meta")
        if meta is not None:
            if not isinstance(meta, dict):
                raise ValueError("_meta must be an object")
            mode = meta.get("deploy_mode")
            if mode is not None and mode != "draft-only":
                raise ValueError(
                    f"plan _meta deploy_mode is {mode!r}, not draft-only")
            # Design 1.3 step 6: _meta content hashes present. An
            # emitted, versioned plan (one carrying plan_version, the
            # S50 emit_build_plan shape) must carry its content_hashes;
            # their absence is a validation failure, not a dispatch.
            if "content_hashes" in meta and not isinstance(
                    meta["content_hashes"], dict):
                raise ValueError(
                    "_meta content_hashes must be an object mapping "
                    "workflow slug to SHA-256 hex")
            if "plan_version" in meta:
                hashes = meta.get("content_hashes")
                if not isinstance(hashes, dict) or not hashes:
                    raise ValueError(
                        "plan _meta carries plan_version but no "
                        "content_hashes; design 1.3 step 6 requires "
                        "content hashes present on an emitted plan")
        folder = plan.get("folder", "caf-build")
        declared, exceptions = self._partition_workflows(request)
        for entry in declared.values():
            self._validate_trigger_contract(entry)
        out = []
        for slug, wf_def in plan.items():
            if slug in ("_meta", "folder"):
                continue
            if not isinstance(wf_def, dict) or "name" not in wf_def:
                raise ValueError(
                    f"plan entry {slug!r} is not a workflow definition "
                    "(missing 'name'); refusing the whole request")
            if slug not in declared:
                raise ValueError(
                    f"plan workflow {slug!r} is not declared in the "
                    "request's workflows[]; refusing")
            out.append((slug, {"folder": folder, slug: wf_def}))
        if not out:
            raise ValueError("plan contains no workflows")
        return out, exceptions

    @staticmethod
    def _trigger_record(declared: dict):
        """The receipt's per-operation trigger record (packet section
        4): the declared ORIGIN and MECHANISM side by side — a record
        naming only one side is incomplete. Legacy S50-shape requests
        carry a single `trigger` object, echoed as-is."""
        if "origin" in declared or "mechanism" in declared:
            record = {}
            if "origin" in declared:
                record["origin"] = declared["origin"]
            if "mechanism" in declared:
                record["mechanism"] = declared["mechanism"]
            return record
        return declared.get("trigger")

    @staticmethod
    def _build_method(declared: dict, probe: dict):
        """Packet section 4 build_method vocabulary: 'caf-cli' when
        the execution provenance is the tier-0 caf path,
        'tier4-browser-backstop' when Tier 4 was used. A native
        mechanism declares its method in the contract itself."""
        mechanism = declared.get("mechanism") or {}
        if mechanism.get("build_method"):
            return mechanism["build_method"]
        tier = probe.get("access_tier_used", "")
        if tier.startswith("tier0"):
            return "caf-cli"
        if "tier4" in tier:
            return "tier4-browser-backstop"
        return None

    @staticmethod
    def _trigger_bound(declared: dict, export: dict) -> bool:
        """Trigger check against the packet contract. The native
        trigger the mechanism must realize in the export: for a
        contact_tag mechanism, a contact_tag trigger (and, where the
        export carries the tag, the VERBATIM Phase-A tag string — a
        drifted tag is a receipt-level defect); for a native
        mechanism, the form_submitted origin trigger itself. Legacy
        requests keep the declared `trigger` type check."""
        triggers = export.get("triggers", [])
        observed_types = [t.get("type") for t in triggers]
        if not triggers:
            # Layer-9 observation basis (MAIN ruling, 2026-10-18,
            # option (a)): the native object carries no trigger
            # contents — triggers live in a separate trigger-bucket
            # file. When the export records that bucket evidence
            # verbatim (bucket_migrated true + the workflow's own
            # triggers_file_path), the binding is observed from it:
            # the bucket exists only because the builder created and
            # linked this workflow's trigger at build time. An
            # explicit triggers list, when present, always governs
            # instead — a drifted explicit list is a defect the
            # bucket must never paper over.
            evidence = export.get("trigger_evidence") or {}
            if evidence.get("bucket_migrated") is True \
                    and isinstance(evidence.get("triggers_file_path"),
                                   str) \
                    and evidence.get("triggers_file_path"):
                return True
        mechanism = declared.get("mechanism")
        if mechanism:
            mtype = mechanism.get("type")
            if mtype == "contact_tag":
                if "contact_tag" not in observed_types:
                    return False
                tagged = [t for t in triggers
                          if t.get("type") == "contact_tag"
                          and "tag" in t]
                if tagged:
                    return any(t.get("tag") == mechanism.get("tag")
                               for t in tagged)
                return True
            if mtype == "native":
                origin = declared.get("origin") or {}
                return origin.get("type", "form_submitted") \
                    in observed_types
            return mtype in observed_types
        exp_trigger = declared.get("trigger", {})
        return exp_trigger.get("type") in observed_types

    def _execute_one(self, request: dict, slug: str,
                     builder_plan: dict, probe: dict) -> dict:
        declared = next(w for w in request["workflows"]
                        if w.get("slug") == slug)
        op = {"slug": slug, "status_claimed": "failed", "workflow_id": None,
              "expect": [], "readback": None, "errors": [],
              # design 1.4 / packet section 4 per-operation fields the
              # receiver produces from its own state
              "name": (builder_plan.get(slug) or {}).get("name"),
              "folder": builder_plan.get("folder"),
              "build_method": self._build_method(declared, probe),
              "trigger": self._trigger_record(declared),
              # artifact-contracts.md:663-664: the mechanism recorded
              # alongside the trigger, not only nested inside it.
              "mechanism": declared.get("mechanism"),
              "qc": {"script": "qc-built-workflow.sh",
                     "exit_code": None, "rubric": None,
                     "checklist_instance": None,
                     # The executor contract creates no checklist
                     # instance, so these stay explicitly unknown
                     # (automation-handoff.md:196-204) rather than
                     # invented.
                     "checklist_complete": None, "wf_items": None},
              "readback_summary": {"exists": False, "status": None}}
        # dependency precheck (Phase-A receipts are the input contract)
        missing = self.executor.dependencies_present(
            request["location_id"], declared)
        if missing:
            op["errors"].append(f"missing dependencies: {missing}")
            return op
        # snapshot-or-abort (AC20)
        if not self.executor.snapshot(request["location_id"], slug):
            op["errors"].append(
                "pre-write snapshot failed: state unreadable, build "
                "aborted with no write sent")
            return op
        result = self.executor.build(builder_plan)
        op["errors"] = list(result.get("errors", []))
        # Full build stats recorded on the receipt (MAIN layer-9
        # ruling; None only when the build emitted no parseable
        # stats, which the errors above already report).
        op["build_stats"] = result.get("stats")
        export = result.get("export") or {}
        op["workflow_id"] = result.get("workflow_id")
        op["readback"] = export if export else None
        op["qc"] = {"script": "qc-built-workflow.sh",
                    "exit_code": result.get("qc_exit_code"),
                    "rubric": result.get("rubric"),
                    "checklist_instance": result.get("checklist_instance"),
                    "checklist_complete": result.get("checklist_complete"),
                    "wf_items": result.get("wf_items")}
        checks = []
        checks.append({
            "name": "object_exists",
            "ok": bool(result.get("workflow_id") and export)})
        checks.append({
            "name": "trigger_bound",
            "ok": self._trigger_bound(declared, export)})
        checks.append({
            "name": "steps_match_contract",
            "ok": len(export.get("steps", [])) ==
                  declared.get("expected_steps", -1)})
        checks.append({
            "name": "draft_state_recorded",
            "ok": export.get("status") == "draft"})
        checks.append({
            "name": "reentry_matches_contract",
            "ok": export.get("allowMultiple") ==
                  declared.get("allow_multiple", False)})
        checks.append({
            "name": "qc_exit_zero",
            "ok": result.get("qc_exit_code") == 0})
        op["expect"] = checks
        # Packet section 4 readback pair: exists means the export
        # read-back was returned, its id equals the claimed id, and
        # every expected check passed (the judge's VERIFIED condition,
        # computed here mechanically for the stage-14 mapper; the raw
        # export stays in op["readback"] as the evidence itself).
        op["readback_summary"] = {
            "exists": bool(export)
                      and export.get("id") == result.get("workflow_id")
                      and all(c["ok"] for c in checks),
            "status": export.get("status")}
        if result.get("exit_code") == 0 and result.get("workflow_id") \
                and all(c["ok"] for c in checks):
            op["status_claimed"] = "created"
        return op


def judge_receipt(receipt: dict) -> dict:
    """Consumer-side judge (the Item 33a rule): a claimed success without
    its verification read-back judges UNVERIFIED, never success. Verified
    requires the remote object id, every expect[] check ok, and the
    read-back's object id equal to the claimed id. The receipt's top-level
    status is advisory and is never adopted."""
    verdicts = {}
    for op in receipt.get("operations", []):
        if op.get("status_claimed") == "skipped":
            # A packet-sanctioned exception (no_workflow_reason): the
            # operation asserts no build, so there is nothing to
            # verify — and nothing to fail. It is judged SKIPPED and
            # excluded from the overall computation.
            verdicts[op["slug"]] = "SKIPPED"
            continue
        claimed_id = op.get("workflow_id")
        readback = op.get("readback") or {}
        if not claimed_id or not readback:
            verdicts[op["slug"]] = "UNVERIFIED"
            continue
        if readback.get("id") != claimed_id:
            verdicts[op["slug"]] = "UNVERIFIED"
            continue
        if not all(c.get("ok") for c in op.get("expect", [])):
            verdicts[op["slug"]] = "FAILED_CHECKS"
            continue
        verdicts[op["slug"]] = "VERIFIED"
    counted = [v for v in verdicts.values() if v != "SKIPPED"]
    overall = "VERIFIED" if counted and all(
        v == "VERIFIED" for v in counted) else "NOT_VERIFIED"
    return {"overall": overall, "operations": verdicts}

# ── stage-14 outcome record (the Skill 71 filing surface) ────────────────
# The receiver's own receipt keeps the raw export in operations[].readback
# for judge_receipt(). The stage-14 contract names the per-workflow
# readback {exists, status} and a flat trigger; this translation emits
# exactly the outcome record that automation_handoff.py's
# file_dispatch_receipt() (CLI: --outcome <file>) consumes.

def stage14_outcome(request: dict, exit_code: int, result: dict) -> dict:
    """Translate a dispatch return into the stage-14 outcome record.

    Citations:
      - artifact-contracts.md:656-667: workflows[], form_exceptions,
        conversational, conversational_overrides,
        conversational_not_present, ghl_pack_version, and the dispatch
        binding request_id / request_version / handoff_sha256 / outcome.
      - automation-handoff.md:186-213: per workflow workflow_id, name,
        trigger (form_submitted + form_id) with the mechanism alongside,
        build_method, qc.script / exit_code / checklist_instance /
        checklist_complete / wf_items, readback {exists, status}; a
        refusal or failure carries its verbatim reason.

    A field this dispatch genuinely cannot know is None — explicitly
    absent, never "" or invented data — and is named in `unproducible`
    (automation-handoff.md: an un-named omission is a defect)."""
    outcome = result.get("outcome")
    if outcome not in ("accepted", "refused", "failed"):
        if result.get("status_claimed") == "blocked-auth":
            outcome = "refused"
        elif exit_code == EXIT_OK:
            outcome = "accepted"
        else:
            outcome = "failed"
    record = {
        "outcome": outcome,
        "request_id": request.get("request_id"),
        "request_version": request.get("request_version"),
        "handoff_sha256": request.get("handoff_sha256"),
    }
    unproducible = []
    # Form exceptions are the envelope's no_workflow_reason entries,
    # verbatim (artifact-contracts.md:657; automation-handoff.md:205-206).
    record["form_exceptions"] = [
        {"form_id": w["form_id"],
         "no_workflow_reason": w["no_workflow_reason"]}
        for w in request.get("workflows") or []
        if isinstance(w, dict) and w.get("form_id")
        and isinstance(w.get("no_workflow_reason"), str)
        and w["no_workflow_reason"].strip()]
    if outcome == "refused":
        refusal = result.get("dispatch_refusal") or {}
        record["refusal"] = {
            "code": refusal.get("code") or result.get("refused"),
            "reason": refusal.get("reason") or result.get("detail")}
        record["workflows"] = None
    elif outcome == "failed":
        errors = [e for op in result.get("operations", [])
                  for e in (op.get("errors") or [])]
        record["failure"] = {
            "code": "DISPATCH_FAILED",
            "reason": "; ".join(errors) if errors else None}
        if not errors:
            unproducible.append("failure.reason")
        record["workflows"] = None
    else:
        workflows = []
        for i, op in enumerate(result.get("operations", [])):
            if op.get("status_claimed") == "skipped":
                continue  # already recorded in form_exceptions
            trig = op.get("trigger") or {}
            origin = trig.get("origin") if isinstance(trig, dict) else None
            wf = {"workflow_id": op.get("workflow_id"),
                  "name": op.get("name")}
            if isinstance(origin, dict) \
                    and origin.get("type") == "form_submitted" \
                    and origin.get("form_id"):
                wf["trigger"] = {"type": "form_submitted",
                                 "form_id": origin["form_id"]}
            else:
                wf["trigger"] = None
                unproducible.append(f"workflows[{i}].trigger")
            mechanism = op.get("mechanism")
            wf["mechanism"] = mechanism if isinstance(mechanism, dict) else None
            if wf["mechanism"] is None:
                unproducible.append(f"workflows[{i}].mechanism")
            wf["build_method"] = op.get("build_method")
            if wf["build_method"] not in ("caf-cli",
                                          "tier4-browser-backstop"):
                unproducible.append(f"workflows[{i}].build_method")
            qc_in = op.get("qc") or {}
            wf["qc"] = {"script": qc_in.get("script"),
                        "exit_code": qc_in.get("exit_code")}
            for key in ("checklist_instance", "checklist_complete",
                        "wf_items"):
                wf["qc"][key] = qc_in.get(key)
                if qc_in.get(key) is None:
                    unproducible.append(f"workflows[{i}].qc.{key}")
            rb = op.get("readback_summary")
            if isinstance(rb, dict) and "exists" in rb and "status" in rb:
                wf["readback"] = {"exists": rb["exists"],
                                  "status": rb["status"]}
            else:
                wf["readback"] = None
                unproducible.append(f"workflows[{i}].readback")
            workflows.append(wf)
        record["workflows"] = workflows
    # The receiver derives none of these (named in the receipt notes).
    for key in ("conversational", "conversational_overrides",
                "conversational_not_present", "ghl_pack_version"):
        record[key] = None
        unproducible.append(key)
    record["unproducible"] = unproducible
    return record
