#!/usr/bin/env bash
# qc-launch-conversation-ai.sh — launch Conversation-AI completion gate.
#
# Proves a launch Conversation-AI build is ACTUALLY complete for the exact
# tenant, location, workflow, launch revision and playbook — not that a global
# registry looks tidy. A registry hygiene pass (row exists, files exist) is
# explicitly rejected as completion evidence.
#
# Input is one or more synthetic-local evidence bundles (JSON), schema
# documented in conversation-runtime-contract.md and offer-knowledge.md.
# Everything here is offline: no network, no provider calls, no sends.
#
# Usage:
#   bash qc-launch-conversation-ai.sh --bundle <bundle.json>
#   bash qc-launch-conversation-ai.sh --dir <dir-of-bundles>
#   bash qc-launch-conversation-ai.sh --bundle <b.json> --json
#
# Exit codes: 0 = PASS, 1 = FAIL (problems printed), 2 = usage/IO.

set -uo pipefail

BUNDLE=""
BUNDLE_DIR=""
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) BUNDLE="${2:-}"; shift 2 ;;
    --dir) BUNDLE_DIR="${2:-}"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$BUNDLE" ] && [ -z "$BUNDLE_DIR" ]; then
  echo "qc-launch-conversation-ai: pass --bundle <file.json> or --dir <dir>." >&2
  exit 2
fi

export QC_BUNDLE="$BUNDLE" QC_BUNDLE_DIR="$BUNDLE_DIR" QC_JSON="$JSON_MODE"

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

BUNDLE = os.environ.get("QC_BUNDLE", "")
BUNDLE_DIR = os.environ.get("QC_BUNDLE_DIR", "")
JSON_MODE = os.environ.get("QC_JSON", "0") == "1"

