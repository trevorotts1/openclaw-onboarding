"""PD-TEST-115 -- the front-door nonce MUST be the one the engine actually mints.

THE DEFECT. `phases._run_script_phase` (phases.py:2298-2323, FIX 25) mints a
PER-PHASE nonce and exports BOTH:

    OC_DECK_ENTRY_NONCE      = <nonce>
    OC_DECK_ENTRY_NONCE_FILE = <sanitized phase token>

so the compare target is `<run>/working/checkpoints/.nonce-<token>`.
`build_infographic.py` and `build_deck.py` read `OC_DECK_ENTRY_NONCE_FILE` and
honour it. `sales_checkout_builder.py` and `workbook_builder.py` did NOT: they
compared the environment nonce against the LEGACY run-scoped file
`<run>/working/checkpoints/.canonical-entry-nonce`, which the engine no longer
mints at all. The env var carried one secret and the file held another, so the
comparison could never succeed.

Measured live on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4:
`P-U-CHECKOUT-BUILD` was quarantined after its 3 attempts with

    FATAL [AF-CANONICAL-RENDER-BYPASS]: sales_checkout_builder.py must run via
    presentation-canonical-entry.sh, which mints the per-run front-door nonce.

and 0 nonce files existed under the run's checkpoints dir.

WHAT THESE TESTS PIN
  1. The per-phase handshake the ENGINE actually delivers is ACCEPTED. This is
     the case that was impossible before the port, so it is the acceptance
     target; it is asserted RED against the pre-port function below.
  2. The legacy run-scoped handshake still works when
     `OC_DECK_ENTRY_NONCE_FILE` is unset -- that is the standalone
     `presentation-canonical-entry.sh` path, and the port must not break it.
  3. Fail-closed on every malformed input: missing env var, short nonce, absent
     file, short file, a foreign phase's file, and a traversal path.
  4. DRIFT GUARD: `_entry_nonce_phase_file` agrees byte-for-byte with
     `phases._entry_nonce_phase_file` for the real phase ids -- the two must
     never diverge, and a silent divergence is exactly how this defect arose.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import phases as _phases_mod  # noqa: E402

BUILDERS = ("sales_checkout_builder", "workbook_builder", "vsl_builder",
            "build_webinar_video")

# The real phase id from the live run, plus ids that exercise the sanitizer.
PHASE_IDS = (
    "P-U-CHECKOUT-BUILD",
    "P-U-SALES-BUILD",
    "P-U-VSL-BUILD",
    "P9.6-WEBINAR-VIDEO",
    "P-U-CHECKOUT-BUILD.RETRY",   # a dot survives the sanitizer
    "P-U/CHECKOUT BUILD",         # slash + space do not
)

NONCE = "0f3a9c1d5e7b2468"          # 16 chars, the documented minimum


def _load(name: str):
    """Import a builder module by name, from THIS scripts dir.

    Both builders parse argv at import only under `__main__`, so importing is
    side-effect free; they are stdlib-only by contract on a deployed box.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module(name)


