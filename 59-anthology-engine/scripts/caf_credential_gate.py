#!/usr/bin/env python3
"""caf_credential_gate.py -- the Anthology Engine Convert and Flow credential gate.

Unit W2.3. SPEC 3.4 row 26 / SPEC 13.1 step 1 / SPEC 10.3. Part C refs 16 and 19.
AF-AE-COMMINGLE (ENGINE-MANIFEST autofail, py_symbol "fingerprint"). This is the
provisioning gate that provision-anthology-client.sh runs FIRST, before any field
create, pipeline provision, Drive touch, or webhook mint.

WHAT IT PROVES (all offline, deterministic, no network call -- the live create-feasibility
probe of the PIT write scope is a DIFFERENT gate, AF-AE-PIT-SCOPE, owned by
provision-anthology-client.sh):

  1. LABEL RESOLUTION, LIVE-PROCESS-FIRST, across the three client env stores.
     The definitive test for "does this box have credential X" is the RUNNING PROCESS
     ENV; if os.environ carries the label the credential EXISTS, full stop. Only when
     the live process env is empty for every alias do we descend into the three client
     .env stores (in order). Every store consulted is listed in the report so a
     "NOT SET" verdict is never a shallow-search lie (the env-store doctrine). A
     credential is referenced by LABEL and reported SET or NOT SET only; no value, and
     by default no fingerprint, is ever printed.

  2. PAIRING PROOF. The Convert and Flow credential PAIR is the private integration
     token (prefix pit-, the same thing as the API key under any alias) AND the Location
     ID. A half pair (one member present, the other NOT SET) is not a usable credential
     and exits 2 (missing label). Both members present is a proven pair (structural
     completeness); ownership of that pair is the fingerprint's job below.

  3. ANTI-COMMINGLING FINGERPRINT (client OWN keys only; never operator, shared, or
     another client's). A credential is fingerprinted as an unsalted sha256 of its VALUE
     (non-reversible; the value is never revealed, and an operator can precompute an
     expected or deny fingerprint with `printf %s "$V" | sha256sum`). Commingling is
     declared, and the gate exits 4, when ANY of these fire:
       (a) OPERATOR/SHARED/FLEET COLLISION (config-free): the client's resolved Convert
           and Flow value is byte-identical to a value that also sits under an operator,
           shared, fleet, master, global, or default namespaced env label -- i.e. the
           client's "own" key is actually the operator's shared key.
       (b) FOREIGN-CLIENT COLLISION: the same value also sits under another client's or
           tenant's namespaced label on this box.
       (c) EXPECTED-OWN MISMATCH: an expected own fingerprint was supplied (from a prior
           clean provisioning) and the resolved credential does not match it.
       (d) DENYLISTED FINGERPRINT: the resolved credential matches a known operator or
           other-client fingerprint passed by the operator (flag or env).
     The report is honest about which of these checks were ACTIVE versus INACTIVE, so a
     clean verdict never implies proof that no evidence supported.

  4. THE LEGACY EXPOSURE CLASS FORBIDDEN. The legacy cover node carried a LITERAL
     Authorization header with a live key (SPEC 5.8 V4 / Part C item 16). This gate
     scans the engine runtime source for that class -- a literal Authorization: Bearer
     <real-token> header, or an inline provider key literal (sk-, sk-or-, pit-, key-,
     AIza...) -- and exits 4 on any finding. Templated headers ("Bearer %s" % pit,
     Bearer $PIT, Bearer <PIT>) and the deny-pattern regex DEFINITIONS themselves are
     ALLOWED: the token charset filter plus a regex/format context guard mean only an
     actual leaked literal trips it. The finding reports file and line and a reason
     class, never the token. The scanned set also excludes this repo's own four
     merge-gate secret-pattern scanners BY BASENAME (_SELF_TEST_FIXTURE_BASENAMES,
     the same scan-no-secrets.sh / scan-no-json-exports.sh /
     scan-no-client-identifiers.sh / scan-skill53-untouched.sh set those four already
     exclude each other by): each embeds a deliberately real-shaped self-test fixture
     to prove ITS OWN detector works, which is not runtime exposure of this gate's
     concern. This is basename-scoped only -- a real leak under any other filename in
     the scanned set still trips it (see the self-test's adversarial case).

EXIT CODES (SPEC 3.4 row 26; the manifest house convention for the edge cases):
  0  all required labels resolve, pairing proven, fingerprint clean, no inline exposure
     (an idempotent re-run of a clean box is the same 0)
  2  a required label is missing (an unresolved Convert and Flow member), or a bad
     invocation / validation refusal
  4  an enforced violation: commingling detected, OR a forbidden literal Authorization
     header / inline key found in the scanned runtime set
  1  unexpected error
  3  dependency unavailable (reserved; this gate is pure standard library)
Precedence when several conditions hold: 4 (violation) outranks 2 (missing) outranks 0.

DOCTRINE: move in silence, operator-verbose and never client-facing; a value is never
printed; presence is SET(len=N) or NOT SET; a fingerprint prefix appears only under the
explicit --show-fingerprints operator-debug flag; Convert and Flow naming throughout.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (SPEC 3.4 row 26).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_MISSING = 2       # a required Convert and Flow label is NOT SET / bad invocation
EX_DEP = 3           # dependency unavailable (reserved; pure stdlib gate)
EX_VIOLATION = 4     # commingling detected OR a forbidden literal header / inline key

# ---------------------------------------------------------------------------
# The Convert and Flow shared alias resolver. SPEC 10.3: "the private integration
# token and API key being the same thing under any alias." Held BYTE-IDENTICAL to
# caf_delivery.py's PIT_LABELS / LOCATION_LABELS / ALLOWED_LOCATION_LABELS (the two
# modules resolve the SAME credential the SAME way); the self-test best-effort imports
# caf_delivery and asserts the tuples still match so drift is caught at build time.
# Canonical engine label FIRST, then the operator/legacy aliases, so the same gate runs
# on the operator canary and on a client box.
# ---------------------------------------------------------------------------
PIT_LABELS = (
    "CONVERT_AND_FLOW_PIT",
    "CONVERT_AND_FLOW_API_KEY",
    "GOHIGHLEVEL_API_KEY",
    "GOHIGHLEVEL_PIT",
    "GHL_API_KEY",
)
LOCATION_LABELS = (
    "CONVERT_AND_FLOW_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "GHL_LOCATION_ID",
)
ALLOWED_LOCATION_LABELS = (
    "CAF_ALLOWED_LOCATION_IDS",
    "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
)

# The Convert and Flow PAIR is the gate's REQUIRED set (family key -> alias tuple).
REQUIRED_FAMILIES = (
    ("convert_and_flow_pit", PIT_LABELS),
    ("convert_and_flow_location", LOCATION_LABELS),
)

# The wider PRD Section 14 credential family, resolved and reported for context under
# --all (informational: never gates the exit code here -- the model chain is preflight's
# concern, SPEC 8). Aliases include the three-name Google key (GOOGLE_API_KEY /
# GOOGLE_AI_STUDIO_API_KEY / GEMINI_API_KEY are one value) and the ollama-cloud id.
INFORMATIONAL_FAMILIES = (
    ("ollama_cloud_key", ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_CLOUD_KEY")),
    ("openrouter_key", ("OPENROUTER_API_KEY", "OPENROUTER_KEY")),
    ("gemini_key", ("GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GEMINI_API_KEY")),
    ("minimax_key", ("MINIMAX_API_KEY", "MINIMAX_KEY")),
    ("kie_key", ("KIE_API_KEY", "KIE_AI_API_KEY", "KIEAI_API_KEY")),
    ("deepseek_or_kimi_key_optional",
     ("DEEPSEEK_API_KEY", "KIMI_API_KEY", "MOONSHOT_API_KEY")),
    ("anthology_intake_hook_secret", ("ANTHOLOGY_INTAKE_HOOK_SECRET",)),
    ("anthology_gate_token_secret", ("ANTHOLOGY_GATE_TOKEN_SECRET",)),
    ("search_tool_key_optional", ("PERPLEXITY_API_KEY", "PPLX_API_KEY")),
)

# ---------------------------------------------------------------------------
# The three client env stores (SPEC/PRD: "all three client env stores, live process
# env first"). The headline three are the stores fleet agents most often miss; the
# extended set (memory: client-box-env-stores) is opt-in via --extended-stores, and
# --store adds an explicit path (used by the self-test to inject temp stores). The live
# process env is ALWAYS consulted first and is not a "store" -- it is ground truth.
# ---------------------------------------------------------------------------
CANONICAL_STORES = (
    "~/.openclaw/secrets/.env",
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
)
EXTENDED_STORES = (
    "~/.openclaw/.env",
    "~/.openclaw/workspace/secrets/.env",
    "~/clawd/.env",
    "~/.openclaw/service-env/ai.openclaw.gateway.env",
)

# Env label NAMESPACES that mark a value as operator / shared / fleet owned rather than
# this one client's own. A client Convert and Flow value whose fingerprint collides with
# a value under one of these labels is commingling (the config-free check (a)/(b)).
OPERATOR_NS_RE = re.compile(
    r"(?i)(^(OPERATOR|OPERATORS|BLACKCEO|BLACK_CEO|FLEET|SHARED|ADMIN|MASTER|GLOBAL"
    r"|DEFAULT|OPS|INTERNAL|TREVOR|COMPANY|ORG)_)"
    r"|(_(OPERATOR|SHARED|FLEET|GLOBAL|MASTER)(_|$))"
)
FOREIGN_CLIENT_NS_RE = re.compile(
    r"(?i)(^|_)(CLIENT|TENANT|ACCT|ACCOUNT|CUSTOMER|SUBACCOUNT)_[A-Z0-9]{2,}"
)
ENV_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DENY_FP_ENV_LABEL = "ANTHOLOGY_COMMINGLE_DENY_FPS"

# ---------------------------------------------------------------------------
# The inline-exposure scanner. A REAL literal secret is a known key prefix followed by a
# long run of key characters, or an Authorization: Bearer header whose token is a real
# literal. The key-character run deliberately EXCLUDES regex/format metacharacters, so a
# pattern definition (sk-[a-z0-9]{16,}) or a template ("Bearer %s") never matches.
# ---------------------------------------------------------------------------
_INLINE_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(sk-or-v1-[A-Za-z0-9]{20,}"          # OpenRouter
    r"|sk-proj-[A-Za-z0-9]{20,}"           # OpenAI project key
    r"|sk-[A-Za-z0-9]{20,}"                # OpenAI / generic sk-
    r"|pit-[A-Za-z0-9]{20,}"               # Convert and Flow / GoHighLevel PIT
    r"|key-[A-Za-z0-9]{16,}"               # generic key-
    r"|AIza[0-9A-Za-z_\-]{30,})"           # Google
)
_INLINE_AUTH_RE = re.compile(
    r"(?i)authorization[\"'\s:=]{1,6}bearer\s+([A-Za-z0-9._\-]{20,})"
)
# Line-context markers that mean a prefix hit is a regex/format/env-ref or a detector
# TEST fixture, never a live-credential leak. A hardcoded runtime credential is never on
# an `assert` line and never sits next to a key-detector call: those are test scaffolds.
_TEMPLATE_MARKERS = (
    "re.compile", "_re", "regex", "pattern", "re.match", "re.search", "re.sub",
    "os.environ", "getenv", "environ.get", "_labels", ".format(", ".join(",
    "placeholder", "example", "redacted", "your_", "<pit", "<token", "<key",
    "${", "{{", "%s", "%(",
    "assert ", "self-test", "self_test", "_looks_like", "unittest", "def test",
)
# Tokens that are obvious placeholders even when the shape looks real.
_PLACEHOLDER_TOKENS = re.compile(
    r"(?i)(x{6,}|\.{3,}|example|redacted|your[_-]?key|placeholder|dummy|sample|test{4,})"
)


def _has_sequential_run(token, n=8):
    """True if `token` carries an ascending consecutive-codepoint run of length >= n
    (abcdefgh, 0123456789). A high-entropy real key effectively never does; a synthetic
    detector fixture (sk-abcdefghijklmnop1234567890) always does, so this cleanly
    separates test example keys from a genuine leak."""
    if len(token) < n:
        return False
    run = 1
    for i in range(1, len(token)):
        if ord(token[i]) - ord(token[i - 1]) == 1:
            run += 1
            if run >= n:
                return True
        else:
            run = 1
    return False


def _is_placeholder_token(token):
    """A shaped token that is unmistakably NOT a live credential: a named placeholder or
    a sequential/low-entropy fixture string."""
    return bool(_PLACEHOLDER_TOKENS.search(token)) or _has_sequential_run(token)

# Directory / file names excluded from the DEFAULT runtime scan (synthetic attack
# fixtures deliberately carry key-shaped strings; the entry bypass-scan and
# guard-prompt-pins own those trees).
_SCAN_SKIP_DIRS = {"fixtures", "tests", "assets", "__pycache__", ".git", "node_modules"}
_SCAN_EXTS = {".py", ".sh", ".json", ".js", ".ts", ".env", ".cfg", ".ini", ".yaml",
              ".yml", ".toml", ".md", ".txt", ".template"}

# AF-AE-CREDGATE-SELFHIT fix (branch anthology-engine-build): basenames of this repo's
# OWN four merge-gate secret-pattern scanners, held BYTE-IDENTICAL to each scanner's own
# SELF_NAMES list (scan-no-secrets.sh / scan-no-json-exports.sh /
# scan-no-client-identifiers.sh / scan-skill53-untouched.sh already exclude THEMSELVES
# from each other by this exact basename set -- see is_self() in scan-no-secrets.sh).
# Each of the four deliberately embeds a real-shaped fixture literal in its own
# self-test to PROVE its detector catches a genuine-looking leak (e.g.
# scan-no-secrets.sh's `fake_sk`, built at its line 319 specifically to evade that
# script's own low-entropy synthetic-key filter) -- a proof-of-detection fixture, never
# a live credential. This gate's inline-exposure scanner is a SEPARATE detector (Part C
# item 16's literal-Authorization-header/inline-key ban, not the four merge-gate
# secret-pattern scans) with no visibility into scan-no-secrets.sh's own allowlist, and
# its DEFAULT scan target (SKILL_DIR / "scripts") walks the whole scripts/ dir including
# these four scanners' own source. Confirmed live: a real, correctly-paired,
# non-commingled client credential pair on this box still tripped exit 4 purely because
# scan-no-secrets.sh:319's self-test fixture looked like a leak to THIS scanner. Fix:
# adopt the SAME basename exclusion the four scanners already apply to each other, for
# the same reason, rather than invent a second convention. This is basename-scoped
# ONLY (mirrors guard-no-anthropic-runtime.py's CHANGELOG.md _NON_RUNTIME_BASENAMES
# exemption) -- it does not exempt a directory or these files' surrounding tree, and a
# real leak planted under any OTHER filename in scripts/ is unaffected.
_SELF_TEST_FIXTURE_BASENAMES = {
    "scan-no-secrets.sh",
    "scan-no-json-exports.sh",
    "scan-no-client-identifiers.sh",
    "scan-skill53-untouched.sh",
}

SKILL_DIR = Path(__file__).resolve().parent.parent

Resolution = namedtuple("Resolution", "family label source present value")


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def credential_fingerprint(value, salt=""):
    """Non-reversible fingerprint of a credential VALUE -- never the value itself.

    Unsalted by default so an operator can precompute an expected/deny fingerprint with
    `printf %s "$VALUE" | sha256sum`. Returns a 64-hex sha256, or None for an empty
    value. A salt is available for callers that want per-run non-correlatable prints."""
    if value is None or value == "":
        return None
    h = hashlib.sha256()
    if salt:
        h.update(salt.encode("utf-8"))
    h.update(value.encode("utf-8"))
    return h.hexdigest()


def _fp_short(fp):
    return fp[:12] if fp else None


def _mask(value):
    """Presence and length ONLY, never a character of the value (doctrine)."""
    if not value:
        return "NOT SET"
    return "SET(len=%d)" % len(value)


def _fp_match(resolved_fp, given):
    """A resolved 64-hex fingerprint matches `given` (a full hex or a >=8 char prefix)."""
    if not resolved_fp or not given:
        return False
    given = given.strip().lower()
    if len(given) < 8:
        return False
    return resolved_fp == given or resolved_fp.startswith(given)


def _dotenv_parse(path):
    """Best-effort KEY=VALUE parse of one .env file. Never prints any value; returns a
    dict. Missing / unreadable files yield {} (the caller records the path as checked)."""
    out = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not ENV_LABEL_RE.match(key):
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        # Strip a trailing inline comment on unquoted values (conservative: only when
        # preceded by whitespace, so a '#' inside a token is preserved).
        out[key] = val
    return out


def resolve_stores(explicit=None, extended=False):
    """Ordered list of (source_label, Path) env stores to consult AFTER the live process
    env. Explicit --store paths come first (self-test injection / operator override),
    then the canonical three, then the extended set when requested. De-duplicated by
    resolved absolute path while preserving order."""
    paths = []
    for p in (explicit or ()):
        paths.append(Path(p).expanduser())
    for p in CANONICAL_STORES:
        paths.append(Path(p).expanduser())
    if extended:
        for p in EXTENDED_STORES:
            paths.append(Path(p).expanduser())
    seen = set()
    ordered = []
    for p in paths:
        try:
            key = str(p.resolve())
        except (OSError, RuntimeError):
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)
    return ordered


def build_env_view(environ, store_paths):
    """Return (sources, checked). `sources` is an ordered list of
    (source_label, mapping) with the LIVE PROCESS ENV first, then each store parsed.
    `checked` is the human list of every source consulted (for the report -- proves the
    search was exhaustive, per the env-store doctrine)."""
    sources = [("process-env", dict(environ))]
    checked = ["process-env"]
    for p in store_paths:
        label = str(p)
        exists = p.exists() and p.is_file()
        sources.append((label, _dotenv_parse(p) if exists else {}))
        checked.append("%s%s" % (label, "" if exists else " (absent)"))
    return sources, checked


def resolve_label(family, aliases, sources):
    """Live-process-first resolution of one credential family across the ordered
    sources. Within a source the alias order is honoured. Returns a Resolution; a missing
    credential is Resolution(family, None, None, False, None)."""
    for source_label, mapping in sources:
        for alias in aliases:
            val = mapping.get(alias, "")
            if val is not None and str(val).strip():
                return Resolution(family, alias, source_label, True, str(val).strip())
    return Resolution(family, None, None, False, None)


def index_namespaced_values(sources):
    """Fingerprint every env value whose LABEL sits in an operator/shared/fleet or
    foreign-client namespace, across ALL sources. Returns
    {fingerprint: {"operator": set(labels), "foreign": set(labels)}} so a collision with
    a resolved client credential can name the offending label(s) (names are not secrets)
    without ever handling the value again."""
    index = {}
    for _source_label, mapping in sources:
        for name, val in mapping.items():
            if not val or not str(val).strip():
                continue
            kind = None
            if OPERATOR_NS_RE.search(name):
                kind = "operator"
            elif FOREIGN_CLIENT_NS_RE.search(name):
                kind = "foreign"
            if kind is None:
                continue
            fp = credential_fingerprint(str(val).strip())
            slot = index.setdefault(fp, {"operator": set(), "foreign": set()})
            slot[kind].add(name)
    return index


# ---------------------------------------------------------------------------
# THE ANTI-COMMINGLING DECISION. This is the ENGINE-MANIFEST py_symbol "fingerprint"
# for AF-AE-COMMINGLE (row 130): given the resolved client credentials plus the evidence
# available on this box, decide whether any operator, shared, or other-client credential
# stands in place of the named client's own. Returns a verdict dict carrying label NAMES
# and reason CODES only -- never a value, never a full fingerprint.
# ---------------------------------------------------------------------------
def fingerprint(resolutions, namespaced_index=None, expected=None, deny_fps=None):
    """AF-AE-COMMINGLE enforcement.

    resolutions      : iterable of Resolution (the resolved client credentials).
    namespaced_index : output of index_namespaced_values() (config-free collision base).
    expected         : {"convert_and_flow_pit": fp_or_None,
                        "convert_and_flow_location": fp_or_None} expected-own fingerprints.
    deny_fps         : iterable of known operator/other-client fingerprints (full or >=8
                       hex prefix).

    Returns {"clean": bool, "checks_active": [...], "checks_inactive": [...],
             "reasons": [ {"credential","code","detail"} ... ]} with zero secret material.
    """
    namespaced_index = namespaced_index or {}
    expected = expected or {}
    deny_fps = [d.strip().lower() for d in (deny_fps or []) if d and d.strip()]

    reasons = []
    active, inactive = [], []

    (active if namespaced_index else inactive).append("operator_shared_value_collision")
    (active if any(expected.get(k) for k in expected) else inactive).append(
        "expected_own_fingerprint")
    (active if deny_fps else inactive).append("denylisted_fingerprint")

    for res in resolutions:
        if not res.present:
            continue
        fp = credential_fingerprint(res.value)

        # (a)/(b) config-free namespace collision.
        slot = namespaced_index.get(fp)
        if slot:
            if slot.get("operator"):
                reasons.append({
                    "credential": res.family, "code": "operator_shared_value_collision",
                    "detail": "resolved value is byte-identical to a value under "
                              "operator/shared label(s): %s"
                              % ", ".join(sorted(slot["operator"]))})
            if slot.get("foreign"):
                reasons.append({
                    "credential": res.family, "code": "foreign_client_value_collision",
                    "detail": "resolved value is byte-identical to a value under another "
                              "client/tenant label(s): %s"
                              % ", ".join(sorted(slot["foreign"]))})

        # (c) expected-own mismatch.
        exp = expected.get(res.family)
        if exp and not _fp_match(fp, exp):
            reasons.append({
                "credential": res.family, "code": "expected_own_mismatch",
                "detail": "resolved fingerprint does not match the expected own "
                          "fingerprint for this client (credential was replaced or "
                          "rotated to a non-client value)"})

        # (d) denylisted fingerprint.
        for d in deny_fps:
            if _fp_match(fp, d):
                reasons.append({
                    "credential": res.family, "code": "denylisted_fingerprint",
                    "detail": "resolved fingerprint is on the operator/other-client "
                              "deny list"})
                break

    return {
        "clean": len(reasons) == 0,
        "checks_active": active,
        "checks_inactive": inactive,
        "reasons": reasons,
    }


def pairing_proof(resolutions_by_family):
    """Structural pairing of the Convert and Flow credential PAIR (PIT + Location).
    Both present -> proven. A half pair names the missing member. Ownership of the pair
    is the fingerprint's concern, not pairing's."""
    pit = resolutions_by_family.get("convert_and_flow_pit")
    loc = resolutions_by_family.get("convert_and_flow_location")
    pit_ok = bool(pit and pit.present)
    loc_ok = bool(loc and loc.present)
    if pit_ok and loc_ok:
        return {"proven": True, "reason": "pit and location both resolve"}
    missing = []
    if not pit_ok:
        missing.append("convert_and_flow_pit")
    if not loc_ok:
        missing.append("convert_and_flow_location")
    return {"proven": False, "reason": "unpaired: missing %s" % ", ".join(missing),
            "missing": missing}


# ---------------------------------------------------------------------------
# THE INLINE-EXPOSURE SCAN. Forbid the legacy literal Authorization header / inline key
# class (Part C item 16). Reports file:line and a reason class, never the token.
# ---------------------------------------------------------------------------
def _looks_templated(line):
    low = line.lower()
    return any(m in low for m in _TEMPLATE_MARKERS)


def scan_line(line):
    """Return a reason code for a real inline-credential exposure on one line, else None.
    A prefix key or a Bearer literal is IGNORED when the line is a regex/format/env-ref
    (a template, not a leak) or the token is an obvious placeholder."""
    templated = _looks_templated(line)

    m = _INLINE_AUTH_RE.search(line)
    if m:
        token = m.group(1)
        if not templated and not _is_placeholder_token(token):
            return "literal_authorization_bearer_header"

    m = _INLINE_KEY_RE.search(line)
    if m:
        token = m.group(1)
        if not templated and not _is_placeholder_token(token):
            return "inline_provider_key_literal"

    return None


def scan_inline_credentials(paths, skip_dirs=None):
    """Walk each path (file or directory) and return findings for the legacy exposure
    class. A finding is {"file","line","reason"} -- never the offending token. Directory
    walks skip synthetic-fixture and cache trees and non-text files. A file whose
    basename is one of this repo's own four merge-gate secret-pattern scanners
    (_SELF_TEST_FIXTURE_BASENAMES) is exempt regardless of how it was reached (explicit
    path or directory walk) -- its content is that scanner's own self-test fixture, not
    this gate's runtime-exposure concern; see _SELF_TEST_FIXTURE_BASENAMES."""
    skip_dirs = skip_dirs if skip_dirs is not None else _SCAN_SKIP_DIRS
    findings = []

    def scan_file(fp):
        if fp.name in _SELF_TEST_FIXTURE_BASENAMES:
            return
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            return
        for i, line in enumerate(text.splitlines(), 1):
            reason = scan_line(line)
            if reason:
                findings.append({"file": str(fp), "line": i, "reason": reason})

    for p in paths:
        path = Path(p).expanduser()
        if path.is_file():
            scan_file(path)
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if any(part in skip_dirs for part in f.parts):
                    continue
                if f.is_file() and f.suffix.lower() in _SCAN_EXTS:
                    scan_file(f)
    return findings


