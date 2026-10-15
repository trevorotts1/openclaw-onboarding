// The timeline compiler (Directive MG-021, Sections 5.4 and 16).
//
// compileTimeline(input) is the single entry point. It takes an
// unvalidated value (typically parsed JSON), validates its shape under
// the contracts layer's closed-schema discipline (unknown keys are
// errors, MG_SCHEMA_INVALID), then compiles placement and checks the
// timing doctrine (MG_TIMELINE_INVALID with a stable named rule at the
// start of each message). It never throws on bad data: failures are
// findings. It never silently adjusts a duration: a plan that does not
// fit is a failed plan.
//
// Placement arithmetic (the whole point of the item):
// - Scenes are placed in declaration order. The first scene starts at
//   output frame 0. Each later scene starts at (previous scene's placed
//   end) minus (the declared transition's frames). The overlap is
//   subtracted exactly once, here; no scene, caption, narration, or
//   SFX code recomputes it (Section 5.4).
// - Program mode: the total is the last scene's placed end.
// - Slot mode: scenes are placed in slot-local frames and their
//   compiled total must equal the parent slot length exactly. Edge
//   transitions consume parent-granted handle frames outside the slot
//   and never change the total.

import type { Finding } from "../validation/semantics";
import type { Timeline } from "../validation/generated-types";
import { validateAgainstDef } from "../validation/validate";
import {
  TIMELINE_ROUNDING_RULE,
  TIMELINE_SAMPLE_RATE,
  type CompiledCue,
  type CompiledHandle,
  type CompiledRangeTrack,
  type CompiledSceneDetail,
  type CompiledSfx,
  type CompiledTimeline,
  type DeclaredPropertyOverlap,
  type TimelineCompileInput,
  type TimelineSidecar,
} from "./types";
import { frameToSample, rangeMidpointSample, sampleToFrameFloor, secondsToFrame, secondsToSample } from "./samples";

export type CompileResult =
  | { ok: true; compiled: CompiledTimeline }
  | { ok: false; findings: Finding[] };

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
const CUE_TYPES = ["reveal_start", "proof", "hold_start", "cue"];
const ANCHOR_KINDS = ["semantic_state", "spoken_word", "music_beat"];

function schemaFinding(path: string, message: string): Finding {
  return { category: "MG_SCHEMA_INVALID", path, message };
}

