import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools/tests/fixtures/legacy/video-edit-door.md"
MIGRATOR = ROOT / "scripts/33-migrate-legacy-playbooks.sh"
ENGINE = ROOT / "tools/playbook_engine.py"
GATES = (
    "scripts/qc-tool-gating.sh",
    "scripts/qc-workflow-exits.sh",
    "scripts/qc-playbook-declares.sh",
    "scripts/qc-playbook-doc.sh",
)
# Pinned so the control fixture cannot drift unnoticed. Repinned when the
# fixture was sanitised: it had been copied from a live client playbook and
# carried a real location id, page id, owner name and local path, which this
# fleet-wide repo may not contain (qc-no-personal-data.sh was failing on it).
# The structural property the tests need — a legacy playbook with no
# `### Phase N` — is unchanged.
EXPECTED_SHA256 = (
    "09d1fc09dff2b7d18b96379ee34be3eb1117c258c6c8231812e6c471e7afeab6"
)
MIGRATION_SUMMARY = "legacy playbooks NEEDS-MIGRATION: 1"
MIGRATION_RESULT = (
    "RESULT: NEEDS-MIGRATION - 1 legacy playbook(s) need migration; "
    "nothing else failed. They are not PASS."
)
MIGRATION_REASON = (
    "[NEEDS-MIGRATION] video-edit-door.md — legacy playbook "
    "(no '### Phase N', no declares, no model-tier:); NOT a pass. Fix: "
)


def run(*args):
    env = os.environ.copy()
    env["AGENTS_MD"] = "/nonexistent"
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def output(result):
    return result.stdout + result.stderr


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_command(directory):
    return (
        "bash scripts/33-migrate-legacy-playbooks.sh "
        f"{directory.resolve()} --write"
    )


def migrated_path(original):
    return original.with_name(f"{original.stem}.migrated.md")


def test_legacy_fixture_reports_needs_migration_not_pass():
    assert FIXTURE.is_file(), f"Missing legacy fixture: {FIXTURE}"
    assert sha256(FIXTURE) == EXPECTED_SHA256, "Fixture bytes changed"

    expected_command = migration_command(FIXTURE.parent)

    for gate in GATES:
        result = run("bash", ROOT / gate, "--dir", FIXTURE.parent)
        text = output(result)

        assert result.returncode == 0, f"{gate} failed:\n{text}"
        assert "NEEDS-MIGRATION" in text, f"{gate} omitted migration status"
        assert FIXTURE.name in text, f"{gate} omitted fixture basename"
        assert expected_command in text, f"{gate} printed wrong migration command"
        assert "--in-place" not in text, f"{gate} printed removed flag"
        assert MIGRATION_SUMMARY in text, f"{gate} omitted migration summary"
        assert MIGRATION_RESULT in text, f"{gate} omitted migration result"
        assert MIGRATION_REASON in text, f"{gate} omitted legacy explanation"
        assert "RESULT: PASS" not in text, f"{gate} incorrectly passed legacy fixture"
        assert "RESULT: FAIL" not in text, f"{gate} incorrectly failed legacy fixture"
        assert sha256(FIXTURE) == EXPECTED_SHA256, (
            f"{gate} modified the original fixture"
        )

    assert sha256(FIXTURE) == EXPECTED_SHA256, "Fixture changed after gate runs"


def test_new_style_without_phases_fails_all_four(tmp_path):
    playbook = tmp_path / "synthetic.md"
    playbook.write_text(
        "# Conversation Workflow: Synthetic\n\n"
        "model-tier: realtime-standard\n\n"
        "declares\n"
        "tools-used:\n"
        "exits-used:\n"
        "fields-used:\n"
        "tags-used:\n"
        "calendars:\n"
        "pipeline:\n"
        "stage-map:\n",
        encoding="utf-8",
    )
    (tmp_path / "registry.md").write_text(
        "# Registry\n\n"
        "| ID | Name | Documentation |\n"
        "|---|---|---|\n"
        "| synthetic | Synthetic | https://example.com/synthetic.md |\n",
        encoding="utf-8",
    )

    assert not re.search(
        r"(?m)^### Phase \d+\b", playbook.read_text(encoding="utf-8")
    ), "Synthetic fixture must contain no phases"

    for gate in GATES:
        result = run("bash", ROOT / gate, "--dir", tmp_path)
        text = output(result)

        assert result.returncode == 1, (
            f"{gate} should reject new-style playbook without phases:\n{text}"
        )
        assert "RESULT: FAIL" in text, f"{gate} omitted failure result:\n{text}"


def test_dry_run_prints_diff_and_leaves_original_identical(tmp_path):
    original = tmp_path / FIXTURE.name
    shutil.copyfile(FIXTURE, original)
    before = sha256(original)

    result = run("bash", MIGRATOR, tmp_path)
    text = output(result)

    assert result.returncode == 0, text
    assert "+declares" in text, f"Missing declares diff:\n{text}"
    assert "### Phase 1" in text, f"Missing phase diff:\n{text}"
    assert "files needing migration: 1" in text, text
    assert sha256(original) == before, "Dry run modified original"
    assert not migrated_path(original).exists(), "Dry run created migrated output"
    assert not list(tmp_path.glob("*.bak")), "Dry run created backup file"


