// Asset QC over composition plans (Directive MG-012 acceptance;
// Sections 16.9, 17.1 M08 and M10).
//
// checkCompositionPlan judges a structurally valid plan against the
// four MG-012 acceptance lines, mechanically:
// 1. Subject visibility: the subject's visible fraction is sampled
//    at every frame of the plan duration under its declared motion;
//    it must never vanish mid-motion without a declared exit, and
//    the motion must be monotonic and reach its declared final
//    state (M10: assertions inspect the named subject).
// 2. Focal constraints in both ratios: every crop target is solved
//    with the crop solver; an impossibility becomes a QC finding
//    naming the protected region (the plan document is well-formed,
//    so the failure is acceptance, not shape: MG_QC_FAILED, exit
//    class 6). The focal point and every protected region are
//    additionally asserted inside each solved crop as defense in
//    depth over the solver's own construction proofs.
// 3. Text protection (M08): every title/essential-text box is
//    intersected with every protected region mapped onto the canvas
//    through the primary crop and placement, boxes rounded outward
//    so a sub-pixel overlap can never round into a pass. Zero
//    intersection is the rule; a region id listed in
//    allow_text_overlap is the M08 "approved design deliberately
//    permits it" exception, recorded in the plan itself.
// 4. Source detail accuracy: the close-up's upscale assessment; the
//    measured factor and required source size are recorded in the
//    measurements whether or not the plan passes.
//
// assertCompositionPlan is the throwing entry point: structural
// findings (from parse) precede QC findings in its CompositingError,
// matching the Section 16.9 blocking order (validation before QC).

import {
  Box,
  COMPOSITING_QC_CATEGORY,
  CompositingError,
  CompositingFinding,
  Point,
  boxContains,
  boxIntersection,
  normalizedPointToSource,
} from "./types";
import {
  mapSourceBoxToTarget,
  placementForCrop,
  protectedRegionsFromNormalized,
  solveCropFromNormalized,
} from "./crop";
import {
  checkSubjectMotion,
  checkSubjectVisibility,
  subjectFractionAt,
} from "./reveal";
import { assessUpscale, upscaleFinding, zoomWindowAt, type UpscaleAssessment, type ZoomWindow } from "./closeup";
import {
  CompositionPlan,
  parseCompositionPlan,
  toSubjectMotion,
} from "./plan";

export interface QcMeasurements {
  /** The solved crop per crop target name (targets whose crop was
   * impossible are absent and carry a finding instead). */
  crops: Record<string, Box>;
  /** Protected regions mapped onto the canvas through the primary
   * crop, by region id (the M08 evidence). */
  mappedProtectedRegions: Record<string, Box>;
  /** The close-up assessment, when the plan declares one. */
  closeUp?: { window: ZoomWindow; assessment: UpscaleAssessment };
  /** The subject's visible fraction at the plan's final frame. */
  subjectFinalFraction?: number;
}

export interface QcResult {
  findings: CompositingFinding[];
  measurements: QcMeasurements;
}

function qcFinding(rule: string, path: string, message: string): CompositingFinding {
  return { category: COMPOSITING_QC_CATEGORY, rule, path, message };
}

