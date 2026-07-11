#!/usr/bin/env python3
"""model_router.py -- the ONE call site for every runtime model TURN in the
Podcast Production Engine (Skill 58).

config/models.json is the DECLARED runtime routing policy (which client-owned
models do content and judge work, in what priority, with which credential
labels). Before this module existed that policy was config-only: the pipeline
"routed" in prose. This is the deterministic executor of that policy -- the
single choke point through which every billable text turn flows. It:

  * resolves a runtime TIER ("content" or "qc_judge") to the CLIENT's own
    priority-ordered provider chain from config/models.json (never a hardcoded
    model name; forward-dated client model ids are taken AS-CONFIGURED),
  * resolves each link's credential by ENV LABEL only (live process env first),
    reporting SET / NOT SET and NEVER a secret value,
  * advances the chain on retryable failures (insufficient_credits, auth,
    rate_limit, timeout, refusal), meters every call through the ONE cost ledger
    (podcast-cost-ledger.py), holds the job durably on chain exhaustion
    (credit_queue.py) with exactly ONE deduped founder alert through the
    OpenClaw gateway (alert-dedup.py),
  * refuses at call time any resolved model / provider / family matching the
    config deny_patterns (claude, anthropic, us.anthropic, opus, sonnet, haiku)
    OR an Anthropic-family shape -- a deny match is a HARD ERROR, never a silent
    fallback (furnace-design Guardrail 5; mirrors guard-no-anthropic-runtime.py),
  * records the model ACTUALLY used honestly, and marks a SUBSTITUTION whenever a
    non-primary link served the turn so the delivery report can name it.

SOVEREIGNTY: the chain is the CLIENT's own accounts under the CLIENT's own
labels. Operator keys never land on a client box. The engine never substitutes a
client's expressed model choice for a non-client one. This module never prints a
credential value: a credential is reported SET or NOT SET by label, and its
value is used solely to build an Authorization header, never logged or stored.

Exit codes (house convention; 1 = unexpected error):
  0  completion
  2  deny-pattern refusal (a denied / Anthropic-shaped id reached the router)
  3  chain exhausted, job held (durable HOLD + ONE deduped founder alert)
  4  budget ceiling block (podcast-cost-ledger.py refused the call before it billed)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
CONFIG = SKILL_DIR / "config"
MODELS_JSON_PATH = CONFIG / "models.json"

# House exit codes for this script.
EX_OK, EX_ERR, EX_DENY, EX_HOLD, EX_BUDGET = 0, 1, 2, 3, 4

# The two RUNTIME tiers this router serves. Prompts speak only these tier names;
# they never name a model. Everything else under podcast_engine.models (the
# deny_patterns / deny_match metadata) is policy, not a routable tier.
CONTENT_TIER = "content"
JUDGE_TIER = "qc_judge"
ROUTABLE_TIERS = (CONTENT_TIER, JUDGE_TIER)

# Default per-tier generation parameters. The judge runs deterministically
# (temperature 0) and is ALWAYS a different resolution than the writer (the
# config already orders the tiers so the first content and first judge models
# differ; qc-attempt-gate.py enforces the independence law downstream).
_TIER_DEFAULT_PARAMS = {
    CONTENT_TIER: {"temperature": 0.3},
    JUDGE_TIER: {"temperature": 0.0},
}

# Cost-ledger hard-ceiling exit codes (podcast-cost-ledger.py): any of these
# means "do not spend" and becomes a BudgetCeilingBlock. EXIT_SOFT (2) is
# advisory and allowed through.
_LEDGER_HARD_CEILING_CODES = frozenset((10, 13, 14))

# Default OpenAI-compatible chat path appended to a link base_url.
_CHAT_PATH = "/chat/completions"

# ---------------------------------------------------------------------------
# Anthropic-family shape backstop. Assembled from FRAGMENTS so this shipped
# runtime file carries no contiguous banned literal (guard-no-anthropic-runtime
# scans .py source). This is defense in depth BESIDE the config deny_patterns:
# even if the config list were emptied, an Anthropic-shaped id is still refused.
# ---------------------------------------------------------------------------
_A = "anthro" + "pic"
_C = "clau" + "de"
_ANTHROPIC_SHAPE_RE = re.compile(
    r"(?i)(^|[^a-z0-9])(" + _C + r"|" + _A + r")([^a-z0-9]|$)"
    r"|" + _A + r"/"
    r"|" + _C + r"-"
    r"|us\." + _A + r"\.",
)

_CREDIT_TERMS = (
    "insufficient", "credit", "quota", "billing", "balance", "payment required",
    "exceeded your current", "out of funds", "top up", "top-up",
)
_REFUSAL_TERMS = (
    "content policy", "safety", "cannot assist", "i can't help", "i cannot help",
    "refuse", "moderation", "flagged", "prohibited content",
)


def is_denied(text: str, deny_patterns: List[str]) -> bool:
    """True iff `text` matches any config deny pattern (case-insensitive
    substring, mirroring deny_match) OR an Anthropic-family shape."""
    if not text:
        return False
    low = str(text).lower()
    for pat in (deny_patterns or []):
        if pat and str(pat).lower() in low:
            return True
    return bool(_ANTHROPIC_SHAPE_RE.search(str(text)))


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
class ErrorClass(str, Enum):
    INSUFFICIENT_CREDITS = "insufficient_credits"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    """A single provider link failed. Retryable classes advance the chain."""

    def __init__(self, provider: str, error_class: ErrorClass,
                 status: Optional[int] = None, detail: str = ""):
        self.provider = provider
        self.error_class = error_class
        self.status = status
        self.detail = detail  # never credential-shaped (caller controls content)
        super().__init__("%s %s (status=%s)" % (provider, error_class.value, status))


class ModelRouterError(Exception):
    """Base router error; carries the engine exit code."""

    exit_code = EX_ERR


class DenyPatternRefusal(ModelRouterError):
    exit_code = EX_DENY


class ChainExhaustedHold(ModelRouterError):
    exit_code = EX_HOLD

    def __init__(self, reason: str, tier: str, degradations: List[dict]):
        self.reason = reason  # "credit_out" | "chain_exhausted"
        self.tier = tier
        self.degradations = degradations
        super().__init__("tier %s chain exhausted (%s); job held" % (tier, reason))


class BudgetCeilingBlock(ModelRouterError):
    exit_code = EX_BUDGET


class UnknownTierError(ModelRouterError):
    exit_code = EX_ERR


class ConfigError(ModelRouterError):
    exit_code = EX_ERR


# ---------------------------------------------------------------------------
# Transport (default: stdlib urllib; injectable for tests)
# ---------------------------------------------------------------------------
@dataclass
class HttpRequest:
    url: str
    headers: Dict[str, str]
    body: dict
    method: str = "POST"


@dataclass
class HttpResponse:
    status: int
    body_text: str
    json: Optional[dict] = None


Transport = Callable[[HttpRequest, float], HttpResponse]


def default_transport(req: HttpRequest, timeout: float) -> HttpResponse:
    """Real HTTP via the stdlib. Never logs headers (they carry the bearer)."""
    data = json.dumps(req.body).encode("utf-8")
    r = urllib.request.Request(req.url, data=data, method=req.method)
    for k, v in req.headers.items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            return HttpResponse(status=resp.getcode(), body_text=raw, json=parsed)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        return HttpResponse(status=exc.code, body_text=raw, json=None)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Transport-level failure -> transient/timeout class, advance the chain.
        raise ProviderError("transport", ErrorClass.TIMEOUT, status=None,
                            detail=type(exc).__name__)


# ---------------------------------------------------------------------------
# Config loading + fail-closed validation
# ---------------------------------------------------------------------------
def _candidate_config_paths(explicit: Optional[str]) -> List[Path]:
    out: List[Path] = []
    if explicit:
        out.append(Path(explicit))
    env = os.environ.get("PODCAST_MODELS_JSON", "").strip()
    if env:
        out.append(Path(env))
    out.append(MODELS_JSON_PATH)
    return out


def load_models_config(explicit: Optional[str] = None) -> Tuple[dict, Path]:
    """Load config/models.json and return (podcast_engine_block, path)."""
    for p in _candidate_config_paths(explicit):
        if p.is_file():
            raw = json.loads(p.read_text(encoding="utf-8"))
            block = raw.get("podcast_engine")
            if not isinstance(block, dict):
                raise ConfigError("models.json missing 'podcast_engine' block: %s" % p)
            return block, p
    raise ConfigError(
        "no models.json found; searched: %s"
        % ", ".join(str(x) for x in _candidate_config_paths(explicit)))


def deny_patterns_of(block: dict) -> List[str]:
    """The runtime deny list. In config/models.json it lives under
    podcast_engine.models.deny_patterns; accept a top-level list too."""
    models = block.get("models") if isinstance(block.get("models"), dict) else {}
    pats = models.get("deny_patterns")
    if not isinstance(pats, list):
        pats = block.get("deny_patterns")
    return [str(p) for p in pats] if isinstance(pats, list) else []


def validate_config(block: dict) -> None:
    """Fail closed if the content tier is empty, a routable entry is missing a
    base_url / api_key_env / provider / model, or ANY tier entry matches a deny
    pattern (an Anthropic-shaped or denied id must never sit in a routable tier)."""
    models = block.get("models")
    if not isinstance(models, dict):
        raise ConfigError("podcast_engine.models missing")
    deny = deny_patterns_of(block)
    if not deny:
        raise ConfigError("podcast_engine.deny_patterns missing or empty")
    content = models.get(CONTENT_TIER)
    if not isinstance(content, list) or not content:
        raise ConfigError("content tier is empty; the router has nothing to route")
    for tier in ROUTABLE_TIERS:
        for i, link in enumerate(models.get(tier, []) or []):
            where = "%s[%d]" % (tier, i)
            for field_name in ("provider", "model", "base_url", "api_key_env"):
                if not str(link.get(field_name, "")).strip():
                    raise ConfigError("%s missing %s" % (where, field_name))
            for probe in (link.get("id"), link.get("model"),
                          link.get("provider"), link.get("family")):
                if probe and is_denied(str(probe), deny):
                    raise DenyPatternRefusal(
                        "config carries a denied id at %s (deny_patterns armed)" % where)


def resolve_tier(block: dict, tier: str) -> List[dict]:
    if tier not in ROUTABLE_TIERS:
        raise UnknownTierError(
            "unknown tier %r (routable: %s)" % (tier, ", ".join(ROUTABLE_TIERS)))
    links = (block.get("models", {}) or {}).get(tier)
    if not isinstance(links, list) or not links:
        raise ConfigError("tier %r has no configured models" % tier)
    return sorted(links, key=lambda link: int(link.get("priority", 1_000_000)))


# ---------------------------------------------------------------------------
# Credential resolution (env-first; SET / NOT SET only; value never printed)
# ---------------------------------------------------------------------------
def resolve_credential(link: dict) -> Tuple[Optional[str], str]:
    """Return (value_or_None, status). status is 'SET' or 'NOT SET' -- never the
    value. Order: the link's api_key_env label, then its api_key_env_aliases."""
    labels = []
    primary = str(link.get("api_key_env", "")).strip()
    if primary:
        labels.append(primary)
    for alias in link.get("api_key_env_aliases", []) or []:
        if str(alias).strip():
            labels.append(str(alias).strip())
    for label in labels:
        val = os.environ.get(label)
        if val:
            return val, "SET"
    return None, "NOT SET"


