#!/usr/bin/env bash
# tunnel-takeover-guard.sh
# -----------------------------------------------------------------------------
# Refuse to hand a box a SECOND cloudflared connector token when another tunnel
# already owns that box's public hostnames.
#
# WHY THIS EXISTS (fleet incident 2026-11-06, two boxes at once)
#   A Mac can run exactly one useful connector per installed service, and the
#   installer paths write the SAME token file:
#       /Library/Application Support/com.cloudflare.cloudflared/token
#   Two installers each believed they owned the box:
#       * 38-conversational-ai-system/.../13-create-cloudflare-tunnel.sh
#         (operator installs it with `sudo cloudflared service install <TOKEN>`,
#          which writes com.cloudflare.cloudflared.plist + that token file)
#       * 32-command-center-setup/scripts/setup-tunnel-daemon.sh
#         (writes com.cloudflare.command-center.plist + its own token file)
#   Whichever ran last took the live connector. The other tunnel went to
#   0 connections while DNS still pointed at it, so the client's Command Center
#   and Council links were dead AFTER a successful Cloudflare Access login
#   (CF 1033 / 502). two client boxes both hit it.
#
# WHAT IT CHECKS (read-only; no writes, no sudo, no secret ever printed)
#   A. LOCAL  — every installed cloudflared service on this box, and the tunnel
#      id inside its token file. A DIFFERENT id than the one being installed
#      means the box is already connected to another tunnel.
#   B. CLOUD  — (only when CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID are set)
#      other tunnels that carry a hostname under the same parent domain AND have
#      live connectors. Those hostnames are the ones that would go dark.
#
# USAGE (source it)
#   source "<repo>/shared-utils/tunnel-takeover-guard.sh"
#   guard_tunnel_takeover "$TUNNEL_ID" "$PARENT_DOMAIN" || exit 11
#
# Override: FORCE_TUNNEL_TAKEOVER=1 — operator has decided to displace the
# existing connector on purpose. Never set it inside a script.
# -----------------------------------------------------------------------------
set -uo pipefail

TTG_MAC_TOKEN_FILE="/Library/Application Support/com.cloudflare.cloudflared/token"
TTG_MAC_PLIST_DIR="${TTG_LAUNCHD_DIR:-/Library/LaunchDaemons}"
TTG_MAC_AGENT_DIR="${TTG_AGENT_DIR:-${HOME:-/root}/Library/LaunchAgents}"

# tunnel id embedded in a cloudflared connector token (base64 JSON, key "t").
# Prints the id, or nothing. Never prints the token itself.
ttg_token_tunnel_id() {
  local f="${1:-}" out
  [[ -r "$f" ]] || return 0
  out="$(python3 - "$f" <<'PY' 2>/dev/null
import base64, json, sys
try:
    raw = open(sys.argv[1], "rb").read().strip()
    j = json.loads(base64.b64decode(raw))
    tid = j.get("t") or ""
    if isinstance(tid, str) and len(tid) == 36:
        print(tid)
except Exception:
    pass
PY
)"
  printf '%s' "$out"
}

# Same, but for a token supplied on stdin (never written to disk first).
# Uses `python3 -c` so stdin stays the pipe (a heredoc would consume it).
ttg_token_tunnel_id_stdin() {
  python3 -c '
import base64, json, sys
try:
    raw = sys.stdin.read().strip().encode()
    j = json.loads(base64.b64decode(raw))
    tid = j.get("t") or ""
    if isinstance(tid, str) and len(tid) == 36:
        print(tid)
except Exception:
    pass
' 2>/dev/null
}