export function checkCompositionPlan(plan: CompositionPlan): QcResult {
  const findings: CompositingFinding[] = [];
  const measurements: QcMeasurements = { crops: {}, mappedProtectedRegions: {} };

  const image = plan.image;

  // ---- outcome 2: crop solving per target (both ratios) -------------
  if (image) {
    plan.cropTargets.forEach((target, index) => {
      const path = `crop_targets[${index}]`;
      const result = solveCropFromNormalized(
        image.source,
        target.aspect,
        image.focalPoint,
        image.protectedRegions
      );
      if (!result.ok) {
        findings.push(
          qcFinding(
            result.reason,
            path,
            `crop target "${target.name}" (${target.aspect.w}:${target.aspect.h}) ` +
              `cannot be satisfied: ${result.message}`
          )
        );
        return;
      }
      measurements.crops[target.name] = result.crop;
      // Defense in depth: the solver proves these by construction;
      // QC re-asserts them independently over the recorded crop.
      if (image.focalPoint) {
        const focal: Point = normalizedPointToSource(image.focalPoint, image.source);
        const inside =
          focal.x >= result.crop.x &&
          focal.x <= result.crop.x + result.crop.width &&
          focal.y >= result.crop.y &&
          focal.y <= result.crop.y + result.crop.height;
        if (!inside) {
          findings.push(
            qcFinding(
              "focal-outside-crop",
              path,
              `focal point (${focal.x}, ${focal.y}) lies outside the solved crop ` +
                `for target "${target.name}": ${JSON.stringify(result.crop)}`
            )
          );
        }
      }
      const regionsPx = protectedRegionsFromNormalized(image.protectedRegions, image.source);
      for (const region of regionsPx) {
        if (!boxContains(result.crop, region.box)) {
          findings.push(
            qcFinding(
              "protected-region-outside-crop",
              path,
              `protected region "${region.id}" ${JSON.stringify(region.box)} is not ` +
                `fully inside the solved crop for target "${target.name}": ` +
                JSON.stringify(result.crop)
            )
          );
        }
      }
    });

    // ---- outcome 3: M08 text vs protected regions -------------------
    const primaryCrop = measurements.crops[plan.cropTargets[0].name] as Box | undefined;
    if (primaryCrop && plan.textBoxes.length > 0) {
      const primary = plan.cropTargets[0];
      const placement = placementForCrop(primaryCrop, {
        width: primary.box.width,
        height: primary.box.height,
      });
      const regionsPx = protectedRegionsFromNormalized(image.protectedRegions, image.source);
      for (const region of regionsPx) {
        measurements.mappedProtectedRegions[region.id] = mapSourceBoxToTarget(
          region.box,
          primaryCrop,
          placement
        );
      }
      for (const textBox of plan.textBoxes) {
        for (const region of image.protectedRegions) {
          const mapped = measurements.mappedProtectedRegions[region.id];
          if (!mapped) continue;
          const hit = boxIntersection(textBox.box, mapped);
          if (hit && !plan.allowTextOverlap.includes(region.id)) {
            findings.push(
              qcFinding(
                "protected-text-intersection",
                `text_boxes/${textBox.id}`,
                `text box "${textBox.id}" (${textBox.kind}) intersects protected ` +
                  `region "${region.id}"${region.label ? ` (${region.label})` : ""} ` +
                  `over ${JSON.stringify(hit)} on the canvas: essential type may ` +
                  "never cover a face, logo, or proof region (M08). If the " +
                  "approved design deliberately permits this overlap, record " +
                  `the region id in allow_text_overlap`
              )
            );
          }
        }
      }
    }
  }

  // ---- outcome 1: subject visibility and motion shape -----------------
  const motion = toSubjectMotion(plan);
  if (motion && plan.subjectMotion) {
    const path = "subject_motion";
    findings.push(...checkSubjectMotion(motion, path));
    findings.push(
      ...checkSubjectVisibility(
        motion,
        plan.declaredExit,
        0,
        plan.durationFrames,
        path
      )
    );
    measurements.subjectFinalFraction = subjectFractionAt(
      plan.durationFrames - 1,
      motion
    );
  }

  // ---- outcome 4: close-up detail accuracy ---------------------------
  if (plan.closeUp && image) {
    const closeUp = plan.closeUp;
    const detail: Point = normalizedPointToSource(closeUp.detail, image.source);
    const window = zoomWindowAt(image.source, detail, closeUp.maxZoom);
    const assessment = assessUpscale({
      source: image.source,
      detail,
      maxZoom: closeUp.maxZoom,
      output: closeUp.output,
      declaredLimit: closeUp.maxUpscale,
    });
    measurements.closeUp = { window, assessment };
    const finding = upscaleFinding(assessment, closeUp.id, "close_up");
    if (finding) findings.push(finding);
  }

  return { findings, measurements };
}

/**
 * Full gate: parse the document (contract findings first), then QC.
 * Throws CompositingError carrying every finding; returns the plan
 * and its measurements when clean.
 */
export function assertCompositionPlan(doc: unknown): {
  plan: CompositionPlan;
  measurements: QcMeasurements;
} {
  const plan = parseCompositionPlan(doc);
  const { findings, measurements } = checkCompositionPlan(plan);
  if (findings.length > 0) throw new CompositingError(findings);
  return { plan, measurements };
}
