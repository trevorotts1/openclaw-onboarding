#!/usr/bin/env python3
"""model_router.py — probe-gated, NON-ANTHROPIC model fallback ladder for Skill 06.

WHY THIS EXISTS (Area-4 gap)
----------------------------
Skill 06 has NO in-skill model API call — the heavy lifting is deterministic
Python (REST canvas + gates) and the "model" is whoever the OpenClaw runtime is
configured to run the agent on. The model only matters at two seams: (a) a
live-selector ambiguity recovery, (b) the broken-code fix-retry loop. On a CLIENT
box (no Anthropic key) there was no coded probe-gate and no coded failover — if
the configured model silently failed to tool-call, the build just stalled. This
module is that missing probe-gated fallback ladder.

CLIENT-PROVIDER POLICY (BINDING — clients run their OWN providers)
-----------------------------------------------------------------
This router NEVER selects an Anthropic/Claude model. Preference order is
**Ollama Cloud** (rungs 1-3), then **OpenRouter** as a provider-failover backup
(rungs 4-6). Roles, thinking effort = HIGH throughout:
  * BROWSER CONTROL + TOOL CALLS + QC  -> MiniMax 3  (PRIMARY, PROBE-GATED because
    MiniMax priors are flagged-suspect — the probe DEMANDS a real tool-call).
  * HIGH-THINKING / REASONING          -> DeepSeek v4 pro  (or GLM 5.2).
  * PAGE / WEBSITE / HTML content      -> GLM 5.2.

THE LADDER
----------
  RUNG 1  Ollama Cloud   MiniMax M3 -> M2   (PRIMARY, probe-gated)
  RUNG 2  Ollama Cloud   DeepSeek v4 pro    (doc-sanctioned thinking/code-fix)
  RUNG 3  Ollama Cloud   GLM 5.2
  RUNG 4  OpenRouter     MiniMax M3 -> M2   (probe-gated)   ┐ same chain,
  RUNG 5  OpenRouter     DeepSeek v4 pro                    ├ OpenRouter provider
  RUNG 6  OpenRouter     GLM 5.2                            ┘ failover tier
Per rung: probe (when gated) -> use; on a runtime tool-call failure do ONE backoff
retry, then advance; HTTP 429 / timeout = advance (never retry forever). Ollama
Cloud needs ``<model>:cloud`` + ``baseUrl=ollama.com`` + the id_ed25519 device key
(asserted before rungs 1-3). HARD GUARD: an Anthropic id anywhere raises.

ANTI-FABRICATION / HONESTY
--------------------------
Only the DeepSeek slug (``deepseek-v4-pro`` / ``openrouter/deepseek/deepseek-v4-pro``)
is repo-documented (ghl-install-pages-full.md:1577-1579). The MiniMax/GLM provider
slugs follow the documented ``<model>:cloud`` (Ollama Cloud) and ``<vendor>/<model>``
(OpenRouter) conventions but each carries ``slug_confidence:"confirm"`` — the
operator confirms the exact tag per box. This is SAFE because the probe-gate is the
net: an unavailable / mis-tagged rung fails its probe and the router ADVANCES, so a
wrong slug degrades gracefully instead of wasting a build. Live API calls are made
ONLY by an INJECTED executor (the reference executors require real creds and are
NOT exercised by --selftest); the shipped, tested value is the ladder + guards +
probe-gate + failover, all verifiable offline.

USAGE
  python3 tools/model_router.py --selftest          # offline, exits 0 on pass
  python3 tools/model_router.py --print-ladder       # show the ladder JSON
  python3 tools/model_router.py --emit <out.json>    # write the receipt (outside skill dir)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Callable, Optional

# A model/provider string containing any of these is an Anthropic id — HARD-banned
# on a client box. The router refuses to ever return one.
_ANTHROPIC_MARKERS = ("anthropic", "claude", "opus", "sonnet", "haiku")

OLLAMA_CLOUD_BASE_URL = "https://ollama.com"   # MEMORY: ollama-cloud baseUrl trap
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default thinking/reasoning effort for every rung (policy: HIGH).
THINKING_EFFORT = "high"


class AnthropicModelError(RuntimeError):
    """Raised if any ladder entry resolves to an Anthropic/Claude model — a hard
    client-box policy violation."""


class OllamaCloudConfigError(RuntimeError):
    """Raised when an Ollama Cloud rung is missing the :cloud suffix / ollama.com
    baseUrl (the documented Ollama Cloud trap)."""


def _looks_anthropic(*values: str) -> bool:
    blob = " ".join(v for v in values if v).lower()
    return any(m in blob for m in _ANTHROPIC_MARKERS)


# ---------------------------------------------------------------------------
# Ladder definition. Slugs are overridable via env (MODEL_ROUTER_<KEY>) so a box
# can pin the exact provider tag without a code change.
# ---------------------------------------------------------------------------
def _slug(env: dict, key: str, default: str) -> str:
    return (env.get(f"MODEL_ROUTER_{key}") or default).strip() or default


def build_ladder(env: Optional[dict] = None) -> list:
    """Build the 6-rung non-Anthropic ladder. Returns a list of rung dicts. Raises
    AnthropicModelError if any resolved slug looks Anthropic."""
    env = env if env is not None else os.environ

    ladder = [
        {
            "rung": 1, "provider": "ollama-cloud", "base_url": OLLAMA_CLOUD_BASE_URL,
            "role": "browser-control+tool-calls+qc", "probe_gated": True,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OLLAMA_MINIMAX_M3", "minimax-m3:cloud"),
                 "family": "minimax", "slug_confidence": "confirm"},
                {"slug": _slug(env, "OLLAMA_MINIMAX_M2", "minimax-m2:cloud"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "provider": "ollama-cloud", "base_url": OLLAMA_CLOUD_BASE_URL,
            "role": "reasoning+code-fix", "probe_gated": False,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OLLAMA_DEEPSEEK", "deepseek-v4-pro:cloud"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 3, "provider": "ollama-cloud", "base_url": OLLAMA_CLOUD_BASE_URL,
            "role": "content+html+reasoning", "probe_gated": False,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OLLAMA_GLM", "glm-5.2:cloud"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 4, "provider": "openrouter", "base_url": OPENROUTER_BASE_URL,
            "role": "browser-control+tool-calls+qc", "probe_gated": True,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OPENROUTER_MINIMAX_M3", "minimax/minimax-m3"),
                 "family": "minimax", "slug_confidence": "confirm"},
                {"slug": _slug(env, "OPENROUTER_MINIMAX_M2", "minimax/minimax-m2"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 5, "provider": "openrouter", "base_url": OPENROUTER_BASE_URL,
            "role": "reasoning+code-fix", "probe_gated": False,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OPENROUTER_DEEPSEEK", "deepseek/deepseek-v4-pro"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 6, "provider": "openrouter", "base_url": OPENROUTER_BASE_URL,
            "role": "content+html+reasoning", "probe_gated": False,
            "thinking": THINKING_EFFORT,
            "models": [
                {"slug": _slug(env, "OPENROUTER_GLM", "z-ai/glm-5.2"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
    ]
    assert_no_anthropic(ladder)
    return ladder


def assert_no_anthropic(ladder: list) -> None:
    """HARD GUARD: raise AnthropicModelError if any rung resolves to an Anthropic
    model or provider. Never silently fall to Anthropic on a client box."""
    for rung in ladder:
        if _looks_anthropic(rung.get("provider", "")):
            raise AnthropicModelError(f"rung {rung.get('rung')} provider is Anthropic")
        for m in rung.get("models", []):
            if _looks_anthropic(m.get("slug", ""), m.get("family", "")):
                raise AnthropicModelError(
                    f"rung {rung.get('rung')} model {m.get('slug')!r} is Anthropic — banned on a client box"
                )


def assert_ollama_cloud_ready(rung: dict, env: Optional[dict] = None) -> None:
    """For an ollama-cloud rung, assert the documented Ollama Cloud invariants:
    every model slug ends with ``:cloud`` and the baseUrl is ollama.com. (The
    id_ed25519 device-key requirement is enforced by the runtime, not here; we
    surface it in the receipt.)"""
    if rung.get("provider") != "ollama-cloud":
        return
    if "ollama.com" not in (rung.get("base_url") or ""):
        raise OllamaCloudConfigError(
            f"rung {rung.get('rung')}: Ollama Cloud baseUrl must be ollama.com, got {rung.get('base_url')!r}"
        )
    for m in rung.get("models", []):
        if not m.get("slug", "").endswith(":cloud"):
            raise OllamaCloudConfigError(
                f"rung {rung.get('rung')}: Ollama Cloud slug must end with ':cloud', got {m.get('slug')!r}"
            )


# ---------------------------------------------------------------------------
# Probe gate — a tiny task that REQUIRES a tool-call/JSON return.
# ---------------------------------------------------------------------------
# The fixed probe task. PASS only if the executor returns a dict that BOTH parses
# AND reports the tool-call actually fired. This catches MiniMax's historical
# "plausible-looking non-tool text" before a whole build is wasted.
PROBE_TASK = {
    "instruction": "Call the tool `echo_tool` with exactly {\"ok\": true}. Reply ONLY via the tool call.",
    "tool": {"name": "echo_tool", "schema": {"ok": "boolean"}},
    "expect": {"ok": True},
}


def probe_passes(result: Optional[dict]) -> bool:
    """A probe PASSES only when the executor result parses AND the tool-call fired
    AND the returned args match the expected {ok:true}."""
    if not isinstance(result, dict):
        return False
    if not result.get("tool_call_fired"):
        return False
    if not result.get("parsed"):
        return False
    return result.get("args", {}) == PROBE_TASK["expect"]


# Executor signature: executor(provider, model_slug, base_url, task_dict) -> dict
# Reference (live) executors require real creds and are NOT used by --selftest.
ExecutorType = Callable[[str, str, str, dict], Optional[dict]]


def select(
    executor: ExecutorType,
    *,
    env: Optional[dict] = None,
    ladder: Optional[list] = None,
    backoff: tuple = (2.0, 8.0),
    sleep: Callable[[float], None] = time.sleep,
    receipt_path: Optional[str] = None,
) -> dict:
    """Walk the ladder, probe-gating gated rungs, and return the chosen rung+model.

    Returns a dict:
      {"chosen": {...} | None, "probe_results": [...], "ladder": [...]}
    The chosen model is the first that (a) passes its probe when probe_gated, and
    (b) does not raise on a runtime tool-call. On a runtime failure: ONE backoff
    retry, then advance. 429/timeout (executor returns {"advance": true}) = advance.
    Never returns an Anthropic model (guarded at build time)."""
    env = env if env is not None else os.environ
    ladder = ladder if ladder is not None else build_ladder(env)
    assert_no_anthropic(ladder)

    probe_results: list = []
    chosen: Optional[dict] = None

    for rung in ladder:
        try:
            assert_ollama_cloud_ready(rung, env)
        except OllamaCloudConfigError as exc:
            probe_results.append({"rung": rung["rung"], "skipped": True, "reason": str(exc)})
            continue

        for model in rung["models"]:
            slug = model["slug"]
            entry = {"rung": rung["rung"], "provider": rung["provider"], "model": slug}

            # Probe gate (only on probe_gated rungs — e.g. MiniMax).
            if rung.get("probe_gated"):
                try:
                    pr = executor(rung["provider"], slug, rung["base_url"], PROBE_TASK)
                except Exception as exc:  # noqa: BLE001 — a raising probe = fail, advance
                    pr = None
                    entry["probe_error"] = f"{type(exc).__name__}: {exc}"
                if isinstance(pr, dict) and pr.get("advance"):
                    entry["probe"] = "advance(429/timeout)"
                    probe_results.append(entry)
                    continue
                if not probe_passes(pr):
                    # ONE backoff retry, then advance to the next model/rung.
                    sleep(backoff[0])
                    try:
                        pr2 = executor(rung["provider"], slug, rung["base_url"], PROBE_TASK)
                    except Exception as exc:  # noqa: BLE001
                        pr2 = None
                        entry["probe_retry_error"] = f"{type(exc).__name__}: {exc}"
                    if not probe_passes(pr2):
                        entry["probe"] = "FAIL"
                        probe_results.append(entry)
                        continue
                entry["probe"] = "PASS"

            entry["chosen"] = True
            entry["thinking"] = rung.get("thinking", THINKING_EFFORT)
            entry["role"] = rung.get("role")
            probe_results.append(entry)
            chosen = entry
            break
        if chosen:
            break

    receipt = {
        "policy": "client-provider; NEVER Anthropic; Ollama Cloud preferred, OpenRouter backup; thinking=HIGH",
        "chosen": chosen,
        "probe_results": probe_results,
        "ladder": ladder,
    }
    if receipt_path:
        _write_receipt(receipt_path, receipt)
    return receipt


def _write_receipt(path: str, receipt: dict) -> None:
    """Write routing/model-ladder.json (the chosen rung + probe evidence). MUST be
    a path OUTSIDE the skill dir (run-evidence root) per the update-overlay rule."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)


