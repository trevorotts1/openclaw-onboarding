# n8n Workflow: command-center-register (v4)

This is the n8n webhook workflow at `https://main.blackceoautomations.com/webhook/command-center-register-v3` that Trevor's BlackCEO automation hub runs to provision new Command Center tunnels.

## The bug we found in v3 (fixed in v4 — 2026-05-24)

The v3 SSH command did `cloudflared tunnel create` + `route dns` + `tunnel token` but NEVER set tunnel **ingress** config. Token-based tunnels (`cloudflared tunnel run --token X`) use Cloudflare's remote-managed config — if ingress is empty, the tunnel returns HTTP 503 from CF edge even when the connector is healthy. Every client onboarded under v3 hit this: tunnel created, DNS resolved, connector connected, but the URL never served the dashboard.

This was confirmed by inspecting older tunnels in Trevor's CF account: the OLD working pattern was a single shared `command-center` tunnel where each new client was added as another hostname under that tunnel's ingress. When v3 switched to per-client tunnels, the ingress step got lost.

## The v4 fix

One curl call inserted between `route dns` and `tunnel token` in the SSH command, calling Cloudflare's PUT `/configurations` API to set ingress for the newly-created tunnel. Maps `<client>.zerohumanworkforce.com → http://localhost:4000` (where the Mission Control dashboard runs).

## Required env vars on main.blackceoautomations.com (the n8n SSH target)

The new curl call needs two env vars in the SSH user's shell environment:

- `CLOUDFLARE_ACCOUNT_ID` — Trevor's main CF account ID
- `CLOUDFLARE_API_TOKEN` — CF API token scoped to `Account > Cloudflare Tunnel: Edit`

For non-interactive SSH (which n8n uses), these typically need to live in `~/.profile` or `~/.ssh/environment` (with `PermitUserEnvironment yes` in `/etc/ssh/sshd_config`). Bash `~/.bashrc` is often NOT sourced on non-interactive sessions.

## The complete v4 SSH command

```bash
CLIENT="{{ $('Webhook: Client Registration').item.json.body.clientName }}"
cloudflared tunnel create $CLIENT > /dev/null 2>&1
TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$CLIENT" | awk '{print $1}' | head -1)
cloudflared tunnel route dns -f $TUNNEL_ID ${CLIENT}.zerohumanworkforce.com > /dev/null 2>&1

# v4 — set tunnel ingress so CF edge routes to dashboard on :4000
curl -sS -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"config\":{\"ingress\":[{\"hostname\":\"${CLIENT}.zerohumanworkforce.com\",\"service\":\"http://localhost:4000\"},{\"service\":\"http_status:404\"}]}}" > /dev/null

TOKEN=$(cloudflared tunnel token $TUNNEL_ID 2>/dev/null)
echo "TUNNEL_ID=$TUNNEL_ID"
echo "TUNNEL_TOKEN=$TOKEN"
echo "SUBDOMAIN=${CLIENT}.zerohumanworkforce.com"
```

## v5 fix — MERGE, don't full-replace (shared-tunnel wrong-port / CF 1303) — HELD FOR OPERATOR GO

**Symptom:** on several boxes the Command Center public link 502s, and some throw
Cloudflare **1303 "no route to your origin"**. The dashboard is up locally on
`:4000`, but the tunnel's ingress for `<client>.zerohumanworkforce.com` either has
no rule (→ 1303) or points at the wrong localhost port (→ 502).

**Root cause:** the v4 curl above does a **full-replace** PUT — it sets the tunnel
ingress to `[{<client> → :4000}, {404}]` and nothing else. On the fleet's
one-tunnel-per-box model, that single tunnel also carries sibling hostnames — the
OpenClaw gateway (`…-hooks → 127.0.0.1:18789`) and the podcast board
(`…-podcast → localhost:4010`). Because CF's PUT `/configurations` **replaces the
entire ingress array**, whichever writer runs *last* wins and silently deletes the
others' rules:
- The gateway tunnel writer (Skill-38 `13-create-cloudflare-tunnel.sh`, now fixed to
  merge) full-replacing → drops the CC's `:4000` rule → CC goes **1303**, or a
  still-routed host now maps to `:18789` → CC **502s** (the "wrong localhost port").
