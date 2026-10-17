// Native Hyperframes composition generators for MG-005.
//
// Each generator authors a real Hyperframes project (HTML compositions
// following the pinned 0.8.155 core contract): a root element carrying
// data-composition-id, data-width, data-height, data-start and
// data-duration; timed elements carrying class "clip" with data-start and
// data-duration; one paused GSAP timeline per composition registered on
// window.__timelines under its composition id; sub-compositions embedded
// through data-composition-src with per-instance data-variable-values.
//
// Generators are pure: spec in, file map out. The adapter owns all I/O,
// process execution, and evidence. Timing is authored from integer
// frames (Directive Section 5.4) and converted to seconds only here, at
// the engine boundary.
//
// Registered generators:
// - C05 (contracts-registered): the Section 16 bar-comparison fixture run
//   on the Hyperframes native clock (Directive 17.2: the same fixture
//   through Hyperframes uses its native animation clock, not a
//   screenshot of the Remotion output; Section 7.1 requires C05 natively
//   in Hyperframes as a capability/reference test).
// - C01 (catalog component, contracts registration is MG-018 scope): the
//   image-led mask reveal of Section 15.3 / VREF-01 shape.
// - C01 variant "nested_detail": a root composition embedding a detail
//   sub-composition (composition-structure proof).
// - C02 variant "media_timing": a scene whose media clip timing is owned
//   by the framework (data-start, data-duration, data-media-start),
//   while the visual wrapper animates separately on the root timeline.
//   The clip is an abstract locally generated timing fixture, not a
//   product demonstration (VREF-04 stays BLOCKED_ASSET until a real
//   product source exists).

import type { Dataset, Design, Scene } from "../validation/generated-types";
import { embeddedJson, esc, fontFaceCss, ResolvedFont, seconds, secondsAttr } from "./project";
import { annotationAnchorAt, zoomWindowAt } from "../compositing/closeup";

/** A generated project: relative file path to file content, plus the
 * composition ids the project defines (root first). */
export interface GeneratedProject {
  files: Record<string, string>;
  compositionIds: string[];
  rootCompositionId: string;
}

/** MG-005 scene spec for the C01 image-led reveal. This shape is the
 * MG-005 component contract for C01 until MG-018 registers the catalog
 * schema; jobs using it are adapter-level fixture jobs. */
export interface ImageRevealSceneSpec {
  schema_version: "mg005-1";
  id: string;
  component_id: "C01";
  component_version: "1.0.0";
  variant?: "mask_reveal";
  engine: "hyperframes";
  duration_frames: number;
  /** Job-relative path of the subject image asset. */
  asset_file: string;
  /** Optional expected sha256 of the asset; verified when present. */
  asset_sha256?: string;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  subject: {
    id: string;
    box: { x: number; y: number; width: number; height: number };
    /** Hex color identifying subject pixels in decoded frames. */
    measure_color: string;
  };
  copy: { headline: string; caption: string; fixture_label: string };
  headline_px: number;
  caption_px: number;
  motion: {
    kind: "mask_reveal";
    start_frame: number;
    end_frame_exclusive: number;
    hold_to_frame_exclusive: number;
  };
  semantic_motion_assertions: Array<{
    id: string;
    kind: "subject_reveal";
    frame: number;
    /** Revealed fraction of the subject, normalized so the fully
     * revealed state measures 1. */
    min_fraction: number;
    max_fraction: number;
  }>;
}

/** MG-005 scene spec for the nested-composition proof: a static subject
 * beside a detail sub-composition embedded with data-composition-src. */
export interface NestedDetailSceneSpec {
  schema_version: "mg005-1";
  id: string;
  component_id: "C01";
  component_version: "1.0.0";
  variant: "nested_detail";
  engine: "hyperframes";
  duration_frames: number;
  asset_file: string;
  asset_sha256?: string;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  subject: {
    id: string;
    box: { x: number; y: number; width: number; height: number };
    measure_color: string;
  };
  detail: {
    box: { x: number; y: number; width: number; height: number };
    start_frame: number;
    /** Hex color identifying the detail chip in decoded frames. */
    measure_color: string;
    variables: { label: string; value: string };
  };
  copy: { headline: string; fixture_label: string };
  headline_px: number;
}

/** MG-005 scene spec for the media-timed scene. The media file is a
 * locally generated timing fixture whose color segments are declared so
 * decoded frames can prove the framework honored data-media-start. */
export interface MediaTimedSceneSpec {
  schema_version: "mg005-1";
  id: string;
  component_id: "C02";
  component_version: "1.0.0";
  variant: "media_timing";
  engine: "hyperframes";
  duration_frames: number;
  /** Job-relative path of the media clip. */
  media_file: string;
  media_sha256?: string;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  clip: {
    start_frame: number;
    duration_frames: number;
    /** Trim offset into the media file, seconds (data-media-start). */
    media_start_seconds: number;
    box: { x: number; y: number; width: number; height: number };
  };
  /** Declared media content: solid-color segments over media time. */
  media_segments: Array<{ start: number; end: number; color: string }>;
  copy: { headline: string; caption: string; fixture_label: string };
  headline_px: number;
  caption_px: number;
}

export type Mg005SceneSpec = ImageRevealSceneSpec | NestedDetailSceneSpec | MediaTimedSceneSpec;

export type SceneSpec =
  | { origin: "contracts"; scene: Scene; dataset: Dataset; design: Design }
  | { origin: "mg005"; spec: Mg005SceneSpec };

