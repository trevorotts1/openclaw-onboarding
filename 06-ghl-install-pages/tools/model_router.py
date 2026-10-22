#!/usr/bin/env python3
"""model_router.py — role-aware, probe-gated, NON-ANTHROPIC model resolution for Skill 06.

This router prescribes NO model by name. Every role resolves its model from
the client's own configuration, in this order:

  1. The client's explicit choice for the task/role:
     MODEL_ROUTER_CHOICE_<ROLE>, then MODEL_ROUTER_CHOICE.
  2. The client's configured default model:
     MODEL_ROUTER_DEFAULT_<ROLE>, then MODEL_ROUTER_DEFAULT.
     MODEL_ROUTER_DEFAULT mirrors the client's configured default (for example
     agents.defaults.model.primary in the client's own openclaw.json),
     exported into the environment by the install/runtime on the client's box.
  3. Neither is set: resolution STOPS with ClientModelNotConfiguredError,
     whose message asks the client to choose. A named model is never silently
     substituted.

The resolved ladder is the client's chosen model first (when a choice is set),
then the client's configured default (when set and different). That is the
whole ladder; the router invents no further rungs.

RECOMMENDATIONS (guidance only — the client can override; never a prescription
and never wired as a fallback value in code):
  content          — copy writing: welcome slides, prompts.
                     Recommendation: a model with a large context window,
                     because content work drafts full page and slide copy in
                     one pass.
  html  (code)     — code-block fix-loop.
                     Recommendation: a model with strong code generation and
                     reliable tool calling, because the fix-loop edits code
                     blocks and verifies the result in tight iterations.
  reasoning (funnel) — structure and planning.
                     Recommendation: a model with strong reasoning and a
                     large context window, because funnel planning holds the
                     whole funnel structure in context at once.
  execution        — browser-click drive loop (probe-gated).
                     Recommendation: a model with reliable tool calling,
                     because the drive loop issues a tool call on every step.
                     The probe gate verifies this before the role runs.
  qc               — vision QC on screenshots + DOM (probe-gated).
                     Recommendation: a vision-capable model, because QC reads
                     screenshots and rendered DOM; a text-only model cannot
                     do this role. The client must configure a vision-capable
                     model for qc.

PROVIDERS are derived from the resolved slug, never prescribed:
  slug ending in `:cloud`  → Ollama Cloud (baseUrl ollama.com, `:cloud` suffix,
                             `id_ed25519` device key)
  any other slug           → OpenRouter

EFFORT (OPT-IN, plan §4.4)
  Legacy behavior is preserved: `thinking=high` on every rung when NO effort
  profile is set. A client MAY opt in per role:
    MODEL_ROUTER_EFFORT_PROFILE_<ROLE>   e.g. MODEL_ROUTER_EFFORT_PROFILE_HTML
    MODEL_ROUTER_EFFORT_PROFILE          (all roles)
  Value: a bare level, one of "low" | "medium" | "high".
  Precedence: role profile > global profile > legacy "high".
  Provider capability is validated per rung against EFFORT_CAPABILITIES; an
  unsupported level or provider FAILS EXPLICITLY (EffortUnsupportedError /
  EffortProfileError) — it never silently becomes max/high. Level names are
  generic; no project model names are ever baked into a client install.
  Known deterministic procedures need no model selection per click (B18):
  select() runs once per role/build, never per scripted action.

BANNED
------
  MiniMax M2   — PURGED. Never appears in any rung, table, or recommendation.
  Anthropic    — Hard-blocked by both `assert_no_anthropic` (internal, build-time)
                 AND `assert_model_sovereignty` (shared-utils, per-slug at select-time).
                 The block applies to resolved slugs too: a client configuration
                 naming an Anthropic model is rejected, not routed.
  S24 excluded models — Luna, Terra, Qwen, Muse Wonder / Muse Wonder Full, and
                 free endpoints are a POLICY REJECTION (ExcludedModelPolicyError):
                 never called, never routed, never proposed as a fallback.

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

# Every rung carries thinking=high (policy binding) unless the client opts in
# to a role effort profile (see EFFORT_LEVELS / resolve_effort below).
THINKING_EFFORT = "high"

# Generic effort levels — provider-neutral names, never a project model name.
EFFORT_LEVELS = frozenset(["low", "medium", "high"])

# Opt-in role effort profile env keys (plan §4.4). Absent = legacy THINKING_EFFORT.
EFFORT_PROFILE_ENV = "MODEL_ROUTER_EFFORT_PROFILE"
EFFORT_PROFILE_ENV_ROLE = "MODEL_ROUTER_EFFORT_PROFILE_{ROLE}"

# Provider capability table (documented approved capability map, plan §4.4).
# A level outside a provider's set FAILS EXPLICITLY — it never silently becomes
# max. When a preflight probe reports narrower observed support, pass it as
# `capabilities` to resolve_effort(); the probe observation wins over this table.
EFFORT_CAPABILITIES: dict[str, frozenset] = {
    "openrouter": frozenset(["low", "medium", "high"]),
    "ollama-cloud": frozenset(["low", "medium", "high"]),
}

# S24 excluded models (plan §4.2): Luna, Terra, Qwen, Muse Wonder / Muse Wonder
# Full, and free endpoints. Any slug naming one is a POLICY REJECTION at
# resolution time — never called, never proposed as a fallback. Substring match
# on the lowercase slug; "free" excludes OpenRouter `:free` endpoints.
_EXCLUDED_MODEL_MARKERS = (
    "luna", "terra", "qwen", "muse-wonder", "muse wonder", "musewonder", ":free",
)

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


class ClientModelNotConfiguredError(RuntimeError):
    """Raised when the client has configured neither a model choice nor a
    configured default model for a role. This is the ask-the-client stop: the
    router never silently substitutes a named model of its own."""


class EffortProfileError(RuntimeError):
    """Raised when an opt-in effort profile is malformed (unknown level name).
    Fails explicitly — never silently degrades to the legacy/max level."""


class EffortUnsupportedError(RuntimeError):
    """Raised when the requested effort level is not supported by the resolved
    provider's capability set. Fails explicitly or maps through a documented
    approved mapping — never silently becomes max (plan §4.4)."""


class ExcludedModelPolicyError(RuntimeError):
    """Raised when any configured or proposed model names an S24 excluded model
    (Luna, Terra, Qwen, Muse Wonder/Full, free endpoints). Policy rejection:
    the model is never called."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _looks_anthropic(*values: str) -> bool:
    blob = " ".join(v for v in values if v).lower()
    return any(m in blob for m in _ANTHROPIC_MARKERS)


