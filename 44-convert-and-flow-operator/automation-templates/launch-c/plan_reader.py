#!/usr/bin/env python3
# =============================================================================
# LAUNCH-C — PLAN READER :: Skill 50 build plans -> launch automation builds
# -----------------------------------------------------------------------------
# Reads the U-CONTRACT launch plan (shared-utils/signature_launch_contract) and
# the Skill 50 P4 build plan(s) (50-email-engine/schema/build-plan.schema.json)
# and emits ONE automation-build document for the automation lanes (WF-AUTO-*).
#
# Deterministic, stdlib-only, model-free, DRAFT-ONLY. It never sends, never
# calls a provider, and never publishes: every workflow it carries must already
# be status "draft" in the Skill 50 plan or the read FAILS CLOSED.
#
# USAGE
#   plan_reader.py --launch-plan plan.json --build-plan pre.json [--build-plan ...]
#                  [--sequence-map map.json] --out automation-builds.json
#   plan_reader.py --selftest
#
#   map.json: {"email_pre_launch": "path/to/build-plan.json", ...}
#   Without a map, each build plan is bound to a launch email_sequence by
#   _meta.sequence_id / _meta.source_ids.sequence_id, then by file stem, then by
#   the single sequence id its workflow keys/names/tags name. Ambiguity fails.
#
# EXIT CODES: 0 ok / 2 usage-or-structural-invalid / 3 IO
# =============================================================================
"""Skill 50 build plans -> launch automation builds (launch-c)."""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3

SCHEMA_VERSION = "1.0.0"

FAMILIES = {
    "pre_launch", "opt_in", "event_reminders", "post_sale", "upsell_downsell",
    "abandoned_checkout", "page_retargeting", "onboarding_review", "win_back",
    "failed_payment", "conversation_ai_reply",
}
RAILS = {"ghl_api", "skill44_engine", "unknown"}
STEP_TYPES = {"email", "wait"}
UNIT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
LAUNCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# Credential-shaped keys must never travel in a plan; sender configuration is a
# named reference and binds under a *_ref key.
CREDENTIAL_KEY_RE = re.compile(
    r"(password|passwd|secret|api[-_]?key|credential|private[-_]?key|(^|_)token(_|$))",
    re.IGNORECASE,
)


class ReaderError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _fail(code, message):
    raise ReaderError(code, message)


# ----------------------------------------------------------------------------- IO
def load_json(path, label):
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        _fail("IO", "%s %s: %s" % (label, p, exc))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail("INVALID-JSON", "%s %s: %s" % (label, p, exc))


def _walk_keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            here = "%s.%s" % (path, key) if path else str(key)
            yield here, key
            for item in _walk_keys(value, here):
                yield item
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            for item in _walk_keys(value, "%s[%d]" % (path, idx)):
                yield item


def reject_credentials(doc, label):
    for where, key in _walk_keys(doc):
        if key.lower().endswith("_ref"):
            continue
        if CREDENTIAL_KEY_RE.search(str(key)):
            _fail("CREDENTIAL-IN-PLAN", "%s carries credential-shaped key %r at %s" % (label, key, where))


# ------------------------------------------------------------------- launch plan
def _require(cond, code, message):
    if not cond:
        _fail(code, message)


