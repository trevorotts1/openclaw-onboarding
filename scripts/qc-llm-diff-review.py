#!/usr/bin/env python3
# qc-llm-diff-review.py — LLM DIFF REVIEWER (fleet-wide leak gate, R6)
#
# ─── THE RULE THIS GATE ENFORCES (operator, 2026-07-11 — AUTHORITATIVE) ───────
# This repo is FLEET-WIDE: it ships to every client. Exactly THREE things are
# enforceable, and NOTHING else:
#
#   1. No CLIENT / ROSTER MEMBER real human names — an actual customer or team
#      member. NOT book characters. NOT personas. NOT authors of referenced works.
#   2. No genuine secrets — live tokens, API keys, `pit-` GHL tokens, bot tokens,
#      private keys. ABSOLUTE. DO NOT WEAKEN THIS.
#   3. Nothing built for ONE client — repo content stays generic + fleet-reusable.
#
# ─── EXPLICITLY EXEMPT — never flag, block, or scrub ──────────────────────────
#   • Cloudflare Access Application UUIDs / AUD tags
#   • Telegram chat IDs
#   • GHL location IDs
#   • ANY opaque identifier (UUID, numeric ID, hash)
#   • Book titles
#   • Persona names derived from books
#   • Authors of referenced works
#   • Product proper nouns
#
# GOVERNING PRINCIPLE: opaque infrastructure identifiers and product content are
# NOT the target.
#
# ─── ⛔ WHY THIS IS AN LLM AND NOT A GREP ─────────────────────────────────────
# NEVER enforce the NAME rule with a grep / regex / name-roster. A pattern match
# cannot tell a client's real name from a book-persona name — it either misses
# real leaks or blocks legitimate product PRs forever. (Regex IS still correct
# for SECRETS — a secret has a literal shape; a human name does not. That is why
# a cheap secret regex runs here as a pre-filter IN ADDITION to the model.)
#
# ─── ✅ MODEL PROVIDER — GOOGLE GEMINI FLASH ──────────────────────────────────
# This reviewer calls GOOGLE GEMINI FLASH via the Generative Language API — the
# fleet's own provider. Do NOT wire this gate to a provider the fleet does not
# run (an earlier draft's Anthropic/Haiku call was a defect: no such key exists
# on the fleet — it has been removed, do not reintroduce it).
#   • If this gate is ever run on a CLIENT box, it must use the CLIENT's own
#     configured provider — never a provider the client does not own. Client
#     sovereignty is absolute.
#
# ─── FAIL CLOSED (non-negotiable) ─────────────────────────────────────────────
# Non-zero exit, malformed JSON, API error, timeout, or an empty/blocked model
# response → BLOCK with `reviewer_error`. A guard that fails open is not a guard.
#
# ─── CREDENTIAL ───────────────────────────────────────────────────────────────
#   Reads the Google Generative Language API key from the FIRST set of:
#       GEMINI_API_KEY  →  GOOGLE_AI_STUDIO_API_KEY  →  GOOGLE_API_KEY
#   (These three env-var names are aliases for the SAME single Google key.)
#   In GitHub Actions add ONE repo secret named `GEMINI_API_KEY`. No key → BLOCK.
#
# Exit codes: 0 = PASS · 1 = BLOCK (findings or reviewer_error) · 2 = bad usage
#
# Usage:
#   python3 scripts/qc-llm-diff-review.py                       # origin/main...HEAD
#   python3 scripts/qc-llm-diff-review.py --base origin/main
#   python3 scripts/qc-llm-diff-review.py --diff-file some.diff # review a saved diff
#   python3 scripts/qc-llm-diff-review.py --diff-file d.diff \
#           --response-file canned.txt                          # TEST-ONLY transport stub

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# Reviewer model. Default is the rolling `-latest` Flash alias so a single model
# retirement never silently disables the gate (Google retires pinned versions —
# e.g. gemini-2.5-flash / 2.0-flash returned HTTP 404 "no longer available").
# Override with QC_LLM_REVIEW_MODEL to pin a specific version.
MODEL = os.environ.get("QC_LLM_REVIEW_MODEL", "gemini-flash-latest")
API_BASE = os.environ.get(
    "QC_LLM_REVIEW_API_BASE",
    "https://generativelanguage.googleapis.com/v1beta",
)
TIMEOUT_S = int(os.environ.get("QC_LLM_REVIEW_TIMEOUT", "90"))
MAX_LINES_PER_CHUNK = 250

# The three env-var aliases for the ONE Google Generative Language API key.
API_KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GOOGLE_API_KEY")


def get_api_key():
    for name in API_KEY_ENV_NAMES:
        v = os.environ.get(name, "")
        if v:
            return v
    return ""

