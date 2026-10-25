#!/usr/bin/env python3
"""S75-T29 onboarding package adapter — assembles the onboarding flavor.

One job: prove that the ONB supported entrypoint still reaches the four things
A29 names, using the modules the other accepted units own. It resolves, it
reads, it reports. It never writes, never generates, never calls a provider.

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


# ── probes ───────────────────────────────────────────────────────────────────

def _probe(probe_id, ok, detail):
    return {"id": probe_id, "ok": bool(ok), "detail": detail}


def _probe_order(spec, cache, manifest):
    mod = _module_of(spec["providers"][0], cache)
    if mod is None:
        return [_probe("order_matches_declared", False, "provider not loaded"),
                _probe("order_is_enforced", False, "provider not loaded")]
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

_PROBE_TABLE = {
    "artifact_order": lambda spec, cache, root, manifest: _probe_order(spec, cache, manifest),
    "cast_world_script_gates": lambda spec, cache, root, manifest: _probe_gates(spec, cache),
    "notion": lambda spec, cache, root, manifest: _probe_notion(spec, cache),
    "styles_18": lambda spec, cache, root, manifest: _probe_styles(spec, cache, root),
    "flavor_parity": lambda spec, cache, root, manifest: _probe_flavor(spec, cache, root),
    "emergency_fixes_read_only": lambda spec, cache, root, manifest: _probe_emergency(spec, root),
}


def _entrypoint_report(skill_root, fixture):
    path = os.path.join(skill_root, ENTRYPOINT_REL)
    row = {"path": ENTRYPOINT_REL, "exists": os.path.isfile(path),
           "help_rc": None, "command_surface": None, "required_present": False,
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
    return row


def report(skill_root=None):
    """Build the receipt. Pure read: no write, no network, no provider call."""
    root = _skill_root(skill_root)
    manifest_path = os.path.join(_here(), MANIFEST_NAME)
    fixture_path = os.path.join(root, FIXTURE_REL)
    manifest = _read_json(manifest_path)
    fixture = _read_json(fixture_path)
    cache = {}

    clauses = {}
    order = list((fixture.get("clause_order")
                  or list(manifest["clauses"].keys())))
    extensions = {}
    for name in order:
        spec = manifest["clauses"][name]
        providers = [_provider_state(p, root, cache) for p in spec.get("providers") or ()]
        recipe_rows = [_provider_state(p, root, cache)
                       for p in spec.get("recipe_providers") or ()]
        probe_fn = _PROBE_TABLE.get(name)
        probes = probe_fn(spec, cache, root, manifest) if probe_fn else []
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
            "providers": providers,
            "probes": probes,
            "extensions": ext,
        }
        if spec.get("recipe_providers"):
            clauses[name]["recipe_providers"] = recipe_rows

    entry = _entrypoint_report(root, fixture)
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

    ok = all(c["status"] == "PASS" for c in clauses.values()) and entry["required_present"]
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
        "flavor_provider": flavor_provider,
        "entrypoint": entry,
        "clause_order": order,
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
    fixture = _read_json(os.path.join(_skill_root(skill_root), FIXTURE_REL))
    return {"schema": fixture.get("schema"), "entrypoints": fixture.get("entrypoints"),
            "not_advertised": fixture.get("not_advertised")}


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
