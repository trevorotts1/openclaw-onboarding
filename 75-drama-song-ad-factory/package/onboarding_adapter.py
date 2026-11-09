#!/usr/bin/env python3
"""S75-T29 onboarding package adapter — assembles the onboarding flavor.

One job: prove that the ONB supported entrypoint still reaches the four things
A29 names, using the modules the other accepted units own. It resolves, it
reads, it reports. It never writes, never generates, never calls a provider.

"Exposes" has one meaning here and the receipt reports it separately from
existence: a module is EXISTING when this checker can import it and its symbols
resolve, and EXPOSED when it is in the transitive import closure of the
supported entrypoint (scripts/core/intake_preflight/factory.py, which
scripts/openclaw_adapter.py relays to). Round 1 failed exactly on that gap --
the four providers existed and the entrypoint reached none of them -- so a
clause now needs BOTH columns to pass, and the entrypoint-reachability walker
carries a positive control (a module known to be reached) so it can never
report an empty closure and pass.

What it consumes, by name, so nothing is forked here:

  scripts/core/package_flavor_adapter.py   the one flavor seam (S75-T03)
  scripts/core/story_first_contracts.py    artifact order + envelope gates (S75-T03)
  scripts/core/character_bible/identity.py complete cast / crowd / world gates (S75-T05)
  scripts/core/character_library/notion_adapter.py  Notion discovery (S75-T14)
  scripts/core/music_styles/catalog.py     the eighteen-style catalogue (S75-T18)

The five emergency-held files are treated as fixed inputs: their digests are
reported, their names are never imported, and this file contains no write path
(proved by the adapter's own AST probe).

Stdlib only. No network. No paid call. Exit 0 = every required clause proved.

Usage:
  python3 package/onboarding_adapter.py report [--skill-root DIR] [--pretty]
  python3 package/onboarding_adapter.py check  [--skill-root DIR]
  python3 package/onboarding_adapter.py entrypoints [--skill-root DIR]
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import subprocess
import sys

SCHEMA = "blackceo.s75.onboarding-adapter-receipt/v1"
SEAM = "onboarding_adapter.report"
MANIFEST_NAME = "onboarding-manifest.json"
FIXTURE_REL = os.path.join("tests", "fixtures", "onboarding_entrypoints.json")
ENTRYPOINT_REL = os.path.join("scripts", "openclaw_adapter.py")

#: The supported entrypoint whose import closure defines "exposed". The wrapper
#: above is a relay: it runs this file as [sys.executable, entrypoint, *argv],
#: so the entrypoint process is the one whose imports matter.
ENTRYPOINT_ROOT_REL = os.path.join("scripts", "core", "intake_preflight", "factory.py")

#: Import roots the entrypoint process has, in the order it has them: its own
#: directory (sys.path[0] when factory.py runs as a script, which is what the
#: wrapper does), then the sys.path.insert() factory.py itself performs
#: (scripts/core), then the remaining tree roots. A provider that resolves only
#: when THIS checker imports it from its own path is not in here -- that
#: difference is the whole point of the probe.
_IMPORT_ROOT_RELS = (
    os.path.join("scripts", "core", "intake_preflight"),
    os.path.join("scripts", "core"),
    "scripts",
    ".",
)

#: Modules known to be reached from the entrypoint. The walker must find these
#: or it is broken, not the tree: a probe that can miss a known-positive would
#: otherwise report an empty closure and pass.
DEFAULT_POSITIVE_CONTROLS = ("music_styles.music_styles", "character_library.character_library")

#: stdlib names are not tree gaps, so they are left out of unresolved_imports
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))

EXISTENCE_MEANING = ("EXISTING: the module file is present under the skill root, imports "
                     "cleanly in this checker, and every declared symbol resolves.")
EXPOSURE_MEANING = ("EXPOSED: the module is in the transitive static import closure of "
                    "the supported entrypoint (%s), i.e. the entrypoint process reaches "
                    "it without this checker importing it directly. Existence is not "
                    "exposure; only this column answers A29's word 'exposes'."
                    % ENTRYPOINT_ROOT_REL)

#: Held by task 01a16e50 (owner UNKNOWN). Named so the AST probe can refuse
#: any import of them; never imported and never edited here.
HELD_MODULES = ("factory", "lyric_writer", "character_approval", "method_plan")

_MUTATING_ATTRS = frozenset({
    "remove", "unlink", "rename", "replace", "rmdir", "mkdir", "makedirs",
    "write_text", "write_bytes", "touch", "chmod", "chown", "copy", "copy2",
    "copyfile", "copytree", "move", "rmtree",
})
_PATH_ROOTS = frozenset({"os", "shutil", "pathlib", "Path"})


class ProviderUnavailable(Exception):
    """A declared provider module or symbol is not reachable from the tree."""


# ── small helpers ────────────────────────────────────────────────────────────

def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _skill_root(explicit=None):
    return os.path.abspath(explicit) if explicit else os.path.dirname(_here())


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_json_optional(path):
    """(data, error). A missing or unreadable file is a receipt row, never a traceback."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, ValueError) as exc:
        return None, "%s: %s: %s" % (path, type(exc).__name__, exc)


