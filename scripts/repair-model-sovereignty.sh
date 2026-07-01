#!/usr/bin/env bash
# repair-model-sovereignty.sh — retro-fix existing "no model" / "openrouter/free"
# agents + tasks on a box, per the PREFERENCE CASCADE (PLAN.md §8).
#
# WHAT IT FIXES (idempotent):
#   - openclaw.json agents whose primary model is null / a bare string-with-no-
#     fallbacks / the free sentinel / a forbidden (Anthropic) model -> re-resolves
#     a real, modality-correct, cascade-ordered dept-default model.
#   - Emits a CC-side repair payload (model-sweep receipt) listing every
#     agent_settings dept-default + tasks.model_id offender the CC repair driver
#     (command-center/scripts/repair-model-defaults.ts) must rewrite.
#   - Re-runs the AF-MODEL-SOVEREIGNTY gate over the box; the box is only marked
#     clean when the gate returns clean.
#
# DESIGN (per memory):
#   - PER-BOX receipt file (/tmp/model-sweep/<box>.json) — NEVER a shared ledger
#     appended by many concurrent agents (that loses writes).
#   - Idempotent: safe to re-run; skips agents already sovereign.
#   - Intended to run DETACHED on the box (the fleet driver SSHes, kicks this off
#     with nohup/at, and EXITS — never babysits). This script itself does only
#     local work on the box it runs on.
#   - Does NOT restart the gateway over SSH (N-rule: never `gateway restart` on a
#     rescue Mac over SSH). It only edits openclaw.json + writes a receipt; the
#     caller decides when/how to reload.
#
# USAGE (on the box):
#   repair-model-sovereignty.sh [--config <openclaw.json>] [--box <name>] \
#       [--receipt-dir /tmp/model-sweep] [--apply] [--shared-utils <dir>]
#
#   Without --apply it runs in DRY-RUN (reports offenders + planned fixes, writes
#   the receipt, changes nothing). With --apply it rewrites openclaw.json (after a
#   timestamped .bak) and re-runs the gate.
#
# EXIT: 0 = clean (or dry-run found nothing) ; 3 = offenders remain after repair ;
#       2 = could not locate config / shared-utils.
set -euo pipefail

CONFIG=""
BOX="$(hostname -s 2>/dev/null || echo box)"
RECEIPT_DIR="/tmp/model-sweep"
APPLY=0
SHARED_UTILS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="${2:-}"; shift 2;;
    --box) BOX="${2:-}"; shift 2;;
    --receipt-dir) RECEIPT_DIR="${2:-}"; shift 2;;
    --apply) APPLY=1; shift;;
    --shared-utils) SHARED_UTILS="${2:-}"; shift 2;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "[repair] unknown arg: $1" >&2; exit 2;;
  esac
done

# ── Locate openclaw.json ──
if [ -z "$CONFIG" ]; then
  for c in "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$c" ] && CONFIG="$c" && break
  done
fi
if [ -z "$CONFIG" ] || [ ! -f "$CONFIG" ]; then
  echo "[repair] FATAL: no openclaw.json found (use --config)" >&2; exit 2
fi

# ── Locate shared-utils (select_model.py + assert_model_sovereignty.py) ──
if [ -z "$SHARED_UTILS" ]; then
  for d in \
    "$HOME/Downloads/openclaw-master-files/shared-utils" \
    "$HOME/.openclaw/skills/shared-utils" \
    "$(cd "$(dirname "$0")/../shared-utils" 2>/dev/null && pwd)"; do
    if [ -n "$d" ] && [ -f "$d/select_model.py" ] && [ -f "$d/assert_model_sovereignty.py" ]; then
      SHARED_UTILS="$d"; break
    fi
  done
fi
if [ -z "$SHARED_UTILS" ] || [ ! -f "$SHARED_UTILS/select_model.py" ]; then
  echo "[repair] FATAL: cannot find shared-utils (select_model.py)" >&2; exit 2
fi

mkdir -p "$RECEIPT_DIR"
RECEIPT="$RECEIPT_DIR/${BOX}.json"

echo "[repair] box=$BOX config=$CONFIG apply=$APPLY shared-utils=$SHARED_UTILS" >&2

# Timestamped backup path — used by BOTH the Python apply (backup-before-write)
# and the post-apply `openclaw config validate` restore below. The Python step
# creates this file ONLY when it actually mutates the config.
TS="$(date +%Y%m%d-%H%M%S)"
BAK="${CONFIG}.bak-model-sweep-${TS}"