def test_write_creates_migrated_file_next_to_original(tmp_path):
    original = tmp_path / FIXTURE.name
    shutil.copyfile(FIXTURE, original)
    before = sha256(original)
    migrated = migrated_path(original)

    result = run("bash", MIGRATOR, tmp_path, "--write")
    text = output(result)

    assert result.returncode == 0, text
    assert migrated.is_file(), f"Missing migrated file: {migrated}"
    assert sha256(original) == before, "Migration modified original"
    assert not list(tmp_path.glob("*.bak")), "Migration created backup file"


def test_migrated_file_validates(tmp_path):
    original = tmp_path / FIXTURE.name
    shutil.copyfile(FIXTURE, original)
    migrated = migrated_path(original)

    result = run("bash", MIGRATOR, tmp_path, "--write")
    text = output(result)

    assert result.returncode == 0, text
    assert migrated.is_file(), f"Missing migrated file: {migrated}"

    migrated_text = migrated.read_text(encoding="utf-8")
    phase_count = len(re.findall(r"(?m)^### Phase ", migrated_text))
    assert phase_count == 15, f"Expected 15 phases, got {phase_count}"

    fields = (
        "tools-used",
        "exits-used",
        "fields-used",
        "tags-used",
        "calendars",
        "pipeline",
        "stage-map",
    )
    for field in fields:
        matches = re.findall(
            rf"(?m)^{re.escape(field)}:[ \t]*$",
            migrated_text,
        )
        assert matches, f"Missing or non-empty declares field: {field}"

    validation = run(
        "python3", "-I", ENGINE, "validate", migrated
    )
    validation_text = output(validation)
    assert validation.returncode == 0, validation_text
    assert "OK: playbook is grammatically valid" in validation_text, (
        validation_text
    )


def test_never_touches_outside_given_directory(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    outside = tmp_path / "outside.md"
    shutil.copyfile(FIXTURE, outside)
    before = sha256(outside)

    result = run("bash", MIGRATOR, target_dir, "--write")
    text = output(result)

    assert result.returncode == 0, text
    assert sha256(outside) == before, "Migration modified outside file"
    assert not migrated_path(outside).exists(), (
        "Migration created outside migrated sibling"
    )
    assert not list(tmp_path.rglob("*.bak")), (
        "Migration created backup file outside target directory"
    )


def test_in_place_is_rejected(tmp_path):
    original = tmp_path / FIXTURE.name
    shutil.copyfile(FIXTURE, original)

    result = run("bash", MIGRATOR, tmp_path, "--in-place")
    text = output(result)

    assert result.returncode == 2, text
    assert "Usage: bash scripts/33-migrate-legacy-playbooks.sh <dir> [--write]" in text, text
    assert sorted(path.name for path in tmp_path.iterdir()) == [original.name], (
        "Rejected flag changed directory contents"
    )
    assert sha256(original) == EXPECTED_SHA256, "Rejected flag modified original"


def test_existing_migrated_file_is_not_overwritten(tmp_path):
    original = tmp_path / FIXTURE.name
    shutil.copyfile(FIXTURE, original)
    migrated = migrated_path(original)

    first = run("bash", MIGRATOR, tmp_path, "--write")
    assert first.returncode == 0, output(first)
    assert migrated.is_file(), f"Missing migrated file: {migrated}"
    migrated_before = sha256(migrated)

    second = run("bash", MIGRATOR, tmp_path, "--write")
    second_text = output(second)

    assert second.returncode == 1, second_text
    assert sha256(migrated) == migrated_before, (
        "Second migration modified existing migrated file"
    )
    assert not list(tmp_path.glob("*.bak")), "Migration created backup file"


def test_broken_new_style_is_refused(tmp_path):
    broken = tmp_path / "broken.md"
    broken.write_text(
        "# Conversation Workflow: Broken\n\n"
        "model-tier: realtime-standard\n\n"
        "declares\n"
        "tools-used:\n"
        "exits-used:\n"
        "fields-used:\n"
        "tags-used:\n"
        "calendars:\n"
        "pipeline:\n"
        "stage-map:\n",
        encoding="utf-8",
    )
    before = sha256(broken)

    result = run("bash", MIGRATOR, tmp_path, "--write")
    text = output(result)

    assert result.returncode == 0, text
    assert "SKIP" in text, f"Migrator did not report skipped file:\n{text}"
    assert "broken" in text.lower(), f"Migrator did not name broken file:\n{text}"
    assert sha256(broken) == before, "Migrator modified broken new-style file"
    assert not migrated_path(broken).exists(), (
        "Migrator created output for broken new-style file"
    )
