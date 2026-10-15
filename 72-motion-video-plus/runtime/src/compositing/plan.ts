// The composition plan document and its structural validation
// (Directive MG-012; Sections 16.6, 16.9).
//
// A composition plan is the serialized record a component or planner
// hands to the compositing layer: one canvas, one primary image with
// its manifest facts (usage class, source size, focal point,
// protected regions in the MG-011 sidecar's normalized shape), the
// crop targets it must satisfy, the subject and its motion, the
// essential text boxes, and optionally layers/depth and a close-up.
//
// validateCompositionPlan checks the document's structure and its
// internal claims (ids, ranges, fractions, containment in the
// canvas, the depth rules via validateLayers). Every finding is a
// contract error: MG_SCHEMA_INVALID, exit class 2. Geometry outcomes
// (can this crop exist, does text hit a protected region, does the
// close-up upscale too far) are NOT decided here; they are the QC
// checker's acceptance findings in qc.ts.

import {
  AssetUsage,
  Box,
  COMPOSITING_CONTRACT_CATEGORY,
  CompositingError,
  CompositingFinding,
  NormalizedBox,
  NormalizedPoint,
  Size,
  boxContains,
  isBox,
  isFiniteNumber,
  isNonNegativeInt,
  isPositiveInt,
  isRecord,
  isSize,
} from "./types";
import {
  DepthSpec,
  LAYER_ROLES,
  LayerSpec,
  validateLayers,
} from "./layers";
import {
  REVEAL_DIRECTIONS,
  RevealDirection,
  SUBJECT_MOTION_KINDS,
  SubjectMotion,
} from "./reveal";

export const PLAN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;

export const ASSET_USAGES: readonly AssetUsage[] = [
  "embed_original",
  "approved_derivative",
  "reference_only",
];

export interface PlanProtectedRegion {
  id: string;
  label?: string;
  /** Normalized box over the source (the sidecar shape). */
  box: NormalizedBox;
}

export interface PlanImage {
  assetId: string;
  usage: AssetUsage;
  source: Size;
  focalPoint: NormalizedPoint | null;
  protectedRegions: PlanProtectedRegion[];
}

export interface CropTarget {
  name: string;
  aspect: { w: number; h: number };
  /** The box the solved crop is placed into. The first target's box
   * must equal the plan canvas (structural rule): it is the primary
   * mapping the M08 check uses. */
  box: Size;
}

export interface PlanSubjectMotion {
  subjectId: string;
  kind: SubjectMotion["kind"];
  range: { startFrame: number; endFrameExclusive: number };
  direction: RevealDirection;
  fromFraction: number;
  toFraction: number;
}

export interface PlanTextBox {
  id: string;
  /** "title", "essential", "caption", ... (the M08 rule protects
   * against every declared text box; kind is for the record). */
  kind: string;
  box: Box;
}

export interface PlanCloseUp {
  id: string;
  /** Normalized detail point over the source. */
  detail: NormalizedPoint;
  maxZoom: number;
  output: Box;
  maxUpscale?: number;
}

/** A structurally valid composition plan, in internal form. */
export interface CompositionPlan {
  id: string;
  canvas: Size;
  durationFrames: number;
  declaredExit: boolean;
  image?: PlanImage;
  cropTargets: CropTarget[];
  subject?: { id: string; box: Box };
  subjectMotion?: PlanSubjectMotion;
  textBoxes: PlanTextBox[];
  allowTextOverlap: string[];
  layers: LayerSpec[];
  depth?: DepthSpec;
  closeUp?: PlanCloseUp;
}

const TOP_LEVEL_KEYS = new Set([
  "schema_version",
  "id",
  "canvas",
  "duration_frames",
  "declared_exit",
  "image",
  "crop_targets",
  "subject",
  "subject_motion",
  "text_boxes",
  "allow_text_overlap",
  "layers",
  "depth",
  "close_up",
]);

function finding(path: string, message: string, rule = "plan-shape"): CompositingFinding {
  return { category: COMPOSITING_CONTRACT_CATEGORY, rule, path, message };
}

function isNormalizedPoint(value: unknown): value is NormalizedPoint {
  return (
    isRecord(value) &&
    isFiniteNumber(value.x) &&
    isFiniteNumber(value.y) &&
    value.x >= 0 &&
    value.x <= 1 &&
    value.y >= 0 &&
    value.y <= 1
  );
}