# Installed cloudflared services on this box: prints "<label>\t<token-file>".
# Parsed with plistlib — a `sed` for "any string containing 'token'" matches
# the literal `--token-file` flag and yields a path that does not exist, which
# makes every box look conflict-free. That is the bug this guard exists for.
ttg_installed_services() {
  python3 -c '
import os, plistlib, sys
fallback = sys.argv[1]
for d in sys.argv[2:]:
    if not os.path.isdir(d):
        continue
    for name in sorted(os.listdir(d)):
        if not name.endswith(".plist"):
            continue
        if "cloudflare" not in name and "tunnel" not in name:
            continue
        p = os.path.join(d, name)
        tok = ""
        try:
            with open(p, "rb") as fh:
                pl = plistlib.load(fh)
            args = pl.get("ProgramArguments") or []
            for i, a in enumerate(args):
                if a == "--token-file" and i + 1 < len(args):
                    tok = args[i + 1]
                    break
            if not tok:
                env = pl.get("EnvironmentVariables") or {}
                tok = env.get("TUNNEL_TOKEN_FILE") or env.get("CLOUDFLARE_TUNNEL_TOKEN") or ""
        except Exception:
            tok = ""
        print("%s\t%s" % (name[:-6], tok or fallback))
' "$TTG_MAC_TOKEN_FILE" "$TTG_MAC_PLIST_DIR" "$TTG_MAC_AGENT_DIR" 2>/dev/null
}

# guard_tunnel_takeover <new-tunnel-id> [parent-domain]
guard_tunnel_takeover() {
  local new_id="${1:-}" domain="${2:-}"
  [[ -n "$new_id" ]] || { echo "TTG: missing tunnel id" >&2; return 2; }

  local conflicts="" label tokf tid
  while IFS=$'\t' read -r label tokf; do
    [[ -n "${label:-}" ]] || continue
    tid="$(ttg_token_tunnel_id "$tokf")"
    [[ -n "$tid" ]] || continue
    [[ "$tid" == "$new_id" ]] && continue
    conflicts="${conflicts}  local service '${label}' is connected to tunnel ${tid}"$'\n'
  done < <(ttg_installed_services)

  # Cloud-side: tunnels carrying hostnames under this parent domain, with connectors.
  local cloud=""
  if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -n "${CLOUDFLARE_ACCOUNT_ID:-}" && -n "$domain" ]]; then
    cloud="$(CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" \
             CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID" \
             TTG_NEW_ID="$new_id" TTG_DOMAIN="$domain" python3 - <<'PY' 2>/dev/null
import json, os, urllib.request
tok = os.environ["CLOUDFLARE_API_TOKEN"]
acc = os.environ["CLOUDFLARE_ACCOUNT_ID"]
new_id = os.environ["TTG_NEW_ID"]
dom = os.environ["TTG_DOMAIN"]
def api(u):
    r = urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(r, timeout=20) as x:
        return json.loads(x.read())
base = "https://api.cloudflare.com/client/v4/accounts/" + acc
try:
    tunnels = api(base + "/cfd_tunnel?is_deleted=false&per_page=200").get("result") or []
except Exception:
    raise SystemExit(0)
for t in tunnels:
    if t.get("id") == new_id:
        continue
    conns = t.get("connections") or []
    if not conns:
        continue
    try:
        cfg = api(base + "/cfd_tunnel/" + t["id"] + "/configurations")
    except Exception:
        continue
    ing = ((cfg.get("result") or {}).get("config") or {}).get("ingress") or []
    hosts = [i.get("hostname") for i in ing
             if i.get("hostname") and i["hostname"].endswith("." + dom)]
    if hosts:
        print("  tunnel '%s' (%s) has %d live connector(s) and carries: %s"
              % (t.get("name"), t["id"], len(conns), ", ".join(hosts)))
PY
)"
  fi

  if [[ -z "$conflicts" && -z "$cloud" ]]; then
    return 0
  fi

  if [[ "${FORCE_TUNNEL_TAKEOVER:-0}" == "1" ]]; then
    echo "TTG: FORCE_TUNNEL_TAKEOVER=1 — displacing the existing connector on purpose." >&2
    return 0
  fi

  {
    echo "TUNNEL-TAKEOVER-GUARD FAIL: this box already serves public hostnames from another tunnel."
    [[ -n "$conflicts" ]] && printf '%s' "$conflicts"
    [[ -n "$cloud" ]] && printf '%s\n' "$cloud"
    echo "  Installing tunnel ${new_id} here would leave the hostnames above at 0 connectors —"
    echo "  the link still answers Cloudflare Access, then fails with CF 1033 / 502."
    echo "  Correct fix: keep ONE tunnel for this box and merge the hostnames into its ingress"
    echo "  (shared-utils/cc-tunnel-ingress.sh), or re-point DNS to the tunnel that stays."
    echo "  Deliberate displacement: re-run with FORCE_TUNNEL_TAKEOVER=1."
  } >&2
  return 11
}