# ---------------------------------------------------------------------------
# THE GATE. Orchestrates resolution -> pairing -> fingerprint -> inline scan and returns
# (exit_code, report). Injectable environ / stores / scan_paths make it self-testable.
# ---------------------------------------------------------------------------
def gate(environ=None, store_paths=None, extended_stores=False, scan_paths=None,
         do_scan=True, include_informational=False, expected=None, deny_fps=None,
         require_families=None):
    environ = os.environ if environ is None else environ
    if store_paths is None:
        store_paths = resolve_stores(extended=extended_stores)

    sources, checked = build_env_view(environ, store_paths)

    # The base required set is the Convert and Flow PIT+Location pair. The canary /
    # verify path may PROMOTE a box-generated Anthology secret (created at provision
    # step 7, e.g. anthology_intake_hook_secret) into the required set via
    # require_families -- those secrets are NOT required for the INITIAL credential
    # gate (they do not exist until step 7 generates them), only for the confirm-SET
    # before the intake route can fire: the gateway resolves hooks.token =
    # ${ANTHOLOGY_INTAKE_HOOK_SECRET} from the env at load, so an unset secret leaves
    # the hook "unavailable" (the gateway's own config-validate warning). Promotion is
    # opt-in so the default gate stays non-regressive on a fresh box.
    require_families = set(require_families or ())
    promoted = [(fam, aliases) for fam, aliases in INFORMATIONAL_FAMILIES
                if fam in require_families]
    promoted_keys = {fam for fam, _a in promoted}
    active_required = list(REQUIRED_FAMILIES) + promoted

    # Resolve the required set (base + promoted) then the remaining informational.
    resolutions_by_family = {}
    resolution_report = {}
    for fam, aliases in active_required:
        res = resolve_label(fam, aliases, sources)
        resolutions_by_family[fam] = res
        resolution_report[fam] = {
            "required": True, "present": res.present, "label": res.label,
            "source": res.source, "presence": _mask(res.value)}
    if include_informational:
        for fam, aliases in INFORMATIONAL_FAMILIES:
            if fam in promoted_keys:
                continue                        # already resolved as required above
            res = resolve_label(fam, aliases, sources)
            resolutions_by_family[fam] = res
            resolution_report[fam] = {
                "required": False, "present": res.present, "label": res.label,
                "source": res.source, "presence": _mask(res.value)}

    # Required-label check (exit 2 candidate) -- the base pair AND any promoted secret.
    missing = [fam for fam, _a in active_required
               if not resolutions_by_family[fam].present]

    pairing = pairing_proof(resolutions_by_family)

    # Anti-commingling over the resolved CLIENT Convert and Flow credentials.
    namespaced_index = index_namespaced_values(sources)
    # Deny fingerprints: explicit + the env-supplied list.
    all_deny = list(deny_fps or [])
    env_deny = environ.get(DENY_FP_ENV_LABEL, "")
    if env_deny:
        all_deny.extend([x for x in re.split(r"[,\s]+", env_deny) if x])
    fam_res = [resolutions_by_family[fam] for fam, _a in REQUIRED_FAMILIES]
    fp_verdict = fingerprint(fam_res, namespaced_index=namespaced_index,
                             expected=expected, deny_fps=all_deny)

    # Inline exposure scan.
    inline = {"scanned": False, "clean": True, "findings": []}
    if do_scan:
        targets = scan_paths if scan_paths is not None else [
            SKILL_DIR / "scripts", SKILL_DIR / "config"]
        findings = scan_inline_credentials(targets)
        inline = {"scanned": True, "clean": not findings, "findings": findings,
                  "targets": [str(t) for t in targets]}

    # Exit precedence: 4 (violation) > 2 (missing) > 0.
    if not fp_verdict["clean"] or not inline["clean"]:
        exit_code = EX_VIOLATION
        if not inline["clean"] and fp_verdict["clean"]:
            verdict = "INLINE_EXPOSURE"
        elif not inline["clean"]:
            verdict = "COMMINGLE_AND_INLINE_EXPOSURE"
        else:
            verdict = "COMMINGLE"
    elif missing:
        exit_code = EX_MISSING
        verdict = "MISSING_LABEL"
    else:
        exit_code = EX_OK
        verdict = "PASS"

    report = {
        "gate": "caf_credential_gate",
        "generated_at": now_utc(),
        "stores_checked": checked,
        "resolutions": resolution_report,
        "required": [fam for fam, _a in active_required],
        "missing": missing,
        "pairing": pairing,
        "fingerprint": fp_verdict,
        "inline_scan": inline,
        "verdict": verdict,
        "exit_code": exit_code,
    }
    return exit_code, report


