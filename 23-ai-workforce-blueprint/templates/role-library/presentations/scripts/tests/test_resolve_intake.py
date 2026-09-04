#!/usr/bin/env python3
"""test_resolve_intake.py -- pins FAULT-04 and FAULT-05
(presentation_job/resolve_intake.py), both found on the live Wave E run
(pres-wave-e-zhc-1787175621).

FAULT-04: resolve_intake.py used to emit
  requester: {"chat_id": "", "client_name": "operator"}
whenever no source carried a real chat id -- an artifact
presentation_job.py --new was GUARANTEED to hard-fail on one step later
(fix F1: "no requester.chat_id in intake ... must not start"). resolve()
must now raise MissingRequester (main() -> exit 4, AF-REQUESTER-MISSING)
naming the missing field and where it should come from, instead of handing
forward a known-invalid artifact.

FAULT-05: the resolved engine intake carried only 6 keys
(client, deck_type, presentation_type, requester, signature_source, source)
-- WANT_SALES_CHECKOUT and WANT_VSL_PAGE (and their verbatim
declined-reason waivers) never survived the resolve step in ANY shape, even
though sales+checkout is DEFAULT YES. resolve() must now carry them forward
under the documented NESTED shape, pre_presentation_capture.*, resolved
from whichever real source (ledger entries, or working/copy/intake.json in
either its nested or flat shape) actually carries the answer.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_upsell_intake_shape.py, test_gates.py).
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import resolve_intake as ri  # noqa: E402
from presentation_job.vocab import UnknownPresentationType  # noqa: E402


# ---------------------------------------------------------------------------
# fixture plumbing
# ---------------------------------------------------------------------------
def _run_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _entry(value: str) -> dict:
    """One real intake_ledger.json entries[] value -- mirrors the live Wave
    E ledger's own shape exactly: {"value": ..., "validated": True, ...}."""
    return {"value": value, "validated": True, "source": "deck-intake-driver"}


def _write_ledger(run_dir: pathlib.Path, entries: dict, top_level: dict = None) -> pathlib.Path:
    ledger = {"entries": entries, "status": "complete", "complete": True}
    ledger.update(top_level or {})
    path = run_dir / "working" / "interview" / "intake_ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


def _write_intake_copy(run_dir: pathlib.Path, obj: dict) -> pathlib.Path:
    path = run_dir / "working" / "copy" / "intake.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _base_entries(ptype: str = "from_scratch") -> dict:
    """The one entry every real ledger must carry for resolve() to get past
    the deck-type gate at all."""
    return {"presentation_type": _entry(ptype)}


