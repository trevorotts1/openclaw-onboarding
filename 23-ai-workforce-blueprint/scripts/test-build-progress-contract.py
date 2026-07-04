#!/usr/bin/env python3
"""
Issue #9 — onboarding "building" progress contract test.

Proves the producer (build-workforce.write_build_progress) emits a
build-progress.json that the Command Center consumer can render:

  producer:  23-ai-workforce-blueprint/scripts/build-workforce.py
             -> COMPANY_DIR/build-progress.json
  route:     command-center/src/app/api/onboarding/build-status/route.ts
             (scans <ZHC_ROOT>/<company>/build-progress.json, returns it as-is)
  page:      command-center/src/app/onboarding/building/page.tsx
             (renders progress.stage / documents_* / departments[] / eta_minutes)

This test:
  1. drives write_build_progress across the real build lifecycle
     (manifest -> departments -> roles -> assembly -> qc -> complete),
  2. re-implements the route's exact directory scan to CONSUME the file,
  3. asserts every field the page.tsx interface accesses is present + typed,
  4. asserts the terminal emit is stage="complete" with documents fully done.

Run:  python3 test-build-progress-contract.py   (exit 0 = PASS)
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Field/type contract the page.tsx BuildProgress interface depends on.
VALID_STAGES = {
    "idle", "manifest", "research", "departments",
    "roles", "qc", "assembly", "complete",
}
VALID_DEPT_STATUS = {"pending", "in_progress", "complete"}

_failures = []


def check(cond, msg):
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        _failures.append(msg)


def load_producer():
    spec = importlib.util.spec_from_file_location(
        "bw_under_test", os.path.join(HERE, "build-workforce.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def route_scan(zhc_root):
    """Re-implementation of route.ts findActiveBuildProgress() scan semantics:
    scan <zhc_root>/<entry>/build-progress.json, return the first that parses."""
    if not os.path.isdir(zhc_root):
        return None
    for entry in sorted(os.listdir(zhc_root)):
        pf = os.path.join(zhc_root, entry, "build-progress.json")
        if os.path.isfile(pf):
            try:
                with open(pf) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
    return None


def assert_page_contract(progress, label):
    """Assert every field page.tsx reads is present with the right type."""
    check(isinstance(progress, dict), f"[{label}] progress is an object")
    check(progress.get("stage") in VALID_STAGES,
          f"[{label}] stage '{progress.get('stage')}' is a valid BuildProgress stage")
    check(isinstance(progress.get("message"), str) and progress["message"],
          f"[{label}] message is a non-empty string")
    check(isinstance(progress.get("documents_total"), int),
          f"[{label}] documents_total is an int")
    check(isinstance(progress.get("documents_complete"), int),
          f"[{label}] documents_complete is an int")
    check(isinstance(progress.get("eta_minutes"), int),
          f"[{label}] eta_minutes is an int")
    depts = progress.get("departments")
    check(isinstance(depts, list), f"[{label}] departments is a list")
    for d in depts or []:
        check(isinstance(d.get("name"), str) and d["name"],
              f"[{label}] dept.name present ({d.get('name')})")
        check(isinstance(d.get("roles_total"), int),
              f"[{label}] dept.roles_total is an int ({d.get('name')})")
        check(isinstance(d.get("roles_complete"), int),
              f"[{label}] dept.roles_complete is an int ({d.get('name')})")
        check(d.get("status") in VALID_DEPT_STATUS,
              f"[{label}] dept.status valid ({d.get('name')}={d.get('status')})")
    # page.tsx computes pct = documents_complete/documents_total; guard divide path.
    if progress.get("documents_total", 0) > 0:
        check(0 <= progress["documents_complete"] <= progress["documents_total"],
              f"[{label}] documents_complete within [0, total]")


def main():
    bw = load_producer()

    with tempfile.TemporaryDirectory() as zhc_root:
        slug = "acme-widgets"
        company_dir = os.path.join(zhc_root, slug)
        os.makedirs(company_dir, exist_ok=True)
        # Point the producer at our temp company folder.
        bw.COMPANY_DIR = company_dir

        started = "2026-07-03T10:00:00"
        depts = [
            {"id": "operations", "name": "Operations",
             "roles_total": 4, "roles_complete": 0, "status": "pending"},
            {"id": "billing-finance", "name": "Billing & Finance",
             "roles_total": 3, "roles_complete": 0, "status": "pending"},
        ]
        docs_total = sum(d["roles_total"] for d in depts)

        print("[1] manifest stage")
        bw.write_build_progress("manifest", "Writing your workforce manifest...",
                                eta_minutes=8, started_at=started)
        assert_page_contract(route_scan(zhc_root), "manifest")

        print("[2] departments stage")
        bw.write_build_progress("departments", "Building 2 departments...",
                                departments=depts, documents_total=docs_total,
                                documents_complete=0, eta_minutes=4,
                                started_at=started)
        p = route_scan(zhc_root)
        assert_page_contract(p, "departments")
        check(p["documents_total"] == docs_total,
              "departments documents_total derived from dept roles_total")

        print("[3] roles stage (incremental completion)")
        done = 0
        for d in depts:
            d["status"] = "in_progress"
            bw.write_build_progress("roles", f"Generating roles for {d['name']}...",
                                    departments=depts, documents_total=docs_total,
                                    documents_complete=done, eta_minutes=3,
                                    started_at=started)
            d["roles_complete"] = d["roles_total"]
            d["status"] = "complete"
            done += d["roles_total"]
            bw.write_build_progress("roles", f"Completed {d['name']}",
                                    departments=depts, documents_total=docs_total,
                                    documents_complete=done, eta_minutes=2,
                                    started_at=started)
            assert_page_contract(route_scan(zhc_root), f"roles:{d['id']}")
        check(done == docs_total, "roles stage completes all documents")

        print("[4] assembly + qc stages")
        bw.write_build_progress("assembly", "Assembling org chart...",
                                departments=depts, documents_total=docs_total,
                                documents_complete=done, eta_minutes=3,
                                started_at=started)
        assert_page_contract(route_scan(zhc_root), "assembly")
        bw.write_build_progress("qc", "Quality reviewing every document...",
                                departments=depts, documents_total=docs_total,
                                documents_complete=done, eta_minutes=5,
                                started_at=started)
        assert_page_contract(route_scan(zhc_root), "qc")

        print("[5] complete stage (terminal)")
        bw.write_build_progress("complete", "Your AI workforce is ready ✓",
                                departments=depts, documents_total=docs_total,
                                documents_complete=docs_total, eta_minutes=0,
                                started_at=started,
                                completed_at="2026-07-03T10:30:00")
        final = route_scan(zhc_root)
        assert_page_contract(final, "complete")
        check(final["stage"] == "complete",
              "terminal emit stage == 'complete' (page stops polling + shows CTA)")
        check(final["documents_complete"] == final["documents_total"],
              "complete: documents_complete == documents_total (100%)")
        check(final.get("completed_at"), "complete: completed_at timestamp present")
        check(all(d["status"] == "complete" for d in final["departments"]),
              "complete: every department marked complete")

        print("[6] atomic write leaves no .tmp turd")
        check(not os.path.exists(os.path.join(company_dir, "build-progress.json.tmp")),
              "no stray build-progress.json.tmp after atomic replace")

        print("[7] COMPANY_DIR unset is a safe no-op (never raises)")
        bw.COMPANY_DIR = None
        try:
            bw.write_build_progress("manifest", "noop")
            check(True, "write_build_progress no-ops when COMPANY_DIR is unset")
        except Exception as e:  # noqa: BLE001
            check(False, f"write_build_progress raised with COMPANY_DIR unset: {e}")

    print()
    if _failures:
        print(f"RESULT: FAIL — {len(_failures)} check(s) failed")
        return 1
    print("RESULT: PASS — producer emits a page-consumable build-progress contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
