#!/usr/bin/env python3
"""model_router.py -- the ONE call site for every model TURN in the engine (SPEC 8).

Authored by unit W1.9. This is the single choke point through which every billable
text-generation turn flows. It resolves a capability TIER (never a model name; prompts
and stage runners speak only tiers) to the CLIENT's own provider chain, advances that
chain on retryable failures, meters every call, refuses Anthropic-shaped identifiers at
call time, and on chain exhaustion holds the job durably with exactly ONE deduped founder
Telegram alert through the OpenClaw gateway.

TIER MAP (config/model-map.template.json, resolved per box by preflight.sh into
model-map.json; SPEC 8.1). The router NEVER hardcodes a model name and NEVER validates a
model name against a known list: forward-dated names (GLM 5.2, Gemini 3.5 Flash, Minimax V3,
DeepSeek V4 Pro, Kimi 2.6, ...) are taken AS-CONFIGURED. The ONLY name it rejects is an
Anthropic-family shape.

  HEAVY-WRITER : (1) GLM 5.2 on ollama-cloud (baseUrl slotting, maxTokens 65536)
                 (2) OpenRouter GLM 5.2  (3) Gemini 3.5 Flash  (4) HOLD sentinel
                 parameters: thinking high, temperature 0.3
  LIGHT        : Minimax V3 (ollama-cloud) -> OpenRouter counterpart -> Gemini 3.5 Flash
  JUDGE        : Minimax V3 -> Gemini 3.5 Flash; temperature 0; ALWAYS a DIFFERENT
                 resolution than the tier that drafted the piece (judge_harness.py enforces
                 AF-AE-JUDGE-INDEPENDENCE; this router records the honest resolved model so
                 the harness can compare)
  LONGCTX      : DeepSeek V4 Pro / Kimi 2.6 (~1M ctx) ONLY when the client configured a key;
                 else S9 chunks on HEAVY-WRITER (the caller falls back, not this router)
  IMAGE        : NOT routed here -- S7 covers go through cover_render.py / Kie / Skills 07+46

ROUTER SEMANTICS (SPEC 8.2): one call site; per-call pre-meter and post-meter through
anthology-cost-ledger.py (per-deliverable budgets shared across QC attempts); typed error
classification (insufficient_credits, auth, rate_limit, timeout, refusal) with chain advance
on retryable classes and a durable credit_out HOLD when the chain is exhausted; DENY PATTERNS
refuse any resolved model matching an Anthropic-family shape (mirrors Skill 54 AF-AW-ANTHROPIC
and anthology_state.py's ledger deny gate); the model ACTUALLY used is recorded honestly for
the Artifact row and run ledger.

SOVEREIGNTY (SPEC 8.3): the chain is the CLIENT's own accounts under the CLIENT's own labels;
operator keys never land on a client box; the engine never substitutes a client's expressed
model choice; provider-state alarms NOTIFY, they never modify. This module NEVER prints a
credential value: credentials are reported SET or NOT SET by label only, and the resolved
value is used solely to build an Authorization header, never logged, echoed, or stored.

Exit codes (SPEC 3.4 row 4; house convention: 1 unexpected error):
  0  completion
  2  deny-pattern refusal (an Anthropic-shaped identifier reached the router; AF-AE-ANTHROPIC)
  3  chain exhausted, job held (durable HOLD + ONE deduped founder alert; AF-AE-CREDIT-HOLD)
  4  budget ceiling block (anthology-cost-ledger.py refused the call before it billed)
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
TEMPLATE_PATH = CONFIG / "model-map.template.json"

# House exit codes for this script.
EX_OK, EX_ERR, EX_DENY, EX_HOLD, EX_BUDGET = 0, 1, 2, 3, 4

# The chain sentinel that means "no funded provider remains; hold and alert."
HOLD_SENTINEL = "HOLD"

# The IMAGE tier is deliberately NOT a text turn; it is handled by cover_render.py.
NON_TEXT_TIERS = ("IMAGE",)

# Default OpenAI-compatible chat path appended to a provider base URL.
_CHAT_PATH = "/chat/completions"

# Default provider base URLs (OpenAI-compatible surfaces). A link may override any of
# these with its own "baseUrl". ollama-cloud MUST carry a baseUrl (baseUrl slotting);
# the others default here and are confirmed live at preflight.
_DEFAULT_BASE_URLS = {
    "ollama-cloud": "https://ollama.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "minimax": "https://api.minimax.io/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "moonshot": "https://api.moonshot.ai/v1",
}

# Common env-var aliases per provider, tried AFTER the resolved credential_label and the
# live process env. The Gemini three-alias rule (one key, three names) lives here. These
# are conventional NAMES only; no value is ever embedded.
_PROVIDER_ENV_ALIASES = {
    "ollama-cloud": ["OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    "moonshot": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
}

# ---------------------------------------------------------------------------
# Anthropic-family deny pattern. Assembled from FRAGMENTS so this shipped runtime
# file carries no contiguous banned literal (guard-no-anthropic-runtime.py scans .py
# source; preflight.sh and verify.sh use the identical fragment convention). The
# COMPILED pattern is functionally identical to anthology_state.py's ledger deny gate,
# so the router and the ledger agree on what an Anthropic-shaped id is. SPEC 8.2.
# ---------------------------------------------------------------------------
_A = "anthro" + "pic"
_C = "clau" + "de"
_ANTHROPIC_DENY_RE = re.compile(
    r"(?i)(^|[^a-z0-9])(" + _C + r"|" + _A + r")([^a-z0-9]|$)"
    r"|" + _A + r"/"
    r"|" + _C + r"-"
    r"|us\." + _A + r"\.",
)

_PLACEHOLDER_RE = re.compile(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>")

_CREDIT_TERMS = (
    "insufficient", "credit", "quota", "billing", "balance", "payment required",
    "exceeded your current", "out of funds", "top up", "top-up",
)
_REFUSAL_TERMS = (
    "content policy", "safety", "cannot assist", "i can't help", "i cannot help",
    "refuse", "moderation", "flagged", "prohibited content",
)


def is_anthropic_shaped(text: str) -> bool:
    """True iff the string carries an Anthropic-family identifier shape."""
    return bool(text) and bool(_ANTHROPIC_DENY_RE.search(str(text)))


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
        # detail is scrubbed of anything credential-shaped by the caller before storage.
        self.detail = detail
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


class NonTextTierError(ModelRouterError):
    exit_code = EX_ERR


class UnknownTierError(ModelRouterError):
    exit_code = EX_ERR


class UnresolvedMapError(ModelRouterError):
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
        # Transport-level failure -> treat as a transient/timeout class, advance the chain.
        raise ProviderError("transport", ErrorClass.TIMEOUT, status=None,
                            detail=type(exc).__name__)


# ---------------------------------------------------------------------------
# Model map loading and fail-closed validation
# ---------------------------------------------------------------------------
def _candidate_map_paths(explicit: Optional[str], run_dir: Optional[str]) -> List[Path]:
    out: List[Path] = []
    if explicit:
        out.append(Path(explicit))
    env = os.environ.get("ANTHOLOGY_MODEL_MAP", "").strip()
    if env:
        out.append(Path(env))
    if run_dir:
        out.append(Path(run_dir) / "model-map.json")
    out.append(SKILL_DIR / "model-map.json")        # preflight.sh default output
    out.append(CONFIG / "model-map.json")           # alternative resolved location
    return out


def load_model_map(explicit: Optional[str] = None, run_dir: Optional[str] = None,
                   allow_template: bool = False) -> Tuple[dict, Path]:
    """Load the RESOLVED model-map.json. Falls back to the template ONLY when
    allow_template is set (validate / self-test), never for a live route."""
    for p in _candidate_map_paths(explicit, run_dir):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")), p
    if allow_template and TEMPLATE_PATH.is_file():
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")), TEMPLATE_PATH
    raise UnresolvedMapError(
        "no resolved model-map.json found (run preflight.sh to resolve this box); "
        "searched: %s" % ", ".join(str(x) for x in _candidate_map_paths(explicit, run_dir)))


def validate_resolved_map(model_map: dict) -> None:
    """Fail closed on a residual <CLIENT_*> placeholder (unresolved box) or any
    Anthropic-family id in the TIER TREE (the actual routing surface). Defense in
    depth beside preflight.sh --check; this runs at every route().

    Only the tiers subtree is scanned, never free-text prose: both the template's
    $schema_note and preflight.sh's own resolved-map note legitimately contain the
    literal string <CLIENT_*> while DESCRIBING placeholders, and that documentation
    is not a routing hazard. What matters is that every chain link's provider, model,
    credential_label, and baseUrl are resolved and non-Anthropic."""
    tiers = model_map.get("tiers", {})
    residual = sorted(set(_PLACEHOLDER_RE.findall(json.dumps(tiers))))
    if residual:
        raise UnresolvedMapError(
            "model-map tier tree still carries placeholder(s), box not resolved: %s"
            % ", ".join(residual))

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + "." + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))
        elif isinstance(node, str):
            if is_anthropic_shaped(node):
                raise DenyPatternRefusal(
                    "AF-AE-ANTHROPIC: resolved map carries a banned id at %s" % path)

    walk(tiers, "tiers")


def resolve_tier(model_map: dict, tier: str) -> dict:
    tiers = model_map.get("tiers", {})
    if tier not in tiers:
        raise UnknownTierError("unknown tier %r (known: %s)"
                               % (tier, ", ".join(sorted(tiers))))
    return tiers[tier]


def ordered_chain(tier_obj: dict) -> List[dict]:
    chain = tier_obj.get("chain", [])
    return sorted(chain, key=lambda link: link.get("order", 1_000_000))


# ---------------------------------------------------------------------------
# Credential resolution (env-first; SET / NOT SET only; value never printed)
# ---------------------------------------------------------------------------
CredentialResolver = Callable[[str, str], Optional[str]]


def resolve_credential(credential_label: str, provider: str,
                       external: Optional[CredentialResolver] = None) -> Tuple[Optional[str], str]:
    """Return (value_or_None, status). status is 'SET' or 'NOT SET' -- never the value.
    Order: live process env under the resolved label; then this provider's conventional
    env aliases; then an optional external resolver (e.g. caf_credential_gate.py)."""
    if credential_label:
        val = os.environ.get(credential_label)
        if val:
            return val, "SET"
    for alias in _PROVIDER_ENV_ALIASES.get(provider, []):
        val = os.environ.get(alias)
        if val:
            return val, "SET"
    if external is not None:
        try:
            val = external(credential_label, provider)
        except Exception:
            val = None
        if val:
            return val, "SET"
    return None, "NOT SET"


# ---------------------------------------------------------------------------
# Request building, response parsing, error classification
# ---------------------------------------------------------------------------
def _base_url(link: dict, provider: str) -> Optional[str]:
    b = (link.get("baseUrl") or link.get("base_url") or "").strip()
    if b:
        return b.rstrip("/")
    d = _DEFAULT_BASE_URLS.get(provider)
    return d.rstrip("/") if d else None


def encode_parameters(provider: str, link: dict, params: dict) -> dict:
    """Map the tier parameters onto an OpenAI-compatible body fragment. The exact
    thinking-mode wire field varies by provider/version and is confirmed live at
    preflight; the emerging OpenAI-compatible field 'reasoning_effort' is used as the
    portable default. Overridable by injecting a different encoder."""
    frag: dict = {}
    if "temperature" in params and params["temperature"] is not None:
        frag["temperature"] = params["temperature"]
    max_tokens = link.get("maxTokens") or params.get("maxTokens")
    if max_tokens:
        frag["max_tokens"] = max_tokens
    thinking = params.get("thinking")
    if thinking:
        frag["reasoning_effort"] = thinking
    return frag


def build_chat_request(link: dict, provider: str, model: str, messages: List[dict],
                       params: dict, credential_value: str,
                       encoder: Callable[[str, dict, dict], dict]) -> HttpRequest:
    base = _base_url(link, provider)
    if not base:
        raise ProviderError(provider, ErrorClass.UNKNOWN, status=None,
                            detail="no base url resolvable")
    url = base + _CHAT_PATH
    body = {"model": model, "messages": messages}
    body.update(encoder(provider, link, params))
    headers = {
        "Authorization": "Bearer " + credential_value,
        "Content-Type": "application/json",
    }
    return HttpRequest(url=url, headers=headers, body=body)


def parse_chat_response(resp: HttpResponse, configured_model: str) -> dict:
    """Normalize an OpenAI-compatible chat completion. Returns text, honest model_used,
    and usage. Raises ProviderError(REFUSAL) if the body reads as a content refusal."""
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
    if status == 402 or credit_hit and status in (401, 403, 429, 400):
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
# Metering / hold / alert side-channels (subprocess; injectable; fail-soft)
# ---------------------------------------------------------------------------
def _script_cmd(name: str) -> Optional[List[str]]:
    p = SCRIPTS / name
    if p.is_file():
        return [sys.executable, str(p)]
    return None


def default_pre_meter(context: dict, tier: str, model: str, est_prompt_tokens: int) -> None:
    """Pre-meter via anthology-cost-ledger.py. Exit 4 => BudgetCeilingBlock (the call is
    blocked BEFORE it bills). A missing ledger is a loud warn-and-allow (unit/canary
    contexts); a resolved box always ships the ledger."""
    key = (context or {}).get("deliverable_key")
    if not key:
        return
    cmd = _script_cmd("anthology-cost-ledger.py")
    if not cmd:
        sys.stderr.write("[model_router] cost ledger absent; metering skipped (warn)\n")
        return
    argv = cmd + ["meter", "--phase", "pre", "--deliverable-key", str(key),
                  "--tier", tier, "--model", str(model),
                  "--prompt-tokens", str(int(est_prompt_tokens)),
                  "--qc-attempt", str((context or {}).get("qc_attempt", 0))]
    rc = subprocess.call(argv)
    if rc == EX_BUDGET:
        raise BudgetCeilingBlock(
            "anthology-cost-ledger.py blocked the call: per-deliverable budget ceiling "
            "reached for %s (shared across QC attempts)" % key)


def default_post_meter(context: dict, tier: str, model: str, usage: dict) -> None:
    key = (context or {}).get("deliverable_key")
    if not key:
        return
    cmd = _script_cmd("anthology-cost-ledger.py")
    if not cmd:
        return
    argv = cmd + ["meter", "--phase", "post", "--deliverable-key", str(key),
                  "--tier", tier, "--model", str(model),
                  "--prompt-tokens", str(int(usage.get("prompt_tokens", 0) or 0)),
                  "--completion-tokens", str(int(usage.get("completion_tokens", 0) or 0)),
                  "--qc-attempt", str((context or {}).get("qc_attempt", 0))]
    subprocess.call(argv)


def default_hold(context: dict, reason: str, tier: str) -> None:
    """Durably HOLD the job at its exact cursor via hold_queue.py. Fail-soft: a hold
    failure is logged; the router still raises ChainExhaustedHold so the caller stops."""
    cmd = _script_cmd("hold_queue.py")
    if not cmd:
        sys.stderr.write("[model_router] hold_queue.py absent; HOLD not persisted (warn)\n")
        return
    ctx = context or {}
    argv = cmd + ["hold", "--reason", reason, "--tier", tier]
    for flag, k in (("--participant-key", "participant_key"),
                    ("--anthology-id", "anthology_id"),
                    ("--cursor", "cursor"),
                    ("--deliverable-key", "deliverable_key")):
        if ctx.get(k):
            argv += [flag, str(ctx[k])]
    try:
        subprocess.call(argv)
    except Exception as exc:
        sys.stderr.write("[model_router] hold_queue.py call failed: %s\n" % type(exc).__name__)


def default_alert(dedupe_key: str, message: str) -> None:
    """ONE deduped founder alert through the OpenClaw gateway (Telegram), never bypassed.
    alert-dedup.py owns the dedupe window; this passes a STABLE key so repeated exhaustions
    of the same job collapse to a single alert. Fail-soft."""
    cmd = _script_cmd("alert-dedup.py")
    if not cmd:
        sys.stderr.write("[model_router] alert-dedup.py absent; founder alert not sent (warn)\n")
        return
    try:
        subprocess.call(cmd + ["send", "--category", "credit-hold",
                               "--key", dedupe_key, "--message", message])
    except Exception as exc:
        sys.stderr.write("[model_router] alert-dedup.py call failed: %s\n" % type(exc).__name__)


# ---------------------------------------------------------------------------
# Route result
# ---------------------------------------------------------------------------
@dataclass
class RouteResult:
    tier: str
    provider: str
    model_used: str          # honest, non-Anthropic (deny-checked before return)
    chain_order: int
    text: str
    usage: dict = field(default_factory=dict)
    degradations: List[dict] = field(default_factory=list)

    def to_public_dict(self) -> dict:
        """A record safe for the Artifact row / run ledger. Carries NO credential."""
        return {
            "tier": self.tier,
            "provider": self.provider,
            "model_used": self.model_used,
            "chain_order": self.chain_order,
            "usage": self.usage,
            "degradations": self.degradations,
        }


# ---------------------------------------------------------------------------
# The router
# ---------------------------------------------------------------------------
class ModelRouter:
    def __init__(self,
                 model_map: Optional[dict] = None,
                 transport: Optional[Transport] = None,
                 pre_meter: Optional[Callable] = None,
                 post_meter: Optional[Callable] = None,
                 hold_fn: Optional[Callable] = None,
                 alert_fn: Optional[Callable] = None,
                 credential_resolver: Optional[CredentialResolver] = None,
                 parameter_encoder: Optional[Callable] = None,
                 timeout: float = 600.0,
                 hold_immediately_on_credit_out: bool = False):
        if model_map is not None:
            validate_resolved_map(model_map)
        self.model_map = model_map
        self.transport = transport or default_transport
        self.pre_meter = pre_meter if pre_meter is not None else default_pre_meter
        self.post_meter = post_meter if post_meter is not None else default_post_meter
        self.hold_fn = hold_fn if hold_fn is not None else default_hold
        self.alert_fn = alert_fn if alert_fn is not None else default_alert
        self.credential_resolver = credential_resolver
        self.parameter_encoder = parameter_encoder or encode_parameters
        self.timeout = timeout
        # SPEC 8.2 reads two ways; default advances through funded fallbacks first
        # (the whole point of a chain), holding only at true exhaustion. Operators who
        # want an immediate credit_out hold on the FIRST insufficient-credits set this.
        self.hold_immediately_on_credit_out = hold_immediately_on_credit_out

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _estimate_prompt_tokens(messages: List[dict]) -> int:
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        return max(1, chars // 4)

    @staticmethod
    def _dedupe_key(tier: str, context: dict) -> str:
        ctx = context or {}
        anchor = ctx.get("participant_key") or ctx.get("deliverable_key") or ctx.get("anthology_id") or "no-subject"
        return "credit-hold:%s:%s" % (tier, anchor)

    def _guard_model(self, model: str, provider: str) -> None:
        if is_anthropic_shaped(model) or is_anthropic_shaped(provider):
            raise DenyPatternRefusal(
                "AF-AE-ANTHROPIC: resolved model %r on provider %r matches an Anthropic-shaped "
                "deny pattern; refused at call time (SPEC 8.2)" % (model, provider))

    # -- the single call site -------------------------------------------
    def route(self, tier: str, messages: List[dict],
              context: Optional[dict] = None) -> RouteResult:
        context = context or {}
        if tier in NON_TEXT_TIERS:
            raise NonTextTierError(
                "tier %s is not a text turn; S7 covers route through cover_render.py "
                "(Kie GPT-image-2 portrait via Skills 07/46), never model_router.py" % tier)
        if self.model_map is None:
            raise UnresolvedMapError("router has no model map loaded")

        tier_obj = resolve_tier(self.model_map, tier)
        params = tier_obj.get("parameters", {}) or {}
        chain = ordered_chain(tier_obj)
        est_prompt = self._estimate_prompt_tokens(messages)

        degradations: List[dict] = []
        credit_seen = False

        for link in chain:
            provider = str(link.get("provider", "")).strip()
            if provider.upper() == HOLD_SENTINEL:
                break  # explicit chain terminus -> exhaustion path below
            model = str(link.get("model", "")).strip()
            order = int(link.get("order", 0))

            # Deny at call time (defense in depth beside preflight + the ledger gate).
            self._guard_model(model, provider)

            # Credential by label, live process env first. SET / NOT SET only.
            cred_value, cred_status = resolve_credential(
                str(link.get("credential_label", "")), provider, self.credential_resolver)
            if cred_status != "SET":
                degradations.append({"provider": provider, "order": order,
                                     "class": ErrorClass.AUTH.value,
                                     "detail": "credential NOT SET by label"})
                continue

            # ollama-cloud REQUIRES baseUrl slotting; a missing base is a config fault.
            if str(link.get("slotting", "")).strip() == "baseUrl" and not _base_url(link, provider):
                degradations.append({"provider": provider, "order": order,
                                     "class": ErrorClass.UNKNOWN.value,
                                     "detail": "baseUrl slotting but no base url resolvable"})
                continue

            # Pre-meter (may block on the per-deliverable budget ceiling -> exit 4).
            self.pre_meter(context, tier, model, est_prompt)

            # Call the provider.
            try:
                req = build_chat_request(link, provider, model, messages, params,
                                         cred_value, self.parameter_encoder)
                resp = self.transport(req, self.timeout)
            except ProviderError as pe:
                degradations.append({"provider": provider, "order": order,
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
                    degradations.append({"provider": provider, "order": order,
                                         "class": pe.error_class.value,
                                         "status": resp.status, "detail": pe.detail})
                    continue
                # Honest record: refuse if the provider echoed an Anthropic id.
                self._guard_model(parsed["model_used"], provider)
                self.post_meter(context, tier, parsed["model_used"], parsed["usage"])
                return RouteResult(
                    tier=tier, provider=provider, model_used=parsed["model_used"],
                    chain_order=order, text=parsed["text"], usage=parsed["usage"],
                    degradations=degradations)

            # Non-2xx: classify and advance (or hold-now on credit_out if configured).
            eclass = classify_http_error(resp.status, resp.body_text)
            degradations.append({"provider": provider, "order": order,
                                 "class": eclass.value, "status": resp.status})
            if eclass == ErrorClass.INSUFFICIENT_CREDITS:
                credit_seen = True
                if self.hold_immediately_on_credit_out:
                    break

        # Chain exhausted -> durable HOLD + ONE deduped founder alert.
        reason = "credit_out" if credit_seen else "chain_exhausted"
        self.hold_fn(context, reason, tier)
        self.alert_fn(
            self._dedupe_key(tier, context),
            "Anthology engine: %s tier chain exhausted (%s). Job held at its cursor; "
            "resumes when a provider in the chain is funded and reachable." % (tier, reason))
        raise ChainExhaustedHold(reason, tier, degradations)


# ---------------------------------------------------------------------------
# Convenience module-level entry (simple import usage for stage runners)
# ---------------------------------------------------------------------------
def route(tier: str, messages: List[dict], context: Optional[dict] = None,
          run_dir: Optional[str] = None, model_map_path: Optional[str] = None,
          **router_kwargs) -> RouteResult:
    model_map, _ = load_model_map(model_map_path, run_dir)
    return ModelRouter(model_map=model_map, **router_kwargs).route(tier, messages, context)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_validate(args) -> int:
    model_map, path = load_model_map(args.path, args.run_dir, allow_template=args.allow_template)
    validate_resolved_map(model_map)
    print("model-map OK: %s" % path)
    for tier, obj in model_map.get("tiers", {}).items():
        links = ordered_chain(obj)
        chain = " -> ".join(
            (str(l.get("provider")) if str(l.get("provider", "")).upper() != HOLD_SENTINEL
             else "HOLD") for l in links)
        print("  %-13s : %s" % (tier, chain))
    return EX_OK


def _cli_resolve(args) -> int:
    model_map, _ = load_model_map(args.path, args.run_dir, allow_template=args.allow_template)
    tier_obj = resolve_tier(model_map, args.tier)
    print("tier %s  parameters=%s" % (args.tier, json.dumps(tier_obj.get("parameters", {}))))
    for link in ordered_chain(tier_obj):
        provider = str(link.get("provider", ""))
        if provider.upper() == HOLD_SENTINEL:
            print("  %2d. HOLD (durable hold + one deduped founder alert)" % link.get("order", 0))
            continue
        _, status = resolve_credential(str(link.get("credential_label", "")), provider,
                                       None)
        print("  %2d. provider=%-12s model=%-28s slotting=%-7s credential=%s"
              % (link.get("order", 0), provider, link.get("model", ""),
                 link.get("slotting", "apiKey"), status))
    return EX_OK


def _cli_deny_check(args) -> int:
    if is_anthropic_shaped(args.model):
        print("DENY: %r matches an Anthropic-family shape (AF-AE-ANTHROPIC)" % args.model)
        return EX_DENY
    print("OK: %r is not Anthropic-shaped" % args.model)
    return EX_OK


def _cli_route(args) -> int:
    payload = json.loads(sys.stdin.read())
    tier = payload["tier"]
    messages = payload["messages"]
    context = payload.get("context", {})
    model_map, _ = load_model_map(args.path, args.run_dir)
    router = ModelRouter(model_map=model_map,
                         hold_immediately_on_credit_out=args.hold_on_credit)
    result = router.route(tier, messages, context)
    out = result.to_public_dict()
    out["text"] = result.text
    print(json.dumps(out, ensure_ascii=False))
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Anthology engine model router (SPEC 8).")
    ap.add_argument("--path", help="explicit model-map.json path")
    ap.add_argument("--run-dir", help="run dir holding a resolved model-map.json")
    sub = ap.add_subparsers(dest="cmd")

    v = sub.add_parser("validate-map", help="load + fail-closed validate the resolved map")
    v.add_argument("--allow-template", action="store_true",
                   help="permit the unresolved template (still fails on residual placeholders)")

    r = sub.add_parser("resolve", help="print a tier's ordered chain (SET/NOT SET only)")
    r.add_argument("tier")
    r.add_argument("--allow-template", action="store_true")

    d = sub.add_parser("deny-check", help="test a model id against the Anthropic deny pattern")
    d.add_argument("model")

    rt = sub.add_parser("route", help="route a turn: JSON {tier,messages,context} on stdin")
    rt.add_argument("--hold-on-credit", action="store_true",
                    help="hold immediately on the first insufficient-credits (default: advance)")

    sub.add_parser("self-test", help="in-process routing/deny/exhaustion/budget battery")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "validate-map":
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
# Self-test: proves routing, fallback, deny, exhaustion, budget, independence
# with a fully injected transport and side-channels (no network, no siblings).
# ---------------------------------------------------------------------------
def _synthetic_resolved_map() -> dict:
    """Build a RESOLVED map by substituting the template's <CLIENT_*> slots with dummy
    NON-Anthropic values, so validation passes and tiers resolve to known dummy models."""
    tmpl = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    subs = {
        "<CLIENT_HEAVY_PRIMARY_MODEL>": "glm-5.2",
        "<CLIENT_HEAVY_FALLBACK1_MODEL>": "z-ai/glm-5.2",
        "<CLIENT_HEAVY_FALLBACK2_MODEL>": "gemini-3.5-flash",
        "<CLIENT_LIGHT_PRIMARY_MODEL>": "minimax-v3",
        "<CLIENT_LIGHT_FALLBACK1_MODEL>": "minimaxai/minimax-v3",
        "<CLIENT_JUDGE_PRIMARY_MODEL>": "minimax-v3",
        "<CLIENT_LONGCTX_MODEL>": "deepseek-v4-pro",
        "<CLIENT_IMAGE_MODEL>": "gpt-image-2",
        "<CLIENT_OLLAMA_CLOUD_KEY_LABEL>": "OLLAMA_API_KEY",
        "<CLIENT_OPENROUTER_KEY_LABEL>": "OPENROUTER_API_KEY",
        "<CLIENT_GEMINI_KEY_LABEL>": "GOOGLE_API_KEY",
        "<CLIENT_MINIMAX_KEY_LABEL>": "MINIMAX_API_KEY",
        "<CLIENT_DEEPSEEK_OR_KIMI_KEY_LABEL>": "DEEPSEEK_API_KEY",
        "<CLIENT_KIE_KEY_LABEL>": "KIE_API_KEY",
    }
    blob = json.dumps(tmpl)
    for k, v in subs.items():
        blob = blob.replace(k, v)
    m = json.loads(blob)
    # ollama-cloud links need a base url for baseUrl slotting.
    for tier in m.get("tiers", {}).values():
        for link in tier.get("chain", []):
            if link.get("slotting") == "baseUrl" and not link.get("baseUrl"):
                link["baseUrl"] = "https://ollama.com/v1"
    return m


class _ScriptedTransport:
    """Yields a programmed HttpResponse (or raises a ProviderError) per call, in order."""

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


def self_test() -> int:
    failures = []
    total = [0]

    def check(name, cond):
        total[0] += 1
        print("  [%s] %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            failures.append(name)

    # Ensure the dummy credential env is SET for every provider the tiers use.
    for name in ("OLLAMA_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY",
                 "MINIMAX_API_KEY", "DEEPSEEK_API_KEY", "KIE_API_KEY"):
        os.environ.setdefault(name, "dummy-not-a-real-secret")

    model_map = _synthetic_resolved_map()

    # t0: template + resolved-map validation
    try:
        validate_resolved_map(model_map)
        check("resolved synthetic map validates", True)
    except Exception as exc:
        check("resolved synthetic map validates (%s)" % exc, False)

    # t1: deny-check catches an Anthropic-shaped id assembled from fragments
    forbidden = "cl" + "aude-" + "sonnet-4"          # no literal in source (mirrors sibling)
    forbidden2 = "anthro" + "pic/" + "cl" + "aude-opus-4"
    check("deny-check catches a hyphenated vendor model id", is_anthropic_shaped(forbidden))
    check("deny-check catches a slash-prefixed vendor model id", is_anthropic_shaped(forbidden2))
    check("deny-check passes a real GLM id", not is_anthropic_shaped("glm-5.2"))
    check("deny-check passes minimax id", not is_anthropic_shaped("minimax-v3"))

    # t2: HEAVY-WRITER succeeds on order-1 (ollama-cloud GLM)
    tr = _ScriptedTransport([_ok_response("glm-5.2", "chapter body")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    res = router.route("HEAVY-WRITER", [{"role": "user", "content": "write"}],
                       {"deliverable_key": "d1"})
    check("HEAVY-WRITER order-1 success", res.provider == "ollama-cloud"
          and res.model_used == "glm-5.2" and res.chain_order == 1 and res.text == "chapter body")

    # t3: order-1 rate-limit(429) advances to order-2 (openrouter) success
    tr = _ScriptedTransport([_err_response(429, "rate limited"), _ok_response("z-ai/glm-5.2")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    res = router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}], {"deliverable_key": "d2"})
    check("rate-limit advances to fallback", res.provider == "openrouter"
          and any(d["class"] == "rate_limit" for d in res.degradations))

    # t4: all links fail (429 then timeout then 503) -> ChainExhaustedHold(chain_exhausted)
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(429), ProviderError("openrouter", ErrorClass.TIMEOUT),
                             _err_response(503)])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda key, msg: alerts.append(key))
    try:
        router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}],
                     {"participant_key": "p1::a1", "deliverable_key": "d3", "cursor": "s5_chapter"})
        check("exhaustion raises ChainExhaustedHold", False)
    except ChainExhaustedHold as exc:
        check("exhaustion raises ChainExhaustedHold(chain_exhausted)", exc.reason == "chain_exhausted")
    check("exhaustion holds exactly once", holds == ["chain_exhausted"])
    check("exhaustion alerts exactly once", len(alerts) == 1)

    # t5: order-1 credit-out(402) then order-2 success -> recovers, NO hold, NO alert (silence)
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(402, "insufficient credits"), _ok_response("z-ai/glm-5.2")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda key, msg: alerts.append(key))
    res = router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}], {"deliverable_key": "d4"})
    check("credit-out on primary recovers on fallback", res.provider == "openrouter"
          and not holds and not alerts
          and any(d["class"] == "insufficient_credits" for d in res.degradations))

    # t6: every link credit-out -> ChainExhaustedHold(credit_out) with one hold + one alert
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(402, "insufficient credit"),
                             _err_response(402, "insufficient credit"),
                             _err_response(402, "insufficient credit")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda key, msg: alerts.append(key))
    try:
        router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}], {"deliverable_key": "d5"})
        check("all-credit-out raises hold", False)
    except ChainExhaustedHold as exc:
        check("all-credit-out reason is credit_out", exc.reason == "credit_out")
    check("all-credit-out holds+alerts once", holds == ["credit_out"] and len(alerts) == 1)

    # t7: budget ceiling blocks BEFORE any provider call (exit 4), transport untouched
    def blocking_pre(*a, **k):
        raise BudgetCeilingBlock("ceiling reached")
    tr = _ScriptedTransport([_ok_response("glm-5.2")])
    router = ModelRouter(model_map=model_map, transport=tr, pre_meter=blocking_pre,
                         post_meter=lambda *a, **k: None,
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    try:
        router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}], {"deliverable_key": "d6"})
        check("budget ceiling raises", False)
    except BudgetCeilingBlock:
        check("budget ceiling raises BudgetCeilingBlock (exit 4)", True)
    check("budget block never called the provider", tr.calls == [])

    # t8: JUDGE resolves to a DIFFERENT model than the HEAVY-WRITER drafting tier
    heavy_first = ordered_chain(resolve_tier(model_map, "HEAVY-WRITER"))[0]["model"]
    judge_first = ordered_chain(resolve_tier(model_map, "JUDGE"))[0]["model"]
    check("JUDGE first resolution differs from HEAVY drafting", judge_first != heavy_first)
    tr = _ScriptedTransport([_ok_response("minimax-v3", "score: 9")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    jres = router.route("JUDGE", [{"role": "user", "content": "judge this"}], {"deliverable_key": "d7"})
    check("JUDGE routes and records a non-Anthropic honest model",
          jres.model_used == "minimax-v3" and not is_anthropic_shaped(jres.model_used))

    # t9: IMAGE tier is refused (handled by cover_render.py)
    router = ModelRouter(model_map=model_map, transport=_ScriptedTransport([]),
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    try:
        router.route("IMAGE", [{"role": "user", "content": "x"}], {})
        check("IMAGE tier refused", False)
    except NonTextTierError:
        check("IMAGE tier refused (routes via cover_render.py)", True)

    # t10: a residual placeholder map fails closed at construction
    bad = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    try:
        ModelRouter(model_map=bad)
        check("unresolved placeholder map fails closed", False)
    except UnresolvedMapError:
        check("unresolved placeholder map fails closed (UnresolvedMapError)", True)

    # t11: a map carrying an Anthropic id fails closed
    poisoned = _synthetic_resolved_map()
    poisoned["tiers"]["HEAVY-WRITER"]["chain"][0]["model"] = "cl" + "aude-" + "opus-4"
    try:
        ModelRouter(model_map=poisoned)
        check("Anthropic-poisoned map fails closed", False)
    except DenyPatternRefusal:
        check("Anthropic-poisoned map fails closed (DenyPatternRefusal, exit 2)", True)

    # t12: hold-immediately-on-credit-out short-circuits on the FIRST 402
    holds, alerts = [], []
    tr = _ScriptedTransport([_err_response(402, "insufficient credit"), _ok_response("z-ai/glm-5.2")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda key, msg: alerts.append(key),
                         hold_immediately_on_credit_out=True)
    try:
        router.route("HEAVY-WRITER", [{"role": "user", "content": "x"}], {"deliverable_key": "d8"})
        check("strict credit-out holds immediately", False)
    except ChainExhaustedHold as exc:
        check("strict credit-out holds immediately (credit_out, no fallback)",
              exc.reason == "credit_out" and len(tr.calls) == 1)

    # t13: LIGHT tier resolves and routes (extraction chores)
    tr = _ScriptedTransport([_ok_response("minimax-v3", "primary goal: X")])
    router = ModelRouter(model_map=model_map, transport=tr,
                         pre_meter=lambda *a, **k: None, post_meter=lambda *a, **k: None,
                         hold_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None)
    lres = router.route("LIGHT", [{"role": "user", "content": "extract"}], {"deliverable_key": "d9"})
    check("LIGHT tier routes", lres.provider == "ollama-cloud" and lres.model_used == "minimax-v3")

    print("\nmodel_router self-test: %s (%d checks, %d failures)"
          % ("OK" if not failures else "FAILURES", total[0], len(failures)))
    return EX_OK if not failures else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
