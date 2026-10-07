#!/usr/bin/env python3
"""Provenance closure: every required provenance record exists, parses,
says what it must say, and the writer/verifier pair actually discriminates.

Three parts:

  records     the standing provenance set for this build — artifact
              provenance contract, delivery provenance writer, run-level
              campaign provenance + receipts, receipt reconciliation,
              merge provenance (all four landed merges), donor/repo/provider
              planning provenance, third-party notices in both
              distributions, and the recorded QC verdicts of the accepted
              W3 units. Each row carries path + sha256 so the receipt
              pins the exact bytes judged.

  controls    live round-trip against core/delivery_variants/manifests.py
              in private scratch (/tmp/<operator-slug>-W4-05-U1-prov-*):
                A write_provenance -> verify_binding must return ok=True
                B manifest byte tamper  -> verify_binding must refuse
                C artifact byte tamper  -> verify_binding must refuse
              B and C are negative controls: a verifier that says PASS to
              them is broken, so a green A alone proves nothing.

  verdict     PASS only when every record is present+valid and all three
              controls behave. Receipt: receipts/provenance-closure.json
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from lib import (EXIT_FAIL, EXIT_TOOLING, ROOT, ToolingError, finish,
                 read_json, sha256_file, utcnow)

sys.path.insert(0, str(ROOT))
try:
    from core.delivery_variants import manifests as delivery
except Exception as exc:  # import failure is tooling, not a target fact
    raise SystemExit("TOOLING: cannot import core.delivery_variants: %s" % exc)

SCRATCH_PREFIX = "/tmp/<operator-slug>-W4-05-U1-prov"

EXPECTED_MERGE_ROWS = 4
SHORT_RUN_ID = "w3-04-short-run"


def _record(record_id: str, rel_path: str, checks) -> dict:
    """checks: list of (label, ok, detail). Presence checked first."""
    path = ROOT / rel_path
    row = {"id": record_id, "path": rel_path, "present": path.exists()}
    row["checks"] = []
    if not path.is_file() and not path.is_dir():
        row["checks"].append({"check": "present", "ok": False,
                              "detail": "missing on disk"})
        row["ok"] = False
        return row
    row["kind"] = "dir" if path.is_dir() else "file"
    if path.is_file():
        row["sha256"] = sha256_file(path)
        row["bytes"] = path.stat().st_size
    for label, ok, detail in checks(path):
        row["checks"].append({"check": label, "ok": bool(ok),
                              "detail": detail})
    row["ok"] = all(c["ok"] for c in row["checks"])
    return row


def _parse_json(path: Path):
    try:
        return read_json(path), None
    except Exception as exc:
        return None, str(exc)


def records() -> list:
    out = []

    # --- contract level -------------------------------------------------
    def schema_checks(path):
        data, err = _parse_json(path)
        if err:
            return [("json-parses", False, err)]
        prov = (data.get("properties") or {}).get("provenance") or {}
        fields = sorted((prov.get("properties") or {}).keys())
        need = {"model", "provider", "receipt_path", "task_id"}
        return [
            ("json-parses", True, "schema_version=%s"
             % data.get("schema_version")),
            ("provenance-field-contract", need.issubset(set(fields)),
             "provenance fields=%s" % fields),
            ("hash-required", "sha256" in (data.get("required") or []),
             "required=%s" % data.get("required")),
        ]

    out.append(_record("artifact-provenance-contract",
                       "core/contracts/artifact-schema.json", schema_checks))

    def writer_checks(path):
        text = path.read_text(encoding="utf-8", errors="replace")
        return [
            ("write_provenance-defined", "def write_provenance(" in text, ""),
            ("verify_binding-defined", "def verify_binding(" in text, ""),
            ("pins-manifest-and-cost-hash",
             "campaign_manifest_sha256" in text and
             "cost_report_sha256" in text, ""),
        ]

    out.append(_record("delivery-provenance-writer",
                       "core/delivery_variants/manifests.py", writer_checks))

    # --- run-level provenance (accepted W3-04 short run) ----------------
    def campaign_prov_checks(path):
        data, err = _parse_json(path)
        if err:
            return [("json-parses", False, err)]
        return [
            ("json-parses", True, ""),
            ("campaign-id", data.get("campaign_id") == SHORT_RUN_ID,
             "campaign_id=%s" % data.get("campaign_id")),
            ("authorization-digest-recorded",
             bool(data.get("auth_scope_digest")),
             "auth_scope_digest=%s" % data.get("auth_scope_digest")),
            ("authorization-source-recorded", bool(data.get("source")), ""),
        ]

    out.append(_record("run-campaign-provenance",
                       "qualification/short-run/campaign-provenance.json",
                       campaign_prov_checks))

    def receipts_checks(path):
        data, err = _parse_json(path)
        if err:
            return [("json-parses", False, err)]
        jobs = data.get("jobs")
        return [
            ("json-parses", True, ""),
            ("run-id", data.get("run_id") == SHORT_RUN_ID,
             "run_id=%s" % data.get("run_id")),
            ("ceiling-recorded", isinstance(data.get("ceiling"), int),
             "ceiling=%s" % data.get("ceiling")),
            ("jobs-recorded", isinstance(jobs, list) and len(jobs) > 0,
             "jobs=%d" % (len(jobs) if isinstance(jobs, list) else -1)),
            ("db-receipts-recorded", "db_receipts" in data, ""),
        ]

    out.append(_record("run-receipts-record",
                       "qualification/short-run/08-receipts.json",
                       receipts_checks))

    def recon_checks(path):
        files = sorted(p for p in path.iterdir() if p.suffix == ".json")
        bad = []
        for f in files:
            _, err = _parse_json(f)
            if err:
                bad.append("%s: %s" % (f.name, err))
        return [
            ("at-least-one-reconciliation", len(files) >= 1,
             "%d json files" % len(files)),
            ("all-json-parses", not bad, "; ".join(bad) or "all parse"),
        ]

    out.append(_record("receipt-reconciliation-set",
                       "qualification/short-run-receipts", recon_checks))

    def merge_checks(path):
        data, err = _parse_json(path)
        if err:
            return [("json-parses", False, err)]
        if not isinstance(data, list):
            return [("json-parses", True, "expected list")]
        unproven = [r.get("unit") for r in data
                    if not (r.get("proven") and r.get("commit")
                            and r.get("remote_main"))]
        return [
            ("json-parses", True, ""),
            ("row-count", len(data) == EXPECTED_MERGE_ROWS,
             "%d rows" % len(data)),
            ("every-row-fetched-ancestry-proven", not unproven,
             "unproven=%s" % unproven or "all rows proven"),
        ]

    out.append(_record("merge-provenance", "qualification/merge-receipts.json",
                       merge_checks))

    # --- donor / repo / provider planning provenance --------------------
    def text_checks(path, *needles):
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [n for n in needles if n not in text]
        return [
            ("non-empty", path.stat().st_size > 0,
             "%d bytes" % path.stat().st_size),
            ("contains-required-markers", not missing,
             "missing=%s" % missing or "all markers"),
        ]

    out.append(_record("donor-license-provenance", "planning/donor-selections.md",
                       lambda p: text_checks(p, "License", "MIT")))
    out.append(_record("repo-ci-ownership-provenance",
                       "planning/repo-ownership.md",
                       lambda p: text_checks(p, "CI guards", "origin/main")))
    out.append(_record("provider-contract-provenance",
                       "planning/provider-contracts.md",
                       lambda p: text_checks(p, "KIE")))
    out.append(_record("runtime-readiness-provenance",
                       "planning/runtime-readiness.md",
                       lambda p: text_checks(p, "MIT")))

    # --- third-party notices, both distributions ------------------------
    for rid, rel in (
        ("notices-scaffold", "core/release_scaffolds/THIRD_PARTY_NOTICES.md"),
        ("notices-999-distribution", "999-setup/THIRD_PARTY_NOTICES.md"),
        ("notices-onboarding-distribution",
         "onboarding/75-drama-song-ad-factory/THIRD_PARTY_NOTICES.md"),
    ):
        out.append(_record(rid, rel,
                           lambda p: text_checks(p, "License")))

    # --- recorded QC verdicts (provenance of the accepted W3 evidence) ---
    def verdict_checks(path):
        data, err = _parse_json(path)
        if err:
            return [("json-parses", False, err)]
        return [
            ("json-parses", True, ""),
            ("verdict-PASS", data.get("verdict") == "PASS",
             "verdict=%s" % data.get("verdict")),
            ("unit-recorded", bool(data.get("unit_id")),
             "unit_id=%s" % data.get("unit_id")),
            ("models-recorded", bool(data.get("builder_model"))
             and bool(data.get("reviewer_model")),
             "builder=%s reviewer=%s" % (data.get("builder_model"),
                                         data.get("reviewer_model"))),
        ]

    for rel in ("evidence/W3-04/W3-04-U1.verdict.json",
                "evidence/W3-04/W3-04-U2.verdict.json",
                "evidence/W3-06/W3-06-U1.verdict.json"):
        out.append(_record("qc-verdict-" + Path(rel).stem, rel, verdict_checks))

    return out


def controls() -> list:
    """A: round-trip green; B/C: tamper must be refused (negative controls)."""
    results = []
    scratch = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX + "-"))
    try:
        artifact = scratch / "artifact.json"
        artifact.write_text('{"probe":"w4-05-provenance-control"}\n',
                            encoding="utf-8")
        good_hash = sha256_file(artifact)

        manifest = delivery.write_campaign_manifest(
            scratch / "campaign-manifest.json",
            campaign_id="w4-05-prov-control", run_id="w4-05-prov-control",
            artifacts=[{"artifact_id": "probe", "kind": "json",
                        "path": "artifact.json", "file": "artifact.json"}],
            artifact_root=scratch)
        report = delivery.write_cost_report(
            scratch / "cost-report.json", run_id="w4-05-prov-control",
            estimated_cost=0, committed_cost=0, actual_cost=0,
            remaining_budget=0)
        prov_path = scratch / "provenance.json"
        delivery.write_provenance(
            prov_path, run_id="w4-05-prov-control",
            campaign_manifest_sha256=manifest["sha256"],
            cost_report_sha256=report["sha256"],
            artifact_hashes={"probe": good_hash})

        ok, details = delivery.verify_binding(
            scratch / "campaign-manifest.json",
            prov_path, scratch / "cost-report.json", artifact_root=scratch)
        results.append({"control": "A-roundtrip",
                        "expect": "verify_binding ok=True", "got": ok,
                        "ok": bool(ok is True),
                        "details": {k: details.get(k)
                                    for k in ("manifest_match",
                                              "cost_report_match")}})

        # B: flip one byte of the manifest after the hash was pinned.
        manifest_path = scratch / "campaign-manifest.json"
        original = manifest_path.read_bytes()
        manifest_path.write_bytes(original[:-2] + b" }")
        ok_b, det_b = delivery.verify_binding(
            manifest_path, prov_path, scratch / "cost-report.json",
            artifact_root=scratch)
        results.append({"control": "B-manifest-tamper",
                        "expect": "verify_binding ok=False", "got": ok_b,
                        "ok": bool(ok_b) is False,
                        "details": {"manifest_match":
                                    det_b.get("manifest_match")}})
        manifest_path.write_bytes(original)

        # C: flip the artifact bytes after they were bound.
        artifact.write_text('{"probe":"TAMPERED"}\n', encoding="utf-8")
        ok_c, det_c = delivery.verify_binding(
            manifest_path, prov_path, scratch / "cost-report.json",
            artifact_root=scratch)
        art = (det_c.get("artifacts") or {}).get("probe")
        results.append({"control": "C-artifact-tamper",
                        "expect": "verify_binding ok=False + artifact mismatch",
                        "got": ok_c,
                        "ok": bool(ok_c) is False and art is False,
                        "details": {"artifact_probe": art,
                                    "manifest_match":
                                        det_c.get("manifest_match")}})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results


def main() -> int:
    recs = records()
    ctrls = controls()

    bad_recs = [r for r in recs if not r["ok"]]
    bad_ctrls = [c for c in ctrls if not c["ok"]]
    verdict = "PASS" if not bad_recs and not bad_ctrls else "FAIL"

    summary = [
        ["provenance records complete",
         "PASS" if not bad_recs else "FAIL",
         "%d/%d records valid" % (len(recs) - len(bad_recs), len(recs))],
        ["record failures", "PASS" if not bad_recs else "FAIL",
         ", ".join(r["id"] for r in bad_recs) or "none"],
        ["roundtrip control A", "PASS" if ctrls[0]["ok"] else "FAIL",
         "ok=%s" % ctrls[0]["got"]],
        ["negative control B (manifest tamper)",
         "PASS" if ctrls[1]["ok"] else "FAIL",
         "refused=%s" % (not ctrls[1]["got"])],
        ["negative control C (artifact tamper)",
         "PASS" if ctrls[2]["ok"] else "FAIL",
         "refused=%s" % (not ctrls[2]["got"])],
    ]

    receipt = {
        "receipt_name": "provenance-closure.json",
        "schema": "blackceo.ci-provenance/provenance-closure/v1",
        "unit_id": "W4-05-U1",
        "root": str(ROOT),
        "generated_at": utcnow(),
        "records": recs,
        "controls": ctrls,
        "counts": {"records": len(recs),
                   "records_ok": len(recs) - len(bad_recs),
                   "controls": len(ctrls),
                   "controls_ok": len(ctrls) - len(bad_ctrls)},
    }
    return finish(verdict, summary, receipt)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ToolingError as exc:
        print("TOOLING FAILURE (exit 2): %s" % exc)
        raise SystemExit(EXIT_TOOLING)
