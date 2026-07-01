#!/usr/bin/env python3
"""model_router.py — role-aware, probe-gated, NON-ANTHROPIC model fallback ladder for Skill 06.

ROLES (aliases in parentheses)
-------------------------------
  content          — copy writing: welcome slides, prompts; primary: Kimi 2.6
  html  (code)     — code-block fix-loop; primary: GLM 5.2
  reasoning (funnel) — structure and planning; primary: GLM 5.2 + DeepSeek v4 pro
  execution        — browser-click drive loop; primary: MiniMax M3 (probe-gated) + DeepSeek v4 pro
  qc               — vision QC on screenshots + DOM; primary: MiniMax M3 (probe-gated, vision)

FALLBACK ORDER — every role, no exceptions
------------------------------------------
  Tier 1  Ollama Cloud FIRST  (`:cloud` suffix, `baseUrl=ollama.com`, `id_ed25519` device key)
  Tier 2  OpenRouter equivalent  (only if Ollama Cloud fails)
  Tier 3  Universal backup: DeepSeek v4 pro appended to every ladder EXCEPT `qc`
           (DeepSeek has no confirmed vision; QC tasks must stay vision-capable)
  Last    OpenRouter Gemini 3.5 Flash on every ladder (only if live + credits)

  `thinking=high` on every rung.

BANNED
------
  MiniMax M2   — PURGED. Never appears in any rung, table, or recommendation.
                 Execution uses MiniMax M3 only, falling back to DeepSeek v4 pro.
  Anthropic    — Hard-blocked by both `assert_no_anthropic` (internal, build-time)
                 AND `assert_model_sovereignty` (shared-utils, per-slug at select-time).
  Kimi direct  — Kimi 2.6 is NEVER used "direct". Only via:
                   Ollama Cloud  ollama/kimi-k2.6:cloud
                   OpenRouter    openrouter/moonshotai/kimi-k2.6

ENV OVERRIDES (per-rung MODEL_ROUTER_<KEY>)
-------------------------------------------
  MODEL_ROUTER_OLLAMA_KIMI              default: kimi-k2.6:cloud
  MODEL_ROUTER_OPENROUTER_KIMI          default: moonshotai/kimi-k2.6
  MODEL_ROUTER_OLLAMA_GLM               default: glm-5.2:cloud
  MODEL_ROUTER_OPENROUTER_GLM           default: z-ai/glm-5.2
  MODEL_ROUTER_OLLAMA_DEEPSEEK          default: deepseek-v4-pro:cloud
  MODEL_ROUTER_OPENROUTER_DEEPSEEK      default: deepseek/deepseek-v4-pro
  MODEL_ROUTER_OLLAMA_MINIMAX_M3        default: minimax-m3:cloud
  MODEL_ROUTER_OPENROUTER_MINIMAX_M3    default: minimax/minimax-m3
  MODEL_ROUTER_OPENROUTER_GEMINI        default: google/gemini-3.5-flash

USAGE
  python3 tools/model_router.py --selftest                    # offline, exits 0 on pass
  python3 tools/model_router.py --print-ladder                # ladder for default role (execution)
  python3 tools/model_router.py --print-ladder --role content # ladder for content role
  python3 tools/model_router.py --emit <out.json> [--role qc] # write receipt JSON
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# shared-utils: assert_model_sovereignty — sovereign HARD-block on every slug.
# ---------------------------------------------------------------------------
_SHARED_UTILS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils")
)
if _SHARED_UTILS not in sys.path:
    sys.path.insert(0, _SHARED_UTILS)

try:
    from assert_model_sovereignty import assert_model_sovereignty as _ams
except Exception:  # noqa: BLE001 — graceful; internal _looks_anthropic guard still fires
    _ams = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# A model/provider string containing any of these is an Anthropic id — HARD-banned.
_ANTHROPIC_MARKERS = ("anthropic", "claude", "opus", "sonnet", "haiku")

OLLAMA_CLOUD_BASE_URL = "https://ollama.com"   # MEMORY: ollama-cloud baseUrl trap
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Every rung carries thinking=high (policy binding).
THINKING_EFFORT = "high"

# Ollama Cloud hard output-token ceiling (enforced on every ollama-cloud rung).
OLLAMA_CLOUD_MAX_TOKENS = 65536

# Canonical role names and their aliases.
_ROLE_ALIASES: dict[str, str] = {
    "code": "html",
    "funnel": "reasoning",
}
_VALID_ROLES = frozenset(["content", "html", "reasoning", "execution", "qc"])

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AnthropicModelError(RuntimeError):
    """Raised when any ladder entry resolves to an Anthropic/Claude model.
    Hard client-box policy violation — must never be caught and silenced."""


class OllamaCloudConfigError(RuntimeError):
    """Raised when an Ollama Cloud rung is missing the :cloud suffix or ollama.com
    baseUrl (the documented Ollama Cloud trap)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _looks_anthropic(*values: str) -> bool:
    blob = " ".join(v for v in values if v).lower()
    return any(m in blob for m in _ANTHROPIC_MARKERS)


