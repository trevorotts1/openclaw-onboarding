#!/usr/bin/env python3
"""
shared-utils/secret_helper.py — FIX 67 shared secret-name canon helper.

ONE module that every python reader imports instead of restating its own
secret-name map or its own placeholder sniffing:

    from secret_helper import (
        load_secret_names,          # raw {"CANONICAL": [...]} canon
        alias_list,                 # canonical name -> [aliases incl. itself]
        resolve_secret,             # value of a canonical name via any alias
        looks_like_real_key,        # placeholder rejection (gate before dispatch)
        assert_real_key,            # resolve + looks_like_real_key or raise
        is_placeholder,             # bare predicate used by readers' presence checks
    )

Contract (QC FIX 67):
  * A key written under ANY alias in a family resolves in every reader on both
    platforms (Mac ~/.openclaw/..., VPS /data/.openclaw/...).
  * A placeholder value (PASTE_REAL_TOKEN, your_key_here, CHANGE_ME, <TODO>,
    the doc-example shapes, low-entropy filler) is REJECTED by every reader.
  * Nothing here ever prints a secret value. Presence and shape only.

The canon lives in shared-utils/secret_names.json next to this file
({"CANONICAL": ["ALIAS", ...]}). Add new aliases THERE, never in code.
"""

import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "load_secret_names",
    "alias_list",
    "canonical_for",
    "resolve_secret",
    "resolve_secret_strict",
    "looks_like_real_key",
    "assert_real_key",
    "is_placeholder",
    "env_file_candidates",
]

# ---------------------------------------------------------------------------
# Env-file candidates, platform-aware (Fix 68 ordering preserved here without
# importing presentation_job — shared-utils must stay dependency-free).
# VPS containers put the root at /data/.openclaw; Mac boxes at ~/.openclaw.
# ---------------------------------------------------------------------------
ENV_FILE_CANDIDATES = [
    "/data/.openclaw/secrets/.env",
    "/data/.openclaw/secrets/secrets.env",
    "/data/.openclaw/.env",
    os.path.expanduser("~/.openclaw/secrets/.env"),
    os.path.expanduser("~/.openclaw/secrets/secrets.env"),
    os.path.expanduser("~/.openclaw/.env"),
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.env"),
]


def env_file_candidates() -> List[str]:
    """Ordered env-file candidates: /data/.openclaw first (VPS), then $HOME."""
    return list(ENV_FILE_CANDIDATES)


# ---------------------------------------------------------------------------
# Canon loading
# ---------------------------------------------------------------------------
_CANON_CACHE: Optional[Dict[str, List[str]]] = None

_HERE = Path(__file__).resolve().parent
CANON_PATH = _HERE / "secret_names.json"


