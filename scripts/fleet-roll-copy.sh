#!/bin/sh
# fleet-roll-copy.sh — keep the fleet roll's OWN copy of the onboarding repo on a box.
#
# fleet-refresh.sh sends this script to every box (run inside the container on
# Docker boxes) before it runs the runner. The roll runs from ONE dedicated clone,
# owned by the roll, refreshed to origin/main every time:
#
#     <OpenClaw root>/fleet-refresh/onboarding
#     (OpenClaw root: $OPENCLAW_ROOT, else /data/.openclaw, else ~/.openclaw)
#
# so it never depends on whatever old clone a box happens to have (a shallow,
# tag-only or detached clone broke the roll). The client's own clones are never
# read, changed or deleted. Only this dedicated directory is ever replaced, and
# only when it is not a clone of the onboarding repo.
#
# Also writes <OpenClaw root>/fleet-refresh/client.json ({"client", "label"})
# when FLEET_CLIENT_JSON is set, so the box can name its client itself.
#
# Prints one line:  COPY <cloned|updated> <previous sha or -> <path>
#              or:  COPYFAIL <reason>
# scripts/weekly-full-update.sh (a box's own Sunday update) keeps the same copy
# with the same steps.
U="${FLEET_ROLL_REPO_URL:-https://github.com/trevorotts1/openclaw-onboarding.git}"
B="${OPENCLAW_ROOT:-}"
[ -n "$B" ] || { if [ -d /data/.openclaw ]; then B=/data/.openclaw; else B="$HOME/.openclaw"; fi; }
R="$B/fleet-refresh/onboarding"
if [ -e "$R" ] && [ "$(git -C "$R" remote get-url origin 2>/dev/null)" != "$U" ]; then
  rm -rf "$R"
fi
PREV=$(git -C "$R" rev-parse HEAD 2>/dev/null || true)
if [ -d "$R/.git" ]; then
  git -C "$R" fetch -q --depth 1 origin +refs/heads/main:refs/remotes/origin/main >&2 \
    && git -C "$R" checkout -q -B main origin/main >&2 \
    && git -C "$R" reset -q --hard origin/main >&2 \
    || { echo "COPYFAIL could not refresh $R from GitHub"; exit 0; }
  S=updated
else
  mkdir -p "$B/fleet-refresh" \
    && git clone -q --depth 1 --single-branch --branch main "$U" "$R" >&2 \
    || { echo "COPYFAIL could not clone the onboarding repo to $R"; exit 0; }
  S=cloned
fi
[ -f "$R/shared-utils/fleet_refresh_runner.py" ] || { echo "COPYFAIL $R has no runner"; exit 0; }
# Who this box belongs to, so the box's own Sunday update names its client
# ("Client Name (Platform)") instead of its hostname. Set by fleet-refresh.sh.
if [ -n "${FLEET_CLIENT_JSON:-}" ]; then
  printf '%s\n' "$FLEET_CLIENT_JSON" > "$B/fleet-refresh/client.json"
fi
echo "COPY $S ${PREV:--} $R"
