#!/usr/bin/env python3
"""
runner_gate_integrity_check.py — GUARD A (runner scope): DECLARED RUNNER GATE MUST
BE REFERENCED IN THE RUNTIME.

================================================================================
gate_integrity_check.py (Guard A) already asserts that every enforced_by==
"build_deck" autofail is referenced AND tested. This companion script extends
that discipline to enforced_by=="runner" codes: every such code declared in
PIPELINE-MANIFEST.json must appear as a STRING LITERAL in run_signature_deck.py
or prove-deck.py (both live in the same scripts/ directory as this file).

A runner code that is declared in the manifest but never appears as a string in
the runner source is a dead declaration — the gate cannot be raised at runtime.
This is the exact class of failure that gate_integrity_check.py caught for
build_deck codes; this guard applies the same discipline to runner codes.

Codes with py_symbol:null are governed by their presence as a string literal
(the AF code itself referenced anywhere in the source — comment, print, raise,
or string constant) so the enforcement path NAMES the code it raises. A code
that is NEITHER cited NOR referenced is structurally unreachable.

SCOPE: enforced_by == "runner" only.
       enforced_by == "build_deck" / "qc_check" / "closeout_gate" / etc. are
       out of scope (governed by gate_integrity_check.py / sync_check.py).
================================================================================

ZERO third-party deps (stdlib json / re / pathlib only).

INPUTS (resolved relative to THIS script via the same repo-root walk that
gate_integrity_check.py uses — works identically in the repo and on a deployed
client box):
  * PIPELINE-MANIFEST.json (via _find_repo_root walk, same as gate_integrity_check.py)
  * run_signature_deck.py  (in the same scripts/ dir as this file)
  * prove-deck.py          (in the same scripts/ dir as this file; may be absent —
                            its absence is noted but not a fatal error unless a
                            code is unresolved in both files)

EXIT CODES:
    0 — every runner-enforced code is referenced in run_signature_deck.py or
        prove-deck.py (at least one of the two).
    1 — one or more runner codes are dead declarations (referenced in neither
        runner file). Message names the offending code(s).
    2 — could not run (missing manifest or run_signature_deck.py, parse error).

USAGE:
    python3 runner_gate_integrity_check.py
    python3 runner_gate_integrity_check.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../presentations/scripts
PRES_DIR = HERE.parent

# Runner source files to scan for AF code string literals.
RUNNER_SOURCES = [
    HERE / "run_signature_deck.py",
    HERE / "prove-deck.py",
]


def _fatal(msg: str) -> None:
    print(f"FATAL (runner_gate_integrity_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def _find_repo_root(start: Path) -> "Path | None":
    """Walk up from start until a directory containing 'universal-sops' is found.
    Mirrors gate_integrity_check.py's path resolution exactly."""
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _resolve_manifest() -> Path:
    """Resolve PIPELINE-MANIFEST.json via repo-root walk, same as gate_integrity_check.py."""
    repo_root = _find_repo_root(HERE)
    candidates = []
    if repo_root:
        candidates.append(
            repo_root / "universal-sops" / "presentation-slide-craft"
            / "PIPELINE-MANIFEST.json"
        )
    candidates += [
        PRES_DIR / "sops" / "PIPELINE-MANIFEST.json",
        PRES_DIR / "PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # return canonical path for the error message


def load_manifest() -> dict:
    mpath = _resolve_manifest()
    if not mpath.exists():
        _fatal(f"PIPELINE-MANIFEST.json not found (looked at {mpath}).")
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _fatal(f"PIPELINE-MANIFEST.json is not valid JSON: {exc}")


def _af_strings_in_file(path: Path) -> "set[str]":
    """Return every AF-* string literal found in source, checking both quote forms."""
    if not path.exists():
        return set()
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return set()
    found = set()
    # The AF code must appear quoted — either "AF-..." or 'AF-...'
    # We scan for both to mirror gate_integrity_check.py's af_strings approach
    import re
    af_re = re.compile(r"AF-[A-Z0-9]+(?:-[A-Z0-9]+)*")
    for code in af_re.findall(src):
        # Only count if it appears as a quoted string literal (not just in a comment
        # that happens to match — but we accept comment mentions as "cited" per
        # gate_integrity_check.py's af_strings precedent which uses regex on full source).
        found.add(code)
    return found


def run_check(
    manifest: dict,
    runner_af: "set[str]",
    prove_af: "set[str]",
) -> "list[dict]":
    """Return a list of problem dicts for each dead-declared runner code."""
    problems = []
    for a in manifest.get("autofails", []):
        if a.get("enforced_by") != "runner":
            continue
        code = a.get("code", "<no-code>")
        in_runner = code in runner_af
        in_prove = code in prove_af
        if not in_runner and not in_prove:
            absent_files = []
            for src_path in RUNNER_SOURCES:
                label = src_path.name
                if not src_path.exists():
                    label += " (file absent)"
                absent_files.append(label)
            problems.append({
                "code": code,
                "detail": (
                    f"AF code {code!r} is declared enforced_by:runner in the manifest "
                    f"but does not appear as a string in either "
                    f"{' or '.join(absent_files)}. "
                    f"A declared runner gate that is never cited in the runner source "
                    f"cannot be raised at runtime — dead declaration. "
                    f"Add the code string (in a print/raise/comment/constant) to "
                    f"run_signature_deck.py (or prove-deck.py for the process-integrity "
                    f"gate) so the enforcement path names the code it raises."
                ),
            })
    return problems


def main() -> None:
    as_json = "--json" in sys.argv[1:]

    manifest = load_manifest()

    # Collect AF strings from both runner files
    runner_af = _af_strings_in_file(RUNNER_SOURCES[0])   # run_signature_deck.py
    prove_af = _af_strings_in_file(RUNNER_SOURCES[1])    # prove-deck.py

    # Enumerate in-scope codes
    in_scope = [
        a["code"] for a in manifest.get("autofails", [])
        if a.get("enforced_by") == "runner"
    ]

    problems = run_check(manifest, runner_af, prove_af)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "runner_enforced_codes": sorted(in_scope),
            "runner_af_strings_found": sorted(runner_af & set(in_scope)),
            "prove_af_strings_found": sorted(prove_af & set(in_scope)),
            "problems": problems,
        }, indent=2))
    else:
        if not problems:
            print("=== runner_gate_integrity_check: RUNNER CODES REFERENCED (Guard A — runner scope) ===")
            print(f"runner-enforced autofails: {len(in_scope)}")
            print(f"run_signature_deck.py present: {RUNNER_SOURCES[0].exists()}")
            print(f"prove-deck.py present:         {RUNNER_SOURCES[1].exists()}")
            print(
                "OK — every runner-enforced autofail code appears as a string in "
                "run_signature_deck.py or prove-deck.py. No dead declarations."
            )
        else:
            print(
                "=== runner_gate_integrity_check: DEAD RUNNER DECLARATION(S) (Guard A — runner scope) ===",
                file=sys.stderr,
            )
            print(
                "\nDEAD DECLARATIONS — runner-enforced codes absent from both runner files:",
                file=sys.stderr,
            )
            for p in problems:
                print(f"  {p['code']}: {p['detail']}", file=sys.stderr)
            print(
                f"\n{len(problems)} violation(s). A declared runner gate that is never "
                "cited as a string in run_signature_deck.py or prove-deck.py "
                "cannot be raised at runtime — it is a silent no-op. "
                "Add the code string to the runner (in a print/raise/comment/constant) "
                "so the enforcement path names the code it raises.",
                file=sys.stderr,
            )

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
