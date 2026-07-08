#!/usr/bin/env bash
# 59-anthology-engine/preflight.sh -- resolve the engine tier map per box.
# ----------------------------------------------------------------------------
# Reads config/model-map.template.json and writes a resolved model-map.json into
# the run dir (or the skill dir if no --run-dir), keeping each capability TIER
# (HEAVY-WRITER / LIGHT / JUDGE / LONGCTX / IMAGE) and its ordered provider chain.
# It performs the REAL per-box resolution: it reads the CLIENT's OWN configured
# models from their openclaw.json (agents.defaults.model / agents.list[].model /
# models.list[]) and resolves each tier to the client's OWN strongest matching
# model via the fleet's single source of truth shared-utils/select_model.py -- the
# same mechanism Skills 52/53 preflight and Skill 23 build-workforce use. It NEVER
# bakes a default model id, NEVER substitutes the client's expressed choice, and
# FAILS CLOSED (exit 2) when a REQUIRED tier has no resolvable client model or the
# client has configured no usable model at all. Credentials are referenced by LABEL
# only. It NEVER writes an Anthropic-family id and NEVER an operator key.
#
# MODES:
#   (default) RESOLVE -- resolve every tier from the client's OWN openclaw.json and
#                        write model-map.json into OUT_DIR (fail-closed, never a
#                        <CLIENT_*> placeholder and never a guessed default).
#   --check           -- PRE-GATE: read an existing OUT_DIR/model-map.json and
#                        fail-closed if it still carries <CLIENT_*> placeholders
#                        (AF-AE-UNRESOLVED-MODELMAP) or an Anthropic-family id
#                        (AF-AE-ANTHROPIC). A missing map is a clean pass (the
#                        installer resolves per box).
#
# Exit 0 = ok; 2 = banned id / residual placeholder (fail-closed); 3 = usage.
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TEMPLATE="$SELF_DIR/config/model-map.template.json"
OUT_DIR="$SELF_DIR"
MODE="resolve"
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) OUT_DIR="${2:-}"; shift 2 ;;
        --check)   MODE="check"; shift ;;
        -h|--help) echo "usage: preflight.sh [--run-dir DIR] [--check]"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 3 ;;
    esac
done
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required" >&2; exit 3; }

if [ "$MODE" = "check" ]; then
    OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
mp = os.path.join(os.environ["OUT_DIR"], "model-map.json")
if not os.path.isfile(mp):
    print("  preflight --check: no resolved model-map.json (installer resolves per box) -- OK")
    sys.exit(0)
try:
    blob = open(mp, "r", encoding="utf-8").read()
    data = json.loads(blob)
except Exception as exc:
    print("AF-AE-UNRESOLVED-MODELMAP: model-map.json unreadable/invalid: %s" % exc, file=sys.stderr)
    sys.exit(2)
