#!/usr/bin/env python3
"""
register-library-additions.py — system-wide AUTO-REGISTER for the role/SOP/persona library.

THE PROBLEM THIS CLOSES (system-wide, every department — not presentation-only)
──────────────────────────────────────────────────────────────────────────────
The role library has ONE machine source of truth: templates/role-library/_index.json.
EVERYTHING downstream reads the index, never the raw files:
  - create_role_workspaces.library_lookup / _build_library_index resolve a role
    ONLY through _index.json.roles[].
  - hash-content-manifest.py stamps content_sha onto the entries that ALREADY
    exist in _index.json — it does NOT discover new files.
  - the repo-consistency + content-hash gates validate the entries that exist;
    they did NOT catch an on-disk role/SOP/persona file that was never registered.

So when a new artifact is ADDED to the library (a role .md, a dept SOP, a persona,
or a whole new dept folder) and _index.json is not updated in lockstep, the
artifact is INVISIBLE to the build AND silently passes CI — a "half-add". The
mirror failure is a stale entry whose file was renamed/removed (e.g. a flat
`<dept>/<slug>.md` left beside the canonical `<dept>/<slug>/how-to.md`, or a
triple-hyphen orphan draft).

This script is the idempotent disk→index reconciler that makes an add WHOLE in
one step, for ANY department:
  1. discovers every canonical role file on disk (flat `<dept>/<slug>.md` OR
     folder `<dept>/<slug>/how-to.md`), skipping infra/draft dirs + non-role docs,
  2. ADDS a roles[] entry + the dept membership for any role missing from the
     index (preserving existing entries' rich metadata — never clobbers),
  3. recomputes total_roles / total_departments / per-dept count,
  4. chains tag_role_classes.py (capability_class/vision_flag) + the SOP/persona
     discovery + content-hash restamp so the WHOLE manifest is current,
  5. reports (and with --prune-duplicate-residue, removes) duplicate-residue flat
     files and unregistered triple-hyphen orphans the new check finds.

It is the LIBRARY-side companion to add-role.sh (single live-box role) and
32-command-center-setup/scripts/sync-extensions.sh --converge (live-workspace
propagation). add-role.sh / sync-extensions call this so a new library role is
in roles[] BEFORE it is propagated into a client workspace.

IDEMPOTENCY: running twice in a row is a no-op. Existing metadata is preserved;
only genuinely-new files add entries; counts are recomputed deterministically.

USAGE
    python3 register-library-additions.py            # report only (no write)
    python3 register-library-additions.py --apply    # reconcile + restamp, write
    python3 register-library-additions.py --check     # CI: rc 7 on any drift
    python3 register-library-additions.py --apply --prune-duplicate-residue
                                                      # also delete stale flat/orphan files
    python3 register-library-additions.py --no-hash    # skip content-hash restamp (faster)

EXIT CODES
    0  in sync (or --apply succeeded)
    7  --check found unregistered files / missing files / duplicate-residue / orphans
    2  fatal (index unreadable, etc.)
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

# ─── PATHS ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent                       # 23-ai-workforce-blueprint/
_REPO_ROOT = _SKILL_DIR.parent                        # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_LIBRARY_DIR = _SKILL_DIR / "templates" / "role-library"
_PERSONA_DIR = _SKILL_DIR / "templates" / "persona-library"
_INDEX_PATH = _LIBRARY_DIR / "_index.json"

# Filenames directly under a <dept>/ that are NOT role docs (department-level
# infra/scaffold). A canonical role is EITHER a folder `<dept>/<slug>/how-to.md`
# OR a flat `<dept>/<slug>.md` whose stem is not one of these.
_INFRA_STEMS = frozenset({
    "how-to-use-this-department", "00-START-HERE", "IDENTITY", "SOUL", "TOOLS",
    "USER", "AGENTS", "MEMORY", "HEARTBEAT", "BUILDER-PROMPT", "README",
    "governing-personas", "00-INDEX",
})
# Dept-folder names under role-library/ that are NOT departments (staging / meta).
# Mirrors create_role_workspaces._ROSTER_SKIP_FOLDERS + the leading-underscore rule.
_NON_DEPT_DIRS = frozenset({
    "_stage1_drafts", "_internal", "_pending_rewrite", "_compliance_audit",
    "_drafts", "_archive", "sops", "scripts", "templates", "assets",
})

# A triple-hyphen (or longer) run in a role stem is the residue of an old draft
# naming scheme (e.g. `qc-specialist---legal`). The canonical form is a single
# hyphen. We never AUTO-register a triple-hyphen file; the check flags it.
_TRIPLE_HYPHEN_RE = re.compile(r"-{3,}")


# ─── BEST-EFFORT MODULE LOADERS ──────────────────────────────────────────────
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _try_infer_class(slug, dept, role_type):
    """capability_class/vision_flag via shared-utils model_selector; safe default."""
    try:
        if str(_SHARED_UTILS) not in sys.path:
            sys.path.insert(0, str(_SHARED_UTILS))
        from model_selector import infer_class  # type: ignore
        ci = infer_class(slug, dept, role_type)
        return ci.get("capability_class", "CONVERSATIONAL"), bool(ci.get("vision_flag", False))
    except Exception:
        return "CONVERSATIONAL", False


# ─── SOP LINKAGE (C9 fix) ─────────────────────────────────────────────────────
# Single source of truth for "how many embedded SOPs does this role's text
# carry" lives in hash-content-manifest.py (the LAST stamper in the chain,
# already reading every role's canonical text) — imported here, never
# re-implemented, so the generator/--check backstop and the restamp chain can
# never disagree on the count. Best-effort: a missing/broken sibling script
# means "skip the sop-linkage stamp/check", never "silently report 0" (that
# silent-0 was the original C9 bug).
_SOP_COUNTER_FN = None
_SOP_COUNTER_FLOOR = None
_SOP_COUNTER_LOADED = False


def _load_sop_counter():
    global _SOP_COUNTER_FN, _SOP_COUNTER_FLOOR, _SOP_COUNTER_LOADED
    if _SOP_COUNTER_LOADED:
        return _SOP_COUNTER_FN, _SOP_COUNTER_FLOOR
    _SOP_COUNTER_LOADED = True
    hcm_path = _SCRIPT_DIR / "hash-content-manifest.py"
    if hcm_path.is_file():
        try:
            hcm = _load_module("_hcm_for_sop_count", hcm_path)
            _SOP_COUNTER_FN = hcm.count_embedded_sop_headings
            _SOP_COUNTER_FLOOR = hcm.EMBEDDED_SOP_FLOOR
        except Exception:
            pass
    return _SOP_COUNTER_FN, _SOP_COUNTER_FLOOR


# ─── DISCOVERY ────────────────────────────────────────────────────────────────
def _is_dept_dir(p: Path) -> bool:
    return p.is_dir() and p.name not in _NON_DEPT_DIRS and not p.name.startswith("_")


def _canonical_role_path(dept_dir: Path, stem: str):
    """Resolve the canonical doc path for a role stem in a dept dir.
    Folder form `<slug>/how-to.md` is preferred over flat `<slug>.md`."""
    folder = dept_dir / stem / "how-to.md"
    flat = dept_dir / f"{stem}.md"
    if folder.is_file():
        return folder
    if flat.is_file():
        return flat
    return None


def discover_role_files():
    """
    Walk role-library/<dept>/ and return a dict keyed by (dept, slug) -> {
        "dept", "slug", "path" (rel-to-skill), "abspath", "layout" (folder|flat),
        "flat_path" (rel, if a flat sibling exists), "is_triple_hyphen" (bool)
    }. The canonical path prefers the folder form; a flat sibling beside a
    folder-form role is recorded as duplicate-residue.
    """
    out = {}
    if not _LIBRARY_DIR.is_dir():
        return out
    for dept_dir in sorted(_LIBRARY_DIR.iterdir()):
        if not _is_dept_dir(dept_dir):
            continue
        dept = dept_dir.name
        slugs = set()
        # folder-form roles: <dept>/<slug>/how-to.md
        for sub in sorted(dept_dir.iterdir()):
            if sub.is_dir() and sub.name not in _NON_DEPT_DIRS and not sub.name.startswith("_"):
                if (sub / "how-to.md").is_file():
                    slugs.add(sub.name)
        # flat-form roles: <dept>/<slug>.md (excluding infra docs)
        for md in sorted(dept_dir.glob("*.md")):
            if md.stem in _INFRA_STEMS:
                continue
            slugs.add(md.stem)
        for slug in sorted(slugs):
            doc = _canonical_role_path(dept_dir, slug)
            if doc is None:
                continue
            layout = "folder" if doc.name == "how-to.md" else "flat"
            flat = dept_dir / f"{slug}.md"
            flat_rel = flat.relative_to(_SKILL_DIR).as_posix() if flat.is_file() else None
            out[(dept, slug)] = {
                "dept": dept,
                "slug": slug,
                "path": doc.relative_to(_SKILL_DIR).as_posix(),
                "abspath": doc,
                "layout": layout,
                "flat_path": flat_rel,
                "is_triple_hyphen": bool(_TRIPLE_HYPHEN_RE.search(slug)),
            }
    return out


def discover_dept_sop_files():
    """role-library/<dept>/sops/*.md -> list of {slug,dept,path}."""
    out = []
    for sops_dir in sorted(_LIBRARY_DIR.glob("*/sops")):
        if not sops_dir.is_dir():
            continue
        dept = sops_dir.parent.name
        if dept.startswith("_") or dept in _NON_DEPT_DIRS:
            continue
        for md in sorted(sops_dir.glob("*.md")):
            out.append({"slug": md.stem, "dept": dept,
                        "path": md.relative_to(_SKILL_DIR).as_posix()})
    return out


