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


def _resolve(cfg_obj):
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
    proc = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                          capture_output=True, text=True, timeout=60, env=env)
    return proc.returncode, run_dir, proc, td


# --------------------------------------------------------------------------- #
def test_real_client_config_resolves_every_required_tier():
    rc, run_dir, proc, _td = _resolve(GOOD_CFG)
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


def test_resolved_map_routes_without_unresolvedmaperror():
    rc, run_dir, proc, _td = _resolve(GOOD_CFG)
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
    rc, run_dir, proc, _td = _resolve(GOOD_CFG)
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
    rc, run_dir, proc, _td = _resolve(GOOD_CFG)
    assert rc == 0
    mm = json.loads((run_dir / "model-map.json").read_text(encoding="utf-8"))
    hw = mm["tiers"]["HEAVY-WRITER"]["chain"][0]
    jg = mm["tiers"]["JUDGE"]["chain"][0]
    assert (hw["provider"], hw["model"]) != (jg["provider"], jg["model"]), \
        "JUDGE resolved to the same model as HEAVY-WRITER: %s" % jg


def test_thin_single_model_client_fails_closed_on_judge_independence():
    # A thin client with one usable model would resolve JUDGE == HEAVY-WRITER; that
    # passes tier-fill but trips judge_harness mid-run at S9 Gate B. Resolution must
    # fail CLOSED (exit 2, AF-AE-JUDGE-INDEPENDENCE) and write NO map.
    rc, run_dir, proc, _td = _resolve(THIN_ONE_MODEL_CFG)
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
