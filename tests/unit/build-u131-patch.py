#!/usr/bin/env python3
"""build-u131-patch.py: Patch weekly-batch.sh with U131 zero-work-idle heartbeat."""
import sys, os, subprocess

def main():
    if len(sys.argv) != 4:
        print("Usage: build-u131-patch.py <src> <dst> <fake_cycle_path>", file=sys.stderr)
        sys.exit(1)

    src, dst, fake = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(src, 'r') as f:
        content = f.read()

    old_marker = (
        "err()  { printf '[%s] [Skill35-batch][ERR ] %s\\n' "
        '"$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }\n\n'
        'case "${1:-}" in'
    )

    injection = (
        "err()  { printf '[%s] [Skill35-batch][ERR ] %s\\n' "
        '"$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }\n\n'
        "# --- Exit codes:\n"
        "#   0  = work done (one or more topics published)\n"
        "#   10 = zero-work idle (no calendar or no entries due)\n"
        "#   4+ = error (4=missing cycle script, 6=publishing failure)\n"
        "ZERO_WORK_EXIT=10\n\n"
        "# Zero-work heartbeat file (written every idle batch)\n"
        'IDLE_HEARTBEAT="$OPENCLAW_DIR/data/skill35/last-zero-work-heartbeat"\n'
        'HEARTBEAT_DIR="$(dirname "$IDLE_HEARTBEAT")"\n'
        'mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true\n\n'
        "write_idle_heartbeat() {\n"
        "  local now_iso\n"
        '  now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"\n'
        "  printf '{\"status\":\"idle\",\"reason\":\"%s\",\"timestamp\":\"%s\",\"batch_version\":\"%s\"}\\n' \\\n"
        '    "${1:-no-calendar}" "$now_iso" "$SCRIPT_VERSION" > "$IDLE_HEARTBEAT" 2>/dev/null || true\n'
        '  log "zero-work heartbeat written to $IDLE_HEARTBEAT (reason: ${1:-no-calendar})"\n'
        "}\n\n"
        'case "${1:-}" in'
    )

    assert old_marker in content, "marker 1 (err + case)"
    content = content.replace(old_marker, injection, 1)

    assert "Exiting 0 (nothing to do today)." in content, "marker 2 (exit msg)"
    content = content.replace(
        "Exiting 0 (nothing to do today).",
        "Exiting $ZERO_WORK_EXIT (nothing to do today -- idle heartbeat).",
        1
    )

    old_no_cal = "EOF\n  exit 0\nfi\n\n# ---------- parse + filter"
    new_no_cal = (
        "EOF\n"
        '  write_idle_heartbeat "no-calendar"\n'
        "  exit $ZERO_WORK_EXIT\n"
        "fi\n\n# ---------- parse + filter"
    )
    assert old_no_cal in content, "marker 3 (no-cal exit block)"
    content = content.replace(old_no_cal, new_no_cal, 1)

    old_no_match = (
        'log "calendar present but no entries match the current week. Nothing to do."\n'
        "  exit 0\n"
        "fi"
    )
    new_no_match = (
        'log "calendar present but no entries match the current week. Nothing to do."\n'
        '  write_idle_heartbeat "no-matching-entries"\n'
        "  exit $ZERO_WORK_EXIT\n"
        "fi"
    )
    assert old_no_match in content, "marker 4 (no-match exit)"
    content = content.replace(old_no_match, new_no_match, 1)

    assert 'CYCLE_SCRIPT="$SCRIPT_DIR/run-publishing-cycle.sh"' in content, "marker 5 (CYCLE_SCRIPT)"
    content = content.replace(
        'CYCLE_SCRIPT="$SCRIPT_DIR/run-publishing-cycle.sh"',
        f'CYCLE_SCRIPT="{fake}"',
        1
    )

    assert "ZERO_WORK_EXIT" in content, "ZERO_WORK_EXIT missing"
    assert "write_idle_heartbeat" in content, "write_idle_heartbeat missing"
    assert "$ZERO_WORK_EXIT" in content, "$ZERO_WORK_EXIT reference missing"

    with open(dst, 'w') as f:
        f.write(content)
    os.chmod(dst, 0o755)

    r = subprocess.run(['bash', '-n', dst], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"SYNTAX ERROR:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Patched: {dst}")

if __name__ == '__main__':
    main()
