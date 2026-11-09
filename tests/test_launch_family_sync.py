"""CON-06: the launch-family sync copies by allowlist and the parity gate reports
every difference outside it. Fixtures are synthetic trees built from the
declared FAMILIES, so the test needs no 999 clone and no network."""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parity = _load("check_launch_family_parity", "check-launch-family-parity.py")
sync = _load("sync_launch_family_to_999", "sync_launch_family_to_999.py")

PLAIN = [n for n in parity.FAMILIES if n != "signature-page"]
SEAM_TOKENS = {d: t for d, (_n, t) in parity.DIVERGENT.items()}


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(tmp: Path, family: str, drift: bool = True):
    """Onboarding trees for the family; 999 trees behind them, with the declared
    999-only and divergent files in place."""
    onb, nine = tmp / "onb", tmp / "nine"
    onb.mkdir(), nine.mkdir()
    for onb_rel, nine_rel in parity.FAMILIES[family]:
        _write(onb / onb_rel / "skill-version.txt", "2.0.0\n")
        _write(onb / onb_rel / "sub" / "mod.py", "print('onboarding')\n")
        _write(onb / onb_rel / "CHANGELOG.md", "onboarding changelog\n")
        _write(nine / nine_rel / "CHANGELOG.md", "999 changelog\n")
        if drift:
            _write(nine / nine_rel / "skill-version.txt", "1.0.0\n")
        else:
            _write(nine / nine_rel / "skill-version.txt", "2.0.0\n")
            _write(nine / nine_rel / "sub" / "mod.py", "print('onboarding')\n")
    for dest in parity.NINE_ONLY:
        if any(dest.startswith(n + "/") for _o, n in parity.FAMILIES[family]):
            _write(nine / dest, "999 ONLY SENTINEL\n")
    for dest, tokens in SEAM_TOKENS.items():
        for onb_rel, nine_rel in parity.FAMILIES[family]:
            if dest.startswith(nine_rel + "/"):
                _write(nine / dest, "999 edition " + " ".join(tokens) + "\n")
                _write(onb / onb_rel / dest[len(nine_rel) + 1:], "onboarding version\n")
    for onb_rel, nine_rel in parity.FAMILIES[family]:
        for manifest in parity.REQUIRED_ROOT_MANIFESTS.get(onb_rel, ()):
            body = '{"schema": "blackceo.skill.metadata/1", "name": "%s"}\n' % onb_rel
            _write(onb / onb_rel / manifest, body)
            _write(nine / nine_rel / manifest, body)
    return onb, nine


def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_all_six_families_are_declared():
    assert set(sync.FAMILY_CHOICES) == {"launcher", "signature-funnel", "signature-page",
                                        "page-skills", "ghl-install-pages", "caf-email"}