def _run_dir(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return rd


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts with NO nonce env, so a pass cannot come from leakage."""
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE", raising=False)
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE_FILE", raising=False)


# ---------------------------------------------------------------------------
# 1 -- THE ACCEPTANCE TARGET: the handshake the engine really delivers.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modname", BUILDERS)
@pytest.mark.parametrize("phase_id", PHASE_IDS)
def test_per_phase_nonce_the_engine_mints_is_accepted(tmp_path, monkeypatch, modname, phase_id):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    token = mod._entry_nonce_phase_file(rd, phase_id).name[len(".nonce-"):]
    _write(mod._entry_nonce_phase_file(rd, phase_id), NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", token)
    assert mod._verify_entry_nonce(rd) is True, (
        f"{modname}: the engine delivered a per-phase nonce in "
        f"OC_DECK_ENTRY_NONCE_FILE={token!r} and it was refused -- this is the "
        "PD-TEST-115 defect (the builder read the legacy run-scoped file).")


@pytest.mark.parametrize("modname", BUILDERS)
def test_negative_control_preport_function_refuses_the_engine_handshake(tmp_path, monkeypatch, modname):
    """Proves the test above actually pins the defect: re-implement the PRE-PORT
    body and show it REFUSES the very handshake the engine delivers."""
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    phase_id = "P-U-CHECKOUT-BUILD"
    _write(mod._entry_nonce_phase_file(rd, phase_id), NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", phase_id)

    import hmac

    def pre_port_verify(run_dir: Path) -> bool:
        env_nonce = (os.environ.get("OC_DECK_ENTRY_NONCE") or "").strip()
        if len(env_nonce) < 16:
            return False
        nf = run_dir / mod.ENTRY_NONCE_REL
        try:
            file_nonce = nf.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        return hmac.compare_digest(env_nonce, file_nonce)

    assert pre_port_verify(rd) is False, (
        "the pre-port body accepted the engine's per-phase nonce, so this test "
        "does not pin PD-TEST-115")
    assert mod._verify_entry_nonce(rd) is True, "the ported body must accept it"


# ---------------------------------------------------------------------------
# 2 -- the legacy standalone handshake must keep working.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modname", BUILDERS)
def test_legacy_run_scoped_handshake_still_works(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(rd / mod.ENTRY_NONCE_REL, NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    # OC_DECK_ENTRY_NONCE_FILE deliberately UNSET -- the canonical-entry path
    assert mod._verify_entry_nonce(rd) is True


@pytest.mark.parametrize("modname", BUILDERS)
def test_path_form_nonce_file_inside_checkpoints_is_accepted(tmp_path, monkeypatch, modname):
    """The engine may name the file by PATH; a path confined to this run's
    checkpoints dir with a `.nonce-` basename is valid."""
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    nf = mod._entry_nonce_phase_file(rd, "P-U-CHECKOUT-BUILD")
    _write(nf, NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", str(nf))
    assert mod._verify_entry_nonce(rd) is True


# ---------------------------------------------------------------------------
# 3 -- fail-closed on every malformed input.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modname", BUILDERS)
def test_missing_env_var_is_refused(tmp_path, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(mod._entry_nonce_phase_file(rd, "P-U-CHECKOUT-BUILD"), NONCE)
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_short_env_nonce_is_refused(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(mod._entry_nonce_phase_file(rd, "P-U-CHECKOUT-BUILD"), NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", "short")
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", "P-U-CHECKOUT-BUILD")
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_foreign_phase_file_is_refused(tmp_path, monkeypatch, modname):
    """A valid nonce for ANOTHER phase must not admit this one."""
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(mod._entry_nonce_phase_file(rd, "P-U-SALES-BUILD"), NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", "P-U-CHECKOUT-BUILD")
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_path_outside_checkpoints_is_refused(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    outside = tmp_path / ".nonce-evil"
    _write(outside, NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", str(outside))
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_traversal_path_is_refused(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(tmp_path / ".nonce-evil", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE",
                       str(rd / "working" / "checkpoints" / ".." / ".." / ".." / ".nonce-evil"))
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_short_file_nonce_is_refused(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(mod._entry_nonce_phase_file(rd, "P-U-CHECKOUT-BUILD"), "short")
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", "P-U-CHECKOUT-BUILD")
    assert mod._verify_entry_nonce(rd) is False


@pytest.mark.parametrize("modname", BUILDERS)
def test_mismatched_nonce_is_refused(tmp_path, monkeypatch, modname):
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    _write(mod._entry_nonce_phase_file(rd, "P-U-CHECKOUT-BUILD"), NONCE)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", "ffffffffffffffff")
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE_FILE", "P-U-CHECKOUT-BUILD")
    assert mod._verify_entry_nonce(rd) is False


# ---------------------------------------------------------------------------
# 4 -- DRIFT GUARD: the builder's token derivation must equal the engine's.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modname", BUILDERS)
@pytest.mark.parametrize("phase_id", PHASE_IDS)
def test_phase_file_derivation_matches_the_engine(tmp_path, modname, phase_id):
    """`phases._entry_nonce_phase_file` is the MINT; the builder's is the COMPARE
    target. If they ever disagree, every script phase fails its front door --
    which is precisely the PD-TEST-115 shape, so pin the equality directly."""
    mod = _load(modname)
    rd = _run_dir(tmp_path)
    mine = mod._entry_nonce_phase_file(rd, phase_id)
    theirs = _phases_mod._entry_nonce_phase_file(rd, phase_id)
    assert mine == theirs, (
        f"{modname}: token derivation drifted from the engine's mint -- "
        f"builder={mine.name!r} engine={theirs.name!r}")
