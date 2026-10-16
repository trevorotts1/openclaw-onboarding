#!/usr/bin/env python3
"""Skill 80 (80-signature-upsell) package verification — S80-10.

Runs every locally provable check for this packaging candidate and exits
non-zero on ANY failure:

  1. version lockstep: skill-version.txt == SKILL.md frontmatter version
  2. validator test suite        (components/80-signature-upsell/tests)
  3. validator self-test         (scripts/validate_upsell_copy.py --self-test)
  4. page checker in place       (components/pages/check_pages.py)
  5. adapters test suite         (components/adapters/tests, incl. the
     binding wiring tests tests/test_binding_wiring.py) — staged, see below
  6. binding core test suite     (components/binding/test_binding.py) —
     staged; proves the S80-06 extra-offer binding at L1 interface level
     against the TEST-ONLY fixture driver only
  7. renderer determinism: re-render in the staged mirror and require every
     generated page file to be byte-identical to the packaged pages
  8. schema validation of the examples: every examples/*.example bundle's
     "result" against schemas/upsell-result.schema.json, and every example
     request against schemas/upsell-request.schema.json

Staging note (steps 5-7): the adapters' routing tests resolve the Signature
Launch packet by path arithmetic (their work dir's parents[2] / "packet"),
and the components resolve each other as siblings (the binding core imports
the adapters' vocabulary and guard). Verification therefore copies the four
component trees, byte-for-byte (SHA-256 compared), into a scratch mirror
with the same sibling layout at the same depth relative to the packet,
runs the suites there, and removes the mirror. If no packet is found above
this package (standalone install), the mirror is staged in a temp dir
instead and the routing differential test is reported NOT RUN — never
silently passed — while every other suite still runs in place/stage.

Nothing here touches a network, a native action, or a payment. Proof class:
L0/L1/L2 local only. The S80-06 binding is proven at interface level
(fixture) only: binding_status stays interface_conformant_pending_s06,
native_action_id stays null, and the native install via S06 plus L3/L4
remain open regardless of this script's result.

Usage: python3 verify.py
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent
CORE = SKILL / "components" / "80-signature-upsell"
ADAPTERS = SKILL / "components" / "adapters"
PAGES = SKILL / "components" / "pages"
BINDING = SKILL / "components" / "binding"
EXAMPLES = SKILL / "examples"
COMPONENTS = ("80-signature-upsell", "adapters", "pages", "binding")

failures = []
not_run = []


def run(label, cmd, cwd):
    print(f"\n=== {label}\n$ {' '.join(str(c) for c in cmd)}  (cwd={cwd})")
    r = subprocess.run([str(c) for c in cmd], cwd=cwd,
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print(out[-2500:] if out else "(no output)")
    ok = r.returncode == 0
    print(f"--- {label}: {'PASS' if ok else 'FAIL'} (exit {r.returncode})")
    if not ok:
        failures.append(label)
    return ok


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def find_packet_parent():
    for anc in SKILL.parents:
        if (anc / "packet" / "reference" / "reference_contracts.py").is_file():
            return anc
    return None


def main():
    print("Skill 80 package verification — candidate v"
          + (SKILL / "skill-version.txt").read_text().strip())

    # 1. version lockstep
    print("\n=== version lockstep (skill-version.txt vs SKILL.md)")
    txt_version = (SKILL / "skill-version.txt").read_text().strip()
    md = (SKILL / "SKILL.md").read_text()
    front = md.split("---", 2)[1]
    md_version = next((ln.split(":", 1)[1].strip() for ln in front.splitlines()
                       if ln.startswith("version:")), None)
    ok = txt_version == md_version
    print(f"skill-version.txt={txt_version}  SKILL.md version={md_version}")
    print(f"--- version lockstep: {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append("version lockstep")

    # 2. validator suite
    run("validator test suite",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"], CORE)

    # 3. validator self-test
    run("validator self-test",
        [sys.executable, "scripts/validate_upsell_copy.py", "--self-test"], CORE)

    # 4. page checker in place
    run("page checker (packaged pages)", [sys.executable, "check_pages.py"], PAGES)

    # 5-7. staged mirror for adapters + binding suites and renderer determinism
    packet_parent = find_packet_parent()
    stage_base = None
    stage_work = None
    try:
        if packet_parent is not None:
            stage_work = (packet_parent / "rooms" / "S80"
                          / ".s80-pkg-verify-stage")
            if stage_work.exists():
                shutil.rmtree(stage_work)
            stage_work.mkdir(parents=True)
            stage_base = stage_work
            print(f"\n=== staging mirror at {stage_work} "
                  f"(packet found at {packet_parent / 'packet'})")
        else:
            stage_base = Path(tempfile.mkdtemp(prefix="s80-pkg-verify-"))
            stage_work = stage_base / "rooms" / "S80" / "work"
            stage_work.mkdir(parents=True)
            print(f"\n=== staging mirror at {stage_work} "
                  "(no packet found above the package; routing differential "
                  "will be reported NOT RUN)")
        for comp in COMPONENTS:
            shutil.copytree(SKILL / "components" / comp, stage_work / comp,
                            ignore=shutil.ignore_patterns("__pycache__"))
        # staged copies must be byte-identical to the packaged components
        same = all(tree_hashes(SKILL / "components" / comp)
                   == tree_hashes(stage_work / comp) for comp in COMPONENTS)
        print(f"--- staged copies byte-identical to package: "
              f"{'PASS' if same else 'FAIL'}")
        if not same:
            failures.append("staged copy identity")

        if packet_parent is not None:
            run("adapters test suite incl. binding wiring (staged mirror)",
                [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                stage_work / "adapters")
        else:
            run("adapters test suite, non-routing modules (staged mirror)",
                [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_adapters_*.py"], stage_work / "adapters")
            run("binding wiring tests (staged mirror)",
                [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_binding_wiring.py"], stage_work / "adapters")
            not_run.append(
                "adapters routing differential tests (test_routing_state.py) "
                "— packet/reference not found above this package")

        # binding core suite: L1 interface-level proof against the
        # TEST-ONLY fixture driver; needs only the sibling adapters tree,
        # which the mirror provides, so it runs in both staging modes.
        run("binding core test suite (staged mirror)",
            [sys.executable, "-m", "unittest", "test_binding"],
            stage_work / "binding")

        # renderer determinism: regenerate in the mirror, compare to package
        run("renderer (staged mirror)",
            [sys.executable, "render_pages.py"], stage_work / "pages")
        run("page checker (staged mirror)",
            [sys.executable, "check_pages.py"], stage_work / "pages")
        pkg_pages = tree_hashes(PAGES)
        stg_pages = tree_hashes(stage_work / "pages")
        det_ok = pkg_pages == stg_pages
        print(f"--- renderer determinism (packaged pages == fresh render): "
              f"{'PASS' if det_ok else 'FAIL'}")
        if not det_ok:
            only = [k for k in set(pkg_pages) | set(stg_pages)
                    if pkg_pages.get(k) != stg_pages.get(k)]
            print("    differing files:", only[:10])
            failures.append("renderer determinism")
    finally:
        if stage_base is not None and stage_base.exists():
            shutil.rmtree(stage_base)

    # 8. schema validation of the examples
    print("\n=== schema validation of examples")
    try:
        import jsonschema
        req_schema = json.loads(
            (CORE / "schemas" / "upsell-request.schema.json").read_text())
        res_schema = json.loads(
            (CORE / "schemas" / "upsell-result.schema.json").read_text())
        req_v = jsonschema.Draft202012Validator(req_schema)
        res_v = jsonschema.Draft202012Validator(res_schema)
        checked = 0
        step_failed = False
        for f in sorted(EXAMPLES.glob("*.json")):
            doc = json.loads(f.read_text())
            if "result" in doc:  # a bundle: validate its result object
                errs = sorted(res_v.iter_errors(doc["result"]),
                              key=lambda e: e.path)
                checked += 1
                print(f"{f.name}: result vs upsell-result.schema.json — "
                      f"{'VALID' if not errs else 'INVALID: ' + str(errs[0].message)}")
                if errs:
                    failures.append(f"schema validation {f.name}")
                    step_failed = True
            else:  # an example request
                errs = sorted(req_v.iter_errors(doc), key=lambda e: e.path)
                checked += 1
                print(f"{f.name}: request vs upsell-request.schema.json — "
                      f"{'VALID' if not errs else 'INVALID: ' + str(errs[0].message)}")
                if errs:
                    failures.append(f"schema validation {f.name}")
                    step_failed = True
        print(f"--- schema validation of examples: "
              f"{'PASS' if checked and not step_failed else 'FAIL'} "
              f"({checked} documents)")
        if not checked:
            failures.append("schema validation (no example documents found)")
    except ImportError:
        failures.append("schema validation (jsonschema module unavailable)")
        print("jsonschema module unavailable — FAIL")

    print("\n================ SUMMARY ================")
    for item in not_run:
        print(f"NOT RUN: {item}")
    if failures:
        print("FAILURES:", "; ".join(failures))
        return 1
    print("ALL RUN CHECKS PASS"
          + (" (with NOT RUN items above)" if not_run else ""))
    print("Reminder: this proves L0/L1/L2 local only. S80-06 binding is "
          "built at interface level (binding_status "
          "interface_conformant_pending_s06, native_action_id null); the "
          "native install via S06 is pending S06 answers to CR-S80-001 "
          "Q1-Q6; L3/L4 not_run; screenshots not_run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
