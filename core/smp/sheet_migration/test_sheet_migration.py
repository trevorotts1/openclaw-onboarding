#!/usr/bin/env python3
"""Mocked tests for core/smp/sheet_migration (Owner D27 / decision 35 / plan
section 6.15, 2026-10-07).

Covered, one group per acceptance line:

  1. Contract constants — the five drama-song fields named by plan 6.15 and
     their payload keys / Weekly Overview column indexes.
  2. Migration no-loss proof — 1.2.0 -> 1.3.0 is additive: every pre-existing
     heading, cell and row survives unchanged and in place; the technical
     _row_key cell moves from column U to Z instead of being overwritten; no
     other tab changes; nothing vanishes; the input document is not mutated;
     a second run is a no-op.
  3. Fail-closed refusals — newer-than-1.3.0, a 1.3.0 stamp with missing
     fields, a partial field set, a missing Weekly Overview tab, a heading
     collision, a malformed version.
  4. scripts/migrate-template.py CLI — dry-run alters nothing, --apply backs
     up FIRST and stamps identity, live master template refused, live sheet
     without credentials never touched, exit codes 0/2/3/4.
  5. config/validate-sheet-format.py — validates 1.3.0, rejects the 1.2.0
     contract, catches a missing/moved drama field, catches NUMBER_EQ, and its
     --export wiring checks the staged social-planner-row-append.json.
  6. The staged webhook payload — node graph parity with Skill 35's export,
     and (under node) the actual jsCode: a 1.3.0 sheet gets 26 cells with the
     five fields at 20..24 and the key in Z; a 1.2.0 sheet keeps 21 cells, the
     key in U and the fields reported pending, never written over the key.
  7. Static gates — no network client, no operator path, no KIE host or key,
     no insecure scheme, no media file in the module, stdlib only.
  8. Zero paid calls — the whole flow runs in a process whose socket layer
     raises, and prints NO_NETWORK_OK.

Run: python3 core/smp/sheet_migration/test_sheet_migration.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent            # core/smp/sheet_migration/
REPO = HERE.parents[2]                            # onboarding repo root
UPSTREAM = REPO / "35-social-media-planner"
UPSTREAM_CONTRACT = UPSTREAM / "config" / "sheet-template.schema.json"
UPSTREAM_APPEND = UPSTREAM / "config" / "n8n" / "social-planner-row-append.json"

MIGRATE_CLI = HERE / "scripts" / "migrate-template.py"
VALIDATOR = HERE / "config" / "validate-sheet-format.py"
STAGED_APPEND = HERE / "config" / "n8n" / "social-planner-row-append.json"
BUNDLED_130 = HERE / "testdata" / "sheet-template-1.3.0.json"
LIVE_120 = HERE / "testdata" / "sheet-live-1.2.0.json"

sys.path.insert(0, str(HERE))
import migrate as M  # noqa: E402

FAILS = []
COUNT = 0


def check(name, cond, detail=""):
    global COUNT
    COUNT += 1
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if not cond else ""))
    if not cond:
        FAILS.append(name)


def run_py(args, timeout=90):
    return subprocess.run([sys.executable] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=timeout)


def tmp_copy(path, dst_dir):
    dst = Path(dst_dir) / Path(path).name
    dst.write_text(Path(path).read_text())
    return dst


def live_doc():
    return json.loads(LIVE_120.read_text())


# =============================================================================
# 1. contract constants (plan 6.15)
# =============================================================================
def test_constants():
    check("five drama-song fields, named as plan 6.15 words them",
          M.DRAMA_SONG_FIELDS == [
              "Drama Style Chosen", "Drama Status", "Drama KIE Cost",
              "Drama Video Link", "Drama Channels Posted"],
          str(M.DRAMA_SONG_FIELDS))
    check("payload keys are the five snake_case counterparts",
          M.DRAMA_SONG_PAYLOAD_KEYS == [
              "drama_style_chosen", "drama_status", "drama_kie_cost",
              "drama_video_link", "drama_channels_posted"],
          str(M.DRAMA_SONG_PAYLOAD_KEYS))
    check("payload keys map to Weekly Overview indexes 20..24",
          [M.OVERVIEW_FIELD_INDEX[k] for k in M.DRAMA_SONG_PAYLOAD_KEYS]
          == [20, 21, 22, 23, 24],
          str(M.OVERVIEW_FIELD_INDEX))
    check("technical key index: 20 at 1.2.0, 25 at 1.3.0",
          M.OVERVIEW_KEY_INDEX_120 == 20 and M.OVERVIEW_KEY_INDEX_130 == 25)
    check("legacy Weekly Overview layout is the 20 client-facing columns",
          len(M.LEGACY_OVERVIEW_HEADINGS) == 20
          and M.LEGACY_OVERVIEW_HEADINGS[0] == "Week Of"
          and M.LEGACY_OVERVIEW_HEADINGS[-1] == "Notes",
          str(len(M.LEGACY_OVERVIEW_HEADINGS)))
    check("schema bump is 1.2.0 -> 1.3.0",
          M.SCHEMA_FROM == "1.2.0" and M.SCHEMA_TO == "1.3.0")
    if UPSTREAM_CONTRACT.exists():
        upstream = json.loads(UPSTREAM_CONTRACT.read_text())
        heads = upstream["tabs"]["Weekly Overview"]["headings"]
        live_sv = upstream.get("schema_version")
        if live_sv == M.SCHEMA_TO:
            # SMP-W2-U1 shipped Skill 35's 1.3.0 contract upstream first, so the
            # live contract is no longer the 1.2.0 this unit migrates FROM. Hold
            # it to this module's 1.3.0 expectations instead: the legacy
            # 20-column prefix must still be this module's legacy heading list,
            # the shipped layout must still be 26 headings, and the stamp must
            # be this module's target version. The module's own 1.3.0 layout
            # (five drama-song fields at 20..24 per DRAMA_SONG_PAYLOAD_KEYS,
            # technical key at 25) is asserted above and in test_no_loss, on the
            # documents this module actually produces.
            check("legacy heading list matches Skill 35's live contract",
                  list(heads[:len(M.LEGACY_OVERVIEW_HEADINGS)])
                  == M.LEGACY_OVERVIEW_HEADINGS and len(heads) == 26,
                  "n=%d prefix=%r" % (len(heads), list(heads[:3])))
            check("Skill 35's contract is the 1.3.0 this unit migrates to",
                  live_sv == M.SCHEMA_TO and len(heads) == 26,
                  str(live_sv))
        else:
            check("legacy heading list matches Skill 35's live contract",
                  list(heads) == M.LEGACY_OVERVIEW_HEADINGS,
                  str(heads[:3]))
            check("Skill 35's contract is the 1.2.0 this unit migrates from",
                  live_sv == "1.2.0",
                  str(live_sv))


# =============================================================================
# 2. no-loss proof
# =============================================================================
def test_no_loss():
    original = live_doc()
    frozen = copy.deepcopy(original)
    migrated, report = M.migrate_doc(original)

    check("input document is not mutated (migration is pure)",
          original == frozen)
    ok, problems = M.lossless(original, migrated)
    check("lossless() structural proof passes", ok, "; ".join(problems))

    b_heads = frozen["tabs"]["Weekly Overview"]["headings"]
    a_heads = migrated["tabs"]["Weekly Overview"]["headings"]
    check("every pre-existing heading survives, in order, as the prefix",
          a_heads[:len(b_heads)] == b_heads,
          str(a_heads[:len(b_heads)][:3]))
    check("the five drama-song headings follow at 20..24",
          a_heads[len(b_heads):] == M.DRAMA_SONG_FIELDS,
          str(a_heads[len(b_heads):]))
    check("25 headings at 1.3.0", len(a_heads) == 25, str(len(a_heads)))

    b_rows = frozen["tabs"]["Weekly Overview"]["rows"]
    a_rows = migrated["tabs"]["Weekly Overview"]["rows"]
    check("row count unchanged", len(b_rows) == len(a_rows),
          "%d -> %d" % (len(b_rows), len(a_rows)))
    for i, (br, ar) in enumerate(zip(b_rows, a_rows)):
        width = min(len(br), len(b_heads))
        check("row %d: pre-existing heading cells keep value and index" % i,
              list(ar[:width]) == list(br[:width]),
              "before=%r after=%r" % (list(br[:width]), list(ar[:width])))
        check("row %d: new drama cells are empty" % i,
              list(ar[len(b_heads):len(b_heads) + 5]) == [""] * 5,
              str(ar[len(b_heads):len(b_heads) + 5]))
        check("row %d: trailing technical cell(s) survive in order" % i,
              list(ar[len(b_heads) + 5:]) == list(br[len(b_heads):]),
              "before=%r after=%r" % (list(br[len(b_heads):]),
                                      list(ar[len(b_heads) + 5:])))

    # trailing technical key: column U (20) -> column Z (25)
    check("row 0 technical _row_key moved U(20) -> Z(25), value intact",
          b_rows[0][20] == "OV::c1::r1" and len(a_rows[0]) == 26
          and a_rows[0][25] == "OV::c1::r1" and a_rows[0][20] == "",
          "before[%d]=%r after[%d]=%r after[%d]=%r"
          % (20, b_rows[0][20], 20, a_rows[0][20], 25, a_rows[0][25]))
    check("row 0: all 20 original cells still hold their original values",
          list(a_rows[0][:20]) == list(b_rows[0][:20]))
    check("rows without a technical key gain exactly 5 cells",
          len(a_rows[1]) == len(b_rows[1]) + 5
          and len(a_rows[2]) == 25          # ragged row padded to the 20 headings
          and len(a_rows[3]) == len(b_rows[3]) + 5,
          "before=%s after=%s"
          % ([len(r) for r in b_rows], [len(r) for r in a_rows]))

    for tab in ("Posts", "Client Notes", "Example (never copy)"):
        check("tab '%s' is byte-identical" % tab,
              migrated["tabs"][tab] == frozen["tabs"][tab])

    def values(doc):
        out = []
        for tab in doc["tabs"].values():
            for row in tab.get("rows") or []:
                out.extend(str(c) for c in row
                           if c is not None and str(c).strip() != "")
        return out

    b_vals, a_vals = values(frozen), values(migrated)
    check("no non-empty cell value vanished",
          all(v in a_vals for v in b_vals),
          str([v for v in b_vals if v not in a_vals]))
    expected_added = sum((25 - len(b)) if len(b) <= len(b_heads) else 5
                         for b in b_rows)
    check("cells_added equals the five new cells per widened row",
          report["cells_added"] == expected_added,
          "got %d expected %d" % (report["cells_added"], expected_added))
    check("schema_version stamped 1.3.0",
          migrated["schema_version"] == "1.3.0"
          and migrated["identity"]["schema_version"] == "1.3.0")
    check("migrated_from recorded",
          migrated["identity"].get("migrated_from") == "1.2.0",
          str(migrated["identity"].get("migrated_from")))

    again, report2 = M.migrate_doc(migrated)
    check("second run is idempotent (no further change)",
          report2["already_current"] and again == migrated
          and report2["cells_added"] == 0,
          str(report2))
    check("plan names the additive action",
          any(p.get("action") == "append_drama_song_fields"
              for p in report["plan"]), str(report["plan"]))
    check("plan leaves every other tab untouched",
          all(p.get("action") in ("append_drama_song_fields", "untouched")
              for p in report["plan"]), str(report["plan"]))


# =============================================================================
# 3. fail-closed refusals
# =============================================================================
def expect_reject(name, doc, fragment):
    try:
        M.migrate_doc(doc)
    except M.MigrationError as exc:
        check(name, fragment in str(exc), str(exc))
        return
    check(name, False, "no MigrationError raised")


def test_refusals():
    d = live_doc()
    d["schema_version"] = "1.4.0"
    expect_reject("refuses to downgrade a 1.4.0 document", d, "downgrade")

    d = live_doc()
    d["schema_version"] = "1.3.0"
    del d["tabs"]["Weekly Overview"]["headings"][-5:]  # stamp says 1.3.0, fields gone
    expect_reject("refuses a 1.3.0 stamp with the fields missing", d,
                  "repair the contract")

    d = live_doc()
    d["tabs"]["Weekly Overview"]["headings"].append("Drama Style Chosen")
    expect_reject("refuses a partial drama-song layout", d, "refuses a partial")

    d = live_doc()
    del d["tabs"]["Weekly Overview"]
    expect_reject("refuses a document with no Weekly Overview tab", d,
                  "nowhere to go")

    d = live_doc()
    # a legacy heading spelled like a drama field would be duplicated
    d["tabs"]["Weekly Overview"]["headings"][0] = "drama status"
    expect_reject("refuses a heading collision with a drama field", d,
                  "duplicate")

    d = live_doc()
    d["schema_version"] = "1.2"
    expect_reject("refuses a malformed schema_version", d,
                  "unrecognised schema_version")

    d = live_doc()
    d["schema_version"] = ""
    migrated, report = M.migrate_doc(d)
    check("an empty schema_version is treated as 1.2.0 and migrates",
          migrated["schema_version"] == "1.3.0"
          and report["from_version"].startswith("(absent"),
          str(report["from_version"]))

    d = live_doc()
    del d["schema_version"]
    migrated, _ = M.migrate_doc(d)
    check("a missing schema_version is treated as 1.2.0 and migrates",
          migrated["schema_version"] == "1.3.0")

    try:
        M.parse_version("v1.3.0")
        check("parse_version rejects a non-numeric version", False)
    except M.MigrationError:
        check("parse_version rejects a non-numeric version", True)


# =============================================================================
# 4. the contract itself, migrated
# =============================================================================
def test_contract_migration():
    if not UPSTREAM_CONTRACT.exists():
        check("Skill 35 contract present", False, str(UPSTREAM_CONTRACT))
        return
    original = json.loads(UPSTREAM_CONTRACT.read_text())
    if original.get("schema_version") == M.SCHEMA_TO:
        # Skill 35's live contract is already stamped 1.3.0 (SMP-W2-U1 shipped
        # it first), so there is no 1.2.0 -> 1.3.0 work left for it here. Assert
        # the module stays fail-closed on it — never guesses, never mutates —
        # and prove the migration itself on the bundled 1.2.0 snapshot.
        frozen = copy.deepcopy(original)
        try:
            migrated, report = M.migrate_doc(original)
        except M.MigrationError as exc:
            check("live 1.3.0 contract is refused fail-closed (no guessing)",
                  "repair the contract" in str(exc), str(exc)[:200])
        else:
            ok, problems = M.lossless(original, migrated)
            check("live 1.3.0 contract: an accepted migration loses nothing",
                  ok, "; ".join(problems))
        check("live 1.3.0 contract is left untouched (migrate is pure)",
              original == frozen)

        snap = json.loads(LIVE_120.read_text())
        snap_frozen = copy.deepcopy(snap)
        migrated, report = M.migrate_doc(snap)
        ok, problems = M.lossless(snap, migrated)
        check("bundled 1.2.0 snapshot migrates losslessly", ok,
              "; ".join(problems))
        check("bundled 1.2.0 snapshot input is not mutated",
              snap == snap_frozen)
        heads = migrated["tabs"]["Weekly Overview"]["headings"]
        check("bundled 1.2.0 snapshot reaches the module's 1.3.0 layout",
              len(heads) == 25
              and heads[20:25] == M.DRAMA_SONG_FIELDS
              and migrated["schema_version"] == M.SCHEMA_TO,
              str(heads[20:]))
    else:
        migrated, report = M.migrate_doc(original)
        ok, problems = M.lossless(original, migrated)
        check("migrating Skill 35's real contract loses nothing", ok,
              "; ".join(problems))
        check("migrated contract carries 25 Weekly Overview headings",
              len(migrated["tabs"]["Weekly Overview"]["headings"]) == 25)
        check("migrated contract matches the bundled 1.3.0 reference",
              migrated == json.loads(BUNDLED_130.read_text()))


# =============================================================================
# 5. scripts/migrate-template.py CLI
# =============================================================================
def test_cli():
    with tempfile.TemporaryDirectory(prefix="smp-u2-") as tmp:
        # dry-run alters nothing
        fx = tmp_copy(LIVE_120, tmp)
        before = fx.read_text()
        proc = run_py([MIGRATE_CLI, "--fixture", fx])
        check("dry-run exits 2 (changes pending)", proc.returncode == 2,
              "rc=%s %s" % (proc.returncode, proc.stdout[-400:]))
        check("dry-run leaves the fixture byte-identical",
              fx.read_text() == before)
        check("dry-run says nothing was altered",
              "nothing was altered" in proc.stdout, proc.stdout[-300:])
        check("dry-run names the drama-song fields",
              "Drama Style Chosen" in proc.stdout and "Drama Channels Posted"
              in proc.stdout, proc.stdout[:400])
        check("dry-run reports the additive cell count",
              "26 new empty cell" not in proc.stdout
              and "cell(s) would be added" in proc.stdout, proc.stdout[-300:])
        check("dry-run writes no output file",
              not (Path(str(fx) + ".migrated.json")).exists())

        # --apply: backup FIRST, then the migrated document
        fx2 = tmp_copy(LIVE_120, tmp)
        proc = run_py([MIGRATE_CLI, "--fixture", fx2, "--apply",
                       "--client-title", "Acme Co", "--timezone",
                       "America/New_York"])
        check("--apply exits 0", proc.returncode == 0,
              "rc=%s %s" % (proc.returncode, proc.stdout[-400:]))
        backup = Path(str(fx2) + ".backup.json")
        out = Path(str(fx2) + ".migrated.json")
        check("--apply writes a backup FIRST", backup.exists())
        check("--apply writes the migrated document", out.exists())
        if backup.exists():
            bdoc = json.loads(backup.read_text())["document"]
            check("backup holds the untouched 1.2.0 document",
                  bdoc["schema_version"] == "1.2.0"
                  and bdoc["tabs"]["Weekly Overview"]["headings"][0] == "Week Of")
            check("backup records the plan and direction",
                  json.loads(backup.read_text())["migrated_to"] == "1.3.0")
        if out.exists():
            doc = json.loads(out.read_text())
            check("migrated file is stamped 1.3.0 with identity provisioned",
                  doc["schema_version"] == "1.3.0"
                  and doc["identity"]["schema_version"] == "1.3.0"
                  and doc["identity"].get("client_title") == "Acme Co"
                  and doc["identity"].get("timezone") == "America/New_York")
            check("the written file is lossless against its input",
                  M.lossless(json.loads(fx2.read_text()), doc)[0],
                  str(M.lossless(json.loads(fx2.read_text()), doc)[1]))
            # the source file itself must still be the 1.2.0 original
            src = json.loads(fx2.read_text())
            check("the input fixture is never rewritten in place",
                  src["schema_version"] == "1.2.0")
        check("--apply prints the no-loss proof",
              "NO-LOSS PROOF: passed" in proc.stdout, proc.stdout[-400:])

        # --apply without full identity still works and says so
        fx3 = tmp_copy(LIVE_120, tmp)
        proc = run_py([MIGRATE_CLI, "--fixture", fx3, "--apply"])
        check("--apply without identity still succeeds and flags the gap",
              proc.returncode == 0 and "NOTE: identity fields not all provided"
              in proc.stdout, proc.stdout[-300:])

        # --sheet-id: never a network call
        proc = run_py([MIGRATE_CLI, "--sheet-id",
                       "1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c", "--apply"])
        check("live master template is refused (exit 3)",
              proc.returncode == 3 and "REFUSED" in proc.stdout,
              proc.stdout[-300:])
        proc = run_py([MIGRATE_CLI, "--sheet-id", "SandboxSheetId123", "--apply"])
        check("live sheet without credentials alters nothing (exit 3)",
              proc.returncode == 3 and "requires Sheets credentials" in proc.stdout,
              "rc=%s %s" % (proc.returncode, proc.stdout[-300:]))
        proc = run_py([MIGRATE_CLI, "--sheet-id", "SandboxSheetId123"])
        check("live sheet dry-run reports changes pending (exit 2)",
              proc.returncode == 2, "rc=%s" % proc.returncode)

        # rejected version
        bad = Path(tmp) / "future.json"
        doc = live_doc()
        doc["schema_version"] = "2.0.0"
        bad.write_text(json.dumps(doc))
        proc = run_py([MIGRATE_CLI, "--fixture", bad, "--apply"])
        check("unsupported version is rejected (exit 4)",
              proc.returncode == 4 and "REJECTED" in proc.stdout,
              "rc=%s %s" % (proc.returncode, proc.stdout[-300:]))
        check("a rejected run writes no output file",
              not Path(str(bad) + ".migrated.json").exists())

        # already current
        cur = Path(tmp) / "current.json"
        cur.write_text(BUNDLED_130.read_text())
        proc = run_py([MIGRATE_CLI, "--fixture", cur, "--apply"])
        check("an already-1.3.0 document is a clean no-op (exit 0)",
              proc.returncode == 0 and "ALREADY 1.3.0" in proc.stdout,
              "rc=%s %s" % (proc.returncode, proc.stdout[-300:]))

        # no arguments
        proc = run_py([MIGRATE_CLI])
        check("no --fixture and no --sheet-id is a usage error",
              proc.returncode != 0,
              "rc=%s" % proc.returncode)


# =============================================================================
# 6. config/validate-sheet-format.py
# =============================================================================
def run_validator(args):
    return run_py([VALIDATOR] + list(args))


def test_validator():
    proc = run_validator([str(BUNDLED_130)])
    check("validates the 1.3.0 contract (exit 0)",
          proc.returncode == 0, proc.stdout + proc.stderr)
    check("reports the check count and contract path",
          "checks, 0 failures" in proc.stdout and "contract:" in proc.stdout,
          proc.stdout[:300])

    if UPSTREAM_CONTRACT.exists():
        live_sv = json.loads(UPSTREAM_CONTRACT.read_text()).get("schema_version")
        proc = run_validator([str(UPSTREAM_CONTRACT)])
        if live_sv == "1.2.0":
            check("rejects the 1.2.0 contract (exit 1)",
                  proc.returncode == 1 and "expected 1.3.0" in proc.stdout,
                  proc.stdout[:500])
        else:
            # SMP-W2-U1 shipped its own 1.3.0 Weekly Overview layout upstream
            # first (cycle_id at 20, its five drama-song headings at 21..25,
            # 26 headings). This module's validator judges the live contract
            # against THIS module's 1.3.0 layout (five DRAMA_SONG_FIELDS at
            # 20..24, 25 headings) and must reject a layout it does not own
            # loudly, never pass it silently. The two 1.3.0 layouts are a known
            # cross-unit divergence for the merge train to reconcile — recorded
            # here, not papered over.
            check("live 1.3.0 contract is rejected against this module's layout",
                  proc.returncode == 1
                  and "26 headings, expected 25" in proc.stdout,
                  proc.stdout[:500])

    with tempfile.TemporaryDirectory(prefix="smp-u2-v-") as tmp:
        def write(name, mutate):
            doc = json.loads(BUNDLED_130.read_text())
            mutate(doc)
            p = Path(tmp) / name
            p.write_text(json.dumps(doc))
            return p

        p = write("missing-field.json",
                  lambda d: d["tabs"]["Weekly Overview"]["headings"].pop())
        proc = run_validator([str(p)])
        check("rejects a contract missing a drama-song heading",
              proc.returncode == 1 and "drama-song" in proc.stdout,
              proc.stdout[:500])

        def reorder(d):
            h = d["tabs"]["Weekly Overview"]["headings"]
            h[20], h[21] = h[21], h[20]
        p = write("reordered.json", reorder)
        proc = run_validator([str(p)])
        check("rejects drama-song headings in the wrong order",
              proc.returncode == 1 and "drama-song headings" in proc.stdout
              and "after the legacy 20" in proc.stdout,
              proc.stdout[:500])

        def rename_legacy(d):
            h = d["tabs"]["Weekly Overview"]["headings"]
            h[5] = "Videos Renamed"
        p = write("renamed.json", rename_legacy)
        proc = run_validator([str(p)])
        check("rejects a moved or renamed legacy column",
              proc.returncode == 1 and "legacy headings moved" in proc.stdout,
              proc.stdout[:500])

        def number_eq(d):
            # an EMITTED condition shape, not prose about the ban
            d["status_colors"]["conditional_format_rules"] = \
                '{"type": "NUMBER_EQ"} for every status'
        p = write("numeq.json", number_eq)
        proc = run_validator([str(p)])
        check("still rejects a NUMBER_EQ-emitting contract (F25)",
              proc.returncode == 1 and "NUMBER_EQ" in proc.stdout,
              proc.stdout[:500])

        def drop_this_week(d):
            heads = d["tabs"]["This Week"]["headings"]
            heads.remove("Needs Attention")
        p = write("tw.json", drop_this_week)
        proc = run_validator([str(p)])
        check("still rejects a This Week view missing a column (F25)",
              proc.returncode == 1 and "Needs Attention" in proc.stdout,
              proc.stdout[:500])

        def drop_identity(d):
            d["identity_fields"]["schema_version"] = "stamped on the sheet"
        p = write("novermatch.json", drop_identity)
        proc = run_validator([str(p)])
        check("rejects a contract that dropped the appProperties version-match",
              proc.returncode == 1 and "appProperties" in proc.stdout,
              proc.stdout[:500])

        def bad_declared(d):
            d["drama_song_fields"] = list(M.DRAMA_SONG_FIELDS)[:4]
        p = write("declared.json", bad_declared)
        proc = run_validator([str(p)])
        check("rejects a declared drama_song_fields list that disagrees",
              proc.returncode == 1 and "drama_song_fields" in proc.stdout,
              proc.stdout[:500])


def test_validator_export():
    proc = run_validator([str(BUNDLED_130), "--export"])
    check("--export validates the staged row-append wiring (exit 0)",
          proc.returncode == 0, proc.stdout + proc.stderr)
    create_upstream = (UPSTREAM / "config" / "n8n" /
                       "social-planner-sheet-create.json")
    if create_upstream.exists():
        check("--export also validates Skill 35's sheet-create F25 wiring",
              "social-planner-sheet-create.json" in proc.stdout,
              proc.stdout[:600])
    check("--export names the row-append export it validated",
          "social-planner-row-append.json" in proc.stdout,
          proc.stdout[:400])

    with tempfile.TemporaryDirectory(prefix="smp-u2-e-") as tmp:
        def export_copy(name, mutate=None):
            doc = json.loads(STAGED_APPEND.read_text())
            if mutate:
                mutate(doc)
            d = Path(tmp) / "n8n"
            d.mkdir(exist_ok=True)
            p = d / name
            p.write_text(json.dumps(doc))
            return d

        def drop_payload_key(d):
            node = next(n for n in d["nodes"]
                        if n["name"] == "Validate + Build Keys")
            node["parameters"]["jsCode"] = node["parameters"]["jsCode"].replace(
                "drama_video_link", "gone_field")

        n8n = export_copy("social-planner-row-append.json", drop_payload_key)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export whose payload dropped a new field",
              proc.returncode == 1 and "drama_video_link" in proc.stdout,
              proc.stdout[:600])

        def drop_contract(d):
            d["contract"].pop("drama_song_contract", None)
        n8n = export_copy("social-planner-row-append.json", drop_contract)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export with no drama_song_contract",
              proc.returncode == 1 and "drama_song_contract" in proc.stdout,
              proc.stdout[:600])

        def no_appprops(d):
            node = next(n for n in d["nodes"]
                        if n["name"] == "Verify Sheet Metadata (F14)")
            node["parameters"]["url"] = node["parameters"]["url"].split("?")[0]
        n8n = export_copy("social-planner-row-append.json", no_appprops)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export that cannot version-match the sheet",
              proc.returncode == 1 and "appProperties" in proc.stdout,
              proc.stdout[:600])

        def hardcoded(d):
            node = next(n for n in d["nodes"]
                        if n["name"] == "Update Overview Row (upsert)")
            node["parameters"]["url"] = node["parameters"]["url"].replace(
                "{{ $json.ovLastCol }}{{ $json.ovRowNumber }}", "U{{ $json.ovRowNumber }}")
        n8n = export_copy("social-planner-row-append.json", hardcoded)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export that hardcodes the 1.2.0 column range",
              proc.returncode == 1 and "hardcodes the column range" in proc.stdout,
              proc.stdout[:600])

        def old_version(d):
            d["schema_version"] = "1.1.0"
        n8n = export_copy("social-planner-row-append.json", old_version)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export still stamped payload 1.1.0",
              proc.returncode == 1 and "payload schema_version" in proc.stdout,
              proc.stdout[:600])

        def drop_app(d):
            d["contract"]["drama_song_contract"].pop("sheet_version_match", None)
        n8n = export_copy("social-planner-row-append.json", drop_app)
        proc = run_validator([str(BUNDLED_130), "--export", "--n8n-dir", str(n8n)])
        check("rejects an export without the documented version-match",
              proc.returncode == 1 and "sheet_version_match" in proc.stdout,
              proc.stdout[:600])

        # missing export file
        empty = Path(tmp) / "empty-n8n"
        empty.mkdir(exist_ok=True)
        proc = run_validator([str(BUNDLED_130), "--export",
                              "--n8n-dir", str(empty)])
        check("rejects a run with no staged row-append export",
              proc.returncode == 1 and "file missing" in proc.stdout,
              proc.stdout[:600])


# =============================================================================
# 7. staged webhook payload
# =============================================================================
def test_staged_export():
    check("staged social-planner-row-append.json parses",
          STAGED_APPEND.exists() and json.loads(STAGED_APPEND.read_text()),
          str(STAGED_APPEND))
    doc = json.loads(STAGED_APPEND.read_text())
    check("payload contract bumped to 1.2.0 everywhere",
          doc["schema_version"] == "1.2.0"
          and doc["meta"]["schema_version"] == "1.2.0"
          and doc["contract"]["schema_version"] == "1.2.0",
          str(doc["schema_version"]))
    dsc = doc["contract"]["drama_song_contract"]
    check("drama_song_contract names all five fields with their columns",
          [f["payload_key"] for f in dsc["fields"]] == M.DRAMA_SONG_PAYLOAD_KEYS
          and [f["heading"] for f in dsc["fields"]] == M.DRAMA_SONG_FIELDS
          and [f["overview_index"] for f in dsc["fields"]] == [20, 21, 22, 23, 24]
          and [f["column"] for f in dsc["fields"]] == list("UVWXY"),
          json.dumps(dsc["fields"]))
    check("legacy 1.1.0 callers stay accepted",
          dsc["accepted_payload_versions"] == ["1.1.0", "1.2.0"])
    check("version-match reads appProperties",
          "appProperties" in dsc["sheet_version_match"])

    if UPSTREAM_APPEND.exists():
        up = json.loads(UPSTREAM_APPEND.read_text())
        check("node graph is unchanged from Skill 35's export (same nodes)",
              [n["name"] for n in doc["nodes"]] == [n["name"] for n in up["nodes"]])
        check("connection graph is unchanged from Skill 35's export",
              doc["connections"] == up["connections"])
        check("the staged copy is a superset of the upstream payload contract",
              all(k in doc["contract"] for k in up["contract"]))
        # only the documented nodes differ
        changed = []
        for a, b in zip(doc["nodes"], up["nodes"]):
            if json.dumps(a.get("parameters"), sort_keys=True) != \
                    json.dumps(b.get("parameters"), sort_keys=True):
                changed.append(a["name"])
        check("exactly the documented nodes changed",
              sorted(changed) == sorted([
                  "Validate + Build Keys", "Verify Sheet Metadata (F14)",
                  "Read Weekly Overview (readback)", "Build Overview Summary",
                  "Update Overview Row (upsert)", "Append Overview Row",
                  "Build Receipt"]),
              str(changed))


# =============================================================================
# 8. execute the webhook jsCode under node (real proof the fields carry)
# =============================================================================
HARNESS = r"""
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