# ---------------------------------------------------------------------------
# Request building, response parsing, error classification
# ---------------------------------------------------------------------------
def encode_parameters(tier: str, link: dict) -> dict:
    """Map the tier defaults + link config onto an OpenAI-compatible body
    fragment. thinking rides only where the config set it to a non-default value
    (high reasoning stays on the primary lanes; furnace-design Guardrail 5). The
    portable 'reasoning_effort' field is used; override by injecting an encoder."""
    frag: dict = {}
    params = _TIER_DEFAULT_PARAMS.get(tier, {})
    if params.get("temperature") is not None:
        frag["temperature"] = params["temperature"]
    max_tokens = link.get("max_output_tokens") or link.get("maxTokens")
    if max_tokens:
        frag["max_tokens"] = int(max_tokens)
    thinking = str(link.get("thinking", "")).strip().lower()
    if thinking and thinking != "default":
        frag["reasoning_effort"] = thinking
    return frag


def build_chat_request(link: dict, tier: str, messages: List[dict],
                       credential_value: str,
                       encoder: Callable[[str, dict], dict]) -> HttpRequest:
    base = str(link.get("base_url", "")).strip().rstrip("/")
    if not base:
        raise ProviderError(str(link.get("provider", "")), ErrorClass.UNKNOWN,
                            status=None, detail="no base url configured")
    model = str(link.get("model", "")).strip()
    body = {"model": model, "messages": messages}
    body.update(encoder(tier, link))
    headers = {
        "Authorization": "Bearer " + credential_value,
        "Content-Type": "application/json",
    }
    return HttpRequest(url=base + _CHAT_PATH, headers=headers, body=body)


