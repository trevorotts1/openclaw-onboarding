#!/usr/bin/env python3
"""FU-AI-MODELS-QUESTION tests: live role binding + dispatch admission (repair D01).
Run: python3 core/choice_card/intake_card/test_ai_models.py  (or pytest)
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import ai_models as AM  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402
from intake_preflight import intake as INT  # noqa: E402

REC = {"build": "openrouter/xiaomi/mimo-v2.6-pro", "check": "openrouter/z-ai/glm-5.3", "route": "openrouter"}
MIMO = "openrouter/xiaomi/mimo-v2.6-pro"
GLM = "openrouter/z-ai/glm-5.3"


def _summary(brief):
    return INT.summarize(INT.normalize(brief)[0])[0]


def _run_dir():
    return tempfile.mkdtemp(prefix="skill75-ai-models-")


#: AI MODELS is the first of the nine production choices; the five story-brief
#: questions (DSR-105) open the card ahead of it.
MODELS_AT = [q["id"] for q in IC.QUESTIONS].index("models") + 1
#: The brief answers that come before AI MODELS, so a reply lands on it.
BRIEF = IC.example_replies()[:MODELS_AT - 1]


def test_catalog_defaults_bind_mimo_build_glm_check():
    assert AM.recommended() == REC
    assert REC["build"] in AM.MODELS and REC["check"] in AM.MODELS
    assert AM.MODELS[REC["check"]]["reasoning"]["efforts"] == ["low", "high", "max"]
    assert AM.MODELS[REC["build"]]["reasoning"]["effort_selector"] is False  # never fabricated


def test_no_family_is_excluded_from_the_catalog():
    # No vendor rule: nothing is filtered out of the catalog by family name.
    assert not hasattr(AM, "banned_hits")
    assert len(AM.selectable()) == len(AM.MODELS)


def test_two_plain_language_selection_questions_one_recommended_pair():
    q = AM.selection_questions()
    assert [x["ask"] for x in q["questions"]] == [AM.BUILD_QUESTION, AM.CHECK_QUESTION]
    assert AM.BUILD_QUESTION == "Which available model should build and develop this?"
    assert AM.CHECK_QUESTION == "Which available model should check quality and fix problems?"
    assert q["recommended_pair"] == {"build": MIMO, "check": GLM, "rationale": q["recommended_pair"]["rationale"]}
    for question in q["questions"]:
        ids = [o["id"] for o in question["options"]]
        assert set(ids) <= {m["id"] for m in AM.selectable()}
        assert question["recommended"] is not None
    # OpenClaw gets the verified openrouter/ prefix identifiers (spec 7.1)
    oc = AM.selection_questions(runtime="openclaw")
    assert all(o["model_id"].startswith("openrouter/") or not o["id"].startswith("openrouter/")
               for o in oc["questions"][0]["options"])
    direct = AM.selection_questions(runtime="openrouter-direct")
    mimo_row = next(o for o in direct["questions"][0]["options"] if o["id"] == MIMO)
    assert mimo_row["model_id"] == "xiaomi/mimo-v2.6-pro"


def test_unavailable_or_inaccessible_model_is_never_selectable():
    off = {GLM: {"status": "unavailable", "reason": "no eligible endpoint"}}
    q = AM.selection_questions(availability=off)
    ids = [o["id"] for qn in q["questions"] for o in qn["options"]]
    assert GLM not in ids and MIMO in ids
    assert q["recommended_pair"]["check"] != GLM          # recommendation filtered too
    q2 = AM.selection_questions(access={MIMO: False})
    ids2 = [o["id"] for o in q2["questions"][0]["options"]]
    assert MIMO not in ids2
    q3 = AM.selection_questions(needs=["tool_use"], price_policy="local-only")
    assert all(AM.MODELS[o["id"]]["price_class"] == "local" for o in q3["questions"][0]["options"])


def test_selecting_mimo_binds_real_dispatch():
    rd = _run_dir()
    try:
        c, err = AM.parse("MiMo 2.6 Pro builds, GLM 5.3 checks")
        assert err is None and c == REC
        bound = AM.bind_roles(rd, "MiMo 2.6 Pro", "GLM 5.3")
        assert bound["ok"] is True and os.path.exists(bound["store"])
        assert AM.load_bindings(rd)["bindings"]["build"]["model_id"] == MIMO
        adm = AM.admit_dispatch(rd, "build", "mimo")
        assert adm["ok"] is True and adm["decision"] == "admit"
        assert adm["dispatch"]["claude-nine"] == "openrouter/xiaomi/mimo-v2.6-pro"
        assert adm["dispatch"]["openclaw"] == "openrouter/xiaomi/mimo-v2.6-pro"
        assert adm["dispatch"]["openrouter-direct"] == "xiaomi/mimo-v2.6-pro"
        rec = AM.record_attempt(
            rd, "build", "a1", requested_model="mimo",
            resolved_provider_model="xiaomi/mimo-v2.6-pro",
            response_model="xiaomi/mimo-v2.6-pro", route="openrouter",
            request_receipt="req-1", router_receipt="rtr-1",
            response_provider="DeepInfra")
        assert rec["ok"] is True
        row = rec["attempt"]
        assert row["binding"]["model_id"] == MIMO          # attempt carries its persisted role binding
        assert row["evidence"]["request_receipt"] == "req-1"
        assert row["evidence"]["router_receipt"] == "rtr-1"
        assert row["evidence"]["response_evidence"] == "response_metadata"
        assert len(row["evidence"]["correlation"]) == 64   # correlated request/router/response digest
        again = AM.load_bindings(rd)
        assert [a["attempt_id"] for a in again["attempts"]] == ["a1"]
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_unlisted_sonnet_request_is_unknown_not_banned():
    # Sonnet is not in the catalog (nothing is added automatically), so it is an
    # ordinary unknown name: MODEL_UNKNOWN, never MODEL_NOT_PERMITTED.
    for name in ("Sonnet", "sonnet-chain", "claude sonnet", "claude-sonnet-4.5"):
        res = AM.check_result(name, "GLM 5.3")
        assert res["ok"] is False and res["error_code"] == "MODEL_UNKNOWN", name
        assert res["selectable"] and res["recommended"] == REC and res["next_action"], name


def test_other_approved_models_stay_configurable():
    c, err = AM.parse("MiniMax M3 builds, GLM 5.3 checks")
    assert err is None and c["build"] == "ollama/minimax-m3" and c["route"] == "ollama"
    c, err = AM.parse("Claude Opus builds, GLM 5.3 checks")
    assert err is None and c["build"] == "opus-chain"
    for mid in ("haiku-chain", "fusion-chain", "ollama/agnes", "deepseek/deepseek-v4.1-flash"):
        assert mid in AM.MODELS
    rd = _run_dir()
    try:
        bound = AM.bind_roles(rd, "ollama", "kimi k2.6")     # aliases resolve, ollama stays bindable
        assert bound["ok"] is True
        assert bound["bindings"]["build"]["model_id"] == "ollama/deepseek-v4.1-flash"
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_unknown_model_refused_with_actionable_result():
    c, err = AM.parse("Banana builds, GLM 5.3 checks")
    assert c is None and 'cannot use "Banana"' in err and "GLM 5.3" in err
    res = AM.check_result("Banana", "GLM 5.3")
    assert res["error_code"] == "MODEL_UNKNOWN" and res["selectable"] and res["next_action"]
    st = IC.conversation(BRIEF + ["Banana builds, GLM 5.3 checks"])
    assert len(st["answers"]) == len(BRIEF) and st["message"].startswith("Sorry, I cannot use")
    assert AM.parse("2")[0] is None                      # "choose my own" alone asks for both names


def test_checker_must_differ_from_builder():
    res = AM.check_result("DeepSeek V4 Flash", "DeepSeek V4 Flash")
    assert res["ok"] is False and res["error_code"] == "SAME_MODEL_ROLES"
    c, err = AM.parse("DeepSeek V4 Flash builds, DeepSeek V4 Flash checks")
    assert c is None and "different model" in err


def test_dispatch_requires_the_stored_role_binding():
    rd = _run_dir()
    try:
        adm = AM.admit_dispatch(rd, "build", "mimo")
        assert adm["ok"] is False and adm["error_code"] == "NO_ROLE_BINDING"
        assert adm["next_action"]
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_attempt_identity_proven_never_by_label():
    rd = _run_dir()
    try:
        AM.bind_roles(rd, "MiMo 2.6 Pro", "GLM 5.3")
        base = dict(requested_model="mimo", resolved_provider_model="xiaomi/mimo-v2.6-pro",
                    response_model="xiaomi/mimo-v2.6-pro", route="openrouter")
        # the label or an alias is never proof of the model actually called
        for claim, code in (("MiMo 2.6 Pro (OpenRouter)", "PROOF_NOT_IDENTITY"),
                            ("mimo", "PROOF_NOT_IDENTITY"),
                            ("z-ai/glm-5.3", "RESPONSE_MISMATCH"),
                            ("deepseek/deepseek-v4-flash", "RESPONSE_MISMATCH")):
            rec = AM.record_attempt(rd, "build", "a1", response_model=claim, **{
                k: v for k, v in base.items() if k != "response_model"})
            assert rec["ok"] is False and rec["error_code"] == code, (claim, rec)
        rec = AM.record_attempt(rd, "build", "a1", response_evidence="label", **base)
        assert rec["ok"] is False and rec["error_code"] == "PROOF_NOT_IDENTITY"
        rec = AM.record_attempt(rd, "build", "a1", resolved_provider_model="z-ai/glm-5.3", **{
            k: v for k, v in base.items() if k != "resolved_provider_model"})
        assert rec["ok"] is False and rec["error_code"] == "RESOLVED_MISMATCH"
        # the model cannot be swapped under a bound role
        adm = AM.admit_dispatch(rd, "build", "GLM 5.3")
        assert adm["ok"] is False and adm["error_code"] == "MODEL_MISMATCH"
        good = AM.record_attempt(rd, "build", "a1", **base)
        assert good["ok"] is True
        dup = AM.record_attempt(rd, "build", "a1", **base)
        assert dup["ok"] is False and dup["error_code"] == "ATTEMPT_EXISTS"
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_reasoning_request_verified_never_fabricated():
    rd = _run_dir()
    try:
        AM.bind_roles(rd, "MiMo 2.6 Pro", "GLM 5.3")
        # MiMo has no effort selector: an effort is refused, not invented
        adm = AM.admit_dispatch(rd, "build", "mimo", reasoning_request={"effort": "high"})
        assert adm["ok"] is False and adm["error_code"] == "REASONING_NOT_SUPPORTED"
        adm = AM.admit_dispatch(rd, "build", "mimo")
        assert adm["ok"] is True and adm["reasoning_request"] is None
        # GLM 5.3 exposes low/high/max: high is real
        adm = AM.admit_dispatch(rd, "check", "GLM 5.3", reasoning_request={"effort": "high"})
        assert adm["ok"] is True and adm["reasoning_request"] == {"effort": "high"}
        adm = AM.admit_dispatch(rd, "check", "GLM 5.3", reasoning_request={"effort": "turbo"})
        assert adm["ok"] is False and adm["error_code"] == "REASONING_NOT_SUPPORTED"
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_route_verified_against_the_binding():
    rd = _run_dir()
    try:
        AM.bind_roles(rd, "MiMo 2.6 Pro", "GLM 5.3")
        adm = AM.admit_dispatch(rd, "build", "mimo", route="ollama")
        assert adm["ok"] is False and adm["error_code"] == "ROUTE_MISMATCH"
        adm = AM.admit_dispatch(rd, "build", "mimo", route="openrouter")
        assert adm["ok"] is True
    finally:
        shutil.rmtree(rd, ignore_errors=True)


def test_choice_is_recorded_in_the_approved_summary():
    mine = {"build": "ollama/deepseek-v4.1-flash", "check": "openrouter/z-ai/glm-5.3", "route": "ollama"}
    assert _summary({"ai_models": mine})["ai_models"] == mine
    assert _summary({})["ai_models"] == REC                     # card skipped -> recommended pair
    assert _summary({"ai_models": {"build": "Banana", "check": "GLM 5.3"}})["ai_models"] == REC
    assert _summary({"ai_models": {"build": "Sonnet", "check": "Sonnet"}})["ai_models"] == REC
    st = IC.conversation(BRIEF + ["1"])
    assert st["answers"][MODELS_AT - 1]["value"] == REC         # selecting the recommended pair stores it


def test_card_question_surface():
    q = AM.card_question()
    assert q["id"] == "models" and q["recommended"] == 0
    assert AM.recommended_text() == ("MiMo 2.6 Pro (OpenRouter) builds, GLM 5.3 (OpenRouter) checks")


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
