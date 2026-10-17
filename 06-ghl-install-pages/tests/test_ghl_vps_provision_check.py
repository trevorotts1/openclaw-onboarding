"""S06-05 — the VPS provisioning verifier (tools/ghl_vps_provision_check.py).

Hermetic: every verdict is driven by injected stat / mount-table / UID
fixtures, apart from the planted-content test (real tmp files) and the
one advisory CLI test, which asserts only the advisory contract (exit 0,
WARN-prefixed lines, nothing written). NO real secret is read and NO
network is touched. The verifier's no-secret-value guarantee is
STRUCTURAL — the module only ever stats its targets and never opens one
for reading (verified by firsthand code read, Checkpoint-1 pre-review);
the planted-content test in this file pins the observable half of that
property: real value-shaped content sitting at a *_FILE target and in a
store never surfaces in a receipt, a finding line, or a written receipt
file.

The Q1 split under test (delta-check C1): the shared resolver owns the
READ-TIME refusal; this verifier owns the PROVISIONING verdicts
(existence, owner UID vs service UID, runs-as-root, directory modes,
mount classification, storage label). Every repair it emits NARROWS
access — a repair that widens a mode is a defect these tests hunt for.
"""
from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import browser_manager as bm  # noqa: E402
import ghl_vps_provision_check as vpc  # noqa: E402

FakeStat = collections.namedtuple(
    "FakeStat", ["st_mode", "st_uid", "st_gid", "st_size"])

BOX = {"durable_root": "/data/.openclaw", "is_vps": True,
       "supervisor": "pm2-or-systemd", "platform": "linux"}

BASE_PATHS = {
    "agent_browser_state": "/home/node/.agent-browser",
    "evidence_base": "",
    "run_state_root": "/data/.openclaw/skill6-runs",
    "playwright_data_dir": "/data/.openclaw/playwright-data/ghl-install-pages",
    "secrets_dir": "/home/node/.openclaw/secrets",
}

REFRESH = "/run/secrets/refresh-token"
PIT = "/run/secrets/location-pit"
LOCID = "/run/secrets/location-id"
STORE = "/home/node/.openclaw/secrets/.env"


def reader_for(table):
    def _read(path):
        if path not in table:
            raise FileNotFoundError(path)
        return table[path]
    return _read


def mounts_ext4():
    return [("/dev/vda1", "/", "ext4", "rw,relatime")]


def mounts_overlay():
    return [("overlay", "/", "overlay", "rw,relatime")]


def good_table():
    return {
        REFRESH: FakeStat(0o100600, 1000, 1000, 64),
        PIT: FakeStat(0o100600, 1000, 1000, 64),
        LOCID: FakeStat(0o100600, 1000, 1000, 20),
        "/run/secrets": FakeStat(0o40700, 1000, 1000, 0),
        STORE: FakeStat(0o100600, 1000, 1000, 128),
        "/home/node/.openclaw/secrets": FakeStat(0o40700, 1000, 1000, 0),
    }


def run_verifier(table=None, env=None, mounts=mounts_ext4, **kw):
    kw.setdefault("client", "fixtureloc")
    kw.setdefault("paths", dict(BASE_PATHS))
    kw.setdefault("stores", [STORE])
    kw.setdefault("service_uid", 1000)
    kw.setdefault("service_gid", 1000)
    kw.setdefault("stat_reader", reader_for(table if table is not None
                                            else good_table()))
    kw.setdefault("mounts_reader", mounts)
    kw.setdefault("platform", "linux")
    kw.setdefault("box", dict(BOX))
    return vpc.verify_provisioning(env=env or {}, **kw)


def row_of(receipt, name):
    rows = [r for r in receipt["rows"] if r["name"] == name]
    assert rows, f"no row named {name!r} in {[r['name'] for r in receipt['rows']]}"
    return rows[0]


def assert_no_widening_repair(receipt):
    """The Q1 invariant: a repair may only ever NARROW (chmod 600/700) or
    chown. Any chmod to a mode with group/other bits is a widening repair
    and fails this test wherever it appears."""
    for r in receipt["rows"]:
        for mode in re.findall(r"chmod\s+([0-7]{3,4})", r.get("repair", "")):
            assert mode[-3:] in ("600", "700"), (
                f"widening repair in row {r['name']}: {r['repair']}")


# ── happy path + value hygiene ──────────────────────────────────────────────