function timelineFinding(path: string, kind: string, message: string): Finding {
  return { category: "MG_TIMELINE_INVALID", path, message: `${kind}: ${message}` };
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function checkClosedKeys(
  findings: Finding[],
  path: string,
  rec: Record<string, unknown>,
  allowed: readonly string[]
): void {
  for (const key of Object.keys(rec)) {
    if (!allowed.includes(key)) {
      findings.push(schemaFinding(`${path}/${key}`, `unknown key "${key}" is not part of the timeline compiler input`));
    }
  }
}

function checkId(findings: Finding[], path: string, v: unknown, what: string): void {
  if (typeof v !== "string" || !ID_PATTERN.test(v)) {
    findings.push(schemaFinding(path, `${what} must be a string matching ${ID_PATTERN.source}`));
  }
}

function checkInt(
  findings: Finding[],
  path: string,
  v: unknown,
  what: string,
  min: number
): void {
  if (typeof v !== "number" || !Number.isInteger(v) || v < min) {
    findings.push(schemaFinding(path, `${what} must be an integer >= ${min}`));
  }
}

function checkRangeShape(
  findings: Finding[],
  path: string,
  rec: Record<string, unknown>,
  startKey: string,
  endKey: string
): void {
  checkInt(findings, `${path}/${startKey}`, rec[startKey], "range start", 0);
  checkInt(findings, `${path}/${endKey}`, rec[endKey], "range end", 0);
  const s = rec[startKey];
  const e = rec[endKey];
  if (typeof s === "number" && typeof e === "number" && Number.isInteger(s) && Number.isInteger(e) && e <= s) {
    findings.push(schemaFinding(path, `range end (${e}) must be after range start (${s})`));
  }
}

/** Phase 1: shape validation. Returns the input typed, or null with
 * findings. Semantic checks never run on a malformed shape. */
function validateShape(input: unknown, findings: Finding[]): TimelineCompileInput | null {
  if (!isRecord(input)) {
    findings.push(schemaFinding("", "timeline compiler input must be an object"));
    return null;
  }
  checkClosedKeys(findings, "", input, [
    "jobId", "fps", "mode", "audioOwner", "parentSlot", "edgeTransition",
    "scenes", "transitions", "narration", "captions", "sfxCues", "cues",
    "musicGrid", "propertyTracks",
  ]);
  checkId(findings, "/jobId", input.jobId, "jobId");
  if (input.fps !== 30 && input.fps !== 60) {
    findings.push(schemaFinding("/fps", "fps must be 30 or 60"));
  }
  if (input.mode !== "program" && input.mode !== "slot") {
    findings.push(schemaFinding("/mode", 'mode must be "program" or "slot"'));
  }
  if (input.audioOwner !== "none" && input.audioOwner !== "parent" && input.audioOwner !== "self") {
    findings.push(schemaFinding("/audioOwner", 'audioOwner must be "none", "parent", or "self"'));
  }

  if (input.parentSlot !== undefined && input.parentSlot !== null) {
    const p = input.parentSlot;
    if (!isRecord(p)) {
      findings.push(schemaFinding("/parentSlot", "parentSlot must be an object or null"));
    } else {
      checkClosedKeys(findings, "/parentSlot", p, ["range", "grantedHandles"]);
      if (!isRecord(p.range)) {
        findings.push(schemaFinding("/parentSlot/range", "parentSlot.range must be a frame range object"));
      } else {
        checkClosedKeys(findings, "/parentSlot/range", p.range, ["startFrame", "endFrameExclusive"]);
        checkRangeShape(findings, "/parentSlot/range", p.range, "startFrame", "endFrameExclusive");
      }
      if (!isRecord(p.grantedHandles)) {
        findings.push(schemaFinding("/parentSlot/grantedHandles", "grantedHandles must be an object"));
      } else {
        checkClosedKeys(findings, "/parentSlot/grantedHandles", p.grantedHandles, ["headFrames", "tailFrames"]);
        checkInt(findings, "/parentSlot/grantedHandles/headFrames", p.grantedHandles.headFrames, "granted head handle", 0);
        checkInt(findings, "/parentSlot/grantedHandles/tailFrames", p.grantedHandles.tailFrames, "granted tail handle", 0);
      }
    }
  }
  if (input.edgeTransition !== undefined && input.edgeTransition !== null) {
    const e = input.edgeTransition;
    if (!isRecord(e)) {
      findings.push(schemaFinding("/edgeTransition", "edgeTransition must be an object or null"));
    } else {
      checkClosedKeys(findings, "/edgeTransition", e, ["headFrames", "tailFrames"]);
      checkInt(findings, "/edgeTransition/headFrames", e.headFrames, "edge head transition", 0);
      checkInt(findings, "/edgeTransition/tailFrames", e.tailFrames, "edge tail transition", 0);
    }
  }

  if (!Array.isArray(input.scenes) || input.scenes.length < 1) {
    findings.push(schemaFinding("/scenes", "scenes must be an array with at least one scene"));
  } else {
    const seen = new Set<string>();
    input.scenes.forEach((raw, i) => {
      const path = `/scenes/${i}`;
      if (!isRecord(raw)) {
        findings.push(schemaFinding(path, "scene must be an object"));
        return;
      }
      checkClosedKeys(findings, path, raw, ["id", "durationFrames", "sourceStartFrame", "sourceDurationFrames"]);
      checkId(findings, `${path}/id`, raw.id, "scene id");
      if (typeof raw.id === "string") {
        if (seen.has(raw.id)) findings.push(schemaFinding(`${path}/id`, `duplicate scene id "${raw.id}"`));
        seen.add(raw.id);
      }
      checkInt(findings, `${path}/durationFrames`, raw.durationFrames, "scene durationFrames", 1);
      if (raw.sourceStartFrame !== undefined) checkInt(findings, `${path}/sourceStartFrame`, raw.sourceStartFrame, "sourceStartFrame", 0);
      if (raw.sourceDurationFrames !== undefined) checkInt(findings, `${path}/sourceDurationFrames`, raw.sourceDurationFrames, "sourceDurationFrames", 1);
    });
  }

  if (input.transitions !== undefined) {
    if (!Array.isArray(input.transitions)) {
      findings.push(schemaFinding("/transitions", "transitions must be an array"));
    } else {
      const seen = new Set<string>();
      input.transitions.forEach((raw, i) => {
        const path = `/transitions/${i}`;
        if (!isRecord(raw)) {
          findings.push(schemaFinding(path, "transition must be an object"));
          return;
        }
        checkClosedKeys(findings, path, raw, ["id", "fromSceneId", "toSceneId", "frames", "ownerSceneId"]);
        checkId(findings, `${path}/id`, raw.id, "transition id");
        if (typeof raw.id === "string") {
          if (seen.has(raw.id)) findings.push(schemaFinding(`${path}/id`, `duplicate transition id "${raw.id}"`));
          seen.add(raw.id);
        }
        checkId(findings, `${path}/fromSceneId`, raw.fromSceneId, "transition fromSceneId");
        checkId(findings, `${path}/toSceneId`, raw.toSceneId, "transition toSceneId");
        checkId(findings, `${path}/ownerSceneId`, raw.ownerSceneId, "transition ownerSceneId");
        checkInt(findings, `${path}/frames`, raw.frames, "transition frames (declare no transition for a hard cut)", 1);
      });
    }
  }

  const checkTrackArray = (
    key: "narration" | "captions",
    withWords: boolean
  ): void => {
    const arr = input[key];
    if (arr === undefined) return;
    if (!Array.isArray(arr)) {
      findings.push(schemaFinding(`/${key}`, `${key} must be an array`));
      return;
    }
    const seen = new Set<string>();
    arr.forEach((raw, i) => {
      const path = `/${key}/${i}`;
      if (!isRecord(raw)) {
        findings.push(schemaFinding(path, `${key} entry must be an object`));
        return;
      }
      checkClosedKeys(findings, path, raw, withWords ? ["id", "sceneId", "startFrame", "endFrameExclusive", "words"] : ["id", "sceneId", "startFrame", "endFrameExclusive"]);
      checkId(findings, `${path}/id`, raw.id, `${key} id`);
      if (typeof raw.id === "string") {
        if (seen.has(raw.id)) findings.push(schemaFinding(`${path}/id`, `duplicate ${key} id "${raw.id}"`));
        seen.add(raw.id);
      }
      if (raw.sceneId !== undefined) checkId(findings, `${path}/sceneId`, raw.sceneId, "sceneId");
      checkRangeShape(findings, path, raw, "startFrame", "endFrameExclusive");
      if (withWords && raw.words !== undefined) {
        if (!Array.isArray(raw.words)) {
          findings.push(schemaFinding(`${path}/words`, "words must be an array"));
        } else {
          const idxSeen = new Set<number>();
          raw.words.forEach((w, j) => {
            const wp = `${path}/words/${j}`;
            if (!isRecord(w)) {
              findings.push(schemaFinding(wp, "word must be an object"));
              return;
            }
            checkClosedKeys(findings, wp, w, ["index", "startSample", "endSample"]);
            checkInt(findings, `${wp}/index`, w.index, "word index", 0);
            if (typeof w.index === "number") {
              if (idxSeen.has(w.index)) findings.push(schemaFinding(`${wp}/index`, `duplicate word index ${w.index}`));
              idxSeen.add(w.index);
            }
            checkRangeShape(findings, wp, w, "startSample", "endSample");
          });
        }
      }
    });
  };
  checkTrackArray("narration", true);
  checkTrackArray("captions", false);

  if (input.sfxCues !== undefined) {
    if (!Array.isArray(input.sfxCues)) {
      findings.push(schemaFinding("/sfxCues", "sfxCues must be an array"));
    } else {
      const seen = new Set<string>();
      input.sfxCues.forEach((raw, i) => {
        const path = `/sfxCues/${i}`;
        if (!isRecord(raw)) {
          findings.push(schemaFinding(path, "sfx cue must be an object"));
          return;
        }
        checkClosedKeys(findings, path, raw, ["id", "sceneId", "frame"]);
        checkId(findings, `${path}/id`, raw.id, "sfx cue id");
        if (typeof raw.id === "string") {
          if (seen.has(raw.id)) findings.push(schemaFinding(`${path}/id`, `duplicate sfx cue id "${raw.id}"`));
          seen.add(raw.id);
        }
        if (raw.sceneId !== undefined) checkId(findings, `${path}/sceneId`, raw.sceneId, "sceneId");
        checkInt(findings, `${path}/frame`, raw.frame, "sfx cue frame", 0);
      });
    }
  }

  if (input.musicGrid !== undefined && input.musicGrid !== null) {
    const g = input.musicGrid;
    if (!isRecord(g)) {
      findings.push(schemaFinding("/musicGrid", "musicGrid must be an object or null"));
    } else {
      checkClosedKeys(findings, "/musicGrid", g, ["bpm", "firstBeatFrame"]);
      if (typeof g.bpm !== "number" || !Number.isFinite(g.bpm) || g.bpm <= 0) {
        findings.push(schemaFinding("/musicGrid/bpm", "music grid bpm must be a positive finite number"));
      }
      checkInt(findings, "/musicGrid/firstBeatFrame", g.firstBeatFrame, "firstBeatFrame", 0);
    }
  }

  if (input.cues !== undefined) {
    if (!Array.isArray(input.cues)) {
      findings.push(schemaFinding("/cues", "cues must be an array"));
    } else {
      const seen = new Set<string>();
      input.cues.forEach((raw, i) => {
        const path = `/cues/${i}`;
        if (!isRecord(raw)) {
          findings.push(schemaFinding(path, "cue must be an object"));
          return;
        }
        checkClosedKeys(findings, path, raw, ["id", "sceneId", "type", "anchor"]);
        checkId(findings, `${path}/id`, raw.id, "cue id");
        if (typeof raw.id === "string") {
          if (seen.has(raw.id)) findings.push(schemaFinding(`${path}/id`, `duplicate cue id "${raw.id}"`));
          seen.add(raw.id);
        }
        checkId(findings, `${path}/sceneId`, raw.sceneId, "cue sceneId");
        if (typeof raw.type !== "string" || !CUE_TYPES.includes(raw.type)) {
          findings.push(schemaFinding(`${path}/type`, `cue type must be one of ${CUE_TYPES.join(", ")}`));
        }
        if (!isRecord(raw.anchor)) {
          findings.push(schemaFinding(`${path}/anchor`, "cue anchor must be an object"));
          return;
        }
        const a = raw.anchor;
        const ap = `${path}/anchor`;
        if (typeof a.kind !== "string" || !ANCHOR_KINDS.includes(a.kind)) {
          findings.push(schemaFinding(`${ap}/kind`, `anchor kind must be one of ${ANCHOR_KINDS.join(", ")}`));
          return;
        }
        if (a.kind === "semantic_state") {
          checkClosedKeys(findings, ap, a, ["kind", "state", "sceneLocalFrame"]);
          if (typeof a.state !== "string" || a.state.length === 0) {
            findings.push(schemaFinding(`${ap}/state`, "semantic_state anchor requires a non-empty state name"));
          }
          checkInt(findings, `${ap}/sceneLocalFrame`, a.sceneLocalFrame, "sceneLocalFrame", 0);
        } else if (a.kind === "spoken_word") {
          checkClosedKeys(findings, ap, a, ["kind", "segmentId", "wordIndex"]);
          checkId(findings, `${ap}/segmentId`, a.segmentId, "spoken_word segmentId");
          checkInt(findings, `${ap}/wordIndex`, a.wordIndex, "wordIndex", 0);
        } else {
          checkClosedKeys(findings, ap, a, ["kind", "beatIndex"]);
          checkInt(findings, `${ap}/beatIndex`, a.beatIndex, "beatIndex", 0);
        }
      });
    }
  }

  if (input.propertyTracks !== undefined) {
    if (!Array.isArray(input.propertyTracks)) {
      findings.push(schemaFinding("/propertyTracks", "propertyTracks must be an array"));
    } else {
      input.propertyTracks.forEach((raw, i) => {
        const path = `/propertyTracks/${i}`;
        if (!isRecord(raw)) {
          findings.push(schemaFinding(path, "property track must be an object"));
          return;
        }
        checkClosedKeys(findings, path, raw, ["sceneId", "property", "writes"]);
        checkId(findings, `${path}/sceneId`, raw.sceneId, "property track sceneId");
        if (typeof raw.property !== "string" || raw.property.length === 0) {
          findings.push(schemaFinding(`${path}/property`, "property track requires a non-empty property name"));
        }
        if (!Array.isArray(raw.writes) || raw.writes.length < 1) {
          findings.push(schemaFinding(`${path}/writes`, "property track writes must be a non-empty array"));
        } else {
          raw.writes.forEach((w, j) => {
            const wp = `${path}/writes/${j}`;
            if (!isRecord(w)) {
              findings.push(schemaFinding(wp, "property write must be an object"));
              return;
            }
            checkClosedKeys(findings, wp, w, ["startFrame", "endFrameExclusive", "intentionalOverlap"]);
            checkRangeShape(findings, wp, w, "startFrame", "endFrameExclusive");
            if (w.intentionalOverlap !== undefined && typeof w.intentionalOverlap !== "boolean") {
              findings.push(schemaFinding(`${wp}/intentionalOverlap`, "intentionalOverlap must be a boolean"));
            }
          });
        }
      });
    }
  }

  return findings.length === 0 ? (input as unknown as TimelineCompileInput) : null;
}

/** Compile one authoritative timeline. See the module header for the
 * placement arithmetic and the failure discipline. */
export function compileTimeline(input: unknown): CompileResult {
  const findings: Finding[] = [];
  const typed = validateShape(input, findings);
  if (!typed) return { ok: false, findings };

  const fps = typed.fps;
  const scenes = typed.scenes;
  const sceneIndex = new Map(scenes.map((s, i) => [s.id, i] as const));
  const transitions = typed.transitions ?? [];

  // ---- Mode and slot discipline -------------------------------------
  const slot = typed.parentSlot ?? null;
  const edge = typed.edgeTransition ?? null;
  if (typed.mode === "slot" && !slot) {
    findings.push(timelineFinding("/parentSlot", "TIMELINE_SLOT_MISSING",
      "slot mode requires a parentSlot; a fixed-duration insert cannot be compiled without the parent's slot and granted handles"));
  }
  if (typed.mode === "program" && slot) {
    findings.push(timelineFinding("/parentSlot", "TIMELINE_SLOT_MODE_CONFLICT",
      "program mode takes no parentSlot; parent slots belong to fixed-duration inserts"));
  }
  if (typed.mode === "program" && edge) {
    findings.push(timelineFinding("/edgeTransition", "TIMELINE_SLOT_MODE_CONFLICT",
      "edge transitions consume parent-granted handles and exist only in slot mode"));
  }
  let slotLength = 0;
  if (slot) slotLength = slot.range.endFrameExclusive - slot.range.startFrame;
  const usedHead = edge?.headFrames ?? 0;
  const usedTail = edge?.tailFrames ?? 0;
  if (slot && edge) {
    if (usedHead > slot.grantedHandles.headFrames) {
      findings.push(timelineFinding("/edgeTransition/headFrames", "TIMELINE_HANDLE_NOT_GRANTED",
        `edge head transition uses ${usedHead} frames but the parent granted ${slot.grantedHandles.headFrames}; handles the parent did not grant cannot be consumed`));
    }
    if (usedTail > slot.grantedHandles.tailFrames) {
      findings.push(timelineFinding("/edgeTransition/tailFrames", "TIMELINE_HANDLE_NOT_GRANTED",
        `edge tail transition uses ${usedTail} frames but the parent granted ${slot.grantedHandles.tailFrames}; handles the parent did not grant cannot be consumed`));
    }
  }

  // ---- Transitions: adjacency, one per boundary, single owner -------
  const byBoundary = new Map<number, (typeof transitions)[number]>();
  for (let i = 0; i < transitions.length; i += 1) {
    const t = transitions[i];
    const path = `/transitions/${i}`;
    const fromIdx = sceneIndex.get(t.fromSceneId);
    const toIdx = sceneIndex.get(t.toSceneId);
    if (fromIdx === undefined || toIdx === undefined) {
      findings.push(timelineFinding(path, "TIMELINE_TRANSITION_NOT_ADJACENT",
        `transition "${t.id}" references unknown scene(s) "${t.fromSceneId}" -> "${t.toSceneId}"`));
      continue;
    }
    if (toIdx !== fromIdx + 1) {
      findings.push(timelineFinding(path, "TIMELINE_TRANSITION_NOT_ADJACENT",
        `transition "${t.id}" joins "${t.fromSceneId}" (scene ${fromIdx}) to "${t.toSceneId}" (scene ${toIdx}); transitions join adjacent scenes only`));
      continue;
    }
    if (byBoundary.has(fromIdx)) {
      findings.push(timelineFinding(path, "TIMELINE_TRANSITION_DUPLICATE",
        `boundary after scene "${t.fromSceneId}" already has a transition; each boundary has exactly one transition and each overlap exactly one subtraction`));
      continue;
    }
    if (t.ownerSceneId !== t.fromSceneId && t.ownerSceneId !== t.toSceneId) {
      findings.push(timelineFinding(`${path}/ownerSceneId`, "TIMELINE_HANDLE_OWNER_INVALID",
        `overlap owner "${t.ownerSceneId}" is neither side of the boundary; an overlap is owned by exactly one of its two scenes`));
      continue;
    }
    byBoundary.set(fromIdx, t);
  }

  if (findings.length > 0) return { ok: false, findings };

  // ---- Placement ------------------------------------------------------
  const placed: { start: number; end: number }[] = [];
  let cursor = 0;
  for (let i = 0; i < scenes.length; i += 1) {
    const start = i === 0 ? 0 : cursor - (byBoundary.get(i - 1)?.frames ?? 0);
    const end = start + scenes[i].durationFrames;
    placed.push({ start, end });
    cursor = end;
  }
  const contentTotal = cursor;

  // Overlap bounds: an overlap may not consume a scene entirely, and a
  // scene's incoming plus outgoing overlaps may not meet or cross.
  for (let i = 0; i < scenes.length; i += 1) {
    const inFrames = byBoundary.get(i - 1)?.frames ?? 0;
    const outFrames = byBoundary.get(i)?.frames ?? 0;
    if (inFrames + outFrames >= scenes[i].durationFrames) {
      findings.push(timelineFinding(`/scenes/${i}`, "TIMELINE_OVERLAP_EXCEEDS_SCENE",
        `scene "${scenes[i].id}" is ${scenes[i].durationFrames} frames but its overlaps total ${inFrames + outFrames} (in ${inFrames}, out ${outFrames}); a scene must keep a positive solo region`));
    }
  }

  // ---- Totals ---------------------------------------------------------
  let totalFrames: number;
  if (typed.mode === "slot") {
    totalFrames = slotLength;
    if (contentTotal > slotLength) {
      findings.push(timelineFinding("/scenes", "TIMELINE_SLOT_OVERFLOW",
        `insert content compiles to ${contentTotal} frames but the parent slot is exactly ${slotLength}; the slot is never resized and the parent narration is never shortened to fit`));
    } else if (contentTotal < slotLength) {
      findings.push(timelineFinding("/scenes", "TIMELINE_SLOT_UNDERFILL",
        `insert content compiles to ${contentTotal} frames but the parent slot is exactly ${slotLength}; declare the full duration (lengthen a scene or add a hold) instead of leaving unplanned frames`));
    }
  } else {
    totalFrames = contentTotal;
  }

  // ---- Source ranges ----------------------------------------------------
  for (let i = 0; i < scenes.length; i += 1) {
    const s = scenes[i];
    if (s.sourceDurationFrames !== undefined && s.sourceDurationFrames < s.durationFrames) {
      findings.push(timelineFinding(`/scenes/${i}/sourceDurationFrames`, "TIMELINE_SOURCE_RANGE_SHORT",
        `scene "${s.id}" consumes ${s.durationFrames} source frames but only ${s.sourceDurationFrames} are declared available; the compiler never stretches source media silently`));
    }
  }

  // ---- Narration: authoritative, never truncated ------------------------
  const narration = typed.narration ?? [];
  const sortedNarration = [...narration].sort((a, b) => a.startFrame - b.startFrame || (a.id < b.id ? -1 : 1));
  for (let i = 0; i < narration.length; i += 1) {
    const seg = narration[i];
    if (seg.endFrameExclusive > totalFrames) {
      findings.push(timelineFinding(`/narration/${i}`, "TIMELINE_NARRATION_EXCEEDS_PICTURE",
        `narration segment "${seg.id}" ends at frame ${seg.endFrameExclusive} but the compiled picture is ${totalFrames} frames; narration is authoritative and is never truncated or shortened to fit the picture`));
    }
  }
  for (let i = 1; i < sortedNarration.length; i += 1) {
    const prev = sortedNarration[i - 1];
    const cur = sortedNarration[i];
    if (cur.startFrame < prev.endFrameExclusive) {
      findings.push(timelineFinding("/narration", "TIMELINE_NARRATION_OVERLAP",
        `narration segments "${prev.id}" and "${cur.id}" overlap; one narration stream cannot speak twice at once`));
    }
  }

  // ---- Captions and SFX bounds ------------------------------------------
  const captions = typed.captions ?? [];
  captions.forEach((c, i) => {
    if (c.endFrameExclusive > totalFrames) {
      findings.push(timelineFinding(`/captions/${i}`, "TIMELINE_CAPTION_OUT_OF_BOUNDS",
        `caption "${c.id}" ends at frame ${c.endFrameExclusive}, beyond the compiled total ${totalFrames}`));
    }
  });
  const sfx = typed.sfxCues ?? [];
  sfx.forEach((s, i) => {
    if (s.frame >= totalFrames) {
      findings.push(timelineFinding(`/sfxCues/${i}`, "TIMELINE_SFX_OUT_OF_BOUNDS",
        `sfx cue "${s.id}" sits at frame ${s.frame}, beyond the compiled total ${totalFrames}`));
    }
  });

  // ---- Cues and anchors ---------------------------------------------------
  const compiledCues: CompiledCue[] = [];
  const cues = typed.cues ?? [];
  const narrationById = new Map(narration.map((n) => [n.id, n] as const));
  cues.forEach((cue, i) => {
    const path = `/cues/${i}`;
    const sceneIdx = sceneIndex.get(cue.sceneId);
    if (sceneIdx === undefined) {
      findings.push(timelineFinding(`${path}/sceneId`, "TIMELINE_ANCHOR_UNRESOLVED",
        `cue "${cue.id}" names unknown scene "${cue.sceneId}"`));
      return;
    }
    const range = placed[sceneIdx];
    const a = cue.anchor;
    if (a.kind === "semantic_state") {
      if (a.sceneLocalFrame >= scenes[sceneIdx].durationFrames) {
        findings.push(timelineFinding(`${path}/anchor`, "TIMELINE_CUE_OUT_OF_BOUNDS",
          `cue "${cue.id}" anchors at scene-local frame ${a.sceneLocalFrame} but scene "${cue.sceneId}" is ${scenes[sceneIdx].durationFrames} frames`));
        return;
      }
      const frame = range.start + a.sceneLocalFrame;
      compiledCues.push({
        id: cue.id, sceneId: cue.sceneId, type: cue.type,
        frame, sample: frameToSample(frame, fps),
        anchorKind: a.kind, anchorRef: a.state,
      });
    } else if (a.kind === "spoken_word") {
      const seg = narrationById.get(a.segmentId);
      const word = seg?.words?.find((w) => w.index === a.wordIndex);
      if (!seg || !word) {
        findings.push(timelineFinding(`${path}/anchor`, "TIMELINE_ANCHOR_UNRESOLVED",
          `cue "${cue.id}" anchors to word ${a.wordIndex} of narration segment "${a.segmentId}", which does not exist in the measured narration`));
        return;
      }
      const frame = sampleToFrameFloor(word.startSample, fps);
      if (frame < range.start || frame >= range.end) {
        findings.push(timelineFinding(`${path}/anchor`, "TIMELINE_CUE_OUTSIDE_SCENE",
          `cue "${cue.id}" resolves to frame ${frame} (word at sample ${word.startSample}), outside scene "${cue.sceneId}" placed at [${range.start}, ${range.end})`));
        return;
      }
      compiledCues.push({
        id: cue.id, sceneId: cue.sceneId, type: cue.type,
        frame, sample: word.startSample,
        anchorKind: a.kind, anchorRef: `${a.segmentId}#${a.wordIndex}`,
      });
    } else {
      const grid = typed.musicGrid ?? null;
      if (!grid) {
        findings.push(timelineFinding(`${path}/anchor`, "TIMELINE_ANCHOR_UNRESOLVED",
          `cue "${cue.id}" anchors to music beat ${a.beatIndex} but the plan declares no music grid`));
        return;
      }
      const posSeconds = grid.firstBeatFrame / fps + (a.beatIndex * 60) / grid.bpm;
      const frame = secondsToFrame(posSeconds, fps);
      if (frame < range.start || frame >= range.end) {
        findings.push(timelineFinding(`${path}/anchor`, "TIMELINE_CUE_OUTSIDE_SCENE",
          `cue "${cue.id}" resolves to frame ${frame} (beat ${a.beatIndex} at ${grid.bpm} bpm), outside scene "${cue.sceneId}" placed at [${range.start}, ${range.end})`));
        return;
      }
      compiledCues.push({
        id: cue.id, sceneId: cue.sceneId, type: cue.type,
        frame, sample: secondsToSample(posSeconds),
        anchorKind: a.kind, anchorRef: `beat#${a.beatIndex}`,
      });
    }
  });

  // ---- Property writes ------------------------------------------------------
  const declaredOverlaps: DeclaredPropertyOverlap[] = [];
  const tracks = typed.propertyTracks ?? [];
  tracks.forEach((track, ti) => {
    const path = `/propertyTracks/${ti}`;
    const sceneIdx = sceneIndex.get(track.sceneId);
    if (sceneIdx === undefined) {
      findings.push(timelineFinding(`${path}/sceneId`, "TIMELINE_PROPERTY_SCENE_UNKNOWN",
        `property track names unknown scene "${track.sceneId}"`));
      return;
    }
    const duration = scenes[sceneIdx].durationFrames;
    track.writes.forEach((w, wi) => {
      if (w.endFrameExclusive > duration) {
        findings.push(timelineFinding(`${path}/writes/${wi}`, "TIMELINE_PROPERTY_WRITE_OUT_OF_BOUNDS",
          `write on "${track.property}" in scene "${track.sceneId}" ends at scene-local frame ${w.endFrameExclusive}, beyond the scene's ${duration} frames`));
      }
    });
    const order = track.writes.map((w, idx) => ({ w, idx })).sort((x, y) => x.w.startFrame - y.w.startFrame || x.idx - y.idx);
    let maxEnd = -1;
    let maxIdx = -1;
    for (const { w, idx } of order) {
      if (w.startFrame < maxEnd) {
        if (w.intentionalOverlap === true) {
          declaredOverlaps.push({
            sceneId: track.sceneId,
            property: track.property,
            earlierWriteIndex: maxIdx,
            laterWriteIndex: idx,
            overlapRange: { startFrame: w.startFrame, endFrameExclusive: Math.min(maxEnd, w.endFrameExclusive) },
          });
        } else {
          findings.push(timelineFinding(`${path}/writes/${idx}`, "TIMELINE_PROPERTY_WRITE_OVERLAP",
            `writes ${maxIdx} and ${idx} on "${track.property}" in scene "${track.sceneId}" overlap at scene-local frames [${w.startFrame}, ${Math.min(maxEnd, w.endFrameExclusive)}); overlapping writes to one animated property must be declared intentional on the later write`));
        }
      }
      if (w.endFrameExclusive > maxEnd) {
        maxEnd = w.endFrameExclusive;
        maxIdx = idx;
      }
    }
  });

  if (findings.length > 0) return { ok: false, findings };

  // ---- Assemble outputs ------------------------------------------------------
  const sceneDetails: CompiledSceneDetail[] = scenes.map((s, i) => {
    const srcStart = s.sourceStartFrame ?? 0;
    return {
      id: s.id,
      placedRange: { startFrame: placed[i].start, endFrameExclusive: placed[i].end },
      durationFrames: s.durationFrames,
      sourceRange: { startFrame: srcStart, endFrameExclusive: srcStart + s.durationFrames },
      sourceRangeSamples: {
        startSample: frameToSample(srcStart, fps),
        endSampleExclusive: frameToSample(srcStart + s.durationFrames, fps),
      },
      transitionInFrames: i === 0 ? usedHead : (byBoundary.get(i - 1)?.frames ?? 0),
      transitionOutFrames: i === scenes.length - 1 ? usedTail : (byBoundary.get(i)?.frames ?? 0),
    };
  });

  const handles: CompiledHandle[] = [];
  for (let b = 0; b < scenes.length - 1; b += 1) {
    const t = byBoundary.get(b);
    if (!t) continue;
    const start = placed[b + 1].start;
    const end = placed[b].end;
    handles.push({
      id: t.id,
      fromSceneId: t.fromSceneId,
      toSceneId: t.toSceneId,
      ownerSceneId: t.ownerSceneId,
      frames: t.frames,
      placedRange: { startFrame: start, endFrameExclusive: end },
      midpointFrameTimesTwo: start + end,
      midpointSample: rangeMidpointSample(start, end, fps),
    });
  }

  const sortedCues = [...compiledCues].sort((a, b) => a.frame - b.frame || (a.id < b.id ? -1 : 1));
  const toRangeTrack = (r: { id: string; startFrame: number; endFrameExclusive: number }): CompiledRangeTrack => ({
    id: r.id,
    startFrame: r.startFrame,
    endFrameExclusive: r.endFrameExclusive,
    startSample: frameToSample(r.startFrame, fps),
    endSampleExclusive: frameToSample(r.endFrameExclusive, fps),
  });

  const timelineDoc = {
    schema_version: "2.0",
    job_id: typed.jobId,
    fps,
    total_frames: totalFrames,
    scenes: sceneDetails.map((d) => ({
      id: d.id,
      start_frame: d.placedRange.startFrame,
      end_frame_exclusive: d.placedRange.endFrameExclusive,
      source_start_frame: d.sourceRange.startFrame,
      transition_in_frames: d.transitionInFrames,
      transition_out_frames: d.transitionOutFrames,
    })),
    events: sortedCues.map((c) => ({ id: c.id, scene_id: c.sceneId, frame: c.frame, type: c.type })),
    parent_slot: slot ? { start_frame: slot.range.startFrame, end_frame_exclusive: slot.range.endFrameExclusive } : null,
    audio_owner: typed.audioOwner,
  };

  // The compiler's own output must satisfy the canonical schema. A
  // failure here is a compiler bug, surfaced as a finding, never shipped.
  const schemaErrors = validateAgainstDef("timeline", timelineDoc);
  if (schemaErrors.length > 0) {
    return {
      ok: false,
      findings: schemaErrors.map((e) => ({
        category: "MG_SCHEMA_INVALID" as const,
        path: `/timeline${e.instancePath}`,
        message: `compiled timeline violates the canonical schema: ${e.message}`,
      })),
    };
  }

  const sidecar: TimelineSidecar = {
    schema_version: "1.0",
    item: "MG-021",
    job_id: typed.jobId,
    fps,
    sample_rate: TIMELINE_SAMPLE_RATE,
    rounding_rule: TIMELINE_ROUNDING_RULE,
    mode: typed.mode,
    total_frames: totalFrames,
    total_samples: frameToSample(totalFrames, fps),
    scenes: sceneDetails,
    handles,
    cues: sortedCues,
    narration: sortedNarration.map(toRangeTrack),
    captions: [...captions]
      .sort((a, b) => a.startFrame - b.startFrame || (a.id < b.id ? -1 : 1))
      .map(toRangeTrack),
    sfx: [...sfx]
      .sort((a, b) => a.frame - b.frame || (a.id < b.id ? -1 : 1))
      .map((s): CompiledSfx => ({ id: s.id, frame: s.frame, sample: frameToSample(s.frame, fps) })),
    property_overlaps_declared: declaredOverlaps,
    slot: slot
      ? {
          parentRange: { startFrame: slot.range.startFrame, endFrameExclusive: slot.range.endFrameExclusive },
          grantedHandles: { headFrames: slot.grantedHandles.headFrames, tailFrames: slot.grantedHandles.tailFrames },
          usedHandles: { headFrames: usedHead, tailFrames: usedTail },
        }
      : null,
  };

  return { ok: true, compiled: { timeline: timelineDoc as unknown as Timeline, sidecar } };
}