function pageShell(opts: {
  width: number;
  height: number;
  font: ResolvedFont;
  variables: Array<{ id: string; type: string; label: string; default: string }>;
  css: string;
  body: string;
  script: string;
}): string {
  const vars = opts.variables.length
    ? ` data-composition-variables='${JSON.stringify(opts.variables).replace(/'/g, "&#39;")}'`
    : "";
  return [
    "<!doctype html>",
    `<html lang="en"${vars}>`,
    "  <head>",
    '    <meta charset="UTF-8" />',
    `    <meta name="viewport" content="width=${opts.width}, height=${opts.height}" />`,
    '    <script src="./vendor/gsap.min.js"></script>',
    "    <style>",
    fontFaceCss(opts.font),
    "      * { margin: 0; padding: 0; box-sizing: border-box; }",
    `      html, body { margin: 0; width: ${opts.width}px; height: ${opts.height}px; overflow: hidden; }`,
    `      body { font-family: "${opts.font.cssFamily}", sans-serif; }`,
    opts.css,
    "    </style>",
    "  </head>",
    "  <body>",
    opts.body,
    "    <script>",
    opts.script,
    "    </script>",
    "  </body>",
    "</html>",
    "",
  ].join("\n");
}

/** C05 bar comparison on the Hyperframes native clock. Geometry comes
 * from the job's own design file (plot box, row positions, type sizes),
 * values from the job's dataset; final bar width is value / domain max
 * times plot width, the shared scale calculation of Directive 17.2. */
export function generateC05Project(input: {
  scene: Scene;
  dataset: Dataset;
  design: Design;
  font: ResolvedFont;
  fps: number;
  canvas: { width: number; height: number };
}): GeneratedProject {
  const { scene, dataset, design, font, fps, canvas } = input;
  const layout = design.layouts[scene.layout_variant];
  const durationSec = seconds(scene.duration_frames, fps);
  const startSec = seconds(scene.motion.start_frame, fps);
  const revealSec = seconds(scene.motion.end_frame_exclusive - scene.motion.start_frame, fps);
  const domainMax = dataset.domain[1];
  const rows = dataset.rows.map((row, i) => ({
    subjectId: `bar-${row.id}`,
    label: row.label,
    value: row.value,
    finalWidth: (row.value / domainMax) * layout.plot.width,
    y: layout.row_y[i],
  }));
  const colors = design.colors;

  const rowCss = rows
    .map(
      (r) => `
      .row-${r.subjectId} { position: absolute; left: 0; top: ${r.y}px; width: 100%; height: ${layout.bar_height}px; }
      .label-${r.subjectId} { position: absolute; left: 40px; top: 0; width: ${layout.plot.x - 64}px; height: ${layout.bar_height}px; line-height: ${layout.bar_height}px; text-align: right; font-size: ${layout.label_px}px; font-weight: 700; color: ${colors.ink}; }
      .track-${r.subjectId} { position: absolute; left: ${layout.plot.x}px; top: 0; width: ${layout.plot.width}px; height: ${layout.bar_height}px; }
      .${r.subjectId} { position: absolute; left: 0; top: 0; height: ${layout.bar_height}px; width: 0px; background: ${colors.accent}; }
      .value-${r.subjectId} { position: absolute; top: 0; height: ${layout.bar_height}px; line-height: ${layout.bar_height}px; font-size: ${layout.value_px}px; font-weight: 700; color: ${colors.ink}; }`
    )
    .join("\n");
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: ${layout.headline_box.x}px; top: ${layout.headline_box.y}px; width: ${layout.headline_box.width}px; font-size: ${layout.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #disclosure { position: absolute; left: ${layout.headline_box.x}px; bottom: 48px; font-size: ${layout.disclosure_px}px; color: ${colors.ink}; opacity: 0.66; }
      .axis { position: absolute; left: ${layout.plot.x}px; top: ${layout.plot.y - 24}px; width: 3px; height: ${layout.plot.height + 48}px; background: ${colors.ink}; opacity: 0.35; }
      .baseline { position: absolute; left: ${layout.plot.x}px; top: ${layout.plot.y + layout.plot.height + 24}px; width: ${layout.plot.width}px; height: 3px; background: ${colors.ink}; opacity: 0.35; }${rowCss}`;
  const rowsHtml = rows
    .map(
      (r) => `
      <div class="clip row-${r.subjectId}" data-start="0" data-duration="${durationSec}" data-track-index="1">
        <div class="label-${r.subjectId}">${esc(r.label)}</div>
        <div class="track-${r.subjectId}">
          <div class="${r.subjectId}" id="${r.subjectId}"></div>
          <div class="value-${r.subjectId}" id="value-${r.subjectId}">${r.value}</div>
        </div>
      </div>`
    )
    .join("\n");
  const body = `
    <div id="root" data-composition-id="${esc(scene.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(scene.copy.headline)}</div>
      <div class="axis"></div>
      <div class="baseline"></div>${rowsHtml}
      <div id="disclosure" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2">${esc(scene.copy.disclosure)}</div>
    </div>`;
  const script = `
      const ROWS = ${embeddedJson(rows.map((r) => ({ id: r.subjectId, finalWidth: r.finalWidth, value: r.value })))};
      const vars = (window.__hyperframes && window.__hyperframes.getVariables) ? window.__hyperframes.getVariables() : {};
      if (vars.headline) document.getElementById("headline").textContent = vars.headline;
      if (vars.disclosure) document.getElementById("disclosure").textContent = vars.disclosure;
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      for (const row of ROWS) {
        const bar = document.getElementById(row.id);
        const valueEl = document.getElementById("value-" + row.id);
        const proxy = { w: 0 };
        tl.to(proxy, {
          w: row.finalWidth,
          duration: ${revealSec},
          ease: "none",
          onUpdate: () => {
            bar.style.width = proxy.w + "px";
            valueEl.style.left = (proxy.w + 24) + "px";
            valueEl.textContent = String(Math.round((proxy.w / row.finalWidth) * row.value));
          },
        }, ${startSec});
      }
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(scene.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [
      { id: "headline", type: "string", label: "Headline", default: scene.copy.headline },
      { id: "disclosure", type: "string", label: "Disclosure", default: scene.copy.disclosure },
    ],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [scene.id], rootCompositionId: scene.id };
}

/** C01 image-led mask reveal: the named subject itself is progressively
 * uncovered left to right (subject-owned motion, M10). The wrapper clips;
 * the image inside never moves or scales. */
export function generateC01Project(input: {
  spec: ImageRevealSceneSpec;
  font: ResolvedFont;
  fps: number;
  assetFileName: string;
}): GeneratedProject {
  const { spec, font, fps, assetFileName } = input;
  const { canvas, subject, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const startSec = seconds(spec.motion.start_frame, fps);
  const revealSec = seconds(spec.motion.end_frame_exclusive - spec.motion.start_frame, fps);
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 96px; top: 72px; width: ${canvas.width - 192}px; font-size: ${spec.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #subject-mask { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y}px; width: 0px; height: ${subject.box.height}px; overflow: hidden; }
      #subject-img { width: ${subject.box.width}px; height: ${subject.box.height}px; display: block; }
      #subject-frame { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y}px; width: ${subject.box.width}px; height: ${subject.box.height}px; border: 4px solid ${colors.ink}; }
      #caption { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y + subject.box.height + 28}px; width: ${subject.box.width}px; font-size: ${spec.caption_px}px; color: ${colors.ink}; opacity: 0; }
      #fixture-label { position: absolute; left: 96px; bottom: 56px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }`;
  const body = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <div id="subject-mask" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="1">
        <img id="subject-img" src="./assets/${esc(assetFileName)}" alt="" />
      </div>
      <div id="subject-frame"></div>
      <div id="caption" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2">${esc(spec.copy.caption)}</div>
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.fixture_label)}</div>
    </div>`;
  const script = `
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      tl.fromTo("#subject-mask", { width: 0 }, { width: ${subject.box.width}, duration: ${revealSec}, ease: "none" }, ${startSec});
      tl.to("#caption", { opacity: 1, duration: 0.4, ease: "none" }, ${startSec + revealSec});
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [{ id: "headline", type: "string", label: "Headline", default: spec.copy.headline }],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [spec.id], rootCompositionId: spec.id };
}