def test_happy_path_ok_and_receipt_carries_no_values():
    env = {"GHL_REFRESH_TOKEN_FILE": REFRESH,
           "GHL_LOCATION_PIT_FILE": PIT,
           "GHL_LOCATION_ID_FILE": LOCID}
    receipt = run_verifier(env=env)
    assert receipt["ok"] is True, receipt["rows"]
    assert receipt["errors"] == 0
    assert receipt["schema"] == "skill6-vps-provisioning/1"
    assert receipt["storage_label"] == "permission-protected plaintext"
    # Tripwire over the receipt shape only: a value-shaped string that is
    # not an input to anything must not materialise in the receipt. The
    # planted-content proof is test_planted_secret_content_never_surfaces
    # below; the guarantee itself is structural (the verifier stats its
    # targets, it never reads them — see the module docstring).
    blob = json.dumps(receipt)
    assert "FIXTURE-SECRET-VALUE" not in blob
    for var in ("GHL_REFRESH_TOKEN_FILE", "GHL_LOCATION_PIT_FILE",
                "GHL_LOCATION_ID_FILE"):
        assert row_of(receipt, var)["status"] == "PASS"
    assert_no_widening_repair(receipt)


def test_planted_secret_content_never_surfaces(tmp_path):
    """D-P2 cure: REAL value-shaped content sits at the *_FILE target and
    in the fixture store, on real tmp paths — exactly where a
    content-reading implementation would pick it up and leak it. The
    verifier stats only, so the planted content must appear NOWHERE: not
    in the receipt JSON, not in any finding line, and not in the receipt
    file a full run writes. (An earlier form of this check asserted the
    absence of a string that was never an input to anything; that proved
    nothing. This one can fail.)"""
    sentinel = "PLANTED-FIXTURE-SECRET-9f3b7d"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    target = secret_dir / "refresh-token"
    target.write_text(sentinel + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    store = secret_dir / "store.env"
    store.write_text(f"GHL_REFRESH_TOKEN={sentinel}\n", encoding="utf-8")
    os.chmod(store, 0o600)
    os.chmod(secret_dir, 0o700)
    uid, gid = os.getuid(), os.getegid()
    paths = dict(BASE_PATHS)
    paths["secrets_dir"] = str(secret_dir)
    durable = tmp_path / "durable"
    receipt = vpc.verify_provisioning(
        client="fixtureloc",
        env={"GHL_REFRESH_TOKEN_FILE": str(target)},
        paths=paths, stores=[str(store)],
        service_uid=uid, service_gid=gid,
        stat_reader=os.stat, mounts_reader=mounts_ext4,
        platform="linux",
        box={"durable_root": str(durable), "is_vps": True,
             "supervisor": "pm2-or-systemd", "platform": "linux"})
    # The planted files are well-provisioned (0600/0700, service-owned,
    # persistent mount), so their rows PASS — the content was there to be
    # leaked and the verdicts were still reached by stat alone.
    assert row_of(receipt, "GHL_REFRESH_TOKEN_FILE")["status"] == "PASS"
    assert row_of(receipt, f"store:{store}")["status"] == "PASS"
    assert sentinel not in json.dumps(receipt)
    for line in vpc.finding_lines(receipt):
        assert sentinel not in line
    written = vpc.write_receipts(receipt)
    assert written, "expected the namespaced receipt under the tmp durable root"
    for path in written:
        assert sentinel not in Path(path).read_text(encoding="utf-8")


def test_all_three_file_vars_are_checked():
    # Delta C3: the location-ID file is held to the same refusal as the
    # two secret files, so all three names must produce rows.
    env = {"GHL_REFRESH_TOKEN_FILE": REFRESH,
           "GHL_LOCATION_PIT_FILE": PIT,
           "GHL_LOCATION_ID_FILE": LOCID}
    receipt = run_verifier(env=env)
    names = {r["name"] for r in receipt["rows"]}
    assert {"GHL_REFRESH_TOKEN_FILE", "GHL_LOCATION_PIT_FILE",
            "GHL_LOCATION_ID_FILE"} <= names


# ── the *_FILE verdicts ─────────────────────────────────────────────────────

def test_group_other_readable_is_error_with_narrowing_repair():
    table = good_table()
    table[REFRESH] = FakeStat(0o100644, 1000, 1000, 64)
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert "chmod 600" in row["repair"]
    assert receipt["ok"] is False
    assert_no_widening_repair(receipt)


def test_owner_mismatch_errors_with_chown_never_a_widening_chmod():
    table = good_table()
    table[REFRESH] = FakeStat(0o100600, 999, 999, 64)  # owned by uid 999
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert "chown 1000" in row["repair"]
    assert "never widen" in row["repair"]
    assert_no_widening_repair(receipt)


def test_missing_file_target_is_a_named_error():
    receipt = run_verifier(table={},
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert "GHL_REFRESH_TOKEN_FILE" in row["detail"]
    assert REFRESH in row["detail"]
    assert "does not exist" in row["detail"]


def test_empty_file_target_is_an_error():
    table = good_table()
    table[REFRESH] = FakeStat(0o100600, 1000, 1000, 0)
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert "empty" in row["detail"]


def test_file_target_on_ephemeral_mount_is_an_error():
    receipt = run_verifier(env={"GHL_REFRESH_TOKEN_FILE": REFRESH},
                           mounts=mounts_overlay)
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert row["mount_type"] == "overlay"
    assert "ephemeral" in row["detail"]


def test_unset_file_vars_are_info_not_errors():
    receipt = run_verifier(env={})
    for var in ("GHL_REFRESH_TOKEN_FILE", "GHL_LOCATION_PIT_FILE",
                "GHL_LOCATION_ID_FILE"):
        assert row_of(receipt, var)["status"] == "INFO"
    assert receipt["ok"] is True


# ── identity, stores, dirs, mounts ──────────────────────────────────────────

def test_service_running_as_root_is_an_error():
    receipt = run_verifier(service_uid=0, service_gid=0)
    row = row_of(receipt, "service-identity")
    assert row["status"] == "ERROR"
    assert receipt["service"]["runs_as_root"] is True
    assert receipt["ok"] is False


def test_loose_store_mode_is_an_error():
    table = good_table()
    table[STORE] = FakeStat(0o100640, 1000, 1000, 128)
    receipt = run_verifier(table=table)
    row = row_of(receipt, f"store:{STORE}")
    assert row["status"] == "ERROR"
    assert "chmod 600" in row["repair"]
    assert_no_widening_repair(receipt)


def test_store_owner_mismatch_is_a_warn_with_chown_repair():
    table = good_table()
    table[STORE] = FakeStat(0o100600, 999, 999, 128)
    receipt = run_verifier(table=table)
    row = row_of(receipt, f"store:{STORE}")
    assert row["status"] == "WARN"
    assert "chown 1000" in row["repair"]
    assert receipt["ok"] is True  # a WARN never fails the gate
    assert_no_widening_repair(receipt)


def test_loose_secret_dir_mode_is_an_error():
    table = good_table()
    table["/run/secrets"] = FakeStat(0o40755, 1000, 1000, 0)
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "dir:/run/secrets")
    assert row["status"] == "ERROR"
    assert "chmod 700" in row["repair"]
    assert_no_widening_repair(receipt)


def test_secret_dir_owner_mismatch_is_an_error_with_chown_repair():
    """D-P1 pin: a mode-0700 secrets directory owned by a DIFFERENT uid
    than the service must ERROR — at 0700 the service cannot traverse a
    directory it does not own — with the same narrowing chown repair the
    file check emits (never a mode widening). Before the cure,
    _check_secret_dir accepted service_uid and never compared it, so
    this exact fixture returned PASS."""
    table = good_table()
    table["/run/secrets"] = FakeStat(0o40700, 999, 999, 0)  # owner != service
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    row = row_of(receipt, "dir:/run/secrets")
    assert row["status"] == "ERROR"
    assert "chown 1000" in row["repair"]
    assert "never widen" in row["repair"]
    assert row["owner_uid"] == 999
    assert receipt["ok"] is False
    assert_no_widening_repair(receipt)


def test_ephemeral_pathset_path_is_an_error():
    receipt = run_verifier(mounts=mounts_overlay)
    row = row_of(receipt, "pathset:run_state_root")
    assert row["status"] == "ERROR"
    assert row["is_persistent"] is False
    assert "durable" in row["repair"]


def test_undeterminable_mount_table_is_reported_never_guessed():
    receipt = run_verifier(mounts=lambda: [])
    row = row_of(receipt, "pathset:run_state_root")
    assert row["status"] == "UNDETERMINABLE"
    assert row["is_persistent"] is None
    # UNDETERMINABLE is a warning, not a failure — and never a PASS.
    assert receipt["warnings"] >= 1
    assert receipt["ok"] is True


def test_operator_storage_label_overrides_the_default():
    receipt = run_verifier(storage_label="encrypted-volume (operator policy)")
    assert receipt["storage_label"] == "encrypted-volume (operator policy)"
    row = row_of(receipt, "storage-label")
    assert "operator-named" in row["detail"]


# ── receipts: namespacing, isolation, advisory ──────────────────────────────

def _receipt_for(client, durable):
    return vpc.verify_provisioning(
        client=client, env={}, paths=dict(BASE_PATHS), stores=[],
        service_uid=1000, service_gid=1000,
        stat_reader=reader_for(good_table()), mounts_reader=mounts_ext4,
        platform="linux",
        box={"durable_root": str(durable), "is_vps": True,
             "supervisor": "pm2-or-systemd", "platform": "linux"})


def test_receipts_are_namespaced_per_client(tmp_path):
    durable = tmp_path / "durable"
    ra = _receipt_for("Client A", durable)
    rb = _receipt_for("client-b", durable)
    written_a = vpc.write_receipts(ra, evidence_root=str(tmp_path / "ev-a"))
    written_b = vpc.write_receipts(rb)
    a_main = durable / "skill6-provisioning" / "client-a" / "provisioning-receipt.json"
    b_main = durable / "skill6-provisioning" / "client-b" / "provisioning-receipt.json"
    assert str(a_main) in written_a and a_main.exists()
    assert str(b_main) in written_b and b_main.exists()
    assert (tmp_path / "ev-a" / "routing" / "provisioning-receipt.json").exists()
    # Client A's receipt names client A only — no bleed from client B.
    a_text = a_main.read_text(encoding="utf-8")
    assert json.loads(a_text)["client"] == "Client A"
    assert "client-b" not in a_text
    assert json.loads(b_main.read_text(encoding="utf-8"))["client"] == "client-b"


def test_finding_lines_cover_only_non_pass_rows():
    table = good_table()
    table[REFRESH] = FakeStat(0o100644, 1000, 1000, 64)
    receipt = run_verifier(table=table,
                           env={"GHL_REFRESH_TOKEN_FILE": REFRESH})
    lines = vpc.finding_lines(receipt)
    assert lines, "a failing receipt must produce advisory lines"
    for line in lines:
        assert line.startswith("WARN (provision preflight, S06-05):")
    assert any("GHL_REFRESH_TOKEN_FILE" in line for line in lines)
    non_pass = [r for r in receipt["rows"] if r["status"] != "PASS"]
    assert len(lines) == len(non_pass)


def test_advisory_cli_exits_zero_and_writes_nothing():
    client = "s06-05-advisory-fixture"
    env = dict(os.environ)
    env.pop("BM_DURABLE_ROOT_OVERRIDE", None)
    proc = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "ghl_vps_provision_check.py"),
         "--client", client, "--advisory"],
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    for line in proc.stdout.splitlines():
        assert line.startswith("WARN (provision preflight, S06-05):")
    for root in (Path("/data/.openclaw"),
                 Path.home() / ".openclaw"):
        receipt = (root / "skill6-provisioning" / client
                   / "provisioning-receipt.json")
        assert not receipt.exists(), (
            f"advisory mode wrote a receipt: {receipt}")