def _digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _kind(value):
    return type(value).__name__


# ── provider resolution ──────────────────────────────────────────────────────

def _load_module(decl, skill_root, cache):
    """Import one declared provider by the path the manifest names."""
    key = decl["module"]
    if key in cache:
        return cache[key]
    path = os.path.join(skill_root, decl["path"])
    import_dir = os.path.join(skill_root, decl["import_dir"])
    if not os.path.isfile(path):
        raise ProviderUnavailable("module file missing: %s" % decl["path"])
    if not os.path.isdir(import_dir):
        raise ProviderUnavailable("import dir missing: %s" % decl["import_dir"])
    if import_dir not in sys.path:
        sys.path.insert(0, import_dir)
    try:
        module = importlib.import_module(decl["module"])
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed silently
        raise ProviderUnavailable("import %s failed: %s: %s"
                                  % (decl["module"], type(exc).__name__, exc))
    cache[key] = module
    return module


def _provider_state(decl, skill_root, cache):
    """Resolve one provider into a receipt row. Never raises."""
    row = {
        "id": decl.get("id"),
        "module": decl.get("module"),
        "path": decl.get("path"),
        "required": decl.get("required", True),
        "provenance": decl.get("provenance"),
        "state": "ABSENT",
        "digest": None,
        "symbols": {},
        "error": None,
    }
    try:
        module = _load_module(decl, skill_root, cache)
    except ProviderUnavailable as exc:
        row["error"] = str(exc)
        return row
    row["state"] = "PRESENT"
    path = os.path.join(skill_root, decl["path"])
    if os.path.isfile(path):
        row["digest"] = _digest(path)
    missing = []
    for name in decl.get("symbols") or ():
        if not hasattr(module, name):
            row["symbols"][name] = "MISSING"
            missing.append(name)
            continue
        value = getattr(module, name)
        row["symbols"][name] = "callable" if callable(value) else _kind(value)
    if missing:
        row["state"] = "INCOMPLETE"
        row["error"] = "symbols missing: %s" % ", ".join(missing)
    return row


def _module_of(decl, cache):
    return cache.get(decl["module"])


# ── entrypoint reachability: exposure, not existence ──────────────────────────

def _file_for_parts(base, parts):
    """Exact module path under base -> file. None when that exact module is absent."""
    if not parts:
        return None
    head = os.path.join(base, *parts)
    if os.path.isfile(head + ".py"):
        return os.path.abspath(head + ".py")
    init = os.path.join(head, "__init__.py")
    return os.path.abspath(init) if os.path.isfile(init) else None


def _resolve_name(name, skill_root, entry_dir):
    """Resolve one dotted module name the way the entrypoint process would."""
    parts = [p for p in name.split(".") if p]
    roots = [entry_dir] + [os.path.join(skill_root, r) for r in _IMPORT_ROOT_RELS]
    seen = set()
    for base in roots:
        base = os.path.abspath(base)
        if base in seen or not os.path.isdir(base):
            continue
        seen.add(base)
        hit = _file_for_parts(base, parts)
        if hit:
            return hit
    return None


def _import_files(node, path, skill_root, entry_dir):
    """Files one import statement can load, plus names nothing resolves.

    Covers `import a.b.c` (with the intermediate packages Python loads),
    `import a.b.c as x`, `from a.b import c` (c may be a submodule), and the
    relative forms `from . import x` / `from .x import y`. A from-import name
    that is not a submodule is an attribute of the module, not a gap.
    """
    found, unresolved = [], []

    def _add(name_or_parts, base=None):
        parts = (name_or_parts.split(".") if isinstance(name_or_parts, str)
                 else list(name_or_parts))
        hit = (_file_for_parts(base, parts) if base is not None
               else _resolve_name(".".join(parts), skill_root, entry_dir))
        if hit:
            found.append((hit, ".".join(parts)))
        return hit

    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            for i in range(1, len(parts) + 1):
                hit = _add(parts[:i])
                if not hit and i == len(parts):
                    unresolved.append(alias.name)
    else:
        level = node.level or 0
        base = os.path.dirname(os.path.abspath(path))
        for _ in range(max(level - 1, 0)):
            base = os.path.dirname(base)
        mod_parts = [p for p in (node.module or "").split(".") if p]
        if level:
            if mod_parts and not _add(mod_parts, base):
                unresolved.append("." * level + (node.module or ""))
        elif node.module:
            if not _add(mod_parts):
                unresolved.append(node.module)
        for alias in node.names:
            if alias.name == "*":
                continue
            if level:
                _add(mod_parts + [alias.name], base)
            elif node.module:
                _add(mod_parts + [alias.name])
    return found, unresolved