def _slug(env: dict, key: str, default: str) -> str:
    """Return MODEL_ROUTER_<KEY> from env, or default."""
    return (env.get(f"MODEL_ROUTER_{key}") or default).strip() or default


def _sovereignty_check(slug: str) -> None:
    """Delegate to assert_model_sovereignty (shared-utils) for HARD Anthropic ban.
    Only raises AnthropicModelError on FORBIDDEN verdict. All other failure codes
    (NOT_IN_INVENTORY, MODALITY_MISMATCH) are ignored — those are dispatch-time
    concerns, not ladder-selection concerns. Never blocks a build on an import error."""
    if _ams is None:
        return  # shared-utils unavailable; internal _looks_anthropic guard already fired
    try:
        v = _ams(slug, inventory=None)
        if v.get("code") == "FORBIDDEN":
            raise AnthropicModelError(
                f"assert_model_sovereignty BLOCKED {slug!r}: {v.get('reason')}"
            )
    except AnthropicModelError:
        raise
    except Exception:  # noqa: BLE001
        pass  # never block a build on a sovereignty-check auxiliary error


# ---------------------------------------------------------------------------
# Role-specific ladder builders
# ---------------------------------------------------------------------------


def _build_content_ladder(env: dict) -> list:
    """content: Kimi 2.6 (Ollama Cloud → OpenRouter) → DeepSeek backup → Gemini last resort.
    Kimi is NEVER used direct — only via Ollama Cloud or OpenRouter."""
    return [
        {
            "rung": 1, "role": "content", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_KIMI", "kimi-k2.6:cloud"),
                 "family": "kimi", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "role": "content", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "models": [
                {"slug": _slug(env, "OPENROUTER_KIMI", "moonshotai/kimi-k2.6"),
                 "family": "kimi", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 3, "role": "content", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "universal-backup",
            "models": [
                {"slug": _slug(env, "OPENROUTER_DEEPSEEK", "deepseek/deepseek-v4-pro"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 4, "role": "content", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "last-resort",
            "models": [
                {"slug": _slug(env, "OPENROUTER_GEMINI", "google/gemini-3.5-flash"),
                 "family": "gemini", "slug_confidence": "confirm"},
            ],
        },
    ]


def _build_html_ladder(env: dict) -> list:
    """html / code: GLM 5.2 (Ollama Cloud → OpenRouter) → DeepSeek backup → Gemini last resort."""
    return [
        {
            "rung": 1, "role": "html", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_GLM", "glm-5.2:cloud"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "role": "html", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "models": [
                {"slug": _slug(env, "OPENROUTER_GLM", "z-ai/glm-5.2"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 3, "role": "html", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "universal-backup",
            "models": [
                {"slug": _slug(env, "OPENROUTER_DEEPSEEK", "deepseek/deepseek-v4-pro"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 4, "role": "html", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "last-resort",
            "models": [
                {"slug": _slug(env, "OPENROUTER_GEMINI", "google/gemini-3.5-flash"),
                 "family": "gemini", "slug_confidence": "confirm"},
            ],
        },
    ]


def _build_reasoning_ladder(env: dict) -> list:
    """reasoning / funnel: GLM 5.2 + DeepSeek (Ollama Cloud first) →
    OpenRouter equivalents → Gemini last resort."""
    return [
        {
            "rung": 1, "role": "reasoning", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_GLM", "glm-5.2:cloud"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "role": "reasoning", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_DEEPSEEK", "deepseek-v4-pro:cloud"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 3, "role": "reasoning", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "models": [
                {"slug": _slug(env, "OPENROUTER_GLM", "z-ai/glm-5.2"),
                 "family": "glm", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 4, "role": "reasoning", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "models": [
                {"slug": _slug(env, "OPENROUTER_DEEPSEEK", "deepseek/deepseek-v4-pro"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 5, "role": "reasoning", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "last-resort",
            "models": [
                {"slug": _slug(env, "OPENROUTER_GEMINI", "google/gemini-3.5-flash"),
                 "family": "gemini", "slug_confidence": "confirm"},
            ],
        },
    ]


def _build_execution_ladder(env: dict) -> list:
    """execution: MiniMax M3 (probe-gated) → DeepSeek (Ollama Cloud then OpenRouter) →
    Gemini last resort.  MiniMax M2 is BANNED — it does not appear here."""
    return [
        {
            "rung": 1, "role": "execution", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": True,
            "thinking": THINKING_EFFORT, "vision": True,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_MINIMAX_M3", "minimax-m3:cloud"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "role": "execution", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_DEEPSEEK", "deepseek-v4-pro:cloud"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 3, "role": "execution", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": True,
            "thinking": THINKING_EFFORT, "vision": True,
            "models": [
                {"slug": _slug(env, "OPENROUTER_MINIMAX_M3", "minimax/minimax-m3"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 4, "role": "execution", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "models": [
                {"slug": _slug(env, "OPENROUTER_DEEPSEEK", "deepseek/deepseek-v4-pro"),
                 "family": "deepseek", "slug_confidence": "repo-documented"},
            ],
        },
        {
            "rung": 5, "role": "execution", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": False,
            "notes": "last-resort",
            "models": [
                {"slug": _slug(env, "OPENROUTER_GEMINI", "google/gemini-3.5-flash"),
                 "family": "gemini", "slug_confidence": "confirm"},
            ],
        },
    ]


def _build_qc_ladder(env: dict) -> list:
    """qc: MiniMax M3 (probe-gated, vision required) → Gemini 3.5 Flash last resort (vision).
    DeepSeek and GLM are NOT on this ladder — no confirmed vision capability.
    Vision must never route to a text-only model."""
    return [
        {
            "rung": 1, "role": "qc", "provider": "ollama-cloud",
            "base_url": OLLAMA_CLOUD_BASE_URL, "probe_gated": True,
            "thinking": THINKING_EFFORT, "vision": True,
            "max_tokens": OLLAMA_CLOUD_MAX_TOKENS,
            "models": [
                {"slug": _slug(env, "OLLAMA_MINIMAX_M3", "minimax-m3:cloud"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 2, "role": "qc", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": True,
            "thinking": THINKING_EFFORT, "vision": True,
            "models": [
                {"slug": _slug(env, "OPENROUTER_MINIMAX_M3", "minimax/minimax-m3"),
                 "family": "minimax", "slug_confidence": "confirm"},
            ],
        },
        {
            "rung": 3, "role": "qc", "provider": "openrouter",
            "base_url": OPENROUTER_BASE_URL, "probe_gated": False,
            "thinking": THINKING_EFFORT, "vision": True,
            "notes": "last-resort",
            "models": [
                {"slug": _slug(env, "OPENROUTER_GEMINI", "google/gemini-3.5-flash"),
                 "family": "gemini", "slug_confidence": "confirm"},
            ],
        },
    ]


_ROLE_BUILDERS: dict[str, Callable[[dict], list]] = {
    "content": _build_content_ladder,
    "html": _build_html_ladder,
    "reasoning": _build_reasoning_ladder,
    "execution": _build_execution_ladder,
    "qc": _build_qc_ladder,
}

# ---------------------------------------------------------------------------
# Public ladder API
# ---------------------------------------------------------------------------


def build_ladder(env: Optional[dict] = None, *, role: str = "execution") -> list:
    """Build the role-keyed non-Anthropic fallback ladder.

    Parameters
    ----------
    env:
        Environment dict for MODEL_ROUTER_* overrides. Defaults to ``os.environ``.
    role:
        One of ``content``, ``html`` (alias ``code``), ``reasoning`` (alias ``funnel``),
        ``execution``, ``qc``. Default: ``execution``.

    Returns a list of rung dicts. Raises AnthropicModelError if any resolved
    slug is Anthropic (build-time guard)."""
    env = env if env is not None else os.environ
    canonical = _ROLE_ALIASES.get(role, role)
    if canonical not in _VALID_ROLES:
        raise ValueError(
            f"Unknown role {role!r}. Must be one of: "
            f"{sorted(_VALID_ROLES | set(_ROLE_ALIASES))}"
        )
    ladder = _ROLE_BUILDERS[canonical](env)
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
                    f"rung {rung.get('rung')} model {m.get('slug')!r} is Anthropic "
                    f"— banned on a client box"
                )


def assert_ollama_cloud_ready(rung: dict, env: Optional[dict] = None) -> None:
    """For an Ollama Cloud rung, assert the documented Ollama Cloud invariants:
    every model slug ends with ``:cloud`` and the baseUrl contains ollama.com.
    (The id_ed25519 device-key requirement is enforced by the runtime, not here.)"""
    if rung.get("provider") != "ollama-cloud":
        return
    if "ollama.com" not in (rung.get("base_url") or ""):
        raise OllamaCloudConfigError(
            f"rung {rung.get('rung')}: Ollama Cloud baseUrl must be ollama.com, "
            f"got {rung.get('base_url')!r}"
        )
    for m in rung.get("models", []):
        if not m.get("slug", "").endswith(":cloud"):
            raise OllamaCloudConfigError(
                f"rung {rung.get('rung')}: Ollama Cloud slug must end with ':cloud', "
                f"got {m.get('slug')!r}"
            )


# ---------------------------------------------------------------------------
# Probe gate — requires a real tool-call / JSON return from the model.
# ---------------------------------------------------------------------------

# The fixed probe task. PASS only if the executor returns a dict that BOTH parses
# AND reports the tool-call actually fired. Catches MiniMax's historical
# "plausible-looking non-tool text" before a whole build is wasted.
PROBE_TASK = {
    "instruction": (
        "Call the tool `echo_tool` with exactly {\"ok\": true}. "
        "Reply ONLY via the tool call."
    ),
    "tool": {"name": "echo_tool", "schema": {"ok": "boolean"}},
    "expect": {"ok": True},
}


def probe_passes(result: Optional[dict]) -> bool:
    """A probe PASSES only when the executor result parses AND the tool-call fired
    AND the returned args match {ok: true}."""
    if not isinstance(result, dict):
        return False
    if not result.get("tool_call_fired"):
        return False
    if not result.get("parsed"):
        return False
    return result.get("args", {}) == PROBE_TASK["expect"]


# Executor signature: executor(provider, model_slug, base_url, task_dict) -> dict
ExecutorType = Callable[[str, str, str, dict], Optional[dict]]


# ---------------------------------------------------------------------------
# Stub executor for offline tests / dry-runs
# ---------------------------------------------------------------------------


def make_stub_executor(
    fail_families: tuple = (), advance_families: tuple = ()
) -> ExecutorType:
    """Deterministic, OFFLINE executor for tests and dry-runs.

    Returns a passing tool-call result unless:
      - the model family is in ``fail_families``   → probe FAIL
      - the model family is in ``advance_families`` → simulated 429/timeout (advance)
    Family extraction: last path component, strip version/cloud suffix.
    """
    def _exec(
        provider: str, slug: str, base_url: str, task: dict
    ) -> Optional[dict]:
        fam = slug.split("/")[-1].split(":")[0]      # e.g. "kimi-k2.6:cloud" → "kimi-k2.6"
        fam = re.sub(r"[-_].*$", "", fam)             # "kimi-k2.6" → "kimi"
        if fam in advance_families:
            return {"advance": True}
        if fam in fail_families:
            return {"tool_call_fired": False, "parsed": True, "args": {}}
        return {"tool_call_fired": True, "parsed": True, "args": {"ok": True}}
    return _exec


# ---------------------------------------------------------------------------
# select() — the public entry point imported by v2_dispatcher et al.
# ---------------------------------------------------------------------------


def select(
    executor: ExecutorType,
    *,
    role: str = "execution",
    env: Optional[dict] = None,
    ladder: Optional[list] = None,
    backoff: tuple = (2.0, 8.0),
    sleep: Callable[[float], None] = time.sleep,
    receipt_path: Optional[str] = None,
) -> dict:
    """Walk the role-keyed ladder, probe-gate gated rungs, return the chosen rung+model.

    Parameters
    ----------
    executor:
        Callable(provider, slug, base_url, task) -> dict|None.  Use
        ``make_stub_executor()`` for offline tests.
    role:
        One of ``content``, ``html`` / ``code``, ``reasoning`` / ``funnel``,
        ``execution``, ``qc``.  Default: ``execution``.
    env:
        Env overrides for MODEL_ROUTER_* slugs.
    ladder:
        Pre-built ladder (overrides ``role`` / ``env``).
    backoff:
        (first_retry_sleep_s, max_sleep_s) — currently only first is used.
    sleep:
        Injection point for tests (pass ``lambda *_: None``).
    receipt_path:
        If given, write the routing receipt JSON here (must be OUTSIDE the skill dir).

    Returns
    -------
    dict with keys:
        ``chosen``        — the winning rung+model entry, or None if all rungs failed.
        ``probe_results`` — per-rung probe log.
        ``ladder``        — the full ladder that was walked.
        ``role``          — the canonical role that was resolved.

    assert_model_sovereignty (shared-utils) is called on each slug before dispatch —
    hard-blocking any Anthropic model. NEVER returns an Anthropic model.
    """
    env = env if env is not None else os.environ
    if ladder is None:
        ladder = build_ladder(env, role=role)
    assert_no_anthropic(ladder)

    # Resolve canonical role name from the ladder or the argument.
    canonical_role = _ROLE_ALIASES.get(role, role)

    probe_results: list = []
    chosen: Optional[dict] = None

    for rung in ladder:
        # Ollama Cloud structural invariants check.
        try:
            assert_ollama_cloud_ready(rung, env)
        except OllamaCloudConfigError as exc:
            probe_results.append({
                "rung": rung["rung"], "skipped": True, "reason": str(exc),
            })
            continue

        for model in rung["models"]:
            slug = model["slug"]

            # Per-slug sovereign check (Anthropic hard-block via shared-utils).
            _sovereignty_check(slug)

            entry: dict = {
                "rung": rung["rung"],
                "provider": rung["provider"],
                "model": slug,
                "role": rung.get("role"),
            }

            # Probe gate: only on probe_gated rungs (MiniMax M3).
            if rung.get("probe_gated"):
                try:
                    pr = executor(rung["provider"], slug, rung["base_url"], PROBE_TASK)
                except Exception as exc:  # noqa: BLE001
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
            if rung.get("max_tokens") is not None:
                entry["max_tokens"] = rung["max_tokens"]
            probe_results.append(entry)
            chosen = entry
            break

        if chosen:
            break

    receipt = {
        "policy": (
            "client-provider; NEVER Anthropic; Ollama Cloud preferred, OpenRouter backup; "
            "thinking=HIGH; MiniMax M2 BANNED; Kimi via Ollama/OpenRouter only"
        ),
        "role": canonical_role,
        "chosen": chosen,
        "probe_results": probe_results,
        "ladder": ladder,
    }
    if receipt_path:
        _write_receipt(receipt_path, receipt)
    return receipt


def _write_receipt(path: str, receipt: dict) -> None:
    """Write the routing receipt JSON. Path MUST be outside the skill dir
    (run-evidence root) per the update-overlay rule."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)


# ---------------------------------------------------------------------------
# Offline self-test (--selftest CLI flag)
# ---------------------------------------------------------------------------


def _selftest() -> int:
    """Offline self-test: role-aware ladders, Anthropic guard, probe-gate, failover."""
    errors: list = []

    # ── 1. All roles produce valid, non-Anthropic ladders ─────────────────
    for role in list(_VALID_ROLES) + list(_ROLE_ALIASES):
        try:
            ladder = build_ladder({}, role=role)
        except Exception as exc:
            errors.append(f"build_ladder failed for role={role!r}: {exc}")
            continue
        try:
            assert_no_anthropic(ladder)
        except AnthropicModelError as exc:
            errors.append(f"role={role!r}: Anthropic leaked into ladder: {exc}")
        blob = json.dumps(ladder).lower()
        if any(m in blob for m in _ANTHROPIC_MARKERS):
            errors.append(f"role={role!r}: Anthropic marker in ladder JSON")
        # No M2 anywhere.
        if "minimax-m2" in blob or "minimax_m2" in blob:
            errors.append(f"role={role!r}: BANNED MiniMax M2 found in ladder JSON")

    # ── 2. Ollama Cloud BEFORE OpenRouter on every role ───────────────────
    for role in _VALID_ROLES:
        ladder = build_ladder({}, role=role)
        providers = [r["provider"] for r in ladder]
        first_openrouter = next(
            (i for i, p in enumerate(providers) if p == "openrouter"), len(providers)
        )
        last_ollama = max(
            (i for i, p in enumerate(providers) if p == "ollama-cloud"), default=-1
        )
        if last_ollama != -1 and last_ollama > first_openrouter:
            errors.append(
                f"role={role!r}: Ollama Cloud rung appears AFTER OpenRouter rung "
                f"(providers={providers})"
            )

    # ── 3. Last rung on every role is Gemini 3.5 Flash (last-resort) ──────
    for role in _VALID_ROLES:
        ladder = build_ladder({}, role=role)
        last_slug = ladder[-1]["models"][0]["slug"]
        if "gemini" not in last_slug.lower():
            errors.append(
                f"role={role!r}: last rung must be Gemini 3.5 Flash, got {last_slug!r}"
            )

    # ── 4. Per-role rung-1 model assertions ───────────────────────────────
    checks = {
        "content": ("kimi", False),        # family, probe_gated
        "html": ("glm", False),
        "reasoning": ("glm", False),
        "execution": ("minimax", True),
        "qc": ("minimax", True),
    }
    for role, (expected_family, expected_probe) in checks.items():
        ladder = build_ladder({}, role=role)
        r1 = ladder[0]
        fam = r1["models"][0]["family"]
        if fam != expected_family:
            errors.append(
                f"role={role!r}: rung-1 family must be {expected_family!r}, got {fam!r}"
            )
        if bool(r1.get("probe_gated")) != expected_probe:
            errors.append(
                f"role={role!r}: rung-1 probe_gated must be {expected_probe}, "
                f"got {r1.get('probe_gated')}"
            )

    # ── 5. content rung-1 is Ollama Cloud Kimi ────────────────────────────
    content_ladder = build_ladder({}, role="content")
    r1_slug = content_ladder[0]["models"][0]["slug"]
    if r1_slug != "kimi-k2.6:cloud":
        errors.append(f"content rung-1 slug must be kimi-k2.6:cloud, got {r1_slug!r}")
    if content_ladder[0]["provider"] != "ollama-cloud":
        errors.append("content rung-1 must be ollama-cloud provider")

    # ── 6. execution rung-2 is DeepSeek (the M3-probe-fail fallback) ──────
    exec_ladder = build_ladder({}, role="execution")
    exec_r2 = exec_ladder[1]
    if exec_r2["models"][0]["family"] != "deepseek":
        errors.append(
            f"execution rung-2 must be DeepSeek (probe-fail fallback), "
            f"got {exec_r2['models'][0]['family']!r}"
        )
    if exec_r2.get("probe_gated"):
        errors.append("execution rung-2 (DeepSeek) must NOT be probe-gated")

    # ── 7. execution role: no MiniMax M2 at all ───────────────────────────
    exec_blob = json.dumps(exec_ladder).lower()
    if "minimax-m2" in exec_blob or "minimax_m2" in exec_blob:
        errors.append("execution ladder: BANNED MiniMax M2 found")

    # ── 8. Ollama Cloud invariants (:cloud + ollama.com) ──────────────────
    for role in _VALID_ROLES:
        ladder = build_ladder({}, role=role)
        for rung in ladder:
            if rung.get("provider") == "ollama-cloud":
                try:
                    assert_ollama_cloud_ready(rung, {})
                except OllamaCloudConfigError as exc:
                    errors.append(
                        f"role={role!r} rung {rung.get('rung')}: {exc}"
                    )

    # ── 9. thinking=high on every rung, every role ────────────────────────
    for role in _VALID_ROLES:
        for rung in build_ladder({}, role=role):
            if rung.get("thinking") != "high":
                errors.append(
                    f"role={role!r} rung {rung.get('rung')}: thinking must be high"
                )

    # ── 10. select() with role= works; probe-fail advances correctly ───────
    # content: clean stub → rung 1 (Kimi Ollama Cloud)
    out_c = select(make_stub_executor(), role="content", env={}, sleep=lambda *_: None)
    if not out_c["chosen"] or out_c["chosen"]["rung"] != 1:
        errors.append(f"content clean stub should choose rung 1, got {out_c['chosen']}")

    # execution: probe-fail on MiniMax → rung 2 DeepSeek
    out_e = select(
        make_stub_executor(fail_families=("minimax",)),
        role="execution", env={}, sleep=lambda *_: None,
    )
    if not out_e["chosen"] or out_e["chosen"]["rung"] != 2:
        errors.append(
            f"execution minimax-fail should advance to rung 2 (DeepSeek), "
            f"got {out_e['chosen']}"
        )
    if out_e["chosen"] and "deepseek" not in out_e["chosen"]["model"]:
        errors.append(f"execution rung-2 model must be DeepSeek, got {out_e['chosen']['model']}")

    # qc: probe-fail on MiniMax → rung 3 Gemini (the only non-probe-gated qc rung)
    out_q = select(
        make_stub_executor(fail_families=("minimax",)),
        role="qc", env={}, sleep=lambda *_: None,
    )
    if not out_q["chosen"] or "gemini" not in out_q["chosen"]["model"]:
        errors.append(
            f"qc minimax-fail should advance to Gemini rung, got {out_q['chosen']}"
        )

    # ── 11. thinking=high carried onto the chosen entry ───────────────────
    out = select(make_stub_executor(), role="execution", env={}, sleep=lambda *_: None)
    if out["chosen"] and out["chosen"].get("thinking") != "high":
        errors.append("chosen entry must carry thinking=high")

    # ── 12. Anthropic injection is caught by assert_no_anthropic ──────────
    bad = build_ladder({}, role="execution")
    bad[0]["models"][0]["slug"] = "BANNED-claude-sentinel-must-be-rejected"
    try:
        assert_no_anthropic(bad)
        errors.append("assert_no_anthropic failed to catch an injected Anthropic slug")
    except AnthropicModelError:
        pass

    # ── 13. Aliases resolve correctly ─────────────────────────────────────
    code_ladder = build_ladder({}, role="code")
    html_ladder = build_ladder({}, role="html")
    if code_ladder != html_ladder:
        errors.append("role alias 'code' must produce same ladder as 'html'")
    funnel_ladder = build_ladder({}, role="funnel")
    reasoning_ladder = build_ladder({}, role="reasoning")
    if funnel_ladder != reasoning_ladder:
        errors.append("role alias 'funnel' must produce same ladder as 'reasoning'")

    # ── 14. kimi slug is kimi-k2.6, not kimi-2.6 ─────────────────────────
    for rung in build_ladder({}, role="content"):
        for m in rung["models"]:
            if "kimi" in m["slug"] and "kimi-k2.6" not in m["slug"] and "kimi" in m["slug"]:
                errors.append(
                    f"Kimi slug must be kimi-k2.6 (not kimi-2.6), got {m['slug']!r}"
                )

    # ── 15. Ollama Cloud max_tokens == 65536 on every ollama-cloud rung ───
    for role in _VALID_ROLES:
        ladder = build_ladder({}, role=role)
        for rung in ladder:
            if rung.get("provider") == "ollama-cloud":
                mt = rung.get("max_tokens")
                if mt != OLLAMA_CLOUD_MAX_TOKENS:
                    errors.append(
                        f"role={role!r} rung {rung.get('rung')}: "
                        f"ollama-cloud max_tokens must be {OLLAMA_CLOUD_MAX_TOKENS}, got {mt!r}"
                    )

    # ── 15b. select() carries max_tokens onto chosen when ollama-cloud ────
    out_mt = select(make_stub_executor(), role="content", env={}, sleep=lambda *_: None)
    if out_mt["chosen"] and out_mt["chosen"].get("provider") == "ollama-cloud":
        if out_mt["chosen"].get("max_tokens") != OLLAMA_CLOUD_MAX_TOKENS:
            errors.append(
                f"select() must carry max_tokens={OLLAMA_CLOUD_MAX_TOKENS} onto "
                f"chosen ollama-cloud entry, got {out_mt['chosen'].get('max_tokens')!r}"
            )

    # ── 15c. OpenRouter chosen entry must NOT have max_tokens ─────────────
    # Force to openrouter by making Ollama Cloud content rung fail.
    # content rung-2 is openrouter/kimi — stub never fails non-probe-gated rungs,
    # so we use a ladder with no ollama-cloud entries to guarantee openrouter is chosen.
    or_ladder = [r for r in build_ladder({}, role="content") if r["provider"] == "openrouter"]
    if or_ladder:
        out_or = select(
            make_stub_executor(), role="content", env={},
            ladder=or_ladder, sleep=lambda *_: None,
        )
        if out_or["chosen"] and "max_tokens" in out_or["chosen"]:
            errors.append(
                f"select() must NOT add max_tokens to an openrouter chosen entry, "
                f"got {out_or['chosen'].get('max_tokens')!r}"
            )

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[model_router selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(
        "[model_router selftest] PASS — role-aware ladder + guards + "
        "probe-gate + failover OK (offline)"
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="Skill-6 role-aware probe-gated non-Anthropic model ladder"
    )
    p.add_argument("--selftest", action="store_true", help="Run offline self-test (exits 0 on pass)")
    p.add_argument("--print-ladder", action="store_true", help="Print the ladder JSON for a role")
    p.add_argument(
        "--role",
        default="execution",
        choices=list(_VALID_ROLES) + list(_ROLE_ALIASES),
        help="Role to build the ladder for (default: execution)",
    )
    p.add_argument(
        "--emit",
        metavar="OUT",
        help="Run a stub select and write the receipt JSON to OUT (outside skill dir)",
    )
    args = p.parse_args(argv[1:])

    if args.selftest:
        return _selftest()
    if args.print_ladder:
        print(json.dumps(build_ladder(role=args.role), indent=2))
        return 0
    if args.emit:
        out = select(
            make_stub_executor(), role=args.role, receipt_path=args.emit,
            sleep=lambda *_: None,
        )
        print(json.dumps({"role": args.role, "chosen": out["chosen"], "receipt": args.emit}, indent=2))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
