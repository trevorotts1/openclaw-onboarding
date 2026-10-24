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
    0  installed runtime is ready: layout, imports, local assets and the
       representative dry run passed, and no demonstrated dependency is missing
    1  a runtime gap was demonstrated: something a production script needs is
       missing or fails
    2  the preflight could not complete a section (named in the output)

A demonstrated gap is fatal to the verdict even when the exercised path never
reached it — a dependency does not stop being missing because this run did not
call it. Optional imaging/render capabilities are reported SKIP, matching
`verify.sh --capabilities`, and never flip the verdict.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
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


def skill_root_for(script: Path) -> Path:
    return script.resolve().parents[1]


def check_layout(root: Path):
    rows, ok = [], True
    for rel in REQUIRED_LOCAL:
        present = (root / rel).is_file()
        rows.append(("PASS" if present else "FAIL", f"asset {rel}",
                     "" if present else "missing"))
        ok = ok and present
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


def classify_build_failure(text: str) -> str:
    """'gap', 'refused' or 'error' for a failed build_production_request run.

    build_production_request prints REFUSED for OSError too, and OSError
    includes a missing packaged file. A packaging break must never be read as a
    polite refusal, so the file/module signature is tested first and wins.
    """
    if any(tok in text for tok in PACKAGING_TOKENS):
        return "gap"
    if "REFUSED" in text:
        return "refused"
    return "gap"


def self_check() -> int:
    cases = (
        ("REFUSED: brand colors unresolved, no image stage may start. Ask the client", "refused"),
        ("REFUSED: [Errno 2] No such file or directory: 'references/planted.md'", "gap"),
        ("REFUSED: ModuleNotFoundError: No module named 'jsonschema'", "gap"),
        ("Traceback (most recent call last): ValueError: boom", "gap"),
    )
    bad = [(t, want, classify_build_failure(t)) for t, want in cases
           if classify_build_failure(t) != want]
    for text, want, got in bad:
        print(f"  [FAIL] classify {text[:60]!r}: want {want}, got {got}")
    if bad:
        print("SELF-CHECK FAIL")
        return 1
    print(f"SELF-CHECK PASS — {len(cases)} build-failure classifications")
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
            verdict = classify_build_failure(build_text)
            if verdict == "gap":
                rows.append(("GAP", "dry run: build_production_request", detail))
                return rows, False
            if verdict == "refused":
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
        tail = [ln for ln in (pre.stdout + pre.stderr).splitlines() if ln.strip()][-3:]
        # A preflight that fails closed on the request's own content is a correct
        # runtime: the modules loaded and resolved their assets. A traceback that
        # names a missing file is the gap we are looking for.
        missing = [ln for ln in tail if "No such file" in ln or "ModuleNotFoundError" in ln]
        if missing:
            rows.append(("GAP", "dry run: stage_executor --preflight", missing[-1]))
            return rows, False
        rows.append(("PASS", "dry run: stage_executor --preflight",
                     "" if pre.returncode == 0 else f"fail-closed rc={pre.returncode}: {tail[-1] if tail else ''}"))
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
    gaps = [r for r in rows if r[0] in ("GAP", "FAIL")]
    # A demonstrated gap keeps the verdict honest even when the exercised path
    # succeeded: the dry run need not reach a conditional dependency for that
    # dependency to be missing.
    ready = layout_ok and import_ok and dry_ok and not gaps

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