def _dynamic_import_sites(path, rel, tree):
    """Call sites this static walk cannot follow. Reported, never resolved."""
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None)
        if name not in ("import_module", "__import__", "reload"):
            continue
        literal = None
        if node.args and isinstance(node.args[0], ast.Constant):
            literal = node.args[0].value
        sites.append({"file": rel, "line": getattr(node, "lineno", None),
                      "call": name, "literal": literal})
    return sites


def _entrypoint_closure(skill_root, targets, controls):
    """Static import closure of the supported entrypoint, with its controls.

    `valid` is False whenever the walker cannot be trusted (entrypoint missing
    or unparsable, closure empty, or a positive control not reached). A probe
    that cannot find a known-positive is broken, so the exposure verdict is
    PROBE_INVALID rather than NOT_REACHABLE in that case.
    """
    root = os.path.abspath(skill_root)
    entry = os.path.join(root, ENTRYPOINT_ROOT_REL)
    row = {
        "entrypoint": ENTRYPOINT_ROOT_REL,
        "walker": "static AST import closure: absolute, package-qualified, "
                  "from-import submodules and relative imports",
        "import_roots": [os.path.join(root, r) for r in _IMPORT_ROOT_RELS],
        "files_reached": 0,
        "files": [],
        "unresolved_imports": [],
        "dynamic_import_sites": [],
        "parse_errors": [],
        "targets": [],
        "controls": [],
        "positive_controls_ok": False,
        "valid": False,
        "error": None,
    }
    if not os.path.isfile(entry):
        row["error"] = "entrypoint file missing: %s" % ENTRYPOINT_ROOT_REL
        return row
    entry_dir = os.path.dirname(entry)
    reached = {}
    queue = [os.path.abspath(entry)]
    reached[os.path.abspath(entry)] = {"via": None, "name": "<entrypoint>"}
    while queue:
        current = queue.pop(0)
        rel = os.path.relpath(current, root)
        try:
            with open(current, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=current)
        except (OSError, SyntaxError, ValueError) as exc:
            row["parse_errors"].append({"file": rel, "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        row["dynamic_import_sites"].extend(_dynamic_import_sites(current, rel, tree))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            found, unresolved = _import_files(node, current, root, entry_dir)
            for name in unresolved:
                if name.split(".")[0] in _STDLIB:
                    continue  # stdlib is not a gap in the tree's own closure
                if name not in row["unresolved_imports"]:
                    row["unresolved_imports"].append(name)
            for hit, name in found:
                if hit not in reached:
                    reached[hit] = {"via": rel, "name": name}
                    queue.append(hit)
    row["files_reached"] = len(reached)
    row["files"] = sorted(os.path.relpath(p, root) for p in reached)

    def _row_for(name, role):
        path = _resolve_name(name, root, entry_dir)
        got = reached.get(path) if path else None
        return {"module": name, "role": role, "file": (
                    os.path.relpath(path, root) if path else None),
                "exists": bool(path), "reachable": bool(got),
                "via": (got or {}).get("via")}

    row["targets"] = [_row_for(name, "acceptance_capability") for name in targets]
    row["controls"] = [_row_for(name, "positive_control") for name in controls]
    row["positive_controls_ok"] = bool(row["controls"]) and all(
        c["reachable"] for c in row["controls"])
    problems = []
    if not row["files_reached"]:
        problems.append("closure is empty")
    if row["parse_errors"]:
        problems.append("entrypoint closure had %d parse errors" % len(row["parse_errors"]))
    if not row["positive_controls_ok"]:
        missed = [c["module"] for c in row["controls"] if not c["reachable"]]
        problems.append("positive control not reached: %s"
                        % (", ".join(missed) if missed else "none declared"))
    row["error"] = "; ".join(problems) or None
    row["valid"] = not problems
    return row


_CLOSURE_CACHE = {}


def _closure_for(skill_root, targets, controls):
    key = (os.path.abspath(skill_root), tuple(targets), tuple(controls))
    if key not in _CLOSURE_CACHE:
        _CLOSURE_CACHE[key] = _entrypoint_closure(skill_root, targets, controls)
    return _CLOSURE_CACHE[key]


# ── probes ───────────────────────────────────────────────────────────────────

def _probe(probe_id, ok, detail):
    return {"id": probe_id, "ok": bool(ok), "detail": detail}


def _probe_order(spec, cache, root, manifest):
    mod = _module_of(spec["providers"][0], cache)
    if mod is None:
        return [_probe("order_matches_declared", False, "provider not loaded"),
                _probe("order_is_enforced", False, "provider not loaded"),
                _probe("order_is_consumed_in_production", False, "provider not loaded")]
    expected = list(manifest["expected_artifact_order"])
    got = list(getattr(mod, "STAGE_ORDER", ()))
    out = [_probe("order_matches_declared", got == expected,
                  {"expected": expected, "observed": got})]

    registry = mod.RunRegistry()
    try:
        mod.check_stage("script_lyrics", registry)
        enforced = False
        detail = "check_stage admitted script_lyrics on an empty registry"
    except mod.ContractError as exc:
        code = getattr(exc, "code", None)
        enforced = code == "ORDER"
        detail = {"refused": True, "code": code}
    out.append(_probe("order_is_enforced", enforced, detail))

    missing = []
    for consumer in spec.get("consumers") or ():
        path = os.path.join(root, consumer["path"])
        if not os.path.isfile(path):
            missing.append({"path": consumer["path"], "state": "missing"})
            continue
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        imported = "story_first_contracts" in _imported_names(tree)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in set(consumer.get("symbols") or ())]
        missing.append({"path": consumer["path"], "imported": imported,
                        "calls": [n.func.attr for n in calls]})
    consumed = bool(missing) and all(
        row.get("imported") and row.get("calls") for row in missing)
    out.append(_probe("order_is_consumed_in_production", consumed, missing))
    return out


def _probe_gates(spec, cache):
    mod = _module_of(spec["providers"][0], cache)
    if mod is None:
        return [_probe("script_gate_requires_script_and_lyrics", False, "provider not loaded")]
    requires = set(mod.STAGE_REQUIRES.get("package_approval") or ())
    binds = set(mod.APPROVAL_BINDS.get("package_approval") or ())
    callables = all(callable(getattr(mod, n, None)) for n in
                    ("validate_identity", "validate_world", "validate_cast_manifest",
                     "validate_scene", "validate_scene_plan"))
    return [
        _probe("script_gate_requires_script_and_lyrics",
               {"script", "lyrics"} <= requires, sorted(requires)),
        _probe("approval_binds_script",
               {"script", "lyrics", "creative_package_manifest"} <= binds, sorted(binds)),
        _probe("gates_are_callable", callables,
               "envelope validators resolve as callables" if callables
               else "one or more envelope validators are not callable"),
    ]


def _probe_notion(spec, cache):
    mod = _module_of(spec["providers"][0], cache)
    if mod is None:
        return [_probe("ops_are_the_four_supported", False, "provider not loaded"),
                _probe("dead_connection_is_refused_offline", False, "provider not loaded")]
    expected_ops = ("search", "read_page", "query_data_source", "create_page")
    out = [_probe("ops_are_the_four_supported", tuple(mod.OPS) == expected_ops,
                  list(mod.OPS))]

    class _Dead:
        connection_ref = "s75-t29-offline-probe"

        def call(self, op, payload):  # noqa: ARG002 - signature parity
            raise RuntimeError("no transport in this probe")

    refused = False
    detail = None
    try:
        mod.resolve_client_library(_Dead(), "s75-t29-probe-namespace")
    except mod.ConnectionUnavailable as exc:
        refused = True
        detail = type(exc).__name__
    except mod.DiscoveryError as exc:
        refused = True
        detail = "%s (offline refusal)" % type(exc).__name__
    except Exception as exc:  # noqa: BLE001 - probe reports, never passes silently
        detail = "%s: %s" % (type(exc).__name__, exc)
    out.append(_probe("dead_connection_is_refused_offline", refused,
                      detail or "no refusal raised"))
    return out


def _probe_styles(spec, cache, root):
    mod = _module_of(spec["providers"][0], cache)
    styles = spec
    if mod is None:
        return [_probe("count_is_eighteen", False, "provider not loaded")]
    ids = list(getattr(mod, "STYLE_IDS", ()))
    expected = list(styles["expected_ids"])
    out = [
        _probe("count_is_eighteen",
               len(ids) == mod.MAX_STYLES == styles["expected_count"] and ids == expected,
               {"max_styles": mod.MAX_STYLES, "count": len(ids),
                "order_matches": ids == expected}),
        _probe("catalogue_is_valid",
               mod.validate_catalog() == styles["expected_count"]
               and len(mod.CATALOG) == styles["expected_count"],
               {"validate_catalog": mod.validate_catalog(), "catalog": len(mod.CATALOG)}),
        _probe("choice_surface_is_eighteen",
               len(mod.choice_rows()) == styles["expected_count"],
               len(mod.choice_rows())),
    ]
    bad = []
    for sid in ids:
        try:
            ok = all((mod.label(sid), mod.description(sid), mod.production_traits(sid),
                      mod.delivery_map(sid), mod.provider_hint(sid)))
        except Exception as exc:  # noqa: BLE001 - probe reports, never passes silently
            bad.append([sid, type(exc).__name__, str(exc)[:120]])
            continue
        if not ok:
            bad.append([sid, "empty", ""])
    out.append(_probe("every_style_compiles", not bad, bad or "%d styles compiled" % len(ids)))

    covered = set()
    for decl in styles.get("recipe_providers") or ():
        module = _module_of(decl, cache)
        if module is not None and hasattr(module, decl["ids_symbol"]):
            covered |= set(getattr(module, decl["ids_symbol"]))
    uncovered = sorted(set(ids) - covered)
    out.append(_probe("recipe_coverage_reported", True,
                      {"compiled_recipe_ids": sorted(covered),
                       "catalogue_trait_only": uncovered}))
    return out


def _probe_flavor(spec, cache, skill_root):
    mod = _module_of(spec["providers"][0], cache)
    if mod is None:
        return [_probe("onb_resolves_through_the_seam", False, "provider not loaded")]
    onb = mod.resolve(mod.ONB)
    n999 = mod.resolve(mod.N999)
    approval_rel = onb.get("character_approval_module")
    approval_exists = bool(approval_rel) and os.path.isfile(
        os.path.join(skill_root, approval_rel))
    return [
        _probe("onb_resolves_through_the_seam", onb.get("seam") == mod.SEAM,
               {"seam": onb.get("seam")}),
        _probe("onb_approval_module_is_present", approval_exists,
               {"declared": approval_rel, "exists": approval_exists}),
        _probe("n999_absence_is_preserved_not_filled",
               n999.get("character_approval_module") is None
               and not os.path.isfile(os.path.join(
                   skill_root, "scripts/core/character_bible/character_approval.py.999")),
               {"n999_character_approval_module": n999.get("character_approval_module")}),
        _probe("one_shared_core",
               onb.get("core_digest") == n999.get("core_digest") == mod.core_digest(),
               {"core_digest": onb.get("core_digest")}),
    ]


def _imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _mutation_calls(tree):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            modes = [a for a in node.args[1:2]]
            modes += [kw.value for kw in node.keywords if kw.arg == "mode"]
            for mode in modes:
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    if set(mode.value) & set("wax+"):
                        found.append("open(mode=%r)" % mode.value)
        elif isinstance(func, ast.Attribute) and func.attr in _MUTATING_ATTRS:
            root = func.value
            root_name = root.id if isinstance(root, ast.Name) else (
                root.attr if isinstance(root, ast.Attribute) else None)
            if root_name in _PATH_ROOTS:
                found.append("%s.%s()" % (root_name, func.attr))
    return found


def _held_rows(spec, skill_root):
    """Digest every held file that exists. Observation only; no claim is made."""
    held = []
    for item in spec.get("held_files") or ():
        row = {"name": item["name"], "path": item.get("path"), "state": item["state"],
               "sha256": None, "bytes": None}
        if item.get("path"):
            full = os.path.join(skill_root, item["path"])
            if os.path.isfile(full):
                row["sha256"] = _digest(full)
                row["bytes"] = os.path.getsize(full)
                row["state"] = "present_in_base"
            else:
                row["state"] = "absent_in_base_tree"
        held.append(row)
    return held


def _probe_emergency(spec, skill_root):
    source = os.path.abspath(__file__)
    with open(source, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source)
    imported = _imported_names(tree)
    touched = sorted(imported & set(HELD_MODULES))
    mutations = _mutation_calls(tree)
    held = _held_rows(spec, skill_root)
    return [
        _probe("adapter_imports_no_held_module", not touched,
               touched or "none of %s is imported" % ", ".join(HELD_MODULES)),
        _probe("adapter_has_no_mutation_path", not mutations,
               mutations or "no writable open(), os/shutil/pathlib mutation call"),
        _probe("held_files_reported", True, held),
    ]


# ── clause assembly ──────────────────────────────────────────────────────────

def _exposure_targets(spec):
    """Modules whose EXPOSURE this clause claims. Declared, never inferred:
    a clause with no exposure_targets makes no exposure claim (its acceptance
    phrase is not about exposure), and existence alone never claims exposure."""
    return list(spec.get("exposure_targets") or ())


def _positive_controls(manifest, fixture):
    control = (fixture or {}).get("control") or {}
    return list(control.get("reachability_positive_controls")
                or (manifest.get("reachability") or {}).get("positive_controls")
                or DEFAULT_POSITIVE_CONTROLS)


def _probe_exposure(spec, root, controls):
    """Both columns, reported side by side: existence (imported here) vs exposure
    (reached from the entrypoint without this checker importing it)."""
    targets = _exposure_targets(spec)
    closure = _closure_for(root, targets, controls)
    rows = [{
        "module": t["module"],
        "existing": bool(t["exists"]),
        "reachable_from_entrypoint": bool(t["reachable"]),
        "file": t["file"],
        "reached_via": t["via"],
    } for t in closure["targets"]]
    return [
        _probe("positive_control_reaches_known_module",
               closure["positive_controls_ok"],
               {"controls": closure["controls"], "files_reached": closure["files_reached"],
                "error": closure["error"]}),
        _probe("capability_modules_exist_and_resolve",
               all(t["existing"] for t in rows),
               [{"module": t["module"], "existing": t["existing"]} for t in rows]),
        _probe("capability_modules_are_exposed_by_entrypoint",
               closure["valid"] and all(t["existing"] and t["reachable_from_entrypoint"]
                                        for t in rows),
               rows),
    ]


def _probe_reachability(spec, cache, root, manifest, fixture):
    """The round-1 defect class, caught by the unit's own check."""
    controls = _positive_controls(manifest, fixture)
    targets = list((manifest.get("reachability") or {}).get("capability_targets") or ())
    closure = _closure_for(root, targets, controls)
    rows = closure["targets"]
    meanings = manifest.get("capability_meanings") or {}
    exposed = all(t["exists"] and t["reachable"] for t in rows) if rows else False
    return [
        _probe("closure_is_non_empty_and_controlled", closure["valid"],
               {"entrypoint": closure["entrypoint"], "files_reached": closure["files_reached"],
                "positive_controls_ok": closure["positive_controls_ok"],
                "controls": closure["controls"],
                "unresolved_imports": closure["unresolved_imports"],
                "dynamic_import_sites": closure["dynamic_import_sites"],
                "parse_errors": closure["parse_errors"],
                "error": closure["error"]}),
        _probe("exposes_meaning_is_declared_and_bound",
               meanings.get("existence") == EXISTENCE_MEANING
               and meanings.get("exposure") == EXPOSURE_MEANING
               and bool(meanings.get("existence")) and bool(meanings.get("exposure"))
               and (fixture.get("control") or {}).get("entrypoint_root") == ENTRYPOINT_ROOT_REL,
               {"existence": meanings.get("existence"), "exposure": meanings.get("exposure"),
                "entrypoint_root_declared_in_fixture":
                    (fixture.get("control") or {}).get("entrypoint_root"),
                "entrypoint_root_in_code": ENTRYPOINT_ROOT_REL}),
        _probe("declared_capabilities_reachable_from_entrypoint",
               closure["valid"] and exposed,
               rows),
    ]


_PROBE_TABLE = {
    "artifact_order": lambda spec, cache, root, manifest, fixture: _probe_order(spec, cache, root, manifest),
    "cast_world_script_gates": lambda spec, cache, root, manifest, fixture: _probe_gates(spec, cache),
    "notion": lambda spec, cache, root, manifest, fixture: _probe_notion(spec, cache),
    "styles_18": lambda spec, cache, root, manifest, fixture: _probe_styles(spec, cache, root),
    "flavor_parity": lambda spec, cache, root, manifest, fixture: _probe_flavor(spec, cache, root),
    "emergency_fixes_read_only": lambda spec, cache, root, manifest, fixture: _probe_emergency(spec, root),
    "entrypoint_reachability": lambda spec, cache, root, manifest, fixture: _probe_reachability(
        spec, cache, root, manifest, fixture),
}


def _entrypoint_report(skill_root, fixture, fixture_error=None):
    path = os.path.join(skill_root, ENTRYPOINT_REL)
    row = {"path": ENTRYPOINT_REL, "exists": os.path.isfile(path),
           "help_rc": None, "command_surface": None, "required_present": False,
           "required_surface_checked": False,
           "error": None}
    if not row["exists"]:
        row["error"] = "wrapper missing at %s" % ENTRYPOINT_REL
        return row
    try:
        proc = subprocess.run([sys.executable, path, "--help"], cwd=skill_root,
                              capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        row["error"] = "%s: %s" % (type(exc).__name__, exc)
        return row
    row["help_rc"] = proc.returncode
    surface = None
    for line in (proc.stdout or "").splitlines():
        start = line.find("{")
        end = line.find("}", start + 1)
        if start >= 0 and end > start:
            surface = [c.strip() for c in line[start + 1:end].split(",") if c.strip()]
            break
    row["command_surface"] = surface
    required = list((fixture.get("control") or {}).get("required_commands") or ())
    if proc.returncode != 0:
        row["error"] = "wrapper --help exited %d: %s" % (
            proc.returncode, (proc.stderr or "").strip()[:200])
        return row
    if surface is None:
        row["error"] = "no command surface found in wrapper --help output"
        return row
    missing = [c for c in required if c not in surface]
    row["required_present"] = not missing
    row["missing_required"] = missing
    row["required_surface_checked"] = True
    if fixture_error is not None:
        # the fixture is where required_commands lives; without it the surface
        # cannot be checked, so it is never reported as satisfied
        row["required_present"] = False
        row["required_surface_checked"] = False
        row["error"] = ("fixture unreadable, so the required command surface "
                        "cannot be checked: %s" % fixture_error)
    return row


def report(skill_root=None):
    """Build the receipt. Pure read: no write, no network, no provider call.

    Every tree fact is a receipt row. A missing fixture, manifest or entrypoint
    is a structured FAIL receipt -- never a traceback.
    """
    root = _skill_root(skill_root)
    manifest_path = os.path.join(_here(), MANIFEST_NAME)
    fixture_path = os.path.join(root, FIXTURE_REL)
    manifest, manifest_error = _read_json_optional(manifest_path)
    fixture, fixture_error = _read_json_optional(fixture_path)
    cache = {}

    tree_state = {
        "skill_root_readable": os.path.isdir(root),
        "manifest_present": manifest_error is None,
        "manifest_error": manifest_error,
        "fixture_present": fixture_error is None,
        "fixture_error": fixture_error,
        "fixture_expected_at": FIXTURE_REL,
    }
    fixture = fixture or {}
    if manifest is None:
        return {
            "schema": SCHEMA,
            "unit": None,
            "seam": SEAM,
            "skill_root": root,
            "tree_state": tree_state,
            "errors": ["manifest unreadable: %s" % manifest_error],
            "clause_order": [],
            "clauses": {},
            "ok": False,
        }

    clauses = {}
    clause_order = list(fixture.get("clause_order")
                        or list(manifest["clauses"].keys()))
    controls = _positive_controls(manifest, fixture)
    extensions = {}
    for name in clause_order:
        spec = manifest["clauses"][name]
        providers = [_provider_state(p, root, cache) for p in spec.get("providers") or ()]
        recipe_rows = [_provider_state(p, root, cache)
                       for p in spec.get("recipe_providers") or ()]
        probe_fn = _PROBE_TABLE.get(name)
        probes = probe_fn(spec, cache, root, manifest, fixture) if probe_fn else []
        if _exposure_targets(spec) and name != "entrypoint_reachability":
            probes = probes + _probe_exposure(spec, root, controls)
        ext = [_provider_state(p, root, cache) for p in spec.get("extensions") or ()]
        extensions[name] = ext

        required_ok = all(p["state"] == "PRESENT" for p in providers)
        probes_ok = all(p["ok"] for p in probes)
        status = "PASS" if (required_ok and probes_ok) else "FAIL"
        reason = None
        if not required_ok:
            reason = "; ".join("%s: %s" % (p["id"], p["error"] or p["state"])
                               for p in providers if p["state"] != "PRESENT")
        elif not probes_ok:
            reason = "; ".join("%s: %s" % (p["id"], p["detail"])
                               for p in probes if not p["ok"])
        clauses[name] = {
            "acceptance_phrase": spec.get("acceptance_phrase"),
            "status": status,
            "reason": reason,
            "existence": [p["state"] for p in providers],
            "providers": providers,
            "probes": probes,
            "extensions": ext,
        }
        if spec.get("recipe_providers"):
            clauses[name]["recipe_providers"] = recipe_rows

    entry = _entrypoint_report(root, fixture, fixture_error)
    closure = _closure_for(root,
                           list((manifest.get("reachability") or {}).get("capability_targets") or ()),
                           controls)
    held_spec = manifest["clauses"]["emergency_fixes_read_only"]
    held_rows = _held_rows(held_spec, root)
    flavor_provider = next((p for p in clauses["flavor_parity"]["providers"]), None)
    limitations = list(manifest.get("not_claimed") or ())
    cast_ext = clauses["cast_world_script_gates"]["extensions"]
    for row in cast_ext:
        if row["state"] != "PRESENT":
            limitations.append(
                "S75-T07 hardening (%s) is not in this tree: %s. Bound automatically "
                "when the accepted module lands; the base gates above are what is "
                "proved here." % (row["path"], row["error"] or row["state"]))
    if fixture_error is not None:
        limitations.append(
            "fixture unreadable at %s (%s): required_commands, clause_order and "
            "reachability_positive_controls fell back to the manifest and to "
            "built-in defaults" % (FIXTURE_REL, fixture_error))
    if not closure["valid"]:
        limitations.append("entrypoint reachability walk not valid: %s" % closure["error"])
    unreachable = [t["module"] for t in closure["targets"]
                   if t["exists"] and not t["reachable"]]
    if unreachable:
        limitations.append(
            "exist but are NOT exposed by the entrypoint (declared but reachable "
            "only because this checker imports them): %s. Closing that gap needs "
            "either a wiring change in the held scripts/core/intake_preflight/factory.py "
            "or a scope decision on A29's word 'exposes'; this unit does neither "
            "(see not_claimed)." % ", ".join(unreachable))

    ok = (all(c["status"] == "PASS" for c in clauses.values())
          and entry["required_present"]
          and tree_state["fixture_present"] and tree_state["manifest_present"])
    return {
        "schema": SCHEMA,
        "unit": manifest["unit"],
        "acceptance_id": manifest["acceptance_id"],
        "seam": SEAM,
        "skill_root": root,
        "base_sha": manifest.get("base_sha"),
        "python": sys.version.split()[0],
        "manifest": os.path.relpath(manifest_path, root),
        "fixture": FIXTURE_REL,
        "tree_state": tree_state,
        "capability_meanings": manifest.get("capability_meanings"),
        "capability_exposure": {
            "meaning": {"existence": EXISTENCE_MEANING, "exposure": EXPOSURE_MEANING},
            "entrypoint": closure["entrypoint"],
            "positive_controls": closure["controls"],
            "positive_controls_ok": closure["positive_controls_ok"],
            "walker_valid": closure["valid"],
            "walker_error": closure["error"],
            "files_reached": closure["files_reached"],
            "unresolved_imports": closure["unresolved_imports"],
            "dynamic_import_sites": closure["dynamic_import_sites"],
            "rows": [{"module": t["module"], "existing": bool(t["exists"]),
                      "reachable_from_entrypoint": bool(t["reachable"]),
                      "file": t["file"], "reached_via": t["via"]}
                     for t in closure["targets"]],
        },
        "flavor_provider": flavor_provider,
        "entrypoint": entry,
        "clause_order": clause_order,
        "clauses": clauses,
        "held_owner": held_spec.get("owner"),
        "held_policy": held_spec.get("policy"),
        "held_files": held_rows,
        "limitations": limitations,
        "ok": ok,
    }


def check(skill_root=None):
    receipt = report(skill_root)
    return receipt, bool(receipt["ok"])


def _entrypoints(skill_root=None):
    path = os.path.join(_skill_root(skill_root), FIXTURE_REL)
    fixture, error = _read_json_optional(path)
    fixture = fixture or {}
    return {"schema": fixture.get("schema"), "entrypoints": fixture.get("entrypoints"),
            "not_advertised": fixture.get("not_advertised"),
            "fixture_expected_at": FIXTURE_REL,
            "fixture_error": error}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = None
    pretty = False
    if "--skill-root" in argv:
        i = argv.index("--skill-root")
        if i + 1 >= len(argv):
            sys.stderr.write("--skill-root needs a directory\n")
            return 2
        root = argv[i + 1]
        del argv[i:i + 2]
    if "--pretty" in argv:
        pretty = True
        argv.remove("--pretty")
    command = argv[0] if argv else "report"
    if command in ("-h", "--help"):
        sys.stdout.write(__doc__ or "")
        return 0
    if command == "entrypoints":
        sys.stdout.write(json.dumps(_entrypoints(root), indent=2, sort_keys=True) + "\n")
        return 0
    if command == "report":
        receipt = report(root)
        sys.stdout.write(json.dumps(receipt, indent=2 if pretty else None,
                                    sort_keys=True) + "\n")
        return 0
    if command == "check":
        receipt, ok = check(root)
        sys.stdout.write(json.dumps(receipt, indent=2 if pretty else None,
                                    sort_keys=True) + "\n")
        sys.stderr.write("S75-T29 onboarding package: %s\n"
                         % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    sys.stderr.write("unknown command %r (report|check|entrypoints)\n" % command)
    return 2


if __name__ == "__main__":
    sys.exit(main())
