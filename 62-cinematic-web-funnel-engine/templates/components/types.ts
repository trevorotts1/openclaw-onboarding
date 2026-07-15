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

/**
 * Conversion layer (build unit U16, P12-CRM). `SiteData.ctaMap` is written
 * by `scripts/build_site.py` as a raw pass-through of the locked
 * content-manifest.json's `cta_map` object (structure/content-manifest.schema.json
 * declares it `additionalProperties: true` — deliberately open so the
 * conversion layer, not the P3 content router, owns this shape). This file
 * is that shape's single source of truth; `conversion-map.ts` is the only
 * place raw `ctaMap` entries are trusted, and only after passing validation.
 *
 * Per spec Section 14.1/14.3, this engine never grows its own GHL build
 * client — it only WIRES to GHL surfaces Skill 6 (06-ghl-install-pages) and
 * Skill 44 (44-convert-and-flow-operator) already provisioned for the
 * client: a hosted form/calendar embed URL ("ghl-form-embed") or an inbound
 * webhook that fires a Convert and Flow workflow ("ghl-webhook"). Every
 * secret-shaped value (embed URL, webhook URL) is resolved server-side by
 * ENV VAR NAME only — the name lives in this map, never the value (spec
 * Section 20 "record secret presence by name only in receipts").
 */
export type ConversionActionKind = "ghl-form-embed" | "ghl-webhook" | "external-link";

export interface ConversionAction {
  kind: ConversionActionKind;
  /** Human-readable label used for the embed iframe title / dev diagnostics. */
  label: string;
  /**
   * Required when kind === "ghl-form-embed". The NAME (never the value) of
   * a server-resolved env var holding the client's GHL-hosted form or
   * calendar widget embed URL. Resolved only inside the Server Component
   * `GhlFormEmbed`, never inlined into the client bundle as a literal
   * `NEXT_PUBLIC_*` access (Next.js only statically replaces literal
   * `process.env.NEXT_PUBLIC_X` member expressions in client code, not a
   * computed/dynamic lookup — so this must stay server-side by design).
   */
  embedUrlEnvVar?: string;
  /**
   * Required when kind === "ghl-webhook". The NAME of a server-only env var
   * holding the client's GHL inbound webhook URL (Convert and Flow
   * workflow trigger). Resolved only inside the `/api/conversion-event`
   * route handler, which runs server-side and may read `process.env` by a
   * dynamic key at runtime.
   */
  webhookEnvVar?: string;
  /** Required when kind === "external-link". A same-app-relative or
   * absolute URL; never a template literal built from user input. */
  href?: string;
  /** Field names a submitting `<form data-cwfe-cta="...">` (or a
   * `data-cwfe-field-*` set on a plain webhook CTA) must supply, non-empty,
   * before this action is allowed to fire. Enforced independently on the
   * client (fast fail before a network call) AND the server (never trusts
   * the client's own validation). */
  requiredFields: string[];
}

export type ConversionMap = Record<string, ConversionAction>;

/** One rejected `ctaMap` entry — parsing is fail-closed (spec: "Fail-closed
 * if the conversion wiring is missing required fields"): a malformed entry
 * is dropped from the usable `ConversionMap`, recorded here, and any DOM
 * element that references it renders/behaves as explicitly broken rather
 * than silently doing nothing or guessing a default. */
export interface ConversionMapError {
  ctaId: string;
  reason: string;
}

/** Deterministic debug state the conversion tracking hook writes to
 * `window.__cwfeConversionDebug` (mirrors `ScrollDebugState` above) so
 * Playwright/E2E tests can assert on real tracked events instead of
 * inferring them from network traffic. */
export interface ConversionTrackedEvent {
  name: string;
  ctaId?: string;
  payload: Record<string, unknown>;
  utm: Record<string, string>;
  timestamp: number;
}

export interface ConversionDebugState {
  events: ConversionTrackedEvent[];
}

declare global {
  interface Window {
    __cwfeConversionDebug?: ConversionDebugState;
    dataLayer?: unknown[];
  }
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