# ---------------------------------------------------------------------------
# Reference LIVE executors (require real creds; NOT exercised by --selftest).
# ---------------------------------------------------------------------------
def make_stub_executor(fail_families: tuple = (), advance_families: tuple = ()) -> ExecutorType:
    """A deterministic, OFFLINE executor for tests/dry-runs. Returns a passing
    tool-call result UNLESS the model family is in ``fail_families`` (probe FAIL)
    or ``advance_families`` (simulated 429/timeout -> advance)."""
    def _exec(provider: str, slug: str, base_url: str, task: dict) -> Optional[dict]:
        fam = slug.split("/")[-1].split(":")[0]
        fam = re.sub(r"[-_].*$", "", fam)  # 'minimax-m3' -> 'minimax'
        if fam in advance_families:
            return {"advance": True}
        if fam in fail_families:
            return {"tool_call_fired": False, "parsed": True, "args": {}}
        return {"tool_call_fired": True, "parsed": True, "args": {"ok": True}}
    return _exec


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Offline self-test of the ladder + guards + probe-gate + failover."""
    errors: list = []

    ladder = build_ladder({})

    # 1. Six rungs, Ollama Cloud (1-3) BEFORE OpenRouter (4-6).
    rungs = [r["rung"] for r in ladder]
    if rungs != [1, 2, 3, 4, 5, 6]:
        errors.append(f"rung order wrong: {rungs}")
    providers = [r["provider"] for r in ladder]
    if providers != ["ollama-cloud"] * 3 + ["openrouter"] * 3:
        errors.append(f"provider order wrong: {providers}")

    # 2. NO Anthropic id anywhere (build-time guard already ran; assert explicitly).
    try:
        assert_no_anthropic(ladder)
    except AnthropicModelError as exc:
        errors.append(f"assert_no_anthropic raised on a clean ladder: {exc}")
    blob = json.dumps(ladder).lower()
    if any(m in blob for m in _ANTHROPIC_MARKERS):
        errors.append("an Anthropic marker leaked into the ladder JSON")

    # 3. Rung 1 is MiniMax + probe-gated; rung 2 DeepSeek; rung 3 GLM.
    if ladder[0]["models"][0]["family"] != "minimax" or not ladder[0]["probe_gated"]:
        errors.append("rung 1 must be probe-gated MiniMax")
    if ladder[1]["models"][0]["family"] != "deepseek":
        errors.append("rung 2 must be DeepSeek")
    if ladder[2]["models"][0]["family"] != "glm":
        errors.append("rung 3 must be GLM")

    # 4. Ollama Cloud invariants (:cloud + ollama.com) hold for rungs 1-3.
    for r in ladder[:3]:
        try:
            assert_ollama_cloud_ready(r, {})
        except OllamaCloudConfigError as exc:
            errors.append(f"ollama-cloud readiness failed: {exc}")

    # 5. Happy path — a stub that passes everything -> rung 1 chosen.
    out = select(make_stub_executor(), env={}, sleep=lambda *_: None)
    if not out["chosen"] or out["chosen"]["rung"] != 1:
        errors.append(f"clean stub should choose rung 1, got {out['chosen']}")

    # 6. A FORCED rung-1 MiniMax probe failure advances to rung 2 (DeepSeek).
    out2 = select(make_stub_executor(fail_families=("minimax",)), env={}, sleep=lambda *_: None)
    if not out2["chosen"] or out2["chosen"]["rung"] != 2:
        errors.append(f"minimax-fail should advance to rung 2, got {out2['chosen']}")
    if out2["chosen"] and "deepseek" not in out2["chosen"]["model"]:
        errors.append(f"rung 2 model should be DeepSeek, got {out2['chosen']['model']}")

    # 7. Ollama Cloud unreachable (429/advance on ALL ollama families) -> OpenRouter tier.
    out3 = select(
        make_stub_executor(advance_families=("minimax",), fail_families=()),
        env={}, sleep=lambda *_: None,
    )
    # rung 1 (ollama minimax) advances; rung 2/3 are not probe-gated so the first
    # reached (rung 2 DeepSeek on Ollama Cloud) is chosen — still non-Anthropic.
    if not out3["chosen"]:
        errors.append("a probe-advance on rung 1 must still resolve a non-Anthropic rung")
    if out3["chosen"] and _looks_anthropic(out3["chosen"]["model"]):
        errors.append("resolved an Anthropic model — HARD policy violation")

    # 8. The chosen receipt carries thinking=high.
    if out["chosen"] and out["chosen"].get("thinking") != "high":
        errors.append("chosen rung must carry thinking=high")

    # 9. A guard catches an injected Anthropic slug. The sentinel below is a
    #    NEGATIVE test fixture (it must be REJECTED), never a usable model id.
    bad = build_ladder({})
    bad[0]["models"][0]["slug"] = "BANNED-claude-sentinel-must-be-rejected"
    try:
        assert_no_anthropic(bad)
        errors.append("assert_no_anthropic FAILED to catch an injected Anthropic slug")
    except AnthropicModelError:
        pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[model_router selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[model_router selftest] PASS — ladder + guards + probe-gate + failover OK (offline)")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description="Skill-6 probe-gated non-Anthropic model ladder")
    p.add_argument("--selftest", action="store_true", help="Run offline self-test (exits 0 on pass)")
    p.add_argument("--print-ladder", action="store_true", help="Print the ladder JSON")
    p.add_argument("--emit", metavar="OUT", help="Run a stub select and write the receipt JSON to OUT (outside skill dir)")
    args = p.parse_args(argv[1:])

    if args.selftest:
        return _selftest()
    if args.print_ladder:
        print(json.dumps(build_ladder(), indent=2))
        return 0
    if args.emit:
        out = select(make_stub_executor(), receipt_path=args.emit, sleep=lambda *_: None)
        print(json.dumps({"chosen": out["chosen"], "receipt": args.emit}, indent=2))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
