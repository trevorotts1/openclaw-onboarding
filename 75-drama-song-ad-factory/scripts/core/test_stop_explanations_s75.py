#!/usr/bin/env python3
"""Every stop explains itself: what happened, why the rule exists, the fix,
and the client's choices (owner order 2026-11-20). Offline, no spend.

Run: python3 scripts/core/test_stop_explanations_s75.py   (also collects as pytest)

The INVENTORY below is every place in this skill where the work stops,
refuses, holds or waits and the client would see it. A new client-facing stop
must be added here AND given a row in references/client-messages.md ("Every
stop explained"); ``test_every_inventoried_stop_has_a_row`` fails otherwise,
and ``test_inventory_matches_the_code`` fails when a scanned module grows a
stop code that is neither inventoried nor named internal.
"""
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import loud_failure as LF                         # noqa: E402
import suno_recipe as R                           # noqa: E402

# code -> where the client meets it (source of the stop)
INVENTORY = {
    # music: lyric checks (suno_recipe.prepare, raised from build_requests in cmd_generate)
    "LYRICS_REJECTED": "suno_recipe.prepare -> song_choices.build_requests / cmd_generate",
    "LYRICS_REJECTED/words_over_budget": "suno_recipe.check_lyric_sheet word budget",
    "LYRICS_REJECTED/opener_over_cap": "suno_recipe.check_lyric_sheet spoken-intro cap",
    "LYRICS_REJECTED/line_under_no_voice_cue": "suno_recipe.check_no_voice_lines",
    "CAST_REJECTED": "suno_recipe.build_request ensemble gate",
    "VOICE_TAG_MISMATCH": "suno_recipe.guard_request voice tags",
    "STYLE_TOO_LONG": "suno_recipe style cap",
    "UNTAGGED_LYRIC_LINES": "suno_recipe.parse_lyrics",
    "SONG_LENGTH_NOT_SUPPORTED": "song_choices.build_requests",
    # music: song stage
    "SONG_FAILURE_AWAITING_CLIENT": "factory.music_stage (song judge failed: client fork)",
    "SONG_PICK_MISSING": "song_choices.refusal",
    "SONG_APPROVAL_UNANSWERED": "song_choices._unanswered_hold",
    "SONG_CONSTITUENT_EVIDENCE_MISSING": "song_choices.constituent_hold",
    "ACCEPTANCE_NOT_PROVEN": "song_dispatch acceptance hold",
    "EMPTY_TAKE_LIST": "song_choices.run_takes",
    "SONG_SAVE_FAILED": "song_choices save recovery",
    # money and redo limits (spend_ledger, carried by kie_dispatch)
    "MISSING_AUTH_REF": "spend_ledger.plan creative retake without the client's OK",
    "REPAIR_CAP": "spend_ledger.plan redo limit",
    "REPAIR_CAP_EXHAUSTED": "retake_manager redo limit",
    "BUDGET_EXCEEDED": "spend_ledger.can_spend",
    "NO_CEILING": "spend_ledger.init_run",
    "UNKNOWN_PRICE": "spend_ledger.can_spend / kie_dispatch",
    "RUN_PARKED": "spend_ledger",
    "RECONCILE_FIRST": "spend_ledger.plan",
    "DUPLICATE_LOGICAL_JOB": "spend_ledger.plan",
    # approvals and the card
    "CARD_UNANSWERED": "card_gate / preflight / kie_dispatch / agnes_dispatch",
    "TESTIMONIAL_PERMISSION_MISSING": "factory next",
    "SCRIPT_AWAITING_APPROVAL": "factory script gate",
    "storyboard-approval-required": "factory next",
    "approval-missing": "preflight",
    "approval-expired": "preflight",
    "approval-out-of-scope": "preflight",
    # dispatch (kie_dispatch)
    "MODEL_REQUIRED": "kie_dispatch", "VIDEO_MODEL_LOCK_MISSING": "kie_dispatch",
    "VIDEO_MODEL_MISMATCH": "kie_dispatch", "VIDEO_MODEL_DOWN": "kie_dispatch",
    "kie-rate-limited-not-submitted": "kie_dispatch",
    "preflight-shortfall": "kie_dispatch", "preflight-failed": "kie_dispatch",
    "preflight-unreadable": "kie_dispatch", "adapter-not-found": "kie_dispatch",
    "adapter-health-unreadable": "kie_dispatch", "adapter-mode-unknown": "kie_dispatch",
    "generation-not-switched-on": "kie_dispatch",
    "generation-skipped-not-generated": "kie_dispatch",
    "prompt-over-max": "kie_dispatch", "prompt-below-floor": "kie_dispatch",
    "prompt-budget-failed": "kie_dispatch", "prompt-budget-unreadable": "kie_dispatch",
    "kie-submit-failed": "kie_dispatch", "kie-run-failed": "kie_dispatch",
    "unknown-outcome-no-retry": "kie_dispatch", "ledger-settle-failed": "kie_dispatch",
    "dispatch-internal-error": "kie_dispatch",
    # preflight (intake_preflight/preflight.py)
    "schema-untrusted": "preflight", "delivery-profile-unknown": "preflight",
    "reference-outside-approved-storage": "preflight",
    "reference-missing-or-truncated": "preflight", "tool-unavailable": "preflight",
    "module-unavailable": "preflight", "storage-not-writable": "preflight",
    "disk-limit": "preflight", "credential-missing": "preflight",
    # retake manager
    "ACCEPTED_ARTIFACT": "retake_manager", "INVALID_REQUEST": "retake_manager",
    "PROFILE_UNAVAILABLE": "retake_manager", "UNKNOWN_ARTIFACT": "retake_manager",
}

