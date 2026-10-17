// Export profiles for the Skill 72 Motion Graphics V2 runtime
// (Directive MG-040). A delivery profile is data the capability layer
// can reason about, not a flag buried in an adapter: each profile names
// its container, the stream codec and pixel format a truthful artifact
// must probe as, the qualified encode that produces it from a PNG frame
// sequence, and the per-engine route that delivers it.
//
// Qualification rule: a profile may only name an encode that the
// pinned toolchain on this machine was probed to perform. The probes
// live in probe.ts (live micro-roundtrips through the pinned ffmpeg
// 8.1.2 encoders) and in the MG-040 suite (tests/run-export-profiles.ts),
// which exercises every engine route claimed here end to end. The
// reference document is references/export-profiles.md.
//
// The three profile ids are exactly the manifest contract's
// delivery.video_profile enum (references/contracts-v2.schema.json);
// the MG-040 suite asserts the two lists stay identical.

import type { Engine } from "../adapters/types";

/** The manifest contract's delivery video profiles. */
export type VideoProfileId = "h264_opaque" | "prores_4444_alpha" | "vp9_alpha";

/** Section 16.9 failure categories raised by the export layer, with
 * their exit classes: capability failures are class 3, encode failures
 * class 5, quality-control (truthfulness) failures class 6. */
export type ExportErrorCategory =
  | "MG_CAPABILITY_UNSUPPORTED"
  | "MG_ENCODE_FAILED"
  | "MG_QC_FAILED";

export function exportExitClassForCategory(category: ExportErrorCategory): number {
  switch (category) {
    case "MG_CAPABILITY_UNSUPPORTED":
      return 3;
    case "MG_ENCODE_FAILED":
      return 5;
    case "MG_QC_FAILED":
      return 6;
  }
}

/** Structured export-layer failure. `check` names the stable check
 * that failed (for example "export.alpha_channel_present") so a
 * refusal can be asserted by name, not by message text. */
export class ExportError extends Error {
  readonly category: ExportErrorCategory;
  readonly exitClass: number;
  readonly check: string | null;

  constructor(opts: { category: ExportErrorCategory; message: string; check?: string | null }) {
    super(opts.message);
    this.name = "ExportError";
    this.category = opts.category;
    this.exitClass = exportExitClassForCategory(opts.category);
    this.check = opts.check ?? null;
  }
}

/** How one engine delivers one profile. "engine_native" means the
 * engine's own pinned encoder path produces the artifact;
 * "image_sequence_encode" means the engine supplies PNG frames and
 * the export layer encodes them with the profile's qualified encode. */
export interface ProfileRoute {
  kind: "engine_native" | "image_sequence_encode";
  detail: string;
}

/** One delivery profile, as data. */
export interface ExportProfile {
  id: VideoProfileId;
  label: string;
  /** True when the profile promises an alpha channel. The promise is
   * always verified by measurement before it is recorded (verify.ts). */
  alpha: boolean;
  /** Artifact file extension, including the dot. */
  containerExtension: string;
  /** The codec_name ffprobe must report for a truthful artifact. */
  streamCodec: string;
  /** Prefix the stream pixel format must carry. For VP9 the decoded
   * stream reports yuv420p and alpha is carried as stream metadata
   * (the alpha_mode tag), so this prefix is the color format and
   * alpha presence is proven by decoding, never by this field. */
  streamPixelFormatPrefix: string;
  /** ffmpeg encoder that produces this profile from PNG frames, or
   * null when the profile has no qualified sequence encode. */
  sequenceEncoder: string | null;
  /** ffmpeg arguments (after the frame-sequence input) for the
   * profile's delivery encode from a PNG sequence. */
  sequenceEncodeArgs: string[];
  /** Per-engine delivery routes. */
  routes: Record<"hyperframes" | "remotion", ProfileRoute>;
}