def read_launch_plan(plan, source="launch-plan"):
    _require(isinstance(plan, dict), "LAUNCH-PLAN-SHAPE", "%s is not an object" % source)
    _require(plan.get("schema_version") == SCHEMA_VERSION,
             "LAUNCH-PLAN-VERSION", "schema_version must be %r" % SCHEMA_VERSION)
    launch_id = plan.get("launch_id")
    _require(isinstance(launch_id, str) and LAUNCH_ID_RE.match(launch_id),
             "LAUNCH-PLAN-ID", "launch_id is missing or malformed")

    units = {}          # id -> kind
    email_sequences = {}  # id -> sequence object (insertion order = plan order)
    automations = []

    for kind in ("pages", "email_sequences", "text_sets", "automations"):
        items = plan.get(kind)
        _require(isinstance(items, list), "LAUNCH-PLAN-SHAPE", "%s must be a list" % kind)
        for item in items:
            _require(isinstance(item, dict), "LAUNCH-PLAN-SHAPE", "%s entry is not an object" % kind)
            unit_id = item.get("id")
            _require(isinstance(unit_id, str) and UNIT_ID_RE.match(unit_id),
                     "LAUNCH-PLAN-UNIT-ID", "%s unit id %r is malformed" % (kind, unit_id))
            _require(unit_id not in units, "LAUNCH-PLAN-DUPLICATE-ID",
                     "unit id %r appears twice" % unit_id)
            units[unit_id] = kind
            if kind == "email_sequences":
                _require(item.get("draft_only") is True,
                         "LAUNCH-PLAN-NOT-DRAFT", "email sequence %r is not draft_only" % unit_id)
                email_sequences[unit_id] = item

    # waits_for resolution + acyclicity over every unit.
    edges = {unit_id: [] for unit_id in units}
    for kind in ("pages", "email_sequences", "text_sets", "automations"):
        for item in plan[kind]:
            waits = item.get("waits_for")
            _require(isinstance(waits, list), "LAUNCH-PLAN-WAITS",
                     "%s %r waits_for must be a list" % (kind, item["id"]))
            for dep in waits:
                _require(dep in units, "LAUNCH-PLAN-UNRESOLVED-WAITS",
                         "%s %r waits for unknown unit %r" % (kind, item["id"], dep))
                edges[item["id"]].append(dep)
    _assert_acyclic(edges)

    for item in plan["automations"]:
        unit_id = item["id"]
        family = item.get("family")
        _require(family in FAMILIES, "LAUNCH-PLAN-FAMILY",
                 "automation %r family %r is not canonical" % (unit_id, family))
        rail = item.get("build_rail")
        _require(rail in RAILS, "LAUNCH-PLAN-RAIL",
                 "automation %r build_rail %r is not canonical" % (unit_id, rail))
        _require(item.get("draft_only") is True,
                 "LAUNCH-PLAN-NOT-DRAFT", "automation %r is not draft_only" % unit_id)
        trigger = item.get("trigger")
        _require(isinstance(trigger, dict) and isinstance(trigger.get("type"), str) and trigger["type"],
                 "LAUNCH-PLAN-TRIGGER", "automation %r trigger.type is missing" % unit_id)
        automations.append(item)

    return {
        "launch_id": launch_id,
        "units": units,
        "email_sequences": email_sequences,
        "automations": automations,
    }