# Codes the scanned modules raise that are operator/plumbing faults, not a
# client decision; they still get the four-part fallback (never a dead stop).
INTERNAL = {
    "BAD_BILLABLE", "BAD_OUTCOME", "BAD_OUTCOME_CLASS", "BAD_RETRY_CATEGORY",
    "BAD_TRACK_NO", "BAD_TRANSITION", "BAD_VERDICT", "DUPLICATE_ATTEMPT",
    "DUPLICATE_AUTHORIZATION", "DUPLICATE_PROVIDER_JOB", "LEASE_HELD",
    "MISSING_DIGEST", "MISSING_LOOKUP_REF", "MISSING_REMOTE_ID", "NO_SUCH_JOB",
    "NO_SUCH_RUN", "NO_SUCH_TRACK", "ORDINAL_MISMATCH", "PROVIDER_LOOKUP_REQUIRED",
    "RETRY_CATEGORY_MISMATCH", "STALE_VERSION", "TASK_TAKEN",
    "ILLEGAL_TRANSITION", "LEASE_EXPIRED_WAITING", "NOT_OWNER",
    "BAD_DELIVERED_S", "BAD_VOCAL_GENDER", "EXEMPT", "GENDER_REQUIRED",
    "NO_STYLE_PARTS", "RECIPE_BYPASSED", "REQUEST_ENVELOPE_REJECTED",
    "UNKNOWN_STYLE", "UNMEASURED",
    "SUBMIT_ALL_READY-EXCEPTION", "LIPSYNC_PICTURE_NOT_GATED",
    "ONSCREEN_TEXT_NOT_CHECKED", "SFX_JOB_NOT_ORDERED",
    "ZERO_ESTIMATE_FOR_PAID_JOB", "REQUEST_PLACEHOLDER",
}

SCANS = {   # module -> regexes that capture the stop codes it hands back
    "spend_ledger.py": [r'refuse\(\s*"([A-Za-z_-]+)"',
                        r'envelope\(\s*(?:cmd|"[a-z_]+")\s*,\s*"(?:rejected|waiting|error|parked)"\s*,\s*"([A-Za-z_-]+)"'],
    "kie_dispatch/kie_dispatch.py": [
        r'stop\(\s*"(?:rejected|waiting|error|parked)"\s*,\s*"([A-Za-z_-]+)"',
        r'"dispatch",\s*"(?:rejected|waiting|error|parked)",\s*"([A-Za-z_-]+)"'],
    "intake_preflight/factory.py": [r'_mres\(\s*"(?:waiting|rejected)"\s*,\s*"([A-Za-z_-]+)"'],
    "intake_preflight/preflight.py": [
        r'"outcome":\s*"(?:rejected|waiting|error)",\s*"reason_code":\s*"([A-Za-z_-]+)"'],
    "song_choices/song_choices.py": [r'reason_code="([A-Z_]+)"', r'"reason_code": "([A-Z_]+)"'],
    "suno_recipe/suno_recipe.py": [r'RecipeError\(\s*"([A-Z_]+)"'],
}
# preflight setup faults the operator repairs (the box, not a client choice)
INTERNAL |= {"PRODUCTION_PROCESS_UNVERIFIED", "requirements-empty",
             "manifest-unavailable"}