def test_bm_provision_preflight_opt_in_and_override_deferral():
    """The bm_ensure wiring (browser_manager.sh bm_provision_preflight,
    Checkpoint-1 item 5): a silent no-op unless GHL_VPS_PROVISION_CLIENT
    is set, and fully deferred while BM_DURABLE_ROOT_OVERRIDE is set
    (the gap-14 test-isolation rule). Both paths exit 0 and print
    nothing; the advisory path itself is pinned by the CLI test above.
    Uses the suite-proven source-and-call shape (test_env_matrix.py)."""
    script = str(_TOOLS_DIR / "browser_manager.sh")
    base_env = {k: v for k, v in os.environ.items()
                if k not in ("GHL_VPS_PROVISION_CLIENT",
                             "BM_DURABLE_ROOT_OVERRIDE")}
    res = subprocess.run(
        ["bash", "-c", f'source "{script}"; bm_provision_preflight'],
        capture_output=True, text=True, env=base_env, timeout=60)
    assert res.returncode == 0, res.stderr
    assert res.stdout == "" and res.stderr == ""
    env = dict(base_env, GHL_VPS_PROVISION_CLIENT="fixtureloc",
               BM_DURABLE_ROOT_OVERRIDE="/tmp/s06-05-override-fixture")
    res = subprocess.run(
        ["bash", "-c", f'source "{script}"; bm_provision_preflight'],
        capture_output=True, text=True, env=env, timeout=60)
    assert res.returncode == 0, res.stderr
    assert res.stdout == "" and res.stderr == ""


