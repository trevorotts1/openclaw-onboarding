#!/usr/bin/env bash
# Council of Wise Elders (77): wave-gate entry point.
# The onboarding wave gate (lib-onboarding-state.sh, oc_gate_skill)
# resolves a skill's canonical QC script at the SKILL ROOT as
# qc-<SKILL.md name>.sh. The canonical script for this skill lives in
# scripts/ per the portable package layout; this root file is only the
# gate's entry point and delegates to it unchanged, so there is one
# source of truth: scripts/qc-council-of-wise-elders.sh.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/qc-council-of-wise-elders.sh" "$@"
