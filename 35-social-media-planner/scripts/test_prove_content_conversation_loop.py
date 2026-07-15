#!/usr/bin/env python3
"""test_prove_content_conversation_loop.py — CI wrapper + fail-first regression
for U88/GK-26's OFFLINE/FIXTURE content->conversation loop proof run.

Wires `prove_content_conversation_loop.py` into the standard pytest run and
pins the two honesty properties the module docstring promises:

  1. Zero client-visible messages: FixtureAdapters makes no network call of
     any kind, and the default `run()` path never instantiates LiveAdapters.
  2. LiveAdapters never silently fabricates a live result -- every method
     raises NotImplementedError naming the exact real call it stands in for
     (the LIVE-PROOF tier this unit still owes, per the master spec's
     ratified PER-REPO/OFFLINE ACCEPTANCE DOCTRINE).

No network, no browser, no live GHL/Command Center/box calls.

Run: pytest 35-social-media-planner/scripts/test_prove_content_conversation_loop.py -q
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "prove_content_conversation_loop.py")


def _load():
    spec = importlib.util.spec_from_file_location(
        "prove_content_conversation_loop", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


proof = _load()


def test_module_exists():
    assert os.path.exists(_MODULE_PATH), "prove_content_conversation_loop.py must exist (U88/GK-26)"


# ---------------------------------------------------------------------------
# Whole-run proof (mirrors the U22/GK-26 sibling proof's CI-wrapper shape).
# ---------------------------------------------------------------------------

def test_offline_fixture_run_all_five_legs_pass(capsys):
    ok, bundle = proof.run()
    out = capsys.readouterr().out
    assert ok is True, out
    assert out.count("[PASS]") == 5, (
        f"expected exactly 5 leg PASS lines; got {out.count('[PASS]')}:\n{out}"
    )
    assert "[FAIL]" not in out
    assert bundle["overall_pass"] is True
    assert bundle["run_mode"] == "offline-fixture"
    assert bundle["zero_client_visible_messages"] is True
    assert bundle["live_proof_tier_owed"] is True
    for leg_key in ("leg1_pregen_gate_and_qc", "leg2_queued_post",
                    "leg3_inbound_conversation", "leg4_comment_handoff",
                    "leg5_gap_c_matcher"):
        assert leg_key in bundle["legs"], f"missing leg in bundle: {leg_key}"
        assert bundle["legs"][leg_key]["pass"] is True, bundle["legs"][leg_key]


def test_evidence_bundle_read_backs_present_and_typed(tmp_path):
    """BINARY acceptance (GK-26): 'one archived evidence bundle containing all
    five legs with read-backs (queued post id; conversation id + brain reply;
    fenced handoff file; matcher receipt) -- each leg pass/fail explicit.'
    Uses an explicit evidence_root so the read-back file is still on disk to
    inspect (the default tempdir run is intentionally wiped on return --
    covered separately by test_evidence_bundle_default_tempdir_is_cleaned_up_
    after_run)."""
    ok, bundle = proof.run(evidence_root=str(tmp_path / "read-back-check"))
    assert ok is True
    legs = bundle["legs"]
    assert isinstance(legs["leg2_queued_post"]["queued_post_id"], str)
    assert legs["leg2_queued_post"]["queued_post_id"]
    assert isinstance(legs["leg3_inbound_conversation"]["conversation_id"], str)
    assert isinstance(legs["leg3_inbound_conversation"]["brain_reply"], str)
    assert legs["leg3_inbound_conversation"]["brain_reply"]
    assert isinstance(legs["leg4_comment_handoff"]["fenced_handoff_file"], str)
    assert os.path.isfile(legs["leg4_comment_handoff"]["fenced_handoff_file"])
    assert legs["leg5_gap_c_matcher"]["matcher_receipt"] is not None
    assert "matched_template" in legs["leg5_gap_c_matcher"]["matcher_receipt"]


def test_offline_fixture_run_is_deterministic():
    """Same fixtures in, same result out (minus the timestamp/tempdir path)."""
    _, bundle_a = proof.run()
    _, bundle_b = proof.run()
    for b in (bundle_a, bundle_b):
        b.pop("generated_at", None)
        b.pop("_bundle_path", None)
        b["legs"]["leg4_comment_handoff"].pop("fenced_handoff_file", None)
        for entry in b["legs"]["leg4_comment_handoff"]["handed_off"]:
            entry.pop("log_path", None)
        b["step_f_preflight"] = None  # subprocess timing-dependent, not content
    assert bundle_a == bundle_b


def test_evidence_bundle_default_tempdir_is_cleaned_up_after_run():
    """'Revert: delete the draft post + test conversation artifacts (both
    read-back-verified deleted).' The default (no explicit evidence_root) run
    writes into a tempdir that is wiped on return -- nothing persists."""
    ok, bundle = proof.run()
    assert ok is True
    bundle_path = bundle["_bundle_path"]
    assert not os.path.exists(bundle_path), (
        "default run() must clean up its own tempdir on exit (read-back-"
        "verified deletion) -- found a leftover file: " + bundle_path
    )


def test_evidence_bundle_persists_with_explicit_evidence_root(tmp_path):
    evidence_root = str(tmp_path / "u88-evidence")
    ok, bundle = proof.run(evidence_root=evidence_root)
    assert ok is True
    assert os.path.isfile(bundle["_bundle_path"])
    with open(bundle["_bundle_path"], encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["overall_pass"] is True
    assert on_disk["unit"] == "U88 (GK-26)"


# ---------------------------------------------------------------------------
# Individual legs (isolate a regression to the exact leg that broke it).
# ---------------------------------------------------------------------------

def test_leg1_cta_is_dm_first_with_comment_backup():
    leg1 = proof.leg1_pregen_gate_and_qc()
    assert leg1["pass"] is True
    assert leg1["pregen_gate_ok"] is True
    assert leg1["pregen_gate_exit_code"] == 0
    assert leg1["cta_dm_first_with_comment_backup"] is True
    copy_lc = leg1["post_copy"].lower()
    assert copy_lc.index("dm") < copy_lc.index("comment")


def test_leg1_pregen_gate_actually_gates_a_bad_prompt():
    """Fail-first anchor: the REAL pregen gate must still reject a malformed
    prompt -- proves leg 1 calls the real function, not a stub that always
    says PASS."""
    import pregen_prompt_gate as pgg
    bad = pgg.check_prompt(
        "", model="nano-banana-2", ratio="not-a-ratio", pixels=None,
        platform="instagram", text_overlay=None, brand_colors=None,
        avoid_list_text=None, asset_source="internal-generated", qc_receipt=None,
    )
    assert bad.ok is False
    assert bad.exit_code == pgg.EXIT_FORM


def test_leg2_read_back_matches_queued_post_id():
    adapters = proof.FixtureAdapters(seed_id="leg2-test")
    leg2 = proof.leg2_queue_draft_post(adapters, "post copy for leg 2 test")
    assert leg2["pass"] is True
    assert leg2["queued_post_id"] == "fixture-post-leg2-test"
    assert leg2["read_back"]["id"] == leg2["queued_post_id"]
    assert leg2["read_back"]["status"] == "draft"


def test_leg3_reuses_skill38_own_proven_fixtures_verbatim():
    """Leg 3 must resolve against Skill 38's OWN fixture pair, not a
    reinvented one -- pins active_workflow/phase/tools to the real, already
    shipped tools/tests/fixtures/sample-log.md + good-playbook.md pair."""
    adapters = proof.FixtureAdapters()
    leg3 = proof.leg3_inbound_dm_tier_ladder(adapters)
    assert leg3["pass"] is True
    ladder = leg3["tier_ladder"]
    assert ladder["active_workflow"] == "good-playbook"
    assert ladder["active_phase"] == 4
    assert ladder["model_tier"] == "realtime-standard"
    assert "book_appointment" in ladder["enabled_tools"]
    assert "escalate_to_human" in ladder["enabled_tools"], (
        "escalate_to_human must always be granted (playbook_engine.py "
        "ALWAYS_GRANTED) -- a broken tier-ladder resolution would drop it."
    )
    assert leg3["conversation_id"]
    assert leg3["brain_reply"]


def test_leg4_unsupported_channel_is_ledgered_not_fabricated(tmp_path):
    """Fail-first anchor mirroring comment_reader's own honesty contract: an
    unsupported channel must be skipped with a reason, never silently
    dropped or faked as handed-off."""
    import comment_reader
    summary = comment_reader.run(
        [{"channel": "tiktok", "author_id": "x", "text": "hi",
          "post_id": "p1", "comment_id": "c1"}],
        str(tmp_path), dry_run=True)
    assert summary["handed_off"] == []
    assert len(summary["skipped"]) == 1
    assert summary["skipped"][0]["reason"].startswith("no comment-read API surface")


def test_leg4_fenced_handoff_neutralizes_injection_attempt(tmp_path):
    """The comment body is attacker-controlled -- a crafted comment trying to
    forge a new inbound turn or delimiter token must come out neutralized in
    the handoff leg's own write, not just in comment_reader's unit tests."""
    evidence_root = str(tmp_path)
    leg4 = proof.leg4_comment_handoff(evidence_root)
    assert leg4["pass"] is True
    text = open(leg4["fenced_handoff_file"], encoding="utf-8").read()
    assert "<<<UNTRUSTED-PUBLIC-COMMENT" in text
    assert "<<<END-UNTRUSTED-PUBLIC-COMMENT>>>" in text


def test_leg5_client_link_wins_matcher_never_invoked():
    catalog = proof._load_catalog()
    result = proof.resolve_post_link(
        "https://client-domain.example/their-own-page",
        proof._GAP_C_REQUEST_TEXT, catalog)
    assert result["source"] == "client_supplied"
    assert result["matcher_invoked"] is False
    assert result["matcher_receipt"] is None
    assert result["link"] == "https://client-domain.example/their-own-page"


def test_leg5_no_client_link_falls_back_to_matcher():
    catalog = proof._load_catalog()
    result = proof.resolve_post_link(None, proof._GAP_C_REQUEST_TEXT, catalog)
    assert result["source"] == "matcher"
    assert result["matcher_invoked"] is True
    assert result["matcher_receipt"]["matched_template"] in proof._GAP_C_EXPECTED_TEMPLATES
    assert result["link"] == proof._fixture_page_link_for_template(
        result["matcher_receipt"]["matched_template"])


def test_leg5_fixture_page_link_is_not_a_real_resolvable_url():
    """The Gap-C link resolved from the matcher branch must be an obviously
    non-real placeholder -- never mistakable for a live page URL."""
    link = proof._fixture_page_link_for_template("lead-magnet")
    assert link.startswith("<GHL-PAGE-URL-PLACEHOLDER:")
    assert not link.startswith("http")


# ---------------------------------------------------------------------------
# Honesty gates: zero client-visible messages; LiveAdapters never fabricated.
# ---------------------------------------------------------------------------

def test_zero_network_import_in_module():
    """No networking primitive is imported at module scope anywhere in this
    file -- the offline proof cannot accidentally reach a live endpoint."""
    src = open(_MODULE_PATH, encoding="utf-8").read()
    for banned in ("import requests", "import http.client", "import socket\n"):
        assert banned not in src, f"unexpected networking import found: {banned!r}"


def test_default_run_never_touches_urllib(monkeypatch):
    """Patch urllib.request.urlopen to explode; the default (fixture-mode)
    run must still succeed untouched -- proving no leg reaches for a live
    network call under the hood."""
    def _boom(*a, **k):
        raise AssertionError("urllib.request.urlopen must never be called "
                              "by the OFFLINE/FIXTURE proof run")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    ok, bundle = proof.run()
    assert ok is True
    assert bundle["overall_pass"] is True


def test_live_adapters_never_silently_fabricate_a_result():
    live = proof.LiveAdapters()
    for method_name, kwargs in (
        ("create_social_post", {"account_ids": ["a"], "text": "t"}),
        ("read_social_post", {"post_id": "p"}),
        ("deliver_inbound_dm", {"contact_id": "c", "text": "t"}),
        ("brain_reply", {"resolved_tier_ladder": {}}),
    ):
        method = getattr(live, method_name)
        try:
            method(**kwargs)
            raised = False
        except NotImplementedError as exc:
            raised = True
            assert "LIVE-PROOF tier owed" in str(exc)
        assert raised, f"LiveAdapters.{method_name} must raise, never fabricate a live result"


def test_default_run_never_instantiates_live_adapters(monkeypatch):
    """A regression that swapped FixtureAdapters for LiveAdapters as the
    default would blow up immediately -- LiveAdapters always raises."""
    calls = []
    real_init = proof.LiveAdapters.__init__ if hasattr(proof.LiveAdapters, "__init__") else None

    class _Sentinel(proof.LiveAdapters):
        def __init__(self):
            calls.append(1)
            super().__init__()

    monkeypatch.setattr(proof, "LiveAdapters", _Sentinel)
    ok, bundle = proof.run()
    assert ok is True
    assert calls == [], "run()'s default path must never instantiate LiveAdapters"


def test_liveadapters_methods_have_no_implementation_body_beyond_raise():
    """Guards against someone quietly filling in a live call without also
    updating this file's honesty tests -- every LiveAdapters method's only
    statement is the NotImplementedError raise."""
    for name in ("create_social_post", "read_social_post",
                "deliver_inbound_dm", "brain_reply"):
        method = getattr(proof.LiveAdapters, name)
        src = inspect.getsource(method)
        assert "raise NotImplementedError" in src
        assert "urllib" not in src and "subprocess" not in src and "socket" not in src


# ---------------------------------------------------------------------------
# CLI entry point.
# ---------------------------------------------------------------------------

def test_main_returns_zero_on_success(capsys):
    rc = proof.main([])
    capsys.readouterr()
    assert rc == 0


def test_main_persists_to_explicit_evidence_root(tmp_path, capsys):
    evidence_root = str(tmp_path / "cli-evidence")
    rc = proof.main(["--evidence-root", evidence_root])
    capsys.readouterr()
    assert rc == 0
    assert os.path.isfile(
        os.path.join(evidence_root, "u88-content-conversation-loop-evidence.json"))
