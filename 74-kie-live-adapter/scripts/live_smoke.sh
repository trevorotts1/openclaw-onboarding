#!/usr/bin/env bash
# live_smoke.sh - OPT-IN live check for Skill 74. Operator account only. Never part of the QC script.
#   bash scripts/live_smoke.sh           free calls only: health, credits, catalog, one schema, one validate, tiny upload
#   bash scripts/live_smoke.sh --paid    ALSO runs exactly ONE paid job: gpt-image-2-5-sunburst-text-to-image at 1K
# Prints SET / NOT-SET for the key and never the value. Cache and receipts go to a temp dir.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADA="$HERE/kie_live_adapter.py"
PAID=0; [ "${1:-}" = "--paid" ] && PAID=1
[ -n "${KIE_API_KEY:-}" ] && echo "KIE_API_KEY: SET" || { echo "KIE_API_KEY: NOT-SET - live smoke PENDING"; exit 0; }
export PYTHONDONTWRITEBYTECODE=1 KIE_LIVE_ADAPTER_MODE=active
W="$(mktemp -d "${TMPDIR:-/tmp}/kie-live-smoke.XXXXXX")"; trap 'rm -rf "$W"' EXIT
export KIE_LIVE_CACHE_DIR="$W/cache"
MODEL="gpt-image-2-5-sunburst-text-to-image"   # the fleet image pin; the adapter never substitutes another model
run() { python3 "$ADA" "$@" --json; }
show() { python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r.get("task_id"), r.get("credits_consumed"), r.get("error"), r.get("data",{}).get("credits",""))'; }
echo "== health";  run health  | show
echo "== credits"; run credits | show
echo "== discover image"; run discover --modality image --limit 5 | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r["data"]["total"], r["data"]["matched"])'
echo "== schema";  run schema --model "$MODEL" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r["data"].get("path"), r["error"])'
printf '{"prompt":"a single red maple leaf on wet slate, macro photograph","resolution":"1K","aspect_ratio":"1:1"}' > "$W/in.json"
echo "== validate"; run validate --model "$MODEL" --payload "$W/in.json" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r["error"])'
python3 - "$W/t.png" <<'PY'
import struct, sys, zlib
def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
raw = b"".join(b"\x00" + b"\xff\x00\x00" * 8 for _ in range(8))
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
PY
echo "== upload 8x8 png"; run upload --file "$W/t.png" --upload-path openclaw/smoke | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r["data"].get("upload_method"), r["error"])'
if [ "$PAID" = 1 ]; then
  SAVE="${KIE_SMOKE_SAVE_DIR:-$W/save}"; mkdir -p "$SAVE"
  printf '{"model":"%s","input":{"prompt":"a single red maple leaf resting on wet slate, macro photograph","resolution":"1K","aspect_ratio":"1:1"},"timeout":300}' "$MODEL" > "$W/req.json"
  echo "== balance before"; run credits | show
  echo "== ONE paid job"; run run --request "$W/req.json" --save-dir "$SAVE" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r["task_id"], r["model_id"], r["credits_consumed"], r["saved_paths"], r["error"])'
  echo "== balance after"; run credits | show
  [ -n "${KIE_SMOKE_SAVE_DIR:-}" ] && echo "saved under $SAVE (kept)"
fi