/** Nested composition proof: the root embeds a detail sub-composition
 * through data-composition-src with per-instance variable values. The
 * subject image is static in the root; the detail chip animates on its
 * own registered timeline inside the sub-composition. */
export function generateNestedProject(input: {
  spec: NestedDetailSceneSpec;
  font: ResolvedFont;
  fps: number;
  assetFileName: string;
}): GeneratedProject {
  const { spec, font, fps, assetFileName } = input;
  const { canvas, subject, detail, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const detailStartSec = seconds(detail.start_frame, fps);
  const detailDurationSec = seconds(spec.duration_frames - detail.start_frame, fps);
  const subId = `${spec.id}-detail`;
  const rootCss = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 96px; top: 72px; width: ${canvas.width - 192}px; font-size: ${spec.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #subject-img { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y}px; width: ${subject.box.width}px; height: ${subject.box.height}px; border: 4px solid ${colors.ink}; }
      #detail-host { position: absolute; left: ${detail.box.x}px; top: ${detail.box.y}px; width: ${detail.box.width}px; height: ${detail.box.height}px; }
      #fixture-label { position: absolute; left: 96px; bottom: 56px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }`;
  const rootBody = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <img id="subject-img" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="1" src="./assets/${esc(assetFileName)}" alt="" />
      <div id="detail-host" data-composition-id="${esc(subId)}" data-composition-src="./compositions/detail.html" data-start="${detailStartSec}" data-duration="${detailDurationSec}" data-variable-values='${embeddedJson(detail.variables)}'></div>
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.fixture_label)}</div>
    </div>`;
  const rootScript = `
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const rootHtml = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [{ id: "headline", type: "string", label: "Headline", default: spec.copy.headline }],
    css: rootCss,
    body: rootBody,
    script: rootScript,
  });
  const subCss = `
      body { background: transparent; }
      #root { position: relative; width: 100%; height: 100%; }
      #chip { position: absolute; left: 0; top: 0; width: ${detail.box.width}px; height: ${detail.box.height}px; background: ${detail.measure_color}; border-radius: 24px; padding: 28px 36px; opacity: 0; }
      #chip-value { font-size: 96px; font-weight: 700; color: #FFFFFF; }
      #chip-label { font-size: 40px; font-weight: 400; color: #FFFFFF; margin-top: 6px; }`;
  const subBody = `
    <div id="root" data-composition-id="${esc(subId)}" data-start="0" data-duration="${detailDurationSec}" data-width="${detail.box.width}" data-height="${detail.box.height}">
      <div id="chip" class="clip" data-start="0" data-duration="${detailDurationSec}" data-track-index="0">
        <div id="chip-value"></div>
        <div id="chip-label"></div>
      </div>
    </div>`;
  const subScript = `
      const vars = (window.__hyperframes && window.__hyperframes.getVariables) ? window.__hyperframes.getVariables() : { label: "", value: "" };
      document.getElementById("chip-value").textContent = vars.value || "";
      document.getElementById("chip-label").textContent = vars.label || "";
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#chip", { opacity: 0, scale: 0.92 }, { opacity: 1, scale: 1, duration: 0.6, ease: "none" }, 0);
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(subId)}] = tl;
      tl.seek(0);`;
  const subHtml = pageShell({
    width: detail.box.width,
    height: detail.box.height,
    font,
    variables: [
      { id: "label", type: "string", label: "Label", default: detail.variables.label },
      { id: "value", type: "string", label: "Value", default: detail.variables.value },
    ],
    css: subCss,
    body: subBody,
    script: subScript,
  });
  return {
    files: { "index.html": rootHtml, "compositions/detail.html": subHtml },
    compositionIds: [spec.id, subId],
    rootCompositionId: spec.id,
  };
}

