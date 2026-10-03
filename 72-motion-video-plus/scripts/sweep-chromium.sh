#!/usr/bin/env bash
# Skill 72 orphan sweep.
#
# Runs at the end of every motion-video-plus run. Kills any headless
# Chromium processes this pipeline left behind and reports the memory freed.
# Headless only, always: this script never touches a visible browser.
#
# It matches only processes whose command line contains BOTH --headless and
# the pipeline's user-data-dir marker, so an operator's own visible Chrome
# is never a target.
set -u
MARKER="${1:-mvplus}"  # user-data-dir marker passed by the run driver
freed_kb=0
killed=0
while read -r pid rss cmd; do
  case "$cmd" in
    *--headless*"$MARKER"*)
      freed_kb=$((freed_kb + rss)); killed=$((killed + 1))
      kill -9 "$pid" 2>/dev/null || true
      ;;
  esac
done < <(ps -eo pid=,rss=,args= 2>/dev/null | grep -E 'chrom|chrome' | grep -v grep || true)
freed_mb=$((freed_kb / 1024))
echo "sweep: killed $killed orphaned Chromium process(es), freed ~${freed_mb}MB"
# A second pass one second later catches slow exits; report only.
sleep 1
left=$(ps -eo args= 2>/dev/null | grep -E 'chrom|chrome' | grep -- "--headless" | grep -c "$MARKER" || true)
echo "sweep: $left matching process(es) remain"
