#!/usr/bin/env python3
"""
floor-fill-driver.py - idempotent, fill-missing-ONLY workforce floor remediation.

SHIPPED-TO-BOX materializer (v16.0.2). Runs ON the client box as the BOX USER
(never root). Reuses the box's OWN installed Skill-23 pipeline
(create_role_workspaces.py from templates/role-library) so all content is REAL
canonical library content - NEVER hand-authored or fabricated, NEVER stubbed.

This is the tool the update path was MISSING: detect-stale-artifacts.py correctly
DETECTS which canonical floor roles / SOPs a v16-updated box is missing, but until
v16.0.2 nothing ever APPLIED the fill. This driver consumes a gap-file (produced by
make-gap-from-staleness.py from the detect-stale verdict) and materializes the
missing slots idempotently.

For each (dept, role) gap supplied it:
  - SKIPS the role entirely if a normalized-matching role folder/file already
    exists on disk (idempotent; never clobbers curated content).
  - Otherwise instantiates the role via create_role_workspace() with the canonical
    roster slug + number, which fills how-to.md FROM the role-library
    (try_library_fill) - real content, identical to a fresh build.

For named-set SOP depts it copies missing-ONLY the library <dept>/sops/*.md into
the live dept/sops/ directory (never overwrites an existing file).

Dept-level scaffolding (sops/ dir, how-to-use-this-department.md) is created
missing-only via scaffold_department().

GAP MAP is passed as a JSON file (--gap-file) in the form:
  { "<dept>": { "kind": "roster"|"named-set",
                "missing_roles": ["<slug>", ...],
                "missing_sops":  ["<file.md>", ...]   # named-set only
              }, ... }

SAFETY CONTRACT:
  - skip-existing, no-clobber: a present role/SOP is NEVER overwritten.
  - additive-only: the driver only CREATES missing slots.
  - dry-run by default; --apply required to mutate.
  - resolves the box's OWN skill-23 install (self-locating: this script lives in
    <skill-23>/scripts/) so it never depends on operator-only tooling.
  - the department DIRECTORY is DETECTED (crw.resolve_dept_dir), never assumed.
  - it never fabricates content: a role the canonical library cannot produce is
    reported as a FAILURE, never stubbed.

EXIT CODES
  0  every slot in the gap-map is now filled (or was already present).
  3  at least one slot the gap-map asked for could NOT be materialized —
     unresolvable department, no canonical library content, a builder error, or
     a missing library SOP source. The gap-map is a list of gaps the detector
     already PROVED are missing, so a slot left unfilled is a detected gap that
     went unrepaired and MUST be loud: migrate-existing-workforce.sh Step 2b
     propagates this into its own exit status, which trips update-skills.sh's
     _D2_MIGRATE_STATUS latch and prints the WORKFORCE-PROVISIONING INCOMPLETE
     block. Returning 0 unconditionally (every release up to v20.0.76) is what
     let "detected the gap, filled nothing, reported success" ship.
  2  the gap-file could not be read or parsed.
"""
import argparse, json, os, re, sys
from pathlib import Path

# ── Self-locating skill-23 resolution ────────────────────────────────────────
# This script ships INSIDE <skill-23>/scripts/, so parent.parent IS the skill
# dir on every box (Mac ~/.openclaw, VPS /data/.openclaw, or a repo checkout).
# An explicit env override + the canonical platform paths are tried as a
# defensive fallback. We anchor on the presence of create_role_workspaces.py.
_SCRIPT = Path(__file__).resolve()
_DEFAULT_SKILL_DIR = _SCRIPT.parent.parent


def _resolve_skill_dir() -> Path:
    cands = []
    env = os.environ.get("OPENCLAW_SKILL23_DIR")
    if env:
        cands.append(Path(env))
    cands.append(_DEFAULT_SKILL_DIR)
    cands.append(Path.home() / ".openclaw/skills/23-ai-workforce-blueprint")
    cands.append(Path("/data/.openclaw/skills/23-ai-workforce-blueprint"))
    for c in cands:
        try:
            if (c / "scripts" / "create_role_workspaces.py").is_file():
                return c
        except OSError:
            continue
    return _DEFAULT_SKILL_DIR