RAW_CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\b[a-z]+(?:-[a-z]+){2,}\b")
PATH = re.compile(r"(?:~|\.{1,2})?/[\w.\-]+/|\b\w+\.(?:py|json|sqlite3|sh)\b")


def _assert_plain(text, where):
    assert text and text.strip(), where
    assert not RAW_CODE.search(text), (where, RAW_CODE.search(text).group(0), text)
    assert not PATH.search(text), (where, text)
    assert "Traceback" not in text, (where, text)
    assert "{" not in text and "}" not in text, (where, text)


def _assert_four(parts, where):
    for k in LF.PARTS + ("message",):
        assert parts.get(k), (where, k, parts)
    assert 2 <= len(parts["choices"]) <= 4, (where, parts["choices"])
    for k in ("what_happened", "why", "fix", "message"):
        _assert_plain(parts[k], "%s/%s" % (where, k))
    for c in parts["choices"]:
        _assert_plain(c, "%s/choice" % where)


def test_every_table_row_has_four_parts_and_two_choices():
    table = LF.explanation_table()
    assert len(table) >= len(INVENTORY), len(table)
    for code, row in table.items():
        for k in ("what_happened", "why", "fix"):
            assert row[k].strip(), (code, k)
        assert 2 <= len(row["choices"]) <= 4, (code, row["choices"])


def test_every_inventoried_stop_has_a_row():
    missing = sorted(set(INVENTORY) - set(LF.explanation_table()))
    assert not missing, "stops with no explanation row: %s" % missing


def test_inventory_matches_the_code():
    found = set()
    for rel, pats in SCANS.items():
        text = open(os.path.join(HERE, rel), encoding="utf-8").read()
        for p in pats:
            found |= set(re.findall(p, text))
    unknown = sorted(found - set(INVENTORY) - INTERNAL)
    assert not unknown, ("new stop codes need an INVENTORY entry and a table "
                         "row, or an INTERNAL entry: %s" % unknown)


def test_rendered_messages_are_plain():
    for code in LF.explanation_table():
        _assert_four(LF.explain_stop(code.split("/")[0] if "/" in code else code), code)


def test_unknown_code_falls_back_to_four_parts():
    env = {"reason_code": "SOMETHING_NEW",
           "detail": "SOMETHING_NEW: broke at /tmp/x/run/a.json\nTraceback (most recent call last): boom",
           "next_action": "re-run factory.py next --run-dir /tmp/x"}
    _assert_four(LF.explain_stop("SOMETHING_NEW", None, env), "fallback-dirty")
    clean = LF.explain_stop("ODD_STOP", None, {
        "detail": "ODD_STOP: the cover title came back blank",
        "next_action": "add the cover title and try again"})
    _assert_four(clean, "fallback-clean")
    assert "cover title came back blank" in clean["what_happened"], clean
    _assert_four(LF.explain_stop(None, None, None), "fallback-empty")


SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": [" ".join(["word"] * 62)]},
         {"tag": "Verse", "delivery": "sung", "lines": [" ".join(["sing"] * 45)]},
         {"tag": "Hook 1", "delivery": "sung", "lines": ["rise up now"]},
         {"tag": "Bridge", "delivery": "spoken", "lines": ["a b c d e"]},
         {"tag": "Hook 2", "delivery": "sung", "lines": ["rise up now"]},
         {"tag": "Hook 3", "delivery": "sung", "lines": ["rise up now"]},
         {"tag": "Outro", "delivery": "spoken", "lines": [" ".join(["call"] * 14)]}]


def test_lyric_word_budget_names_the_length_that_fits():
    total = R.sheet_words(SHEET)
    assert total == 135, total
    fit = R.length_that_fits(SHEET, "soul-ballad")
    L = fit["words_fit_length_s"]
    assert L == 120, fit
    # held in step with the gate itself: the word-budget error is gone at the
    # named length and present at the offered length before it
    def budget_errs(length):
        return [e for e in R.check_lyric_sheet(SHEET, "rise up now", length - 2,
                                               style_id="soul-ballad")
                if re.search(r"\d+ words, the \d+ s budget", e)]
    assert not budget_errs(L), budget_errs(L)
    assert budget_errs(90), "the 90 s card must still refuse 135 words"
    detail = "; ".join(R.check_lyric_sheet(SHEET, "rise up now", 88, style_id="soul-ballad"))
    out = LF.explain_stop("LYRICS_REJECTED", {"fit_length_s": L}, {"detail": detail})
    _assert_four(out, "lyrics")
    w = out["what_happened"]
    assert "135 words" in w and "90-second" in w and "about 95" in w, w
    assert "62 words" in w and "about 3 spoken words" in w, w
    assert "2-minute song fits" in out["fix"], out["fix"]
    joined = " | ".join(out["choices"])
    assert "make the song longer, up to 2 minutes" in joined, joined
    assert "trim the words" in joined and "show you" in joined, joined
    assert "Keep your words as they are and I check again" in joined, joined