SCHEMA_VERSION = "1.0.0"
REQUIRED_MODES = {
    "faq": ["faq"],
    "booking": ["booking"],
    "checkout": ["checkout"],
    "full": ["faq", "booking", "checkout"],
}
PLAYBOOK = {
    "faq": "faq-playbook.md",
    "booking": "booking-playbook.md",
    "checkout": "checkout-playbook.md",
}
EVIDENCE_KINDS = ("graph_readback", "bot_registration_receipt")
SCENARIOS = (
    "booking_success", "no_availability", "answered_not_booked", "timeout",
    "repeat_reply", "keyword_wake", "stop_opt_out", "human_handoff",
)
# Typed completion values. A required scenario is satisfied only by its exact
# outcome token — any other string (including "failed") is incomplete, even
# with an evidence_ref present. ponytail: single-token outcomes; upgrade to a
# versioned outcome enum when a second consumer needs structured reasons.
SCENARIO_OUTCOMES = {
    "booking_success": ("booked",),
    "no_availability": ("no_availability",),
    "answered_not_booked": ("answered",),
    "timeout": ("timed_out",),
    "repeat_reply": ("answered_once",),
    "keyword_wake": ("reactivated",),
    "stop_opt_out": ("opted_out",),
    "human_handoff": ("handed_off",),
}
KNOWLEDGE_FIELDS = (
    "deliverables", "eligibility", "terms", "payment_schedule",
    "supported_claims", "access",
)
CHANNELS = ("sms", "chat")
LAUNCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def nonempty(value):
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return False


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate(bundle):
    problems = []

    def add(code, message):
        problems.append({"code": code, "problem": message})

    if bundle.get("schema_version") != SCHEMA_VERSION:
        add("SCHEMA", "schema_version must be %r" % SCHEMA_VERSION)

    mode = bundle.get("mode")
    if mode not in REQUIRED_MODES:
        add("MODE", "mode must be one of %s" % ", ".join(sorted(REQUIRED_MODES)))
        return problems

    tenant = bundle.get("tenant") or {}
    launch = bundle.get("launch") or {}
    tenant_id = tenant.get("tenant_id")
    location_id = tenant.get("location_id")
    launch_id = launch.get("launch_id")
    launch_revision = launch.get("launch_revision")
    workflow_id = bundle.get("workflow_id")

    for label, value in (
        ("tenant.tenant_id", tenant_id),
        ("tenant.location_id", location_id),
        ("launch.launch_id", launch_id),
        ("workflow_id", workflow_id),
    ):
        if not nonempty(value):
            add("IDENTITY", "%s must be a nonempty string" % label)
    if nonempty(launch_id) and not LAUNCH_ID_RE.match(launch_id):
        add("IDENTITY", "launch.launch_id must be a launch slug")
    if not is_int(launch_revision) or launch_revision < 1:
        add("IDENTITY", "launch.launch_revision must be an integer >= 1")

    channels = bundle.get("channels")
    if not isinstance(channels, list) or not channels:
        add("CHANNELS", "channels must be a nonempty list")
        channels = []
    else:
        if len(set(channels)) != len(channels):
            add("CHANNELS", "channels must not repeat")
        for channel in channels:
            if channel not in CHANNELS:
                add("CHANNELS", "unsupported channel %r" % (channel,))

    owner = bundle.get("reply_owner") or {}
    owner_kind = owner.get("kind")
    if owner_kind == "openclaw_inbound":
        if not nonempty(owner.get("inbound_path")):
            add("REPLY_OWNER", "openclaw_inbound requires a nonempty inbound_path")
    elif owner_kind == "native_ghl":
        if owner.get("translation_approved") is not True:
            add("REPLY_OWNER_TRANSLATION",
                "native_ghl requires translation_approved=true from the operator")
        binding = owner.get("prompt_binding") or {}
        if not nonempty(binding.get("playbook")):
            add("REPLY_OWNER_TRANSLATION", "native_ghl requires prompt_binding.playbook")
        if not nonempty(binding.get("offer_knowledge_version")):
            add("REPLY_OWNER_TRANSLATION",
                "native_ghl requires prompt_binding.offer_knowledge_version")
    else:
        add("REPLY_OWNER", "exactly one reply owner: kind must be openclaw_inbound or native_ghl")

    enrollment = bundle.get("enrollment") or {}
    for key in ("launch_enrolled", "location_enrolled", "contact_enrolled"):
        if enrollment.get(key) is not True:
            add("ENROLLMENT", "enrollment.%s must be true" % key)
    if enrollment.get("launch_id") != launch_id:
        add("ENROLLMENT", "enrollment.launch_id must match the bundle launch")
    if enrollment.get("location_id") != location_id:
        add("ENROLLMENT", "enrollment.location_id must match the bundle location")

    state = bundle.get("state") or {}
    namespace = state.get("namespace") if isinstance(state.get("namespace"), str) else ""
    expected_prefix = "launch-ai/%s/%s/%s/" % (tenant_id, location_id, launch_id)
    if not namespace.startswith(expected_prefix):
        add("STATE_NAMESPACE",
            "state.namespace must start with %r" % expected_prefix)
    sample_key = state.get("sample_key") if isinstance(state.get("sample_key"), str) else ""
    if not namespace or not sample_key.startswith(namespace.rstrip("/") + "/"):
        add("STATE_KEY", "state.sample_key must live under state.namespace")

    consent = bundle.get("consent") or {}
    for channel in channels:
        record = consent.get(channel)
        if not isinstance(record, dict) or record.get("granted") is not True:
            add("CONSENT", "consent.%s must record granted=true" % channel)
            continue
        for key in ("source", "captured_at"):
            if not nonempty(record.get(key)):
                add("CONSENT", "consent.%s.%s must be nonempty" % (channel, key))
    for channel in consent:
        if channel not in channels:
            add("CONSENT_SCOPE",
                "consent recorded for %r but the channel is not in the launch plan" % (channel,))

    fallback = bundle.get("human_fallback") or {}
    if fallback.get("bounded") is not True:
        add("FALLBACK", "human_fallback.bounded must be true")
    if not nonempty(fallback.get("owner")):
        add("FALLBACK", "human_fallback.owner must name the human who takes over")
    if not nonempty(fallback.get("closure_path")):
        add("FALLBACK", "human_fallback.closure_path must say how the handoff closes")
    turns = fallback.get("max_turns")
    if not is_int(turns) or not 1 <= turns <= 10:
        add("FALLBACK", "human_fallback.max_turns must be an integer 1..10")
    timeout = fallback.get("timeout_minutes")
    if not is_int(timeout) or not 1 <= timeout <= 1440:
        add("FALLBACK", "human_fallback.timeout_minutes must be an integer 1..1440")
    triggers = fallback.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        add("FALLBACK", "human_fallback.triggers must be a nonempty list")

    knowledge = bundle.get("knowledge")
    if not isinstance(knowledge, list) or not knowledge:
        add("KNOWLEDGE", "knowledge must be a nonempty list of versioned offers")
        knowledge = []
    for index, offer in enumerate(knowledge):
        label = "knowledge[%d]" % index
        if not isinstance(offer, dict):
            add("KNOWLEDGE", "%s must be an object" % label)
            continue
        for key in ("offer_id", "version", "updated_at", "escalation_owner"):
            if not nonempty(offer.get(key)):
                add("KNOWLEDGE", "%s.%s must be nonempty" % (label, key))
        for key in KNOWLEDGE_FIELDS:
            if not nonempty(offer.get(key)):
                add("KNOWLEDGE", "%s.%s must be nonempty" % (label, key))
        if offer.get("update_rule") != "operator_published_only":
            add("KNOWLEDGE_UPDATE_RULE",
                "%s.update_rule must be operator_published_only" % label)
        if offer.get("unknown_policy") != "escalate":
            add("KNOWLEDGE_UNKNOWN",
                "%s.unknown_policy must be escalate" % label)
        if offer.get("invention_guard") is not True:
            add("KNOWLEDGE_INVENTION",
                "%s.invention_guard must be true" % label)

    adapters = bundle.get("adapters") or {}
    for adapter_name in REQUIRED_MODES[mode]:
        adapter = adapters.get(adapter_name)
        if not isinstance(adapter, dict):
            add("ADAPTER_MISSING", "mode %r requires a %r adapter" % (mode, adapter_name))
            continue
        for key in ("observed_schema", "bot_registration_receipt"):
            if not nonempty(adapter.get(key)):
                add("ADAPTER", "adapters.%s.%s must be nonempty" % (adapter_name, key))
        for key in ("required_fields", "actions"):
            if not isinstance(adapter.get(key), list) or not adapter.get(key):
                add("ADAPTER", "adapters.%s.%s must be a nonempty list"
                    % (adapter_name, key))
        if adapter.get("saved_graph_readback") is not True:
            add("ADAPTER", "adapters.%s.saved_graph_readback must be true" % adapter_name)

    evidence = bundle.get("evidence")
    if not isinstance(evidence, list):
        add("EVIDENCE", "evidence must be a list")
        evidence = []
    targeted_digests = set()
    for adapter_name in REQUIRED_MODES[mode]:
        playbook = PLAYBOOK[adapter_name]
        candidates = [e for e in evidence if isinstance(e, dict)
                      and e.get("playbook") == playbook]
        if not candidates:
            add("EVIDENCE_MISSING",
                "no target-specific evidence for playbook %r" % playbook)
            continue
        global_only = [e for e in candidates
                       if e.get("scope") == "global" or e.get("global_registry_hygiene") is True]
        targeted = []
        for entry in candidates:
            if entry in global_only:
                continue
            if entry.get("tenant_id") != tenant_id:
                continue
            if entry.get("location_id") != location_id:
                continue
            if entry.get("workflow_id") != workflow_id:
                continue
            if entry.get("launch_id") != launch_id:
                continue
            if entry.get("launch_revision") != launch_revision:
                continue
            if not is_int(entry.get("records")) or entry.get("records") < 1:
                continue
            if not nonempty(entry.get("digest")):
                continue
            targeted.append(entry)
            if isinstance(entry.get("digest"), str) and entry["digest"].strip():
                targeted_digests.add(entry["digest"])
        if not targeted:
            if global_only:
                add("EVIDENCE_GLOBAL",
                    "playbook %r has only global registry hygiene evidence; "
                    "it never satisfies launch completion" % playbook)
            else:
                add("EVIDENCE_TARGET",
                    "playbook %r evidence does not match the exact tenant, location, "
                    "workflow, launch revision" % playbook)
            continue
        kinds = {entry.get("kind") for entry in targeted}
        if "graph_readback" not in kinds:
            add("EVIDENCE_READBACK",
                "playbook %r lacks a saved graph readback record" % playbook)
        if "bot_registration_receipt" not in kinds:
            add("EVIDENCE_RECEIPT",
                "playbook %r lacks a registered bot receipt" % playbook)

    scenarios = bundle.get("scenarios") or {}
    for name in SCENARIOS:
        scenario = scenarios.get(name)
        if not isinstance(scenario, dict):
            add("SCENARIO_MISSING", "scenario %r is missing" % name)
            continue
        for key in ("outcome", "evidence_ref"):
            if not nonempty(scenario.get(key)):
                add("SCENARIO", "scenarios.%s.%s must be nonempty" % (name, key))
        expected = SCENARIO_OUTCOMES[name]
        if scenario.get("outcome") not in expected:
            add("SCENARIO_OUTCOME",
                "scenarios.%s.outcome must be %s (got %r); "
                "a failed required scenario never satisfies completion"
                % (name, " or ".join(repr(v) for v in expected),
                   scenario.get("outcome")))
        ref = scenario.get("evidence_ref")
        if nonempty(ref) and ref not in targeted_digests:
            add("SCENARIO_EVIDENCE",
                "scenarios.%s.evidence_ref must equal the digest of this "
                "bundle's targeted %s evidence" % (name, name))
        if name == "human_handoff":
            for key in ("observable_owner", "closure_path"):
                if not nonempty(scenario.get(key)):
                    add("SCENARIO_HANDOFF",
                        "scenarios.human_handoff.%s must be nonempty" % key)

    probes = bundle.get("qa_probes")
    if not isinstance(probes, list) or len(probes) < 30:
        got = len(probes) if isinstance(probes, list) else 0
        add("PROBES_COUNT", "qa_probes must hold at least 30 buyer questions (got %d)" % got)
        probes = probes if isinstance(probes, list) else []
    for index, probe in enumerate(probes):
        label = "qa_probes[%d]" % index
        if not isinstance(probe, dict):
            add("PROBE", "%s must be an object" % label)
            continue
        if not nonempty(probe.get("question")):
            add("PROBE", "%s.question must be nonempty" % label)
        outcome = probe.get("outcome")
        if outcome == "grounded":
            if not nonempty(probe.get("grounded_ref")):
                add("PROBE_GROUNDING", "%s is grounded but names no grounded_ref" % label)
        elif outcome == "escalated":
            if not nonempty(probe.get("escalation_owner")):
                add("PROBE_ESCALATION", "%s escalates but names no escalation_owner" % label)
        else:
            add("PROBE", "%s.outcome must be grounded or escalated" % label)
        if probe.get("config_mutation") is not False:
            add("PROBE_MUTATION", "%s must keep config_mutation=false" % label)
        category = probe.get("category")
        if category == "injection" and outcome != "escalated":
            add("PROBE_INJECTION",
                "%s injection probe must escalate, never obey" % label)
        if category == "price_change":
            matches = probe.get("reported_price_matches_plan")
            if matches is False and outcome != "escalated":
                add("PROBE_PRICE_CHANGE",
                    "%s reports a divergent price and must escalate" % label)
            if matches is True and (outcome != "grounded"
                                    or not nonempty(probe.get("grounded_ref"))):
                add("PROBE_PRICE_CHANGE",
                    "%s restates the plan price only as a grounded answer" % label)

    isolation = bundle.get("isolation") or {}
    launches = isolation.get("launches")
    if not isinstance(launches, list) or len(launches) < 2 or len(set(launches)) != len(launches):
        add("ISOLATION", "isolation.launches must list at least two distinct launches")
    elif launch_id not in launches:
        add("ISOLATION", "isolation.launches must include this bundle's launch")
    if isolation.get("unrelated_support_isolated") is not True:
        add("ISOLATION", "isolation.unrelated_support_isolated must be true")
    if isolation.get("false_booking_success") is not False:
        add("FALSE_BOOKING_SUCCESS",
            "isolation.false_booking_success must be false for unrelated support")

    live_effects = bundle.get("live_effects", [])
    if live_effects != []:
        add("LIVE_EFFECTS", "live_effects must be empty — this lane sends nothing")

    staging = bundle.get("staging")
    if isinstance(staging, dict):
        authorized = staging.get("authorized_account")
        result = staging.get("result")
        if authorized is not True:
            if result != "blocked" or not nonempty(staging.get("reason")):
                add("STAGING_BYPASS",
                    "staging without a separately authorized account must be blocked "
                    "with a precise reason")
        elif result not in ("pass", "fail"):
            add("STAGING", "staging.result must be pass or fail")

    return problems


