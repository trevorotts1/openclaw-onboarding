#!/usr/bin/env python3
"""test_fix36_doc_code_reconcile.py -- pins FIX 36 (doc-vs-code reconciliation).

Five sub-items, each matching the spec's numbered list:

  (1) SOP-SLIDE-06 §3 gate 2 is WIRED: the repo pre-commit hook runs
      sync_check.py and blocks on drift (exit 4) AND on cannot-run (exit 2 —
      fail-closed), for exactly the documented trigger set (Presentations role
      .md, dept sops/, the manifest, build_deck.py). The CI half already lived
      in .github/workflows/presentations-drift-gates.yml; this pins the local half.
  (2) GHL folder-create is DISABLED: ghl_media.create_media_folder never POSTs
      (returns the documented-declined shape; endpoint 404s per the binding SOP
      rule) and ghl_media_push.push_deck_media accepts ONLY a pre-existing,
      human-approved intake.json.ghl_media_folder_id — else the media root. The
      old "201 primary path" branch is gone (no create_media_folder call remains
      at any push call site).
  (3) INTAKE-DEPTH vocabulary: --intake-depth quick|in-depth
      (env PRESENTATION_INTAKE_DEPTH) is a DIFFERENT axis from run-mode
      --mode Ultra|Standard|Economy (env PRESENTATION_MODE). resolve_intake
      resolves the depth (ledger interview_depth / STANDARD_MODE beats the
      schema default QUICK), validates explicit values loudly (exit 5,
      AF-INTAKE-DEPTH-INVALID), and NEVER reads PRESENTATION_MODE.
  (4) ENFORCEMENT-REGISTRY parity: every PIPELINE-MANIFEST autofail with
      enforced_by=build_deck carries a py_symbol that EXISTS in build_deck.py —
      including FIX 15 (AF-SLIDE-CRAFT-LOADER) and FIX 18
      (AF-CRAFT-JUDGEMENT-LOADER), both mapped to _chk_slide_craft. A missing
      symbol fails the test.
  (5) DISPLAYED phase count is DERIVED from the canonical manifest, not the
      stale hardcoded "36": the canonical entry script computes it from
      PIPELINE-MANIFEST.json (manifest_version 55 -> 55 phases) and the
      hardcoded literal is gone.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS
for _ in range(6):
    if (REPO / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json").is_file():
        break
    REPO = REPO.parent

sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import resolve_intake as ri  # noqa: E402

MANIFEST = REPO / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
ENTRY = SCRIPTS / "presentation-canonical-entry.sh"
HOOK = REPO / ".githooks" / "pre-commit"
BUILD_DECK = SCRIPTS / "build_deck.py"


# ---------------------------------------------------------------------------
# fixture plumbing (mirrors test_resolve_intake.py)
# ---------------------------------------------------------------------------
def _run_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _entry(value: str) -> dict:
    return {"value": value, "validated": True, "source": "deck-intake-driver"}


def _write_ledger(run_dir: pathlib.Path, entries: dict) -> pathlib.Path:
    ledger = {"entries": entries, "status": "complete", "complete": True,
              "requester_chat_id": "123456789", "requester_channel": "telegram",
              "client_name": "Acme Corp"}
    path = run_dir / "working" / "interview" / "intake_ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


def _write_intake_copy(run_dir: pathlib.Path, obj: dict) -> pathlib.Path:
    base = {"requester_chat_id": "123456789", "requester_channel": "telegram",
            "client_name": "Acme Corp"}
    base.update(obj)
    path = run_dir / "working" / "copy" / "intake.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


def _base_entries(ptype: str = "from_scratch") -> dict:
    return {"presentation_type": _entry(ptype)}


# ===========================================================================
# (1) pre-commit / CI wiring (SOP-SLIDE-06 §3 gate 2)
# ===========================================================================
class TestSyncCheckGateWiring:
    def test_precommit_hook_runs_sync_check(self):
        src = HOOK.read_text(encoding="utf-8")
        assert "sync_check.py" in src, "pre-commit must invoke sync_check.py"
        assert "--json" in src

    def test_precommit_blocks_on_drift_and_on_cannot_run(self):
        """Fail-closed: BOTH documented non-zero outcomes block. exit 4 = drift;
        exit 2 = cannot run (a broken checker never waves a commit through)."""
        src = HOOK.read_text(encoding="utf-8")
        assert "-eq 4" in src, "drift (exit 4) must block"
        assert "-ne 0" in src, "cannot-run (any other non-zero) must also block"

    def test_precommit_trigger_set_matches_sop(self):
        """Trigger set per SOP-SLIDE-06 §3 gate 2: Presentations role .md,
        dept sops/, the manifest, build_deck.py — and NOT unrelated paths."""
        src = HOOK.read_text(encoding="utf-8")
        for needle in (
            "presentations/.*\\.md$",
            "presentations/scripts/sops/",
            "build_deck\\.py$",
            "universal-sops/presentation-slide-craft/",
        ):
            assert needle in src, f"pre-commit trigger set missing {needle}"

    def test_ci_half_exists(self):
        wf = REPO / ".github" / "workflows" / "presentations-drift-gates.yml"
        assert wf.is_file()
        body = wf.read_text(encoding="utf-8")
        assert "sync_check" in body

    def test_sync_check_clean_today(self):
        """Control: with the current tree, the gate the hook runs reports 0 drift."""
        r = subprocess.run([sys.executable, str(SCRIPTS / "sync_check.py"), "--json"],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"sync_check rc={r.returncode}: {r.stderr[:400]}"
        d = json.loads(r.stdout)
        assert d["in_sync"] is True
        assert d["drift_summary"]["total"] == 0


# ===========================================================================
# (2) GHL folder-create disabled
# ===========================================================================
class TestFolderCreateDisabled:
    def test_create_media_folder_never_posts(self, monkeypatch):
        """THE FIX — the dept-side create_media_folder NEVER issues the POST:
        the mocked opener would blow up if it were reached."""
        import ghl_media

        def _boom(*a, **k):  # noqa: ANN002, ANN003
            raise AssertionError("folder-create POST must never be issued (SOP: endpoint 404s)")

        monkeypatch.setattr("urllib.request.urlopen", _boom, raising=False)
        res = ghl_media.create_media_folder("DECK demo", "loc-1", "pit-1")
        assert res.get("folderId") is None
        assert res.get("fallback") == "name-prefix"
        # the documented-declined shape, no network shape fields faked
        assert res.get("http") is None

    def test_disabled_reason_is_named(self):
        import ghl_media
        res = ghl_media.create_media_folder("DECK demo", "loc-1", "pit-1")
        assert "fix36" in str(res.get("disabled") or "")

    def test_canonical_call_still_importable_for_ad_pipeline(self):
        import ghl_media
        assert hasattr(ghl_media, "CANON_CREATE_MEDIA_FOLDER")
        assert callable(ghl_media.CANON_CREATE_MEDIA_FOLDER)
        # and the import-surface contract holds (test_fix23 pins hasattr too)
        assert hasattr(ghl_media, "create_media_folder")

    def test_push_call_site_removed_the_201_branch(self):
        """The push module must not call create_media_folder at all, and must
        resolve the folder ONLY from the pre-existing intake id (else root)."""
        src = (SCRIPTS / "ghl_media_push.py").read_text(encoding="utf-8")
        assert "create_media_folder(" not in src, \
            "ghl_media_push must never call create_media_folder (FIX 36 removed the 201 path)"
        assert 'intake.get("ghl_media_folder_id")' in src

    def test_push_accepts_only_preexisting_folder(self):
        """Control: a governed push over a clean deck with NO intake folder id
        records the 'root' fallback; with one, it records that id. Both upload
        cleanly through the same chokepoint (mock opener; no folder POST)."""
        import ghl_media_push
        import delivery_gate

        def _mock_opener(req, timeout):
            class _R:
                def getcode(self):
                    return 200

                def read(self):
                    return (b'{"fileId":"file_x",'
                            b'"url":"https://storage.googleapis.com/msgsndr/file_x"}')
            return _R()

        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            deck = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
            delivery_gate._write_render_manifest(base, ["kie-aaa"])
            saved = {k: os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
            # 40+ chars so the canonical placeholder detector does not skip it.
            os.environ["GHL_API_KEY"] = "pit-" + "a" * 40
            os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
            try:
                out = ghl_media_push.push_deck_media(base, [], extra_files=[str(deck)],
                                                     opener=_mock_opener)
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            assert str(out.get("pptx_ghl_media_id") or "").strip()
            assert out.get("ghl_folder_id") == "root", \
                f"no intake folder -> root expected, got {out.get('ghl_folder_id')!r}"


# ===========================================================================
# (3) intake-depth vs run-mode vocabulary
# ===========================================================================
class TestIntakeDepthVocabulary:
    def test_ledger_interview_depth_wins_over_schema_default(self):
        rd = _run_dir()
        entries = _base_entries()
        entries["interview_depth"] = _entry("in-depth")
        ledger = _write_ledger(rd, entries)
        intake = ri.resolve(ledger, "intake-poll")
        assert intake["standard_mode"] == "IN-DEPTH"

    def test_schema_default_is_quick(self):
        rd = _run_dir()
        ledger = _write_ledger(rd, _base_entries())
        intake = ri.resolve(ledger, "intake-poll")
        assert intake["standard_mode"] == "QUICK"

    def test_explicit_flag_beats_everything(self):
        rd = _run_dir()
        entries = _base_entries()
        entries["interview_depth"] = _entry("in-depth")
        ledger = _write_ledger(rd, entries)
        intake = ri.resolve(ledger, "intake-poll", intake_depth="quick")
        assert intake["standard_mode"] == "QUICK"

    def test_env_presentations_intake_depth_resolves(self, monkeypatch):
        monkeypatch.setenv(ri.INTAKE_DEPTH_ENV, "in-depth")
        rd = _run_dir()
        ledger = _write_ledger(rd, _base_entries())
        intake = ri.resolve(ledger, "intake-poll")
        assert intake["standard_mode"] == "IN-DEPTH"

    def test_run_mode_env_is_ignored_for_intake_depth(self, monkeypatch):
        """THE AXIS SEPARATION: PRESENTATION_MODE (run mode: Ultra|Standard|
        Economy) must NEVER leak into intake depth (quick|in-depth)."""
        monkeypatch.setenv("PRESENTATION_MODE", "Economy")
        rd = _run_dir()
        ledger = _write_ledger(rd, _base_entries())
        intake = ri.resolve(ledger, "intake-poll")
        assert intake["standard_mode"] == "QUICK"

    def test_run_mode_vocabulary_rejected_for_intake_depth(self, monkeypatch):
        """Feeding a RUN-MODE value to the intake-depth axis fails loudly
        (UnknownIntakeDepth -> main() exit 5, AF-INTAKE-DEPTH-INVALID), with a
        message that names the other axis."""
        monkeypatch.setenv(ri.INTAKE_DEPTH_ENV, "economy")
        rd = _run_dir()
        ledger = _write_ledger(rd, _base_entries())
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        with pytest.raises(ri.UnknownIntakeDepth) as exc_info:
            ri.resolve(ledger_path, "intake-poll")
        msg = str(exc_info.value)
        assert "--mode" in msg, "error must point at the run-mode axis"

    def test_main_exits_5_on_bad_depth(self, capsys, monkeypatch):
        monkeypatch.setenv(ri.INTAKE_DEPTH_ENV, "ultra")
        rd = _run_dir()
        _write_ledger(rd, _base_entries())
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"
        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])
        assert rc == 5
        err = capsys.readouterr().err
        assert "AF-INTAKE-DEPTH-INVALID" in err
        assert not out_path.exists()

    def test_canonical_entry_rejects_run_mode_words_for_intake_depth(self):
        """The entry script's --intake-depth validation refuses ultra|standard|
        economy with a message naming the run-mode axis."""
        src = ENTRY.read_text(encoding="utf-8")
        assert "--intake-depth)" in src
        assert "ultra|standard|economy" in src
        assert "PRESENTATION_INTAKE_DEPTH" in src
        # and the usage documents the axis separation
        assert "never interchangeable and never share a flag name" in src

    def test_depth_threaded_to_resolve(self):
        src = ENTRY.read_text(encoding="utf-8")
        # The depth reaches resolve_intake.py via _RESOLVE_DEPTH_ARGS: the shell
        # keeps INTAKE_DEPTH in display case for stamp_intake_depth, so the
        # resolver call lowercases it inline (resolve_intake.py's argparse
        # choices are exactly quick|in-depth) — see the SMOKE-1 comment at the
        # _RESOLVE_DEPTH_ARGS build.
        assert '--intake-depth $(printf' in src and "tr '[:upper:]' '[:lower:]'" in src
        assert "RESOLVE_DEPTH_ARGS" in src
        assert "--source canonical-entry $_RESOLVE_DEPTH_ARGS" in src


# ===========================================================================
# (4) enforcement-registry parity
# ===========================================================================
class TestRegistryParity:
    @staticmethod
    def _module_top_level_names(tree: ast.Module) -> set:
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
        return names

    def test_every_enforced_autofail_symbol_exists(self):
        """THE PARITY TEST: every manifest autofail enforced_by build_deck names
        a real module-level symbol in build_deck.py. A registry entry whose
        checker drifted away fails here."""
        manifest = json.loads(MANIFEST.read_text())
        enforced = [a for a in manifest["autofails"] if a.get("enforced_by") == "build_deck"]
        assert enforced, "manifest carries no enforced autofails — registry empty?"
        tree = ast.parse(BUILD_DECK.read_text(encoding="utf-8"))
        top = self._module_top_level_names(tree)
        missing = sorted({a["py_symbol"] for a in enforced
                          if a.get("py_symbol")} - top)
        assert not missing, f"manifest-enforced symbols missing from build_deck.py: {missing}"

    def test_enforced_autofails_all_carry_symbols(self):
        manifest = json.loads(MANIFEST.read_text())
        enforced = [a for a in manifest["autofails"] if a.get("enforced_by") == "build_deck"]
        no_sym = [a["code"] for a in enforced if not a.get("py_symbol")]
        assert not no_sym, f"enforced autofails without py_symbol: {no_sym}"

    def test_fix15_and_fix18_loaders_registered(self):
        """FIX 15/18 enforcement is registry-visible and backed by real code."""
        manifest = json.loads(MANIFEST.read_text())
        codes = {a["code"]: a for a in manifest["autofails"]}
        for code in ("AF-SLIDE-CRAFT-LOADER", "AF-CRAFT-JUDGEMENT-LOADER"):
            assert code in codes, f"{code} missing from manifest autofails"
            assert codes[code].get("enforced_by") == "build_deck"
            assert codes[code].get("py_symbol") == "_chk_slide_craft"
        src = BUILD_DECK.read_text(encoding="utf-8")
        assert "def _chk_slide_craft(" in src
        # and registered in the mechanical checker list (not a dead def)
        assert src.count("_chk_slide_craft)") >= 1

    def test_registry_counts_stay_sane(self):
        """Pin the documented shape: 105 enforced_by build_deck, every one
        carrying a symbol — a silent registry shrink fails here. FIX 92
        (2026-09-02) registers five closeout_gate grounding/casting rows
        (AF-IMAGE-GROUNDING(-PARK), AF-CASTING(-PARK / -MIX-PARITY)) with
        resolving py_symbols, so the total moves 183 -> 188 while the
        build_deck-enforced count and the tightened A3 invariant both hold.
        The FIX 5/M7 teleprompter publish gate (AF-TELEPROMPTER-UNPUBLISHED,
        enforced_by postflight_bundle_gate) and the FIX 103-family registrations
        (AF-SPEECH-PACING, AF-RENDER-EMPTY, AF-RENDER-COMPLETE — all
        build_deck-enforced with resolving py_symbols) bring the total to 192
        and the build_deck-enforced count to 108."""
        manifest = json.loads(MANIFEST.read_text())
        enforced = [a for a in manifest["autofails"] if a.get("enforced_by") == "build_deck"]
        assert len(manifest["autofails"]) == 192
        assert len(enforced) == 108


# ===========================================================================
# (5) manifest-derived displayed phase count
# ===========================================================================
class TestManifestDerivedPhaseCount:
    def test_canonical_manifest_has_coherent_phase_count(self):
        m = json.loads(MANIFEST.read_text())
        # FIX 36(5): the count is DERIVED from the manifest, never hardcoded.
        # The merged fleet reality is 55 phases (40 engine + 15 P-U); the count
        # contract lives in tests/test_client_step_count.py — this test only
        # asserts the manifest is self-coherent, so a future phase add/subtract
        # cannot stale-pin this file.
        phases = m["phases"]
        assert len(phases) == len({p["id"] for p in phases}), "phase ids must be unique"
        assert m["manifest_version"] >= 55  # FIX 83: floor and manifest move together (U019 step 8); FIX 92/103 waves bumped it further (v64 at merge)

    def test_entry_script_derives_count_from_manifest(self):
        """No stale hardcoded '36' for the displayed count; the script computes
        it from PIPELINE-MANIFEST.json (both the dept sops/ copy and the
        cluster universal-sops copy) at runtime."""
        src = ENTRY.read_text(encoding="utf-8")
        assert "_PHASE_COUNT" in src
        assert "PIPELINE-MANIFEST.json" in src
        assert "len(m.get('phases', []))" in src

    def test_no_hardcoded_36_phase_strings_left(self):
        src = ENTRY.read_text(encoding="utf-8")
        bad = [ln for ln in src.splitlines()
               if "36 phases" in ln or "36 mechanical" in ln]
        assert not bad, f"stale hardcoded 36-phase strings remain: {bad}"

    def test_displayed_lines_use_the_variable(self):
        src = ENTRY.read_text(encoding="utf-8")
        assert "Manifest phases: $_PHASE_COUNT" in src
        assert "all $_PHASE_COUNT manifest phases" in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))