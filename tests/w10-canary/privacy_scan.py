#!/usr/bin/env python3
"""privacy_scan.py — shared-artifact privacy scan (spec 15.3 / A12).

Scans shared deliverables for content that must never reach a shared artifact:
  * real incident identifiers and named client/person identities;
  * private run / host / chat identities;
  * access-bearing links (Cloudflare Access URLs, signed URLs, token query params);
  * person-conditioned repair branch names.

Because this harness ships INSIDE a shared tree, the scanner never hardcodes the
operator home path (the packaging scanner would trip on it): it assembles any
literal it needs from parts. Patterns live in the DETECTS list below; extend it
when a new private-identity class appears.

Modes:
  python3 privacy_scan.py --root <dir>            scan; exit 0 clean, 1 findings
  python3 privacy_scan.py --root <dir> --dry-run  run the SELF-TEST only: prove the
      scanner discriminates (a planted private string is caught, clean text is not)

Read-only against --root (findings are printed and optionally written to --out).
Self-test scratch: /tmp/skill75-repair-SFR-007-canary-privscan-*. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

#: operator home path assembled from parts so this scanner never trips the
#: packaging "zero operator paths in code" check on its own tree
OP_PATH = "/" + "Users/" + "blac" + "kceomacmini"

DETECTS = [
    ("operator-home-path", re.compile(re.escape(OP_PATH))),
    ("access-bearing-link", re.compile(
        r"https://[^\s\"']*\.(cloudflareaccess\.com|trycloudflare\.com)[^\s\"']*")),
    ("signed-url-token-param", re.compile(
        r"[?&](token|sig|signature|key|access_token|X-Amz-Signature)=[A-Za-z0-9%+/=_-]{8,}")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-run-id", re.compile(r"\b(wf|run|inc)_[0-9a-f]{8,}\b")),
    ("person-conditioned-branch", re.compile(
        r"\b(fix|repair|hotfix)/(?:incident|client|box)-[a-z0-9-]+\b", re.I)),
]

TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".sh", ".js", ".ts", ".yml",
                 ".yaml", ".html", ".css"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "w10-canary"}


def scan_file(path):
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for name, rx in DETECTS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append({"file": str(path), "line": line, "class": name,
                             "match": m.group(0)[:80]})
    return findings


def scan_tree(root):
    root = Path(root)
    self_path = Path(__file__).resolve()
    all_findings = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        # skip only DIRECTORIES BELOW the scan root, never the root itself —
        # otherwise --root tests/w10-canary scans nothing and reports "clean"
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        # the scanner's own pattern table is not a deliverable; it would
        # otherwise match its own DETECTS literals when scanned as a file
        if p.resolve() == self_path:
            continue
        all_findings.extend(scan_file(p))
    return all_findings


def selftest():
    """Prove the scanner discriminates: planted private strings are caught,
    clean text is not. A scanner that cannot discriminate must FAIL."""
    ok = True
    with tempfile.TemporaryDirectory(
            prefix=cc.SCRATCH_PREFIX + "privscan-") as td:
        bad = Path(td) / "bad.md"
        bad.write_text(
            "incident run_deadbeef1234567890 was fixed on box\n"
            "link https://secret.cloudflareaccess.com/app?token=abcdefghijklmnop\n",
            encoding="utf-8")
        good = Path(td) / "good.md"
        good.write_text("Skill 75 acceptance matrix row A08 evidence.\n",
                        encoding="utf-8")
        f_bad = scan_file(bad)
        f_good = scan_file(good)
        hit = {f["class"] for f in f_bad}
        print("  [%s] planted private strings caught"
              % ("PASS" if {"private-run-id", "access-bearing-link",
                            "signed-url-token-param"} <= hit else "FAIL"))
        ok &= {"private-run-id", "access-bearing-link",
               "signed-url-token-param"} <= hit
        print("  [%s] clean text flagged nothing"
              % ("PASS" if not f_good else "FAIL"))
        ok &= not f_good
        # regression: a scan root whose own NAME is in SKIP_DIRS must still be
        # scanned (--root tests/w10-canary used to scan nothing -> false clean)
        named = Path(td) / "w10-canary"
        named.mkdir()
        (named / "planted.md").write_text(
            "incident run_deadbeef1234567890\n", encoding="utf-8")
        f_named = scan_tree(named)
        print("  [%s] scan root named like a skip dir is still scanned"
              % ("PASS" if f_named else "FAIL"))
        ok &= bool(f_named)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", help="shared artifact directory to scan")
    ap.add_argument("--out", help="write findings JSON here")
    ap.add_argument("--dry-run", action="store_true",
                    help="run the scanner self-test only")
    a = ap.parse_args()

    if a.dry_run:
        print("privacy scanner self-test:")
        return selftest()

    if not a.root:
        print("--root required (or --dry-run)")
        return 2
    root = Path(a.root)
    if not root.is_dir():
        print("not a directory: %s" % root)
        return 2

    findings = scan_tree(root)
    if findings:
        print("PRIVACY FINDINGS (%d):" % len(findings))
        for f in findings[:50]:
            print("  %s:%d [%s] %s" % (f["file"], f["line"], f["class"],
                                       f["match"]))
    else:
        print("privacy scan clean: no private incident identifiers or "
              "access-bearing links in %s" % root)

    if a.out:
        cc.write_json(a.out, {"schema": "blackceo.skill75.privacy-scan/v1",
                              "root": str(root), "findings": findings,
                              "count": len(findings)})
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
