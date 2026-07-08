#!/usr/bin/env python3
"""
test_guard_department_runtime_parity.py — regression guard for
guard-department-runtime-parity.py.

THE BUG THIS GUARD PROTECTS AGAINST (confirmed by direct code audit,
2026-07-08): run-full-install.sh Phase 4's only safety check was a blunt
TOTAL COUNT floor (`AGENT_COUNT -lt 2`) over openclaw.json's agents.list[].
That check passes as long as ANY two agents exist anywhere in agents.list[] —
it never verifies that EVERY individual department seeded onto the board (a
`workspaces` row in mission-control.db) has its OWN matching runtime entry.
If N-2 departments wire correctly and 2 silently don't, the blunt floor still
passes and those 2 departments get a full board row with ZERO working
runtime — the exact `no_specialist_runtime` failure class documented in
blackceo-command-center's resolveSpecialistSessionKey().

WHAT THIS FILE PROVES:
    1. A hermetic mocked mission-control.db with N departments + a mocked
       openclaw.json missing the runtime for exactly 1 of them: the guard
       catches EXACTLY that 1 department (by name) and exits non-zero
       (fail-closed) -- never a false pass, never over-reporting.
    2. A clean case where every department has a matching runtime entry:
       the guard exits 0.
    3. The slug-matching logic (candidate_variants) covers all 6 variants
       the real dispatcher (resolveSpecialistSessionKey in
       blackceo-command-center's src/lib/task-dispatcher.ts) tries, in the
       same shapes, including the canonical-alias mapping mirrored from
       shared-utils/canonical_slug.py (itself a mirror of
       src/lib/routing/canonical-slug.ts -- both sides are required to
       agree; a spot-check against known alias-map entries pins that
       agreement here).
    4. Soft-fail vs. hard-fail boundary: a missing DB / empty workspaces
       table is NOT a failure (nothing seeded yet); a DB with department
       rows but an unreadable/missing openclaw.json IS a hard failure
       (distinct exit code) -- we refuse to silently vouch for runtimes we
       cannot verify.

Run:  python3 -m pytest test_guard_department_runtime_parity.py -q
   or: python3 test_guard_department_runtime_parity.py     (no pytest required)
"""
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "guard-department-runtime-parity.py"

_spec = importlib.util.spec_from_file_location("guard_dept_parity", SCRIPT)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
candidate_variants = _guard.candidate_variants
canonical_dept_slug = _guard.canonical_dept_slug

EX_OK = 0
EX_MISMATCH = 1
EX_CONFIG_UNREADABLE = 2


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------
def _make_db(tmp, departments, with_type_column=False, with_agents_table=True):
    """departments: list of dicts {slug, name, agent_name?, agent_role?}."""
    db_path = Path(tmp) / "mission-control.db"
    conn = sqlite3.connect(db_path)
    type_col = ", type TEXT" if with_type_column else ""
    conn.executescript(f"""
        CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, slug TEXT, industry TEXT, config TEXT);
        CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT UNIQUE,
            description TEXT, icon TEXT, company_id TEXT{type_col});
    """)
    if with_agents_table:
        conn.executescript("""
            CREATE TABLE agents (id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT,
                role TEXT, is_master INTEGER DEFAULT 0);
        """)
    for i, d in enumerate(departments):
        cols = ["id", "name", "slug", "description", "icon", "company_id"]
        vals = [d["slug"], d["name"], d["slug"], "", "📁", "test-co"]
        if with_type_column:
            cols.append("type")
            vals.append(d.get("type", "department"))
        placeholders = ",".join("?" * len(cols))
        conn.execute(f"INSERT INTO workspaces ({','.join(cols)}) VALUES ({placeholders})", vals)
        if with_agents_table and (d.get("agent_name") or d.get("agent_role")):
            conn.execute(
                "INSERT INTO agents (id, workspace_id, name, role) VALUES (?, ?, ?, ?)",
                (f"ag-{i}", d["slug"], d.get("agent_name", f"{d['name']} Lead"),
                 d.get("agent_role", f"{d['name']} Department Head")),
            )
    conn.commit()
    conn.close()
    return db_path


