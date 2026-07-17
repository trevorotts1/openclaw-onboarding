"""U28 (B-U14) acceptance criterion (d) — hermetic proof of the ZERO-ORPHAN
descriptor-audit tool's matching logic (tools/agent_browser_orphan_audit.py).

This proves the DETECTOR is correct: a fresh descriptor survives, a leased
descriptor survives regardless of age, an aged UNLEASED descriptor with no
matching process is flagged an ORPHAN, and a scoped-Chromium-alive descriptor
is treated conservatively as live (mirrors the reaper's own
never-kill-if-any-lease-alive conservatism). The genuinely LIVE leg — running
this ten minutes after a real Skill-6 fixture build against a real,
operator-authorized GHL test location — is logged as owed in the U28 ledger
note; it needs real GHL credentials this repo-side test suite must not
fabricate.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_TESTS_DIR = Path(__file__).parent.resolve()
_TOOLS_DIR = (_TESTS_DIR.parent / "tools").resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import agent_browser_orphan_audit as oad  # noqa: E402


def _touch(path: Path, *, age_sec: float = 0.0, size: int = 128) -> None:
    path.write_bytes(b"x" * size)
    ts = time.time() - age_sec
    os.utime(path, (ts, ts))


def _write_lease(path: Path, *, started_ago_sec: float = 0.0, ttl_sec: int = 1800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"started_epoch": int(time.time() - started_ago_sec), "ttl_sec": ttl_sec}),
        encoding="utf-8",
    )


class TestOrphanDescriptorAudit:
    def test_fresh_descriptor_within_grace_window_is_not_orphaned(self, tmp_path):
        home = tmp_path / "home"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "fresh-session.engine", age_sec=5)

        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp_path / "tmp"), grace_sec=600,
            now=time.time(), ps_output_provider=lambda: "",
        )
        assert result["ok"] is True
        assert result["orphans"] == []
        assert result["total_descriptors"] == 1

    def test_leased_descriptor_never_orphaned_regardless_of_age(self, tmp_path):
        home = tmp_path / "home"
        tmp = tmp_path / "tmp"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "leased-session.engine", age_sec=99999)
        _write_lease(tmp / "agent-browser" / "leases" / "leased-session.lease",
                    started_ago_sec=100, ttl_sec=999999)

        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp), grace_sec=600,
            now=time.time(), ps_output_provider=lambda: "",
        )
        assert result["ok"] is True
        assert result["orphans"] == []
        assert result["live"][0]["session"] == "leased-session"
        assert "lease" in result["live"][0]["reason"]

    def test_expired_lease_unleased_descriptor_no_process_is_orphan(self, tmp_path):
        home = tmp_path / "home"
        tmp = tmp_path / "tmp"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "abandoned-session.engine", age_sec=99999)
        # An EXPIRED lease (started long ago, short ttl) must NOT count as live.
        _write_lease(tmp / "agent-browser" / "leases" / "abandoned-session.lease",
                    started_ago_sec=99999, ttl_sec=60)

        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp), grace_sec=600,
            now=time.time(), ps_output_provider=lambda: "",
        )
        assert result["ok"] is False
        assert result["orphans"] == [{"session": "abandoned-session", "age_sec": result["orphans"][0]["age_sec"]}]
        assert result["orphans"][0]["session"] == "abandoned-session"

    def test_scoped_chromium_alive_treated_conservatively_as_live(self, tmp_path):
        home = tmp_path / "home"
        tmp = tmp_path / "tmp"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "maybe-owned-session.engine", age_sec=99999)
        fake_ps = (
            f"12345 /Applications/Chromium.app/Contents/MacOS/Chromium "
            f"--user-data-dir={home}/.agent-browser/profile --headless\n"
        )

        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp), grace_sec=600,
            now=time.time(), ps_output_provider=lambda: fake_ps,
        )
        assert result["ok"] is True
        assert result["orphans"] == []

    def test_bare_chrome_process_never_counts_as_scoped(self, tmp_path):
        """The operator's own Google Chrome.app / Claude.app must NEVER make
        an unrelated orphan look live — the SAME safety invariant the reaper
        itself enforces (never match a bare chrome/Chrome/Claude name)."""
        home = tmp_path / "home"
        tmp = tmp_path / "tmp"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "truly-abandoned.engine", age_sec=99999)
        fake_ps = (
            "555 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome "
            "--type=renderer --profile-directory=Default\n"
            "556 /Applications/Claude.app/Contents/MacOS/Claude\n"
        )

        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp), grace_sec=600,
            now=time.time(), ps_output_provider=lambda: fake_ps,
        )
        assert result["ok"] is False
        assert result["orphans"][0]["session"] == "truly-abandoned"

    def test_no_descriptors_is_trivially_ok(self, tmp_path):
        home = tmp_path / "home"
        (home / ".agent-browser").mkdir(parents=True)
        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp_path / "tmp"),
            now=time.time(), ps_output_provider=lambda: "",
        )
        assert result["ok"] is True
        assert result["total_descriptors"] == 0

    def test_missing_engine_dir_is_trivially_ok(self, tmp_path):
        home = tmp_path / "home-never-onboarded"
        result = oad.find_orphans(
            home=str(home), tmpdir=str(tmp_path / "tmp"),
            now=time.time(), ps_output_provider=lambda: "",
        )
        assert result["ok"] is True
        assert result["total_descriptors"] == 0

    def test_cli_check_mode_exit_code_matches_ok(self, tmp_path, monkeypatch, capsys):
        home = tmp_path / "home"
        (home / ".agent-browser").mkdir(parents=True)
        _touch(home / ".agent-browser" / "fresh.engine", age_sec=1)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
        rc = oad.main(["--check"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