SKILL_DIR = _resolve_skill_dir()
SCRIPTS = SKILL_DIR / "scripts"
LIBRARY = SKILL_DIR / "templates/role-library"

# import the box's OWN pipeline module (canonical builder)
sys.path.insert(0, str(SCRIPTS))
for _libp in (SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils", SKILL_DIR / "lib"):
    sys.path.insert(0, str(_libp))
import create_role_workspaces as crw  # type: ignore  # noqa: E402

_NN_RE = re.compile(r'^\d{1,3}[-_]')
_ROLE_RE = re.compile(r'^(?:ROLE|role)--')


def norm(name: str) -> str:
    n = name.strip()
    n = _NN_RE.sub('', n)
    n = _ROLE_RE.sub('', n)
    if n.endswith('.md'):
        n = n[:-3]
    n = n.replace('--', '-')
    return n.lower()


def existing_role_keys(dept_dir: Path):
    keys = set()
    if not dept_dir.is_dir():
        return keys
    for e in dept_dir.iterdir():
        # a role is a dir with IDENTITY.md/how-to.md, or a <slug>.md file
        if e.is_dir() and ((e / "IDENTITY.md").exists() or (e / "how-to.md").exists()):
            keys.add(norm(e.name))
        elif e.is_file() and e.suffix == ".md":
            keys.add(norm(e.name))
    # nested roles/ layout
    rd = dept_dir / "roles"
    if rd.is_dir():
        for e in rd.iterdir():
            if e.is_dir() and ((e / "IDENTITY.md").exists() or (e / "how-to.md").exists()):
                keys.add(norm(e.name))
            elif e.is_file() and e.suffix == ".md":
                keys.add(norm(e.name))
    return keys


def library_has_role(dept_slug: str, role_slug: str) -> bool:
    dept_key = crw.normalize_dept(dept_slug)
    base = LIBRARY / dept_key
    if (base / role_slug / "how-to.md").exists():
        return True
    if (base / f"{role_slug}.md").exists():
        return True
    return False


def roster_numbers(dept_slug: str):
    """Map normalized role slug -> (canonical_slug, number) from the suggested-roles
    roster if present, else empty. Used so NN- prefixes are consistent with a
    canonical build."""
    sr = SKILL_DIR / "suggested-roles" / f"{dept_slug}-suggested-roles.md"
    out = {}
    if sr.is_file():
        try:
            for r in crw.parse_roster(sr):
                out[norm(r["slug"])] = (r["slug"], r.get("number"))
        except Exception:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-file", required=True)
    ap.add_argument("--workspace", default=None,
                    help="departments/ directory (default: platform-appropriate "
                         "~/.openclaw/workspace/departments or /data/.openclaw/...).")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.workspace:
        ws = Path(args.workspace)
    else:
        # platform-appropriate default departments dir
        vps = Path("/data/.openclaw/workspace/departments")
        ws = vps if Path("/data/.openclaw").is_dir() else (Path.home() / ".openclaw/workspace/departments")

    workspace_root = ws.parent  # .../workspace
    try:
        with open(args.gap_file, encoding="utf-8") as f:
            gaps = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not read gap-file {args.gap_file}: {e}", file=sys.stderr)
        return 2

    report = {"apply": args.apply, "skill_dir": str(SKILL_DIR),
              "roles_created": {}, "roles_skipped_present": {},
              "roles_no_library": {}, "sops_copied": {}, "sops_no_source": {},
              "dept_scaffold": {}, "unfilled": 0}

    # Every gap the driver was handed but could not close. The gap-map contains
    # ONLY slots detect-stale-artifacts.py already proved missing, so a non-zero
    # count here is a detected gap left unrepaired — the loud-failure trigger.
    unfilled = 0

    for dept, info in gaps.items():
        dept_slug = dept
        # DETECT the department directory (bare id / legacy "-dept" suffix /
        # normalized scan absorbing case + separator drift). The old code used
        # the bare id unconditionally and mkdir'd it on a miss, so a real
        # `Sales/` on a case-SENSITIVE filesystem produced a SECOND, empty
        # `sales/` and every restored role landed in the wrong department.
        dept_dir = crw.resolve_dept_dir(ws, dept_slug)
        if dept_dir is None:
            # Genuinely absent on this box. Creating it is correct for a
            # MISSING-class fill — but only now that the probe came back empty.
            dept_dir = ws / dept
            if args.apply:
                try:
                    dept_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    report["dept_scaffold"][dept] = {"error": f"could not create department dir: {e}"}
                    n = len(info.get("missing_roles", []) or []) + len(info.get("missing_sops", []) or [])
                    unfilled += max(n, 1)
                    continue
        present = existing_role_keys(dept_dir)
        rnums = roster_numbers(dept_slug)

        # --- dept-level scaffold (sops/ + how-to-use) missing-only ---
        try:
            sc = crw.scaffold_department(dept_dir, dept_slug, dry_run=not args.apply)
            report["dept_scaffold"][dept] = {"files": sc.get("files", []), "sops": sc.get("sops", 0)}
        except Exception as e:
            report["dept_scaffold"][dept] = {"error": str(e)}

        # --- missing roles ---
        created, skipped, nolib = [], [], []
        for role_slug in info.get("missing_roles", []):
            k = norm(role_slug)
            if k in present:
                skipped.append(role_slug)
                continue
            if not library_has_role(dept_slug, role_slug):
                nolib.append(role_slug)
                continue
            canon_slug, number = rnums.get(k, (role_slug, None))
            disp = role_slug.replace("-", " ").title()
            meta = {"slug": canon_slug, "number": number, "role_type": "specialist"}
            if args.apply:
                try:
                    rp = crw.create_role_workspace(dept_dir, disp, workspace_root, role_metadata=meta)
                    created.append(rp.name)
                    present.add(k)
                except Exception as e:
                    nolib.append(f"{role_slug} (ERROR {e})")
            else:
                created.append(f"(dry) {role_slug}")
        if created:
            report["roles_created"][dept] = created
        if skipped:
            report["roles_skipped_present"][dept] = skipped
        if nolib:
            report["roles_no_library"][dept] = nolib
            # A role the detector proved MISSING that the canonical library
            # cannot produce is an unfilled gap. It is NEVER stubbed or
            # hand-authored — it is reported.
            unfilled += len(nolib)

        # --- named-set SOPs missing-only ---
        if info.get("kind") == "named-set" and info.get("missing_sops"):
            dept_key = crw.normalize_dept(dept_slug)
            lib_sops = LIBRARY / dept_key / "sops"
            sops_dir = dept_dir / "sops"
            copied, nosrc = [], []
            for fname in info["missing_sops"]:
                src = lib_sops / fname
                if not src.exists():
                    # Detector said this SOP is missing from the box and the
                    # library has no source for it: unfillable, so it is loud
                    # rather than a silent `continue`.
                    nosrc.append(fname)
                    continue
                dest = sops_dir / fname
                if dest.exists():
                    continue
                try:
                    if args.apply:
                        sops_dir.mkdir(parents=True, exist_ok=True)
                        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                    copied.append(fname)
                except OSError as e:
                    nosrc.append(f"{fname} (ERROR {e})")
            if copied:
                report["sops_copied"][dept] = {"count": len(copied), "files": copied[:5]}
            if nosrc:
                report["sops_no_source"][dept] = nosrc
                unfilled += len(nosrc)

    report["unfilled"] = unfilled
    print(json.dumps(report, indent=1))

    if unfilled:
        # LOUD. A repair tool that cannot repair must say so: rc 3 is what
        # migrate-existing-workforce.sh Step 2b turns into a non-zero migration
        # exit, which trips update-skills.sh's _D2_MIGRATE_STATUS latch.
        print(f"FAILED: {unfilled} detected floor gap(s) could NOT be materialized "
              f"from the canonical library — see roles_no_library / sops_no_source / "
              f"dept_scaffold.error above. Nothing was stubbed or fabricated.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