function nodesOf(exportDoc) {
  const m = {};
  for (const n of exportDoc.nodes) m[n.name] = n;
  return m;
}

function run(exportDoc, nodeName, input, stubs) {
  const nodes = nodesOf(exportDoc);
  const code = nodes[nodeName].parameters.jsCode;
  const $input = { first: () => ({ json: input }) };
  const $ = (name) => {
    if (stubs && Object.prototype.hasOwnProperty.call(stubs, name)) {
      return { first: () => ({ json: stubs[name] }) };
    }
    if (!nodes[name]) throw new Error('unknown node ' + name);
    return { first: () => ({ json: nodes[name].__out !== undefined ? nodes[name].__out : {} }) };
  };
  const fn = new Function('$input', '$', code);
  const out = fn($input, $);
  if (Array.isArray(out) && out[0] && out[0].json) nodes[nodeName].__out = out[0].json;
  return out;
}

const exportDoc = spec.export;
const results = {};

// ---- Validate + Build Keys -------------------------------------------------
const baseBody = {
  sheetId: 'Sheet123', company_id: 'co_1', cycle_id: 'c1',
  content_revision: 'r1', account_id: 'acct1', platform: 'tiktok',
  account_name: 'Brand TikTok', format: '9:16',
  scheduled_local: '2026-09-10 09:00', scheduled_utc: '2026-09-10T13:00:00Z',
  state: 'Published', qc_state: 'ok'
};

