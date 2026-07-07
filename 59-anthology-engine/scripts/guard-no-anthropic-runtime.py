#!/usr/bin/env python3
"""guard-no-anthropic-runtime.py -- static Anthropic-identifier gate over the shipped engine.

Unit W2.2. SPEC 3.4 row 23 / SPEC 8.2 / autofail AF-AE-ANTHROPIC. Mirrors Skill 54's
AF-AW-ANTHROPIC ledger gate and model_router.py's call-time deny patterns, but STATIC:
it proves that ZERO Anthropic-family model-id / SDK / endpoint VALUES ship in any engine
runtime file, and it is built to fold every Command Center edit (department config,
home-screen tiles, the participant token route) into a later full pass via extra path
arguments (positional paths / --include; the W3 train runs it over its own repo too).

WHAT IS A VIOLATION (an actual Anthropic identifier VALUE):
  - a `<C>-<version>` model id             (the drafting-vendor id shape)
  - an `<A>/<model>` vendor-prefixed id     (OpenRouter-style routing)
  - a `us.<A>.<model>` id                   (Bedrock-style ARN)
  - the `@<A>-ai` package scope             (the SDK on npm)
  - `<A>.<C>` or `<A>.com`                  (Bedrock dotted modelId / the API host)
  - a quoted scalar whose ENTIRE value is exactly the bare vendor token
        ( a `"..."` equal to <A> or <C> -- e.g. a `"provider": "<A>"` config leak )
  where <A> and <C> are the two banned vendor tokens, assembled HERE from fragments so
  this shipped file itself carries no contiguous banned literal (the same convention
  model_router.py uses; the guard scans its own source clean, proved in the self-test).

WHAT IS NOT A VIOLATION (the enforcement mechanisms themselves -- ALLOWED):
  The whole point of the engine is to REFUSE Anthropic ids, so the deny machinery has to
  name the thing it bans. A value-shape hit is treated as an ALLOWED enforcement
  DEFINITION, never a violation, when the line is one of:
    - a REGEX definition (carries `(?i)`, a `[^...]` character class, or an
      `re.compile/search/match/fullmatch` call) -- e.g. anthology_state.py and
      caf_delivery.py define `_ANTHROPIC_DENY_RE` as a literal deny regex, and
      model_router.py assembles the identical law from fragments;
    - a deny / scrub / blocklist construct (the line, or a non-blank line just above it,
      names a deny-, scrub-, or block- symbol -- e.g. nudge_send.py's INTERNAL_DENY tuple);
    - a line carrying an explicit inline allow pragma.
  A bare mention of the vendor name in prose, a comment, a docstring, or an identifier
  (`is_<A>_shaped`, `AF-AE-ANTHROPIC`, this file's own name) is NEVER a value shape and is
  never flagged. The bare-token law lives at CALL time in model_router.py (which sees the
  RESOLVED id) and in preflight.sh over the resolved model-map; this static gate is
  deliberately narrower -- it flags the compound VALUE signatures that never occur in
  honest prose but always occur in a real leak.

DOCTRINE: prints the matched vendor-token span ONLY, never the whole source line by
default (an offending line could sit beside a secret-shaped value); --show-line is a
LOCAL-DEBUG escape hatch. Never prints a credential value. Move in silence.

Exit codes (SPEC 3.4 row 23; house convention for the edge cases):
  0  clean (no Anthropic identifier VALUE in any scanned file)
  4  violation (at least one Anthropic identifier VALUE found)
  2  bad invocation (a requested path is missing, or no paths to scan)
  1  unexpected error
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_BAD, EX_DEP, EX_VIOLATION = 0, 1, 2, 3, 4

# The two banned vendor tokens, assembled from fragments so this shipped file carries no
# contiguous banned literal (mirrors model_router.py; proved by the SELF self-test case).
_A = "anthro" + "pic"
_C = "clau" + "de"

# --- VALUE-shape detectors (a real Anthropic identifier value) -----------------------
# Each is a COMPOUND shape that does not occur in honest prose, comments, or identifiers.
# Matched CASE-SENSITIVELY against the lowercase canonical form: every functional
# Anthropic model-id / endpoint / SDK-scope / provider VALUE that could actually ship is
# lowercase, so this cleanly excludes the Capitalized proper-noun ("Anthropic", "Claude")
# that saturates the doctrine, comments, and operator prose. The any-casing bare-token
# law belongs at CALL time (model_router.py sees the RESOLVED id), not to this static gate.
_VALUE_PATTERNS = [
    ("model-id",     re.compile(_C + r"-[a-z0-9]")),                # <C>-<version>
    ("vendor-slash", re.compile(_A + r"/")),                        # <A>/<model>
    ("sdk-scope",    re.compile(r"@?" + _A + r"-ai\b")),            # @<A>-ai
    ("bedrock",      re.compile(r"us\." + _A + r"\.")),             # us.<A>.<model>
    ("dotted",       re.compile(_A + r"\.(?:" + _C + r"|com)")),    # <A>.<C> | <A>.com
]
# A quoted scalar whose ENTIRE value is exactly the bare (lowercase) vendor token, a
# config leak such as a `"provider": "<A>"`. Lowercase-only, so a Capitalized proper-noun
# in an English quotation (a `"Anthropic"` mention in operator prose) is NOT a value.
_SCALAR_PATTERN = ("bare-scalar",
                   re.compile(r"(['\"])(?:" + _A + r"|" + _C + r")\1"))

# --- Enforcement-context discriminators (ALLOWED, never a violation) ------------------
# A value-shape hit on such a line is the deny machinery naming what it bans.
_REGEX_CONTEXT_RE = re.compile(r"\(\?i\)|\[\^|re\.(?:compile|search|match|fullmatch)")
_ENFORCEMENT_MARKER_RE = re.compile(
    r"(?i)(?:deny|blocklist|blocked|scrub|forbidden"
    r"|guard-no-" + _A + r"|is_" + _A + r"_shaped)")
_ALLOW_PRAGMA_RE = re.compile(
    r"(?i)guard-no-" + _A + r"\s*[:=]?\s*(?:allow|ok|ignore|expected)")

# Text file kinds that ship in the engine (and, in the W3 full pass, the Command Center).
# `.env` is deliberately absent: it holds real secrets and is never scanned by default.
DEFAULT_EXTS = {
    ".py", ".sh", ".json", ".md", ".txt", ".tsx", ".ts", ".js", ".jsx",
    ".html", ".css", ".yaml", ".yml", ".toml", ".cfg", ".ini",
}
DEFAULT_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".build-state",
                     ".venv", "venv", ".next", "dist", "build", ".mypy_cache"}


def _value_hit(line):
    """Return (kind, matched_text) for the first Anthropic VALUE shape on the line, else
    None. Checks the compound value shapes first, then the exact bare-scalar shape."""
    for kind, rx in _VALUE_PATTERNS:
        m = rx.search(line)
        if m:
            return kind, m.group(0)
    kind, rx = _SCALAR_PATTERN
    m = rx.search(line)
    if m:
        return kind, m.group(0)
    return None


def deny(text):
    """AF-AE-ANTHROPIC py_symbol. True iff `text` carries an Anthropic-family identifier
    VALUE shape (the static-scan law). Enforcement-context allowlisting is a per-LINE
    concern owned by the scanner; this bare predicate answers only 'is this string an
    Anthropic identifier value?'. Companion to model_router.is_anthropic_shaped, scoped to
    the compound VALUE signatures this static gate enforces."""
    return bool(text) and _value_hit(str(text)) is not None


def _is_enforcement_context(lines, idx, window=3):
    """Return an allow-reason string when the hit at lines[idx] is a deny / scrub / regex
    enforcement DEFINITION (ALLOWED), else None. Looks at the hit line plus up to `window`
    preceding NON-BLANK lines, so an assignment header one line above the literal (the
    `_ANTHROPIC_DENY_RE = re.compile(` or `INTERNAL_DENY = (` shape) still covers it."""
    line = lines[idx]
    if _ALLOW_PRAGMA_RE.search(line):
        return "allow-pragma"
    if _REGEX_CONTEXT_RE.search(line):
        return "regex-definition"
    if _ENFORCEMENT_MARKER_RE.search(line):
        return "deny-symbol"
    seen = 0
    j = idx - 1
    while j >= 0 and seen < window:
        prev = lines[j]
        if prev.strip():
            seen += 1
            if _ENFORCEMENT_MARKER_RE.search(prev):
                return "deny-symbol-header"
        j -= 1
    return None


def scan_file(path, window=3):
    """Scan one text file. Returns {file, scanned, violations:[{line, kind, match, _line}]}.
    Never raises on a read error -- an unreadable file is reported as scanned=False so the
    caller can surface it without turning a read glitch into a false CLEAN."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:
        return {"file": str(p), "scanned": False, "violations": [],
                "skipped_reason": "unreadable: %s" % exc}
    lines = text.splitlines()
    violations = []
    for i, line in enumerate(lines):
        hit = _value_hit(line)
        if not hit:
            continue
        if _is_enforcement_context(lines, i, window):
            continue
        kind, matched = hit
        violations.append({"line": i + 1, "kind": kind, "match": matched, "_line": line})
    return {"file": str(p), "scanned": True, "violations": violations}


