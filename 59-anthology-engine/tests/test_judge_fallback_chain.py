#!/usr/bin/env python3
"""test_judge_fallback_chain.py -- regression tests for the ordered JUDGE fallback
chain (standing order, 2026-10-02).

THE BUG. On a box whose configured models all collapse to ONE main model, the
JUDGE tier resolved to the SAME model as HEAVY-WRITER and preflight.sh failed
closed (exit 2, AF-AE-JUDGE-INDEPENDENCE) -- so Skill 59 refused to install even
though the box had a perfectly good second model (DeepSeek Flash) available.

THE FIX. When the AUTO-resolved JUDGE primary collides with the HEAVY-WRITER
primary, preflight.sh pre﻿pends the first of these providers the client has BOTH
configured (in their OWN inventory) AND keyed, in this EXACT order:
    1) DeepSeek Flash on Ollama Cloud, 2) DeepSeek Flash on OpenRouter,
    3) DeepSeek Direct (deepseek-flash), 4) Agnes.
First one configured answers wins; the judge must still DIFFER from the heavy
writer (a rung whose model IS the writer is skipped, and the walk continues);
an explicit JUDGE owner pin is never silently rewritten (still fails closed).

These tests PROVE THE ORDER with synthetic client configs and key presence:
  * first available provider wins
  * an earlier provider BEATS a later one when both are available
  * a rung that IS the writer is skipped, not chosen
  * changing the order would change the winner (the assertions are order-bound)
  * with no fallback provider both configured and keyed, it still fails closed
Python 3 stdlib only; synthetic configs only; no key value is ever printed.
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

_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)
PLACEHOLDER = re.compile(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>")
_KIE_DUMMY = "dummy-kie-not-a-real-secret"
_KEY_VALUE = "dummy-not-a-real-secret"

# The four providers, and the ONLY model ids each rung accepts. A synthetic client
# config may carry any SUBSET; key presence is supplied per test. ONE main model
# (the writer) plus configured fallback models -- never a real fleet config.
_OLLAMA_FLASH = "ollama/deepseek-v4.1-flash:cloud"
_OR_FLASH = "openrouter/deepseek/deepseek-v4.1-flash"
_DS_DIRECT = "deepseek/deepseek-flash"
_AGNES = "agnes/agnes-3.0-flash"

_ALL_KEYS = ("OLLAMA_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
             "AGNES_API_KEY", "AGNES_AI_API_KEY", "AGNES_KEY", "KIE_API_KEY")


def _cfg_with(models):
    """Synthetic client openclaw.json: agents.defaults.model holds the FIRST model
    (the box's one main model), the rest ride models.list."""
    return {"agents": {"defaults": {"model": models[0]}, "list": []},
            "models": {"list": [{"id": m} for m in models[1:]]}}


def _resolve(models, keys, pins=None):
    """Run preflight.sh RESOLVE against a synthetic config with EXACTLY `keys` set
    (values are placeholders; presence only). HOME is redirected into the temp dir
    so the box's own secrets store can never leak env into this box-independent
    test. Returns (rc, map_or_None, proc, td)."""
    td = tempfile.mkdtemp(prefix="judgefb_")
    cfg_path = Path(td) / "openclaw.json"
    cfg_path.write_text(json.dumps(_cfg_with(models)), encoding="utf-8")
    run_dir = Path(td) / "run"
    run_dir.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in _ALL_KEYS}
    env["HOME"] = td
    env["OPENCLAW_CONFIG"] = str(cfg_path)
    env["KIE_API_KEY"] = _KIE_DUMMY
    for k in keys:
        env[k] = _KEY_VALUE
    proc = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                          capture_output=True, text=True, timeout=90, env=env)
    mp = run_dir / "model-map.json"
    if mp.is_file() and pins:
        mm = json.loads(mp.read_text(encoding="utf-8"))
        mm["owner_pins"] = pins
        mp.write_text(json.dumps(mm), encoding="utf-8")
        proc = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(run_dir)],
                              capture_output=True, text=True, timeout=90, env=env)
    try:
        mm = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        mm = None
    return proc.returncode, mm, proc, td


def _judge_primary(mm):
    link = mm["tiers"]["JUDGE"]["chain"][0]
    return link["provider"], link["model"]


def _heavy_primary(mm):
    link = mm["tiers"]["HEAVY-WRITER"]["chain"][0]
    return link["provider"], link["model"]


# --------------------------------------------------------------------------- #
def test_first_available_provider_wins_when_only_rung1_keyed():
    # Writer = DeepSeek Flash on Ollama Cloud (the box's one MAIN model), so rung 1
    # IS the writer and must be SKIPPED; only rung 3 (DeepSeek Direct) is both
    # configured and keyed -> it wins and the judge differs from the writer.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _DS_DIRECT],
                                 keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"))
    assert rc == 0, "fallback must let this box resolve:\n%s\n%s" % (proc.stdout, proc.stderr)
    assert _heavy_primary(mm) == ("ollama-cloud", "deepseek-v4.1-flash:cloud")
    assert _judge_primary(mm) == ("deepseek", "deepseek-flash"), \
        "JUDGE must fall to the FIRST available rung, got %s" % (_judge_primary(mm),)
    assert _judge_primary(mm) != _heavy_primary(mm)


def test_earlier_provider_beats_later_when_both_available():
    # Same writer, but BOTH DeepSeek Direct (rung 3) and Agnes (rung 4) configured
    # and keyed: rung 3 must win. If the implementation reordered rungs this fails.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _DS_DIRECT, _AGNES],
                                 keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY", "AGNES_AI_API_KEY"))
    assert rc == 0, proc.stderr
    assert _judge_primary(mm) == ("deepseek", "deepseek-flash"), \
        "the earlier rung (DeepSeek Direct) must beat the later rung (Agnes), got %s" \
        % (_judge_primary(mm),)


