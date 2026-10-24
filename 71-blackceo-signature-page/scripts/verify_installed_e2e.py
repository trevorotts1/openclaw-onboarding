#!/usr/bin/env python3
"""Offline end-to-end proof that THIS Skill 71 installation can run its own production path.

A lone-directory install has no repository around it: no tests/fixtures, no sibling
checkout, no network. This harness proves the installed tree is enough by building a
COMPLETE run fixture from scratch in a scratch directory and driving the real two
commands a run drives:

    scripts/build_production_request.py   copy -> production-request.json   ("WROTE ...")
    scripts/stage_executor.py --preflight --provider stub                   ("PREFLIGHT ...")

Nothing here is copied from tests/ at runtime; every input is synthesised below, so the
same file runs against a repository checkout and against a bare install.

What it asserts
  1  packaging   every file the exercised path opens is present in the target tree,
                 and each missing one is named
  2  build       the request builder reaches construction: exit 0, the output file
                 exists, and the WROTE line is printed -- not a REFUSED
  3  preflight   the executor reaches its preflight stage, proved by stage_executor's
                 own markers, not by absence of an error:
                   PREFLIGHT_SECTIONS                 stage_executor.py:1666  (the request
                                                      loaded and its section count checked)
                   PREFLIGHT_COLORS <stage> <file>    stage_executor.py:1698  (the brand block
                                                      was inside the composed prompt)
                   PREFLIGHT <stage> <file> ratio=    stage_executor.py:1706  (a full prompt was
                                                      composed for that template -- the strongest
                                                      single marker; it is printed only after
                                                      stage_prompt returns for the template)
  4  offline     stdlib only, provider `stub`, no network import on the exercised module
                 path, and no generation/provider artifact appears anywhere
  5  discrimination  two throwaway copies prove the harness fails for the reason it
                 claims, not by accident:
                   5a inventory  one required packaged asset deleted -> nonzero, and the
                      report NAMES that asset (proves assertion 1, packaging)
                   5b pipeline   `scripts/stage_executor.py` truncated to an empty file
                      (runs, exits 0, prints nothing) -> nonzero, and the report carries
                      a FAIL line for the PREFLIGHT_SECTIONS marker specifically, so the
                      preflight assertion itself is proved to fire -- exit status alone
                      is never accepted as proof that the executor ran
  6  hygiene     no bytecode is written into the inspected tree

What this does not prove
  - the shared prompt-policy registry. `scripts/launch_context.py:_registry_policy_ids`
    resolves `<parent>/shared-utils/signature_launch/domain/prompt-policy-registry.json`,
    i.e. BESIDE the skill tree. A bare lone-directory install has no such sibling, and
    this harness passes on one anyway, so `_registry_policy_ids` is never exercised here.
    `scripts/preflight_installed.py` reports that path separately (PASS/GAP on its own
    row); run it too. Verified: the harness exits 0 on a bare copy while that preflight
    row is GAP.
  - the repository test suite, the network, any paid provider, and optional imaging or
    render libraries (PIL/playwright/...) -- none is imported on the exercised path.
  - the negative-control plants run the harness against a deliberately broken copy; they
    prove it fails, not that every possible break is caught.

Section-count checking is deliberately NOT on that list: the fixture supplies BOTH
sources the executor checks (<run_dir>/copy.json copy source and
copy/copy-manifest.json) and each is asserted below. A fixture with only the manifest
reports "copy source file not found" and would no longer pass.

How "no generation artifact" is proved
  Code path -- build_production_request.py is a pure builder (module docstring: "Zero
  provider calls; the file is the only output"); its main() writes exactly the --out file.
  stage_executor.main() with --preflight composes and validates prompts and returns at the
  `return 1 if refused else 0` line (stage_executor.py:1720), BEFORE make_provider()
  (:1721) and before run_stage()/run_item() are ever reached, so no provider object exists
  and no image path is written.
  Output -- this harness asserts the built request records provider_calls == 0, that the
  preflight output carries none of the generation markers (GENERATED / STAGE / ITEM /
  COMPOSE / OVERVIEW_BOARD / REVIEW_PDF), that the run directory's file set is unchanged
  across the preflight invocation, and that no image file exists in it.

A preflight that refuses is NOT a pass. This fixture is complete by construction, so the
expected exit is 0; a nonzero exit fails the harness, and the failure report says whether
it was one of the two recognised client-data refusals or something unexpected. A traceback
always fails.

Usage:
    python3 scripts/verify_installed_e2e.py [--target DIR] [--work DIR] [--json]
                                           [--skip-negative-control] [--keep]

  --target DIR   the installation to inspect (default: the tree holding this script)
  --work DIR     where the scratch run fixture and the throwaway copy go
                 (default: a fresh system temp directory, removed afterwards)
  --keep         leave the scratch directory in place and print its path
  --skip-negative-control   used by this harness's own recursive negative control

Exit codes: 0 every assertion held; 1 a named assertion failed; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # requirement 6: never write bytecode into anything we touch

STAGE = "visual-mockup"
# stage_executor.LAYOUT[STAGE] -- one output template per platform slice.
TEMPLATE_COUNT = 2
MODEL = "gpt-image-2-5-sunburst-image-to-image"  # the recorded band: floor 16000, target 19000, max 20000
SEQUENCE = [str(i) for i in range(1, 13)]       # references/copy-specs/standard-v6.json `sequence`

# The two refusal literals the skill treats as a legitimate fail-closed stop on missing
# CLIENT data (scripts/brand_colors.py failure(); scripts/build_production_request.py
# around the "supply --design-prose" message). Anything else refusing is unexpected here.
RECOGNISED_REFUSALS = (
    "brand colors unresolved, no image stage may start.",
    "supply --design-prose with the run's measured design system",
)

# Every module the exercised path imports. Evidence: an audit hook (`open` event) run over
# the two commands above recorded exactly these, plus the data files in REQUIRED_DATA.
EXECUTED_MODULES = (
    "brand_colors.py", "build_production_request.py", "circle_image.py", "composition.py",
    "copy_forms.py", "design_style.py", "hypersaturation.py", "page_kinds.py", "page_role.py",
    "reference_use.py", "role_spec.py", "stage_executor.py", "validate_copy_structure.py",
    "validate_prompt.py", "validate_wireframe.py", "wireframe_spec.py",
)

# Every non-code file the exercised path opens (same audit-hook evidence). These are the
# "required packaged assets": deleting one is what the negative control plants.
REQUIRED_DATA = (
    "assets/visual-standards/manifest.json",
    "assets/visual-standards/reference-catalog.json",
    "references/composition-treatments.json",
    "references/copy-specs/long-form-v6.json",
    "references/copy-specs/product-selection-v1.json",
    "references/copy-specs/standard-v6.json",
    "references/copy-specs/thank-you-v1.json",
    "references/copy-specs/upsell-v6.json",
    "references/page-kinds.json",
    "references/prompt-budget-policy.json",
    "references/section-image-prompt.md",
    "references/wireframe-build-spec.json",
)

# The negative-control plant: the copy spec the builder loads for --copy-version standard.
PLANT = "references/copy-specs/standard-v6.json"

NETWORK_IMPORTS = ("socket", "ssl", "urllib", "http.client", "httpx", "requests",
                   "aiohttp", "ftplib", "smtplib", "telnetlib", "xmlrpc", "asyncio.streams")

GENERATION_MARKERS = ("GENERATED ", "STAGE ", "ITEM ", "COMPOSE ", "OVERVIEW_BOARD", "REVIEW_PDF")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".bmp"}
TRACES = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError",
          "No such file or directory")


class Check:
    def __init__(self):
        self.rows = []

    def add(self, ok, name, detail=""):
        self.rows.append((bool(ok), name, detail))
        return bool(ok)

    @property
    def ok(self):
        return all(r[0] for r in self.rows)

    def report(self):
        out = []
        for passed, name, detail in self.rows:
            out.append(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return "\n".join(out)


def sh(cmd, cwd=None, env=None):
    """Run a command, capturing both streams separately. Never a pipeline: the return
    code is the child's own, not a tail's."""
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env,
                          capture_output=True, text=True, timeout=900)


def child_env(home):
    """A pinned environment: no inherited secrets, no inherited configuration, and HOME
    pointed at the scratch directory so an accidental write cannot land anywhere real."""
    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(home), "HOME": str(home)}


# --------------------------------------------------------------------------
# 1. packaging
# --------------------------------------------------------------------------
def check_packaging(root: Path, chk: Check):
    missing = [f"scripts/{m}" for m in EXECUTED_MODULES if not (root / "scripts" / m).is_file()]
    missing += [rel for rel in REQUIRED_DATA if not (root / rel).is_file()]
    chk.add(not missing, "packaging: every exercised file present in the target tree",
            "missing: " + ", ".join(missing) if missing else
            f"{len(EXECUTED_MODULES)} modules + {len(REQUIRED_DATA)} data files")
    return not missing


def check_no_network_imports(root: Path, chk: Check):
    hits = []
    for name in EXECUTED_MODULES:
        path = root / "scripts" / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            hits.append(f"{name}: unreadable ({exc})")
            continue
        for mod in NETWORK_IMPORTS:
            if re.search(r"^\s*(?:import|from)\s+" + re.escape(mod) + r"\b", text, re.M):
                hits.append(f"{name} imports {mod}")
    chk.add(not hits, "offline: no network library imported on the exercised module path",
            "; ".join(hits) if hits else f"scanned {len(EXECUTED_MODULES)} modules")


# --------------------------------------------------------------------------
# the synthesised run fixture
# --------------------------------------------------------------------------
SECTIONS = {
    "1":  ("A declaration of the future you want",
           ["Today your best work reaches fewer people than it deserves.",
            "This page shows the way forward."], "Begin the journey"),
    "2":  ("The first cost you are paying",
           ["Every week without a clear page costs you quiet opportunities.",
            "The people who need you never find the door."], "See the way out"),
    "3":  ("The second cost you are paying",
           ["Your message changes shape every time you explain it.",
            "That drift keeps the right buyers unsure."], "Fix the message"),
    "4":  ("The third cost you are paying",
           ["Effort spent on the wrong page is effort you never get back.",
            "The work is real, and so is the waste."], "Stop the waste"),
    "5":  ("Why this works",
           ["A clear page carries one promise and proves it in order.",
            "Structure does the selling so you never have to push."], "Read the method"),
    "6":  ("Who this is for",
           ["This is for the owner whose work is strong and whose page is quiet.",
            "It is not for anyone hunting a shortcut."], "Check the fit"),
    "7":  ("What you get",
           ["You get a page built in your own colors, in your own words.",
            "Every section is measured before it is drawn."], "See the package"),
    "8":  ("The first benefit",
           ["Your page finally sounds like you on your best day.",
            "That consistency is what makes strangers trust you."], "Claim the first win"),
    "9":  ("The second benefit",
           ["Visitors stop guessing and start moving.",
            "Each band answers the next question before it is asked."], "Claim the second win"),
    "10": ("The third benefit",
           ["You stop rebuilding and start improving.",
            "A measured page becomes an asset you can keep."], "Claim the third win"),
    "11": ("The steps",
           ["1. We listen for the promise only you can make.",
            "2. We measure the words before we draw.",
            "3. We build and hand you the keys."], "Take the first step"),
    "12": ("A letter from the founder",
           ["I built this because good work deserves a page that carries it.",
            "Thank you for reading this far."], "Write back to us"),
}

BRAND = {
    # brand_id must equal intake brand_owner or brand_colors refuses the palette
    # (scripts/brand_colors.py _why_unusable): this is the run's own pinned brand file,
    # the first resolution source, so the fixture needs no bundled client data.
    "brand_id": "fixture-fabrications",
    "source": "synthetic fixture palette (no real client)",
    "palette": {"gold": "#B07A1E", "navy": "#14203C", "cream": "#F2EDE3"},
    "palette_roles": {
        "primary": "#B07A1E", "secondary": "#3E5C8A",
        "accent": ["#8E2F3F"], "background": ["#F2EDE3"], "text": "#14203C",
    },
}


def design_prose(chars=15000):
    """Varied pseudo-sentences standing in for a run's measured design system.

    The builder tops each section up toward the 95 percent target with genuine
    specification and refuses anything under the 80 percent floor without design prose,
    and its padding screens reject repetition -- so the filler is drawn from a large
    vocabulary with a deterministic generator rather than a repeated sentence.
    """
    syl = ["ba", "ke", "lo", "mi", "su", "ta", "ve", "zo", "ri", "na"]
    words = [a + b + c + d for a in syl for b in syl for c in syl for d in syl]
    text, state = [], 7
    while sum(len(t) + 1 for t in text) < chars:
        sentence = []
        for _ in range(12):
            state = (state * 1103515245 + 12345) % 2147483648
            sentence.append(words[state % len(words)])
        text.append(" ".join(sentence) + ".")
    return {"rules_md": "\n".join(text)}


def manuscript():
    out = ["# Internal manuscript (synthetic fixture)", ""]
    for sid in SEQUENCE:
        name, lines, cta = SECTIONS[sid]
        out += [f"## Section {sid}: {name}", ""]
        for line in lines:
            out += [line, ""]
        out += [f"[CTA BUTTON: {cta}]", ""]
        if sid == "12":
            out += ["With respect, Ada Fixture", ""]   # the founder's signature, a label
    return "\n".join(out)


def build_fixture(run_dir: Path):
    """Write a COMPLETE run fixture: brand palette pin, intake, the twelve-section
    manuscript, BOTH section-count sources the executor checks (the run's `copy.json`
    copy source and `copy/copy-manifest.json`), and the design prose the prompt band
    needs. Nothing is read out of tests/."""
    (run_dir / "copy").mkdir(parents=True, exist_ok=True)
    (run_dir / "private").mkdir(parents=True, exist_ok=True)
    (run_dir / "private" / "brand.json").write_text(json.dumps(BRAND, indent=2) + "\n", encoding="utf-8")
    (run_dir / "intake.json").write_text(json.dumps({
        "brand_owner": BRAND["brand_id"],
        "brand_file": "private/brand.json",
        "copy_version": "standard",
        "page_version": "standard",
    }, indent=2) + "\n", encoding="utf-8")
    (run_dir / "copy" / "internal-manuscript.md").write_text(manuscript(), encoding="utf-8")
    (run_dir / "copy" / "copy-manifest.json").write_text(
        json.dumps({"sections": SEQUENCE}) + "\n", encoding="utf-8")
    # The other half of check_section_count: <run_dir>/copy.json is the run's copy
    # source (stage_executor._copy_source_candidates). No `cta` here, so the
    # manuscript's inline labels stay authoritative (stage_executor.py:838-849).
    (run_dir / "copy.json").write_text(
        json.dumps({"sections": [{"id": sid} for sid in SEQUENCE]}) + "\n", encoding="utf-8")
    (run_dir / "design-prose.json").write_text(json.dumps(design_prose()) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# 2-4. build, preflight, offline
# --------------------------------------------------------------------------
def snapshot(path: Path):
    return sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())


def check_build(root: Path, run_dir: Path, chk: Check, home: Path):
    out = run_dir / "production-request.json"
    cmd = [sys.executable, "-B", "-I", str(root / "scripts" / "build_production_request.py"),
           "--copy-version", "standard",
           "--manuscript", str(run_dir / "copy" / "internal-manuscript.md"),
           "--stage", STAGE,
           "--model", MODEL,
           "--design-prose", str(run_dir / "design-prose.json"),
           "--out", str(out)]
    proc = sh(cmd, cwd=root, env=child_env(home))
    text = proc.stdout + proc.stderr
    (run_dir / "build.log").write_text(text, encoding="utf-8")

    chk.add(proc.returncode == 0,
            f"build: build_production_request exited 0 (rc={proc.returncode})",
            first_line(text))
    wrote = re.search(r"^WROTE (.+?) copy_version=", proc.stdout, re.M)
    chk.add(bool(wrote) and Path(wrote.group(1)) == out,
            "build: printed the WROTE line naming its own output",
            (wrote.group(0)[:200] if wrote else first_line(text)))
    chk.add(out.is_file(), "build: the production request file exists", str(out))
    chk.add("REFUSED" not in text, "build: no REFUSED line", "")
    chk.add(not any(t in text for t in TRACES), "build: no traceback or missing-module error", "")

    ok_ids = False
    provider_calls = None
    if out.is_file():
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            data, parse_err = None, str(exc)
        else:
            parse_err = ""
        if data:
            ids = [str(s.get("section_id")) for s in data.get("sections") or []]
            ok_ids = ids == SEQUENCE
            provider_calls = (data.get("metadata") or {}).get("provider_calls")
            chk.add(ok_ids, "build: one request section per canonical copy section, in order",
                    f"ids={','.join(ids)}")
            chk.add(data.get("metadata", {}).get("section_count") == len(SEQUENCE),
                    "build: metadata.section_count is the form's canonical count", "")
            # Both halves of check_section_count, proved rather than assumed: a
            # fixture with only a manifest reports "copy source file not found".
            checked = data.get("metadata", {}).get("checked_against") or []
            chk.add(checked == ["copy source", "copy manifest"],
                    "build: section count checked against the copy source AND the manifest",
                    f"checked_against={'; '.join(checked) or 'request only'}")
        else:
            chk.add(False, "build: production request is valid JSON", parse_err)
    chk.add(provider_calls == 0, "build: metadata records provider_calls == 0",
            f"provider_calls={provider_calls}")
    return proc.returncode, text


def check_preflight(root: Path, run_dir: Path, chk: Check, home: Path):
    cmd = [sys.executable, "-B", "-I", str(root / "scripts" / "stage_executor.py"),
           str(run_dir), "--stages", STAGE, "--preflight", "--provider", "stub"]
    before = snapshot(run_dir)
    proc = sh(cmd, cwd=root, env=child_env(home))
    text = proc.stdout + proc.stderr
    (run_dir / "preflight.log").write_text(text, encoding="utf-8")
    after = snapshot(run_dir)

    # --- did the preflight stage actually run? stage_executor's own markers, not silence.
    chk.add("PREFLIGHT_SECTIONS" in proc.stdout,
            "preflight: PREFLIGHT_SECTIONS printed (stage_executor.py:1666)",
            grep_line(proc.stdout, "PREFLIGHT_SECTIONS"))
    chk.add("checked_against=copy source; copy manifest" in proc.stdout,
            "preflight: section count proved against both sources, not one",
            grep_line(proc.stdout, "PREFLIGHT_SECTIONS"))
    composed = re.findall(r"^PREFLIGHT " + re.escape(STAGE) + r" (\S+) ratio=", proc.stdout, re.M)
    chk.add(bool(composed),
            f"preflight: PREFLIGHT {STAGE} <file> ratio= lines prove prompts composed "
            "(stage_executor.py:1706)",
            f"{len(composed)} lines")
    expected = len(SEQUENCE) * TEMPLATE_COUNT
    chk.add(len(composed) == expected,
            f"preflight: one composed prompt per section per template ({expected})",
            f"got {len(composed)}")
    cta = re.findall(r"^PREFLIGHT_CTA " + re.escape(STAGE) + r" (\S+) ->", proc.stdout, re.M)
    chk.add(cta == SEQUENCE,
            "preflight: PREFLIGHT_CTA ran for every canonical section in order",
            f"{len(cta)} sections")
    chk.add("PREFLIGHT_COLORS" in proc.stdout and "BRAND COLORS" in proc.stdout,
            "preflight: PREFLIGHT_COLORS shows the client palette inside the composed prompt",
            grep_line(proc.stdout, "PREFLIGHT_COLORS"))

    # --- exit discipline
    chk.add(proc.returncode == 0,
            f"preflight: exit 0 for a complete fixture (rc={proc.returncode})",
            classify(text, proc.returncode))
    chk.add("REFUSED" not in text, "preflight: no REFUSED line", "")
    chk.add(not any(t in text for t in TRACES), "preflight: no traceback or missing-module error", "")

    # --- offline: nothing generated, nothing written
    leaked = [m.strip() for m in GENERATION_MARKERS if re.search(r"^" + re.escape(m.rstrip()), text, re.M)]
    chk.add(not leaked, "offline: preflight output carries no generation markers",
            "found: " + ", ".join(leaked) if leaked else
            "no " + " / ".join(m.strip() for m in GENERATION_MARKERS))
    images = [p for p in after if Path(p).suffix.lower() in IMAGE_SUFFIXES]
    chk.add(not images, "offline: no image artifact exists in the run directory",
            f"{len(images)} images" if images else "")
    new_files = [p for p in after if p not in before and p not in
                 ("build.log", "preflight.log", "production-request.json")]
    chk.add(not new_files, "offline: the preflight invocation wrote no file",
            "new: " + ", ".join(new_files) if new_files else "run file set unchanged")
    return proc.returncode, text


def check_no_bytecode(root: Path, before, chk: Check):
    after = {str(p.relative_to(root)) for p in root.rglob("*")
             if p.name == "__pycache__" or p.suffix == ".pyc"}
    created = sorted(after - before)
    chk.add(not created, "hygiene: no bytecode written into the inspected tree",
            "created: " + ", ".join(created) if created else
            f"{len(after)} pre-existing __pycache__/.pyc left untouched" if after else "none")


# --------------------------------------------------------------------------
# 5. negative control
# --------------------------------------------------------------------------
# Two plants, one per layer the harness claims to assert. A nonzero exit alone
# would not prove WHICH assertion caught it, so each plant also names the
# evidence the report has to carry.
#   (id, relative path, how, evidence the report must carry, what it proves)
PLANTS = (
    ("inventory", PLANT, "delete", PLANT,
     "assertion 1 (packaging): the deleted required asset is named as missing"),
    ("pipeline", "scripts/stage_executor.py", "truncate",
     "[FAIL] preflight: PREFLIGHT_SECTIONS",
     "assertion 3 (preflight): the PREFLIGHT_SECTIONS marker assertion fires on a "
     "stage_executor.py that exits 0 printing nothing"),
)


def negative_control(root: Path, work: Path, chk: Check, self_path: Path):
    """Break one layer at a time in a throwaway copy and require this harness to exit
    nonzero carrying that layer's evidence. Each plant is removed with its copy;
    nothing is left in the tree under test."""
    last_rc = 0
    for plant_id, rel, how, evidence, proves in PLANTS:
        copy = work / f"planted-{plant_id}"
        if copy.exists():
            shutil.rmtree(copy)
        copy_work = work / f"planted-{plant_id}-work"
        copy_home = work / f"planted-{plant_id}-home"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        target = copy / rel
        if not target.is_file():
            chk.add(False, f"negative control ({plant_id}): {rel} exists in the copy before planting",
                    rel)
            shutil.rmtree(copy, ignore_errors=True)
            continue
        if how == "delete":
            target.unlink()
        else:  # truncate: the file still exists, imports, exits 0 and prints nothing
            target.write_text("", encoding="utf-8")
        proc = sh([sys.executable, "-B", "-I", str(self_path), "--target", str(copy),
                   "--work", str(copy_work), "--skip-negative-control"],
                  cwd=root, env=child_env(copy_home))
        text = proc.stdout + proc.stderr
        carried = evidence in text
        shutil.rmtree(copy, ignore_errors=True)
        shutil.rmtree(copy_work, ignore_errors=True)
        shutil.rmtree(copy_home, ignore_errors=True)
        last_rc = proc.returncode
        chk.add(proc.returncode != 0,
                f"negative control ({plant_id}): harness exits nonzero (rc={proc.returncode})",
                first_line(text))
        chk.add(carried, f"negative control ({plant_id}): {proves}",
                f"carried {evidence!r}" if carried else
                f"report does not carry {evidence!r}: {first_line(text)}")
    return last_rc


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return "(no output)"


def grep_line(text, needle):
    for line in text.splitlines():
        if needle in line:
            return line.strip()[:200]
    return "(absent)"


def classify(text, rc):
    """Say plainly whether a nonzero exit was a recognised client-data refusal."""
    if rc == 0:
        return "exit 0"
    for sig in RECOGNISED_REFUSALS:
        if sig in text:
            return f"RECOGNISED client-data refusal: {sig}"
    return f"UNEXPECTED nonzero exit rc={rc}: {first_line(text)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Skill 71 offline installed-runtime end-to-end proof")
    ap.add_argument("--target", default=None,
                    help="installation to inspect (default: the tree holding this script)")
    ap.add_argument("--work", default=None,
                    help="scratch directory for the run fixture and the throwaway copy")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--keep", action="store_true", help="leave the scratch directory in place")
    ap.add_argument("--skip-negative-control", action="store_true",
                    help="internal: used by this harness's own negative control")
    args = ap.parse_args(argv)

    root = Path(args.target).resolve() if args.target else Path(__file__).resolve().parents[1]
    if not (root / "scripts").is_dir():
        print(f"FAIL: {root} is not a Skill 71 installation (no scripts/)")
        return 2
    self_path = Path(__file__).resolve()

    work = Path(args.work).resolve() if args.work else Path(tempfile.mkdtemp(prefix="s71-e2e-"))
    work.mkdir(parents=True, exist_ok=True)
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    run_dir = work / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)

    bytecode_before = {str(p.relative_to(root)) for p in root.rglob("*")
                       if p.name == "__pycache__" or p.suffix == ".pyc"}
    chk = Check()
    print(f"Skill 71 offline end-to-end proof — target: {root}")

    complete = check_packaging(root, chk)
    check_no_network_imports(root, chk)
    if complete:
        build_fixture(run_dir)
        chk.add(all((run_dir / r).is_file() for r in
                    ("intake.json", "private/brand.json", "copy/internal-manuscript.md",
                     "copy/copy-manifest.json", "copy.json", "design-prose.json")),
                "fixture: a complete run fixture was synthesised in the scratch directory",
                str(run_dir))
        check_build(root, run_dir, chk, home)
        check_preflight(root, run_dir, chk, home)
    else:
        chk.add(False, "fixture / build / preflight", "not attempted: the target tree is incomplete")
    check_no_bytecode(root, bytecode_before, chk)
    if not args.skip_negative_control:
        negative_control(root, work, chk, self_path)

    print(chk.report())
    print("VERDICT:", "installed runtime runs its own production path offline" if chk.ok
          else "FAILURES above")
    if args.keep:
        print(f"scratch kept at: {work}")
    elif not args.work:
        shutil.rmtree(work, ignore_errors=True)

    if args.json:
        print(json.dumps({"target": str(root), "ok": chk.ok,
                          "rows": [{"ok": ok, "check": n, "detail": d} for ok, n, d in chk.rows]},
                         indent=2))
    return 0 if chk.ok else 1


if __name__ == "__main__":
    sys.exit(main())
