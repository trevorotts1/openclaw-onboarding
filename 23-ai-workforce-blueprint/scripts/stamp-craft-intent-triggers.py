#!/usr/bin/env python3
"""
stamp-craft-intent-triggers.py — Layer-D generator/validator
(PRD Departments-That-Use-Skills §5.4, Wave 1.3b).

Reads the ONE source of truth `skill-department-map.json` (Layer D) and stamps a
marker-guarded **"Intent triggers"** header block into each craft-cluster README
under `universal-sops/<cluster>/README.md`, for every cluster referenced by a
client-facing skill's `execution_sops`. For a referenced cluster that has no
README yet, a minimal README scaffold (title + one-line intro) is created and the
block stamped into it, so EVERY map-referenced craft cluster becomes
self-describing to a specialist and to the map generator.

WHY: the craft clusters are the markdown face of each client-facing skill's
execution playbook, but a specialist had to already KNOW to go read one. The
Intent-triggers header lets the specialist (and any future map generator)
recognize, from the cluster README alone, which plain-language client intents this
craft serves — the same phrasings the role "Skills You Operate" block and the
front-door reflex carry. GENERATED/VALIDATED from the map so it can never desync.

The block is marker-guarded (`<!-- CRAFT_INTENT_TRIGGERS_V1 -->` … `<!-- END … -->`)
so stamping is idempotent and byte-stable across re-runs.

AFTER STAMPING you MUST re-run `scripts/hash-universal-sops-manifest.py` so the
universal-sops content manifest (universal-sops/_content-manifest.json) is current
— every edited/created craft README's sha256 changes and its --check gate fails
otherwise. (This is the universal-sops twin of the role-library CONTENT-HASH gate.)

USAGE
    python3 stamp-craft-intent-triggers.py            # stamp/refresh all map-referenced craft READMEs
    python3 stamp-craft-intent-triggers.py --dry-run   # report what would change, write nothing
    python3 stamp-craft-intent-triggers.py --check      # assert every referenced craft README carries a
                                                        # CURRENT block (rc 8 on drift); writes nothing

EXIT CODES
    0  all map-referenced craft READMEs carry a current, correct block
    8  --check found a missing/stale block (drift)
    2  could not load the map
"""
import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)                     # 23-ai-workforce-blueprint/
_REPO_ROOT = os.path.dirname(_SKILL_DIR)                      # repo root
_MAP_PATH = os.path.join(_SKILL_DIR, "skill-department-map.json")
_USOPS_DIR = os.path.join(_REPO_ROOT, "universal-sops")

START = "<!-- CRAFT_INTENT_TRIGGERS_V1 -->"
END = "<!-- END CRAFT_INTENT_TRIGGERS_V1 -->"

# Strip the block AND any blank line(s) hugging it, so a re-stamp is byte-stable.
_BLOCK_RE = re.compile(
    r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"[ \t]*\n*",
    re.DOTALL,
)
# Existing READMEs open with a `# Title` + intro; insert the block before the
# first `## ` sub-heading (e.g. "## Files"). If none, append after the intro.
_FIRST_SUBHEAD_RE = re.compile(r"^##\s+", re.MULTILINE)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cluster_skills(m):
    """cluster_dir -> list of client-facing skill entries whose execution_sops
    reference that DIRECTORY cluster (loose *.md execution_sops are not clusters)."""
    clusters = {}
    for s in m["skills"]:
        if not s.get("client_facing"):
            continue
        for sop in s.get("execution_sops", []):
            sop = (sop or "").rstrip("/")
            if not sop or sop.endswith(".md"):
                continue  # loose cross-cutting doc, not a craft-cluster directory
            clusters.setdefault(sop, [])
            if s not in clusters[sop]:
                clusters[sop].append(s)
    return clusters


def _say_phrases(skill, limit=5):
    trg = [t for t in skill.get("intent_triggers", []) if t][:limit]
    return " · ".join(f'"{t}"' for t in trg) if trg else "(a request in this area)"


def build_block(cluster, skills):
    """Render the Intent-triggers block for one craft cluster's skills."""
    skills = sorted(skills, key=lambda s: int(s["skill"]))
    lines = [
        START,
        "## Intent triggers",
        "",
        f"This craft cluster (`universal-sops/{cluster}/`) is the execution playbook "
        "for the skill(s) below. A specialist reaches for it when the client's "
        "plain-language request matches any of these intents — the client never has "
        "to name the skill or type its slash command. Source of truth: "
        "`23-ai-workforce-blueprint/skill-department-map.json` (Layer D).",
        "",
        "| Skill | Reach for this craft when the client says… |",
        "|---|---|",
    ]
    for s in skills:
        lines.append(f"| **{s['skill']}** {s['slug']} | {_say_phrases(s)} |")
    lines += [
        "",
        "Dept-scoped: only the task department's craft is offered. Operate the owning "
        "skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero "
        "paid-call approval (USD announce + budget cap) still applies. Doctrine: "
        "`universal-sops/native-skill-invocation.md`.",
        END,
    ]
    return "\n".join(lines)


