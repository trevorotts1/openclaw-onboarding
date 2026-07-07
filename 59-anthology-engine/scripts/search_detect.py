#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: search_detect.py
# THE WEB-SEARCH DETECTION LADDER (SPEC Section 9; Avatar Questions 31 and 32)
# -----------------------------------------------------------------------------
# Runs ONCE per box, caches the result to the client state directory, and
# re-detects on preflight. It answers ONE question for stage S1: "which enabled
# OpenClaw web-search tool does this box have, and do we PREFER Perplexity?"
#
# THE LADDER (SPEC 9, verbatim intent):
#   (1) enumerate the ENABLED OpenClaw web-search tools on the INSTALLED gateway
#       — LIVE availability, never mere config presence: a provider can be
#       CONFIGURED yet UNAVAILABLE because its plugin is not installed/enabled
#       (W0.4 recorded exactly this on the operator box: tools.web.search
#       provider perplexity "configured but unavailable"). Tool-registration
#       schemas DRIFT between gateway versions, so every brittle probe is behind
#       _probe_gateway() and the pure ladder consumes a NORMALIZED signals dict
#       (also injectable via --signals-file for tests and a cleaner integrator
#       probe). Detection = AVAILABILITY, not config-key presence.
#   (2) PREFER Perplexity when it is enabled AND available.
#   (3) else the best available enabled search tool (Ollama Cloud web search and
#       the client's other enabled options rank by quota state then recency).
#   (4) else NO TOOL: emit an HONEST limitation note for the operator run report,
#       fire ONE deduped founder Telegram flag through the OpenClaw gateway
#       (alert-dedup.py, gateway ONLY, fail-soft), and let the participant run
#       CONTINUE. Exit 3 here means "no tool — DEGRADE AND CONTINUE", it is NOT a
#       hold. (Wiring note: stage_s1_avatar.py must treat this script's exit 3 as
#       degrade-and-continue, reading the "continue": true field on stdout, NOT
#       as EX_HELD. See cross_file_needs.)
#
# WHAT THIS SCRIPT IS NOT: it does NOT itself call Perplexity or any provider —
# the actual search is a Layer 2 tool step the gateway/model runs at S1 time.
# This script DETECTS the tool, and provides the surrounding contract so the
# findings inject into pin aa-02 as CONTEXT (never editing the pinned prompt
# text) and so fabricated links are REFUSABLE by Gate B:
#   * build-context   -> wraps returned findings into the aa-02 context payload
#                        (injection_mode=context_only; the pinned text is never
#                        edited) with an explicit no-fabrication directive.
#   * record-findings -> persists the Layer-2 search-pass OUTPUT to the run dir
#                        as the canonical trace record.
#   * trace           -> read-only membership check a claim/link traces to that
#                        recorded output; a link NOT in the record is fabricated
#                        and Gate B Tier 1 check 10 (in qc-tier1-anthology.py)
#                        refuses it. GLM 5.2 does not search natively and the
#                        engine NEVER asks it to invent links.
#
# EXIT CODE CONTRACT (SPEC 3.4 row 5 for detect/resolve; auxiliary verbs below):
#   detect / resolve : 0 tool detected and cached ; 3 no tool (degrade+flag+CONTINUE)
#   build-context    : 0 context payload emitted   ; 2 bad input
#   record-findings  : 0 findings recorded         ; 2 bad input
#   trace            : 0 claim/link traces to the search pass ; 5 NOT traced (fabricated)
#   any verb         : 1 unexpected error ; 2 validation / bad invocation
#
# STDLIB ONLY (subprocess + urllib-free): zero third-party deps, calls NO model
# and NO paid provider (detection must never spend credits — furnace doctrine).
# DOCTRINE: move in silence (operator-verbose only; the founder flag is operator
# facing, the client is never messaged); zero disallowed vendor model ids in any
# runtime file; Convert and Flow naming in every client surface; NEVER print a
# secret value (labels resolve SET / NOT SET only); state writes run as the node
# user, never root; the engine NOTIFIES about provider state, never MODIFIES it.
# =============================================================================
"""search_detect.py — the Section 9 web-search detection ladder, cached per box."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes. detect/resolve honor SPEC 3.4 row 5 (0 tool, 3 no tool); the
# auxiliary verbs carry their own documented, non-conflicting codes.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VALIDATION = 2
EXIT_NO_TOOL = 3
EXIT_TRACE_MISS = 5

# Cache/record schema versions (bump only on a breaking shape change).
CACHE_SCHEMA = "1"
FINDINGS_SCHEMA = "1"
CONTEXT_SCHEMA = "1"

# ---------------------------------------------------------------------------
# Provider vocabulary. Canonical ids + an alias map so drift in how a gateway
# spells a provider never breaks selection. Only SEARCH-capable providers are
# eligible — a chat provider (deepseek/moonshot/etc.) must NEVER be mistaken for
# a search tool. The `tools.web.search.provider` config key is search by
# definition, so an UNKNOWN value there is still treated as search-capable.
# ---------------------------------------------------------------------------
SEARCH_CANON = {
    # perplexity family
    "perplexity": "perplexity", "pplx": "perplexity", "perplexity-ai": "perplexity",
    "perplexityai": "perplexity", "@openclaw/perplexity-plugin": "perplexity",
    # brave
    "brave": "brave-search", "brave-search": "brave-search", "brave_search": "brave-search",
    "bravesearch": "brave-search",
    # tavily / exa / serper / you / bing / google cse
    "tavily": "tavily", "exa": "exa", "exa-search": "exa",
    "serper": "serper", "serper-dev": "serper",
    "you": "you", "you.com": "you", "ydc": "you",
    "bing": "bing", "bing-search": "bing",
    "google": "google-cse", "google-cse": "google-cse", "google-search": "google-cse",
    "cse": "google-cse",
    # ollama cloud web search
    "ollama": "ollama-cloud", "ollama-cloud": "ollama-cloud", "ollama_cloud": "ollama-cloud",
    "ollama-web-search": "ollama-cloud", "ollamacloud": "ollama-cloud",
    # open-source / metasearch
    "searxng": "searxng", "searx": "searxng",
    "duckduckgo": "duckduckgo", "ddg": "duckduckgo",
}
# Providers we positively recognize as search-capable (canonical ids).
SEARCH_CAPABLE = frozenset(SEARCH_CANON.values())

# Common env label names per provider — a SOFT corroboration signal ONLY (a
# provider with no key SET cannot be usable). Values are NEVER read or printed;
# only os.environ membership (SET / NOT SET) is consulted. engine-config may
# extend/override this via web_search.provider_key_labels.
DEFAULT_KEY_LABELS = {
    "perplexity": ["PERPLEXITY_API_KEY", "PPLX_API_KEY"],
    "brave-search": ["BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"],
    "tavily": ["TAVILY_API_KEY"],
    "exa": ["EXA_API_KEY"],
    "serper": ["SERPER_API_KEY", "SERPER_DEV_API_KEY"],
    "you": ["YOU_API_KEY", "YDC_API_KEY"],
    "bing": ["BING_API_KEY", "BING_SEARCH_API_KEY"],
    "google-cse": ["GOOGLE_CSE_API_KEY", "GOOGLE_SEARCH_API_KEY"],
    "ollama-cloud": ["OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"],
    "searxng": [],       # self-hosted, usually keyless
    "duckduckgo": [],    # keyless
}

# The ONLY hard preference in the ladder is Perplexity (SPEC 9 step 2). Every
# other enabled provider is ranked by quota then recency then name. engine-config
# may EXTEND this list (web_search.prefer) but Perplexity stays first by default.
DEFAULT_PREFER = ["perplexity"]

# The gateway tool the Layer 2 search step invokes once a provider is selected.
GATEWAY_SEARCH_TOOL = "web_search"

# Heuristic parse of gateway warnings (drift-tolerant; regexes over the human
# message, overridable by injecting --signals-file). The cheap `plugins list`
# output already prints the config-warnings block instantly, so we do NOT rely on
# the heavy `openclaw doctor` call (it can exceed 45s on a real box — a furnace
# and latency hazard); doctor is opt-in via --deep. Matches lines like:
#   "web_search provider is not available: perplexity (configured plugin ...)"
#   "plugin not installed: brave — install the official external plugin ..."
_UNAVAIL_SEARCH_RE = re.compile(
    r"web[ _]?search provider is not available:\s*([a-z0-9@/._-]+)", re.IGNORECASE
)
_NOT_INSTALLED_RE = re.compile(
    r"plugin not installed:\s*([a-z0-9@/._-]+)", re.IGNORECASE
)
# Warning-line markers: when parsing NON-json plugin/config text, these lines
# describe absent providers and must NEVER be read as "installed".
_WARN_LINE_MARKERS = ("not available", "not installed", "install the official",
                      "install with", "openclaw plugins install", "unavailable")

# Candidate OpenClaw CLI locations (W0.4 recorded ~/.local/bin/openclaw and the
# npm-global bin). Resolution order: --openclaw-bin > $OPENCLAW_BIN > PATH > these.
_KNOWN_BIN_PATHS = (
    "~/.local/bin/openclaw",
    "~/.npm-global/bin/openclaw",
    "/usr/local/bin/openclaw",
    "/opt/homebrew/bin/openclaw",
)


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------
def now_utc() -> str:
    """ISO-8601 UTC, second precision, explicit offset (matches anthology_state)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canon_provider(name):
    """Canonicalize a provider spelling; unknowns pass through lowercased/trimmed."""
    if not name:
        return None
    s = str(name).strip().lower()
    return SEARCH_CANON.get(s, s)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _warn_if_root():
    """Doctrine: state writes run as the node user, never root. Warn (operator-
    side) but do not hard-block, so CI under assorted users still runs."""
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            sys.stderr.write("[search_detect] WARNING: running as root; the engine "
                             "writes state as the node user, never root.\n")
    except OSError:
        pass