def load_secret_names() -> Dict[str, List[str]]:
    """Load {"CANONICAL": ["ALIAS", ...]} from secret_names.json.

    Returns {} on any failure so a broken canon can never take down a reader
    that still has its own fallback list (readers fail OPEN on the canon,
    then apply their own maps; placeholder rejection stays hard regardless).
    """
    global _CANON_CACHE
    if _CANON_CACHE is not None:
        return _CANON_CACHE
    canon: Dict[str, List[str]] = {}
    try:
        with open(CANON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        names = data.get("canonical_names") if isinstance(data, dict) else None
        if isinstance(names, dict):
            for canonical, aliases in names.items():
                if not isinstance(aliases, list):
                    continue
                cleaned = []
                for a in aliases:
                    if isinstance(a, str) and a and a not in cleaned:
                        cleaned.append(a)
                if canonical not in cleaned:
                    cleaned.insert(0, canonical)
                canon[canonical] = cleaned
    except Exception:
        canon = {}
    _CANON_CACHE = canon
    return canon


def alias_list(canonical: str) -> List[str]:
    """All accepted names for a canonical secret, canonical first.

    Unknown names resolve to [name] (a name that is its own family), which
    keeps new callers working before their family is added to the canon.
    """
    return list(load_secret_names().get(canonical, [canonical]))


def canonical_for(name: str) -> str:
    """Map any alias to its canonical head. Unknown -> itself."""
    canon = load_secret_names()
    if name in canon:
        return name
    for canonical, aliases in canon.items():
        if name in aliases:
            return canonical
    return name


# ---------------------------------------------------------------------------
# Env-file parsing (same tolerance as key_resolver.py / install.sh)
# ---------------------------------------------------------------------------
def _parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        if not os.path.isfile(path):
            return values
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[key] = value
    except OSError:
        pass
    return values


def _build_env_map(override_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Priority: env files (VPS-first order) < process env < explicit override."""
    values: Dict[str, str] = {}
    for path in ENV_FILE_CANDIDATES:
        values.update(_parse_env_file(path))
    values.update(os.environ)
    if override_env:
        values.update({k: v for k, v in override_env.items() if isinstance(v, str)})
    return values


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def resolve_secret(canonical: str, override_env: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Value of a canonical secret found via ANY alias in its family.

    Order per alias: process/override env first, then every env-file candidate.
    First non-empty hit wins. Returns None when no alias carries a value.
    """
    env_map = _build_env_map(override_env)
    for name in alias_list(canonical):
        value = (env_map.get(name) or "").strip()
        if value:
            return value
    return None


def resolve_secret_strict(
    canonical: str, override_env: Optional[Dict[str, str]] = None
) -> str:
    """resolve_secret + looks_like_real_key. Raises ValueError when absent or
    placeholder-shaped — the fail-closed gate readers put before dispatch."""

    value = resolve_secret(canonical, override_env)
    if value is None:
        raise ValueError(
            f"{canonical} absent from every store (aliases: "
            f"{', '.join(alias_list(canonical))})")
    if not looks_like_real_key(value, canonical):
        # NEVER include the value in the error.
        raise ValueError(
            f"{canonical} present but rejected as a placeholder/wrong-shape "
            f"value (aliases tried: {', '.join(alias_list(canonical))})")
    return value


# ---------------------------------------------------------------------------
# Placeholder rejection — the python twin of install.sh looks_like_real_key.
# Three stages; a value must pass ALL: (1) provider-shape regex when the
# canonical name maps to a known provider shape, (2) obvious-placeholder
# substrings / bracket templates, (3) Shannon entropy floor.
# ---------------------------------------------------------------------------
# Value shapes that read as real keys: mixed-case alphanumerics with
# punctuation like -_:. in provider-typical prefixes, long enough to be real.
_REALISH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-:.+/=]{9,}$")

_LOW_WORDS = {
    "true", "false", "yes", "no", "null", "none", "undefined", "n/a", "na",
}
_PLACEHOLDER_SUBSTRINGS = (
    "xxxxx", "your_key", "your-key", "your_api", "your-api", "yourkey",
    "your_token", "replace_me", "replace-me", "replaceme", "changeme",
    "change_me", "change-me", "placeholder", "example", "sample_key",
    "sample-key", "dummy", "demo_key", "demo-key", "test_key", "test-key",
    "fake_key", "fake-key", "sk-test", "sk-xxx", "sk-example", "sk-replace",
    "todo", "tbd", "fill_in", "fill-in", "fillin", "paste-your", "paste_your",
    "paste-real", "paste_real", "pastereal", "insert_your", "insert-your",
    "enter_your", "enter-your", "set_your", "set-your", "no_key", "nokey",
    "none_yet", "not_set", "not-set", "unset", "missing",
)

# Provider shape regexes (canonical var name -> anchored regex). Mirrors the
# stage-1 table in install.sh looks_like_real_key; extend both together.
_PROVIDER_SHAPE = {
    "OPENAI_API_KEY": re.compile(r"^sk-(proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}$"),
    "ANTHROPIC_API_KEY": re.compile(r"^sk-ant-(api03-)?[A-Za-z0-9_-]{80,}$"),
    "GEMINI_API_KEY": re.compile(r"^AIza[A-Za-z0-9_-]{35}$"),
    "GOOGLE_API_KEY": re.compile(r"^AIza[A-Za-z0-9_-]{35}$"),
    "OPENROUTER_API_KEY": re.compile(r"^sk-or-(v1-)?[A-Za-z0-9_-]{32,}$"),
    "GITHUB_TOKEN": re.compile(r"^(gh[poursr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|[a-f0-9]{40})$"),
    "BRAVE_SEARCH_API_KEY": re.compile(r"^BSA[A-Za-z][A-Za-z0-9_-]{20,}$"),
    "BRAVE_API_KEY": re.compile(r"^BSA[A-Za-z][A-Za-z0-9_-]{20,}$"),
    "TAVILY_API_KEY": re.compile(r"^tvly-[A-Za-z0-9_-]{20,}$"),
    "DEEPSEEK_API_KEY": re.compile(r"^sk-[a-f0-9]{32,}$"),
    "OLLAMA_API_KEY": re.compile(r"^[A-Za-z0-9]{32,}$"),
    "OLLAMA_CLOUD_API_KEY": re.compile(r"^[A-Za-z0-9]{32,}$"),
    "KIE_API_KEY": re.compile(r"^[A-Za-z0-9_-]{24,}$"),
    "TELEGRAM_BOT_TOKEN": re.compile(r"^[0-9]{8,12}:[A-Za-z0-9_-]{30,40}$"),
    "SUPABASE_SERVICE_ROLE_KEY": re.compile(
        r"^(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sb_secret_[A-Za-z0-9_-]{20,})$"),
    "GOHIGHLEVEL_API_KEY": re.compile(
        r"^(eyJ[A-Za-z0-9_.-]{30,}|pit-[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{40,})$"),
    "GOHIGHLEVEL_LOCATION_ID": re.compile(r"^[A-Za-z0-9]{20,28}$"),
    "ELEVENLABS_API_KEY": re.compile(r"^[a-f0-9]{32}$|^sk_[A-Za-z0-9_-]{32,}$"),
    "CONTEXT7_API_KEY": re.compile(r"^ctx7sk-[A-Za-z0-9_-]{20,}$"),
    "CLOUDFLARE_ZHW_APPS_API_TOKEN": re.compile(r"^[A-Za-z0-9_-]{30,}$"),
}


def is_placeholder(value: str) -> bool:
    """True when the value is obviously a placeholder, empty, or trivially
    low-information. Pure predicate; no filesystem, no provider regexes."""
    if value is None:
        return True
    value = str(value).strip()
    if len(value) < 10:
        return True
    low = value.lower()
    if low in _LOW_WORDS:
        return True
    for sub in _PLACEHOLDER_SUBSTRINGS:
        if sub in low:
            return True
    # Template shapes: <TODO>, [REPLACE], {{var}}
    if value.startswith("<") and value.endswith(">"):
        return True
    if value.startswith("[") and value.endswith("]"):
        return True
    if "{{" in value and "}}" in value:
        return True
    return False


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in value:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def looks_like_real_key(value: str, canonical: Optional[str] = None) -> bool:
    """Placeholder rejection gate. True only when the value plausibly is a
    real key for `canonical`. Keep byte-compatible with install.sh's bash
    implementation of the same name — extend both together."""
    if value is None:
        return False
    value = str(value).strip()
    if is_placeholder(value):
        return False
    low = value.lower()

    # Stage 1: provider shape. A known provider whose documented shape does
    # NOT match is rejected outright (it is not this provider's credential).
    shape = _PROVIDER_SHAPE.get(canonical or "")
    if shape is not None and not shape.match(value):
        return False

    # Stage 2 (shape gate passed or unknown provider): must look like a key.
    if not _REALISH_RE.match(value):
        return False

    # Stage 3: Shannon entropy floor, 3.0 bits/char (gitleaks band).
    if _entropy(value) < 3.0:
        return False
    return True


def assert_real_key(canonical: str, override_env: Optional[Dict[str, str]] = None) -> str:
    """Alias of resolve_secret_strict kept for reader ergonomics."""
    return resolve_secret_strict(canonical, override_env)


if __name__ == "__main__":
    # Self-test: presence/shape only, no values printed.
    import sys

    failures = []

    def check(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # Placeholders rejected (QC FIX 67: PASTE_REAL_TOKEN rejected by every reader)
    for bad in ("PASTE_REAL_TOKEN", "your_key_here", "CHANGE_ME_LATER",
                "<TODO>", "{{SECRET}}", "sk-example123", "short", "",
                "BRAVE_TOKEN_REPLACE_ME"):
        check(f"placeholder {bad!r}", is_placeholder(bad), True)
    # Uniform 'aaaaaaaaaa' passes the substring pre-check by design (no
    # placeholder marker) but is rejected by the entropy floor:
    check("uniform run entropy", looks_like_real_key("aaaaaaaaaa"), False)

    # Real-shaped values pass shape+entropy (high-entropy fixtures — each
    # char drawn across >= 10 symbols so entropy clears the 3.0 floor)
    _alpha = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    _fixture = "".join(_alpha[(i * 37 + 11) % len(_alpha)] for i in range(48))
    check("brave shape", looks_like_real_key("BSA" + _fixture, "BRAVE_SEARCH_API_KEY"), True)
    check("brave alias shape", looks_like_real_key("BSA" + _fixture, "BRAVE_API_KEY"), True)
    check("openai shape", looks_like_real_key("sk-" + _fixture, "OPENAI_API_KEY"), True)
    check("ollama shape", looks_like_real_key(_fixture, "OLLAMA_CLOUD_API_KEY"), True)

    # Wrong shape for a known provider rejected
    check("openai wrong shape", looks_like_real_key("ghp_" + "A" * 36, "OPENAI_API_KEY"), False)

    # Low entropy rejected even with no provider mapping (uniform run)
    check("low entropy", looks_like_real_key("aaaaaaaaaaaaaaaaaaaa"), False)
    # Repetitive two-symbol pattern also below 3.0 bits/char
    check("two-symbol low entropy", looks_like_real_key("Ab3Ab3Ab3Ab3Ab3Ab3Ab3"), False)

    # Canon: QC FIX 67 bidirectional families
    canon = load_secret_names()
    check("canon nonempty", bool(canon), True)
    check("brave family", sorted(canon.get("BRAVE_API_KEY", [])),
          sorted(["BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"]))
    check("ollama family has both", "OLLAMA_CLOUD_API_KEY" in canon.get("OLLAMA_API_KEY", []), True)
    check("cf token present", "CLOUDFLARE_ZHW_APPS_API_TOKEN" in canon, True)
    check("cf account present", "CLOUDFLARE_ZHW_ACCOUNT_ID" in canon, True)

    # Resolution: key written under an alias resolves (override env simulates
    # the secrets file; both directions of both QC families). Fixture values
    # are synthetic high-entropy strings, never real credentials.
    _alpha = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    _fx = "".join(_alpha[(i * 37 + 11) % len(_alpha)] for i in range(48))
    check("alias->BRAVE_SEARCH", bool(resolve_secret(
        "BRAVE_SEARCH_API_KEY", {"BRAVE_API_KEY": "BSA" + _fx})), True)
    check("alias->OLLAMA", bool(resolve_secret(
        "OLLAMA_CLOUD_API_KEY", {"OLLAMA_API_KEY": _fx})), True)
    # AND the reverse directions (QC FIX 67 both ways):
    check("alias->BRAVE reverse", bool(resolve_secret(
        "BRAVE_API_KEY", {"BRAVE_SEARCH_API_KEY": "BSA" + _fx})), True)
    check("alias->OLLAMA reverse", bool(resolve_secret(
        "OLLAMA_API_KEY", {"OLLAMA_CLOUD_API_KEY": _fx})), True)

    # Placeholder written under an alias is REJECTED by the strict resolver.
    # The self-test runs with store probing isolated (empty temp dir) so the
    # operator's real secrets on this box never take part in the fixture and
    # no real value ever enters a test path.
    import tempfile

    try:
        _real_candidates = list(ENV_FILE_CANDIDATES)
        with tempfile.TemporaryDirectory() as _td:
            ENV_FILE_CANDIDATES[:] = [os.path.join(_td, "none.env")]
            try:
                resolve_secret_strict(
                    "BRAVE_SEARCH_API_KEY", {"BRAVE_API_KEY": "PASTE_REAL_TOKEN"})
                failures.append("placeholder under alias: not rejected")
            except ValueError:
                pass
            try:
                resolve_secret_strict(
                    "BRAVE_SEARCH_API_KEY", {"BRAVE_SEARCH_API_KEY": "PASTE_REAL_TOKEN"})
                failures.append("placeholder under canonical: not rejected")
            except ValueError:
                pass
    finally:
        ENV_FILE_CANDIDATES[:] = _real_candidates

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        sys.exit(1)
    print("secret_helper self-test: ALL PASS")
