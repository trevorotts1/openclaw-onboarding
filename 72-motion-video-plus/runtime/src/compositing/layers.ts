// Layered composition descriptors and depth honesty (Directive
// MG-012; the MG-019 choreography vocabulary's "depth" behavior).
//
// A layered plan stacks images back to front. Depth in such a plan is
// one of exactly two things, and the plan must say which:
// - "2.5d_layered": flat layers at different parallax rates. The
//   separation is real composition, not a spatial scene.
// - "3d_genuine": a native spatial scene. The plan must carry spatial
//   scene inputs (a declared spatial scene with a renderer); calling
//   flat layers "3D" because they move at different rates is exactly
//   the mislabel VREF-05 forbids ("labeled 3D only when the native
//   implementation actually uses a spatial scene").
//
// Validation failures here are plan-contract errors (MG_SCHEMA_INVALID,
// exit class 2): the document claims something its own contents
// contradict, before any frame is rendered.
//
// Parallax is DERIVED from layer order, never declared per layer (a
// declared factor could disagree with the stacking it describes). The
// single subject layer is the reference at exactly 1. Each step away
// from the subject changes the factor by one quarter: behind the
// subject 0.75, 0.5, 0.25, floored at 0.125; in front of it 1.25,
// 1.5, 1.75, and so on. Quarter steps are exact in binary floating
// point, so derived factors compare exactly.

import {
  COMPOSITING_CONTRACT_CATEGORY,
  CompositingFinding,
} from "./types";

export type DepthKind = "2.5d_layered" | "3d_genuine";
export const DEPTH_KINDS: readonly DepthKind[] = ["2.5d_layered", "3d_genuine"];

export type LayerRole =
  | "background"
  | "midground"
  | "subject"
  | "foreground"
  | "overlay";

export const LAYER_ROLES: readonly LayerRole[] = [
  "background",
  "midground",
  "subject",
  "foreground",
  "overlay",
];

export interface LayerSpec {
  id: string;
  role: LayerRole;
  /** Asset id from the job's manifest, when the layer is an asset. */
  assetId?: string;
}

/** The plan's depth declaration. `spatialScene` records whether the
 * plan carries native spatial-scene inputs; it is the evidence a
 * "3d_genuine" claim stands on. */
export interface DepthSpec {
  kind?: DepthKind;
  spatialScene?: {
    present: boolean;
    /** The native scene source or renderer, for the record. */
    source?: string;
  };
}

export interface LayerPlan {
  /** The derived parallax factor for this layer (subject = 1). */
  factor: number;
  layer: LayerSpec;
}

const PARALLAX_STEP = 0.25;
const PARALLAX_FLOOR = 0.125;

/** Derive the parallax factor for the layer at `index` in a stack of
 * `count` layers whose subject sits at `subjectIndex`. */
export function parallaxFactor(index: number, subjectIndex: number): number {
  const distance = Math.abs(index - subjectIndex);
  if (distance === 0) return 1;
  if (index < subjectIndex) {
    return Math.max(PARALLAX_FLOOR, 1 - PARALLAX_STEP * distance);
  }
  return 1 + PARALLAX_STEP * distance;
}

/**
 * True when a plan claims depth at all: an explicit depth block, or a
 * stack of two or more layers (stacked layers moving as one rigid
 * plane would not need a plan; a layered plan exists to separate
 * them). A plan claiming depth must declare its kind.
 */
export function planClaimsDepth(
  layers: LayerSpec[] | undefined,
  depth: DepthSpec | undefined
): boolean {
  if (depth !== undefined) return true;
  return Array.isArray(layers) && layers.length >= 2;
}

/**
 * Validate the layer stack and depth declaration of a plan. Returns
 * contract findings (MG_SCHEMA_INVALID): undeclared or mislabeled
 * depth, a 3D claim with no spatial scene behind it, a layered claim
 * with nothing to layer, duplicate layer ids, or a stack with no
 * single subject reference.
 */
export function validateLayers(
  layers: LayerSpec[] | undefined,
  depth: DepthSpec | undefined,
  path: string
): CompositingFinding[] {
  const findings: CompositingFinding[] = [];
  const fail = (rule: string, message: string): void => {
    findings.push({
      category: COMPOSITING_CONTRACT_CATEGORY,
      rule,
      path: rule.startsWith("depth-") ? "depth" : path,
      message,
    });
  };
  const stack = layers ?? [];

  const seen = new Set<string>();
  for (const layer of stack) {
    if (seen.has(layer.id)) {
      fail("layers-duplicate-id", `layer id "${layer.id}" appears twice in the stack`);
    }
    seen.add(layer.id);
  }

  if (stack.length >= 2) {
    const subjects = stack.filter((l) => l.role === "subject");
    if (subjects.length !== 1) {
      fail(
        "layers-subject-count",
        `a layered stack needs exactly one subject layer as its parallax ` +
          `reference, found ${subjects.length}: parallax is derived from the ` +
          "subject's position, so an ambiguous stack has no honest factors"
      );
    }
  }

  if (planClaimsDepth(layers, depth)) {
    if (!depth || depth.kind === undefined) {
      fail(
        "depth-kind-missing",
        "the plan claims depth (a depth block or a multi-layer stack) but does " +
          'not declare depth_kind: record exactly "2.5d_layered" or "3d_genuine" ' +
          "(MG-012: record whether depth is 2.5D layered composition or genuine 3D)"
      );
    } else if (!DEPTH_KINDS.includes(depth.kind)) {
      fail(
        "depth-kind-invalid",
        `depth_kind ${JSON.stringify(depth.kind)} is not one of "2.5d_layered", "3d_genuine"`
      );
    } else if (depth.kind === "3d_genuine") {
      if (!depth.spatialScene || depth.spatialScene.present !== true) {
        fail(
          "depth-3d-without-spatial-scene",
          'depth_kind "3d_genuine" is claimed but the plan carries no spatial ' +
            "scene inputs: flat layers at different parallax rates are 2.5D " +
            "layered composition, and labeling them 3D misstates the scene"
        );
      }
    } else if (depth.kind === "2.5d_layered") {
      if (stack.length < 2) {
        fail(
          "depth-layered-needs-layers",
          'depth_kind "2.5d_layered" is declared but the stack has fewer than ' +
            "two layers: layered composition needs layers to compose"
        );
      }
    }
  }
  return findings;
}

/**
 * Build the layer plan with derived parallax factors. Throws a plain
 * Error when the stack has no single subject: callers validate first
 * (validateLayers) for the structured finding; this is the computing
 * entry point and assumes a valid stack.
 */
export function buildLayerPlan(layers: LayerSpec[]): LayerPlan[] {
  const subjectIndex = layers.findIndex((l) => l.role === "subject");
  if (layers.length >= 2 && subjectIndex < 0) {
    throw new Error("layered stack has no subject layer to derive parallax from");
  }
  const reference = subjectIndex >= 0 ? subjectIndex : 0;
  return layers.map((layer, index) => ({
    layer,
    factor: layers.length < 2 ? 1 : parallaxFactor(index, reference),
  }));
}
