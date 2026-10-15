// The layout-variant resolver (Directive MG-014).
//
// resolveVariantSet judges a set of per-destination layout records
// against their one shared content record:
//
// 1. Identity and canvas law: each variant names the shared content
//    it lays out; its canvas carries the aspect its destination
//    requires (Section 4.1: PowerPoint and desktop VSL are 16:9,
//    mobile VSL is 9:16, an export keeps its own aspect even inside a
//    slide layout, so exportAspect must equal the canvas aspect).
// 2. Completeness: the shared message must actually arrive. The
//    headline element exists; for chart content, every row has both
//    a label element and a value element; every copy reference
//    resolves into the shared content (elements reference copy, they
//    never restate it).
// 3. Safe areas: every text element box, the plot, and the image box
//    stay out of the unsafe zones of the variant's declared profile.
//    The profile must exist, must be measured for the variant's
//    canvas, and must be the destination's own: a social-platform
//    chrome profile is refused for any variant whose destination
//    does not explicitly declare platform delivery.
// 4. Recomposition, proven geometrically: a vsl_mobile variant is
//    compared against the set's landscape sibling. It is a SCALED
//    DUPLICATE, and rejected, when everything corresponds under one
//    uniform scale: same arrangement kind, same slot order, no
//    staging beats, and every corresponding element box, the plot,
//    and the bar thickness at the same normalized position (within
//    rounding tolerance). Any material difference (a different
//    arrangement, staged beats, re-derived geometry) is a genuine
//    recomposition. The check is geometric, not nominal: renaming
//    the arrangement kind while keeping scaled geometry still
//    fails, because the boxes are what is compared.
// 5. Comparable data scales (MG-015): every chart variant maps the
//    shared dataset under the dataset's own domain and scale type,
//    and the same value lands at the same fraction of the plot
//    extent in every variant. Pixels per unit legitimately differ
//    between a 1200 px desktop plot and a 740 px mobile plot; what
//    may not differ is the domain or the normalized mapping, which
//    is what would change what the data says.

import { boxIntersection, type Box } from "../compositing";
import { getSafeAreaProfile } from "./profiles";
import {
  destinationAspect,
  reduceAspect,
  type LayoutFinding,
  type LayoutVariant,
  type SharedContentRecord,
} from "./types";
import { chartScaleFacts, materializeCopy, type ChartScaleFacts } from "./validate";

export interface VariantResolution {
  variantId: string;
  destination: LayoutVariant["destination"];
  findings: LayoutFinding[];
  scaleFacts: ChartScaleFacts | null;
  pass: boolean;
}

export interface VariantSetResolution {
  contentId: string;
  results: VariantResolution[];
  findings: LayoutFinding[];
  pass: boolean;
}

/** Normalized-position tolerance for the scaled-duplicate test:
 * 0.2% of the canvas dimension absorbs integer rounding of an
 * honest scale copy (a 420 px offset on a 1920 canvas lands within
 * a pixel or two on a 1080 canvas) while remaining far below the
 * geometry shift of any real recomposition. */
export const SCALE_DUPLICATE_TOLERANCE = 0.002;

function err(
  kind: string,
  variantId: string | null,
  elementId: string | null,
  message: string,
  measured?: Record<string, number | string>
): LayoutFinding {
  return { kind, severity: "error", variantId, elementId, message, measured };
}

function normalized(box: Box, canvas: { width: number; height: number }) {
  return {
    x: box.x / canvas.width,
    y: box.y / canvas.height,
    width: box.width / canvas.width,
    height: box.height / canvas.height,
  };
}

function boxesMatchUnderScale(
  a: Box,
  aCanvas: { width: number; height: number },
  b: Box,
  bCanvas: { width: number; height: number },
  tolerance: number
): boolean {
  const na = normalized(a, aCanvas);
  const nb = normalized(b, bCanvas);
  return (
    Math.abs(na.x - nb.x) <= tolerance &&
    Math.abs(na.y - nb.y) <= tolerance &&
    Math.abs(na.width - nb.width) <= tolerance &&
    Math.abs(na.height - nb.height) <= tolerance
  );
}

/** True when `mobile` is the landscape `reference` under one uniform
 * scale: the exact thing MG-014 forbids calling a mobile variant. */
