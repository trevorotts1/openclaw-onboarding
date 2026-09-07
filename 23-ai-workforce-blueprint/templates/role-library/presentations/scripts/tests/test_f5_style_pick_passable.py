#!/usr/bin/env python3
"""test_f5_style_pick_passable.py -- F5: the style pick is passable without an operator.

MEASURED ON PRISTINE main (ea331f82a), with python3 full-string counts over the
repo (instrument: python3 os.walk + str.count, NOT grep -- the shell's grep is
ugrep in a function and zsh aborts on unmatched globs):

  * "style_pick_auto" appeared in exactly 3 files, ALL of them engine-side:
    presentation_job/phases.py (11), phase_verifiers.py (2) and
    tests/test_fix29_style_pick_human_stage.py (10). ZERO occurrences in
    intake/deck-intake-questions.json (the 48-row, 23-turn bank) and ZERO in
    either deck-intake-driver.py fork.
    CONTROL, same scan, same instrument: "run_mode" -- the sibling client-side
    opt-in that DOES exist -- returned the bank (11) and the canonical driver
    (4). The scan was not broken; the field genuinely had no client-side half.
  * "style_preview_choice" appeared in 12 files -- every one of them a reader,
    a verifier, a doc or a test. NOTHING client-side ever WROTE
    working/copy/style_preview_choice.json, and the only writer of any kind was
    the engine's own timeout auto-pick, which is gated on the opt-in that
    intake could not record.
  * "--style-pick" / "--owner-msg-id": 0 occurrences in deck-intake-driver.py.
    CONTROL: "--sig-answer" (a sibling driver flag) returned 3.

So P-STYLE-PICK (order 4.86, executor kind "human", PHASE_BUDGET_MINUTES 45)
was a GUARANTEED 45-minute stall in the middle of every deck: the engine
delivered "pick A, B or C", the agent holding the client's reply had no
sanctioned way to record it, and the timeout auto-pick could never fire because
no interview could ever set intake.style_pick_auto.

WHAT F5 ADDS (and what this file pins, in both directions):

  1. THE OPT-IN rides an EXISTING turn as a labelled subfield -- never a 24th
     turn. session_budget.max_turns stays 23 and the merged-turn count stays
     23, exactly as the run-mode slot did (Trevor ruling).
     Its host is `style_and_brand` (order 15, required + block_gate), NOT
     `resource_plan`: resource_plan's own help text says it is asked ONLY when
     the capacity probe left a pending question ("a fully detected client is
     never asked it"), so an opt-in parked there would be unreachable for most
     clients. The turn that already asks the client about STYLE is asked on
     every deck.
  2. THE DRIVER records it as a real BOOLEAN. The engine's reader tests
     `auto is True`; the generic merged-turn writer records the answered STRING
     "yes", and `"yes" is True` is False. _record_style_pick_auto overwrites
     both the ledger key and the intake root key with the boolean.
  3. THE RECORDER: `deck-intake-driver.py --run-dir DIR --style-pick A|B|C
     --owner-msg-id ID` writes the exact shape the engine's
     _style_choice_authentic() verifies, REFUSES to run without an owner
     message id, and never writes the auto_pick provenance that belongs only
     to the engine's own timeout path.
  4. THE DOCS name the command in the department files the agent actually
     reads.

Unit-level: no network, no model spend, no deck, no render. The driver runs as
a REAL child interpreter through its REAL CLI; the engine's own reader and its
own authenticity gate are called directly (never re-implemented here), with the
Fix 32 owner oracle stubbed the same way tests/test_fix29_style_pick_human_stage.py
stubs it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import approvals as approvals_mod  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402

BANK = SCRIPTS.parent / "intake" / "deck-intake-questions.json"
DRIVER = SCRIPTS / "deck-intake-driver.py"
DEPT = SCRIPTS.parent

CHOICE_REL = "working/copy/style_preview_choice.json"
SAMPLES_REL = "working/style-preview/style_samples_manifest.json"
HOST_TURN = "style_and_brand"
SUBFIELD = "style_pick_auto"
STORE_KEY = "STYLE_PICK_AUTO"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _bank() -> dict:
    return json.loads(BANK.read_text(encoding="utf-8"))


def _host_turn() -> dict:
    return [q for q in _bank()["questions"] if q["id"] == HOST_TURN][0]


def _run_driver(run_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir), *args],
        capture_output=True, text=True, timeout=180)


def _seed_samples(run_dir: Path, variants=("A", "B", "C")) -> None:
    p = run_dir / SAMPLES_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema": "style_samples_manifest/v1",
        "variants": list(variants),
        "owner_pick_required": True,
        "owner_pick_artifact": CHOICE_REL,
    }), encoding="utf-8")


def _drive_intake(run_dir: Path, style_answer: str | None) -> dict:
    """Drive the REAL driver CLI through presentation_type (+ the style turn
    when given) and --complete. Returns the written intake.json."""
    r = _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
    assert r.returncode == 0, f"presentation_type: {r.stdout}\n{r.stderr}"
    if style_answer is not None:
        r = _run_driver(run_dir, "--answer", HOST_TURN, style_answer)
        assert r.returncode == 0, f"{HOST_TURN}: {r.stdout}\n{r.stderr}"
    r = _run_driver(run_dir, "--complete")
    assert r.returncode == 0, f"--complete: {r.stdout}\n{r.stderr}"
    return json.loads((run_dir / "working" / "copy" / "intake.json")
                      .read_text(encoding="utf-8"))


class _ReaderProbe:
    """The narrowest possible stand-in for an Engine: it carries ONLY a run_dir,
    so Engine._style_pick_intake_auto -- the REAL production reader, called
    unbound -- is exercised verbatim against a real run directory. Nothing about
    the opt-in decision is re-implemented in this test file."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir


def _engine_reads_opt_in(run_dir: Path) -> bool:
    return Engine._style_pick_intake_auto(_ReaderProbe(run_dir))


class _GateProbe:
    """Same idea for the authenticity gate: run_dir only. _style_choice_authentic
    touches self.run_dir and nothing else."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir


def _engine_accepts_choice(run_dir: Path, choice: dict, variants) -> tuple:
    return Engine._style_choice_authentic(_GateProbe(run_dir), choice,
                                          list(variants))


def _stub_oracle(monkeypatch, ids):
    """Same stub tests/test_fix29_style_pick_human_stage.py uses: the Fix 32
    Command-Center oracle resolves exactly these owner message ids."""
    monkeypatch.setattr(
        approvals_mod, "_cc_board_oracle",
        lambda run_dir=None: frozenset(ids) if ids is not None else None)


# ---------------------------------------------------------------------------
# 1. THE BANK -- a client-declarable opt-in that costs no extra turn
# ---------------------------------------------------------------------------
class TestBankCarriesTheOptIn:
    def test_the_opt_in_subfield_exists_on_a_turn_asked_on_every_deck(self):
        """0 occurrences on pristine main. The host turn must be one the client
        is ALWAYS asked -- required + block_gate -- or the opt-in is unreachable."""
        turn = _host_turn()
        assert SUBFIELD in (turn.get("subfields") or {}), (
            f"the bank has no {SUBFIELD} subfield; without it no interview can "
            f"ever record intake.style_pick_auto and every deck parks 45 min "
            f"at P-STYLE-PICK")
        assert turn.get("required") is True
        assert turn.get("block_gate") is True

    def test_the_subfield_declares_its_own_yes_no_vocabulary(self):
        ann = _host_turn()["subfields"][SUBFIELD]
        assert [str(v).lower() for v in ann.get("enum") or []] == ["yes", "no"]
        assert ann.get("storeOn") == STORE_KEY

    def test_absence_is_absence__no_default_key(self):
        """A `default` here would hand every silent client a recorded answer.
        The engine reads a missing/falsy field as NO opt-in; the bank must not
        manufacture one."""
        ann = _host_turn()["subfields"][SUBFIELD]
        assert "default" not in ann, (
            "a default on the style-pick opt-in would auto-pick for clients who "
            "never answered -- the exact forgery FIX 29 exists to prevent")

    def test_the_prompt_actually_asks_it(self):
        """A subfield nobody is asked about is dead plumbing. The turn's own
        prompt has to put the choice in front of the client."""
        turn = _host_turn()
        prompt = turn["prompt"].lower()
        assert "style pick auto" in prompt
        assert "45" in prompt, "the client is told what the wait costs them"

    def test_it_is_routed_to_the_capture_store(self):
        assert (_bank()["storeTarget"].get(STORE_KEY)
                == "pre_presentation_capture.STYLE_PICK_AUTO")

    def test_the_turn_ceiling_is_untouched(self):
        """Trevor ruling, binding: the opt-in EXTENDS an existing turn. It never
        adds a 24th. This assertion passes on pristine main too -- it is the
        guard, not the change."""
        bank = _bank()
        assert bank["session_budget"]["max_turns"] == 23
        merged = [q for q in bank["questions"] if q.get("kind") == "merged"]
        assert len(merged) == 23, [q["id"] for q in merged]

    def test_the_opt_in_did_not_land_on_the_skippable_turn(self):
        """resource_plan is asked ONLY when the capacity probe leaves a pending
        question (its own help text: 'a fully detected client is never asked
        it'). An opt-in parked there is unreachable for a fully-detected client,
        which is most of them."""
        rp = [q for q in _bank()["questions"] if q["id"] == "resource_plan"][0]
        assert rp.get("required") is False
        assert "never asked it" in rp.get("help", "")
        assert SUBFIELD not in (rp.get("subfields") or {})


# ---------------------------------------------------------------------------
# 2. THE DRIVER -- records a real BOOLEAN, or records nothing
# ---------------------------------------------------------------------------
class TestDriverRecordsTheOptIn:
    def test_yes_reaches_the_engines_own_reader_as_true(self, tmp_path):
        """The whole point, end to end: a client says yes in the interview, and
        the ENGINE's own production reader returns True for that run dir."""
        rd = tmp_path / "run"
        intake = _drive_intake(
            rd, "match brand; brand_primary: #123456; style pick auto: yes")
        assert intake.get(SUBFIELD) is True, (
            f"intake.json carries {intake.get(SUBFIELD)!r} -- the engine tests "
            f"`auto is True`, so the string 'yes' parks the deck anyway")
        assert (intake.get("pre_presentation_capture") or {}).get(STORE_KEY) is True
        assert _engine_reads_opt_in(rd) is True

    def test_no_is_recorded_and_reads_as_no_opt_in(self, tmp_path):
        rd = tmp_path / "run"
        intake = _drive_intake(
            rd, "fresh clean-white; style pick auto: no")
        assert intake.get(SUBFIELD) is False
        assert _engine_reads_opt_in(rd) is False

    def test_silence_records_nothing_and_never_opts_in(self, tmp_path):
        """A client who answered the style turn without mentioning the pick
        must NOT end up with a truthy value on the ledger or in intake.json."""
        rd = tmp_path / "run"
        intake = _drive_intake(rd, "match brand, navy and gold, dark is fine")
        assert intake.get(SUBFIELD) in (None, False), intake.get(SUBFIELD)
        assert (intake.get("pre_presentation_capture") or {}).get(STORE_KEY) \
            in (None, False)
        assert _engine_reads_opt_in(rd) is False

    def test_a_deck_that_never_answered_the_style_turn_never_opts_in(self, tmp_path):
        rd = tmp_path / "run"
        intake = _drive_intake(rd, None)
        assert SUBFIELD not in intake
        assert _engine_reads_opt_in(rd) is False

    def test_the_ledger_value_is_a_bool_not_a_string(self, tmp_path):
        rd = tmp_path / "run"
        _drive_intake(rd, "brand; style_pick_auto: yes")
        ledger = json.loads(
            (rd / "working" / "interview" / "intake_ledger.json")
            .read_text(encoding="utf-8"))
        for key in (STORE_KEY, SUBFIELD):
            assert isinstance(ledger["entries"][key]["value"], bool), (
                f"ledger entry {key} holds "
                f"{ledger['entries'][key]['value']!r}, not a bool")

    def test_a_later_answer_without_the_slot_does_not_revoke_consent(self, tmp_path):
        """Same asymmetry _record_run_mode documents: re-answering the turn to
        change a brand colour must not silently withdraw a standing yes."""
        rd = tmp_path / "run"
        r = _run_driver(rd, "--answer", "presentation_type", "from_scratch")
        assert r.returncode == 0, r.stderr
        r = _run_driver(rd, "--answer", HOST_TURN, "brand; style pick auto: yes")
        assert r.returncode == 0, r.stderr
        r = _run_driver(rd, "--answer", HOST_TURN,
                        "actually make it navy; brand_primary: #001F3F")
        assert r.returncode == 0, r.stderr
        r = _run_driver(rd, "--complete")
        assert r.returncode == 0, r.stderr
        intake = json.loads((rd / "working" / "copy" / "intake.json")
                            .read_text(encoding="utf-8"))
        assert intake.get(SUBFIELD) is True
        assert _engine_reads_opt_in(rd) is True

    def test_an_explicit_no_does_revoke_it(self, tmp_path):
        rd = tmp_path / "run"
        for args in (("--answer", "presentation_type", "from_scratch"),
                     ("--answer", HOST_TURN, "brand; style pick auto: yes"),
                     ("--answer", HOST_TURN, "brand; style pick auto: no"),
                     ("--complete",)):
            r = _run_driver(rd, *args)
            assert r.returncode == 0, f"{args}: {r.stdout}\n{r.stderr}"
        intake = json.loads((rd / "working" / "copy" / "intake.json")
                            .read_text(encoding="utf-8"))
        assert intake.get(SUBFIELD) is False
        assert _engine_reads_opt_in(rd) is False


# ---------------------------------------------------------------------------
# 3. THE RECORDER -- the sanctioned client-side writer of the choice file
# ---------------------------------------------------------------------------
class TestStylePickRecorder:
    def test_the_flag_exists(self):
        """0 occurrences on pristine main; control: --sig-answer, a sibling
        flag on the same parser, is present on both."""
        src = DRIVER.read_text(encoding="utf-8")
        assert "--style-pick" in src
        assert "--owner-msg-id" in src
        assert "--sig-answer" in src  # control: the scan sees real flags

    def test_it_refuses_without_an_owner_msg_id_and_writes_nothing(self, tmp_path):
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "B")
        assert r.returncode != 0, r.stdout
        assert "owner-msg-id" in r.stdout
        assert not (rd / CHOICE_REL).exists(), (
            "a pick with no owner message id must leave NO file behind -- a "
            "file on disk is what the forged e2e-test-002 pick looked like")

    def test_it_refuses_a_variant_that_was_never_offered(self, tmp_path):
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "Z", "--owner-msg-id", "owner-msg-42")
        assert r.returncode != 0
        assert "offered" in r.stdout
        assert not (rd / CHOICE_REL).exists()

    def test_it_writes_the_shape_the_engine_gate_accepts(self, tmp_path, monkeypatch):
        """The binding proof: the file this command writes is ACCEPTED by the
        engine's own _style_choice_authentic(), called directly. Nothing about
        the accept/deny rule is re-stated here."""
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "B", "--owner-msg-id", "owner-msg-42")
        assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
        choice = json.loads((rd / CHOICE_REL).read_text(encoding="utf-8"))
        assert choice["owner_approved"] is True
        assert choice["chosen_variant"] == "B"
        assert choice["owner_msg_id"] == "owner-msg-42"

        _stub_oracle(monkeypatch, ["owner-msg-42"])
        ok, denial = _engine_accepts_choice(rd, choice, ["A", "B", "C"])
        assert ok is True, denial

    def test_a_lowercase_or_numeric_reply_resolves_to_the_offered_id(self, tmp_path):
        """Clients type 'b' and '2'. The engine compares membership with no
        normalisation at all, so the resolution has to happen in the recorder or
        a perfectly good pick is denied for a reason no client could guess."""
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "b", "--owner-msg-id", "owner-msg-42")
        assert r.returncode == 0, r.stderr
        assert json.loads((rd / CHOICE_REL).read_text())["chosen_variant"] == "B"
        r = _run_driver(rd, "--style-pick", "3", "--owner-msg-id", "owner-msg-43")
        assert r.returncode == 0, r.stderr
        assert json.loads((rd / CHOICE_REL).read_text())["chosen_variant"] == "C"

    def test_it_never_writes_the_auto_pick_provenance(self, tmp_path):
        """auto_pick:true means 'the engine picked, under a recorded opt-in'.
        A client-side recorder that stamped it would launder a human pick into
        machine provenance -- and vice versa."""
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "A", "--owner-msg-id", "owner-msg-42")
        assert r.returncode == 0, r.stderr
        choice = json.loads((rd / CHOICE_REL).read_text(encoding="utf-8"))
        assert "auto_pick" not in choice
        assert "auto_pick_basis" not in choice

    def test_an_unresolvable_id_is_still_denied_at_the_gate(self, tmp_path,
                                                            monkeypatch):
        """The recorder is NOT a second oracle. It records; the engine decides.
        A file written with an id the oracle cannot resolve must still be
        denied -- the recorder must never be a way around Fix 32."""
        rd = tmp_path / "run"
        _seed_samples(rd)
        r = _run_driver(rd, "--style-pick", "A", "--owner-msg-id", "not-a-real-id")
        assert r.returncode == 0, r.stderr
        choice = json.loads((rd / CHOICE_REL).read_text(encoding="utf-8"))
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        ok, denial = _engine_accepts_choice(rd, choice, ["A", "B", "C"])
        assert ok is False
        assert "not-a-real-id" in denial

    def test_the_usage_line_names_the_new_mode(self, tmp_path):
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        r = _run_driver(rd)
        assert r.returncode != 0
        assert "--style-pick" in r.stdout


