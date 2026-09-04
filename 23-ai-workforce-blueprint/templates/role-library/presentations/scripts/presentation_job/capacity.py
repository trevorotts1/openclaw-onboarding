#!/usr/bin/env python3
"""capacity.py -- CLIENT capacity detection for the Presentations department.

WHAT CHANGED AND WHY (unit u07)
-------------------------------
The previous version of this module hard-coded ONE operator's setup as module
constants -- PROVIDER_CEILING = 2500 (DeepSeek v4 Flash), WORKFLOWS = 30,
SUBAGENTS_PER_WORKFLOW = 16 -- read an operator-box settings path, and was
consulted by nothing in the dispatch path. On a client box running Ollama Cloud
at $20/month it would have reported hundreds of dispatchable agents. That is not
a measurement, it is one machine's number wearing a measurement's clothes.

This module now DETECTS the client's provider and plan and returns the cap that
belongs to THAT account. It never guesses upward: an unknown provider or an
unknown plan collapses to DEFAULT_CONSERVATIVE (3), and a provider whose plan
cannot be determined PARKS the run behind a one-time interview question instead
of inventing a number.

HARDENING (fix/capacity-override-clamp)
----------------------------------------
`_resolve_override()` had an ordering-plus-trust bug: a declared
`max_concurrent` with no recognisable `plan` returned status MEASURED with the
declared value verbatim and unbounded, and that branch sat AHEAD of the
provider-known/plan-unknown PARK branch -- so a `capacity_override.json` of
`{"provider":"ollama-cloud","max_concurrent":9999}` (a known cap-table
provider whose highest row anywhere is 10) yielded MEASURED / available=9999,
never PARKED, never AF-CAPACITY-UNMEASURED. The declared number was trusted as
if it were a reading off the account, when it was only ever a claim about it.
Fixed by re-ordering `_resolve_override()`'s three cases so the PARK check for
"provider known, plan unknown" runs BEFORE the bare-declared-int fallback (a
declaration can never outrun the interview question for a cap-table provider),
and by giving a genuinely unrecognised provider's declaration its own status --
DECLARED_UNVERIFIED, bounded to DEFAULT_CONSERVATIVE -- so it is never
mistaken for a real measurement again.

THE CAP TABLE (binding) -- operator ruling fix/capacity-uncap-byok
--------------------------------------------------------------------
Do not limit someone who brought their own capacity. A bring-your-own-key
direct provider is money the client is already paying for directly; this
module is not the place to invent a ceiling on it.

    ollama-cloud    + $20/month    ->     3 concurrent agents  (structural:
    ollama-cloud    + $100/month   ->    8 concurrent agents   the account
                                          itself enforces this, not us)
    deepseek-direct + Flash         ->  2500 concurrent agents (structural)
    deepseek-direct + Pro           ->   500 concurrent agents (structural)
    openrouter                      ->  NO CAP (UNBOUNDED)
    any other declared BYOK-direct
      provider added to NO_CAP_PROVIDERS -> NO CAP (UNBOUNDED)
    unknown provider (cannot even be identified) -> 3 (DEFAULT_CONSERVATIVE)

ollama-cloud and deepseek-direct both have real, plan-dependent ceilings the
account itself enforces (ollama $20 -> 3, $100 -> 8; deepseek Flash -> 25,
Pro -> 500), so both live in CAP_TABLE and both PARK behind the one-time plan
interview when the plan is unknown. OpenRouter has no such observable
structural ceiling, so this module stops pretending one exists: `available` for those providers is the UNBOUNDED
sentinel (see below) unless the operator/client DECLARES a lower number for
this run via capacity_override.json's `max_concurrent` (self-throttling is
always honoured; inventing an upward ceiling never is). UNBOUNDED is never
a large magic integer -- see execution_plan.cap_wave_width(), which is what
actually keeps a wave's width bounded by the number of items ready to run.

DETECTION ORDER (first hit wins; every step is read-only)
---------------------------------------------------------
    a. capacity_override.json in the department config dir -- an explicitly
       declared {provider, plan, max_concurrent}.
    b. the 9Router configuration -- which provider the primary model routes to
       (~/.9router/db/data.sqlite, opened read-only; ONLY the non-secret
       `combos.name` / `combos.models` columns are read).
    c. the OpenClaw agent model configuration -- the provider namespace prefix
       on the primary model (~/.openclaw/openclaw.json, `agents.*.model.primary`).
    d. provider is on the cap table (ollama-cloud) but plan unknown -> emit the
       interview question and PARK. The answer is persisted to
       capacity_override.json so the question is asked ONCE, never every run.
       A NO_CAP_PROVIDERS hit (deepseek-direct, openrouter, ...) never reaches
       this step -- it resolves MEASURED/UNBOUNDED at step b or c regardless
       of whether a plan could be determined, because no plan of theirs
       changes the ceiling: there isn't one.
    e. nothing found -> DEFAULT_CONSERVATIVE plus a loud UNDETERMINED line.

CREDENTIAL SAFETY (binding)
---------------------------
Detection reads only WHICH provider is configured. It never reads, returns, logs
or prints a credential VALUE. Every value that leaves this module passes through
_safe_value(), which refuses any field whose key looks like a secret
(key/token/secret/password/auth/credential/cookie/bearer). The 9Router
`apiKeys` table and `providerConnections.data` blob are never queried. If a
provider cannot be determined without touching secret material, this module
returns UNDETERMINED instead.

STATUSES
--------
    MEASURED           -- either (a) provider + plan BOTH resolved against the
                          structural cap table (ollama-cloud): `available` is
                          the cap-table number, and a declared max_concurrent
                          may lower it, never raise it; or (b) the provider is
                          a NO_CAP_PROVIDERS BYOK provider (deepseek-direct,
                          openrouter, ...): `available` is UNBOUNDED, or the
                          declared max_concurrent verbatim when the
                          operator/client chose to self-throttle this run --
                          there is no table ceiling to reconcile it against.
    DECLARED_UNVERIFIED -- max_concurrent was declared for a provider that is
                          not recognised at all (not on the cap table, not a
                          NO_CAP_PROVIDERS entry -- normalize_provider()
                          returned None). A declaration about an unidentified
                          provider is not a measurement: `available` is the
                          declared value bounded to DEFAULT_CONSERVATIVE so a
                          typo cannot produce a four-digit fan-out, and it is
                          never labelled MEASURED.
    UNDETERMINED       -- nothing resolved; `available` = DEFAULT_CONSERVATIVE (3).
    PARKED             -- provider is on the STRUCTURAL cap table (ollama-cloud)
                          but its plan is not; `available` is None and an
                          interview question is attached. Dispatch must REFUSE.
                          This fires even when a max_concurrent was declared
                          alongside the provider: ollama-cloud's real ceiling is
                          a physical fact the operator cannot opt out of by
                          typing a bigger number, and clamping to its highest
                          cap-table row would still be a guess about which plan
                          is actually in effect -- this module never guesses
                          upward. NO_CAP_PROVIDERS entries NEVER reach this
                          status: they have no plan-dependent ceiling to park
                          behind in the first place.
    FAILED             -- a declared config exists but is unusable (e.g. malformed
                          capacity_override.json); `available` is None. Dispatch
                          must REFUSE. A broken declaration is never silently
                          downgraded to a default -- that would hide the
                          operator's own mistake.

`available is None` is the ONLY signal a caller needs: it means "this probe could
not produce a number", and the dispatch path fails closed with
AF-CAPACITY-UNMEASURED.

Exit codes (CLI): 0 success, 3 probe could not produce a number, 2 usage.

FIX 9 -- per-provider live probes (presentation rev2 Phase B)
-------------------------------------------------------------
Capacity detection answers "HOW WIDE can this client run at once". It never
answered "WHAT does this client actually own" -- which provider keys exist
(presence only, never values), which exact models are unlocked on each one,
and which models 9Router has wired locally. FIX 9 adds that inventory:

  * `PROVIDER_PROBE_DEFS` names each probeable provider (openrouter,
    ollama-cloud, deepseek-direct, agnes), the env keys that carry its
    credential and its cheap `GET /models` endpoint.
  * `probe_one_provider()` resolves key presence (env first, then the
    secrets env files BY NAME ONLY -- the value is read into the Bearer
    header transport and never anywhere else), then runs the models call
    through an injectable transport (proofs/tests always inject a stub; the
    default transport is the only thing that touches the network).
  * `detect_9router_lineup()` reads the 9Router's LOCAL database -- the
    already-established non-secret columns (providerNodes.prefix/baseUrl,
    the kv `...|llm` wired-model rows, combos) and NEVER apiKeys or
    providerConnections.data.
  * `probe_providers(...)` is the FIX 9 entry point; `persist=True` stores
    the inventory into the resource profile (resource_profile.py's
    store_provider_probes). `capacity.probe()` itself stays read-only: it
    surfaces presence + lineup under `provider_probes`, never a models call.

Rollout flag: PRESENTATION_PROVIDER_PROBES (default ON; documented =0
rollback below). Credentials never appear in any result, report, or log --
each probe reports `presence: "yes"/"no"` and `key_source` (the env NAME or
file path), never a key value.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Cap table + doctrine constants
# ---------------------------------------------------------------------------

#: The floor every unknown collapses to. NEVER guess upward.
DEFAULT_CONSERVATIVE = 3

PROBE_MODE = "live"  # NEVER "SIMULATED"

PROVIDER_OLLAMA_CLOUD = "ollama-cloud"
PROVIDER_DEEPSEEK_DIRECT = "deepseek-direct"
PROVIDER_OPENROUTER = "openrouter"

PLAN_OLLAMA_20 = "$20/month"
PLAN_OLLAMA_100 = "$100/month"
#: DeepSeek Direct's plan DOES change the ceiling (operator ruling
#: 2026-09-04): Flash allows 2500 concurrent, Pro 500. Both are
#: CAP_TABLE rows, so an over-declaration is clamped DOWN and an unknown
#: plan PARKs behind the one-time interview, same as ollama-cloud.
PLAN_DEEPSEEK_PRO = "v4-pro"
PLAN_DEEPSEEK_FLASH = "v4-flash"

#: (provider, plan) -> concurrent agents. The single source of truth for the
#: providers that have a REAL, structural ceiling -- one this module can
#: observe and that the account itself enforces. As of fix/capacity-uncap-byok
#: this is ollama-cloud ONLY: its $20/$100 tiers are hard account limits, not
#: a number anyone chose. A bring-your-own-key direct provider (DeepSeek
#: Direct, OpenRouter, ...) has no such table row -- see NO_CAP_PROVIDERS.
CAP_TABLE = {
    (PROVIDER_OLLAMA_CLOUD, PLAN_OLLAMA_20): 3,
    # 8, not the raw account maximum: operator ruling 2026-09-04 deliberately
    # leaves the client 2 free agent slots so a presentation build never
    # starves whatever else they are running on the same seat.
    (PROVIDER_OLLAMA_CLOUD, PLAN_OLLAMA_100): 8,
    (PROVIDER_DEEPSEEK_DIRECT, PLAN_DEEPSEEK_FLASH): 2500,
    (PROVIDER_DEEPSEEK_DIRECT, PLAN_DEEPSEEK_PRO): 500,
}

#: Providers on CAP_TABLE, derived rather than hand-duplicated: the set for
#: which "plan known but unresolved" means PARK (see PLANS_BY_PROVIDER below).
CAP_TABLE_PROVIDERS = frozenset(provider for provider, _plan in CAP_TABLE)

#: Which plans a structural cap-table provider can be on -- drives the
#: interview question and the "provider known, plan unknown" PARK. Only
#: CAP_TABLE providers belong here; a BYOK provider in NO_CAP_PROVIDERS has no
#: plan-dependent ceiling to interview the operator about.
PLANS_BY_PROVIDER = {
    PROVIDER_OLLAMA_CLOUD: (PLAN_OLLAMA_20, PLAN_OLLAMA_100),
    PROVIDER_DEEPSEEK_DIRECT: (PLAN_DEEPSEEK_FLASH, PLAN_DEEPSEEK_PRO),
}

#: OPERATOR RULING (fix/capacity-uncap-byok): "Do not limit someone who
#: brought their own capacity." Every provider in this set is a
#: bring-your-own-key direct account the client is already paying for --
#: dispatch never invents a ceiling on it. `available` for a NO_CAP_PROVIDERS
#: hit is UNBOUNDED (see below) unless the operator/client declares a lower
#: max_concurrent for THIS run, which is always honoured as a self-throttle.
#: Extend this set (never CAP_TABLE) for any other BYOK-direct provider --
#: adding a real per-account ceiling belongs in CAP_TABLE instead, never here.
NO_CAP_PROVIDERS = frozenset({PROVIDER_OPENROUTER})

STATUS_MEASURED = "MEASURED"
STATUS_DECLARED_UNVERIFIED = "DECLARED_UNVERIFIED"
STATUS_UNDETERMINED = "UNDETERMINED"
STATUS_PARKED = "PARKED"
STATUS_FAILED = "FAILED"

#: The autofail the dispatch path raises when this probe cannot produce a number.
AUTOFAIL_CODE = "AF-CAPACITY-UNMEASURED"

SOURCE_OVERRIDE = "capacity_override.json"
SOURCE_9ROUTER = "9router"
SOURCE_OPENCLAW = "openclaw"
SOURCE_NONE = "none"

OVERRIDE_FILENAME = "capacity_override.json"
CONFIG_DIR_ENV = "PRESENTATION_CAPACITY_CONFIG_DIR"

#: Platform-aware config paths (master plan Part 8 Fix 13 / FIX 68 seam):
#: on the docker VPS the openclaw root is /data/.openclaw (HOME is often /tmp),
#: so every Path.home() hard-code above read the WRONG box's config. These
#: three constants resolve through presentation_job/oc_paths.py -- one module
#: owns openclaw root resolution -- and fall back to the legacy Mac layout
#: when oc_paths is not deployed beside this file (a partial deploy keeps the
#: pre-FIX-68 behavior, never a hard break). Each stays a MODULE ATTRIBUTE on
#: purpose: tests patch capacity.NINEROUTER_DB / OPENCLAW_CONFIG /
#: HARNESS_SETTINGS_CANDIDATES directly and that contract is load-bearing.
def _oc_paths():
    """presentation_job.oc_paths when importable (package-relative first),
    else None -- callers degrade to the legacy Mac paths."""
    try:
        from . import oc_paths as _op  # package-relative (python3 -m)
        return _op
    except ImportError:
        try:
            import oc_paths as _op  # direct file run from presentation_job/
            return _op
        except ImportError:
            return None

_ocp = _oc_paths()
if _ocp is not None:
    NINEROUTER_DB = Path.home() / ".9router" / "db" / "data.sqlite"
    OPENCLAW_CONFIG = _ocp.root() / "openclaw.json"
else:
    NINEROUTER_DB = Path.home() / ".9router" / "db" / "data.sqlite"
    OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
HARNESS_SETTINGS_CANDIDATES = (
    Path.home() / ".claude-nine" / "settings.json",
    Path.home() / ".claude" / "settings.json",
)

# Process-table signature for the working-concurrency observation. argv[0]
# basename starting with "claude" catches live sessions and their spawned
# subagents; "openclaw" catches the gateway. The pattern is reported alongside
# the count so the number is auditable, never taken on faith.
PROCESS_PATTERN = re.compile(r"^(claude|openclaw)")


class CapacityUnmeasured(RuntimeError):
    """Raised when a caller demands a number this probe could not produce."""


# ---------------------------------------------------------------------------
# The UNBOUNDED sentinel -- "no cap", genuinely, never a large magic number
# ---------------------------------------------------------------------------
class _Unbounded:
    """`available`'s value for a NO_CAP_PROVIDERS hit (deepseek-direct,
    openrouter, ...): a real measurement ("this account has no structural
    ceiling"), not an absence of one and not a stand-in integer like 999999
    that would eventually be wrong. A single module-level instance (UNBOUNDED,
    below) is the only one ever constructed; compare with `is`, not `==`,
    though `==` also works (see __eq__).

    Comparison contract -- this is the part that keeps every downstream
    consumer safe without special-casing it:
      * UNBOUNDED compares as GREATER than every finite int (never less).
      * Consequently `min(ready_items, UNBOUNDED) == ready_items` for any
        finite `ready_items`, regardless of argument order. This is the ONLY
        property execution_plan.cap_wave_width() relies on: a wave's width
        stays governed by the actual number of DAG items ready to run, never
        by this sentinel itself -- "no cap on the provider" is not "no bound
        on one wave's width".
      * UNBOUNDED is truthy and int()-incompatible on purpose: nothing in
        this codebase may treat it as a literal count to range()/multiply/
        spawn -- that would defeat the entire point of a genuine sentinel.

    JSON: never serializes as Python's non-standard `Infinity` (invalid JSON)
    or as a magic integer. Pass `default=json_default` to any `json.dumps()`
    call whose payload might carry this value; it becomes the string
    "UNBOUNDED"."""

    __slots__ = ()

    def __repr__(self):
        return "UNBOUNDED"

    def __str__(self):
        return "UNBOUNDED"

    def __eq__(self, other):
        return isinstance(other, _Unbounded)

    def __ne__(self, other):
        return not isinstance(other, _Unbounded)

    def __hash__(self):
        return hash("presentation_job.capacity._Unbounded")

    def __lt__(self, other):
        return False  # UNBOUNDED is never less than anything, including itself

    def __le__(self, other):
        return isinstance(other, _Unbounded)

    def __gt__(self, other):
        return not isinstance(other, _Unbounded)

    def __ge__(self, other):
        return True

    def __bool__(self):
        return True

    def __int__(self):
        raise TypeError(
            "UNBOUNDED has no finite integer value -- callers must branch on "
            "is_unbounded()/`is UNBOUNDED` before treating capacity as a count "
            "(e.g. execution_plan.cap_wave_width(), which bounds the WAVE width "
            "by ready_items instead)"
        )


#: The single instance every "no structural ceiling" measurement uses.
UNBOUNDED = _Unbounded()


def is_unbounded(value) -> bool:
    """True when `value` is the UNBOUNDED sentinel."""
    return isinstance(value, _Unbounded)


def json_default(obj):
    """`json.dumps(..., default=json_default)` hook. Any capacity result (or
    anything derived from one, e.g. launcher.py's `.capacity-status.json`
    sidecar) that might carry UNBOUNDED must route its json.dumps() call
    through this so it serializes to the literal string "UNBOUNDED" instead
    of raising TypeError or falling back to JSON-invalid `Infinity`."""
    if is_unbounded(obj):
        return "UNBOUNDED"
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# FIX 9: per-provider live probes (key presence + a cheap list/models call)
# ---------------------------------------------------------------------------
PROBE_FLAG_ENV = "PRESENTATION_PROVIDER_PROBES"
PROBE_FLAG_DEFAULT = "1"

def probe_flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_PROVIDER_PROBES=0.

    Default ON per the rev2 rollback doctrine. `=0` is the documented
    rollback for FIX 9's behavior change: probe_providers() returns an empty
    dict without touching the network or the profile, capacity.probe()'s
    `provider_probes` surface reads {"flag": "disabled"}, and nothing else
    in the detection chain changes."""
    return os.environ.get(PROBE_FLAG_ENV, PROBE_FLAG_DEFAULT) != "0"

#: Per-provider probe definitions. Each names the env keys that may carry the
#: credential (checked IN ORDER), the secrets env files consulted for that
#: key NAME (values are never emitted), and the cheapest possible
#: inventory call: `GET {base}/models` on the same OpenAI-compatible base the
#: department's own transports already use. No completion call, no credit
#: call, no balance query -- list/models is the spec's "cheap list/models
#: call".
PROVIDER_PROBE_DEFS = {
    "openrouter": {
        "label": "OpenRouter",
        "env_keys": ("OPENROUTER_API_KEY",),
        "secret_files": (("~/.openclaw/secrets/.env", "OPENROUTER_API_KEY"),
                         ("~/.openclaw/.env", "OPENROUTER_API_KEY")),
        "models_url": "https://openrouter.ai/api/v1/models",
        # OpenRouter /models is public; the Bearer header is still sent when
        # a key resolves so the key-present path is exercised end to end.
        "auth_required_for_models": False,
    },
    "ollama-cloud": {
        "label": "Ollama Cloud",
        "env_keys": ("OLLAMA_API_KEY",),
        "secret_files": (("~/.openclaw/secrets/.env", "OLLAMA_API_KEY"),
                         ("~/.openclaw/.env", "OLLAMA_API_KEY")),
        "models_url": "https://ollama.com/v1/models",
        "auth_required_for_models": True,
    },
    "deepseek-direct": {
        "label": "DeepSeek Direct",
        "env_keys": ("DEEPSEEK_API_KEY",),
        "secret_files": (("~/.openclaw/secrets/.env", "DEEPSEEK_API_KEY"),
                         ("~/.openclaw/.env", "DEEPSEEK_API_KEY")),
        "models_url": "https://api.deepseek.com/models",
        "auth_required_for_models": True,
    },
    "agnes": {
        "label": "Agnes",
        "env_keys": ("AGNES_AI_API_KEY",),
        "secret_files": (("~/.openclaw/secrets/.env", "AGNES_AI_API_KEY"),
                         ("~/.openclaw/.env", "AGNES_AI_API_KEY")),
        "models_url": "https://apihub.agnes-ai.com/v1/models",
        "auth_required_for_models": True,
    },
    # ------------------------------------------------------------------
    # kie probe target (master plan Part 8 Fix 13 / W08a-B3): kie.ai is the
    # department's image provider (gpt-image-2 per model_catalog.json) and the
    # only probeable provider with NO probe definition -- a box whose ONLY key
    # is KIE_API_KEY reported an empty inventory, and FIX 12's preflight then
    # priced its phases off an unverified account. kie.ai exposes no
    # OpenAI-style `GET /models`; the CHEAPEST authenticated inventory call it
    # has is the same credit read build_deck.py already uses for
    # AF-KIE-BALANCE (KIE_CREDIT_URL): `GET /api/v1/chat/credit` with the
    # Bearer key. The body is a credit count, not a model list, so `models`
    # stays [] (never invented) and `ok` on HTTP 200 means "key present AND
    # accepted by kie.ai" -- the presence/validity evidence FIX 9 asks for.
    # ------------------------------------------------------------------
    "kie": {
        "label": "Kie.ai",
        "env_keys": ("KIE_API_KEY",),
        "secret_files": (),
        "models_url": "https://api.kie.ai/api/v1/chat/credit",
        "auth_required_for_models": True,
        "models_endpoint": False,  # credit read: evidence of a live key, not a lineup
    },
}

#: Where key VALUES may be read from when the environment does not already
#: carry them. Same files the department's own loaders (dispatcher's
#: _load_deepseek_key, build_deck's KIE loader) already read. The VALUE is
#: forwarded ONLY into the Authorization header transport and never placed
#: in any result, report, log, profile or exception message.
#: FIX 68/B3: the list is resolved through oc_paths.secrets_env_candidates()
#: (platform-aware: /data/.openclaw/secrets/.env FIRST on the docker VPS,
#: ~/.openclaw first on a Mac, $OPENCLAW_SECRETS explicit override first of
#: all), degrading to the legacy Mac list when oc_paths is not deployed
#: beside this module. Kept as a module-level FUNCTION so a test can patch it.
def _secrets_env_files():
    try:
        op = _oc_paths()
        if op is not None:
            return tuple(str(p) for p in op.secrets_env_candidates())
    except Exception:  # noqa: BLE001 -- a broken oc_paths degrades to legacy
        pass
    return ("~/.openclaw/secrets/.env",
            "~/.openclaw/secrets/secrets.env",
            "~/.openclaw/.env",
            "~/.openclaw/workspace/.env",
            "~/clawd/secrets/.env")

#: Backwards-compatible module attribute (docs/tests referenced the old tuple).
SECRETS_ENV_FILES = (("~/.openclaw/secrets/.env",), ("~/.openclaw/.env",))

# ---------------------------------------------------------------------------
# FIX 67 secret-name canon (master plan Part 8 Fix 13 / W08a-B3 seam):
# the NAME a credential is written under resolves through the ONE canon
# (shared-utils/secret_helper: alias_list(canonical_for(name))), so a key
# saved as KIE_KEY / KIE_AI_API_KEY / DEEP_SEEK_API_KEY / ... is found by the
# same reader that finds the canonical spelling. The helper is path-imported
# from the repo checkout, the installed skills dir, or /data/.openclaw/skills
# -- the same seam research_web.py and kie_generate.py use -- and a box
# without it keeps the exact pre-canon behavior (direct name only), never a
# hard break. A placeholder-shaped value is REJECTED wherever it sits.
# ---------------------------------------------------------------------------
_secret_helper_mod = None
_secret_helper_tried = False

def _secret_helper():
    """Path-import shared-utils/secret_helper.py (the FIX 67 canon helper).
    Returns the module or None when no candidate location has it. Cached."""
    global _secret_helper_mod, _secret_helper_tried
    if _secret_helper_tried:
        return _secret_helper_mod
    _secret_helper_tried = True
    import importlib.util
    skills_default = None
    op = _oc_paths()
    if op is not None:
        try:
            skills_default = Path(op.skills())
        except Exception:  # noqa: BLE001 -- partial deploy keeps the Mac default
            skills_default = None
    if skills_default is None:
        skills_default = Path.home() / ".openclaw" / "skills"
    repo_root = None
    for anc in Path(__file__).resolve().parents:
        if (anc / "shared-utils" / "secret_helper.py").is_file():
            repo_root = anc
            break
    for d in (os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(repo_root / "shared-utils") if repo_root else "",
              str(skills_default / "shared-utils"),
              "/data/.openclaw/skills/shared-utils"):
        if d and (Path(d) / "secret_helper.py").is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    "secret_helper_s51", str(Path(d) / "secret_helper.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                _secret_helper_mod = mod
            except Exception:  # noqa: BLE001 -- a broken helper is the no-canon path
                _secret_helper_mod = None
            break
    return _secret_helper_mod

def _is_placeholder_value(value: str) -> bool:
    """FIX 67: a placeholder value (PASTE_REAL_TOKEN, CHANGE_ME, <TODO>, ...)
    is rejected by every reader. Uses the canon's is_placeholder when the
    helper is reachable; otherwise the same minimal inline gate so a partial
    deploy still refuses."""
    if not value:
        return True
    helper = _secret_helper()
    if helper is not None:
        try:
            return bool(helper.is_placeholder(value))
        except Exception:  # noqa: BLE001 -- canon failure degrades to inline
            pass
    low = value.strip().lower()
    if len(low) < 10:
        return True
    for sub in ("paste_real_token", "your_key_here", "change_me", "changeme",
                "<todo>", "[replace]", "{{", "placeholder", "example_key",
                "todo:", "xxx"):
        if sub in low:
            return True
    if low.startswith("<") and low.endswith(">"):
        return True
    if low.startswith("[") and low.endswith("]"):
        return True
    return False

def _alias_names(env_key: str) -> Tuple[str, ...]:
    """The accepted names for `env_key`: the canonical spelling plus every
    alias in its canon family. Unknown names resolve to themselves (the canon
    helper's own contract), so a family missing from the canon degrades to the
    direct name -- never a hard break, never a NEW name invented here."""
    helper = _secret_helper()
    if helper is None:
        return (env_key,)
    try:
        names = list(helper.alias_list(helper.canonical_for(env_key)))
        return tuple(n for n in names if isinstance(n, str) and n) or (env_key,)
    except Exception:  # noqa: BLE001 -- canon failure degrades to the direct name
        return (env_key,)

def probe_transport(url: str, key: Optional[str] = None,
                    timeout: float = 8.0) -> Tuple[int, bytes]:
    """THE injectable network transport (single seam; proofs/tests inject a
    stub and never touch the network). Returns (http_status, body_bytes).
    The bearer key, when one resolved, goes ONLY into the Authorization
    header -- it is never returned, logged, or raised. urllib is the stdlib
    default; no third-party HTTP dependency."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001 -- error body is best-effort
            body = b""
        return exc.code, body
    except Exception as exc:  # noqa: BLE001 -- transport failure is a verdict
        return 0, str(exc).encode("utf-8", "replace")

def _extract_model_ids(payload: bytes) -> Tuple[list, Optional[str]]:
    """Pull the wired model ids out of a `GET /models` body.

    OpenAI-compatible providers return {"data": [{"id": ...}, ...]}. Some
    return a bare list. Anything unparseable becomes ([], reason) so the
    probe reports honestly instead of inventing an inventory. Non-string ids
    are coerced via str(); nothing else in the item is kept (some providers
    attach per-model pricing/metadata blobs -- out of scope and untrusted)."""
    try:
        parsed = json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return [], "models body not JSON"
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        items = parsed["data"]
    elif isinstance(parsed, list):
        items = parsed
    else:
        return [], "models body shape unrecognized"
    ids = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
        elif isinstance(item, str):
            ids.append(item)
    return ids, None

def _read_secret_value(env_key: str) -> Optional[str]:
    """Resolve a credential for `probe_one_provider`, in order:

      1. an already-exported environment variable (the normal case for a
         dispatch run -- the Engine inherits the sourced secrets env);
      2. the department's secrets env files, matched BY KEY NAME -- the canon
         FAMILY of that name (FIX 67: KIE_API_KEY also matches KIE_KEY,
         KIE_AI_API_KEY, KIE_VIDEO_API_KEY, KIE_API_KEY_IAFS; DEEPSEEK_API_KEY
         also matches DEEP_SEEK_API_KEY; ...), with the FILE SEARCH ORDER
         resolved platform-aware through oc_paths.secrets_env_candidates()
         (FIX 68: /data/.openclaw/secrets/.env first on the docker VPS,
         ~/.openclaw first on a Mac, $OPENCLAW_SECRETS override first of all).

    The VALUE is returned for the Authorization header only. Every caller
    that surfaces anything to a human uses presence/key_source, never this.
    A placeholder-shaped value is REJECTED (FIX 67) -- a key that says
    PASTE_REAL_TOKEN is not a key. Returns None when no source has it."""
    value = (os.environ.get(env_key) or "").strip()
    if value and not _is_placeholder_value(value):
        return value
    # canon family: the canonical spelling plus every alias
    accepted = _alias_names(env_key)
    if env_key not in accepted:
        accepted = (env_key,) + tuple(accepted)
    for file_spec in _secrets_env_files():
        path = Path(os.path.expanduser(file_spec))
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                for name in accepted:
                    if line.startswith(f"{name}="):
                        candidate = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if candidate and not _is_placeholder_value(candidate):
                            return candidate
        except OSError:
            continue
    # env carried a value but the canon rejected it as a placeholder: honour
    # an explicitly injected fake-env view (proof seam) over the rejection,
    # the same posture research_web.brave_key_present documents.
    if value:
        return value
    return None

def probe_one_provider(provider: str,
                       transport: Optional[callable] = None,
                       env: Optional[dict] = None) -> dict:
    """One cheap live probe of one provider. Returns the FIX 9 verdict:

        provider            normalized provider id (PROVIDER_PROBE_DEFS key)
        present             bool -- key FOUND in env or the secrets env files
        key_source          where the key NAME was found ("env:NAME" or the
                            file path) -- never the value
        probed              bool -- a models call was actually attempted
        http_status         the transport's status (0 = transport failure)
        models              sorted wired model ids (may be [] when not probed
                            or the call failed -- never invented)
        models_error        why models is [] (absent on success)
        ok                  bool -- present AND probed AND models resolved

    Never raises. Never puts the key value, or any response body fragment
    beyond model ids, in the verdict. `env` lets proofs simulate presence
    without touching os.environ."""
    if provider not in PROVIDER_PROBE_DEFS:
        return {"provider": provider, "present": False, "key_source": None,
                "probed": False, "http_status": None, "models": [],
                "models_error": "unknown provider", "ok": False}
    spec = PROVIDER_PROBE_DEFS[provider]
    env_keys = spec["env_keys"]
    env_view = os.environ if env is None else env

    present = False
    key_source = None
    key_value = None
    for name in env_keys:
        candidate = str((env_view.get(name) or "")).strip()
        if candidate:
            present, key_source, key_value = True, f"env:{name}", candidate
            break
    key_env = os.environ if env is None else env
    if not present:
        # secrets files: presence read by NAME from the files; the value is
        # loaded only for the header. (Uses the real fs -- env= only fakes
        # the process environment, matching dispatcher's loader posture.)
        for name in env_keys:
            resolved = _read_secret_value(name)
            if resolved:
                present, key_source, key_value = True, (
                    "secrets-env-files"), resolved
                break

    result = {"provider": provider, "present": present,
              "key_source": key_source if present else None,
              "probed": False, "http_status": None, "models": [],
              "models_error": None, "ok": False}

    should_probe = spec["auth_required_for_models"] is False or present
    if not should_probe:
        result["models_error"] = "no key present -- models call skipped"
        return result

    transport = transport or probe_transport
    try:
        status, body = transport(spec["models_url"], key_value)
    except Exception as exc:  # noqa: BLE001 -- a broken stub must not kill the probe
        result.update({"probed": True, "http_status": 0,
                       "models_error": f"transport failure: "
                                       f"{exc.__class__.__name__}"})
        return result
    result["probed"] = True
    result["http_status"] = status
    if status == 200:
        # FIX 9/B3: providers whose probe endpoint is NOT a model lineup
        # (kie's credit read) carry models_endpoint=False in their def -- a
        # 200 there is the evidence (key present AND accepted), `models`
        # stays [] (never invented) and the verdict records the endpoint
        # kind so the report can say what was actually measured.
        if spec.get("models_endpoint") is False:
            result["models_error"] = None
            result["inventory_kind"] = "credit"
            result["ok"] = True
            return result
        ids, error = _extract_model_ids(body)
        if error:
            result["models_error"] = error
        else:
            result["models"] = sorted(ids)
            result["ok"] = True
    elif status == 401 or status == 403:
        result["models_error"] = ("key present but rejected by provider "
                                  f"(HTTP {status})")
    elif status == 0:
        detail = body.decode("utf-8", "replace")[:120]
        result["models_error"] = f"transport failure: {detail}"
    else:
        result["models_error"] = f"HTTP {status} from models endpoint"
    return result

def _ninerouter_lineup(db_path: Optional[Path] = None) -> dict:
    """Read the 9Router's LOCAL model lineup -- the non-secret columns only.

    Reads three things, all already-established non-secret surfaces:
      * providerNodes.data's prefix/baseUrl (which provider namespaces exist);
      * the kv rows keyed `{providerAlias}|{modelId}|llm` (what 9Router has
        WIRED per provider node -- the local lineup the operator sees);
      * combos.name/models (primary route listings, also read by the
        capacity detection chain).
    NEVER apiKeys, NEVER providerConnections.data (both carry credentials).
    Returns {"hit", "detail", "providers": {prefix: {"label", "models"}},
    "total_models"}."""
    path = Path(db_path) if db_path else NINEROUTER_DB
    out = {"hit": False, "detail": "", "providers": {}, "total_models": 0}
    if not path.is_file():
        out["detail"] = f"no 9Router database at {path}"
        return out
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        out["detail"] = f"9Router database unreadable: {exc.__class__.__name__}"
        return out
    try:
        cur = con.cursor()
        nodes = {}
        try:
            for data in cur.execute("select data from providerNodes"):
                try:
                    node = json.loads(data[0] or "{}")
                except ValueError:
                    continue
                prefix = node.get("prefix")
                if isinstance(prefix, str) and prefix:
                    nodes[prefix] = {"label": node.get("name") or prefix,
                                     "baseUrl": node.get("baseUrl"), "models": []}
        except sqlite3.Error:
            pass
        wired = {}
        try:
            for key, in cur.execute("select key from kv where key like '%|llm'"):
                parts = key.split("|")
                if len(parts) < 3:
                    continue
                alias, model_id = parts[0], parts[1]
                wired.setdefault(alias, []).append("|".join(parts[1:-1]))
        except sqlite3.Error:
            pass
        # Map each node's alias onto its prefix when possible; node ids are
        # uuid-ish aliases, so ALSO fall back to the prefix rows that carry
        # their own models. The lineup is whatever 9Router has wired.
        providers = {}
        combined = dict(nodes)
        for alias, models in wired.items():
            if alias in combined:
                combined[alias]["models"].extend(models)
            else:
                combined[alias] = {"label": alias, "baseUrl": None,
                                   "models": list(models)}
        for prefix, info in combined.items():
            models = sorted(dict.fromkeys(info["models"]))
            providers[prefix] = {"label": info["label"], "models": models}
            out["total_models"] += len(models)
        out["providers"] = providers
        out["hit"] = bool(providers)
        out["detail"] = (f"9Router lineup read from {path}: "
                         f"{len(providers)} provider aliases, "
                         f"{out['total_models']} wired models"
                         if out["hit"] else f"no wired models in {path}")
        return out
    finally:
        con.close()

def detect_9router_lineup(db_path: Optional[Path] = None) -> dict:
    """Public FIX 9 entry for the 9Router local lineup (never any secret
    table). See _ninerouter_lineup()."""
    return _ninerouter_lineup(db_path)

def probe_providers(providers: Optional[list] = None,
                    transport: Optional[callable] = None,
                    db_path: Optional[Path] = None,
                    persist: bool = False,
                    config_dir: Optional[Path] = None) -> dict:
    """FIX 9 entry point: probe providers + read the 9Router lineup.

    With persist=True the inventory lands in the resource profile
    (resource_profile.store_provider_probes) under `wired_models` and
    `key_present` per provider, redacted by the profile's write path. With
    persist=False (the default) nothing is stored -- capacity.probe() stays
    read-only and calls this fresh. Returns:

        {"flag": "1"|"0", "probes": {provider: verdict}, "ninerouter": ...,
         "probed_at": iso}
    """
    if not probe_flag_enabled():
        return {"flag": "0", "probes": {}, "ninerouter":
                {"hit": False, "detail": "provider probes disabled by "
                 f"{PROBE_FLAG_ENV}=0", "providers": {}, "total_models": 0},
                "probed_at": datetime.datetime.now().astimezone().isoformat()}
    wanted = providers or sorted(PROVIDER_PROBE_DEFS)
    probes = {}
    for provider in wanted:
        if provider not in PROVIDER_PROBE_DEFS:
            probes[provider] = {"provider": provider, "present": False,
                                "key_source": None, "probed": False,
                                "http_status": None, "models": [],
                                "models_error": "unknown provider", "ok": False}
            continue
        probes[provider] = probe_one_provider(provider, transport=transport)
    lineup = _ninerouter_lineup(db_path)
    result = {
        "flag": "1",
        "probes": probes,
        "ninerouter": lineup,
        "probed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if persist:
        try:
            try:
                from . import resource_profile as _rp
            except ImportError:
                import resource_profile as _rp  # type: ignore[no-redef]
            _rp.store_provider_probes(result, config_dir=config_dir)
        except Exception as exc:  # noqa: BLE001 -- never break the probe path
            result["persist_error"] = f"{exc.__class__.__name__}: {exc}"
    return result

# ---------------------------------------------------------------------------
# Credential safety
# ---------------------------------------------------------------------------
_SECRET_KEY_RE = re.compile(
    r"(api[-_]?key|key|token|secret|password|passwd|auth|credential|cookie|bearer)",
    re.IGNORECASE,
)


def _safe_value(key: str, value):
    """Return `value` only when `key` cannot be carrying credential material.

    Every string this module lifts out of a config file goes through here. A
    field named apiKey / token / authToken / password / ... is dropped on the
    floor: detection needs to know WHICH provider is configured, never what the
    account's secret is."""
    if _SECRET_KEY_RE.search(str(key)):
        return None
    return value


def _get_safe(node, *path):
    """Walk a nested dict by key path, refusing any secret-named segment."""
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return None
        if _safe_value(key, True) is None:
            return None
        cur = cur.get(key)
    return cur


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize_provider(raw) -> Optional[str]:
    """Map a declared/detected provider string onto a cap-table provider id.

    Returns None for anything the cap table does not cover -- an unknown
    provider is an unknown provider, never the nearest-looking one."""
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().replace("_", "-").replace(" ", "-")
    if not token:
        return None
    if token in ("ollama-local", "ollama-localhost", "local-ollama"):
        return None  # a local Ollama has no purchased plan; not a cap-table row
    if token in ("ollama-cloud", "ollamacloud", "ollama", "ollman"):
        return PROVIDER_OLLAMA_CLOUD
    if token.startswith("ollama-cloud"):
        return PROVIDER_OLLAMA_CLOUD
    if token in ("deepseek-direct", "deepseek", "deepseekdirect", "ds",
                 "ds-max", "dspro", "dspro-max", "dspromax"):
        return PROVIDER_DEEPSEEK_DIRECT
    if token.startswith("deepseek"):
        return PROVIDER_DEEPSEEK_DIRECT
    if token in ("openrouter", "open-router", "openrouterai", "openrouter-direct"):
        return PROVIDER_OPENROUTER
    if token.startswith("openrouter"):
        return PROVIDER_OPENROUTER
    return None


def normalize_plan(raw, provider: Optional[str]) -> Optional[str]:
    """Map a declared/detected plan string onto a cap-table plan id."""
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower()
    if not token:
        return None
    if provider == PROVIDER_OLLAMA_CLOUD or provider is None:
        digits = re.sub(r"[^0-9]", "", token)
        if digits == "20":
            return PLAN_OLLAMA_20
        if digits == "100":
            return PLAN_OLLAMA_100
    if provider == PROVIDER_DEEPSEEK_DIRECT or provider is None:
        compact = token.replace(" ", "-").replace("_", "-")
        if "pro" in compact:
            return PLAN_DEEPSEEK_PRO
        if "flash" in compact:
            return PLAN_DEEPSEEK_FLASH
    return None


def _plan_from_model_slug(provider: Optional[str], slug: str) -> Optional[str]:
    """Derive the plan from a model identifier, where the model IMPLIES the plan.

    DeepSeek Direct is the only provider where it does: v4-pro and v4-flash are
    different products with different parallel ceilings, and the model id names
    which one. Ollama Cloud's $20 and $100 plans run the SAME models, so no model
    id can ever reveal the plan -- that is why Ollama Cloud always reaches the
    interview question."""
    if provider != PROVIDER_DEEPSEEK_DIRECT:
        return None
    text = slug.lower()
    if "pro" in text:
        return PLAN_DEEPSEEK_PRO
    if "flash" in text:
        return PLAN_DEEPSEEK_FLASH
    return None


def interview_question(provider: str) -> str:
    """The ONE question that resolves a STRUCTURAL cap-table provider with an
    unknown plan -- today ollama-cloud and deepseek-direct. NO_CAP_PROVIDERS
    entries (openrouter, ...) never reach PARK, so this is never called for
    them: there is no plan that would change their ceiling.

    The numbers are rendered FROM CAP_TABLE, never hardcoded. A hardcoded
    per-provider sentence drifted once already (it still advertised
    "$100/month -> 10" after the operator lowered that row to 8), so the
    only source of truth here is the table itself."""
    plans = PLANS_BY_PROVIDER.get(provider, ())
    if plans:
        rows = ", ".join(f"{p} -> {CAP_TABLE.get((provider, p), '?')}" for p in plans)
        return f"Which plan is your {provider} account on? ({rows}.)"
    return f"Which plan is your {provider} account on?"


# ---------------------------------------------------------------------------
# Step (a): the declared override
# ---------------------------------------------------------------------------
def department_config_dir() -> Path:
    """Where capacity_override.json lives.

    $PRESENTATION_CAPACITY_CONFIG_DIR wins when set (this is how a client box, a
    test, or an operator points detection at a specific declaration). Otherwise
    the department's own config/ dir, falling back to the department root --
    resolved by walking up from this file (presentation_job/ -> scripts/ -> dept),
    never from a hard-coded operator path."""
    env = os.environ.get(CONFIG_DIR_ENV)
    if env:
        return Path(env).expanduser()
    dept = Path(__file__).resolve().parent.parent.parent
    cfg = dept / "config"
    return cfg if cfg.is_dir() else dept


def override_path(config_dir: Optional[Path] = None) -> Path:
    return Path(config_dir or department_config_dir()) / OVERRIDE_FILENAME


def read_override(config_dir: Optional[Path] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Read the declared override. Returns (record, error).

    Absent file -> (None, None): not an error, detection moves to step (b).
    Present but unreadable/not-JSON/not-an-object -> (None, reason): a HARD error.
    A declaration the operator wrote and we cannot parse is never downgraded to a
    silent default -- that would hide their mistake behind a plausible number."""
    path = override_path(config_dir)
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path} is present but unreadable/not valid JSON: {exc}"
    if not isinstance(raw, dict):
        return None, f"{path} must contain a JSON object, found {type(raw).__name__}"
    return raw, None


def _resolve_override(record: dict, path: Path) -> dict:
    """Turn a declared {provider, plan, max_concurrent} into a resolution dict.

    A declaration is not a measurement -- except for a NO_CAP_PROVIDERS entry,
    where a declared number is exactly what it claims to be: the operator/
    client choosing to self-throttle a provider that has no ceiling to
    reconcile against in the first place. The cases below are checked in THIS
    order on purpose:

      0. provider resolves to a NO_CAP_PROVIDERS entry (deepseek-direct,
         openrouter, ...) -> MEASURED, no matter what the plan says. "Do not
         limit someone who brought their own capacity": `available` is the
         declared max_concurrent verbatim when given (a self-throttle is
         always honoured, and never clamped -- there is no table row to clamp
         it against), or UNBOUNDED when no number was declared. This check
         runs FIRST so a BYOK provider can never fall through to the
         structural-cap-table cases below, which do not apply to it.
      1. (provider, plan) BOTH resolve to a STRUCTURAL cap-table row
         (ollama-cloud) -> that row is authoritative; a declared
         max_concurrent may only lower it.
      2. provider resolves (it IS on the structural cap table) but plan does
         not -> PARK, no matter what max_concurrent says. The provider's real
         ceiling is a physical fact the operator cannot opt out of by typing a
         bigger number, and clamping to that provider's own highest cap-table
         row would still be a guess about which plan is actually in effect (a
         $20/month Ollama Cloud account cannot run 8 just because a
         $100/month account can) -- this module never guesses upward, so it
         asks instead of assuming. This check MUST come before case 3 below:
         if the bare-declared-int fallback ran first it would swallow every
         "provider known, plan missing, max_concurrent present" declaration
         and PARK would never fire -- that ordering mistake is the bug u07's
         hardening fixed, and case 0 above must never reopen it for a
         structural provider (it only ever fires for NO_CAP_PROVIDERS).
      3. provider does not resolve at all (neither a cap-table row nor a
         NO_CAP_PROVIDERS entry, e.g. an entirely unrecognised or absent
         provider name) -> the declared number is the only information
         available, but it is a self-report about an unidentified provider,
         not a measurement. It is honoured only up to DEFAULT_CONSERVATIVE, so
         a typo (784 instead of 8, or a placeholder 9999) cannot produce a
         four-digit fan-out, and the result is labelled DECLARED_UNVERIFIED,
         never MEASURED.
    """
    provider = normalize_provider(_safe_value("provider", record.get("provider")))
    plan = normalize_plan(_safe_value("plan", record.get("plan")), provider)
    declared = record.get("max_concurrent")
    declared_int = declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    if declared_int is not None and declared_int < 1:
        declared_int = None

    notes = []

    # Case 0: a bring-your-own-key direct provider -- NO CAP, by operator
    # ruling. Never reaches PARK; a declared number self-throttles, verbatim,
    # never clamped (there is nothing to clamp it against).
    if provider in NO_CAP_PROVIDERS:
        if declared_int is not None:
            available = declared_int
            notes.append(
                f"{provider} is a NO_CAP_PROVIDERS entry (bring-your-own-key, no "
                f"structural ceiling) -- declared max_concurrent={declared_int} is honoured "
                f"verbatim as a self-throttle for this run, never clamped upward or downward"
            )
        else:
            available = UNBOUNDED
            notes.append(
                f"{provider} is a NO_CAP_PROVIDERS entry (bring-your-own-key, no "
                f"structural ceiling) -- no max_concurrent declared, so capacity is "
                f"UNBOUNDED: dispatch as wide as the ready work allows"
            )
        return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                "available": available, "notes": notes}

    # Case 1: a full known (provider, plan) pair on the STRUCTURAL cap table
    # -- the table is authoritative.
    if provider and plan and (provider, plan) in CAP_TABLE:
        capped = CAP_TABLE[(provider, plan)]
        if declared_int is not None and declared_int != capped:
            # A declared number may lower it (an operator throttling
            # themselves is legitimate) but must never raise it above what the
            # account can actually run.
            available = min(declared_int, capped)
            notes.append(
                f"declared max_concurrent={declared_int} reconciled against cap table "
                f"{capped} for ({provider}, {plan}) -> {available} (never above the table)"
            )
        else:
            available = capped
        return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                "available": available, "notes": notes}

    # Case 2: provider is on the structural cap table, plan is not resolvable
    # -> PARK. Checked BEFORE the bare-declared-int fallback so a
    # max_concurrent typed alongside a known provider can never bypass the
    # interview question.
    if provider in CAP_TABLE_PROVIDERS and not plan:
        if declared_int is not None:
            notes.append(
                f"{path} declares provider {provider} with max_concurrent={declared_int}, "
                f"but no recognisable plan -- a declared number is never authoritative for "
                f"a structural cap-table provider until its plan is confirmed, so the "
                f"declared value is disregarded and this PARKS behind the interview "
                f"question instead of clamping to a guessed ceiling"
            )
        else:
            notes.append(f"{path} declares provider {provider} but no recognisable plan")
        return {"status": STATUS_PARKED, "provider": provider, "plan": None,
                "available": None, "notes": notes}

    # Case 3: provider is not recognised at all -- a self-reported number,
    # bounded, honestly labelled, never MEASURED.
    if declared_int is not None:
        available = min(declared_int, DEFAULT_CONSERVATIVE)
        notes.append(
            f"({record.get('provider')!r}, {record.get('plan')!r}) is not a cap-table row "
            f"and not a recognised NO_CAP_PROVIDERS entry; declared max_concurrent="
            f"{declared_int} is a self-report, not a measurement -- bounded to "
            f"DEFAULT_CONSERVATIVE={DEFAULT_CONSERVATIVE} -> {available}"
        )
        return {"status": STATUS_DECLARED_UNVERIFIED, "provider": provider, "plan": plan,
                "available": available, "notes": notes}

    return {"status": STATUS_UNDETERMINED, "provider": provider, "plan": plan,
            "available": DEFAULT_CONSERVATIVE,
            "notes": [f"{path} declares neither a cap-table provider/plan pair, a "
                      f"NO_CAP_PROVIDERS entry, nor a positive integer max_concurrent"]}


def persist_plan_answer(provider: str, plan: str,
                        config_dir: Optional[Path] = None) -> Path:
    """Write the interview answer to capacity_override.json -- asked ONCE.

    After this file exists, step (a) hits on every subsequent run and the
    interview question is never emitted again. Returns the written path.
    Raises ValueError on a provider/plan pair the cap table does not know."""
    norm_provider = normalize_provider(provider)
    norm_plan = normalize_plan(plan, norm_provider)
    if not norm_provider or not norm_plan or (norm_provider, norm_plan) not in CAP_TABLE:
        raise ValueError(
            f"refusing to persist an unknown pair (provider={provider!r}, plan={plan!r}); "
            f"known pairs: {sorted(CAP_TABLE)}"
        )
    path = override_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": norm_provider,
        "plan": norm_plan,
        "max_concurrent": CAP_TABLE[(norm_provider, norm_plan)],
        "source": "interview",
        "answered_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "_note": "Written by capacity.py after the one-time capacity interview. "
                 "Delete this file to be asked again.",
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Step (b): the 9Router configuration
# ---------------------------------------------------------------------------
def _harness_settings() -> Tuple[Optional[dict], Optional[Path]]:
    """Read the harness settings.json, if one exists. Never exits.

    Only three non-secret fields are ever consulted: `model`, `modelOverrides`,
    and the ANTHROPIC_DEFAULT_*_MODEL aliases. Anything whose key looks like a
    credential is refused by _safe_value()."""
    for path in HARNESS_SETTINGS_CANDIDATES:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            return raw, path
    return None, None


def _primary_route_alias(settings: Optional[dict]) -> Optional[str]:
    """The 9Router combo name the harness' primary model routes through.

    settings.json declares `model` (e.g. "opus"); the ANTHROPIC_DEFAULT_*_MODEL
    env aliases and `modelOverrides` map that onto a 9Router combo (e.g.
    "opus-chain"). Both are plain model/route names -- no credential is read."""
    if not isinstance(settings, dict):
        return None
    model = _safe_value("model", settings.get("model"))
    if not isinstance(model, str) or not model.strip():
        return None
    model = model.strip()
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    alias_key = f"ANTHROPIC_DEFAULT_{model.upper()}_MODEL"
    alias = _safe_value(alias_key, env.get(alias_key))
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    overrides = settings.get("modelOverrides")
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if _safe_value(key, True) is None or not isinstance(value, str):
                continue
            if key == model or key.endswith(f"-{model}") or model in key.split("-"):
                return value.strip()
    return model


def _combo_models(alias: str, db_path: Path) -> Optional[list]:
    """Read ONLY combos.name / combos.models for `alias`, read-only, never the
    apiKeys table and never providerConnections.data (both carry secrets)."""
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(
            "select models from combos where name = ? limit 1", (alias,)
        ).fetchone()
        if row is None:
            return None
        try:
            models = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except ValueError:
            return None
        return models if isinstance(models, list) else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _split_route_entry(entry: str) -> Tuple[Optional[str], str]:
    """'ds-max/deepseek-v4-flash(max)' -> ('ds-max', 'deepseek-v4-flash')."""
    if not isinstance(entry, str) or "/" not in entry:
        return None, str(entry or "")
    namespace, remainder = entry.split("/", 1)
    slug = re.sub(r"\(.*?\)", "", remainder).strip()
    return namespace.strip(), slug


def detect_from_9router(db_path: Optional[Path] = None) -> dict:
    """Step (b). Which provider does the primary model route to?"""
    db_path = Path(db_path) if db_path else NINEROUTER_DB
    settings, settings_path = _harness_settings()
    alias = _primary_route_alias(settings)
    if not alias:
        return {"hit": False,
                "detail": f"no harness settings.json with a `model` field at "
                          f"{', '.join(str(p) for p in HARNESS_SETTINGS_CANDIDATES)}"}
    if not db_path.is_file():
        return {"hit": False,
                "detail": f"primary model alias {alias!r} (from {settings_path}) but no "
                          f"9Router database at {db_path}"}
    models = _combo_models(alias, db_path)
    if not models:
        return {"hit": False,
                "detail": f"9Router database {db_path} has no combo named {alias!r} "
                          f"(or it declares no models)"}
    for entry in models:
        namespace, slug = _split_route_entry(entry)
        provider = normalize_provider(namespace)
        if not provider:
            continue
        return {"hit": True, "provider": provider,
                "plan": _plan_from_model_slug(provider, slug),
                "detail": f"9Router combo {alias!r} routes to namespace {namespace!r} "
                          f"(model {slug!r}) -> {provider}"}
    namespaces = [_split_route_entry(e)[0] for e in models]
    return {"hit": False,
            "detail": f"9Router combo {alias!r} routes to namespaces {namespaces!r}, "
                      f"none of which is a cap-table provider"}


# ---------------------------------------------------------------------------
# Step (c): the OpenClaw agent model configuration
# ---------------------------------------------------------------------------
_OPENCLAW_PRIMARY_PATHS = (
    ("agents", "defaults", "model", "primary"),
    ("agents", "defaults", "subagents", "model", "primary"),
)


def _openclaw_namespace_is_cloud(config: dict, namespace: str) -> Optional[bool]:
    """Is this OpenClaw provider namespace the CLOUD Ollama or a local one?

    Decided from models.providers.<ns>.baseUrl -- a routing endpoint, not a
    credential (and the URL itself never leaves this function). Returns None when
    the namespace declares no baseUrl."""
    base_url = _get_safe(config, "models", "providers", namespace, "baseUrl")
    if not isinstance(base_url, str) or not base_url:
        return None
    host = base_url.lower()
    if "localhost" in host or "127.0.0.1" in host or "::1" in host or "0.0.0.0" in host:
        return False
    return True


def detect_from_openclaw(config_path: Optional[Path] = None) -> dict:
    """Step (c). The provider namespace prefix on the primary model."""
    path = Path(config_path) if config_path else OPENCLAW_CONFIG
    if not path.is_file():
        return {"hit": False, "detail": f"no OpenClaw config at {path}"}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"hit": False, "detail": f"OpenClaw config {path} unreadable: {exc}"}
    if not isinstance(config, dict):
        return {"hit": False, "detail": f"OpenClaw config {path} is not a JSON object"}

    candidates = []
    for keys in _OPENCLAW_PRIMARY_PATHS:
        value = _get_safe(config, *keys)
        if isinstance(value, str) and value.strip():
            candidates.append((".".join(keys), value.strip()))
    agents_list = _get_safe(config, "agents", "list")
    if isinstance(agents_list, list):
        for idx, agent in enumerate(agents_list):
            value = _get_safe(agent, "model", "primary")
            if isinstance(value, str) and value.strip():
                candidates.append((f"agents.list[{idx}].model.primary", value.strip()))

    if not candidates:
        return {"hit": False,
                "detail": f"OpenClaw config {path} declares no agents.*.model.primary"}

    for where, model_id in candidates:
        namespace, slug = _split_route_entry(model_id)
        if namespace is None:
            continue
        if namespace.lower().startswith("ollama"):
            is_cloud = _openclaw_namespace_is_cloud(config, namespace)
            if is_cloud is False:
                continue  # a local Ollama has no purchased plan
        provider = normalize_provider(namespace)
        if not provider:
            continue
        return {"hit": True, "provider": provider,
                "plan": _plan_from_model_slug(provider, slug),
                "detail": f"OpenClaw {where} = namespace {namespace!r} (model {slug!r}) "
                          f"-> {provider}"}
    namespaces = sorted({_split_route_entry(m)[0] for _, m in candidates})
    return {"hit": False,
            "detail": f"OpenClaw primary models use namespaces {namespaces!r}, none of "
                      f"which is a cap-table provider"}


# ---------------------------------------------------------------------------
# Observation: how many harness processes are running right now
# ---------------------------------------------------------------------------
def measure_working_concurrent() -> tuple:
    """Count live harness/subagent processes on the local box.

    Uses psutil when importable; otherwise `ps -A -o pid=,command=` parsing.
    Returns (count, method, ok). On failure returns (0, reason, False) and the
    caller labels the number UNMEASURED -- never a fabricated value."""
    self_pid = os.getpid()
    try:
        import psutil  # optional dependency

        count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == self_pid:
                    continue
                if PROCESS_PATTERN.match(proc.info["name"] or ""):
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return count, "psutil process_iter, pattern " + PROCESS_PATTERN.pattern, True
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return 0, f"ps exited {out.returncode}", False
        count = 0
        for line in out.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_str, command = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid == self_pid:
                continue
            argv0 = command.split(None, 1)[0]
            basename = os.path.basename(argv0)
            if basename.startswith("python") and "capacity.py" in command:
                continue  # this probe's own interpreter
            if PROCESS_PATTERN.match(basename):
                count += 1
        return count, "ps -A scan, argv[0] pattern " + PROCESS_PATTERN.pattern, True
    except Exception as exc:  # noqa: BLE001 -- measurement must never raise
        return 0, f"measurement failed: {exc}", False


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------
def detect(config_dir: Optional[Path] = None) -> dict:
    """Run the detection chain. Returns the resolution plus the audit trail.

    Never raises, never exits, never reads a credential value."""
    trail = []
    path = override_path(config_dir)

    # (a) the declared override
    record, error = read_override(config_dir)
    if error:
        trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": "ERROR",
                      "detail": error})
        return {"status": STATUS_FAILED, "provider": None, "plan": None,
                "available": None, "source": SOURCE_OVERRIDE,
                "override_path": str(path), "trail": trail, "notes": [error]}
    if record is not None:
        resolved = _resolve_override(record, path)
        trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": resolved["status"],
                      "detail": f"declared override at {path}: provider="
                                f"{resolved['provider']}, plan={resolved['plan']}"})
        resolved.update({"source": SOURCE_OVERRIDE, "override_path": str(path),
                         "trail": trail})
        return resolved
    trail.append({"step": "a", "source": SOURCE_OVERRIDE, "result": "MISS",
                  "detail": f"no declared override at {path}"})

    # (b) 9Router, then (c) OpenClaw
    for step, source, detector in (("b", SOURCE_9ROUTER, detect_from_9router),
                                   ("c", SOURCE_OPENCLAW, detect_from_openclaw)):
        found = detector()
        if not found.get("hit"):
            trail.append({"step": step, "source": source, "result": "MISS",
                          "detail": found.get("detail", "")})
            continue
        provider = found["provider"]
        plan = found.get("plan")
        trail.append({"step": step, "source": source,
                      "result": "HIT" if plan else "HIT (plan unknown)",
                      "detail": found.get("detail", "")})
        # NO_CAP_PROVIDERS (deepseek-direct, openrouter, ...): MEASURED and
        # UNBOUNDED regardless of whether a plan was found -- no plan of
        # theirs changes the ceiling, because there isn't one. Checked BEFORE
        # the structural cap-table lookup so a BYOK provider never falls
        # through to PARK.
        if provider in NO_CAP_PROVIDERS:
            return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                    "available": UNBOUNDED, "source": source,
                    "override_path": str(path), "trail": trail,
                    "notes": [f"{provider} is a NO_CAP_PROVIDERS entry (bring-your-own-key, "
                              f"no structural ceiling) -- available is UNBOUNDED"]}
        if plan and (provider, plan) in CAP_TABLE:
            return {"status": STATUS_MEASURED, "provider": provider, "plan": plan,
                    "available": CAP_TABLE[(provider, plan)], "source": source,
                    "override_path": str(path), "trail": trail, "notes": []}
        # (d) provider is on the structural cap table (ollama-cloud), plan
        # unknown -> PARK behind the interview question.
        trail.append({"step": "d", "source": source, "result": "PARK",
                      "detail": f"provider {provider} detected but its plan cannot be "
                                f"read from any configuration -- asking once"})
        return {"status": STATUS_PARKED, "provider": provider, "plan": None,
                "available": None, "source": source, "override_path": str(path),
                "trail": trail,
                "notes": [f"answer persists to {path}; the question is asked ONCE"]}

    # (e) nothing found
    trail.append({"step": "e", "source": SOURCE_NONE, "result": "UNDETERMINED",
                  "detail": f"no provider could be determined from any source; falling "
                            f"back to DEFAULT_CONSERVATIVE={DEFAULT_CONSERVATIVE}"})
    return {"status": STATUS_UNDETERMINED, "provider": None, "plan": None,
            "available": DEFAULT_CONSERVATIVE, "source": SOURCE_NONE,
            "override_path": str(path), "trail": trail, "notes": []}


def resource_profile_surface(config_dir: Optional[Path] = None,
                             resolution: Optional[dict] = None) -> dict:
    """FIX 8: the capacity probe's read-only view of the per-client resource
    profile (resource_profile.py's store). Returns a redacted summary of the
    persisted client picture -- providers, plan tiers, ceilings, the
    ask-once lock state and any intake question still owed -- WITHOUT ever
    reading or emitting a credential, and WITHOUT changing detection: this
    is a surfaced mirror, not a third detection source. `resolution` (the
    detect() result, when available) feeds the pending-question evaluation
    so a provider caught PARKing surfaces its one-time question even before
    the profile has ever heard of it. Never raises; the probe must keep
    working on a box with no profile, a flag-disabled profile, or a corrupt
    one. Import is lazy so this module never depends on the profile module
    at import time (launcher.py's dual-import posture keeps working either
    way)."""
    surface = {"profile_enabled": True, "profile_path": None,
               "providers": [], "pending_questions": []}
    try:
        try:
            from . import resource_profile as _rp  # package-relative
        except ImportError:  # direct file run from presentation_job/
            import resource_profile as _rp  # type: ignore[no-redef]
    except ImportError:
        surface["profile_enabled"] = False
        return surface
    if not _rp.flag_enabled():
        surface["profile_enabled"] = False
        return surface
    try:
        path = _rp.profile_path(config_dir)
        surface["profile_path"] = str(path)
        profile = _rp.load_profile(config_dir)
        if profile.get("error"):
            surface["profile_error"] = profile["error"]
        summary = _rp.redacted_summary(profile)
        surface["providers"] = summary.get("providers", [])
        detection = None
        if isinstance(resolution, dict):
            provider = resolution.get("provider")
            if isinstance(provider, str) and provider.strip():
                detection = {"provider": provider,
                             "detected": resolution["status"] != "UNDETERMINED"}
        pending = _rp.pending_questions(profile=profile, detection=detection)
        surface["pending_questions"] = pending
        surface["pending_intake_ids"] = sorted(
            {q.get("id") for q in pending})
    except Exception as exc:  # noqa: BLE001 -- never break the probe
        surface["profile_error"] = f"{exc.__class__.__name__}: {exc}"
    return surface


def provider_probes_surface(transport: Optional[callable] = None) -> dict:
    """FIX 9 surface on capacity.probe(): a REDACTED summary of the provider
    inventory -- per provider {present, key_source, probed, ok, model_count}
    -- plus the 9Router wired lineups. NEVER carries a key value, NEVER makes
    a models call itself unless the transport is the live default and the
    flag is on: this surface exists so the FIX 30 intake and the report can
    say what the box owns without moving the storage to this path (storing
    stays with probe_providers(persist=True) / the profile). Errors never
    break the capacity probe."""
    surface: dict = {"flag": None, "providers": [], "ninerouter": None}
    try:
        if not probe_flag_enabled():
            surface["flag"] = "0"
            surface["detail"] = (f"provider probes disabled by {PROBE_FLAG_ENV}=0")
            return surface
        surface["flag"] = "1"
        probes = probe_providers(transport=transport)
        for provider, verdict in (probes.get("probes") or {}).items():
            surface["providers"].append({
                "provider": provider,
                "present": bool(verdict.get("present")),
                "key_source": verdict.get("key_source"),
                "probed": bool(verdict.get("probed")),
                "ok": bool(verdict.get("ok")),
                "model_count": len(verdict.get("models") or []),
            })
        lineup = probes.get("ninerouter") or {}
        surface["ninerouter"] = {
            "hit": bool(lineup.get("hit")),
            "total_models": lineup.get("total_models", 0),
            "providers": {prefix: {"label": info.get("label"),
                                   "models": info.get("models", [])}
                          for prefix, info in
                          (lineup.get("providers") or {}).items()},
            "detail": lineup.get("detail", ""),
        }
    except Exception as exc:  # noqa: BLE001 -- never break the capacity probe
        surface["error"] = f"{exc.__class__.__name__}: {exc}"
    return surface

def probe(config_dir: Optional[Path] = None) -> dict:
    """The main entry point. Read-only; never mutates anything, never exits.

    Signature-compatible with the previous version (`probe()` with no arguments
    is the call every existing caller makes). Returns the measured budget:

        available     int  -> the number of agents this account may run at once
        available     None -> the probe COULD NOT produce a number; the dispatch
                              path must refuse with AF-CAPACITY-UNMEASURED
    """
    resolution = detect(config_dir)
    working, method, ok = measure_working_concurrent()
    available = resolution["available"]
    result = {
        "probe_mode": PROBE_MODE,
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "status": resolution["status"],
        "undetermined": resolution["status"] == STATUS_UNDETERMINED,
        "provider": resolution["provider"],
        "plan": resolution["plan"],
        "detection_source": resolution["source"],
        "detection_trail": resolution["trail"],
        "override_path": resolution["override_path"],
        "default_conservative": DEFAULT_CONSERVATIVE,
        "cap_table": {f"{p}|{pl}": n for (p, pl), n in sorted(CAP_TABLE.items())},
        "dispatchable": available,
        "available": available,
        "reserve": 0,
        "interview_question": (interview_question(resolution["provider"])
                               if resolution["status"] == STATUS_PARKED else None),
        "autofail_code": AUTOFAIL_CODE if available is None else None,
        "notes": resolution.get("notes", []),
        "working_concurrent": working if ok else "UNMEASURED",
        "working_concurrent_method": method,
        "resource_profile": resource_profile_surface(config_dir,
                                                     resolution=resolution),
        "provider_probes": provider_probes_surface(),
    }
    return result


def available_or_none(result: dict):
    """The one accessor the dispatch path needs: a positive int, UNBOUNDED, or
    None. UNBOUNDED is a real measurement (a NO_CAP_PROVIDERS hit) and is
    returned as-is -- never coerced to None (that would PARK/refuse a
    bring-your-own-key provider that has nothing to be unmeasured about) and
    never coerced to a magic int (that would be exactly the defect this fix
    removes)."""
    if not isinstance(result, dict):
        return None
    value = result.get("available")
    if is_unbounded(value):
        return value
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def require_available(result: dict):
    """available_or_none(), but refuses instead of returning None. Returns a
    positive int OR the UNBOUNDED sentinel -- never a bare int guaranteed;
    callers that must loop/range/spawn a concrete count (never this module)
    are expected to branch on is_unbounded() first."""
    value = available_or_none(result)
    if value is None:
        raise CapacityUnmeasured(refusal_message(result))
    return value


def autofail_payload(result: dict) -> dict:
    """The machine-readable refusal the dispatch path emits. The literal AF code
    below is what registers this module against PIPELINE-MANIFEST.autofails."""
    status = (result or {}).get("status") if isinstance(result, dict) else None
    return {
        "code": "AF-CAPACITY-UNMEASURED",
        "status": status,
        "detection_source": (result or {}).get("detection_source"),
        "provider": (result or {}).get("provider"),
        "plan": (result or {}).get("plan"),
        "interview_question": (result or {}).get("interview_question"),
        "override_path": (result or {}).get("override_path"),
        "detail": refusal_message(result),
    }


def refusal_message(result: dict) -> str:
    """Why the probe could not produce a number, in one sentence."""
    if not isinstance(result, dict):
        return ("capacity probe returned no result object -- capacity is UNMEASURED "
                "and dispatch must not proceed")
    status = result.get("status")
    if status == STATUS_PARKED:
        return (f"capacity is PARKED: provider {result.get('provider')} was detected but "
                f"its plan is undeclared. Answer the interview question and the answer is "
                f"persisted to {result.get('override_path')} (asked ONCE): "
                f"{result.get('interview_question')}")
    if status == STATUS_FAILED:
        notes = "; ".join(result.get("notes") or []) or "the declared configuration is unusable"
        return f"capacity detection FAILED: {notes}"
    return (f"capacity probe produced no dispatchable number "
            f"(status={status!r}, available={result.get('available')!r})")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def format_report(result: dict) -> str:
    """Human-readable report + machine-greppable JSON block.

    Signature-compatible with the previous version. The JSON block guarantees the
    acceptance greps succeed:
      grep '"probe_mode"'  -> "probe_mode": "live"
      grep '"available"'   -> the cap for THIS account (or null when unmeasured)
    """
    lines = [
        "CAPACITY PROBE -- Presentations department (client-capacity detection)",
        f"Probe mode: {result.get('probe_mode')} (never SIMULATED)",
        f"Status: {result.get('status')}",
        f"Detection source: {result.get('detection_source')}",
        f"Provider: {result.get('provider') or 'UNKNOWN'}",
        f"Plan: {result.get('plan') or 'UNKNOWN'}",
    ]
    if result.get("status") == STATUS_UNDETERMINED:
        sources = ", ".join(
            f"{e.get('source')}({e.get('result')})" for e in result.get("detection_trail", [])
        )
        lines += [
            "",
            "!! UNDETERMINED -- no provider or plan could be determined from any source.",
            f"!! Sources checked: {sources}",
            f"!! Falling back to DEFAULT_CONSERVATIVE = {result.get('default_conservative')}. "
            "Capacity is NEVER guessed upward.",
            "",
        ]
    if result.get("status") == STATUS_PARKED:
        lines += [
            "",
            f"!! PARKED -- {AUTOFAIL_CODE}: provider known, plan undeclared. Dispatch "
            "must refuse until this is answered.",
            f"!! INTERVIEW QUESTION: {result.get('interview_question')}",
            f"!! The answer persists to {result.get('override_path')} -- asked ONCE, "
            "never every run.",
            "",
        ]
    if result.get("status") == STATUS_FAILED:
        lines += [
            "",
            f"!! FAILED -- {AUTOFAIL_CODE}: {refusal_message(result)}",
            "",
        ]
    available = result.get("available")
    lines += [
        f"Dispatchable: {available if available is not None else 'UNMEASURED'}",
        f"Reserve: {result.get('reserve')}",
        f"Effective available: {available if available is not None else 'UNMEASURED'}",
        (f"Working concurrent now: {result.get('working_concurrent')} "
         f"({result.get('working_concurrent_method')})"),
    ]
    for note in result.get("notes") or []:
        lines.append(f"Note: {note}")
    probes = result.get("provider_probes") or {}
    if probes.get("providers"):
        lines.append("Provider inventory (FIX 9 -- key presence, never a value):")
        for entry in probes["providers"]:
            lines.append(
                f"  {entry.get('provider')}: key present: "
                f"{'yes' if entry.get('present') else 'no'}"
                f"{'' if entry.get('present') else ''}"
                + (f" (source {entry.get('key_source')})" if entry.get("key_source") else "")
                + (f", {entry.get('model_count')} models unlocked"
                   if entry.get("probed") and entry.get("ok") else
                   ", models call not resolved" if entry.get("present") else ""))
    nine = probes.get("ninerouter") or {}
    if nine.get("hit"):
        lines.append(f"9Router lineup: {nine.get('total_models')} wired models "
                     f"across {len(nine.get('providers') or {})} provider aliases")
    lines.append("Detection trail:")
    for entry in result.get("detection_trail", []):
        lines.append(f"  ({entry.get('step')}) {entry.get('source')}: "
                     f"{entry.get('result')} -- {entry.get('detail')}")
    lines += ["", "=== JSON ===", json.dumps(result, indent=2, default=json_default)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capacity.py",
        description="Client-capacity detection -- detects, never guesses upward.",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Run the capacity probe and print the detected numbers (default).",
    )
    parser.add_argument(
        "--answer-plan", metavar="PLAN",
        help="Persist the capacity-interview answer (e.g. '$20', '$100', 'v4 Pro', "
             "'v4 Flash') to capacity_override.json so it is asked ONCE.",
    )
    parser.add_argument(
        "--provider", metavar="PROVIDER",
        help="Provider for --answer-plan; defaults to the detected provider.",
    )
    parser.add_argument(
        "--config-dir", metavar="DIR",
        help=f"Department config dir holding {OVERRIDE_FILENAME} "
             f"(default: ${CONFIG_DIR_ENV} or the department root).",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else None

    if args.answer_plan:
        provider = args.provider
        if not provider:
            provider = detect(config_dir).get("provider")
        if not provider:
            print("capacity: no provider detected and none given -- pass --provider "
                  f"(one of {sorted(PLANS_BY_PROVIDER)})", file=sys.stderr)
            return 2
        try:
            written = persist_plan_answer(provider, args.answer_plan, config_dir)
        except (ValueError, OSError) as exc:
            print(f"capacity: {exc}", file=sys.stderr)
            return 2
        print(f"capacity: recorded {provider} / {args.answer_plan} -> {written}")

    result = probe(config_dir)
    print(format_report(result))
    if available_or_none(result) is None:
        print(json.dumps(autofail_payload(result), indent=2), file=sys.stderr)
        return 3  # == state.EXIT_GATE_BLOCKED: measured nothing, so nothing dispatches
    return 0


if __name__ == "__main__":
    sys.exit(main())
