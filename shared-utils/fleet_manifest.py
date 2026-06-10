#!/usr/bin/env python3
"""
fleet_manifest.py — Per-box loaded-state tracker + legacy-retirement trigger.

AF4: make the legacy-retirement clock REAL.

The deprecation shim + legacy-root fallbacks (tracked in docs/LEGACY-RETIREMENT.md)
are specced "removed one release after fleet migration" but nothing tracked the
trigger.  This module:

  1. Maintains a fleet manifest (fleet-manifest.json at the repo root) that
     records the loaded=YES/NO state per box, updated by fleet-refresh.sh after
     every run.

  2. When EVERY box in the manifest has reported loaded=YES, it fires the
     retirement trigger: create or update the "retire legacy shim + clawd
     fallbacks" GitHub issue via `gh issue create` / `gh issue edit`.

  3. The trigger is DETERMINISTIC — it fires exactly once when the last box
     crosses the loaded=YES threshold. Subsequent runs are idempotent (the
     issue already exists; only update a "last confirmed" timestamp field).

  4. The trigger can also write a sentinel file (`legacy-retirement-triggered`)
     that a CI step or external cron can poll if `gh` is not available.

Schema of fleet-manifest.json:
    {
      "schema_version": 1,
      "boxes": {
        "<box-name>": {
          "loaded": true | false | null,
          "loaded_confidence": "authoritative" | "proxy" | "unknown",
          "last_updated_ts": 1234567890,
          "onboarding_version": "v11.5.0",
          "cc_version": "4.14.0"
        },
        ...
      },
      "retirement_triggered": false,
      "retirement_issue_number": null,
      "retirement_triggered_ts": null,
      "_notes": "Managed by fleet_manifest.py — do not edit manually."
    }

Environment variables (for CI / non-interactive):
    FLEET_MANIFEST_GH_REPO      GitHub "owner/repo" for the issue (default: read from git)
    FLEET_MANIFEST_GITHUB_TOKEN passed through to `gh` implicitly (gh reads GITHUB_TOKEN)
    FLEET_MANIFEST_DRY_RUN      set to "1" to skip the `gh` call and only write the sentinel

Usage (Python):
    from fleet_manifest import update_manifest_for_box, check_retirement_trigger

    # After a fleet-refresh run for one box:
    update_manifest_for_box(repo_root, box_name, box_result)

    # Check if ALL boxes have loaded=YES and fire the trigger if so:
    triggered = check_retirement_trigger(repo_root)

Usage (CLI — for dry-run fixture tests):
    python3 shared-utils/fleet_manifest.py --repo-root <path> \\
        --simulate-all-loaded \\
        --boxes "box-a,box-b,box-c" \\
        [--dry-run]

PRD 1.11 — AF4 — v11.13.0
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
NC     = "\033[0m"

def _err(msg: str) -> None:  print(f"{RED}[fleet-manifest] {msg}{NC}", file=sys.stderr)
def _warn(msg: str) -> None: print(f"{YELLOW}[fleet-manifest] {msg}{NC}", file=sys.stderr)
def _info(msg: str) -> None: print(f"{CYAN}[fleet-manifest] {msg}{NC}", file=sys.stderr)
def _ok(msg: str) -> None:   print(f"{GREEN}[fleet-manifest] {msg}{NC}", file=sys.stderr)


# ── Constants ─────────────────────────────────────────────────────────────────

MANIFEST_FILENAME    = "fleet-manifest.json"
SENTINEL_FILENAME    = "legacy-retirement-triggered"
RETIREMENT_ISSUE_TITLE = "Retire legacy shim + clawd fallbacks (AF4 retirement trigger)"
RETIREMENT_ISSUE_BODY  = """\
## Legacy Retirement Triggered

**All managed boxes have reported `loaded=YES`** — the fleet migration to the
canonical `get_openclaw_paths()` resolver is complete.

### What this means

The deprecation shim and legacy `~/clawd/...` fallbacks tracked in
`docs/LEGACY-RETIREMENT.md` can now be removed in the NEXT release, per the
retirement plan in that document.

### Files to clean up

See `docs/LEGACY-RETIREMENT.md` for the authoritative list of files and the
exact removal steps.  Key areas:

- `32-command-center-setup/scripts/generate-kpi-rollup.py` — remove `roots.extend(...)` local loop
- `32-command-center-setup/scripts/generate-brand-css.py`  — remove `roots.extend(...)` local loop
- `32-command-center-setup/scripts/seed-workspaces.py`     — remove `_zhc_root_candidates()` local loop
- `32-command-center-setup/scripts/seed-dashboard-content.py` — remove inline `~/clawd/...` loop
- `23-ai-workforce-blueprint/scripts/populate-sops-from-manifest.py` — remove inline candidate list
- `23-ai-workforce-blueprint/scripts/sync-md-content-to-db.py`       — remove local loop
- `23-ai-workforce-blueprint/scripts/backfill-build-state.py`        — remove local loop
- `23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py`       — remove single-item local list
- `23-ai-workforce-blueprint/scripts/persona-selector-v2.py`         — remove local path list
- `22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py` — remove local path
- `shared-utils/key_resolver.py`  — consolidate into api_key_utils
- `shared-utils/llm_score.py`     — remove local `~/clawd/...` paths

### Trigger source

Fired automatically by `fleet-refresh.sh` via `shared-utils/fleet_manifest.py`
when the last box crossed the `loaded=YES` threshold.

See `fleet-manifest.json` in the repo root for the per-box state snapshot.

### Next steps