# ---------------------------------------------------------------------------
# 4. THE DOCS -- the agent has to be TOLD how to record a pick
# ---------------------------------------------------------------------------
DOCS = [
    DEPT / "director-of-presentations.md",
    DEPT / "sops" / "director-of-presentations-sops.md",
    DEPT / "sops" / "brand-steward-sops.md",
]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_the_department_docs_tell_the_agent_how_to_record_a_pick(doc):
    """Measured on pristine main: 0 of these 3 files contained '--style-pick'.
    CONTROL, same instrument: all 3 already contain 'P-STYLE-PICK' or
    'style_preview_choice' -- the phase was documented, the ACTION was not."""
    text = doc.read_text(encoding="utf-8")
    assert "--style-pick" in text, (
        f"{doc.name} never tells the agent how to record the client's A/B/C "
        f"reply, so the deck parks for 45 minutes with the answer in the chat")
    assert "--owner-msg-id" in text
    assert "style_pick_auto" in text


# ---------------------------------------------------------------------------
# 5. EVERY INVOCABLE DRIVER -- no fork may silently drop the opt-in
#
# The precedent is tests/test_intake_driver_run_mode_unification.py: two skill-23
# driver copies existed beside the canonical one against the SAME bank, and a
# client who declared "mode: ultra" through either copy got {"validated": true}
# back while RUN_MODE was silently dropped. The P0-1 fix made those copies
# DELEGATE --next/--answer/--complete to the canonical driver instead of
# reimplementing them, so there is one body of code and nothing to drift.
#
# The style-pick opt-in inherits exactly the same exposure, so it gets exactly
# the same behavioural gate: DISCOVER every deck-intake-*.py exposing the
# answer-recording CLI (never a hard-coded list -- the defect was a NEW copy
# appearing), EXECUTE it against a real run directory, and read back the ledger
# it actually wrote. A string check would be satisfied by a comment.
# ---------------------------------------------------------------------------
SKILL23 = SCRIPTS.parents[3]