def _env_value(env: dict, key: str) -> str:
    return (env.get(key) or "").strip()


def _provider_for_slug(slug: str) -> str:
    """Providers are derived from the client's slug, never prescribed:
    a `:cloud` slug runs on Ollama Cloud; anything else runs on OpenRouter."""
    return "ollama-cloud" if slug.endswith(":cloud") else "openrouter"


def _family_of(slug: str) -> str:
    """Derive a family label from a slug: last path component, version/cloud
    suffix stripped (e.g. "vendor/some-model-2:cloud" → "some")."""
    fam = slug.split("/")[-1].split(":")[0]
    fam = re.sub(r"[-_].*$", "", fam).lower()
    return fam or "client"


# Per-role structural requirements the resolved rung inherits. probe_gated and
# vision are properties of the ROLE, not of any named model.
_ROLE_REQUIREMENTS: dict[str, dict] = {
    "content": {"probe_gated": False, "vision": False},
    "html": {"probe_gated": False, "vision": False},
    "reasoning": {"probe_gated": False, "vision": False},
    "execution": {"probe_gated": True, "vision": True},
    "qc": {"probe_gated": True, "vision": True},
}

# Guidance only. Surfaced in the ask-the-client stop message and the module
# docstring; never used as a value anywhere in resolution.
_ROLE_RECOMMENDATIONS: dict[str, str] = {
    "content": (
        "a model with a large context window, because content work drafts "
        "full page and slide copy in one pass"
    ),
    "html": (
        "a model with strong code generation and reliable tool calling, "
        "because the fix-loop edits code blocks and verifies the result in "
        "tight iterations"
    ),
    "reasoning": (
        "a model with strong reasoning and a large context window, because "
        "funnel planning holds the whole funnel structure in context at once"
    ),
    "execution": (
        "a model with reliable tool calling, because the drive loop issues "
        "a tool call on every step"
    ),
    "qc": (
        "a vision-capable model, because QC reads screenshots and rendered "
        "DOM; a text-only model cannot do this role"
    ),
}