def _assert_acyclic(edges):
    indegree = {node: 0 for node in edges}
    forward = {node: [] for node in edges}
    for node, deps in edges.items():
        for dep in deps:
            forward[dep].append(node)
            indegree[node] += 1
    ready = [node for node, deg in indegree.items() if deg == 0]
    seen = 0
    while ready:
        node = ready.pop()
        seen += 1
        for nxt in forward[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if seen != len(edges):
        _fail("LAUNCH-PLAN-CYCLE", "waits_for graph contains a cycle")


# ------------------------------------------------------------------- build plan
def read_build_plan(doc, source):
    """Validate one Skill 50 P4 build plan and return its workflows verbatim."""
    _require(isinstance(doc, dict), "BUILD-PLAN-SHAPE", "%s is not an object" % source)
    folder = doc.get("folder")
    _require(isinstance(folder, str) and folder.strip(), "BUILD-PLAN-FOLDER",
             "%s has no folder" % source)
    reject_credentials(doc, source)

    meta = doc.get("_meta")
    if isinstance(meta, dict):
        if "draft_only" in meta:
            _require(meta["draft_only"] is True, "BUILD-PLAN-NOT-DRAFT",
                     "%s _meta.draft_only must be true" % source)
        if "deploy_mode" in meta:
            _require(meta["deploy_mode"] == "draft-only", "BUILD-PLAN-NOT-DRAFT",
                     "%s _meta.deploy_mode must be 'draft-only'" % source)

    workflows = []
    for key, workflow in doc.items():
        if key in ("folder", "_meta"):
            continue
        where = "%s#%s" % (source, key)
        _require(isinstance(workflow, dict), "BUILD-PLAN-SHAPE", "%s is not an object" % where)
        _require(isinstance(workflow.get("name"), str) and workflow["name"].strip(),
                 "BUILD-PLAN-WORKFLOW-NAME", "%s has no name" % where)
        status = workflow.get("status", "draft")
        _require(status == "draft", "BUILD-PLAN-NOT-DRAFT",
                 "%s status %r is not 'draft'; nothing but a draft may be read" % (where, status))
        templates = workflow.get("templates")
        _require(isinstance(templates, list) and templates, "BUILD-PLAN-STEPS",
                 "%s has no templates" % where)
        email_count = wait_count = 0
        for idx, step in enumerate(templates):
            _validate_step(step, "%s step %d" % (where, idx))
            if step["type"] == "email":
                email_count += 1
            else:
                wait_count += 1
        workflows.append({
            "key": key,
            "name": workflow["name"],
            "tag": workflow.get("tag"),
            "status": status,
            "folder": folder,
            "email_count": email_count,
            "wait_count": wait_count,
            "steps": templates,
        })
    _require(workflows, "BUILD-PLAN-EMPTY", "%s carries no workflows" % source)
    return workflows


def _validate_step(step, where):
    _require(isinstance(step, dict), "BUILD-PLAN-STEP", "%s is not an object" % where)
    _require(isinstance(step.get("id"), str) and step["id"], "BUILD-PLAN-STEP-ID",
             "%s has no id" % where)
    _require(isinstance(step.get("name"), str) and step["name"], "BUILD-PLAN-STEP-NAME",
             "%s has no name" % where)
    step_type = step.get("type")
    _require(step_type in STEP_TYPES, "BUILD-PLAN-STEP-TYPE",
             "%s type %r is not email|wait" % (where, step_type))
    attrs = step.get("attributes")
    _require(isinstance(attrs, dict), "BUILD-PLAN-STEP-ATTRS", "%s has no attributes" % where)
    if step_type == "email":
        for field in ("subject", "body", "html"):
            _require(isinstance(attrs.get(field), str) and attrs[field].strip(),
                     "BUILD-PLAN-EMAIL-ATTRS", "%s email is missing %s" % (where, field))
        _require(isinstance(attrs.get("fromName"), str), "BUILD-PLAN-EMAIL-ATTRS",
                 "%s email is missing fromName" % where)
    else:
        start = attrs.get("startAfter")
        _require(isinstance(start, dict), "BUILD-PLAN-WAIT-ATTRS",
                 "%s wait is missing startAfter" % where)
        for field in ("type", "when"):
            _require(isinstance(start.get(field), str) and start[field],
                     "BUILD-PLAN-WAIT-ATTRS", "%s wait startAfter.%s is missing" % (where, field))
        _require(isinstance(start.get("value"), int) and start["value"] >= 0,
                 "BUILD-PLAN-WAIT-ATTRS", "%s wait startAfter.value must be a non-negative integer" % where)


# ---------------------------------------------------------------- sequence bind
def _meta_sequence_id(doc):
    meta = doc.get("_meta")
    if not isinstance(meta, dict):
        return None
    if meta.get("sequence_id"):
        return meta["sequence_id"]
    src = meta.get("source_ids")
    if isinstance(src, dict) and src.get("sequence_id"):
        return src["sequence_id"]
    return None


def bind_build_plans(paths, email_sequence_ids, explicit_map):
    """Bind each build plan to exactly one launch email_sequence id."""
    seq_ids = list(email_sequence_ids)
    bound = {}      # seq id -> (path, doc, workflows)
    explicit = {str(Path(p).resolve()): seq for seq, p in explicit_map.items()}
    problems = []

    for path in paths:
        doc = load_json(path, "build-plan")
        workflows = read_build_plan(doc, str(path))
        resolved = Path(path).resolve()

        seq = explicit.get(str(resolved))
        if seq is not None:
            _require(seq in email_sequence_ids, "SEQUENCE-MAP-UNKNOWN",
                     "--sequence-map names unknown email_sequence %r" % seq)

        if seq is None:
            candidates = []
            meta_seq = _meta_sequence_id(doc)
            if meta_seq in email_sequence_ids:
                candidates.append(meta_seq)
            stem = resolved.stem.lower()
            if stem in email_sequence_ids:
                candidates.append(stem)
            else:
                hits = [sid for sid in seq_ids if sid in stem]
                if len(hits) == 1:
                    candidates.append(hits[0])
            if not candidates:
                hits = set()
                for workflow in workflows:
                    blob = " ".join(str(workflow.get(f) or "") for f in ("key", "name", "tag")).lower()
                    hits.update(sid for sid in seq_ids if sid in blob)
                if len(hits) == 1:
                    candidates.append(hits.pop())
            unique = sorted(set(candidates))
            if len(unique) > 1:
                _fail("SEQUENCE-BIND-AMBIGUOUS",
                      "%s could belong to %s; pass --sequence-map" % (path, unique))
            if not unique:
                problems.append({"build_plan": str(path),
                                 "reason": "no launch email_sequence matches",
                                 "workflows": [w["key"] for w in workflows]})
                continue
            seq = unique[0]

        if seq in bound:
            _fail("SEQUENCE-BIND-DUPLICATE",
                  "two build plans claim email_sequence %r: %s and %s" % (seq, bound[seq][0], path))
        bound[seq] = (str(path), doc, workflows)

    return bound, problems


# ----------------------------------------------------------------------- builder
def build_document(plan_path, plan, bound, unbound, warnings):
    email_sequences = plan["email_sequences"]
    builds = []
    for automation in plan["automations"]:
        refs = [dep for dep in automation["waits_for"] if dep in email_sequences]
        workflows = []
        missing = []
        for seq_id in refs:
            if seq_id not in bound:
                missing.append(seq_id)
                continue
            workflows.extend(bound[seq_id][2])
            expected = email_sequences[seq_id].get("email_count")
            got = sum(w["email_count"] for w in bound[seq_id][2])
            if isinstance(expected, int) and expected != got:
                warnings.append({
                    "code": "EMAIL-COUNT-MISMATCH",
                    "automation": automation["id"],
                    "email_sequence": seq_id,
                    "expected": expected,
                    "build_plan_emails": got,
                })
        builds.append({
            "id": automation["id"],
            "family": automation["family"],
            "template": automation.get("template"),
            "build_rail": automation["build_rail"],
            "draft_only": True,
            "trigger": automation["trigger"],
            "waits_for": list(automation["waits_for"]),
            "email_sequences": refs,
            "workflows": workflows,
            "state": "blocked" if missing else "ready",
            "blocked_by": missing,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "launch_id": plan["launch_id"],
        "draft_only": True,
        "sources": {"launch_plan": str(plan_path), "build_plans": sorted(
            path for path, _doc, _wfs in bound.values())},
        "builds": builds,
        "unused_build_plan_workflows": unbound,
        "warnings": warnings,
    }


# -------------------------------------------------------------------------- CLI
def read_sequence_map(path):
    if not path:
        return {}
    doc = load_json(path, "sequence-map")
    _require(isinstance(doc, dict), "SEQUENCE-MAP-SHAPE", "sequence map is not an object")
    for seq, build_path in doc.items():
        _require(isinstance(build_path, str) and build_path, "SEQUENCE-MAP-SHAPE",
                 "sequence map entry %r is not a path" % seq)
    return doc


def run(args):
    plan = load_json(args.launch_plan, "launch-plan")
    parsed = read_launch_plan(plan, args.launch_plan)
    explicit = read_sequence_map(args.sequence_map)
    bound, unbound = bind_build_plans(
        args.build_plan or [], parsed["email_sequences"], explicit)
    return build_document(args.launch_plan, parsed, bound, unbound, [])


def _selftest():
    plan = {
        "schema_version": "1.0.0",
        "launch_id": "selftest-launch",
        "pages": [{"id": "page_landing", "kind": "landing", "url": None, "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
             "email_count": 1, "draft_only": True, "waits_for": []}],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "new",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"}, "waits_for": ["email_pre_launch"]}],
    }
    parsed = read_launch_plan(plan)
    doc = {"folder": "F", "wf": {"name": "wf", "status": "draft", "templates": [
        {"id": "e1", "type": "email", "name": "Email 1", "attributes": {
            "subject": "s", "body": "b", "html": "<p>b</p>", "fromName": "n"}},
        {"id": "w1", "type": "wait", "name": "Wait 1 Days", "attributes": {
            "type": "time", "startAfter": {"type": "days", "value": 1, "when": "after"}}}],
    }}
    workflows = read_build_plan(doc, "selftest")
    bound = {"email_pre_launch": ("selftest", doc, workflows)}
    out = build_document("selftest", parsed, bound, [], [])
    assert out["builds"][0]["state"] == "ready"
    assert out["builds"][0]["workflows"][0]["email_count"] == 1
    assert out["builds"][0]["draft_only"] is True

    bad = json.loads(json.dumps(doc))
    bad["wf"]["status"] = "published"
    try:
        read_build_plan(bad, "selftest")
        raise AssertionError("published workflow was accepted")
    except ReaderError as exc:
        assert exc.code == "BUILD-PLAN-NOT-DRAFT", exc.code

    bad = json.loads(json.dumps(doc))
    bad["wf"]["templates"][0]["attributes"]["api_key"] = "x"
    try:
        read_build_plan(bad, "selftest")
        raise AssertionError("credential key was accepted")
    except ReaderError as exc:
        assert exc.code == "CREDENTIAL-IN-PLAN", exc.code

    cyclic = json.loads(json.dumps(plan))
    cyclic["automations"][0]["waits_for"] = ["auto_pre_launch"]
    try:
        read_launch_plan(cyclic)
        raise AssertionError("cycle was accepted")
    except ReaderError as exc:
        assert exc.code == "LAUNCH-PLAN-CYCLE", exc.code
    print("selftest ok")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read Skill 50 build plans into launch automation builds.")
    parser.add_argument("--launch-plan")
    parser.add_argument("--build-plan", action="append", default=[])
    parser.add_argument("--sequence-map")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return EXIT_OK
    if not args.launch_plan or not args.out:
        parser.error("--launch-plan and --out are required")

    try:
        document = run(args)
        Path(args.out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except ReaderError as exc:
        print("plan-reader: %s" % exc, file=sys.stderr)
        return EXIT_IO if exc.code == "IO" else EXIT_INVALID
    except OSError as exc:
        print("plan-reader: IO: %s" % exc, file=sys.stderr)
        return EXIT_IO
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
