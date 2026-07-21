#!/usr/bin/env python3
"""qc-assert-qc-summary-provenance.py — a QC summary may only carry the version
it was actually generated at.

WHY THIS EXISTS
---------------
`scripts/bump-version.sh` used to rewrite
`23-ai-workforce-blueprint/templates/role-library/_qc-summary.md` on every
release, rolling the version out of its `Role Library vX.Y.Z` heading. Nothing
re-ran quality control; only the number moved.

The measurement in that file was taken ONCE, on 2026-06-09, at repo version
v11.0.1 (commit 5c4075a5): 244 roles across 19 departments. By v20.0.85 the
heading read `Role Library v20.0.85` — 589 commits later — while the generation
date, the role count and the `ALL PASS` verdict had not moved. The sibling index
`_index.json` declared 438 roles across 36 departments at that same anchor.

So the artifact read as a current, comprehensive ALL-PASS certification of a
library that had never been measured at that version, and it renewed that claim
automatically on every single release. That is durable false evidence with a
refresh cycle. The defect survived for months precisely because nothing checked
the artifact — the version marker agreed with /version, so every version gate
went green while the number it agreed on was meaningless.

WHAT THIS GATE ENFORCES
-----------------------
For every registered QC-summary artifact:

  1. It carries a machine-readable provenance block: measurement status, the
     repo version the measurement was taken at, when it was taken, and how many
     roles were observed.
  2. ANTI-STAMP: every `Role Library vX.Y.Z` token in the document equals the
     recorded "measured at repo version". If no measurement is recorded, the
     document may not carry a `Role Library vX.Y.Z` token at all. A release that
     stamps the current version onto the heading without re-running the
     measurement therefore turns this gate RED.
  3. A recorded measurement version must be a real vX.Y.Z and must not be NEWER
     than /version — an artifact cannot have been measured at a version that
     does not exist yet. It is deliberately allowed to be OLDER: a genuine run
     ages as the repo moves on, and that is honest, not a failure.
  4. An artifact whose status is `not-measured` may not assert a pass verdict.
     No `ALL PASS`, no passing `Stage 2 verdict:` line.

And, because the defect's mechanism was the marker registration itself:

  5. MECHANISM: no QC-summary artifact may be registered as a repo version
     marker — not in `scripts/version-markers.json` and not in the inline
     fallback list in `qc-assert-repo-consistency.py`. Registering it is what
     obliged the bumper to roll it in the first place; re-registering it is how
     this defect comes back.
  6. `scripts/version-markers.json` `count` equals `len(markers)`, and
     `BUMP_CHECKED_MARKERS` in `scripts/bump-version.sh` equals both. The two
     tools already guard each other on the marker SET; nothing guarded the
     manifest's own self-declared count.

Exit codes:
  0  — every QC-summary artifact's version is the version it was measured at
  1  — INVARIANT VIOLATED
  2  — environment error (inputs not found / unparseable)

Usage:
  python3 scripts/qc-assert-qc-summary-provenance.py             # scan repo root
  python3 scripts/qc-assert-qc-summary-provenance.py --root DIR  # scan DIR
  python3 scripts/qc-assert-qc-summary-provenance.py --self-test # embedded tests

Wired into:
  - .github/workflows/qc-summary-provenance-guard.yml (push/PR)

v1.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Every artifact that records a quality-control measurement and carries a
# version. Add new QC summaries here; each one gets the same treatment.
QC_SUMMARY_RELPATHS = [
    "23-ai-workforce-blueprint/templates/role-library/_qc-summary.md",
]

MANIFEST_REL = "scripts/version-markers.json"
BUMPER_REL = "scripts/bump-version.sh"
FALLBACK_REL = "23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py"
VERSION_REL = "version"

# Provenance fields the artifact must carry, as `**Label:** value` lines.
F_STATUS = "Measurement status"
F_VERSION = "Last measured at repo version"
F_WHEN = "Last measured (UTC)"
F_ROLES = "Roles observed at last measurement"
REQUIRED_FIELDS = [F_STATUS, F_VERSION, F_WHEN, F_ROLES]

STATUS_MEASURED = "measured"
STATUS_NOT_MEASURED = "not-measured"
NONE_TOKEN = "none"

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
# The stamped heading token the bumper used to rewrite.
ROLE_LIBRARY_VERSION_RE = re.compile(r"Role Library (v\d+\.\d+\.\d+)")
# Pass verdicts an unmeasured artifact must not assert.
PASS_VERDICT_RE = re.compile(r"ALL\s+PASS", re.IGNORECASE)
BUMP_MARKERS_RE = re.compile(r"^BUMP_CHECKED_MARKERS=(\d+)", re.MULTILINE)


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _field_re(label: str) -> re.Pattern[str]:
    """Match `**Label:** value` on its own line."""
    return re.compile(r"^\*\*" + re.escape(label) + r":\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE)


def parse_provenance(text: str) -> dict[str, str | None]:
    """Extract the provenance block. A missing field maps to None."""
    out: dict[str, str | None] = {}
    for label in REQUIRED_FIELDS:
        m = _field_re(label).search(text)
        out[label] = m.group(1).strip() if m else None
    return out


def _version_tuple(v: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in v.lstrip("v").split("."))  # type: ignore[return-value]


def check_artifact(relpath: str, text: str, repo_version: str | None) -> int:
    """Check one QC-summary artifact. Returns 1 on any violation."""
    fail = 0
    prov = parse_provenance(text)

    missing = [label for label in REQUIRED_FIELDS if prov[label] is None]
    if missing:
        _fail(
            f"{relpath} — provenance block incomplete; missing field(s): "
            + ", ".join(missing)
            + ". Every QC summary must state, as `**Label:** value` lines: "
            + ", ".join(REQUIRED_FIELDS)
            + "."
        )
        return 1

    status = (prov[F_STATUS] or "").strip()
    measured_at = (prov[F_VERSION] or "").strip()

    if status not in (STATUS_MEASURED, STATUS_NOT_MEASURED):
        _fail(
            f"{relpath} — `{F_STATUS}` is '{status}'; expected "
            f"'{STATUS_MEASURED}' or '{STATUS_NOT_MEASURED}'."
        )
        fail = 1

    # ── The measured-at version itself ────────────────────────────────────────
    recorded_version: str | None = None
    if measured_at == NONE_TOKEN:
        if status == STATUS_MEASURED:
            _fail(
                f"{relpath} — status is '{STATUS_MEASURED}' but `{F_VERSION}` is "
                f"'{NONE_TOKEN}'. A measurement must record the version it ran at."
            )
            fail = 1
    elif not VERSION_RE.match(measured_at):
        _fail(
            f"{relpath} — `{F_VERSION}` is '{measured_at}'; expected a vX.Y.Z "
            f"version or '{NONE_TOKEN}'."
        )
        fail = 1
    else:
        recorded_version = measured_at
        if repo_version and VERSION_RE.match(repo_version):
            if _version_tuple(recorded_version) > _version_tuple(repo_version):
                _fail(
                    f"{relpath} — `{F_VERSION}` {recorded_version} is NEWER than "
                    f"/version {repo_version}. An artifact cannot have been measured "
                    f"at a version that does not exist yet."
                )
                fail = 1

    # ── ANTI-STAMP: heading version must be the measured-at version ───────────
    stamped = sorted(set(ROLE_LIBRARY_VERSION_RE.findall(text)))
    if stamped:
        if recorded_version is None:
            _fail(
                f"{relpath} — carries version token(s) {stamped} but records no "
                f"measurement version. A QC summary may only carry the version it "
                f"was generated at. Re-run the measurement, or drop the version "
                f"from the document."
            )
            fail = 1
        else:
            wrong = [v for v in stamped if v != recorded_version]
            if wrong:
                _fail(
                    f"{relpath} — STAMPED WITH A VERSION IT WAS NOT GENERATED AT: "
                    f"document says 'Role Library {wrong[0]}' but the measurement "
                    f"was taken at {recorded_version}. Something rolled the version "
                    f"without re-running quality control. Do not roll it — re-run "
                    f"the measurement and rewrite both fields together."
                )
                fail = 1
            else:
                _ok(f"{relpath} — version token {recorded_version} matches the measurement")
    else:
        _ok(f"{relpath} — carries no stamped version token")

    # ── An unmeasured artifact may not assert a pass ─────────────────────────
    if status == STATUS_NOT_MEASURED:
        hit = PASS_VERDICT_RE.search(text)
        if hit:
            _fail(
                f"{relpath} — status is '{STATUS_NOT_MEASURED}' but the document "
                f"asserts '{hit.group(0)}'. An artifact that was not measured "
                f"cannot report a verdict."
            )
            fail = 1
        else:
            _ok(f"{relpath} — status '{STATUS_NOT_MEASURED}', asserts no pass verdict")
    else:
        _ok(f"{relpath} — status '{STATUS_MEASURED}' at {recorded_version}")

    return fail


def check_not_a_version_marker(root: str) -> int:
    """No QC summary may be registered as a repo version marker (rule 5), and the
    manifest's self-declared count must agree with its list and the bumper (6)."""
    fail = 0
    manifest_path = os.path.join(root, MANIFEST_REL)

    if not os.path.isfile(manifest_path):
        print(f"ENVIRONMENT: {MANIFEST_REL} not found under {root}")
        return 2

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:  # noqa: BLE001
        print(f"ENVIRONMENT: {MANIFEST_REL} is unparseable: {e}")
        return 2

    markers = manifest.get("markers")
    if not isinstance(markers, list):
        print(f"ENVIRONMENT: {MANIFEST_REL} has no 'markers' list")
        return 2

    marker_files = {str(m.get("file", "")) for m in markers}
    for rel in QC_SUMMARY_RELPATHS:
        if rel in marker_files:
            _fail(
                f"{MANIFEST_REL} registers {rel} as a repo version marker. A QC "
                f"summary records a MEASUREMENT, not the release it ships in — "
                f"registering it obliges bump-version.sh to roll it, which is "
                f"exactly how the stale ALL-PASS artifact renewed itself on every "
                f"release. Remove the marker entry."
            )
            fail = 1
        else:
            _ok(f"{MANIFEST_REL} does not register {rel} as a version marker")

    # The inline fallback list inside the repo-consistency gate is a byte-for-byte
    # mirror of the manifest; a QC summary must be absent from it too.
    fallback_path = os.path.join(root, FALLBACK_REL)
    if os.path.isfile(fallback_path):
        with open(fallback_path, encoding="utf-8") as fh:
            fallback_text = fh.read()
        for rel in QC_SUMMARY_RELPATHS:
            if rel in fallback_text:
                _fail(
                    f"{FALLBACK_REL} still names {rel} — the inline fallback marker "
                    f"list mirrors {MANIFEST_REL} and must drop it too, or the "
                    f"missing-manifest path re-introduces the marker."
                )
                fail = 1
            else:
                _ok(f"{FALLBACK_REL} does not name {rel}")

    # Manifest count vs its own list.
    declared = manifest.get("count")
    if declared != len(markers):
        _fail(
            f"{MANIFEST_REL} declares count={declared} but lists {len(markers)} "
            f"markers. Update 'count' whenever a marker is added or removed."
        )
        fail = 1
    else:
        _ok(f"{MANIFEST_REL} count={declared} matches its {len(markers)} marker entries")

    # Bumper's self-declared marker count vs the manifest.
    bumper_path = os.path.join(root, BUMPER_REL)
    if os.path.isfile(bumper_path):
        with open(bumper_path, encoding="utf-8") as fh:
            m = BUMP_MARKERS_RE.search(fh.read())
        if not m:
            _fail(f"{BUMPER_REL} — BUMP_CHECKED_MARKERS assignment not found")
            fail = 1
        elif int(m.group(1)) != len(markers):
            _fail(
                f"{BUMPER_REL} sets BUMP_CHECKED_MARKERS={m.group(1)} but "
                f"{MANIFEST_REL} lists {len(markers)} markers."
            )
            fail = 1
        else:
            _ok(f"{BUMPER_REL} BUMP_CHECKED_MARKERS={m.group(1)} matches the manifest")

    return fail