def resolve_client_models(env: dict, role: str) -> list:
    """Resolve the client's models for a role, in resolution order.

    Returns a list of (slug, provider, source) tuples: the client's explicit
    choice first (MODEL_ROUTER_CHOICE_<ROLE>, then MODEL_ROUTER_CHOICE), then
    the client's configured default (MODEL_ROUTER_DEFAULT_<ROLE>, then
    MODEL_ROUTER_DEFAULT), de-duplicated. Returns [] when the client has
    configured neither; callers turn that into the ask-the-client stop."""
    canonical = _ROLE_ALIASES.get(role, role)
    suffix = canonical.upper()
    choice = (
        _env_value(env, f"MODEL_ROUTER_CHOICE_{suffix}")
        or _env_value(env, "MODEL_ROUTER_CHOICE")
    )
    default = (
        _env_value(env, f"MODEL_ROUTER_DEFAULT_{suffix}")
        or _env_value(env, "MODEL_ROUTER_DEFAULT")
    )
    out: list = []
    if choice:
        _excluded_model_check(choice)
        out.append((choice, _provider_for_slug(choice), "client-choice"))
    if default and default != choice:
        _excluded_model_check(default)
        out.append((default, _provider_for_slug(default), "client-default"))
    return out


def ask_client_message(role: str) -> str:
    """The ask-the-client stop message for an unconfigured role, carrying the
    per-role recommendation as guidance."""
    canonical = _ROLE_ALIASES.get(role, role)
    rec = _ROLE_RECOMMENDATIONS.get(canonical, "a model suited to this role")
    return (
        f"No model is configured for the {canonical!r} role. "
        "Ask the client which model they want to use for this role, or use "
        "the client's configured default model (set MODEL_ROUTER_CHOICE or "
        f"MODEL_ROUTER_DEFAULT). Recommendation: {rec}. "
        "This router does not prescribe a specific model by name."
    )


def _excluded_model_check(slug: str) -> None:
    """S24 guard: reject any slug naming an excluded model (Luna, Terra, Qwen,
    Muse Wonder/Full, free endpoints). Policy rejection — the slug is never
    called and never proposed as a fallback."""
    low = (slug or "").lower()
    for marker in _EXCLUDED_MODEL_MARKERS:
        if marker in low:
            raise ExcludedModelPolicyError(
                f"excluded model {slug!r} rejected by S24 policy "
                f"(matched {marker!r}): never called, never proposed as a "
                f"fallback"
            )


def resolve_effort(
    env: dict,
    role: str,
    provider: str,
    capabilities: Optional[dict] = None,
) -> str:
    """Resolve the opt-in effort level for a role, validated against the
    provider's capability set.

    Precedence (plan §4.4, client-choice preserved):
      1. MODEL_ROUTER_EFFORT_PROFILE_<ROLE>  (client's role-level opt-in)
      2. MODEL_ROUTER_EFFORT_PROFILE         (client's global opt-in)
      3. Legacy THINKING_EFFORT ("high")     when no profile is set

    Validation:
      - Unknown level name → EffortProfileError (explicit fail, never silent max).
      - Level outside the provider's capability set → EffortUnsupportedError
        (explicit fail or documented approved mapping — never silent max).
        A preflight `capabilities` observation, when given, wins over the
        static EFFORT_CAPABILITIES table.

    Returns the resolved level string. No project model names involved."""
    canonical = _ROLE_ALIASES.get(role, role)
    suffix = canonical.upper()
    raw = (
        _env_value(env, EFFORT_PROFILE_ENV_ROLE.format(ROLE=suffix))
        or _env_value(env, EFFORT_PROFILE_ENV)
    )
    if not raw:
        return THINKING_EFFORT  # legacy behavior preserved: profile absent
    level = raw.strip().lower()
    if level not in EFFORT_LEVELS:
        raise EffortProfileError(
            f"effort profile {raw!r} for role {canonical!r} is not a valid "
            f"level; must be one of {sorted(EFFORT_LEVELS)}"
        )
    caps = (
        (capabilities or {}).get(provider)
        or EFFORT_CAPABILITIES.get(provider)
        or frozenset()
    )
    caps = frozenset(caps)
    if level not in caps:
        raise EffortUnsupportedError(
            f"effort level {level!r} is not supported by provider "
            f"{provider!r} for role {canonical!r} (supported: "
            f"{sorted(caps)}); refusing to silently become max"
        )
    return level


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
# Ladder builder — client resolution only; no model is prescribed by name.
# ---------------------------------------------------------------------------