export function isScaledDuplicate(
  reference: LayoutVariant,
  mobile: LayoutVariant
): boolean {
  const refArr = reference.arrangement;
  const mobArr = mobile.arrangement;
  if (refArr && mobArr) {
    if (refArr.kind !== mobArr.kind) return false;
    const refOrder = refArr.slots.map((s) => s.rowId).join(",");
    const mobOrder = mobArr.slots.map((s) => s.rowId).join(",");
    if (refOrder !== mobOrder) return false;
    if ((mobArr.beats?.length ?? 0) > 0) return false;
    if (
      !boxesMatchUnderScale(
        refArr.plot,
        reference.canvas,
        mobArr.plot,
        mobile.canvas,
        SCALE_DUPLICATE_TOLERANCE
      )
    ) {
      return false;
    }
    const refThick = refArr.barThickness / reference.canvas.height;
    const mobThick = mobArr.barThickness / mobile.canvas.height;
    if (Math.abs(refThick - mobThick) > SCALE_DUPLICATE_TOLERANCE) return false;
  } else if (refArr || mobArr) {
    return false;
  }
  if (reference.elements.length !== mobile.elements.length) return false;
  const mobileById = new Map(mobile.elements.map((e) => [e.id, e]));
  for (const refEl of reference.elements) {
    const mobEl = mobileById.get(refEl.id);
    if (!mobEl) return false;
    if (
      !boxesMatchUnderScale(
        refEl.box,
        reference.canvas,
        mobEl.box,
        mobile.canvas,
        SCALE_DUPLICATE_TOLERANCE
      )
    ) {
      return false;
    }
  }
  return true;
}

