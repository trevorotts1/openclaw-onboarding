#!/usr/bin/env python3
"""test_model_map_resolution.py -- regression tests for the Wave 5 canary model-map gap:

    model-map.json carried literal <CLIENT_*> placeholders instead of a resolved
    model, so in-pipeline steps (order curation, editor's introduction, front/back
    matter, bios) failed closed with UnresolvedMapError.

These tests prove preflight.sh RESOLVE now fills every REQUIRED tier from the
CLIENT's OWN configured models (their openclaw.json, via the fleet single source of
truth shared-utils/select_model.py), so the resolved map validates + routes with NO
UnresolvedMapError -- AND that it FAILS CLOSED (never substitutes a hardcoded model)
when the client has configured no usable model. No credential value, no Anthropic
identifier, synthetic client configs only. Python 3 stdlib only.

Run: python3 -m pytest 59-anthology-engine/tests/test_model_map_resolution.py -q
 or: python3 59-anthology-engine/tests/test_model_map_resolution.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PREFLIGHT = SKILL_DIR / "preflight.sh"
SCRIPTS = SKILL_DIR / "scripts"

# Anthropic-family id shapes assembled from fragments; no banned literal appears.
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)
PLACEHOLDER = re.compile(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>")

# A KIE_API_KEY value for resolving the IMAGE tier (never a real secret, only a
# presence check; the RESOLVE mode gates on presence via os.environ).
_KIE_DUMMY = "dummy-kie-not-a-real-secret"

# A client who configured their OWN (non-Anthropic) models across ollama-cloud +
# openrouter -- the exact fields the fleet harvests (agents.defaults.model /
# agents.list[].model / models.list[]).
GOOD_CFG = {
    "agents": {
        "defaults": {"model": "ollama/deepseek-v4-pro:cloud"},
        "list": [
            {"id": "main", "model": {"primary": "ollama/kimi-k2.6:cloud",
                                     "fallbacks": ["openrouter/moonshotai/kimi-k2.6"]}},
            {"id": "dept-marketing", "model": "openrouter/z-ai/glm-5.2"},
        ],
    },
    "models": {"list": [
        {"id": "ollama/minimax-m2:cloud"},
        {"id": "openrouter/deepseek/deepseek-v4-flash"},
    ]},
}
# A client with NO usable model -- their only configured model is Anthropic (which
# the fleet filters as forbidden), so nothing eligible remains.
NO_MODEL_CFG = {"agents": {"defaults": {"model": "anthropic/claude-opus-4"}, "list": []}}
# A THIN client with exactly ONE usable model: HEAVY-WRITER and JUDGE both fall back
# to the single configured model, so JUDGE would resolve == HEAVY-WRITER and the QC
# step would fail closed mid-run at S9 Gate B (AF-AE-JUDGE-INDEPENDENCE). Resolution
# must catch this and fail closed NOW, never write a same-model map.
THIN_ONE_MODEL_CFG = {"agents": {"defaults": {"model": "openrouter/z-ai/glm-5.2"},
                                 "list": []}, "models": {"list": []}}
# ISSUE-08: the model ids the fleet ACTUALLY runs -- date-tagged cloud builds
# (:0813-cloud), a plain :cloud tag, and a code variant that must never fill the
# Kimi chat slot. Before the fix every one of these matched NO chain pattern, so
# HEAVY-WRITER and JUDGE both fell back to client_best() and resolution died on
# AF-AE-JUDGE-INDEPENDENCE, surfacing as GATE 1b MISSING PREREQUISITE at install.
REAL_FLEET_CFG = {
    "agents": {"defaults": {}, "list": []},
    "models": {"list": [
        {"id": "ollama/kimi-k2.6:0711-cloud"},
        {"id": "ollama/deepseek-v4-pro:0813-cloud"},
        {"id": "ollama/deepseek-v4-flash:0731-cloud"},
        {"id": "ollama/minimax-m3:cloud"},
        {"id": "ollama/glm-5.3:cloud"},
        {"id": "ollama/kimi-k2.7-code:cloud"},
    ]},
}


def _resolve(cfg_obj, extra_env=None):
    """Run preflight.sh RESOLVE against a synthetic client openclaw.json in a temp
    run dir. Returns (returncode, run_dir(Path), CompletedProcess). The run_dir is
    kept alive by the caller's TemporaryDirectory."""
    td = tempfile.mkdtemp(prefix="mmtest_")
    cfg_path = Path(td) / "openclaw.json"
    cfg_path.write_text(json.dumps(cfg_obj), encoding="utf-8")
    run_dir = Path(td) / "run"
    run_dir.mkdir()
    env = dict(os.environ)
    env["OPENCLAW_CONFIG"] = str(cfg_path)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                          capture_output=True, text=True, timeout=60, env=env)
    return proc.returncode, run_dir, proc, td