def load_bundles():
    paths = []
    if BUNDLE:
        paths.append(Path(BUNDLE))
    if BUNDLE_DIR:
        directory = Path(BUNDLE_DIR)
        if not directory.is_dir():
            print("qc-launch-conversation-ai: no such dir: %s" % directory, file=sys.stderr)
            raise SystemExit(2)
        paths.extend(sorted(directory.glob("*.json")))
    return paths


def main():
    paths = load_bundles()
    if not paths:
        print("qc-launch-conversation-ai: no bundles found.", file=sys.stderr)
        return 2

    results = []
    for path in paths:
        try:
            bundle = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            results.append({
                "bundle": str(path),
                "verdict": "FAIL",
                "problems": [{"code": "IO", "problem": str(exc)}],
            })
            continue
        problems = validate(bundle)
        results.append({
            "bundle": str(path),
            "verdict": "PASS" if not problems else "FAIL",
            "problems": problems,
        })

    failed = [r for r in results if r["verdict"] == "FAIL"]
    payload = {
        "verdict": "PASS" if not failed else "FAIL",
        "bundles": results,
        "result_count": len(results),
        "fail_count": len(failed),
    }

    if JSON_MODE:
        print(json.dumps(payload, indent=2))
    else:
        print("=== qc-launch-conversation-ai: launch completion gate ===")
        for result in results:
            print("")
            print("bundle: %s" % result["bundle"])
            print("  verdict: %s" % result["verdict"])
            for problem in result["problems"]:
                print("    [%s] %s" % (problem["code"], problem["problem"]))
        print("")
        if failed:
            print("RESULT: FAIL — %d of %d bundle(s) incomplete." % (len(failed), len(results)))
        else:
            print("RESULT: PASS — %d bundle(s) complete for their exact targets." % len(results))

    return 1 if failed else 0


sys.exit(main())
PYEOF