1. Assign this issue to the next sprint.
2. Remove each listed loop/fallback, replacing with `Path(_PATHS["company_root"])`.
3. Clear the tracked-files tables in `docs/LEGACY-RETIREMENT.md`.
4. The CI guard (`AF3: local-candidate-loop guard`) will then enforce the empty allowlist.
5. Close this issue once all removals are shipped and CI is green.
"""

SCHEMA_VERSION = 1


# ── Manifest I/O ──────────────────────────────────────────────────────────────

def _manifest_path(repo_root: Path) -> Path:
    return repo_root / MANIFEST_FILENAME


def load_manifest(repo_root: Path) -> dict:
    """
    Load fleet-manifest.json from repo_root.  Returns a fresh skeleton if the
    file does not exist or is malformed.
    """
    path = _manifest_path(repo_root)
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and "boxes" in data:
                return data
        except Exception:
            _warn(f"fleet-manifest.json is malformed; starting fresh")
    return _empty_manifest()


def _empty_manifest() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "boxes": {},
        "retirement_triggered": False,
        "retirement_issue_number": None,
        "retirement_triggered_ts": None,
        "_notes": (
            "Managed by shared-utils/fleet_manifest.py — do not edit manually. "
            "Updated by fleet-refresh.sh after each run. "
            "When all boxes show loaded=true, the retirement trigger fires (AF4)."
        ),
    }


def save_manifest(repo_root: Path, manifest: dict) -> None:
    """Atomically write fleet-manifest.json."""
    path = _manifest_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2))
    tmp_path.replace(path)
    _info(f"fleet-manifest.json updated at {path}")


# ── Per-box update ─────────────────────────────────────────────────────────────

def update_manifest_for_box(
    repo_root: Path,
    box_name: str,
    box_result: dict,
) -> dict:
    """
    Record the loaded state for one box in fleet-manifest.json.

    Args:
        repo_root:  repo root Path
        box_name:   the box identifier string
        box_result: the JSON dict emitted by fleet_refresh_runner.py for this box

    Returns:
        The updated manifest dict (already saved to disk).
    """
    manifest = load_manifest(repo_root)

    loaded_dict   = box_result.get("loaded", {})
    loaded_yes    = bool(loaded_dict.get("present", False))
    confidence    = loaded_dict.get("loaded_confidence", "unknown")
    onb_version   = box_result.get("onboarding_version", "unknown")
    cc_version    = box_result.get("cc_version", "unknown")

    manifest["boxes"][box_name] = {
        "loaded":             loaded_yes,
        "loaded_confidence":  confidence,
        "last_updated_ts":    int(time.time()),
        "onboarding_version": onb_version,
        "cc_version":         cc_version,
    }

    save_manifest(repo_root, manifest)
    _info(f"Box '{box_name}': loaded={loaded_yes} (confidence={confidence})")
    return manifest


# ── Retirement trigger ─────────────────────────────────────────────────────────

def check_retirement_trigger(
    repo_root: Path,
    dry_run: bool = False,
    gh_repo: Optional[str] = None,
) -> dict:
    """
    Check whether ALL boxes in the manifest have loaded=True.  If so, and the
    trigger has not already fired, fire the retirement trigger:

      1. Write the sentinel file (legacy-retirement-triggered) at repo_root.
      2. Create or update the GitHub retirement-tracker issue via `gh`.

    Args:
        repo_root: repo root Path
        dry_run:   if True, skip the `gh` call (still writes the sentinel)
        gh_repo:   "owner/repo" string; inferred from git remote if None

    Returns:
        A status dict:
          {
            "trigger_fired":    bool,   # True if trigger fired this call
            "already_triggered": bool,   # True if manifest shows already done
            "all_loaded":       bool,
            "loaded_boxes":     [str],
            "not_loaded_boxes": [str],
            "total_boxes":      int,
            "issue_number":     int|None,
            "sentinel_path":    str|None,
            "dry_run":          bool,
          }
    """
    manifest = load_manifest(repo_root)
    boxes = manifest.get("boxes", {})

    if not boxes:
        _warn("fleet-manifest.json has no boxes registered; trigger cannot fire")
        return _trigger_status(
            trigger_fired=False, already_triggered=False,
            all_loaded=False, loaded_boxes=[], not_loaded_boxes=[],
            total_boxes=0, issue_number=None, sentinel_path=None, dry_run=dry_run,
        )

    loaded_boxes     = [b for b, v in boxes.items() if v.get("loaded") is True]
    not_loaded_boxes = [b for b, v in boxes.items() if v.get("loaded") is not True]
    all_loaded       = len(not_loaded_boxes) == 0

    # Already triggered?
    if manifest.get("retirement_triggered"):
        issue_num = manifest.get("retirement_issue_number")
        _ok(f"Retirement trigger already fired (issue #{issue_num}); skipping")
        return _trigger_status(
            trigger_fired=False, already_triggered=True,
            all_loaded=all_loaded, loaded_boxes=loaded_boxes,
            not_loaded_boxes=not_loaded_boxes, total_boxes=len(boxes),
            issue_number=issue_num, sentinel_path=None, dry_run=dry_run,
        )

    if not all_loaded:
        _info(
            f"Retirement trigger NOT yet ready: "
            f"{len(loaded_boxes)}/{len(boxes)} boxes loaded "
            f"(waiting: {', '.join(not_loaded_boxes)})"
        )
        return _trigger_status(
            trigger_fired=False, already_triggered=False,
            all_loaded=False, loaded_boxes=loaded_boxes,
            not_loaded_boxes=not_loaded_boxes, total_boxes=len(boxes),
            issue_number=None, sentinel_path=None, dry_run=dry_run,
        )

    # ALL boxes loaded — fire the trigger
    _ok(f"ALL {len(boxes)} boxes are loaded=YES — firing retirement trigger!")

    # 1. Write sentinel file
    sentinel_path = repo_root / SENTINEL_FILENAME
    sentinel_payload = {
        "triggered_ts":  int(time.time()),
        "boxes":         loaded_boxes,
        "total":         len(boxes),
        "dry_run":       dry_run,
    }
    sentinel_path.write_text(json.dumps(sentinel_payload, indent=2))
    _ok(f"Sentinel written: {sentinel_path}")

    # 2. Create / update GitHub issue
    issue_number = None
    if not dry_run:
        env_dry = os.environ.get("FLEET_MANIFEST_DRY_RUN", "0")
        if env_dry == "1":
            _info("FLEET_MANIFEST_DRY_RUN=1 — skipping gh call")
        else:
            issue_number = _fire_gh_issue(repo_root, gh_repo, loaded_boxes)
    else:
        _info("dry_run=True — skipping gh issue create (sentinel written)")

    # 3. Record in manifest
    manifest["retirement_triggered"]     = True
    manifest["retirement_issue_number"]  = issue_number
    manifest["retirement_triggered_ts"]  = int(time.time())
    save_manifest(repo_root, manifest)

    return _trigger_status(
        trigger_fired=True, already_triggered=False,
        all_loaded=True, loaded_boxes=loaded_boxes,
        not_loaded_boxes=[], total_boxes=len(boxes),
        issue_number=issue_number,
        sentinel_path=str(sentinel_path),
        dry_run=dry_run,
    )


def _trigger_status(
    *,
    trigger_fired: bool,
    already_triggered: bool,
    all_loaded: bool,
    loaded_boxes: list,
    not_loaded_boxes: list,
    total_boxes: int,
    issue_number,
    sentinel_path,
    dry_run: bool,
) -> dict:
    return {
        "trigger_fired":     trigger_fired,
        "already_triggered": already_triggered,
        "all_loaded":        all_loaded,
        "loaded_boxes":      loaded_boxes,
        "not_loaded_boxes":  not_loaded_boxes,
        "total_boxes":       total_boxes,
        "issue_number":      issue_number,
        "sentinel_path":     sentinel_path,
        "dry_run":           dry_run,
    }


def _fire_gh_issue(
    repo_root: Path,
    gh_repo: Optional[str],
    loaded_boxes: list,
) -> Optional[int]:
    """
    Create the retirement-tracker GitHub issue via `gh issue create`.
    Returns the issue number on success, None on failure.

    If the issue already exists (idempotency: someone re-runs after partial
    success), we search for it and update the body instead.
    """
    if gh_repo is None:
        gh_repo = _infer_gh_repo(repo_root)

    if not gh_repo:
        _warn("Cannot infer GitHub repo; set FLEET_MANIFEST_GH_REPO env var")
        return None

    # Check if gh is available
    if not _gh_available():
        _warn("gh CLI not found; skipping GitHub issue creation (sentinel still written)")
        return None

    # Check for an existing open issue with our title
    existing_number = _find_existing_issue(gh_repo)
    if existing_number is not None:
        _info(f"Retirement issue #{existing_number} already exists — updating body")
        return _update_issue(gh_repo, existing_number, loaded_boxes)

    # Create a new issue
    return _create_issue(gh_repo, loaded_boxes)


def _gh_available() -> bool:
    try:
        result = subprocess.run(
            ["gh", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def _infer_gh_repo(repo_root: Path) -> Optional[str]:
    """Infer 'owner/repo' from git remote.get-url origin."""
    env_repo = os.environ.get("FLEET_MANIFEST_GH_REPO", "").strip()
    if env_repo:
        return env_repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, cwd=str(repo_root)
        )
        url = result.stdout.strip()
        # Handle ssh: git@github.com:owner/repo.git
        if url.startswith("git@github.com:"):
            path = url[len("git@github.com:"):]
            return path.removesuffix(".git")
        # Handle https: https://github.com/owner/repo.git
        if "github.com/" in url:
            path = url.split("github.com/", 1)[1]
            return path.removesuffix(".git")
    except Exception:
        pass
    return None


def _find_existing_issue(gh_repo: str) -> Optional[int]:
    """Search for an open issue with the retirement title."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list",
             "--repo", gh_repo,
             "--state", "open",
             "--search", RETIREMENT_ISSUE_TITLE[:50],
             "--json", "number,title",
             "--limit", "20"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        issues = json.loads(result.stdout)
        for issue in issues:
            if RETIREMENT_ISSUE_TITLE in issue.get("title", ""):
                return int(issue["number"])
    except Exception:
        pass
    return None


