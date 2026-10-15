// The V2 narration script record (MG-025 settlement C, from MG-020).
//
// The canonical V2 contracts carry no narration text field, while the
// V1 pipeline (scripts/tts.py) consumes per-scene voiceover_text from
// a V1 manifest. The V2 convention settled here, at the job-package
// layer the orchestrator owns (the canonical schema is not edited):
//
// - A job that narrates carries narration.json at the job root: the
//   narration script record. Per scene it holds the exact text to
//   speak and, once MG-020 measurement has run, the measured sample
//   range the spoken text occupies at the compiled rate of 48000 Hz.
// - The record is a revision component (see revision.ts): editing the
//   text or its measured timing moves the full revision and stales
//   preview and delivery approvals.
// - Measured ranges flow into the MG-021 compiler as
//   NarrationSegmentInput values through toNarrationSegments: samples
//   convert to frames with the compiler's own helpers (a segment
//   starts in the frame its first sample lands in; its exclusive end
//   is the frame after the frame its last sample lands in), so the
//   compiler, not this record, owns placement arithmetic and the
//   narration-overrun failure (TIMELINE_NARRATION_EXCEEDS_PICTURE).
// - TTS synthesis (scripts/tts.py) keeps consuming the V1 shape on V1
//   jobs. On V2 jobs the narration record is the text source: an
//   adapter projects it to the V1 per-scene voiceover_text shape at
//   the synthesis boundary (projectToVoiceoverTexts), rather than the
//   V2 manifest growing a text field the frozen schema forbids.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { NarrationSegmentInput } from "../timeline/types";
import { TIMELINE_SAMPLE_RATE } from "../timeline/types";
import { sampleToFrameFloor } from "../timeline/samples";

export interface NarrationSceneRecord {
  scene_id: string;
  text: string;
  /** Measured spoken range at 48000 Hz, or null before measurement. */
  measured: { start_sample: number; end_sample: number } | null;
  voice_ref: string | null;
}

export interface NarrationRecord {
  schema_version: "1.0";
  job_id: string;
  kind: "narration_script";
  scenes: NarrationSceneRecord[];
}

export interface NarrationProblem {
  path: string;
  message: string;
}

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The job-relative path of the narration script record. */
export const NARRATION_PATH = "narration.json";

/**
 * Load and validate a job's narration record. Returns the record (or
 * null when the job carries none) plus structural problems. A record
 * that contradicts the manifest (foreign job id, unknown scene) is a
 * problem, never silently ignored.
 */
export function loadNarrationRecord(
  jobDir: string,
  manifest: { job_id: string; scenes: Array<{ id: string }> }
): { record: NarrationRecord | null; problems: NarrationProblem[] } {
  const problems: NarrationProblem[] = [];
  const path = join(jobDir, NARRATION_PATH);
  if (!existsSync(path)) return { record: null, problems };
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch (err) {
    problems.push({
      path: NARRATION_PATH,
      message: `narration.json is not parseable JSON: ${(err as Error).message}`,
    });
    return { record: null, problems };
  }
  if (!isDoc(parsed)) {
    problems.push({ path: NARRATION_PATH, message: "narration.json is not a JSON object." });
    return { record: null, problems };
  }
  if (parsed.schema_version !== "1.0" || parsed.kind !== "narration_script") {
    problems.push({
      path: NARRATION_PATH,
      message: 'narration.json must carry schema_version "1.0" and kind "narration_script".',
    });
  }
  if (parsed.job_id !== manifest.job_id) {
    problems.push({
      path: NARRATION_PATH,
      message: `narration record is bound to job ${String(parsed.job_id)}, not ${manifest.job_id}.`,
    });
  }
  const sceneIds = new Set(manifest.scenes.map((s) => s.id));
  const scenes: NarrationSceneRecord[] = [];
  if (!Array.isArray(parsed.scenes)) {
    problems.push({ path: NARRATION_PATH, message: "narration.json scenes must be an array." });
  } else {
    const seen = new Set<string>();
    for (const entry of parsed.scenes) {
      if (!isDoc(entry) || typeof entry.scene_id !== "string") {
        problems.push({ path: NARRATION_PATH, message: "narration scene entry lacks a scene_id." });
        continue;
      }
      if (!sceneIds.has(entry.scene_id)) {
        problems.push({
          path: NARRATION_PATH,
          message: `narration names scene ${entry.scene_id}, which the manifest does not declare.`,
        });
      }
      if (seen.has(entry.scene_id)) {
        problems.push({
          path: NARRATION_PATH,
          message: `narration carries scene ${entry.scene_id} twice.`,
        });
      }
      seen.add(entry.scene_id);
      if (typeof entry.text !== "string" || entry.text.length === 0) {
        problems.push({
          path: NARRATION_PATH,
          message: `narration scene ${entry.scene_id} carries no text.`,
        });
      }
      let measured: NarrationSceneRecord["measured"] = null;
      if (entry.measured !== null && entry.measured !== undefined) {
        if (
          isDoc(entry.measured) &&
          Number.isInteger(entry.measured.start_sample) &&
          Number.isInteger(entry.measured.end_sample) &&
          (entry.measured.start_sample as number) >= 0 &&
          (entry.measured.start_sample as number) < (entry.measured.end_sample as number)
        ) {
          measured = {
            start_sample: entry.measured.start_sample as number,
            end_sample: entry.measured.end_sample as number,
          };
        } else {
          problems.push({
            path: NARRATION_PATH,
            message:
              `narration scene ${entry.scene_id} measured range must be integer samples ` +
              "with 0 <= start < end at the compiled rate.",
          });
        }
      }
      scenes.push({
        scene_id: entry.scene_id,
        text: typeof entry.text === "string" ? entry.text : "",
        measured,
        voice_ref: typeof entry.voice_ref === "string" ? entry.voice_ref : null,
      });
    }
  }
  const record: NarrationRecord = {
    schema_version: "1.0",
    job_id: manifest.job_id,
    kind: "narration_script",
    scenes,
  };
  return { record, problems };
}

/**
 * Project the record into MG-021 compiler narration inputs. Scenes
 * without a measured range cannot be placed and are skipped here; the
 * gate reports unmeasured narration as an input problem when the job's
 * audio policy requires narration, and the compiler fails loudly if a
 * placed segment overruns the picture.
 */
export function toNarrationSegments(record: NarrationRecord, fps: number): NarrationSegmentInput[] {
  const segments: NarrationSegmentInput[] = [];
  for (const scene of record.scenes) {
    if (!scene.measured) continue;
    const startFrame = sampleToFrameFloor(scene.measured.start_sample, fps);
    const endFrameExclusive = sampleToFrameFloor(scene.measured.end_sample - 1, fps) + 1;
    segments.push({
      id: `narration-${scene.scene_id}`,
      sceneId: scene.scene_id,
      startFrame,
      endFrameExclusive,
    });
  }
  return segments;
}

/** Project the record to the V1 per-scene voiceover_text shape that
 * scripts/tts.py consumes, keyed by scene id. The projection happens
 * at the synthesis boundary; the record stays the V2 source. */
export function projectToVoiceoverTexts(record: NarrationRecord): Record<string, string> {
  const out: Record<string, string> = {};
  for (const scene of record.scenes) out[scene.scene_id] = scene.text;
  return out;
}

/** The compiled audio rate the record's measured samples use. */
export const NARRATION_SAMPLE_RATE = TIMELINE_SAMPLE_RATE;