def _is_intake_driver(path: Path) -> bool:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return '"--answer"' in src or "'--answer'" in src


def _discover_drivers() -> list:
    found = []
    for d in (SCRIPTS, SKILL23 / "scripts"):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("deck-intake-*.py")):
            if _is_intake_driver(p):
                found.append(p)
    return found


_DRIVERS = _discover_drivers()
_DRIVER_IDS = [str(p.relative_to(SKILL23.parent)) for p in _DRIVERS]


def test_driver_discovery_is_not_vacuous():
    """A gate that inspects nothing must never report green. Without this, an
    empty list would make the parametrised case below vanish silently."""
    assert _DRIVERS, (
        f"no intake drivers discovered under {SCRIPTS} or "
        f"{SKILL23 / 'scripts'} -- this gate inspected nothing")
    assert (SCRIPTS / "deck-intake-driver.py") in _DRIVERS
    assert len(_DRIVERS) >= 2, (
        "only the canonical driver was discovered; the skill-23 copies this "
        "gate exists for are not being exercised")


@pytest.mark.parametrize("driver", _DRIVERS, ids=_DRIVER_IDS)
def test_every_driver_records_the_opt_in_as_a_boolean(driver, tmp_path):
    """Executed, not grepped. Each driver records the style turn for real and
    the ledger it wrote is read back: the opt-in must land as the BOOLEAN True
    on both the storeOn key and the subfield id, or a client interviewed
    through that copy opts in and still parks 45 minutes at P-STYLE-PICK."""
    rd = tmp_path / "run"
    rd.mkdir(parents=True)  # the skill-23 copies require an existing run dir
    proc = subprocess.run(
        [sys.executable, str(driver), "--run-dir", str(rd),
         "--answer", HOST_TURN, "match brand; style pick auto: yes"],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"{driver}: {proc.stdout}\n{proc.stderr}"
    ledger = json.loads(
        (rd / "working" / "interview" / "intake_ledger.json")
        .read_text(encoding="utf-8"))
    entries = ledger.get("entries") or {}
    for key in (STORE_KEY, SUBFIELD):
        entry = entries.get(key)
        assert isinstance(entry, dict), f"{driver}: no ledger entry {key}"
        assert entry.get("value") is True, (
            f"{driver}: ledger {key} holds {entry.get('value')!r} -- the "
            f"engine tests `auto is True`, so anything else parks the deck")


# ---------------------------------------------------------------------------
# 6. THE SECOND GATE -- phase_verifiers._verify_style_pick
#
# _run_human_phase returning EXIT_OK is only half of P-STYLE-PICK. run_phase
# then re-measures the artifact through the phase's declared substance verifier,
# which re-reads the FILE's shape independently of the authenticity oracle. A
# recorder that satisfied the executor but not the verifier would advance the
# phase and then fail it, so both legs are proven here against the real
# production functions.
# ---------------------------------------------------------------------------
def test_the_recorded_choice_also_passes_the_substance_verifier(tmp_path):
    import phase_verifiers  # noqa: PLC0415 -- flat module beside the driver

    rd = tmp_path / "run"
    _seed_samples(rd)
    r = _run_driver(rd, "--style-pick", "C", "--owner-msg-id", "owner-msg-42")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    ok, reasons = phase_verifiers._verify_style_pick(rd)
    assert ok is True, reasons


def test_the_verifier_still_refuses_an_empty_run(tmp_path):
    """Control: the same verifier, the same instrument, a run with no choice
    file -- it must FAIL. A verifier that passes everything proves nothing about
    the case above."""
    import phase_verifiers  # noqa: PLC0415

    rd = tmp_path / "run"
    _seed_samples(rd)
    ok, reasons = phase_verifiers._verify_style_pick(rd)
    assert ok is False and reasons
