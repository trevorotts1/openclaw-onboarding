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

class _SkipDimension(Exception):
    """Raised to cleanly skip an artifact dimension (row already added as a pass)."""


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
        """The floor dept ids: 22 mandatory + the universal-primary verticals
        (currently 6 per naming-map v2.6.1 = 28; read live, never a frozen count).

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

def _persona_set_triad_failures(skill_dir):
    """N38 7th assertion (FIX 5). Return a list of (scope, category, detail)
    failure tuples when the persona-SET COUNT triad disagrees:

        blueprint dirs (22-…/personas/*)
        == categories.json persona keys (22-…/persona-categories.json)
        == manifest persona_count        (shared-utils/prebuilt-index/INDEX-MANIFEST.json)
        == manifest canonical_persona_count

    Empty list ⇒ triad agrees. Any mismatch ⇒ one failure tuple (rc=5 in
    evaluate()). Pure static file compare — never embeds, never downloads.
    Missing files are reported as a failure (a persona system that cannot prove
    its own count is drifted by definition), but a TOTAL absence of the persona
    subsystem (no Skill-22 dir at all) is tolerated as additive.
    """
    repo_root = Path(skill_dir).resolve().parent
    sk22 = repo_root / "22-book-to-persona-coaching-leadership-system"
    personas_dir = sk22 / "personas"
    cats_path = sk22 / "persona-categories.json"
    manifest_path = repo_root / "shared-utils" / "prebuilt-index" / "INDEX-MANIFEST.json"

    # Additive tolerance: if the whole Skill-22 persona subsystem is absent, do
    # not fail (some trimmed repos may not ship it).
    if not sk22.is_dir():
        return []

    fails = []

    dir_count = None
    if personas_dir.is_dir():
        dir_count = sum(1 for p in personas_dir.iterdir() if p.is_dir())
    else:
        fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                      f"blueprint dir missing: {personas_dir}"))

    cats_count = None
    if cats_path.is_file():
        try:
            cats = json.loads(cats_path.read_text(encoding="utf-8"))
            cats_count = len(cats.get("personas", {}))
        except Exception as e:
            fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                          f"persona-categories.json unreadable: {e}"))
    else:
        fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                      f"persona-categories.json missing: {cats_path}"))

    man_count = man_canon = None
    man_embedded = None
    man_rebuild = False
    if manifest_path.is_file():
        try:
            man = json.loads(manifest_path.read_text(encoding="utf-8"))
            man_count = int(man.get("persona_count", -1))
            man_canon = int(man.get("canonical_persona_count", -1))
            man_rebuild = bool(man.get("asset_rebuild_required", False))
            _emb = man.get("embedded_persona_count")
            man_embedded = int(_emb) if _emb is not None else None
        except Exception as e:
            fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                          f"INDEX-MANIFEST.json unreadable: {e}"))
    else:
        fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                      f"INDEX-MANIFEST.json missing: {manifest_path}"))

    vals = {
        "blueprint_dirs": dir_count,
        "categories.json_keys": cats_count,
        "manifest.persona_count": man_count,
        "manifest.canonical_persona_count": man_canon,
    }
    present = {k: v for k, v in vals.items() if v is not None}
    core_agree = len(present) > 0 and len(set(present.values())) == 1
    if len(set(present.values())) > 1:
        fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                      "persona-SET count triad DISAGREES (a persona shipped to "
                      "the SET without an embedded asset, or the manifest was "
                      "bumped without a blueprint): " +
                      ", ".join(f"{k}={v}" for k, v in vals.items())))

    # ── FIX F1.3/F2.2 — 5th triad member: the PUBLISHED asset's embedded persona
    # count. Only meaningful once the core-4 agree (an SET count exists). CARVE-OUT
    # when asset_rebuild_required==true (a --no-asset staging bump synced counts but
    # did NOT re-embed — branch-level enforcement for main/release lives in
    # persona-set-asset-consistency-guard.yml). Field absent ⇒ additive tolerance
    # (legacy manifest). Otherwise embedded MUST equal the SET count, else the
    # served asset is STALE (counted-but-vector-less persona). Kept in lockstep with
    # persona_fleet.py:_embedded_member_failure.
    if core_agree and not man_rebuild and man_embedded is not None:
        core_n = next(iter(present.values()))
        if man_embedded != core_n:
            fails.append(("(persona-set)", "PERSONA-SET-COUNT",
                          f"persona-SET 5th member DISAGREES — "
                          f"manifest.embedded_persona_count={man_embedded} != SET "
                          f"count {core_n} while asset_rebuild_required=false: the "
                          f"PUBLISHED embeddings asset is STALE (a persona was "
                          f"counted but its vectors were not embedded/published). "
                          f"Rebuild via shared-utils/prebuilt-index/"
                          f"build-and-publish.sh and commit the refreshed manifest."))
    return fails


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

    # N38 7th assertion (FIX 5 — persona-SET propagation invariant). The five
    # dimensions above guard persona→DOMAIN mappings, NOT the persona-SET COUNT
    # triad. A persona could be added to the blueprint dir + categories.json while
    # the prebuilt-index manifest still claimed the OLD count (matchable-but-
    # vector-less), or the manifest could be bumped without a blueprint — both ship
    # broken propagation silently. Assert the triad agrees: blueprint dirs ==
    # categories.json keys == manifest persona_count == manifest
    # canonical_persona_count. Static file compare only — NO embeddings. rc=5.
    for _f in _persona_set_triad_failures(skill_dir):
        failures.append(_f)

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
#   VERSION       every version marker across the repo agrees. The marker SET is
#                 the shared SSOT scripts/version-markers.json (currently 11
#                 markers), the SAME manifest bump-version.sh rolls + drift-checks.
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


# ─── VERSION-MARKER SSOT (shared with scripts/bump-version.sh) ────────────────
# The repo-wide version markers that must ALL equal /version are enumerated ONCE,
# in scripts/version-markers.json. bump-version.sh rolls + drift-checks that exact
# set; this gate's VERSION-MARKERS dimension reads the SAME manifest so the two can
# never disagree on which markers (or how many) track the repo version.

def _load_version_markers_manifest(repo_root):
    """Return the SSOT marker list from scripts/version-markers.json, or None if the
    manifest is absent/unreadable."""
    path = Path(repo_root) / "scripts" / "version-markers.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("markers")
    except Exception:  # noqa: BLE001
        return None


# INLINE FALLBACK marker set — the dimension's PRIOR (pre-SSOT) inline behavior,
# used ONLY when scripts/version-markers.json is absent/unreadable (e.g. the
# minimal sandbox in test-artifact-versioning.sh copies the marker SOURCE files
# but NOT the repo-root scripts/ dir / the SSOT manifest). Kept byte-for-byte in
# sync with version-markers.json so the missing-manifest case evaluates the SAME
# markers the SSOT would, exactly as this dimension did before the SSOT change —
# rather than hard-failing (which no other repo-root-dependent dimension does for
# a missing input). The real repo / CI always ships the manifest, so the SSOT path
# below is authoritative there and real-drift detection is unchanged.
_VERSION_MARKERS_FALLBACK = [
    {"id": "/version", "file": "version", "type": "plainfile"},
    {"id": "install.sh ONBOARDING_VERSION", "file": "install.sh", "type": "regex",
     "pattern": "^ONBOARDING_VERSION=\"?(v?[0-9.]+)\"?"},
    {"id": "update-skills.sh ONBOARDING_VERSION", "file": "update-skills.sh", "type": "regex",
     "pattern": "^ONBOARDING_VERSION=\"?(v?[0-9.]+)\"?"},
    {"id": "23-ai-workforce-blueprint/skill-version.txt",
     "file": "23-ai-workforce-blueprint/skill-version.txt", "type": "plainfile"},
    {"id": "_index.json version",
     "file": "23-ai-workforce-blueprint/templates/role-library/_index.json",
     "type": "json", "key": "version"},
    {"id": "_qc-summary.md",
     "file": "23-ai-workforce-blueprint/templates/role-library/_qc-summary.md",
     "type": "regex", "pattern": "Role Library v([0-9]+\\.[0-9]+\\.[0-9]+)"},
    {"id": "README this-repo-at", "file": "README.md", "type": "regex",
     "pattern": "this repo at v([0-9]+\\.[0-9]+\\.[0-9]+)"},
    {"id": "README Current-Version", "file": "README.md", "type": "regex",
     "pattern": "Current Version: v([0-9]+\\.[0-9]+\\.[0-9]+)"},
    {"id": "DIRECT-TO-AGENT **vX.Y.Z**", "file": "DIRECT-TO-AGENT-UPDATE-MESSAGE.md",
     "type": "regex", "pattern": "\\*\\*v([0-9]+\\.[0-9]+\\.[0-9]+)\\*\\*"},
    {"id": "cc-compat onboardingVersion", "file": "cc-compat.json", "type": "json",
     "key": "onboardingVersion"},
    {"id": "23-ai-workforce-blueprint/SKILL.md [version:]",
     "file": "23-ai-workforce-blueprint/SKILL.md", "type": "yaml_frontmatter"},
]


def _extract_marker_value(repo_root, marker):
    """Extract the raw (un-normalized) version string for one SSOT marker, or None
    if the file/pattern is not found. Extraction mirrors bump-version.sh
    read_current() so both tools read each marker identically.

    Marker types:
      plainfile         first non-empty line is the version.
      regex             re.search(pattern, MULTILINE); group(1) is the version.
      json              JSON object; value at key.
      yaml_frontmatter  first `version:` line inside the leading `---`…`---` block.
    """
    path = Path(repo_root) / marker["file"]
    if not path.is_file():
        return None
    mtype = marker.get("type")
    if mtype == "plainfile":
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[0].strip() if lines else None
    if mtype == "regex":
        mm = re.search(marker["pattern"],
                       path.read_text(encoding="utf-8", errors="replace"),
                       re.MULTILINE)
        return mm.group(1) if mm else None
    if mtype == "json":
        try:
            val = json.loads(path.read_text(encoding="utf-8")).get(marker["key"])
        except Exception:  # noqa: BLE001
            return "UNREADABLE"
        return str(val) if val is not None else None
    if mtype == "yaml_frontmatter":
        txt = path.read_text(encoding="utf-8", errors="replace")
        fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", txt, re.DOTALL)
        block = fm.group(1) if fm else ""
        vm = re.search(r"^version:\s*(\S+)", block, re.MULTILINE)
        return vm.group(1) if vm else None
    return None


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
    # Every place a repo-wide version lives must agree with /version. The marker
    # SET is defined ONCE, in scripts/version-markers.json — the SINGLE SOURCE OF
    # TRUTH shared with scripts/bump-version.sh, which rolls + drift-checks the
    # SAME set. Both consumers read that manifest, so this gate and the bump tool
    # can never disagree on which markers (or how many) must equal /version. The
    # per-marker extraction here mirrors bump-version.sh read_current().
    try:
        root = repo.repo_root

        def _norm_v(v):
            return (v or "").strip().lstrip("v")

        manifest_markers = _load_version_markers_manifest(root)
        marker_source = "scripts/version-markers.json (SSOT)"
        if manifest_markers is None:
            # GRACEFUL DEGRADATION (not a hard fail): the SSOT manifest is absent —
            # e.g. the minimal sandbox in test-artifact-versioning.sh copies the
            # marker SOURCE files but not the repo-root scripts/ dir. Fall back to the
            # dimension's PRIOR inline marker set and evaluate it exactly as before the
            # SSOT change, mirroring how DREAMING/BOOTSTRAP/SKILLS-COUNT tolerate a
            # missing input instead of reporting DRIFT. The real repo/CI always ships
            # the manifest, so the SSOT set + real-drift detection are unchanged there.
            manifest_markers = _VERSION_MARKERS_FALLBACK
            marker_source = "inline fallback (SSOT manifest absent)"
        markers = {}  # label -> normalized value
        v_root = None
        for m in manifest_markers:
            raw = _extract_marker_value(root, m)
            val = raw if raw in (None, "UNREADABLE") else _norm_v(raw)
            markers[m["id"]] = val
            if m.get("file") == "version":
                v_root = val
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
                    f"version drift vs /version={v_root} [{marker_source}]: "
                    + "; ".join(ver_problems))
        else:
            add_row("VERSION-MARKERS", True,
                    f"all {len(markers)} version markers agree at v{v_root} [{marker_source}]")
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

    # ── DIMENSION: MAP-CONSISTENCY (Departments-That-Use-Skills, Layer D) ──────
    # The skill↔dept↔role↔intent binding (skill-department-map.json) is the ONE
    # source of truth that Layer A (CC ContextPack), Layer B (role how-to.md
    # "Skills You Operate" blocks) and Layer C (the SKILL_INTENT_ROUTING_REFLEX_V1
    # front-door reflex) all feed off. This dimension proves the three stay in
    # lockstep with the map (mirrors N38's six-source discipline for skills):
    #   (a) STRUCTURE — every client-facing skill resolves to a live dept + owning
    #       role (exactly one primary), map<->disk skill-folder coverage, infra
    #       ownership, execution_sops resolve  (check-skill-department-map.run_checks).
    #   (b) LAYER B — every owning role's canonical template carries a CURRENT
    #       "Skills You Operate" block matching the map (stamp-skills-you-operate.check_all);
    #       a stale/missing block => drift (forces a re-stamp before ship).
    #   (c) LAYER C — the SKILL_INTENT_ROUTING_REFLEX_V1 catalog in
    #       scripts/apply-fleet-standards.sh lists a department for EVERY department
    #       that owns a client-facing skill (the reflex is generated-from-the-map;
    #       a dropped department would leave an intent unrouted at the front door).
    # Any drift => rc 6 (same class as the other artifact dimensions).
    try:
        # MAP-CONSISTENCY is only meaningful against a FULL checkout: it needs the
        # map, the repo-root universal-sops/ tree (execution_sops resolve there), and
        # the numbered skill folders on disk (map<->disk coverage). The minimal
        # skill-dir-only sandboxes (test-artifact-versioning.sh, test-repo-consistency.sh)
        # copy neither — skip cleanly there rather than flag phantom drift.
        _map_file = repo.skill_dir / "skill-department-map.json"
        _usops_dir = repo.repo_root / "universal-sops"
        if not (_map_file.is_file() and _usops_dir.is_dir()):
            add_row("MAP-CONSISTENCY", True,
                    "skipped — minimal sandbox (no repo-root universal-sops / map)")
            raise _SkipDimension()
        cksd = _load_module("check_skill_department_map",
                            repo.scripts / "check-skill-department-map.py")
        stamp = _load_module("stamp_skills_you_operate",
                             repo.scripts / "stamp-skills-you-operate.py")
        deptg = _load_module("stamp_dept_skill_guides",
                             repo.scripts / "stamp-dept-skill-guides.py")
        craft = _load_module("stamp_craft_intent_triggers",
                             repo.scripts / "stamp-craft-intent-triggers.py")
        map_path = str(_map_file)
        index_path = str(repo.index_path)
        library_dir = str(repo.skill_dir / "templates" / "role-library")
        usops_dir = str(repo.repo_root / "universal-sops")

        map_problems = []
        struct_errors, _struct_warns, struct_stats = cksd.run_checks(
            map_path=map_path, index_path=index_path,
            usops=str(repo.repo_root / "universal-sops"))
        map_problems += [f"[structure] {e}" for e in struct_errors]

        layerb_drift, n_owners = stamp.check_all(
            map_path=map_path, index_path=index_path, skill_dir=str(repo.skill_dir))
        map_problems += [f"[layer-b] {d}" for d in layerb_drift]

        # (d) DEPT-GUIDES — every owning department's owner-facing
        # how-to-use-this-department.md carries a CURRENT DEPT_SKILLS block matching
        # the map (owner guide + front-door reflex speak the same plain language).
        deptg_drift, n_depts = deptg.check_all(map_path=map_path, library_dir=library_dir)
        map_problems += [f"[dept-guides] {d}" for d in deptg_drift]

        # (e) CRAFT-READMES — every map-referenced craft cluster README carries a
        # CURRENT Intent-triggers header (self-describing to specialist + generator).
        craft_drift, n_clusters = craft.check_all(map_path=map_path, usops_dir=usops_dir)
        map_problems += [f"[craft-readmes] {d}" for d in craft_drift]

        # (c) Layer-C reflex coverage: departments owning a client-facing skill
        # must all appear in the reflex catalog. Read the reflex block from
        # apply-fleet-standards.sh (repo-root scripts/) and extract the department
        # slugs it routes to.
        owning_depts = set()
        _map = json.loads(open(map_path, encoding="utf-8").read())
        for s in _map["skills"]:
            if s.get("client_facing"):
                for r in s.get("roles", []):
                    owning_depts.add(r["dept"])
        afs = repo.repo_root / "scripts" / "apply-fleet-standards.sh"
        # Sandbox skill-dir copies (test-repo-consistency.sh) have no repo-root
        # scripts/ tree — Layer-C coverage is only meaningful against a full
        # checkout, so skip it silently there rather than flag a phantom drift.
        if not (repo.repo_root / "scripts").is_dir():
            pass
        elif afs.is_file():
            afs_txt = afs.read_text(encoding="utf-8", errors="replace")
            # The marker string appears several times in the script (a shell var, the
            # strip regexes, the heredoc). Take EVERY HTML-comment-delimited block and
            # keep the RICHEST one (the rendered table heredoc — the others are the
            # single-line strip-regex sources with no dept rows).
            blocks = re.findall(
                r"<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->(.*?)<!-- END SKILL_INTENT_ROUTING_REFLEX_V1 -->",
                afs_txt, re.DOTALL)
            if not blocks:
                map_problems.append("[layer-c] SKILL_INTENT_ROUTING_REFLEX_V1 block "
                                    "not found in scripts/apply-fleet-standards.sh")
            else:
                # dept slugs are emitted as backticked `<slug>` tokens in the
                # department column — pick the block with the most of them.
                best = max(blocks, key=lambda b: len(re.findall(r"`[a-z][a-z0-9-]+`", b)))
                routed = set(re.findall(r"`([a-z][a-z0-9-]+)`", best))
                missing = sorted(d for d in owning_depts if d not in routed)
                if missing:
                    map_problems.append(
                        "[layer-c] reflex catalog omits department(s) that own a "
                        f"client-facing skill: {', '.join(missing)}")
        else:
            map_problems.append("[layer-c] scripts/apply-fleet-standards.sh not found")

        if map_problems:
            add_row("MAP-CONSISTENCY", False,
                    f"skill-department-map drift ({len(map_problems)}): "
                    + "; ".join(map_problems[:4])
                    + (f" … +{len(map_problems) - 4} more" if len(map_problems) > 4 else ""))
        else:
            add_row("MAP-CONSISTENCY", True,
                    f"map<->role<->guide<->craft<->reflex in lockstep: {struct_stats['client_facing']} "
                    f"client-facing skills resolve to live dept+role; {n_owners} owning "
                    f"roles carry a current Skills-You-Operate block; {n_depts} dept guides "
                    f"carry a current DEPT_SKILLS block; {n_clusters} craft READMEs carry a "
                    f"current Intent-triggers block; reflex routes all "
                    f"{len(owning_depts)} owning departments")
    except _SkipDimension:
        pass  # minimal sandbox — MAP-CONSISTENCY row already added as a clean skip
    except Exception as e:  # noqa: BLE001
        add_row("MAP-CONSISTENCY", False, f"map-consistency check raised: {e}")

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


# Issue #7: LATER = BUILD-NOW. The interview doc must NEVER promise a deferral
# ("ask me again in 90 days") or reference a 90-day-reassessment artifact — those
# imply a defer path that does not (and must not) exist. This guard fails if the
# deferral phrasing reappears in the interviewer-executed docs.
_FORBIDDEN_DEFERRAL_LITERALS = [
    "ask me again in 90 days",
    "90-day-reassessment",
    "90-day reassessment",
    "90 day reassessment",
    "reassessment.md",
]

# Issue #10: STALE CANONICAL-FLOOR SIZE. The interviewer executes INSTRUCTIONS.md
# verbatim, so a frozen floor number there makes the LLM pitch the WRONG department
# set to a live client. The floor is computed at runtime by
# scripts/list-canonical-departments.py (22 mandatory + the universal-primary
# verticals; naming-map v2.6.1 = 22 + 6 = 28 after Listings Management was demoted
# to an industry-gated real-estate vertical). The doc must DEFER to that script and
# never hardcode the "7 universal-primary" / "= 29" framing. This guard fails if the
# retired count reappears. Literals are matched case-insensitively as substrings, so
# they must be phrasings that only ever occur in the stale framing.
_FORBIDDEN_STALE_FLOOR_LITERALS = [
    "7 universal-primary",
    "7 universal primary",
    "22 mandatory + 7",
    "currently 29",
    "primary = 29",
]

# Issue #10 (contextual): "Listings Management" is a LEGITIMATE industry-gated
# real-estate-pack vertical, so it must NOT be forbidden outright — it appears
# correctly in the Industry Vertical Packs section. It is stale ONLY when pitched as
# a UNIVERSAL-PRIMARY department (the v2.6.1-retired bug where every client, not just
# real-estate ones, was walked through it). Each rule is
# (literal, required_co_literal); BOTH must appear on the SAME line to fire, so the
# legit vertical-pack line (no "universal-primary" on it) never trips.
_FORBIDDEN_STALE_FLOOR_CONTEXTUAL = [
    ("listings management", "universal-primary"),
    ("listings management", "universal primary"),
]


def evaluate_forbidden_literals(skill_dir):
    """Scan the interviewer-executed markdown for forbidden phrasing:
      - LATER-deferral promises (Issue #7): LATER = build-now, no 90-day defer.
      - stale canonical-floor size (Issue #10): the retired "7 universal-primary" /
        "= 29" framing, and Listings-Management-pitched-as-universal-primary.
    Returns {"rc": 0|7, "violations": [(file, line_no, literal, text)]}."""
    root = Path(skill_dir)
    violations = []

    def _rel(path):
        return str(path.relative_to(root.parent)
                   if root.parent in path.parents else path)

    # The interviewer executes INSTRUCTIONS.md verbatim; scan it plus any sibling
    # interview/phase docs so a copy-paste of a forbidden promise is also caught.
    candidates = [root / "INSTRUCTIONS.md"]
    candidates += sorted(root.glob("*INTERVIEW*.md")) + sorted(root.glob("*interview*.md"))
    seen = set()
    for path in candidates:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            low = line.lower()
            for lit in _FORBIDDEN_DEFERRAL_LITERALS:
                if lit in low:
                    violations.append((_rel(path), i, lit, line.strip()[:120]))
            for lit in _FORBIDDEN_STALE_FLOOR_LITERALS:
                if lit.lower() in low:
                    violations.append((_rel(path), i, lit, line.strip()[:120]))
            for lit, co in _FORBIDDEN_STALE_FLOOR_CONTEXTUAL:
                if lit in low and co in low:
                    violations.append((_rel(path), i, f"{lit} (as {co})",
                                       line.strip()[:120]))
    return {"rc": 7 if violations else 0, "violations": violations}


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
    # Forbidden-literal guard runs with the consistency gate (Issue #7).
    v_forbidden = evaluate_forbidden_literals(skill_dir) if run_consistency else None

    if args.json:
        out = {}
        if v_consistency is not None:
            out["consistency"] = v_consistency
        if v_artifact is not None:
            out["artifact"] = v_artifact
        if v_forbidden is not None:
            out["forbiddenLiterals"] = v_forbidden
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

        if v_forbidden is not None and v_forbidden["violations"]:
            print("\nFORBIDDEN-LITERAL DRIFT (Issue #7 LATER = build-now, no deferral; "
                  "Issue #10 stale canonical-floor size / Listings-as-universal-primary):",
                  file=sys.stderr)
            for f, ln, lit, text in v_forbidden["violations"]:
                print(f"  {f}:{ln}: forbidden '{lit}' -> {text}", file=sys.stderr)

    # Combined exit code (most-severe wins). Fatal (2) > consistency drift (5) >
    # artifact drift (6) > forbidden-literal drift (7) > clean (0). A fatal/load
    # error from either gate is the loudest signal that the gate could not be trusted.
    rcs = [v for v in (v_consistency, v_artifact) if v is not None]
    if any(v["rc"] == 2 for v in rcs):
        return 2
    if any(v["rc"] == 5 for v in rcs):
        return 5
    if any(v["rc"] == 6 for v in rcs):
        return 6
    if v_forbidden is not None and v_forbidden["rc"] == 7:
        return 7
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
