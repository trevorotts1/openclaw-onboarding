#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: ANONYMIZATION LINT (fail-closed)
# -----------------------------------------------------------------------------
# Fleet-wide repo law: NO client-name token in shipped skill files or deliverable
# metadata. This lint fails on any CONFIGURED client-name token (word-boundary,
# case-insensitive). The token list is a DENYLIST supplied at CI/delivery time
# (--tokens / --tokens-file); it is never checked into the fleet repo, so no client
# name lives here. Fixtures use fictional names only; the only permitted real name
# is the owner "Trevor Otts".
#
#   AF-BK-ANON — a configured client-name token appears in a scanned file.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_anon.py --dir DIR --tokens "Acme,Jane Client" [--json]
#        prove_bw_anon.py --dir DIR --tokens-file tokens.txt [--json] | --self-test
# =============================================================================
"""Fail-closed anonymization lint (Skill 53)."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_ANON = "AF-BK-ANON"
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".html", ".py", ".sh"}


def evaluate(named_texts: dict, tokens) -> c.Result:
    r = c.Result("prove_bw_anon")
    tokens = [t.strip() for t in tokens if t and t.strip()]
    if not tokens:
        r.note("no client-name tokens configured — nothing to lint (supply --tokens at CI/delivery)")
        return r
    patterns = [(t, re.compile(r"\b%s\b" % re.escape(t), re.IGNORECASE)) for t in tokens]
    for label, text in named_texts.items():
        for tok, pat in patterns:
            if pat.search(text):
                r.fail(AF_ANON, "configured client-name token %r found in %s" % (tok, label))
    if r.passed:
        r.note("no configured client-name token across %d file(s)" % len(named_texts))
    return r


def _collect_dir(dir_path: str) -> dict:
    out = {}
    root = Path(dir_path)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES and "__pycache__" not in p.parts:
            try:
                out[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return out


def prove_dir(dir_path, tokens, as_json=False) -> int:
    return evaluate(_collect_dir(dir_path), tokens).emit(as_json)


def self_test() -> int:
    files = {"chapter.md": "Marcus Halloway leads his team with quiet authority.\n"}
    checks = []
    checks.append(("no configured tokens -> PASS", evaluate(files, []).passed))
    checks.append(("fictional author present but NOT in denylist -> PASS",
                   evaluate(files, ["Acme Corp", "Jane RealClient"]).passed))
    leak = {"meta.json": '{"client": "Jane RealClient"}'}
    checks.append(("configured token present AUTOFAILs AF-BK-ANON",
                   any(cd == AF_ANON for cd, _ in evaluate(leak, ["Jane RealClient"]).violations)))
    checks.append(("case-insensitive token match AUTOFAILs AF-BK-ANON",
                   any(cd == AF_ANON for cd, _ in
                       evaluate({"x.md": "written for acme corp"}, ["Acme Corp"]).violations)))
    return c.selftest_report("prove_bw_anon", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer anonymization lint (Skill 53).")
    ap.add_argument("--dir", help="directory to scan recursively")
    ap.add_argument("--tokens", help="comma-separated client-name denylist tokens")
    ap.add_argument("--tokens-file", help="file of newline-separated denylist tokens")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.dir:
        ap.error("--dir is required (or use --self-test)")
    tokens = []
    if args.tokens:
        tokens += args.tokens.split(",")
    if args.tokens_file:
        tokens += c.read_text(args.tokens_file).splitlines()
    return prove_dir(args.dir, tokens, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
