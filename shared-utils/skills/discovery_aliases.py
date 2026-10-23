"""
shared-utils/skills/discovery_aliases.py — delivery-skill discovery, alias
resolution, and package integration for the GHL delivery stream (W10B).

One writer for this file: assignment W10B. The delivery skills are the seven
GHL-delivery skills named across the GHL-DELIVERY-SPEC.md streams:

    06-ghl-install-pages        (W8C order components host)
    49-signature-funnel         (W9B role wrappers host)
    71-blackceo-signature-page  (W9A composition host)
    79-signature-order-form     (W8A order bumps host)
    80-signature-upsell         (W8B native upsell host)
    81-signature-downsell       (W8B downsell)
    82-signature-thank-you      (confirmation)

The same skill is reached under several spellings in the wild — the swarm
ledger says `skills/79-checkout`, the 999 distribution ships
`79-signature-order-form -> signature-order-form` symlink pairs, and the
runtime registers both halves. This module is the single alias/dedup
authority so no caller re-invents the mapping:

    canon_skill_id(name)                 -> canonical id or None (fail closed)
    discover_delivery_skills(root)       -> {skill_id: SkillRecord}
    resolve_skill(name, roots=None)      -> SkillRecord or None
    skill_package(record)                -> packaging manifest dict
    default_roots()                      -> repo root + existing install roots

Fail-closed contract (spec gap 5): an unknown name is None, never a guess;
a directory without SKILL.md is not a skill and is never validated as one.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from skills.discovery_aliases import resolve_skill

Run the assert-based self-check:

    python3 -I shared-utils/skills/discovery_aliases.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# ALIAS MAP — every observed spelling of a delivery skill -> canonical id.
# Canonical ids are the numbered slugs that exist in the openclaw-onboarding
# repository root. Keep in sync with the folder names on disk; the self-check
# proves each canonical id's own directory spelling still maps to itself.
# ---------------------------------------------------------------------------
CANONICAL_IDS: Tuple[str, ...] = (
    "06-ghl-install-pages",
    "49-signature-funnel",
    "71-blackceo-signature-page",
    "79-signature-order-form",
    "80-signature-upsell",
    "81-signature-downsell",
    "82-signature-thank-you",
)

ALIAS_MAP: Dict[str, str] = {
    # 06 — GHL install pages / order components ("06-ghl-delivery" is the
    # swarm ledger's spelling for the same skill)
    "06-ghl-delivery": "06-ghl-install-pages",
    "ghl-install-pages": "06-ghl-install-pages",
    # 49 — signature funnel
    "signature-funnel": "49-signature-funnel",
    # 71 — signature page
    "blackceo-signature-page": "71-blackceo-signature-page",
    # 79 — order form / checkout
    "79-checkout": "79-signature-order-form",
    "signature-order-form": "79-signature-order-form",
    # 80 — upsell
    "80-upsell": "80-signature-upsell",
    "signature-upsell": "80-signature-upsell",
    # 81 — downsell
    "81-downsell": "81-signature-downsell",
    "signature-downsell": "81-signature-downsell",
    # 82 — thank-you / confirmation
    "82-thank-you": "82-signature-thank-you",
    "signature-thank-you": "82-signature-thank-you",
}

# Directory spellings accepted per canonical id, canonical first. A root may
# carry several of them at once (999 ships alias dirs plus numbered symlinks);
# discovery dedupes by resolved real path and prefers a real directory over a
# symlink alias.
CANDIDATE_NAMES: Dict[str, Tuple[str, ...]] = {
    cid: tuple(
        [cid] + sorted(a for a, c in ALIAS_MAP.items() if c == cid)
    )
    for cid in CANONICAL_IDS
}

_SKILL_MD = "SKILL.md"
_VERSION_FILE = "skill-version.txt"


def _normalize(name: str) -> str:
    """Lowercase, whitespace/underscore -> hyphen, collapse hyphens, strip."""
    out = "-".join(part for part in str(name).strip().lower().replace("_", "-").split() if part)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def canon_skill_id(name: str) -> Optional[str]:
    """Map any observed spelling to its canonical delivery-skill id.

    Returns None for unknown names — an unavailable alias must never
    silently validate an unknown skill (fail closed, spec gap 5).
    """
    key = _normalize(name)
    if not key:
        return None
    if key in CANONICAL_IDS:
        return key
    return ALIAS_MAP.get(key)


@dataclass
class SkillRecord:
    """One delivery skill as found under one root."""

    skill_id: str
    matched_name: str          # directory spelling that matched
    root: Path
    path: Path                 # as matched (may be a symlink)
    real_path: Path            # symlink-resolved identity
    skill_md: Path
    version: Optional[str] = None
    entry_points: Tuple[str, ...] = field(default_factory=tuple)
    # True when the matched spelling is itself a symlink alias (numbered name
    # -> real dir, as the 999 distribution ships). Compared on the spelling
    # itself, never on resolved paths: /tmp resolves to /private/tmp on macOS
    # and would mark every record as a symlink.
    found_via_symlink: bool = False


def _read_version(skill_dir: Path) -> Optional[str]:
    vf = skill_dir / _VERSION_FILE
    try:
        first = vf.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    return first or None


def _entry_points(skill_dir: Path) -> Tuple[str, ...]:
    """Top-level *.py / *.sh entry scripts of the skill package."""
    try:
        names = [
            p.name
            for p in skill_dir.iterdir()
            if p.is_file() and p.suffix in (".py", ".sh") and not p.name.startswith(".")
        ]
    except OSError:
        return ()
    return tuple(sorted(names))


def discover_delivery_skills(root: Path) -> Dict[str, SkillRecord]:
    """Find every delivery skill under ``root`` (one record per skill id).

    A directory counts as a skill only when it contains SKILL.md. When a root
    carries several spellings of one skill (alias dir + numbered symlink),
    exactly one record is returned: a real directory wins over a symlink, and
    ties break on canonical-first candidate order. All paths are resolved so
    the record identifies the real skill package wherever the alias points.
    """
    root = Path(root)
    found: Dict[str, SkillRecord] = {}
    if not root.is_dir():
        return found
    for skill_id in CANONICAL_IDS:
        for name in CANDIDATE_NAMES[skill_id]:
            cand = root / name
            if not cand.exists():
                continue
            real = cand.resolve()
            skill_md = real / _SKILL_MD
            if not skill_md.is_file():
                continue  # not a skill package — never validated as one
            rec = SkillRecord(
                skill_id=skill_id,
                matched_name=name,
                root=root,
                path=cand,
                real_path=real,
                skill_md=skill_md,
                version=_read_version(real),
                entry_points=_entry_points(real),
                found_via_symlink=cand.is_symlink(),
            )
            prev = found.get(skill_id)
            if prev is None or (prev.found_via_symlink and not rec.found_via_symlink):
                found[skill_id] = rec
    return found


def default_roots() -> List[Path]:
    """Repo root plus every well-known install root that exists on this box."""
    repo_root = Path(__file__).resolve().parent.parent.parent  # shared-utils/skills -> repo
    candidates = [repo_root]
    env_root = os.environ.get("OPENCLAW_SKILLS")
    if env_root:
        candidates.append(Path(env_root))
    candidates += [
        Path.home() / ".openclaw" / "skills",      # Mac install root
        Path("/data/.openclaw/skills"),            # VPS install root
        Path.home() / ".claude" / "skills",        # claude skill root
    ]
    roots: List[Path] = []
    for c in candidates:
        try:
            cr = c.resolve()
        except OSError:
            continue
        if cr.is_dir() and cr not in roots:
            roots.append(cr)
    return roots


def resolve_skill(name: str, roots: Optional[Iterable[Path]] = None) -> Optional[SkillRecord]:
    """Resolve any spelling of a delivery skill to its first found record.

    Unknown spelling -> None. Known spelling absent from every root -> None.
    Never invents a record for a skill that is not actually on disk.
    """
    skill_id = canon_skill_id(name)
    if skill_id is None:
        return None
    for root in (Path(r) for r in (roots if roots is not None else default_roots())):
        rec = discover_delivery_skills(root).get(skill_id)
        if rec is not None:
            return rec
    return None


def skill_package(rec: SkillRecord) -> Dict[str, object]:
    """Package-integration manifest for one discovered skill.

    Everything an installer/packager needs to ship the skill package
    unchanged: identity, real package directory, SKILL.md, version file +
    value, and the top-level entry scripts that exist right now.
    """
    return {
        "skill_id": rec.skill_id,
        "matched_name": rec.matched_name,
        "skill_dir": str(rec.real_path),
        "skill_md": str(rec.skill_md),
        "version_file": str(rec.real_path / _VERSION_FILE),
        "version": rec.version,
        "entry_points": list(rec.entry_points),
        "shared_utils": str(rec.real_path.parent / "shared-utils"),
    }


# ---------------------------------------------------------------------------
# Assert-based self-check (the runnable check for W10B-U1).
#   python3 -I shared-utils/skills/discovery_aliases.py
# ---------------------------------------------------------------------------
def _selfcheck() -> int:
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        assert cond, "FAIL: " + label
        passed += 1
        print("PASS", label)

    # 1 — alias round-trip, fail-closed on unknowns
    for alias, cid in ALIAS_MAP.items():
        ok(canon_skill_id(alias) == cid, f"alias {alias} -> {cid}")
        ok(canon_skill_id(alias.upper().replace("-", "_")) == cid, f"alias casefold {alias}")
    for cid in CANONICAL_IDS:
        ok(canon_skill_id(cid) == cid, f"canonical {cid} maps to itself")
    ok(canon_skill_id("99-nonexistent-skill") is None, "unknown id fails closed")
    ok(canon_skill_id("75-drama-song-ad-factory") is None, "fenced skill 75 not a delivery skill")
    ok(canon_skill_id("77-council-of-wise-elders") is None, "fenced skill 77 not a delivery skill")
    ok(canon_skill_id("") is None, "empty name fails closed")

    # 2 — repo-style root: numbered dirs with SKILL.md + version + entry script
    tmp = Path(tempfile.mkdtemp(prefix="operator-W10B-U1-", dir="/tmp"))
    try:
        repoish = tmp / "repoish"
        for cid in CANONICAL_IDS:
            d = repoish / cid
            d.mkdir(parents=True)
            (d / _SKILL_MD).write_text(f"# {cid}\n", encoding="utf-8")
            (d / _VERSION_FILE).write_text("9.9.9\n", encoding="utf-8")
            (d / "entry.py").write_text("# entry\n", encoding="utf-8")
        recs = discover_delivery_skills(repoish)
        ok(set(recs) == set(CANONICAL_IDS), "repo-style root discovers 7/7")
        ok(all(r.version == "9.9.9" for r in recs.values()), "versions read from skill-version.txt")
        ok(all("entry.py" in r.entry_points for r in recs.values()), "entry points recorded")
        ok(recs["79-signature-order-form"].real_path == (repoish / "79-signature-order-form").resolve(),
           "repo-style real path identity")

        # 3 — dist-style root (999): alias real dirs + numbered symlinks
        dist = tmp / "dist"
        for cid in CANONICAL_IDS:
            alias = next(a for a, c in ALIAS_MAP.items() if c == cid)  # any alias spelling
            real_dir = dist / alias
            real_dir.mkdir(parents=True)
            (real_dir / _SKILL_MD).write_text(f"# {cid}\n", encoding="utf-8")
            (real_dir / _VERSION_FILE).write_text("1.2.3\n", encoding="utf-8")
            (dist / cid).symlink_to(alias)  # numbered name -> alias dir
        drecs = discover_delivery_skills(dist)
        ok(set(drecs) == set(CANONICAL_IDS), "dist-style root discovers 7/7")
        for cid, r in drecs.items():
            alias = next(a for a, c in ALIAS_MAP.items() if c == cid)
            ok(r.real_path == (dist / alias).resolve(), f"dist dedupe keeps real dir for {cid}")
            ok(r.matched_name == alias, f"dist prefers real dir spelling over symlink for {cid}")
        ok(len({id(r) for r in drecs.values()}) == 7, "one record per skill id (no duplicates)")

        # 4 — identity rules: SKILL.md required, symlink real_path, unknown name
        bare = tmp / "bare"
        bare.mkdir()
        (bare / "79-signature-order-form").mkdir()          # no SKILL.md
        (bare / "06-ghl-install-pages").mkdir()
        (bare / "06-ghl-install-pages" / _SKILL_MD).write_text("# 06\n", encoding="utf-8")
        brecs = discover_delivery_skills(bare)
        ok(set(brecs) == {"06-ghl-install-pages"}, "dir without SKILL.md is never validated as a skill")
        ok(resolve_skill("79-checkout", roots=[bare]) is None, "known alias absent from root -> None")
        ok(resolve_skill("totally-unknown", roots=[bare]) is None, "unknown name -> None")
        rec06 = resolve_skill("06-ghl-delivery", roots=[bare])
        ok(rec06 is not None and rec06.skill_id == "06-ghl-install-pages", "resolve_skill via alias")
        ok(skill_package(rec06)["skill_md"].endswith("06-ghl-install-pages/SKILL.md"),
           "package manifest carries SKILL.md path")

        # 5 — live repository root when this file sits in a real checkout
        live_root = Path(__file__).resolve().parent.parent.parent
        if (live_root / "06-ghl-install-pages" / _SKILL_MD).is_file():
            live = discover_delivery_skills(live_root)
            ok(set(live) == set(CANONICAL_IDS), "live repo root discovers 7/7 delivery skills")
            for cid, r in live.items():
                ok((r.real_path / _SKILL_MD).is_file(), f"live SKILL.md present for {cid}")
                ok(r.version is not None, f"live version present for {cid}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
