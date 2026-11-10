#!/usr/bin/env python3
"""Launch-family cross-repo parity checker (CON-06).

Compares the onboarding launch family against the 999 (Claude Code harness)
edition, file by file, under the declared allowlist below. The family is
Skill 83 (black-friday-launcher), Skill 49 (signature-funnel), Skill 71
(signature page), Skills 78-82 (page skills), Skill 6 (ghl-install-pages),
Skill 44 + Skill 50 (caf-email) and the three shared-utils trees the launch
reads (signature_launch, client_intake, signature_launch_contract).

Every file in an onboarding tree has exactly one class:

  neutral     byte parity required in 999 (the default; versions included)
  adapter     per-repo: SKILL-level CHANGELOG.md, and the GHL pack files the
              pack manifest (71 repo-integration/ghl-pack-manifest.json) marks
              adapter. Must exist in 999; the diff is reported, never failed
  excluded    the pack manifest marks it exclude: must be ABSENT in 999
  divergent   a declared 999-edition divergence (DIVERGENT below): must exist
              in 999, bytes are NOT compared, but the 999 copy must still
              carry the listed seam tokens, so it cannot silently stay behind
  nine_only   a declared 999-only file (NINE_ONLY below): must be PRESENT in
              999 and is never copied over, deleted or compared

Anything present only in 999 that is not declared nine_only FAILS. Skill 71
itself is judged by its own checker (check-skill71-parity.py), which this
script runs and folds into the report.

Usage:
  check-launch-family-parity.py --onboarding DIR --nine DIR
                                [--family NAME ...] [--json PATH]

Exit codes: 0 parity holds, 1 differences outside the allowlist, 2 usage or
config error. No network, no credentials; file bytes only.
"""
import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

PAGE_SKILLS = ("78-signature-product-selection", "79-signature-order-form",
               "80-signature-upsell", "81-signature-downsell",
               "82-signature-thank-you")
_N = ".claude/skills/"


def _pair(onb_rel, nine_rel=None):
    return (onb_rel, nine_rel or onb_rel)


# family -> (onboarding tree, 999 tree) pairs. "signature-page" (Skill 71) is
# judged by its own checker and synced by its own script.
FAMILIES = {
    "launcher": (
        _pair("83-black-friday-launcher", _N + "black-friday-launcher"),
        _pair("shared-utils/signature_launch"),
        _pair("shared-utils/client_intake"),
        _pair("shared-utils/signature_launch_contract"),
    ),
    "signature-funnel": (_pair("49-signature-funnel", _N + "signature-funnel"),),
    "signature-page": (),
    "page-skills": tuple(_pair(s, _N + s.split("-", 1)[1]) for s in PAGE_SKILLS),
    "ghl-install-pages": (_pair("06-ghl-install-pages", _N + "ghl-install-pages"),),
    "caf-email": (
        _pair("44-convert-and-flow-operator", _N + "convert-and-flow-operator"),
        _pair("50-email-engine", _N + "email-engine"),
    ),
}
FAMILY_CHOICES = tuple(FAMILIES)
PACK_MANIFEST_REL = "71-blackceo-signature-page/repo-integration/ghl-pack-manifest.json"

_LAUNCHER = _N + "black-friday-launcher/"
_SL = "shared-utils/signature_launch/"

# The declared 999-only allowlist. Paths are relative to the 999 repo root.
# The sync never writes, deletes or compares these; parity requires each one
# present while its tree is in scope.
NINE_ONLY = {
    # D1 guided client experience, authored for the 999 harness
    _SL + "experience/guided_experience.py": "D1 guided experience",
    # D2 DIST-02 packaging re-measure tool lives only in 999
    _LAUNCHER + "scripts/generate_dist02_manifest.py": "D2 DIST-02 manifest tool",
    # D4 999-only installer and intake alignment checks
    _LAUNCHER + "tests/verify_installer_python_deps.sh": "D4 installer deps check",
    "shared-utils/client_intake/tests/test_guided_alignment.py": "D4 guided alignment",
    # GHL pack harness files (ADAPTER.md defines the four seams)
    _N + "ghl-install-pages/ADAPTER.md": "pack seam contract",
    _N + "ghl-install-pages/PACK.md": "pack membership",
    _N + "ghl-install-pages/skill_runner.py": "999 skill runner",
    _N + "ghl-install-pages/tests/test_s06_entry_wiring_skill_runner.py": "999 skill runner test",
    _N + "convert-and-flow-operator/PACK.md": "pack membership",
}