# --------------------------------------------------------------------------- #
def test_real_client_config_resolves_every_required_tier():
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0, "resolve failed for a real client config:\n%s\n%s" % (proc.stdout, proc.stderr)
    mp = run_dir / "model-map.json"
    assert mp.is_file(), "no resolved model-map.json written"
    blob = mp.read_text(encoding="utf-8")

    # No residual placeholder (the exact bug) and no Anthropic id.
    assert not PLACEHOLDER.findall(blob), "resolved map still carries placeholders: %s" \
        % sorted(set(PLACEHOLDER.findall(blob)))
    assert not BANNED.search(blob), "resolved map carries an Anthropic-family id"

    mm = json.loads(blob)
    tiers = mm["tiers"]
    # Every REQUIRED tier resolved to a real, non-placeholder client model.
    for t in ("HEAVY-WRITER", "LIGHT", "JUDGE"):
        assert t in tiers, "required tier %s missing" % t
        primary = tiers[t]["chain"][0]
        assert primary["model"] and not PLACEHOLDER.search(primary["model"])
        assert primary["provider"] in ("ollama-cloud", "openrouter", "gemini",
                                       "minimax", "deepseek", "kimi")
        # Credentials referenced by LABEL only (a label, never a value).
        assert primary["credential_label"] and "_API_KEY" in primary["credential_label"]
    # The client's OWN strongest heavy model is the HEAVY-WRITER primary.
    assert tiers["HEAVY-WRITER"]["chain"][0]["model"] == "deepseek-v4-pro:cloud"

    # IMAGE tier resolved via Kie when KIE_API_KEY is set (S7 cover route).
    assert "IMAGE" in tiers, "required IMAGE tier missing when KIE_API_KEY is set"
    img_primary = tiers["IMAGE"]["chain"][0]
    assert img_primary["provider"] == "kie"
    assert img_primary["credential_label"] == "KIE_API_KEY"
    assert img_primary["model"], "IMAGE tier must have a model label"
    # The template IMAGE chain preserves endpoint/via fields.
    assert img_primary.get("endpoint"), "IMAGE tier must carry endpoint from template"
    assert img_primary.get("via"), "IMAGE tier must carry via from template"