# ── The work is in Python (JSON-safe edits + the cascade + the gate) ──
# errexit is relaxed ONLY around the python call so a non-zero gate rc (3 =
# offenders remain) is captured into $rc instead of aborting BEFORE the
# post-apply validate/restore can run.
set +e
SHARED_UTILS="$SHARED_UTILS" CONFIG="$CONFIG" BOX="$BOX" RECEIPT="$RECEIPT" APPLY="$APPLY" BAK="$BAK" \
python3 - <<'PY'
import json, os, sys, datetime, shutil
sys.path.insert(0, os.environ["SHARED_UTILS"])
import select_model as sm
import assert_model_sovereignty as gate

CONFIG = os.environ["CONFIG"]
BOX = os.environ["BOX"]
RECEIPT = os.environ["RECEIPT"]
APPLY = os.environ["APPLY"] == "1"
BAK = os.environ.get("BAK") or (CONFIG + ".bak-model-sweep")

with open(CONFIG) as f:
    cfg = json.load(f)

FREE = set(sm.FREE_SENTINELS)


def _should_strip(slug):
    """The SOLE sovereignty-strip predicate. A slug is stripped iff it is:
      - a free sentinel (openrouter/free / free / openrouter/auto:free), OR
      - forbidden (Anthropic — FORBIDDEN_PREFIXES), OR
      - any `-preview` slug.
    It NEVER matches a legitimate OpenAI / OpenRouter / Gemini (non-preview)
    model, so a client's own providers/chains are preserved untouched.
    """
    if not slug or not str(slug).strip():
        return False
    s = str(slug).strip().lower()
    if s in FREE:
        return True
    if sm._is_forbidden(s):
        return True
    if "-preview" in s:
        return True
    return False


# Full inventory already excludes FORBIDDEN (via _is_forbidden inside
# _list_available_models). Drop preview/free too, so a re-resolved PRIMARY can
# never be a preview/free model AND so a `-preview` primary is treated as
# not-in-inventory (→ re-resolved). This is the box's OWN inventory — nothing
# foreign is ever introduced.
full_inventory = sm._list_available_models(cfg)
inventory = [m for m in full_inventory if not _should_strip(m)]


def is_offender(primary):
    if not primary or not str(primary).strip():
        return "NULL_MODEL"
    p = str(primary).strip().lower()
    if p in FREE:
        return "FREE_DEFAULT"
    if sm._is_forbidden(p):
        return "FORBIDDEN"
    if "-preview" in p:
        return "PREVIEW"
    if inventory and primary not in inventory:
        return "NOT_IN_INVENTORY"
    return None


def primary_of(model_field):
    if isinstance(model_field, str):
        return model_field
    if isinstance(model_field, dict):
        return model_field.get("primary") or model_field.get("model")
    return None


def fallbacks_of(model_field):
    if isinstance(model_field, dict):
        fb = model_field.get("fallbacks")
        if isinstance(fb, list):
            return fb
    return None


def dept_of_agent(agent_id):
    # dept-<slug> -> <slug> ; otherwise treat the id as the dept hint
    aid = agent_id or ""
    return aid[5:] if aid.startswith("dept-") else aid


MAX_DEPTH = 3

openclaw_fixes = []   # PRIMARY re-resolutions we apply to openclaw.json on this box
cc_payload = {        # what the CC repair driver must rewrite in the CC DB
    "agent_settings_dept_defaults": [],   # offending dept defaults to re-resolve
    "tasks_model_id": [],                 # offending tasks to re-resolve (CC-side only)
}
fallback_scrubs = []  # [{location, removed:[...]}] — forbidden/preview/free pruned from fallbacks[]
depth_caps = []       # [{location, from, to}]      — runaway cascades capped to MAX_DEPTH
strip_actions = {     # provider/plugin BLOCK strip
    "providers_removed": [],       # models.providers.* keys removed
    "plugin_entries_removed": [],  # plugins.entries.* keys removed
    "plugins_allow_removed": [],   # entries pulled from plugins.allow[]
}

changed = 0  # count of mutations actually written (APPLY only) — governs the write


def _scrub_fallbacks(fb, location):
    """Remove forbidden/preview/free entries from a fallbacks list (order-preserving).
    Legitimate models are kept verbatim. Returns (kept, removed)."""
    kept, removed = [], []
    for item in fb:
        if isinstance(item, str) and _should_strip(item):
            removed.append(item)
        else:
            kept.append(item)
    if removed:
        fallback_scrubs.append({"location": location, "removed": removed})
    return kept, removed


