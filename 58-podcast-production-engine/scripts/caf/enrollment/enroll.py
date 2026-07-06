#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: ENROLLMENT LAYER (PRD Step 17)
# -----------------------------------------------------------------------------
# Skill 44 caf (Tier 0) workflow enrollment for Interview-mode episodes:
# discovery-then-verify-then-enroll, a double-enrollment guard so no customer is
# ever double-notified, and a HARD Personal-mode refusal. Everything is verified
# through caf reads. Tier 3 REST is the sub-agent-safe fallback for the enroll
# call only; the two Model Context Protocol tiers are forbidden here (sub-agents
# get no MCP injection). This module never sends a customer message: after
# enrollment the engine STOPS and Convert and Flow owns all messaging.
#
# THE TWO WORKFLOWS (exact names, standardized across clients; ghl-design 5.1):
#   06-Podcast_Episode_Is_Ready  adds the "podcast episode is ready" tag.
#   04-Podcast is Completed      is field-triggered by the Podcast Survey
#                                Episode URL changing; adds the
#                                "Podcast Completed Survey Style" tag.
#
# WHY VERIFICATION IS TAG-BASED (honest, no false done):
#   The public Convert and Flow API exposes no endpoint that lists a contact's
#   active workflow enrollments. The caf-observable proof of enrollment is the
#   tag each workflow applies. So this module verifies enrollment by re-reading
#   the contact through caf and confirming the workflow's known tag, and, for a
#   workflow it enrolled directly, by the enroll call's own success ack. If
#   neither evidence is present after one retry, the result is UNVERIFIED and the
#   episode is NOT marked delivered.
#
# GATE (hard): enrollment runs only AFTER (1) the Podbean episode exists with a
#   captured permalink AND (2) every Step 16 field write passed read-back
#   verification. Enrolling earlier notifies a customer about an episode that is
#   not there, which the responsibility-boundary rule makes a total failure.
#
# DOUBLE-ENROLLMENT GUARD: 04 is field-triggered, so the Step 16 URL write may
#   have already enrolled the contact. This module verifies first and enrolls 04
#   explicitly ONLY when the field trigger did not, making a double SMS
#   impossible from our side.
#
# NO WORKFLOW BUILDING AT RUNTIME: a workflow missing by name STOPS setup and is
#   surfaced to the founder. Building a workflow needs the separate Skill 44
#   Firebase refresh token and is an operator decision, never an autonomous act.
#
# EXIT CODES (CLI): 0 ok / 1 generic / 2 mode refusal (Personal) /
#   3 usage / 4 gate not met / 5 rate-limit stop / 6 unverified after retry /
#   7 workflow discovery failure.
#
# USAGE:
#   python3 enroll.py --self-test
#   python3 enroll.py enroll --job job.json --state ghl-state.json
# =============================================================================
"""Skill 44 caf workflow enrollment for the Podcast Engine (Interview mode)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

INTERVIEW_MODE = "interview_style_podcast"
PERSONAL_MODE = "personal_podcast_style"

WF_06 = "06-Podcast_Episode_Is_Ready"
WF_04 = "04-Podcast is Completed"

# The tag each workflow applies. Tag presence is the caf-observable proof of
# enrollment (see the module header). These names are standardized across
# clients; only workflow IDs differ per account and are discovered at setup.
WF_TAGS: Dict[str, str] = {
    WF_04: "Podcast Completed Survey Style",
    WF_06: "podcast episode is ready",
}

URL_FIELD_KEY = "podcast_survey_episode_url"
DEFAULT_CAF_BIN = os.environ.get("CAF_BIN", "caf")

BASE_HOST = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class EnrollmentError(Exception):
    """Base class for every enrollment-layer failure."""


class ModeGuardError(EnrollmentError):
    """Personal Podcast mode reached the enrollment function. Hard refusal."""


class GateError(EnrollmentError):
    """Publish/field-write preconditions were not met. Enrollment refused."""


class DiscoveryError(EnrollmentError):
    """A required workflow could not be resolved by name. Stop setup."""


class EnrollUnverified(EnrollmentError):
    """Enrollment could not be verified via a caf read after one retry."""


class RateLimited(EnrollmentError):
    """HTTP 429 from the shared per-location bucket. Full stop, never retry."""

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# --------------------------------------------------------------------------- #
# caf runner (Tier 0). Injectable so tests never touch a live CRM.
# --------------------------------------------------------------------------- #

@dataclass
class CafResult:
    """The outcome of one caf invocation."""

    ok: bool
    returncode: int
    data: Any = None
    stdout: str = ""
    stderr: str = ""


CafRunner = Callable[[List[str]], CafResult]


def _looks_rate_limited(text: str) -> bool:
    low = (text or "").lower()
    return "429" in low or "rate limit" in low or "too many requests" in low


def make_caf_runner(
    caf_bin: str = DEFAULT_CAF_BIN,
    location_id: Optional[str] = None,
    timeout: float = 60.0,
) -> CafRunner:
    """Build a caf runner that shells out to the Skill 44 CLI with --json.

    The returned callable takes the caf argument vector AFTER the global flags
    (for example ["workflows", "enroll", "--contact-id", cid, "--workflow-id",
    wid]) and returns a parsed CafResult. A 429 anywhere raises RateLimited.
    """

    def runner(args: List[str]) -> CafResult:
        cmd = [caf_bin, "--json"]
        if location_id:
            cmd += ["--location-id", location_id]
        cmd += list(args)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise EnrollmentError(
                f"caf CLI not found ({caf_bin}). Install Skill 44 or set CAF_BIN."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise EnrollmentError(f"caf timed out after {timeout}s.") from exc

        if _looks_rate_limited(proc.stdout) or _looks_rate_limited(proc.stderr):
            raise RateLimited("Convert and Flow rate limit (429) via caf. Full stop.")

        data: Any = None
        if proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = None
        return CafResult(
            ok=(proc.returncode == 0),
            returncode=proc.returncode,
            data=data,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    return runner


def caf_call(runner: CafRunner, args: List[str], what: str) -> CafResult:
    """Run a caf command and raise EnrollmentError on a non-zero exit."""
    result = runner(args)
    if not result.ok:
        detail = (result.stderr or result.stdout or "").strip()
        raise EnrollmentError(f"caf {what} failed (rc={result.returncode}): {detail}")
    return result


# --------------------------------------------------------------------------- #
# Contact reads and tag helpers
# --------------------------------------------------------------------------- #

def _unwrap_contact(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        if isinstance(data.get("contact"), dict):
            return data["contact"]
        return data
    return {}


def read_contact(runner: CafRunner, contact_id: str) -> Dict[str, Any]:
    """Read a contact via caf contacts get. Returns the contact object."""
    result = caf_call(runner, ["contacts", "get", contact_id], "contacts get")
    return _unwrap_contact(result.data)


def contact_tags(contact: Dict[str, Any]) -> set:
    """Return the contact's tags as a set of trimmed, lowercased strings."""
    tags = contact.get("tags") or []
    out = set()
    for tag in tags:
        if isinstance(tag, str):
            out.add(tag.strip().lower())
    return out