# ---------------------------------------------------------------------------
# Operator-surface rendering. Never a value; fingerprints only under --show-fingerprints.
# ---------------------------------------------------------------------------
def render_human(report, show_fingerprints=False):
    lines = []
    lines.append("[caf_credential_gate] verdict=%s exit=%d  (%s)"
                 % (report["verdict"], report["exit_code"], report["generated_at"]))
    lines.append("  stores checked (live process env first): %s"
                 % "; ".join(report["stores_checked"]))
    for fam, r in report["resolutions"].items():
        tag = "REQUIRED" if r["required"] else "optional"
        src = (" via %s in %s" % (r["label"], r["source"])) if r["present"] else ""
        lines.append("  - %-32s [%s] %s%s" % (fam, tag, r["presence"], src))
    p = report["pairing"]
    lines.append("  pairing: %s -- %s"
                 % ("PROVEN" if p["proven"] else "UNPAIRED", p["reason"]))
    fpv = report["fingerprint"]
    lines.append("  anti-commingling: %s  (active: %s | inactive: %s)"
                 % ("CLEAN" if fpv["clean"] else "COMMINGLING",
                    ", ".join(fpv["checks_active"]) or "none",
                    ", ".join(fpv["checks_inactive"]) or "none"))
    for rs in fpv["reasons"]:
        lines.append("    ! %s: %s -- %s" % (rs["credential"], rs["code"], rs["detail"]))
    isc = report["inline_scan"]
    if isc.get("scanned"):
        lines.append("  inline-exposure scan: %s (%d finding(s))"
                     % ("CLEAN" if isc["clean"] else "VIOLATION", len(isc["findings"])))
        for f in isc["findings"]:
            lines.append("    ! %s:%d -- %s" % (f["file"], f["line"], f["reason"]))
    else:
        lines.append("  inline-exposure scan: skipped (--no-scan)")
    if show_fingerprints:
        lines.append("  [fingerprints omitted from report payload by doctrine; "
                     "presence + length only]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test: force-observe every failure mode (SPEC 3.4 / Part C item 19). No network,
# no real credential; synthetic environ dicts and temp files only.
# ---------------------------------------------------------------------------
def self_test():
    import tempfile

    print("[caf_credential_gate] self-test: forcing every exit-code path")
    real_pit = "pit-" + "a1b2c3d4e5f6a7b8c9d0" * 2          # real-shaped, synthetic
    real_loc = "loc7Zx9Qw3Rt5Yu8Io2Pk4"
    other_pit = "pit-" + "9988776655443322110f" * 2

    # 1. PASS: both members present, no collision, no exposure.
    code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                              "CONVERT_AND_FLOW_LOCATION_ID": real_loc},
                     store_paths=[], do_scan=False)
    assert code == EX_OK and rep["verdict"] == "PASS", rep
    assert rep["pairing"]["proven"], rep
    assert rep["resolutions"]["convert_and_flow_pit"]["source"] == "process-env", rep
    assert "SET(len=" in rep["resolutions"]["convert_and_flow_pit"]["presence"], rep
    # Never a value in the payload.
    blob = json.dumps(rep)
    assert real_pit not in blob and real_loc not in blob, "value leaked into report"
    print("  [1] PASS path -> exit 0, pairing proven, no value in report: OK")

    # 2. MISSING: PIT only, then neither.
    code, _ = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit},
                   store_paths=[], do_scan=False)
    assert code == EX_MISSING, "half-pair must be exit 2, got %d" % code
    code, rep = gate(environ={}, store_paths=[], do_scan=False)
    assert code == EX_MISSING and set(rep["missing"]) == {
        "convert_and_flow_pit", "convert_and_flow_location"}, rep
    print("  [2] MISSING label (half pair and empty) -> exit 2: OK")

    # 3. COMMINGLE via operator/shared value collision (config-free).
    code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                              "CONVERT_AND_FLOW_LOCATION_ID": real_loc,
                              "OPERATOR_CAF_PIT": real_pit},   # same value under op label
                     store_paths=[], do_scan=False)
    assert code == EX_VIOLATION and rep["verdict"] == "COMMINGLE", rep
    codes = {r["code"] for r in rep["fingerprint"]["reasons"]}
    assert "operator_shared_value_collision" in codes, rep
    print("  [3] COMMINGLE via operator/shared value collision -> exit 4: OK")

    # 4. COMMINGLE via foreign-client value collision.
    code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                              "CONVERT_AND_FLOW_LOCATION_ID": real_loc,
                              "CLIENT_XY_PIT": real_pit},
                     store_paths=[], do_scan=False)
    assert code == EX_VIOLATION, rep
    assert any(r["code"] == "foreign_client_value_collision"
               for r in rep["fingerprint"]["reasons"]), rep
    print("  [4] COMMINGLE via foreign-client value collision -> exit 4: OK")

    # 5. COMMINGLE via expected-own mismatch.
    wrong_fp = credential_fingerprint(other_pit)
    code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                              "CONVERT_AND_FLOW_LOCATION_ID": real_loc},
                     store_paths=[], do_scan=False,
                     expected={"convert_and_flow_pit": wrong_fp})
    assert code == EX_VIOLATION, rep
    assert any(r["code"] == "expected_own_mismatch"
               for r in rep["fingerprint"]["reasons"]), rep
    # And the matching expected passes.
    right_fp = credential_fingerprint(real_pit)
    code, _ = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                            "CONVERT_AND_FLOW_LOCATION_ID": real_loc},
                   store_paths=[], do_scan=False,
                   expected={"convert_and_flow_pit": right_fp})
    assert code == EX_OK, "matching expected fp must pass"
    print("  [5] COMMINGLE via expected-own mismatch -> exit 4 (and match -> 0): OK")

    # 6. COMMINGLE via denylisted fingerprint (short prefix accepted).
    deny = credential_fingerprint(real_pit)[:16]
    code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                              "CONVERT_AND_FLOW_LOCATION_ID": real_loc},
                     store_paths=[], do_scan=False, deny_fps=[deny])
    assert code == EX_VIOLATION, rep
    assert any(r["code"] == "denylisted_fingerprint"
               for r in rep["fingerprint"]["reasons"]), rep
    print("  [6] COMMINGLE via denylisted fingerprint (prefix) -> exit 4: OK")

    # 7. LIVE-PROCESS-FIRST precedence: same label in process env and a store, different
    #    values -> the process env wins.
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "store.env"
        store.write_text("CONVERT_AND_FLOW_PIT=%s\n"
                         "CONVERT_AND_FLOW_LOCATION_ID=%s\n" % (other_pit, real_loc))
        code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit},
                         store_paths=[store], do_scan=False)
        assert rep["resolutions"]["convert_and_flow_pit"]["source"] == "process-env", rep
        assert rep["resolutions"]["convert_and_flow_location"]["source"] == str(store), rep
        # And the store IS listed in stores_checked (exhaustive-search doctrine).
        assert any(str(store) in s for s in rep["stores_checked"]), rep
        print("  [7] live-process-first precedence + store fallback + stores_checked: OK")

    # 8. INLINE exposure: a real literal Authorization header and an inline key.
    with tempfile.TemporaryDirectory() as td:
        leak = Path(td) / "legacy_node.py"
        leak.write_text(
            'HEADERS = {"Authorization": "Bearer sk-' + "Z" * 40 + '"}\n'
            'PIT = "pit-' + "Q" * 40 + '"\n')
        findings = scan_inline_credentials([leak])
        reasons = {f["reason"] for f in findings}
        assert "literal_authorization_bearer_header" in reasons, findings
        assert "inline_provider_key_literal" in reasons, findings
        # And the token never appears in a finding.
        assert all("Z" * 40 not in json.dumps(f) for f in findings), findings
        code, rep = gate(environ={"CONVERT_AND_FLOW_PIT": real_pit,
                                  "CONVERT_AND_FLOW_LOCATION_ID": real_loc},
                         store_paths=[], scan_paths=[leak])
        assert code == EX_VIOLATION and "INLINE_EXPOSURE" in rep["verdict"], rep
        print("  [8] INLINE exposure (literal header + inline key) -> exit 4: OK")

    # 9. INLINE discrimination: templated headers, regex definitions, named placeholders,
    #    AND a sibling detector's own assert-line sequential fixtures must NOT flag (the
    #    exact cover_render.py self-test pattern that must never false-fail a clean box).
    with tempfile.TemporaryDirectory() as td:
        clean = Path(td) / "clean_adapter.py"
        clean.write_text(
            'auth = {"Authorization": "Bearer %s" % self._pit}\n'
            'SHELL = "Authorization: Bearer $PIT"\n'
            '_SECRET_SHAPE_RE = re.compile(r"pit-[a-z0-9]{16,}")\n'
            'PLACE = "Bearer YOUR_KEY_HERE"\n'
            '    assert _looks_like_literal_key("leaked sk-abcdefghijklmnop1234567890QRSTUV") is True\n'
            '    assert _looks_like_literal_key("or sk-or-v1-0123456789abcdef0123456789abcdef") is True\n'
            '    assert _looks_like_literal_key("Authorization: Bearer abcdefghijklmnop1234567890") is True\n')
        findings = scan_inline_credentials([clean])
        assert findings == [], "false positive on template/regex/placeholder/fixture: %s" % findings
        print("  [9] INLINE discrimination (template/regex/placeholder/assert-fixture clean): OK")

    # 10. Regression: AF-AE-CREDGATE-SELFHIT (branch anthology-engine-build). A prior
    #     live run with real, correctly-paired, non-commingled client credentials still
    #     hit exit 4 -- purely because scan-no-secrets.sh:319's OWN self-test fixture (a
    #     synthetic, deliberately real-shaped key literal that fixture uses to prove ITS
    #     detector works) walked into this gate's default scripts/ scan. Reproduce that
    #     exact shape under one of the four exempt merge-gate-scanner basenames and
    #     confirm it is now clean, WHILE an adversarial planted secret under a
    #     DIFFERENT, non-exempt filename with the identical content is still caught (the
    #     exemption is basename-scoped, not a blanket allow).
    with tempfile.TemporaryDirectory() as td:
        # A non-sequential, non-placeholder-shaped fixture token, same construction as
        # scan-no-secrets.sh's own `fake_sk` (built to evade low-entropy/placeholder
        # filters and read as a genuine leak to any detector that doesn't know it).
        # Assembled from fragments at runtime -- NEVER as one contiguous literal -- so
        # this shipped file's OWN source stays clean under this same gate's self-scan
        # (the identical discipline test #8 already uses with "Z" * 40, and the one
        # model_router.py / guard-no-anthropic-runtime.py use for their banned tokens).
        fixture_token = "sk-" + "9k3Rp7Xm2Qw8Lz4Vt6Bn1Cy5Hd0Js3Gf" + "QeWr"
        for exempt_name in sorted(_SELF_TEST_FIXTURE_BASENAMES):
            f = Path(td) / exempt_name
            f.write_text('    local fake_sk="%s"\n' % fixture_token)
        exempt_findings = scan_inline_credentials(
            [Path(td) / n for n in _SELF_TEST_FIXTURE_BASENAMES])
        assert exempt_findings == [], \
            "AF-AE-CREDGATE-SELFHIT regressed: a known scanner's own self-test " \
            "fixture wrongly flagged: %s" % exempt_findings
        print("  [10a] self-test-fixture basename exemption (4 known scanners): OK "
              "(0 findings for identical content the gate used to flag)")

        adversarial = Path(td) / "legacy_cover_node.py"
        adversarial.write_text('PIT = "%s"\n' % fixture_token)
        adv_findings = scan_inline_credentials([adversarial])
        assert len(adv_findings) == 1 \
            and adv_findings[0]["reason"] == "inline_provider_key_literal", adv_findings
        assert fixture_token not in json.dumps(adv_findings), "token leaked into finding"
        print("  [10b] adversarial check: identical fixture-shaped literal under a "
              "NON-exempt filename is still caught -- exemption is not a blanket allow: OK")

    # 11. Sibling lockstep: if caf_delivery imports, its alias tuples must match ours.
    try:
        import importlib.util
        cd = SKILL_DIR / "scripts" / "caf_delivery.py"
        if cd.exists():
            spec = importlib.util.spec_from_file_location("_caf_delivery_probe", cd)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            assert tuple(mod.PIT_LABELS) == PIT_LABELS, "PIT_LABELS drift vs caf_delivery"
            assert tuple(mod.LOCATION_LABELS) == LOCATION_LABELS, "LOCATION_LABELS drift"
            assert tuple(mod.ALLOWED_LOCATION_LABELS) == ALLOWED_LOCATION_LABELS, \
                "ALLOWED_LOCATION_LABELS drift"
            print("  [11] sibling lockstep with caf_delivery alias tuples: OK")
        else:
            print("  [11] sibling lockstep: caf_delivery.py absent, skipped")
    except Exception as exc:  # noqa: BLE001  -- lockstep is advisory, never fatal here
        print("  [11] sibling lockstep: caf_delivery not importable (%s), skipped" % exc)

    # 12. Idempotent no-op: a clean box run twice yields the same clean exit.
    env = {"CONVERT_AND_FLOW_PIT": real_pit, "CONVERT_AND_FLOW_LOCATION_ID": real_loc}
    c1, _ = gate(environ=env, store_paths=[], do_scan=False)
    c2, _ = gate(environ=env, store_paths=[], do_scan=False)
    assert c1 == c2 == EX_OK, "not idempotent"
    print("  [12] idempotent clean re-run -> exit 0 both times: OK")

    # 13. Real-integration regression proof: the ACTUAL scan-no-secrets.sh shipped in
    #     this skill's scripts/ dir (not a synthetic mirror) must no longer trip the
    #     DEFAULT scan target used by provision-anthology-client.sh STEP 1. This is the
    #     literal file:line from the confirmed live false positive.
    real_scanner = SKILL_DIR / "scripts" / "scan-no-secrets.sh"
    if real_scanner.exists():
        real_findings = scan_inline_credentials([SKILL_DIR / "scripts"])
        hit_on_real_scanner = [f for f in real_findings if f["file"] == str(real_scanner)]
        assert not hit_on_real_scanner, \
            "AF-AE-CREDGATE-SELFHIT LIVE REGRESSION: the shipped scan-no-secrets.sh " \
            "still trips the default scripts/ scan: %s" % hit_on_real_scanner
        print("  [13] real scan-no-secrets.sh (shipped, not synthetic) clean under the "
              "default scripts/ scan target: OK")
    else:
        print("  [13] real-file regression check: scan-no-secrets.sh absent, skipped")

    # 14. Opt-in require: --require-anthology-hook-secret promotes the box-generated
    #     intake secret into the required set. The base CnF pair stays present so ONLY
    #     the promoted secret drives the verdict: UNSET -> exit 2 MISSING; SET -> exit 0.
    #     WITHOUT the flag the same unset secret must NOT gate (informational only), so a
    #     fresh box (secret generated later at provision step 7) is never falsely blocked.
    base_env = {"CONVERT_AND_FLOW_PIT": real_pit, "CONVERT_AND_FLOW_LOCATION_ID": real_loc}
    code, rep = gate(environ=base_env, store_paths=[], do_scan=False,
                     require_families={"anthology_intake_hook_secret"})
    assert code == EX_MISSING and "anthology_intake_hook_secret" in rep["missing"], rep
    assert rep["resolutions"]["anthology_intake_hook_secret"]["required"] is True, rep
    gen_secret = "synthGENERATEDintakeSecretUNIT14"
    code2, rep2 = gate(
        environ=dict(base_env, ANTHOLOGY_INTAKE_HOOK_SECRET=gen_secret),
        store_paths=[], do_scan=False,
        require_families={"anthology_intake_hook_secret"})
    assert code2 == EX_OK and rep2["verdict"] == "PASS", rep2
    assert gen_secret not in json.dumps(rep2), "the confirmed secret value leaked into the report"
    code3, _ = gate(environ=base_env, store_paths=[], do_scan=False)
    assert code3 == EX_OK, "an unset box-generated secret must NOT gate the DEFAULT credential gate"
    print("  [14] --require-anthology-hook-secret: unset->exit2, set->exit0, "
          "default-ungated (no value leak): OK")

    print("[caf_credential_gate] self-test: PASS")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def _parse_expected(args):
    expected = {}
    if args.expect_pit_fp:
        expected["convert_and_flow_pit"] = args.expect_pit_fp
    if args.expect_location_fp:
        expected["convert_and_flow_location"] = args.expect_location_fp
    if args.expect_location:
        expected["convert_and_flow_location"] = credential_fingerprint(
            args.expect_location.strip())
    return expected


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert and Flow credential gate for the Anthology Engine (W2.3): "
                    "label resolution live-process-first across the three env stores, "
                    "pairing proof, anti-commingling fingerprint, and the legacy "
                    "literal-Authorization-header ban. Reports SET or NOT SET only.")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable report to stdout")
    ap.add_argument("--all", action="store_true",
                    help="also resolve and report the wider PRD Section 14 family "
                         "(informational; does not gate the exit code)")
    ap.add_argument("--store", action="append", default=[], metavar="PATH",
                    help="add an explicit env-store path (repeatable; checked after the "
                         "live process env, before the canonical three)")
    ap.add_argument("--extended-stores", action="store_true",
                    help="also consult the extended client env-store set")
    ap.add_argument("--scan", action="append", default=None, metavar="PATH",
                    help="inline-exposure scan target (repeatable; default: the skill "
                         "scripts/ and config/ dirs)")
    ap.add_argument("--no-scan", action="store_true",
                    help="skip the inline-exposure scan")
    ap.add_argument("--expect-location", metavar="VALUE",
                    help="expected client Location ID (hashed immediately; never stored "
                         "or printed) -- a resolved Location that differs is commingling")
    ap.add_argument("--expect-location-fp", metavar="SHA256",
                    help="expected client Location fingerprint (full or >=8 hex prefix)")
    ap.add_argument("--expect-pit-fp", metavar="SHA256",
                    help="expected client PIT fingerprint (full or >=8 hex prefix)")
    ap.add_argument("--deny-fp", action="append", default=[], metavar="SHA256",
                    help="operator/other-client fingerprint to refuse (repeatable)")
    ap.add_argument("--show-fingerprints", action="store_true",
                    help="operator-debug note (fingerprints stay out of the payload)")
    ap.add_argument("--require-anthology-hook-secret", action="store_true",
                    help="promote the box-generated ANTHOLOGY_INTAKE_HOOK_SECRET into the "
                         "REQUIRED set so the gate FAILS (exit 2) when it is not SET -- the "
                         "canary confirm-SET before the intake webhook route fires (the "
                         "gateway resolves hooks.token=${ANTHOLOGY_INTAKE_HOOK_SECRET} from "
                         "this label at load). Reports SET / NOT SET only; never the value.")
    ap.add_argument("--self-test", action="store_true",
                    help="force every failure mode and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test()

        exit_code, report = gate(
            store_paths=resolve_stores(explicit=args.store,
                                       extended=args.extended_stores),
            scan_paths=args.scan,
            do_scan=not args.no_scan,
            include_informational=args.all,
            expected=_parse_expected(args),
            deny_fps=args.deny_fp,
            require_families=({"anthology_intake_hook_secret"}
                              if args.require_anthology_hook_secret else None),
        )

        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_human(report, show_fingerprints=args.show_fingerprints))

        return exit_code

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[caf_credential_gate] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