def _process_model_field(holder, key, location, dept_hint):
    """Strip/scrub/cap/re-resolve one model field at holder[key] (mutates in place
    only when APPLY). Handles PRIMARY (offender → re-resolve from the box's own
    inventory) and fallbacks[] (scrub forbidden/preview/free, then cap depth)."""
    global changed
    mf = holder.get(key)
    if mf is None:
        return

    primary = primary_of(mf)
    fb = fallbacks_of(mf)
    orig_fb = list(fb) if isinstance(fb, list) else []

    # (1) scrub fallbacks — always safe, and applied EVEN WHEN the primary is
    #     already valid (today those arrays are never inspected).
    if orig_fb:
        scrubbed_fb, _removed = _scrub_fallbacks(orig_fb, location)
    else:
        scrubbed_fb = []

    # (2) primary offender → re-resolve. Resolver FIRST (Ollama-first cascade over
    #     the box's OWN inventory); if the box has nothing the cascade classifies
    #     (e.g. an OpenAI/OpenRouter/Gemini-only box), PROMOTE the box's own next
    #     surviving fallback — NEVER inject a foreign (e.g. Ollama) model. Only if
    #     neither yields a model do we fall through to owner-input.
    code = is_offender(primary)
    new_primary = primary
    needs_owner = False
    if code:
        res = sm.resolve_dept_default_model(dept_hint, inventory=inventory)
        cand = res.get("model_id")
        if cand and not res.get("needs_owner_input"):
            new_primary = cand
            resolution = "resolver"
        elif scrubbed_fb:
            new_primary = scrubbed_fb[0]
            scrubbed_fb = scrubbed_fb[1:]
            resolution = "promote_own_fallback"
        else:
            needs_owner = True
            resolution = "needs_owner_input"
        rec = {
            "agent": location, "location": location, "department": dept_hint,
            "old": primary, "offense": code,
            "new": (None if needs_owner else new_primary),
            "resolution": resolution,
            "tier": res.get("tier"),
            "required_modality": res.get("required_modality"),
            "needs_owner_input": needs_owner,
        }
        openclaw_fixes.append(rec)
        # CC dept-default row to rewrite (role_id IS NULL, setting_type='model').
        # Only real department agents carry a dept row; defaults/subagents don't.
        if location.startswith("agents.list["):
            cc_payload["agent_settings_dept_defaults"].append({
                "department": dept_hint,
                "model_id": (None if needs_owner else new_primary),
                "setting_type": "model", "role_id": None,
                "needs_owner_input": needs_owner,
            })

    # (3) drop any fallback identical to the (possibly new) primary
    if new_primary:
        np = str(new_primary).strip().lower()
        scrubbed_fb = [x for x in scrubbed_fb
                       if not (isinstance(x, str) and x.strip().lower() == np)]

    # (4) cap runaway cascades to MAX_DEPTH
    if len(scrubbed_fb) > MAX_DEPTH:
        depth_caps.append({"location": location,
                           "from": len(scrubbed_fb), "to": MAX_DEPTH})
        scrubbed_fb = scrubbed_fb[:MAX_DEPTH]

    primary_changed = (code is not None) and (not needs_owner) and (new_primary != primary)
    fb_changed = (scrubbed_fb != orig_fb)
    if not primary_changed and not fb_changed:
        return  # idempotent no-op for this field

    if not APPLY:
        return  # dry-run: recorded above, mutate nothing

    # (5) write back, preserving shape
    if isinstance(mf, dict):
        if primary_changed:
            mf.pop("model", None)
            mf["primary"] = new_primary
        if isinstance(fb, list) or scrubbed_fb:
            mf["fallbacks"] = scrubbed_fb
        holder[key] = mf
    else:
        # original was a bare string primary
        holder[key] = ({"primary": new_primary, "fallbacks": scrubbed_fb}
                       if scrubbed_fb else new_primary)
    changed += 1


def _strip_provider_and_plugins():
    """(a) Strip the Anthropic provider/plugin BLOCK: models.providers.anthropic,
    any anthropic plugins.entries.* entry, and "anthropic" in plugins.allow[]."""
    global changed
    mb = cfg.get("models")
    if isinstance(mb, dict):
        provs = mb.get("providers")
        if isinstance(provs, dict) and "anthropic" in provs:
            strip_actions["providers_removed"].append("anthropic")
            if APPLY:
                del provs["anthropic"]
                changed += 1
    pb = cfg.get("plugins")
    if isinstance(pb, dict):
        entries = pb.get("entries")
        if isinstance(entries, dict):
            for name in list(entries.keys()):
                ent = entries[name]
                is_anthropic = (str(name).strip().lower() == "anthropic")
                if not is_anthropic and isinstance(ent, dict):
                    for k in ("provider", "type", "name", "module", "package", "id"):
                        v = ent.get(k)
                        if isinstance(v, str) and "anthropic" in v.strip().lower():
                            is_anthropic = True
                            break
                if is_anthropic:
                    strip_actions["plugin_entries_removed"].append(name)
                    if APPLY:
                        del entries[name]
                        changed += 1
        allow = pb.get("allow")
        if isinstance(allow, list):
            new_allow = [x for x in allow
                         if not (isinstance(x, str) and x.strip().lower() == "anthropic")]
            if len(new_allow) != len(allow):
                strip_actions["plugins_allow_removed"].append("anthropic")
                if APPLY:
                    pb["allow"] = new_allow
                    changed += 1