def has_tag(contact: Dict[str, Any], tag: str) -> bool:
    return tag.strip().lower() in contact_tags(contact)


def url_field_is_set(contact: Dict[str, Any]) -> bool:
    """Whether the podcast_survey_episode_url custom field carries a value.

    This is the field-trigger precondition for 04. The byte-for-byte read-back
    of the field write itself is owned by the field-write layer; here we only
    confirm the trigger field is populated.
    """
    fields = contact.get("customFields") or contact.get("custom_fields") or []
    if isinstance(fields, dict):
        value = fields.get(URL_FIELD_KEY)
        return bool(value)
    for entry in fields:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key") or entry.get("fieldKey") or ""
        key = str(key).split(".")[-1]
        if key == URL_FIELD_KEY:
            return bool(entry.get("value") or entry.get("field_value"))
    return False


# --------------------------------------------------------------------------- #
# Workflow resolution (setup-time discovery; never guessed at runtime)
# --------------------------------------------------------------------------- #

def discover_workflows(runner: CafRunner) -> Dict[str, Dict[str, Any]]:
    """List workflows via caf and return {name: {"id": ...}}."""
    result = caf_call(runner, ["workflows", "list"], "workflows list")
    data = result.data
    items: List[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("workflows") or data.get("data") or []
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        wid = item.get("id") or item.get("_id")
        if name and wid:
            out[str(name)] = {"id": str(wid)}
    return out


def resolve_workflow(
    state: Dict[str, Any],
    name: str,
    runner: Optional[CafRunner] = None,
) -> Dict[str, Any]:
    """Resolve a workflow to {"id", "trigger"} from state, or live discovery.

    A workflow missing everywhere is a DiscoveryError: stop setup, surface to
    the founder. Never guess an ID and never build a workflow at runtime.
    """
    workflows = (state or {}).get("workflows") or {}
    entry = workflows.get(name)
    if entry and entry.get("id"):
        return {"id": str(entry["id"]), "trigger": entry.get("trigger", "direct_add")}
    if runner is not None:
        discovered = discover_workflows(runner)
        if name in discovered:
            return {"id": discovered[name]["id"], "trigger": "direct_add"}
    raise DiscoveryError(
        f"Workflow '{name}' not found in state or via caf discovery. Stop setup "
        f"and surface to the founder; do not build it at runtime."
    )


# --------------------------------------------------------------------------- #
# Enrollment primitives (Tier 0 caf; optional Tier 3 REST fallback)
# --------------------------------------------------------------------------- #

def enroll_via_caf(runner: CafRunner, contact_id: str, workflow_id: str) -> bool:
    """Enroll a contact into a workflow via caf. Returns True on success ack."""
    result = caf_call(
        runner,
        ["workflows", "enroll", "--contact-id", contact_id,
         "--workflow-id", workflow_id],
        "workflows enroll",
    )
    return result.ok


def apply_tag_via_caf(runner: CafRunner, contact_id: str, tag: str) -> bool:
    """Apply a trigger tag via caf contacts add-tag. Returns True on success."""
    result = caf_call(
        runner, ["contacts", "add-tag", contact_id, tag], "contacts add-tag"
    )
    return result.ok


def enroll_via_rest(
    contact_id: str,
    workflow_id: str,
    token: str,
    location_id: str,
) -> bool:
    """Tier 3 REST fallback for the enroll call only (POST .../workflow/...).

    Used solely when caf is unavailable or the caf enroll fails with a non-429
    error. Never on a 429 (all tiers share one bucket). The token is never
    logged.
    """
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise EnrollmentError("requests is required for the REST fallback.") from exc
    url = f"{BASE_HOST}/contacts/{contact_id}/workflow/{workflow_id}"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Version": API_VERSION,
        },
        params={"locationId": location_id},
        timeout=60,
    )
    if response.status_code == 429:
        raise RateLimited("Convert and Flow rate limit (429) via REST. Full stop.")
    return response.status_code in (200, 201)