def discover_persona_files():
    """persona-library/*.md (excluding _* sidecars) -> list of {slug,path}."""
    out = []
    if not _PERSONA_DIR.is_dir():
        return out
    for md in sorted(_PERSONA_DIR.glob("*.md")):
        if md.name.startswith("_"):
            continue
        out.append({"slug": md.stem, "path": md.relative_to(_SKILL_DIR).as_posix()})
    return out


# ─── ROLE METADATA FOR A NEW ENTRY ───────────────────────────────────────────
_TITLE_RE = re.compile(r"^#\s+(.*?)\s*$")
_ROLE_TYPE_RE = re.compile(r"^\*\*Role[ _]?type:\*\*\s*(.+?)\s*$", re.IGNORECASE)


def _derive_role_meta(info):
    """Read title + role_type from the role doc; infer the rest. Best-effort."""
    title, role_type = "", ""
    try:
        text = info["abspath"].read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.split("\n"):
        if not title:
            m = _TITLE_RE.match(line)
            if m:
                # strip a trailing " — how-to.md (stub)" / " — IDENTITY" decoration
                t = re.split(r"\s+[—–-]\s+(?:how-to|IDENTITY|SOUL)", m.group(1))[0].strip()
                # ignore token-only headings
                title = t
        if not role_type:
            m = _ROLE_TYPE_RE.match(line)
            if m:
                role_type = m.group(1).strip()
        if title and role_type:
            break
    if not title or "{{" in title:
        title = info["slug"].replace("-", " ").title()
    # Normalize role_type to the index's vocabulary; infer from slug as a fallback.
    rt = (role_type or "").strip().lower()
    if "{{" in rt or rt not in ("director", "manager", "coordinator", "specialist"):
        slug = info["slug"]
        if slug.startswith("director-") or slug.startswith("head-of-") or "chief-" in slug:
            rt = "director"
        elif "manager" in slug:
            rt = "manager"
        elif "coordinator" in slug:
            rt = "coordinator"
        else:
            rt = "specialist"
    word_count = len(text.split()) if text else 0
    cap_class, vision = _try_infer_class(info["slug"], info["dept"], rt)
    # C9 fix: sop_count/sop_min used to be hardcoded 0/0 regardless of the
    # role's actual embedded SOP content — compute real values from the SAME
    # text already read above. Falls back to 0/0 ONLY if the shared counter
    # can't be loaded at all (hash-content-manifest.py missing/broken); the
    # next restamp (which chains it unconditionally) fills in the real value.
    count_fn, floor = _load_sop_counter()
    return {
        "slug": info["slug"],
        "dept": info["dept"],
        "title": title,
        "role_type": rt,
        "word_count": word_count,
        "sop_count": count_fn(text) if count_fn else 0,
        "sop_min": floor if floor is not None else 0,
        "path": info["path"],
        "capability_class": cap_class,
        "vision_flag": vision,
    }


