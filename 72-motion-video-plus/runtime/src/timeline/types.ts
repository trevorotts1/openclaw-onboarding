// Timeline compiler types (Directive MG-021, Sections 5.4 and 16).
//
// The compiler is the single place where picture and sound durations are
// turned into placed frame ranges. Scenes, transitions, captions,
// narration, and SFX never do their own duration arithmetic again: they
// declare durations, overlaps, and cues, and this module compiles the one
// authoritative plan.
//
// Two documents come out of a successful compile:
//
// - timeline: the canonical contracts document (references/
//   contracts-v2.schema.json, $defs/timeline). It carries placed scene
//   ranges, transition frame counts, cue events, the parent slot, and the
//   total frame count. It is validated against the canonical schema
//   before it leaves the compiler.
// - sidecar: the compiler record defined here (TimelineSidecar). The
//   canonical timeline $def has no room for overlap ownership, cue anchor
//   kinds, audio sample positions, narration and caption sample ranges,
//   source-media ranges, or declared property-write overlaps, so those
//   facts live in the sidecar, keyed to the canonical document by job id
//   and scene id. See references/timeline-compiler.md for the field-by-
//   field account of what lives where and why.
//
// All internal time is integer frames in half-open intervals
// [startFrame, endFrameExclusive) (Section 5.4). Seconds and samples are
// produced only at the export boundary (engines.ts, samples.ts).

import type { Timeline } from "../validation/generated-types";

/** The compiled timeline's audio sample rate. See samples.ts for why
 * 48000 Hz is the rate and why frame positions convert exactly. */
export const TIMELINE_SAMPLE_RATE = 48000;

/** The one rounding rule for sub-frame positions (samples.ts). */
export const TIMELINE_ROUNDING_RULE = "round_half_up" as const;

export type AnchorKind = "spoken_word" | "semantic_state" | "music_beat";

/** Cue types, identical to the canonical timeline events enum. */
export type CueType = "reveal_start" | "proof" | "hold_start" | "cue";

export type AudioOwner = "none" | "parent" | "self";

/** "program": a full program whose total duration is whatever the scenes
 * and their explicitly allocated overlaps produce. "slot": a fixed-
 * duration insert that must fill its parent slot exactly. */
export type CompileMode = "program" | "slot";

export interface FrameRangeInput {
  startFrame: number;
  endFrameExclusive: number;
}

export interface SceneInput {
  id: string;
  /** Content duration in frames at the job fps. */
  durationFrames: number;
  /** First frame of this scene's source media. Default 0. */
  sourceStartFrame?: number;
  /** Available source media length in frames. Default: exactly the
   * frames the scene consumes (durationFrames). A shorter declared
   * source is a compile failure, never a silent stretch. */
  sourceDurationFrames?: number;
}

export interface TransitionInput {
  id: string;
  /** The scene before the boundary. Must be immediately followed by
   * toSceneId in the scenes array. */
  fromSceneId: string;
  toSceneId: string;
  /** Overlap length in frames. The overlap is subtracted exactly once,
   * when the to-scene is placed; the two scenes never each subtract it
   * (Section 5.4). */
  frames: number;
  /** The one owner of this overlap (Section 5.4: each overlap has
   * exactly one owner). Must be fromSceneId or toSceneId. */
  ownerSceneId: string;
}

/** Edge transitions for a slot insert: a fade across the slot boundary
 * into the parent's neighbouring content. The frames live in the
 * parent's granted handles, outside the slot; they never change the
 * slot's total. */
export interface EdgeTransitionInput {
  headFrames: number;
  tailFrames: number;
}

export interface ParentSlotInput {
  /** The slot's range in parent timeline frames. */
  range: FrameRangeInput;
  /** Transition frames the parent grants outside the slot. */
  grantedHandles: { headFrames: number; tailFrames: number };
}

export interface WordInput {
  index: number;
  /** Measured word boundaries in audio samples at TIMELINE_SAMPLE_RATE,
   * on the job timeline (MG-020 alignment output). */
  startSample: number;
  endSample: number;
}

export interface NarrationSegmentInput {
  id: string;
  sceneId?: string;
  startFrame: number;
  endFrameExclusive: number;
  words?: WordInput[];
}

export interface CaptionInput {
  id: string;
  sceneId?: string;
  startFrame: number;
  endFrameExclusive: number;
}

export interface SfxCueInput {
  id: string;
  sceneId?: string;
  frame: number;
}

export interface MusicGridInput {
  /** Beats per minute; may be fractional (for example 117.5). */
  bpm: number;
  /** Job frame at which beat 0 falls. */
  firstBeatFrame: number;
}