def default_state_dir() -> Path:
    """Engine state directory (node-user owned), identical resolution to
    anthology_state.py: $ANTHOLOGY_STATE_DIR, else $OPENCLAW_DATA_DIR/..., else
    ~/.anthology-engine/state."""
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def cache_path(state_dir: Path) -> Path:
    return Path(state_dir) / "search-detect-cache.json"


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _atomic_write_json(path: Path, obj) -> None:
    """Write JSON atomically under the node user; create parents as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sd-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _env_label_set(labels) -> bool:
    """True if ANY of the given env labels is present and non-empty. NEVER prints
    or returns the value (doctrine: SET / NOT SET only)."""
    for name in labels or ():
        v = os.environ.get(name, "")
        if v and v.strip():
            return True
    return False


def _run_cli(argv, timeout):
    """Run a CLI probe, fail-soft. Returns (rc, stdout, stderr); rc is None if the
    binary is missing or the call timed out. Never raises, never spends credits."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        return None, "", ""


def _resolve_openclaw_bin(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        return str(p) if p.exists() else explicit
    env = os.environ.get("OPENCLAW_BIN", "").strip()
    if env and Path(env).expanduser().exists():
        return str(Path(env).expanduser())
    which = shutil.which("openclaw")
    if which:
        return which
    for cand in _KNOWN_BIN_PATHS:
        p = Path(cand).expanduser()
        if p.exists():
            return str(p)
    return None


# ---------------------------------------------------------------------------
# CONFIG. engine-config.template.json currently carries NO web_search block; we
# read one defensively if present and fall back to built-in defaults otherwise
# (see cross_file_needs for the optional block the integrator may add).
# ---------------------------------------------------------------------------
def load_web_search_config(config_path):
    cfg = _read_json(config_path) if config_path else None
    ws = {}
    if isinstance(cfg, dict):
        ws = cfg.get("web_search") or cfg.get("search_detect") or {}
        if not isinstance(ws, dict):
            ws = {}
    prefer = ws.get("prefer")
    if not isinstance(prefer, list) or not prefer:
        prefer = list(DEFAULT_PREFER)
    prefer = [canon_provider(p) for p in prefer if p]
    key_labels = dict(DEFAULT_KEY_LABELS)
    extra = ws.get("provider_key_labels")
    if isinstance(extra, dict):
        for prov, labels in extra.items():
            cp = canon_provider(prov)
            if isinstance(labels, list):
                key_labels[cp] = list(labels)
            elif isinstance(labels, str):
                key_labels[cp] = [labels]
    return {
        "prefer": prefer,
        "key_labels": key_labels,
        # When live availability is inconclusive, may we fall back to a provider
        # that is explicitly CONFIGURED and has a key SET? Default yes, but marked
        # confidence=config-inferred so the operator can verify.
        "allow_config_inferred": bool(ws.get("allow_config_inferred", True)),
        # box-level dedup scope for the founder flag (SPEC 9: ONE flag).
        "flag_dedup_scope": ws.get("flag_dedup_scope", "box"),
    }


# ---------------------------------------------------------------------------
# GATEWAY PROBE. Every brittle, drift-prone call lives here. It returns a
# NORMALIZED signals dict the pure ladder consumes. --signals-file bypasses this
# entirely so the ladder is deterministically testable and the integrator can
# supply a cleaner probe without touching selection logic.
# ---------------------------------------------------------------------------
def _probe_config(bin_path, evidence):
    """Read tools.web.search config -> (configured_provider, [configured_providers])."""
    configured, providers = None, []
    if not bin_path:
        return configured, providers
    for argv in (
        [bin_path, "config", "get", "tools.web.search", "--json"],
        [bin_path, "config", "get", "tools.web.search"],
        [bin_path, "config", "get", "tools.web.search.provider"],
    ):
        rc, out, _ = _run_cli(argv, timeout=10)
        if rc is None or not out.strip():
            continue
        raw = out.strip()
        parsed = None
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw.strip().strip('"').strip()
        if isinstance(parsed, dict):
            configured = parsed.get("provider") or configured
            for k in ("providers", "fallback", "fallbacks", "order"):
                v = parsed.get(k)
                if isinstance(v, list):
                    providers.extend(str(x) for x in v)
            evidence.append("config:tools.web.search(dict)")
            break
        if isinstance(parsed, str) and parsed and parsed.lower() not in ("null", "none", ""):
            configured = parsed
            evidence.append("config:tools.web.search.provider=<set>")
            break
    if configured:
        providers.append(configured)
    return configured, providers


def _unavail_from_blob(blob):
    """Extract UNAVAILABLE search providers from any gateway warnings blob:
    the explicit 'web_search provider is not available: X' line, plus any
    'plugin not installed: X' where X is a search-capable provider."""
    unavailable = set()
    for m in _UNAVAIL_SEARCH_RE.finditer(blob):
        cp = canon_provider(m.group(1))
        if cp:
            unavailable.add(cp)
    for m in _NOT_INSTALLED_RE.finditer(blob):
        cp = canon_provider(m.group(1))
        if cp in SEARCH_CAPABLE:
            unavailable.add(cp)
    return unavailable


def _probe_warnings(bin_path, evidence):
    """CHEAP availability harvest. The NON-json `plugins list` prints the gateway's
    Doctor/Config warnings block instantly (no --fix, no network), which carries
    the authoritative 'web_search provider is not available: X' line. This is the
    reliable availability signal; `openclaw doctor` is too slow to run routinely."""
    unavailable = set()
    if not bin_path:
        return unavailable
    rc, out, err = _run_cli([bin_path, "plugins", "list"], timeout=15)
    blob = (out or "") + "\n" + (err or "")
    if rc is None and not blob.strip():
        return unavailable
    unavailable |= _unavail_from_blob(blob)
    if unavailable:
        evidence.append("warnings:unavailable=%s" % ",".join(sorted(unavailable)))
    elif blob.strip():
        evidence.append("warnings:parsed(no-unavailable-lines)")
    return unavailable


def _probe_doctor(bin_path, evidence):
    """OPT-IN deep probe: parse `openclaw doctor` for availability warnings. Slow
    and heavy (can exceed 45s), so only called under --deep; a timeout contributes
    nothing (fail-soft) and the cheap warnings harvest already covers this."""
    unavailable = set()
    if not bin_path:
        return unavailable
    rc, out, err = _run_cli([bin_path, "doctor"], timeout=25)
    blob = (out or "") + "\n" + (err or "")
    if rc is None and not blob.strip():
        evidence.append("doctor:timed-out-or-empty(ignored)")
        return unavailable
    unavailable |= _unavail_from_blob(blob)
    if unavailable:
        evidence.append("doctor:unavailable=%s" % ",".join(sorted(unavailable)))
    return unavailable


def _probe_plugins(bin_path, evidence):
    """List installed plugins -> search-capable provider ids present as plugins.
    Prefers `--json` (a clean install list, no warning noise). The non-json text
    fallback SKIPS warning lines (which name ABSENT providers) so a not-installed
    provider mentioned in a warning is never miscounted as installed."""
    found = set()
    if not bin_path:
        return found
    # 1) JSON list: clean and authoritative when supported.
    rc, out, _ = _run_cli([bin_path, "plugins", "list", "--json"], timeout=10)
    if rc is not None and out.strip():
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if data is not None:
            for tok in _json_string_tokens(data):
                cp = canon_provider(tok)
                if cp in SEARCH_CAPABLE:
                    found.add(cp)
            evidence.append("plugins:list(json)")
            if found:
                evidence.append("plugins:search-capable=%s" % ",".join(sorted(found)))
            return found
    # 2) Text fallback: parse line by line, skipping warning lines.
    for argv in ([bin_path, "plugins", "list"], [bin_path, "plugin", "list"]):
        rc, out, _ = _run_cli(argv, timeout=10)
        if rc is None or not out.strip():
            continue
        for line in out.splitlines():
            low = line.lower()
            if any(mark in low for mark in _WARN_LINE_MARKERS):
                continue
            for t in re.split(r"[\s,\"'\[\]{}():|│]+", low):
                cp = canon_provider(t)
                if cp in SEARCH_CAPABLE:
                    found.add(cp)
        evidence.append("plugins:list(text)")
        break
    if found:
        evidence.append("plugins:search-capable=%s" % ",".join(sorted(found)))
    return found


def _json_string_tokens(obj):
    """Yield string tokens from a parsed JSON structure (keys and scalar values)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from _json_string_tokens(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _json_string_tokens(it)
    elif isinstance(obj, str):
        yield obj


def _probe_keys(providers, key_labels, evidence):
    """SOFT signal: which candidate providers have a key label SET (never value)."""
    present = {}
    for prov in providers:
        present[prov] = _env_label_set(key_labels.get(prov, []))
    if any(present.values()):
        evidence.append("env:key-labels-present=%s"
                        % ",".join(sorted(p for p, v in present.items() if v)))
    return present


def probe_gateway(bin_path, cfg, deep=False):
    """Compose a NORMALIZED signals dict from all live probes. Fail-soft: any
    absent/failed probe simply contributes nothing; the ladder degrades honestly
    when availability cannot be established (availability, not config presence).
    `deep` additionally runs the heavy `openclaw doctor` probe (opt-in)."""
    evidence = []
    version = None
    if bin_path:
        rc, out, _ = _run_cli([bin_path, "--version"], timeout=8)
        if rc == 0 and out.strip():
            version = out.strip().splitlines()[0][:40]

    configured, configured_providers = _probe_config(bin_path, evidence)
    unavailable = _probe_warnings(bin_path, evidence)   # cheap, authoritative
    if deep:
        unavailable |= _probe_doctor(bin_path, evidence)
    plugin_providers = _probe_plugins(bin_path, evidence)

    # Candidate universe = configured providers (search by definition) + any
    # search-capable plugins. Canonicalize and keep search-capable (an unknown
    # value that came from tools.web.search is kept — that key IS search).
    candidates = set()
    for p in configured_providers:
        cp = canon_provider(p)
        if cp:
            candidates.add(cp)          # configured => trusted as search-intent
    candidates |= set(plugin_providers)
    # Available = candidates MINUS the warning-reported unavailable set (a
    # configured-but-unavailable provider, e.g. an uninstalled plugin, is excluded).
    available = sorted(c for c in candidates if c not in unavailable)

    key_present = _probe_keys(sorted(candidates), cfg["key_labels"], evidence)

    probe_ok = bool(bin_path) and bool(evidence)
    return {
        "gateway_version": version,
        "probe_ok": probe_ok,
        "configured_provider": canon_provider(configured),
        "configured_providers": sorted({canon_provider(p) for p in configured_providers if p}),
        "available": available,
        "unavailable": sorted(unavailable),
        "installed_plugins": sorted(plugin_providers),
        "key_present": key_present,
        "quota": {},        # detection never spends credits to probe live quota
        "recency": {},      # optional; supplied via --signals-file if known
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# THE PURE LADDER. Given normalized signals + config, decide the tool. No I/O,
# fully unit-testable. This is the SPEC Section 9 selection policy.
# ---------------------------------------------------------------------------
def run_ladder(signals, cfg):
    prefer = cfg.get("prefer") or list(DEFAULT_PREFER)
    available = list(dict.fromkeys(canon_provider(p) for p in signals.get("available") or []))
    unavailable = set(signals.get("unavailable") or [])
    key_present = signals.get("key_present") or {}
    quota = signals.get("quota") or {}
    recency = signals.get("recency") or {}
    trace = []

    # Confidence: LIVE if we positively established availability; config-inferred
    # if availability was inconclusive but a configured provider has a key SET.
    confidence = "live"

    usable = []
    for prov in available:
        # A provider with quota explicitly "out" is unusable right now.
        if quota.get(prov) == "out":
            trace.append("drop %s: quota out" % prov)
            continue
        # A provider we KNOW has no key label set (and is not keyless) is unusable.
        needs_key = bool(DEFAULT_KEY_LABELS.get(prov, ["_"]))  # [] => keyless
        if prov in key_present and key_present[prov] is False and needs_key:
            trace.append("drop %s: no key label SET" % prov)
            continue
        usable.append(prov)

    # If live availability was inconclusive, optionally fall back to a CONFIGURED
    # provider whose key is SET (client explicitly chose it and supplied a key).
    if not usable and not signals.get("probe_ok") and cfg.get("allow_config_inferred", True):
        for prov in signals.get("configured_providers") or []:
            cp = canon_provider(prov)
            if cp in unavailable:
                continue
            if _key_ok(cp, key_present):
                usable.append(cp)
                confidence = "config-inferred"
                trace.append("config-inferred %s: availability inconclusive, "
                             "configured + key SET" % cp)

    if not usable:
        checked = sorted(set(available) | unavailable
                         | set(signals.get("configured_providers") or []))
        trace.append("no usable search tool (checked: %s)" % (", ".join(checked) or "none"))
        return {
            "tool": None,
            "provider": None,
            "degraded": True,
            "continue": True,       # SPEC 9 step 4: the participant run CONTINUES
            "confidence": confidence,
            "checked": checked,
            "unavailable": sorted(unavailable),
            "ladder_trace": trace,
        }

    def rank_key(prov):
        pref_rank = prefer.index(prov) if prov in prefer else len(prefer) + 1
        quota_rank = {"ok": 0, None: 1, "low": 2}.get(quota.get(prov), 1)
        # recency: newer first -> invert the ISO string ordering
        rec = recency.get(prov) or ""
        return (pref_rank, quota_rank, _neg_str(rec), prov)

    usable.sort(key=rank_key)
    chosen = usable[0]
    trace.append("selected %s (prefer=%s available=%s)"
                 % (chosen, prefer, usable))

    # The gateway's web_search tool actually calls tools.web.search.provider. When
    # the tool we SELECTED differs from that configured provider — because the
    # configured one is unavailable, or because a preferred provider outranks it —
    # the operator must align config for the Layer 2 step to use our choice.
    # Detection NEVER modifies config (sovereignty: alarms notify, never modify).
    effective = signals.get("configured_provider")
    provisioning_note = None
    if effective and effective != chosen:
        if effective in unavailable:
            provisioning_note = (
                "The gateway's configured tools.web.search.provider is %r but it is "
                "UNAVAILABLE on this box (plugin not installed/enabled); detection "
                "selected the best available tool %r instead. Install/enable %r or "
                "repoint the config to %r so the Layer 2 search step uses a live "
                "provider. Detection never modifies config."
                % (effective, chosen, effective, chosen)
            )
        elif chosen in prefer and prefer.index(chosen) == 0:
            provisioning_note = (
                "Preferred provider %r is available but the gateway's configured "
                "tools.web.search.provider is %r; to make the Layer 2 search step USE "
                "%r, provisioning should set that config. Detection never modifies it."
                % (chosen, effective, chosen)
            )

    return {
        "tool": chosen,
        "provider": chosen,
        "gateway_tool": GATEWAY_SEARCH_TOOL,
        "degraded": False,
        "continue": True,
        "confidence": confidence,
        "preferred": chosen in prefer,
        "effective_gateway_provider": effective,
        "provisioning_note": provisioning_note,
        "ladder_trace": trace,
    }


def _key_ok(prov, key_present):
    needs_key = bool(DEFAULT_KEY_LABELS.get(prov, ["_"]))
    if not needs_key:
        return True
    return bool(key_present.get(prov))


def _neg_str(s):
    """Sort helper: make lexicographically-larger strings sort FIRST (newer ISO
    timestamp first) without reversing the whole tuple."""
    return tuple(-ord(c) for c in s)


# ---------------------------------------------------------------------------
# HONEST LIMITATION NOTE (operator run report; never a client surface).
# ---------------------------------------------------------------------------
def honest_note(decision):
    checked = ", ".join(decision.get("checked") or []) or "none detected"
    return (
        "WEB SEARCH UNAVAILABLE on this box: no enabled OpenClaw web-search "
        "provider was detected (checked: %s). Avatar Questions 31 and 32 were "
        "produced from Questions 1 to 30 only, WITHOUT live external research. "
        "No links were fabricated; any research-shaped claim without a real "
        "source is omitted and would be refused by Gate B. The participant run "
        "continued normally." % checked
    )


# ---------------------------------------------------------------------------
# aa-02 CONTEXT INJECTION. The pinned prompt aa-02 (Avatar Questions 31/32) is
# sha256-pinned and NEVER edited at runtime. Findings are supplied as ADDITIVE
# CONTEXT the composer places alongside the pinned text (e.g. a preceding
# context turn or a {{research_context}} compose slot), carrying an explicit
# no-fabrication directive. This is the surface Gate B check 10 leans on.
# ---------------------------------------------------------------------------
_NO_FAB_DIRECTIVE = (
    "Use ONLY the sources listed below as live research for Avatar Questions 31 "
    "and 32. Do NOT invent, guess, or infer any URL. Every external claim must "
    "cite one of these sources verbatim; if a claim has no source here, omit it. "
    "Fabricated or uncited links are rejected by content QC."
)


def build_context(findings, decision):
    """Return the aa-02 context payload. `findings` is a list of
    {claim, url, source_title, retrieved_at}. Degraded (no tool) -> empty sources
    plus a note that no live research was available (still no fabrication)."""
    items = _normalize_findings(findings)
    degraded = bool(decision.get("degraded")) or not items
    lines = [_NO_FAB_DIRECTIVE, ""]
    if items:
        lines.append("LIVE RESEARCH SOURCES (tool: %s):" % (decision.get("tool") or "n/a"))
        for i, it in enumerate(items, 1):
            src = it.get("source_title") or it.get("url") or "source"
            lines.append("  [%d] %s — %s" % (i, src, it.get("url") or ""))
            if it.get("claim"):
                lines.append("      claim: %s" % it["claim"])
    else:
        lines.append("NO LIVE RESEARCH SOURCES were available on this box. Answer "
                     "Avatar Questions 31 and 32 from Questions 1 to 30 only and "
                     "cite no external links.")
    return {
        "schema": CONTEXT_SCHEMA,
        "pin": "aa-02",
        "injection_mode": "context_only",   # the pinned prompt text is never edited
        "degraded": degraded,
        "tool": decision.get("tool"),
        "directive": _NO_FAB_DIRECTIVE,
        "sources": items,
        "rendered": "\n".join(lines),
        "built_at": now_utc(),
    }


def _normalize_findings(findings):
    out = []
    if isinstance(findings, dict):
        findings = findings.get("items") or findings.get("sources") or findings.get("findings") or []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        url = (f.get("url") or f.get("link") or "").strip()
        item = {
            "url": url,
            "source_title": (f.get("source_title") or f.get("title") or "").strip(),
            "claim": (f.get("claim") or f.get("text") or "").strip(),
            "retrieved_at": (f.get("retrieved_at") or "").strip(),
        }
        if url or item["claim"]:
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# SEARCH-PASS TRACE RECORD (the canonical Layer-2 output Gate B check 10 traces
# claims against). Persisted per run so a fabricated link — one not present in
# the record — is detectable and refusable.
# ---------------------------------------------------------------------------
def findings_record_path(run_dir):
    return Path(run_dir) / "search-findings.json"


def record_findings(run_dir, tool, query, findings):
    items = _normalize_findings(findings)
    rec = {
        "schema": FINDINGS_SCHEMA,
        "tool": tool,
        "query": query or "",
        "recorded_at": now_utc(),
        "items": items,
        "urls": sorted({_norm_url(it["url"]) for it in items if it.get("url")}),
    }
    _atomic_write_json(findings_record_path(run_dir), rec)
    return rec


def _norm_url(url):
    """Deterministic URL normalization for trace membership: scheme-insensitive,
    host lowercased, fragment dropped, trailing slash on the path removed. Kept
    conservative so a fabricated link cannot accidentally match a real one."""
    if not url:
        return ""
    s = url.strip()
    s = re.sub(r"#.*$", "", s)                      # drop fragment
    s = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", "", s)  # drop scheme
    if "/" in s:
        host, rest = s.split("/", 1)
        s = host.lower() + "/" + rest
    else:
        s = s.lower()
    s = re.sub(r"/+$", "", s)                        # drop trailing slash(es)
    return s


def trace_claim(run_dir, url=None, claim=None):
    rec = _read_json(findings_record_path(run_dir))
    if not isinstance(rec, dict):
        return {"traced": False, "reason": "no search-findings record for this run",
                "run_dir": str(run_dir)}
    if url:
        target = _norm_url(url)
        known = set(rec.get("urls") or [])
        if not known:
            known = {_norm_url(it.get("url")) for it in rec.get("items") or [] if it.get("url")}
        traced = target in known and bool(target)
        return {"traced": traced, "url": url,
                "reason": "url present in search pass output" if traced
                          else "url NOT in search pass output (fabricated/untraceable)"}
    if claim:
        needle = " ".join(claim.lower().split())
        for it in rec.get("items") or []:
            hay = " ".join((it.get("claim") or "").lower().split())
            if needle and (needle in hay or hay in needle):
                return {"traced": True, "claim": claim,
                        "reason": "claim matches a recorded finding"}
        return {"traced": False, "claim": claim,
                "reason": "claim does not match any recorded finding"}
    return {"traced": False, "reason": "provide --url or --claim to trace"}


# ---------------------------------------------------------------------------
# THE ONE DEDUPED FOUNDER FLAG (SPEC 9 step 4). Fired ONLY through the OpenClaw
# gateway via alert-dedup.py (Telegram is NEVER called directly). Fail-soft: if
# alert-dedup.py is not yet present or errors, the flag is best-effort and the
# run STILL degrades and continues. A cache marker guarantees ONE flag per box
# even if the alert-dedup dedup state is reset.
# ---------------------------------------------------------------------------
def _alert_dedup_path():
    p = Path(__file__).resolve().parent / "alert-dedup.py"
    return p if p.exists() else None


def _flag_dedup_key(cfg, anthology_id):
    if cfg.get("flag_dedup_scope") == "anthology" and anthology_id:
        return "search_detect:no_search_tool:%s" % anthology_id
    return "search_detect:no_search_tool"


def fire_founder_flag(cfg, anthology_id, decision, prior_cache, suppress=False):
    key = _flag_dedup_key(cfg, anthology_id)
    # Belt-and-suspenders dedup: if we already fired for this key and no tool has
    # since appeared, do not fire again.
    prior = (prior_cache or {}).get("flag") if isinstance(prior_cache, dict) else None
    if isinstance(prior, dict) and prior.get("fired") and prior.get("dedup_key") == key:
        return {"fired": False, "suppressed": True, "dedup_key": key,
                "reason": "already flagged for this box; deduped"}
    if suppress:
        return {"fired": False, "suppressed": True, "dedup_key": key,
                "reason": "flag suppressed by caller (--no-flag)"}
    script = _alert_dedup_path()
    if not script:
        return {"fired": False, "dedup_key": key, "delivered": False,
                "reason": "alert-dedup.py not present yet; flag is best-effort (fail-soft)"}
    body = ("Anthology Engine: web search unavailable on this box. Avatar Questions "
            "31 and 32 will run without live research (no links fabricated). Install "
            "or enable a search provider (Perplexity preferred) to restore research.")
    argv = [sys.executable, str(script),
            "--dedup-key", key,
            "--subject", "Anthology Engine: web search unavailable",
            "--body", body, "--severity", "warning"]
    rc, _out, _err = _run_cli(argv, timeout=20)
    delivered = rc == 0
    return {"fired": True, "dedup_key": key, "delivered": delivered,
            "reason": ("founder flag sent via gateway (alert-dedup.py)" if delivered
                       else "alert-dedup.py returned rc=%s; flag best-effort" % rc)}


# ---------------------------------------------------------------------------
# CACHE / DETECT / RESOLVE.
# ---------------------------------------------------------------------------
def _config_path(args):
    if args.config:
        return Path(args.config).expanduser()
    p = Path(__file__).resolve().parent.parent / "config" / "engine-config.json"
    if p.exists():
        return p
    t = Path(__file__).resolve().parent.parent / "config" / "engine-config.template.json"
    return t if t.exists() else None


def _load_signals(args, cfg):
    if args.signals_file:
        sig = _read_json(Path(args.signals_file).expanduser())
        if not isinstance(sig, dict):
            raise ValueError("--signals-file did not contain a JSON object")
        sig.setdefault("evidence", ["injected:--signals-file"])
        sig.setdefault("probe_ok", True)
        sig.setdefault("available", sig.get("available") or [])
        sig.setdefault("configured_providers", sig.get("configured_providers") or [])
        sig.setdefault("unavailable", sig.get("unavailable") or [])
        sig.setdefault("key_present", sig.get("key_present") or {})
        return sig
    bin_path = _resolve_openclaw_bin(args.openclaw_bin)
    return probe_gateway(bin_path, cfg, deep=getattr(args, "deep", False))


def build_cache_record(signals, decision):
    return {
        "schema": CACHE_SCHEMA,
        "detected_at": now_utc(),
        "gateway_version": signals.get("gateway_version"),
        "degraded": bool(decision.get("degraded")),
        "tool": decision.get("tool"),
        "provider": decision.get("provider"),
        "gateway_tool": decision.get("gateway_tool"),
        "confidence": decision.get("confidence"),
        "effective_gateway_provider": decision.get("effective_gateway_provider"),
        "provisioning_note": decision.get("provisioning_note"),
        "signals_summary": {
            "probe_ok": signals.get("probe_ok"),
            "configured_provider": signals.get("configured_provider"),
            "available": signals.get("available"),
            "unavailable": signals.get("unavailable"),
            "installed_plugins": signals.get("installed_plugins"),
            "evidence": signals.get("evidence"),
        },
        "ladder_trace": decision.get("ladder_trace"),
    }


def cmd_detect(args):
    _warn_if_root()
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else default_state_dir()
    cfg = load_web_search_config(_config_path(args))
    prior = _read_json(cache_path(state_dir))

    signals = _load_signals(args, cfg)
    decision = run_ladder(signals, cfg)
    record = build_cache_record(signals, decision)

    if decision.get("degraded"):
        note = honest_note(decision)
        record["honest_note"] = note
        flag = fire_founder_flag(cfg, args.anthology_id, decision, prior,
                                 suppress=args.no_flag)
        record["flag"] = flag
        if args.run_report:
            _append_run_report(args.run_report, note, flag)
    else:
        # a tool re-appeared: clear any stale flag marker so a FUTURE regression
        # re-alerts exactly once.
        record["flag"] = {"fired": False, "dedup_key": _flag_dedup_key(cfg, args.anthology_id),
                          "reason": "search tool available; no flag needed"}

    _atomic_write_json(cache_path(state_dir), record)
    out = dict(decision)
    out["cache_path"] = str(cache_path(state_dir))
    if decision.get("degraded"):
        out["honest_note"] = record.get("honest_note")
        out["flag"] = record.get("flag")
    _emit(args, out)
    return EXIT_NO_TOOL if decision.get("degraded") else EXIT_OK


def cmd_resolve(args):
    """Read the cached detection for the runtime (stage S1). Re-detects only when
    the cache is missing, forced, or older than --max-age-seconds."""
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else default_state_dir()
    record = _read_json(cache_path(state_dir))
    stale = record is None or args.force
    if record is not None and args.max_age_seconds and record.get("detected_at"):
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(record["detected_at"])).total_seconds()
            stale = stale or age > args.max_age_seconds
        except ValueError:
            stale = True
    if stale:
        return cmd_detect(args)
    out = {
        "tool": record.get("tool"),
        "provider": record.get("provider"),
        "gateway_tool": record.get("gateway_tool"),
        "degraded": bool(record.get("degraded")),
        "continue": True,
        "confidence": record.get("confidence"),
        "from_cache": True,
        "detected_at": record.get("detected_at"),
        "cache_path": str(cache_path(state_dir)),
    }
    if record.get("degraded"):
        out["honest_note"] = record.get("honest_note")
    _emit(args, out)
    return EXIT_NO_TOOL if record.get("degraded") else EXIT_OK


def _append_run_report(path, note, flag):
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("\n[%s] search_detect: %s\n" % (now_utc(), note))
            fh.write("  founder flag: %s\n" % json.dumps(flag, sort_keys=True))
    except OSError as exc:
        sys.stderr.write("[search_detect] could not append run report: %s\n" % exc)


# ---------------------------------------------------------------------------
# AUXILIARY VERBS: build-context, record-findings, trace.
# ---------------------------------------------------------------------------
def _load_findings_arg(args):
    if args.findings_file:
        data = _read_json(Path(args.findings_file).expanduser())
        if data is None:
            raise ValueError("--findings-file is missing or not valid JSON")
        return data
    if getattr(args, "stdin", False) or (not sys.stdin.isatty()):
        raw = sys.stdin.read().strip()
        if raw:
            try:
                return json.loads(raw)
            except ValueError:
                raise ValueError("stdin was not valid JSON findings")
    return []


def cmd_build_context(args):
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else default_state_dir()
    record = _read_json(cache_path(state_dir)) or {}
    decision = {"tool": record.get("tool"), "degraded": bool(record.get("degraded", True))}
    findings = _load_findings_arg(args)
    ctx = build_context(findings, decision)
    if args.run_dir and ctx["sources"]:
        record_findings(args.run_dir, decision.get("tool"), args.query, findings)
        ctx["recorded_to"] = str(findings_record_path(args.run_dir))
    _emit(args, ctx)
    return EXIT_OK


def cmd_record_findings(args):
    if not args.run_dir:
        sys.stderr.write("[search_detect] record-findings requires --run-dir\n")
        return EXIT_VALIDATION
    findings = _load_findings_arg(args)
    rec = record_findings(args.run_dir, args.tool, args.query, findings)
    _emit(args, {"ok": True, "recorded_to": str(findings_record_path(args.run_dir)),
                 "count": len(rec["items"])})
    return EXIT_OK


def cmd_trace(args):
    if not args.run_dir:
        sys.stderr.write("[search_detect] trace requires --run-dir\n")
        return EXIT_VALIDATION
    if not (args.url or args.claim):
        sys.stderr.write("[search_detect] trace requires --url or --claim\n")
        return EXIT_VALIDATION
    result = trace_claim(args.run_dir, url=args.url, claim=args.claim)
    _emit(args, result)
    return EXIT_OK if result.get("traced") else EXIT_TRACE_MISS


def cmd_plan(args):
    cfg = load_web_search_config(_config_path(args))
    bin_path = _resolve_openclaw_bin(args.openclaw_bin)
    info = {
        "script": "search_detect.py",
        "ladder": [
            "1. enumerate ENABLED search tools on the INSTALLED gateway (live availability, not config presence)",
            "2. PREFER Perplexity when enabled and available",
            "3. else best available (quota, then recency, then name)",
            "4. else NO TOOL: honest note + ONE deduped founder flag + CONTINUE (exit 3)",
        ],
        "prefer": cfg["prefer"],
        "openclaw_bin": bin_path or "NOT FOUND (probe will be inconclusive -> degrade)",
        "state_dir": str(default_state_dir()),
        "cache_path": str(cache_path(default_state_dir())),
        "exit_contract": {"detect/resolve": "0 tool, 3 no-tool (degrade+continue)",
                          "trace": "0 traced, 5 not-traced (fabricated)"},
        "search_capable_providers": sorted(SEARCH_CAPABLE),
    }
    _emit(args, info)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Output.
# ---------------------------------------------------------------------------
def _emit(args, obj):
    if getattr(args, "pretty", False):
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------------------
# SELF-TEST: the pure ladder + canonicalization + trace + context, on injected
# signals in a temp dir. No gateway, no network, no credentials, no spend.
# ---------------------------------------------------------------------------
def self_test():
    base_cfg = {"prefer": ["perplexity"], "key_labels": DEFAULT_KEY_LABELS,
                "allow_config_inferred": True, "flag_dedup_scope": "box"}

    # canonicalization
    assert canon_provider("PPLX") == "perplexity"
    assert canon_provider("brave_search") == "brave-search"
    assert canon_provider("Ollama-Cloud") == "ollama-cloud"

    # 1. perplexity available among others -> perplexity wins (SPEC step 2)
    d = run_ladder({"probe_ok": True, "available": ["ollama-cloud", "perplexity", "tavily"],
                    "key_present": {"perplexity": True, "ollama-cloud": True, "tavily": True}},
                   base_cfg)
    assert d["tool"] == "perplexity" and d["degraded"] is False, d

    # 2. W0.4 real case: perplexity CONFIGURED but UNAVAILABLE; ollama available
    d = run_ladder({"probe_ok": True, "configured_provider": "perplexity",
                    "configured_providers": ["perplexity"],
                    "available": ["ollama-cloud"], "unavailable": ["perplexity"],
                    "key_present": {"ollama-cloud": True}}, base_cfg)
    assert d["tool"] == "ollama-cloud" and d["degraded"] is False, d
    # the operator provisioning note must flag the unavailable configured provider
    assert d["provisioning_note"] and "UNAVAILABLE" in d["provisioning_note"], d

    # 2b. warnings-blob parsing (the reliable availability signal) + JSON tokens
    blob = ('tools.web.search.provider: web_search provider is not available:\n'
            '    perplexity (configured plugin "perplexity" is unavailable)\n'
            '  - plugins.entries.brave: plugin not installed: brave — install ...\n')
    ua = _unavail_from_blob(blob)
    assert "perplexity" in ua and "brave-search" in ua, ua
    toks = set(_json_string_tokens({"plugins": [{"id": "ollama-cloud"}, {"id": "notes"}]}))
    assert "ollama-cloud" in toks

    # 3. nothing available -> degrade + continue + honest note, exit-3 semantics
    d = run_ladder({"probe_ok": True, "available": [], "unavailable": ["perplexity"],
                    "configured_providers": ["perplexity"], "key_present": {}}, base_cfg)
    assert d["degraded"] is True and d["continue"] is True and d["tool"] is None, d
    note = honest_note(d)
    assert "WITHOUT live external research" in note and "fabricat" in note.lower()

    # 4. quota out drops the top provider
    d = run_ladder({"probe_ok": True, "available": ["perplexity", "tavily"],
                    "quota": {"perplexity": "out", "tavily": "ok"},
                    "key_present": {"perplexity": True, "tavily": True}}, base_cfg)
    assert d["tool"] == "tavily", d

    # 5. availability inconclusive + configured + key SET -> config-inferred
    d = run_ladder({"probe_ok": False, "available": [],
                    "configured_providers": ["perplexity"],
                    "key_present": {"perplexity": True}}, base_cfg)
    assert d["tool"] == "perplexity" and d["confidence"] == "config-inferred", d

    # 5b. inconclusive + configured but NO key -> still degrade
    d = run_ladder({"probe_ok": False, "available": [],
                    "configured_providers": ["perplexity"],
                    "key_present": {"perplexity": False}}, base_cfg)
    assert d["degraded"] is True, d

    # 6. recency tiebreak among equal-preference providers (newer first)
    d = run_ladder({"probe_ok": True, "available": ["tavily", "exa"],
                    "key_present": {"tavily": True, "exa": True},
                    "recency": {"tavily": "2026-01-01", "exa": "2026-07-01"}}, base_cfg)
    assert d["tool"] == "exa", d

    # 7. URL normalization + trace membership (fabricated link refused)
    assert _norm_url("HTTPS://Example.com/Path/") == "example.com/Path"
    tmp = Path(tempfile.mkdtemp(prefix="sd-selftest-"))
    try:
        record_findings(tmp, "perplexity", "founder niche research",
                        [{"url": "https://example.com/report", "source_title": "Report",
                          "claim": "the market grew"}])
        assert trace_claim(tmp, url="https://example.com/report/")["traced"] is True
        assert trace_claim(tmp, url="https://fabricated.example/none")["traced"] is False
        assert trace_claim(tmp, claim="the market grew")["traced"] is True

        # 8. context injection: pinned text never edited; no-fab directive present
        ctx = build_context([{"url": "https://example.com/report", "claim": "x"}],
                            {"tool": "perplexity", "degraded": False})
        assert ctx["injection_mode"] == "context_only" and ctx["pin"] == "aa-02"
        assert "Do NOT invent" in ctx["directive"]
        # degraded context: empty sources, still no fabrication
        ctxd = build_context([], {"tool": None, "degraded": True})
        assert ctxd["degraded"] is True and ctxd["sources"] == []
        assert "cite no external links" in ctxd["rendered"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 9. flag dedup: a prior fired marker suppresses a second flag
    prior = {"flag": {"fired": True, "dedup_key": "search_detect:no_search_tool"}}
    f = fire_founder_flag(base_cfg, None, {"degraded": True}, prior)
    assert f["fired"] is False and f["suppressed"] is True, f

    print("search_detect self-test: OK (ladder + availability + trace + context + dedup)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(
        description="Anthology Engine web-search detection ladder (SPEC Section 9).")
    ap.add_argument("--self-test", action="store_true",
                    help="run the pure-logic self-test and exit")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--state-dir", help="override the engine state dir (cache location)")
        p.add_argument("--config", help="path to engine-config json (web_search block)")
        p.add_argument("--openclaw-bin", help="explicit OpenClaw CLI path")
        p.add_argument("--signals-file",
                       help="inject a normalized signals JSON (bypasses live probe)")
        p.add_argument("--deep", action="store_true",
                       help="also run the heavy `openclaw doctor` probe (slow; opt-in)")
        p.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    d = sub.add_parser("detect", help="run the ladder, cache, print result (0 tool / 3 no-tool)")
    common(d)
    d.add_argument("--anthology-id", help="optional anthology id for flag dedup scope")
    d.add_argument("--no-flag", action="store_true",
                   help="suppress the founder Telegram flag (tests / operator dry-run)")
    d.add_argument("--run-report", help="append the honest limitation note to this operator report")

    r = sub.add_parser("resolve", help="read the cached tool for stage S1 (re-detect if stale)")
    common(r)
    r.add_argument("--anthology-id", help="optional anthology id for flag dedup scope")
    r.add_argument("--no-flag", action="store_true", help="suppress the founder flag on re-detect")
    r.add_argument("--run-report", help="append the honest note if a re-detect degrades")
    r.add_argument("--force", action="store_true", help="force a fresh detection")
    r.add_argument("--max-age-seconds", type=int, default=0,
                   help="re-detect if the cache is older than this many seconds")

    bc = sub.add_parser("build-context",
                        help="wrap search findings into the aa-02 context payload (never edits the pin)")
    bc.add_argument("--state-dir", help="engine state dir (to read the detected tool)")
    bc.add_argument("--config", help="engine-config json path")
    bc.add_argument("--findings-file", help="JSON findings (list or {items:[...]})")
    bc.add_argument("--stdin", action="store_true", help="read findings JSON from stdin")
    bc.add_argument("--run-dir", help="also record the findings to this run dir (trace record)")
    bc.add_argument("--query", help="the search query, recorded with the findings")
    bc.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    rf = sub.add_parser("record-findings",
                        help="persist the Layer-2 search-pass output as the Gate B trace record")
    rf.add_argument("--run-dir", required=False, help="the per-participant run dir")
    rf.add_argument("--tool", help="the search tool that produced these findings")
    rf.add_argument("--query", help="the search query")
    rf.add_argument("--findings-file", help="JSON findings (list or {items:[...]})")
    rf.add_argument("--stdin", action="store_true", help="read findings JSON from stdin")
    rf.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    t = sub.add_parser("trace",
                       help="check a link/claim traces to the search pass output (0 traced / 5 fabricated)")
    t.add_argument("--run-dir", required=False, help="the per-participant run dir")
    t.add_argument("--url", help="the link to verify")
    t.add_argument("--claim", help="the claim text to verify")
    t.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    pl = sub.add_parser("plan", help="print the ladder, config, and paths (no side effects)")
    common(pl)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        if getattr(args, "self_test", False):
            return self_test()
        if not args.cmd:
            ap.print_help()
            return EXIT_VALIDATION
        handler = {
            "detect": cmd_detect,
            "resolve": cmd_resolve,
            "build-context": cmd_build_context,
            "record-findings": cmd_record_findings,
            "trace": cmd_trace,
            "plan": cmd_plan,
        }[args.cmd]
        return handler(args)
    except ValueError as exc:
        sys.stderr.write("[search_detect] validation error: %s\n" % exc)
        return EXIT_VALIDATION
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-soft top level; never crash the stage
        sys.stderr.write("[search_detect] unexpected error: %s\n" % exc)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
