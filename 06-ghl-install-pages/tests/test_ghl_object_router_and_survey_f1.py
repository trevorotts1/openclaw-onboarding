"""Offline tests for the two U1/U7 foundation pieces (no network, no browser):

  • ghl_survey_builder F1/F2 — survey rail reuses API-pre-created custom fields
    (map-only), never creates fields in-browser by default; verbatim key contract.
  • ghl_object_router — the §3 mixed-use rail matrix + decision path.

These wrap the modules' own selftests AND add direct behavioural assertions so a
regression in the grocery-shopping rule or the rail-decision policy fails CI.
"""

import os
import sys
import tempfile

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_survey_builder as sb  # noqa: E402
import ghl_object_router as router  # noqa: E402


# ---------------------------------------------------------------------------
# Module selftests (belt-and-suspenders — the modules assert far more internally)
# ---------------------------------------------------------------------------
def test_survey_builder_selftest_passes():
    assert sb._selftest() == 0


def test_object_router_selftest_passes():
    assert router._selftest() == 0


# ---------------------------------------------------------------------------
# F1 — the survey rail must NOT create custom fields in the browser by default
# ---------------------------------------------------------------------------
def test_default_field_creation_is_api():
    with tempfile.TemporaryDirectory() as tmp:
        res = sb.build_survey(
            {"survey_name": "S", "title": "S", "folder_name": "F",
             "location_id": "LOC", "brief": {"s": 1}},
            tmp, dry_run=True)
    assert res["field_creation"] == "api"
    assert "dependency_plan" in res and res["dependency_plan_path"]


def test_api_mode_clicklist_has_no_inbrowser_field_creation():
    cl = sb._emit_click_list(sb.REFERENCE_FIELDS, "F", "S", "Acme", "camp",
                             "Hi", "LOC", field_creation="api")
    import json
    blob = json.dumps(cl).lower()
    assert "create custom field" not in blob
    assert "add custom field" not in blob
    # Part 1 is a single 'skip' step delegating to Skill 44.
    assert any(s["phase"] == "P1" and s["action"] == "skip" for s in cl["steps"])


def test_browser_mode_retains_legacy_create_path():
    cl = sb._emit_click_list(sb.REFERENCE_FIELDS, "F", "S", "Acme", "camp",
                             "Hi", "LOC", field_creation="browser")
    import json
    assert "create custom field" in json.dumps(cl).lower()


# ---------------------------------------------------------------------------
# F2 — field-key contract (zhc idempotent-create vs verbatim must-pre-exist)
# ---------------------------------------------------------------------------
def test_zhc_key_prefixed_and_idempotent():
    k, p = sb._resolve_field_key({"label": "Business Stage"})
    assert p == "zhc" and k.startswith("zhc_")
    k2, _ = sb._resolve_field_key({"key": "zhc_already", "key_policy": "zhc"})
    assert k2 == "zhc_already"  # never double-prefixed


def test_verbatim_key_preserved_byte_for_byte():
    k, p = sb._resolve_field_key(
        {"label": "x", "key": "podcast_survey__additional_info",
         "key_policy": "verbatim"})
    assert p == "verbatim" and k == "podcast_survey__additional_info"


def test_dependency_plan_get_first_reuse_vs_create():
    dep = sb.plan_survey_dependencies(
        [{"label": "Fav Color", "type": "single_line"}],
        {"folder_name": "F"}, existing_field_keys=["zhc_fav_color"])
    assert dep["custom_fields"][0]["action"] == "reuse"
    dep2 = sb.plan_survey_dependencies(
        [{"label": "New One", "type": "single_line"}],
        {"folder_name": "F"}, existing_field_keys=[])
    assert dep2["custom_fields"][0]["action"] == "create"


def test_verbatim_missing_blocks_the_plan_loudly():
    dep = sb.plan_survey_dependencies(
        [{"label": "Engine", "key": "engine__key", "key_policy": "verbatim",
          "type": "single_line"}],
        {"folder_name": "F"}, existing_field_keys=["other"])
    assert dep["blocked"] is True and dep["missing_verbatim_keys"]


def test_map_only_preflight_stops_when_a_create_would_be_needed():
    with tempfile.TemporaryDirectory() as tmp:
        pf = sb._run_preflight(
            {"survey_name": "S", "title": "S", "location_id": "LOC",
             "field_creation": "map_only",
             "survey_fields": [{"label": "New Field", "type": "single_line",
                                "slide_name": "S1"}],
             "existing_field_keys": []},
            tmp)
    assert pf["pass"] is False


# ---------------------------------------------------------------------------
# Router — matrix + decision doctrine
# ---------------------------------------------------------------------------
def test_browser_only_objects_have_no_create_api():
    for t in ("form", "survey", "community", "course", "channel"):
        r = router.route(t)
        assert r.create_api_exists is False
        assert r.rails[0].rail == router.Rail.BROWSER


def test_api_first_objects_lead_with_non_browser_rail():
    for t in ("custom_field", "custom_value", "tag", "media"):
        assert router.route(t).rails[0].tier != router.Tier.BROWSER


def test_token_routing_f9():
    assert router.route("subaccount").rails[0].token == router.Token.OAUTH_COMPANY
    assert router.route("snapshot").rails[0].token == router.Token.AGENCY_PIT
    assert router.route("media").rails[0].token == router.Token.LOCATION_PIT


def test_429_never_tier_hops():
    with tempfile.TemporaryDirectory() as tmp:
        hop = {"rest": 0}

        def rest_runner(step):
            hop["rest"] += 1
            return router.RunResult(ok=True, response_id="x")

        res = router.execute_write(
            "tag", "zhc_429", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={
                router.Rail.SKILL44_CAF: lambda s: router.RunResult(ok=False, status=429),
                router.Rail.REST_SERVICES: rest_runner,
            },
            verifier=lambda rid: {"ok": True},
            rate_cooldown=lambda s: None)
    assert hop["rest"] == 0
    assert res["action"] == "failed" and res["board_note"] == "RATE-LIMIT"


def test_verify_failure_fails_even_when_write_succeeds():
    with tempfile.TemporaryDirectory() as tmp:
        res = router.execute_write(
            "survey", "zhc_s", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={router.Rail.BROWSER: lambda s: router.RunResult(ok=True, response_id="s1")},
            verifier=lambda rid: {"ok": False, "detail": "public URL 404"})
    assert res["action"] == "failed" and res["board_note"] == "VERIFY-FAIL"


def test_disclosure_format():
    d = router.tier_disclosure(router.route("custom_field").rails[0])
    assert d.startswith("[GHL tier used: 0 — ") and d.endswith("]")