export type CueAnchorInput =
  | { kind: "semantic_state"; state: string; sceneLocalFrame: number }
  | { kind: "spoken_word"; segmentId: string; wordIndex: number }
  | { kind: "music_beat"; beatIndex: number };

export interface CueInput {
  id: string;
  sceneId: string;
  type: CueType;
  anchor: CueAnchorInput;
}

export interface PropertyWriteInput {
  /** Scene-local frame range of this write. */
  startFrame: number;
  endFrameExclusive: number;
  /** Declares that overlapping the previous write on the same property
   * is intentional (for example a crossfade between two states of one
   * property). Undeclared overlaps are compile failures. */
  intentionalOverlap?: boolean;
}

export interface PropertyTrackInput {
  sceneId: string;
  property: string;
  writes: PropertyWriteInput[];
}

/** The compiler's input: a closed record. Unknown keys at any level are
 * rejected (the contracts layer's closed-schema discipline). Scenes
 * declare durations only; placement belongs to the compiler. */
export interface TimelineCompileInput {
  jobId: string;
  fps: 30 | 60;
  mode: CompileMode;
  audioOwner: AudioOwner;
  /** Required in slot mode, forbidden in program mode. */
  parentSlot?: ParentSlotInput | null;
  /** Slot mode only. Default: no edge transitions. */
  edgeTransition?: EdgeTransitionInput | null;
  scenes: SceneInput[];
  transitions?: TransitionInput[];
  narration?: NarrationSegmentInput[];
  captions?: CaptionInput[];
  sfxCues?: SfxCueInput[];
  cues?: CueInput[];
  musicGrid?: MusicGridInput | null;
  propertyTracks?: PropertyTrackInput[];
}

export interface CompiledSceneDetail {
  id: string;
  placedRange: { startFrame: number; endFrameExclusive: number };
  durationFrames: number;
  sourceRange: { startFrame: number; endFrameExclusive: number };
  sourceRangeSamples: { startSample: number; endSampleExclusive: number };
  transitionInFrames: number;
  transitionOutFrames: number;
}

export interface CompiledHandle {
  id: string;
  fromSceneId: string;
  toSceneId: string;
  ownerSceneId: string;
  frames: number;
  /** The overlap region in output frames: the placed range shared by
   * the two scenes. */
  placedRange: { startFrame: number; endFrameExclusive: number };
  /** Twice the midpoint frame. Kept doubled so a half-frame midpoint
   * stays an exact integer. */
  midpointFrameTimesTwo: number;
  /** The midpoint in audio samples, under the one rounding rule. */
  midpointSample: number;
}

export interface CompiledCue {
  id: string;
  sceneId: string;
  type: CueType;
  frame: number;
  sample: number;
  anchorKind: AnchorKind;
  /** The anchor reference: the state name, "segmentId#wordIndex", or
   * "beat#beatIndex". */
  anchorRef: string;
}

export interface CompiledRangeTrack {
  id: string;
  startFrame: number;
  endFrameExclusive: number;
  startSample: number;
  endSampleExclusive: number;
}

export interface CompiledSfx {
  id: string;
  frame: number;
  sample: number;
}

export interface CompiledSlotRecord {
  parentRange: { startFrame: number; endFrameExclusive: number };
  grantedHandles: { headFrames: number; tailFrames: number };
  usedHandles: { headFrames: number; tailFrames: number };
}

export interface DeclaredPropertyOverlap {
  sceneId: string;
  property: string;
  /** Indices into the track's writes array (input order). */
  earlierWriteIndex: number;
  laterWriteIndex: number;
  /** The overlapping region, in scene-local frames. */
  overlapRange: { startFrame: number; endFrameExclusive: number };
}

/** The compiler sidecar record. Fields the canonical timeline $def
 * cannot carry live here; see the module header and
 * references/timeline-compiler.md. */
export interface TimelineSidecar {
  schema_version: "1.0";
  item: "MG-021";
  job_id: string;
  fps: 30 | 60;
  sample_rate: typeof TIMELINE_SAMPLE_RATE;
  rounding_rule: typeof TIMELINE_ROUNDING_RULE;
  mode: CompileMode;
  total_frames: number;
  total_samples: number;
  scenes: CompiledSceneDetail[];
  handles: CompiledHandle[];
  cues: CompiledCue[];
  narration: CompiledRangeTrack[];
  captions: CompiledRangeTrack[];
  sfx: CompiledSfx[];
  property_overlaps_declared: DeclaredPropertyOverlap[];
  slot: CompiledSlotRecord | null;
}

/** A successful compile: the canonical timeline plus its sidecar. */
export interface CompiledTimeline {
  timeline: Timeline;
  sidecar: TimelineSidecar;
}