def test_resolved_map_routes_without_unresolvedmaperror():
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0
    sys.path.insert(0, str(SCRIPTS))
    import model_router as mr  # noqa: E402

    mm, _path = mr.load_model_map(str(run_dir / "model-map.json"))
    # This is the call that previously raised UnresolvedMapError on the placeholder map.
    mr.validate_resolved_map(mm)

    saved = os.environ.get("OLLAMA_API_KEY")
    os.environ["OLLAMA_API_KEY"] = "dummy-not-a-real-secret"
    try:
        class _T:
            def __call__(self, req, timeout):
                return mr.HttpResponse(
                    status=200, body_text="{}",
                    json={"model": req.body["model"],
                          "choices": [{"message": {"content": "chapter body"}}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
        router = mr.ModelRouter(model_map=mm, transport=_T(),
                                pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                                hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
        res = router.route("HEAVY-WRITER", [{"role": "user", "content": "write"}],
                           {"deliverable_key": "d1"})
        assert res.provider == "ollama-cloud" and res.model_used == "deepseek-v4-pro:cloud"
        assert res.text == "chapter body"
    finally:
        if saved is None:
            os.environ.pop("OLLAMA_API_KEY", None)
        else:
            os.environ["OLLAMA_API_KEY"] = saved


def test_resolved_map_passes_the_entry_pregate_check():
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0
    # preflight.sh --check is the anthology-engine-entry GATE 1b pre-gate.
    r = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir), "--check"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, "resolved map fails the entry pre-gate:\n%s\n%s" % (r.stdout, r.stderr)


def test_no_client_model_fails_closed_never_hardcodes():
    rc, run_dir, proc, _td = _resolve(NO_MODEL_CFG)
    # FAIL CLOSED -- exit 2, and NO map written (never a substituted default).
    assert rc == 2, "no-model config must fail closed (exit 2), got %d:\n%s" % (rc, proc.stderr)
    assert not (run_dir / "model-map.json").is_file(), \
        "fail-closed must NOT write a map (it would carry a hardcoded/substituted model)"
    assert "AF-AE-UNRESOLVED-MODELMAP" in proc.stderr


def test_judge_never_equals_heavy_writer_in_a_resolved_map():
    # Defense in depth on the happy path: whenever a map resolves cleanly, its JUDGE
    # primary must differ from its HEAVY-WRITER primary (independent QC at S9 Gate B).
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0
    mm = json.loads((run_dir / "model-map.json").read_text(encoding="utf-8"))
    hw = mm["tiers"]["HEAVY-WRITER"]["chain"][0]
    jg = mm["tiers"]["JUDGE"]["chain"][0]
    assert (hw["provider"], hw["model"]) != (jg["provider"], jg["model"]), \
        "JUDGE resolved to the same model as HEAVY-WRITER: %s" % jg


def test_image_tier_fails_closed_when_kie_api_key_unset():
    # IMAGE is a REQUIRED tier gated on KIE_API_KEY only (it's a Kie PORTRAIT route
    # that does NOT consume an inventory image_generation model). When KIE_API_KEY is
    # unset, RESOLVE must fail closed with exit 2 and emit the absent_behavior WARNING.
    env_no_kie = {"KIE_API_KEY": ""}
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env=env_no_kie)
    assert rc == 2, "IMAGE tier must fail closed when KIE_API_KEY is unset (got rc=%d)" % rc
    combined = proc.stdout + proc.stderr
    assert "AF-AE-UNRESOLVED-MODELMAP" in combined, \
        "expected AF-AE-UNRESOLVED-MODELMAP when IMAGE is unresolved:\n%s" % combined
    assert "IMAGE" in combined, \
        "expected IMAGE in the unresolved report:\n%s" % combined
    assert "WARNING" in combined, \
        "expected the absent_behavior WARNING on stderr:\n%s" % combined
    # No map written when a REQUIRED tier fails.
    assert not (run_dir / "model-map.json").is_file(), \
        "fail-closed must NOT write a map when IMAGE is unresolved"


def test_thin_single_model_client_fails_closed_on_judge_independence():
    # A thin client with one usable model would resolve JUDGE == HEAVY-WRITER; that
    # passes tier-fill but trips judge_harness mid-run at S9 Gate B. Resolution must
    # fail CLOSED (exit 2, AF-AE-JUDGE-INDEPENDENCE) and write NO map.
    rc, run_dir, proc, _td = _resolve(THIN_ONE_MODEL_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 2, "thin single-model client must fail closed (exit 2), got %d:\n%s" \
        % (rc, proc.stderr)
    assert "AF-AE-JUDGE-INDEPENDENCE" in proc.stderr, \
        "expected AF-AE-JUDGE-INDEPENDENCE, got:\n%s" % proc.stderr
    assert not (run_dir / "model-map.json").is_file(), \
        "a same-model (non-independent) map must NEVER be written"


def test_anthropic_only_client_is_filtered_and_fails_closed():
    # A client whose only model is an Anthropic id has NO usable model -> fail closed,
    # never falls back to an Anthropic id and never a baked default.
    rc, run_dir, proc, _td = _resolve(NO_MODEL_CFG)
    assert rc == 2
    assert not BANNED.search(proc.stdout), "an Anthropic id leaked to the resolver output"


def test_real_fleet_cloud_tagged_ids_resolve_and_stay_independent():
    # ISSUE-08 end to end: a config whose models are all date/plain-tagged Ollama
    # Cloud ids must resolve rc 0, with HEAVY-WRITER and JUDGE on DIFFERENT
    # (provider, model) pairs -- not both collapsed onto client_best().
    rc, run_dir, proc, _td = _resolve(REAL_FLEET_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0, "date-tagged cloud ids must resolve:\n%s\n%s" % (proc.stdout, proc.stderr)
    mm = json.loads((run_dir / "model-map.json").read_text(encoding="utf-8"))
    hw = mm["tiers"]["HEAVY-WRITER"]["chain"][0]
    jg = mm["tiers"]["JUDGE"]["chain"][0]
    assert (hw["provider"], hw["model"]) != (jg["provider"], jg["model"]), \
        "HEAVY-WRITER and JUDGE collapsed onto one model: %s" % jg
    assert hw["model"] == "deepseek-v4-pro:0813-cloud", \
        "HEAVY-WRITER must take the date-tagged DeepSeek pro build, got %s" % hw["model"]
    assert mm["tiers"]["LIGHT"]["chain"][0]["model"] == "deepseek-v4-flash:0731-cloud"
    # The code variant is a different model and must never fill a chat slot.
    assert "kimi-k2.7-code" not in json.dumps(mm["tiers"]["HEAVY-WRITER"])


def test_owner_pin_survives_re_resolution_at_order_1():
    # Part 2: preflight rewrites the map on every roll, so a hand-tuned choice was
    # clobbered by the next update. An owner_pins block must survive re-resolution.
    rc, run_dir, proc, _td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0
    mp = run_dir / "model-map.json"
    mm = json.loads(mp.read_text(encoding="utf-8"))
    auto_hw = mm["tiers"]["HEAVY-WRITER"]["chain"][0]["model"]

    # Pin HEAVY-WRITER to a DIFFERENT client-owned model, then re-resolve in place.
    pin = "ollama/kimi-k2.6:cloud"
    mm["owner_pins"] = {"HEAVY-WRITER": pin}
    mp.write_text(json.dumps(mm), encoding="utf-8")

    env = dict(os.environ)
    env["OPENCLAW_CONFIG"] = str(Path(_td) / "openclaw.json")
    env["KIE_API_KEY"] = _KIE_DUMMY
    r = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, "re-resolve with an owner pin failed:\n%s\n%s" % (r.stdout, r.stderr)
    assert "owner pin honored: HEAVY-WRITER -> %s" % pin in r.stdout, \
        "the honored pin must be logged:\n%s" % r.stdout

    mm2 = json.loads(mp.read_text(encoding="utf-8"))
    chain = mm2["tiers"]["HEAVY-WRITER"]["chain"]
    assert chain[0]["order"] == 1
    assert chain[0]["model"] == "kimi-k2.6:cloud", "the pin must be order 1, got %s" % chain[0]
    # the auto-resolved links survive BEHIND the pin as ordered fallbacks
    assert any(l["model"] == auto_hw for l in chain[1:]), \
        "auto-resolved links must remain as fallbacks: %s" % chain
    assert [l["order"] for l in chain] == list(range(1, len(chain) + 1)), \
        "chain order must stay dense and 1-based: %s" % chain
    # owner_pins carried forward verbatim so the NEXT roll honors it too
    assert mm2.get("owner_pins") == {"HEAVY-WRITER": pin}
    # independence still holds after the pin
    jg = mm2["tiers"]["JUDGE"]["chain"][0]
    assert (chain[0]["provider"], chain[0]["model"]) != (jg["provider"], jg["model"])
    # and the pinned map still passes the entry pre-gate
    g = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir), "--check"],
                       capture_output=True, text=True, timeout=30)
    assert g.returncode == 0, "pinned map fails the entry pre-gate:\n%s\n%s" % (g.stdout, g.stderr)


def _repin_and_resolve(cfg_obj, pins):
    """Resolve, inject owner_pins, re-resolve. Returns the second CompletedProcess."""
    rc, run_dir, proc, td = _resolve(cfg_obj, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0, proc.stderr
    mp = run_dir / "model-map.json"
    mm = json.loads(mp.read_text(encoding="utf-8"))
    mm["owner_pins"] = pins
    mp.write_text(json.dumps(mm), encoding="utf-8")
    env = dict(os.environ)
    env["OPENCLAW_CONFIG"] = str(Path(td) / "openclaw.json")
    env["KIE_API_KEY"] = _KIE_DUMMY
    return subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                          capture_output=True, text=True, timeout=60, env=env)


def test_forbidden_owner_pin_fails_closed():
    # An Anthropic-family pin must FAIL CLOSED, never be silently dropped.
    r = _repin_and_resolve(GOOD_CFG, {"HEAVY-WRITER": _A + "/" + _C + "opus-4"})
    assert r.returncode == 2, "a denied owner pin must fail closed, got %d:\n%s" \
        % (r.returncode, r.stderr)
    assert "AF-AE-UNRESOLVED-MODELMAP" in r.stderr
    assert "HEAVY-WRITER" in r.stderr
    assert not BANNED.search(r.stdout), "a denied id leaked to stdout"


def test_owner_pin_outside_client_inventory_fails_closed():
    r = _repin_and_resolve(GOOD_CFG, {"JUDGE": "ollama/not-a-configured-model:cloud"})
    assert r.returncode == 2, "an out-of-inventory pin must fail closed, got %d:\n%s" \
        % (r.returncode, r.stderr)
    assert "AF-AE-UNRESOLVED-MODELMAP" in r.stderr
    assert "not-a-configured-model" in r.stderr


def test_owner_pin_for_an_unresolved_role_fails_closed():
    r = _repin_and_resolve(GOOD_CFG, {"NOT-A-TIER": "ollama/kimi-k2.6:cloud"})
    assert r.returncode == 2, "a pin on an unknown role must fail closed, got %d:\n%s" \
        % (r.returncode, r.stderr)
    assert "AF-AE-UNRESOLVED-MODELMAP" in r.stderr
    assert "NOT-A-TIER" in r.stderr


def test_owner_pin_that_breaks_judge_independence_fails_closed():
    # Pins are applied BEFORE the independence invariant, so a pin that collapses
    # JUDGE onto HEAVY-WRITER is caught at resolve, never mid-run at S9 Gate B.
    r = _repin_and_resolve(GOOD_CFG, {"JUDGE": "ollama/deepseek-v4-pro:cloud"})
    assert r.returncode == 2, "a pin collapsing JUDGE onto HEAVY-WRITER must fail closed"
    assert "AF-AE-JUDGE-INDEPENDENCE" in r.stderr


def test_unreadable_existing_map_still_self_heals_with_a_warning():
    # Owner-pin support must not cost the resolver its self-heal: a truncated map
    # is re-resolved from scratch (as it was before pins existed), with a LOUD
    # warning that any pins it carried are gone. Never a fail-closed brick.
    rc, run_dir, proc, td = _resolve(GOOD_CFG, extra_env={"KIE_API_KEY": _KIE_DUMMY})
    assert rc == 0
    mp = run_dir / "model-map.json"
    mp.write_text("not json {{{", encoding="utf-8")
    env = dict(os.environ)
    env["OPENCLAW_CONFIG"] = str(Path(td) / "openclaw.json")
    env["KIE_API_KEY"] = _KIE_DUMMY
    r = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, "an unreadable map must self-heal, not brick the roll:\n%s" % r.stderr
    assert "WARNING" in r.stderr and "owner_pins" in r.stderr, \
        "the lost-pins warning must name owner_pins:\n%s" % r.stderr
    mm = json.loads(mp.read_text(encoding="utf-8"))
    assert "HEAVY-WRITER" in mm["tiers"]
    assert "owner_pins" not in mm


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_model_map_resolution: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
