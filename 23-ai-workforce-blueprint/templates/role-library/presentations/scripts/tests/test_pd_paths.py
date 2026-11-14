"""PD-216 — the path table matches the producers, the PDF exporter finds the deck.

Rows (01-BUILD-SPEC, PD-216):
  * deck only at working/deliverables/ -> pdf_export._find_pptx finds it, and
    that directory wins over the run top when both hold a deck.
  * the audit passes on the manifest as edited by PD-062 (P8-ASSEMBLE produces
    working/deliverables/*-FINAL.pptx) and FAILS on the manifest as it is
    today, naming the key and the alias spelling the producer writes.

Both manifest rows are built from the repo manifest and patched in a tmp dir,
so the pair keeps its meaning after PD-062 merges.

No network. Stdlib + pytest only; SCRIPTS goes on sys.path so
presentation_job and pdf_export resolve the way the pipeline imports them.
"""

import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pdf_export  # noqa: E402
from presentation_job import deliverable_paths as dp  # noqa: E402

CANONICAL_DECK_PPTX = "working/deliverables/{deck_slug}-FINAL.pptx"
CANONICAL_DECK_PDF = "working/deliverables/{deck_slug}-FINAL.pdf"


def _manifest_with(tmp_path, patches):
    """Copy the repo manifest and set produces_artifact for each phase id."""
    src = dp._manifest_location()
    assert src is not None, "PIPELINE-MANIFEST.json not found from the module"
    man = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    for phase_id, produces in patches.items():
        hits = [p for p in man["phases"] if p.get("id") == phase_id]
        assert len(hits) == 1, f"{phase_id}: expected exactly one phase, got {len(hits)}"
        hits[0]["produces_artifact"] = produces
    out = tmp_path / "PIPELINE-MANIFEST.json"
    out.write_text(json.dumps(man), encoding="utf-8")
    return out


# The PD-062 state: both deck producers declare the canonical directory.
PD062_MANIFEST = {
    "P8-ASSEMBLE": CANONICAL_DECK_PPTX,
    "P8.1-PDF-EXPORT": CANONICAL_DECK_PDF,
}


# --- the path table ---------------------------------------------------------

def test_canonical_deck_paths_are_the_producers_paths():
    assert dp.CANONICAL_PATHS["deck_pptx"] == CANONICAL_DECK_PPTX
    assert dp.CANONICAL_PATHS["deck_pdf"] == CANONICAL_DECK_PDF
    # The older spellings are aliases, never canon.
    assert "working/delivery/{deck_slug}-FINAL.pptx" in dp.ALIAS_PATHS["deck_pptx"]
    assert "{deck_slug}-FINAL.pptx" in dp.ALIAS_PATHS["deck_pptx"]
    assert "working/delivery/{deck_slug}-FINAL.pdf" in dp.ALIAS_PATHS["deck_pdf"]
    assert "{deck_slug}-FINAL.pdf" in dp.ALIAS_PATHS["deck_pdf"]


def test_deliverable_path_expands_deck_slug():
    p = dp.deliverable_path("deck_pptx", deck_slug="out")
    assert p.as_posix() == "working/deliverables/out-FINAL.pptx"


# --- the PDF exporter finds the deck ---------------------------------------

def test_find_pptx_in_working_deliverables_only(tmp_path):
    d = tmp_path / "working" / "deliverables"
    d.mkdir(parents=True)
    (d / "out-FINAL.pptx").write_bytes(b"PK\x03\x04")
    assert pdf_export._find_pptx(tmp_path) == d / "out-FINAL.pptx"


def test_find_pptx_prefers_producer_dir_over_run_top(tmp_path):
    d = tmp_path / "working" / "deliverables"
    d.mkdir(parents=True)
    (d / "out-FINAL.pptx").write_bytes(b"PK\x03\x04")
    (tmp_path / "old-FINAL.pptx").write_bytes(b"PK\x03\x04")
    assert pdf_export._find_pptx(tmp_path) == d / "out-FINAL.pptx"


def test_find_pptx_falls_back_to_run_top(tmp_path):
    (tmp_path / "old-FINAL.pptx").write_bytes(b"PK\x03\x04")
    assert pdf_export._find_pptx(tmp_path) == tmp_path / "old-FINAL.pptx"


def test_find_pptx_none_when_absent(tmp_path):
    assert pdf_export._find_pptx(tmp_path) is None


# --- the audit: pass on the PD-062 manifest, fail on today's ----------------

def test_audit_passes_on_the_pd062_manifest(tmp_path):
    man = _manifest_with(tmp_path, PD062_MANIFEST)
    ok, problems = dp.audit_paths(manifest_path=str(man))
    assert ok is True, problems


@pytest.mark.parametrize(
    "phase_id,canonical,alias,key",
    [
        ("P8-ASSEMBLE", CANONICAL_DECK_PPTX, "*-FINAL.pptx", "deck_pptx"),
        ("P8.1-PDF-EXPORT", CANONICAL_DECK_PDF, "{deck_slug}-FINAL.pdf", "deck_pdf"),
    ],
)
def test_audit_fails_naming_the_alias_a_producer_writes(
        tmp_path, phase_id, canonical, alias, key):
    patches = dict(PD062_MANIFEST)
    patches[phase_id] = alias
    man = _manifest_with(tmp_path, patches)
    ok, problems = dp.audit_paths(manifest_path=str(man))
    assert ok is False
    named = [p for p in problems if key in p and phase_id in p]
    assert named, f"no problem names {key}/{phase_id}: {problems}"
    assert any("alias" in p for p in named), named


def test_audit_reports_todays_deck_pptx_spelling(tmp_path):
    """The BEFORE row: the shipped manifest's bare '*-FINAL.pptx' producer."""
    patches = dict(PD062_MANIFEST)
    patches["P8-ASSEMBLE"] = "*-FINAL.pptx"
    man = _manifest_with(tmp_path, patches)
    ok, problems = dp.audit_paths(manifest_path=str(man))
    assert ok is False
    assert any("deck_pptx" in p and "P8-ASSEMBLE" in p for p in problems), problems
