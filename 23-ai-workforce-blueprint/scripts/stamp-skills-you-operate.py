#!/usr/bin/env python3
"""
stamp-skills-you-operate.py — Layer B generator/validator (PRD Departments-That-Use-Skills §4 Layer B, §5.1).

Reads the ONE source of truth `skill-department-map.json` (Layer D) + the role
library `_index.json`, and stamps a marker-guarded **"Skills You Operate"** block
into every OWNING role's canonical template `how-to.md`/`<slug>.md` under
templates/role-library/<dept>/. The block is placed inside the existing §8
"Tools You Use" region (reusing the 19-section skeleton — NO new section) when
that anchor exists, else appended at the end for the few deep-cluster roles that
use a bespoke skeleton.

Each block lists, for the skills THIS (dept, slug) owns per the map:
  - the numbered skill + slug,
  - the plain-language client-intent phrasing that should make the specialist
    reach for it (so intent → skill without the client naming it),
  - the on-box install path (`~/.openclaw/skills/NN-slug/`),
  - the `universal-sops/<cluster>/` execution playbook pointer (when one exists).

WHY A GENERATOR (not hand edits): Layer D is the single binding — Layer B is
GENERATED/VALIDATED against it so the map, the role blocks, and the routing reflex
can never silently desync (mirrors the N38 six-source discipline). The block is
marker-guarded (`<!-- SKILLS_YOU_OPERATE_V1 -->` … `<!-- END SKILLS_YOU_OPERATE_V1 -->`)
so stamping is idempotent and byte-stable across re-runs.

TOKEN-LEAK SAFETY: the block contains NO canonical `{{UPPER_TOKEN}}` fill tokens
(only literal on-box paths + prose), so the content-hash neutral-render token-leak
invariant (hash-content-manifest.py --check) is never tripped by this block.

AFTER STAMPING you MUST re-run `hash-content-manifest.py` so the content manifest
is current (every edited role file's content_sha changes) — the CONTENT-HASH gate
(qc-assert-repo-consistency.py rc=6) forces this before the edit can ship.

USAGE
    python3 stamp-skills-you-operate.py            # stamp/refresh all owning roles in place
    python3 stamp-skills-you-operate.py --dry-run   # report what would change, write nothing
    python3 stamp-skills-you-operate.py --check      # assert every owning role carries a CURRENT
                                                     # block (rc 8 on drift/missing); writes nothing

EXIT CODES
    0  all owning roles carry a current, correct Skills-You-Operate block
    8  --check found a missing/stale block (drift)
    2  could not load the map or the index
"""
import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)                     # 23-ai-workforce-blueprint/
_MAP_PATH = os.path.join(_SKILL_DIR, "skill-department-map.json")
_INDEX_PATH = os.path.join(_SKILL_DIR, "templates", "role-library", "_index.json")

START = "<!-- SKILLS_YOU_OPERATE_V1 -->"
END = "<!-- END SKILLS_YOU_OPERATE_V1 -->"

# Strip the block AND any blank line(s) hugging it, so a re-stamp is byte-stable.
_BLOCK_RE = re.compile(
    r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"[ \t]*\n*",
    re.DOTALL,
)
# §8 "Tools You Use" heading (numbered or by name); we insert before the NEXT
# top-level "## " heading that follows it.
_SEC8_RE = re.compile(r"^##\s*8\.|^##\s+.*Tools You Use", re.MULTILINE | re.IGNORECASE)
_TOP_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def owners_from_map(m):
    """(dept, slug) -> list of owned client-facing skill entries (dicts)."""
    owners = {}
    for s in m["skills"]:
        if not s.get("client_facing"):
            continue
        for r in s.get("roles", []):
            owners.setdefault((r["dept"], r["slug"]), []).append(s)
    return owners


def _intent_phrase(skill, limit=3):
    trg = [t for t in skill.get("intent_triggers", []) if t]
    trg = trg[:limit]
    return " · ".join(f'"{t}"' for t in trg) if trg else "(department capability)"


def _playbook(skill):
    sops = [s for s in skill.get("execution_sops", []) if s]
    if not sops:
        return "—"
    return " · ".join(f"`universal-sops/{s.rstrip('/')}/`" for s in sops)


def build_block(skills):
    """Render the marker-guarded Skills-You-Operate block for one role's skills."""
    # Deterministic order: by numeric skill id.
    skills = sorted(skills, key=lambda s: int(s["skill"]))
    lines = [
        START,
        "**Skills You Operate** — native department capabilities. Reach for these from the client's "
        "plain-language intent; the client never has to name the skill or type its slash command. "
        "Dept-scoped: only your department's skills are offered. Operate the owning skill per its "
        "execution playbook **before** authoring by hand. Rule-Zero paid-call approval (USD announce + "
        "budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.",
        "",
        "| Skill | Reach for it when the client says… | On-box path | Execution playbook |",
        "|---|---|---|---|",
    ]
    for s in skills:
        num = s["skill"]
        slug = s["slug"]
        path = f"`~/.openclaw/skills/{num}-{slug}/`"
        lines.append(f"| **{num}** {slug} | {_intent_phrase(s)} | {path} | {_playbook(s)} |")
    lines.append(END)
    return "\n".join(lines)


