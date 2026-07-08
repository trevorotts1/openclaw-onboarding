#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: SCRUB GATE (build + runtime output screen)
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. Runs at BUILD time over every shipped file
# AND at RUNTIME over generated content. Screens for four classes of leak:
#   * client-name tokens   -> AF-SM-CLIENT-NAME  (list is env-supplied, NEVER shipped)
#   * secret patterns      -> AF-SM-SECRET       (sk-or-v1-/pit-/JWT/sk-ant-/Google/Slack/accessToken)
#   * n8n pinData blocks   -> AF-SM-PINDATA
#   * Anthropic model ids  -> AF-SM-NOANTHROPIC  (G-NOANTHROPIC: client runtime NEVER uses Anthropic)
#
# ⚠️ SECURITY DISCIPLINE (fleet rule): this screen CONFIRMS a hit and names the
# file + line + which pattern class matched. It NEVER prints the matched value
# (no sed-masking, no snippet) — a secret is confirmed SET-and-forbidden, never
# echoed. The client-name list is read from the environment and is never written
# into a shipped file.
#
# The Anthropic screen matches concrete model-id shapes (claude-opus-4...,
# anthropic/claude-3..., sk-ant-, us.anthropic.claude, ANTHROPIC_API_KEY), NOT
# the bare word "Anthropic" — so a doc that STATES the never-Anthropic rule is
# clean while a real client-path model id is caught.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 scrub_gate.py <file|dir> [<file|dir> ...] [--json]
#   python3 scrub_gate.py --self-test
# Env: SMIB_SCRUB_NAMES_FILE=/path (newline list) or SMIB_SCRUB_NAMES="a,b,c"
# =============================================================================
"""Fail-closed client-name/secret/pinData/Anthropic scrub gate for Skill 57."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_NAME = "AF-SM-CLIENT-NAME"
AF_SECRET = "AF-SM-SECRET"
AF_PINDATA = "AF-SM-PINDATA"
AF_NOANTHROPIC = "AF-SM-NOANTHROPIC"

_SELF = Path(__file__).resolve()
# The two enforcement DETECTORS carry the forbidden literals (the Anthropic/secret
# regexes + their negative-test fixtures) by necessity, so a directory walk skips
# them the same way it self-excludes this scanner. Every other file — prompts,
# config, docs, the other 5 provers, and ALL generated content — is scanned.
_SKIP_FILES = {_SELF, (_SELF.parent / "build_manifest.py").resolve()}
_TEXT_EXT = {".py", ".json", ".md", ".sh", ".txt", ".yml", ".yaml", ".cfg", ".ini"}
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

# --- secret patterns (report the CLASS only; never the value) ---
_SECRET_PATTERNS = [
    ("openrouter-key", re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}")),
    ("ghl-pit-token", re.compile(r"pit-[A-Za-z0-9]{20,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9\-]{16,}")),
    ("openai-proj-key", re.compile(r"sk-proj-[A-Za-z0-9\-]{16,}")),
    ("generic-sk-key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("jwt-bearer", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}")),
    ("google-api-key", re.compile(r"AIza[A-Za-z0-9_\-]{20,}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("access-token-value", re.compile(r"accessToken\"?\s*[:=]\s*\"?[A-Za-z0-9._\-]{20,}")),
]

# --- Anthropic model-id shapes (concrete ids only, NOT the bare word) ---
_ANTHROPIC_PATTERNS = [
    ("claude-model-id", re.compile(r"claude-(?:opus|sonnet|haiku|instant|fable|[0-9])", re.I)),
    ("anthropic-slash-model", re.compile(r"anthropic/claude-(?:[0-9]|opus|sonnet|haiku|instant)", re.I)),
    ("bedrock-anthropic", re.compile(r"us\.anthropic\.claude", re.I)),
    ("anthropic-npm", re.compile(r"@anthropic-ai/")),
    ("anthropic-env", re.compile(r"ANTHROPIC_API_KEY")),
]

_PINDATA_RE = re.compile(r"\"pinData\"\s*:")


def _client_names():
    """Load the build-private client-name list from the environment. Never shipped."""
    names = []
    fp = os.environ.get("SMIB_SCRUB_NAMES_FILE")
    if fp and Path(fp).is_file():
        try:
            names += [ln.strip() for ln in Path(fp).read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            pass
    inline = os.environ.get("SMIB_SCRUB_NAMES", "")
    names += [t.strip() for t in inline.split(",") if t.strip()]
    return names


def scan_secrets(text):
    return [(AF_SECRET, name) for name, rx in _SECRET_PATTERNS if rx.search(text)]


def scan_pindata(text):
    return [(AF_PINDATA, "n8n-pinData-block")] if _PINDATA_RE.search(text) else []


def scan_anthropic(text):
    return [(AF_NOANTHROPIC, name) for name, rx in _ANTHROPIC_PATTERNS if rx.search(text)]


def scan_client_names(text, names=None):
    names = names if names is not None else _client_names()
    hits = []
    low = text.lower()
    for i, n in enumerate(names, 1):
        if n and n.lower() in low:
            hits.append((AF_NAME, "client-name-token-#%d" % i))  # index only; NEVER the token
    return hits


def scan_text(text, names=None):
    return scan_secrets(text) + scan_pindata(text) + scan_anthropic(text) + scan_client_names(text, names)


def _scan_file(path, names):
    findings = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [(AF_SECRET, "unreadable:%s" % exc, 0)]
    for lineno, line in enumerate(lines, 1):
        for code, cls in scan_text(line, names):
            findings.append((code, cls, lineno))
    return findings


def _iter_files(target):
    p = Path(target)
    if p.is_file():
        yield p
        return
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            fp = Path(root) / fn
            if fp.resolve() in _SKIP_FILES:
                continue  # never scan the detectors (they hold the patterns literally)
            if fp.suffix.lower() in _TEXT_EXT:
                yield fp


def scan_targets(targets, names=None):
    names = names if names is not None else _client_names()
    report = []
    for t in targets:
        if not Path(t).exists():
            report.append({"file": str(t), "code": AF_SECRET, "class": "missing-target", "line": 0})
            continue
        for fp in _iter_files(t):
            for code, cls, lineno in _scan_file(fp, names):
                report.append({"file": str(fp), "code": code, "class": cls, "line": lineno})
    return report


def _emit(report, as_json, name_list_len):
    if as_json:
        print(json.dumps({"gate": "social-media-scrub-gate", "pass": not report,
                          "client_name_list_size": name_list_len,
                          "findings": report}, indent=2))
        return
    print("== Social Media in a Box :: scrub gate ==")
    print("client-name list size: %d (env-supplied; never shipped)" % name_list_len)
    if not report:
        print("RESULT: PASS — no client-name / secret / pinData / Anthropic leak found.")
    else:
        print("RESULT: FAIL (fail-closed) — %d finding(s) [value never printed]:" % len(report))
        for r in report:
            print("  [%s] %s:%d — %s" % (r["code"], r["file"], r["line"], r["class"]))


def run(targets, as_json=False, require_names=False, names=None):
    names = names if names is not None else _client_names()
    report = []
    # SK2-13: fail-CLOSED when the client-name list is unconfigured while a client-
    # content scan is required. At BUILD time (scanning shipped skill files) an empty
    # list is correct — client names are NEVER shipped. But at RUNTIME over generated
    # client content, an empty list means the client-name leak screen never actually
    # ran; silently passing would let a client name leak into published content. The
    # runtime caller passes --require-names (or sets SMIB_SCRUB_REQUIRE_NAMES=1).
    if require_names and not names:
        report.append({"file": "SMIB_SCRUB_NAMES(_FILE)", "code": AF_NAME,
                       "class": "name-list-unconfigured-fail-closed", "line": 0})
    report += scan_targets(targets, names)
    _emit(report, as_json, len(names))
    return EXIT_PASS if not report else EXIT_AUTOFAIL


# =============================================================================
# SELF-TEST — in-memory fixtures (fake secret SHAPES; no real secrets).
# =============================================================================
def self_test():
    ok = True

    def cp(name, text, names=None):
        nonlocal ok
        hits = scan_text(text, names or [])
        good = not hits
        ok = ok and good
        print("  [%s] CLEAN %-26s -> %d hit(s) %s" % ("PASS" if good else "MISS", name, len(hits),
              "" if good else hits))

    def cf(name, text, expect, names=None):
        nonlocal ok
        hits = scan_text(text, names or [])
        codes = [c for c, _ in hits]
        good = expect in codes
        ok = ok and good
        print("  [%s] LEAK  %-26s -> has %s %s" % ("PASS" if good else "MISS", name, expect,
              "" if good else codes))

    print("== self-test: CLEAN fixtures (must find NOTHING) ==")
    cp("plain-doc", "This skill NEVER uses Anthropic; client providers only. pit- prefix, claude-* rule.")
    cp("openrouter-model", "openrouterModel: google/gemini-2.0-flash-001")
    cp("schema-pit-anchor", '"pattern": "^pit-"')
    cp("no-names-configured", "Brand A ships weekly content", [])

    print("== self-test: LEAK fixtures (must be caught) ==")
    cf("openrouter-key", "key = sk-or-v1-" + "a" * 40, AF_SECRET)
    cf("ghl-pit", "token: pit-" + "b" * 30, AF_SECRET)
    cf("jwt", "auth eyJabc12345.eyJdef67890.sig12345", AF_SECRET)
    cf("access-token", 'body {"accessToken": "' + "c" * 30 + '"}', AF_SECRET)
    cf("pindata", '{"pinData": {"Webhook": []}}', AF_PINDATA)
    cf("claude-id", "model: claude-opus-4-8", AF_NOANTHROPIC)
    cf("anthropic-slash", "route to anthropic/claude-3.5-sonnet", AF_NOANTHROPIC)
    cf("sk-ant", "ANTHROPIC key sk-ant-" + "d" * 30, AF_SECRET)
    cf("anthropic-env", "export ANTHROPIC_API_KEY=x", AF_NOANTHROPIC)
    cf("client-name", "The ACME Parenting Co brand", AF_NAME, ["Acme Parenting Co"])

    print("== self-test: require-names fail-closed (SK2-13) ==")
    import contextlib
    import io
    import tempfile

    def _run_quiet(targets, require_names, names):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return run(targets, as_json=True, require_names=require_names, names=names)

    def chk(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    with tempfile.TemporaryDirectory() as td:
        clean = Path(td) / "clean.md"
        clean.write_text("Brand ships weekly content. No secrets here.\n", encoding="utf-8")
        chk("require-names + UNCONFIGURED list -> AUTOFAIL (fail-closed)",
            _run_quiet([str(clean)], require_names=True, names=[]) == EXIT_AUTOFAIL)
        chk("require-names + configured list, no leak -> PASS",
            _run_quiet([str(clean)], require_names=True, names=["Acme Parenting Co"]) == EXIT_PASS)
        chk("build scan (no require-names) + empty list -> PASS (names never shipped)",
            _run_quiet([str(clean)], require_names=False, names=[]) == EXIT_PASS)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed scrub gate for Social Media in a Box (Skill 57).")
    ap.add_argument("targets", nargs="*", help="files or directories to screen")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-names", dest="require_names", action="store_true",
                    help="fail-closed if the client-name list (SMIB_SCRUB_NAMES[_FILE]) is "
                         "unset — pass this when scanning generated CLIENT content")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.targets:
        ap.error("at least one file/dir target is required (or use --self-test)")
    require_names = args.require_names or \
        os.environ.get("SMIB_SCRUB_REQUIRE_NAMES", "").strip().lower() in ("1", "true", "yes", "on")
    return run(args.targets, as_json=args.json, require_names=require_names)


if __name__ == "__main__":
    sys.exit(main())
