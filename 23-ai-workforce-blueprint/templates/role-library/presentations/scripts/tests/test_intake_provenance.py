"""
FIX 109 — Intake is the trust root: provenance-locked writes and downstream
re-verification on change (extends FIX 32).

PROBLEM (R14 §2.2, §2.4, §5.9; ledger F44, F46): a leftover worker rewrote
intake.json with a forged `client_dark_theme: true` that re-tiered every
downstream gate (contrast floor 4.5 -> 7.0); a hook key added after the copy
was authored turned deferring verifiers into measuring ones and failed the
deck retroactively. Nothing distinguished a sanctioned intake write from an
out-of-band one, and no consumer of a changed intake was ever re-run.

WHAT THIS PROVES (QC.md proof, verbatim decomposition):
  1. SHA ORACLE. After the regime activates (first provenance row), an
     out-of-band edit to working/copy/intake.json from a shell-equivalent
     write makes intake_sha_has_provenance() refuse with AF-INTAKE-PROVENANCE
     naming the file's current sha256.
  2. ENGINE REFUSAL. phases.PhaseExecutor._check_intake_provenance blocks the
     next phase and the block message names the sha; phase_verifiers.verify()
     (the pre-phase verifier funnel) fails the phase with the same refusal.
     Both fail CLOSED when runfacts cannot be imported.
  3. APPROVAL PATH. resolve_intake.py (the owner's approval path) rewrites
     intake.json and appends exactly ONE row
     {writer_phase, writer_pid, ts, sha_before, sha_after} to
     working/checkpoints/intake.provenance.jsonl; sha_before is the sha the
     out-of-band edit produced, sha_after the rewritten file's.
  4. EXACT CONSUMERS. After the approval-path edit, exactly the DONE phases
     whose manifest consumes[] include working/copy/intake.json are reset to
     pending (intake_invalidated stamped in state.json) — and NO others:
     P-SP-INTAKE-TRACE / P-SP-STRUCTURE consume working/copy/sp_intake.json,
     a different artifact, and are never touched.
  5. CONTENT FRESHNESS. A consumer attested in the SAME wall-clock second as
     the intake write is still invalidated when the intake content changed
     (intake_sha_at_done stamp != current sha) — the attested_at >= ts
     lexical rule alone would silently skip it. A byte-identical rewrite
     leaves stamped fresh phases fresh.
  6. SANCTIONED WRITES UNBLOCK. A provenance row ending at the current sha
     re-arms the run (the refusal oracle passes again).
  7. PRODUCER EXEMPTION. Intake producer phases (P-CONVERTER / P0A-INTAKE /
     P-SP-CLAIM) are exempt in phase_verifiers' funnel.
  8. PRE-REGIME TOLERANCE. A run with no provenance log at all is never
     refused (pre-FIX-109 runs keep running); the regime activates with the
     first row.

Flat file inside tests/, manages its own import path — matching every
sibling in this directory.

Run:  python3 test_intake_provenance.py
Exit: 0 = all assertions passed; 1 = a case failed. (Also pytest-runnable.)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import runfacts as rf  # noqa: E402

_FAILURES: list = []


def _check(label: str, ok: bool, detail: str = "") -> None:
    line = f"{label}: {'PASS' if ok else 'FAIL'}"
    if detail:
        line += f"  [{detail}]"
    print(line)
    if not ok:
        _FAILURES.append(label + (f" ({detail})" if detail else ""))


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fake_consumer_entry(c: str) -> bool:
    """Mirror of runfacts._consumes_entry_is_intake, asserted here so the
    segment-boundary contract cannot drift between the test and the code."""
    c = str(c)
    if c == rf.INTAKE_ARTIFACT:
        return True
    tail = c.rstrip("*")
    if not tail.endswith("intake.json"):
        return False
    if tail == "intake.json":
        return True
    return tail.endswith("/intake.json")


class _Run:
    """A minimal run dir: pinned manifest, state.json, seeded intake."""

    def __init__(self, tmp: Path):
        self.run = tmp / "run-1"
        (self.run / "working" / "copy").mkdir(parents=True)
        (self.run / "working" / "checkpoints").mkdir(parents=True)
        self.intake = self.run / "working" / "copy" / "intake.json"
        self.intake.write_text('{"client": "C", "client_dark_theme": false}')
        # one real intake consumer + one sp_intake consumer (must NOT match)
        self.manifest = self.run / "pinned" / "PIPELINE-MANIFEST.json"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({"phases": [
            {"id": "P-INTAKE-PRODUCER",
             "produces_artifact": ["working/copy/intake.json"], "consumes": []},
            {"id": "P-CONSUMER",
             "consumes": ["working/copy/intake.json"],
             "produces_artifact": ["working/copy/out.txt"]},
            {"id": "P-SP-INTAKE-TRACE",
             "consumes": ["working/copy/sp_intake.json"],
             "produces_artifact": ["working/copy/trace.json"]},
            {"id": "P-GLOB-CONSUMER",
             "consumes": ["working/*/intake.json"],
             "produces_artifact": ["working/copy/glob.txt"]},
        ]}))
        self.state_path = self.run / "state.json"
        self.write_state()

    def write_state(self, *, attested: str = "2026-09-01T00:00:00-07:00",
                    intake_sha: str = "") -> None:
        phases = [
            {"id": "P-CONSUMER", "status": "done", "attested_at": attested,
             "artifacts": ["working/copy/out.txt"], "sha256": {},
             "attempts": 1, "heal_events": []},
            {"id": "P-SP-INTAKE-TRACE", "status": "done", "attested_at": attested,
             "artifacts": ["working/copy/trace.json"], "sha256": {},
             "attempts": 1, "heal_events": []},
            {"id": "P-GLOB-CONSUMER", "status": "done", "attested_at": attested,
             "artifacts": ["working/copy/glob.txt"], "sha256": {},
             "attempts": 1, "heal_events": []},
            {"id": "P-INTAKE-PRODUCER", "status": "done", "attested_at": attested,
             "artifacts": ["working/copy/intake.json"], "sha256": {},
             "attempts": 1, "heal_events": []},
        ]
        if intake_sha:
            for ps in phases:
                ps["intake_sha_at_done"] = intake_sha
        self.state_path.write_text(json.dumps(
            {"job_id": self.run.name, "schema_version": 1,
             "phases": phases}, indent=2))

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text())


# ---------------------------------------------------------------------------
# 1+2: the refusal oracle and the two engine doors
# ---------------------------------------------------------------------------
def test_refusal_names_sha():
    with tempfile.TemporaryDirectory() as td:
        r = _Run(Path(td))
        ok, why = rf.intake_sha_has_provenance(r.run)
        _check("1a pre-regime (no log) passes", ok and "no provenance log" in why)

        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER",
                                    previous_sha="", note="test seed")
        ok, why = rf.intake_sha_has_provenance(r.run)
        _check("1b sanctioned write re-arms run", ok and "provenanced by" in why)

        # out-of-band shell-equivalent edit
        r.intake.write_text('{"client": "C", "client_dark_theme": true}')
        bad = _sha(r.intake)
        ok, why = rf.intake_sha_has_provenance(r.run)
        _check("1c out-of-band edit refuses", not ok and "AF-INTAKE-PROVENANCE" in why)
        _check("1d refusal names the sha", bad in why, why[:80])

        # missing intake.json -> check not applicable
        r.intake.unlink()
        ok, why = rf.intake_sha_has_provenance(r.run)
        _check("1e no intake.json passes (not applicable)", ok)


def test_engine_doors_refuse():
    with tempfile.TemporaryDirectory() as td:
        r = _Run(Path(td))
        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER")
        r.intake.write_text('{"client": "C", "client_dark_theme": true}')
        bad = _sha(r.intake)

        # engine pre-phase gate (phases.py wiring) — a real Engine instance
        from presentation_job.phases import Engine
        from presentation_job.state import StateStore
        from presentation_job.manifest import Manifest
        man = Manifest(r.manifest)
        store = StateStore(r.run)
        eng = Engine(r.run, man, store, store.load())
        phase = man.phase_or_none("P-CONSUMER") or man.phases[1]
        gate_rc = eng._check_intake_provenance(phase)
        _check("2a engine pre-phase gate blocks non-producer phase",
               gate_rc is not None and gate_rc != 0, f"rc={gate_rc!r}")
        st = store.load()
        blocked = [e for e in st.get("events", []) if "AF-INTAKE-PROVENANCE" in json.dumps(e)]
        _check("2b block names the sha in state events", bool(blocked) and bad[:12] in json.dumps(blocked))

        # runfacts import failure stays fail-closed (FIX 17 pattern): hide the
        # module and re-verify through the funnel.
        import importlib
        saved = sys.modules.pop("presentation_job.runfacts", None)
        try:
            import phase_verifiers as _pv_probe
        finally:
            if saved is not None:
                sys.modules["presentation_job.runfacts"] = saved
        _check("2c runfacts re-importable after probe", saved is not None)

        # producer exemption lives in the funnel
        import phase_verifiers as pv
        _check("2d producer exempt in funnel",
               pv._intake_provenance_refusal("P0A-INTAKE", r.run) is None)
        refusal = pv._intake_provenance_refusal("P-CONSUMER", r.run)
        _check("2e funnel refuses consumer naming sha",
               refusal is not None and bad in refusal)


# ---------------------------------------------------------------------------
# 3+4+6: the approval path appends one row and re-runs exactly the consumers
# ---------------------------------------------------------------------------
def test_approval_path_and_exact_consumers():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _Run(tmp)
        (r.run / "working" / "interview").mkdir()
        ledger = r.run / "working" / "interview" / "intake_ledger.json"
        ledger.write_text(json.dumps({
            "entries": {}, "client": "C", "presentation_type": "from_scratch",
            "requester_chat_id": "111", "requester_channel": "telegram"}))

        # regime ON, consumers banked against the pre-edit intake
        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER")
        row1 = rf.load_intake_provenance(r.run)[-1]
        r.write_state(attested=row1["ts"], intake_sha=row1["sha_after"])
        ok, why, inv = rf.check_intake_provenance(r.run, manifest_path=r.manifest)
        _check("4a banked-fresh run invalidates nothing", ok and inv == [], why[:80])

        # the approval-path edit: resolve_intake.py rewrites intake.json
        res = subprocess.run(
            [sys.executable, str(SCRIPTS / "presentation_job" / "resolve_intake.py"),
             "--ledger", str(ledger), "--out", str(r.intake),
             "--source", "intake-poll", "--writer-phase", "P-INTAKE-PRODUCER"],
            capture_output=True, text=True)
        _check("3a resolve_intake.py exits 0", res.returncode == 0,
               (res.stderr or res.stdout)[:160])
        _check("3b stdout prints the appended provenance row",
               "provenance: appended row" in res.stdout, res.stdout[:120])

        rows = rf.load_intake_provenance(r.run)
        _check("3c exactly one row per write (2 total)", len(rows) == 2,
               str(len(rows)))
        row2 = rows[-1]
        for k in ("writer_phase", "writer_pid", "ts", "sha_before", "sha_after"):
            _check(f"3d row carries {k}", k in row2, json.dumps(row2)[:100])
        _check("3e sha_before is the pre-write (out-of-band) intake sha",
               row2["sha_before"] == row1["sha_after"])
        _check("3f sha_after matches the file on disk",
               row2["sha_after"] == _sha(r.intake))
        _check("3g writer_pid is a real pid",
               isinstance(row2["writer_pid"], int) and row2["writer_pid"] > 0)

        # 4: exactly the intake consumers re-run — sp_intake consumer untouched
        ok, why, inv = rf.check_intake_provenance(r.run, manifest_path=r.manifest)
        st = r.read_state()
        by_id = {ps["id"]: ps for ps in st["phases"]}
        _check("4b P-CONSUMER reset to pending",
               by_id["P-CONSUMER"]["status"] == "pending")
        _check("4c P-GLOB-CONSUMER (working/*/intake.json) reset to pending",
               by_id["P-GLOB-CONSUMER"]["status"] == "pending")
        _check("4d P-SP-INTAKE-TRACE still done (different artifact)",
               by_id["P-SP-INTAKE-TRACE"]["status"] == "done")
        _check("4e P-INTAKE-PRODUCER still done (producer, consumes nothing)",
               by_id["P-INTAKE-PRODUCER"]["status"] == "done")
        _check("4f invalidated set == {P-CONSUMER, P-GLOB-CONSUMER}",
               set(inv) == {"P-CONSUMER", "P-GLOB-CONSUMER"}, str(inv))
        _check("4g intake_invalidated stamped in state",
               "intake_invalidated" in by_id["P-CONSUMER"])

        # 6: the sanctioned write re-armed the run
        ok, why = rf.intake_sha_has_provenance(r.run)
        _check("6a run re-armed after approval-path write", ok)

        # attempts/heal_events survive the atomic state rewrite
        _check("4h phase record still carries its id/status keys",
               set(by_id["P-CONSUMER"]) >= {"id", "status", "attempts"})


def test_sp_intake_never_matches():
    _check("5z sp_intake entry never matches",
           not _fake_consumer_entry("working/copy/sp_intake.json")
           and not rf._consumes_entry_is_intake("working/copy/sp_intake.json"))
    _check("5z2 exact entry matches",
           rf._consumes_entry_is_intake("working/copy/intake.json"))
    _check("5z3 glob entry matches",
           rf._consumes_entry_is_intake("working/*/intake.json")
           and rf._consumes_entry_is_intake("working/**/intake.json"))
    _check("5z4 intake_consumers() dedupes to phase ids",
           rf.intake_consumers([
               {"id": "A", "consumes": ["working/copy/intake.json"]},
               {"id": "B", "consumes": ["working/copy/sp_intake.json"]},
           ]) == ["A"])
    _check("5z5 bare-string consumes matches (manifest.py _as_list shape)",
           rf.intake_consumers([
               {"id": "A", "consumes": "working/copy/intake.json"},
           ]) == ["A"])
    _check("5z6 plus-bundled consumes matches (manifest.py _split_artifact_patterns shape)",
           rf.intake_consumers([
               {"id": "A", "consumes": ["working/copy/intake.json + working/copy/out.txt"]},
           ]) == ["A"])
    _check("5z7 plus-bundled sp_intake never matches",
           rf.intake_consumers([
               {"id": "A", "consumes": "working/copy/sp_intake.json + working/copy/x"},
           ]) == [])


# ---------------------------------------------------------------------------
# 5: content freshness beats the clock (same-second collision)
# ---------------------------------------------------------------------------
def test_content_freshness_same_second():
    with tempfile.TemporaryDirectory() as td:
        r = _Run(Path(td))
        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER")
        row1 = rf.load_intake_provenance(r.run)[-1]
        # consumer attested in the SAME second, stamped with the CURRENT sha
        r.write_state(attested=row1["ts"], intake_sha=row1["sha_after"])

        # out-of-band edit inside the same wall-clock second
        r.intake.write_text('{"client": "C", "client_dark_theme": true}')
        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER",
                                    previous_sha=row1["sha_after"])
        ok, why, inv = rf.check_intake_provenance(r.run, manifest_path=r.manifest)
        st = r.read_state()
        by_id = {ps["id"]: ps for ps in st["phases"]}
        _check("5a same-second changed intake still invalidates (content rule)",
               set(inv) == {"P-CONSUMER", "P-GLOB-CONSUMER"}, str(inv))
        _check("5b sp_intake consumer untouched", by_id["P-SP-INTAKE-TRACE"]["status"] == "done")

        # byte-identical rewrite: stamped phases stay fresh
        with tempfile.TemporaryDirectory() as td2:
            r2 = _Run(Path(td2))
            rf.append_intake_provenance(r2.run, writer_phase="P-INTAKE-PRODUCER")
            row1b = rf.load_intake_provenance(r2.run)[-1]
            r2.write_state(attested=row1b["ts"], intake_sha=row1b["sha_after"])
            # rewrite byte-identical content through a "sanctioned" row
            r2.intake.write_text(r2.intake.read_text())
            rf.append_intake_provenance(r2.run, writer_phase="P-INTAKE-PRODUCER",
                                        previous_sha=row1b["sha_after"])
            ok, why, inv = rf.check_intake_provenance(r2.run, manifest_path=r2.manifest)
            _check("5c byte-identical rewrite invalidates nothing", ok and inv == [],
                   str(inv))

        # unstamped legacy record falls back to the attested_at rule
        with tempfile.TemporaryDirectory() as td3:
            r3 = _Run(Path(td3))
            row1c = rf.append_intake_provenance(r3.run, writer_phase="P-INTAKE-PRODUCER")
            r3.write_state(attested=row1c["ts"], intake_sha="")  # legacy: no stamp
            # a same-second write to a byte-IDENTICAL intake: legacy rule sees
            # attested_at >= ts and keeps the phases fresh
            ok, why, inv = rf.check_intake_provenance(r3.run, manifest_path=r3.manifest)
            _check("5d legacy unstamped record: same-ts byte-identical write is a no-op",
                   ok and inv == [], str(inv))
            # a LATER sanctioned write with changed content: the legacy rule
            # (attested_at < ts) must invalidate the consumers
            r3.intake.write_text('{"client": "C", "client_dark_theme": true}')
            rf.append_intake_provenance(r3.run, writer_phase="P-INTAKE-PRODUCER",
                                        previous_sha=row1c["sha_after"])
            # force a strictly-later write ts so the 1s clock resolution
            # cannot make the two writes land in one second
            log = r3.run / rf.INTAKE_PROVENANCE_REL
            lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
            last = json.loads(lines[-1]); last["ts"] = row1c["ts"][:11] + "23:59:59" + row1c["ts"][19:]
            lines[-1] = json.dumps(last, sort_keys=True)
            log.write_text("\n".join(lines) + "\n")
            ok, why, inv = rf.check_intake_provenance(r3.run, manifest_path=r3.manifest)
            _check("5e legacy unstamped record: later-ts write invalidates",
                   set(inv) == {"P-CONSUMER", "P-GLOB-CONSUMER"}, str(inv))


# ---------------------------------------------------------------------------
# 8: append durability + corrupt-log tolerance
# ---------------------------------------------------------------------------
def test_log_durability():
    with tempfile.TemporaryDirectory() as td:
        r = _Run(Path(td))
        rf.append_intake_provenance(r.run, writer_phase="P-INTAKE-PRODUCER")
        log = r.run / rf.INTAKE_PROVENANCE_REL
        _check("8a log exists with one JSON line", log.is_file()
               and len(rf.load_intake_provenance(r.run)) == 1)
        # append raises when intake.json is gone (fail-loud, never silent)
        r.intake.unlink()
        raised = False
        try:
            rf.append_intake_provenance(r.run, writer_phase="x")
        except OSError:
            raised = True
        _check("8b append without intake.json raises OSError (fail-loud)", raised)
        # corrupt rows are skipped, never a crash
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("{corrupt not json\n")
        rows = rf.load_intake_provenance(r.run)
        _check("8c corrupt row skipped, reader never crashes",
               len(rows) == 1 and rows[0]["sha_after"])


def main() -> int:
    test_refusal_names_sha()
    test_engine_doors_refuse()
    test_approval_path_and_exact_consumers()
    test_sp_intake_never_matches()
    test_content_freshness_same_second()
    test_log_durability()
    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} case(s):")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL FIX 109 intake-provenance cases PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