export const EXPORT_PROFILES: Record<VideoProfileId, ExportProfile> = {
  h264_opaque: {
    id: "h264_opaque",
    label: "H.264 opaque (PowerPoint delivery default)",
    alpha: false,
    containerExtension: ".mp4",
    streamCodec: "h264",
    streamPixelFormatPrefix: "yuv420p",
    sequenceEncoder: "libx264",
    sequenceEncodeArgs: ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"],
    routes: {
      hyperframes: {
        kind: "engine_native",
        detail: "Hyperframes CLI render, default mp4 format (the historical final path).",
      },
      remotion: {
        kind: "engine_native",
        detail: "Remotion renderMedia with codec h264, pixelFormat yuv420p, crf 16 (the historical final path).",
      },
    },
  },
  prores_4444_alpha: {
    id: "prores_4444_alpha",
    label: "ProRes 4444 with alpha",
    alpha: true,
    containerExtension: ".mov",
    streamCodec: "prores",
    streamPixelFormatPrefix: "yuva444p",
    sequenceEncoder: "prores_ks",
    sequenceEncodeArgs: ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"],
    routes: {
      hyperframes: {
        kind: "engine_native",
        detail:
          "Hyperframes CLI render --format mov: the pinned CLI 0.8.155 documents MOV as its " +
          "fixed alpha-preserving ProRes 4444 profile.",
      },
      remotion: {
        kind: "engine_native",
        detail:
          "Remotion renderMedia with codec prores, proResProfile 4444, pixelFormat yuva444p10le " +
          "(pinned @remotion/renderer 4.0.535 API).",
      },
    },
  },
  vp9_alpha: {
    id: "vp9_alpha",
    label: "VP9 with alpha (WebM)",
    alpha: true,
    containerExtension: ".webm",
    streamCodec: "vp9",
    streamPixelFormatPrefix: "yuv420p",
    sequenceEncoder: "libvpx-vp9",
    sequenceEncodeArgs: ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "18"],
    routes: {
      hyperframes: {
        kind: "engine_native",
        detail:
          "Hyperframes CLI render --format webm: the pinned CLI 0.8.155 documents WebM as a " +
          "transparency-carrying render format.",
      },
      remotion: {
        kind: "image_sequence_encode",
        detail:
          "No Remotion-native VP9 alpha render is wired in the adapter; the qualified route is " +
          "PNG frames from the engine encoded by the export layer (libvpx-vp9, yuva420p).",
      },
    },
  },
};

export const VIDEO_PROFILE_IDS = Object.keys(EXPORT_PROFILES) as VideoProfileId[];

/** Look up a profile by id. Unknown ids fail capability selection by
 * name (Section 16.9, MG_CAPABILITY_UNSUPPORTED) instead of falling
 * back to any default. */
export function exportProfileById(id: string): ExportProfile {
  const profile = (EXPORT_PROFILES as Record<string, ExportProfile>)[id];
  if (!profile) {
    throw new ExportError({
      category: "MG_CAPABILITY_UNSUPPORTED",
      check: "export.profile_known",
      message:
        `Unknown delivery video profile "${id}". Known profiles: ${VIDEO_PROFILE_IDS.join(", ")}.`,
    });
  }
  return profile;
}

/**
 * THE intermediate-quality policy (MG-040). One policy governs every
 * intermediate encode in the export layer:
 *
 * - The mezzanine is a lossless PNG frame sequence (RGBA). PNG is
 *   mathematically lossless, so handing work between stages through
 *   the mezzanine adds zero drift.
 * - A delivery encode consumes the mezzanine (or engine frames) in
 *   exactly ONE encode at the profile's fixed settings. A delivery
 *   encode never consumes another delivery encode.
 * - When a video mezzanine is unavoidable, it is created once, from
 *   the PNG mezzanine, at the mezzanine settings below (ProRes 4444
 *   at its fixed profile grade, or VP9 lossless), never at delivery
 *   settings.
 *
 * The MG-040 suite proves the consequence on the alpha fixture: two
 * generations under this policy stay inside the patch tolerances,
 * while an unmanaged chain (a delivery-grade VP9 encode used as an
 * intermediate and encoded again) drifts measurably further.
 */
export const INTERMEDIATE_POLICY = {
  id: "png-mezzanine-single-encode",
  version: "1.0",
  mezzanine: "lossless PNG frame sequence (RGBA)",
  deliveryEncodeGenerations: 1,
  videoMezzanineArgs: {
    prores_4444_alpha: ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"],
    vp9_alpha: ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-lossless", "1", "-b:v", "0"],
  } as Record<string, string[]>,
  /** Tolerances the suite enforces, as mean absolute error bounds on
   * 8-bit channel values unless a case states otherwise. */
  tolerances: {
    /** Flat known-color patches, per-channel mean, after one encode. */
    patchMeanProres: 2,
    patchMeanVp9: 4,
    /** Flat patches after two generations under the policy. */
    patchMeanTwoGenerationsProres: 2,
    patchMeanTwoGenerationsVp9: 5,
    /** One-pixel chromatic detail region after two policy generations
     * of ProRes 4444 (4:4:4, no chroma subsampling). */
    detailRegionMaeProresTwoGenerations: 1.0,
    /** Sampled composite pixels over a known background. */
    compositeSample: 8,
  },
} as const;

/** The engines the export layer routes for. The legacy compatibility
 * renderer has no export profiles; it is not part of MG-040. */
export type ExportEngine = Extract<Engine, "hyperframes" | "remotion">;