/** Media-timed scene: the framework owns the clip's timing through
 * data-start, data-duration and data-media-start on the video element.
 * The wrapper (frame, headline, progress track) animates on the root
 * GSAP timeline, separately from the media lifecycle. */
export function generateMediaProject(input: {
  spec: MediaTimedSceneSpec;
  font: ResolvedFont;
  fps: number;
  mediaFileName: string;
}): GeneratedProject {
  const { spec, font, fps, mediaFileName } = input;
  const { canvas, clip, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const clipStartSec = seconds(clip.start_frame, fps);
  const clipDurationSec = seconds(clip.duration_frames, fps);
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 96px; top: 64px; width: ${canvas.width - 192}px; font-size: ${spec.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #clip-frame { position: absolute; left: ${clip.box.x - 8}px; top: ${clip.box.y - 8}px; width: ${clip.box.width + 16}px; height: ${clip.box.height + 16}px; border: 5px solid ${colors.ink}; }
      #media-clip { position: absolute; left: ${clip.box.x}px; top: ${clip.box.y}px; width: ${clip.box.width}px; height: ${clip.box.height}px; object-fit: fill; }
      #progress-track { position: absolute; left: ${clip.box.x}px; top: ${clip.box.y + clip.box.height + 36}px; width: ${clip.box.width}px; height: 14px; background: ${colors.ink}; opacity: 0.25; }
      #progress-fill { position: absolute; left: ${clip.box.x}px; top: ${clip.box.y + clip.box.height + 36}px; width: 0px; height: 14px; background: ${colors.accent}; }
      #caption { position: absolute; left: ${clip.box.x}px; top: ${clip.box.y + clip.box.height + 64}px; width: ${clip.box.width}px; font-size: ${spec.caption_px}px; color: ${colors.ink}; }
      #fixture-label { position: absolute; left: 96px; bottom: 16px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }`;
  const body = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <div id="clip-frame"></div>
      <video id="media-clip" class="clip" data-start="${clipStartSec}" data-duration="${clipDurationSec}" data-media-start="${clip.media_start_seconds}" data-track-index="1" src="./assets/${esc(mediaFileName)}" muted playsinline></video>
      <div id="progress-track"></div>
      <div id="progress-fill" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2"></div>
      <div id="caption" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.caption)}</div>
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="4">${esc(spec.copy.fixture_label)}</div>
    </div>`;
  const script = `
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      tl.fromTo("#progress-fill", { width: 0 }, { width: ${clip.box.width}, duration: ${durationSec}, ease: "none" }, 0);
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [{ id: "headline", type: "string", label: "Headline", default: spec.copy.headline }],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [spec.id], rootCompositionId: spec.id };
}

// ---------------------------------------------------------------------
// MG-016: C06 line trend on the Hyperframes native clock.
//
// The Hyperframes sample chart for the MG-016 library (Directive
// MG-016: at least one Hyperframes-native chart demonstrates the
// second engine without duplicating every component). The same
// line-trend-a fixture the Remotion component renders is authored
// here as a generated composition on the GSAP timeline. The staging
// mirrors chart-geometry.ts lineStateAt exactly: the motion interval
// divides into one equal stage per point; a point establishes during
// the first half of its stage; the connection to it draws during the
// second half, joining only established values; no smoothing is
// applied anywhere. The animation uses only GSAP-native tweens (dot
// opacity and scale, value-label opacity, attribute interpolation of
// the polyline between keyframed point states, and timed sets for
// the focus ring), so every frame is a pure function of the timeline
// position under any seek, with no script callbacks and no
// wall-clock timers.

/** MG-016 scene spec for the C06 Hyperframes sample. Point coordinates
 * are final canvas positions computed by the chart geometry layer; the
 * MG-016 test runner asserts they match lineGeometry for the fixture
 * dataset and design, so this spec cannot drift from the shared math. */
export interface LineTrendSceneSpec {
  schema_version: "mg016-1";
  id: string;
  component_id: "C06";
  component_version: "1.0.0";
  engine: "hyperframes";
  duration_frames: number;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  copy: { headline: string; disclosure: string; fixture_label: string };
  headline_px: number;
  label_px: number;
  value_px: number;
  disclosure_px: number;
  plot: { x: number; y: number; width: number; height: number };
  units: string;
  /** Final point positions in canvas coordinates, in time order. */
  points: Array<{
    id: string;
    label: string;
    value_label: string;
    x: number;
    y: number;
  }>;
  annotations: Array<{ id: string; row_id: string; text: string }>;
  focus_row_id: string | null;
  motion: {
    kind: "line_trend_reveal";
    start_frame: number;
    end_frame_exclusive: number;
    hold_to_frame_exclusive: number;
  };
}

