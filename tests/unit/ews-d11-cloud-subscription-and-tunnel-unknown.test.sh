#!/usr/bin/env bash
# tests/unit/ews-d11-cloud-subscription-and-tunnel-unknown.test.sh
# D11: the Early Warning System (skill 60) raised a permanent false P1 for an Ollama Cloud
# (":cloud", a subscription per billing-models.json) fallback, and a false S7 "tunnel down"
# on boxes that never had cloudflared. Offline, hermetic, fixture HOME only.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export EWS_SCRIPTS="$REPO_ROOT/60-zhc-early-warning-system/scripts"
python3 -I - <<'PY'
import os, sys, tempfile
sys.path.insert(0, os.environ["EWS_SCRIPTS"])
import ews_sentinel as S, ews_common as C
sig = C.load_signatures()
fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond: fails.append(name)
def s1(live):
    d = [{"class": "model", "changed": True, "direction": "changed", "path": "agents.defaults.model", "live_value": live}]
    return S.sig_s1(d, "client", sig)[0]["severity"]
check("S1: ollama :cloud fallback on a client box is NOT P1", s1(["glm-5.2", "ollama-cloud/glm-5.3:cloud"]) == "P2")
check("S1: metered openrouter fallback on a client box is still P1", s1(["glm-5.2", "openrouter/glm-5.2"]) == "P1")
ev = lambda m: [{"modelId": m}]
check("S2: runtime :cloud model outside allowlist is NOT P1",
      all(f["severity"] != "P1" for f in S.sig_s2(["glm-5.2"], ev("ollama-cloud/glm-5.3:cloud"), "client", sig)))
check("S2: runtime metered openrouter model outside allowlist is still P1",
      any(f["severity"] == "P1" for f in S.sig_s2(["glm-5.2"], ev("openrouter/glm-5.2"), "client", sig)))
with tempfile.TemporaryDirectory() as h:
    nodaemon = os.path.join(h, "none", "*cloudflared*")
    check("S7: box with no cloudflared token/config/pm2 app/daemon -> not configured", S.tunnel_configured(h, nodaemon) is False)
    check("S7: tunnel=unknown raises no tunnel finding", S.sig_s7({"gateway": "up", "tunnel": "unknown"}) == [])
    os.makedirs(os.path.join(h, ".cloudflared"))
    open(os.path.join(h, ".cloudflared", "config.yml"), "w").close()
    check("S7: a ~/.cloudflared config makes the tunnel configured", S.tunnel_configured(h, nodaemon) is True)
check("S7: a configured tunnel that is down still raises P2",
      S.sig_s7({"gateway": "up", "tunnel": "down"})[0]["key_path"] == "surface.tunnel")
sys.exit(1 if fails else 0)
PY