# ─── RECONCILE ────────────────────────────────────────────────────────────────
def reconcile(data, disk_roles):
    """
    Mutate `data` so roles[] + departments{}.roles[] cover every disk role.
    Preserves existing entries. Returns a report dict.
    """
    report = {
        "added_roles": [], "added_depts": [], "fixed_paths": [],
        "missing_files": [], "duplicate_residue": [], "triple_hyphen_orphans": [],
        "sop_linkage_refreshed": [],
        "recount": {},
    }
    roles = data.setdefault("roles", [])
    depts = data.setdefault("departments", {})
    by_key = {(r.get("dept"), r.get("slug")): r for r in roles}
    count_fn, sop_floor = _load_sop_counter()

    # 1. ADD any disk role missing from roles[]. Skip triple-hyphen orphans —
    #    they are never canonical; the gate flags them for removal instead.
    for key, info in sorted(disk_roles.items()):
        if info["is_triple_hyphen"] and key not in by_key:
            report["triple_hyphen_orphans"].append(info["path"])
            continue
        existing = by_key.get(key)
        if existing is None:
            meta = _derive_role_meta(info)
            roles.append(meta)
            by_key[key] = meta
            report["added_roles"].append(info["path"])
        else:
            # Heal a stale path: index points at a file that no longer exists, but
            # the canonical file is present at the discovered path.
            stored = existing.get("path", "")
            if stored != info["path"] and not (_SKILL_DIR / stored).is_file():
                existing["path"] = info["path"]
                report["fixed_paths"].append(f"{stored} -> {info['path']}")
            # C9 fix: refresh sop_count/sop_min for EXISTING entries too, not
            # just brand-new ones — this is what self-heals the historical
            # hardcoded-0 ghost values already sitting in the index for every
            # previously-registered role (_derive_role_meta only runs once,
            # at first registration, so without this an existing role's
            # sop_count would never be revisited even as its content grows
            # real embedded SOP sections).
            if count_fn is not None:
                try:
                    fresh_text = info["abspath"].read_text(encoding="utf-8")
                except OSError:
                    fresh_text = ""
                fresh_count = count_fn(fresh_text)
                if existing.get("sop_count") != fresh_count or existing.get("sop_min") != sop_floor:
                    report["sop_linkage_refreshed"].append(
                        f"{info['dept']}/{info['slug']}: sop_count "
                        f"{existing.get('sop_count')}->{fresh_count}, "
                        f"sop_min {existing.get('sop_min')}->{sop_floor}")
                existing["sop_count"] = fresh_count
                existing["sop_min"] = sop_floor

    # 2. Detect duplicate-residue: a flat `<dept>/<slug>.md` sitting beside a
    #    canonical folder-form role of the same (dept, slug).
    for key, info in sorted(disk_roles.items()):
        if info["layout"] == "folder" and info.get("flat_path"):
            report["duplicate_residue"].append(info["flat_path"])

    # 3. Detect roles[] entries whose file is gone (and no canonical disk role
    #    of the same key was discovered to heal it).
    disk_keys = set(disk_roles.keys())
    for r in roles:
        rel = r.get("path", "")
        if not (_SKILL_DIR / rel).is_file() and (r.get("dept"), r.get("slug")) not in disk_keys:
            report["missing_files"].append(rel)

    # 4. Rebuild departments{}.roles[] membership + counts from roles[].
    members = {}
    for r in roles:
        members.setdefault(r.get("dept"), set()).add(r.get("slug"))
    for dept_id, slugs in members.items():
        entry = depts.get(dept_id)
        if entry is None:
            entry = {"count": 0, "roles": []}
            depts[dept_id] = entry
            report["added_depts"].append(dept_id)
        entry["roles"] = sorted(slugs)
        entry["count"] = len(entry["roles"])

    # 5. Register SOPs + personas from disk (membership only — content_sha is
    #    stamped later by hash-content-manifest). Done HERE so registration is
    #    complete even with --no-hash; the hash step preserves these entries and
    #    only adds/refreshes content_sha/content_version.
    report["added_sops"] = []
    report["added_personas"] = []
    sops = data.setdefault("sops", [])
    sop_paths = {s.get("path") for s in sops}
    for sop in discover_dept_sop_files():
        if sop["path"] not in sop_paths:
            sops.append({"slug": sop["slug"], "dept": sop["dept"], "path": sop["path"]})
            sop_paths.add(sop["path"])
            report["added_sops"].append(sop["path"])
    # Drop dead SOP entries (file gone).
    data["sops"] = [s for s in sops if (_SKILL_DIR / s.get("path", "")).is_file()]

    personas = data.setdefault("personas", [])
    persona_paths = {p.get("path") for p in personas}
    for persona in discover_persona_files():
        if persona["path"] not in persona_paths:
            personas.append({"slug": persona["slug"], "path": persona["path"]})
            persona_paths.add(persona["path"])
            report["added_personas"].append(persona["path"])
    data["personas"] = [p for p in personas if (_SKILL_DIR / p.get("path", "")).is_file()]

    # 6. Recompute global totals.
    data["total_roles"] = sum(len(d.get("roles", [])) for d in depts.values())
    data["total_departments"] = len(depts)
    report["recount"] = {
        "total_roles": data["total_roles"],
        "total_departments": data["total_departments"],
    }
    return report