# ── complement: stale-env preflight vs the verifier ─────────────────────────

def test_stale_env_silent_while_verifier_errors_on_overlay_secret():
    """The two preflights are complementary, not redundant. Scenario: the
    host .env is OLDER than the container start (so the stale-env check is
    correctly silent — nothing is stale) while the refresh-token FILE sits
    on an ephemeral overlay mount (a provisioning fault the stale-env
    check cannot see). The verifier must ERROR on exactly that."""
    started = datetime(2026, 10, 16, 12, 0, 0,
                       tzinfo=timezone.utc).timestamp()
    common = dict(
        container="fixture-box",
        env_path="/host/project/.env",
        env={"GHL_DOCKER_CONTAINER": "fixture-box"},
        inspect_fn=lambda c: "2026-10-16T12:00:00.000000000Z",
        isvps_fn=lambda: True,
    )
    # Positive control: a NEWER env file DOES trip the stale-env warning,
    # so the silence below is a verdict, not a broken fixture.
    assert bm.stale_env_preflight(mtime_fn=lambda p: started + 3600,
                                  **common) is not None
    # Fresh env (older than the container start): silent.
    assert bm.stale_env_preflight(mtime_fn=lambda p: started - 3600,
                                  **common) is None
    # Same box: the verifier errors on the overlay-backed secret file.
    receipt = run_verifier(env={"GHL_REFRESH_TOKEN_FILE": REFRESH},
                           mounts=mounts_overlay)
    row = row_of(receipt, "GHL_REFRESH_TOKEN_FILE")
    assert row["status"] == "ERROR"
    assert row["mount_type"] == "overlay"


