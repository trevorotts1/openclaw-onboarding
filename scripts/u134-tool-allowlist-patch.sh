#!/usr/bin/env bash
# u134-tool-allowlist-patch.sh -- U134: Fleet-wide tool allowlist config-patch.
set -euo pipefail
HOOKS_LIB="${0%/*}/../hooks/lib-ceo-tool-gate.sh"
source "$HOOKS_LIB" || { echo "ERROR: lib-ceo-tool-gate.sh not found" >&2; exit 1; }
if [ -f /data/.openclaw/openclaw.json ]; then OC_ROOT=/data/.openclaw; OC_USER=node
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then OC_ROOT="$HOME/.openclaw"; OC_USER=$(whoami)
else echo "ERROR: cannot find openclaw.json" >&2; exit 1; fi
OC_CONFIG="$OC_ROOT/openclaw.json"
OC_BACKUP="$OC_CONFIG.bak-tool-allowlist-$(date +%Y%m%d%H%M%S)"
cp "$OC_CONFIG" "$OC_BACKUP"
APPLY_RESULT="$(CEO_GATE_DENY="${CEO_GATE_DENY_TOOLS[*]}" CEO_GATE_ALLOW="${CEO_GATE_ALLOW_TOOLS[*]}" CEO_GATE_MCP="${CEO_GATE_MCP_PROVIDERS[*]}" python3 - "$OC_CONFIG" <<'PY'
import json,os,sys
from pathlib import Path
cfg_path=Path(sys.argv[1])
cfg=json.loads(cfg_path.read_text())
before=json.dumps(cfg,sort_keys=True,indent=2)
DENY=os.environ.get("CEO_GATE_DENY","").split()
ALLOW=os.environ.get("CEO_GATE_ALLOW","").split()
MCP=os.environ.get("CEO_GATE_MCP","").split()
ROUTER_IDS={"main","ceo","dept-ceo","master-orchestrator","dept-master-orchestrator","dept-executive-office"}
def is_router(a):
    if not isinstance(a,dict): return False
    if a.get("is_master") is True: return True
    if isinstance(a.get("role"),str) and a.get("role").strip().lower()=="router": return True
    return a.get("id") in ROUTER_IDS
def consent_active():
    cands=[os.environ.get("CEO_CONSENT_FILE",""),"/data/.openclaw/state/ceo-consent.json",os.path.join(os.path.expanduser("~"),".openclaw/state/ceo-consent.json")]
    for c in filter(None,cands):
        try:
            if json.load(open(c)).get("granted") is True: return True
        except: continue
    return False
if consent_active(): print("STATUS: tool-allowlist=CONSENT_SKIP"); sys.exit(0)
agents=cfg.get("agents",{}).get("list",[]) or []
main=next((a for a in agents if isinstance(a,dict) and a.get("default") is True),None)
if main is None: main=next((a for a in agents if isinstance(a,dict) and a.get("id")=="main"),None)
if main is None: print("STATUS: tool-allowlist=NO_MAIN_AGENT"); sys.exit(0)
if not is_router(main): print("STATUS: tool-allowlist=PA_SKIP"); sys.exit(0)
agent=main;aid=agent.get("id","<unknown>")
tools=agent.setdefault("tools",{})
deny=tools.setdefault("deny",[])
if not isinstance(deny,list): deny=[];tools["deny"]=deny
db=list(deny)
for t in DENY:
    if t not in deny: deny.append(t)
allow=tools.setdefault("allow",[])
if not isinstance(allow,list): allow=[];tools["allow"]=allow
ab=list(allow)
for t in ALLOW:
    if t not in allow: allow.append(t)
tools["allow"]=[t for t in allow if t not in set(deny)]
bp=tools.setdefault("byProvider",{})
if not isinstance(bp,dict): bp={};tools["byProvider"]=bp
bb=dict(bp)
for p in MCP:
    if p: bp[p]={"deny":["*"]}
after=json.dumps(cfg,sort_keys=True,indent=2)
if before==after:
    print("STATUS: tool-allowlist=CANONICAL")
else:
    cfg_path.write_text(json.dumps(cfg,indent=2)+"\n")
    da=[t for t in deny if t not in db]
    aa=[t for t in allow if t not in ab]
    bc=bp!=bb
    det=[]
    if da: det.append(f"deny+={da}")
    if aa: det.append(f"allow+={aa}")
    if bc: det.append("byProvider refreshed")
    print(f"STATUS: tool-allowlist=APPLIED details={' '.join(det)} agent={aid}")
PY
)" || true
[ "$OC_ROOT" = "/data/.openclaw" ] && chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
case "$APPLY_RESULT" in
  *CONSENT_SKIP*) echo "[u134] consent skip" ;;
  *PA_SKIP*) echo "[u134] PA skip" ;;
  *NO_MAIN_AGENT*) echo "[u134] no main agent" ;;
  *CANONICAL*) echo "[u134] already canonical" ;;
  *APPLIED*) echo "[u134] APPLIED" ;;
  *) echo "[u134] unexpected: $APPLY_RESULT" ;;
esac
echo "$APPLY_RESULT"
if echo "$APPLY_RESULT" | grep -qE 'CANONICAL|APPLIED'; then
  if command -v openclaw >/dev/null 2>&1; then
    if ! openclaw config validate 2>&1; then
      echo "STATUS: tool-allowlist=VALIDATE_FAILED"
      cp "$OC_BACKUP" "$OC_CONFIG"
      [ "$OC_ROOT" = "/data/.openclaw" ] && chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
      exit 1
    fi
  fi
fi
echo "[u134] done"