def _make_config(tmp, agent_ids):
    config_path = Path(tmp) / "openclaw.json"
    cfg = {
        "agents": {"list": [{"id": aid, "name": aid} for aid in agent_ids]},
    }
    config_path.write_text(json.dumps(cfg, indent=2))
    return config_path


def _run(db_path=None, config_path=None, *extra):
    cmd = [sys.executable, str(SCRIPT)]
    if db_path is not None:
        cmd += ["--db", str(db_path)]
    if config_path is not None:
        cmd += ["--config", str(config_path)]
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


# --------------------------------------------------------------------------
# 1. Hermetic mismatch case: N departments, exactly 1 missing its runtime.
# --------------------------------------------------------------------------
def test_one_missing_department_fails_closed():
    depts = [
        {"slug": "marketing", "name": "Marketing"},
        {"slug": "sales", "name": "Sales"},
        {"slug": "billing-finance", "name": "Billing Finance"},
        {"slug": "graphics", "name": "Graphics"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        # Every department gets a matching dept-<slug> entry EXCEPT "graphics".
        config_path = _make_config(tmp, ["dept-marketing", "dept-sales", "dept-billing-finance"])

        res = _run(db_path, config_path)
        assert res.returncode == EX_MISMATCH, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"

        out = res.stdout + res.stderr
        assert "Graphics" in out, f"missing department name not reported:\n{out}"
        assert "1/4" in out, f"expected exactly 1 of 4 departments flagged:\n{out}"
        # The 3 correctly-wired departments must NOT be reported as mismatches.
        for clean_name in ("Marketing", "Sales", "Billing Finance"):
            assert f"! {clean_name}" not in out, f"false positive on {clean_name}:\n{out}"


# --------------------------------------------------------------------------
# 2. Clean case: every department matches -> PASS, exit 0.
# --------------------------------------------------------------------------
def test_all_departments_match_passes():
    depts = [
        {"slug": "marketing", "name": "Marketing"},
        {"slug": "sales", "name": "Sales"},
        {"slug": "graphics", "name": "Graphics"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        config_path = _make_config(tmp, ["dept-marketing", "dept-sales", "dept-graphics"])

        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"
        assert "PASS" in res.stdout
        assert "3/3" in res.stdout


def test_match_via_bare_slug_variant_passes():
    """A department whose runtime is registered WITHOUT the dept- prefix
    (bare workspace-slug variant) must still be recognized as wired."""
    depts = [{"slug": "presentations", "name": "Presentations"}]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        config_path = _make_config(tmp, ["presentations"])  # bare, no dept- prefix
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"


def test_match_via_canonical_alias_variant_passes():
    """A workspace slug that is a non-canonical alias (e.g. 'webdev') must
    still match a runtime registered under the CANONICAL slug
    ('dept-web-development'), mirroring resolveSpecialistSessionKey's
    Attempt 1b canonical-slug fallback."""
    depts = [{"slug": "webdev", "name": "Web Dev"}]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        config_path = _make_config(tmp, ["dept-web-development"])
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"


def test_match_via_role_slug_variant_passes():
    """A department only resolvable via the dashboard agent's `role` field
    (Attempt 2) must still be recognized."""
    depts = [{"slug": "unmapped-thing", "name": "Unmapped Thing",
              "agent_role": "Growth Ops Lead"}]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        config_path = _make_config(tmp, ["dept-growth-ops-lead"])
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"


def test_match_via_agent_name_slug_variant_passes():
    """A department only resolvable via the dashboard agent's `name` field
    (Attempt 3, NOT dept-prefixed) must still be recognized."""
    depts = [{"slug": "another-unmapped", "name": "Another Unmapped",
              "agent_name": "GrowthBot"}]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        config_path = _make_config(tmp, ["growthbot"])  # no dept- prefix, per Attempt 3
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"


# --------------------------------------------------------------------------
# 3. Soft-fail vs. hard-fail boundary.
# --------------------------------------------------------------------------
def test_missing_db_is_not_a_failure():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _make_config(tmp, ["dept-marketing"])
        missing_db = Path(tmp) / "does-not-exist.db"
        res = _run(missing_db, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"
        assert "SKIP" in res.stdout


def test_empty_workspaces_table_is_not_a_failure():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, [])  # workspaces table exists, zero rows
        config_path = _make_config(tmp, [])
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"
        assert "PASS" in res.stdout


def test_departments_seeded_but_config_unreadable_is_hard_fail():
    """A workspaces table with real department rows but NO readable
    openclaw.json must NOT silently pass -- we cannot vouch for ANY
    department's runtime in that state."""
    depts = [{"slug": "marketing", "name": "Marketing"}]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts)
        missing_config = Path(tmp) / "does-not-exist.json"
        res = _run(db_path, missing_config)
        assert res.returncode == EX_CONFIG_UNREADABLE, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"
        assert "Marketing" in (res.stdout + res.stderr)


def test_main_system_type_rows_are_excluded_when_type_column_present():
    """Schema-tolerant: when a `type` column exists on workspaces, main/system
    pseudo-workspaces are not departments and must not be checked."""
    depts = [
        {"slug": "main", "name": "Main", "type": "main"},
        {"slug": "marketing", "name": "Marketing", "type": "department"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _make_db(tmp, depts, with_type_column=True)
        # Only marketing has a runtime; "main" would fail if it were checked.
        config_path = _make_config(tmp, ["dept-marketing"])
        res = _run(db_path, config_path)
        assert res.returncode == EX_OK, f"exit {res.returncode}\n{res.stdout}\n{res.stderr}"
        assert "1/1" in res.stdout


# --------------------------------------------------------------------------
# 4. Slug-variant unit coverage (candidate_variants) -- all 6 dispatcher shapes.
# --------------------------------------------------------------------------
def test_variant_1_dept_prefixed_workspace_slug():
    assert "dept-marketing" in candidate_variants("marketing")


def test_variant_2_bare_workspace_slug():
    assert "marketing" in candidate_variants("marketing")


def test_variant_3_dept_prefixed_canonical_alias():
    # "webdev" canonicalizes to "web-development" (shared-utils/canonical_slug.py).
    assert "dept-web-development" in candidate_variants("webdev")


def test_variant_4_bare_canonical_alias():
    assert "web-development" in candidate_variants("webdev")


def test_variant_5_dept_prefixed_role_slug():
    variants = candidate_variants("some-slug", agent_role="Marketing Lead")
    assert "dept-marketing-lead" in variants


def test_variant_6_bare_agent_name_slug():
    variants = candidate_variants("some-slug", agent_name="GrowthBot")
    assert "growthbot" in variants
    # Attempt 3 is explicitly NOT dept-prefixed in the real dispatcher.
    assert "dept-growthbot" not in variants


def test_canonical_alias_map_spot_checks_match_command_center():
    """Pins agreement with blackceo-command-center's src/lib/routing/canonical-slug.ts
    ALIAS_MAP on a few representative entries (both sides are contractually
    required to stay in sync; this is the guard's own drift detector)."""
    cases = {
        "ceo": "master-orchestrator",
        "webdev": "web-development",
        "billing": "billing-finance",
        "app-development": "engineering",
        "marketing": "marketing",  # already canonical -> unchanged
    }
    for raw, expected in cases.items():
        assert canonical_dept_slug(raw) == expected, (
            f"canonical_dept_slug({raw!r}) == {canonical_dept_slug(raw)!r}, "
            f"expected {expected!r} (drift from command-center canonical-slug.ts?)"
        )


def _main():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL: {name}: {e}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR: {name}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{failures} test(s) failed", file=sys.stderr)
        sys.exit(1)
    print("\nall guard-department-runtime-parity tests passed")


if __name__ == "__main__":
    _main()
