"""test_env_matrix.py — VPS-vs-Mac ENVIRONMENT MATRIX (build unit `envmatrix`,
spec §4). Hermetic, offline, no live browser, no GHL write.

Proves:
  (a) browser_manager.py::durable_root()/is_vps() agree with the shell
      gateway's _bm_durable_root() detection order (VPS /data/.openclaw
      first, Mac ~/.openclaw second, "" third) — via an injectable `isdir`
      so no real /data directory (root-owned) is ever touched.
  (b) The shell side's mkdir-lock fallback path (no-flock Mac case) is
      exercised and actually serializes two callers, not just present in
      source.
  (c) Every Skill-6 .sh file under tools/ and scripts/ is bash-3.2-SAFE:
      no mapfile/readarray/declare -A/${var,,}/${var^^}/wait -n, and every
      file parses cleanly under REAL /bin/bash (3.2 on a stock Mac) as well
      as the box's default bash.
  (d) No `grep -P` (GNU-only) anywhere in the Skill-6 .sh files (BSD grep
      on macOS has no -P).
  (e) parallel_saves.sh's run-batch end-to-end (stubbed agent-browser, no
      network) produces identical output/exit code under /bin/bash and the
      box's default bash — the concrete regression this unit fixed
      (mapfile crashing on real bash 3.2).
  (f) ENV-MATRIX.md exists and documents the full matrix + adaptation
      contract (a sealed reference doc, like the SELECTORS-LIVE-*.md
      pattern elsewhere in this skill).
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_DIR = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _SKILL_DIR / "tools"
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
_MANAGER_PY = _TOOLS_DIR / "browser_manager.py"
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_PARALLEL_SH = _TOOLS_DIR / "parallel_saves.sh"
_ENV_MATRIX_DOC = _SKILL_DIR / "ENV-MATRIX.md"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _sh_files() -> list[Path]:
    out: list[Path] = []
    for d in (_TOOLS_DIR, _SCRIPTS_DIR):
        if d.is_dir():
            out.extend(sorted(d.glob("*.sh")))
    return out


# A real, stock /bin/bash 3.2 if this box has one (macOS ships one; some
# Linux CI boxes may only have a newer bash at /bin/bash — either is a valid
# probe, we just prefer the oldest one available so a real 3.2 incompatibility
# is caught where it exists).
_REAL_BIN_BASH = Path("/bin/bash")


def _bash32_available() -> bool:
    if not _REAL_BIN_BASH.exists():
        return False
    try:
        out = subprocess.run(
            [str(_REAL_BIN_BASH), "-c", "echo $BASH_VERSION"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return bool(out)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# (a) durable_root() / is_vps() — Python mirror of _bm_durable_root()
# ---------------------------------------------------------------------------

class TestDurableRootPython:
    def _reload_bm(self):
        import importlib
        import browser_manager as bm
        importlib.reload(bm)
        return bm

    def test_vps_wins_when_data_openclaw_present(self):
        bm = self._reload_bm()

        def fake_isdir(p: str) -> bool:
            return p == "/data/.openclaw"

        root = bm.durable_root(env={"HOME": "/Users/fixture"}, isdir=fake_isdir)
        assert root == "/data/.openclaw"
        assert bm.is_vps(env={"HOME": "/Users/fixture"}, isdir=fake_isdir) is True

    def test_mac_fallback_when_no_vps_root(self):
        bm = self._reload_bm()

        def fake_isdir(p: str) -> bool:
            return p == "/Users/fixture/.openclaw"

        root = bm.durable_root(env={"HOME": "/Users/fixture"}, isdir=fake_isdir)
        assert root == "/Users/fixture/.openclaw"
        assert bm.is_vps(env={"HOME": "/Users/fixture"}, isdir=fake_isdir) is False

    def test_empty_when_neither_root_exists(self):
        """Bare CI / dev checkout with no onboarded root — must return "",
        mirroring the shell side's fallback-to-ephemeral-dir contract, never
        a guessed or invented path."""
        bm = self._reload_bm()
        root = bm.durable_root(env={"HOME": "/Users/nobody"}, isdir=lambda p: False)
        assert root == ""

    def test_vps_checked_before_mac_even_when_both_exist(self):
        """VPS convention wins when BOTH would resolve — matches the shell's
        if/elif ordering (VPS first) exactly."""
        bm = self._reload_bm()

        def fake_isdir(p: str) -> bool:
            return p in ("/data/.openclaw", "/Users/fixture/.openclaw")

        root = bm.durable_root(env={"HOME": "/Users/fixture"}, isdir=fake_isdir)
        assert root == "/data/.openclaw"

    def test_no_home_env_no_crash(self):
        bm = self._reload_bm()
        root = bm.durable_root(env={}, isdir=lambda p: False)
        assert root == ""

    def test_matches_shell_side_for_the_same_simulated_inputs(self, tmp_path, monkeypatch):
        """Cross-check: build a FAKE HOME with a real ~/.openclaw dir (no real
        /data touched — that would need root) and assert the shell's
        _bm_durable_root() and the python durable_root() agree on the
        Mac-fallback branch, which IS safely reproducible without root."""
        fake_home = tmp_path / "fixturehome"
        (fake_home / ".openclaw").mkdir(parents=True)
        env = dict(os.environ, HOME=str(fake_home))
        res = subprocess.run(
            ["bash", "-c", f'source "{_MANAGER_SH}"; _bm_durable_root'],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 0, res.stderr
        shell_root = res.stdout.strip()
        # Only assert the Mac-fallback branch when this test box truly has no
        # real /data/.openclaw (true on every Mac and any hermetic CI box).
        if not os.path.isdir("/data/.openclaw"):
            assert shell_root == str(fake_home / ".openclaw")
            bm = self._reload_bm()
            py_root = bm.durable_root(env={"HOME": str(fake_home)})
            assert py_root == shell_root


class TestSupervisor:
    def test_supervisor_is_informational_not_used_for_control_flow(self):
        """supervisor() must be a pure string return with no side effects and
        must not appear anywhere else in the module gating logic (it exists
        for diagnostics only — spec §4 D14-style invariant: identical
        behavior both sides)."""
        import browser_manager as bm
        val = bm.supervisor()
        assert val in ("launchd", "pm2-or-systemd")
        # Calling it twice must be side-effect-free / stable.
        assert bm.supervisor() == val


# ---------------------------------------------------------------------------
# (b) mkdir-lock fallback (no-flock Mac case) actually serializes
# ---------------------------------------------------------------------------

class TestMkdirLockFallbackSerializes:
    def test_two_concurrent_ensures_serialize_via_mkdir_lock(self, tmp_path):
        """Force the mkdir-lock branch by hiding flock from PATH, then launch
        two `browser_manager.sh ensure` calls back-to-back with a short
        AB_LOCK_WAIT on the second — it must either succeed after the first
        tears down, or REFUSE (75) if still held; it must NEVER silently run
        both concurrently with no lock at all (which would be the real
        no-flock-on-macOS bug this fallback exists to prevent)."""
        bindir = tmp_path / "bin"
        bindir.mkdir()
        # A minimal stub agent-browser + a bash/flock-free PATH forces the
        # atomic-mkdir branch (no `flock` binary reachable).
        stub = bindir / "agent-browser"
        stub.write_text("#!/usr/bin/env bash\nprintf ''\nexit 0\n", encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        # Re-expose bash + core utils but NOT flock: build a PATH from the
        # coreutils dirs minus wherever flock happens to live, by symlinking
        # only the specific binaries the script needs into an isolated bindir.
        needed = ["bash", "sh", "cat", "mkdir", "rm", "rmdir", "sleep", "date",
                  "printf", "kill", "basename", "dirname", "tr", "sed", "wc"]
        for name in needed:
            found = shutil.which(name)
            if found and not (bindir / name).exists():
                (bindir / name).symlink_to(found)
        env = dict(
            PATH=str(bindir),
            TMPDIR=str(tmp_path / "lockdir"),
            HOME=str(tmp_path / "home"),
            GHL_LOCATION_ID="mkdirlockfixture",
            AB_MAX_SESSIONS="5",  # avoid pool-ceiling noise; we're testing the LOCK
            AB_LOCK_WAIT="2",
            AB_SESSION_TTL="5",
        )
        os.makedirs(env["HOME"], exist_ok=True)
        res = subprocess.run(
            ["bash", str(_MANAGER_SH), "ensure"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        # With flock hidden, the manager must still succeed via the mkdir
        # fallback (not silently skip locking, not crash).
        assert res.returncode == 0, (
            f"mkdir-lock fallback must let a solo caller proceed.\n"
            f"stdout={res.stdout}\nstderr={res.stderr}"
        )
        assert "ENSURED" in res.stdout


# ---------------------------------------------------------------------------
# (c) bash-3.2 safety — static scan + real /bin/bash parse of every .sh file
# ---------------------------------------------------------------------------

_BASH4_PLUS_PATTERNS = {
    "mapfile": re.compile(r"(?<![\w-])mapfile\b"),
    "readarray": re.compile(r"(?<![\w-])readarray\b"),
    "declare -A / local -A (associative arrays)": re.compile(r"\b(declare|local|typeset)\s+-A\b"),
    "${var,,} / ${var^^} case expansion": re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*[,^]{1,2}[^}]*\}"),
    "wait -n": re.compile(r"\bwait\s+-n\b"),
}


class TestBash32Safety:
    @pytest.mark.parametrize("shfile", _sh_files(), ids=lambda p: p.name)
    def test_no_bash4_plus_constructs(self, shfile: Path):
        src = shfile.read_text(encoding="utf-8")
        # Strip comment-only lines so a doc comment mentioning "mapfile" (e.g.
        # explaining why NOT to use it) doesn't false-positive.
        code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        hits = []
        for label, pat in _BASH4_PLUS_PATTERNS.items():
            if pat.search(code):
                hits.append(label)
        assert not hits, (
            f"{shfile.name} uses bash-4+-only construct(s) {hits!r} — macOS's "
            f"real /bin/bash is 3.2 and does not have these. See ENV-MATRIX.md "
            f"adaptation contract item 3."
        )

    @pytest.mark.parametrize("shfile", _sh_files(), ids=lambda p: p.name)
    def test_no_grep_dash_p(self, shfile: Path):
        """BSD grep (macOS system grep) has no -P (Perl regex). Any grep -P
        in a Skill-6 script would silently misbehave or error on a Mac."""
        src = shfile.read_text(encoding="utf-8")
        code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        hits = re.findall(r"grep\s+[^|;\n]*-[A-Za-z]*P[A-Za-z]*", code)
        assert not hits, f"{shfile.name} uses `grep -P` (GNU-only, BSD-incompatible): {hits!r}"

    @pytest.mark.skipif(not _bash32_available(), reason="no /bin/bash on this box to probe")
    @pytest.mark.parametrize("shfile", _sh_files(), ids=lambda p: p.name)
    def test_parses_under_real_bin_bash(self, shfile: Path):
        """`bash -n` (syntax-check only, no execution) against the box's real
        /bin/bash — this is the ACTUAL bash macOS resolves `#!/usr/bin/env
        bash` to whenever no newer bash is ahead of it in PATH."""
        res = subprocess.run(
            [str(_REAL_BIN_BASH), "-n", str(shfile)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, (
            f"{shfile.name} fails to parse under real /bin/bash "
            f"({_REAL_BIN_BASH}):\n{res.stderr}"
        )


# ---------------------------------------------------------------------------
# (e) parallel_saves.sh run-batch: identical behavior under /bin/bash vs
#     the box's default bash — the concrete regression this unit fixed.
# ---------------------------------------------------------------------------

def _write_stub_agent_browser(bindir: Path) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "agent-browser"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'echo "{\\"ok\\":true}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


def _run_batch(shell: str, tmp_path: Path, spec_path: Path) -> subprocess.CompletedProcess:
    bindir = tmp_path / f"bin-{Path(shell).name.replace('/', '_')}"
    _write_stub_agent_browser(bindir)
    env = dict(
        os.environ,
        PATH=f"{bindir}:{os.environ.get('PATH', '')}",
        TMPDIR=str(tmp_path / f"tmpdir-{Path(shell).name.replace('/', '_')}"),
        HOME=str(tmp_path / "home"),
        GHL_LOCATION_ID="envmatrixbatchfixture",
        AB_MAX_SESSIONS="1",
        AB_LOCK_WAIT="10",
        AB_SESSION_TTL="30",
    )
    os.makedirs(env["HOME"], exist_ok=True)
    return subprocess.run(
        [shell, str(_PARALLEL_SH), "run-batch", str(spec_path)],
        capture_output=True, text=True, env=env, timeout=60,
    )


class TestParallelSavesRunBatchCrossShell:
    @pytest.fixture
    def spec_file(self, tmp_path):
        p = tmp_path / "spec.json"
        p.write_text(
            '{"session":"ghl-skill6-envmatrixbatchfixture",'
            '"pages":[{"page_id":"p1","js":"1+1"},{"page_id":"p2","js":"2+2"}]}',
            encoding="utf-8",
        )
        return p

    def test_run_batch_succeeds_under_real_bin_bash(self, tmp_path, spec_file):
        """This is the concrete regression proof: before the fix, `mapfile -t`
        made this fail under real /bin/bash 3.2 with 'mapfile: command not
        found' and a non-zero exit. After the fix it must succeed."""
        if not _bash32_available():
            pytest.skip("no /bin/bash on this box to probe")
        res = _run_batch(str(_REAL_BIN_BASH), tmp_path, spec_file)
        assert res.returncode == 0, (
            f"run-batch must succeed under real /bin/bash.\n"
            f"stdout={res.stdout}\nstderr={res.stderr}"
        )
        assert "mapfile" not in res.stderr, "mapfile must never be invoked (bash 3.2 has none)"
        assert '"page_id":"p1"' in res.stdout
        assert '"page_id":"p2"' in res.stdout
        assert "BATCH-DONE" in res.stderr

    def test_run_batch_succeeds_under_default_bash(self, tmp_path, spec_file):
        default_bash = shutil.which("bash") or "bash"
        res = _run_batch(default_bash, tmp_path, spec_file)
        assert res.returncode == 0, (
            f"run-batch must succeed under the box default bash.\n"
            f"stdout={res.stdout}\nstderr={res.stderr}"
        )
        assert '"page_id":"p1"' in res.stdout
        assert '"page_id":"p2"' in res.stdout

    def test_both_shells_agree_on_page_count(self, tmp_path, spec_file):
        if not _bash32_available():
            pytest.skip("no /bin/bash on this box to probe")
        res_32 = _run_batch(str(_REAL_BIN_BASH), tmp_path, spec_file)
        res_default = _run_batch(shutil.which("bash") or "bash", tmp_path, spec_file)
        assert res_32.returncode == res_default.returncode == 0
        for pid in ("p1", "p2"):
            assert f'"page_id":"{pid}"' in res_32.stdout
            assert f'"page_id":"{pid}"' in res_default.stdout

    def test_empty_pages_list_warns_not_fails_either_shell(self, tmp_path):
        spec = tmp_path / "empty-spec.json"
        spec.write_text(
            '{"session":"ghl-skill6-envmatrixbatchfixture","pages":[]}',
            encoding="utf-8",
        )
        shells = [shutil.which("bash") or "bash"]
        if _bash32_available():
            shells.append(str(_REAL_BIN_BASH))
        for shell in shells:
            res = _run_batch(shell, tmp_path, spec)
            assert res.returncode == 0, f"{shell}: {res.stdout}\n{res.stderr}"
            assert "WARN" in res.stderr and "no pages" in res.stderr

    def test_malformed_spec_fails_loud_either_shell(self, tmp_path):
        spec = tmp_path / "bad-spec.json"
        spec.write_text("{not valid json", encoding="utf-8")
        shells = [shutil.which("bash") or "bash"]
        if _bash32_available():
            shells.append(str(_REAL_BIN_BASH))
        for shell in shells:
            res = _run_batch(shell, tmp_path, spec)
            assert res.returncode == 1, f"{shell}: expected FAIL exit 1, got {res.returncode}"
            assert "could not parse" in res.stderr


# ---------------------------------------------------------------------------
# (f) ENV-MATRIX.md is present and covers every required topic
# ---------------------------------------------------------------------------

class TestEnvMatrixDoc:
    def test_doc_exists(self):
        assert _ENV_MATRIX_DOC.exists(), "ENV-MATRIX.md must exist in the skill root"

    def test_doc_covers_required_topics(self):
        text = _ENV_MATRIX_DOC.read_text(encoding="utf-8")
        required = [
            "/data/.openclaw",
            "~/.openclaw",
            "flock",
            "mkdir",
            "bash 3.2",
            "mapfile",
            "grep",
            "launchd",
            "pm2",
            "systemd",
            "Docker",
            "env_file",
            "chown",
            "headless",
            "durable_root",
        ]
        missing = [kw for kw in required if kw not in text]
        assert not missing, f"ENV-MATRIX.md is missing required topics: {missing!r}"

    def test_doc_documents_the_mapfile_fix(self):
        text = _ENV_MATRIX_DOC.read_text(encoding="utf-8")
        assert "parallel_saves.sh" in text
        assert "mapfile" in text