# D3: the unpinned 999 guided-experience files built around `render_question`
# (the 999 `questions` path). Copied only when absent, never overwritten; the
# 999 copy must keep the listed seam tokens. launcher_core/cli.py is NOT here:
# it is a pinned file (front_door.py pins every launcher_core/*.py by bytes and
# each repository mints its own pin, see D6), so it is an ordinary neutral
# file and must be byte-identical in both repos. experience/progress_report.py
# is NOT here either: it is neutral because delivery_report.py, which is
# neutral, calls its CON-19 API (RowsRefused, --manifest, --emit-rows).
DIVERGENT = {
    _SL + "experience/render_question.py": ("D3 999 questions path", ()),
    _SL + "experience/test_experience.py": ("D3 999 questions path", ()),
    _SL + "experience/README.md": ("D3 999 questions path", ()),
    # D5: the F17 hosting-admission test loads Skill 45's hosting route
    # (45-design-intelligence-library/scripts/graphics_ghl_push.py) to RECORD the evidence.
    # 999 ships no Skill 45 tree at all; its production fallback is real
    # (launcher_core/graphics_hooks.py -> {state: unavailable, reason: PUSH_REF is not installed}).
    # The 999 copy therefore skips ONLY the route-evidence cases, conditionally and by name, and
    # runs every admission/refusal case against launcher_core/image_stages.py. The seam tokens
    # prove that adaptation is present: the Skill 45 path is still named, the skip is conditional,
    # and the admission matrix is the thing under test.
    _LAUNCHER + "tests/test_hosting_admission.py": (
        "D5 999 has no Skill 45: route-evidence cases skip conditionally, admission matrix runs",
        ("_SKILL45_PUSH", "unittest.skipUnless", "hosted_admission")),
    # D6: Skill 71 is in the pin spec and carries declared 999 differences, so the two
    # repositories pin different files and must hold different digests; each pin is
    # checked against its own files by hashpin and the Skill 49 self-test.
    _N + "signature-funnel/scripts/SF-PROVER-PIN.sha256": (
        "D6 per-repo pin: each repository's own sf-prover-pin-authority workflow mints it", ()),
}

# The parity gates themselves ride with the signature-page family, so 999 can
# run them in its own workflow (and the carried CON-09 checker reaches 999).
GATE_TOOLS = ("scripts/check-skill71-parity.py", "scripts/check-launch-family-parity.py")

FAIL_STATUSES = {"missing", "drift", "adapter_missing", "divergent_missing",
                 "excluded_present", "unclassified_nine_only", "nine_only_missing",
                 "divergent_token_missing", "self_certifying", "onb_tree_missing"}
TRACKED_STATUSES = {"adapter_diff", "divergent_diff"}
COPY_STATUSES = {"missing", "drift"}                       # sync overwrites or creates
SEED_STATUSES = {"adapter_missing", "divergent_missing"}   # sync creates, never overwrites
REFUSE_STATUSES = {"excluded_present", "self_certifying", "onb_tree_missing"}


def _files(root: Path) -> dict:
    if not root.is_dir():
        return {}
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if (p.is_file() and "__pycache__" not in rel.parts
                and p.name != ".DS_Store" and p.suffix != ".pyc"):
            out[rel.as_posix()] = p
    return out


def _pack_manifest(onb: Path) -> dict:
    """dest path (999 root relative) -> (class, verdict) from the GHL pack manifest."""
    path = onb / PACK_MANIFEST_REL
    if not path.is_file():
        return {}
    items = json.loads(path.read_text(encoding="utf-8")).get("files", [])
    return {i["dest"]: (i.get("class"), i.get("verdict")) for i in items}


def diff_counts(a: bytes, b: bytes) -> tuple:
    al = a.decode("utf-8", errors="replace").splitlines()
    bl = b.decode("utf-8", errors="replace").splitlines()
    lines = list(difflib.unified_diff(al, bl, lineterm=""))
    return (sum(1 for x in lines if x.startswith("+") and not x.startswith("+++")),
            sum(1 for x in lines if x.startswith("-") and not x.startswith("---")))


