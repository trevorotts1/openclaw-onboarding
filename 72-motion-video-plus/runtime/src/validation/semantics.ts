// Cross-file and cross-field semantic validation for a Skill 72 V2 job
// directory: validateJob(jobDir) and firstErrorCategory(findings).
//
// This is the TypeScript half of the shared CONTRACTS validation layer
// (Directive Section 16.6). The Python half implements the same rules and
// the same stable error categories; the shared fixture corpus must produce
// the same first error category in both languages (Directive 16.6 rule 12,
// Section 16.9 exit code 2 family). Categories, in family order:
//   MG_SCHEMA_INVALID, MG_UNKNOWN_COMPONENT, MG_MODE_MISMATCH,
//   MG_TIMELINE_INVALID
//
// Rules implemented (Directive 16.6 items 1 to 6, serialized-input scope):
// - Every document parses and passes its exact versioned $defs schema.
//   A bare unknown key is an error, never silently ignored (closed schemas).
//   The manifest is the one two-phase document: its mode-conditional
//   if/then allOf clauses encode mode agreement inside the schema itself,
//   so violations of those clauses are reported as MG_MODE_MISMATCH (the
//   Section 16.9 mode-conflict family), while violations of the remaining
//   core schema are MG_SCHEMA_INVALID.
// - Scene documents dispatch on their registered component schema. The
//   contracts schema's scene def is closed on the one currently registered
//   component, C05 version 1.0.0 with motion kind linear_bar_reveal. A scene
//   whose only schema errors are const mismatches on component_id,
//   component_version or motion.kind, and whose component_id is a
//   well-formed ID other than C05, is reported once as MG_UNKNOWN_COMPONENT.
//   C05 with a version or kind mismatch stays MG_SCHEMA_INVALID.
// - Scene IDs are unique and consistent across manifest, storyboard,
//   timeline and scene files; every referenced scene file exists.
// - Canvas aspect agrees with mode (Section 16.6 rule 3): PowerPoint and
//   desktop VSL are 16:9, mobile VSL is 9:16, standalone permits only those
//   two ratios in this release, and H.264 dimensions are even.
// - Parent rules: VSL modes require a non-null manifest parent and a
//   parent-handoff.json; PowerPoint and standalone require a null parent.
// - Timeline arithmetic uses half-open integer-frame intervals: total
//   frames equal the manifest duration, scene intervals start before they
//   end and lie within the duration, timeline scene durations agree with
//   the scene files, scene motion start < end <= hold within the scene
//   duration, and a VSL parent slot length equals the insert length.
// - Datasets: values are finite, category (row) IDs are unique, and the
//   scale domain has exactly two strictly increasing endpoints.
// - Audio ownership agrees with mode: PowerPoint requires audio mode
//   "none"; VSL modes require "inherited" or "none" and may never create
//   a voiceover or music track; standalone may not use "inherited".

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { coreManifestSchema, modeConditionalClauses, validateAgainstDef, validateWithSchema } from "./validate";

export type ErrorCategory =
  | "MG_SCHEMA_INVALID"
  | "MG_UNKNOWN_COMPONENT"
  | "MG_MODE_MISMATCH"
  | "MG_TIMELINE_INVALID"
  | "MG_SECURITY_VIOLATION";

export interface Finding {
  category: ErrorCategory;
  /** Job-relative locator, for example "manifest.json/canvas". */
  path: string;
  message: string;
}

// MG_SECURITY_VIOLATION heads the order: Section 16.9 stops security
// errors immediately and never downgrades them. It is produced by the
// adapter asset gate (MG-029), never by validateJob, so the Python
// contracts layer (which orders only the exit-2 family) is unaffected.
const CATEGORY_ORDER: ErrorCategory[] = [
  "MG_SECURITY_VIOLATION",
  "MG_SCHEMA_INVALID",
  "MG_UNKNOWN_COMPONENT",
  "MG_MODE_MISMATCH",
  "MG_TIMELINE_INVALID",
];

/** First blocking category present, in the Section 16.9 family order. */
export function firstErrorCategory(findings: Finding[]): ErrorCategory | null {
  for (const category of CATEGORY_ORDER) {
    if (findings.some((f) => f.category === category)) return category;
  }
  return null;
}

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
const REGISTERED_COMPONENT_ID = "C05";
const COMPONENT_CONST_PATHS = new Set(["/component_id", "/component_version", "/motion/kind"]);

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

interface LoadResult {
  doc: Doc | null;
  rel: string;
}