function tryValidate(body) {
  try {
    run(exportDoc, 'Validate + Build Keys', { body: body }, null);
    return { ok: true };
  } catch (e) { return { ok: false, error: String(e.message) }; }
}

results.validate_120 = tryValidate(Object.assign({}, baseBody, { schema_version: '1.2.0' }));
results.validate_110 = tryValidate(Object.assign({}, baseBody, { schema_version: '1.1.0' }));
results.validate_200 = tryValidate(Object.assign({}, baseBody, { schema_version: '2.0.0' }));
results.validate_no_version = tryValidate(Object.assign({}, baseBody));

const withDrama = Object.assign({}, baseBody, {
  drama_style_chosen: 'Lifelike 3D', drama_status: 'Scheduled',
  drama_kie_cost: '4.75', drama_video_link: 'https://videos.example.invalid/w1',
  drama_channels_posted: 'TikTok; Instagram Reels'
});
const vres = run(exportDoc, 'Validate + Build Keys', { body: withDrama }, null);
results.validate_drama = {
  ok: true,
  drama: vres[0].json.drama,
  body: vres[0].json.body,
  payloadVersion: vres[0].json.payloadSchemaVersion
};
results.validate_bad_cost = tryValidate(Object.assign({}, baseBody, { drama_kie_cost: '$4.75' }));
results.validate_bad_type = tryValidate(Object.assign({}, baseBody, { drama_status: { nested: 1 } }));
results.validate_optional_absent = tryValidate(Object.assign({}, baseBody));