# ── (a) provider/plugin block strip ──
_strip_provider_and_plugins()

# ── (b)/(c)/(d) primary re-resolve + fallback scrub + depth cap across
#     agents.defaults.model, agents.defaults.subagents.model, every
#     agents.list[*].model AND its subagents.model ──
agents = cfg.setdefault("agents", {})
if isinstance(agents, dict):
    defaults = agents.get("defaults")
    if isinstance(defaults, dict):
        _process_model_field(defaults, "model", "agents.defaults.model", "")
        _sub = defaults.get("subagents")
        if isinstance(_sub, dict):
            _process_model_field(_sub, "model", "agents.defaults.subagents.model", "")
    alist = agents.get("list")
    if isinstance(alist, list):
        for a in alist:
            if not isinstance(a, dict):
                continue
            aid = a.get("id", "?")
            _process_model_field(a, "model", f"agents.list[{aid}].model", dept_of_agent(aid))
            _sub = a.get("subagents")
            if isinstance(_sub, dict):
                _process_model_field(_sub, "model",
                                     f"agents.list[{aid}].subagents.model", dept_of_agent(aid))

wrote = False
if APPLY and changed:
    # Back up the ORIGINAL config byte-for-byte BEFORE rewriting (file on disk is
    # still the original — cfg is mutated only in memory until now).
    shutil.copy2(CONFIG, BAK)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    wrote = True
    print(f"[repair] applied {changed} mutation(s); backup -> {BAK}", file=sys.stderr)

# ── Re-run the gate over the (possibly repaired) config — ground truth ──
offenders_after, scanned = gate.scan_config(CONFIG)

_planned = (len(openclaw_fixes)
            + sum(len(v) for v in strip_actions.values())
            + len(fallback_scrubs) + len(depth_caps))

receipt = {
    "box": BOX,
    "config": CONFIG,
    "ts": datetime.datetime.now().isoformat(),
    "apply": APPLY,
    "inventory_count": len(inventory),
    "openclaw_fixes_planned": openclaw_fixes,
    "strip_actions": strip_actions,
    "fallback_scrubs": fallback_scrubs,
    "depth_caps": depth_caps,
    "cc_repair_payload": cc_payload,
    "gate_scanned": len(scanned),
    "gate_offenders_after": offenders_after,
    "clean": not offenders_after,
    "mutations_applied": changed if APPLY else 0,
    "backup": BAK if wrote else None,
}
with open(RECEIPT, "w") as f:
    json.dump(receipt, f, indent=2)
print(f"[repair] receipt -> {RECEIPT} (clean={not offenders_after}, "
      f"planned_actions={_planned}, primary_fixes={len(openclaw_fixes)}, "
      f"providers_stripped={len(strip_actions['providers_removed'])}, "
      f"plugin_entries_stripped={len(strip_actions['plugin_entries_removed'])}, "
      f"fallback_scrubs={len(fallback_scrubs)}, depth_caps={len(depth_caps)}, "
      f"cc_dept_defaults={len(cc_payload['agent_settings_dept_defaults'])})", file=sys.stderr)

sys.exit(0 if not offenders_after else 3)
PY
rc=$?
set -e

# ── Post-apply schema validation (restore backup on non-zero) ──────────────
# Runs ONLY when we APPLIED and actually wrote (the Python step creates $BAK
# only when it mutated the config). `openclaw config validate` checks the live
# default config — the same file edited in place here. On failure, restore the
# byte-for-byte backup so a bad edit can never leave the box unbootable, and
# force a non-clean rc. NO gateway restart/reload here — the caller reloads.
if [ "$APPLY" = "1" ] && [ -f "$BAK" ]; then
  if command -v openclaw >/dev/null 2>&1; then
    if openclaw config validate >/dev/null 2>&1; then
      echo "[repair] openclaw config validate PASS after apply" >&2
    else
      echo "[repair] openclaw config validate FAILED after apply — restoring $BAK" >&2
      cp "$BAK" "$CONFIG"
      rc=2
    fi
  else
    echo "[repair] openclaw not on PATH — skipping post-apply config validate (edits left in place)" >&2
  fi
fi

echo "[repair] done (rc=$rc). receipt: $RECEIPT" >&2
exit $rc