# ---------------------------------------------------------------------------
# FAULT-04 -- requester.chat_id must never resolve to an empty string
# ---------------------------------------------------------------------------
class TestFault04MissingRequester:
    def test_no_requester_anywhere_fails_loudly_not_empty_chat_id(self):
        """THE FIX -- a ledger with genuinely nothing stamped anywhere (no
        working/copy/intake.json, no requester fields on the ledger itself,
        exactly the live Wave E shape) must raise MissingRequester, never
        return an intake with requester.chat_id == ''."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        with pytest.raises(ri.MissingRequester) as exc_info:
            ri.resolve(ledger_path, "intake-poll")

        msg = str(exc_info.value)
        # names the missing field and where it should come from
        assert "requester_chat_id" in msg
        assert "intake.json" in msg
        assert str(ledger_path) in msg

    def test_main_exits_4_and_writes_nothing_on_missing_requester(self, capsys):
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"

        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])

        assert rc == 4
        err = capsys.readouterr().err
        assert "AF-REQUESTER-MISSING" in err
        assert "requester_chat_id" in err
        assert not out_path.exists(), "resolve_intake must write NOTHING on a fail-loud path"

    def test_requester_chat_id_from_intake_copy_resolves_cleanly(self):
        """Regression control: this is not a blanket failure -- a real
        requester_chat_id stamped on working/copy/intake.json (the
        documented, "per-deck and durable" source) must still resolve."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {
            "requester_chat_id": "123456789",
            "requester_channel": "telegram",
            "client_name": "Acme Corp",
        })
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert intake["requester"]["chat_id"] == "123456789"
        assert intake["requester"]["client_name"] == "Acme Corp"
        assert intake["requester"]["channel"] == "telegram"

    def test_requester_chat_id_from_ledger_top_level_fallback_resolves(self):
        """The legacy/hand-authored fallback path (ledger's own top-level
        requester_chat_id, no working/copy/intake.json at all) must still
        resolve -- unchanged behaviour, not tightened away by the fix."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"),
                      top_level={"requester_chat_id": "999", "client_name": "Beta LLC"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert intake["requester"]["chat_id"] == "999"


# ---------------------------------------------------------------------------
# FAULT-05 -- upsell answers must survive into pre_presentation_capture.*
# ---------------------------------------------------------------------------
class TestFault05UpsellCapture:
    def test_upsell_answers_survive_from_ledger_entries_flat_driver_shape(self):
        """SHAPE 1 -- the real chat-driver ledger shape: entries keyed by
        the question's own lowercase id (want_sales_checkout / want_vsl_page),
        no working/copy/intake.json at all yet. Must still resolve into the
        documented NESTED pre_presentation_capture.* output shape."""
        rd = _run_dir()
        entries = _base_entries("from_scratch")
        entries["want_sales_checkout"] = _entry("yes")
        entries["want_vsl_page"] = _entry("yes")
        _write_ledger(rd, entries)
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert "pre_presentation_capture" in intake, (
            "FAULT-05: upsell answers were captured but did not survive "
            "the resolve step in ANY shape"
        )
        cap = intake["pre_presentation_capture"]
        assert cap["WANT_SALES_CHECKOUT"] == "yes"
        assert cap["WANT_VSL_PAGE"] == "yes"

    def test_upsell_answers_survive_from_intake_copy_flat_top_level_shape(self):
        """SHAPE 2 -- the real live Wave E working/copy/intake.json shape:
        WANT_SALES_CHECKOUT / WANT_VSL_PAGE FLAT at the top level, with NO
        pre_presentation_capture wrapper at all (deck-intake-driver.py's
        cmd_complete()). Must still resolve into the documented NESTED
        output shape -- this is the exact live-run defect."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {
            "requester_chat_id": "42",
            "WANT_SALES_CHECKOUT": "yes",
            "WANT_VSL_PAGE": "yes",
            "OFFER_NAME": "some offer",
            # deliberately NO "pre_presentation_capture" key -- matches the
            # real driver-produced live intake.json this fix targets.
        })
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        cap = intake.get("pre_presentation_capture")
        assert cap is not None, "flat top-level upsell answers must be lifted into pre_presentation_capture"
        assert cap["WANT_SALES_CHECKOUT"] == "yes"
        assert cap["WANT_VSL_PAGE"] == "yes"

    def test_upsell_answers_survive_from_intake_copy_nested_documented_shape(self):
        """SHAPE 3 -- the documented app-bridge contract shape
        (intake_writer.py): already nested under pre_presentation_capture.
        Must pass through unchanged."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {
            "requester_chat_id": "42",
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "no",
                "SALES_CHECKOUT_DECLINED_REASON": "We already have a checkout page we like.",
                "WANT_VSL_PAGE": "yes",
            },
        })
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        cap = intake["pre_presentation_capture"]
        assert cap["WANT_SALES_CHECKOUT"] == "no"
        assert cap["WANT_VSL_PAGE"] == "yes"

    def test_declined_reason_survives_verbatim(self):
        """A 'no' answer's declined-reason must survive WORD FOR WORD --
        silence is never consent, and neither is a resolver paraphrase.
        Uses a reason string with punctuation/casing that a naive
        .strip()/.lower()/.title() transform would visibly mangle."""
        verbatim = "We already have a Checkout page from ClickFunnels -- don't touch it!"
        rd = _run_dir()
        entries = _base_entries("from_scratch")
        entries["want_sales_checkout"] = _entry("no")
        entries["sales_checkout_declined_reason"] = _entry(verbatim)
        _write_ledger(rd, entries)
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        cap = intake["pre_presentation_capture"]
        assert cap["WANT_SALES_CHECKOUT"] == "no"
        assert cap["SALES_CHECKOUT_DECLINED_REASON"] == verbatim, (
            "the waiver reason must survive character-for-character"
        )

    def test_vsl_declined_reason_survives_verbatim_from_intake_copy(self):
        verbatim = "No video exists yet; ask again after the webinar ships."
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {
            "requester_chat_id": "42",
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": verbatim,
        })
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        cap = intake["pre_presentation_capture"]
        assert cap["VSL_PAGE_DECLINED_REASON"] == verbatim

    def test_no_upsell_answers_omits_pre_presentation_capture_entirely(self):
        """Never-fabricate rule: when nothing was ever asked/answered,
        pre_presentation_capture must be ABSENT, never present as an empty
        object or with guessed/defaulted values (sales+checkout's DEFAULT
        YES belongs to the interview layer, not this resolver)."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert "pre_presentation_capture" not in intake