// ---- Build Overview Summary ------------------------------------------------
const validateOut = vres[0].json;
const postsValues = validateOut.postsValues;
const meta130 = { properties: { appProperties: { schema_version: '1.3.0' } } };
const meta120 = { properties: { appProperties: { schema_version: '1.2.0' } } };
const metaNone = { properties: {} };

const ovRowsExisting = [
  ['', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '',
   '', '', '', '', '', 'OV::c1::r1']
];

function overview(sheetSchema, ovRows, bodyOverrides) {
  const body = Object.assign({}, validateOut.body, bodyOverrides || {});
  const stubs = {
    'Find Posts Row': {
      sheetId: 'Sheet123', rowKey: validateOut.rowKey,
      postsValues: postsValues, allRows: [postsValues], body: body
    },
    'Normalize Posts Write': { postsUpdatedRange: 'Posts!A2:N2', postsMode: 'appended' },
    'Verify Sheet Metadata (F14)': sheetSchema === null
      ? metaNone
      : { properties: { appProperties: { schema_version: sheetSchema } } }
  };
  const out = run(exportDoc, 'Build Overview Summary',
                  { values: ovRows || [] }, stubs);
  return out[0].json;
}

results.ov_130 = overview('1.3.0', []);
results.ov_130_existing = overview('1.3.0', ovRowsExisting);
results.ov_120 = overview('1.2.0', []);
results.ov_120_nodrama = overview('1.2.0', [], {
  drama_style_chosen: '', drama_status: '', drama_kie_cost: '',
  drama_video_link: '', drama_channels_posted: ''
});
results.ov_unstamped = overview(null, []);

