#!/usr/bin/env bash
# Folded from .github/workflows/cinematic-forge-delivery-guard.yml (job "Skill 28: the delivered artifact is the requested one (T0-46/47/48, T2-29/30)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Install ffmpeg + jq
set -e -o pipefail
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg jq
ffmpeg -version | head -1
jq --version
)
( # step: Shell syntax
set -e -o pipefail
set -euo pipefail
bash -n 28-cinematic-forge/qc-output.sh
bash -n 28-cinematic-forge/qc-cinematic-forge.sh
bash -n tests/unit/cinematic-forge-delivery-gate.test.sh
echo "OK: every Skill 28 shell file parses"
)
( # step: Only the delivery mode may say "safe to deliver"
set -e -o pipefail
set -euo pipefail
python3 - <<'PY'
import sys
src = open("28-cinematic-forge/qc-output.sh").read()
# Executable lines only, so the explanatory header cannot satisfy this.
bare = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith("#"))
verdicts = bare.lower().count("safe to deliver")
if verdicts != 1:
    print(f"FAIL: expected exactly 1 executable 'safe to deliver' verdict, found {verdicts}")
    sys.exit(1)
if "--requirements" not in bare:
    print("FAIL: the gate no longer accepts a delivery-requirements record")
    sys.exit(1)
print("OK: one delivery verdict, and it is reachable only through the requirements record")
PY
)
( # step: Delivery-gate suite (with the mutation proof)
set -e -o pipefail
bash tests/unit/cinematic-forge-delivery-gate.test.sh
)
( # step: The install QC script still runs
set -e -o pipefail
bash -n 28-cinematic-forge/qc-cinematic-forge.sh
)
