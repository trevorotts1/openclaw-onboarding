"""PD-077 -- the speech builder refuses to assume a length, checks its key first,
and fails on a wrong-length speech (A1 to A5).

The transport is stubbed in every test: `_llm_generate_once` is replaced in the
module namespace under test, so no model, no network and no paid service is reached.

The exit codes are the script's own contract:
  2 = no talk length in intake.json, or a missing/empty intake.json outside --dry-run
  3 = no key NAME set (checked before any model call)
  4 = the finished speech is outside +/-10 % of its word budget; the file is written
"""
import json
import re
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import speech_build_harness as sbh  # noqa: E402

KEY_ENV_NAMES = (
    "SPEECH_LLM_API_KEY",
    "OLLAMA_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
)

DECK_MARKDOWN = (
    "SLIDE 1\n**Welcome**\nSECTION: WELCOME\nPURPOSE: welcome\n"
    "PRESENTER NOTE: greet them.\n\n"
    "SLIDE 2\n**There is a difference**\nSECTION: HOOK\nPURPOSE: hook\n"
    "PRESENTER NOTE: open the loop.\n"
)


def _clear_keys(monkeypatch):
    for name in KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("PRESENTATION_MODE", raising=False)


def _set_key(monkeypatch, name="OLLAMA_API_KEY"):
    _clear_keys(monkeypatch)
    monkeypatch.setenv(name, "stub-key")


def _deck_files(tmp_path):
    slides = tmp_path / "slides_copy.md"
    slides.write_text(DECK_MARKDOWN)
    arc = tmp_path / "arc_allocation.json"
    arc.write_text("{}")
    return slides, arc


def _write_intake(tmp_path, payload):
    p = tmp_path / "intake.json"
    p.write_text(json.dumps(payload) if isinstance(payload, dict) else payload)
    return p


