#!/usr/bin/env python3
"""
qc-assert-repo-consistency.py — the SINGLE cross-checking gate that makes it
IMPOSSIBLE for a department / role / SOP / persona to ship inconsistent.

WHY THIS EXISTS (the bug it kills)
----------------------------------
The repo carries SIX independent sources of truth that, until now, NOTHING
cross-checked:

  1. FLOOR              department-naming-map.json `.mandatory` (22) +
                        the 6 universal-primary vertical-pack depts = 28.
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


# ═════════════════════════════════════════════════════════════════════════════
# ARTIFACT-COVERAGE GATE (v12.25.0) — "complete check for everything"
# ─────────────────────────────────────────────────────────────────────────────
# The 5-dimension gate above guarantees every floor dept is consistent across
# floor/roster/library/SOP/persona. This SECOND gate closes the remaining classes
# of drift where a floor department / role / version / skill / bootstrap file can
# silently fall out of a DOWNSTREAM artifact even though the 5-dimension gate is
# green:
#
#   ORG-CHART     every floor dept (and its roster roles) is represented in the
#                 org-chart generator output.
#   ROUTING       the universal routing map covers every floor dept (no floor
#                 dept unrouted -> work falls back to general-task silently).
#   COMMAND-CENTER the Command Center departments.json generator covers every
#                 floor dept (else no Kanban column / topic for that dept).
#   DREAMING      the per-dept workspace scaffolding (DREAMS.md) covers every
#                 floor dept (none excluded by a hardcoded subset).
#   BOOTSTRAP     the core/bootstrap template files (IDENTITY/SOUL/AGENTS/USER/
#                 TOOLS/HEARTBEAT shipped templates + MEMORY runtime-seeded) exist
#                 and the canonical 7-file enumeration names all seven.
#   SKILLS-COUNT  install.sh active-skill count == README count == actual skill
#                 dir tree (the recurring install.sh/README/tree drift).
#   VERSION       every version marker across the repo agrees (the bump-version
#                 9-marker set + cc-compat.json onboardingVersion).
#
# DESIGN — mirror the build, never re-derive it. ORG-CHART / ROUTING / CC / DREAMING
# are all DERIVED at build time by iterating `selected_departments`. There is no
# static per-dept dict to diff; the drift risk is a generator that drops a dept,
# hardcodes a subset, or is unwired. So this gate SYNTHESIZES a `selected_departments`
# covering ALL floor depts (using the SAME naming-map metadata the build uses via
# load_canonical_floor() + the vertical-pack one-liners) and runs the REAL generator
# functions (generate_org_chart / write_universal_routing_map / generate_departments_json),
# then asserts every floor dept appears in the output. A generator that silently
# omits a floor dept FAILS. It also statically asserts each generator is WIRED
# (called from build_from_config) so a deleted call site FAILS too.
#
# EXIT CODES (combined with the 5-dimension gate in main()):
#   0  every dimension consistent.
#   6  ARTIFACT DRIFT FOUND (at least one downstream artifact omits a floor dept,
#      counts disagree, a bootstrap file is missing, or versions drift).
#   2  could not load the repo to run the artifact checks.
# ═════════════════════════════════════════════════════════════════════════════

# The 7 OpenClaw bootstrap ("core.md") files. Six ship as repo-root templates;
# MEMORY.md is intentionally NOT shipped — it is seeded fresh+empty per agent at
# install time (a committed MEMORY template would leak one client's facts to the
# next). So MEMORY is required to be REFERENCED as a core file but must NOT be a
# committed template.
_BOOTSTRAP_TEMPLATE_FILES = ["IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md",
                             "TOOLS.md", "HEARTBEAT.md"]
_BOOTSTRAP_RUNTIME_FILES = ["MEMORY.md"]
_BOOTSTRAP_ALL = _BOOTSTRAP_TEMPLATE_FILES + _BOOTSTRAP_RUNTIME_FILES

# Generators that MUST stay wired into the build (call-site presence check).
_REQUIRED_GENERATOR_CALLS = [
    "generate_org_chart(",
    "write_universal_routing_map(",
    "generate_departments_json(",
]


def _synthesize_full_floor_departments(repo):
    """Build a `selected_departments` dict covering ALL floor depts, shaped exactly
    like the dict the real build feeds the generators ({name, emoji, head,
    description} per dept id). Mandatory depts come from load_canonical_floor()
    (same source the build uses); the 7 universal-primary verticals are assembled
    from their naming-map auto_add_departments entry the SAME way apply_vertical_packs
    does ({name, emoji, head: "Director of <name>", description: one_liner}).

    Returns (selected_departments, floor_ids) or raises on failure.
    """
    bw = _load_module("bw_artifact", repo.scripts / "build-workforce.py")
    # Mandatory floor depts, already in the {name,emoji,head,description} shape.
    floor = dict(bw.load_canonical_floor())  # {cid: {name,emoji,head,description}}
    # Universal-primary vertical depts (the 7 not in load_canonical_floor()).
    ups = repo.floor_mod.universal_primary_vertical_departments(repo.naming_map)
    vpacks = (repo.naming_map.get("vertical_packs") or {})
    vmeta = {}
    for pack in vpacks.values():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("id"):
                vmeta.setdefault(dept["id"], dept)
    for did in ups:
        if did in floor:
            continue
        meta = vmeta.get(did, {})
        name = meta.get("name", did.replace("-", " ").title())
        floor[did] = {
            "name": name,
            "emoji": meta.get("emoji", "\U0001f4c1"),
            "head": f"Director of {name}",
            "description": meta.get("one_liner", ""),
        }
    mandatory = list((repo.naming_map.get("mandatory") or {}).keys())
    floor_ids = mandatory + list(ups)
    return bw, floor, floor_ids


def evaluate_artifact_coverage(skill_dir):
    """Run the 7 artifact-coverage dimensions. Returns a verdict dict with rc 0/6/2."""
    failures = []  # (dimension, detail)
    rows = []      # (dimension, status, detail)

    def add_row(dim, ok, detail):
        rows.append((dim, "OK" if ok else "DRIFT", detail))
        if not ok:
            failures.append((dim, detail))

    try:
        repo = Repo(skill_dir)
    except Exception as e:  # noqa: BLE001
        return {"rc": 2, "fatal": f"could not load repo: {e}", "rows": [],
                "failures": [], "summary": {}}

    # ── Synthesize the full floor + load the real build module ────────────────
    try:
        bw, floor_depts, floor_ids = _synthesize_full_floor_departments(repo)
    except Exception as e:  # noqa: BLE001
        return {"rc": 2, "fatal": f"could not synthesize floor / load build-workforce: {e}",
                "rows": [], "failures": [], "summary": {}}

    floor_set = set(floor_ids)

    # ── DIMENSION: ORG-CHART ──────────────────────────────────────────────────
    # Run the REAL generate_org_chart against the full floor; assert every floor
    # dept's display NAME appears in the rendered org chart. specialists_by_dept
    # is keyed by the floor roster so role-level coverage is exercised too.
    try:
        specialists_by_dept = {}
        for did in floor_ids:
            fn, _ = repo.roster_filename_for(did)
            roles = []
            if fn and (repo.rosters_dir / fn).is_file():
                try:
                    roles = repo.crw.parse_roster(repo.rosters_dir / fn)
                except Exception:
                    roles = []
            specialists_by_dept[did] = [{"name": r["name"], "type": "permanent"} for r in roles]
        org_md = bw.generate_org_chart(floor_depts, specialists_by_dept)
        missing_oc = [did for did in floor_ids
                      if floor_depts[did]["name"] not in org_md]
        # Role-level: a dept whose roster has roles but none rendered is a gap.
        role_gap_oc = []
        for did in floor_ids:
            specs = specialists_by_dept.get(did, [])
            if specs:
                rendered = sum(1 for s in specs if s["name"] in org_md)
                if rendered < len(specs):
                    role_gap_oc.append(f"{did}({rendered}/{len(specs)})")
        if missing_oc:
            add_row("ORG-CHART", False,
                    f"floor dept(s) absent from generate_org_chart output: {missing_oc}")
        elif role_gap_oc:
            add_row("ORG-CHART", False,
                    f"roster role(s) absent from org chart for: {role_gap_oc}")
        else:
            add_row("ORG-CHART", True,
                    f"all {len(floor_ids)} floor depts + their roster roles rendered")
    except Exception as e:  # noqa: BLE001
        add_row("ORG-CHART", False, f"generate_org_chart raised: {e}")

    # ── DIMENSION: ROUTING ────────────────────────────────────────────────────
    # write_universal_routing_map writes to COMPANY_DIR. Point COMPANY_DIR at a
    # temp dir, run the REAL generator, read 00-ROUTING.md, assert every floor
    # dept has a `departments/<dept>/` routing row. (CEO/orchestrator are
    # intentionally skipped by the generator and are not floor depts.)
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            old_company = getattr(bw, "COMPANY_DIR", None)
            bw.COMPANY_DIR = td
            try:
                routing_path = bw.write_universal_routing_map(floor_depts)
            finally:
                bw.COMPANY_DIR = old_company
            routing_md = Path(routing_path).read_text(encoding="utf-8") if routing_path else ""
        missing_rt = [did for did in floor_ids
                      if did not in ("ceo", "master-orchestrator", "dept-ceo")
                      and f"departments/{did}/" not in routing_md]
        if missing_rt:
            add_row("ROUTING", False,
                    f"floor dept(s) with NO row in 00-ROUTING.md: {missing_rt}")
        else:
            add_row("ROUTING", True,
                    f"all {len(floor_ids)} floor depts routed in 00-ROUTING.md")
    except Exception as e:  # noqa: BLE001
        add_row("ROUTING", False, f"write_universal_routing_map raised: {e}")

    # ── DIMENSION: COMMAND-CENTER ─────────────────────────────────────────────
    # generate_departments_json drives the Command Center Kanban columns + the
    # SQLite workspaces table + the Telegram topic bindings (one per dept slug).
    # Assert every floor dept appears as a `slug` in the generated array.
    try:
        cc_entries = bw.generate_departments_json(floor_depts)
        cc_slugs = {e.get("slug") for e in cc_entries}
        # The generator canonicalizes slugs; compare against canonical floor slugs.
        canon = getattr(bw, "_canonical_dept_slug", lambda s: s)
        missing_cc = []
        for did in floor_ids:
            if did in ("ceo", "master-orchestrator", "dept-ceo"):
                continue
            want = canon(did) or did
            if want not in cc_slugs and did not in cc_slugs:
                missing_cc.append(did)
        if missing_cc:
            add_row("COMMAND-CENTER", False,
                    f"floor dept(s) absent from departments.json (no CC column/topic): {missing_cc}")
        else:
            add_row("COMMAND-CENTER", True,
                    f"all {len(floor_ids)} floor depts present in departments.json (+CEO column)")
    except Exception as e:  # noqa: BLE001
        add_row("COMMAND-CENTER", False, f"generate_departments_json raised: {e}")

    # ── DIMENSION: DREAMING ───────────────────────────────────────────────────
    # Dreaming (nightly memory consolidation) operates on the per-dept memory/
    # substrate that EVERY department workspace carries. Two invariants make
    # "dreaming covers all departments (none excluded)" TRUE and keep it true:
    #
    #   (1) Every floor dept gets a workspace (with a memory/ folder) — the dept
    #       workspace creator (create_department_workspace) MUST be invoked inside
    #       the build's `for ... in selected_departments` loop, and must create
    #       the per-dept memory/ folder. A hardcoded subset (a loop over a fixed
    #       list instead of selected_departments) would silently exclude a floor
    #       dept from the dreaming substrate.
    #   (2) Dreaming is configured WORKSPACE-WIDE (the install.sh configure_dreaming
    #       step writes plugins.entries.memory-core.config.dreaming), NOT per-dept,
    #       and there is NO per-dept dreaming allow/exclude list anywhere that
    #       could drop a floor dept. (A per-dept dreaming list is the drift this
    #       guards against — none exists today, and this fails if one appears that
    #       does not enumerate the full floor.)
    try:
        bw_src = (repo.scripts / "build-workforce.py").read_text(encoding="utf-8")
        dream_problems = []

        # (1) create_department_workspace must exist, be called inside the
        #     selected_departments loop, and create the per-dept memory/ substrate.
        if "def create_department_workspace(" not in bw_src:
            dream_problems.append("create_department_workspace() not defined")
        else:
            # Find the call (not the def) and confirm a `selected_departments`
            # iteration precedes it within the same enclosing build function.
            call_lines = [i for i, ln in enumerate(bw_src.splitlines())
                          if "create_department_workspace(" in ln
                          and not ln.lstrip().startswith("def ")]
            if not call_lines:
                dream_problems.append("create_department_workspace() defined but never CALLED")
            else:
                lines = bw_src.splitlines()
                wired_in_loop = False
                for ci in call_lines:
                    # Walk back up to ~60 lines for the governing for-loop header.
                    for j in range(ci, max(0, ci - 60), -1):
                        if re.match(r"\s*for\s+\w+(?:\s*,\s*\w+)?\s+in\s+selected_departments",
                                    lines[j]):
                            wired_in_loop = True
                            break
                    if wired_in_loop:
                        break
                if not wired_in_loop:
                    dream_problems.append("create_department_workspace() is not driven by the "
                                          "selected_departments loop (a hardcoded subset could "
                                          "exclude a floor dept from the dreaming substrate)")
            # Per-dept memory/ substrate the dreaming engine consolidates.
            cdw_m = re.search(r"\ndef create_department_workspace\(", bw_src)
            cdw_body = bw_src[cdw_m.end():] if cdw_m else ""
            nxt = re.search(r"\ndef \w+\(", cdw_body)
            cdw_body = cdw_body[:nxt.start()] if nxt else cdw_body
            if 'os.makedirs(os.path.join(dept_dir, "memory")' not in cdw_body \
                    and "'memory'" not in cdw_body and '"memory"' not in cdw_body:
                dream_problems.append("create_department_workspace() does not create the per-dept "
                                      "memory/ substrate dreaming consolidates")

        # (2) Global dreaming config step + no per-dept dreaming exclusion list.
        install_sh = repo.repo_root / "install.sh"
        install_txt = install_sh.read_text(encoding="utf-8", errors="replace") if install_sh.is_file() else ""
        if "configure_dreaming" not in install_txt:
            dream_problems.append("install.sh has no configure_dreaming step")
        elif "memory-core" not in install_txt or "dreaming" not in install_txt:
            dream_problems.append("install.sh configure_dreaming does not write the "
                                  "memory-core dreaming config")
        # A per-dept dreaming allow/exclude list would be the drift. If one is
        # introduced, it MUST enumerate the full floor — fail if it omits a dept.
        for var in ("DREAMING_DEPARTMENTS", "DREAMING_DEPTS", "DREAM_DEPARTMENTS"):
            mm = re.search(re.escape(var) + r"\s*=\s*[\[{]([^\]}]*)[\]}]", bw_src)
            if mm:
                listed = set(re.findall(r"['\"]([a-z0-9\-]+)['\"]", mm.group(1)))
                omitted = [d for d in floor_ids if d not in listed]
                if omitted:
                    dream_problems.append(f"per-dept dreaming list {var} omits floor dept(s): {omitted}")

        if dream_problems:
            add_row("DREAMING", False, "; ".join(dream_problems))
        else:
            add_row("DREAMING", True,
                    f"every floor dept gets a workspace+memory/ substrate via the "
                    f"selected_departments loop; dreaming configured workspace-wide "
                    f"(no per-dept exclusion)")
    except Exception as e:  # noqa: BLE001
        add_row("DREAMING", False, f"dreaming coverage check raised: {e}")

    # ── DIMENSION: GENERATOR WIRING (org-chart/routing/CC called by the build) ─
    # A generator can be perfect but unwired. Statically assert each required
    # generator is CALLED somewhere in build-workforce.py (not just defined).
    try:
        bw_src = (repo.scripts / "build-workforce.py").read_text(encoding="utf-8")
        unwired = []
        for call in _REQUIRED_GENERATOR_CALLS:
            # Count call sites that are NOT the `def` line.
            fn_name = call[:-1]
            calls = [ln for ln in bw_src.splitlines()
                     if call in ln and not ln.lstrip().startswith(f"def {fn_name}")]
            if not calls:
                unwired.append(fn_name)
        if unwired:
            add_row("GENERATOR-WIRING", False,
                    f"generator(s) defined but never CALLED by build-workforce.py: {unwired}")
        else:
            add_row("GENERATOR-WIRING", True,
                    "org-chart / routing / departments.json generators are wired")
    except Exception as e:  # noqa: BLE001
        add_row("GENERATOR-WIRING", False, f"wiring check raised: {e}")

    # ── DIMENSION: BOOTSTRAP ──────────────────────────────────────────────────
    # The 6 shipped bootstrap templates must EXIST at repo root; MEMORY.md must
    # NOT be a committed template (seeded fresh per agent) but MUST be referenced
    # as a core file; the canonical 7-file enumeration (Start Here.md) must name
    # all seven.
    try:
        root = repo.repo_root
        missing_tmpl = [f for f in _BOOTSTRAP_TEMPLATE_FILES if not (root / f).is_file()]
        boot_problems = []
        if missing_tmpl:
            boot_problems.append(f"missing shipped template(s): {missing_tmpl}")
        # MEMORY.md must be runtime-seeded, not a committed template.
        if (root / "MEMORY.md").is_file():
            boot_problems.append("MEMORY.md is committed at repo root — it must be "
                                 "seeded fresh+empty per agent (a committed template "
                                 "leaks one client's facts to the next)")
        # Canonical 7-file enumeration in Start Here.md names all seven.
        start_here = root / "Start Here.md"
        if start_here.is_file():
            sh = start_here.read_text(encoding="utf-8", errors="replace")
            unref = [f for f in _BOOTSTRAP_ALL if f not in sh]
            if unref:
                boot_problems.append(f"Start Here.md core enumeration omits: {unref}")
        else:
            boot_problems.append("Start Here.md not found (canonical core enumeration)")
        if boot_problems:
            add_row("BOOTSTRAP", False, "; ".join(boot_problems))
        else:
            add_row("BOOTSTRAP", True,
                    "6 shipped templates exist, MEMORY runtime-seeded, all 7 enumerated")
    except Exception as e:  # noqa: BLE001
        add_row("BOOTSTRAP", False, f"bootstrap check raised: {e}")

    # ── DIMENSION: SKILLS-COUNT ───────────────────────────────────────────────
    # install.sh active-skill prose count == README count == actual skill-dir tree.
    try:
        root = repo.repo_root
        # Actual tree: top-level ^[0-9]+-<name> dirs, minus *-ARCHIVED.
        all_dirs = sorted(d.name for d in root.iterdir()
                          if d.is_dir() and re.match(r"^\d+-", d.name))
        active_dirs = [d for d in all_dirs if not d.endswith("-ARCHIVED")]
        archived_dirs = [d for d in all_dirs if d.endswith("-ARCHIVED")]
        actual_active = len(active_dirs)
        actual_total = len(all_dirs)
        actual_archived = len(archived_dirs)

        skill_problems = []
        # README prose: "N numbered skill folders" + "M active ... K archived".
        readme = root / "README.md"
        readme_txt = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
        for m in re.finditer(r"\*\*(\d+) numbered skill folders", readme_txt):
            n = int(m.group(1))
            if n != actual_total:
                skill_problems.append(f"README states {n} folders, tree has {actual_total}")
        for m in re.finditer(r"(\d+) active (?:plus|\+) (\d+) archived", readme_txt):
            act, arch = int(m.group(1)), int(m.group(2))
            if act != actual_active:
                skill_problems.append(f"README states {act} active, tree has {actual_active}")
            if arch != actual_archived:
                skill_problems.append(f"README states {arch} archived, tree has {actual_archived}")
        # README inventory table rows: each ^| NN-<slug> | — must cover every
        # ACTIVE skill dir (ARCHIVED dirs are intentionally not listed as rows).
        inv_rows = set(re.findall(r"^\|\s*(\d+-[a-z0-9-]+)\s*\|", readme_txt, re.MULTILINE))
        inv_missing = [d for d in active_dirs if d not in inv_rows]
        if inv_missing:
            skill_problems.append(f"README inventory table missing active-skill row(s): {inv_missing}")
        # install.sh prose: "(N active + K archived)" and "The N active skills".
        install_sh = root / "install.sh"
        install_txt = install_sh.read_text(encoding="utf-8", errors="replace") if install_sh.is_file() else ""
        for m in re.finditer(r"\((\d+) active \+ (\d+) archived\)", install_txt):
            act, arch = int(m.group(1)), int(m.group(2))
            if act != actual_active:
                skill_problems.append(f"install.sh prose states {act} active, tree has {actual_active}")
            if arch != actual_archived:
                skill_problems.append(f"install.sh prose states {arch} archived, tree has {actual_archived}")
        for m in re.finditer(r"The (\d+) active skills", install_txt):
            n = int(m.group(1))
            if n != actual_active:
                skill_problems.append(f"install.sh 'The N active skills' states {n}, tree has {actual_active}")
        if skill_problems:
            add_row("SKILLS-COUNT", False, "; ".join(dict.fromkeys(skill_problems)))
        else:
            add_row("SKILLS-COUNT", True,
                    f"install.sh == README == tree ({actual_active} active, {actual_archived} archived, {actual_total} total)")
    except Exception as e:  # noqa: BLE001
        add_row("SKILLS-COUNT", False, f"skills-count check raised: {e}")

    # ── DIMENSION: VERSION-MARKERS ────────────────────────────────────────────
    # Every place a repo-wide version lives must agree with /version. This is the
    # 9-marker bump-version.sh set + cc-compat.json onboardingVersion, promoted
    # from CI-only into the gate so a build refuses to run against a drifted repo.
    try:
        root = repo.repo_root

        def _norm_v(v):
            return (v or "").strip().lstrip("v")

        ver_path = root / "version"
        v_root = _norm_v(ver_path.read_text(encoding="utf-8").splitlines()[0]) if ver_path.is_file() else None
        markers = {}  # label -> value
        markers["/version"] = v_root

        def _grep1(path, pat, group=1):
            if not path.is_file():
                return None
            mm = re.search(pat, path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            return _norm_v(mm.group(group)) if mm else None

        markers["install.sh ONBOARDING_VERSION"] = _grep1(
            root / "install.sh", r'^ONBOARDING_VERSION="?(v?[0-9.]+)"?')
        markers["update-skills.sh ONBOARDING_VERSION"] = _grep1(
            root / "update-skills.sh", r'^ONBOARDING_VERSION="?(v?[0-9.]+)"?')
        skv = root / "23-ai-workforce-blueprint" / "skill-version.txt"
        markers["skill-version.txt"] = _norm_v(skv.read_text(encoding="utf-8").splitlines()[0]) if skv.is_file() else None
        markers["_index.json version"] = _norm_v(str(repo.index.get("version")))
        _SEMVER = r"([0-9]+\.[0-9]+\.[0-9]+)"  # anchored: no trailing punctuation
        markers["_qc-summary.md"] = _grep1(
            root / "23-ai-workforce-blueprint" / "templates" / "role-library" / "_qc-summary.md",
            r"Role Library v" + _SEMVER)
        markers["README this-repo-at"] = _grep1(root / "README.md", r"this repo at v" + _SEMVER)
        markers["README Current-Version"] = _grep1(root / "README.md", r"Current Version: v" + _SEMVER)
        markers["DIRECT-TO-AGENT **vX.Y.Z**"] = _grep1(
            root / "DIRECT-TO-AGENT-UPDATE-MESSAGE.md", r"\*\*v" + _SEMVER + r"\*\*")
        cc = root / "cc-compat.json"
        if cc.is_file():
            try:
                markers["cc-compat onboardingVersion"] = _norm_v(
                    json.loads(cc.read_text(encoding="utf-8")).get("onboardingVersion"))
            except Exception:
                markers["cc-compat onboardingVersion"] = "UNREADABLE"
        ver_problems = []
        if not v_root:
            ver_problems.append("/version unreadable")
        else:
            for label, val in markers.items():
                if label == "/version":
                    continue
                if val != v_root:
                    ver_problems.append(f"{label}={val or 'MISSING'} (want {v_root})")
        if ver_problems:
            add_row("VERSION-MARKERS", False,
                    f"version drift vs /version={v_root}: " + "; ".join(ver_problems))
        else:
            add_row("VERSION-MARKERS", True,
                    f"all {len(markers)} version markers agree at v{v_root}")
    except Exception as e:  # noqa: BLE001
        add_row("VERSION-MARKERS", False, f"version-marker check raised: {e}")

    # ── DIMENSION: CONTENT-HASH (v12.27.0) ────────────────────────────────────
    # The per-artifact content-manifest must be PRESENT + UP TO DATE. This makes a
    # stale content manifest IMPOSSIBLE to ship: it re-runs the SAME hash pipeline
    # (hash-content-manifest.check_manifest) over the LIVE library files under test
    # and asserts (a) EVERY roles[]/sops[]/personas[] entry HAS content_sha + content_version,
    # (b) each STORED content_sha EQUALS the freshly recomputed one (manifest not
    # stale vs files), (c) the content_manifest header is present + uses the
    # expected algo/schema, and (d) render_sha recomputes cleanly — no un-mapped
    # CANONICAL token survives the neutral render (the TOKEN_LEAK invariant). Any
    # mismatch => DRIFT => rc 6. Because content_sha is canonical-source-based, any
    # future edit to a role/SOP/dept .md changes that artifact's content_sha at the
    # next hash-content-manifest.py run; this gate forces that re-stamp before the
    # edit can ship, so detect-stale-artifacts.py can flag exactly the affected
    # clients.
    try:
        hcm = _load_module("hash_content_manifest", repo.scripts / "hash-content-manifest.py")
        # The hash module resolves the library under _SKILL_DIR (its own parent).
        # Repo() already forced ROLE_LIBRARY_PATH = skill under test, but the hash
        # module pins _SKILL_DIR at import time from its OWN location, which IS the
        # skill-under-test's scripts/ parent — so it reads the same files. Validate
        # the repo's loaded index against the live files via the shared check.
        # render is best-effort: if fill_tokens isn't importable, the token-leak
        # sub-check is skipped (content_sha assertion is unaffected).
        ok_hash, hash_problems = hcm.check_manifest(repo.index, do_render=True)
        if ok_hash:
            n_roles = len(repo.index.get("roles", []))
            n_sops = len(repo.index.get("sops", []))
            n_personas = len(repo.index.get("personas", []))
            add_row("CONTENT-HASH", True,
                    f"content-manifest present + current: {n_roles} roles + "
                    f"{n_sops} sops + {n_personas} personas carry content_sha/version; "
                    f"all match live files")
        else:
            add_row("CONTENT-HASH", False,
                    f"content-manifest drift ({len(hash_problems)}): "
                    + "; ".join(hash_problems[:4])
                    + (f" … +{len(hash_problems) - 4} more" if len(hash_problems) > 4 else ""))
    except Exception as e:  # noqa: BLE001
        add_row("CONTENT-HASH", False, f"content-hash check raised: {e}")

    rc = 0 if not failures else 6
    summary = {
        "floor_count": len(floor_ids),
        "dimensions_ok": sum(1 for r in rows if r[1] == "OK"),
        "dimensions_drift": sum(1 for r in rows if r[1] == "DRIFT"),
        "failure_count": len(failures),
    }
    return {"rc": rc, "fatal": None, "rows": rows, "failures": failures,
            "summary": summary}


def _print_artifact_table(verdict):
    s = verdict["summary"]
    print("=" * 110)
    print("ARTIFACT COVERAGE GATE — org-chart x routing x command-center x dreaming "
          "x bootstrap x skills-count x version x content-hash")
    print(f"floor = {s.get('floor_count')} departments")
    print("=" * 110)
    print(f"{'DIMENSION':<20}{'STATUS':<8}DETAIL")
    print("-" * 110)
    for dim, status, detail in verdict["rows"]:
        d = detail if len(detail) <= 86 else detail[:83] + "..."
        print(f"{dim:<20}{status:<8}{d}")
    print("-" * 110)
    print(f"dimensions: {s['dimensions_ok']} OK, {s['dimensions_drift']} DRIFT   |   "
          f"failures: {s['failure_count']}")
    if verdict.get("failures"):
        print("\nARTIFACT FAILURE DETAIL:")
        for dim, detail in verdict["failures"]:
            print(f"  [{dim}] {detail}")
    print("=" * 110)
    if verdict["rc"] == 0:
        print(f"RESULT: PASS — every downstream artifact covers all {s.get('floor_count')} "
              f"floor departments; skills + versions + bootstrap consistent (rc=0)")
    else:
        print(f"RESULT: FAIL — {s['dimensions_drift']} artifact dimension(s) with drift, "
              f"{s['failure_count']} problem(s) (rc={verdict['rc']})")


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
        description="Cross-check floor x roster x library x SOP x persona, plus "
                    "downstream artifact coverage (org-chart/routing/command-center/"
                    "dreaming/bootstrap/skills-count/version).")
    parser.add_argument("--skill-dir", default=None,
                        help="Path to the 23-ai-workforce-blueprint skill dir "
                             "(default: this script's parent skill dir).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of the table.")
    parser.add_argument("--only", choices=["consistency", "artifact"], default=None,
                        help="Run only one gate (default: BOTH). 'consistency' = the "
                             "5-dimension floor/roster/library/SOP/persona gate; "
                             "'artifact' = the 7 downstream-artifact dimensions.")
    args = parser.parse_args(argv)

    skill_dir = args.skill_dir or str(Path(__file__).resolve().parent.parent)

    run_consistency = args.only in (None, "consistency")
    run_artifact = args.only in (None, "artifact")

    v_consistency = evaluate(skill_dir) if run_consistency else None
    v_artifact = evaluate_artifact_coverage(skill_dir) if run_artifact else None

    if args.json:
        out = {}
        if v_consistency is not None:
            out["consistency"] = v_consistency
        if v_artifact is not None:
            out["artifact"] = v_artifact
        print(json.dumps(out, indent=2))
    else:
        if v_consistency is not None:
            if v_consistency.get("fatal"):
                print(f"FATAL (consistency): {v_consistency['fatal']}", file=sys.stderr)
            else:
                _print_table(v_consistency)
        if v_consistency is not None and v_artifact is not None:
            print()  # spacer between the two tables
        if v_artifact is not None:
            if v_artifact.get("fatal"):
                print(f"FATAL (artifact): {v_artifact['fatal']}", file=sys.stderr)
            else:
                _print_artifact_table(v_artifact)

    # Combined exit code (most-severe wins). Fatal (2) > consistency drift (5) >
    # artifact drift (6) > clean (0). A fatal/load error from either gate is the
    # loudest signal that the gate could not be trusted to pass.
    rcs = [v for v in (v_consistency, v_artifact) if v is not None]
    if any(v["rc"] == 2 for v in rcs):
        return 2
    if any(v["rc"] == 5 for v in rcs):
        return 5
    if any(v["rc"] == 6 for v in rcs):
        return 6
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