def test_no_voice_cue_line_is_named():
    raw = "[Intro (spoken)]\nOne door.\n[Instrumental Break]\n6 s, band only\n"
    errs = R.check_no_voice_lines(raw)
    assert errs, raw
    out = LF.explain_stop("LYRICS_REJECTED", None, {"detail": "; ".join(errs)})
    _assert_four(out, "no-voice")
    assert "6 s, band only" in out["what_happened"], out["what_happened"]
    assert ".." not in out["what_happened"], out["what_happened"]


def test_placeholders_fill_with_real_numbers():
    rc = LF.explain_stop("REPAIR_CAP", None, {"next_action":
         "retry count exceeds approved repair cap 2; this attempt would be repair 3"})
    assert "redone 2 times" in rc["what_happened"] and "redo number 3" in rc["what_happened"], rc
    card = LF.explain_stop("CARD_UNANSWERED", None, {"missing": ["video_model", "length"]})
    assert "video model, length" in card["what_happened"], card
    short = LF.explain_stop("preflight-shortfall", {"shortfall": 412})
    assert "412 credits" in short["what_happened"], short
    sl = LF.explain_stop("SONG_LENGTH_NOT_SUPPORTED", None, {"detail":
         "the ad asks for a 600-second song and the song provider makes one take "
         "of at most 360 seconds; choose 360 seconds or less."})
    assert "600-second" in sl["what_happened"] and "360" in sl["fix"], sl


def test_required_codes_carry_their_choices():
    auth = LF.explain_stop("MISSING_AUTH_REF")
    assert any("record your OK" in c for c in auth["choices"]), auth
    fork = LF.explain_stop("SONG_FAILURE_AWAITING_CLIENT")
    assert [c.split(" (")[0].rstrip(".") for c in fork["choices"][:3]] == \
        ["Redo all of them", "Keep one of these three", "Generate three new options"], fork


def test_wired_envelopes_carry_the_explanation_and_keep_their_fields():
    from kie_dispatch import kie_dispatch as KD
    from intake_preflight import factory as F
    e = KD.envelope("dispatch", "rejected", "MISSING_AUTH_REF", "needs auth")
    assert e["reason_code"] == "MISSING_AUTH_REF" and e["outcome"] == "rejected"
    _assert_four(e["client_explanation"], "kie envelope")
    assert "client_explanation" not in KD.envelope("dispatch", "ok", "KIE_DISPATCH_OK")
    m = F._mres("waiting", "SONG_FAILURE_AWAITING_CLIENT", "fork")
    assert m["reason_code"] == "SONG_FAILURE_AWAITING_CLIENT" and m["detail"] == "fork"
    _assert_four(m["client_explanation"], "music block")
    assert "client_explanation" not in F._mres("ok", "music-complete", "done")
    f = F.envelope("music", "r", "error", "MUSIC_OWNER_REQUIRED", "name the worker")
    _assert_four(f["client_explanation"], "factory envelope")


def test_cmd_generate_lyric_refusal_carries_the_explanation():
    from song_choices import song_choices as SC
    d = tempfile.mkdtemp(prefix="s75-explain-")
    text = "".join("[%s: %s]\n%s\n" % (s["tag"], s["delivery"], "\n".join(s["lines"]))
                   for s in SHEET)
    req = os.path.join(d, "req.json")
    with open(req, "w", encoding="utf-8") as fh:
        json.dump({"style_id": "soul-ballad", "sheet_text": text,
                   "client_text": "rise up now", "title": "T", "length_s": 88}, fh)
    a = types.SimpleNamespace(run_dir=d, request=req, ledger="", run_id="",
                              variant="", unit_id="")
    try:
        SC.cmd_generate(a, generate=lambda *x, **k: [], measure=lambda t: {},
                        save=lambda *x, **k: None)
    except R.RecipeError as exc:
        assert exc.code == "LYRICS_REJECTED", exc      # the gate itself is unchanged
        out = exc.client_explanation
        _assert_four(out, "cmd_generate")
        assert "2-minute song fits" in out["fix"], out["fix"]
    else:
        raise AssertionError("the 135-word sheet must still be refused at 90 s")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("%d passed" % len(tests))