def _build_role_ladder(env: dict, role: str) -> list:
    """Build the ladder for a role from the client's own configuration.

    Rung 1 is the client's explicit choice when one is set; the next rung is
    the client's configured default when set and different. No other rungs
    exist. Raises ClientModelNotConfiguredError when the client has configured
    neither (the ask-the-client stop)."""
    resolved = resolve_client_models(env, role)
    if not resolved:
        raise ClientModelNotConfiguredError(ask_client_message(role))
    req = _ROLE_REQUIREMENTS[role]
    ladder: list = []
    for i, (slug, provider, source) in enumerate(resolved, start=1):
        rung = {
            "rung": i, "role": role, "provider": provider,
            "base_url": (
                OLLAMA_CLOUD_BASE_URL if provider == "ollama-cloud"
                else OPENROUTER_BASE_URL
            ),
            "probe_gated": req["probe_gated"],
            # Opt-in effort seam (plan §4.4): legacy "high" when no profile is
            # set; a validated level otherwise. Provider capability mismatch
            # raises here — explicit fail, never silent max.
            "thinking": resolve_effort(env, role, provider),
            "vision": req["vision"],
            "resolution": source,
            "models": [
                {"slug": slug, "family": _family_of(slug),
                 "slug_confidence": "client-configured"},
            ],
        }
        if provider == "ollama-cloud":
            rung["max_tokens"] = OLLAMA_CLOUD_MAX_TOKENS
        ladder.append(rung)
    return ladder


def _make_builder(role: str) -> Callable[[dict], list]:
    def _build(env: dict) -> list:
        return _build_role_ladder(env, role)
    return _build


_ROLE_BUILDERS: dict[str, Callable[[dict], list]] = {
    role: _make_builder(role)
    for role in ("content", "html", "reasoning", "execution", "qc")
}

# ---------------------------------------------------------------------------
# Public ladder API
# ---------------------------------------------------------------------------


