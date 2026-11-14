#!/usr/bin/env python3
"""U-J01 BUILD readiness: gate predicate, dependency-closed candidate, strict parity.

U-J01 (FINAL/01-BUILD-SPEC.md, section "U-J01 - 999 copy") starts only after
every onboarding unit is merged on GitHub main (amendment 4: merged OR closed
in the ledger). This tool does not perform the sync. It produces the
dependency-closed candidate tree and proves, offline and read-only:

  * the gate predicate is FALSE while any prerequisite is unmet, and names why;
  * every file in the packaged (999) core exists in the candidate, so the
    literal sync can delete nothing;
  * every candidate file is byte-identical to ONB main except the declared
    dependency overlay (PR #3270 U-B01/U-B02) and the ported-test overlay;
  * the spend-ledger money-safety markers survive in the candidate.

It never writes to either repository and never overwrites the 999 tree.
Paths come from arguments; no operator path is embedded.

Usage:
  python3 uj01_candidate_ready.py --onb-repo DIR --n99-repo DIR \
      --onb-ref origin/main --pr-ref <sha> --lane-ref <sha> \
      --heartbeat control/heartbeat.json --expected-units 103 \
      --out BUILD_DIR [--selftest]

Exit 0 = all checks pass (gate may still be false; reported as data).
Exit 1 = a strict check failed.
Exit 2 = refusal: gate unmet for assembly? No - assembly is allowed; assembly
         is refused only when it would write inside the 999 repository.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ONB_CORE = "75-drama-song-ad-factory/scripts/core"
ONB_REFS = "75-drama-song-ad-factory/references"
ONB_BRIDGE = "75-drama-song-ad-factory/shared-bridge"
N99_CORE = ".claude/skills/drama-song-ad-factory/scripts/core"
N99_REFS = ".claude/skills/drama-song-ad-factory/references"
N99_STUDIO = ".claude/skills/drama-studio"
MONEY_MARKERS = ("idx_receipts_attempt", "backfill_uncertain", "strip()")
ZERO_ESTIMATE = "ZERO_ESTIMATE_FOR_PAID_JOB"
NON_TERMINAL = ("in_batch", "qc_pass", "pr_open", "open", "building",
                "blocked", "needs_decision")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True).stdout


def tree(repo, rev, path):
    raw = git(repo, "ls-tree", "-r", rev, "--", path).decode()
    prefix = path.rstrip("/") + "/"
    out = {}
    for line in raw.splitlines():
        meta, full = line.split("\t", 1)
        out[full[len(prefix):]] = meta.split()[2]
    return out


def merge_base(repo, a, b):
    return git(repo, "merge-base", a, b).decode().strip()


def changed(repo, base, head, path):
    raw = git(repo, "diff", "--name-only", base, head, "--", path).decode()
    prefix = path.rstrip("/") + "/"
    return {line[len(prefix):] for line in raw.splitlines() if line}


def is_ancestor(repo, a, b):
    return subprocess.run(["git", "-C", str(repo), "merge-base",
                           "--is-ancestor", a, b]).returncode == 0


def blob(repo, rev, path):
    return git(repo, "show", f"{rev}:{path}")


def blobs(repo, rev, paths):
    """Bulk-read many blobs in one git process (external volumes are slow)."""
    paths = list(paths)
    if not paths:
        return {}
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input="".join(f"{rev}:{p}\n" for p in paths).encode(),
        check=True, capture_output=True)
    out, data, pos, res = proc.stdout, {}, 0, {}
    for name in paths:
        nl = out.index(b"\n", pos)
        header = out[pos:nl].decode()
        if header.endswith(" missing"):
            raise SystemExit(f"missing blob: {rev}:{name}")
        size = int(header.split()[2])
        start = nl + 1
        res[name] = out[start:start + size]
        pos = start + size + 1
    return res


def gate(onb, onb_ref, pr_ref, heartbeat_path, expected):
    blockers, facts = [], {}
    if not is_ancestor(onb, pr_ref, onb_ref):
        blockers.append(f"PR #3270 head {pr_ref[:12]} is not on {onb_ref}")
    facts["pr3270_on_onb_main"] = not blockers
    if heartbeat_path:
        hb = json.loads(Path(heartbeat_path).read_text())
        counts = hb.get("counts_by_status", {})
        facts["counts_by_status"] = counts
        facts["awaiting_merge"] = hb.get("awaiting_merge", [])
        for key in NON_TERMINAL:
            if counts.get(key, 0):
                blockers.append(f"{key}={counts[key]}")
        if hb.get("awaiting_merge"):
            blockers.append(f"awaiting_merge={len(hb['awaiting_merge'])}")
        if expected is None:
            blockers.append("expected onboarding unit total not supplied")
        else:
            done = counts.get("merged", 0) + counts.get("closed", 0)
            facts["merged_plus_closed"] = done
            facts["expected_units"] = expected
            if done < expected:
                blockers.append(f"merged+closed={done} < expected={expected}")
    else:
        blockers.append("heartbeat path not supplied; MERGED:ONB unproven")
    return {"ready": not blockers, "blockers": blockers, "facts": facts}


def assemble(onb, onb_ref, pr_ref, lane_ref, n99, n99_ref, out):
    out = Path(out)
    if out.resolve().is_relative_to(Path(n99).resolve()):
        raise SystemExit("refusal: --out must not be inside the 999 repository")
    base = tree(onb, onb_ref, ONB_CORE)
    pr_overlay = changed(onb, merge_base(onb, onb_ref, pr_ref), pr_ref, ONB_CORE)
    lane_overlay = changed(onb, merge_base(onb, onb_ref, lane_ref), lane_ref, ONB_CORE)
    overlay = sorted(set(pr_overlay) | set(lane_overlay))
    missing = [p for p in overlay if p not in tree(onb, pr_ref, ONB_CORE)
               and p not in tree(onb, lane_ref, ONB_CORE)]
    if missing:
        raise SystemExit(f"overlay path absent from its source ref: {missing}")

    core = out / "core"
    if core.exists():
        shutil.rmtree(core)
    core.mkdir(parents=True)
    expected = {}
    base_data = blobs(onb, onb_ref, [f"{ONB_CORE}/{r}" for r in base])
    for rel in base:
        data = base_data[f"{ONB_CORE}/{rel}"]
        dest = core / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        expected[rel] = hashlib.sha256(data).hexdigest()
    pr_data = blobs(onb, pr_ref, [f"{ONB_CORE}/{r}" for r in pr_overlay])
    lane_data = blobs(onb, lane_ref, [f"{ONB_CORE}/{r}" for r in lane_overlay])
    for rel in overlay:
        src_rev = pr_ref if rel in pr_overlay else lane_ref
        data = (pr_data if rel in pr_overlay else lane_data)[f"{ONB_CORE}/{rel}"]
        dest = core / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        expected[rel] = hashlib.sha256(data).hexdigest()

    # references: ONB copy wins where the path also exists in the packaged tree
    refs = {}
    onb_refs = tree(onb, onb_ref, ONB_REFS)
    n99_refs = tree(n99, n99_ref, N99_REFS)
    ref_copy = sorted(p for p in onb_refs if p in n99_refs)
    ref_keep = sorted(p for p in n99_refs if p not in onb_refs)
    for rel in ref_copy:
        d = out / "references" / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(blob(onb, onb_ref, f"{ONB_REFS}/{rel}"))
    for rel in ref_keep:
        refs[rel] = "n99-only: kept"
    # bridges
    bridges = {}
    for name in ("approvals_bridge.py", "studio_bridge.py"):
        d = out / "studio" / name
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(blob(onb, onb_ref, f"{ONB_BRIDGE}/{name}"))
        bridges[name] = hashlib.sha256(d.read_bytes()).hexdigest()

    return {
        "onb_repo": str(onb),
        "onb_ref": onb_ref, "pr_ref": pr_ref, "lane_ref": lane_ref,
        "n99_ref": n99_ref,
        "core_files": len(base) + len([p for p in overlay if p not in base]),
        "expected_sha256": expected,
        "pr_overlay": sorted(pr_overlay), "lane_overlay": sorted(lane_overlay),
        "overlay": overlay,
        "references_copy": len(ref_copy), "references_kept_n99_only": refs,
        "bridges_sha256": bridges,
        "n99_core_must_exist": sorted(tree(n99, n99_ref, N99_CORE)),
    }


def verify(core_dir, manifest, n99):
    fails = []
    core_dir = Path(core_dir)
    onb = manifest["onb_repo"]
    present = {p.relative_to(core_dir).as_posix()
               for p in core_dir.rglob("*") if p.is_file()}
    for rel in manifest["n99_core_must_exist"]:
        if rel not in present:
            fails.append(f"deletion risk: packaged file absent from candidate: {rel}")
    pr_set = set(manifest["pr_overlay"])
    lane_set = set(manifest["lane_overlay"])
    expected = manifest["expected_sha256"]
    for rel in sorted(present):
        if rel not in expected:
            fails.append(f"unexpected candidate file: {rel}")
            continue
        if hashlib.sha256((core_dir / rel).read_bytes()).hexdigest() != expected[rel]:
            src_rev = (manifest["pr_ref"] if rel in pr_set else
                       manifest["lane_ref"] if rel in lane_set else
                       manifest["onb_ref"])
            fails.append(f"byte mismatch vs {src_rev[:12]}: {rel}")
    spend = core_dir / "spend_ledger.py"
    text = spend.read_text(errors="replace") if spend.exists() else ""
    for marker in MONEY_MARKERS:
        if marker not in text:
            fails.append(f"money-safety marker missing in spend_ledger.py: {marker}")
    kie = core_dir / "kie_dispatch" / "kie_dispatch.py"
    if ZERO_ESTIMATE not in kie.read_text(errors="replace") if kie.exists() else True:
        fails.append(f"money-safety marker missing in kie_dispatch.py: {ZERO_ESTIMATE}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onb-repo", required=True)
    ap.add_argument("--n99-repo", required=True)
    ap.add_argument("--onb-ref", default="origin/main")
    ap.add_argument("--pr-ref", required=True)
    ap.add_argument("--lane-ref", default="HEAD")
    ap.add_argument("--n99-ref", default="origin/main")
    ap.add_argument("--heartbeat")
    ap.add_argument("--expected-units", type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    g = gate(a.onb_repo, a.onb_ref, a.pr_ref, a.heartbeat, a.expected_units)
    m = assemble(a.onb_repo, a.onb_ref, a.pr_ref, a.lane_ref,
                 a.n99_repo, a.n99_ref, a.out)
    m["base_paths"] = sorted(tree(a.onb_repo, a.onb_ref, ONB_CORE))
    fails = verify(Path(a.out) / "core", m, a.n99_repo)

    # negative control: flip one byte in a scratch copy of the candidate; the
    # same checker must reject it, proving it discriminates.
    control = {"performed": False}
    if a.selftest:
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "core"
            shutil.copytree(Path(a.out) / "core", copy)
            victim = copy / "spend_ledger.py"
            data = bytearray(victim.read_bytes())
            pos = next((i for i, b in enumerate(data) if b == ord("X")), 0)
            data[pos] = ord("Y") if data[pos] != ord("Y") else ord("Z")
            victim.write_bytes(bytes(data))
            got = verify(copy, m, a.n99_repo)
            control = {"performed": True, "tampered": "spend_ledger.py",
                       "checker_failed_on_tamper": bool(got),
                       "failures": got[:3]}
            if not got:
                fails.append("negative control did not discriminate")

    result = {"gate": g, "candidate": m, "checks": {"failures": fails},
              "negative_control": control}
    print(json.dumps(result, indent=1))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