function resolveOne(
  content: SharedContentRecord,
  variant: LayoutVariant,
  siblings: LayoutVariant[]
): VariantResolution {
  const findings: LayoutFinding[] = [];
  const vid = variant.id;

  if (variant.contentId !== content.id) {
    findings.push(
      err(
        "LAYOUT_CONTENT_MISMATCH",
        vid,
        null,
        `Variant "${vid}" lays out content "${variant.contentId}" but was resolved against "${content.id}". A variant record belongs to exactly one shared content record.`
      )
    );
  }

  const required = destinationAspect(variant.destination);
  const canvasAspect = reduceAspect(variant.canvas);
  const aspectOk = Array.isArray(required)
    ? required.some((a) => a.w === canvasAspect.w && a.h === canvasAspect.h)
    : required.w === canvasAspect.w && required.h === canvasAspect.h;
  if (!aspectOk) {
    findings.push(
      err(
        "LAYOUT_CANVAS_MISMATCH",
        vid,
        null,
        `Variant "${vid}" targets ${variant.destination}, whose canvas must be ` +
          (Array.isArray(required)
            ? required.map((a) => `${a.w}:${a.h}`).join(" or ")
            : `${required.w}:${required.h}`) +
          `, but its canvas is ${variant.canvas.width}x${variant.canvas.height} (${canvasAspect.w}:${canvasAspect.h}). Section 4.1 fixes the canvas per mode; a vertical destination is never served a landscape canvas or the reverse.`,
        { canvasAspect: `${canvasAspect.w}:${canvasAspect.h}` }
      )
    );
  }
  if (
    variant.exportAspect.w !== canvasAspect.w ||
    variant.exportAspect.h !== canvasAspect.h
  ) {
    findings.push(
      err(
        "LAYOUT_EXPORT_ASPECT",
        vid,
        null,
        `Variant "${vid}" declares export aspect ${variant.exportAspect.w}:${variant.exportAspect.h} but its canvas is ${canvasAspect.w}:${canvasAspect.h}. An export keeps its own aspect even when placed inside a slide layout; placement never rewrites it.`,
        { exportAspect: `${variant.exportAspect.w}:${variant.exportAspect.h}`, canvasAspect: `${canvasAspect.w}:${canvasAspect.h}` }
      )
    );
  }

  // Completeness and copy references.
  const refs = new Set<string>();
  for (const element of variant.elements) {
    const copy = materializeCopy(content, element.ref);
    if (copy === null) {
      findings.push(
        err(
          "LAYOUT_COPY_REF_UNKNOWN",
          vid,
          element.id,
          `Element "${element.id}" references copy the shared content does not carry (${JSON.stringify(element.ref)}). Elements reference the shared content; they never restate copy locally, so an unresolvable reference means the message does not arrive.`
        )
      );
      continue;
    }
    refs.add(JSON.stringify(element.ref));
  }
  if (!refs.has(JSON.stringify({ field: "headline" }))) {
    findings.push(
      err(
        "LAYOUT_CONTENT_MISSING",
        vid,
        null,
        `Variant "${vid}" has no element carrying the shared headline. Every variant delivers the whole message, not a subset of it.`
      )
    );
  }
  if (content.chart) {
    for (const row of content.chart.rows) {
      if (!refs.has(JSON.stringify({ rowLabel: row.id }))) {
        findings.push(
          err(
            "LAYOUT_CONTENT_MISSING",
            vid,
            null,
            `Variant "${vid}" has no label element for chart row "${row.id}". A variant that drops a category has changed the message, not recomposed it.`
          )
        );
      }
      if (!refs.has(JSON.stringify({ rowValue: row.id }))) {
        findings.push(
          err(
            "LAYOUT_CONTENT_MISSING",
            vid,
            null,
            `Variant "${vid}" has no value element for chart row "${row.id}". A variant that drops a value has changed the message, not recomposed it.`
          )
        );
      }
    }
    const arr = variant.arrangement;
    if (!arr) {
      findings.push(
        err(
          "LAYOUT_CONTENT_MISSING",
          vid,
          null,
          `Variant "${vid}" lays out chart content but declares no arrangement. The plot geometry is a layout decision every chart variant records.`
        )
      );
    } else {
      const rowIds = new Set(content.chart.rows.map((r) => r.id));
      for (const slot of arr.slots) {
        if (!rowIds.has(slot.rowId)) {
          findings.push(
            err(
              "LAYOUT_COPY_REF_UNKNOWN",
              vid,
              null,
              `Arrangement slot names row "${slot.rowId}", which the shared dataset does not carry.`
            )
          );
        }
      }
      if (arr.kind === "staged_rows" && arr.beats) {
        const beatRows = new Set(arr.beats.flatMap((b) => b.rowIds));
        for (const row of content.chart.rows) {
          if (!beatRows.has(row.id)) {
            findings.push(
              err(
                "LAYOUT_CONTENT_MISSING",
                vid,
                null,
                `Staged variant "${vid}" never stages chart row "${row.id}" in any beat. Staging spreads the message across beats; it does not drop parts of it.`
              )
            );
          }
        }
      }
    }
  }

  // Safe-area profile discipline and zone checks.
  const profile = getSafeAreaProfile(variant.safeAreaProfile);
  if (!profile) {
    findings.push(
      err(
        "LAYOUT_PROFILE_UNKNOWN",
        vid,
        null,
        `Variant "${vid}" names safe-area profile "${variant.safeAreaProfile}", which is not a registered profile. Safe areas come from a measured player profile, not from memory.`
      )
    );
  } else {
    if (
      profile.canvas.width !== variant.canvas.width ||
      profile.canvas.height !== variant.canvas.height
    ) {
      findings.push(
        err(
          "LAYOUT_PROFILE_CANVAS_MISMATCH",
          vid,
          null,
          `Profile "${profile.id}" was measured for a ${profile.canvas.width}x${profile.canvas.height} canvas but variant "${vid}" composes on ${variant.canvas.width}x${variant.canvas.height}. A profile is only meaningful on the canvas it was measured for.`
        )
      );
    }
    if (profile.kind === "social_platform" && variant.platformDelivery !== true) {
      findings.push(
        err(
          "LAYOUT_PROFILE_NOT_APPLICABLE",
          vid,
          null,
          `Variant "${vid}" declares the social-platform profile "${profile.id}" but its destination does not declare platform delivery. Social-platform controls are not applied to a mobile VSL by default (MG-014): compose for the player the piece will actually play in.`
        )
      );
    }
    const guarded: Array<{ id: string | null; box: Box; what: string }> = [
      ...variant.elements.map((e) => ({
        id: e.id as string | null,
        box: e.box,
        what: `text element "${e.id}"`,
      })),
      ...(variant.arrangement
        ? [{ id: null, box: variant.arrangement.plot, what: "the plot" }]
        : []),
      ...(variant.imageBox
        ? [{ id: null, box: variant.imageBox, what: "the image placement" }]
        : []),
    ];
    for (const item of guarded) {
      for (const zone of profile.unsafeZones) {
        const hit = boxIntersection(item.box, zone.box);
        if (hit) {
          findings.push(
            err(
              "LAYOUT_UNSAFE_ZONE",
              vid,
              item.id,
              `Variant "${vid}": ${item.what} intersects the "${zone.id}" unsafe zone of profile "${profile.id}" (${zone.reason}) over ${JSON.stringify(hit)}. The destination's own chrome will cover or fight that content.`,
              { zone: zone.id, overlapWidth: hit.width, overlapHeight: hit.height }
            )
          );
        }
      }
    }
  }

  // Recomposition: a mobile variant is judged against the set's
  // landscape sibling when one exists.
  if (variant.destination === "vsl_mobile") {
    const reference = siblings.find(
      (s) => s.id !== variant.id && s.canvas.width > s.canvas.height
    );
    if (reference && isScaledDuplicate(reference, variant)) {
      findings.push(
        err(
          "LAYOUT_SCALED_DUPLICATE",
          vid,
          null,
          `Mobile variant "${vid}" is variant "${reference.id}" under one uniform scale: same arrangement, same normalized geometry, no staging. That is a scaled duplicate, not a recomposition (MG-014, Section 4.1: do not call a center crop or a squeeze a mobile composition). Recompose: stack, restage across beats, and re-derive the plot for the vertical canvas.`
        )
      );
    }
  }

  let scaleFacts: ChartScaleFacts | null = null;
  if (content.chart && variant.arrangement) {
    scaleFacts = chartScaleFacts(content, variant.arrangement);
  }

  return {
    variantId: vid,
    destination: variant.destination,
    findings,
    scaleFacts,
    pass: findings.every((f) => f.severity !== "error"),
  };
}

