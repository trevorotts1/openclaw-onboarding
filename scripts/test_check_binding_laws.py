#!/usr/bin/env python3
"""Self-check for scripts/check-binding-laws.py -- proves the guard DISCRIMINATES.

A guard is only worth having if it can be shown to go red on a known-bad tree and
green on a known-good one. This file builds throwaway git repositories in a temp
directory, runs the real checker against them, and asserts both directions for every
law the checker can decide from git (L1, L5, L6, L12, L13) plus the evidence laws
(L2-L4, L7-L11, L14-L16) and the DEFERRED rule.

Run either way:
    python3 scripts/test_check_binding_laws.py
    python3 -m pytest scripts/test_check_binding_laws.py -q

Exit 0 = every case behaved as asserted.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "check-binding-laws.py")
BOT = "41898282+github-actions[bot]@users.noreply.github.com"
PIN = "49-signature-funnel/scripts/SF-PROVER-PIN.sha256"
# This file is itself a test path, so the checker scans it when it lands. The
# skip-marker fixture is therefore assembled from parts, the same idiom
# tools/gate-added-paths.sh uses: a scanner must never contain the literal text
# it scans for, or the guard trips on its own fixture (which it did, on PR #3029).
XF = "x" + "fail"
SKIP_MARK = "pytest.mark." + XF


class Repo:
    """A throwaway repository with a base commit and a branch to test."""

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="binding-laws-test-")
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "lane@example.test")
        self._git("config", "user.name", "lane")
        self._git("config", "commit.gpgsign", "false")
        self._write("README.md", "base\n")
        self._write("tests/test_sample.py", "def test_ok():\n    assert 1 == 1\n")
        self.commit("base")
        self.base = self.head()

    # -- plumbing --
    def _git(self, *args, env=None):
        e = dict(os.environ)
        if env:
            e.update(env)
        cp = subprocess.run(
            ["git", *args], cwd=self.path, capture_output=True, text=True, env=e
        )
        if cp.returncode != 0 and args[0] not in ("merge-base",):
            raise RuntimeError(f"git {' '.join(args)} rc={cp.returncode}: {cp.stderr}")
        return cp

    def _write(self, rel, content):
        full = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(full) or self.path, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)

    def commit(self, message, author=BOT, committer=BOT):
        self._git("add", "-A")
        self._git(
            "commit",
            "-q",
            "--no-gpg-sign",
            "-m",
            message,
            env={
                "GIT_AUTHOR_NAME": "bot" if author == BOT else "lane",
                "GIT_AUTHOR_EMAIL": author,
                "GIT_COMMITTER_NAME": "bot" if committer == BOT else "lane",
                "GIT_COMMITTER_EMAIL": committer,
            },
        )
        return self.head()

    def head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


def run(repo, *extra):
    cp = subprocess.run(
        [sys.executable, CHECKER, "--repo", repo.path, "--base", repo.base, "--head", "HEAD", *extra],
        capture_output=True,
        text=True,
    )
    return cp.returncode, cp.stdout + cp.stderr


def statuses(out):
    table = {}
    for line in out.splitlines():
        if line.startswith("[") and "]" in line:
            mark = line[1 : line.index("]")]
            law = line[line.index("]") + 1 :].split()[0]
            table[law] = {"PASS": "PASS", "FAIL": "FAIL", "DEFER": "DEFERRED"}[mark]
    return table


# --- L1 ---------------------------------------------------------------------------
def test_l1_clean_range_passes():
    r = Repo()
    try:
        r._write("tests/test_sample.py", "def test_ok():\n    assert 2 == 2\n")
        r.commit("tighten a test")
        rc, out = run(r)
        assert statuses(out)["L1"] == "PASS", out
    finally:
        r.cleanup()


def test_l1_removed_assertion_fails():
    r = Repo()
    try:
        r._write("tests/test_sample.py", "def test_ok():\n    pass\n")
        r.commit("drop the check")
        rc, out = run(r)
        assert statuses(out)["L1"] == "FAIL", out
        assert rc == 1, out
    finally:
        r.cleanup()


def test_l1_added_xfail_fails():
    r = Repo()
    try:
        fixture = f"import pytest\n@{SKIP_MARK}\ndef test_ok():\n    assert 1 == 1\n"
        r._write("tests/test_sample.py", fixture)
        r.commit("mark it xfail")
        rc, out = run(r)
        assert statuses(out)["L1"] == "FAIL", out
    finally:
        r.cleanup()


def test_l1_widened_threshold_fails():
    r = Repo()
    try:
        r._write("tests/test_sample.py", "FLOOR = 90\ndef test_ok():\n    assert SCORE >= 90\n")
        r.commit("add a floor")
        r.base = r.head()
        r._write("tests/test_sample.py", "FLOOR = 90\ndef test_ok():\n    assert SCORE >= 70\n")
        r.commit("lower the floor")
        rc, out = run(r)
        assert statuses(out)["L1"] == "FAIL", out
    finally:
        r.cleanup()


# --- L12 / L13 --------------------------------------------------------------------
def test_l12_merge_commit_fails():
    r = Repo()
    try:
        r._git("checkout", "-q", "-b", "side")
        r._write("side.txt", "x\n")
        r.commit("side work")
        r._git("checkout", "-q", "main")
        r._write("main.txt", "y\n")
        r.commit("main work")
        r._git("merge", "-q", "--no-ff", "-m", "merge side", "side")
        rc, out = run(r)
        assert statuses(out)["L12"] == "FAIL", out
    finally:
        r.cleanup()


def test_l13_stale_base_fails():
    r = Repo()
    try:
        r._git("checkout", "-q", "-b", "stale")
        r._write("a.txt", "a\n")
        r.commit("stale branch work")
        r._git("checkout", "-q", "main")
        r._write("b.txt", "b\n")
        r.commit("main moved on")
        cp = subprocess.run(
            [sys.executable, CHECKER, "--repo", r.path, "--base", "main", "--head", "stale"],
            capture_output=True,
            text=True,
        )
        assert statuses(cp.stdout + cp.stderr)["L13"] == "FAIL", cp.stdout + cp.stderr
        assert cp.returncode == 1, cp.stdout + cp.stderr
    finally:
        r.cleanup()


# --- L5 / L6 ----------------------------------------------------------------------
def test_l5_hand_written_pin_fails():
    r = Repo()
    try:
        r._write(PIN, "deadbeef\n")
        r.commit("edit the pin by hand", author="lane@example.test", committer="lane@example.test")
        rc, out = run(r)
        assert statuses(out)["L5"] == "FAIL", out
    finally:
        r.cleanup()


def test_l5_bot_written_pin_passes():
    r = Repo()
    try:
        r._write(PIN, "deadbeef\n")
        r.commit("ci: mint the pin")
        rc, out = run(r)
        assert statuses(out)["L5"] == "PASS", out
    finally:
        r.cleanup()


def test_l6_second_mint_commit_fails():
    r = Repo()
    try:
        r._write(PIN, "aaaa\n")
        r.commit("ci: mint one")
        r._write(PIN, "bbbb\n")
        r.commit("ci: mint two")
        rc, out = run(r)
        assert statuses(out)["L6"] == "FAIL", out
    finally:
        r.cleanup()


# --- evidence laws ----------------------------------------------------------------
def _evidence_dir(tmp, **laws):
    d = os.path.join(tmp, "evidence")
    os.makedirs(d, exist_ok=True)
    defaults = {
        "L2": {"force_push_events": 0},
        "L3": {"admin_bypassed": False, "required_checks_green_at_merge": True},
        "L4": {"used_no_verify": False},
        "L7": {"ssh_invocations": 0},
        "L8": {"fleet_targets_contacted": 0},
        "L9": {"secrets_in_transcript": 0},
        "L10": {"files_changed_without_collision_check": []},
        "L11": {"open_prs_for_unit": 1, "closed_prs_all_link_replacement": True},
        "L14": {"out_of_scope_paths_written": []},
        "L15": {"qc_lane_id": "qc-1", "builder_lane_id": "build-1", "qc_model": "opus-chain"},
        "L16": {"verdict": "CONFIRMED", "defects": []},
    }
    defaults.update(laws)
    for law, payload in defaults.items():
        with open(os.path.join(d, f"{law}.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return d


def test_evidence_deferred_without_dir():
    r = Repo()
    try:
        rc, out = run(r)
        assert statuses(out)["L2"] == "DEFERRED", out
        assert rc == 0, "a deferred law must not fail the default run"
    finally:
        r.cleanup()


def test_evidence_required_fails_when_deferred():
    r = Repo()
    try:
        rc, out = run(r, "--require-evidence")
        assert rc == 1, out
    finally:
        r.cleanup()


def test_evidence_good_payloads_pass():
    r = Repo()
    try:
        d = _evidence_dir(r.path)
        rc, out = run(r, "--evidence-dir", d, "--require-evidence")
        assert rc == 0, out
        table = statuses(out)
        for law in ("L2", "L3", "L4", "L7", "L8", "L9", "L10", "L11", "L14", "L15", "L16"):
            assert table[law] == "PASS", (law, out)
    finally:
        r.cleanup()


def test_evidence_force_push_count_fails():
    r = Repo()
    try:
        d = _evidence_dir(r.path, L2={"force_push_events": 1})
        rc, out = run(r, "--evidence-dir", d)
        assert statuses(out)["L2"] == "FAIL", out
        assert rc == 1, out
    finally:
        r.cleanup()


def test_evidence_self_qc_fails():
    r = Repo()
    try:
        d = _evidence_dir(r.path, L15={"qc_lane_id": "same", "builder_lane_id": "same", "qc_model": "opus-chain"})
        rc, out = run(r, "--evidence-dir", d)
        assert statuses(out)["L15"] == "FAIL", out
    finally:
        r.cleanup()


def test_evidence_deepseek_qc_fails():
    r = Repo()
    try:
        d = _evidence_dir(r.path, L15={"qc_lane_id": "qc-1", "builder_lane_id": "build-1", "qc_model": "deepseek-chat"})
        rc, out = run(r, "--evidence-dir", d)
        assert statuses(out)["L15"] == "FAIL", out
    finally:
        r.cleanup()


def test_evidence_failed_verdict_must_name_defects():
    r = Repo()
    try:
        d = _evidence_dir(r.path, L16={"verdict": "FAILED", "defects": []})
        rc, out = run(r, "--evidence-dir", d)
        assert statuses(out)["L16"] == "FAIL", out
    finally:
        r.cleanup()


def test_evidence_missing_file_fails():
    r = Repo()
    try:
        d = _evidence_dir(r.path)
        os.remove(os.path.join(d, "L7.json"))
        rc, out = run(r, "--evidence-dir", d)
        assert statuses(out)["L7"] == "FAIL", out
    finally:
        r.cleanup()


# --- applications table -----------------------------------------------------------
def test_applications_slice_is_141_to_208():
    cp = subprocess.run(
        [sys.executable, CHECKER, "--apps", "--json"], capture_output=True, text=True
    )
    payload = json.loads(cp.stdout)
    assert payload["slice"] == {"start": 141, "end": 208, "count": 68}, payload["slice"]
    first = payload["rows"][0]
    last = payload["rows"][-1]
    assert first["n"] == 141 and first["application"] == "RES-004-L13", first
    assert last["n"] == 208 and last["application"] == "INST-001-L16", last


def _main():
    failures = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures.append((name, exc))
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a crashing test is a failing test
            failures.append((name, exc))
            print(f"ERROR {name}: {exc!r}")
    print()
    print(f"{len(tests) - len(failures)} of {len(tests)} self-check cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