def collect_files(roots, exts, skip_dirs):
    """Yield the text files under the given roots (each a file or directory) matching
    `exts`. A root named directly as a FILE is scanned regardless of extension (an explicit
    ask overrides the extension filter). Raises FileNotFoundError if a root is missing."""
    found = []
    for root in roots:
        rp = Path(root)
        if not rp.exists():
            raise FileNotFoundError(str(root))
        if rp.is_file():
            found.append(rp)
            continue
        for dirpath, dirnames, filenames in os.walk(rp):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if Path(fn).suffix.lower() in exts:
                    found.append(Path(dirpath) / fn)
    seen = set()
    uniq = []
    for f in sorted(found, key=str):
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def default_engine_root():
    """The skill root that ships this guard: the parent of the scripts/ directory."""
    return Path(__file__).resolve().parent.parent


def scan_paths(roots, exts=None, skip_dirs=None, window=3):
    """Scan every text file under `roots`; return an aggregate report dict."""
    exts = exts or DEFAULT_EXTS
    skip_dirs = skip_dirs or DEFAULT_SKIP_DIRS
    files = collect_files(roots, exts, skip_dirs)
    reports = [scan_file(f, window) for f in files]
    total = sum(len(r["violations"]) for r in reports)
    return {
        "roots": [str(r) for r in roots],
        "files_scanned": sum(1 for r in reports if r["scanned"]),
        "files_skipped": sum(1 for r in reports if not r["scanned"]),
        "violation_count": total,
        "violations": [r for r in reports if r["violations"]],
        "skipped": [r for r in reports if not r["scanned"]],
        "ok": total == 0,
    }


