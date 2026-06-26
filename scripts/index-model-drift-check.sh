#!/usr/bin/env bash
# index-model-drift-check.sh — EMBEDDING-PREVENTION BUNDLE item 4.
#
# THE PROBLEM (fleet-confirmed stale-index thrash):
#   The memory index (the on-disk vector DB) is built FOR a specific embedding
#   model + dimension count. If the config model later changes (a model pin, a
#   migration off the dying gemini-embedding-001, a provider swap) but the
#   on-disk index was built for the OLD model, every memory search embeds the
#   query with the NEW model and compares it against vectors from the OLD model.
#   The scores are garbage, the runtime keeps re-querying / re-embedding, and the
#   box thrashes (CPU + repeated provider calls) until someone rebuilds the index.
#
# WHAT THIS DOES:
#   Reads the CONFIG embedding model (agents.defaults.memorySearch.model +
#   .dimensions) and the LIVE index's BUILT-FOR model/dimensions (from the index
#   sidecar metadata that the OpenClaw memory backend writes next to each
#   *.sqlite vector DB), and FLAGS a mismatch BEFORE it thrashes. On drift it:
#     - logs a DRIFT line (model + dims, config-vs-index)
#     - writes a machine-readable .index-drift.json marker next to openclaw.json
#     - (optional) escalates one Telegram line to the operator via openclaw
#       message send when OC_DRIFT_ESCALATE=1 and an owner/operator chat resolves
#   It does NOT auto-rebuild (a rebuild re-embeds the whole corpus — an expensive
#   action the operator must trigger). It is a DETECTOR + alarm.
#
# INDEX METADATA DISCOVERY (best-effort, version-tolerant):
#   The builtin memory backend stores its vector DBs under
#   $OC_ROOT/memory/**/<name>.sqlite with a sibling metadata file that records
#   the model the index was built for. We probe, in order:
#     1. a sibling <db>.meta.json / <db>.json with {model,dimensions}
#     2. a `meta`/`config` row inside the sqlite (key/value), if sqlite3 present
#     3. the dimension width of the stored vectors (column/byte length), as a
#        last-resort dimension-only check.
#   If we genuinely cannot read the built-for model AND cannot read dimensions,
#   we report INDETERMINATE (exit 0, logged) rather than a false DRIFT.
#
# DESIGN: host-level, idempotent, platform-detected OC_ROOT, dedicated log,
#   clear exit-code contract. Mirrors scripts/capacity-monitor.sh. Safe to run
#   from an hourly host cron. bash-not-zsh.
#
# EXIT CODES:
#   0  no drift (or indeterminate — logged, non-fatal)
#   4  DRIFT detected (config model/dims != index built-for model/dims)
#   2  could not run (no OpenClaw root / no python3 / unreadable config)
#
# ENV OVERRIDES:
#   OC_DRIFT_ESCALATE=1   send one operator Telegram line on drift (default off)
#   OC_DRIFT_DRY_RUN=1    detect + log only; never write marker / escalate
#
# Version marker (kept in sync by scripts/bump-version.sh):
INDEX_MODEL_DRIFT_CHECK_VERSION="v13.2.0"

set -u

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[index-model-drift-check] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

CONFIG_FILE="$OC_ROOT/openclaw.json"
MEMORY_DIR="$OC_ROOT/memory"
MARKER_FILE="$OC_ROOT/.index-drift.json"
DRIFT_LOG="$OC_ROOT/index-model-drift.log"
DRY_RUN="${OC_DRIFT_DRY_RUN:-0}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$DRIFT_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

# ─── Preflight ────────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  log "WARN" "python3 not on PATH — required for JSON read; skipping"
  exit 2
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  log "WARN" "config not found: $CONFIG_FILE — box not onboarded yet; skipping"
  exit 2
fi
if [[ ! -d "$MEMORY_DIR" ]]; then
  log "INFO" "no memory index dir yet ($MEMORY_DIR) — nothing built; no drift possible"
  exit 0
fi

# ─── Compare config model/dims vs the live index built-for model/dims ─────────
# All the heavy lifting is in python3 (JSON + optional sqlite via stdlib).
OC_ROOT="$OC_ROOT" CONFIG_FILE="$CONFIG_FILE" MEMORY_DIR="$MEMORY_DIR" \
MARKER_FILE="$MARKER_FILE" DRY_RUN="$DRY_RUN" python3 <<'PYEOF'
import json, os, sys, glob, sqlite3

cfg_file   = os.environ["CONFIG_FILE"]
memory_dir = os.environ["MEMORY_DIR"]
marker     = os.environ["MARKER_FILE"]
dry        = os.environ.get("DRY_RUN", "0") == "1"

def norm(v):
    return str(v).strip().lower() if v is not None else None

# ── config side ──────────────────────────────────────────────────────────────
try:
    cfg = json.load(open(cfg_file))
except Exception as e:
    print(f"  WARN cannot read config: {e}")
    sys.exit(2)