residual = sorted(set(re.findall(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>", blob)))
if residual:
    print("AF-AE-UNRESOLVED-MODELMAP: model-map.json still carries placeholder(s): %s"
          % ", ".join(residual), file=sys.stderr)
    sys.exit(2)
# Deny Anthropic-family identifiers. The banned id shapes are assembled from
# fragments so no contiguous banned literal ever lives in this file.
_a = "anthro" + "pic"
_c = "clau" + "de-"
banned = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)
def scan(node, path):
    if isinstance(node, dict):
        for k, v in node.items():
            scan(v, path + "." + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        if banned.search(node):
            print("AF-AE-ANTHROPIC: resolved map carries a banned id at %s: %r" % (path, node), file=sys.stderr)
            sys.exit(2)
scan(data.get("tiers", {}), "tiers")
print("  preflight --check: resolved model-map.json OK (no residual placeholder, no Anthropic-family id)")
sys.exit(0)
PY
    exit $?
fi

[ -f "$TEMPLATE" ] || { echo "FATAL: template not found: $TEMPLATE" >&2; exit 3; }

# --------------------------------------------------------------------------
# RESOLVE the CLIENT's OWN configured models into the tier chains. This is the
# per-box resolution the fleet performs everywhere else (Skills 52/53 preflight,
# Skill 23 build-workforce): read the client's openclaw.json, take the models the
# CLIENT configured (agents.defaults.model / agents.list[].model / models.list[]),
# and resolve each capability tier to the client's OWN strongest matching model
# via the fleet's single source of truth shared-utils/select_model.py. It NEVER
# bakes a default model id and NEVER substitutes the client's expressed choice; a
# REQUIRED tier with no resolvable client model FAILS CLOSED (exit 2). Credentials
# are referenced by LABEL only (a label is not a secret; the value stays in the
# client env). NEVER an Anthropic-family id; NEVER an operator key.
# --------------------------------------------------------------------------
# Locate the fleet shared-utils (select_model.py) -- repo checkout first, then the
# installed-skills mirrors. Absence is a HARD fail: we resolve real client models
# or we fail closed; we never fall back to writing <CLIENT_*> placeholders.
SELECT_MODEL_DIR=""
for _d in "$SELF_DIR/../shared-utils" \
          "$HOME/.openclaw/skills/shared-utils" \
          "/data/.openclaw/skills/shared-utils" \
          "$HOME/Downloads/openclaw-master-files/shared-utils"; do
    if [ -f "$_d/select_model.py" ]; then SELECT_MODEL_DIR="$(cd "$_d" && pwd)"; break; fi
done

# The client's openclaw.json: an explicit OPENCLAW_CONFIG override (used by the
# regression test and the fleet installer), else the standard per-box locations.
OPENCLAW_CFG="${OPENCLAW_CONFIG:-}"
if [ -z "$OPENCLAW_CFG" ]; then
    for _c in "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
        [ -f "$_c" ] && { OPENCLAW_CFG="$_c"; break; }
    done
fi

TEMPLATE="$TEMPLATE" OUT_DIR="$OUT_DIR" SELECT_MODEL_DIR="$SELECT_MODEL_DIR" \
OPENCLAW_CFG="$OPENCLAW_CFG" python3 - <<'PY'
import json, os, re, sys

TEMPLATE = os.environ["TEMPLATE"]
OUT_DIR = os.environ["OUT_DIR"]
SMDIR = os.environ.get("SELECT_MODEL_DIR", "")
CFG = os.environ.get("OPENCLAW_CFG", "").strip() or None

# Anthropic-family deny shape, assembled from fragments so this file carries no
# contiguous banned literal (mirrors model_router.py + the --check block above).
_a = "anthro" + "pic"
_c = "clau" + "de-"
banned = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)

tmpl = json.load(open(TEMPLATE, encoding="utf-8"))
tiers_tmpl = tmpl.get("tiers", {})

# Defense in depth: the shipped template must itself never carry an Anthropic id.
if banned.search(json.dumps(tiers_tmpl)):
    print("AF-AE-ANTHROPIC: template carries a banned id (refusing to resolve)", file=sys.stderr)
    sys.exit(2)

# The fleet's single source of truth for reading + resolving the client's own model.
if not SMDIR or not os.path.isfile(os.path.join(SMDIR, "select_model.py")):
    print("AF-AE-UNRESOLVED-MODELMAP: fleet shared-utils/select_model.py not found "
          "(searched the repo checkout and the installed-skills mirrors); cannot resolve "
          "the client's OWN configured models. The engine never writes a guessed default.",
          file=sys.stderr)
    sys.exit(2)
sys.path.insert(0, SMDIR)
import select_model as sm  # noqa: E402

# The exact fields the fleet harvests as the client's OWN configured models
# (agents.defaults.model, agents.list[].model, models.list[]); forbidden
# (Anthropic) ids are already filtered by _list_available_models.
cfg = sm._load_openclaw_config(CFG)
inventory = [m for m in sm._list_available_models(cfg)
             if m and m.strip().lower() not in sm.FREE_SENTINELS]

# Fail closed when the client has configured NO usable model at all -- the engine
# never substitutes a hardcoded default (client-sovereignty; mirrors select_model's
# needs_owner_input and Skills 52/53 preflight hard-fail).
if not inventory:
    print("AF-AE-UNRESOLVED-MODELMAP: the client has configured NO usable (non-Anthropic, "
          "non-free) model in openclaw.json (%s). The engine never substitutes a default; "
          "configure the client's OWN model(s) and re-run."
          % (CFG or "no config found"), file=sys.stderr)
    sys.exit(2)

# anthology provider -> (credential LABEL, slotting, base URL or None). LABEL only,
# never a value. Mirrors model_router.py's provider surface + credential aliases.
PROVIDER_META = {
    "ollama-cloud": ("OLLAMA_API_KEY", "baseUrl", "https://ollama.com/v1"),
    "openrouter":   ("OPENROUTER_API_KEY", "apiKey", None),
    "gemini":       ("GOOGLE_API_KEY", "apiKey", None),
    "minimax":      ("MINIMAX_API_KEY", "apiKey", None),
    "deepseek":     ("DEEPSEEK_API_KEY", "apiKey", None),
    "kimi":         ("KIMI_API_KEY", "apiKey", None),
}


def to_link(fleet_id):
    """Map ONE of the client's OWN fleet-namespaced model ids to an anthology chain
    link, deriving the provider + provider-native model string from the client's id
    (so the resolved chain uses exactly the providers the CLIENT configured). Returns
    None for a provider the anthology router does not carry (e.g. an OAuth GPT id)."""
    mid = fleet_id.strip()
    low = mid.lower()
    if low.startswith("ollama/") or low.startswith("ollama-cloud/"):
        prov, native = "ollama-cloud", mid.split("/", 1)[1]
    elif low.startswith("openrouter/"):
        prov, native = "openrouter", mid.split("/", 1)[1]
    elif low.startswith("gemini/") or low.startswith("google/gemini") or low.startswith("gemini-"):
        prov, native = "gemini", (mid.split("/", 1)[1] if "/" in mid else mid)
    elif low.startswith("minimax/") or low.startswith("minimax-"):
        prov, native = "minimax", (mid.split("/", 1)[1] if "/" in mid else mid)
    elif low.startswith("deepseek/") or low.startswith("deepseek-"):
        prov, native = "deepseek", (mid.split("/", 1)[1] if "/" in mid else mid)
    elif low.startswith("kimi/") or low.startswith("moonshot") or low.startswith("kimi-"):
        prov, native = "kimi", (mid.split("/", 1)[1] if "/" in mid else mid)
    else:
        return None
    if banned.search(native) or banned.search(mid):   # defense in depth
        return None
    cred, slot, base = PROVIDER_META[prov]
    link = {"provider": prov, "model": native, "credential_label": cred, "slotting": slot}
    if base:
        link["baseUrl"] = base
    return link


def ordered_for_purpose(purpose, context="normal"):
    """The client's OWN models matching a select_model purpose cascade, in the
    fleet's preference order (highest version per slot), deduped."""
    out = []
    for entry in sm.CHAINS.get(purpose, {}).get(context, []):
        m = sm._best_match_in_position(inventory, entry)
        if m and m not in out:
            out.append(m)
    return out


def client_best():
    """The client's overall strongest configured model (heavy -> mid -> fast),
    else a deterministic pick from the inventory. Used so a REQUIRED tier whose own
    purpose chain matched nothing still resolves to one of the CLIENT's OWN models
    rather than failing (sovereign: the client's model, never a substituted default)."""
    for p in ("heavy", "mid", "fast"):
        got = ordered_for_purpose(p)
        if got:
            return got[0]
    return sorted(inventory)[0]


TIER_PURPOSE = {"HEAVY-WRITER": "heavy", "LIGHT": "fast", "JUDGE": "mid", "LONGCTX": "heavy"}
REQUIRED = {"HEAVY-WRITER", "LIGHT", "JUDGE"}

resolved_tiers = {}
unresolved_required = []

for name, t in tiers_tmpl.items():
    if name == "IMAGE":
        # S7 covers route through cover_render.py / Kie (never model_router). Keep
        # the IMAGE tier ONLY if the client configured an image-generation model;
        # otherwise DROP it (SPEC/Skill-54 degrade: the cover ships as a prompt doc).
        imgs = [m for m in inventory if sm.model_has_modality(m, "image_generation")]
        if not imgs:
            continue
        m = imgs[0]
        native = m.split("/", 1)[1] if "/" in m else m
        link = {"order": 1, "provider": "kie", "model": native, "credential_label": "KIE_API_KEY"}
        tmpl_links = t.get("chain", [])
        if tmpl_links and isinstance(tmpl_links[0], dict):
            for k in ("endpoint", "via"):
                if tmpl_links[0].get(k):
                    link[k] = tmpl_links[0][k]
        nt = {k: v for k, v in t.items() if k != "chain"}
        nt["chain"] = [link]
        resolved_tiers[name] = nt
        continue

    purpose = TIER_PURPOSE.get(name, "mid")
    context = "large" if name == "LONGCTX" else "normal"
    ordered = ordered_for_purpose(purpose, context)
    if name in REQUIRED and not ordered:
        ordered = [client_best()]

    links, seen = [], set()
    for fid in ordered:
        link = to_link(fid)
        if not link:
            continue
        key = (link["provider"], link["model"])
        if key in seen:
            continue
        seen.add(key)
        link["order"] = len(links) + 1
        links.append(link)

    if not links:
        if name in REQUIRED:
            unresolved_required.append(name)
        # optional tier (e.g. LONGCTX): drop it -> S9 chunks on HEAVY-WRITER.
        continue

    # Carry the template primary's maxTokens onto the resolved primary.
    tmpl_links = t.get("chain", [])
    if tmpl_links and isinstance(tmpl_links[0], dict) and tmpl_links[0].get("maxTokens"):
        links[0]["maxTokens"] = tmpl_links[0]["maxTokens"]
    # Preserve the durable HOLD sentinel terminus if the template tier carried one.
    for tl in tmpl_links:
        if isinstance(tl, dict) and str(tl.get("provider", "")).upper() == "HOLD":
            links.append({"order": len(links) + 1, "provider": "HOLD",
                          "model": tl.get("model", "durable HOLD + one deduped founder alert")})
            break

    nt = {k: v for k, v in t.items() if k != "chain"}
    nt["chain"] = links
    resolved_tiers[name] = nt

if unresolved_required:
    print("AF-AE-UNRESOLVED-MODELMAP: no client model resolves for REQUIRED tier(s): %s. "
          "The engine never substitutes a default; configure the client's OWN model(s) and "
          "re-run. Client models discovered: %s"
          % (", ".join(sorted(unresolved_required)), ", ".join(inventory) or "(none)"),
          file=sys.stderr)
    sys.exit(2)

resolved = {
    "skill": "anthology-engine",
    "resolved_per_box": True,
    "note": "Resolved from the CLIENT's OWN configured models (openclaw.json) via the fleet "
            "shared-utils/select_model.py. NEVER an Anthropic-family id, NEVER operator keys, "
            "NEVER a substituted default; credentials are referenced by LABEL only.",
    "deny_policy": tmpl.get("deny_policy", {}),
    "tiers": resolved_tiers,
    "no_formatter_tier": True,
}

# Final fail-closed audit: no residual placeholder, no Anthropic id.
blob = json.dumps(resolved)
residual = sorted(set(re.findall(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>", blob)))
if residual:
    print("AF-AE-UNRESOLVED-MODELMAP: resolver left placeholder(s): %s" % ", ".join(residual),
          file=sys.stderr)
    sys.exit(2)
if banned.search(blob):
    print("AF-AE-ANTHROPIC: resolved map carries a banned id (refusing to write)", file=sys.stderr)
    sys.exit(2)

out = os.path.join(OUT_DIR, "model-map.json")
json.dump(resolved, open(out, "w"), indent=2)
print("  resolved model-map.json ->", out)
for name, t in resolved_tiers.items():
    chain = " -> ".join(l.get("provider", "?") for l in t.get("chain", []))
    print("   tier %-13s -> %s (client's OWN models)" % (name, chain))
PY
rc=$?
[ "$rc" -eq 0 ] && echo "preflight: PASS (client's own models resolved into every REQUIRED tier; no Anthropic-family id)"
exit "$rc"