function isNormalizedBox(value: unknown): value is NormalizedBox {
  return (
    isRecord(value) &&
    isFiniteNumber(value.x) &&
    isFiniteNumber(value.y) &&
    isFiniteNumber(value.width) &&
    isFiniteNumber(value.height) &&
    value.x >= 0 &&
    value.y >= 0 &&
    value.width > 0 &&
    value.height > 0 &&
    value.x + value.width <= 1 + 1e-9 &&
    value.y + value.height <= 1 + 1e-9
  );
}

function isFraction(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0 && value <= 1;
}

/**
 * Structural validation of a composition plan document. Returns every
 * contract finding; an empty list means the document is a plan the QC
 * checker can judge. Unknown top-level keys are rejected (the closed
 * document posture of the V2 contracts).
 */
export function validateCompositionPlan(doc: unknown): CompositingFinding[] {
  const findings: CompositingFinding[] = [];
  if (!isRecord(doc)) {
    return [finding("", "composition plan must be a JSON object")];
  }
  for (const key of Object.keys(doc)) {
    if (!TOP_LEVEL_KEYS.has(key)) {
      findings.push(finding(key, `unknown top-level field "${key}" in composition plan`));
    }
  }
  if (doc.schema_version !== "2.0") {
    findings.push(finding("schema_version", 'schema_version must be "2.0"'));
  }
  if (typeof doc.id !== "string" || !PLAN_ID_PATTERN.test(doc.id)) {
    findings.push(finding("id", "plan id must match the job id pattern"));
  }
  const canvasOk = isSize(doc.canvas);
  if (!canvasOk) {
    findings.push(finding("canvas", "canvas must be a positive integer size"));
  }
  const canvas = canvasOk ? (doc.canvas as Size) : { width: 0, height: 0 };
  const canvasBox: Box = { x: 0, y: 0, width: canvas.width, height: canvas.height };
  if (!isPositiveInt(doc.duration_frames)) {
    findings.push(finding("duration_frames", "duration_frames must be a positive integer"));
  }
  const duration = isPositiveInt(doc.duration_frames) ? doc.duration_frames : 0;
  if (doc.declared_exit !== undefined && typeof doc.declared_exit !== "boolean") {
    findings.push(finding("declared_exit", "declared_exit must be a boolean"));
  }

  // ---- image -------------------------------------------------------
  if (doc.image !== undefined) {
    const image = doc.image;
    if (!isRecord(image)) {
      findings.push(finding("image", "image must be an object"));
    } else {
      if (typeof image.asset_id !== "string" || !PLAN_ID_PATTERN.test(image.asset_id)) {
        findings.push(finding("image/asset_id", "image asset_id must match the id pattern"));
      }
      if (!ASSET_USAGES.includes(image.usage as AssetUsage)) {
        findings.push(
          finding("image/usage", `image usage must be one of ${ASSET_USAGES.join(", ")}`)
        );
      }
      if (!isSize(image.source)) {
        findings.push(finding("image/source", "image source must be a positive integer size"));
      }
      if (image.focal_point !== null && !isNormalizedPoint(image.focal_point)) {
        findings.push(
          finding("image/focal_point", "focal_point must be null or a normalized point in [0, 1]")
        );
      }
      if (!Array.isArray(image.protected_regions)) {
        findings.push(finding("image/protected_regions", "protected_regions must be an array"));
      } else {
        const seen = new Set<string>();
        image.protected_regions.forEach((region, i) => {
          const path = `image/protected_regions[${i}]`;
          if (!isRecord(region) || typeof region.id !== "string" || !PLAN_ID_PATTERN.test(region.id)) {
            findings.push(finding(path, "protected region needs a valid id"));
            return;
          }
          if (seen.has(region.id)) {
            findings.push(finding(path, `protected region id "${region.id}" appears twice`));
          }
          seen.add(region.id);
          if (region.label !== undefined && typeof region.label !== "string") {
            findings.push(finding(`${path}/label`, "protected region label must be a string"));
          }
          if (!isNormalizedBox(region.box)) {
            findings.push(
              finding(
                `${path}/box`,
                "protected region box must be a normalized box inside [0, 1] with positive extent"
              )
            );
          }
        });
      }
    }
  }

  // ---- crop targets --------------------------------------------------
  if (doc.crop_targets !== undefined) {
    if (!Array.isArray(doc.crop_targets) || doc.crop_targets.length === 0) {
      findings.push(finding("crop_targets", "crop_targets must be a non-empty array when present"));
    } else {
      const seen = new Set<string>();
      doc.crop_targets.forEach((target, i) => {
        const path = `crop_targets[${i}]`;
        if (!isRecord(target) || typeof target.name !== "string" || target.name.length === 0) {
          findings.push(finding(path, "crop target needs a name"));
          return;
        }
        if (seen.has(target.name)) {
          findings.push(finding(path, `crop target name "${target.name}" appears twice`));
        }
        seen.add(target.name);
        if (
          !isRecord(target.aspect) ||
          !isPositiveInt(target.aspect.w) ||
          !isPositiveInt(target.aspect.h)
        ) {
          findings.push(finding(`${path}/aspect`, "crop target aspect must be positive integers"));
        }
        if (!isSize(target.box)) {
          findings.push(finding(`${path}/box`, "crop target box must be a positive integer size"));
        }
      });
      const first = doc.crop_targets[0];
      if (
        isRecord(first) &&
        isSize(first.box) &&
        canvasOk &&
        (first.box.width !== canvas.width || first.box.height !== canvas.height)
      ) {
        findings.push(
          finding(
            "crop_targets[0]/box",
            "the first crop target is the primary mapping and its box must equal the canvas",
            "crop-target-primary"
          )
        );
      }
    }
  }

  // ---- subject and motion ---------------------------------------------
  let subjectId: string | null = null;
  if (doc.subject !== undefined) {
    const subject = doc.subject;
    if (!isRecord(subject) || typeof subject.id !== "string" || subject.id.length === 0) {
      findings.push(finding("subject", "subject needs an id"));
    } else {
      subjectId = subject.id;
      if (!isBox(subject.box)) {
        findings.push(finding("subject/box", "subject box must be an integer pixel box"));
      } else if (canvasOk && !boxContains(canvasBox, subject.box)) {
        findings.push(
          finding("subject/box", "subject box extends outside the canvas", "subject-box-in-canvas")
        );
      }
    }
  }
  if (doc.subject_motion !== undefined) {
    const motion = doc.subject_motion;
    if (!isRecord(motion)) {
      findings.push(finding("subject_motion", "subject_motion must be an object"));
    } else {
      if (subjectId !== null && motion.subject_id !== subjectId) {
        findings.push(
          finding("subject_motion/subject_id", "subject_motion must name the plan's subject")
        );
      }
      if (!SUBJECT_MOTION_KINDS.includes(motion.kind as SubjectMotion["kind"])) {
        findings.push(
          finding("subject_motion/kind", `kind must be one of ${SUBJECT_MOTION_KINDS.join(", ")}`)
        );
      }
      if (!REVEAL_DIRECTIONS.includes(motion.direction as RevealDirection)) {
        findings.push(
          finding(
            "subject_motion/direction",
            `direction must be one of ${REVEAL_DIRECTIONS.join(", ")}`
          )
        );
      }
      const range = motion.range;
      if (
        !isRecord(range) ||
        !isNonNegativeInt(range.start_frame) ||
        !isPositiveInt(range.end_frame_exclusive) ||
        (isNonNegativeInt(range.start_frame) &&
          isPositiveInt(range.end_frame_exclusive) &&
          (range.end_frame_exclusive as number) <= (range.start_frame as number))
      ) {
        findings.push(
          finding("subject_motion/range", "range must be integer frames with start < end")
        );
      } else if (duration > 0 && (range.end_frame_exclusive as number) > duration) {
        findings.push(
          finding(
            "subject_motion/range",
            "motion range ends after the plan duration",
            "motion-range-in-duration"
          )
        );
      }
      if (!isFraction(motion.from_fraction) || !isFraction(motion.to_fraction)) {
        findings.push(
          finding("subject_motion", "from_fraction and to_fraction must lie in [0, 1]")
        );
      }
    }
  }

  // ---- text boxes -------------------------------------------------------
  if (doc.text_boxes !== undefined) {
    if (!Array.isArray(doc.text_boxes)) {
      findings.push(finding("text_boxes", "text_boxes must be an array"));
    } else {
      const seen = new Set<string>();
      doc.text_boxes.forEach((textBox, i) => {
        const path = `text_boxes[${i}]`;
        if (!isRecord(textBox) || typeof textBox.id !== "string" || textBox.id.length === 0) {
          findings.push(finding(path, "text box needs an id"));
          return;
        }
        if (seen.has(textBox.id)) {
          findings.push(finding(path, `text box id "${textBox.id}" appears twice`));
        }
        seen.add(textBox.id);
        if (!isBox(textBox.box)) {
          findings.push(finding(`${path}/box`, "text box must be an integer pixel box"));
        } else if (canvasOk && !boxContains(canvasBox, textBox.box)) {
          findings.push(
            finding(`${path}/box`, "text box extends outside the canvas", "text-box-in-canvas")
          );
        }
      });
    }
  }
  if (doc.allow_text_overlap !== undefined) {
    if (
      !Array.isArray(doc.allow_text_overlap) ||
      !doc.allow_text_overlap.every((v) => typeof v === "string")
    ) {
      findings.push(
        finding("allow_text_overlap", "allow_text_overlap must be an array of region ids")
      );
    }
  }

  // ---- layers and depth ---------------------------------------------------
  let layers: LayerSpec[] = [];
  if (doc.layers !== undefined) {
    if (!Array.isArray(doc.layers)) {
      findings.push(finding("layers", "layers must be an array"));
    } else {
      let layersOk = true;
      doc.layers.forEach((layer, i) => {
        if (
          !isRecord(layer) ||
          typeof layer.id !== "string" ||
          layer.id.length === 0 ||
          !LAYER_ROLES.includes(layer.role as LayerSpec["role"])
        ) {
          findings.push(
            finding(`layers[${i}]`, `layer needs an id and a role in ${LAYER_ROLES.join(", ")}`)
          );
          layersOk = false;
        }
      });
      if (layersOk) {
        layers = (doc.layers as Array<Record<string, unknown>>).map((layer) => ({
          id: layer.id as string,
          role: layer.role as LayerSpec["role"],
          assetId: typeof layer.asset_id === "string" ? layer.asset_id : undefined,
        }));
      }
    }
  }
  let depth: DepthSpec | undefined;
  if (doc.depth !== undefined) {
    if (!isRecord(doc.depth)) {
      findings.push(finding("depth", "depth must be an object"));
    } else {
      depth = {
        kind: doc.depth.kind as DepthSpec["kind"],
        spatialScene: isRecord(doc.depth.spatial_scene)
          ? {
              present: doc.depth.spatial_scene.present === true,
              source:
                typeof doc.depth.spatial_scene.source === "string"
                  ? doc.depth.spatial_scene.source
                  : undefined,
            }
          : undefined,
      };
    }
  }
  if (findings.length === 0 || layers.length > 0 || depth !== undefined) {
    findings.push(...validateLayers(layers.length > 0 ? layers : undefined, depth, "layers"));
  }

  // ---- close-up -------------------------------------------------------------
  if (doc.close_up !== undefined) {
    const closeUp = doc.close_up;
    if (!isRecord(closeUp)) {
      findings.push(finding("close_up", "close_up must be an object"));
    } else {
      if (typeof closeUp.id !== "string" || closeUp.id.length === 0) {
        findings.push(finding("close_up/id", "close_up needs an id"));
      }
      if (doc.image === undefined) {
        findings.push(
          finding("close_up", "a close-up is a view of the plan's image: the plan has none", "close-up-needs-image")
        );
      }
      if (!isNormalizedPoint(closeUp.detail)) {
        findings.push(finding("close_up/detail", "detail must be a normalized point in [0, 1]"));
      }
      if (!isFiniteNumber(closeUp.max_zoom) || (closeUp.max_zoom as number) < 1) {
        findings.push(finding("close_up/max_zoom", "max_zoom must be a finite number >= 1"));
      }
      if (!isBox(closeUp.output)) {
        findings.push(finding("close_up/output", "output must be an integer pixel box"));
      } else if (canvasOk && !boxContains(canvasBox, closeUp.output)) {
        findings.push(
          finding("close_up/output", "close-up output extends outside the canvas", "close-up-output-in-canvas")
        );
      }
      if (
        closeUp.max_upscale !== undefined &&
        (!isFiniteNumber(closeUp.max_upscale) || (closeUp.max_upscale as number) < 1)
      ) {
        findings.push(finding("close_up/max_upscale", "max_upscale must be a finite number >= 1"));
      }
    }
  }

  return findings;
}