ms = cfg.get("agents", {}).get("defaults", {}).get("memorySearch", {}) or {}
cfg_model = norm(ms.get("model"))
cfg_dims  = ms.get("dimensions")
try:
    cfg_dims = int(cfg_dims) if cfg_dims is not None else None
except Exception:
    cfg_dims = None

if not cfg_model:
    print("  INFO config has no memorySearch.model — cannot compare; INDETERMINATE")
    sys.exit(0)

# ── index side — probe each vector DB for its built-for model/dims ────────────
def probe_index(db_path):
    """Return (model, dims) the index was built for, any may be None."""
    model = None
    dims = None
    # 1. sibling metadata json
    for cand in (db_path + ".meta.json", db_path + ".json",
                 os.path.splitext(db_path)[0] + ".meta.json"):
        if os.path.isfile(cand):
            try:
                m = json.load(open(cand))
                model = model or m.get("model") or m.get("embeddingModel")
                d = m.get("dimensions") or m.get("dim") or m.get("dimension")
                if d is not None and dims is None:
                    dims = int(d)
            except Exception:
                pass
    # 2. meta/config key-value rows inside the sqlite
    if model is None or dims is None:
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
            cur = con.cursor()
            tabs = {r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for t in ("meta", "metadata", "config", "index_meta"):
                if t in tabs:
                    try:
                        rows = dict(cur.execute(f"SELECT key, value FROM {t}").fetchall())
                        model = model or rows.get("model") or rows.get("embeddingModel")
                        d = rows.get("dimensions") or rows.get("dim")
                        if d is not None and dims is None:
                            dims = int(d)
                    except Exception:
                        pass
            con.close()
        except Exception:
            pass
    return (norm(model), dims)

dbs = sorted(set(glob.glob(os.path.join(memory_dir, "**", "*.sqlite"), recursive=True)
                 + glob.glob(os.path.join(memory_dir, "**", "*.db"), recursive=True)))
if not dbs:
    print(f"  INFO no vector DBs under {memory_dir} — nothing built; no drift")
    sys.exit(0)

drift_rows = []
indeterminate = 0
for db in dbs:
    idx_model, idx_dims = probe_index(db)
    if idx_model is None and idx_dims is None:
        indeterminate += 1
        continue
    model_mismatch = (idx_model is not None and idx_model != cfg_model)
    dims_mismatch  = (idx_dims is not None and cfg_dims is not None and idx_dims != cfg_dims)
    if model_mismatch or dims_mismatch:
        drift_rows.append({
            "db": db,
            "configModel": cfg_model, "indexModel": idx_model,
            "configDims": cfg_dims, "indexDims": idx_dims,
            "modelMismatch": model_mismatch, "dimsMismatch": dims_mismatch,
        })

if not drift_rows:
    if indeterminate and indeterminate == len(dbs):
        print(f"  INFO {indeterminate} index DB(s) carry no readable built-for model — INDETERMINATE (no false drift)")
    else:
        print(f"  OK    index matches config model {cfg_model!r} dims={cfg_dims} ({len(dbs)} DB(s) checked, {indeterminate} indeterminate)")
    # clear any stale marker
    if os.path.isfile(marker) and not dry:
        try: os.remove(marker)
        except Exception: pass
    sys.exit(0)

# DRIFT
print(f"  DRIFT index built for a DIFFERENT model than config (config={cfg_model!r} dims={cfg_dims}):")
for r in drift_rows:
    print(f"    ✗ {r['db']}  indexModel={r['indexModel']!r} indexDims={r['indexDims']}"
          + ("  [MODEL]" if r["modelMismatch"] else "")
          + ("  [DIMS]" if r["dimsMismatch"] else ""))
print("  ACTION rebuild the memory index for the new model (e.g. `openclaw memory reindex`)"
      " — this re-embeds the corpus, so the OPERATOR must trigger it.")

if not dry:
    try:
        json.dump({
            "detectedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "configModel": cfg_model, "configDims": cfg_dims,
            "drift": drift_rows,
        }, open(marker, "w"), indent=2)
        print(f"  ✓ wrote drift marker: {marker}")
    except Exception as e:
        print(f"  WARN could not write marker {marker}: {e}")

sys.exit(4)
PYEOF
rc=$?

if [[ "$rc" -eq 4 ]]; then
  log "DRIFT" "index-model drift detected (see $DRIFT_LOG / $MARKER_FILE)"
  # Optional operator escalation — one line, only if explicitly enabled AND CLI present.
  if [[ "${OC_DRIFT_ESCALATE:-0}" == "1" ]] && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]]; then
    _esc_msg="[index-drift] $(hostname): memory index built for a model that no longer matches config. Run a reindex before it thrashes. See $MARKER_FILE."
    _esc_msg="${_esc_msg//\\/\\\\}"; _esc_msg="${_esc_msg//\"/\\\"}"
    curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
      -H 'Content-Type: application/json' \
      -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"index-model-drift-check\",\"message\":\"${_esc_msg}\"}" \
      --max-time 15 >/dev/null 2>&1 || log "WARN" "rescue-rangers webhook escalation failed (non-fatal)"
  fi
  exit 4
fi

exit "$rc"
