#!/usr/bin/env python3
"""Validate compact bootstrap budgets, stable markers, and literal reference targets.

Ported into the repo from the operator box so every box on the fleet gets the
same check instead of one box having a private copy.

WHAT IT CHECKS, per bootstrap file (AGENTS.md, MEMORY.md, TOOLS.md, USER.md,
SOUL.md, IDENTITY.md):

  1. SIZE against a per-file budget. These files are re-billed to the model on
     EVERY turn, so a budget is the only thing that keeps a fleet roll from
     quietly making every turn more expensive forever.
  2. The compact-policy marker is present, so a file that was pointerized does
     not silently drift back to carrying full text.
  3. BEGIN/END markers balance. An orphan marker breaks every idempotency guard
     that keys on the pair, and the repo's dedup pass deliberately refuses to
     touch a box whose wiring is already broken — so one orphan freezes the box.
  4. Code fences balance.
  5. Every literal absolute path quoted in backticks EXISTS. This is the check
     that makes pointer stamping safe: a pointer to a file that is not there is
     worse than the bloat it replaced.

BUDGETS ARE OVERRIDABLE (the operator tunes these per box, and a VPS box does
not have the same shape as a Mac):
    --budget AGENTS.md=80000 --budget MEMORY.md=40000     (repeatable)
    --budget-file <json>                                  ({"AGENTS.md": 80000})
    OPENCLAW_BOOTSTRAP_BUDGETS='{"AGENTS.md": 80000}'     (env)
    --from-config <openclaw.json>   reads agents.defaults.bootstrapMaxChars and
                                    applies it to every file as the per-file cap
Later sources win in that order. The defaults below are the LEAN targets, which
are deliberately far below the 200k/400k hard limits a box enforces.

Exit: 0 when every file passes, 1 otherwise. Output is JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Lean targets. Not the box's hard limit — the point is to stay far under it.
DEFAULT_BUDGET = {
    "AGENTS.md": 60000,
    "MEMORY.md": 32000,
    "TOOLS.md": 60000,
    "USER.md": 32000,
    "SOUL.md": 32000,
    "IDENTITY.md": 32000,
}

POLICY_MARKER = "<!-- CORE_REFERENCE_POLICY_V1 -->"

# A backticked absolute path on any platform this fleet runs on: macOS boxes
# live under /Users, VPS boxes under /data (and /root for a container home).
_ABS_PATH_RE = re.compile(r"`((?:/Users/|/data/|/root/|/opt/|/home/)[^`]+)`")

# A POINTER stamped by bootstrap-pointerize.py. This is the check that makes
# pointer stamping safe to ship: the whole design trades inline text for a path,
# so a path that does not resolve turns a rule the agent used to be able to read
# into one it cannot. Pointers are NOT backticked, so _ABS_PATH_RE never sees
# them — they need their own pattern or they go unchecked.
# No prefix allowlist here, unlike the backticked-path pattern above: the
# stamper REFUSES to write a relative pointer, so every pointer is absolute by
# construction, and a prefix list would only create silent blind spots on any
# box whose master-files root sits somewhere the list did not anticipate.
_POINTER_RE = re.compile(r"\*\*Full text:\*\*\s+(/\S+)")
_MARKER_RE = re.compile(r"<!--\s*(?:(BEGIN|END)\s+)?([A-Za-z][A-Za-z0-9_:\-. ]*?)\s*-->")

# A path that is a TEMPLATE or a prose example, not a literal target to check.
_PLACEHOLDER_TOKENS = ("<", ">", "YYYY-MM-DD", "*", "…", "...", "$", "{", "}")
_CHECKABLE_SUFFIXES = (".md", ".json", ".py", ".sh", ".txt", ".yaml", ".yml")


def _load_budgets(args) -> dict[str, int]:
    budget = dict(DEFAULT_BUDGET)

    env = os.environ.get("OPENCLAW_BOOTSTRAP_BUDGETS", "").strip()
    if env:
        try:
            budget.update({k: int(v) for k, v in json.loads(env).items()})
        except (ValueError, AttributeError, TypeError) as exc:
            print(f"warning: OPENCLAW_BOOTSTRAP_BUDGETS ignored ({exc})", file=sys.stderr)

    if args.from_config:
        try:
            cfg = json.load(open(args.from_config, encoding="utf-8"))
            cap = cfg.get("agents", {}).get("defaults", {}).get("bootstrapMaxChars")
            if isinstance(cap, int) and cap > 0:
                budget = {k: cap for k in budget}
        except (OSError, ValueError) as exc:
            print(f"warning: --from-config ignored ({exc})", file=sys.stderr)

    if args.budget_file:
        try:
            budget.update({k: int(v) for k, v in
                           json.load(open(args.budget_file, encoding="utf-8")).items()})
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            print(f"warning: --budget-file ignored ({exc})", file=sys.stderr)

    for item in args.budget or []:
        if "=" not in item:
            print(f"warning: --budget {item!r} ignored (expected NAME=CHARS)", file=sys.stderr)
            continue
        name, _, raw = item.partition("=")
        try:
            budget[name.strip()] = int(raw)
        except ValueError:
            print(f"warning: --budget {item!r} ignored (not a number)", file=sys.stderr)

    return budget


def _check_markers(name: str, text: str, errors: list[str]) -> None:
    pairs = _MARKER_RE.findall(text)
    ends = {label for kind, label in pairs if kind == "END"}
    stack: list[str] = []
    for kind, label in pairs:
        # A bare `<!-- NAME -->` sentinel with no END anywhere is a legitimate
        # single-line marker (apply-fleet-standards.sh uses that shape), not an
        # unbalanced pair. Only treat a bare marker as an opener when an END for
        # it genuinely exists somewhere in the file.
        if not kind and label not in ends:
            continue
        if kind != "END":
            stack.append(label)
        elif not stack or stack.pop() != label:
            errors.append(f"{name}: unbalanced marker {label}")
    if stack:
        errors.append(f"{name}: unclosed markers: {', '.join(stack)}")


def validate(workspace: Path, budget: dict[str, int], require_policy: bool) -> dict:
    errors: list[str] = []
    counts: dict[str, int] = {}
    checked: set[str] = set()
    missing_refs: list[str] = []

    for name, limit in budget.items():
        path = workspace / name
        if not path.is_file():
            errors.append(f"{name}: missing")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{name}: unreadable ({exc.__class__.__name__})")
            continue

        counts[name] = len(text)
        if len(text) > limit:
            errors.append(f"{name}: {len(text)} characters exceeds budget {limit}")
        if not text.strip():
            continue
        if require_policy and POLICY_MARKER not in text:
            errors.append(f"{name}: missing compact policy marker {POLICY_MARKER}")

        _check_markers(name, text, errors)

        if sum(line.lstrip().startswith("```") for line in text.splitlines()) % 2:
            errors.append(f"{name}: unbalanced code fence")

        for raw in _ABS_PATH_RE.findall(text):
            # Drop an anchor fragment: `/path/to/file.md#section` names a section
            # INSIDE the file, so the file is what has to exist.
            raw = raw.split("#", 1)[0]
            if any(tok in raw for tok in _PLACEHOLDER_TOKENS):
                continue
            if "\n" in raw or " --" in raw or " " in raw.strip():
                continue
            ref = Path(raw.rstrip("/"))
            if ref.suffix in _CHECKABLE_SUFFIXES or raw.endswith("/"):
                checked.add(str(ref))
                if not ref.exists():
                    errors.append(f"{name}: missing reference {ref}")
                    missing_refs.append(str(ref))

        # Every pointer must resolve, with no suffix filter and no placeholder
        # escape hatch: a pointer is a literal promise that this exact file is
        # readable right now.
        for raw in _POINTER_RE.findall(text):
            ref = Path(raw.split("#", 1)[0].rstrip("/"))
            checked.add(str(ref))
            if not ref.exists():
                errors.append(f"{name}: DANGLING POINTER — full text not at {ref}")
                missing_refs.append(str(ref))

    return {
        "ok": not errors,
        "workspace": str(workspace),
        "characters": counts,
        "total_characters": sum(counts.values()),
        "budgets": budget,
        "checked_references": len(checked),
        "missing_references": missing_refs,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--workspace", type=Path, default=Path.home() / "clawd",
                   help="workspace holding the bootstrap files (default ~/clawd)")
    p.add_argument("--budget", action="append",
                   help="override one budget: NAME=CHARS (repeatable)")
    p.add_argument("--budget-file", type=Path, help="JSON file of {NAME: CHARS}")
    p.add_argument("--from-config", type=Path,
                   help="openclaw.json to read agents.defaults.bootstrapMaxChars from")
    p.add_argument("--no-require-policy", action="store_true",
                   help="do not require the compact-policy marker")
    a = p.parse_args(argv)

    result = validate(a.workspace, _load_budgets(a), not a.no_require_policy)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