/** Polyline keyframe state k: points 0..k at their true positions,
 * every later point stacked on point k (zero-length segments render
 * nothing new), so tweening state k-1 to state k draws exactly the
 * one new segment and nothing else. */
function trendState(points: Array<{ x: number; y: number }>, k: number): string {
  const anchor = points[Math.min(k, points.length - 1)];
  return points
    .map((p, i) => {
      const at = i <= k ? p : anchor;
      return `${at.x},${at.y}`;
    })
    .join(" ");
}

export function generateC06Project(input: {
  spec: LineTrendSceneSpec;
  font: ResolvedFont;
  fps: number;
}): GeneratedProject {
  const { spec, font, fps } = input;
  const { canvas, plot, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const startSec = seconds(spec.motion.start_frame, fps);
  const revealSec = seconds(
    spec.motion.end_frame_exclusive - spec.motion.start_frame,
    fps
  );
  const endSec = startSec + revealSec;
  const n = spec.points.length;
  const slotSec = revealSec / n;
  const focusIndex = spec.focus_row_id
    ? spec.points.findIndex((p) => p.id === spec.focus_row_id)
    : -1;
  // Layout discipline (MG-044 polish of the MG-016 sample): the axis
  // caption sits in the empty left rail, right-aligned against the
  // axis and below the headline block, never inside the plot's top
  // edge where it crowded the headline's second line and descenders.
  // The fixture label bar sits on the disclosure row at the right,
  // clear of the month labels that hang below the plot; it previously
  // sat at bottom:96px on the left, directly over the month-label row.
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 120px; top: 90px; width: ${canvas.width - 240}px; font-size: ${spec.headline_px}px; line-height: 1.05; font-weight: 700; color: ${colors.ink}; }
      #disclosure { position: absolute; left: 120px; bottom: 40px; font-size: ${spec.disclosure_px}px; color: ${colors.ink}; }
      #fixture-label { position: absolute; right: 120px; bottom: 40px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }
      .axis { position: absolute; background: ${colors.ink}; opacity: 0.35; }
      #units { position: absolute; left: ${plot.x - 232}px; top: ${plot.y + 36}px; width: 200px; text-align: right; font-size: ${spec.label_px}px; color: ${colors.ink}; opacity: 0.55; }
      #axis-left { left: ${plot.x}px; top: ${plot.y}px; width: 3px; height: ${plot.height}px; }
      #axis-bottom { left: ${plot.x}px; top: ${plot.y + plot.height}px; width: ${plot.width}px; height: 3px; }
      .pt-dot { position: absolute; width: 22px; height: 22px; border-radius: 50%; background: ${colors.accent}; border: 3px solid ${colors.background}; opacity: 0; transform: translate(-50%, -50%); }
      .pt-value { position: absolute; width: 220px; text-align: center; font-size: ${spec.value_px}px; font-weight: 700; color: ${colors.ink}; opacity: 0; }
      .pt-label { position: absolute; width: 280px; text-align: center; font-size: ${spec.label_px}px; line-height: 1.15; color: ${colors.ink}; }
      #focus-ring { position: absolute; width: 42px; height: 42px; border-radius: 50%; border: 3px solid ${colors.ink}; opacity: 0; }
      .annotation { position: absolute; width: 430px; padding: 14px 18px; border: 3px solid ${colors.ink}; background: ${colors.background}; font-size: ${spec.label_px}px; line-height: 1.2; color: ${colors.ink}; opacity: 0; }`;
  const dotsHtml = spec.points
    .map(
      (p) => `
      <div class="pt-dot" id="dot-${esc(p.id)}" style="left: ${p.x}px; top: ${p.y}px;"></div>
      <div class="pt-value" id="val-${esc(p.id)}" style="left: ${p.x - 110}px; top: ${p.y - spec.value_px - 20}px;">${esc(p.value_label)}</div>
      <div class="pt-label" style="left: ${p.x - 140}px; top: ${plot.y + plot.height + 16}px;">${esc(p.label)}</div>`
    )
    .join("\n");
  const annotationsHtml = spec.annotations
    .map((a) => {
      const point = spec.points.find((p) => p.id === a.row_id);
      if (!point) return "";
      // The callout sits on the side of the point with more plot
      // room, so it never covers a neighboring data mark (the same
      // placement rule as the Remotion component).
      const left =
        point.x - plot.x > plot.width / 2 ? point.x - 38 - 430 : point.x + 38;
      return `
      <div class="annotation" id="annotation-${esc(a.id)}" style="left: ${left}px; top: ${point.y - 176}px;">${esc(a.text)}</div>`;
    })
    .join("\n");
  const body = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <div id="axis-left" class="axis"></div>
      <div id="axis-bottom" class="axis"></div>
      <div id="units">${esc(spec.units)}</div>
      <svg id="trend-svg" width="${canvas.width}" height="${canvas.height}" style="position: absolute; left: 0; top: 0;">
        <polyline id="trend-line" fill="none" stroke="${colors.accent}" stroke-width="6" stroke-linejoin="round" stroke-linecap="round" points="" />
      </svg>
      <div id="focus-ring"></div>${dotsHtml}${annotationsHtml}
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.fixture_label)}</div>
      <div id="disclosure" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2">${esc(spec.copy.disclosure)}</div>
    </div>`;
  const states = spec.points.map((_, k) => trendState(spec.points, k));
  const dotTweens = spec.points
    .map(
      (p, i) => `
      tl.fromTo("#dot-${p.id}", { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: ${slotSec / 2}, ease: "none" }, ${startSec + i * slotSec});
      tl.fromTo("#val-${p.id}", { opacity: 0 }, { opacity: 1, duration: ${slotSec / 2}, ease: "none" }, ${startSec + i * slotSec});`
    )
    .join("\n");
  const segmentTweens = states
    .slice(1)
    .map(
      (state, idx) => `
      tl.to("#trend-line", { attr: { points: ${JSON.stringify(state)} }, duration: ${slotSec / 2}, ease: "none" }, ${startSec + (idx + 1.5) * slotSec});`
    )
    .join("\n");
  const ringSets = spec.points
    .map(
      (p, i) => `
      tl.set("#focus-ring", { left: "${p.x - 21}px", top: "${p.y - 21}px", opacity: 1 }, ${startSec + i * slotSec + 0.01});`
    )
    .join("\n");
  const focusSet =
    focusIndex >= 0
      ? `
      tl.set("#focus-ring", { left: "${spec.points[focusIndex].x - 21}px", top: "${spec.points[focusIndex].y - 21}px", opacity: 1 }, ${endSec});`
      : "";
  const annotationTweens = spec.annotations
    .map(
      (a) => `
      tl.to("#annotation-${a.id}", { opacity: 1, duration: 0.5, ease: "none" }, ${endSec});`
    )
    .join("\n");
  const script = `
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      tl.set("#trend-line", { attr: { points: ${JSON.stringify(states[0])} } }, ${startSec + 1.5 * slotSec});${dotTweens}${segmentTweens}${ringSets}${focusSet}${annotationTweens}
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [
      { id: "headline", type: "string", label: "Headline", default: spec.copy.headline },
      { id: "disclosure", type: "string", label: "Disclosure", default: spec.copy.disclosure },
    ],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [spec.id], rootCompositionId: spec.id };
}

// ---------------------------------------------------------------------
// MG-044: C02 product-detail demonstration and C03 before/after
// comparison, registered through the same generator seam as C01.
//
// C02: the authentic product view stays fixed and undistorted on the
// left. On the right, a close view of the SAME source pixels zooms
// from the full view to the declared maximum zoom over the motion
// interval. The zoom window and the annotation anchor are computed by
// the MG-012 close-up geometry (runtime/src/compositing/closeup.ts):
// the generator embeds the per-keyframe window and anchor values that
// geometry produces, and the timeline interpolates between them, so
// the annotation names the same source point at every zoom step.
// The spec's max zoom is refused at authoring time when the MG-012
// upscale assessment exceeds the readable-detail limit, so a shipped
// C02 scene can never claim detail its source does not contain.
//
// C03: both states share one subject box at the same crop and scale.
// The after state is uncovered by a mask whose edge is the comparison
// boundary; the boundary position is a linear function of frame over
// the motion interval (the MG-012 reveal geometry), and both state
// labels are visible at the final hold, where both states remain
// readable together on either side of the boundary's rest position.
// The boundary comes to rest at the declared rest fraction, not at
// the frame edge, so the final composition compares, not replaces.

/** MG-044 scene spec for the C02 product-detail demonstration. */
export interface ProductDetailSceneSpec {
  schema_version: "mg044-1";
  id: string;
  component_id: "C02";
  component_version: "1.0.0";
  variant: "detail_closeup";
  engine: "hyperframes";
  duration_frames: number;
  /** Job-relative path of the original product view asset. */
  asset_file: string;
  asset_sha256?: string;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  /** The product view, undistorted: source pixels at one uniform
   * scale inside this box. */
  product: {
    box: { x: number; y: number; width: number; height: number };
    source: { width: number; height: number };
  };
  detail: {
    /** Normalized detail point over the source (the MG-011 shape). */
    point: { x: number; y: number };
    /** Hex color identifying the detail in decoded frames. */
    measure_color: string;
  };
  zoom: {
    max_zoom: number;
    start_frame: number;
    end_frame_exclusive: number;
    hold_to_frame_exclusive: number;
    /** Where the close view lands on the canvas. */
    output: { x: number; y: number; width: number; height: number };
  };
  copy: {
    headline: string;
    annotation_label: string;
    caption: string;
    fixture_label: string;
  };
  headline_px: number;
  caption_px: number;
  annotation_px: number;
  semantic_motion_assertions: Array<{
    id: string;
    kind: "closeup_detail_fraction";
    frame: number;
    /** Detail-color fraction inside the close-view output box,
     * normalized so the maximum-zoom state measures 1. */
    min_fraction: number;
    max_fraction: number;
  }>;
}

/** MG-044 scene spec for the C03 before/after comparison. */
export interface BeforeAfterSceneSpec {
  schema_version: "mg044-1";
  id: string;
  component_id: "C03";
  component_version: "1.0.0";
  variant: "wipe_reveal";
  engine: "hyperframes";
  duration_frames: number;
  before_file: string;
  before_sha256?: string;
  after_file: string;
  after_sha256?: string;
  font_ref: string;
  canvas: { width: number; height: number };
  design: { colors: { background: string; ink: string; accent: string } };
  subject: {
    id: string;
    box: { x: number; y: number; width: number; height: number };
    /** Hex color identifying after-state pixels in decoded frames. */
    measure_color: string;
  };
  copy: {
    headline: string;
    before_label: string;
    after_label: string;
    caption: string;
    fixture_label: string;
  };
  headline_px: number;
  caption_px: number;
  label_px: number;
  motion: {
    kind: "wipe_reveal";
    start_frame: number;
    end_frame_exclusive: number;
    hold_to_frame_exclusive: number;
    /** Where the boundary rests at the final hold, as a fraction of
     * the subject width from its left edge. */
    rest_fraction: number;
  };
  semantic_motion_assertions: Array<{
    id: string;
    kind: "state_fraction";
    frame: number;
    /** After-state color fraction inside the subject box, normalized
     * so the fully-after state would measure 1. */
    min_fraction: number;
    max_fraction: number;
  }>;
}

export type Mg044SceneSpec = ProductDetailSceneSpec | BeforeAfterSceneSpec;

/** C02 product-detail demonstration: fixed authentic product view, a
 * close view zooming on the MG-012 close-up geometry, and an
 * annotation chip whose marker tracks the detail anchor.
 * Layout discipline (found by visual review during MG-044): the
 * caption block sits on its own row above the fixture label bar
 * (bottom: 128px against the bar's bottom: 52px row); on the bar's
 * row its lines ran underneath the bar at the right. */
export function generateC02Project(input: {
  spec: ProductDetailSceneSpec;
  font: ResolvedFont;
  fps: number;
  assetFileName: string;
}): GeneratedProject {
  const { spec, font, fps, assetFileName } = input;
  const { canvas, product, detail, zoom, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const startSec = seconds(zoom.start_frame, fps);
  const zoomSec = seconds(zoom.end_frame_exclusive - zoom.start_frame, fps);
  const detailSource = {
    x: detail.point.x * product.source.width,
    y: detail.point.y * product.source.height,
  };
  // Keyframes at zoom 1, the midpoint, and the declared maximum: the
  // window and anchor at each come straight from the MG-012 geometry,
  // and the timeline interpolates the rendered background geometry
  // and marker position linearly between them.
  const keyframes = [1, (1 + zoom.max_zoom) / 2, zoom.max_zoom].map((z) => {
    const window = zoomWindowAt(product.source, detailSource, z);
    const anchor = annotationAnchorAt(detailSource, window, zoom.output);
    const scaleX = zoom.output.width / window.width;
    const scaleY = zoom.output.height / window.height;
    return {
      zoom: z,
      bgWidth: product.source.width * scaleX,
      bgHeight: product.source.height * scaleY,
      bgPosX: -window.x * scaleX,
      bgPosY: -window.y * scaleY,
      anchorX: anchor.x,
      anchorY: anchor.y,
    };
  });
  const out = zoom.output;
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 96px; top: 72px; width: ${canvas.width - 192}px; font-size: ${spec.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #product-img { position: absolute; left: ${product.box.x}px; top: ${product.box.y}px; width: ${product.box.width}px; height: ${product.box.height}px; border: 4px solid ${colors.ink}; }
      #product-frame-label { position: absolute; left: ${product.box.x}px; top: ${product.box.y - 52}px; font-size: ${spec.caption_px}px; font-weight: 700; color: ${colors.ink}; }
      #closeup { position: absolute; left: ${out.x}px; top: ${out.y}px; width: ${out.width}px; height: ${out.height}px; overflow: hidden; border: 4px solid ${colors.accent}; background-image: url("./assets/${esc(assetFileName)}"); background-repeat: no-repeat; }
      #anchor-dot { position: absolute; width: 34px; height: 34px; border-radius: 50%; border: 6px solid ${detail.measure_color}; background: transparent; transform: translate(-50%, -50%); }
      #annotation { position: absolute; left: ${out.x}px; top: ${out.y + out.height + 26}px; width: ${out.width}px; padding: 16px 20px; border: 3px solid ${colors.ink}; background: ${colors.background}; font-size: ${spec.annotation_px}px; color: ${colors.ink}; opacity: 0; }
      #caption { position: absolute; left: 96px; bottom: 128px; width: ${canvas.width - 192}px; font-size: ${spec.caption_px}px; color: ${colors.ink}; }
      #fixture-label { position: absolute; right: 96px; bottom: 52px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }`;
  const body = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <div id="product-frame-label">Original view, unmodified</div>
      <img id="product-img" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="1" src="./assets/${esc(assetFileName)}" alt="" />
      <div id="closeup" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2"></div>
      <div id="anchor-dot"></div>
      <div id="annotation" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.annotation_label)}</div>
      <div id="caption" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="4">${esc(spec.copy.caption)}</div>
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="5">${esc(spec.copy.fixture_label)}</div>
    </div>`;
  const kfJson = embeddedJson(
    keyframes.map((k) => ({
      bgW: Math.round(k.bgWidth * 100) / 100,
      bgH: Math.round(k.bgHeight * 100) / 100,
      bgX: Math.round(k.bgPosX * 100) / 100,
      bgY: Math.round(k.bgPosY * 100) / 100,
      ax: Math.round(k.anchorX * 100) / 100,
      ay: Math.round(k.anchorY * 100) / 100,
    }))
  );
  const script = `
      const KF = ${kfJson};
      const closeup = document.getElementById("closeup");
      const dot = document.getElementById("anchor-dot");
      function applyState(a, b, t) {
        const bgW = a.bgW + (b.bgW - a.bgW) * t;
        const bgH = a.bgH + (b.bgH - a.bgH) * t;
        const bgX = a.bgX + (b.bgX - a.bgX) * t;
        const bgY = a.bgY + (b.bgY - a.bgY) * t;
        closeup.style.backgroundSize = bgW + "px " + bgH + "px";
        closeup.style.backgroundPosition = bgX + "px " + bgY + "px";
        dot.style.left = (a.ax + (b.ax - a.ax) * t) + "px";
        dot.style.top = (a.ay + (b.ay - a.ay) * t) + "px";
      }
      applyState(KF[0], KF[0], 0);
      const proxy = { t: 0 };
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      tl.to(proxy, {
        t: 1,
        duration: ${zoomSec},
        ease: "none",
        onUpdate: () => {
          const p = proxy.t * (KF.length - 1);
          const i = Math.min(KF.length - 2, Math.floor(p));
          applyState(KF[i], KF[i + 1], p - i);
        },
      }, ${startSec});
      tl.to("#annotation", { opacity: 1, duration: 0.4, ease: "none" }, ${startSec + zoomSec});
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [{ id: "headline", type: "string", label: "Headline", default: spec.copy.headline }],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [spec.id], rootCompositionId: spec.id };
}