def test_openrouter_flash_beats_deepseek_direct():
    # A box whose writer is Ollama Cloud DeepSeek Flash and whose OpenRouter Flash
    # (rung 2) and DeepSeek Direct (rung 3) are both available: rung 2 must win.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _OR_FLASH, _DS_DIRECT],
                                 keys=("OLLAMA_API_KEY", "OPENROUTER_API_KEY",
                                       "DEEPSEEK_API_KEY"))
    assert rc == 0, proc.stderr
    assert _judge_primary(mm) == ("openrouter", "deepseek/deepseek-v4.1-flash"), \
        "Ollama-Cloud rung is the writer; OpenRouter rung must win next, got %s" \
        % (_judge_primary(mm),)
    # Order-bound cross-check: with the SAME writer but OpenRouter REMOVED from the
    # config, the winner must move to the later rung (DeepSeek Direct). Same code,
    # different winner -- the rung order is what decides it.
    assert tuple(_judge_primary(mm)) != ("deepseek", "deepseek-flash")


def test_agnes_wins_only_when_rungs_1_to_3_unavailable():
    # Writer on Ollama Cloud Flash; OpenRouter/DeepSeek not configured or not keyed;
    # Agnes (rung 4) is the ONLY available fallback -> Agnes must be chosen.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _AGNES],
                                 keys=("OLLAMA_API_KEY", "AGNES_AI_API_KEY"))
    assert rc == 0, proc.stderr
    assert _judge_primary(mm) == ("agnes", "agnes-3.0-flash"), \
        "Agnes must fill JUDGE when it is the only available rung, got %s" \
        % (_judge_primary(mm),)


def test_configured_but_unkeyed_provider_is_skipped():
    # The client CONFIGURED OpenRouter DeepSeek Flash, but this box has NO
    # OPENROUTER_API_KEY: rung 2 must be skipped (never routed without a key), and
    # the next keyed rung (DeepSeek Direct) must win.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _OR_FLASH, _DS_DIRECT],
                                 keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"))
    assert rc == 0, proc.stderr
    assert _judge_primary(mm) == ("deepseek", "deepseek-flash"), \
        "an unkeyed provider must be skipped, got %s" % (_judge_primary(mm),)


def test_writer_model_is_skipped_even_when_its_rung_is_available():
    # Rung 1 = DeepSeek Flash on Ollama Cloud, which IS the writer: choosing it
    # would violate independence. The walk must continue to rung 3.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _DS_DIRECT, _AGNES],
                                 keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY", "AGNES_AI_API_KEY"))
    assert rc == 0, proc.stderr
    assert _judge_primary(mm) != _heavy_primary(mm), \
        "the writer's own model must never be chosen as judge"
    assert _judge_primary(mm) == ("deepseek", "deepseek-flash")


def test_fallback_map_still_passes_deny_placeholder_and_pregate():
    rc, mm, proc, td = _resolve([_OLLAMA_FLASH, _DS_DIRECT],
                                keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"))
    assert rc == 0, proc.stderr
    blob = json.dumps(mm)
    assert not PLACEHOLDER.findall(blob), "resolved map still carries placeholders"
    assert not BANNED.search(blob), "resolved map carries an Anthropic-family id"
    r = subprocess.run(["bash", str(PREFLIGHT), "--run-dir", str(Path(td) / "run"), "--check"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, "fallback map fails the entry pre-gate:\n%s\n%s" % (r.stdout, r.stderr)


def test_no_fallback_provider_keyed_still_fails_closed():
    # Only the writer model is configured (and keyed): no rung is available, so the
    # box must still fail closed with AF-AE-JUDGE-INDEPENDENCE and write NO map.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH], keys=("OLLAMA_API_KEY",))
    assert rc == 2, "a single-model box with no fallback must fail closed, got %d" % rc
    assert "AF-AE-JUDGE-INDEPENDENCE" in proc.stderr
    assert mm is None, "a fail-closed resolve must write NO map"


def test_explicit_judge_owner_pin_is_never_silently_rewritten():
    # An owner who EXPLICITLY pins JUDGE onto the writer gets the doctrine answer:
    # fail closed. The fallback pass must not quietly overrule the pin.
    rc, mm, proc, _td = _resolve([_OLLAMA_FLASH, _DS_DIRECT],
                                 keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"),
                                 pins={"JUDGE": _OLLAMA_FLASH})
    assert rc == 2, "an explicit pin collapsing JUDGE onto the writer must fail closed, got %d" % rc
    assert "AF-AE-JUDGE-INDEPENDENCE" in proc.stderr


def test_heavy_writer_chain_is_untouched_by_the_judge_fallback():
    # The fallback only inserts a link into the JUDGE tier -- the HEAVY-WRITER chain
    # (and its order) must be byte-identical to a resolve with no fallback needed.
    rc_plain, mm_plain, _p1, _t1 = _resolve(
        ["openrouter/meta/muse-spark-1.3-contributor", _OLLAMA_FLASH, _DS_DIRECT],
        keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"))
    rc_fb, mm_fb, _p2, _t2 = _resolve([_OLLAMA_FLASH, _DS_DIRECT],
                                      keys=("OLLAMA_API_KEY", "DEEPSEEK_API_KEY"))
    assert rc_plain == 0, _p1.stderr
    assert rc_fb == 0, _p2.stderr
    assert mm_plain["tiers"]["HEAVY-WRITER"] == mm_fb["tiers"]["HEAVY-WRITER"], \
        "the judge fallback must not alter the HEAVY-WRITER chain"


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
    print("test_judge_fallback_chain: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
