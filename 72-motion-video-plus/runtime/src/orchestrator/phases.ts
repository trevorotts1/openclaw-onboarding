// Lifecycle phase states (MG-025, Directive Section 16.8).
//
// The orchestrator tracks a job through the exact Section 16.8 states.
// The gates in gate.ts are the transitions that require approvals:
// DESIGN_APPROVED (design gate), PREVIEW_APPROVED (render gate), and
// the delivery decision after FINAL_QC_PASSED (delivery gate). No
// final-render gate depends on QC of output it has not yet created,
// and no delivery gate accepts preview QC alone: the delivery gate
// requires final QC evidence for the actual final artifact. Fixture
// execution follows the same states with test-only authority and
// diagnostic evidence; it never reaches a production DELIVERED state.

export const PHASES = [
  "CREATED",
  "SCHEMA_VALID",
  "INPUTS_READY",
  "DESIGN_APPROVED",
  "SCENES_READY",
  "PREVIEW_READY",
  "PREVIEW_APPROVED",
  "FINAL_RENDERED",
  "FINAL_QC_PASSED",
  "PACKAGED",
  "DELIVERED",
] as const;

export type Phase = (typeof PHASES)[number];

/** The phase a passed gate admits the job to. */
export const GATE_PHASES = {
  design: "DESIGN_APPROVED",
  render: "PREVIEW_APPROVED",
  delivery: "FINAL_QC_PASSED",
} as const satisfies Record<string, Phase>;

/** True when `phase` is at or beyond `target` in the lifecycle order. */
export function phaseAtLeast(phase: Phase, target: Phase): boolean {
  return PHASES.indexOf(phase) >= PHASES.indexOf(target);
}
