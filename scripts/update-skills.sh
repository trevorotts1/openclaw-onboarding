#!/usr/bin/env bash
# RETIRED: scripts/update-skills.sh is not an updater. Never execute legacy bodies.
# Compatibility path retained so old callers fail clearly without mutating anything.
cat >&2 <<'RETIRED_NOTICE'
RETIRED: this secondary updater path does not apply updates.
Canonical source: https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh
That URL identifies source for review, not an instruction to execute a download.
On this compact installation, use ~/.openclaw/skills/.update-restart-if-needed --stage-only
to collect a candidate, then follow the canonical References 4 Bootstrap/writer-review-procedure.md.
No files, configuration, schedules or services were changed. No update was applied.
RETIRED_NOTICE
exit 1