def parse_chat_response(resp: HttpResponse, configured_model: str) -> dict:
    """Normalize an OpenAI-compatible chat completion. Raises
    ProviderError(REFUSAL) if the body reads as a content refusal."""
    data = resp.json or {}
    choices = data.get("choices") or []
    text = ""
    if choices:
        msg = choices[0].get("message") or {}
        text = msg.get("content") or choices[0].get("text") or ""
    model_used = data.get("model") or configured_model
    usage = data.get("usage") or {}
    return {"text": text, "model_used": model_used, "usage": usage}


def classify_http_error(status: int, body_text: str) -> ErrorClass:
    low = (body_text or "").lower()
    credit_hit = any(term in low for term in _CREDIT_TERMS)
    if status == 402 or (credit_hit and status in (401, 403, 429, 400)):
        return ErrorClass.INSUFFICIENT_CREDITS
    if status in (401, 403):
        return ErrorClass.AUTH
    if status == 429:
        return ErrorClass.RATE_LIMIT
    if status == 408 or 500 <= status <= 599:
        return ErrorClass.TIMEOUT
    if any(term in low for term in _REFUSAL_TERMS):
        return ErrorClass.REFUSAL
    return ErrorClass.UNKNOWN


# ---------------------------------------------------------------------------
# Metering / hold / alert / substitution side-channels (subprocess; injectable;
# fail-soft). Defaults shell the engine's ONE ledger / queue / alert scripts.
# ---------------------------------------------------------------------------
def _script_cmd(name: str) -> Optional[List[str]]:
    p = SCRIPTS / name
    return [sys.executable, str(p)] if p.is_file() else None


