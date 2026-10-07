#!/usr/bin/env python3
"""W4-04-U1 family 2 — version migration on scratch copies of BOTH
distributions, with a receipt.

Baseline (real recorded releases, read-only from git history):
  A  openclaw-onboarding 75-drama-song-ad-factory at f2b99f292 = v1.0.0
     (skill-version.txt v1.0.0, SKILL.md not yet shipped)
  B  999-setup bundled-skills.txt at 8203088 (no drama-song-ad-factory
     entry — the gap DEPENDENCY-MANIFEST records)

Migration = upgrade both installs to the current release of their own repo.
Local run state lives outside the install tree and must survive untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

check = _lib.check
RUN_ID = "w404-run"


def _failed_checks(receipt):
    if not isinstance(receipt, dict):
        return []
    return [r["check"] for fam in receipt.get("families", {}).values()
            for r in fam["checks"] if r["status"] == "fail"]


def main():
    box = _lib.mktmp("migrate")
    snapshot = None
    state = None
    try:
        # ---------------- pre-migration install ----------------
        _lib.build_migration_box(box)
        p = _lib.box_paths(box)
        pre = {
            "openclaw_version": (p["a"] / "skill-version.txt").read_text().strip(),
            "openclaw_tree_sha256": _lib.tree_digest(p["a"])[0],
            "registry_sha256": _lib.file_sha(p["registry"]),
            "skill_md_present": (p["a"] / "SKILL.md").is_file(),
        }
        check("baseline A is v1.0.0", pre["openclaw_version"] == "v1.0.0",
              pre["openclaw_version"])
        check("baseline A ships no SKILL.md", not pre["skill_md_present"])
        check("baseline 999 registry has no %s entry"
              % _lib.DEPT_SLUG,
              _lib.DEPT_SLUG not in p["registry"].read_text(),
              str(p["registry"]))

        # Local run state, outside the install tree (directive 24.4).
        state = _lib.mktmp("state")
        state_db = state / "run-state.sqlite3"
        _lib.make_run_state(p["core_a"], state_db)
        state_pre, rows = _lib.run_state_digest(state_db)
        check("local run state built", rows >= 3, "rows=%d" % rows)

        # A stale install must FAIL release_check (negative control built
        # into the migration itself).
        rc_pre, rec_pre, out_pre, err_pre = _lib.run_release_check(box)
        fails_pre = _failed_checks(rec_pre)
        check("stale install fails release_check", rc_pre == 1,
              "rc=%s %s" % (rc_pre, (err_pre or out_pre).strip()[-300:]))
        check("pre-state failure names missing SKILL.md",
              any("A ships SKILL.md" == f for f in fails_pre),
              json.dumps(fails_pre))
        check("pre-state failure names registry gap",
              any("999 registry lists" in f for f in fails_pre),
              json.dumps(fails_pre))

        # Rollback source: the exact pre-migration install.
        snapshot = _lib.mktmp("snapshot")
        _lib.snapshot_box(box, snapshot)
        snap_sha = _lib.tree_digest(_lib.box_paths(snapshot)["a"])[0]
        check("pre-migration snapshot captured",
              snap_sha == pre["openclaw_tree_sha256"],
              snap_sha)

        # ---------------- migrate both installs ----------------
        delta = _lib.migrate_box(box)
        post = {
            "openclaw_version": (p["a"] / "skill-version.txt").read_text().strip(),
            "openclaw_tree_sha256": _lib.tree_digest(p["a"])[0],
            "registry_sha256": _lib.file_sha(p["registry"]),
            "skill_md_present": (p["a"] / "SKILL.md").is_file(),
            "nine_tree_sha256": _lib.tree_digest(p["b"])[0],
        }

        check("A version migrated v1.0.0 -> v2.3.0",
              pre["openclaw_version"] == "v1.0.0"
              and post["openclaw_version"] == "v2.3.0",
              "%s -> %s" % (pre["openclaw_version"], post["openclaw_version"]))
        check("A tree digest changed across migration",
              post["openclaw_tree_sha256"] != pre["openclaw_tree_sha256"])
        check("migration added SKILL.md", "SKILL.md" in delta["added"],
              json.dumps(delta["added"]))
        check("migration changed skill-version.txt",
              "skill-version.txt" in delta["changed"],
              json.dumps(delta["changed"]))
        check("migration touched nothing else in A",
              delta["added"] == ["SKILL.md"]
              and delta["changed"] == ["skill-version.txt"]
              and delta["removed"] == [],
              json.dumps({k: delta[k] for k in ("added", "changed", "removed")}))
        check("B skill folder byte-identical across migration",
              delta["nine_changed"] == [],
              json.dumps(delta["nine_changed"]))
        check("999 registry now lists %s" % _lib.DEPT_SLUG,
              _lib.DEPT_SLUG in p["registry"].read_text())
        check("999 registry digest changed",
              post["registry_sha256"] != pre["registry_sha256"])

        # Local run state survives the upgrade untouched.
        state_post, rows_post = _lib.run_state_digest(state_db)
        check("local run state rows unchanged across migration",
              rows_post == rows and state_post == state_pre,
              "%s -> %s" % (state_pre, state_post))

        # ---------------- release_check after migration ----------------
        rc_post, rec_post, out_post, err_post = _lib.run_release_check(box)
        check("release_check exit 0 after migration", rc_post == 0,
              "rc=%s %s" % (rc_post, (err_post or out_post).strip()[-300:]))
        check("release_check verdict PASS after migration",
              isinstance(rec_post, dict) and rec_post.get("verdict") == "PASS",
              str(rec_post.get("verdict") if isinstance(rec_post, dict) else rec_post))

        receipt = _lib.stamp({
            "receipt": "migration",
            "covered": ["openclaw", "nine"],
            "baseline": {
                "description": "pre-current recorded releases, read from git "
                               "history (read-only)",
                "openclaw_repo": str(_lib.ONB_REPO),
                "openclaw_commit": _lib.OLD_A_COMMIT,
                "nine_repo": str(_lib.NINE_REPO),
                "nine_commit": _lib.OLD_B_COMMIT,
            },
            "target": {
                "openclaw_commit": _lib.git_head(_lib.ONB_REPO),
                "nine_commit": _lib.git_head(_lib.NINE_REPO),
            },
            "before": dict(pre, release_check_exit=rc_pre,
                           release_check_failed=fails_pre),
            "after": dict(post, release_check_exit=rc_post,
                          release_check_verdict=rec_post.get("verdict")
                          if isinstance(rec_post, dict) else None),
            "delta": delta,
            "local_run_state": {
                "path": "outside install tree (caller-chosen)",
                "rows": rows,
                "sha256_before": state_pre,
                "sha256_after": state_post,
                "preserved": state_pre == state_post,
            },
            "checks": _lib.CHECKS,
            "verdict": "PASS",
        })
        _lib.write_receipt("migration.json", receipt)
        _lib.EVIDENCE.mkdir(parents=True, exist_ok=True)
        (_lib.EVIDENCE / "migration.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n")

        print("MIGRATION_OK openclaw %s -> %s"
              % (pre["openclaw_version"], post["openclaw_version"]))
        return 0
    finally:
        _lib.rm_tmp(box)
        _lib.rm_tmp(snapshot)
        _lib.rm_tmp(state)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("tooling-failure: %s" % exc, file=sys.stderr)
        sys.exit(2)