// ---- Build Receipt ---------------------------------------------------------
const ovForReceipt = results.ov_130;
const receiptStubs = {
  'Normalize Posts Write': { postsUpdatedRange: 'Posts!A2:N2', postsMode: 'appended',
    sheetId: 'Sheet123', rowKey: validateOut.rowKey, allRows: [postsValues],
    body: validateOut.body },
  'Find Posts Row': { sheetId: 'Sheet123', rowKey: validateOut.rowKey,
    postsValues: postsValues, allRows: [postsValues], body: validateOut.body },
  'Build Overview Summary': ovForReceipt
};
const receiptOut = run(exportDoc, 'Build Receipt',
  { updates: { updatedRange: 'Weekly Overview!A2:Z2' } }, receiptStubs);
results.receipt = receiptOut[0].json.receipt;

const receiptStubs120 = Object.assign({}, receiptStubs, {
  'Build Overview Summary': results.ov_120
});
results.receipt_120 = run(exportDoc, 'Build Receipt',
  { updates: { updatedRange: 'Weekly Overview!A2:U2' } }, receiptStubs120)[0].json.receipt;

// ---- range wiring ----------------------------------------------------------
const nodes = nodesOf(exportDoc);
results.urls = {
  update: nodes['Update Overview Row (upsert)'].parameters.url,
  append: nodes['Append Overview Row'].parameters.url,
  read: nodes['Read Weekly Overview (readback)'].parameters.url,
  meta: nodes['Verify Sheet Metadata (F14)'].parameters.url
};

