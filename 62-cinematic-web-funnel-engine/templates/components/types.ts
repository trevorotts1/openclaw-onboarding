/**
 * types.ts — shared contract between the generated `lib/site-data.generated.ts`
 * data module (written by scripts/build_site.py from a locked
 * content-manifest.json + journey/scene-plan.json, spec Section 9/11) and the
 * scroll-scrub engine components in this directory (spec Section 13.2).
 *
 * Nothing in this file talks to a network, a provider, or a secret. It is
 * pure shape. Keep it that way — provider/media resolution stays in the
 * Python build step (scripts/build_site.py), never in browser code.
 */

export type MotionSpeed = "slow" | "medium" | "fast";

export type JourneyArchitecture =
  | "continuous-forward-journey"
  | "scene-dives-plus-connectors"
  | "hybrid";

/** One scrollable cinematic scene, mapped 1:1 from scene-plan.json's `scenes[]`
 * (structure/scene-plan.schema.json) plus the resolved browser-media paths
 * scripts/build_site.py copies into `public/media/`. */
export interface SceneConfig {
  sceneId: string;
  pageSection: string;
  /** Path under `public/`, e.g. "/media/hero-open.mp4". Always same-origin —
   * build_site.py never emits an absolute/external URL here. */
  videoSrc: string;
  /** Poster image shown before the video is ready to seek and used as the
   * complete fallback when `prefers-reduced-motion` is active (spec 13.4). */
  posterSrc: string;
  durationSeconds: number;
  crop: {
    desktop: string;
    mobile: string;
  };
  camera: {
    motionDirection: string;
    motionSpeed: MotionSpeed;
  };
  ctaRelationship: string;
  /** sha256 of the video file at generation time — carried through only for
   * build-receipt cross-referencing/tests, never rendered to the DOM. */
  videoSha256: string;
  posterSha256: string;
}

/** A real, DOM-rendered copy block sourced verbatim from a locked
 * content-manifest.json `approved_copy_paths` fragment (ADR-10 — this engine
 * never rewrites delegated sacred copy, it only displays it). `html` is
 * trusted, locally-authored fixture/delegate HTML resolved and embedded at
 * generation time by scripts/build_site.py, not user input. */
export interface CopySection {
  id: string;
  html: string;
}

export interface SiteMeta {
  projectId: string;
  title: string;
  description: string;
  architecture: JourneyArchitecture;
}

export interface EmbedConfig {
  /** Parent origins this page is allowed to postMessage to / accept
   * postMessage from when running inside a GHL whole-page iframe (spec
   * 14.2). Empty in direct-hosted mode. */
  allowedAncestors: string[];
}

export interface SiteData {
  meta: SiteMeta;
  scenes: SceneConfig[];
  sections: CopySection[];
  ctaMap: Record<string, unknown>;
  embed: EmbedConfig;
}

/** Deterministic debug state the scroll engine writes to
 * `window.__cwfeScrollDebug` on every animation-frame tick (spec 13.2
 * "expose deterministic debug state for automated tests"). Playwright/E2E
 * tests read this instead of inferring state from pixels. */
export interface ScrollDebugState {
  activeSceneId: string | null;
  activeSceneIndex: number;
  sceneProgress: number;
  overallProgress: number;
  direction: "forward" | "reverse" | "idle";
  reducedMotion: boolean;
  tabVisible: boolean;
  lowPowerMode: boolean;
  mountedSceneIds: string[];
  lastUpdate: number;
}

declare global {
  interface Window {
    __cwfeScrollDebug?: ScrollDebugState;
  }
}