def _build_issue_body(loaded_boxes: list) -> str:
    boxes_list = "\n".join(f"- `{b}`" for b in sorted(loaded_boxes))
    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return (
        RETIREMENT_ISSUE_BODY
        + f"\n### Fleet state at trigger time ({ts})\n\nAll loaded boxes:\n{boxes_list}\n"
    )


def _create_issue(gh_repo: str, loaded_boxes: list) -> Optional[int]:
    """Create the retirement-tracker issue. Returns issue number or None."""
    body = _build_issue_body(loaded_boxes)
    label_flags: list[str] = []
    # Try to use 'technical-debt' label if it exists; gh will error if it
    # doesn't, so we use --label only if we can confirm the label.
    # For robustness: skip the label if gh label list fails.
    try:
        label_result = subprocess.run(
            ["gh", "label", "list", "--repo", gh_repo, "--json", "name"],
            capture_output=True, text=True, timeout=20
        )
        if label_result.returncode == 0:
            labels = [l.get("name", "") for l in json.loads(label_result.stdout)]
            if "technical-debt" in labels:
                label_flags = ["--label", "technical-debt"]
            elif "enhancement" in labels:
                label_flags = ["--label", "enhancement"]
    except Exception:
        pass

    try:
        cmd = (
            ["gh", "issue", "create",
             "--repo", gh_repo,
             "--title", RETIREMENT_ISSUE_TITLE,
             "--body", body]
            + label_flags
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            # Output is the issue URL, e.g. https://github.com/owner/repo/issues/123
            url = result.stdout.strip()
            _ok(f"Retirement issue created: {url}")
            try:
                return int(url.rstrip("/").split("/")[-1])
            except Exception:
                return None
        else:
            _err(f"gh issue create failed (exit {result.returncode}): {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        _err("gh issue create timed out")
        return None
    except Exception as e:
        _err(f"gh issue create exception: {e}")
        return None


def _update_issue(gh_repo: str, issue_number: int, loaded_boxes: list) -> Optional[int]:
    """Update the body of an existing retirement-tracker issue."""
    body = _build_issue_body(loaded_boxes)
    try:
        result = subprocess.run(
            ["gh", "issue", "edit", str(issue_number),
             "--repo", gh_repo,
             "--body", body],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            _ok(f"Retirement issue #{issue_number} updated")
            return issue_number
        else:
            _err(f"gh issue edit failed (exit {result.returncode}): {result.stderr[:200]}")
            return issue_number  # return existing number even if update failed
    except Exception as e:
        _err(f"gh issue edit exception: {e}")
        return issue_number


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "fleet_manifest.py — per-box loaded-state tracker + legacy-retirement trigger (AF4). "
            "Used by fleet-refresh.sh and fixture tests."
        )
    )
    parser.add_argument("--repo-root", required=True,
                        help="Path to openclaw-onboarding repo root")
    parser.add_argument("--simulate-all-loaded", action="store_true",
                        help="Simulate all named boxes reporting loaded=YES and check the trigger")
    parser.add_argument("--boxes", default="",
                        help="Comma-separated list of box names for --simulate-all-loaded")
    parser.add_argument("--update-box", default="",
                        help="Box name to update with --box-result")
    parser.add_argument("--box-result", default="",
                        help="JSON string of box result to record for --update-box")
    parser.add_argument("--check-trigger", action="store_true",
                        help="Check retirement trigger for the current manifest state")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip gh issue creation (sentinel still written)")
    parser.add_argument("--gh-repo", default="",
                        help="GitHub 'owner/repo' (overrides env + git remote)")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    dry_run   = args.dry_run or os.environ.get("FLEET_MANIFEST_DRY_RUN", "0") == "1"
    gh_repo   = args.gh_repo or os.environ.get("FLEET_MANIFEST_GH_REPO", "") or None

    if args.simulate_all_loaded:
        # Fixture mode: seed all named boxes as loaded=YES, then check trigger
        boxes = [b.strip() for b in args.boxes.split(",") if b.strip()]
        if not boxes:
            print("ERROR: --simulate-all-loaded requires --boxes <comma-list>", file=sys.stderr)
            sys.exit(1)
        manifest = _empty_manifest()
        ts = int(time.time())
        for box in boxes:
            manifest["boxes"][box] = {
                "loaded":             True,
                "loaded_confidence":  "authoritative",
                "last_updated_ts":    ts,
                "onboarding_version": "v11.13.0",
                "cc_version":         "4.14.0",
            }
        save_manifest(repo_root, manifest)
        _info(f"Simulated {len(boxes)} boxes as loaded=YES in {repo_root / MANIFEST_FILENAME}")

        status = check_retirement_trigger(repo_root, dry_run=dry_run, gh_repo=gh_repo)
        print(json.dumps(status, indent=2))

        if status["trigger_fired"] or status["already_triggered"]:
            _ok("Retirement trigger fired (or already triggered) — dry-run simulation complete")
            sys.exit(0)
        else:
            _err("Retirement trigger did NOT fire — check manifest state")
            sys.exit(1)

    elif args.update_box:
        if not args.box_result:
            print("ERROR: --update-box requires --box-result <json>", file=sys.stderr)
            sys.exit(1)
        try:
            box_result = json.loads(args.box_result)
        except Exception as e:
            print(f"ERROR: --box-result is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        update_manifest_for_box(repo_root, args.update_box, box_result)
        status = check_retirement_trigger(repo_root, dry_run=dry_run, gh_repo=gh_repo)
        print(json.dumps(status, indent=2))

    elif args.check_trigger:
        status = check_retirement_trigger(repo_root, dry_run=dry_run, gh_repo=gh_repo)
        print(json.dumps(status, indent=2))

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