@pytest.mark.parametrize("family", PLAIN)
def test_dry_run_lists_copies_and_writes_nothing(tmp_path, family, capsys):
    onb, nine = build(tmp_path, family)
    before = snapshot(nine)
    assert sync.main(["--onboarding", str(onb), "--nine", str(nine),
                      "--family", family, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY copy" in out and "skill-version.txt" in out
    assert snapshot(nine) == before


@pytest.mark.parametrize("family", PLAIN)
def test_sync_never_touches_declared_999_only_files(tmp_path, family):
    onb, nine = build(tmp_path, family)
    before = snapshot(nine)
    sync.main(["--onboarding", str(onb), "--nine", str(nine), "--family", family])
    after = snapshot(nine)
    kept = [d for d in list(parity.NINE_ONLY) + list(parity.DIVERGENT) if d in before]
    if family in ("launcher", "ghl-install-pages", "caf-email"):  # the families with declared ones
        assert kept, "fixture must carry 999-only and divergent files"
    for dest in kept:
        assert after[dest] == before[dest], dest
    assert set(before) <= set(after), "the sync deleted a 999 file"
    for rel, data in before.items():  # per-repo changelog is reported, never overwritten
        if rel.endswith("CHANGELOG.md"):
            assert after[rel] == data


@pytest.mark.parametrize("family", PLAIN)
def test_parity_reports_drift_then_passes_after_sync(tmp_path, family, capsys):
    onb, nine = build(tmp_path, family)
    args = ["--onboarding", str(onb), "--nine", str(nine), "--family", family]
    assert parity.main(args) == 1
    assert "FAIL" in capsys.readouterr().out
    assert sync.main(args) == 0
    assert parity.main(args) == 0


def test_parity_reports_missing_tree_and_unclassified_999_only(tmp_path, capsys):
    onb, nine = build(tmp_path, "launcher", drift=False)
    contract = "shared-utils/signature_launch_contract"
    _write(onb / contract / "schema.json", "{}\n")  # whole tree absent in 999
    _write(nine / "shared-utils/client_intake/stray.py", "x = 1\n")
    report = parity.check(onb, nine, ["launcher"])
    text = "\n".join(report["failures"])
    assert f"missing: {contract}/schema.json" in text
    assert "unclassified_nine_only: shared-utils/client_intake/stray.py" in text


def test_parity_fails_when_999_loses_a_declared_999_only_file(tmp_path):
    onb, nine = build(tmp_path, "launcher", drift=False)
    victim = next(d for d in parity.NINE_ONLY if d.startswith(".claude/skills/black-friday-launcher/"))
    (nine / victim).unlink()
    report = parity.check(onb, nine, ["launcher"])
    assert any(f"nine_only_missing: {victim}" in f for f in report["failures"])


ONB_CLI = "83-black-friday-launcher/launcher_core/cli.py"
NINE_CLI = ".claude/skills/black-friday-launcher/launcher_core/cli.py"
NINE_ROUTE = ".claude/skills/black-friday-launcher/launcher_core/route.py"


def test_parity_fails_when_divergent_file_lacks_its_seam_tokens(tmp_path, monkeypatch):
    # cli.py is pinned, so it is no longer a divergence; the token check is still covered through route.py
    monkeypatch.setitem(parity.DIVERGENT, NINE_ROUTE, ("test seam", ("def cmd_plan",)))
    onb, nine = build(tmp_path, "launcher", drift=False)
    _write(onb / "83-black-friday-launcher/launcher_core/route.py", "onboarding route\n")
    _write(nine / NINE_ROUTE, "an old 999 route without the plan command\n")
    report = parity.check(onb, nine, ["launcher"])
    assert any("divergent_token_missing" in f and "def cmd_plan" in f for f in report["failures"])
    # the divergence is allowed to differ in bytes: only the missing seam fails
    assert not any("drift: " + NINE_ROUTE in f for f in report["failures"])


def test_cli_is_neutral_and_synced(tmp_path):
    # a pinned file cannot be a declared divergence: 999 gets the pin only through the sync
    assert NINE_CLI not in parity.DIVERGENT
    onb, nine = build(tmp_path, "launcher", drift=False)
    _write(onb / ONB_CLI, "onboarding cli\n")
    _write(nine / NINE_CLI, "an old 999 cli\n")
    report = parity.check(onb, nine, ["launcher"])
    assert any(f.startswith("[launcher] drift: " + NINE_CLI) for f in report["failures"])
    assert sync.main(["--onboarding", str(onb), "--nine", str(nine), "--family", "launcher"]) == 0
    assert (nine / NINE_CLI).read_bytes() == (onb / ONB_CLI).read_bytes()


PROGRESS = "shared-utils/signature_launch/experience/progress_report.py"


def test_progress_report_is_neutral_and_synced(tmp_path):
    # delivery_report.py (neutral) calls progress_report's CON-19 API, so a stale 999 copy cannot be a declared divergence
    assert PROGRESS not in parity.DIVERGENT
    onb, nine = build(tmp_path, "launcher", drift=False)
    _write(onb / PROGRESS, "onboarding progress_report\n")
    _write(nine / PROGRESS, "a stale 999 progress_report without RowsRefused\n")
    report = parity.check(onb, nine, ["launcher"])
    assert any(f.startswith("[launcher] drift: " + PROGRESS) for f in report["failures"])
    assert sync.main(["--onboarding", str(onb), "--nine", str(nine), "--family", "launcher"]) == 0
    assert (nine / PROGRESS).read_bytes() == (onb / PROGRESS).read_bytes()


def test_excluded_pack_file_present_in_999_refuses_the_sync(tmp_path, capsys):
    onb, nine = build(tmp_path, "ghl-install-pages", drift=False)
    onb_rel, nine_rel = parity.FAMILIES["ghl-install-pages"][0]
    _write(onb / onb_rel / "banned.txt", "x\n")
    _write(nine / nine_rel / "banned.txt", "x\n")
    manifest = onb / parity.PACK_MANIFEST_REL
    _write(manifest, '{"files": [{"source": "%s/banned.txt", "dest": "%s/banned.txt", '
                     '"verdict": "exclude", "class": "adapter"}]}' % (onb_rel, nine_rel))
    before = snapshot(nine)
    assert sync.main(["--onboarding", str(onb), "--nine", str(nine),
                      "--family", "ghl-install-pages"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert snapshot(nine) == before


def test_gate_scripts_travel_with_the_signature_page_family(tmp_path):
    onb, nine = tmp_path / "onb", tmp_path / "nine"
    for rel in parity.GATE_TOOLS:
        _write(onb / rel, "new gate\n")
    _write(nine / parity.GATE_TOOLS[0], "old gate\n")
    rows = {d: s for s, d, _ in parity.family_plan(onb, nine, "signature-page")}
    assert rows == {parity.GATE_TOOLS[0]: "drift", parity.GATE_TOOLS[1]: "missing"}


def test_failing_sync_never_prints_unprefixed_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sync._parity.DIVERGENT, NINE_ROUTE, ("test seam", ("def cmd_plan",)))
    onb, nine = build(tmp_path, "launcher", drift=False)
    for onb_rel, nine_rel in parity.FAMILIES["signature-page"]:
        _write(onb / onb_rel / "skill-version.txt", "2.0.0\n")
        _write(nine / nine_rel / "skill-version.txt", "2.0.0\n")
    for rel in parity.GATE_TOOLS:
        _write(onb / rel, "gate\n")
        _write(nine / rel, "gate\n")
    _write(nine / NINE_ROUTE, "an old 999 route without the plan command\n")
    ok = type("P", (), {"returncode": 0, "stdout": "SYNC DONE, PARITY PASS\n", "stderr": ""})()
    monkeypatch.setattr(sync.subprocess, "run", lambda *a, **k: ok)
    rc = sync.main(["--onboarding", str(onb), "--nine", str(nine),
                    "--family", "launcher", "--family", "signature-page"])
    lines = capsys.readouterr().out.splitlines()
    assert rc == 1
    assert "SYNC DONE, PARITY PASS" not in lines
    assert "[skill71] SYNC DONE, PARITY PASS" in lines
    assert any(l.startswith("HAND-MERGE NEEDED: ") and "def cmd_plan" in l for l in lines)
    assert lines[-1].startswith("SYNC DONE, PARITY FAILURES REMAIN")


ONB_MANIFEST = "49-signature-funnel/skill.json"
NINE_MANIFEST = ".claude/skills/signature-funnel/skill.json"


def test_built_root_manifest_list_names_the_manifest(tmp_path):
    # FIX-02: the assertion is read off the BUILT tree, so this proves the positive half.
    onb, nine = build(tmp_path, "signature-funnel", drift=False)
    report = parity.check(onb, nine, ["signature-funnel"])
    assert report["built_root_manifests"][".claude/skills/signature-funnel"] == ["skill.json"]
    assert report["failures"] == [], report["failures"]


def test_parity_fails_when_the_built_tree_lost_a_required_root_manifest(tmp_path):
    onb, nine = build(tmp_path, "signature-funnel", drift=False)
    (nine / NINE_MANIFEST).unlink()
    report = parity.check(onb, nine, ["signature-funnel"])
    assert any(f"root_manifest_missing_built: {NINE_MANIFEST}" in f for f in report["failures"]), \
        report["failures"]
    assert report["built_root_manifests"][".claude/skills/signature-funnel"] == []


def test_parity_fails_when_the_source_tree_lost_a_required_root_manifest(tmp_path):
    onb, nine = build(tmp_path, "signature-funnel", drift=False)
    (onb / ONB_MANIFEST).unlink()
    report = parity.check(onb, nine, ["signature-funnel"])
    assert any("root_manifest_missing_source: " + NINE_MANIFEST in f for f in report["failures"]), \
        report["failures"]


def test_the_required_root_manifests_are_the_launch_family_pair():
    assert set(parity.REQUIRED_ROOT_MANIFESTS) == {"49-signature-funnel", "83-black-friday-launcher"}
    assert all(v == ("skill.json",) for v in parity.REQUIRED_ROOT_MANIFESTS.values())
