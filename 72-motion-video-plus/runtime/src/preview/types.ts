// Preview planning and review records for Skill 72 Motion Graphics V2
// (Directive MG-024). A preview is the SAME composition as the final at
// a lower spatial resolution and, by default, the SAME frame rate: lower
// resolution must never again be confused with an altered layout or with
// inadequate temporal evidence. The only sanctioned way to lower the
// frame rate is an explicitly labeled rough layout check, and the gate
// in gate.ts refuses rough-layout records as full-fps motion evidence.
//
// This module is engine-agnostic: adapters consume a PreviewPlan, stamp
// the artifacts they produce with a PreviewReviewRecord, and review
// bundles carry that record as metadata (Directive MG-024, "review
// bundle metadata").

import type { Engine } from "../adapters/types";

/** Caller-supplied preview options (Section 5.5 permits an optional
 * trailing options argument on adapter operations). */
export interface PreviewOptions {
  /** Spatial scale relative to the job canvas, in (0, 1]. Default 1:
   * the canonical-dimension preview the adapters have always produced.
   * Previews never upscale. */
  scale?: number;
  /** When true, render at a reduced frame rate for a rough layout
   * check only. The artifact is labeled "rough_layout_only" in its
   * review record and can never satisfy the full-fps motion gate. */
  roughLayout?: boolean;
}

/** How the spatial scale was realized, named honestly per engine.
 * "render_scale": the engine rendered at the scale (Remotion scale
 * option). "post_encode_scale": the engine has no sub-native render
 * scale (the pinned Hyperframes CLI exposes only integer-multiple DPR
 * upscales through --resolution presets), so the adapter scaled the
 * engine's canonical frames at encode time. "none": scale 1. */
export type PreviewScaleMethod = "none" | "render_scale" | "post_encode_scale";

/** The review record stamped on every V2 preview artifact (MG-024). */
export interface PreviewReviewRecord {
  schemaVersion: "1.0";
  engine: Engine;
  jobId: string;
  kind: "preview";
  /** "rough_layout_only" is the explicit label a reduced-fps preview
   * carries in its artifact name, its sidecar, and this record. */
  label: "preview" | "rough_layout_only";
  roughLayoutOnly: boolean;
  scale: number;
  scaleMethod: PreviewScaleMethod;
  /** Hash of the job's content inputs (manifest, storyboard, assets,
   * timeline, scene specs, datasets, designs). Identical for the
   * preview, the rough preview, and the final of one job revision, so
   * a reviewer can prove the preview shows the same content the final
   * will. See media.ts hashJobSourceInputs. */
  sourceHash: string;
  /** Hash of the exact content payload the engine consumed for this
   * call: for Remotion, the canonical JSON of the input props object;
   * for Hyperframes, the generated project files (the composition the
   * CLI rendered). A full-fps preview's props hash equals the final's:
   * both engines consume one identical payload for preview and final.
   * A rough Remotion preview's props differ only in the fps and
   * duration fields (timing in seconds is preserved; see remotion
   * frame-math); a rough Hyperframes preview consumes the identical
   * project and differs only in the render invocation's fps. */
  propsHash: string;
  /** sha256 of the produced preview artifact file. */
  previewHash: string;
  /** The final's geometry: canvas dimensions, authored fps, frames. */
  final: { width: number; height: number; fps: number; durationFrames: number };
  /** The preview's geometry as produced and probed. */
  preview: {
    width: number;
    height: number;
    fps: number;
    durationFrames: number;
    durationSeconds: number;
  };
  generatedAt: string;
}