- This v4 workflow full-replacing → drops the gateway/podcast rules the other way.

**Fix (v5):** GET the current config, MERGE the CC host at the authoritative
`:4000`, keep every other hostname rule, keep exactly one `http_status:404` last —
then PUT. Same shape as the podcast provisioner (Skill-58) and
`shared-utils/cc-tunnel-ingress.sh`. Replace the single v4 curl with:

```bash
# v5 — MERGE ingress (preserve sibling hostname rules; CC host authoritative on :4000)
CUR=$(curl -sS "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")
PUT_BODY=$(printf '%s' "$CUR" | python3 -c '
import json,sys,os
cur=json.load(sys.stdin); host=os.environ["CLIENT"]+".zerohumanworkforce.com"
cfg=((cur.get("result") or {}).get("config") or {})
ing=[r for r in (cfg.get("ingress") or []) if r.get("hostname") and r["hostname"]!=host]
ing=[r for r in ing if r.get("hostname")]                    # keep sibling host rules
ing.append({"hostname":host,"service":"http://localhost:4000"})  # CC host -> authoritative :4000
ing.append({"service":"http_status:404"})                    # exactly one catch-all, last
print(json.dumps({"config":dict(cfg,ingress=ing)}))')
# GUARD: refuse to PUT if the CC host is not on :4000 (fail loud, do not clobber)
echo "$PUT_BODY" | python3 -c '
import json,sys,os
host=os.environ["CLIENT"]+".zerohumanworkforce.com"
ing=json.load(sys.stdin)["config"]["ingress"]
m=[r for r in ing if r.get("hostname")==host]
assert m and m[0]["service"]=="http://localhost:4000", "CC ingress not on :4000 — refusing to PUT"'
curl -sS -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json" \
  -d "$PUT_BODY" > /dev/null
```

**This is a repo/doc change only — NOT yet applied to the live n8n workflow.** The
live workflow (`i0P3OWCEsXZxVo0N`) still runs v4 full-replace until the operator
elects to roll v5 with the rotation playbook below.

## Backfill for tunnels created under v3 (one-time, on main.blackceoautomations.com)

```bash
ACCT="$CLOUDFLARE_ACCOUNT_ID"
TOKEN="$CLOUDFLARE_API_TOKEN"
curl -sS "https://api.cloudflare.com/client/v4/accounts/$ACCT/cfd_tunnel?per_page=50" \
  -H "Authorization: Bearer $TOKEN" | \
  python3 -c '
import json, sys, urllib.request, os
acct=os.environ["CLOUDFLARE_ACCOUNT_ID"]; tok=os.environ["CLOUDFLARE_API_TOKEN"]
for t in json.load(sys.stdin).get("result",[]):
    if t.get("deleted_at"): continue
    tid, name = t["id"], t["name"]
    cfg = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        headers={"Authorization": f"Bearer {tok}"})))
    ing = ((cfg.get("result") or {}).get("config") or {}).get("ingress") or []
    if [r for r in ing if r.get("hostname")]:
        print(f"  SKIP {name}: ingress already set")
        continue
    body = json.dumps({"config":{"ingress":[
        {"hostname": f"{name}.zerohumanworkforce.com", "service": "http://localhost:4000"},
        {"service": "http_status:404"}
    ]}}).encode()
    json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        data=body, method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type":"application/json"})))
    print(f"  PATCHED {name}")'
```

Applied this against the operator account on 2026-05-24 — patched 2 broken v3-era tunnels (fleet clients). Both went 503 → 200 after their cloudflared connectors picked up the new remote config.

---

## Option B chosen — credentials inline (Trevor's instance, 2026-05-24)