def evaluate(roots=None):
    """Importable harness API (matches the guard-font-floor `evaluate` convention): True
    iff every scanned file is clean of Anthropic identifier VALUES. Defaults to the engine
    root. Accepts a single path or an iterable of paths."""
    if roots is None:
        roots = [default_engine_root()]
    elif isinstance(roots, (str, Path)):
        roots = [roots]
    return scan_paths(list(roots))["ok"]


def self_test(window=3):
    """Force-observe every failure mode: a clean file passes, a planted leak is caught on
    every shape, a deny-DEFINITION is NOT flagged, and the guard's own source scans clean.
    All planted content is built from fragments so this .py file stays free of any
    contiguous banned literal; the temp files carry the literals and are then discarded."""
    import tempfile
    a, c = _A, _C
    print("[guard-no-anthropic] self-test: clean file, planted leak, deny-definition, self-scan")

    # Adversarial CLEAN content: honest non-Anthropic ids, an enforcement predicate name,
    # and the exact prose shapes that must NEVER flag -- a Capitalized proper-noun quoted
    # in operator prose ("Anthropic") and a Title-cased mention ("Claude-3"), neither of
    # which is a lowercase functional VALUE (this regression-guards the delivery_report FP).
    q = chr(34)  # a double-quote, kept out of any contiguous banned literal
    clean = "\n".join([
        "# Nothing " + a.capitalize() + " ships in any runtime file (doctrine, bare word).",
        'CHAIN = ["glm-5.2", "minimax-v3", "gemini-3.5-flash", "deepseek-v4"]',
        "def is_" + a + "_shaped(x): return bool(_DENY.search(x))  # named predicate only",
        "# the certificate legitimately names " + q + a.capitalize() + q + " in its prose",
        "# and mentions the " + q + c.capitalize() + "-3" + q + " family once; neither is a value",
    ])
    # One shape per line so each detector is isolated (a line carrying several shapes is
    # caught by whichever matches first, proved by the REALISTIC line at the end).
    leaks = "\n".join([
        'PRIMARY   = "' + c + '-opus-4-8"',                       # model-id  <C>-<ver>
        'ROUTED    = "' + a + '/opus-4-1"',                       # vendor-slash  <A>/<model>
        'BEDROCK   = "us.' + a + '.reasoning-v2:0"',              # bedrock  us.<A>.<model>
        'PKG       = "@' + a + '-ai/sdk"',                        # sdk-scope  @<A>-ai
        'HOST      = "api.' + a + '.com/v1/messages"',           # dotted  <A>.com
        'CONF      = {"provider": "' + a + '"}',                  # bare-scalar  exact "<A>"
        'REALISTIC = "' + a + "/" + c + '-3-5-sonnet-latest"',    # combined; still caught
    ])
    denydef = "\n".join([
        "_ANTHROPIC_DENY_RE = re.compile(",
        '    r"(?i)(^|[^a-z0-9])(' + c + "|" + a + ")([^a-z0-9]|$)|"
        + a + "/|" + c + "-|us." + a + '.",',
        ")",
        'INTERNAL_DENY = ("' + a + '", "' + c + '-", "openrouter")',
        'DOC = "' + c + '-opus-4-8"  # guard-no-' + a + ": allow (documented example only)",
    ])

    with tempfile.TemporaryDirectory() as td:
        pc = Path(td) / "clean.py"
        pl = Path(td) / "leak.py"
        pd = Path(td) / "denydef.py"
        pc.write_text(clean, encoding="utf-8")
        pl.write_text(leaks, encoding="utf-8")
        pd.write_text(denydef, encoding="utf-8")

        rc = scan_file(pc, window)
        assert rc["scanned"] and not rc["violations"], "CLEAN file wrongly flagged: %r" % rc
        print("[guard-no-anthropic] clean case: PASS (0 violations, %d lines)"
              % len(clean.splitlines()))

        rl = scan_file(pl, window)
        kinds = {v["kind"] for v in rl["violations"]}
        assert len(rl["violations"]) >= 7, "planted leak not fully caught: %r" % rl
        for expect in ("model-id", "vendor-slash", "bedrock", "sdk-scope", "dotted", "bare-scalar"):
            assert expect in kinds, "planted %s leak missed (got %s)" % (expect, sorted(kinds))
        print("[guard-no-anthropic] leak case: PASS (caught %d, shapes %s)"
              % (len(rl["violations"]), sorted(kinds)))

        rd = scan_file(pd, window)
        assert rd["scanned"] and not rd["violations"], \
            "deny-DEFINITION wrongly flagged (regex/scrub/pragma must be ALLOWED): %r" % rd
        print("[guard-no-anthropic] deny-definition case: PASS "
              "(regex + scrub-list + pragma all ALLOWED, 0 violations)")

    self_report = scan_file(Path(__file__).resolve(), window)
    assert self_report["scanned"] and not self_report["violations"], \
        "guard flagged its OWN source (a contiguous banned literal leaked in): %r" % self_report
    print("[guard-no-anthropic] self-scan case: PASS (own source carries no Anthropic value)")

    assert deny(c + "-3-5-sonnet") and deny(a + "/" + c) and deny("us." + a + ".x")
    assert deny("@" + a + "-ai/sdk") and deny(a + ".com")
    assert not deny("glm-5.2") and not deny("minimax-v3") and not deny("gemini-3.5-flash")
    assert not deny(a) and not deny(c), "a BARE vendor word is not a VALUE shape (call-time law owns it)"
    print("[guard-no-anthropic] predicate case: PASS (value shapes deny; real ids and bare words pass)")

    print("[guard-no-anthropic] self-test: PASS")
    return EX_OK