def family_plan(onb: Path, nine: Path, name: str) -> list:
    """One (status, dest_rel, detail) row per file or finding in the family.

    dest_rel is relative to the 999 root; detail is the onboarding source path
    (relative to the onboarding root) or a note. Pure: reads only.
    """
    pack = _pack_manifest(onb)
    rows = []
    if name == "signature-page":
        for rel in GATE_TOOLS:
            a, b = onb / rel, nine / rel
            rows.append(("onb_tree_missing", rel, rel) if not a.is_file()
                        else ("missing", rel, rel) if not b.is_file()
                        else ("drift" if a.read_bytes() != b.read_bytes() else "ok", rel, rel))
    for onb_rel, nine_rel in FAMILIES[name]:
        a_root, b_root = onb / onb_rel, nine / nine_rel
        if not a_root.is_dir():
            rows.append(("onb_tree_missing", nine_rel, onb_rel))
            continue
        if b_root.exists() and onb.resolve() in b_root.resolve().parents:
            rows.append(("self_certifying", nine_rel, str(b_root.resolve())))
            continue
        a, b = _files(a_root), _files(b_root)
        for rel, ap in a.items():
            dest, src = f"{nine_rel}/{rel}", f"{onb_rel}/{rel}"
            if dest in NINE_ONLY:
                continue
            bp = b.get(rel)
            cls, verdict = pack.get(dest, (None, None))
            if verdict == "exclude":
                if bp:
                    rows.append(("excluded_present", dest, src))
                continue
            if dest in DIVERGENT:
                same = bp is not None and ap.read_bytes() == bp.read_bytes()
                rows.append(("ok" if same else "divergent_missing" if bp is None
                             else "divergent_diff", dest, src))
            elif cls == "adapter" or rel == "CHANGELOG.md":
                same = bp is not None and ap.read_bytes() == bp.read_bytes()
                rows.append(("ok" if same else "adapter_missing" if bp is None
                             else "adapter_diff", dest, src))
            elif bp is None:
                rows.append(("missing", dest, src))
            elif ap.read_bytes() != bp.read_bytes():
                rows.append(("drift", dest, src))
            else:
                rows.append(("ok", dest, src))
        for rel in b:
            dest = f"{nine_rel}/{rel}"
            if rel not in a and dest not in NINE_ONLY:
                rows.append(("unclassified_nine_only", dest, "present only in 999"))
        scope = nine_rel + "/"
        for dest in NINE_ONLY:
            if dest.startswith(scope) and not (nine / dest).is_file():
                rows.append(("nine_only_missing", dest, NINE_ONLY[dest]))
        for dest, (_note, tokens) in DIVERGENT.items():
            fp = nine / dest
            if dest.startswith(scope) and fp.is_file():
                text = fp.read_text(encoding="utf-8", errors="replace")
                for tok in tokens:
                    if tok not in text:
                        rows.append(("divergent_token_missing", dest, tok))
    return rows


def check_signature_page(onb: Path, nine: Path) -> tuple:
    """Skill 71 is judged by its own checker; fold its findings in."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "check-skill71-parity.py"),
         "--onb-root", str(onb), "--nine-root", str(nine)],
        text=True, capture_output=True)
    fails = [ln[5:] for ln in proc.stdout.splitlines() if ln.startswith("FAIL ")]
    tracked = [ln[8:] for ln in proc.stdout.splitlines() if ln.startswith("TRACKED ")]
    if proc.returncode not in (0, 1):
        fails.append(f"skill 71 checker error (exit {proc.returncode}): "
                     f"{(proc.stdout + proc.stderr).strip()[:300]}")
    elif proc.returncode == 1 and not fails:
        fails.append("skill 71 checker failed without a FAIL line")
    return fails, tracked


def check(onb: Path, nine: Path, families) -> dict:
    failures, tracked = [], []
    for name in families:
        if name == "signature-page":
            f, t = check_signature_page(onb, nine)
            failures += [f"[{name}] {x}" for x in f]
            tracked += [{"family": name, "note": x} for x in t]
        for status, dest, detail in family_plan(onb, nine, name):
            if status in FAIL_STATUSES:
                failures.append(f"[{name}] {status}: {dest} ({detail})")
            elif status in TRACKED_STATUSES:
                src = onb / detail
                added, removed = diff_counts(src.read_bytes(), (nine / dest).read_bytes())
                tracked.append({"family": name, "class": status, "file": dest,
                                "lines_added": added, "lines_removed": removed})
    return {"failures": failures, "tracked_differences": tracked}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Launch-family cross-repo parity checker (CON-06).")
    ap.add_argument("--onboarding", "--onb-root", dest="onb", type=Path, required=True)
    ap.add_argument("--nine", "--nine-root", dest="nine", type=Path, required=True)
    ap.add_argument("--family", action="append", choices=FAMILY_CHOICES,
                    help="limit to a family (repeatable); default all")
    ap.add_argument("--json", type=Path, default=None, help="write the report as JSON")
    args = ap.parse_args(argv)
    if not args.onb.is_dir() or not args.nine.is_dir():
        print(f"FAIL: root missing (onboarding: {args.onb}, 999: {args.nine})")
        return 2
    report = check(args.onb, args.nine, args.family or FAMILY_CHOICES)
    for t in report["tracked_differences"]:
        print("TRACKED " + " ".join(f"{k}={v}" for k, v in t.items()))
    for f in report["failures"]:
        print(f"FAIL {f}")
    n, m = len(report["failures"]), len(report["tracked_differences"])
    print(f"PARITY FAIL: {n} difference(s) outside the allowlist, {m} declared divergence(s)"
          if n else f"PARITY PASS: no difference outside the allowlist; {m} declared divergence(s)")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
