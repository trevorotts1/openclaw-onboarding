#!/usr/bin/env python3
"""999 package adapter (S75-T30 / S75-A30). Stdlib only.

The 999 flavour's own package adapter. It assembles the package from what the
tree it runs in actually carries and proves the assembly instead of assuming the
primary flavour's layout.

One clause per sentence of S75-A30, plus the two clauses the primary flavour's
manifest carries that the 999 set must not drop:

  resolve()                  the 999 flavour through the S75-T03 seam (consumed,
                             never re-derived); refuses when the manifest
                             disagrees with it
  requirements()             the primary flavour's clause set is read from the
                             primary manifest in the tree (digest-checked), every
                             row is carried by a live carrier whose probe LOADS
                             it, or declared absent with the unit that owes it
  own_adapters()             the 999 entrypoint is this package's own; it never
                             imports onboarding_adapter and never runs
                             scripts/openclaw_adapter.py
  reachability()             the 999 entrypoint's static import closure and its
                             real running process both load every product carrier
  entrypoints()              advertised commands are a subset of what factory.py
                             really implements; every argv is complete; every
                             citation is verified against the file and line it
                             names; excluded steps are re-run, so a false
                             "unsupported" claim fails
  check()                    one envelope over all of it, exit 0 or 1

The advertised check EXECUTES every advertised step. `--execute` is accepted as
a no-op alias so older callers keep working; a fabricated recorded exit code
cannot satisfy the no-missing-steps clause because the real exit is compared.

No write path, no network, no paid call, no generation. Importing the module has
no lasting side effect: sys.path is restored.

Run: python3 package/999_adapter.py check [--execute] [--skill-root PATH]
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(PACKAGE_DIR)

SCHEMA = "s75.n999-adapter-check.v2"
FLAVOR = "999"
N999_SUFFIX = os.path.join(".claude", "skills", "drama-song-ad-factory")
SOURCE_ANCHOR = "75-drama-song-ad-factory"
PRIMARY_ADAPTER_MODULE = "onboarding_adapter"
PRIMARY_WRAPPER = "scripts/openclaw_adapter.py"
FACTORY_REL = os.path.join("scripts", "core", "intake_preflight", "factory.py")
ENTRYPOINT_REL = os.path.join("package", "999_entrypoint.py")
PRIMARY_MANIFEST_REL = os.path.join("tests", "fixtures",
                                    "primary-flavour-manifest.json")

#: A token that means the step was never finished. A fixture may not advertise one.
PLACEHOLDER_TOKENS = ("...", "…", "TODO", "TBD")

#: Tokens the runner substitutes. Anything else wrapped in braces is unresolved.
ALLOWED_TOKENS = ("{python}", "{skill_root}", "{work}")

#: The five held factory/approval files (S75-T01 handoff, owner UNKNOWN). This
#: adapter reads two of them as data and writes none of them.
HELD_FILES = (
    os.path.join("scripts", "core", "intake_preflight", "factory.py"),
    os.path.join("scripts", "core", "lyric_writer", "lyric_writer.py"),
    os.path.join("scripts", "core", "character_bible", "character_approval.py"),
    os.path.join("scripts", "core", "method_plan", "method_plan.py"),
    os.path.join("scripts", "core", "registry.json"),
)

#: Module-level names the checker must never import from a held file.
HELD_MODULE_IMPORTS = ("factory", "lyric_writer", "character_approval",
                       "intake_preflight")

#: Set while a nested check runs, so the advertised `package/999_adapter.py
#: check` row cannot recurse.
NESTED_ENV = "S75_999_NESTED"


class AdapterError(Exception):
    """The package layout cannot support what the manifest declares."""


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _on_path(path):
    added = path not in sys.path
    if added:
        sys.path.insert(0, path)
    try:
        yield
    finally:
        if added:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def _core_dir(skill_root):
    return os.path.join(skill_root, "scripts", "core")


def layout_of(skill_root):
    """Which physical tree is this? '999', 'source' or 'unknown'."""
    real = os.path.normpath(os.path.realpath(skill_root))
    if real.endswith(N999_SUFFIX):
        return FLAVOR
    if os.path.basename(real) == SOURCE_ANCHOR:
        return "source"
    return "unknown"


def load_manifest(skill_root=None):
    path = os.path.join(skill_root or SKILL_ROOT, "package", "999-manifest.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_fixture(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    path = os.path.join(root, manifest["entrypoints"]["fixture"])
    if not os.path.isfile(path):
        raise AdapterError("entrypoints fixture %s is absent"
                           % manifest["entrypoints"]["fixture"])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load(skill_root, module):
    with _on_path(_core_dir(skill_root)):
        return importlib.import_module(module)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_strings(value, trail=""):
    """Every string in a JSON value, with a dotted trail for the message."""
    if isinstance(value, str):
        yield trail, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, "%s.%s" % (trail, key) if trail
                                     else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, "%s[%d]" % (trail, index))


# ---------------------------------------------------------------------------
# resolve: the flavour through the accepted seam
# ---------------------------------------------------------------------------

def resolve(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    seam = _load(root, "package_flavor_adapter")
    resolved = seam.resolve(seam.N999)
    declared = manifest["package_differences"]["values"]

    problems = []
    for key in seam.PACKAGE_DIFFERENCES:
        if declared.get(key) != resolved.get(key):
            problems.append("manifest %s %r disagrees with the seam %r"
                            % (key, declared.get(key), resolved.get(key)))
    if resolved["flavor"] != FLAVOR:
        problems.append("seam resolved flavour %r" % (resolved["flavor"],))
    if resolved["skill_root_anchor"] != manifest["skill_root_anchor"]:
        problems.append("seam anchor %r disagrees with the manifest anchor %r"
                        % (resolved["skill_root_anchor"],
                           manifest["skill_root_anchor"]))

    layout = layout_of(root)
    physical = os.path.basename(os.path.normpath(os.path.realpath(root)))
    if layout == FLAVOR:
        if not os.path.normpath(os.path.realpath(root)).endswith(
                os.path.normpath(resolved["skill_root_anchor"])):
            problems.append("999 layout at %s does not end with the seam anchor"
                            % root)
    elif layout == "source":
        if physical != SOURCE_ANCHOR:
            problems.append("source layout root %r is not %r"
                            % (physical, SOURCE_ANCHOR))
        if seam.resolve(seam.ONB)["skill_root_anchor"] != SOURCE_ANCHOR:
            problems.append("the seam's primary anchor is not %r" % SOURCE_ANCHOR)
    else:
        problems.append("skill root %s matches neither flavour anchor" % root)

    return {
        "layout": layout,
        "physical_anchor": physical,
        "seam": resolved["seam"],
        "flavor": resolved["flavor"],
        "core_module": resolved["core_module"],
        "core_schema_version": resolved["core_schema_version"],
        "core_stage_count": resolved["core_stage_count"],
        "core_digest": resolved["core_digest"],
        "package_differences": {k: resolved[k]
                                for k in seam.PACKAGE_DIFFERENCES},
        "problems": problems,
        "ok": not problems,
    }


# ---------------------------------------------------------------------------
# the requirement set: read from the PRIMARY flavour's manifest in the tree
# ---------------------------------------------------------------------------

def primary_requirement_ids(skill_root=None):
    """The primary flavour's clause ids, read from its manifest in this tree.

    The primary manifest is not present at this base commit (S75-T29 ships it on
    its own branch), so the package carries a byte-identical copy under
    tests/fixtures/ and pins its sha256 in package/999-manifest.json. A copy
    that stops matching the pinned digest fails closed.
    """
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    declared = manifest["primary_flavour"]
    path = os.path.join(root, declared["path"])

    problems = []
    if not os.path.isfile(path):
        return [], ["primary flavour manifest %s is absent" % declared["path"]]
    actual = _sha256(path)
    if actual != declared["sha256"]:
        problems.append("primary flavour manifest sha256 %s != pinned %s"
                        % (actual, declared["sha256"]))
    with open(path, encoding="utf-8") as fh:
        primary = json.load(fh)
    clauses = primary.get(declared.get("clause_key") or "clauses")
    if not isinstance(clauses, dict) or not clauses:
        problems.append("primary flavour manifest carries no clause object")
        return [], problems
    return list(clauses.keys()), problems


def requirements(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    rows = manifest.get("product_requirements") or []
    problems = []
    reported = []

    declared_ids = [r.get("id") for r in rows]
    primary_ids, primary_problems = primary_requirement_ids(root)
    problems.extend(primary_problems)

    # No requirement the primary flavour carries may be dropped.
    missing_primary = [i for i in primary_ids if i not in declared_ids]
    if missing_primary:
        problems.append("requirement set drops primary clause(s) %s"
                        % missing_primary)

    # Extra rows are allowed only as declared additions with a witness.
    additions = {a.get("id"): a for a in manifest.get("requirement_additions")
                 or []}
    extras = [i for i in declared_ids if i not in primary_ids]
    for extra in extras:
        addition = additions.get(extra)
        if not addition:
            problems.append("requirement %r is not a primary clause and is not "
                            "declared in requirement_additions" % extra)
            continue
        for key in ("why_not_in_primary", "witness"):
            if not addition.get(key):
                problems.append("addition %r has no %s" % (extra, key))
    for addition_id in additions:
        if addition_id not in declared_ids:
            problems.append("declared addition %r has no product requirement row"
                            % addition_id)

    seam = None
    for row in rows:
        state = row.get("state")
        carriers = row.get("carriers") or []
        carrier_modules = row.get("carrier_modules") or []
        absent = row.get("absent") or []
        detail = {"id": row.get("id"), "state": state,
                  "primary_clause": row.get("id") in primary_ids}

        if state not in ("carried", "partial", "absent"):
            problems.append("%s: unknown state %r" % (row.get("id"), state))
            reported.append(detail)
            continue

        if state in ("carried", "partial"):
            missing = [c for c in carriers
                       if not os.path.isfile(os.path.join(root, c))]
            if missing:
                problems.append("%s: declared %s but carrier(s) absent: %s"
                                % (row.get("id"), state, missing))
            detail["carriers"] = list(carriers)
            probe_name = row.get("probe")
            if not probe_name:
                problems.append("%s: no probe named" % (row.get("id"),))
            else:
                probe = _run_probe(probe_name, root, manifest, seam)
                if seam is None:
                    seam = _maybe_seam(root)
                detail["probe"] = probe
                if not probe.get("pass"):
                    problems.append("%s: probe %r did not hold"
                                    % (row.get("id"), probe_name))
                # A declared carrier must be LOADED by the probe, not merely
                # present on disk. This is what round 1 missed.
                loaded = set(probe.get("loaded_modules") or [])
                unloaded = [m for m in carrier_modules if m not in loaded]
                if unloaded:
                    problems.append("%s: probe %r never loaded declared "
                                    "carrier module(s) %s"
                                    % (row.get("id"), probe_name, unloaded))
        elif carriers:
            problems.append("%s: declared absent but still lists carriers"
                            % (row.get("id"),))

        if state in ("partial", "absent"):
            if not absent:
                problems.append("%s: declared %s with nothing named absent"
                                % (row.get("id"), state))
            for gap in absent:
                for key in ("carrier", "owed_by", "missing_capability",
                            "upgrade_path"):
                    if not gap.get(key):
                        problems.append("%s: absent entry has no %s"
                                        % (row.get("id"), key))
                carrier = gap.get("carrier")
                if carrier and os.path.isfile(os.path.join(root, carrier)):
                    problems.append("%s: declared %s absent but %s is present"
                                    % (row.get("id"), carrier, carrier))
            detail["absent"] = [{"carrier": g.get("carrier"),
                                 "owed_by": g.get("owed_by")} for g in absent]
        elif absent:
            problems.append("%s: declared %s but still names absent carriers"
                            % (row.get("id"), state))

        reported.append(detail)

    return {
        "rows": reported,
        "primary_clause_ids": primary_ids,
        "declared_additions": sorted(additions),
        "dropped_primary_clauses": missing_primary,
        "problems": problems,
        "ok": not problems,
    }


def _maybe_seam(skill_root):
    try:
        return _load(skill_root, "package_flavor_adapter")
    except ImportError:
        return None


def _run_probe(name, skill_root, manifest, seam):
    if name == "notion_present_carriers":
        return _probe_notion_present_carriers(skill_root, manifest)
    if name == "flavor_parity":
        return _probe_flavor_parity(seam or _load(skill_root,
                                                  "package_flavor_adapter"))
    if name == "styles_18":
        return _probe_styles_18(_load(skill_root, "music_styles.catalog"))
    if name == "entrypoint_reachability":
        return _probe_entrypoint_reachability(skill_root)
    if name == "emergency_fixes_read_only":
        return _probe_emergency_fixes_read_only(skill_root)
    core = _load(skill_root, "story_first_contracts")
    if name == "cast_world_script_gates":
        return _probe_cast_world_script_gates(
            core, _load(skill_root, "character_bible.identity"))
    probes = {
        "artifact_order": _probe_artifact_order,
        "approval_ordering": _probe_approval_ordering,
    }
    return probes[name](core)


# ---------------------------------------------------------------------------
# requirement probes. Each one can fail; none is a restatement of the carrier.
# ---------------------------------------------------------------------------

def _probe_artifact_order(core):
    registry = core.RunRegistry()
    try:
        core.check_stage("script_lyrics", registry)
    except core.ContractError as exc:
        missing = set(exc.packet.get("missing") or [])
    else:
        return {"pass": False, "why": "an empty registry admitted script_lyrics"}
    required = set(core.STAGE_REQUIRES.get("script_lyrics") or ())
    return {
        "pass": bool(required) and required <= missing,
        "required": sorted(required),
        "refused_missing": sorted(missing),
        "loaded_modules": ["story_first_contracts"],
    }


def _probe_cast_world_script_gates(core, identity):
    cast_defects = core.validate_cast_manifest({}) or []
    placeholder = {
        "scene_id": "s1", "purpose": "x", "action": "y", "location_id": "loc1",
        "cast": [], "lines": [{"speaker": "a", "text": "hi"}],
    }
    scene_defects = core.validate_scene(placeholder) or []
    fields = sorted({d.get("field") for d in scene_defects})
    identity_probe = _probe_identity_gates(identity)
    return {
        "pass": bool(cast_defects) and "dialogue" in fields
                and "duration_seconds" in fields and identity_probe["pass"],
        "empty_cast_refused": bool(cast_defects),
        "placeholder_scene_defect_fields": fields,
        "identity": identity_probe,
        "loaded_modules": ["story_first_contracts", "character_bible.identity"],
    }


def _probe_identity_gates(identity):
    """Load character_bible.identity and make it refuse bad records."""
    refusals = {}
    for name in ("validate_library", "validate_episode_setting",
                 "validate_identity"):
        fn = getattr(identity, name, None)
        if not callable(fn):
            return {"pass": False, "why": "%s is not callable" % name,
                    "loaded_modules": ["character_bible.identity"]}
        try:
            fn({})
        except Exception as exc:  # noqa: BLE001 - the refusal IS the evidence
            refusals[name] = type(exc).__name__
        else:
            return {"pass": False, "why": "%s admitted an empty record" % name,
                    "loaded_modules": ["character_bible.identity"]}
    sealed = getattr(identity, "canonical_digest", None)
    return {
        "pass": callable(sealed) and set(refusals) == {
            "validate_library", "validate_episode_setting", "validate_identity"},
        "refusals": refusals,
        "canonical_digest_callable": callable(sealed),
        "loaded_modules": ["character_bible.identity"],
    }


def _probe_styles_18(catalog):
    ids = list(catalog.STYLE_IDS)
    originals = list(catalog.ORIGINAL_STYLE_IDS)
    return {
        "pass": len(ids) == 18 and len(set(ids)) == 18 and len(originals) == 3
                and originals == ids[:3],
        "style_count": len(ids),
        "unique": len(set(ids)),
        "original_ids": originals,
        "loaded_modules": ["music_styles.catalog"],
    }


def _probe_approval_ordering(core):
    registry = core.RunRegistry()
    for kind in ("research_bundle", "episode_cast_manifest", "episode_world",
                 "causal_story_beats", "scene_plan", "script", "lyrics",
                 "creative_package_manifest"):
        registry.put(kind, state=core.COMPLETE, digest="d:" + kind)

    missing_refused = False
    try:
        core.check_stage("music", registry)
    except core.ContractError:
        missing_refused = True

    bound = {target: registry.digest_of(target)
             for target in core.APPROVAL_BINDS["package_approval"]}
    registry.put("package_approval", state=core.APPROVED, digest="d:pkg",
                 approved_digests=bound)
    current_admitted = bool(core.check_stage("music", registry)["admitted"])

    registry.put("script", state=core.COMPLETE, digest="d:script-edited")
    stale_issues = []
    stale_refused = False
    try:
        core.check_stage("music", registry)
    except core.ContractError as exc:
        stale_refused = True
        stale_issues = sorted({d.get("issue")
                               for d in (exc.packet.get("approval_defects") or [])})

    return {
        "pass": missing_refused and current_admitted and stale_refused
                and "stale or mismatched binding" in stale_issues,
        "missing_approval_refused": missing_refused,
        "current_binding_admitted": current_admitted,
        "stale_binding_refused": stale_refused,
        "stale_issues": stale_issues,
        "loaded_modules": ["story_first_contracts"],
    }


def _probe_flavor_parity(seam):
    onb = seam.resolve(seam.ONB)
    n999 = seam.resolve(seam.N999)
    differing = [k for k in seam.PACKAGE_DIFFERENCES if onb[k] != n999[k]]
    return {
        "pass": onb["core_digest"] == n999["core_digest"]
                and differing == list(seam.PACKAGE_DIFFERENCES),
        "shared_core_digest": n999["core_digest"],
        "differing_package_facts": differing,
        "loaded_modules": ["package_flavor_adapter", "story_first_contracts"],
    }


def _probe_notion_present_carriers(skill_root, manifest):
    """Load BOTH notion carriers and exercise them offline.

    Round 1 only checked that the files exist, so gutting either module left the
    clause green. The probe now imports them and drives one refusal each.
    """
    row = [r for r in manifest["product_requirements"] if r["id"] == "notion"][0]
    adapter = _load(skill_root, "character_library.notion_adapter")
    protocol = _load(skill_root, "character_library.sync_protocol")

    ops = list(getattr(adapter, "OPS", ()))
    offline_refused = False
    try:
        adapter.resolve_client_library({}, "probe")
    except adapter.ConnectionUnavailable:
        offline_refused = True

    first = protocol.payload_digest({"a": 1})
    second = protocol.payload_digest({"a": 1})
    operation = protocol.operation_id("put", "obj", 1, {"a": 1})
    policy = protocol.RetryPolicy(max_attempts=3)

    return {
        "pass": len(ops) == 4 and offline_refused and first == second
                and str(first).startswith("sha256:")
                and bool(operation) and policy.max_attempts == 3,
        "ops": ops,
        "offline_refused": offline_refused,
        "payload_digest_stable": first == second,
        "operation_id": operation,
        "retry_attempts": policy.max_attempts,
        "present_carriers": list(row["carriers"]),
        "loaded_modules": ["character_library.notion_adapter",
                           "character_library.sync_protocol"],
    }


def _probe_method_plan_surface(skill_root):
    """Read method_plan.py and prove its advertised steps are executable.

    SPEC.md's ellipsis defect is about the plan advertising steps that do not
    run. This reads the module, requires every advertised step to be a callable,
    executes validate(), and refuses a placeholder token in any declared table.
    """
    plan = _load(skill_root, "method_plan.method_plan")
    steps = ("validate", "gates", "teaching_map", "musical_turns", "shot_seeds",
             "storyboard_input", "music_request_input", "production_map",
             "true_at_beat", "pace_order")
    missing = [s for s in steps if not callable(getattr(plan, s, None))]

    if "validate" in missing:
        return {"pass": False, "missing_steps": missing,
                "validate_outcome": None, "gate_count": 0,
                "teaching_rows": 0, "placeholders": [],
                "loaded_modules": ["method_plan.method_plan"]}

    report = plan.validate({}, {})
    refused = report.get("outcome") == "rejected" and bool(report.get("errors"))
    gates = plan.gates({})
    teaching = plan.teaching_map("campaign")

    placeholders = []
    for table in ("BASE_CUES", "LESSON_CUES", "BEAT_FIELDS", "CUE_FIELDS",
                  "ANCHOR_TEXT", "TEACHING_FUNCTION_ROWS", "TURN_SPEC",
                  "AUDIBLE_FIELDS", "GATES"):
        value = getattr(plan, table, None)
        for trail, text in _walk_strings(value, table):
            for token in PLACEHOLDER_TOKENS:
                if token in text:
                    placeholders.append("%s: %r" % (trail, token))

    return {
        "pass": not missing and refused and sorted(gates) == list("ABCDEF")
                and len(teaching) == 12 and not placeholders,
        "missing_steps": missing,
        "validate_outcome": report.get("outcome"),
        "gate_count": len(gates),
        "teaching_rows": len(teaching),
        "placeholders": placeholders,
        "loaded_modules": ["method_plan.method_plan"],
    }


def _probe_entrypoint_reachability(skill_root):
    result = reachability(skill_root)
    return {
        "pass": result["ok"],
        "entrypoint": result["entrypoint"],
        "targets": result["targets"],
        "unreachable": result["unreachable"],
        "controls": result["controls"],
        "factory_closure_targets": result["factory_closure_targets"],
        "factory_not_claimed": result["factory_not_claimed"],
        "problems": result["problems"],
        "loaded_modules": list(result["runtime_loaded"]),
    }


def _probe_emergency_fixes_read_only(skill_root):
    source = os.path.join(skill_root, "package", "999_adapter.py")
    if not os.path.isfile(source):
        source = os.path.abspath(__file__)
    entry = os.path.join(skill_root, ENTRYPOINT_REL)

    problems = []
    problems.extend(_mutation_path_problems(source, "999_adapter.py"))
    if os.path.isfile(entry):
        problems.extend(_mutation_path_problems(entry, "999_entrypoint.py"))

    imported = imported_modules(source)
    for module in HELD_MODULE_IMPORTS:
        if module in imported:
            problems.append("999_adapter.py imports the held module %r" % module)

    held = []
    for rel in HELD_FILES:
        path = os.path.join(skill_root, rel)
        if os.path.isfile(path):
            held.append({"path": rel, "sha256": _sha256(path),
                         "bytes": os.path.getsize(path)})
        else:
            held.append({"path": rel, "present": False})

    return {
        "pass": not problems and any(h.get("sha256") for h in held),
        "policy": "read_only",
        "held_files": held,
        "problems": problems,
        "loaded_modules": [],
    }


def _constant_text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _mutation_path_problems(path, label):
    """Flag a hardcoded write/delete. Temp-directory scaffolding is allowed.

    The clause is about regressing the accepted emergency fixes, so what is
    forbidden is a literal path into the tree being opened for writing or
    removed. Writes into a tempfile.mkdtemp() scaffolding are how the check
    gives every advertised step a fresh work directory; a variable target is
    not a hardcoded tree write, and the tests prove the tree is byte-identical
    after a full check run.
    """
    with open(path, "rb") as fh:
        tree = ast.parse(fh.read())
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "open":
            mode = None
            if len(node.args) > 1:
                mode = _constant_text(node.args[1])
            for keyword in node.keywords:
                if keyword.arg == "mode":
                    mode = _constant_text(keyword.value)
            target = _constant_text(node.args[0]) if node.args else None
            if isinstance(mode, str) and any(c in mode for c in "wax+") \
                    and target is not None:
                problems.append("%s hardcodes a writable open(%r, mode=%r) at "
                                "line %d" % (label, target, mode, node.lineno))
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                and func.value.id in ("os", "shutil") \
                and func.attr in ("remove", "unlink", "rename", "replace",
                                  "rmtree", "rmdir"):
            target = _constant_text(node.args[0]) if node.args else None
            if target is not None:
                problems.append("%s hardcodes .%s(%r) at line %d"
                                % (label, func.attr, target, node.lineno))
    return problems


# ---------------------------------------------------------------------------
# entrypoint reachability: exposure, not existence
# ---------------------------------------------------------------------------

def module_index(skill_root):
    """dotted module name -> file, indexed under scripts/core and scripts."""
    index = {}
    for base in (os.path.join(skill_root, "scripts", "core"),
                 os.path.join(skill_root, "scripts")):
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", ".git", "node_modules")]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                full = os.path.join(dirpath, filename)
                parts = os.path.relpath(full, base)[:-3].split(os.sep)
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                if parts:
                    index.setdefault(".".join(parts), full)
    return index


def _package_parts(path, skill_root):
    for base in (os.path.join(skill_root, "scripts", "core"),
                 os.path.join(skill_root, "scripts")):
        try:
            rel = os.path.relpath(path, base)
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        parts = rel[:-3].split(os.sep) if rel.endswith(".py") else rel.split(
            os.sep)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            return parts[:-1]
    return []


def static_closure(skill_root, entry_rel):
    """Module-level import closure of one file, plus its dynamic import sites."""
    index = module_index(skill_root)
    start = os.path.join(skill_root, entry_rel)
    seen_files = set()
    modules = set()
    dynamic = []
    stack = [start]

    def record(name):
        path = index.get(name)
        if path:
            modules.add(name)
            if path not in seen_files:
                stack.append(path)

    while stack:
        path = stack.pop()
        if path in seen_files:
            continue
        seen_files.add(path)
        try:
            with open(path, "rb") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        package = _package_parts(path, skill_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    record(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    head = package[:len(package) - (node.level - 1)] \
                        if node.level > 1 else list(package)
                    base = head + (node.module.split(".") if node.module else [])
                else:
                    base = node.module.split(".") if node.module else []
                if base:
                    record(".".join(base))
                for alias in node.names:
                    if alias.name != "*":
                        record(".".join(base + [alias.name]))
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name in ("import_module", "__import__"):
                    arg = node.args[0] if node.args else None
                    literal = None
                    if isinstance(arg, ast.Constant) and isinstance(arg.value,
                                                                    str):
                        literal = arg.value
                    dynamic.append({"file": os.path.relpath(path, skill_root),
                                    "line": node.lineno,
                                    "target": literal})
    return {"modules": modules, "files": seen_files, "dynamic": dynamic}


def runtime_loaded_carriers(skill_root, entry_rel):
    """Run the entrypoint in a fresh process and report what it loaded."""
    entry = os.path.join(skill_root, entry_rel)
    env = dict(os.environ)
    env.pop(NESTED_ENV, None)
    proc = subprocess.run([sys.executable, entry_rel, "carriers"],
                          cwd=skill_root, capture_output=True, text=True,
                          timeout=180, env=env)
    if proc.returncode != 0:
        return None, "%s exited %d: %s" % (entry_rel, proc.returncode,
                                           proc.stderr[-400:])
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return None, "%s printed no JSON: %r" % (entry_rel, proc.stdout[:200])
    return payload, None


def reachability(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    config = manifest["reachability"]
    entry_rel = config["entrypoint"]
    targets = list(config["capability_targets"])
    controls = list(config["positive_controls"])
    problems = []

    if os.path.normpath(entry_rel) != os.path.normpath(ENTRYPOINT_REL):
        problems.append("manifest entrypoint %r is not the adapter's %r"
                        % (entry_rel, ENTRYPOINT_REL))
    if not os.path.isfile(os.path.join(root, entry_rel)):
        return {"ok": False, "entrypoint": entry_rel, "targets": targets,
                "unreachable": targets, "controls": controls,
                "runtime_loaded": [], "factory_closure_targets": [],
                "factory_not_claimed": config.get("factory_not_claimed"),
                "problems": problems + ["entrypoint %s is absent" % entry_rel]}

    closure = static_closure(root, entry_rel)
    reached = closure["modules"]
    unreachable = [t for t in targets if t not in reached]

    # Positive controls prove the walk can report REACHABLE at all. One of them
    # is reached transitively from a different root (the held control CLI), so a
    # walker that only resolves direct imports is caught here.
    control_rows = []
    walkable = {"entrypoint": reached}
    factory_closure = static_closure(root, FACTORY_REL)["modules"]
    for control in controls:
        source = control.get("walked_from", "entrypoint")
        pool = reached if source == "entrypoint" else factory_closure
        seen = control["module"] in pool
        control_rows.append({"module": control["module"],
                             "walked_from": source, "reached": seen,
                             "why": control.get("why")})
        if not seen:
            problems.append("PROBE_INVALID: positive control %r not reached "
                            "from %s" % (control["module"], source))

    payload, error = runtime_loaded_carriers(root, entry_rel)
    runtime_loaded = list(payload.get("loaded") or []) if payload else []
    if error:
        problems.append("runtime probe failed: %s" % error)
    else:
        for target in targets:
            if target not in runtime_loaded:
                problems.append("carrier %r is not loaded by a fresh run of %s"
                                % (target, entry_rel))
        # The static closure must agree with the running process; a module that
        # only appears at run time was loaded dynamically, not routed.
        for target in targets:
            if target in runtime_loaded and target not in reached:
                problems.append("carrier %r loads only through a dynamic import"
                                % target)

    factory_unreached = [t for t in targets if t not in factory_closure]
    return {
        "ok": not problems,
        "entrypoint": entry_rel,
        "targets": targets,
        "unreachable": [t for t in targets if t not in reached],
        "controls": control_rows,
        "runtime_loaded": runtime_loaded,
        "closure_size": len(reached),
        "dynamic_import_sites": len(closure["dynamic"]),
        "factory_closure_size": len(factory_closure),
        "factory_closure_targets": factory_unreached,
        "factory_not_claimed": config.get("factory_not_claimed"),
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# own adapters: the 999 entrypoint is this package's, not the primary's
# ---------------------------------------------------------------------------

def imported_modules(path):
    """Every module name this file's import statements name, by AST."""
    with open(path, "rb") as fh:
        tree = ast.parse(fh.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            if node.level == 0:
                names.update(alias.name.split(".")[0] for alias in node.names)
    return names


def own_adapters(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    declared = manifest["own_adapters"]
    layout = layout_of(root)
    problems = []

    if layout == FLAVOR:
        for rel in declared["layout_999"]["required"]:
            if not os.path.isfile(os.path.join(root, rel)):
                problems.append("999 layout is missing its own adapter %s" % rel)
        for rel in declared["layout_999"]["forbidden"]:
            if os.path.isfile(os.path.join(root, rel)):
                problems.append("999 layout carries the primary wrapper %s" % rel)
    elif layout == "source":
        for rel in declared["layout_source"]["required"]:
            if not os.path.isfile(os.path.join(root, rel)):
                problems.append("source layout is missing %s" % rel)
    else:
        problems.append("unknown layout at %s" % root)

    entrypoint = os.path.join(root, ENTRYPOINT_REL)
    if not os.path.isfile(entrypoint):
        problems.append("the 999 entrypoint %s is absent" % ENTRYPOINT_REL)

    inspected = os.path.join(root, "package", "999_adapter.py")
    if not os.path.isfile(inspected):
        inspected = os.path.abspath(__file__)
    for surface in (inspected, entrypoint):
        if not os.path.isfile(surface):
            continue
        imported = imported_modules(surface)
        label = os.path.basename(surface)
        if PRIMARY_ADAPTER_MODULE in imported:
            problems.append("%s imports the primary adapter module %r"
                            % (label, PRIMARY_ADAPTER_MODULE))
        if "openclaw_adapter" in imported:
            problems.append("%s imports the primary runtime wrapper module"
                            % label)
    leaked = [m for m in sys.modules
              if m in (PRIMARY_ADAPTER_MODULE, "openclaw_adapter")]
    if leaked:
        problems.append("primary adapter module(s) imported: %s" % sorted(leaked))

    try:
        fixture = load_fixture(root)
        for group in ("entrypoints", "checks"):
            for row in fixture.get(group) or []:
                if PRIMARY_WRAPPER in " ".join(row.get("argv") or []):
                    problems.append("%s:%s routes through the primary wrapper %s"
                                    % (group, row.get("id"), PRIMARY_WRAPPER))
    except (AdapterError, OSError, ValueError) as exc:
        problems.append("%s: %s" % (type(exc).__name__, exc))

    return {
        "layout": layout,
        "entrypoint": ENTRYPOINT_REL,
        "primary_adapter_module": PRIMARY_ADAPTER_MODULE,
        "primary_wrapper": PRIMARY_WRAPPER,
        "problems": problems,
        "ok": not problems,
    }


# ---------------------------------------------------------------------------
# entrypoints: advertised means supported, complete, cited and executable
# ---------------------------------------------------------------------------

def factory_subcommands(path):
    with open(path, "rb") as fh:
        tree = ast.parse(fh.read())
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_parser"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str):
            names.add(node.args[0].value)
    return names


def _command_of(argv):
    """The subcommand token of a control-CLI argv, or None."""
    joined = " ".join(argv)
    if "intake_preflight" not in joined:
        return None
    for token in argv[2:]:
        if not token.startswith("-"):
            return token
    return None


CITATION_RE = re.compile(r"^(?P<path>[^:]+?)(?::(?P<line>\d+))?"
                         r"(?:\s+'(?P<quote>.*)')?$")


def verify_citation(root, citation):
    """Open the file a citation names and check its line and quoted text."""
    match = CITATION_RE.match(citation.strip())
    if not match:
        return "citation %r is not 'path[:line][ 'quote']'" % citation
    rel = match.group("path")
    line_no = match.group("line")
    quote = match.group("quote")
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return "citation %r names an absent file" % citation
    if line_no is None:
        return None
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    index = int(line_no)
    if index < 1 or index > len(lines):
        return "citation %r is past the end of %s (%d lines)" % (
            citation, rel, len(lines))
    if quote and quote not in lines[index - 1]:
        return ("citation %r: %r is not on %s line %d (%r)"
                % (citation, quote, rel, index, lines[index - 1].strip()[:120]))
    return None


def _seed_workdir(root, fixture, work):
    for name, content in (fixture.get("workdir_files") or {}).items():
        path = os.path.join(work, name)
        os.makedirs(os.path.dirname(path) or work, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(content, str):
                fh.write(content)
            else:
                json.dump(content, fh, sort_keys=True)


def expand_argv(argv, work):
    out = []
    for token in argv:
        if token == "{python}":
            out.append(sys.executable)
        elif token == "{work}":
            out.append(work)
        else:
            out.append(token.replace("{work}", work))
    return out


REGISTRY_CANDIDATES = (
    os.path.join("74-kie-live-adapter", "references", "kie-model-registry.json"),
    os.path.join("kie-live-adapter", "references", "kie-model-registry.json"),
)


def kie_registry(skill_root):
    """The live KIE model registry a card invocation needs, if this tree has it.

    The card refuses to print a video model it cannot prove, so the check points
    it at the registry the sibling skill ships. Not finding one is reported by
    the card's own exit code, never papered over.
    """
    current = os.path.abspath(skill_root)
    for _ in range(6):
        for rel in REGISTRY_CANDIDATES:
            candidate = os.path.join(current, rel)
            if os.path.isfile(candidate):
                return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def _run(entry, root, work, timeout=300):
    argv = expand_argv(entry["argv"], work)
    env = dict(os.environ)
    env[NESTED_ENV] = "1"
    registry = kie_registry(root)
    if registry and not env.get("KIE_MODEL_REGISTRY_JSON"):
        env["KIE_MODEL_REGISTRY_JSON"] = registry
    return subprocess.run(argv, cwd=root, capture_output=True, text=True,
                          timeout=timeout, env=env)


def entrypoints(skill_root=None):
    root = skill_root or SKILL_ROOT
    fixture = load_fixture(root)
    factory = os.path.join(root, FACTORY_REL)
    implemented = factory_subcommands(factory)

    rows = []
    unsupported = []
    placeholders = []
    missing = []
    citations = []

    groups = (("entrypoints", fixture.get("entrypoints") or []),
              ("checks", fixture.get("checks") or []))
    for group, group_rows in groups:
        for entry in group_rows:
            label = "%s:%s" % (group, entry.get("id"))
            argv = entry.get("argv") or []

            if not argv or not all(isinstance(t, str) and t.strip()
                                   for t in argv):
                missing.append("%s: argv is empty or carries a blank token"
                               % label)

            # Placeholder scan across EVERY string in the record, not argv only.
            for trail, text in _walk_strings(entry):
                for token in PLACEHOLDER_TOKENS:
                    if token in text:
                        placeholders.append("%s: %s carries the placeholder "
                                            "token %r" % (label, trail, token))

            for token in argv:
                if token.startswith("{") and token.endswith("}") \
                        and token not in ALLOWED_TOKENS:
                    placeholders.append("%s: argv carries the unresolved token %r"
                                        % (label, token))

            command = _command_of(argv)
            if command is not None and command not in implemented:
                unsupported.append("%s: subcommand %r is not implemented by "
                                   "factory.py (known: %s)"
                                   % (label, command, sorted(implemented)))

            step_path = None
            if len(argv) >= 2 and argv[0] == "{python}":
                step_path = argv[1]
            if step_path and not os.path.isfile(os.path.join(root, step_path)):
                missing.append("%s: script %s does not exist" % (label, step_path))

            cites = entry.get("advertised_in") or []
            if not cites:
                missing.append("%s: advertised nowhere (advertised_in empty)"
                               % label)
            for citation in cites:
                problem = verify_citation(root, citation)
                citations.append({"step": entry.get("id"), "citation": citation,
                                  "ok": problem is None, "problem": problem})
                if problem:
                    missing.append("%s: %s" % (label, problem))

            observed = (entry.get("observed") or {}).get("exit_code")
            if observed is None:
                missing.append("%s: no observed exit code recorded" % label)
            expected = (entry.get("expect") or {}).get("exit_code")
            if observed is not None and observed != expected:
                missing.append("%s: observed exit %r does not match expected %r"
                               % (label, observed, expected))

            rows.append({"group": group, "id": entry.get("id"),
                         "command": command, "observed_exit": observed})

    excluded = []
    for entry in fixture.get("excluded_steps") or []:
        label = entry.get("id")
        if not entry.get("reason") or not (entry.get("observed") or {}).get(
                "error"):
            missing.append("excluded step %r does not record why it cannot run"
                           % label)
        claim = verify_excluded(root, fixture, entry)
        excluded.append({"id": label, "claim_ok": claim["ok"],
                         "observed_exit": claim.get("exit_code"),
                         "problems": claim["problems"]})
        unsupported.extend("excluded step %r: %s" % (label, p)
                           for p in claim["problems"])

    return {
        "rows": rows,
        "row_count": len(rows),
        "advertised_commands": sorted({r["command"] for r in rows
                                       if r["command"]}),
        "implemented_commands": sorted(implemented),
        "unsupported": unsupported,
        "placeholders": placeholders,
        "citations": citations,
        "missing": missing,
        "excluded": excluded,
        "method_plan": _probe_method_plan_surface(root),
    }


def verify_excluded(skill_root, fixture, entry):
    """Re-run an excluded claim. A command that really runs is not excluded."""
    problems = []
    argv = entry.get("argv") or []
    recorded = (entry.get("observed") or {}).get("exit_code")
    signature = (entry.get("observed") or {}).get("error") or ""
    work = tempfile.mkdtemp(prefix="s75t30-excl-")
    try:
        _seed_workdir(skill_root, fixture, work)
        try:
            proc = _run(entry, skill_root, work)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "exit_code": None,
                    "problems": ["could not run: %s: %s"
                                 % (type(exc).__name__, exc)]}
        combined = (proc.stderr or "") + (proc.stdout or "")
        if proc.returncode == 0:
            problems.append("claims to be unsupported but exits 0 -- it runs")
        if recorded is not None and proc.returncode != recorded:
            problems.append("recorded exit %r but really exits %d"
                            % (recorded, proc.returncode))
        if signature and signature not in combined:
            problems.append("recorded error %r does not appear in the output"
                            % signature)
        return {"ok": not problems, "exit_code": proc.returncode,
                "problems": problems}
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def run_entrypoints(skill_root=None, skip_ids=()):
    """Run every advertised step and compare the exit code it actually gives."""
    root = skill_root or SKILL_ROOT
    fixture = load_fixture(root)
    observed = []
    problems = []
    for group in ("entrypoints", "checks"):
        for entry in fixture.get(group) or []:
            if entry.get("id") in skip_ids:
                continue
            work = tempfile.mkdtemp(prefix="s75t30-step-")
            try:
                _seed_workdir(root, fixture, work)
                try:
                    proc = _run(entry, root, work)
                except (OSError, subprocess.SubprocessError) as exc:
                    observed.append({"id": entry.get("id"),
                                     "error": "%s: %s"
                                              % (type(exc).__name__, exc)})
                    problems.append("%s could not be executed" % entry.get("id"))
                    continue
            finally:
                import shutil
                shutil.rmtree(work, ignore_errors=True)
            expected = (entry.get("expect") or {}).get("exit_code")
            row = {"id": entry.get("id"), "exit_code": proc.returncode,
                   "expected": expected, "stderr_bytes": len(proc.stderr)}
            if proc.returncode != expected:
                problems.append("%s exited %d, expected %r"
                                % (entry.get("id"), proc.returncode, expected))
            if (entry.get("expect") or {}).get("stderr_empty") and proc.stderr:
                problems.append("%s wrote %d stderr bytes"
                                % (entry.get("id"), len(proc.stderr)))
            observed.append(row)
    return {"executed": len(observed), "observed": observed,
            "problems": problems, "ok": not problems}


# ---------------------------------------------------------------------------
# the envelope, one clause per sentence of S75-A30
# ---------------------------------------------------------------------------

def check(skill_root=None, execute=True):
    root = skill_root or SKILL_ROOT
    nested = bool(os.environ.get(NESTED_ENV))
    clauses = []

    try:
        resolved = resolve(root)
        reqs = requirements(root)
        ok = resolved["ok"] and reqs["ok"]
        clauses.append({"id": "same_product_requirements", "ok": ok,
                        "detail": {"resolve": resolved, "requirements": reqs}})
    except (AdapterError, OSError, ImportError, ValueError) as exc:
        clauses.append({"id": "same_product_requirements", "ok": False,
                        "detail": "%s: %s" % (type(exc).__name__, exc)})

    try:
        own = own_adapters(root)
        clauses.append({"id": "own_adapters", "ok": own["ok"], "detail": own})
    except (AdapterError, OSError, ValueError) as exc:
        clauses.append({"id": "own_adapters", "ok": False,
                        "detail": "%s: %s" % (type(exc).__name__, exc)})

    try:
        reach = reachability(root)
        clauses.append({"id": "entrypoint_reachability", "ok": reach["ok"],
                        "detail": reach})
    except (AdapterError, OSError, ImportError, ValueError) as exc:
        clauses.append({"id": "entrypoint_reachability", "ok": False,
                        "detail": "%s: %s" % (type(exc).__name__, exc)})

    try:
        emergency = _probe_emergency_fixes_read_only(root)
        clauses.append({"id": "emergency_fixes_read_only",
                        "ok": emergency["pass"], "detail": emergency})
    except (AdapterError, OSError, ValueError) as exc:
        clauses.append({"id": "emergency_fixes_read_only", "ok": False,
                        "detail": "%s: %s" % (type(exc).__name__, exc)})

    try:
        steps = entrypoints(root)
    except (AdapterError, OSError, ValueError) as exc:
        clauses.append({"id": "no_unsupported_commands", "ok": False,
                        "detail": "%s: %s" % (type(exc).__name__, exc)})
        clauses.append({"id": "no_placeholder_ellipses", "ok": False,
                        "detail": "entrypoints unreadable"})
        clauses.append({"id": "no_missing_advertised_steps", "ok": False,
                        "detail": "entrypoints unreadable"})
        steps = None

    if steps is not None:
        clauses.append({"id": "no_unsupported_commands",
                        "ok": not steps["unsupported"],
                        "detail": {"advertised": steps["advertised_commands"],
                                   "implemented": steps["implemented_commands"],
                                   "excluded": steps["excluded"],
                                   "problems": steps["unsupported"]}})
        methods = steps["method_plan"]
        clauses.append({"id": "no_placeholder_ellipses",
                        "ok": not steps["placeholders"] and methods["pass"],
                        "detail": {"problems": steps["placeholders"],
                                   "tokens": list(PLACEHOLDER_TOKENS),
                                   "method_plan": methods}})
        detail = {"rows": steps["row_count"],
                  "excluded": steps["excluded"],
                  "problems": list(steps["missing"])}
        if execute and not nested:
            ran = run_entrypoints(root)
            detail["executed"] = ran["executed"]
            detail["observed"] = ran["observed"]
            detail["problems"] += ran["problems"]
        else:
            detail["executed"] = 0
            detail["nested"] = nested
        clauses.append({"id": "no_missing_advertised_steps",
                        "ok": not detail["problems"], "detail": detail})

    return {
        "schema": SCHEMA,
        "flavor": FLAVOR,
        "unit": "S75-T30",
        "acceptance": "S75-A30",
        "skill_root": os.path.abspath(root),
        "layout": layout_of(root),
        "executes_advertised_steps": bool(execute) and not nested,
        "ok": all(c["ok"] for c in clauses),
        "clauses": clauses,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="999 package adapter: assemble and prove the 999 flavour.")
    parser.add_argument("cmd", choices=("check", "entrypoints"),
                        help="what to emit")
    parser.add_argument("--execute", action="store_true",
                        help="accepted for compatibility; check always executes")
    parser.add_argument("--skill-root", default=None,
                        help="prove this skill root instead of the one this file "
                             "ships in")
    args = parser.parse_args(argv)

    if args.cmd == "entrypoints":
        payload = entrypoints(args.skill_root)
        payload["ok"] = not (payload["unsupported"] or payload["placeholders"]
                             or payload["missing"])
    else:
        payload = check(args.skill_root)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