def stamp_text(text, block):
    """Return (new_text, changed). Idempotent + byte-stable: strip any existing
    block (normalizing the join to a single blank line), then insert fresh at the
    canonical anchor WITHOUT disturbing surrounding `---` separators.

    Reversibility: the strip regex (``\\n*<block>\\n*`` -> ``\\n\\n``) and the
    insert (``<block>\\n\\n`` immediately before the next top-level heading, or
    ``\\n\\n<block>\\n`` at EOF) are exact inverses, so a second run reproduces the
    first byte-for-byte (verified by test-stamp-skills-you-operate.sh)."""
    base = _BLOCK_RE.sub("\n\n", text)

    m8 = _SEC8_RE.search(base)
    if m8:
        # Insert immediately BEFORE the next top-level heading after §8, keeping
        # any `---` separators between the §8 table and that heading intact.
        nxt = _TOP_HEADING_RE.search(base, m8.end())
        if nxt:
            pos = nxt.start()
            new = base[:pos] + block + "\n\n" + base[pos:]
            return new, (new != text)
    # Fallback: append at end of file (bespoke-skeleton deep-cluster roles).
    new = base.rstrip("\n") + "\n\n" + block + "\n"
    return new, (new != text)


def check_all(map_path=_MAP_PATH, index_path=_INDEX_PATH, skill_dir=_SKILL_DIR):
    """Assert every owning role carries a CURRENT Skills-You-Operate block.

    Returns (drift, n_owners): drift is a list[str] (empty == all current).
    Reused by qc-assert-repo-consistency.py's MAP-CONSISTENCY dimension so the
    role blocks can never silently desync from the map."""
    m = load_json(map_path)
    idx = load_json(index_path)
    pathmap = {(r["dept"], r["slug"]): r["path"] for r in idx["roles"]}
    owners = owners_from_map(m)
    drift = []
    for (dept, slug), skills in sorted(owners.items()):
        rel = pathmap.get((dept, slug))
        if not rel:
            drift.append(f"{dept}/{slug}: owning role not in _index.json")
            continue
        abspath = os.path.join(skill_dir, rel)
        if not os.path.isfile(abspath):
            drift.append(f"{rel}: file missing on disk")
            continue
        text = open(abspath, encoding="utf-8").read()
        _, changed = stamp_text(text, build_block(skills))
        if changed:
            drift.append(f"{rel}: Skills-You-Operate block missing or stale")
    return drift, len(owners)


def main(argv):
    ap = argparse.ArgumentParser(description="Stamp/validate Layer-B Skills-You-Operate role blocks from the map.")
    ap.add_argument("--check", action="store_true", help="assert current; write nothing; rc 8 on drift")
    ap.add_argument("--dry-run", action="store_true", help="report changes; write nothing")
    args = ap.parse_args(argv)

    try:
        m = load_json(_MAP_PATH)
        idx = load_json(_INDEX_PATH)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: could not load map/index: {e}", file=sys.stderr)
        return 2

    pathmap = {(r["dept"], r["slug"]): r["path"] for r in idx["roles"]}
    owners = owners_from_map(m)

    changed_files = []
    drift = []
    missing_files = []

    for (dept, slug), skills in sorted(owners.items()):
        rel = pathmap.get((dept, slug))
        if not rel:
            drift.append(f"{dept}/{slug}: owning role not in _index.json (orphan)")
            continue
        abspath = os.path.join(_SKILL_DIR, rel)
        if not os.path.isfile(abspath):
            missing_files.append(rel)
            drift.append(f"{rel}: file missing on disk")
            continue
        text = open(abspath, encoding="utf-8").read()
        block = build_block(skills)
        new, changed = stamp_text(text, block)
        if changed:
            changed_files.append(rel)
            if args.check:
                drift.append(f"{rel}: Skills-You-Operate block missing or stale")
            elif not args.dry_run:
                open(abspath, "w", encoding="utf-8").write(new)

    if args.check:
        if drift:
            print(f"FAIL — {len(drift)} role(s) with missing/stale Skills-You-Operate block:")
            for d in drift:
                print("  x " + d)
            return 8
        print(f"OK — all {len(owners)} owning roles carry a current Skills-You-Operate block.")
        return 0

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {len(changed_files)} of {len(owners)} owning role file(s).")
    for f in changed_files:
        print("  ~ " + f)
    if drift:
        print("\nWARNINGS:")
        for d in drift:
            print("  ! " + d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
