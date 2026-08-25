#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: PLACEHOLDER-LEAK GATE (fail-closed)
# -----------------------------------------------------------------------------
# The user.md prompts are rebuilt from n8n with {{intake.<key>}} / {{artifact.<id>}}
# substitutions. This gate guarantees NO unresolved template token ever reaches a
# model or a deliverable: any {{...}} or $('...') / $("...") in an artifact fails.
#
#   AF-BK-PLACEHOLDER — an unresolved {{...}} / $('...') token remains.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_placeholder.py <file> [<file> ...] [--json]
#        prove_bw_placeholder.py --dir DIR [--json] | --self-test
# =============================================================================
"""Fail-closed unresolved-placeholder gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_PLACEHOLDER = "AF-BK-PLACEHOLDER"
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".html"}


def evaluate(named_texts: dict) -> c.Result:
    """named_texts: {label: text}."""
    r = c.Result("prove_bw_placeholder")
    for label, text in named_texts.items():
        hits = c.find_placeholders(text)
        for h in hits:
            r.fail(AF_PLACEHOLDER, "unresolved token %r in %s" % (h, label))
    if r.passed:
        r.note("no unresolved {{..}}/$('..') tokens across %d file(s)" % len(named_texts))
    return r


def _collect_dir(dir_path: str) -> dict:
    out = {}
    root = Path(dir_path)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES:
            try:
                out[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return out


def prove_files(paths, as_json=False) -> int:
    return evaluate({p: c.read_text(p) for p in paths}).emit(as_json)


def prove_dir(dir_path, as_json=False) -> int:
    return evaluate(_collect_dir(dir_path)).emit(as_json)


def self_test() -> int:
    checks = []
    clean = {"a.md": "# Chapter 1\nAll tokens resolved. Marcus leads his team.\n"}
    checks.append(("clean artifact PASSES", evaluate(clean).passed))
    checks.append(("{{intake.first_name}} leak AUTOFAILs",
                   any(cd == AF_PLACEHOLDER for cd, _ in
                       evaluate({"b.md": "Hello {{intake.first_name}}"}).violations)))
    checks.append(("$('Webhook') leak AUTOFAILs",
                   any(cd == AF_PLACEHOLDER for cd, _ in
                       evaluate({"c.md": "value $('Webhook2').item.json"}).violations)))
    checks.append(("$(\"Chain\") leak AUTOFAILs",
                   any(cd == AF_PLACEHOLDER for cd, _ in
                       evaluate({"d.md": 'x $("Create Outline").item'}).violations)))
    return c.selftest_report("prove_bw_placeholder", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer placeholder-leak gate (Skill 53).")
    ap.add_argument("files", nargs="*", help="files to scan")
    ap.add_argument("--dir", help="scan every text file under DIR recursively")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.dir:
        return prove_dir(args.dir, as_json=args.json)
    if args.files:
        return prove_files(args.files, as_json=args.json)
    ap.error("file(s) or --dir required (or use --self-test)")


if __name__ == "__main__":
    sys.exit(main())