# ─── CHECK (read-only) ────────────────────────────────────────────────────────
def check(data, disk_roles):
    """Return (ok, problems) — the BACKSTOP cross-check used by --check / CI."""
    problems = []
    roles = data.get("roles", [])
    by_key = {(r.get("dept"), r.get("slug")): r for r in roles}
    idx_paths = {r.get("path") for r in roles}

    # (a) every NON-orphan disk role registered in roles[]
    for key, info in sorted(disk_roles.items()):
        if info["is_triple_hyphen"] and key not in by_key:
            problems.append(
                f"TRIPLE-HYPHEN ORPHAN: {info['path']} (un-registered draft residue; "
                f"rename to single-hyphen + register, or delete)")
            continue
        if key not in by_key:
            problems.append(
                f"UNREGISTERED: {info['path']} present on disk but ABSENT from "
                f"_index.json roles[] (run register-library-additions.py --apply)")

    # (b) every roles[] entry's file exists
    for r in roles:
        rel = r.get("path", "")
        if rel and not (_SKILL_DIR / rel).is_file():
            problems.append(f"DEAD ENTRY: roles[] {r.get('dept')}/{r.get('slug')} -> "
                            f"{rel} (file missing)")

    # (c) no duplicate-residue (flat .md beside a canonical folder-form role)
    for key, info in sorted(disk_roles.items()):
        if info["layout"] == "folder" and info.get("flat_path"):
            problems.append(
                f"DUPLICATE-RESIDUE: {info['flat_path']} is a stale flat copy beside "
                f"the canonical {info['path']} (delete the flat file)")

    # (d) counts agree
    depts = data.get("departments", {})
    total = sum(len(d.get("roles", [])) for d in depts.values())
    if data.get("total_roles") != total:
        problems.append(f"COUNT DRIFT: total_roles={data.get('total_roles')} but "
                        f"sum(dept role counts)={total}")
    if data.get("total_departments") != len(depts):
        problems.append(f"COUNT DRIFT: total_departments={data.get('total_departments')} "
                        f"but len(departments)={len(depts)}")
    for dept_id, entry in depts.items():
        rl = entry.get("roles", [])
        if entry.get("count") != len(rl):
            problems.append(f"COUNT DRIFT: dept '{dept_id}' count={entry.get('count')} "
                            f"but {len(rl)} roles listed")
        # every dept member must have a roles[] entry
        for slug in rl:
            if (dept_id, slug) not in by_key:
                problems.append(f"MEMBERSHIP DRIFT: dept '{dept_id}' lists '{slug}' "
                                f"with no roles[] entry")

    # (e) every dept-level SOP file registered in sops[]
    sop_paths = {s.get("path") for s in data.get("sops", [])}
    for sop in discover_dept_sop_files():
        if sop["path"] not in sop_paths:
            problems.append(f"UNREGISTERED SOP: {sop['path']} present on disk but "
                            f"ABSENT from _index.json sops[]")
    for s in data.get("sops", []):
        rel = s.get("path", "")
        if rel and not (_SKILL_DIR / rel).is_file():
            problems.append(f"DEAD SOP ENTRY: sops[] {rel} (file missing)")

    # (f) every persona file registered in personas[] + WIRED (declares a Domain
    #     tags header so the persona-selector can route depts/tasks to it; a persona
    #     with no domain tags is unreachable — a half-wired persona).
    persona_paths = {p.get("path") for p in data.get("personas", [])}
    for persona in discover_persona_files():
        if persona["path"] not in persona_paths:
            problems.append(f"UNREGISTERED PERSONA: {persona['path']} present on disk "
                            f"but ABSENT from _index.json personas[]")
        abspath = _SKILL_DIR / persona["path"]
        if abspath.is_file():
            try:
                ptext = abspath.read_text(encoding="utf-8")
            except OSError:
                ptext = ""
            m = re.search(r"^\*\*Domain tags:\*\*\s*(.+?)\s*$", ptext, re.MULTILINE)
            tags = [t.strip() for t in m.group(1).split(",")] if m else []
            tags = [t for t in tags if t]
            if not tags:
                problems.append(
                    f"UNWIRED PERSONA: {persona['path']} has no '**Domain tags:**' "
                    f"header — the persona-selector cannot route any dept/task to it")
    for p in data.get("personas", []):
        rel = p.get("path", "")
        if rel and not (_SKILL_DIR / rel).is_file():
            problems.append(f"DEAD PERSONA ENTRY: personas[] {rel} (file missing)")

    # (g) C9 fix: reported SOP linkage matches disk reality — every registered
    # role's stored sop_count/sop_min must equal a fresh recount of its OWN
    # canonical text (the same count hash-content-manifest.py stamps). Catches
    # the exact C9 symptom (hardcoded/stale sop_count=0 on a role that embeds
    # real "### SOP" sections) as a hard --check failure, not a silent ghost.
    count_fn, sop_floor = _load_sop_counter()
    if count_fn is not None:
        for key, info in sorted(disk_roles.items()):
            r = by_key.get(key)
            if r is None:
                continue  # already reported as UNREGISTERED above
            try:
                role_text = info["abspath"].read_text(encoding="utf-8")
            except OSError:
                role_text = ""
            fresh_count = count_fn(role_text)
            stored_count = r.get("sop_count")
            stored_min = r.get("sop_min")
            if stored_count != fresh_count:
                problems.append(
                    f"SOP LINKAGE DRIFT: {r.get('dept')}/{r.get('slug')} "
                    f"sop_count={stored_count} but disk has {fresh_count} "
                    f"embedded '### SOP' heading(s) "
                    f"(run register-library-additions.py --apply)")
            if stored_min != sop_floor:
                problems.append(
                    f"SOP LINKAGE DRIFT: {r.get('dept')}/{r.get('slug')} "
                    f"sop_min={stored_min}, expected {sop_floor} "
                    f"(run register-library-additions.py --apply)")

    return (len(problems) == 0), problems