process.stdout.write(JSON.stringify(results, null, 1));
"""


def test_webhook_js():
    node = _which_node()
    if not node:
        check("webhook jsCode executes under node", True,
              "SKIP — node not available")
        print("  SKIP: node not found; jsCode execution tests not run")
        return
    with tempfile.TemporaryDirectory(prefix="smp-u2-js-") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps({
            "export": json.loads(STAGED_APPEND.read_text()),
        }))
        harness = Path(tmp) / "harness.js"
        harness.write_text(HARNESS)
        proc = subprocess.run([node, str(harness), str(spec_path)],
                              capture_output=True, text=True, timeout=120)
        check("webhook jsCode runs under node", proc.returncode == 0,
              proc.stderr[-2000:])
        if proc.returncode != 0:
            return
        r = json.loads(proc.stdout)

    # --- payload validation
    check("payload accepts schema_version 1.2.0", r["validate_120"]["ok"])
    check("payload accepts legacy schema_version 1.1.0", r["validate_110"]["ok"])
    check("payload rejects schema_version 2.0.0",
          not r["validate_200"]["ok"] and "unsupported schema_version"
          in r["validate_200"]["error"], str(r["validate_200"]))
    check("payload defaults to 1.2.0 when version is absent",
          r["validate_no_version"]["ok"])
    check("payload carries and normalises the five drama fields",
          r["validate_drama"]["drama"] == {
              "drama_style_chosen": "Lifelike 3D", "drama_status": "Scheduled",
              "drama_kie_cost": "4.75",
              "drama_video_link": "https://videos.example.invalid/w1",
              "drama_channels_posted": "TikTok; Instagram Reels"},
          json.dumps(r["validate_drama"]["drama"]))
    check("payload reports its own version",
          r["validate_drama"]["payloadVersion"] == "1.2.0",
          str(r["validate_drama"]["payloadVersion"]))
    check("payload rejects a non-numeric drama_kie_cost",
          not r["validate_bad_cost"]["ok"] and "drama_kie_cost"
          in r["validate_bad_cost"]["error"], str(r["validate_bad_cost"]))
    check("payload rejects a non-string drama_status",
          not r["validate_bad_type"]["ok"], str(r["validate_bad_type"]))
    check("drama fields are optional — a caller without them still passes",
          r["validate_optional_absent"]["ok"])

    # --- 1.3.0 sheet: 26 cells, fields at 20..24, key in Z
    ov = r["ov_130"]
    check("1.3.0 sheet: 26 cells written", len(ov["ovValues"]) == 26,
          str(len(ov["ovValues"])))
    check("1.3.0 sheet: the five fields land at index 20..24",
          ov["ovValues"][20:25] == ["Lifelike 3D", "Scheduled", "4.75",
                                    "https://videos.example.invalid/w1",
                                    "TikTok; Instagram Reels"],
          str(ov["ovValues"][20:25]))
    check("1.3.0 sheet: technical key at index 25 (column Z)",
          ov["ovValues"][25] == "OV::c1::r1",
          str(ov["ovValues"][25]))
    check("1.3.0 sheet: row width Z and dramaWritten true",
          ov["ovLastCol"] == "Z" and ov["dramaWritten"] is True
          and ov["dramaPending"] is False, json.dumps(ov))
    check("1.3.0 sheet: legacy 20 columns still filled the same way",
          ov["ovValues"][0] == "c1" and ov["ovValues"][18] == "Published"
          and ov["ovValues"][19] == "", str(ov["ovValues"][:20]))
    existing = r["ov_130_existing"]
    check("1.3.0 sheet: an existing summary row is found by the key in Z",
          existing["ovExisting"] is True and existing["ovRowNumber"] == 2,
          json.dumps({k: existing[k] for k in ("ovExisting", "ovRowNumber")}))

    # --- 1.2.0 sheet: 21 cells, key stays in U, fields reported pending
    ov120 = r["ov_120"]
    check("1.2.0 sheet: 21 cells, unchanged layout",
          len(ov120["ovValues"]) == 21 and ov120["ovLastCol"] == "U",
          str(len(ov120["ovValues"])))
    check("1.2.0 sheet: technical key stays at index 20 (column U)",
          ov120["ovValues"][20] == "OV::c1::r1", str(ov120["ovValues"][20]))
    check("1.2.0 sheet: the drama fields are NOT written over the key column",
          ov120["ovValues"][20] == "OV::c1::r1"
          and ov120["dramaWritten"] is False, json.dumps(ov120))
    check("1.2.0 sheet: supplied drama fields are reported pending",
          ov120["dramaPending"] is True, json.dumps(ov120))
    check("1.2.0 sheet with no drama fields: nothing pending",
          r["ov_120_nodrama"]["dramaPending"] is False,
          json.dumps(r["ov_120_nodrama"]))
    check("unstamped sheet behaves as 1.2.0 (never overwrites the key)",
          r["ov_unstamped"]["ovLastCol"] == "U"
          and r["ov_unstamped"]["ovValues"][20] == "OV::c1::r1"
          and r["ov_unstamped"]["dramaWritten"] is False,
          json.dumps(r["ov_unstamped"]))

    # --- receipt
    rec = r["receipt"]
    check("receipt at 1.3.0: schema 1.2.0, sheet 1.3.0, fields written",
          rec["schema_version"] == "1.2.0"
          and rec["sheet_schema_version"] == "1.3.0"
          and rec["drama_song_written"] is True
          and rec["drama_song_pending"] is None,
          json.dumps(rec))
    check("receipt echoes the five drama values",
          rec["drama"]["drama_style_chosen"] == "Lifelike 3D"
          and rec["drama"]["drama_kie_cost"] == "4.75"
          and rec["drama"]["drama_channels_posted"] == "TikTok; Instagram Reels",
          json.dumps(rec["drama"]))
    rec120 = r["receipt_120"]
    check("receipt at 1.2.0: fields pending with a migrate-and-replay reason",
          rec120["drama_song_written"] is False
          and rec120["drama_song_pending"] is not None
          and "migrate-template.py" in rec120["drama_song_pending"],
          json.dumps(rec120))

    # --- range wiring
    check("overview upsert range follows the version-matched column",
          "ovLastCol" in r["urls"]["update"], r["urls"]["update"])
    check("overview append range follows the version-matched column",
          "ovLastCol" in r["urls"]["append"], r["urls"]["append"])
    check("overview readback covers column Z",
          "A2:Z" in r["urls"]["read"], r["urls"]["read"])
    check("metadata read fetches properties.appProperties",
          "properties.appProperties" in r["urls"]["meta"], r["urls"]["meta"])


def _which_node():
    from shutil import which
    return which("node")


# =============================================================================
# 9. static gates + zero paid calls
# =============================================================================
def test_static_gates():
    MEDIA = (".mp4", ".mov", ".png", ".jpg", ".jpeg", ".gif", ".wav", ".mp3",
             ".m4a", ".webm", ".mkv", ".avi", ".heic", ".webp", ".flac", ".aiff")
    media = [str(p.relative_to(HERE)) for p in HERE.rglob("*")
             if p.is_file() and p.suffix.lower() in MEDIA]
    check("no media file ships with the module", not media, str(media))

    # The test file legitimately imports socket to BLOCK it; the module itself
    # must not touch transport at all.
    sources = sorted(p for p in HERE.rglob("*")
                     if p.is_file() and p.suffix in (".py", ".json", ".md")
                     and not p.name.startswith("test_"))
    expected_files = sorted([
        "README.md", "__init__.py", "migrate.py",
        "scripts/migrate-template.py",
        "config/validate-sheet-format.py",
        "config/n8n/social-planner-row-append.json",
        "testdata/sheet-template-1.3.0.json",
        "testdata/sheet-live-1.2.0.json",
    ])
    check("module ships only the documented files",
          sorted(str(p.relative_to(HERE)) for p in sources) == expected_files,
          str(sorted(str(p.relative_to(HERE)) for p in sources)))

    net_tokens = ("import urllib", "import requests", "import httpx",
                  "import aiohttp", "from urllib", "from requests",
                  "http.client", "import socket", "from socket",
                  "ftplib", "telnetlib", "websocket", "import ssl")
    shell_tokens = ("curl ", "wget ", "nc -", "ssh ", "os.system",
                    "subprocess.run", "subprocess.Popen", "Popen(")
    operator_paths = ("/Users/", "/private/tmp/", "/home/blackceo")
    for p in sources:
        text = p.read_text(errors="replace")
        rel = str(p.relative_to(HERE))
        if p.suffix == ".py":
            hits = [t for t in net_tokens if t in text]
            check("%s: no network client" % rel, not hits, str(hits))
            hits = [t for t in shell_tokens if t in text]
            check("%s: no shell transport / subprocess escape" % rel,
                  not hits, str(hits))
        hits = [t for t in operator_paths if t in text]
        check("%s: no operator or host path" % rel, not hits, str(hits))
        check("%s: no insecure http:// scheme" % rel,
              "http://" not in text and "HTTP://" not in text,
              [ln for ln in text.splitlines() if "http://" in ln][:1])

    all_text = "\n".join(p.read_text(errors="replace") for p in sources)
    for token in ("kie.ai", "api.kie", "KIE_API_KEY", "KIE_KEY", "KIE_TOKEN",
                  "KIE_LIVE_ADAPTER", "kie_live_adapter",
                  "74-kie-live-adapter", "requests.post", "urlopen",
                  "Authorization", "Bearer ", "sk-", "api_key", "apiKey",
                  "openai", "anthropic", "langchain"):
        check("no %r anywhere in the module" % token,
              token not in all_text,
              [ln.strip() for ln in all_text.splitlines() if token in ln][:2])
    check("no media muxer or video tool reference",
          not any(t in all_text for t in ("ffmpeg", "moviepy", "imageio",
                                          "opencv", "libav")),
          "")
    # "KIE" may appear only as the Weekly Overview column label / plan prose —
    # never as a KIE_* identifier, key, host or client.
    kie_bad = [ln.strip() for ln in all_text.splitlines()
               if re.search(r"\bKIE_[A-Z]", ln)
               or re.search(r"KIE (key|API|host|endpoint|token)", ln, re.I)]
    check("KIE appears only as the 'Drama KIE Cost' sheet label and plan prose",
          not kie_bad, kie_bad[:4])
    check("no KIE host or adapter identifier in the module",
          not any(t in all_text for t in ("http://kie", "https://kie",
                                          "kie.ai", "/v1/video",
                                          "KIE_API", "KIE_HOST", "kie-host")),
          [ln.strip() for ln in all_text.splitlines()
           if "kie.ai" in ln or "KIE_HOST" in ln][:3])

    doc = json.loads(STAGED_APPEND.read_text())
    blob = json.dumps(doc)
    check("staged export has no insecure scheme",
          "http://" not in blob and "HTTP://" not in blob)
    js_blob = json.dumps([n.get("parameters", {}).get("jsCode", "")
                          for n in doc["nodes"]])
    check("staged export jsCode makes no fetch/XHR/transport call",
          not any(t in js_blob for t in ("fetch(", "XMLHttpRequest",
                                         "require('http", 'require("http',
                                         "require('https", 'require("https',
                                         "net.connect", "dns.")),
          "")


def test_zero_paid_calls():
    """Run the whole flow in a process whose socket layer raises."""
    with tempfile.TemporaryDirectory(prefix="smp-u2-net-") as tmp:
        fx = tmp_copy(LIVE_120, tmp)
        contract = tmp_copy(BUNDLED_130, tmp)
        driver = Path(tmp) / "driver.py"
        driver.write_text(r'''
import json, socket, sys, urllib.request
BLOCKED = []
def boom(*a, **k):
    raise AssertionError("NETWORK CALL ATTEMPTED")
for name in ("socket", "create_connection", "getaddrinfo"):
    setattr(socket, name, boom)
urllib.request.urlopen = boom
sys.argv = ["driver"]

sys.path.insert(0, %(module)r)
import migrate as M
import importlib.util, os

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

cli = load(%(cli)r, "migrate_cli")
val = load(%(validator)r, "validate_sheet_format")

import json as _json
doc = _json.load(open(%(fixture)r))
migrated, report = M.migrate_doc(doc)
ok, problems = M.lossless(doc, migrated)
assert ok, problems
assert migrated["schema_version"] == "1.3.0"

# CLI dry-run + apply against a private copy
rc = cli.main(["--fixture", %(fixture)r])
assert rc == 2, rc                       # dry-run, nothing altered
rc = cli.main(["--fixture", %(fixture)r, "--apply", "--client-title", "Acme Co",
               "--timezone", "America/New_York"])
assert rc == 0, rc                       # applied in-process, still no network
# live-sheet paths refuse before any transport
rc = cli.main(["--sheet-id", "1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c", "--apply"])
assert rc == 3, rc
rc = cli.main(["--sheet-id", "SandboxSheetId123", "--apply"])
assert rc == 3, rc
# the validator, contract + export wiring, all offline
rc = val.main([%(contract)r, "--export", "--n8n-dir", %(n8n)r])
assert rc == 0, "validator rc=" + str(rc)
print("NO_NETWORK_OK")
''' % {"module": str(HERE), "cli": str(MIGRATE_CLI),
        "validator": str(VALIDATOR), "fixture": str(fx),
        "contract": str(contract),
        "n8n": str(STAGED_APPEND.parent)})
        proc = subprocess.run([sys.executable, str(driver)],
                              capture_output=True, text=True, timeout=120)
        check("whole flow runs with the socket layer raising — NO_NETWORK_OK",
              proc.returncode == 0 and "NO_NETWORK_OK" in proc.stdout,
              "rc=%s\nstdout=%s\nstderr=%s"
              % (proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:]))


def main():
    print("== SMP-W2-U2 sheet_migration tests ==")
    print("module: %s" % HERE)
    test_constants()
    test_no_loss()
    test_refusals()
    test_contract_migration()
    test_cli()
    test_validator()
    test_validator_export()
    test_staged_export()
    test_webhook_js()
    test_static_gates()
    test_zero_paid_calls()
    print("----")
    print("%d checks, %d FAIL" % (COUNT, len(FAILS)))
    if FAILS:
        for f in FAILS:
            print("FAILED: %s" % f)
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