SYSTEM_PROMPT = """You review a diff from a FLEET-WIDE repo shipped to every client. BLOCK on exactly three things:
1. A CLIENT or ROSTER MEMBER's real human name (an actual customer or team member).
2. A genuine secret — live token, API key, `pit-` GHL token, bot token, private key.
3. Content built for ONE specific client rather than the generic fleet.

EXPLICITLY ALLOWED — never flag: Cloudflare Access Application UUIDs / AUD tags; Telegram chat IDs; GHL location IDs; any opaque identifier (UUID, numeric ID, hash); book titles; persona names derived from books; authors of referenced works; product proper nouns. Opaque infrastructure identifiers and product content are NOT the target.

A hostname that literally CONTAINS a client's name -> BLOCK on the name. An opaque hostname -> ALLOW and list under flag_for_operator.
NEVER output the name or the secret value itself — file, line, and category only.

Respond with ONLY a JSON object, no prose and no code fences:
{"verdict":"PASS"|"BLOCK","findings":[{"file":"...","line":42,"category":"client_name"|"secret"|"one_client_build","confidence":"high"|"medium"}],"flag_for_operator":[{"file":"...","line":7,"why":"opaque hostname"}],"counts":{"client_name":0,"secret":0,"one_client_build":0}}"""

# ─── Cheap SECRET pre-filter (regex is CORRECT for secrets — literal shapes) ───
# Runs IN ADDITION to the model. Never used for names. These are credential
# SHAPES; the model independently catches any key-shaped string it also sees.
SECRET_PATTERNS = [
    ("ghl_pit_token", re.compile(r"pit-[0-9a-f]{8}-[0-9a-f]{4}")),
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Paths whose ADDED lines are not scanned: this guard itself + its fixtures hold
# banned SHAPES as detection data / synthetic test literals, and lockfiles are
# machine-generated noise.
EXCLUDED_PATH_RE = re.compile(
    r"(^|/)("
    r"qc-llm-diff-review\.py"
    r"|selftest-qc-llm-diff-review\.sh"
    r"|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock"
    r"|.*\.lock"
    r")$"
    r"|(^|/)tests/fixtures/llm-diff-review/"
)

BINARY_EXT_RE = re.compile(
    r"\.(png|jpe?g|gif|webp|ico|pdf|zip|gz|tgz|bz2|xz|mp4|mov|mp3|wav|woff2?|ttf|eot|so|dylib|dll|bin|exe|jar|class|pyc|db|sqlite3?)$",
    re.I,
)


def parse_added_lines(diff_text):
    """Return [(path, lineno, content)] for ADDED lines only, skipping excluded paths."""
    added = []
    path = None
    new_ln = 0
    skip = False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            path, new_ln, skip = None, 0, False
            continue
        if raw.startswith("+++ "):
            p = raw[4:].strip()
            if p == "/dev/null":
                path, skip = None, True
                continue
            if p.startswith("b/"):
                p = p[2:]
            path = p
            skip = bool(EXCLUDED_PATH_RE.search(p)) or bool(BINARY_EXT_RE.search(p))
            continue
        if raw.startswith("Binary files "):
            skip = True
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_ln = int(m.group(1)) if m else 0
            continue
        if path is None or skip:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            added.append((path, new_ln, raw[1:]))
            new_ln += 1
        elif raw.startswith(" "):
            new_ln += 1
        # '-' lines do not advance the new-file counter
    return added


def secret_prefilter(added):
    findings = []
    for path, ln, content in added:
        for _label, pat in SECRET_PATTERNS:
            if pat.search(content):
                findings.append(
                    {"file": path, "line": ln, "category": "secret", "confidence": "high"}
                )
                break
    return findings


def chunk(added, size):
    for i in range(0, len(added), size):
        yield added[i : i + size]


def render_chunk(rows):
    return "\n".join("%s:%d: %s" % (p, ln, c) for p, ln, c in rows)


def call_model(payload_text, api_key):
    """Return the model's raw text from Google Gemini. Raise on any transport /
    API failure or an empty/blocked response (fail closed)."""
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": "Review these ADDED diff lines (format `file:line: content`):\n\n"
                            + payload_text
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 4000,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")
    url = "%s/models/%s:generateContent" % (API_BASE, MODEL)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cands = data.get("candidates") or []
    if not cands:
        # No candidate at all — prompt blocked, quota, etc. Fail closed.
        raise RuntimeError("model returned no candidates")
    cand = cands[0]
    parts = cand.get("content", {}).get("parts", []) or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        # Truncated (MAX_TOKENS), safety-blocked, or empty. Fail closed rather
        # than treat a contentless reply as a PASS.
        raise RuntimeError(
            "empty model response (finishReason=%s)" % cand.get("finishReason")
        )
    return text


def parse_verdict(text):
    """Parse the model's verdict. Any deviation raises -> caller BLOCKs.

    Tolerates two harmless model habits (code fences, and trailing prose after
    the JSON) by decoding the FIRST top-level JSON object. It does NOT tolerate
    a missing/invalid verdict — that still raises and fails closed.
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    start = t.find("{")
    if start == -1:
        raise ValueError("no JSON object in reviewer response")
    obj, _end = json.JSONDecoder().raw_decode(t[start:])  # raises on malformed JSON
    if not isinstance(obj, dict):
        raise ValueError("verdict is not a JSON object")
    if obj.get("verdict") not in ("PASS", "BLOCK"):
        raise ValueError("missing/invalid 'verdict'")
    if not isinstance(obj.get("findings", []), list):
        raise ValueError("'findings' is not a list")
    if not isinstance(obj.get("flag_for_operator", []), list):
        raise ValueError("'flag_for_operator' is not a list")
    return obj


def block_on_error(reason, prefilter_findings=None):
    """FAIL CLOSED. Any regex-prefilter secret hits are still reported, so a
    reviewer outage never hides a secret that the cheap pre-filter already saw."""
    findings = list(prefilter_findings or [])
    findings.append(
        {"file": "-", "line": 0, "category": "reviewer_error", "confidence": "high"}
    )
    counts = {"client_name": 0, "secret": 0, "one_client_build": 0}
    for f in findings:
        if f.get("category") in counts:
            counts[f["category"]] += 1
    out = {
        "verdict": "BLOCK",
        "findings": findings,
        "flag_for_operator": [],
        "counts": counts,
        "reviewer_error": reason,
    }
    print(json.dumps(out, indent=2))
    print(
        "\n[qc-llm-diff-review] BLOCK — reviewer_error: %s\n"
        "  FAIL CLOSED: a guard that fails open is not a guard." % reason,
        file=sys.stderr,
    )
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--diff-file", default=None)
    ap.add_argument(
        "--response-file",
        default=None,
        help="TEST-ONLY: read the model response from a file instead of calling the model.",
    )
    args = ap.parse_args()

    # ── Acquire the diff ──────────────────────────────────────────────────────
    if args.diff_file:
        try:
            with open(args.diff_file, "r", encoding="utf-8", errors="replace") as fh:
                diff_text = fh.read()
        except OSError as e:
            return block_on_error("cannot read --diff-file: %s" % e)
    else:
        try:
            diff_text = subprocess.run(
                ["git", "diff", "%s...%s" % (args.base, args.head)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError) as e:
            return block_on_error("git diff failed: %s" % e)

    added = parse_added_lines(diff_text)
    if not added:
        print(
            json.dumps(
                {
                    "verdict": "PASS",
                    "findings": [],
                    "flag_for_operator": [],
                    "counts": {"client_name": 0, "secret": 0, "one_client_build": 0},
                },
                indent=2,
            )
        )
        print("\n[qc-llm-diff-review] PASS — no reviewable added lines.", file=sys.stderr)
        return 0

    findings = secret_prefilter(added)  # regex pre-filter: secrets ONLY
    flags = []

    # ── Model pass ────────────────────────────────────────────────────────────
    if args.response_file:
        try:
            with open(args.response_file, "r", encoding="utf-8", errors="replace") as fh:
                raw_responses = [fh.read()]
        except OSError as e:
            return block_on_error("cannot read --response-file: %s" % e, findings)
    else:
        api_key = get_api_key()
        if not api_key:
            return block_on_error(
                "no Google API key (set GEMINI_API_KEY / GOOGLE_AI_STUDIO_API_KEY / GOOGLE_API_KEY)",
                findings,
            )
        chunks = list(chunk(added, MAX_LINES_PER_CHUNK))
        raw_responses = []
        for rows in chunks:
            try:
                raw_responses.append(call_model(render_chunk(rows), api_key))
            except urllib.error.HTTPError as e:
                return block_on_error("API HTTP %s" % e.code, findings)
            except urllib.error.URLError as e:
                return block_on_error("API unreachable: %s" % e.reason, findings)
            except Exception as e:  # timeout, empty/blocked response, bad payload
                return block_on_error("API call failed: %s" % type(e).__name__, findings)

    for raw in raw_responses:
        try:
            v = parse_verdict(raw)
        except Exception as e:
            return block_on_error("malformed reviewer JSON: %s" % e, findings)
        findings.extend(v.get("findings", []))
        flags.extend(v.get("flag_for_operator", []))

    # ── Merge + verdict ───────────────────────────────────────────────────────
    seen, deduped = set(), []
    for f in findings:
        k = (f.get("file"), f.get("line"), f.get("category"))
        if k not in seen:
            seen.add(k)
            deduped.append(f)

    counts = {"client_name": 0, "secret": 0, "one_client_build": 0}
    for f in deduped:
        c = f.get("category")
        if c in counts:
            counts[c] += 1

    verdict = "BLOCK" if deduped else "PASS"
    print(
        json.dumps(
            {
                "verdict": verdict,
                "findings": deduped,
                "flag_for_operator": flags,
                "counts": counts,
            },
            indent=2,
        )
    )
    if verdict == "BLOCK":
        print(
            "\n[qc-llm-diff-review] BLOCK — %d finding(s). File/line/category only;\n"
            "  the offending name/secret is deliberately NOT printed." % len(deduped),
            file=sys.stderr,
        )
        return 1
    print(
        "\n[qc-llm-diff-review] PASS — %d added line(s) reviewed, %d operator flag(s)."
        % (len(added), len(flags)),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