# ─── CONTENT-HASH RESTAMP + persona/sop manifest (chains the canonical stamper) ─
def restamp_content_hash():
    """Run hash-content-manifest.stamp_manifest over the freshly-written index so
    new roles/sops/personas get content_sha/render_sha/content_version, the dept
    content_shas roll up, and the content_manifest header is current.
    Best-effort: returns (ok, message)."""
    hcm_path = _SCRIPT_DIR / "hash-content-manifest.py"
    if not hcm_path.is_file():
        return False, "hash-content-manifest.py not found"
    try:
        hcm = _load_module("_hcm_restamp", hcm_path)
        data = hcm._load_index(_INDEX_PATH)
        stats = hcm.stamp_manifest(data, do_render=True)
        hcm._save_index(_INDEX_PATH, data)
        return True, (f"roles={stats['roles_hashed']} sops={stats['sops_hashed']} "
                      f"personas={stats['personas_hashed']} depts={stats['depts_hashed']}")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def retag_classes():
    """Run tag_role_classes over the index so new roles get capability_class."""
    trc_path = _SCRIPT_DIR / "tag_role_classes.py"
    if not trc_path.is_file():
        return False, "tag_role_classes.py not found"
    try:
        trc = _load_module("_trc_retag", trc_path)
        data = trc._load_index(_INDEX_PATH)
        tagged, _ = trc.tag_all_roles(data, verbose=False)
        trc._save_index(_INDEX_PATH, data)
        return True, f"tagged={tagged}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# ─── IO ────────────────────────────────────────────────────────────────────────
