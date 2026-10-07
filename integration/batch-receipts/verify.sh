#!/usr/bin/env bash
# verify.sh — the one runnable check for the W5-01-U1 batch-window receipts.
# Re-proves everything from the artifacts and the live scratch remote; trusts
# nothing the driver claimed. Exit 0 = every check holds.
set -uo pipefail
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${DTS_BUILD_ROOT:-$(pwd)}"
LANE="$ROOT/swarm-plans/lanes/W5-01-U1-lane"
REPO="$LANE/scratch/repo"
fails=0
ck() { # ck <name> <0/1>
  if [[ "$2" == 1 ]]; then printf 'PASS | %s\n' "$1"; else printf 'FAIL | %s\n' "$1"; fails=$((fails+1)); fi
}

python3 - "$OUT" "$ROOT/run/state.json" <<'PY'
import json, sys, subprocess, os
out, state_path = sys.argv[1], sys.argv[2]
R = os.path.join(os.environ.get("DTS_BUILD_ROOT", os.getcwd()), "swarm-plans/lanes/W5-01-U1-lane/scratch/repo")
ok = []
def ck(name, cond):
    ok.append((name, bool(cond)))
state = json.load(open(state_path))
t0_state = state.get("build_started_unix")  # run/state.json records T0 here
events = [json.loads(l) for l in open(f"{out}/window-receipts.jsonl")]
batches = [e for e in events if e["event"] == "batch"]
refused = [e for e in events if e["event"] == "refused"]
scan = json.load(open(f"{out}/builder-merge-scan.json"))
neg = json.load(open(f"{out}/negative-controls.json"))
man = json.load(open(f"{out}/candidate-manifest.json"))

ck("T0 receipts matches run/state.json T0", all(e["t0"] == t0_state for e in events))
ck("every event carries MERGE_BATCH_MINUTES=30", all(e["merge_batch_minutes"] == 30 for e in events))
ck("exactly one train batch event", len(batches) == 1)
ck("at least one refusal event", len(refused) >= 1)
b = batches[0]
ck("batch starts no earlier than T0+30min", b["epoch"] >= b["t0"] + 1800)
ck("batch stamp age >= 30min (window was open)", b["stamp_age_s"] >= 1800)
ck("window bounds are T0-anchored 30min slots",
   b["window_start"] == b["t0"] + 1800 * b["window_index"]
   and b["window_end"] == b["window_start"] + 1800)
ck("batch ran inside its own window",
   b["window_start"] <= b["epoch"] < b["window_end"]
   and b["window_start"] <= b["epoch_end"] < b["window_end"])
r = refused[0]
ck("refusal stamp age < 30min (window closed)", r["stamp_age_s"] < 1800)
ck("refusal after the batch (candidate presented outside window)", r["epoch"] > b["epoch"])
ck("refusal reason is window cadence", r["reason"] == "window-cadence-not-due")
ck("batch and refusal in same 30min window slot", r["window_index"] == b["window_index"])

merged = [p.split("@") for p in (b.get("merged") or "").split(",") if p]
ck("batch merged at least the closed set A+B", len(merged) >= 2)
subprocess.run(["git", "-C", R, "fetch", "-q", "origin", "main"], check=True)
tip = subprocess.run(["git", "-C", R, "rev-parse", "origin/main"], capture_output=True, text=True).stdout.strip()
def anc(a, d):
    return subprocess.run(["git", "-C", R, "merge-base", "--is-ancestor", a, d]).returncode == 0
ck("origin/main exists after fetch", len(tip) == 40)
ck("every merged unit sha is ancestor of fetched origin/main (remote proof)",
   all(anc(s, tip) for _, s in merged))
ck("QC-FAIL candidate C not on remote",
   not anc(neg["controls"][0]["tip"], tip))
ck("outside-window candidate D not on remote",
   not anc(neg["controls"][1]["tip"], tip))
ck("dependency closure: B stacked on A", man["candidates"][1]["stack_proof_ancestor"] is True)
ck("closed set recorded as {A,B}", man["dependency_closed_set"] == ["unit/W501U1-A", "unit/W501U1-B"])
ck("builder-merge scan PASS", scan["verdict"] == "PASS")
ck("zero individual builder merges", scan["counts"]["merges_by_builder"] == 0)
log1 = open(f"{out}/batch-1.log").read()
ck("batch log proves merged-on-origin/main", log1.count("trunk=origin/main") >= 2)
ck("batch log shows combined-candidate gate passed", "tests=pass" in log1)
ck("batch log has no REPAIR/CONFLICT/UNPROVEN", not any(t in log1 for t in ("REPAIR:", "CONFLICT:", "MERGE-UNPROVEN")))
log2 = open(f"{out}/negative-1.log").read()
ck("negative control log shows WINDOW-REFUSED", "WINDOW-REFUSED" in log2)
ck("negative control ran no train batch", "MERGE-TRAIN BATCH" not in log2)
st = open(f"{out}/merge-train-selftest.log").read()
ck("existing merge-train selftest passed", "SELFTEST ok" in st and "SELFTEST FAIL" not in st)
ck("negative-controls batch_events_count==1 (no hidden batch)", neg["batch_events_count"] == 1)
for name, good in ok:
    print(("PASS | " if good else "FAIL | ") + name)
bad = [n for n, g in ok if not g]
print(f"VERIFY {'PASS' if not bad else 'FAIL'} | checks={len(ok)} failed={len(bad)}")
sys.exit(1 if bad else 0)
PY
rc=$?
exit "$rc"