def check(root: str) -> int:
    version_path = os.path.join(root, VERSION_REL)
    repo_version = None
    if os.path.isfile(version_path):
        with open(version_path, encoding="utf-8") as fh:
            first = fh.readline().strip()
        repo_version = first or None

    print("== QC summaries carry only the version they were measured at ==")
    fail = 0
    seen_any = False
    for rel in QC_SUMMARY_RELPATHS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            print(f"ENVIRONMENT: registered QC summary not found: {rel}")
            return 2
        seen_any = True
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        fail |= check_artifact(rel, text, repo_version)

    if not seen_any:
        print("ENVIRONMENT: no QC-summary artifacts registered")
        return 2

    print("== no QC summary is registered as a repo version marker ==")
    marker_result = check_not_a_version_marker(root)
    if marker_result == 2:
        return 2
    fail |= marker_result

    if fail:
        print("\nQC-SUMMARY PROVENANCE: FAIL")
        print(
            "A quality-control summary stamped with a version it was not generated "
            "at is false evidence, and a release that re-stamps it renews that "
            "claim automatically. Re-run the measurement or drop the claim."
        )
    else:
        print(
            f"\nQC-SUMMARY PROVENANCE: PASS "
            f"({len(QC_SUMMARY_RELPATHS)} artifact(s) checked at /version={repo_version})"
        )
    return fail


