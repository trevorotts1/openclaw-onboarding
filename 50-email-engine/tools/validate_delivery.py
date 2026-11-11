#!/usr/bin/env python3
# =============================================================================
# SKILL 50 — EMAIL ENGINE :: DELIVERY VALIDATOR  (lane receipt for Skill 83)
# -----------------------------------------------------------------------------
# Produces, and re-checks, the lane receipt Skill 83 (Black Friday launcher)
# requires before it seals an email unit as delivered:
#
#   {"state": "complete", "unit": <id>,
#    "artifacts": [{"path", "sha256", "size", "role"}],
#    "lane_validation": {"lane": "skill50", "contract": "skill50.email-delivery.v1",
#                        "state": "passed", "certificate_sha256": <sha256 of the
#                        PROCESS-CERTIFICATE.json bytes>},
#    "request": {"launch_id", "unit_id", "plan_sha256"}}
#
# Nothing here is a self-declaration. `produce` writes the receipt ONLY after
#   * the SACRED floor prover (tools/prove-email.py) passes on
#     working/copy/emails.json against the locked brief,
#   * the build plan passes run_email_engine's schema check and carries exactly
#     as many email steps as emails.json (and the launch plan's email_count),
#   * delivery/PROCESS-CERTIFICATE.json authenticates (all phases passed, the
#     public sha recomputes AND the run-scoped HMAC key verifies the signature).
# `--check` re-runs all of that from the receipt, so any drift in the staged
# bytes exits non-zero. The HMAC key is a run secret and is never staged with a
# package: when it is not beside the receipt, --check re-verifies everything
# else and says plainly that the signature was not authenticated.
#
# Stdlib only, model-free, no network, DRAFT-ONLY (it sends and installs nothing).
#
# USAGE
#   validate_delivery.py <run_dir> --launch-plan plan.json --unit <id> --out receipt.json
#   validate_delivery.py --check receipt.json [--root DIR] [--launch-plan plan.json]
#   validate_delivery.py --selftest
#
# EXIT CODES: 0 pass / 2 validation failed (fail-closed) / 3 usage or IO
# =============================================================================
"""Skill 50 email delivery validator: the producer of skill50.email-delivery.v1."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

SKILL_DIR = Path(__file__).resolve().parents[1]
PROVER = SKILL_DIR / "tools" / "prove-email.py"
ENGINE = SKILL_DIR / "run_email_engine.py"

LANE = "skill50"
CONTRACT = "skill50.email-delivery.v1"
# role -> path inside the run; the order is the receipt's artifact order.
ARTIFACTS = (
    ("build_plan", "working/deploy/build-plan.json"),
    ("emails", "working/copy/emails.json"),
    ("brief", "working/copy/brief.json"),
    ("certificate", "delivery/PROCESS-CERTIFICATE.json"),
)
KEY_REL = "working/checkpoints/.cert-hmac-key"


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    return _sha256_bytes(Path(path).read_bytes())


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _engine():
    """run_email_engine imported by path, so its P3/P4 checks are the ones reused."""
    spec = importlib.util.spec_from_file_location("_skill50_run_email_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prover_rc(emails, brief):
    proc = subprocess.run(
        [sys.executable, str(PROVER), str(emails), "--json", "--brief", str(brief)],
        capture_output=True, text=True)
    return proc.returncode


def _email_steps(plan):
    return sum(1 for key, wf in plan.items()
               if key not in ("folder", "_meta") and isinstance(wf, dict)
               for step in wf.get("templates") or []
               if isinstance(step, dict) and step.get("type") == "email")


def _resolve(root, rel):
    """A path under root, or None when it is absolute or escapes root."""
    if not isinstance(rel, str) or not rel.strip() or Path(rel).is_absolute():
        return None
    target = (Path(root) / rel).resolve()
    return target if target.is_relative_to(Path(root).resolve()) else None


def _plan_unit(plan_path, unit):
    """(plan sha256, email_count of the unit) or raise ValueError naming the defect."""
    raw = Path(plan_path).read_bytes()
    plan = json.loads(raw.decode("utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("the launch plan is not a JSON object")
    rows = [s for s in plan.get("email_sequences") or [] if isinstance(s, dict)]
    row = next((s for s in rows if s.get("id") == unit), None)
    if row is None:
        raise ValueError("unit %r is not an email_sequence of the launch plan" % unit)
    return _sha256_bytes(raw), plan.get("launch_id"), row.get("email_count")


def verify(root, receipt, launch_plan=None):
    """Every reason `receipt` does not hold against the bytes under `root`.

    Returns (failures, authenticated). Empty failures means the receipt is true."""
    fails = []
    root = Path(root)
    if not isinstance(receipt, dict):
        return ["receipt is not a JSON object"], False
    lane = receipt.get("lane_validation")
    if receipt.get("state") != "complete":
        fails.append("receipt state is not 'complete'")
    if not (isinstance(lane, dict) and lane.get("lane") == LANE
            and lane.get("contract") == CONTRACT and lane.get("state") == "passed"):
        fails.append("lane_validation is not a passed %s %s" % (LANE, CONTRACT))
        lane = lane if isinstance(lane, dict) else {}

    found = {}
    arts = receipt.get("artifacts")
    if not isinstance(arts, list) or not arts:
        fails.append("receipt carries no artifacts")
        arts = []
    for art in arts:
        if not isinstance(art, dict):
            fails.append("an artifact entry is not an object")
            continue
        target = _resolve(root, art.get("path"))
        if target is None or not target.is_file():
            fails.append("artifact %r does not resolve under the receipt root" % art.get("path"))
            continue
        data = target.read_bytes()
        if _sha256_bytes(data) != art.get("sha256"):
            fails.append("artifact %r does not match its recorded sha256" % art.get("path"))
        if art.get("size") != len(data):
            fails.append("artifact %r is %d bytes, the receipt says %r"
                         % (art.get("path"), len(data), art.get("size")))
        # Skill 83 may hand the row over without its role tag; the path names the role.
        role = art.get("role") or next((r for r, rel in ARTIFACTS if rel == art.get("path")), None)
        found[role] = target
    for role, rel in ARTIFACTS:
        if role not in found:
            fails.append("receipt has no %s artifact (%s)" % (role, rel))
    if fails:
        return fails, False

    # 1. The SACRED floor prover on the staged copy, against the locked brief.
    if _prover_rc(found["emails"], found["brief"]) != 0:
        fails.append("tools/prove-email.py refused working/copy/emails.json")

    # 2. The build plan: schema contract + exactly the emails the copy carries.
    engine = _engine()
    try:
        plan = _read_json(found["build_plan"])
        emails = _read_json(found["emails"])
    except (OSError, ValueError) as exc:
        return fails + ["build plan or emails.json unreadable: %s" % exc], False
    errs = engine._validate_build_plan(plan)
    if errs:
        fails.append("build plan violates schema/build-plan.schema.json: " + "; ".join(errs[:4]))
    n_copy = len(emails.get("emails") or []) if isinstance(emails, dict) else 0
    n_plan = _email_steps(plan) if isinstance(plan, dict) else 0
    if n_copy == 0 or n_plan != n_copy:
        fails.append("build plan has %d email step(s), emails.json has %d" % (n_plan, n_copy))

    # 3. The process certificate: bytes bound, body recomputes, signature when keyed.
    cert_bytes = found["certificate"].read_bytes()
    if _sha256_bytes(cert_bytes) != lane.get("certificate_sha256"):
        fails.append("certificate_sha256 does not match delivery/PROCESS-CERTIFICATE.json")
    try:
        cert = json.loads(cert_bytes.decode("utf-8"))
    except ValueError:
        return fails + ["PROCESS-CERTIFICATE.json is not JSON"], False
    if not isinstance(cert, dict):
        return fails + ["PROCESS-CERTIFICATE.json is not a JSON object"], False
    steps = [(s.get("phase_id"), bool(s.get("ok"))) for s in cert.get("steps") or []
             if isinstance(s, dict)]
    if cert.get("all_phases_pass") is not True:
        fails.append("certificate all_phases_pass is not true")
    if cert.get("certificate_sha") != engine._certificate_sha(
            cert.get("sequence_id", ""), cert.get("email_count", 0), steps):
        fails.append("certificate_sha does not recompute (forged or tampered)")
    if cert.get("email_count") != n_copy or (
            isinstance(emails, dict) and cert.get("sequence_id") != emails.get("sequence_id")):
        fails.append("certificate names a different sequence or email count than emails.json")
    authenticated = False
    if (root / KEY_REL).is_file():
        ok, msg = engine._verify_process_certificate(root)
        authenticated = ok
        if not ok:
            fails.append("certificate signature refused: " + msg)

    # 4. The launch plan, when the caller names it: same bytes, same unit, same count.
    req = receipt.get("request")
    if launch_plan is not None:
        try:
            sha, launch_id, want = _plan_unit(launch_plan, (req or {}).get("unit_id"))
        except (OSError, ValueError) as exc:
            return fails + ["launch plan: %s" % exc], authenticated
        if sha != (req or {}).get("plan_sha256"):
            fails.append("receipt echoes a different launch plan than the one supplied")
        if launch_id != (req or {}).get("launch_id"):
            fails.append("receipt launch_id is not the plan's")
        if isinstance(want, int) and want != n_copy:
            fails.append("launch plan expects %d email(s), the delivery has %d" % (want, n_copy))
    return fails, authenticated


def produce(run_dir, launch_plan, unit, out):
    """Write the receipt, or raise ValueError with every reason it cannot be true."""
    run_dir = Path(run_dir)
    sha, launch_id, _want = _plan_unit(launch_plan, unit)
    artifacts = []
    for role, rel in ARTIFACTS:
        target = run_dir / rel
        if not target.is_file():
            raise ValueError("missing %s (%s)" % (role, rel))
        data = target.read_bytes()
        artifacts.append({"path": rel, "sha256": _sha256_bytes(data), "size": len(data),
                          "role": role})
    receipt = {
        "state": "complete",
        "unit": unit,
        "artifacts": artifacts,
        "lane_validation": {
            "lane": LANE, "contract": CONTRACT, "state": "passed",
            "certificate_sha256": next(a["sha256"] for a in artifacts if a["role"] == "certificate"),
        },
        "request": {"launch_id": launch_id, "unit_id": unit, "plan_sha256": sha},
    }
    fails, authenticated = verify(run_dir, receipt, launch_plan)
    if not authenticated and not fails:
        fails.append("the certificate signature could not be authenticated: the run key "
                     "%s is not in %s" % (KEY_REL, run_dir.name))
    if fails:
        raise ValueError("; ".join(fails))
    Path(out).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def _selftest():
    import shutil
    import tempfile
    golden = SKILL_DIR / "examples" / "golden-landing-10"
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run"
        shutil.copytree(golden, run)
        plan = Path(td) / "plan.json"
        plan.write_text(json.dumps({"launch_id": "selftest", "email_sequences": [
            {"id": "email_selftest", "email_count": 10}]}))
        out = run / "receipt.json"
        produce(run, plan, "email_selftest", out)
        fails, authed = verify(run, _read_json(out), plan)
        assert not fails and authed, (fails, authed)
        (run / "working/copy/emails.json").write_text("{}")
        fails, _ = verify(run, _read_json(out), plan)
        assert fails, "a tampered emails.json was accepted"
    print("selftest ok")
    return EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 50 email delivery validator.")
    ap.add_argument("run_dir", nargs="?", help="the email run directory (contains working/)")
    ap.add_argument("--launch-plan", help="the shared launch plan (names the email_sequence unit)")
    ap.add_argument("--unit", help="the launch plan email_sequence id this run delivers")
    ap.add_argument("--out", help="where to write the receipt")
    ap.add_argument("--check", metavar="RECEIPT", help="re-verify an existing receipt")
    ap.add_argument("--root", help="--check: the directory the receipt's artifact paths are "
                                   "relative to (default: the receipt's own directory)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.check:
        receipt_path = Path(args.check)
        try:
            receipt = _read_json(receipt_path)
        except (OSError, ValueError) as exc:
            print("validate_delivery: cannot read %s: %s" % (receipt_path, exc), file=sys.stderr)
            return EXIT_USAGE
        root = Path(args.root) if args.root else receipt_path.resolve().parent
        fails, authed = verify(root, receipt, args.launch_plan)
        print(json.dumps({"ok": not fails, "failures": fails, "signature_authenticated": authed},
                         indent=2))
        if not fails and not authed:
            print("validate_delivery: content re-verified; the certificate signature was NOT "
                  "authenticated (the run key is not beside the receipt)", file=sys.stderr)
        return EXIT_OK if not fails else EXIT_FAIL
    if not (args.run_dir and args.launch_plan and args.unit and args.out):
        ap.error("produce needs <run_dir> --launch-plan --unit --out (or use --check / --selftest)")
    try:
        produce(args.run_dir, args.launch_plan, args.unit, args.out)
    except (OSError, ValueError) as exc:
        print("validate_delivery: REFUSED: %s" % exc, file=sys.stderr)
        return EXIT_FAIL
    print("validate_delivery: receipt written to %s" % args.out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
