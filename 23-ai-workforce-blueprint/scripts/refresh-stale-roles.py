#!/usr/bin/env python3
"""
refresh-stale-roles.py — THE ARTIFACT-REFRESH-QUEUE CONSUMER (P2-08 step 2).

────────────────────────────────────────────────────────────────────────────
THE GAP THIS CLOSES
────────────────────────────────────────────────────────────────────────────
`.artifact-refresh-queue.json` has had a PRODUCER since v12.27.0
(detect-stale-artifacts.py, invoked from update-skills.sh and
shared-utils/workspace-dept-refresh.sh) but NEVER a CONSUMER. A box that
updates its skills keeps its OLD role docs forever — the library content
changes, the queue faithfully records "this role is now STALE", and nothing
ever acts on that record (Presentation spec §13.9 deploy trap; P2-08 (b)).

v16.0.2 shipped floor-fill-driver.py, which closed the MISSING-role half of
this gap (a box that lacks a role the library now ships gets it created).
It is explicitly skip-existing / no-clobber — it will never touch a role
that already has a folder on disk. That leaves the STALE half of the gap
wide open: a role the box already has, whose canonical content changed
upstream, never gets refreshed. THIS script is that missing half.

────────────────────────────────────────────────────────────────────────────
SCOPE (deliberately narrow — matches P2-08 (c) step 2 exactly)
────────────────────────────────────────────────────────────────────────────
Drains ONLY queue items where kind == "role" AND status == "STALE":
  - MISSING roles/SOPs stay floor-fill-driver.py's job (this script never
    creates a new role folder — if the role isn't already on disk, the
    item is skipped loudly, not fabricated).
  - kind == "sop" / "dept" / "persona", and status == "ORPHAN" / "UNTRACKED"
    / "MISSING" items are left untouched in the queue — out of this unit's
    scope. (The stale-SOP-*library*-ghost case, a different defect, was
    fixed at v19.50.0 via ingest-sop-library.sh + the row-count gate.)

For each in-scope item:
  1. Parse "<dept>/<role-slug>" from the item's "key".
  2. Locate the role's EXISTING folder on disk under
     departments/<dept>-dept/ (idempotent: it must already be there; if
     it's missing, this is not actually a "stale" case on this box and the
     item is skipped loudly, never silently, never crashing the drain).
  3. Re-run the SAME library_lookup() + try_library_fill() machinery
     create_role_workspace() itself uses (build-workforce.py's own
     canonical fill path) — real content, identical to what a fresh build
     would produce, never hand-authored or stubbed.
  4. Overwrite ONLY how-to.md with the freshly filled + re-stamped content.
     IDENTITY.md / SOUL.md / MEMORY.md / HEARTBEAT.md are role-specific
     (never library-templated) and are NEVER touched.
  5. On success, the item is dropped from the queue (it is no longer
     actionable — the fresh provenance marker now carries the CURRENT
     content_sha, so a re-run of detect-stale-artifacts.py will classify
     it CURRENT). On failure (poisoned entry: nonexistent path, corrupt
     row, library miss, fill-too-thin), the item is left in the queue,
     a loud WARN is printed, and THE DRAIN CONTINUES — one bad row never
     aborts the update.

Fully additive / idempotent / re-runnable: a role already CURRENT is not in
the queue in the first place (detect-stale-artifacts.py only emits
actionable items), so re-running this script when the queue is already
drained is a no-op that prints "0 artifact(s) refreshed".

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --workspace <dir>    client workspace root (default: platform-appropriate
                        resolution, same as detect-stale-artifacts.py).
  --queue-file <path>  default: <workspace>/.artifact-refresh-queue.json
  --apply              actually write files + rewrite the queue. Without
                        this flag the script is DRY-RUN: it reports exactly
                        what it would refresh/skip but touches nothing.

EXIT CODES
  0   always, on a clean run (including "nothing to drain") — this is a
      best-effort, non-fatal, additive pass; a missing/corrupt queue is
      reported and skipped, never fatal to the caller (update-skills.sh).
  1   only on a usage error (bad CLI args).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Self-locating skill-23 resolution (same pattern as floor-fill-driver.py) ──
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
sys.path.insert(0, str(SCRIPTS))
import create_role_workspaces as crw  # type: ignore  # noqa: E402

HOME = os.path.expanduser("~")

_NN_RE = re.compile(r'^\d{1,3}[-_]')
_ROLE_RE = re.compile(r'^(?:ROLE|role)--')


def norm(name: str) -> str:
    """Same normalization floor-fill-driver.py uses to match a queue slug
    against an on-disk folder name (strip NN- prefix / ROLE-- prefix,
    collapse --, lowercase)."""
    n = str(name or "").strip()
    n = _NN_RE.sub('', n)
    n = _ROLE_RE.sub('', n)
    if n.endswith('.md'):
        n = n[:-3]
    n = n.replace('--', '-')
    return n.lower()


def resolve_workspace(explicit):
    """Mirrors detect-stale-artifacts.py's resolve_workspace()."""
    if explicit:
        return Path(explicit)
    candidates = [
        "/data/.openclaw/workspace",
        os.path.join(HOME, ".openclaw", "workspace"),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "departments")) or \
           os.path.isfile(os.path.join(c, ".workforce-build-state.json")):
            return Path(c)
    if os.path.isdir("/data/.openclaw"):
        return Path("/data/.openclaw/workspace")
    return Path(os.path.join(HOME, ".openclaw", "workspace"))