# ---------------------------------------------------------------------------
# Rule 4 -- deck-type normalization (vocab.py) must remain intact
# ---------------------------------------------------------------------------
class TestDeckTypeNormalizationUnchanged:
    def test_alias_signature_presentation_normalizes_to_signature(self):
        rd = _run_dir()
        _write_ledger(rd, _base_entries("signature_presentation"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert intake["presentation_type"] == "signature"
        assert intake["deck_type"] == "signature"

    def test_alias_standard_normalizes_to_from_scratch(self):
        rd = _run_dir()
        _write_ledger(rd, _base_entries("standard"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert intake["presentation_type"] == "from_scratch"

    def test_unresolvable_deck_type_still_raises_loudly(self):
        """An unresolvable presentation_type must remain a loud error --
        never a silent default to from_scratch, and never masked by any of
        this unit's FAULT-04/FAULT-05 changes."""
        rd = _run_dir()
        _write_ledger(rd, _base_entries("totally_not_a_real_type"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        with pytest.raises(UnknownPresentationType):
            ri.resolve(ledger_path, "intake-poll")

    def test_main_exits_3_on_unresolvable_deck_type(self, capsys):
        rd = _run_dir()
        _write_ledger(rd, _base_entries("totally_not_a_real_type"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"

        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])

        assert rc == 3
        assert "AF-DECK-TYPE-UNKNOWN" in capsys.readouterr().err
        assert not out_path.exists()


# ---------------------------------------------------------------------------
# FIX 25/48 -- deck_slug emission (sweep not_a_run_dir rejection)
# ---------------------------------------------------------------------------
class TestDeckSlugEmission:
    """resolve() must now emit intake['deck_slug'] -- the sweep's
    _deck_slug() reads state.json["intake"]["deck_slug"] first, and that
    snapshot is frozen from THIS resolver's output at --new time. Without
    it the 15-minute board-reconcile-sweep rejected every engine run as
    "no deck_slug resolvable" / not_a_run_dir (FIX 25/48)."""

    def test_deck_slug_defaults_to_slugified_run_dir_name(self):
        rd = pathlib.Path(tempfile.mkdtemp()) / "my-Run_Dir.2"
        rd.mkdir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        # slugified with the SAME regex sweep._slugify / curate /
        # manifest _resolve_deck_slug use -- so the emitted value
        # round-trips their own slugifiers unchanged.
        assert intake["deck_slug"] == "my-run-dir-2", intake["deck_slug"]

    def test_deck_slug_from_upstream_stamped_intake_copy_wins(self):
        """An explicit deck_slug stamped on working/copy/intake.json by an
        upstream step (curate/manifest pass-1 precedence) win over the
        run-dir-name derivation."""
        rd = pathlib.Path(tempfile.mkdtemp()) / "decked"
        rd.mkdir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {"requester_chat_id": "42",
                                "deck_slug": "Wave-E-ZHC"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"

        intake = ri.resolve(ledger_path, "intake-poll")

        assert intake["deck_slug"] == "wave-e-zhc"

    def test_deck_slug_survives_main_write(self, capsys):
        rd = pathlib.Path(tempfile.mkdtemp()) / "mainrun"
        rd.mkdir()
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"

        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])

        assert rc == 0
        written = json.loads(out_path.read_text())
        assert written["deck_slug"] == "mainrun"


# ---------------------------------------------------------------------------
# FIX 59 -- dict-shaped interview_depth unwrap (real driver shape)
# ---------------------------------------------------------------------------
class TestIntakeDepthDictUnwrap:
    """The real deck-intake-driver.py writes the interview_depth entry's
    value/normalized AS A DICT: {"standard_mode": "IN-DEPTH"} (measured on
    the live run). Entry-only _entry_raw_value returns None on the dict's
    inner value when the inner key is 'value' -- no wait: _entry_raw_value
    tries ('normalized','value','answer') and the outer WRAPPER is a dict
    whose value sub-key is itself the {"standard_mode": ...} dict. So the
    raw string must be recovered from the INNER standard_mode sub-key via
    _unwrap; without it resolve raised/refused the real ledger's depth."""

    def _ledger_with_dict_depth(self) -> pathlib.Path:
        rd = pathlib.Path(tempfile.mkdtemp())
        _write_ledger(rd, {
            "presentation_type": _entry("from_scratch"),
            "interview_depth": {
                "value": {"standard_mode": "IN-DEPTH"},
                "normalized": {"standard_mode": "IN-DEPTH"},
                "answer": "IN-DEPTH",  # a bare string, exactly as driver writes it too
            },
        })
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        return rd / "working" / "interview" / "intake_ledger.json"

    def test_dict_shaped_depth_resolves_to_indepth(self):
        intake = ri.resolve(self._ledger_with_dict_depth(), "intake-poll")
        assert intake["standard_mode"] == "IN-DEPTH"

    def test_dict_shaped_depth_via_main_exit_zero(self, capsys):
        ledger_path = self._ledger_with_dict_depth()
        out_path = ledger_path.parent.parent / "working" / "checkpoints" / ".e.json"
        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])
        assert rc == 0, capsys.readouterr().err

    def test_display_case_quick_accepted_by_argparse(self, capsys):
        """FIX 59 leg 1 -- the door passes display-case INTAKE_DEPTH
        (QUICK/IN-DEPTH) as --intake-depth to the resolver; argparse must
        accept it (lowercase pre-argparse), never 'invalid choice:
        QUICK'."""
        rd = pathlib.Path(tempfile.mkdtemp())
        _write_ledger(rd, _base_entries("from_scratch"))
        _write_intake_copy(rd, {"requester_chat_id": "42"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"

        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll", "--intake-depth", "QUICK"])

        assert rc == 0, capsys.readouterr().err
        written = json.loads(out_path.read_text())
        assert written["standard_mode"] == "QUICK"


# ---------------------------------------------------------------------------
# End-to-end: main() writes a well-formed file when everything resolves
# ---------------------------------------------------------------------------
class TestMainEndToEnd:
    def test_main_writes_intake_with_requester_and_upsell_capture(self, capsys):
        rd = _run_dir()
        entries = _base_entries("from_scratch")
        entries["want_sales_checkout"] = _entry("yes")
        entries["want_vsl_page"] = _entry("yes")
        _write_ledger(rd, entries)
        _write_intake_copy(rd, {"requester_chat_id": "42", "client_name": "Gamma Inc"})
        ledger_path = rd / "working" / "interview" / "intake_ledger.json"
        out_path = rd / "working" / "checkpoints" / ".engine-intake.json"

        rc = ri.main(["--ledger", str(ledger_path), "--out", str(out_path),
                      "--source", "intake-poll"])

        assert rc == 0
        written = json.loads(out_path.read_text())
        assert written["requester"]["chat_id"] == "42"
        assert written["pre_presentation_capture"]["WANT_SALES_CHECKOUT"] == "yes"
        assert written["pre_presentation_capture"]["WANT_VSL_PAGE"] == "yes"