def _strip_line(v, show):
    v = dict(v)
    if not show:
        v.pop("_line", None)
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Static Anthropic-identifier gate over the shipped Anthology Engine "
                    "file set, extensible to the Command Center edits (Unit W2.2).")
    ap.add_argument("paths", nargs="*",
                    help="extra files or directories to include (e.g. the Command Center "
                         "repo for the W3 full pass); the engine root is scanned too unless "
                         "--no-default-root is given")
    ap.add_argument("--root", help="override the engine root (default: this skill's root)")
    ap.add_argument("--include", action="append", default=[], metavar="PATH",
                    help="an additional root to scan (repeatable; same effect as a positional path)")
    ap.add_argument("--no-default-root", action="store_true",
                    help="do NOT scan the engine root; scan only the given paths")
    ap.add_argument("--ext", action="append", default=[], metavar=".EXT",
                    help="an additional file extension to scan (repeatable)")
    ap.add_argument("--window", type=int, default=3,
                    help="preceding non-blank lines examined for deny-definition context (default 3)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report to stdout")
    ap.add_argument("--show-line", action="store_true",
                    help="print the full offending line (LOCAL DEBUG ONLY; a line may sit "
                         "beside a secret-shaped value)")
    ap.add_argument("--list-files", action="store_true",
                    help="list the files that would be scanned, then exit 0")
    ap.add_argument("--self-test", action="store_true", help="run the built-in self-test and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test(args.window)

        exts = set(DEFAULT_EXTS)
        for e in args.ext:
            exts.add(e if e.startswith(".") else "." + e)

        roots = []
        if not args.no_default_root:
            roots.append(Path(args.root) if args.root else default_engine_root())
        roots.extend(Path(p) for p in args.include)
        roots.extend(Path(p) for p in args.paths)
        if not roots:
            ap.error("no paths to scan (engine root suppressed and no paths given)")

        try:
            files = collect_files(roots, exts, DEFAULT_SKIP_DIRS)
        except FileNotFoundError as exc:
            sys.stderr.write("[guard-no-anthropic] bad invocation: no such path: %s\n" % exc)
            return EX_BAD

        if args.list_files:
            for f in files:
                print(str(f))
            return EX_OK

        reports = [scan_file(f, args.window) for f in files]
        file_reports = [r for r in reports if r["violations"]]
        skipped = [r for r in reports if not r["scanned"]]
        total = sum(len(r["violations"]) for r in reports)
        scanned = sum(1 for r in reports if r["scanned"])

        if args.json:
            print(json.dumps({
                "roots": [str(r) for r in roots],
                "files_scanned": scanned,
                "files_skipped": len(skipped),
                "violation_count": total,
                "ok": total == 0,
                "violations": [
                    {"file": r["file"],
                     "violations": [_strip_line(v, args.show_line) for v in r["violations"]]}
                    for r in file_reports],
            }, indent=2))
        elif total == 0:
            print("[guard-no-anthropic] CLEAN  %d file(s) scanned, 0 Anthropic identifier "
                  "value(s)  (roots: %s)" % (scanned, ", ".join(str(r) for r in roots)))
        else:
            for r in file_reports:
                for v in r["violations"]:
                    loc = "%s:%d" % (r["file"], v["line"])
                    if args.show_line:
                        print("[guard-no-anthropic] VIOLATION %s [%s]  %s"
                              % (loc, v["kind"], v.get("_line", "")))
                    else:
                        print("[guard-no-anthropic] VIOLATION %s [%s]  match=%r"
                              % (loc, v["kind"], v["match"]))
            print("[guard-no-anthropic] %d violation(s) in %d file(s)"
                  % (total, len(file_reports)))

        for r in skipped:
            sys.stderr.write("[guard-no-anthropic] skipped (unreadable): %s (%s)\n"
                             % (r["file"], r.get("skipped_reason", "")))

        return EX_VIOLATION if total else EX_OK

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[guard-no-anthropic] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