# ── remaining verdict branches (pre-review Q4 smaller gaps) ─────────────────

def test_empty_durable_root_is_an_error():
    receipt = run_verifier(box={"durable_root": "", "is_vps": True,
                                "supervisor": "pm2-or-systemd",
                                "platform": "linux"})
    row = row_of(receipt, "durable-root")
    assert row["status"] == "ERROR"
    assert receipt["ok"] is False


def test_store_on_ephemeral_mount_is_an_error():
    receipt = run_verifier(mounts=mounts_overlay)
    row = row_of(receipt, f"store:{STORE}")
    assert row["status"] == "ERROR"
    assert "ephemeral" in row["detail"]
    assert row["is_persistent"] is False


# ── CLI exit codes, exercised AS exit codes (pre-review Q4) ─────────────────

def _canned_receipt(ok):
    return {
        "schema": vpc.PROVISION_SCHEMA,
        "ts": "2026-10-16T00:00:00Z",
        "client": "fixtureloc",
        "box": {"durable_root": ""},
        "service": {"uid": 1000, "gid": 1000, "runs_as_root": False},
        "storage_label": vpc.DEFAULT_STORAGE_LABEL,
        "rows": [],
        "errors": 0 if ok else 1,
        "warnings": 0,
        "ok": ok,
    }


def _stub_main(monkeypatch, ok):
    """Drive vpc.main() hermetically: the receipt is canned and the
    receipt write is stubbed out, so what is pinned is main()'s own
    exit-code mapping, nothing else."""
    monkeypatch.setattr(vpc, "verify_provisioning",
                        lambda **kw: _canned_receipt(ok))
    monkeypatch.setattr(vpc, "write_receipts",
                        lambda receipt, evidence_root="": [])


def test_cli_full_mode_exits_zero_on_a_clean_receipt(monkeypatch):
    _stub_main(monkeypatch, ok=True)
    assert vpc.main(["--client", "fixtureloc"]) == 0


def test_cli_full_mode_exits_one_on_an_error_receipt(monkeypatch):
    _stub_main(monkeypatch, ok=False)
    assert vpc.main(["--client", "fixtureloc"]) == 1


def test_cli_missing_client_is_usage_error_exit_two():
    # argparse's error path: --client is required unless --selftest.
    with pytest.raises(SystemExit) as excinfo:
        vpc.main([])
    assert excinfo.value.code == 2