# ---------------------------------------------------------------------------
# Embedded self-test: proves the gate FAILS on a stamped version and PASSES clean.
# ---------------------------------------------------------------------------

_CLEAN_SUMMARY = """# Stage 2 QC Summary - Role Library

**Measurement status:** not-measured
**Last measured at repo version:** none
**Last measured (UTC):** none
**Roles observed at last measurement:** none

No Stage 2 run has been performed at this repo version.
"""

_MEASURED_SUMMARY = """# Stage 2 QC Summary - Role Library v1.2.3

**Measurement status:** measured
**Last measured at repo version:** v1.2.3
**Last measured (UTC):** 2026-01-01
**Roles observed at last measurement:** 7

Seven roles scored.
"""

_MANIFEST_CLEAN = {
    "count": 2,
    "markers": [
        {"id": "/version", "file": "version", "type": "plainfile"},
        {"id": "install.sh", "file": "install.sh", "type": "regex",
         "pattern": "^ONBOARDING_VERSION="},
    ],
}

_BUMPER_CLEAN = "#!/usr/bin/env bash\nBUMP_CHECKED_MARKERS=2\necho hi\n"
_FALLBACK_CLEAN = '_VERSION_MARKERS_FALLBACK = [\n    {"id": "/version", "file": "version"},\n]\n'