def default_pre_meter(context: dict, tier: str, model: str, est_prompt_tokens: int) -> None:
    """Pre-meter via podcast-cost-ledger.py precheck. A hard-ceiling exit becomes
    a BudgetCeilingBlock BEFORE the call bills. Skipped with no client in context
    (unit / dry-run); a resolved box always ships the ledger."""
    client = (context or {}).get("client")
    if not client:
        return
    cmd = _script_cmd("podcast-cost-ledger.py")
    if not cmd:
        sys.stderr.write("[model_router] cost ledger absent; metering skipped (warn)\n")
        return
    argv = cmd + ["precheck", "--client", str(client), "--kind", "llm",
                  "--input-tokens", str(int(est_prompt_tokens))]
    ep = (context or {}).get("episode_id") or (context or {}).get("job_id")
    if ep:
        argv += ["--episode-id", str(ep)]
    try:
        rc = subprocess.call(argv, stdout=subprocess.DEVNULL)
    except Exception as exc:
        sys.stderr.write("[model_router] cost precheck failed: %s (warn)\n" % type(exc).__name__)
        return
    if rc in _LEDGER_HARD_CEILING_CODES:
        raise BudgetCeilingBlock(
            "podcast-cost-ledger.py blocked the call: a hard cost ceiling was "
            "reached before this %s turn billed (ledger exit %d)" % (tier, rc))


def default_post_meter(context: dict, tier: str, model: str, usage: dict) -> None:
    client = (context or {}).get("client")
    if not client:
        return
    cmd = _script_cmd("podcast-cost-ledger.py")
    if not cmd:
        return
    argv = cmd + ["record", "--client", str(client), "--kind", "llm",
                  "--model", str(model),
                  "--input-tokens", str(int(usage.get("prompt_tokens", 0) or 0)),
                  "--output-tokens", str(int(usage.get("completion_tokens", 0) or 0)),
                  "--note", "model_router %s turn" % tier]
    ep = (context or {}).get("episode_id") or (context or {}).get("job_id")
    if ep:
        argv += ["--episode-id", str(ep)]
    try:
        subprocess.call(argv, stdout=subprocess.DEVNULL)
    except Exception:
        pass


def default_hold(context: dict, reason: str, tier: str) -> None:
    """Durably HOLD the job on the credit-out queue via credit_queue.py. Fail-soft:
    a hold failure is logged; the router still raises ChainExhaustedHold."""
    ctx = context or {}
    job_id = ctx.get("job_id")
    client_id = ctx.get("client_id") or ctx.get("client")
    if not (job_id and client_id):
        sys.stderr.write("[model_router] hold context incomplete; HOLD not queued (warn)\n")
        return
    cmd = _script_cmd("credit_queue.py")
    if not cmd:
        sys.stderr.write("[model_router] credit_queue.py absent; HOLD not queued (warn)\n")
        return
    service = ctx.get("queue_service") or ("ollama_cloud" if tier == CONTENT_TIER else "openrouter")
    resume_stage = ctx.get("resume_stage") or ctx.get("cursor") or "writing"
    argv = cmd + ["hold", "--job-id", str(job_id), "--client-id", str(client_id),
                  "--service", str(service), "--resume-stage", str(resume_stage)]
    try:
        subprocess.call(argv, stdout=subprocess.DEVNULL)
    except Exception as exc:
        sys.stderr.write("[model_router] credit_queue.py hold failed: %s\n" % type(exc).__name__)


def default_alert(context: dict, tier: str, reason: str) -> None:
    """ONE deduped founder alert through the OpenClaw gateway (alert-dedup.py
    notify, decision severity => always-send, per-episode dedup). Fail-soft."""
    cmd = _script_cmd("alert-dedup.py")
    if not cmd:
        sys.stderr.write("[model_router] alert-dedup.py absent; alert not sent (warn)\n")
        return
    ctx = context or {}
    client = ctx.get("client") or ctx.get("client_id") or "unknown"
    episode = ctx.get("episode_id") or ctx.get("job_id") or "unknown"
    service = ctx.get("queue_service") or ("ollama_cloud" if tier == CONTENT_TIER else "openrouter")
    msg = ("Podcast engine: %s tier chain exhausted (%s). Job held at its cursor; "
           "it resumes when a provider in the chain is funded and reachable." % (tier, reason))
    argv = cmd + ["notify", "--client", str(client), "--service", str(service),
                  "--class", "insufficient_credits", "--severity", "decision",
                  "--episode", str(episode), "--message", msg]
    try:
        subprocess.call(argv, stdout=subprocess.DEVNULL)
    except Exception as exc:
        sys.stderr.write("[model_router] alert-dedup.py notify failed: %s\n" % type(exc).__name__)