def _scaffold(cluster):
    """Minimal README scaffold for a referenced cluster that has none yet."""
    title = cluster.replace("-", " ").title()
    return (
        f"# {title} SOP Cluster (`universal-sops/{cluster}/`)\n\n"
        f"The SHARED, cross-department execution playbook for this craft. It does NOT "
        f"re-implement the skill; the authoritative machine spine lives in the numbered "
        f"skill folder. The SOP/manifest files in this directory govern the procedure; "
        f"the Intent-triggers header below (generated from the skill-department map) "
        f"states which plain-language client intents route here.\n"
    )


def stamp_text(text, block):
    """Return (new_text, changed). Idempotent + byte-stable."""
    base = _BLOCK_RE.sub("\n\n", text)
    m = _FIRST_SUBHEAD_RE.search(base)
    if m:
        pos = m.start()
        new = base[:pos] + block + "\n\n" + base[pos:]
        return new, (new != text)
    new = base.rstrip("\n") + "\n\n" + block + "\n"
    return new, (new != text)


def _readme_path(cluster):
    return os.path.join(_USOPS_DIR, cluster, "README.md")


def check_all(map_path=_MAP_PATH, usops_dir=_USOPS_DIR):
    """Assert every map-referenced craft README carries a CURRENT block.
    Returns (drift, n_clusters). Reused by qc-assert-repo-consistency.py."""
    m = load_json(map_path)
    clusters = cluster_skills(m)
    drift = []
    for cluster, skills in sorted(clusters.items()):
        cdir = os.path.join(usops_dir, cluster)
        if not os.path.isdir(cdir):
            drift.append(f"universal-sops/{cluster}/: cluster directory missing on disk")
            continue
        path = os.path.join(cdir, "README.md")
        text = _scaffold(cluster) if not os.path.isfile(path) else open(path, encoding="utf-8").read()
        _, changed = stamp_text(text, build_block(cluster, skills))
        if changed or not os.path.isfile(path):
            drift.append(f"universal-sops/{cluster}/README.md: Intent-triggers block missing or stale")
    return drift, len(clusters)


def main(argv):
    ap = argparse.ArgumentParser(description="Stamp/validate craft-cluster Intent-triggers headers from the map.")
    ap.add_argument("--check", action="store_true", help="assert current; write nothing; rc 8 on drift")
    ap.add_argument("--dry-run", action="store_true", help="report changes; write nothing")
    args = ap.parse_args(argv)

    try:
        m = load_json(_MAP_PATH)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: could not load map: {e}", file=sys.stderr)
        return 2

    clusters = cluster_skills(m)
    changed_files = []
    created_files = []
    drift = []

    for cluster, skills in sorted(clusters.items()):
        cdir = os.path.join(_USOPS_DIR, cluster)
        if not os.path.isdir(cdir):
            drift.append(f"universal-sops/{cluster}/: cluster directory missing on disk")
            continue
        path = _readme_path(cluster)
        rel = os.path.relpath(path, _REPO_ROOT)
        exists = os.path.isfile(path)
        text = open(path, encoding="utf-8").read() if exists else _scaffold(cluster)
        new, changed = stamp_text(text, build_block(cluster, skills))
        if changed or not exists:
            if args.check:
                drift.append(f"{rel}: Intent-triggers block missing or stale")
            elif not args.dry_run:
                if not exists:
                    os.makedirs(cdir, exist_ok=True)
                    created_files.append(rel)
                else:
                    changed_files.append(rel)
                open(path, "w", encoding="utf-8").write(new)
            else:
                (created_files if not exists else changed_files).append(rel)

    if args.check:
        if drift:
            print(f"FAIL — {len(drift)} craft README(s) with missing/stale Intent-triggers block:")
            for d in drift:
                print("  x " + d)
            return 8
        print(f"OK — all {len(clusters)} map-referenced craft READMEs carry a current Intent-triggers block.")
        return 0

    verb = "would update/create" if args.dry_run else "updated/created"
    print(f"{verb} {len(changed_files) + len(created_files)} of {len(clusters)} craft README(s).")
    for f in created_files:
        print("  + " + f)
    for f in changed_files:
        print("  ~ " + f)
    if drift:
        print("\nWARNINGS:")
        for d in drift:
            print("  ! " + d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