def _build_fixture(tmp: str, summary: str, manifest: dict, bumper: str,
                   fallback: str, version: str = "v1.2.3") -> str:
    root = tempfile.mkdtemp(dir=tmp)
    for rel in QC_SUMMARY_RELPATHS:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(summary)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    with open(os.path.join(root, MANIFEST_REL), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(os.path.join(root, BUMPER_REL), "w", encoding="utf-8") as fh:
        fh.write(bumper)
    fb_path = os.path.join(root, FALLBACK_REL)
    os.makedirs(os.path.dirname(fb_path), exist_ok=True)
    with open(fb_path, "w", encoding="utf-8") as fh:
        fh.write(fallback)
    with open(os.path.join(root, VERSION_REL), "w", encoding="utf-8") as fh:
        fh.write(version + "\n")
    return root


def self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="qc-summary-provenance-selftest-")
    failures = 0
    try:
        qc_rel = QC_SUMMARY_RELPATHS[0]

        # The exact regression: the release bumper rolled the heading to the
        # current version while the measurement stayed where it was.
        stamped = _MEASURED_SUMMARY.replace(
            "Role Library v1.2.3", "Role Library v9.9.9"
        )
        # An unmeasured artifact that still asserts the old verdict.
        unmeasured_pass = _CLEAN_SUMMARY.replace(
            "No Stage 2 run has been performed at this repo version.",
            "**Stage 2 verdict:** ALL PASS",
        )
        no_field = _CLEAN_SUMMARY.replace("**Last measured (UTC):** none\n", "")
        future = _MEASURED_SUMMARY.replace("v1.2.3", "v9.9.9")

        manifest_registers_qc = {
            "count": 3,
            "markers": _MANIFEST_CLEAN["markers"] + [
                {"id": "_qc-summary.md", "file": qc_rel, "type": "regex",
                 "pattern": "Role Library v([0-9.]+)"},
            ],
        }
        manifest_bad_count = {"count": 5, "markers": _MANIFEST_CLEAN["markers"]}

        cases: list[tuple[str, str, dict, str, str, str, int]] = [
            ("clean not-measured artifact passes",
             _CLEAN_SUMMARY, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 0),
            ("genuine measurement at the current version passes",
             _MEASURED_SUMMARY, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 0),
            ("genuine measurement OLDER than /version still passes (no treadmill)",
             _MEASURED_SUMMARY, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v9.9.9", 0),
            ("STAMPED with a version it was not generated at fails",
             stamped, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v9.9.9", 1),
            ("measured at a version NEWER than /version fails",
             future, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 1),
            ("not-measured artifact asserting ALL PASS fails",
             unmeasured_pass, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 1),
            ("missing provenance field fails",
             no_field, _MANIFEST_CLEAN, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 1),
            ("re-registering the QC summary as a version marker fails",
             _CLEAN_SUMMARY, manifest_registers_qc, "#!/usr/bin/env bash\nBUMP_CHECKED_MARKERS=3\n",
             _FALLBACK_CLEAN, "v1.2.3", 1),
            ("QC summary named in the inline fallback marker list fails",
             _CLEAN_SUMMARY, _MANIFEST_CLEAN, _BUMPER_CLEAN,
             _FALLBACK_CLEAN + f'# {qc_rel}\n', "v1.2.3", 1),
            ("manifest count disagreeing with its marker list fails",
             _CLEAN_SUMMARY, manifest_bad_count, _BUMPER_CLEAN, _FALLBACK_CLEAN, "v1.2.3", 1),
            ("bumper marker count disagreeing with the manifest fails",
             _CLEAN_SUMMARY, _MANIFEST_CLEAN,
             "#!/usr/bin/env bash\nBUMP_CHECKED_MARKERS=7\n", _FALLBACK_CLEAN, "v1.2.3", 1),
        ]

        for name, summary, manifest, bumper, fallback, version, expected in cases:
            root = _build_fixture(tmp, summary, manifest, bumper, fallback, version)
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--root", root],
                capture_output=True, text=True,
            )
            got = proc.returncode
            if got == expected:
                print(f"  ✓ self-test: {name} (exit {got})")
            else:
                print(f"  ✗ self-test: {name} — expected exit {expected}, got {got}")
                print("      ---- gate output ----")
                for line in proc.stdout.splitlines():
                    print(f"      {line}")
                failures += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\nSELF-TEST: FAIL ({failures} case(s))")
        return 1
    print(
        "\nSELF-TEST: PASS (gate fails on a stamped version, a future version, an "
        "unmeasured pass verdict, a missing field, marker re-registration and count drift)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None, help="repo root to scan")
    ap.add_argument("--self-test", action="store_true", help="run embedded tests")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return check(root)


if __name__ == "__main__":
    sys.exit(main())