/**
 * Parse a plan document into its internal form. Throws
 * CompositingError with every structural finding when the document is
 * not a valid plan.
 */
export function parseCompositionPlan(doc: unknown): CompositionPlan {
  const findings = validateCompositionPlan(doc);
  if (findings.length > 0) throw new CompositingError(findings);
  const d = doc as Record<string, unknown>;
  const image = d.image as Record<string, unknown> | undefined;
  const motion = d.subject_motion as Record<string, unknown> | undefined;
  const range = motion?.range as Record<string, unknown> | undefined;
  const depthRaw = d.depth as Record<string, unknown> | undefined;
  const spatialRaw = depthRaw?.spatial_scene as Record<string, unknown> | undefined;
  const closeUpRaw = d.close_up as Record<string, unknown> | undefined;
  const targets = (d.crop_targets as Array<Record<string, unknown>> | undefined) ?? [];
  return {
    id: d.id as string,
    canvas: d.canvas as Size,
    durationFrames: d.duration_frames as number,
    declaredExit: d.declared_exit === true,
    image: image
      ? {
          assetId: image.asset_id as string,
          usage: image.usage as AssetUsage,
          source: image.source as Size,
          focalPoint: (image.focal_point as NormalizedPoint | null) ?? null,
          protectedRegions: (
            image.protected_regions as Array<Record<string, unknown>>
          ).map((region) => ({
            id: region.id as string,
            label: typeof region.label === "string" ? region.label : undefined,
            box: region.box as NormalizedBox,
          })),
        }
      : undefined,
    cropTargets:
      targets.length > 0
        ? targets.map((target) => ({
            name: target.name as string,
            aspect: target.aspect as { w: number; h: number },
            box: target.box as Size,
          }))
        : [
            {
              name: "canvas",
              aspect: { w: (d.canvas as Size).width, h: (d.canvas as Size).height },
              box: d.canvas as Size,
            },
          ],
    subject: d.subject
      ? { id: (d.subject as Record<string, unknown>).id as string, box: (d.subject as Record<string, unknown>).box as Box }
      : undefined,
    subjectMotion: motion
      ? {
          subjectId: motion.subject_id as string,
          kind: motion.kind as SubjectMotion["kind"],
          range: {
            startFrame: range?.start_frame as number,
            endFrameExclusive: range?.end_frame_exclusive as number,
          },
          direction: motion.direction as RevealDirection,
          fromFraction: motion.from_fraction as number,
          toFraction: motion.to_fraction as number,
        }
      : undefined,
    textBoxes: ((d.text_boxes as Array<Record<string, unknown>> | undefined) ?? []).map(
      (textBox) => ({
        id: textBox.id as string,
        kind: typeof textBox.kind === "string" ? textBox.kind : "essential",
        box: textBox.box as Box,
      })
    ),
    allowTextOverlap: (d.allow_text_overlap as string[] | undefined) ?? [],
    layers: ((d.layers as Array<Record<string, unknown>> | undefined) ?? []).map((layer) => ({
      id: layer.id as string,
      role: layer.role as LayerSpec["role"],
      assetId: typeof layer.asset_id === "string" ? layer.asset_id : undefined,
    })),
    depth: depthRaw
      ? {
          kind: depthRaw.kind as DepthSpec["kind"],
          spatialScene: spatialRaw
            ? {
                present: spatialRaw.present === true,
                source: typeof spatialRaw.source === "string" ? spatialRaw.source : undefined,
              }
            : undefined,
        }
      : undefined,
    closeUp: closeUpRaw
      ? {
          id: closeUpRaw.id as string,
          detail: closeUpRaw.detail as NormalizedPoint,
          maxZoom: closeUpRaw.max_zoom as number,
          output: closeUpRaw.output as Box,
          maxUpscale:
            typeof closeUpRaw.max_upscale === "number" ? closeUpRaw.max_upscale : undefined,
        }
      : undefined,
  };
}

/** Convert a plan's subject motion document into the parametric
 * SubjectMotion the reveal geometry consumes. */
export function toSubjectMotion(plan: CompositionPlan): SubjectMotion | null {
  if (!plan.subjectMotion) return null;
  const motion = plan.subjectMotion;
  return {
    kind: motion.kind,
    range: motion.range,
    direction: motion.direction,
    fromFraction: motion.fromFraction,
    toFraction: motion.toFraction,
  };
}
