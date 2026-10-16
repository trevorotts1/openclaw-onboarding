// Shared timeline compiler (Directive MG-021). See
// references/timeline-compiler.md for the model, the rounding rule,
// the slot and handle doctrine, and the adapter consumption contract
// for MG-022 and MG-023.

export * from "./types";
export * from "./samples";
export { compileTimeline, type CompileResult } from "./compile";
export {
  toRemotionTiming,
  toHyperframesTiming,
  type RemotionSceneTiming,
  type RemotionTiming,
  type HyperframesSceneTiming,
  type HyperframesTiming,
} from "./engines";