def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ─── CLI ────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="AUTO-REGISTER new library roles/SOPs/personas into _index.json "
                    "and restamp the content manifest (idempotent, any department).")
    ap.add_argument("--index", default=str(_INDEX_PATH))
    ap.add_argument("--apply", action="store_true",
                    help="Write the reconciled index + restamp (default: report only).")
    ap.add_argument("--check", action="store_true",
                    help="CI mode: assert in sync, exit 7 on any drift. No writes.")
    ap.add_argument("--prune-duplicate-residue", action="store_true",
                    help="With --apply: delete stale flat-form duplicates + "
                         "un-registered triple-hyphen orphan files.")
    ap.add_argument("--no-hash", action="store_true",
                    help="Skip the content-hash restamp (faster; manifest unaffected).")
    args = ap.parse_args(argv)

    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"ERROR: _index.json not found at {index_path}", file=sys.stderr)
        return 2
    try:
        data = _load(index_path)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not read {index_path}: {e}", file=sys.stderr)
        return 2

    disk_roles = discover_role_files()

    # ── --check: read-only validation ────────────────────────────────────────
    if args.check:
        ok, problems = check(data, disk_roles)
        if ok:
            print(f"✓ library-register CHECK PASS — {len(disk_roles)} disk roles, "
                  f"{len(data.get('roles', []))} index roles, "
                  f"{len(data.get('sops', []))} sops, "
                  f"{len(data.get('personas', []))} personas all registered + present; "
                  f"counts agree; no duplicate-residue/orphans.")
            return 0
        print(f"✗ library-register CHECK FAIL — {len(problems)} problem(s):", file=sys.stderr)
        for p in problems[:80]:
            print(f"    - {p}", file=sys.stderr)
        if len(problems) > 80:
            print(f"    … and {len(problems) - 80} more", file=sys.stderr)
        print("\n  Fix: python3 register-library-additions.py --apply "
              "[--prune-duplicate-residue]", file=sys.stderr)
        return 7

    # ── reconcile (compute) ──────────────────────────────────────────────────
    report = reconcile(data, disk_roles)

    print("register-library-additions — reconcile report")
    print(f"  disk roles discovered:  {len(disk_roles)}")
    print(f"  roles added to index:   {len(report['added_roles'])}")
    for p in report["added_roles"][:30]:
        print(f"      + {p}")
    if report["added_depts"]:
        print(f"  NEW departments:        {report['added_depts']}")
    if report.get("added_sops"):
        print(f"  sops registered:        {len(report['added_sops'])}")
        for p in report["added_sops"][:20]:
            print(f"      + {p}")
    if report.get("added_personas"):
        print(f"  personas registered:    {len(report['added_personas'])}")
        for p in report["added_personas"][:20]:
            print(f"      + {p}")
    if report["fixed_paths"]:
        print(f"  healed stale paths:     {len(report['fixed_paths'])}")
        for p in report["fixed_paths"][:10]:
            print(f"      ~ {p}")
    if report["sop_linkage_refreshed"]:
        print(f"  sop_count/sop_min refreshed: {len(report['sop_linkage_refreshed'])}")
        for p in report["sop_linkage_refreshed"][:10]:
            print(f"      ~ {p}")
        if len(report["sop_linkage_refreshed"]) > 10:
            print(f"      … and {len(report['sop_linkage_refreshed']) - 10} more")
    print(f"  total_roles:            {report['recount']['total_roles']}")
    print(f"  total_departments:      {report['recount']['total_departments']}")
    if report["duplicate_residue"]:
        print(f"  DUPLICATE-RESIDUE flat files ({len(report['duplicate_residue'])}):")
        for p in report["duplicate_residue"]:
            print(f"      ! {p}")
    if report["triple_hyphen_orphans"]:
        print(f"  TRIPLE-HYPHEN ORPHANS ({len(report['triple_hyphen_orphans'])}):")
        for p in report["triple_hyphen_orphans"]:
            print(f"      ! {p}")
    if report["missing_files"]:
        print(f"  DEAD ENTRIES (file missing) ({len(report['missing_files'])}):")
        for p in report["missing_files"]:
            print(f"      x {p}")

    if not args.apply:
        print("\n  [REPORT ONLY] index NOT written. Re-run with --apply to reconcile.")
        return 0

    _save(index_path, data)
    print(f"\n  Written: {index_path}")

    # ── --prune-duplicate-residue: delete the stale files ────────────────────
    if args.prune_duplicate_residue:
        pruned = []
        for rel in report["duplicate_residue"] + report["triple_hyphen_orphans"]:
            f = _SKILL_DIR / rel
            try:
                if f.is_file():
                    f.unlink()
                    pruned.append(rel)
            except OSError as e:
                print(f"  WARN: could not delete {rel}: {e}", file=sys.stderr)
        print(f"  pruned {len(pruned)} stale flat/orphan file(s).")
        # Re-discover + re-reconcile so the index reflects the prune (idempotent).
        disk_roles = discover_role_files()
        reconcile(data, disk_roles)
        _save(index_path, data)

    # ── chain: re-tag classes + restamp content hash ─────────────────────────
    ok_t, msg_t = retag_classes()
    print(f"  tag_role_classes: {'OK' if ok_t else 'WARN'} ({msg_t})")
    if not args.no_hash:
        ok_h, msg_h = restamp_content_hash()
        print(f"  content-manifest restamp: {'OK' if ok_h else 'WARN'} ({msg_h})")

    # ── final self-verify ─────────────────────────────────────────────────────
    final = _load(index_path)
    ok, problems = check(final, discover_role_files())
    if ok:
        print("\n✓ reconcile complete — index in sync with disk.")
        return 0
    print(f"\n✗ reconcile left {len(problems)} problem(s) (likely require manual fix):",
          file=sys.stderr)
    for p in problems[:40]:
        print(f"    - {p}", file=sys.stderr)
    return 7


if __name__ == "__main__":
    sys.exit(main())