Trevor's live n8n workflow at `i0P3OWCEsXZxVo0N` uses **Option B**: the Cloudflare account ID + API token are written directly into the SSH command string in the n8n workflow JSON, rather than referenced as `${CLOUDFLARE_ACCOUNT_ID}` / `${CLOUDFLARE_API_TOKEN}` env vars on the SSH target host.

**Tradeoff:** no server-side setup needed (no env vars on `main.blackceoautomations.com`), but the CF token is visible inside the n8n workflow JSON to anyone with read access to the workflow.

### Token rotation playbook

If the Cloudflare API token (currently `cfut_...`) is ever rotated, revoked, or expires, the n8n workflow MUST be updated with the new token value. **Symptom of stale token: new client registrations succeed at the webhook level (tunnel created, DNS routed, token returned) but tunnel ingress is silently empty — the new `<client>.zerohumanworkforce.com` URL returns HTTP 503 from Cloudflare edge.** (Identical to the v3 bug we fixed in v4.)

To re-PUT the workflow with a new token, use the n8n API:

```bash
N8N_BASE="https://main.blackceoautomations.com"
N8N_KEY="<n8n API key from Settings → API>"
WF_ID="i0P3OWCEsXZxVo0N"

# 1. Pull current workflow
curl -sS "$N8N_BASE/api/v1/workflows/$WF_ID" -H "X-N8N-API-KEY: $N8N_KEY" > /tmp/wf.json

# 2. Edit the SSH node's command — replace the OLD bearer token with the NEW one
python3 << 'PY'
import json, urllib.request, urllib.error, os
NEW_TOKEN = "<new cfut_... token>"  # paste new token here
wf = json.load(open("/tmp/wf.json"))
for n in wf["nodes"]:
    if n.get("name") == "Create Tunnel + DNS + Token":
        cmd = n["parameters"]["command"]
        # Replace ANY existing Bearer cfut_... value with new one
        import re
        cmd = re.sub(r'Bearer cfut_[A-Za-z0-9]+', f'Bearer {NEW_TOKEN}', cmd)
        n["parameters"]["command"] = cmd
        print("patched SSH command")
        break

# 3. PUT it back
body = {k: v for k, v in wf.items() if k in {"name","nodes","connections","settings","staticData"}}
body.setdefault("settings", {})
req = urllib.request.Request(
    f"{os.environ['N8N_BASE']}/api/v1/workflows/{os.environ['WF_ID']}",
    data=json.dumps(body).encode(),
    method="PUT",
    headers={"X-N8N-API-KEY": os.environ['N8N_KEY'], "Content-Type": "application/json"})
print("updatedAt:", json.load(urllib.request.urlopen(req))["updatedAt"])
PY

# 4. Verify by firing a test webhook + checking ingress on the new tunnel
curl -sS -X POST "https://main.blackceoautomations.com/webhook/command-center-register-v3" \
  -H "Content-Type: application/json" \
  -d '{"clientName":"rotation-test","companyName":"Test","contactEmail":"test@test"}'
# Then in your CF dashboard: confirm rotation-test tunnel has ingress rule for
# rotation-test.zerohumanworkforce.com → http://localhost:4000
```

### Better long-term: migrate to Option A (env vars)

Less risk of credential drift if you migrate. Steps:
1. On `main.blackceoautomations.com`, set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in `~/.profile` (or `~/.ssh/environment` with `PermitUserEnvironment yes` in sshd_config — non-interactive SSH does NOT source `~/.bashrc`).
2. Verify: `ssh root@main.blackceoautomations.com 'echo $CLOUDFLARE_ACCOUNT_ID'` returns the value.
3. Re-PUT the n8n workflow with the original env-var-referencing SSH command (saved at `/tmp/n8n-wf-before-optionB.json` on Trevor's Mac as of 2026-05-24, or reconstruct from the doc above).

### Snapshots saved 2026-05-24 (Trevor's Mac, `/tmp/`)

- `n8n-wf-before.json` — v3 (no ingress curl) — original broken state
- `n8n-wf-before-optionB.json` — v4 with env-var refs — before going to Option B
- Live workflow as of 2026-05-24T04:56:37Z — v4 Option B (inline creds)