def find_role_dir(dept_dir: Path, role_slug: str):
    """Locate an EXISTING role folder under dept_dir matching role_slug
    (normalized match, same convention floor-fill-driver.py uses). Returns
    None if not present — this script never creates folders."""
    if not dept_dir.is_dir():
        return None
    target = norm(role_slug)
    for e in dept_dir.iterdir():
        if e.is_dir() and ((e / "how-to.md").exists() or (e / "IDENTITY.md").exists()):
            if norm(e.name) == target:
                return e
    roles_sub = dept_dir / "roles"
    if roles_sub.is_dir():
        for e in roles_sub.iterdir():
            if e.is_dir() and norm(e.name) == target:
                return e
    return None


def refresh_one(workspace: Path, dept_slug: str, role_slug: str, label, apply_: bool):
    """Attempt to refresh one STALE role artifact. Returns (ok, detail)."""
    dept_dir = workspace / "departments" / f"{dept_slug}-dept"
    role_dir = find_role_dir(dept_dir, role_slug)
    if role_dir is None:
        return False, (f"no EXISTING role folder for '{dept_slug}/{role_slug}' under "
                        f"{dept_dir} — not a stale-refresh case on this box (that would "
                        f"be floor-fill's job); skipped, nothing written")

    is_ceo = (norm(role_slug) == "master-orchestrator")
    role_name = label or role_slug.replace("-", " ").title()

    # try_library_fill() does the lookup + token-fill + provenance-header stamp
    # + the >=3072B floor check, IDENTICAL to what create_role_workspace() runs
    # for a brand-new role. Returns None on no-match or too-thin (never a stub).
    filled = crw.try_library_fill(role_name, dept_dir, is_ceo, lib_key=role_slug)
    if filled is None:
        return False, (f"library_fill produced no usable content for "
                        f"'{dept_slug}/{role_slug}' (no library match, or fill below "
                        f"the 3072B floor) — skipped, existing how-to.md left untouched")

    how_to = role_dir / "how-to.md"
    if apply_:
        how_to.write_text(filled, encoding="utf-8")
    return True, f"{dept_slug}/{role_slug} -> {role_dir.name}/how-to.md ({len(filled.encode('utf-8'))}B)"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Drain STALE role-kind entries from .artifact-refresh-queue.json "
                    "by re-copying fresh content from the role library (P2-08).")
    parser.add_argument("--workspace", default=None,
                        help="Client workspace root (default: resolved platform-appropriately).")
    parser.add_argument("--queue-file", default=None,
                        help="Default: <workspace>/.artifact-refresh-queue.json")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write files + rewrite the queue. Default: dry-run report only.")
    args = parser.parse_args(argv)

    workspace = resolve_workspace(args.workspace)
    queue_path = Path(args.queue_file) if args.queue_file else workspace / ".artifact-refresh-queue.json"

    if not queue_path.is_file():
        print(f"  refresh-stale-roles: no refresh queue found at {queue_path} — nothing to drain")
        return 0

    try:
        raw = queue_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  refresh-stale-roles: WARN queue file unreadable/corrupt at {queue_path} "
              f"({e}) — skipped loudly, update continues", file=sys.stderr)
        return 0

    items = data.get("items", [])
    if not isinstance(items, list):
        print("  refresh-stale-roles: WARN queue 'items' is not a list — treating as empty, "
              "update continues", file=sys.stderr)
        items = []

    refreshed = 0
    skipped = 0
    remaining_items = []

    for it in items:
        if not isinstance(it, dict):
            print(f"  refresh-stale-roles: WARN malformed queue row ({it!r}) — "
                  f"skipped loudly, drain continues", file=sys.stderr)
            skipped += 1
            continue

        if it.get("kind") != "role" or it.get("status") != "STALE":
            remaining_items.append(it)  # out of scope for this consumer -- left queued
            continue

        key = it.get("key", "")
        if not isinstance(key, str) or "/" not in key:
            print(f"  refresh-stale-roles: WARN malformed key '{key}' in a STALE role row — "
                  f"skipped loudly, drain continues", file=sys.stderr)
            skipped += 1
            remaining_items.append(it)
            continue

        dept_slug, role_slug = key.split("/", 1)
        try:
            ok, detail = refresh_one(workspace, dept_slug, role_slug, it.get("label"), args.apply)
        except Exception as e:  # a poisoned entry must NEVER abort the drain
            ok, detail = False, f"EXCEPTION refreshing '{key}': {e}"

        if ok:
            refreshed += 1
            print(f"  refresh-stale-roles: REFRESHED {detail}")
        else:
            skipped += 1
            print(f"  refresh-stale-roles: WARN SKIPPED {detail}", file=sys.stderr)
            remaining_items.append(it)  # stays queued for the next run

    if args.apply:
        new_summary = dict(data.get("summary", {})) if isinstance(data.get("summary"), dict) else {}
        if "stale" in new_summary:
            new_summary["stale"] = max(0, new_summary["stale"] - refreshed)
        new_data = dict(data)
        new_data["items"] = remaining_items
        new_data["summary"] = new_summary
        new_data["last_drain"] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "refreshed": refreshed,
            "skipped": skipped,
            "generator": "refresh-stale-roles.py",
        }
        try:
            queue_path.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"  refresh-stale-roles: WARN could not rewrite queue file {queue_path}: {e}",
                  file=sys.stderr)

    mode = "" if args.apply else " (DRY-RUN -- pass --apply to write)"
    print(f"  refresh-stale-roles: {refreshed} artifact(s) refreshed, {skipped} skipped, "
          f"{len(remaining_items)} item(s) remain queued{mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
