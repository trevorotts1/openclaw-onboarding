#!/usr/bin/env python3
"""check-kie-image-defaults.py — the GPT Image 2.5 -> 2.6 migration, as a gate.

WHY THIS EXISTS
The KIE image default moved from the 2.5 Sunburst model to the 2.6
Sunburst model. Behaviour migrated (the selector resolves the latest family), but the
DOCUMENTATION and the model registry did not: on main 9094aa83's parent,
13 stale claims still asserted 2.5 as the default, spread across five files
(`66-kie-image/models.json` lines 9, 10, 52, 59, 92; `SKILL.md:160`;
`validate_payload.py:335`; `select_image_model.py:41,205`;
`normalize_alias.py:23,62`) plus two `status:"default"` registry rows for the
2-5 models. Counting edited FILES never surfaced any of them: they are 13
sites inside 5 files in a 14,598-file tree. That is why this gate counts
DEFECTS, not files, and why it is executable instead of prose.

THE SIX AXES (all must be zero)
  D_live        an assigned default identifier whose value's first model token
                is 2.5 (value side only, so a historical note cannot false-fire)
  D_prose       a `default` claim within 40 chars of a 2.5 token, nearest token
                wins, clause-scoped; negations ("not", "no longer") and history
                ("at that time", "as history") are not claims
  D_rows        a `66-kie-image/models.json` row whose status contradicts its
                version: 2-5 must be `legacy`, 2-6 must be `default`
  D_dispatch    the live selector must resolve a generic request to a 2.6 id
                (behavioural: this is the check a doc edit cannot satisfy)
  D_ratio       a row on the 2.6 default route whose `aspect_ratios` set is not
                exactly the vendor-served 2.6 set: a ratio it CLAIMS that 2.6
                does not serve (3:1, 1:3, 9:21 are legacy-only), or a ratio it
                fails to advertise that 2.6 does serve
  D_prose_bare  a `default` claim within 40 chars of a BARE version token in a
                GPT-Image context, with no model prefix on that token — the
                same class D_prose catches when the prefix is spelled out.
                Same clause scoping and negation/history exemptions; no
                GPT-Image context on the line, no defect, so unrelated version
                numbers (an interpreter release, a package version) cannot
                trip it

SCOPE
Every tracked text file, minus historical records — `CHANGELOG.md` and any
`archive/` path. History is not rewritten and must not be made to fail.

USAGE
  python3 scripts/check-kie-image-defaults.py [--root DIR] [--self-test]
Exit 0 = zero defects. Exit 1 = defects (each site is named). Exit 2 = the
gate itself could not run (missing selector, unparsable registry).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IDENTS = re.compile(
    r"IMAGE_MODEL_DEFAULT|DEFAULT_MODEL|DEFAULT_IMAGE_MODEL|"
    r"owner_preferred_default|default_model|KNOWN_DEFAULTS"
)
ANY_MODEL = re.compile(r"gpt[-_ ]?image[-_ ]?2[._-](5|6)", re.I)
# A bare version token with no model prefix: 2.5 or 2.6, optionally in
# parentheses. Deliberately narrower than ANY_MODEL so the bare axis only sees
# version claims, and it keeps the 2.6 neighbour so a sentence about 2.6 (the
# migration note in this file's own docstring, for one) is not read as a 2.5
# default claim.
BARE_MODEL = re.compile(r"(?<![\d.])2[._](5|6)\d*(?![\d])")
# "in a GPT-Image context": the line must name the image family, so a stray
# "2.5" in a Python or package-version sentence stays out of scope.
GPT_IMAGE_CTX = re.compile(r"gpt[-_ ]?image|sunburst", re.I)
# Aspect ratios the GPT Image 2.6 route actually serves. Quote provenance:
# docs.kie.ai market pages for gpt-image-2-6/sunburst, verified 2026-08-26 and
# mirrored by BOTH status:"default" rows in 66-kie-image/models.json. 3:1, 1:3
# and 9:21 are NOT served by 2.6 — they are the legacy gpt-image-2 carve-out.
VENDOR_26_RATIOS = frozenset({
    "auto", "1:1", "3:2", "2:3", "16:9", "9:16", "4:3", "3:4", "21:9",
    "27:16", "16:27", "9:8", "8:9",
})
EXCLUDED_BASENAME = "changelog.md"
TEXT_EXT = {
    "", ".md", ".json", ".py", ".sh", ".yaml", ".yml", ".js", ".mjs", ".ts",
    ".skill", ".txt", ".html", ".css",
}
PROXIMITY = 40


def tracked_files(root: Path):
    """Tracked text files, or every text file when the tree is not a git repo."""
    if (root / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z"],
                capture_output=True, text=True, timeout=300, check=True,
            ).stdout
            paths = [p for p in out.split("\0") if p]
        except (OSError, subprocess.SubprocessError):
            paths = []
        if paths:
            for rel in paths:
                if skipped(rel):
                    continue
                yield rel, root / rel
            return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in {".git"})
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            if skipped(rel):
                continue
            yield rel, p


def skipped(rel: str) -> bool:
    parts = rel.replace("\\", "/").lower().split("/")
    if parts[-1] == EXCLUDED_BASENAME:
        return True
    if "archive" in parts[:-1]:
        return True
    return os.path.splitext(rel)[1].lower() not in TEXT_EXT


def read_text(path: Path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="ignore")


def first_model_token(text: str):
    m = ANY_MODEL.search(text)
    return m.group(1) if m else None


def nearest_token(line: str, pos: int):
    best = None
    for m in ANY_MODEL.finditer(line):
        d = 0 if m.start() < pos < m.end() else min(abs(pos - m.start()), abs(pos - m.end()))
        if best is None or d < best[0]:
            best = (d, m.group(1))
    return best


def clause_bounds(line: str, pos: int):
    starts = [line.rfind(ch, 0, pos) for ch in ";.|"]
    end_candidates = [line.find(ch, pos) for ch in ";|"]
    start = max(starts) + 1
    ends = [e for e in end_candidates if e != -1]
    return start, (min(ends) if ends else len(line))


NEGATION = re.compile(r"\b(not|never|no longer)\b", re.I)
HISTORY = re.compile(
    r"\b(at that time|as history|historically|previously|used to|was the default|no longer the default)\b",
    re.I,
)


def audit(root: Path):
    live, prose, bare, ratio = [], [], [], []
    for rel, path in tracked_files(root):
        text = read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if IDENTS.search(line):
                sep = re.search(r"[:=]", line)
                value = line[sep.end():] if sep else line
                if first_model_token(value) == "5":
                    live.append((rel, i, line.strip()))
            prose_hit = False
            for m in re.finditer(r"\bdefault\b", line, re.I):
                start, end = clause_bounds(line, m.start())
                clause = line[start:end]
                if first_model_token(clause) == "6" and ANY_MODEL.search(clause):
                    # a 2.6 mention in the same clause makes this a current claim
                    if not ANY_MODEL.search(clause[: m.start() - start]):
                        continue
                nb = nearest_token(line, m.start())
                if not nb or nb[0] > PROXIMITY or nb[1] != "5":
                    continue
                if NEGATION.search(clause) or HISTORY.search(clause):
                    continue
                prose.append((rel, i, line.strip()))
                prose_hit = True
                break
            if prose_hit or not GPT_IMAGE_CTX.search(line):
                continue
            # An explicitly prefixed 2.6 model on the line means the `default`
            # word is naming 2.6; D_prose owns every prefixed claim already.
            if any(t.group(1) == "6" for t in ANY_MODEL.finditer(line)):
                continue
            # D_prose_bare: the same claim spelled without the model prefix.
            # Only a line already in a GPT-Image context is in scope, so
            # unrelated version numbers never trip it.
            for m in re.finditer(r"\bdefault\b", line, re.I):
                start, end = clause_bounds(line, m.start())
                clause = line[start:end]
                if NEGATION.search(clause) or HISTORY.search(clause):
                    continue
                # a 2.6 token in the same clause makes this a current claim
                if any(t.group(1) == "6" for t in BARE_MODEL.finditer(clause)):
                    continue
                nearest_bare = None
                for bm in BARE_MODEL.finditer(line):
                    d = min(abs(m.start() - bm.start()), abs(m.end() - bm.end()))
                    if nearest_bare is None or d < nearest_bare[0]:
                        nearest_bare = (d, bm.group(1))
                if not nearest_bare or nearest_bare[0] > PROXIMITY or nearest_bare[1] != "5":
                    continue
                bare.append((rel, i, line.strip()))
                break
    rows = []
    registry = root / "66-kie-image" / "models.json"
    if not registry.exists():
        raise SystemExit("check-kie-image-defaults: missing 66-kie-image/models.json")
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("check-kie-image-defaults: unparsable models.json: %s" % exc)
    models = data["models"] if isinstance(data, dict) and "models" in data else data
    for row in models:
        blob = "%s %s" % (row.get("canonical_model_id", ""), row.get("family", ""))
        version = first_model_token(blob)
        status = row.get("status", "")
        label = row.get("canonical_model_id", "?")
        if version == "5" and status != "legacy":
            rows.append((label, status, "2-5 row must be legacy"))
        elif version == "6" and status != "default":
            rows.append((label, status, "2-6 row must be default"))
        # D_ratio: the 2.6 default route must advertise exactly the vendor set.
        # Legacy rows are out of scope by design — the legacy gpt-image-2 route
        # exists precisely to serve 3:1, 1:3 and 9:21, which 2.6 does not.
        if status == "default" or version == "6":
            claimed = row.get("aspect_ratios")
            if not isinstance(claimed, list) or not claimed:
                ratio.append((label, "none", "default row declares no aspect-ratio set"))
                continue
            claimed_set = [str(r) for r in claimed]
            extra = [r for r in claimed_set if r not in VENDOR_26_RATIOS]
            missing = [r for r in sorted(VENDOR_26_RATIOS) if r not in claimed_set]
            if extra:
                ratio.append((label, ",".join(extra),
                              "claims ratio(s) the 2.6 route does not serve"))
            if missing:
                ratio.append((label, ",".join(missing),
                              "does not advertise ratio(s) the 2.6 route serves"))
    dispatch = dispatch_resolution(root)
    return live, prose, rows, ratio, bare, dispatch


def dispatch_resolution(root: Path) -> str:
    selector = root / "66-kie-image" / "scripts" / "select_image_model.py"
    if not selector.exists():
        raise SystemExit("check-kie-image-defaults: missing %s" % selector)
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(selector), "a photo of a cat in a garden", "--json"],
            capture_output=True, text=True, timeout=180, cwd=str(selector.parent),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("check-kie-image-defaults: selector failed to run: %s" % exc)
    if proc.returncode != 0:
        raise SystemExit("check-kie-image-defaults: selector exited %d: %s"
                         % (proc.returncode, (proc.stderr or proc.stdout).strip()[:300]))
    try:
        return json.loads(proc.stdout).get("selected_model_id", "") or "UNPARSED"
    except ValueError:
        raise SystemExit("check-kie-image-defaults: selector output was not JSON")


def report(root: Path, live, prose, rows, ratio, bare, dispatch) -> int:
    dispatch_ok = "2-6" in dispatch
    total = len(live) + len(prose) + len(rows) + len(ratio) + len(bare) + (0 if dispatch_ok else 1)
    print("KIE image-model defaults — root=%s" % root)
    print("D_live=%d D_prose=%d D_rows=%d D_dispatch=%d D_ratio=%d D_prose_bare=%d  selector=%s"
          % (len(live), len(prose), len(rows), 0 if dispatch_ok else 1,
             len(ratio), len(bare), dispatch))
    print("DEFECTS=%d" % total)
    for rel, i, text in live:
        print("  LIVE   %s:%d  %s" % (rel, i, text[:180]))
    for rel, i, text in prose:
        print("  PROSE  %s:%d  %s" % (rel, i, text[:180]))
    for model_id, status, why in rows:
        print("  ROW    %s status=%s  (%s)" % (model_id, status, why))
    for model_id, ratios, why in ratio:
        print("  RATIO  %s ratios=%s  (%s)" % (model_id, ratios, why))
    for rel, i, text in bare:
        print("  BARE   %s:%d  %s" % (rel, i, text[:180]))
    if not dispatch_ok:
        print("  DISPATCH selector resolved to %s, expected a 2-6 id" % dispatch)
    if total:
        print("")
        print("FAIL: %d stale legacy-image default claim(s). 2.6 Sunburst is the default;" % total)
        print("      mark 2.5 rows legacy and state 2.5 as retained, not the default.")
        return 1
    print("OK: no stale 2.5 default claims; selector resolves 2.6.")
    return 0


def self_test() -> int:
    """Prove the gate discriminates: a stale fixture fails, the real tree passes."""
    import tempfile

    failures = 0
    # Fixture tokens are composed at runtime so this scanner, which reads every
    # tracked file, does not count its own self-test fixture as a live defect.
    m25 = "gpt-image-2-" + "5"
    m25d = "2." + "5"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "66-kie-image" / "scripts").mkdir(parents=True)
        (root / "66-kie-image" / "models.json").write_text(json.dumps({"models": [
            {"canonical_model_id": m25 + "-sunburst-text-to-image",
             "family": m25 + "-sunburst", "status": "default"},
            # deliberate D_ratio defect: claims 3:1 (legacy-only) and drops 8:9
            {"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image",
             "family": "gpt-image-2-6/sunburst", "status": "default",
             "aspect_ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16",
                               "4:3", "3:4", "21:9", "27:16", "16:27", "9:8",
                               "3:1"]},
        ]}), encoding="utf-8")
        (root / "docs.md").write_text(
            "GPT Image " + m25d + " Sunburst is the default for everything.\n"
            # deliberate D_prose_bare defect: bare version, no model prefix
            "GPT-Image route: DEFAULT (" + m25d + ") for everything.\n"
            # negative control: a bare version in a NON GPT-Image context
            "Python " + m25d + " is the default interpreter here.\n",
            encoding="utf-8")
        # a stub selector that resolves 2.6, so D_dispatch stays green and the
        # self-test isolates the doc/data axes it is proving
        (root / "66-kie-image" / "scripts" / "select_image_model.py").write_text(
            "import json\nprint(json.dumps({'selected_model_id': 'gpt-image-2-6/sunburst-text-to-image'}))\n",
            encoding="utf-8")
        live, prose, rows, ratio, bare, dispatch = audit(root)
        total = (len(live) + len(prose) + len(rows) + len(ratio) + len(bare)
                 + (0 if "2-6" in dispatch else 1))
        named = any("docs.md" in s[0] for s in prose)
        bare_line = [s[2] for s in bare]
        bare_ok = any("GPT-Image route" in s for s in bare_line)
        decoy_ok = not any("Python" in s for s in bare_line)
        ratio_ok = any("3:1" in why or "3:1" in vals for _, vals, why in ratio)
        print("self-test stale fixture: DEFECTS=%d prose_named=%s bare_ok=%s decoy_ok=%s ratio_ok=%s"
              % (total, named, bare_ok, decoy_ok, ratio_ok))
        if total < 5 or not named:
            print("FAIL: stale fixture was not caught (expected >=5 defects incl. docs.md)")
            failures += 1
        if not bare_ok:
            print("FAIL: bare 'DEFAULT (%s) route' claim was not caught" % m25d)
            failures += 1
        if not decoy_ok:
            print("FAIL: a bare version outside a GPT-Image context was reported")
            failures += 1
        if not ratio_ok:
            print("FAIL: a 2.6 default row claiming 3:1 was not caught")
            failures += 1

    live, prose, rows, ratio, bare, dispatch = audit(ROOT)
    total = (len(live) + len(prose) + len(rows) + len(ratio) + len(bare)
             + (0 if "2-6" in dispatch else 1))
    print("self-test real tree: DEFECTS=%d" % total)
    if total != 0:
        print("FAIL: the real tree must be clean for this gate to be meaningful")
        failures += 1
    print("SELFTEST %s" % ("OK" if failures == 0 else "FAILED"))
    return 0 if failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail on stale legacy-image default claims.")
    ap.add_argument("--root", default=str(ROOT), help="tree to audit (default: repo root)")
    ap.add_argument("--self-test", action="store_true", help="prove the gate discriminates")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.root).resolve()
    live, prose, rows, ratio, bare, dispatch = audit(root)
    return report(root, live, prose, rows, ratio, bare, dispatch)


if __name__ == "__main__":
    sys.exit(main())