/** C03 before/after comparison: the after state is uncovered by a
 * mask boundary traveling to its declared rest fraction; both state
 * labels and the boundary remain visible at the final hold.
 * Layout discipline (found by the shipped hyperframes check gate
 * during MG-044): the headline stays on one line above the subject
 * box (a two-line headline descends into the subject and the check
 * flags it occluded), the caption stays on one line below it, and
 * the fixture label bar sits at the right of the bottom row, clear
 * of the caption block at the left. */
export function generateC03Project(input: {
  spec: BeforeAfterSceneSpec;
  font: ResolvedFont;
  fps: number;
  beforeFileName: string;
  afterFileName: string;
}): GeneratedProject {
  const { spec, font, fps, beforeFileName, afterFileName } = input;
  const { canvas, subject, design } = spec;
  const colors = design.colors;
  const durationSec = seconds(spec.duration_frames, fps);
  const startSec = seconds(spec.motion.start_frame, fps);
  const wipeSec = seconds(spec.motion.end_frame_exclusive - spec.motion.start_frame, fps);
  const restWidth = Math.round(subject.box.width * spec.motion.rest_fraction);
  const css = `
      body { background: ${colors.background}; }
      #root { position: relative; width: 100%; height: 100%; }
      #headline { position: absolute; left: 96px; top: 72px; width: ${canvas.width - 192}px; font-size: ${spec.headline_px}px; font-weight: 700; color: ${colors.ink}; }
      #before-img { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y}px; width: ${subject.box.width}px; height: ${subject.box.height}px; border: 4px solid ${colors.ink}; }
      #after-mask { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y}px; width: 0px; height: ${subject.box.height}px; overflow: hidden; }
      #after-img { width: ${subject.box.width}px; height: ${subject.box.height}px; display: block; }
      #boundary { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y - 12}px; width: 8px; height: ${subject.box.height + 24}px; background: ${colors.accent}; }
      .state-label { position: absolute; top: ${subject.box.y + 18}px; padding: 8px 16px; font-size: ${spec.label_px}px; font-weight: 700; color: #FFFFFF; background: ${colors.ink}; }
      #after-label { left: ${subject.box.x + 18}px; }
      #before-label { left: ${subject.box.x + subject.box.width - 208}px; width: 190px; text-align: center; }
      #caption { position: absolute; left: ${subject.box.x}px; top: ${subject.box.y + subject.box.height + 28}px; width: ${subject.box.width}px; font-size: ${spec.caption_px}px; color: ${colors.ink}; opacity: 0; }
      #fixture-label { position: absolute; right: 96px; bottom: 52px; padding: 10px 18px; border: 3px solid ${colors.accent}; color: ${colors.accent}; font-size: 30px; font-weight: 700; letter-spacing: 1px; }`;
  const body = `
    <div id="root" data-composition-id="${esc(spec.id)}" data-start="0" data-duration="${durationSec}" data-width="${canvas.width}" data-height="${canvas.height}">
      <div id="headline" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="0">${esc(spec.copy.headline)}</div>
      <img id="before-img" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="1" src="./assets/${esc(beforeFileName)}" alt="" />
      <div id="after-mask" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2">
        <img id="after-img" src="./assets/${esc(afterFileName)}" alt="" />
      </div>
      <div id="boundary"></div>
      <div id="after-label" class="state-label">${esc(spec.copy.after_label)}</div>
      <div id="before-label" class="state-label">${esc(spec.copy.before_label)}</div>
      <div id="caption" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="3">${esc(spec.copy.caption)}</div>
      <div id="fixture-label" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="4">${esc(spec.copy.fixture_label)}</div>
    </div>`;
  const script = `
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#headline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "none" }, 0);
      tl.fromTo("#after-mask", { width: 0 }, { width: ${restWidth}, duration: ${wipeSec}, ease: "none" }, ${startSec});
      tl.fromTo("#boundary", { x: 0 }, { x: ${restWidth - 4}, duration: ${wipeSec}, ease: "none" }, ${startSec});
      tl.to("#caption", { opacity: 1, duration: 0.4, ease: "none" }, ${startSec + wipeSec});
      window.__timelines = window.__timelines || {};
      window.__timelines[${JSON.stringify(spec.id)}] = tl;
      tl.seek(0);`;
  const html = pageShell({
    width: canvas.width,
    height: canvas.height,
    font,
    variables: [{ id: "headline", type: "string", label: "Headline", default: spec.copy.headline }],
    css,
    body,
    script,
  });
  return { files: { "index.html": html }, compositionIds: [spec.id], rootCompositionId: spec.id };
}
