#!/usr/bin/env python3
"""999 package adapter (S75-T30 / S75-A30). Stdlib only.

The 999 flavour's own package adapter. It assembles the package from what the
tree it runs in actually carries and proves the assembly instead of assuming the
primary flavour's layout.

Five jobs, one per clause of S75-A30:

  resolve()        the 999 flavour through the S75-T03 seam (consumed, never
                   re-derived); refuses when the manifest disagrees with it
  requirements()   every product requirement either carried by a live carrier
                   whose probe passes, or declared absent with the unit that
                   owes it. A stale declaration in either direction fails.
  own_adapters()   the 999 entrypoint is this module and the 999 adapters/ tree;
                   it never imports onboarding_adapter and never runs
                   scripts/openclaw_adapter.py
  entrypoints()    advertised commands are a subset of what factory.py really
                   implements; every argv is complete; every file exists
  check()          one envelope over all of it, exit 0 or 1

No write path, no network, no paid call, no generation. Importing the module has
no lasting side effect: sys.path is restored.

Run: python3 package/999_adapter.py check [--execute] [--skill-root PATH]
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import importlib
import json
import os
import subprocess
import sys

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(PACKAGE_DIR)

SCHEMA = "s75.n999-adapter-check.v1"
FLAVOR = "999"
N999_SUFFIX = os.path.join(".claude", "skills", "drama-song-ad-factory")
SOURCE_ANCHOR = "75-drama-song-ad-factory"
PRIMARY_ADAPTER_MODULE = "onboarding_adapter"
PRIMARY_WRAPPER = "scripts/openclaw_adapter.py"
FACTORY_REL = os.path.join("scripts", "core", "intake_preflight", "factory.py")

#: A token that means the step was never finished. A fixture may not advertise one.
PLACEHOLDER_TOKENS = ("...", "…", "TODO", "TBD")

#: The product requirement set, identical to the primary flavour's. The manifest
#: must declare exactly these rows; a missing or invented row fails.
REQUIREMENT_IDS = (
    "artifact_order",
    "cast_world_script_gates",
    "notion",
    "styles_18",
    "approval_ordering",
    "flavor_parity",
    "paid_compatibility",
)


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
    }


def _probe_cast_world_script_gates(core):
    cast_defects = core.validate_cast_manifest({}) or []
    placeholder = {
        "scene_id": "s1", "purpose": "x", "action": "y", "location_id": "loc1",
        "cast": [], "lines": [{"speaker": "a", "text": "hi"}],
    }
    scene_defects = core.validate_scene(placeholder) or []
    fields = sorted({d.get("field") for d in scene_defects})
    return {
        "pass": bool(cast_defects) and "dialogue" in fields
                and "duration_seconds" in fields,
        "empty_cast_refused": bool(cast_defects),
        "placeholder_scene_defect_fields": fields,
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
    }


def _probe_notion_present_carriers(skill_root, manifest):
    row = [r for r in manifest["product_requirements"] if r["id"] == "notion"][0]
    return {
        "pass": all(os.path.isfile(os.path.join(skill_root, c))
                    for c in row["carriers"]),
        "present_carriers": list(row["carriers"]),
    }


def requirements(skill_root=None):
    root = skill_root or SKILL_ROOT
    manifest = load_manifest(root)
    rows = manifest.get("product_requirements") or []
    problems = []
    reported = []

    declared_ids = tuple(r.get("id") for r in rows)
    if declared_ids != REQUIREMENT_IDS:
        problems.append("requirement set %r is not the shared product set %r"
                        % (declared_ids, REQUIREMENT_IDS))

    seam = None
    for row in rows:
        state = row.get("state")
        carriers = row.get("carriers") or []
        absent = row.get("absent") or []
        detail = {"id": row.get("id"), "state": state}

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

        reported.append(detail)

    return {"rows": reported, "problems": problems, "ok": not problems}


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
    core = _load(skill_root, "story_first_contracts")
    probes = {
        "artifact_order": _probe_artifact_order,
        "cast_world_script_gates": _probe_cast_world_script_gates,
        "approval_ordering": _probe_approval_ordering,
    }
    return probes[name](core)


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

    inspected = os.path.join(root, "package", "999_adapter.py")
    if not os.path.isfile(inspected):
        inspected = os.path.abspath(__file__)
    imported = imported_modules(inspected)
    if PRIMARY_ADAPTER_MODULE in imported:
        problems.append("%s imports the primary adapter module %r"
                        % (os.path.basename(inspected), PRIMARY_ADAPTER_MODULE))
    if "openclaw_adapter" in imported:
        problems.append("%s imports the primary runtime wrapper module"
                        % os.path.basename(inspected))
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
        "primary_adapter_module": PRIMARY_ADAPTER_MODULE,
        "primary_wrapper": PRIMARY_WRAPPER,
        "problems": problems,
        "ok": not problems,
    }


# ---------------------------------------------------------------------------
# entrypoints: advertised means supported, complete and executable
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


def entrypoints(skill_root=None):
    root = skill_root or SKILL_ROOT
    fixture = load_fixture(root)
    factory = os.path.join(root, FACTORY_REL)
    implemented = factory_subcommands(factory)

    rows = []
    unsupported = []
    placeholders = []
    missing = []

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
            for token in argv:
                if token in PLACEHOLDER_TOKENS:
                    placeholders.append("%s: argv carries the placeholder token %r"
                                        % (label, token))
                if token.startswith("<") and token.endswith(">"):
                    placeholders.append("%s: argv carries the planted placeholder %r"
                                        % (label, token))
                if token.startswith("{") and token.endswith("}") and token not in (
                        "{python}", "{skill_root}"):
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
        if not entry.get("reason") or not entry.get("observed", {}).get("error"):
            missing.append("excluded step %r does not record why it cannot run"
                           % entry.get("id"))
        excluded.append(entry.get("id"))

    return {
        "rows": rows,
        "row_count": len(rows),
        "advertised_commands": sorted({r["command"] for r in rows
                                       if r["command"]}),
        "implemented_commands": sorted(implemented),
        "unsupported": unsupported,
        "placeholders": placeholders,
        "missing": missing,
        "excluded": excluded,
    }


def run_entrypoints(skill_root=None):
    """Run every advertised step and compare the exit code it actually gives."""
    root = skill_root or SKILL_ROOT
    fixture = load_fixture(root)
    observed = []
    problems = []
    for group in ("entrypoints", "checks"):
        for entry in fixture.get(group) or []:
            argv = [sys.executable if t == "{python}" else t
                    for t in entry["argv"]]
            try:
                proc = subprocess.run(argv, cwd=root, capture_output=True,
                                      text=True, timeout=300)
            except (OSError, subprocess.SubprocessError) as exc:
                observed.append({"id": entry["id"],
                                 "error": "%s: %s" % (type(exc).__name__, exc)})
                problems.append("%s could not be executed" % entry["id"])
                continue
            expected = (entry.get("expect") or {}).get("exit_code")
            row = {"id": entry["id"], "exit_code": proc.returncode,
                   "expected": expected, "stderr_bytes": len(proc.stderr)}
            if proc.returncode != expected:
                problems.append("%s exited %d, expected %r"
                                % (entry["id"], proc.returncode, expected))
            if (entry.get("expect") or {}).get("stderr_empty") and proc.stderr:
                problems.append("%s wrote %d stderr bytes"
                                % (entry["id"], len(proc.stderr)))
            observed.append(row)
    return {"executed": len(observed), "observed": observed,
            "problems": problems, "ok": not problems}


# ---------------------------------------------------------------------------
# the envelope, one clause per sentence of S75-A30
# ---------------------------------------------------------------------------

def check(skill_root=None, execute=False):
    root = skill_root or SKILL_ROOT
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
                                   "problems": steps["unsupported"]}})
        clauses.append({"id": "no_placeholder_ellipses",
                        "ok": not steps["placeholders"],
                        "detail": {"problems": steps["placeholders"],
                                   "tokens": list(PLACEHOLDER_TOKENS)}})
        detail = {"rows": steps["row_count"],
                  "excluded": steps["excluded"],
                  "problems": list(steps["missing"])}
        if execute:
            ran = run_entrypoints(root)
            detail["executed"] = ran["executed"]
            detail["observed"] = ran["observed"]
            detail["problems"] += ran["problems"]
        clauses.append({"id": "no_missing_advertised_steps",
                        "ok": not detail["problems"], "detail": detail})

    return {
        "schema": SCHEMA,
        "flavor": FLAVOR,
        "unit": "S75-T30",
        "acceptance": "S75-A30",
        "skill_root": os.path.abspath(root),
        "layout": layout_of(root),
        "ok": all(c["ok"] for c in clauses),
        "clauses": clauses,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="999 package adapter: assemble and prove the 999 flavour.")
    parser.add_argument("cmd", choices=("check", "entrypoints"),
                        help="what to emit")
    parser.add_argument("--execute", action="store_true",
                        help="also run every advertised step")
    parser.add_argument("--skill-root", default=None,
                        help="prove this skill root instead of the one this file "
                             "ships in")
    args = parser.parse_args(argv)

    if args.cmd == "entrypoints":
        payload = entrypoints(args.skill_root)
        payload["ok"] = not (payload["unsupported"] or payload["placeholders"]
                             or payload["missing"])
    else:
        payload = check(args.skill_root, execute=args.execute)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