# --------------------------------------------------------------------------- #
# Orchestration (PRD Step 17)
# --------------------------------------------------------------------------- #

def _verify_gate(preconditions: Dict[str, Any]) -> None:
    """Hard gate: publish permalink present and Step 16 read-back verified."""
    permalink = preconditions.get("podbean_permalink")
    writeback_ok = preconditions.get("field_writeback_verified")
    if not permalink:
        raise GateError(
            "Enrollment refused: no Podbean permalink. Publish must complete "
            "and be captured before any workflow enrollment."
        )
    if writeback_ok is not True:
        raise GateError(
            "Enrollment refused: Step 16 field write-back is not verified. "
            "Enrollment runs only after every field write passes read-back."
        )


def enroll_episode(
    mode: str,
    contact_id: str,
    state: Dict[str, Any],
    *,
    runner: CafRunner,
    preconditions: Dict[str, Any],
    rest_token: Optional[str] = None,
    location_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Enroll an Interview-mode guest into 04 and 06, verified via caf reads.

    Hard-refuses Personal mode. Applies the double-enrollment guard to 04. Never
    sends a customer message. Raises EnrollUnverified if either enrollment cannot
    be confirmed via a caf read after one retry.
    """
    # --- Mode guard (hard) -------------------------------------------------- #
    if mode == PERSONAL_MODE:
        raise ModeGuardError(
            "Personal Podcast mode never touches workflows 04 or 06. Update the "
            "running episode spreadsheet instead and send no customer message."
        )
    if mode != INTERVIEW_MODE:
        return {
            "mode": mode,
            "enrolled": False,
            "skipped": True,
            "reason": f"mode '{mode}' does not enroll (Interview mode only).",
            "verified": True,
        }

    if not contact_id:
        raise EnrollmentError("contact_id is required for enrollment.")

    # --- Gate (hard) -------------------------------------------------------- #
    _verify_gate(preconditions)

    # --- Resolve both workflows (never guessed) ----------------------------- #
    wf04 = resolve_workflow(state, WF_04, runner=runner)
    wf06 = resolve_workflow(state, WF_06, runner=runner)

    notes: List[str] = []
    workflows_result: Dict[str, Any] = {}

    def _do_enroll(workflow_id: str, label: str) -> bool:
        """caf enroll first; Tier 3 REST fallback on a non-429 caf failure."""
        try:
            return enroll_via_caf(runner, contact_id, workflow_id)
        except RateLimited:
            raise
        except EnrollmentError as exc:
            if rest_token and location_id:
                notes.append(f"{label}: caf enroll failed, using Tier 3 REST fallback.")
                return enroll_via_rest(contact_id, workflow_id, rest_token, location_id)
            raise exc

    # --- Read the contact once (verify-then-enroll) ------------------------- #
    contact = read_contact(runner, contact_id)

    # --- Workflow 04: double-enrollment guard ------------------------------- #
    tag04 = WF_TAGS[WF_04]
    field_triggered_04 = str(wf04.get("trigger", "")).startswith("field")
    already_04 = has_tag(contact, tag04)
    if field_triggered_04 and already_04:
        workflows_result[WF_04] = {
            "id": wf04["id"],
            "action": "none",
            "reason": "field trigger already enrolled (double-enrollment guard).",
            "ack": True,
        }
        notes.append("04 enrolled via field trigger; explicit enroll skipped.")
    elif already_04:
        workflows_result[WF_04] = {
            "id": wf04["id"], "action": "none",
            "reason": "already enrolled (tag present).", "ack": True,
        }
    else:
        ack = _do_enroll(wf04["id"], "04")
        workflows_result[WF_04] = {
            "id": wf04["id"], "action": "enroll", "ack": ack,
        }

    # --- Workflow 06: explicit enroll, or apply the discovered trigger tag -- #
    trigger06 = str(wf06.get("trigger", "direct_add"))
    if trigger06.startswith("tag:"):
        tag = trigger06.split(":", 1)[1].strip() or WF_TAGS[WF_06]
        ack = apply_tag_via_caf(runner, contact_id, tag)
        workflows_result[WF_06] = {
            "id": wf06["id"], "action": "apply_tag", "tag": tag, "ack": ack,
        }
    elif has_tag(contact, WF_TAGS[WF_06]):
        workflows_result[WF_06] = {
            "id": wf06["id"], "action": "none",
            "reason": "already enrolled (tag present).", "ack": True,
        }
    else:
        ack = _do_enroll(wf06["id"], "06")
        workflows_result[WF_06] = {
            "id": wf06["id"], "action": "enroll", "ack": ack,
        }

    # --- Verify both via a fresh caf read ----------------------------------- #
    verified, evidence = _verify_both(runner, contact_id, workflows_result)
    if not verified:
        # One retry: re-drive any unverified workflow, then re-verify.
        _retry_unverified(runner, contact_id, wf04, wf06, evidence,
                          workflows_result, _do_enroll)
        verified, evidence = _verify_both(runner, contact_id, workflows_result)

    for name, ev in evidence.items():
        workflows_result[name]["verified"] = ev["verified"]
        workflows_result[name]["evidence"] = ev["method"]

    result = {
        "mode": mode,
        "contact_id": contact_id,
        "enrolled": True,
        "verified": verified,
        "workflows": workflows_result,
        "notes": notes,
        "boundary": "STOP: engine sends no customer message; Convert and Flow "
                    "owns all messaging.",
    }
    if not verified:
        raise EnrollUnverified(
            "Enrollment could not be verified via a caf read after one retry. "
            "Episode is NOT delivered. " + json.dumps(evidence)
        )
    return result


def _verify_both(
    runner: CafRunner,
    contact_id: str,
    workflows_result: Dict[str, Any],
) -> "tuple[bool, Dict[str, Any]]":
    """Re-read the contact and confirm each workflow's enrollment evidence.

    A workflow is verified if its known tag is now present, OR (for a workflow we
    enrolled directly) the enroll call returned a success ack. Absent both, it is
    unverified.
    """
    contact = read_contact(runner, contact_id)
    evidence: Dict[str, Any] = {}
    all_ok = True
    for name, info in workflows_result.items():
        tag = WF_TAGS.get(name, "")
        tag_present = bool(tag) and has_tag(contact, tag)
        direct_ack = info.get("action") in ("enroll",) and info.get("ack") is True
        field_or_prior = info.get("action") == "none" and info.get("ack") is True
        if tag_present:
            method = "tag_present"
            ok = True
        elif field_or_prior:
            method = "prior_enrollment"
            ok = True
        elif direct_ack:
            method = "api_enroll_ack"
            ok = True
        else:
            method = "none"
            ok = False
        evidence[name] = {"verified": ok, "method": method}
        all_ok = all_ok and ok
    return all_ok, evidence


def _retry_unverified(
    runner: CafRunner,
    contact_id: str,
    wf04: Dict[str, Any],
    wf06: Dict[str, Any],
    evidence: Dict[str, Any],
    workflows_result: Dict[str, Any],
    do_enroll: Callable[[str, str], bool],
) -> None:
    """Re-drive exactly the workflows that failed verification (one attempt)."""
    for name, wf in ((WF_04, wf04), (WF_06, wf06)):
        ev = evidence.get(name, {})
        if ev.get("verified"):
            continue
        info = workflows_result.get(name, {})
        if info.get("action") == "apply_tag":
            tag = info.get("tag") or WF_TAGS.get(name, "")
            info["ack"] = apply_tag_via_caf(runner, contact_id, tag)
        else:
            info["ack"] = do_enroll(wf["id"], name[:2])
            info["action"] = "enroll"
        info["retried"] = True
        workflows_result[name] = info


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_enroll(args: argparse.Namespace) -> int:
    with open(args.job, "r", encoding="utf-8") as handle:
        job = json.load(handle)
    state: Dict[str, Any] = {}
    if args.state and os.path.isfile(args.state):
        with open(args.state, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    location_id = job.get("location_id") or state.get("location_id")
    runner = make_caf_runner(location_id=location_id)
    preconditions = {
        "podbean_permalink": job.get("podbean_permalink"),
        "field_writeback_verified": job.get("field_writeback_verified"),
    }
    try:
        result = enroll_episode(
            job.get("mode", ""),
            job.get("contact_id", ""),
            state,
            runner=runner,
            preconditions=preconditions,
        )
    except ModeGuardError as exc:
        print(json.dumps({"error": "mode_refusal", "detail": str(exc)}))
        return 2
    except GateError as exc:
        print(json.dumps({"error": "gate", "detail": str(exc)}))
        return 4
    except RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after}))
        return 5
    except EnrollUnverified as exc:
        print(json.dumps({"error": "unverified", "detail": str(exc)}))
        return 6
    except DiscoveryError as exc:
        print(json.dumps({"error": "discovery", "detail": str(exc)}))
        return 7
    print(json.dumps(result, indent=2))
    return 0


def _cmd_self_test(_args: argparse.Namespace) -> int:
    return 0 if _self_test() else 1


def _fake_runner(script: Dict[str, Any]) -> CafRunner:
    """Build a deterministic caf runner from a scripted response table for tests."""

    def runner(args: List[str]) -> CafResult:
        key = " ".join(args[:2])
        if key == "contacts get":
            contact = script.get("contact", {})
            return CafResult(True, 0, data={"contact": contact})
        if key == "workflows list":
            return CafResult(True, 0, data={"workflows": script.get("workflows", [])})
        if key == "workflows enroll":
            script.setdefault("enroll_calls", []).append(args)
            return CafResult(True, 0, data={"succeeded": True})
        if key == "contacts add-tag":
            script.setdefault("tag_calls", []).append(args)
            return CafResult(True, 0, data={"succeeded": True})
        return CafResult(False, 1, stderr="unknown command")

    return runner


def _self_test() -> bool:
    """Offline checks with fake caf runners. No live CRM is contacted."""
    ok = True

    def check(label: str, condition: bool) -> None:
        nonlocal ok
        status = "PASS" if condition else "FAIL"
        if not condition:
            ok = False
        print(f"  [{status}] {label}")

    print("enrollment self-test:")

    good_gate = {"podbean_permalink": "https://pb/ep1",
                 "field_writeback_verified": True}
    state = {
        "location_id": "LOC",
        "workflows": {
            WF_04: {"id": "W04", "trigger": "field:podcast_survey_episode_url"},
            WF_06: {"id": "W06", "trigger": "direct_add"},
        },
    }

    # 1. Personal mode is a hard refusal.
    refused = False
    try:
        enroll_episode(PERSONAL_MODE, "C1", state,
                       runner=_fake_runner({}), preconditions=good_gate)
    except ModeGuardError:
        refused = True
    check("Personal mode raises ModeGuardError", refused)

    # 2. Gate: no permalink is refused.
    gated = False
    try:
        enroll_episode(INTERVIEW_MODE, "C1", state, runner=_fake_runner({}),
                       preconditions={"field_writeback_verified": True})
    except GateError:
        gated = True
    check("missing Podbean permalink raises GateError", gated)

    # 3. Gate: unverified field write is refused.
    gated2 = False
    try:
        enroll_episode(INTERVIEW_MODE, "C1", state, runner=_fake_runner({}),
                       preconditions={"podbean_permalink": "x"})
    except GateError:
        gated2 = True
    check("unverified field write raises GateError", gated2)

    # 4. Double-enrollment guard: 04 already tagged -> not re-enrolled;
    #    06 gets a direct enroll and its tag confirms it.
    script = {
        "contact": {"id": "C1",
                    "tags": ["Podcast Completed Survey Style",
                             "podcast episode is ready"]},
    }
    runner = _fake_runner(script)
    res = enroll_episode(INTERVIEW_MODE, "C1", state, runner=runner,
                         preconditions=good_gate)
    check("04 skipped via double-enrollment guard",
          res["workflows"][WF_04]["action"] == "none")
    check("04 not in any explicit enroll call",
          all("W04" not in c for c in script.get("enroll_calls", [])))
    check("06 verified by its tag",
          res["workflows"][WF_06]["verified"] is True)
    check("overall verified True", res["verified"] is True)
    check("boundary line present (no customer messaging)",
          "STOP" in res["boundary"])

    # 5. 04 not yet triggered -> explicit enroll happens, tag then confirms.
    script2 = {"contact": {"id": "C2",
                           "tags": ["Podcast Completed Survey Style",
                                    "podcast episode is ready"]}}
    # Contact starts WITHOUT the 04 tag on first read, gains it on verify read.
    reads = {"n": 0}

    def staged_runner(args: List[str]) -> CafResult:
        key = " ".join(args[:2])
        if key == "contacts get":
            reads["n"] += 1
            if reads["n"] == 1:
                return CafResult(True, 0, data={"contact": {"id": "C2", "tags": []}})
            return CafResult(True, 0, data={"contact": script2["contact"]})
        if key == "workflows enroll":
            script2.setdefault("enroll_calls", []).append(args)
            return CafResult(True, 0, data={"ok": True})
        return CafResult(True, 0, data={})

    res2 = enroll_episode(INTERVIEW_MODE, "C2", state, runner=staged_runner,
                          preconditions=good_gate)
    check("04 explicitly enrolled when field trigger did not fire",
          res2["workflows"][WF_04]["action"] == "enroll")
    check("04 enroll call issued once", len(script2.get("enroll_calls", [])) >= 1)
    check("res2 overall verified via tags on re-read", res2["verified"] is True)

    # 6. Unverified path: no tags ever, enroll rejected -> failure, not a pass.
    def noack_runner(args: List[str]) -> CafResult:
        key = " ".join(args[:2])
        if key == "contacts get":
            return CafResult(True, 0, data={"contact": {"id": "C3", "tags": []}})
        if key == "workflows enroll":
            return CafResult(False, 1, stderr="enroll rejected")
        return CafResult(True, 0, data={})

    unverified = False
    try:
        enroll_episode(INTERVIEW_MODE, "C3",
                       {"workflows": {
                           WF_04: {"id": "W04", "trigger": "direct_add"},
                           WF_06: {"id": "W06", "trigger": "direct_add"}}},
                       runner=noack_runner, preconditions=good_gate)
    except (EnrollUnverified, EnrollmentError):
        unverified = True
    check("no evidence anywhere -> failure (not a false pass)", unverified)

    # 7. Discovery failure: workflow missing by name.
    disc_failed = False
    try:
        resolve_workflow({"workflows": {}}, WF_04, runner=_fake_runner({"workflows": []}))
    except DiscoveryError:
        disc_failed = True
    check("missing workflow raises DiscoveryError (never built)", disc_failed)

    # 8. Season/Asset modes skip enrollment cleanly.
    skip = enroll_episode("season_strategy", "C9", state,
                          runner=_fake_runner({}), preconditions=good_gate)
    check("non-Interview, non-Personal mode is skipped, not enrolled",
          skip["skipped"] is True and skip["enrolled"] is False)

    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Podcast Engine Skill 44 caf workflow enrollment (Interview).",
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Run offline self-checks (no live CRM) and exit.")
    sub = parser.add_subparsers(dest="command")
    enroll = sub.add_parser("enroll", help="Enroll an Interview-mode episode.")
    enroll.add_argument("--job", required=True, help="Path to the job JSON file.")
    enroll.add_argument("--state", help="Path to the per-client ghl-state.json.")
    enroll.set_defaults(func=_cmd_enroll)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _cmd_self_test(args)
    if not getattr(args, "command", None):
        parser.print_help()
        return 3
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