/** Cross-variant scale comparability: same domain, and the same
 * value at the same fraction of the plot extent, in every chart
 * variant of the set. */
function comparabilityFindings(
  content: SharedContentRecord,
  variants: LayoutVariant[],
  results: VariantResolution[]
): LayoutFinding[] {
  if (!content.chart) return [];
  const findings: LayoutFinding[] = [];
  const withFacts = results.filter((r) => r.scaleFacts !== null);
  if (withFacts.length < 2) return [];
  const reference = withFacts[0];
  const refFacts = reference.scaleFacts as ChartScaleFacts;
  for (const other of withFacts.slice(1)) {
    const facts = other.scaleFacts as ChartScaleFacts;
    if (
      facts.domain[0] !== refFacts.domain[0] ||
      facts.domain[1] !== refFacts.domain[1]
    ) {
      findings.push(
        err(
          "LAYOUT_SCALE_NOT_COMPARABLE",
          other.variantId,
          null,
          `Variant "${other.variantId}" maps the data under domain [${facts.domain}] while "${reference.variantId}" uses [${refFacts.domain}]. Variants of one message keep one domain; rescaling the domain between destinations changes what the data says.`
        )
      );
      continue;
    }
    for (const pos of facts.normalizedPositions) {
      const refPos = refFacts.normalizedPositions.find((p) => p.rowId === pos.rowId);
      if (refPos && Math.abs(refPos.normalized - pos.normalized) > 1e-9) {
        findings.push(
          err(
            "LAYOUT_SCALE_NOT_COMPARABLE",
            other.variantId,
            null,
            `Value ${pos.value} (row "${pos.rowId}") lands at ${pos.normalized} of the plot extent in variant "${other.variantId}" but ${refPos.normalized} in "${reference.variantId}". Comparable scales put the same value at the same fraction of the plot in every variant (MG-015).`,
            { value: pos.value, normalizedHere: pos.normalized, normalizedReference: refPos.normalized }
          )
        );
      }
    }
  }
  return findings;
}

export function resolveVariantSet(
  content: SharedContentRecord,
  variants: LayoutVariant[]
): VariantSetResolution {
  const results = variants.map((v) => resolveOne(content, v, variants));
  const cross = comparabilityFindings(content, variants, results);
  const byId = new Map(results.map((r) => [r.variantId, r]));
  for (const finding of cross) {
    if (finding.variantId && byId.has(finding.variantId)) {
      byId.get(finding.variantId)?.findings.push(finding);
    }
  }
  for (const result of results) {
    result.pass = result.findings.every((f) => f.severity !== "error");
  }
  const findings = results.flatMap((r) => r.findings);
  return {
    contentId: content.id,
    results,
    findings,
    pass: findings.every((f) => f.severity !== "error"),
  };
}
