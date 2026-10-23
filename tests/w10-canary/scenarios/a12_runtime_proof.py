#!/usr/bin/env python3
"""a12_runtime_proof.py — acceptance row A12 (weight 10).

Contract, quoted from work/S75-FINISH-MERGE/A-ROW-RUNBOOK.md row A12:
    harness = canaries plus the runtime proof
    record --manifest <clean-install manifest>
    check  --manifest <clean-install manifest> --side installed
    sides: onboarding_skill, nine_skill
    evidence: loaded-source proof on both distributions plus the distribution
    manifest hashes

Interface reconciliation (deliberate, stated, not silent):
  * A "clean-install manifest" is what clean_install_canary.py writes:
    schema blackceo.skill75.distribution-manifest/v1, carrying
    files: {rel: sha256}, manifest_sha256, file_count, installed_path, source.
  * The pre-landing scratch tool took `record --onb-root/--nine-root` and read
    its own ["manifest"][side] shape. It cannot consume a clean-install manifest
    at all, and canary_common.loaded_source_proof already names
    `record --manifest M --root R`. The runbook and the repo helper win, so this
    landing implements --manifest/--root and drops the incomparable interface.
  * `--side installed` derives the side from the manifest's own `distribution`
    field. The two named sides are accepted explicitly; a name that disagrees
    with the manifest is refused rather than silently relabelled.

`installer_rc` is never read as a pass signal. Every verdict comes from
recomputing sha256 over the installed tree and over the manifest's own digest.

Modes:
  record --manifest M [--manifest M ...] [--root R] [--out P]
      Recompute the loaded-source proof per distribution and record the
      distribution manifest hashes. A directory argument is expanded over
      clean-install-*.manifest.json. `--root` names one installed tree and is
      therefore valid only with a single manifest.
  check --manifest M --side installed|onboarding_skill|nine_skill [--tree R]
      Exit 1 on any mismatch, missing file, extra file, or manifest whose own
      digest does not match its file map. Exit 0 only when every compared file
      agrees.
  selftest
      Prove the tool can fail: correct manifest passes, an altered installed
      file fails, an altered manifest digest fails, a one-file placeholder is
      refused, and an installer_rc of 0 over a broken tree still fails.

Stdlib only. No network, no process execution, no writes outside --out and a
scratch directory. Exit codes: 0 assertions held, 1 a check failed, 2 tooling.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canary_common as cc  # noqa: E402

ROW = "A12"
WEIGHT = 10
SCHEMA = "blackceo.skill75.a12-runtime-proof/v1"
MANIFEST_SCHEMA = "blackceo.skill75.distribution-manifest/v1"
MANIFEST_GLOB = "clean-install-*.manifest.json"
SIDE_TO_DIST = {"onboarding_skill": "onboarding", "nine_skill": "999"}
DIST_TO_SIDE = {v: k for k, v in SIDE_TO_DIST.items()}
SIDES = ("onboarding_skill", "nine_skill")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REPO_ROOT = Path(__file__).resolve().parents[3]
try:
    SELF_REL = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
except ValueError:                                    # copied outside the repo
    SELF_REL = Path(__file__).name

INSTALLER_RC_POLICY = {
    "used_as_pass_signal": False,
    "note": ("installer_rc is recorded by the installer run, never consumed "
             "here. A zero return code cannot make a missing or modified file "
             "agree with the manifest."),
}


class ToolError(Exception):
    """Tooling/refusal condition: exit 2, never a pass and never a content red."""


def load_manifest(path):
    p = Path(path)
    if not p.is_file():
        raise ToolError("manifest not found: %s" % p)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError("manifest unreadable: %s (%s)" % (p, exc))
    if not isinstance(doc, dict):
        raise ToolError("manifest is not a JSON object: %s" % p)
    return p, doc


def manifest_files(doc, path):
    schema = doc.get("schema")
    if schema and schema != MANIFEST_SCHEMA:
        raise ToolError("%s: schema %r is not %r — not a clean-install manifest"
                        % (path, schema, MANIFEST_SCHEMA))
    files = doc.get("files")
    if not isinstance(files, dict) or not files:
        raise ToolError("%s: manifest has no files — an empty or placeholder "
                        "manifest is refused" % path)
    bad = sorted(k for k, v in files.items() if not SHA256_RE.match(str(v)))
    if bad:
        raise ToolError("%s: %d entr(y/ies) carry a non-sha256 digest, e.g. %s"
                        % (path, len(bad), bad[:3]))
    if len(files) < cc.MIN_SKILL_FILES:
        raise ToolError("%s: manifest has %d file(s), below the %d a Skill 75 "
                        "install ships — refusing a placeholder manifest"
                        % (path, len(files), cc.MIN_SKILL_FILES))
    for top in cc.REQUIRED_SKILL_TOP_LEVEL:
        if not any(k == top or k.startswith(top + "/") for k in files):
            raise ToolError("%s: manifest is missing the required top-level "
                            "path %r" % (path, top))
    return files


def resolve_side(side, doc, path):
    dist = doc.get("distribution")
    if side == "installed":
        if dist not in DIST_TO_SIDE:
            raise ToolError("%s: distribution %r is not one of %s — --side "
                            "installed cannot derive a side"
                            % (path, dist, sorted(DIST_TO_SIDE)))
        return DIST_TO_SIDE[dist]
    want = SIDE_TO_DIST.get(side)
    if want is None:
        raise ToolError("unknown side %r (expected installed, %s)"
                        % (side, ", ".join(SIDES)))
    if dist and dist != want:
        raise ToolError("%s: --side %s expects distribution %r but the manifest "
                        "says %r" % (path, side, want, dist))
    return side


def expand_manifests(arg):
    p = Path(arg)
    if p.is_dir():
        found = sorted(p.glob(MANIFEST_GLOB))
        if not found:
            raise ToolError("no %s under %s" % (MANIFEST_GLOB, p))
        return found
    return [p]


def prove_manifest(manifest_path, tree=None, side=None):
    """Recompute the loaded-source proof and the distribution manifest hash.

    Returns a dict. `ok` is True only when the manifest's own digest matches
    its file map AND every file in the installed tree agrees with the manifest.
    """
    p, doc = load_manifest(manifest_path)
    files = manifest_files(doc, p)
    side = resolve_side(side or "installed", doc, p)

    declared = doc.get("manifest_sha256")
    recomputed = cc.manifest_digest(files)
    problems = []
    if not declared:
        problems.append("manifest_sha256 missing — the distribution manifest "
                        "hash is required evidence")
    elif declared != recomputed:
        problems.append("manifest_sha256 %s != recomputed %s (the manifest does "
                        "not match its own file map)"
                        % (str(declared)[:12], recomputed[:12]))
    count = doc.get("file_count")
    if isinstance(count, int) and count != len(files):
        problems.append("file_count %d != %d file entries" % (count, len(files)))

    root = Path(tree) if tree else Path(doc.get("installed_path") or "")
    proof = {"ok": False, "detail": "not run", "command": None}
    if not str(root):
        problems.append("manifest records no installed_path and no --root/--tree "
                        "was given")
    elif not root.is_dir():
        problems.append("installed tree not found: %s" % root)
    else:
        ok, vproblems = cc.verify_manifest(root, files)
        if not ok:
            problems.extend(vproblems)
        proof_ok, proof_detail, proof_cmd = cc.loaded_source_proof(
            p, root, runtime_proof=SELF_REL)
        proof = {"ok": bool(proof_ok), "detail": proof_detail,
                 "command": proof_cmd}
        if proof_ok and problems:
            # the digests can agree while the manifest's own hash does not
            proof["detail"] = ("file digests agree; manifest integrity: "
                               + "; ".join(problems[:3]))
            proof["ok"] = False

    return {
        "side": side,
        "distribution": doc.get("distribution"),
        "manifest_path": str(p),
        "manifest_schema": doc.get("schema"),
        "file_count": len(files),
        "distribution_manifest": {
            "declared_sha256": declared,
            "recomputed_sha256": recomputed,
            "agrees": bool(declared) and declared == recomputed,
        },
        "installed_path": str(root) if str(root) else None,
        "source": doc.get("source"),
        "loaded_source_proof": proof,
        "problems": problems,
        "ok": not problems and bool(proof["ok"]),
    }


def default_out(manifests, out_arg):
    if out_arg:
        p = Path(out_arg)
        if p.suffix == ".json":
            return p
        return p / "a12-runtime-proof.receipt.json"
    return manifests[0].parent / "a12-runtime-proof.receipt.json"


def receipt_base(mode):
    return {
        "schema": SCHEMA,
        "row": ROW,
        "weight": WEIGHT,
        "mode": mode,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "harness": {"path": SELF_REL, "sha256": cc.sha256_file(__file__)},
        "sides_expected": list(SIDES),
        "installer_rc": dict(INSTALLER_RC_POLICY),
    }


def cmd_record(args):
    manifests = []
    for arg in args.manifest:
        manifests.extend(expand_manifests(arg))
    if args.root and len(manifests) != 1:
        raise ToolError("--root names one installed tree; pass one --manifest "
                        "or omit --root so each manifest uses its recorded "
                        "installed_path")

    sides = {}
    for m in manifests:
        row = prove_manifest(m, args.root)
        if row["side"] in sides:
            raise ToolError("two manifests resolve to side %s: %s and %s"
                            % (row["side"], sides[row["side"]]["manifest_path"],
                               row["manifest_path"]))
        sides[row["side"]] = row

    both = sorted(sides) == sorted(SIDES)
    all_ok = all(r["ok"] for r in sides.values())
    receipt = receipt_base("record")
    receipt["sides"] = sides
    receipt["distributions_covered"] = sorted(
        r["distribution"] for r in sides.values() if r["distribution"])
    receipt["both_sides_present"] = both
    receipt["all_proofs_ok"] = all_ok
    receipt["a12_creditable"] = both and all_ok
    receipt["notes"] = [
        "loaded-source proof: every file in the installed tree is recomputed "
        "against the manifest's file map, and the manifest's own "
        "manifest_sha256 is recomputed from that map.",
        "a12_creditable requires both distributions present AND every proof "
        "ok; one side alone is PARTIAL and can never credit the row.",
        "installer_rc is not a pass signal.",
    ]

    for name in SIDES:
        row = sides.get(name)
        if not row:
            print("[%s] %s: NOT RECORDED (no clean-install manifest supplied)"
                  % (ROW, name))
            continue
        print("[%s] %s (%s): %d file(s), loaded-source proof %s"
              % (ROW, name, row["distribution"] or "?", row["file_count"],
                 "OK" if row["ok"] else "FAILED"))
        dm = row["distribution_manifest"]
        print("      distribution manifest sha256 %s (recomputed %s, %s)"
              % (str(dm["declared_sha256"])[:64], dm["recomputed_sha256"][:64],
                 "agree" if dm["agrees"] else "DISAGREE"))
        print("      installed tree %s" % row["installed_path"])
        print("      loaded-source proof: %s — %s"
              % ("OK" if row["loaded_source_proof"]["ok"] else "FAILED",
                 row["loaded_source_proof"]["detail"]))
        for problem in row["problems"][:10]:
            print("      MISMATCH: %s" % problem)

    out = default_out(manifests, args.out)
    cc.write_json(out, receipt)
    print("[%s] record: %d/%d side(s) proven; both distributions present = %s; "
          "a12_creditable = %s; installer_rc not used as a pass signal"
          % (ROW, sum(1 for r in sides.values() if r["ok"]), len(SIDES), both,
             receipt["a12_creditable"]))
    print("wrote %s" % out)
    return 0 if all_ok else 1


def cmd_check(args):
    manifests = []
    for arg in args.manifest:
        manifests.extend(expand_manifests(arg))
    if args.tree and len(manifests) != 1:
        raise ToolError("--tree names one installed tree; pass one --manifest "
                        "or let each manifest use its recorded installed_path")

    if args.side != "installed":
        selected = []
        for m in manifests:
            _, doc = load_manifest(m)
            if DIST_TO_SIDE.get(doc.get("distribution")) == args.side:
                selected.append(m)
        if not selected:
            raise ToolError("no manifest for --side %s in %s"
                            % (args.side, [str(m) for m in manifests]))
        manifests = selected

    bad_sides = 0
    for m in manifests:
        row = prove_manifest(m, args.tree, args.side)
        mismatches = row["problems"]
        for problem in mismatches[:50]:
            print("[%s] %s: MISMATCH: %s" % (ROW, row["side"], problem))
        dm = row["distribution_manifest"]
        print("[%s] check %s (%s): %d file(s) compared, %d mismatch(es)"
              % (ROW, row["side"], row["distribution"] or "?", row["file_count"],
                 len(mismatches)))
        print("      distribution manifest sha256 %s (declared %s, %s)"
              % (dm["recomputed_sha256"], str(dm["declared_sha256"])[:12],
                 "agree" if dm["agrees"] else "DISAGREE"))
        if not row["ok"]:
            bad_sides += 1

    print("[%s] check: %d/%d side(s) clean%s"
          % (ROW, len(manifests) - bad_sides, len(manifests),
             "" if not bad_sides else "; installer_rc is not a pass signal"))
    return 0 if not bad_sides else 1


def _write_manifest(path, dist, root, extra=None):
    files = cc.manifest_tree(root)
    doc = cc.distribution_manifest(dist, root, files,
                                   {"repo": "selftest-fixture",
                                    "revision": "0" * 40, "subdir": "."})
    if extra:
        doc.update(extra)
    cc.write_json(path, doc)
    return doc, files


def _build_tree(root):
    (root / "scripts" / "core").mkdir(parents=True)
    (root / "SKILL.md").write_text("# selftest skill tree\n", encoding="utf-8")
    (root / "scripts" / "core" / "state_store.py").write_text(
        "VALUE = 1\n", encoding="utf-8")
    for i in range(120):
        (root / "scripts" / "core" / ("mod_%03d.py" % i)).write_text(
            "VALUE = %d\n" % i, encoding="utf-8")


def selftest():
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               (" — " + str(detail)[:200]) if detail else ""))

    with tempfile.TemporaryDirectory(prefix=cc.SCRATCH_PREFIX + "a12-") as td:
        base = Path(td)
        good_tree = base / "good-tree"
        _build_tree(good_tree)
        good_manifest = base / "clean-install-onboarding.manifest.json"
        doc, files = _write_manifest(good_manifest, "onboarding", good_tree)

        row = prove_manifest(good_manifest)
        check("correct manifest passes", row["ok"],
              "%d files, digest %s" % (row["file_count"],
                                       row["distribution_manifest"]
                                       ["recomputed_sha256"][:12]))

        # (1) installed content altered -> MUST fail
        bad_tree = base / "bad-tree"
        shutil.copytree(good_tree, bad_tree)
        victim = sorted(files)[0]
        with open(bad_tree / victim, "a", encoding="utf-8") as f:
            f.write("\n# altered after install\n")
        row_bad = prove_manifest(good_manifest, tree=str(bad_tree))
        check("altered installed file fails the check", not row_bad["ok"],
              row_bad["problems"][:1])

        # (2) manifest digest altered -> MUST fail
        altered = json.loads(good_manifest.read_text(encoding="utf-8"))
        key = sorted(altered["files"])[0]
        altered["files"][key] = "0" * 64
        altered_path = base / "altered.manifest.json"
        cc.write_json(altered_path, altered)
        row_alt = prove_manifest(altered_path, tree=str(good_tree))
        check("altered manifest digest fails the check", not row_alt["ok"],
              row_alt["problems"][:1])

        # (3) one-file placeholder manifest -> MUST be refused
        one = base / "one-file.manifest.json"
        cc.write_json(one, {
            "schema": MANIFEST_SCHEMA, "distribution": "onboarding",
            "installed_path": str(good_tree), "file_count": 1,
            "manifest_sha256": cc.manifest_digest(
                {"SKILL.md": files["SKILL.md"]}),
            "files": {"SKILL.md": files["SKILL.md"]},
        })
        try:
            prove_manifest(one, tree=str(good_tree))
            refused, detail = False, "accepted"
        except ToolError as exc:
            refused, detail = True, str(exc)
        check("one-file placeholder manifest is refused", refused, detail)

        # (4) installer_rc 0 over a broken tree -> MUST still fail
        rc_manifest = json.loads(good_manifest.read_text(encoding="utf-8"))
        rc_manifest["installer_rc"] = 0
        rc_path = base / "rc-zero.manifest.json"
        cc.write_json(rc_path, rc_manifest)
        row_rc = prove_manifest(rc_path, tree=str(bad_tree))
        check("installer_rc 0 does not turn a broken tree green",
              not row_rc["ok"], row_rc["problems"][:1])

        # (5) missing installed tree -> MUST fail, never pass
        row_gone = prove_manifest(good_manifest, tree=str(base / "no-such-tree"))
        check("missing installed tree fails the check", not row_gone["ok"],
              row_gone["problems"][:1])

    ok = all(results)
    print("A12 selftest: %d/%d controls held%s"
          % (sum(results), len(results), "" if ok else "; FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="A12 runtime proof: clean-install manifest hashes plus "
                    "loaded-source proof on both distributions.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record")
    r.add_argument("--manifest", action="append", required=True,
                   help="clean-install manifest file or a directory of "
                        "clean-install-*.manifest.json")
    r.add_argument("--root", default=None,
                   help="installed skill tree (single manifest only; default: "
                        "the manifest's recorded installed_path)")
    r.add_argument("--out", default=None,
                   help="receipt file or directory (default: beside the first "
                        "manifest)")
    r.set_defaults(fn=cmd_record)

    c = sub.add_parser("check")
    c.add_argument("--manifest", action="append", required=True,
                   help="clean-install manifest file or directory")
    c.add_argument("--side", default="installed",
                   choices=("installed",) + SIDES,
                   help="installed derives the side from the manifest's "
                        "distribution; a named side must agree with it")
    c.add_argument("--tree", default=None,
                   help="installed skill tree (single manifest only)")
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("selftest", help="prove the checker can fail")
    s.set_defaults(fn=lambda _a: selftest())

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ToolError as exc:
        print("TOOLING: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