export function validateJob(jobDir: string): Finding[] {
  const findings: Finding[] = [];
  const add = (category: ErrorCategory, path: string, message: string): void => {
    findings.push({ category, path, message });
  };

  function loadJson(rel: string, required: boolean): LoadResult {
    const abs = join(jobDir, rel);
    if (!existsSync(abs)) {
      if (required) {
        add("MG_SCHEMA_INVALID", rel, `Referenced file is missing: ${rel}`);
      }
      return { doc: null, rel };
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(abs, "utf8"));
    } catch (err) {
      add("MG_SCHEMA_INVALID", rel, `File is not valid JSON: ${rel} (${(err as Error).message})`);
      return { doc: null, rel };
    }
    if (!isDoc(parsed)) {
      add("MG_SCHEMA_INVALID", rel, `Top-level JSON value must be an object: ${rel}`);
      return { doc: null, rel };
    }
    return { doc: parsed, rel };
  }

  function schemaCheck(defName: string, loaded: LoadResult): void {
    if (!loaded.doc) return;
    for (const e of validateAgainstDef(defName, loaded.doc)) {
      add(
        "MG_SCHEMA_INVALID",
        `${loaded.rel}${e.instancePath}`,
        `${defName} schema violation at ${e.instancePath || "/"}: ${e.message}`
      );
    }
  }

  // The manifest is checked in two phases (see validate.ts): the core
  // schema, whose violations are MG_SCHEMA_INVALID, and the schema's
  // mode-conditional if/then clauses, whose violations are mode
  // disagreement and therefore MG_MODE_MISMATCH under Section 16.9.
  function manifestCheck(loaded: LoadResult): void {
    if (!loaded.doc) return;
    for (const e of validateWithSchema(coreManifestSchema(), loaded.doc)) {
      add(
        "MG_SCHEMA_INVALID",
        `${loaded.rel}${e.instancePath}`,
        `manifest schema violation at ${e.instancePath || "/"}: ${e.message}`
      );
    }
    for (const clause of modeConditionalClauses()) {
      const ifMatches = validateWithSchema(clause.if, loaded.doc).length === 0;
      const branch = ifMatches ? clause.then : clause.else;
      if (!branch) continue;
      for (const e of validateWithSchema(branch, loaded.doc)) {
        add(
          "MG_MODE_MISMATCH",
          `${loaded.rel}${e.instancePath}`,
          `manifest disagrees with its mode at ${e.instancePath || "/"}: ${e.message}`
        );
      }
    }
  }

  // ---- Manifest -----------------------------------------------------------
  const manifestLoad = loadJson("manifest.json", true);
  if (!manifestLoad.doc) return findings;
  const manifest = manifestLoad.doc;
  manifestCheck(manifestLoad);

  const mode = asString(manifest.mode);
  const durationFrames = isInt(manifest.duration_frames) ? manifest.duration_frames : null;

  const refName = (field: string, fallback: string): string => {
    const v = asString(manifest[field]);
    return v && v.length > 0 ? v : fallback;
  };

  // ---- Companion documents -------------------------------------------------
  const storyboardLoad = loadJson(refName("storyboard", "storyboard.json"), true);
  schemaCheck("storyboard", storyboardLoad);
  const assetsLoad = loadJson(refName("assets", "assets.json"), true);
  schemaCheck("assets", assetsLoad);
  const designLoad = loadJson(refName("design", "design.json"), true);
  schemaCheck("design", designLoad);
  const timelineLoad = loadJson(refName("timeline", "timeline.json"), true);
  schemaCheck("timeline", timelineLoad);

  // ---- Datasets ------------------------------------------------------------
  const dataDir = join(jobDir, "data");
  if (existsSync(dataDir)) {
    const names = readdirSync(dataDir)
      .filter((n) => n.endsWith(".json"))
      .sort();
    for (const name of names) {
      const loaded = loadJson(join("data", name), true);
      if (!loaded.doc) continue;
      schemaCheck("dataset", loaded);
      const ds = loaded.doc;
      const domain = ds.domain;
      if (Array.isArray(domain)) {
        if (domain.length !== 2) {
          add(
            "MG_SCHEMA_INVALID",
            `${loaded.rel}/domain`,
            "Dataset domain must have exactly two endpoints."
          );
        } else if (
          typeof domain[0] !== "number" ||
          typeof domain[1] !== "number" ||
          !Number.isFinite(domain[0]) ||
          !Number.isFinite(domain[1]) ||
          !(domain[0] < domain[1])
        ) {
          add(
            "MG_SCHEMA_INVALID",
            `${loaded.rel}/domain`,
            "Dataset domain endpoints must be finite and strictly increasing."
          );
        }
      }
      const rows = ds.rows;
      if (Array.isArray(rows)) {
        const seen = new Set<string>();
        for (const row of rows) {
          if (!isDoc(row)) continue;
          const rowId = asString(row.id);
          if (rowId) {
            if (seen.has(rowId)) {
              add(
                "MG_SCHEMA_INVALID",
                `${loaded.rel}/rows`,
                `Duplicate dataset category id "${rowId}".`
              );
            }
            seen.add(rowId);
          }
          if (typeof row.value !== "number" || !Number.isFinite(row.value)) {
            add(
              "MG_SCHEMA_INVALID",
              `${loaded.rel}/rows`,
              `Dataset row "${rowId ?? "?"}" has a non-finite value.`
            );
          }
        }
      }
    }
  }

  // ---- Scenes ---------------------------------------------------------------
  const manifestScenes: Array<{ id: string | null; spec: string | null }> = Array.isArray(
    manifest.scenes
  )
    ? manifest.scenes.map((s) => ({
        id: isDoc(s) ? asString(s.id) : null,
        spec: isDoc(s) ? asString(s.spec) : null,
      }))
    : [];
  const manifestIds: string[] = [];
  {
    const seen = new Set<string>();
    for (const entry of manifestScenes) {
      if (!entry.id) continue;
      if (seen.has(entry.id)) {
        add(
          "MG_SCHEMA_INVALID",
          "manifest.json/scenes",
          `Duplicate scene id "${entry.id}" in the manifest.`
        );
      }
      seen.add(entry.id);
      manifestIds.push(entry.id);
    }
  }
  const manifestIdSet = new Set(manifestIds);
  const sceneDocs = new Map<string, { doc: Doc; rel: string }>();

  for (const entry of manifestScenes) {
    if (!entry.spec) continue;
    const loaded = loadJson(entry.spec, true);
    if (!loaded.doc) continue;
    const doc = loaded.doc;
    const errors = validateAgainstDef("scene", doc);
    if (errors.length > 0) {
      const onlyComponentConsts = errors.every(
        (e) => e.keyword === "const" && COMPONENT_CONST_PATHS.has(e.instancePath)
      );
      const componentId = asString(doc.component_id);
      if (
        onlyComponentConsts &&
        componentId !== null &&
        ID_PATTERN.test(componentId) &&
        componentId !== REGISTERED_COMPONENT_ID
      ) {
        add(
          "MG_UNKNOWN_COMPONENT",
          `${loaded.rel}/component_id`,
          `Scene references unregistered component "${componentId}". ` +
            `Only ${REGISTERED_COMPONENT_ID} is registered in this contracts version.`
        );
      } else {
        for (const e of errors) {
          add(
            "MG_SCHEMA_INVALID",
            `${loaded.rel}${e.instancePath}`,
            `scene schema violation at ${e.instancePath || "/"}: ${e.message}`
          );
        }
      }
    }
    const sceneId = asString(doc.id);
    if (entry.id && sceneId && sceneId !== entry.id) {
      add(
        "MG_SCHEMA_INVALID",
        `${loaded.rel}/id`,
        `Scene file id "${sceneId}" does not match manifest scene id "${entry.id}".`
      );
    }
    if (entry.id) sceneDocs.set(entry.id, { doc, rel: loaded.rel });

    // Motion interval arithmetic inside the scene.
    const motion = isDoc(doc.motion) ? doc.motion : null;
    const sceneDuration = isInt(doc.duration_frames) ? doc.duration_frames : null;
    if (motion && sceneDuration !== null) {
      const start = motion.start_frame;
      const end = motion.end_frame_exclusive;
      const hold = motion.hold_to_frame_exclusive;
      if (isInt(start) && isInt(end) && !(start < end)) {
        add(
          "MG_TIMELINE_INVALID",
          `${loaded.rel}/motion`,
          "Scene motion start_frame must be before end_frame_exclusive."
        );
      }
      if (isInt(end) && isInt(hold) && !(end <= hold)) {
        add(
          "MG_TIMELINE_INVALID",
          `${loaded.rel}/motion`,
          "Scene motion end_frame_exclusive must not pass hold_to_frame_exclusive."
        );
      }
      if (isInt(hold) && !(hold <= sceneDuration)) {
        add(
          "MG_TIMELINE_INVALID",
          `${loaded.rel}/motion`,
          "Scene motion hold must lie within the scene duration."
        );
      }
    }
  }

  // ---- Scene ID consistency across storyboard and timeline ------------------
  if (storyboardLoad.doc && Array.isArray(storyboardLoad.doc.beats)) {
    const beatIds = new Set<string>();
    const beatSceneIds = new Set<string>();
    for (const beat of storyboardLoad.doc.beats) {
      if (!isDoc(beat)) continue;
      const beatId = asString(beat.id);
      if (beatId) {
        if (beatIds.has(beatId)) {
          add(
            "MG_SCHEMA_INVALID",
            "storyboard.json/beats",
            `Duplicate storyboard beat id "${beatId}".`
          );
        }
        beatIds.add(beatId);
      }
      const sceneId = asString(beat.scene_id);
      if (sceneId) {
        beatSceneIds.add(sceneId);
        if (!manifestIdSet.has(sceneId)) {
          add(
            "MG_SCHEMA_INVALID",
            "storyboard.json/beats",
            `Storyboard beat references unknown scene "${sceneId}".`
          );
        }
      }
    }
    for (const id of manifestIds) {
      if (!beatSceneIds.has(id)) {
        add(
          "MG_SCHEMA_INVALID",
          "storyboard.json/beats",
          `Scene "${id}" has no storyboard beat.`
        );
      }
    }
  }

  const timeline = timelineLoad.doc;
  if (timeline) {
    if (durationFrames !== null && isInt(timeline.total_frames)) {
      if (timeline.total_frames !== durationFrames) {
        add(
          "MG_TIMELINE_INVALID",
          "timeline.json/total_frames",
          `Timeline total_frames ${timeline.total_frames} does not equal manifest duration_frames ${durationFrames}.`
        );
      }
    }
    if (Array.isArray(timeline.scenes)) {
      const timelineIds = new Set<string>();
      for (const entry of timeline.scenes) {
        if (!isDoc(entry)) continue;
        const sceneId = asString(entry.id);
        if (sceneId) {
          if (timelineIds.has(sceneId)) {
            add(
              "MG_SCHEMA_INVALID",
              "timeline.json/scenes",
              `Duplicate scene id "${sceneId}" in the timeline.`
            );
          }
          timelineIds.add(sceneId);
          if (!manifestIdSet.has(sceneId)) {
            add(
              "MG_SCHEMA_INVALID",
              "timeline.json/scenes",
              `Timeline references unknown scene "${sceneId}".`
            );
          }
        }
        const start = entry.start_frame;
        const end = entry.end_frame_exclusive;
        if (isInt(start) && isInt(end)) {
          if (!(start < end)) {
            add(
              "MG_TIMELINE_INVALID",
              "timeline.json/scenes",
              `Scene "${sceneId ?? "?"}" interval start must be before end.`
            );
          }
          if (durationFrames !== null && (start < 0 || end > durationFrames)) {
            add(
              "MG_TIMELINE_INVALID",
              "timeline.json/scenes",
              `Scene "${sceneId ?? "?"}" interval lies outside the job duration.`
            );
          }
          if (sceneId && sceneDocs.has(sceneId)) {
            const sceneDuration = sceneDocs.get(sceneId)!.doc.duration_frames;
            if (isInt(sceneDuration) && end - start !== sceneDuration) {
              add(
                "MG_TIMELINE_INVALID",
                "timeline.json/scenes",
                `Timeline duration for scene "${sceneId}" (${end - start}) disagrees with the scene file (${sceneDuration}).`
              );
            }
          }
        }
      }
      for (const id of manifestIds) {
        if (!timelineIds.has(id)) {
          add(
            "MG_SCHEMA_INVALID",
            "timeline.json/scenes",
            `Scene "${id}" is missing from the timeline.`
          );
        }
      }
    }
    if (Array.isArray(timeline.events) && durationFrames !== null) {
      for (const event of timeline.events) {
        if (!isDoc(event)) continue;
        const frame = event.frame;
        if (isInt(frame) && (frame < 0 || frame >= durationFrames)) {
          add(
            "MG_TIMELINE_INVALID",
            "timeline.json/events",
            `Timeline event "${asString(event.id) ?? "?"}" frame lies outside the rendered frames.`
          );
        }
      }
    }
    const parentSlot = isDoc(timeline.parent_slot) ? timeline.parent_slot : null;
    if (parentSlot && durationFrames !== null) {
      const s = parentSlot.start_frame;
      const e = parentSlot.end_frame_exclusive;
      if (isInt(s) && isInt(e) && e - s !== durationFrames) {
        add(
          "MG_TIMELINE_INVALID",
          "timeline.json/parent_slot",
          "Parent slot length must equal the insert duration_frames."
        );
      }
    }
  }

  // Poster frame must lie within the rendered frames (Directive 16.6 rule 4).
  if (isDoc(manifest.delivery) && durationFrames !== null) {
    const poster = manifest.delivery.poster_frame;
    if (isInt(poster) && (poster < 0 || poster >= durationFrames)) {
      add(
        "MG_TIMELINE_INVALID",
        "manifest.json/delivery/poster_frame",
        "Poster frame lies outside the rendered frames."
      );
    }
  }

  // ---- Mode, canvas, parent and audio agreement ------------------------------
  const canvas = isDoc(manifest.canvas) ? manifest.canvas : null;
  if (canvas && mode) {
    const w = canvas.width;
    const h = canvas.height;
    if (isInt(w) && isInt(h) && w >= 2 && h >= 2) {
      const is169 = w * 9 === h * 16;
      const is916 = w * 16 === h * 9;
      if ((mode === "powerpoint_graphic" || mode === "vsl_desktop") && !is169) {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/canvas",
          `Mode ${mode} requires a 16:9 canvas; got ${w}x${h}.`
        );
      } else if (mode === "vsl_mobile" && !is916) {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/canvas",
          `Mode vsl_mobile requires a 9:16 canvas; got ${w}x${h}.`
        );
      } else if (mode === "standalone_video" && !is169 && !is916) {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/canvas",
          `Mode standalone_video permits only 16:9 or 9:16 in this release; got ${w}x${h}.`
        );
      }
      if (w % 2 !== 0 || h % 2 !== 0) {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/canvas",
          `H.264 dimensions must be even; got ${w}x${h}.`
        );
      }
    }
  }

  const parent = isDoc(manifest.parent) ? manifest.parent : null;
  if (mode === "vsl_desktop" || mode === "vsl_mobile") {
    if (!parent) {
      add(
        "MG_MODE_MISMATCH",
        "manifest.json/parent",
        `Mode ${mode} requires a non-null parent.`
      );
    }
    const handoffRel =
      parent && asString(parent.handoff_path) ? (asString(parent.handoff_path) as string) : "parent-handoff.json";
    if (!existsSync(join(jobDir, handoffRel))) {
      add(
        "MG_MODE_MISMATCH",
        handoffRel,
        `Mode ${mode} requires the parent handoff file ${handoffRel}.`
      );
    }
    if (parent && durationFrames !== null && isDoc(parent.slot)) {
      const s = parent.slot.start_frame;
      const e = parent.slot.end_frame_exclusive;
      if (isInt(s) && isInt(e) && e - s !== durationFrames) {
        add(
          "MG_TIMELINE_INVALID",
          "manifest.json/parent/slot",
          "Parent slot length must equal the insert duration_frames."
        );
      }
    }
  } else if (mode === "powerpoint_graphic" || mode === "standalone_video") {
    if (manifest.parent !== null && manifest.parent !== undefined) {
      add(
        "MG_MODE_MISMATCH",
        "manifest.json/parent",
        `Mode ${mode} requires a null parent.`
      );
    }
  }

  // Validate the handoff document whenever it is present.
  const handoffFile = join(jobDir, "parent-handoff.json");
  if (existsSync(handoffFile)) {
    schemaCheck("parent_handoff", loadJson("parent-handoff.json", false));
  }

  const audio = isDoc(manifest.audio) ? manifest.audio : null;
  if (audio && mode) {
    const audioMode = asString(audio.mode);
    if (mode === "powerpoint_graphic" && audioMode !== "none") {
      add(
        "MG_MODE_MISMATCH",
        "manifest.json/audio",
        `Mode powerpoint_graphic requires audio mode "none"; got "${audioMode ?? "?"}".`
      );
    }
    if (mode === "vsl_desktop" || mode === "vsl_mobile") {
      if (audioMode !== "inherited" && audioMode !== "none") {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/audio",
          `Mode ${mode} requires audio mode "inherited" or "none"; got "${audioMode ?? "?"}".`
        );
      }
      if (audio.create_voiceover === true || audio.create_music === true) {
        add(
          "MG_MODE_MISMATCH",
          "manifest.json/audio",
          "A VSL insert is silent: it must not create a voiceover or music track."
        );
      }
    }
    if (mode === "standalone_video" && audioMode === "inherited") {
      add(
        "MG_MODE_MISMATCH",
        "manifest.json/audio",
        'Mode standalone_video may not use audio mode "inherited" (there is no parent).'
      );
    }
  }

  return findings;
}