def build_ladder(env: Optional[dict] = None, *, role: str = "execution") -> list:
    """Build the role-keyed ladder from the client's own configuration.

    Parameters
    ----------
    env:
        Environment dict for MODEL_ROUTER_CHOICE / MODEL_ROUTER_DEFAULT
        resolution. Defaults to ``os.environ``.
    role:
        One of ``content``, ``html`` (alias ``code``), ``reasoning`` (alias ``funnel``),
        ``execution``, ``qc``. Default: ``execution``.

    Returns a list of rung dicts. Raises ClientModelNotConfiguredError when the
    client has configured neither a choice nor a configured default for the
    role (the ask-the-client stop), and AnthropicModelError if any resolved
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
    assert_no_excluded_models(ladder)
    return ladder


def assert_no_excluded_models(ladder: list) -> None:
    """HARD S24 GUARD: raise ExcludedModelPolicyError if any rung (including a
    caller-proposed fallback ladder) names an excluded model — Luna, Terra,
    Qwen, Muse Wonder/Full, or a free endpoint. Policy rejection: such a model
    is never called."""
    for rung in ladder:
        for m in rung.get("models", []):
            _excluded_model_check(m.get("slug", ""))


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
# AND reports the tool-call actually fired. Catches models that answer with
# plausible-looking non-tool text before a whole build is wasted.
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
        fam = slug.split("/")[-1].split(":")[0]      # e.g. "acme-1:cloud" → "acme-1"
        fam = re.sub(r"[-_].*$", "", fam)             # "acme-1" → "acme"
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
        Env dict for MODEL_ROUTER_CHOICE / MODEL_ROUTER_DEFAULT resolution.
        When ``ladder`` is not given and the client has configured neither a
        choice nor a default for the role, build_ladder raises
        ClientModelNotConfiguredError (the ask-the-client stop); callers
        surface it rather than routing to a prescribed model.
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
    assert_no_excluded_models(ladder)

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

            # Probe gate: only on probe_gated rungs (execution and qc).
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
            "client-provider; NEVER Anthropic; model is the client's choice "
            "or the client's configured default model; thinking=high (legacy) "
            "unless the client opted in to a validated effort profile; "
            "MiniMax M2 BANNED; S24 excluded models (Luna, Terra, Qwen, "
            "Muse Wonder/Full, free endpoints) rejected, never called"
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
    """Offline self-test: client resolution, Anthropic guard, probe-gate, failover."""
    errors: list = []

    # Test configuration: a neutral client default on Ollama Cloud, and a
    # choice-plus-default pair for precedence and failover checks.
    TEST_ENV = {"MODEL_ROUTER_DEFAULT": "client-default:cloud"}
    CHOICE_ENV = {
        "MODEL_ROUTER_CHOICE": "client/choice-model",
        "MODEL_ROUTER_DEFAULT": "client-default:cloud",
    }

    # ── 1. All roles resolve from the client's configured default ─────────
    for role in list(_VALID_ROLES) + list(_ROLE_ALIASES):
        try:
            ladder = build_ladder(TEST_ENV, role=role)
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
        if "minimax-m2" in blob or "minimax_m2" in blob:
            errors.append(f"role={role!r}: BANNED MiniMax M2 found in ladder JSON")
        # The router prescribes nothing: the only slug is the client's default.
        slugs = [m["slug"] for r in ladder for m in r["models"]]
        if slugs != ["client-default:cloud"]:
            errors.append(
                f"role={role!r}: ladder must be exactly the client's "
                f"configured default, got {slugs}"
            )

    # ── 2. Resolution order: choice rung first, then configured default ──
    for role in _VALID_ROLES:
        ladder = build_ladder(CHOICE_ENV, role=role)
        got = [(r["models"][0]["slug"], r.get("resolution")) for r in ladder]
        want = [("client/choice-model", "client-choice"),
                ("client-default:cloud", "client-default")]
        if got != want:
            errors.append(
                f"role={role!r}: resolution order must be choice then "
                f"default, got {got}"
            )
        env = dict(CHOICE_ENV)
        env[f"MODEL_ROUTER_CHOICE_{role.upper()}"] = "role-pick:cloud"
        ladder = build_ladder(env, role=role)
        if ladder[0]["models"][0]["slug"] != "role-pick:cloud":
            errors.append(
                f"role={role!r}: role-specific choice must win over the "
                f"global choice"
            )

    # ── 3. Unconfigured client: the ask-the-client stop ────────────────────
    for role in _VALID_ROLES:
        try:
            build_ladder({}, role=role)
            errors.append(
                f"role={role!r}: unconfigured build_ladder must raise "
                f"ClientModelNotConfiguredError"
            )
        except ClientModelNotConfiguredError as exc:
            if "Ask the client" not in str(exc):
                errors.append(
                    f"role={role!r}: stop message must ask the client, "
                    f"got {exc}"
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"role={role!r}: wrong exception for unconfigured client: "
                f"{exc!r}"
            )

    # ── 4. Rung-1 structure follows the ROLE, not a named model ────────────
    probe_checks = {
        "content": False, "html": False, "reasoning": False,
        "execution": True, "qc": True,
    }
    for role, expected_probe in probe_checks.items():
        r1 = build_ladder(TEST_ENV, role=role)[0]
        if bool(r1.get("probe_gated")) != expected_probe:
            errors.append(
                f"role={role!r}: rung-1 probe_gated must be {expected_probe}"
            )
        if r1["models"][0]["family"] != "client":
            errors.append(
                f"role={role!r}: rung-1 family must derive from the "
                f"client's slug"
            )
    if not build_ladder(TEST_ENV, role="qc")[0].get("vision"):
        errors.append("qc rung-1 must be vision (a role requirement)")

    # ── 5. A configured Anthropic model is rejected, not routed ──────────
    try:
        build_ladder({"MODEL_ROUTER_DEFAULT": "anthropic/claude-x"}, role="content")
        errors.append(
            "configured Anthropic default must raise AnthropicModelError"
        )
    except AnthropicModelError:
        pass
    except Exception as exc:  # noqa: BLE001
        errors.append(
            f"configured Anthropic default raised wrong exception: {exc!r}"
        )

    # ── 6. Ollama Cloud invariants on resolved :cloud rungs ────────────────
    for role in _VALID_ROLES:
        for rung in build_ladder(TEST_ENV, role=role):
            if rung.get("provider") == "ollama-cloud":
                try:
                    assert_ollama_cloud_ready(rung, {})
                except OllamaCloudConfigError as exc:
                    errors.append(f"role={role!r} rung {rung.get('rung')}: {exc}")
                if rung.get("max_tokens") != OLLAMA_CLOUD_MAX_TOKENS:
                    errors.append(
                        f"role={role!r}: ollama-cloud rung must carry the "
                        f"max_tokens cap"
                    )

    # ── 7. thinking=high on every rung, every role ─────────────────────────
    for role in _VALID_ROLES:
        for rung in build_ladder(CHOICE_ENV, role=role):
            if rung.get("thinking") != "high":
                errors.append(
                    f"role={role!r} rung {rung.get('rung')}: thinking must "
                    f"be high"
                )

    # ── 8. select(): a clean run chooses the client's model ────────────────
    out_c = select(make_stub_executor(), role="content", env=TEST_ENV,
                   sleep=lambda *_: None)
    if not out_c["chosen"] or out_c["chosen"]["model"] != "client-default:cloud":
        errors.append(
            f"content clean stub should choose the client's configured "
            f"default, got {out_c['chosen']}"
        )
    if out_c["chosen"] and out_c["chosen"].get("max_tokens") != OLLAMA_CLOUD_MAX_TOKENS:
        errors.append(
            "select() must carry max_tokens onto an ollama-cloud chosen entry"
        )
    if out_c["chosen"] and out_c["chosen"].get("thinking") != "high":
        errors.append("chosen entry must carry thinking=high")

    # ── 9. select(): choice probe-fail advances to the configured default ──
    out_e = select(make_stub_executor(fail_families=("choice",)),
                   role="execution", env=CHOICE_ENV, sleep=lambda *_: None)
    if (not out_e["chosen"] or out_e["chosen"]["model"] != "client-default:cloud"
            or out_e["chosen"]["rung"] != 2):
        errors.append(
            f"execution choice-fail should advance to the configured "
            f"default rung, got {out_e['chosen']}"
        )

    # ── 10. select(): qc with a failing client model chooses NOTHING ───────
    # There is no named fallback anymore; a failed probe leaves chosen=None
    # rather than silently substituting a prescribed model.
    out_q = select(make_stub_executor(fail_families=("client",)),
                   role="qc", env=TEST_ENV, sleep=lambda *_: None)
    if out_q["chosen"] is not None:
        errors.append(
            f"qc with a failing client model must choose nothing, "
            f"got {out_q['chosen']}"
        )

    # ── 11. Anthropic injection is caught by assert_no_anthropic ───────────
    bad = build_ladder(TEST_ENV, role="execution")
    bad[0]["models"][0]["slug"] = "BANNED-claude-sentinel-must-be-rejected"
    try:
        assert_no_anthropic(bad)
        errors.append("assert_no_anthropic failed to catch an injected Anthropic slug")
    except AnthropicModelError:
        pass

    # ── 12. Aliases resolve identically ────────────────────────────────────
    if build_ladder(TEST_ENV, role="code") != build_ladder(TEST_ENV, role="html"):
        errors.append("role alias 'code' must produce same ladder as 'html'")
    if build_ladder(TEST_ENV, role="funnel") != build_ladder(TEST_ENV, role="reasoning"):
        errors.append("role alias 'funnel' must produce same ladder as 'reasoning'")

    # ── 13. An OpenRouter-resolved chosen entry carries NO max_tokens ──────
    or_env = {"MODEL_ROUTER_DEFAULT": "client/default-model"}
    out_or = select(make_stub_executor(), role="content", env=or_env,
                    sleep=lambda *_: None)
    if not out_or["chosen"] or out_or["chosen"].get("provider") != "openrouter":
        errors.append(
            f"an OpenRouter client default should be chosen on openrouter, "
            f"got {out_or['chosen']}"
        )
    elif "max_tokens" in out_or["chosen"]:
        errors.append(
            "select() must NOT add max_tokens to an openrouter chosen entry"
        )

    # ── 14. Opt-in effort profile: role profile > global profile > legacy ──
    if resolve_effort(TEST_ENV, "content", "openrouter") != THINKING_EFFORT:
        errors.append("no profile set must resolve the legacy high level")
    E_ROLE = dict(TEST_ENV)
    E_ROLE["MODEL_ROUTER_EFFORT_PROFILE_REASONING"] = "medium"
    for role in _VALID_ROLES:
        for rung in build_ladder(E_ROLE, role=role):
            want = "medium" if role == "reasoning" else "high"
            if rung.get("thinking") != want:
                errors.append(
                    f"role={role!r}: effort profile must give {want}, "
                    f"got {rung.get('thinking')}"
                )
    E_ALL = dict(TEST_ENV)
    E_ALL["MODEL_ROUTER_EFFORT_PROFILE"] = "low"
    for role in _VALID_ROLES:
        for rung in build_ladder(E_ALL, role=role):
            if rung.get("thinking") != "low":
                errors.append(
                    f"role={role!r}: global effort profile must give low, "
                    f"got {rung.get('thinking')}"
                )

    # ── 15. Unsupported effort FAILS EXPLICITLY, never silently max ────────
    E_BAD = dict(TEST_ENV)
    E_BAD["MODEL_ROUTER_EFFORT_PROFILE"] = "ultra"
    try:
        build_ladder(E_BAD, role="content")
        errors.append("unknown effort level must raise EffortProfileError")
    except EffortProfileError:
        pass
    E_LOW = dict(TEST_ENV)
    E_LOW["MODEL_ROUTER_EFFORT_PROFILE"] = "low"
    try:
        resolve_effort(E_LOW, "html", "openrouter",
                       {"openrouter": frozenset({"high"})})
        errors.append(
            "effort level outside provider capabilities must raise "
            "EffortUnsupportedError"
        )
    except EffortUnsupportedError:
        pass
    try:
        resolve_effort(E_LOW, "html", "unknown-provider")
        errors.append(
            "an unknown provider with an opt-in profile must fail explicitly"
        )
    except EffortUnsupportedError:
        pass

    # ── 16. S24: excluded models are a policy rejection, never called ──────
    for bad_slug in ("client/luna-x", "acme/terra-2", "ollama/qwen3:cloud",
                     "vendor/muse-wonder-full", "vendor/model:free"):
        try:
            build_ladder({"MODEL_ROUTER_DEFAULT": bad_slug}, role="content")
            errors.append(f"excluded model {bad_slug!r} must be rejected")
        except ExcludedModelPolicyError:
            pass
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"excluded model {bad_slug!r} raised wrong exception: {exc!r}"
            )
    called: list = []

    def _spy_executor(*_a, **_k):
        called.append(1)
        return {"tool_call_fired": True, "parsed": True, "args": {"ok": True}}

    bad_ladder = build_ladder(TEST_ENV, role="execution")
    bad_ladder[0]["models"][0]["slug"] = "client/luna-x"
    try:
        select(_spy_executor, role="execution", ladder=bad_ladder,
               sleep=lambda *_: None)
        errors.append(
            "select() must reject an S24 excluded model in a proposed "
            "fallback ladder"
        )
    except ExcludedModelPolicyError:
        pass
    if called:
        errors.append("an S24 excluded model must NEVER be called")

    # ── 17. B18: select() resolves once per role; deterministic procedures ──
    # need no model selection per click — nothing here dispatches per action.
    if out_c["chosen"] is None:
        errors.append("B18 setup: content selection must still resolve once")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[model_router selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(
        "[model_router selftest] PASS — client resolution + guards + "
        "probe-gate + failover OK (offline)"
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="Skill-6 role-aware probe-gated non-Anthropic model resolution"
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
    try:
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
    except ClientModelNotConfiguredError as exc:
        # The ask-the-client stop, printed plainly instead of a traceback.
        print(str(exc), file=sys.stderr)
        return 2
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