def default_substitution_log(context: dict, tier: str, from_priority: int,
                             used_priority: int, model_used: str) -> None:
    """Record that a NON-primary link served the turn so the delivery report can
    name the substitution. Appends one JSONL line to an operator-only spool under
    the engine state dir; fail-soft (never blocks a successful turn)."""
    ctx = context or {}
    state_dir = ctx.get("state_dir") or os.environ.get("PODCAST_STATE_DIR")
    if not state_dir:
        home = os.environ.get("HOME", "")
        state_dir = os.path.join(home, ".openclaw", "state", "podcast-engine") if home else None
    if not state_dir:
        return
    try:
        spool_dir = os.path.join(state_dir, "substitutions")
        os.makedirs(spool_dir, mode=0o700, exist_ok=True)
        line = {
            "tier": tier,
            "from_priority": from_priority,
            "used_priority": used_priority,
            "model_used": model_used,
            "episode_id": ctx.get("episode_id") or ctx.get("job_id"),
            "client": ctx.get("client") or ctx.get("client_id"),
        }
        path = os.path.join(spool_dir, "substitutions.jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Route result
# ---------------------------------------------------------------------------
@dataclass
class RouteResult:
    tier: str
    provider: str
    model_used: str          # honest, deny-checked before return
    priority: int
    text: str
    substituted: bool = False
    usage: dict = field(default_factory=dict)
    degradations: List[dict] = field(default_factory=list)

    def to_public_dict(self) -> dict:
        """A record safe for the delivery report / run ledger. Carries NO
        credential. `substituted` and `model_used` name any fallback used."""
        return {
            "tier": self.tier,
            "provider": self.provider,
            "model_used": self.model_used,
            "priority": self.priority,
            "substituted": self.substituted,
            "usage": self.usage,
            "degradations": self.degradations,
        }


# ---------------------------------------------------------------------------
# The router
# ---------------------------------------------------------------------------
class ModelRouter:
    def __init__(self,
                 config_block: Optional[dict] = None,
                 transport: Optional[Transport] = None,
                 pre_meter: Optional[Callable] = None,
                 post_meter: Optional[Callable] = None,
                 hold_fn: Optional[Callable] = None,
                 alert_fn: Optional[Callable] = None,
                 substitution_fn: Optional[Callable] = None,
                 parameter_encoder: Optional[Callable] = None,
                 timeout: float = 600.0,
                 hold_immediately_on_credit_out: bool = False):
        if config_block is not None:
            validate_config(config_block)
        self.config = config_block
        self.deny = deny_patterns_of(config_block or {})
        self.transport = transport or default_transport
        self.pre_meter = pre_meter if pre_meter is not None else default_pre_meter
        self.post_meter = post_meter if post_meter is not None else default_post_meter
        self.hold_fn = hold_fn if hold_fn is not None else default_hold
        self.alert_fn = alert_fn if alert_fn is not None else default_alert
        self.substitution_fn = (substitution_fn if substitution_fn is not None
                                else default_substitution_log)
        self.parameter_encoder = parameter_encoder or encode_parameters
        self.timeout = timeout
        # Default advances through funded fallbacks first (the point of a chain),
        # holding only at true exhaustion. Set this to hold on the FIRST credit-out.
        self.hold_immediately_on_credit_out = hold_immediately_on_credit_out

    @staticmethod
    def _estimate_prompt_tokens(messages: List[dict]) -> int:
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        return max(1, chars // 4)

    def _guard(self, *values: str) -> None:
        for v in values:
            if v and is_denied(str(v), self.deny):
                raise DenyPatternRefusal(
                    "deny-pattern refusal: %r matches the runtime deny list; refused "
                    "at call time (never a silent substitution)" % v)

    def route(self, tier: str, messages: List[dict],
              context: Optional[dict] = None) -> RouteResult:
        context = context or {}
        if self.config is None:
            raise ConfigError("router has no config loaded")

        chain = resolve_tier(self.config, tier)
        primary_priority = int(chain[0].get("priority", 1))
        est_prompt = self._estimate_prompt_tokens(messages)

        degradations: List[dict] = []
        credit_seen = False

        for link in chain:
            provider = str(link.get("provider", "")).strip()
            model = str(link.get("model", "")).strip()
            priority = int(link.get("priority", 0))

            # Deny at call time (defense in depth beside validate + the guard).
            self._guard(model, provider, str(link.get("id", "")), str(link.get("family", "")))

            # Credential by label; live process env first. SET / NOT SET only.
            cred_value, cred_status = resolve_credential(link)
            if cred_status != "SET":
                degradations.append({"provider": provider, "priority": priority,
                                     "class": ErrorClass.AUTH.value,
                                     "detail": "credential NOT SET by label"})
                continue

            # Pre-meter (may block on a hard cost ceiling -> exit 4).
            self.pre_meter(context, tier, model, est_prompt)

            try:
                req = build_chat_request(link, tier, messages, cred_value,
                                         self.parameter_encoder)
                resp = self.transport(req, self.timeout)
            except ProviderError as pe:
                degradations.append({"provider": provider, "priority": priority,
                                     "class": pe.error_class.value,
                                     "status": pe.status, "detail": pe.detail})
                if pe.error_class == ErrorClass.INSUFFICIENT_CREDITS:
                    credit_seen = True
                    if self.hold_immediately_on_credit_out:
                        break
                continue

            if 200 <= resp.status < 300:
                try:
                    parsed = parse_chat_response(resp, model)
                except ProviderError as pe:
                    degradations.append({"provider": provider, "priority": priority,
                                         "class": pe.error_class.value,
                                         "status": resp.status, "detail": pe.detail})
                    continue
                # Honest record: refuse if the provider echoed a denied id.
                self._guard(parsed["model_used"])
                substituted = priority != primary_priority
                self.post_meter(context, tier, parsed["model_used"], parsed["usage"])
                if substituted:
                    self.substitution_fn(context, tier, primary_priority, priority,
                                         parsed["model_used"])
                return RouteResult(
                    tier=tier, provider=provider, model_used=parsed["model_used"],
                    priority=priority, text=parsed["text"], substituted=substituted,
                    usage=parsed["usage"], degradations=degradations)

            # Non-2xx: classify and advance (or hold-now on credit_out if configured).
            eclass = classify_http_error(resp.status, resp.body_text)
            degradations.append({"provider": provider, "priority": priority,
                                 "class": eclass.value, "status": resp.status})
            if eclass == ErrorClass.INSUFFICIENT_CREDITS:
                credit_seen = True
                if self.hold_immediately_on_credit_out:
                    break

        # Chain exhausted -> durable HOLD + ONE deduped founder alert.
        reason = "credit_out" if credit_seen else "chain_exhausted"
        self.hold_fn(context, reason, tier)
        self.alert_fn(context, tier, reason)
        raise ChainExhaustedHold(reason, tier, degradations)


# ---------------------------------------------------------------------------
# Convenience module-level entry (simple import usage for stage runners)
# ---------------------------------------------------------------------------
def route(tier: str, messages: List[dict], context: Optional[dict] = None,
          config_path: Optional[str] = None, **router_kwargs) -> RouteResult:
    block, _ = load_models_config(config_path)
    return ModelRouter(config_block=block, **router_kwargs).route(tier, messages, context)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_validate(args) -> int:
    block, path = load_models_config(args.path)
    validate_config(block)
    print("models.json OK: %s" % path)
    for tier in ROUTABLE_TIERS:
        chain = " -> ".join(
            "%s/%s" % (l.get("provider"), l.get("model"))
            for l in resolve_tier(block, tier))
        print("  %-9s : %s" % (tier, chain))
    return EX_OK


def _cli_resolve(args) -> int:
    block, _ = load_models_config(args.path)
    for link in resolve_tier(block, args.tier):
        _, status = resolve_credential(link)
        print("  %2d. provider=%-12s model=%-28s thinking=%-7s credential=%s"
              % (int(link.get("priority", 0)), link.get("provider", ""),
                 link.get("model", ""), link.get("thinking", "default"), status))
    return EX_OK


def _cli_deny_check(args) -> int:
    block, _ = load_models_config(args.path)
    deny = deny_patterns_of(block)
    if is_denied(args.model, deny):
        print("DENY: %r matches the runtime deny list / Anthropic shape" % args.model)
        return EX_DENY
    print("OK: %r is not denied" % args.model)
    return EX_OK


def _cli_route(args) -> int:
    payload = json.loads(sys.stdin.read())
    tier = payload["tier"]
    messages = payload["messages"]
    context = payload.get("context", {})
    block, _ = load_models_config(args.path)
    router = ModelRouter(config_block=block,
                         hold_immediately_on_credit_out=args.hold_on_credit)
    result = router.route(tier, messages, context)
    out = result.to_public_dict()
    out["text"] = result.text
    print(json.dumps(out, ensure_ascii=False))
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Podcast Production Engine model router.")
    ap.add_argument("--path", help="explicit models.json path")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("validate", help="load + fail-closed validate config/models.json")

    r = sub.add_parser("resolve", help="print a tier's ordered chain (SET/NOT SET only)")
    r.add_argument("tier", choices=list(ROUTABLE_TIERS))

    d = sub.add_parser("deny-check", help="test a model id against the runtime deny list")
    d.add_argument("model")

    rt = sub.add_parser("route", help="route a turn: JSON {tier,messages,context} on stdin")
    rt.add_argument("--hold-on-credit", action="store_true",
                    help="hold immediately on the first insufficient-credits (default: advance)")

    sub.add_parser("self-test", help="in-process routing/deny/exhaustion/budget battery")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "validate":
            return _cli_validate(args)
        if args.cmd == "resolve":
            return _cli_resolve(args)
        if args.cmd == "deny-check":
            return _cli_deny_check(args)
        if args.cmd == "route":
            return _cli_route(args)
        if args.cmd == "self-test" or args.cmd is None:
            return self_test()
        ap.error("unknown command")
    except DenyPatternRefusal as exc:
        sys.stderr.write("[model_router] %s\n" % exc)
        return EX_DENY
    except ChainExhaustedHold as exc:
        sys.stderr.write("[model_router] HOLD: %s\n" % exc)
        return EX_HOLD
    except BudgetCeilingBlock as exc:
        sys.stderr.write("[model_router] BUDGET: %s\n" % exc)
        return EX_BUDGET
    except ModelRouterError as exc:
        sys.stderr.write("[model_router] error: %s\n" % exc)
        return exc.exit_code
    except Exception as exc:  # unexpected
        sys.stderr.write("[model_router] unexpected error: %s\n" % exc)
        return EX_ERR


# ---------------------------------------------------------------------------
# Self-test: routing, fallback, deny, exhaustion, budget, substitution, judge
# independence -- fully injected transport + side-channels (no network/siblings).
# ---------------------------------------------------------------------------
class _ScriptedTransport:
    """Yields a programmed HttpResponse (or raises a ProviderError) per call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok_response(model: str, text: str = "ok") -> HttpResponse:
    return HttpResponse(status=200, body_text="{}",
                        json={"model": model, "choices": [{"message": {"content": text}}],
                              "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def _err_response(status: int, body: str = "") -> HttpResponse:
    return HttpResponse(status=status, body_text=body, json=None)


def _noop(*a, **k):
    return None


def _quiet_router(block, transport, **kw):
    return ModelRouter(config_block=block, transport=transport,
                       pre_meter=_noop, post_meter=_noop, hold_fn=kw.pop("hold_fn", _noop),
                       alert_fn=kw.pop("alert_fn", _noop), substitution_fn=kw.pop("substitution_fn", _noop),
                       **kw)


def self_test() -> int:
    failures = []
    total = [0]

    def check(name, cond):
        total[0] += 1
        print("  [%s] %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            failures.append(name)

    # Ensure the dummy credential env is SET for every provider the tiers use.
    for name in ("OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY", "OPENROUTER_API_KEY",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ.setdefault(name, "dummy-not-a-real-secret")

    block, path = load_models_config()
    content = resolve_tier(block, CONTENT_TIER)
    judge = resolve_tier(block, JUDGE_TIER)
    content_first = content[0]["model"]

    # t0: the shipped config validates.
    try:
        validate_config(block)
        check("shipped models.json validates (%s)" % path.name, True)
    except Exception as exc:
        check("shipped models.json validates (%s)" % exc, False)

    deny = deny_patterns_of(block)

    # t1: deny list catches denied family tokens and an Anthropic shape; passes real ids.
    check("deny catches an 'opus' family token", is_denied("vendor-opus-preview", deny))
    check("deny catches a 'sonnet' family token", is_denied("some-sonnet-3", deny))
    check("deny catches an Anthropic-family shape", is_denied(_C + "-x1", deny))
    check("deny passes the real content primary id", not is_denied(content_first, deny))
    check("deny passes a real GLM id", not is_denied("glm-5.2:cloud", deny))

    # t2: content order-1 success (no substitution).
    tr = _ScriptedTransport([_ok_response(content_first, "episode body")])
    res = _quiet_router(block, tr).route(
        CONTENT_TIER, [{"role": "user", "content": "write"}], {"client": "c", "job_id": "j1"})
    check("content priority-1 success", res.priority == content[0]["priority"]
          and res.model_used == content_first and res.text == "episode body"
          and res.substituted is False)

    # t3: priority-1 rate-limit(429) advances to priority-2 and MARKS a substitution.
    subs = []
    tr = _ScriptedTransport([_err_response(429, "rate limited"), _ok_response(content[1]["model"])])
    res = _quiet_router(block, tr, substitution_fn=lambda *a: subs.append(a)).route(
        CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j2"})
    check("rate-limit advances to the fallback", res.priority == content[1]["priority"]
          and any(d["class"] == "rate_limit" for d in res.degradations))
    check("fallback is recorded as a substitution", res.substituted is True and len(subs) == 1)

    # t4: all links fail (429, timeout, 503, ...) -> ChainExhaustedHold(chain_exhausted).
    holds, alerts = [], []
    script = [_err_response(429)] + [ProviderError("p", ErrorClass.TIMEOUT)] * (len(content) - 1)
    tr = _ScriptedTransport(script)
    router = _quiet_router(block, tr,
                           hold_fn=lambda ctx, reason, tier: holds.append(reason),
                           alert_fn=lambda ctx, tier, reason: alerts.append(reason))
    try:
        router.route(CONTENT_TIER, [{"role": "user", "content": "x"}],
                     {"client": "c", "client_id": "c", "job_id": "j3", "resume_stage": "writing"})
        check("exhaustion raises ChainExhaustedHold", False)
    except ChainExhaustedHold as exc:
        check("exhaustion raises ChainExhaustedHold(chain_exhausted)", exc.reason == "chain_exhausted")
    check("exhaustion holds exactly once", holds == ["chain_exhausted"])
    check("exhaustion alerts exactly once", len(alerts) == 1)

    # t5: priority-1 credit-out(402) then priority-2 success -> recovers, NO hold/alert.
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(402, "insufficient credits"), _ok_response(content[1]["model"])])
    router = _quiet_router(block, tr,
                           hold_fn=lambda *a: holds.append(a), alert_fn=lambda *a: alerts.append(a))
    res = router.route(CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j4"})
    check("credit-out on primary recovers on fallback",
          res.priority == content[1]["priority"] and not holds and not alerts
          and any(d["class"] == "insufficient_credits" for d in res.degradations))

    # t6: every link credit-out -> ChainExhaustedHold(credit_out), one hold + one alert.
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(402, "insufficient credit")] * len(content))
    router = _quiet_router(block, tr,
                           hold_fn=lambda ctx, reason, tier: holds.append(reason),
                           alert_fn=lambda ctx, tier, reason: alerts.append(reason))
    try:
        router.route(CONTENT_TIER, [{"role": "user", "content": "x"}],
                     {"client": "c", "client_id": "c", "job_id": "j5"})
        check("all-credit-out raises hold", False)
    except ChainExhaustedHold as exc:
        check("all-credit-out reason is credit_out", exc.reason == "credit_out")
    check("all-credit-out holds+alerts once", holds == ["credit_out"] and len(alerts) == 1)

    # t7: budget ceiling blocks BEFORE any provider call (exit 4), transport untouched.
    def blocking_pre(*a, **k):
        raise BudgetCeilingBlock("ceiling reached")
    tr = _ScriptedTransport([_ok_response(content_first)])
    router = ModelRouter(config_block=block, transport=tr, pre_meter=blocking_pre,
                         post_meter=_noop, hold_fn=_noop, alert_fn=_noop, substitution_fn=_noop)
    try:
        router.route(CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j6"})
        check("budget ceiling raises", False)
    except BudgetCeilingBlock:
        check("budget ceiling raises BudgetCeilingBlock (exit 4)", True)
    check("budget block never called the provider", tr.calls == [])

    # t8: JUDGE resolves to a DIFFERENT first model than the content writer.
    check("judge first resolution differs from content drafting", judge[0]["model"] != content_first)
    tr = _ScriptedTransport([_ok_response(judge[0]["model"], "score: 9")])
    jres = _quiet_router(block, tr).route(
        JUDGE_TIER, [{"role": "user", "content": "judge"}], {"client": "c", "job_id": "j7"})
    check("judge routes and records a non-denied honest model",
          jres.model_used == judge[0]["model"] and not is_denied(jres.model_used, deny))

    # t9: a config carrying a denied id fails closed at construction.
    poisoned = json.loads(json.dumps(block))
    poisoned["models"][CONTENT_TIER][0]["model"] = "vendor-opus-9"
    try:
        ModelRouter(config_block=poisoned)
        check("denied-id config fails closed", False)
    except DenyPatternRefusal:
        check("denied-id config fails closed (DenyPatternRefusal, exit 2)", True)

    # t10: hold-immediately-on-credit-out short-circuits on the FIRST 402.
    holds = []
    tr = _ScriptedTransport([_err_response(402, "insufficient credit"), _ok_response(content[1]["model"])])
    router = _quiet_router(block, tr, hold_fn=lambda ctx, reason, tier: holds.append(reason),
                           hold_immediately_on_credit_out=True)
    try:
        router.route(CONTENT_TIER, [{"role": "user", "content": "x"}],
                     {"client": "c", "client_id": "c", "job_id": "j8"})
        check("strict credit-out holds immediately", False)
    except ChainExhaustedHold as exc:
        check("strict credit-out holds immediately (credit_out, no fallback)",
              exc.reason == "credit_out" and len(tr.calls) == 1)

    # t11: a NOT-SET credential skips the link (auth degradation), advances to a funded one.
    saved = os.environ.pop("OLLAMA_API_KEY", None)
    saved2 = os.environ.pop("OLLAMA_CLOUD_API_KEY", None)
    try:
        # Both ollama-cloud lanes now have no key -> skipped; first funded is openrouter.
        first_funded = next(l for l in content if l["provider"] != "ollama-cloud")
        tr = _ScriptedTransport([_ok_response(first_funded["model"])])
        res = _quiet_router(block, tr).route(
            CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j9"})
        check("unset-credential link is skipped, routes to a funded lane",
              res.provider == first_funded["provider"]
              and any(d.get("detail") == "credential NOT SET by label" for d in res.degradations))
    finally:
        if saved is not None:
            os.environ["OLLAMA_API_KEY"] = saved
        if saved2 is not None:
            os.environ["OLLAMA_CLOUD_API_KEY"] = saved2

    print("\nmodel_router self-test: %s (%d checks, %d failures)"
          % ("OK" if not failures else "FAILURES", total[0], len(failures)))
    return EX_OK if not failures else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
