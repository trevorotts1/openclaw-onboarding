// The placement audit (Directive MG-014: target-size preview
// tooling; acceptance: "An inset PowerPoint placement cannot pass
// solely because the original full-frame render is readable").
//
// auditPlacement judges one variant AT ITS DELIVERY PLACEMENT:
// - Every text element is measured with the actual font by the
//   MG-013 rendered-layout audit, at its EFFECTIVE size: the
//   authored size times the placement scale (display width over
//   canvas width). Role floors never scale down to meet a small
//   placement. An inset at half width halves every effective size,
//   and copy that was comfortable full-frame fails there if it
//   drops below its floor. That is the final placement test the
//   directive requires essential text to pass.
// - Every image is solved through the MG-012 crop solver for this
//   variant's own canvas aspect and placed into the variant's image
//   box with one uniform scale (never stretched, never center-
//   cropped by default: the crop is solved around the focal point
//   and the protected regions). The protected regions, mapped onto
//   the canvas through that crop, join the audit's protected areas,
//   so essential text is checked against the face or proof region
//   as it will actually appear in THIS variant.
// - The export keeps the variant's own aspect regardless of the
//   slide layout it sits in; that rule is enforced in resolve.ts
//   (LAYOUT_EXPORT_ASPECT) and restated in the result for the
//   reviewer.

import {
  mapSourceBoxToTarget,
  placementForCrop,
  protectedRegionsFromNormalized,
  solveCropFromNormalized,
  type Box,
} from "../compositing";
import {
  auditLayout,
  type AuditResult,
  type LayoutElement,
  type LayoutRecord,
  type Placement,
  type ProtectedArea,
  type TypographyTokens,
} from "../typography";
import {
  reduceAspect,
  type LayoutFinding,
  type LayoutVariant,
  type PlacementFacts,
  type SharedContentRecord,
} from "./types";
import { materializeCopy } from "./validate";

/** The display size and effective scale of a variant's placement.
 * Millimetre declarations convert through the slide's own
 * pixel-per-millimetre ratio: presentation sizes are real-world
 * sizes, and no display DPI is assumed. */
export function placementFacts(variant: LayoutVariant): PlacementFacts {
  const { canvas, placement } = variant;
  if (placement.kind === "full_frame") {
    return {
      displayWidthPx: canvas.width,
      displayHeightPx: canvas.height,
      scale: 1,
      basis: "full_frame",
    };
  }
  let widthPx: number;
  let heightPx: number;
  let basis: PlacementFacts["basis"];
  if (placement.display) {
    widthPx = placement.display.widthPx;
    heightPx = placement.display.heightPx;
    basis = "declared_px";
  } else if (placement.displayMm) {
    const pxPerMmX = placement.slide.widthPx / placement.slide.widthMm;
    const pxPerMmY = placement.slide.heightPx / placement.slide.heightMm;
    widthPx = Math.round(placement.displayMm.widthMm * pxPerMmX);
    heightPx = Math.round(placement.displayMm.heightMm * pxPerMmY);
    basis = "declared_mm";
  } else {
    throw new Error(
      `variant "${variant.id}": inset placement declares neither display pixels nor millimetres`
    );
  }
  return {
    displayWidthPx: widthPx,
    displayHeightPx: heightPx,
    scale: widthPx / canvas.width,
    basis,
  };
}

export interface ImagePlacementFacts {
  /** The solved integer crop in source pixels. */
  crop: Box;
  /** The single uniform scale mapping the crop into the image box. */
  scale: number;
  /** Where the crop lands inside the image box. */
  drawn: Box;
  /** Protected regions mapped onto this variant's canvas. */
  mappedProtectedRegions: Record<string, Box>;
  /** Defense in depth: the focal point, rechecked inside the crop. */
  focalInsideCrop: boolean | null;
}

export interface PlacementAuditResult {
  variantId: string;
  destination: LayoutVariant["destination"];
  placement: PlacementFacts;
  /** The aspect the delivered file keeps (the variant's canvas
   * aspect), restated so a reviewer sees placement cannot change it. */
  exportAspect: { w: number; h: number };
  typography: AuditResult;
  imageFacts: ImagePlacementFacts | null;
  /** Layout-level findings (the typography findings live in
   * `typography`). */
  findings: LayoutFinding[];
  pass: boolean;
}

function elementPlacement(variant: LayoutVariant, facts: PlacementFacts): Placement {
  if (variant.placement.kind === "full_frame") {
    return variant.destination === "vsl_mobile" || reduceAspect(variant.canvas).w === 9
      ? { kind: "recomposed" }
      : { kind: "full_frame" };
  }
  return {
    kind: "inset",
    destinationWidth: facts.displayWidthPx,
    destinationHeight: facts.displayHeightPx,
  };
}