def _stub_transport(fraction_of_budget, calls):
    """Stub writer: emit `fraction_of_budget` of the slide's stated WORD BUDGET."""

    def _stub(prompt, model, api_key, max_tokens=1024, base_url=None, temperature=0.7):
        calls.append(prompt)
        m = re.search(r"WORD BUDGET: exactly (\d+) words", prompt)
        budget = int(m.group(1)) if m else 100
        sentence = "these are spoken words for this slide now "
        n = max(1, int(budget * fraction_of_budget) // len(sentence.split()))
        return (sentence * n).strip()

    return _stub


def _run_main(monkeypatch, tmp_path, capsys, *, intake_payload, fraction,
              rounds="1", extra_argv=()):
    """Run main() end to end with a stubbed transport. Returns (exit code, calls)."""
    slides, arc = _deck_files(tmp_path)
    intake = _write_intake(tmp_path, intake_payload)
    out = tmp_path / "PRESENTERS-SPEECH.md"
    workdir = tmp_path / "work"

    calls = []
    original = sbh._llm_generate_once
    sbh._llm_generate_once = _stub_transport(fraction, calls)
    argv = [
        "speech_build_harness.py",
        "--intake", str(intake),
        "--slides", str(slides),
        "--arc", str(arc),
        "--out", str(out),
        "--workdir", str(workdir),
        "--max-expand-rounds", rounds,
        *extra_argv,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        try:
            sbh.main()
            code = None
        except SystemExit as exc:
            code = exc.value.code
    finally:
        sbh._llm_generate_once = original
    return code, calls, out, capsys.readouterr()


def test_a1_no_talk_length_exits_2(monkeypatch, tmp_path, capsys):
    """A1: neither target_talk_minutes nor DURATION_MIN -> exit 2 with the message.

    A key is set, so this also proves the length check runs BEFORE the key check.
    """
    _set_key(monkeypatch)
    code, calls, out, captured = _run_main(
        monkeypatch, tmp_path, capsys,
        intake_payload={"DECK_SLUG": "x", "TONE": "warm"},
        fraction=1.0,
    )
    assert code == 2
    assert "no talk length in intake.json (target_talk_minutes); refusing to assume one" in captured.err
    assert calls == []
    assert not out.exists()


def test_a1_legacy_duration_min_is_accepted(monkeypatch, tmp_path, capsys):
    """A1 companion: the legacy DURATION_MIN key is still a real talk length."""
    _set_key(monkeypatch)
    code, calls, out, _ = _run_main(
        monkeypatch, tmp_path, capsys,
        intake_payload={"DURATION_MIN": 45, "DECK_SLUG": "x"},
        fraction=1.0,
    )
    assert code is None
    assert calls  # the build ran
    assert out.exists()


def test_a2_empty_intake_outside_dry_run_exits_2(monkeypatch, tmp_path, capsys):
    """A2: an empty intake file outside --dry-run -> exit 2 (no 30-minute stub)."""
    _set_key(monkeypatch)
    code, calls, out, captured = _run_main(
        monkeypatch, tmp_path, capsys,
        intake_payload="",
        fraction=1.0,
    )
    assert code == 2
    assert "intake.json is missing or empty" in captured.err
    assert calls == []


def test_a3_wrong_length_writes_file_and_exits_4(monkeypatch, tmp_path, capsys):
    """A3: a build at 70 % of the target -> exit 4, the file exists, ratio reported."""
    _set_key(monkeypatch)
    code, calls, out, captured = _run_main(
        monkeypatch, tmp_path, capsys,
        intake_payload={"target_talk_minutes": 10, "DECK_SLUG": "x"},
        fraction=0.70,
    )
    assert code == 4
    assert calls  # a build really ran
    assert out.exists()  # the speech is kept, not thrown away
    assert "70.00%" in captured.err
    assert "outside +/-10%" in captured.err


def test_a4_45_minute_intake_budgets_for_45(monkeypatch, tmp_path):
    """A4: a 45-minute intake budgets for 45 minutes, not the old 30."""
    _set_key(monkeypatch)
    slides, arc = _deck_files(tmp_path)
    calls = []
    original = sbh._llm_generate_once
    sbh._llm_generate_once = _stub_transport(1.0, calls)
    try:
        ledger = sbh.run_build(
            intake={"target_talk_minutes": 45, "DECK_SLUG": "x"},
            slides=sbh.load_slides(str(slides), str(arc)),
            workdir=tmp_path / "work",
            out_path=tmp_path / "speech.md",
            model="stub",
            fallback_model=None,
            api_key="stub-key",
            wpm=sbh.DEFAULT_WPM,
            max_expand_rounds=1,
        )
    finally:
        sbh._llm_generate_once = original
    assert ledger.duration_min == 45.0
    # The same formula compute_budgets uses, for a 45-minute talk with this deck's
    # pause count — no assumed length anywhere in the path.
    misc_pauses = max(4, len(ledger.slides) // 5)
    pause_sec = misc_pauses * sbh.DEFAULT_PAUSE_MISC_SEC
    net_45 = max(45.0 * 60 - pause_sec, 45.0 * 60 * 0.80)
    net_30 = max(30.0 * 60 - pause_sec, 30.0 * 60 * 0.80)
    assert ledger.target_words == int(net_45 * (sbh.DEFAULT_WPM / 60.0))
    assert ledger.target_words > int(net_30 * (sbh.DEFAULT_WPM / 60.0))


def test_a5_no_key_exits_3_without_calling_the_transport(monkeypatch, tmp_path, capsys):
    """A5: no key name set -> exit 3, and the transport is called zero times."""
    _clear_keys(monkeypatch)
    code, calls, out, captured = _run_main(
        monkeypatch, tmp_path, capsys,
        intake_payload={"target_talk_minutes": 45, "DECK_SLUG": "x"},
        fraction=1.0,
    )
    assert code == 3
    assert calls == []
    assert "no LLM API key set" in captured.err
    assert not out.exists()
