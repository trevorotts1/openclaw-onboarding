#!/usr/bin/env python3
"""Installed-runtime preflight for Skill 71 (blackceo-signature-page).

Answers one question honestly: can THIS installation run the skill's production
scripts, and which declared assets does it actually resolve? It never touches
the network, never spends, and never generates anything.

It deliberately does not pretend the repository test suite ran. Tests that
resolve fixtures from the repository root (the skill's parent directory) cannot
run from a lone-directory install; they are reported as NOT RUN with the exact
command that does run them.

Usage:
    python3 scripts/preflight_installed.py [--target DIR] [--json]

Exit codes:
    0  installed runtime is ready: layout and imports passed, every declared
       local asset resolves, and the representative dry run behaved as expected
    1  a runtime gap was demonstrated: something a production script needs is
       missing or fails
    2  the preflight could not complete a section (named in the output)

What the dry run normally shows. This tree carries no client brand data, so in
the normal case `build_production_request.py` REFUSES ("brand colors
unresolved, ...") before writing a request, and the `stage_executor --preflight`
row is SKIP -- not PASS -- because the executor was never reached. A PASS on
that row means the build produced a request AND the executor printed its own
PREFLIGHT markers; exit status alone is never proof that it ran.

A demonstrated gap is fatal to the verdict even when the exercised path never
reached it — a dependency does not stop being missing because this run did not
call it. Optional imaging/render capabilities are reported SKIP, matching
`verify.sh --capabilities`, and never flip the verdict.

Rows reported but NOT gating the verdict: DEGRADED (the shared design tokens
component resolves outside this tree -- emit_design_tokens records
`component_not_in_tree` and carries on) and REF (the shared design.css is a
component reference recorded in a produced page, with no read path in this
tree). Only GAP and FAIL gate.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Importing the installation's modules must not litter it with bytecode.
sys.dont_write_bytecode = True
_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

# Shared components this skill reaches for beside its own tree. Each entry is
# (relative path, consumer, what breaks when it is absent).
SHARED_REFS = (
    ("shared-utils/signature_launch/domain/prompt-policy-registry.json",
     "scripts/launch_context.py:251",
     "a 1.1 page request whose prompt_policy_id needs the citation vocabulary"),
    ("shared-utils/signature_launch/design/design.css",
     "scripts/launch_context.py:679",
     "the design-tokens component recorded in a produced page"),
    ("shared-utils/signature_launch/design/tokens/tokens.py",
     "scripts/launch_context.py:421",
     "emitting the tokens component for the run's brand"),
)

# Local assets the production scripts declare by constant.
REQUIRED_LOCAL = (
    "SKILL.md",
    "VERSION",
    "skill-version.txt",
    "scripts/stage_executor.py",
    "scripts/build_production_request.py",
    "scripts/launch_context.py",
    "scripts/two_strike_adapter.py",
    "references/copy-specs/standard-v6.json",
    "references/copy-specs/long-form-v6.json",
    "references/section-image-prompt.md",
    "repo-integration/skill71-sync-allowlist.json",
)

# Optional capabilities. verify.sh --capabilities reports these as SKIP-IMAGE /
# SKIP-RENDER when absent, so their absence is a skip here, never a gap.
OPTIONAL_MODULES = ("PIL", "cv2", "numpy", "playwright", "jsonschema", "pypdf")

REPO_ONLY_MARKER = "REPO_ROOT"

# The sync allowlist that classes every file, and the location it records for
# the 999 (Claude Code) edition of this skill.
ALLOWLIST_REL = "repo-integration/skill71-sync-allowlist.json"
NINE_SKILL_REL = ".claude/skills/blackceo-signature-page"


def skill_root_for(script: Path) -> Path:
    return script.resolve().parents[1]


def _allowlist(root: Path) -> dict:
    try:
        return json.loads((root / ALLOWLIST_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def nine_layout(root: Path, allow=None) -> bool:
    """True when `root` is the 999 (Claude Code) install of this skill.

    The allowlist names that location itself (`skill_999`); a checkout of the
    onboarding repository never ends with it.
    """
    if allow is None:
        allow = _allowlist(root)
    nine_rel = allow.get("skill_999") or NINE_SKILL_REL
    here = Path(root).as_posix().rstrip("/")
    return here == nine_rel or here.endswith("/" + nine_rel)


def required_local(root: Path):
    """Required and prohibited assets for THIS layout.

    `scripts/two_strike_adapter.py` is onboarding-only: the sync allowlist
    classes it `onb_only` and forbids it in the 999 edition. Demanding it
    there would make a correctly synced 999 install fail its own gate, so
    the required list follows the layout -- and the prohibition is kept, not
    traded away, by checking those files are ABSENT.
    """
    allow = _allowlist(root)
    if not nine_layout(root, allow):
        return REQUIRED_LOCAL, ()
    globs = allow.get("classes", {}).get("onb_only", {}).get("globs", [])
    prohibited = tuple(rel for rel in REQUIRED_LOCAL
                       if any(fnmatch.fnmatch(rel, g) for g in globs))
    return tuple(rel for rel in REQUIRED_LOCAL if rel not in prohibited), prohibited


def check_layout(root: Path):
    rows, ok = [], True
    required, prohibited = required_local(root)
    for rel in required:
        present = (root / rel).is_file()
        rows.append(("PASS" if present else "FAIL", f"asset {rel}",
                     "" if present else "missing"))
        ok = ok and present
    for rel in prohibited:
        present = (root / rel).is_file()
        rows.append(("FAIL" if present else "PASS", f"prohibited asset {rel}",
                     "present in this layout; the sync allowlist forbids it"
                     if present else "absent, as the sync allowlist requires"))
        ok = ok and not present
    for rel in ("scripts", "references", "assets", "tests"):
        present = (root / rel).is_dir()
        rows.append(("PASS" if present else "FAIL", f"dir {rel}",
                     "" if present else "missing"))
        ok = ok and present
    return rows, ok


def check_imports(root: Path):
    """Import every production module. No network, no writes, no generation."""
    rows, ok = [], True
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    for path in sorted(scripts.glob("*.py")):
        if path.name.startswith("test_") or path.name == Path(__file__).name:
            continue
        mod = "pf_" + path.stem
        try:
            spec = importlib.util.spec_from_file_location(mod, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod] = module
            spec.loader.exec_module(module)
            rows.append(("PASS", f"import {path.name}", ""))
        except SystemExit as exc:                      # argparse in a module body
            rows.append(("PASS" if exc.code in (0, None) else "FAIL",
                         f"import {path.name}", f"SystemExit {exc.code}"))
            ok = ok and exc.code in (0, None)
        except Exception as exc:                       # noqa: BLE001
            # Optional imaging/render libraries are capabilities, not packaging:
            # verify.sh --capabilities reports them as SKIP-IMAGE / SKIP-RENDER,
            # so a lean host must not turn this preflight red for their absence.
            missing = getattr(exc, "name", None) or ""
            if isinstance(exc, ImportError) and missing.split(".")[0] in OPTIONAL_MODULES:
                rows.append(("SKIP", f"import {path.name}",
                             f"optional capability absent: {missing}"))
            else:
                rows.append(("FAIL", f"import {path.name}",
                             f"{type(exc).__name__}: {exc}"))
                ok = False
        finally:
            sys.modules.pop(mod, None)
    sys.path.remove(str(scripts))
    return rows, ok


def check_shared(root: Path):
    """Cross-tree refs resolve against the skill's PARENT by design.

    Demonstrated, not asserted: the two consumers that are functions are called
    here so the refusal (or the dangling path) is real output, not a guess. The
    design.css entry is a recorded component reference; nothing in this tree
    reads it, so it is reported as a reference and not as a failed call.
    """
    rows = []
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("pf_launch_context", scripts / "launch_context.py")
        lc = ilu.module_from_spec(spec)
        sys.modules["pf_launch_context"] = lc
        spec.loader.exec_module(lc)

        try:
            lc._registry_policy_ids(str(root))
            rows.append(("PASS", "shared prompt-policy registry readable", ""))
        except Exception as exc:                       # noqa: BLE001
            rows.append(("GAP", "shared prompt-policy registry",
                         f"demonstrated: {type(exc).__name__}: {str(exc)[:220]}"))
        try:
            path = Path(lc.tokens_component_path(str(root)))
            if path.is_file():
                rows.append(("PASS", "shared tokens component", ""))
            else:
                # emit_design_tokens records component_not_in_tree and carries
                # on, so this is a recorded degradation, not a failed call.
                rows.append(("DEGRADED", "shared tokens component",
                             f"resolved to {path} (absent); design tokens are recorded as "
                             f"component_not_in_tree rather than emitted"))
        except Exception as exc:                       # noqa: BLE001
            rows.append(("FAIL", "shared tokens component",
                         f"{type(exc).__name__}: {exc}"))
    except Exception as exc:                           # noqa: BLE001
        rows.append(("FAIL", "shared consumers import", f"{type(exc).__name__}: {exc}"))
    finally:
        sys.modules.pop("pf_launch_context", None)
        sys.path.remove(str(scripts))

    css = root.parent / "shared-utils/signature_launch/design/design.css"
    rows.append(("PASS" if css.is_file() else "REF", "shared design.css (recorded component ref)",
                 "" if css.is_file() else f"absent at {css}; recorded in a produced page, no read path in this tree"))
    return rows


PACKAGING_TOKENS = ("No such file", "Errno 2", "ModuleNotFoundError", "ImportError")

# The only refusal wording that demonstrates a correct runtime: the skill
# refusing because the CLIENT has not supplied data this preflight must never
# invent. Exact literals, read from the emitting code — not a keyword match:
#   scripts/brand_colors.py failure()            "brand colors unresolved, ..."
#   scripts/build_production_request.py:741      "(supply --design-prose with the
#                                                 run's measured design system)"
# Any other REFUSED means the run failed for a reason that cannot be attributed
# to missing client data, so it is a gap.
CLIENT_DATA_REFUSALS = (
    "brand colors unresolved, no image stage may start.",
    "supply --design-prose with the run's measured design system",
)

# The executor's own fail-closed wording, read from the emitter it actually
# prints (stage_executor.py:1044, surfaced as "PREFLIGHT ... REFUSED: ..." at
# :1694). It differs from the build's rewording above, so mixing the two makes
# a healthy install look broken.
EXECUTOR_FAIL_CLOSED = (
    "brand colors unresolved, no image stage may start.",
    "add genuine specification",
)


TRACEBACK_MARKER = "Traceback (most recent call last)"

# Exit 0 is proof only when BOTH markers of a completed preflight are present:
# the section check (stage_executor.py:1666) and at least one composed prompt
# (`PREFLIGHT <stage> <file> ratio=...`, stage_executor.py:1706). The executor
# prints PREFLIGHT_SECTIONS before composing anything, so a run that dies
# straight after section validation still prints the first and nothing else.
EXECUTOR_SECTIONS_RE = re.compile(r"PREFLIGHT_SECTIONS\b")
EXECUTOR_PROMPT_RE = re.compile(r"PREFLIGHT \S+ \S+ ratio=")


def _last_nonempty_line(text: str) -> str:
    for raw in reversed(text.splitlines()):
        if raw.strip():
            return raw.strip()
    return ""


def classify_build_failure(text: str) -> str:
    """'refused' or 'gap' for a failed build_production_request run.

    build_production_request prints REFUSED for OSError too, and OSError
    includes a missing packaged file. A packaging break must never be read as a
    polite refusal, so the file/module signature is tested first and wins.

    A refusal must also be the TERMINAL evidence, not a substring anywhere:
    the builder prints one `REFUSED: <reason>` line and returns 1, so the last
    non-empty line has to be that line, carrying an allowlisted client-data
    literal. A refusal followed by a traceback or an Errno 13 line, and a
    wrapper error that merely quotes the literal mid-text, are both gaps --
    the run crashed or failed for a reason that cannot be attributed to missing
    client data.
    """
    if any(tok in text for tok in PACKAGING_TOKENS):
        return "gap"
    if TRACEBACK_MARKER in text:
        return "gap"
    last = _last_nonempty_line(text)
    if not last.startswith("REFUSED: "):
        return "gap"
    if any(sig in last for sig in CLIENT_DATA_REFUSALS):
        return "refused"
    return "gap"


def classify_executor_exit(returncode: int, text: str) -> str:
    """'ok', 'fail-closed' or 'gap' for a stage_executor --preflight exit.

    stage_executor returns 1 both for a legitimate fail-closed refusal and for
    an unexpected break (argparse, traceback, missing asset), so the exit code
    alone proves nothing. Only a FAIL or PREFLIGHT REFUSED line carrying an
    allowlisted client-data reason counts as fail-closed; every other nonzero
    exit is a gap.

    Exit 0 is not proof either: an empty or stubbed stage_executor.py imports
    cleanly and exits 0 printing nothing. A zero exit counts as 'ok' only with
    POSITIVE evidence that the preflight both validated and composed -- an
    anchored PREFLIGHT_SECTIONS line AND at least one
    `PREFLIGHT <stage> <file> ratio=...` line -- and no traceback. A refusal-
    shaped line is never a success whatever the exit status: the executor
    prints `PREFLIGHT ... REFUSED:` for a stage it could not compose and
    `FAIL:` for a run it abandoned.
    """
    if returncode == 0:
        lines = [raw.strip() for raw in text.splitlines()]
        if TRACEBACK_MARKER in text:
            return "gap"
        if any(raw.startswith("FAIL:") or "REFUSED:" in raw for raw in lines):
            return "gap"
        if not any(EXECUTOR_SECTIONS_RE.match(raw) for raw in lines):
            return "gap"
        if not any(EXECUTOR_PROMPT_RE.match(raw) for raw in lines):
            return "gap"
        return "ok"
    if returncode != 1:  # 2 is usage/run-dir, never a fail-closed refusal
        return "gap"
    if any(tok in text for tok in PACKAGING_TOKENS):
        return "gap"
    if TRACEBACK_MARKER in text:
        return "gap"
    # Same terminal-evidence rule as the build path: a refusal followed by a
    # crash is a crash, so the last non-empty line must itself be the refusal
    # carrying a client-data literal. Multiple refusal lines still pass (the
    # last one is a refusal); a trailer or exception line does not.
    last = _last_nonempty_line(text)
    if not (last.startswith("FAIL: ") or " REFUSED: " in last):
        return "gap"
    if any(sig in last for sig in EXECUTOR_FAIL_CLOSED):
        return "fail-closed"
    return "gap"


def verdict_is_ready(layout_ok: bool, import_ok: bool, dry_ok: bool, rows) -> bool:
    """A demonstrated gap always loses, whatever the section flags say."""
    gaps = [r for r in rows if r[0] in ("GAP", "FAIL")]
    return bool(layout_ok and import_ok and dry_ok and not gaps)


def _layout_fixture(tmp: Path, omits=(), extra=(), nine=False) -> Path:
    """A synthetic install: every required asset, minus `omits`, plus `extra`."""
    root = tmp / NINE_SKILL_REL if nine else tmp
    for rel in ("scripts", "references", "assets", "tests"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    allow = {"skill_999": NINE_SKILL_REL,
             "classes": {"onb_only": {"globs": ["scripts/two_strike_adapter.py"]}}}
    for rel in [r for r in REQUIRED_LOCAL if r not in omits] + list(extra):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(allow) if rel == ALLOWLIST_REL else "x",
                        encoding="utf-8")
    return root


def self_check() -> int:
    build_cases = (
        ("REFUSED: brand colors unresolved, no image stage may start. Tried: no intake; "
         "Ask the client", "refused"),
        ("REFUSED: visual-mockup section 1: prompt budget: 10609 chars, 5391 below the "
         "16000-char floor; add genuine specification (supply --design-prose with the "
         "run's measured design system)", "refused"),
        ("REFUSED: something else entirely", "gap"),
        ("REFUSED: page role 'bogus' has no entry in references/page-structures.json", "gap"),
        ("REFUSED: [Errno 2] No such file or directory: 'references/planted.md'", "gap"),
        ("REFUSED: ModuleNotFoundError: No module named 'jsonschema'", "gap"),
        ("REFUSED: brand colors unresolved, no image stage may start. "
         "No such file: private/brand.json", "gap"),
        ("Traceback (most recent call last): ValueError: boom", "gap"),
        # A refusal is proof only when it is the TERMINAL line, with nothing
        # after it. A crash wearing a refusal's words is a gap.
        ("REFUSED: brand colors unresolved, no image stage may start.\n"
         "Traceback (most recent call last):\nValueError: boom", "gap"),
        ("wrapper ValueError: brand colors unresolved, no image stage may start.", "gap"),
        ("BUILD REFUSED: something else\n"
         "ValueError: brand colors unresolved, no image stage may start.", "gap"),
        ("REFUSED: brand colors unresolved, no image stage may start.\n"
         "[Errno 13] Permission denied: 'private/brand.json'", "gap"),
        ("REFUSED: brand colors unresolved, no image stage may start.\n"
         "PermissionError: [Errno 13] Permission denied", "gap"),
    )
    exit_cases = (
        # A composed prompt without the section check is half a preflight.
        (0, "PREFLIGHT visual-mockup mobile/part-1.png ratio=3:4 chars=17000", "gap"),
        # Exit 0 from a script that never ran the preflight proves nothing: an
        # empty stage_executor.py exits 0 printing nothing.
        (0, "", "gap"),
        (0, "Traceback (most recent call last):\nKeyError: 'sections'", "gap"),
        # The section banner alone is what a run that dies before composing
        # prints. It proves the section check, not the preflight.
        (0, "PREFLIGHT_SECTIONS copy_version=standard sections=12", "gap"),
        (0, "PREFLIGHT_SECTIONS copy_version=standard sections=12\n"
            "PREFLIGHT visual-mockup desktop/part-01.png ratio=3:4 chars=17000", "ok"),
        # A refusal-shaped line at exit 0 is still a refusal.
        (0, "PREFLIGHT_SECTIONS copy_version=standard sections=12\nFAIL: broken", "gap"),
        (0, "PREFLIGHT_SECTIONS copy_version=standard sections=12\n"
            "PREFLIGHT visual-mockup a.png REFUSED: broken", "gap"),
        (0, "NOTE page_kind: not declared\n", "gap"),
        (1, "FAIL: brand colors unresolved, no image stage may start. Tried: run brand pin "
            "private/brand.json: file not found. Ask the client: What are your brand colors?",
         "fail-closed"),
        # Captured verbatim from stage_executor.py:1044/:1694 — the executor has
        # no design-prose rewording, so the build's phrasing must not pass here.
        (1, "PREFLIGHT visual-mockup desktop/part-01.png REFUSED: prompt budget: "
            "visual-mockup section 1: 3611 chars, 12389 below the 16000-char floor "
            "(19000-char target); add genuine specification", "fail-closed"),
        (1, "PREFLIGHT visual-mockup part-1.png REFUSED: prompt budget: section 1 below the "
            "16000-char floor (supply --design-prose with the run's measured design system)",
         "gap"),
        (1, "Traceback (most recent call last):\nKeyError: 'sections'", "gap"),
        (2, "usage: stage_executor.py [-h] ...\nstage_executor.py: error: unrecognized arguments",
         "gap"),
        (2, "FAIL: brand colors unresolved, no image stage may start. Tried: none", "gap"),
        (1, "FAIL: unknown stage 'bogus'; expected one of ['design-board']", "gap"),
        (1, "FAIL: cannot read production request /x: [Errno 2] No such file or directory",
         "gap"),
        (1, "PREFLIGHT visual-mockup part-1.png REFUSED: something else entirely", "gap"),
        # A crash after a legitimate refusal is a crash, exactly as on the
        # build path: the refusal must be the terminal evidence.
        (1, "PREFLIGHT visual-mockup desktop/part-01.png REFUSED: prompt budget: "
            "visual-mockup section 1: 3611 chars, 12389 below the 16000-char floor "
            "(19000-char target); add genuine specification\n"
            "Traceback (most recent call last):\nValueError: boom after a legitimate refusal",
         "gap"),
        (1, "PREFLIGHT visual-mockup desktop/part-01.png REFUSED: prompt budget: "
            "visual-mockup section 1: 3611 chars, 12389 below the 16000-char floor "
            "(19000-char target); add genuine specification\n"
            "PermissionError: [Errno 13] denied", "gap"),
        (1, "PREFLIGHT visual-mockup a.png REFUSED: prompt budget: 1 chars, 1 below the "
            "16000-char floor; add genuine specification\n"
            "PREFLIGHT visual-mockup b.png REFUSED: prompt budget: 2 chars, 2 below the "
            "16000-char floor; add genuine specification", "fail-closed"),
    )
    layout_cases = (
        # The 999 layout: two_strike_adapter.py is classed onb_only and
        # forbidden there, so its absence must not read as a missing asset.
        ("999 layout without the onb_only module", True,
         ("scripts/two_strike_adapter.py",), (), True),
        # ... and the prohibition still bites when it is carried across.
        ("999 layout carrying the prohibited module", True, (),
         ("scripts/two_strike_adapter.py",), False),
        # The onboarding layout does require it.
        ("onboarding layout without the module", False,
         ("scripts/two_strike_adapter.py",), (), False),
        # A neutral asset missing in 999 is still a gap.
        ("999 layout missing a neutral asset", True,
         ("references/section-image-prompt.md",), (), False),
    )
    verdict_cases = (
        (True, True, True, [("PASS", "x", "")], True),
        (True, True, True, [("GAP", "x", "")], False),
        (True, True, True, [("FAIL", "x", "")], False),
        (True, True, False, [], False),
        (False, True, True, [], False),
        (True, False, True, [], False),
    )

    bad = []
    for text, want in build_cases:
        got = classify_build_failure(text)
        if got != want:
            bad.append(f"build {text[:60]!r}: want {want}, got {got}")
    for rc, text, want in exit_cases:
        got = classify_executor_exit(rc, text)
        if got != want:
            bad.append(f"executor rc={rc} {text[:60]!r}: want {want}, got {got}")
    for lo, io, do, rows, want in verdict_cases:
        got = verdict_is_ready(lo, io, do, rows)
        if got != want:
            bad.append(f"verdict {(lo, io, do, [r[0] for r in rows])}: want {want}, got {got}")
    for label, nine, omits, extra, want in layout_cases:
        with tempfile.TemporaryDirectory() as td:
            _rows, got = check_layout(_layout_fixture(Path(td), omits, extra, nine))
        if got != want:
            bad.append(f"layout {label}: want {want}, got {got}")

    for line in bad:
        print(f"  [FAIL] {line}")
    if bad:
        print("SELF-CHECK FAIL")
        return 1
    total = len(build_cases) + len(exit_cases) + len(layout_cases) + len(verdict_cases)
    print(f"SELF-CHECK PASS — {total} classification, layout and verdict cases "
          f"({len(build_cases)} build, {len(exit_cases)} executor exit, "
          f"{len(layout_cases)} layout, {len(verdict_cases)} verdict)")
    return 0


def check_dry_run(root: Path):
    """One representative production path, offline: build a request, preflight it.

    No network, no paid provider, no generation: build_production_request only
    reads the copy spec and the manuscript, and stage_executor --preflight fails
    closed before any call.
    """
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="s71-preflight-"))
    try:
        spec_path = root / "references" / "copy-specs" / "standard-v6.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        sequence = list(spec["sequence"])
        ms = tmp / "copy" / "internal-manuscript.md"
        ms.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for sid in sequence:
            lines.append(f"## Section {sid}: Preflight section {sid}\n")
            lines.append("[CTA BUTTON: Continue]\n")
            lines.append("Word " * 160 + "\n")
        ms.write_text("\n".join(lines), encoding="utf-8")

        out = tmp / "production-request.json"
        build = subprocess.run(
            [sys.executable, str(root / "scripts" / "build_production_request.py"),
             "--copy-version", "standard", "--manuscript", str(ms),
             "--stage", "visual-mockup", "--out", str(out)],
            cwd=str(root), capture_output=True, text=True, timeout=120, env=_ENV)
        build_text = (build.stdout + build.stderr).strip()
        if build.returncode != 0 or not out.is_file():
            last = [ln for ln in build_text.splitlines() if ln.strip()][-1:] or ["no output"]
            detail = last[0][:200]
            # PASS only for a refusal this preflight can attribute to client data
            # it must not invent; any other refusal is an unproven runtime.
            if classify_build_failure(build_text) == "refused" and not out.is_file():
                rows.append(("PASS", "dry run: build_production_request (refused on client data)",
                             detail[:160]))
                rows.append(("SKIP", "dry run: stage_executor --preflight",
                             "not reached: the build stopped for missing client data, which "
                             "this preflight does not invent"))
                return rows, True
            rows.append(("GAP", "dry run: build_production_request", detail))
            return rows, False
        rows.append(("PASS", "dry run: build_production_request", ""))

        pre = subprocess.run(
            [sys.executable, str(root / "scripts" / "stage_executor.py"),
             str(tmp), "--request", str(out), "--preflight",
             "--stages", "visual-mockup", "--provider", "stub"],
            cwd=str(root), capture_output=True, text=True, timeout=120, env=_ENV)
        pre_text = pre.stdout + pre.stderr
        tail = [ln for ln in pre_text.splitlines() if ln.strip()][-3:]
        # A nonzero exit is success only for the recognised fail-closed refusal
        # for missing run/client data; argparse errors, tracebacks, missing
        # modules and unknown refusals are gaps.
        exit_verdict = classify_executor_exit(pre.returncode, pre_text)
        if exit_verdict == "gap":
            rows.append(("GAP", "dry run: stage_executor --preflight",
                         (tail[-1] if tail else f"rc={pre.returncode}")[:200]))
            return rows, False
        rows.append(("PASS", "dry run: stage_executor --preflight",
                     "" if exit_verdict == "ok"
                     else f"fail-closed rc={pre.returncode}: {tail[-1] if tail else ''}"))
        return rows, True
    except Exception as exc:                           # noqa: BLE001
        rows.append(("GAP", "dry run", f"{type(exc).__name__}: {exc}"))
        return rows, False
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def repo_only_tests(root: Path):
    """Tests that pull fixtures from the repository root cannot run here."""
    tests = root / "tests"
    if not tests.is_dir():
        return 0, 0
    total = repo_only = 0
    for path in sorted(tests.glob("test_*.py")):
        total += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if REPO_ONLY_MARKER in text or "parents[1]" in text:
            repo_only += 1
    return repo_only, total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Skill 71 installed-runtime preflight")
    ap.add_argument("--target", default=None,
                    help="installation to inspect (default: the tree holding this script)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-check", action="store_true",
                    help="test the build-failure classifier and exit")
    args = ap.parse_args(argv)
    if args.self_check:
        return self_check()

    root = Path(args.target).resolve() if args.target else skill_root_for(Path(__file__))
    rows = []
    layout_rows, layout_ok = check_layout(root)
    import_rows, import_ok = check_imports(root)
    shared_rows = check_shared(root)
    dry_rows, dry_ok = check_dry_run(root)
    rows += layout_rows + import_rows + shared_rows + dry_rows

    repo_only, total = repo_only_tests(root)
    repo_shaped = (root.parent / "scripts" / "check-skill71-parity.py").is_file()
    # A demonstrated gap keeps the verdict honest even when the exercised path
    # succeeded: the dry run need not reach a conditional dependency for that
    # dependency to be missing. verdict_is_ready is the single place that rule lives.
    ready = verdict_is_ready(layout_ok, import_ok, dry_ok, rows)

    if args.json:
        print(json.dumps({
            "target": str(root), "ready": ready,
            "rows": [{"status": s, "check": c, "detail": d} for s, c, d in rows],
            "repo_only_tests": repo_only, "tests_total": total,
            "canonical_test_command": (f"cd {Path.home()}/openclaw-onboarding/71-blackceo-signature-page"
                                       " && python3 -m pytest -q tests"),
        }, indent=2))
    else:
        print(f"Skill 71 installed-runtime preflight — target: {root}")
        for status, check, detail in rows:
            print(f"  [{status}] {check}" + (f" — {detail}" if detail else ""))
        print(f"  [{'AVAILABLE' if repo_shaped else 'NOT RUN'}] repository suite: "
              f"{repo_only} of {total} test files resolve fixtures from the repository root")
        if repo_shaped:
            print("            this tree has the repository layout; the preflight does not run them —")
            print("            command: cd ~/openclaw-onboarding/71-blackceo-signature-page "
                  "&& python3 -m pytest -q tests")
        else:
            print("            a lone-directory install cannot run them; canonical command:")
            print("            cd ~/openclaw-onboarding/71-blackceo-signature-page "
                  "&& python3 -m pytest -q tests")
        print("VERDICT:", "installed runtime ready" if ready else "installed runtime GAP")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