export function auditPlacement(
  content: SharedContentRecord,
  variant: LayoutVariant,
  tokens: TypographyTokens
): PlacementAuditResult {
  const findings: LayoutFinding[] = [];
  const facts = placementFacts(variant);
  const placement = elementPlacement(variant, facts);

  // ---- image facts through the MG-012 solver ----------------------
  let imageFacts: ImagePlacementFacts | null = null;
  const mappedAreas: ProtectedArea[] = [];
  if (content.image && variant.imageBox) {
    const image = content.image;
    const aspect = reduceAspect({
      width: variant.imageBox.width,
      height: variant.imageBox.height,
    });
    const solved = solveCropFromNormalized(
      image.source,
      aspect,
      image.focalPoint,
      image.protectedRegions
    );
    if (!solved.ok) {
      findings.push({
        kind: "LAYOUT_IMAGE_CROP_IMPOSSIBLE",
        severity: "error",
        variantId: variant.id,
        elementId: null,
        message:
          `Variant "${variant.id}": no crop of asset "${image.assetId}" satisfies this ` +
          `variant's image box aspect ${aspect.w}:${aspect.h}: ${solved.message}`,
      });
    } else {
      const placementInBox = placementForCrop(solved.crop, {
        width: variant.imageBox.width,
        height: variant.imageBox.height,
      });
      const regionsPx = protectedRegionsFromNormalized(
        image.protectedRegions,
        image.source
      );
      const mapped: Record<string, Box> = {};
      for (const region of regionsPx) {
        const inBox = mapSourceBoxToTarget(region.box, solved.crop, placementInBox);
        const onCanvas: Box = {
          x: inBox.x + variant.imageBox.x,
          y: inBox.y + variant.imageBox.y,
          width: inBox.width,
          height: inBox.height,
        };
        mapped[region.id] = onCanvas;
        mappedAreas.push({
          ...onCanvas,
          id: region.id,
          reason: `protected region of asset "${image.assetId}"${region.label ? ` (${region.label})` : ""}, mapped through this variant's solved crop`,
        });
      }
      let focalInside: boolean | null = null;
      if (image.focalPoint) {
        const focal = {
          x: image.focalPoint.x * image.source.width,
          y: image.focalPoint.y * image.source.height,
        };
        focalInside =
          focal.x >= solved.crop.x &&
          focal.x <= solved.crop.x + solved.crop.width &&
          focal.y >= solved.crop.y &&
          focal.y <= solved.crop.y + solved.crop.height;
        if (!focalInside) {
          findings.push({
            kind: "LAYOUT_IMAGE_FOCAL_LOST",
            severity: "error",
            variantId: variant.id,
            elementId: null,
            message:
              `Variant "${variant.id}": the solved crop ${JSON.stringify(solved.crop)} loses ` +
              `the focal point (${focal.x}, ${focal.y}) of asset "${image.assetId}". The solver ` +
              "proves containment by construction; this recheck exists so a regression is a finding, not a shipped frame.",
          });
        }
      }
      // The drawn box is in image-box space; report it on the canvas.
      const drawn: Box = {
        x: placementInBox.drawn.x + variant.imageBox.x,
        y: placementInBox.drawn.y + variant.imageBox.y,
        width: placementInBox.drawn.width,
        height: placementInBox.drawn.height,
      };
      imageFacts = {
        crop: solved.crop,
        scale: placementInBox.scale,
        drawn,
        mappedProtectedRegions: mapped,
        focalInsideCrop: focalInside,
      };
    }
  } else if (content.image && !variant.imageBox) {
    findings.push({
      kind: "LAYOUT_IMAGE_BOX_MISSING",
      severity: "error",
      variantId: variant.id,
      elementId: null,
      message:
        `Variant "${variant.id}" lays out image content but declares no imageBox. ` +
        "Where the image sits is a layout decision every image variant records.",
    });
  }

  // ---- typography at the effective placement size -----------------
  const elements: LayoutElement[] = [];
  for (const element of variant.elements) {
    const copy = materializeCopy(content, element.ref);
    if (copy === null) {
      // Already a resolver finding; the audit cannot measure copy it
      // cannot read, so it records the gap and moves on.
      findings.push({
        kind: "LAYOUT_COPY_REF_UNKNOWN",
        severity: "error",
        variantId: variant.id,
        elementId: element.id,
        message: `Element "${element.id}" references copy the shared content does not carry; it cannot be measured at placement.`,
      });
      continue;
    }
    elements.push({
      id: element.id,
      role: element.role,
      copy,
      sizePx: element.sizePx,
      box: element.box,
      placement,
      font: element.font,
    });
  }
  const record: LayoutRecord = {
    id: variant.id,
    canvas: variant.canvas,
    font: variant.font,
    protectedAreas: [...(variant.protectedAreas ?? []), ...mappedAreas],
    elements,
  };
  const typography = auditLayout(record, tokens);

  return {
    variantId: variant.id,
    destination: variant.destination,
    placement: facts,
    exportAspect: reduceAspect(variant.canvas),
    typography,
    imageFacts,
    findings,
    pass:
      findings.every((f) => f.severity !== "error") && typography.pass,
  };
}
