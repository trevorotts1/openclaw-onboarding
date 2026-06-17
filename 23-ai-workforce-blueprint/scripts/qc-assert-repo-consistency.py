#!/usr/bin/env python3
"""
qc-assert-repo-consistency.py — the SINGLE cross-checking gate that makes it
IMPOSSIBLE for a department / role / SOP / persona to ship inconsistent.

WHY THIS EXISTS (the bug it kills)
----------------------------------
The repo carries SIX independent sources of truth that, until now, NOTHING
cross-checked:

  1. FLOOR              department-naming-map.json `.mandatory` (22) +
                        the 7 universal-primary vertical-pack depts = 29.
                        Enforced on-disk by department-floor.py.
  2. ROSTERS            suggested-roles/<dept>-suggested-roles.md, parsed by
                        create_role_workspaces.parse_roster() — the proposed
                        specialist menu per department.
  3. ROLE LIBRARY       templates/role-library/_index.json + the per-dept
                        role template docs (the pre-written role + Section-9
                        SOP bodies). Resolved by create_role_workspaces.
                        library_lookup() (the normalizer that matches roster
                        names/slugs to library titles/slugs).
  4. SOP SOURCE         every floor dept's roles must resolve a real SOP source:
                        the Skill-23 role-library template (canonical copy path,
                        guarded by sop_boundary_gate.is_canonical_dept) OR, for
                        personal-assistant, the Skill-42 specialist library.
  5. PERSONA DOMAINS    build-workforce.create_governing_personas_md /
                        generate_persona_matrix `dept_to_domains`, and
                        create_role_workspaces.write_governing_personas_md
                        `DEPT_DOMAIN_HINTS`. A floor dept MISSING from these
                        maps silently falls back to the generic ['leadership']
                        pool — wrong personas, no error.
  6. ORPHANS            a roster with no floor/library home, or a floor dept the
                        library can't reach.

Six departments once shipped UNBUILDABLE because no gate cross-checked floor vs
rosters vs library vs persona maps. This gate HARD-ASSERTS every relationship
and exits non-zero on ANY drift, printing a per-department table.

It uses the SAME functions the build uses (parse_roster, library_lookup,
normalize_dept, evaluate_floor, is_canonical_dept) so the gate can NEVER
disagree with what the build will actually do.

USAGE
  python3 qc-assert-repo-consistency.py            # human table + PASS/FAIL to stdout
  python3 qc-assert-repo-consistency.py --json     # machine-readable verdict
  python3 qc-assert-repo-consistency.py --skill-dir /path/to/23-ai-workforce-blueprint
                                                   # check an explicit skill dir
                                                   # (used by the sandbox tests)

EXIT CODES
  0  every floor dept is consistent across floor/roster/library/SOP/persona;
     no orphans.
  5  DRIFT FOUND (at least one relationship is broken). Details printed.
  2  could not load the repo (missing naming map / index / scripts).

Read-only. Never writes. Idempotent.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Resolution helpers — load the REAL build modules so the gate mirrors the build.
# ─────────────────────────────────────────────────────────────────────────────

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# Library dept alias: roster/floor dept id -> role-library `dept` value in
# _index.json. Mirrors create_role_workspaces._LIBRARY_DEPT_ALIASES so the gate
# resolves the same library folder the build resolves.
_LIBRARY_DEPT_ALIASES = {
    "legal": "legal-compliance",
    "billing-finance": "billing",
    "video-production": "video",
    "audio-production": "audio",
}

# Departments whose SOP/role source is a SIBLING skill library, not the Skill-23
# role-library. personal-assistant pulls its 29 specialists from the Skill-42
# personal-assistant-library (42-personal-assistant-library/specialists/). The
# gate resolves those roster roles against that library instead of role-library.
_SIBLING_LIBRARY_DEPTS = {
    "personal-assistant": "42-personal-assistant-library/specialists",
}


class Repo:
    """Holds the loaded skill modules + the source-of-truth data."""

    def __init__(self, skill_dir):
        self.skill_dir = Path(skill_dir).resolve()
        self.scripts = self.skill_dir / "scripts"
        self.lib = self.skill_dir / "lib"
        self.naming_map_path = self.skill_dir / "department-naming-map.json"
        self.index_path = self.skill_dir / "templates" / "role-library" / "_index.json"
        self.rosters_dir = self.skill_dir / "suggested-roles"
        self.repo_root = self.skill_dir.parent

        # Make lib/ importable for create_role_workspaces' detect_platform import,
        # and scripts/ importable for sop_boundary_gate.
        for p in (str(self.lib), str(self.scripts)):
            if p not in sys.path:
                sys.path.insert(0, p)

        # HERMETIC RESOLUTION: force create_role_workspaces._resolve_skill_dir()
        # (used by library_lookup) to read the skill dir UNDER TEST, not whatever
        # is live-installed at ~/.openclaw/skills. Without this the gate would
        # silently check the installed copy's _index.json instead of the repo's,
        # so a repo fix (renamed file / patched index) would never be seen and a
        # sandbox negative-test would resolve against the real install. ROLE_LIBRARY_PATH
        # is the first-priority override in _resolve_skill_dir().
        os.environ["ROLE_LIBRARY_PATH"] = str(self.skill_dir)

        # Load the REAL build resolution functions.
        self.crw = _load_module(
            "crw_consistency", self.scripts / "create_role_workspaces.py")
        # Drop any cached library index so the forced skill dir is read fresh.
        try:
            self.crw._LIBRARY_INDEX_CACHE.clear()
        except Exception:
            pass
        self.floor_mod = _load_module(
            "floor_consistency", self.scripts / "department-floor.py")
        self.boundary = _load_module(
            "boundary_consistency", self.scripts / "sop_boundary_gate.py")

        # Build-workforce is heavy to import (module-level side effects), so we
        # read its persona dept_to_domains maps + DEPT_TO_SUGGESTED_ROLES builder
        # statically rather than importing the whole module.
        self.build_workforce_src = (self.scripts / "build-workforce.py").read_text(
            encoding="utf-8")

        # Source data.
        self.naming_map = json.loads(self.naming_map_path.read_text(encoding="utf-8"))
        self.index = json.loads(self.index_path.read_text(encoding="utf-8"))

    # ── FLOOR ────────────────────────────────────────────────────────────────
    def floor_dept_ids(self):
        """The 29 floor dept ids: 22 mandatory + 7 universal-primary verticals.

        These are EXACTLY the dept_id keys that reach selected_departments in
        build-workforce.py (canonical ids, not legacy aliases), so they are the
        keys the persona maps must be checked against.
        """
        nm = self.naming_map
        mandatory = list((nm.get("mandatory") or {}).keys())
        ups = self.floor_mod.universal_primary_vertical_departments(nm)
        return mandatory, ups

    # ── ROSTER FILENAME RESOLUTION ─────────────────────────────────────────────
    def roster_filename_for(self, dept_id):
        """Resolve the roster filename a floor dept builds from.

        Mirrors build-workforce.build_dept_to_suggested_roles():
          - mandatory dept:           naming_map.mandatory[id].suggested_roles_file
          - universal-primary dept:   prefer its OWN dedicated
                                       <id>-suggested-roles.md when present (the
                                       file the --from-roster path uses for an
                                       incrementally-added dept), else fall back
                                       to the pack's base_suggested_roles.
        Returns (filename, source) where source describes how it resolved.
        """
        nm = self.naming_map
        m = (nm.get("mandatory") or {}).get(dept_id)
        if isinstance(m, dict) and m.get("suggested_roles_file"):
            return m["suggested_roles_file"], "mandatory.suggested_roles_file"

        # Universal-primary vertical dept.
        dedicated = f"{dept_id}-suggested-roles.md"
        if (self.rosters_dir / dedicated).is_file():
            return dedicated, "dedicated <dept>-suggested-roles.md"

        # Fall back to the pack's base_suggested_roles for this dept id.
        for pack in (nm.get("vertical_packs") or {}).values():
            if not isinstance(pack, dict):
                continue
            for dept in pack.get("auto_add_departments", []) or []:
                if isinstance(dept, dict) and dept.get("id") == dept_id:
                    base = dept.get("base_suggested_roles")
                    if base:
                        return base, "vertical base_suggested_roles"
        return None, "UNRESOLVED"

    # ── ROLE -> LIBRARY / SOP RESOLUTION (mirrors the real build) ───────────────
    def _resolve_role_in_skill23(self, role, dept_id):
        """True if a role dict resolves a Skill-23 role-library template.

        EXACT build order (create_role_workspace -> try_library_fill):
          1. role_metadata['slug'] (lib_key) tried FIRST
          2. role NAME tried as fallback
        """
        slug = (role.get("slug") or "").strip()
        if slug and self.crw.library_lookup(slug, dept_id)[1] is not None:
            return True
        return self.crw.library_lookup(role["name"], dept_id)[1] is not None

    def _resolve_role_in_sibling(self, role, sibling_rel):
        """True if a role resolves a sibling-skill specialist library folder.

        Used for personal-assistant -> Skill-42. Matches the roster slug/name
        against the specialist directory slugs (NN-<slug>/ stripped of the
        numeric prefix), normalized for hyphen/case.
        """
        sib_dir = self.repo_root / sibling_rel
        if not sib_dir.is_dir():
            return False
        avail = set()
        for d in sib_dir.iterdir():
            if d.is_dir():
                avail.add(_norm(re.sub(r"^\d+-", "", d.name)))
        candidates = {_norm(role.get("slug", "")), _norm(role.get("name", ""))}
        # Token-overlap match: a roster name like "My Coach" -> dir "my-coach".
        for cand in candidates:
            if not cand:
                continue
            if cand in avail:
                return True
            for a in avail:
                if cand in a or a in cand:
                    return True
        # Looser token-subset match for multi-word names.
        name_tokens = [t for t in _norm(role.get("name", "")) and
                       re.sub(r"[^a-z0-9 ]", " ", role.get("name", "").lower()).split()
                       if len(t) > 3]
        for a in avail:
            if name_tokens and all(_norm(t) in a for t in name_tokens):
                return True
        return False

    def resolve_role_sop_source(self, role, dept_id):
        """Return ('skill23'|'skill42'|None) for where this role's SOP source is.

        None means the role would fall to the stub+LLM authoring path — which, for
        a canonical (library) department, is a SOP-boundary-gate violation: the
        role ships with no SOP source. That is exactly the drift this gate fails.
        """
        if dept_id in _SIBLING_LIBRARY_DEPTS:
            if self._resolve_role_in_sibling(role, _SIBLING_LIBRARY_DEPTS[dept_id]):
                return "skill42"
            # PA roles can ALSO be Skill-23 universal roles (director/qc/etc).
            if self._resolve_role_in_skill23(role, dept_id):
                return "skill23"
            return None
        if self._resolve_role_in_skill23(role, dept_id):
            return "skill23"
        return None

    # ── PERSONA-DOMAIN MAPS (parse them out of the source, no heavy import) ─────
    def _parse_persona_map_keys(self, func_name):
        """Extract the dept_to_domains/DEPT_DOMAIN_HINTS key set from a function
        body in build-workforce.py (create_governing_personas_md /
        generate_persona_matrix) or create_role_workspaces.py.

        We parse the literal dict assigned to `dept_to_domains` /
        `DEPT_DOMAIN_HINTS` inside the named function, returning the set of keys.
        """
        if func_name in ("create_governing_personas_md", "generate_persona_matrix"):
            src = self.build_workforce_src
            var = "dept_to_domains"
        else:  # write_governing_personas_md (create_role_workspaces.py)
            src = (self.scripts / "create_role_workspaces.py").read_text(encoding="utf-8")
            var = "DEPT_DOMAIN_HINTS"

        # Find the function, then the dict literal assigned to `var` inside it.
        fm = re.search(r"\ndef\s+" + re.escape(func_name) + r"\s*\(", src)
        if not fm:
            return set()
        body = src[fm.end():]
        # Stop at the next top-level def.
        nm = re.search(r"\ndef\s+\w+\s*\(", body)
        if nm:
            body = body[:nm.start()]
        dm = re.search(re.escape(var) + r"\s*=\s*\{", body)
        if not dm:
            return set()
        # Capture to the matching close brace.
        i = dm.end() - 1
        depth = 0
        start = i
        for j in range(i, len(body)):
            if body[j] == "{":
                depth += 1
            elif body[j] == "}":
                depth -= 1
                if depth == 0:
                    block = body[start:j + 1]
                    break
        else:
            return set()
        # Keys are the quoted strings that appear as dict keys (followed by ':').
        return set(re.findall(r"['\"]([a-z0-9\-]+)['\"]\s*:", block))

    def persona_map_keys(self):
        return {
            "create_governing_personas_md":
                self._parse_persona_map_keys("create_governing_personas_md"),
            "generate_persona_matrix":
                self._parse_persona_map_keys("generate_persona_matrix"),
            "write_governing_personas_md(DEPT_DOMAIN_HINTS)":
                self._parse_persona_map_keys("write_governing_personas_md"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(skill_dir):
    try:
        repo = Repo(skill_dir)
    except Exception as e:
        return {"rc": 2, "fatal": f"could not load repo: {e}", "rows": [],
                "orphans": {}, "summary": {}}

    mandatory, ups = repo.floor_dept_ids()
    floor = mandatory + ups
    persona_keys = repo.persona_map_keys()

    # Each persona map must contain the floor dept id as a key (else the dept
    # silently falls back to the generic ['leadership'] pool).
    persona_map_names = list(persona_keys.keys())

    rows = []
    failures = []  # list of (dept, category, detail)

    for dept_id in floor:
        is_mandatory = dept_id in mandatory
        # (a) ROSTER resolves + PARSES
        roster_fn, roster_src = repo.roster_filename_for(dept_id)
        roster_path = repo.rosters_dir / roster_fn if roster_fn else None
        roster_ok = False
        roles = []
        roster_detail = roster_fn or "UNRESOLVED"
        if roster_path and roster_path.is_file():
            try:
                roles = repo.crw.parse_roster(roster_path)
                roster_ok = len(roles) > 0
            except Exception as e:
                roster_detail = f"{roster_fn} (parse error: {e})"
        if not roster_ok:
            failures.append((dept_id, "ROSTER",
                             f"roster '{roster_detail}' missing or parsed 0 roles"))

        # (b)+(d) every roster role resolves a LIBRARY/SOP source
        lib_dept = _LIBRARY_DEPT_ALIASES.get(dept_id, dept_id)
        unresolved_roles = []
        sop_sources = {"skill23": 0, "skill42": 0}
        for r in roles:
            src = repo.resolve_role_sop_source(r, dept_id)
            if src is None:
                unresolved_roles.append(r.get("slug") or r.get("name"))
            else:
                sop_sources[src] = sop_sources.get(src, 0) + 1
        library_ok = roster_ok and not unresolved_roles
        sop_ok = library_ok  # every role has a SOP source iff every role resolved
        if roster_ok and unresolved_roles:
            failures.append((dept_id, "LIBRARY/SOP",
                             f"{len(unresolved_roles)} roster role(s) resolve NO "
                             f"library/SOP template: {unresolved_roles}"))

        # (c) DRY-RUN INSTANTIATE cleanly (roles materialize). We exercise the
        # real instantiate_department in dry-run against a temp dept path and
        # confirm it reports the same role count the roster parsed.
        instantiate_ok = False
        inst_detail = ""
        if roster_ok:
            try:
                import contextlib
                import io
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    dept_path = Path(td) / f"{dept_id}-dept"
                    # instantiate_department prints DRY-RUN lines to stdout; mute
                    # them so the gate's table is the only thing on stdout.
                    _sink = io.StringIO()
                    with contextlib.redirect_stdout(_sink), \
                            contextlib.redirect_stderr(_sink):
                        summary = repo.crw.instantiate_department(
                            dept_path, dept_id, roles,
                            workspace_root=Path(td), dry_run=True)
                    created = len(summary.get("roles_created", []))
                    instantiate_ok = created == len(roles)
                    inst_detail = f"{created}/{len(roles)} roles"
                    if not instantiate_ok:
                        failures.append((dept_id, "INSTANTIATE",
                                         f"dry-run materialized {created} of "
                                         f"{len(roles)} roster roles"))
            except Exception as e:
                inst_detail = f"error: {e}"
                failures.append((dept_id, "INSTANTIATE", f"dry-run raised: {e}"))

        # (e) PERSONA DOMAIN mapping present in EVERY persona map (no generic
        # ['leadership'] fallback).
        missing_persona_maps = [
            name for name in persona_map_names
            if dept_id not in persona_keys[name]
        ]
        persona_ok = not missing_persona_maps
        if missing_persona_maps:
            failures.append((dept_id, "PERSONA-DOMAIN",
                             f"missing dept-domain mapping in: "
                             f"{', '.join(missing_persona_maps)} "
                             f"(would fall back to generic ['leadership'])"))

        # (d) SOP: canonical depts MUST be on the copy path (boundary gate). A
        # floor dept that the boundary gate does NOT consider canonical (no
        # role-library tree) and is not a sibling-library dept would be authored
        # — a token-economics + determinism drift.
        canonical = repo.boundary.is_canonical_dept(dept_id)
        sibling = dept_id in _SIBLING_LIBRARY_DEPTS
        sop_source_ok = canonical or sibling
        if not sop_source_ok:
            failures.append((dept_id, "SOP-SOURCE",
                             "floor dept has NO role-library tree and is not a "
                             "sibling-library dept — its SOPs would be LLM-authored "
                             "(non-deterministic, token burn)"))

        status = "OK" if (roster_ok and library_ok and instantiate_ok
                          and persona_ok and sop_ok and sop_source_ok) else "DRIFT"
        rows.append({
            "dept": dept_id,
            "tier": "mandatory" if is_mandatory else "universal-primary",
            "roster": roster_fn or "—",
            "roster_ok": roster_ok,
            "roles": len(roles),
            "library_ok": library_ok,
            "unresolved_roles": unresolved_roles,
            "instantiate": inst_detail,
            "instantiate_ok": instantiate_ok,
            "sop_sources": sop_sources,
            "sop_ok": sop_ok and sop_source_ok,
            "persona_ok": persona_ok,
            "missing_persona_maps": missing_persona_maps,
            "status": status,
        })

    # (f) ORPHANS — no roster without a floor/library home; no library dept in
    # the floor that's unreachable.
    floor_set = set(floor)
    # Rosters that map to NO floor dept and NO library dept.
    roster_files = sorted(
        f.name for f in repo.rosters_dir.glob("*-suggested-roles.md"))
    # Build the set of every roster filename a floor dept resolves to.
    floor_roster_files = set()
    for d in floor:
        fn, _ = repo.roster_filename_for(d)
        if fn:
            floor_roster_files.add(fn)
    # A roster is an orphan if it is not referenced by ANY floor dept AND its
    # implied dept is not a library dept AND not the always-built master-orch.
    lib_depts = set(repo.index.get("departments", {}).keys())
    KNOWN_NON_FLOOR_OK = {"master-orchestrator-suggested-roles.md"}
    orphan_rosters = []
    for rf in roster_files:
        if rf in floor_roster_files or rf in KNOWN_NON_FLOOR_OK:
            continue
        implied = rf[:-len("-suggested-roles.md")]
        implied_lib = _LIBRARY_DEPT_ALIASES.get(implied, implied)
        # An extra roster that maps to a real library dept is a flavor/vertical
        # roster, fine. Only flag rosters with no floor + no library home.
        if implied in floor_set or implied_lib in lib_depts:
            continue
        orphan_rosters.append(rf)
    if orphan_rosters:
        for rf in orphan_rosters:
            failures.append(("(orphan)", "ORPHAN-ROSTER",
                             f"roster '{rf}' has no floor dept and no library dept"))

    # A floor dept whose library dept folder is missing entirely (unreachable).
    unreachable_floor = []
    for d in floor:
        if d in _SIBLING_LIBRARY_DEPTS:
            continue
        lib_dept = _LIBRARY_DEPT_ALIASES.get(d, d)
        if lib_dept not in lib_depts:
            unreachable_floor.append(d)
    if unreachable_floor:
        for d in unreachable_floor:
            failures.append((d, "ORPHAN-FLOOR",
                             f"floor dept '{d}' has no role-library dept "
                             f"(looked for '{_LIBRARY_DEPT_ALIASES.get(d, d)}')"))

    orphans = {
        "orphan_rosters": orphan_rosters,
        "unreachable_floor": unreachable_floor,
    }

    drift_depts = sorted({f[0] for f in failures})
    rc = 0 if not failures else 5
    summary = {
        "floor_count": len(floor),
        "mandatory_count": len(mandatory),
        "universal_primary_count": len(ups),
        "depts_ok": sum(1 for r in rows if r["status"] == "OK"),
        "depts_drift": sum(1 for r in rows if r["status"] == "DRIFT"),
        "total_roster_roles": sum(r["roles"] for r in rows),
        "total_unresolved_roles": sum(len(r["unresolved_roles"]) for r in rows),
        "failure_count": len(failures),
        "drift_depts": drift_depts,
        "persona_map_names": persona_map_names,
        "naming_map_version": repo.naming_map.get("version"),
        "index_version": repo.index.get("version"),
    }
    return {"rc": rc, "fatal": None, "rows": rows, "orphans": orphans,
            "failures": failures, "summary": summary}


def _print_table(verdict):
    s = verdict["summary"]
    print("=" * 110)
    print("REPO CONSISTENCY GATE — floor x roster x library x SOP x persona "
          "(qc-assert-repo-consistency.py)")
    print(f"naming-map v{s.get('naming_map_version')}  |  role-library index "
          f"v{s.get('index_version')}  |  floor = {s['mandatory_count']} mandatory "
          f"+ {s['universal_primary_count']} universal-primary = {s['floor_count']}")
    print("=" * 110)
    hdr = (f"{'DEPT':<30}{'ROSTER':<7}{'LIBRARY':<9}{'INSTANTIATE':<14}"
           f"{'SOP':<6}{'PERSONA':<9}{'STATUS'}")
    print(hdr)
    print("-" * 110)
    for r in verdict["rows"]:
        def yn(b):
            return "yes" if b else "NO"
        print(f"{r['dept']:<30}"
              f"{yn(r['roster_ok']):<7}"
              f"{yn(r['library_ok']):<9}"
              f"{r['instantiate']:<14}"
              f"{yn(r['sop_ok']):<6}"
              f"{yn(r['persona_ok']):<9}"
              f"{r['status']}")
    print("-" * 110)
    print(f"departments: {s['depts_ok']} OK, {s['depts_drift']} DRIFT   |   "
          f"roster roles: {s['total_roster_roles']}   |   "
          f"unresolved roles: {s['total_unresolved_roles']}   |   "
          f"failures: {s['failure_count']}")
    orphans = verdict.get("orphans", {})
    if orphans.get("orphan_rosters"):
        print(f"orphan rosters: {orphans['orphan_rosters']}")
    if orphans.get("unreachable_floor"):
        print(f"unreachable floor depts: {orphans['unreachable_floor']}")
    if verdict.get("failures"):
        print("\nFAILURE DETAIL:")
        for dept, cat, detail in verdict["failures"]:
            print(f"  [{cat}] {dept}: {detail}")
    print("=" * 110)
    if verdict["rc"] == 0:
        print(f"RESULT: PASS — all {s['floor_count']} floor departments are "
              f"consistent across floor/roster/library/SOP/persona (rc=0)")
    else:
        print(f"RESULT: FAIL — {len(verdict['summary']['drift_depts'])} entity(ies) "
              f"with drift, {s['failure_count']} broken relationship(s) (rc={verdict['rc']})")


def main(argv):
    parser = argparse.ArgumentParser(
        description="Cross-check floor x roster x library x SOP x persona.")
    parser.add_argument("--skill-dir", default=None,
                        help="Path to the 23-ai-workforce-blueprint skill dir "
                             "(default: this script's parent skill dir).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of the table.")
    args = parser.parse_args(argv)

    skill_dir = args.skill_dir or str(Path(__file__).resolve().parent.parent)
    verdict = evaluate(skill_dir)

    if verdict.get("fatal"):
        if args.json:
            print(json.dumps(verdict, indent=2))
        else:
            print(f"FATAL: {verdict['fatal']}", file=sys.stderr)
        return verdict["rc"]

    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        _print_table(verdict)
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
