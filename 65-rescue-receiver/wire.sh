#!/usr/bin/env bash
# 65-rescue-receiver/wire.sh — idempotent box-side wiring for the RR coaching poll.
# Registers the */2-minute command cron ONLY when the box is enrolled
# (RR_RECEIVER_URL + RR_BOX_TOKEN present in <ocroot>/secrets/.env).
set -u

_OCROOT=""
[ -d /data/.openclaw ] && _OCROOT="/data/.openclaw"
[ -z "$_OCROOT" ] && [ -d "$HOME/.openclaw" ] && _OCROOT="$HOME/.openclaw"
[ -n "$_OCROOT" ] || { echo "65-rescue-receiver: no openclaw root; nothing to wire" >&2; exit 0; }
_SECRETS="$_OCROOT/secrets/.env"
_POLL="$_OCROOT/skills/65-rescue-receiver/rescue-poll.sh"

if [ ! -f "$_SECRETS" ] || [ ! -f "$_POLL" ]; then
  echo "65-rescue-receiver: secrets file or rescue-poll.sh missing; nothing to wire" >&2
  exit 0
fi

set -a; . "$_SECRETS" 2>/dev/null; set +a
if [ -z "${RR_RECEIVER_URL:-}" ] || [ -z "${RR_BOX_TOKEN:-}" ]; then
  echo "65-rescue-receiver: box not enrolled (RR_RECEIVER_URL / RR_BOX_TOKEN absent) — poll cron NOT registered" >&2
  exit 0
fi

_NAME="rescue-rr-box-poll"
command -v openclaw >/dev/null 2>&1 || { echo "65-rescue-receiver: openclaw CLI not found" >&2; exit 1; }
if openclaw cron list --json 2>/dev/null | grep -q "\"name\": *\"$_NAME\""; then
  echo "65-rescue-receiver: cron $_NAME already registered"
  exit 0
fi
openclaw cron add --name "$_NAME" --cron "*/2 * * * *" --no-deliver --command "sh $_POLL" >&2 \
  || openclaw cron add --name "$_NAME" --cron "*/2 * * * *" --command "sh $_POLL" >&2 \
  || { echo "65-rescue-receiver: cron add FAILED" >&2; exit 1; }
echo "65-rescue-receiver: registered cron $_NAME (*/2) -> sh $_POLL"
