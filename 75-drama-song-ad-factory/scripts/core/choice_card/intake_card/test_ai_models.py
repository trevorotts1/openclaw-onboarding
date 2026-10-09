#!/usr/bin/env python3
"""FU-AI-MODELS-QUESTION tests. Run: python3 core/choice_card/intake_card/test_ai_models.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import ai_models as AM  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402
from intake_preflight import intake as INT  # noqa: E402

REC = {"build": "openrouter/z-ai/glm-5.3-flash", "check": "sonnet-chain", "route": "openrouter"}


def _summary(brief):
    return INT.summarize(INT.normalize(brief)[0])[0]


def test_models_is_the_first_question_with_the_exact_text():
    t = IC.render_step(1)
    assert t.startswith("Question 1 of %d - AI MODELS" % len(IC.QUESTIONS))
    assert ("Which AI should build your video, and which should check the work? "
            "OpenRouter is recommended because it's faster; Ollama works too.") in t
    assert "1. Recommended setup - An OpenRouter model builds, Claude Sonnet checks. (RECOMMENDED)" in t
    assert "2. Choose my own - Reply with the build model and the check model, " \
           "e.g. 'DeepSeek builds, Sonnet checks'." in t


def test_recommended_is_an_openrouter_build_not_ollama():
    for reply in ("1", "recommended"):
        c, err = AM.parse(reply)
        assert err is None and c == REC
    assert IC.conversation(["1"])["answers"][0]["value"] == REC


def test_ollama_choice_is_accepted():
    c, err = AM.parse("Ollama builds, Sonnet checks")
    assert err is None and c["route"] == "ollama" and c["check"] == "sonnet-chain"
    assert AM.parse("MiniMax M3 builds, Claude Sonnet checks")[0]["build"] == "ollama/minimax-m3"


def test_unknown_model_refused_politely():
    c, err = AM.parse("Banana builds, Sonnet checks")
    assert c is None and 'cannot use "Banana"' in err and "GLM 5.3 Flash" in err
    st = IC.conversation(["Banana builds, Sonnet checks"])
    assert st["answers"] == [] and st["message"].startswith("Sorry, I cannot use")
    assert AM.parse("2")[0] is None                      # "choose my own" alone asks for both names


def test_checker_identical_to_builder_refused():
    c, err = AM.parse("DeepSeek builds, DeepSeek checks")
    assert c is None and "different model" in err
    assert AM.check("Sonnet", "claude sonnet")[0] is None


def test_choice_is_recorded_in_the_approved_summary():
    mine = {"build": "ollama/deepseek-v4.1-flash", "check": "sonnet-chain", "route": "ollama"}
    assert _summary({"ai_models": mine})["ai_models"] == mine
    assert _summary({})["ai_models"] == REC                                     # card skipped -> recommended
    assert _summary({"ai_models": {"build": "Banana", "check": "Sonnet"}})["ai_models"] == REC
    assert _summary({"ai_models": {"build": "Sonnet", "check": "Sonnet"}})["ai_models"] == REC


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
