#!/usr/bin/env python3
"""W4-04-U1 family 3 — rollback path on scratch copies of BOTH
distributions, with a receipt.

Sequence: install the pre-current baseline, migrate it to the current
release (same real commits as test_migration.py), then roll back and prove:

  * the A install tree is byte-identical to the pre-migration snapshot
  * the 999 install manifest is byte-identical to its pre-migration bytes
  * the B skill folder never moved (it has no file delta between releases)
  * local run state outside the install tree is untouched
  * release_check reports exactly the same failures as the pre-migration
    install — rollback lands on the prior state, not on something adjacent
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

check = _lib.check


def _receipt_shape(receipt):
    if not isinstance(receipt, dict):
        return None
    out = []
    for fam in receipt.get("families", {}).values():
        for r in fam["checks"]:
            if r["status"] == "fail":
                out.append(r["check"])
    return out


def main():
    box = _lib.mktmp("rollback")
    snapshot = None
    state = None
    try:
        # ---------------- baseline install ----------------
        _lib.build_migration_box(box)
        p = _lib.box_paths(box)
        pre_a_sha, pre_a_files = _lib.tree_digest(p["a"])
        pre_b_sha, pre_b_files = _lib.tree_digest(p["b"])
        pre_reg_sha = _lib.file_sha(p["registry"])
        pre_version = (p["a"] / "skill-version.txt").read_text().strip()
        check("baseline A is v1.0.0", pre_version == "v1.0.0", pre_version)
        check("baseline A ships no SKILL.md", not (p["a"] / "SKILL.md").is_file())
        check("baseline registry has no %s entry" % _lib.DEPT_SLUG,
              _lib.DEPT_SLUG not in p["registry"].read_text())

        state = _lib.mktmp("state")
        state_db = state / "run-state.sqlite3"
        _lib.make_run_state(p["core_a"], state_db)
        state_pre, rows = _lib.run_state_digest(state_db)

        rc_pre, rec_pre, out_pre, err_pre = _lib.run_release_check(box)
        fails_pre = _receipt_shape(rec_pre)
        check("baseline install fails release_check (stale release)",
              rc_pre == 1, "rc=%s" % rc_pre)

        # ---------------- migrate, then roll back ----------------
        snapshot = _lib.mktmp("snapshot")
        _lib.snapshot_box(box, snapshot)
        snap_a_sha, snap_a_files = _lib.tree_digest(
            _lib.box_paths(snapshot)["a"])
        snap_reg_sha = _lib.file_sha(_lib.box_paths(snapshot)["registry"])
        check("snapshot matches baseline before migration",
              snap_a_sha == pre_a_sha and snap_reg_sha == pre_reg_sha,
              "%s / %s" % (snap_a_sha, snap_reg_sha))

        delta = _lib.migrate_box(box)
        check("migration actually changed A",
              delta["openclaw_before_sha256"] != delta["openclaw_after_sha256"],
              json.dumps({"added": delta["added"],
                          "changed": delta["changed"]}))
        check("migration registered the skill in 999",
              _lib.DEPT_SLUG in p["registry"].read_text())
        check("A is v2.3.0 after migration",
              (p["a"] / "skill-version.txt").read_text().strip() == "v2.3.0")

        _lib.rollback_box(box, snapshot)
        post_a_sha, post_a_files = _lib.tree_digest(p["a"])
        post_b_sha, post_b_files = _lib.tree_digest(p["b"])
        post_reg_sha = _lib.file_sha(p["registry"])
        post_version = (p["a"] / "skill-version.txt").read_text().strip()

        # ---------------- rollback assertions ----------------
        check("A tree restored byte-identical to baseline",
              post_a_sha == pre_a_sha,
              "%s -> %s" % (pre_a_sha, post_a_sha))
        check("A file set restored exactly",
              post_a_files == pre_a_files,
              json.dumps({"before": len(pre_a_files),
                          "after": len(post_a_files),
                          "delta": sorted(set(post_a_files)
                                          ^ set(pre_a_files))}))
        check("A version stamp back to v1.0.0", post_version == "v1.0.0",
              post_version)
        check("A SKILL.md removed again by rollback",
              not (p["a"] / "SKILL.md").is_file())
        check("999 install manifest restored byte-identical",
              post_reg_sha == pre_reg_sha,
              "%s -> %s" % (pre_reg_sha, post_reg_sha))
        check("999 registry entry gone again",
              _lib.DEPT_SLUG not in p["registry"].read_text())
        check("B skill folder byte-identical through migrate+rollback",
              post_b_sha == pre_b_sha and post_b_files == pre_b_files,
              "%s -> %s" % (pre_b_sha, post_b_sha))

        state_post, rows_post = _lib.run_state_digest(state_db)
        check("local run state untouched by migrate+rollback",
              rows_post == rows and state_post == state_pre,
              "%s -> %s" % (state_pre, state_post))

        rc_post, rec_post, out_post, err_post = _lib.run_release_check(box)
        fails_post = _receipt_shape(rec_post)
        check("release_check fails on the rolled-back install",
              rc_post == 1, "rc=%s %s" % (rc_post,
                                          (err_post or out_post).strip()[-300:]))
        check("rolled-back install reports the same failures as baseline",
              fails_post == fails_pre,
              json.dumps({"baseline": fails_pre, "rolled_back": fails_post}))

        receipt = _lib.stamp({
            "receipt": "rollback",
            "covered": ["openclaw", "nine"],
            "procedure": "restore install tree + 999 install manifest from a "
                         "byte snapshot taken immediately before migration; "
                         "local run state lives outside the install tree and "
                         "is never rewritten",
            "baseline": {
                "openclaw_commit": _lib.OLD_A_COMMIT,
                "nine_commit": _lib.OLD_B_COMMIT,
                "openclaw_version": pre_version,
            },
            "migrated_then_rolled_back": {
                "migrated_version": "v2.3.0",
                "delta": delta,
            },
            "after_rollback": {
                "openclaw_version": post_version,
                "openclaw_tree_sha256": post_a_sha,
                "openclaw_tree_sha256_before": pre_a_sha,
                "openclaw_files": len(post_a_files),
                "nine_tree_sha256": post_b_sha,
                "nine_tree_sha256_before": pre_b_sha,
                "registry_sha256": post_reg_sha,
                "registry_sha256_before": pre_reg_sha,
                "release_check_exit": rc_post,
                "release_check_failed": fails_post,
                "release_check_failed_baseline": fails_pre,
            },
            "local_run_state": {
                "sha256_before": state_pre,
                "sha256_after": state_post,
                "preserved": state_pre == state_post,
            },
            "checks": _lib.CHECKS,
            "verdict": "PASS",
        })
        _lib.write_receipt("rollback.json", receipt)
        _lib.EVIDENCE.mkdir(parents=True, exist_ok=True)
        (_lib.EVIDENCE / "rollback.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n")

        print("ROLLBACK_OK restored sha256=%s files=%d"
              % (post_a_sha, len(post_a_files)))
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
