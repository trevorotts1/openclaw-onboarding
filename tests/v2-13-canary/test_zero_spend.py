#!/usr/bin/env python3
"""Zero-spend proof: no network client, no paid call, live entrypoint refused.

Runs standalone (python3 test_zero_spend.py) and under pytest.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import unittest.mock

import mock_harness as mh

HERE = pathlib.Path(__file__).resolve().parent
SOURCES = ("mock_harness.py", "run_canary.py")
BANNED_ROOTS = {
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "ftplib",
    "telnetlib",
    "smtplib",
}


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_network_client_is_imported_by_the_harness():
    for name in SOURCES:
        found = _imported_roots(HERE / name) & BANNED_ROOTS
        assert not found, f"{name} imports a network client: {sorted(found)}"


def test_both_paths_run_with_sockets_blocked():
    spec = mh.load_spec()
    shot = mh.load_fixture("shot_painful_moment.json")
    with unittest.mock.patch("socket.socket", side_effect=AssertionError("socket used")):
        primary = mh.run_path(spec, shot, mh.PRIMARY_OK)
        fallback = mh.run_path(spec, shot, mh.FALLBACK)
    assert primary["paid_calls"] == 0 and primary["spend_usd"] == 0.0
    assert fallback["paid_calls"] == 0 and fallback["spend_usd"] == 0.0
    assert primary["dispatch_order"] == [mh.ROSTER[0]]
    assert fallback["dispatch_order"] == [mh.ROSTER[0], mh.ROSTER[1]]


def test_run_canary_driver_writes_a_zero_spend_report():
    out_dir = HERE / "outcomes"
    rc = run_canary_main([])
    assert rc == 0, rc
    import json

    report = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert report["paid_calls"] == 0
    assert report["spend_usd"] == 0.0
    assert report["mode"] == "mock"
    assert report["providers"] == list(mh.ROSTER)
    assert len(report["runs"]) == 3


def test_live_mode_is_refused():
    try:
        mh.run_live()
    except mh.LiveCallRefused:
        pass
    else:
        raise AssertionError("run_live did not refuse")


def test_live_cli_flag_exits_refused():
    proc = subprocess.run(
        [sys.executable, str(HERE / "run_canary.py"), "--live"],
        capture_output=True,
        text=True,
        cwd=str(HERE),
        check=False,
    )
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "live-refused" in proc.stderr


def test_spec_spend_block_is_zero():
    spend = mh.load_spec()["spend"]
    assert spend["allowed"] is False
    assert float(spend["ceiling_usd"]) == 0.0
    assert int(spend["paid_calls"]) == 0


def run_canary_main(argv):
    import run_canary

    return run_canary.main(argv)


if __name__ == "__main__":
    failures = []
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    for name in names:
        fn = globals()[name]
        if not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report then fail
            failures.append(name)
            print(f"FAIL {name}: {exc}")
    print(f"total={len(names)} failed={len(failures)}")
    raise SystemExit(1 if failures else 0)
