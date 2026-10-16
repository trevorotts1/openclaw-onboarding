// Capability-based engine routing for Skill 72 Motion Graphics V2
// (Directive MG-004, Section 3.2). This module is the executable half of
// references/renderer-routing.md: a pure function from scene requirements,
// explicit choices, and the capability matrix to per-scene engine
// assignments, or to a structured error.
//
// Rules that bind this code, from the directive and the owner decisions:
// - Engine choice is never inferred from the delivery mode. A PowerPoint
//   chart routes to Remotion; a PowerPoint image reveal routes to
//   Hyperframes. Routing input therefore has no mode field at all.
// - An explicit compatible choice (scene level first, then job level, then
//   the manifest default engine) wins over the scene-type default. An
//   explicit choice is never overridden silently: when the chosen engine
//   cannot confirm a required capability, routing fails with an explicit
//   error instead of substituting another engine.
// - Missing required capability is an explicit error, never permission to
//   downgrade imagery, lose alpha, or fall back to the legacy renderer.
// - The legacy engine is selectable only through the declared compatibility
//   path: the job must allow legacy fallback and the caller must choose it
//   explicitly. Routing never produces legacy on its own.
// - Baseline contract capabilities are not matrix-confirmed requirements:
//   both production engines are contracted to deliver the Section 4 mode
//   outputs (H.264 MP4, poster, source package). Requirements beyond that
//   baseline (alpha profiles, non-baseline codecs, 3D features, unusual
//   media types) must be confirmed by a "ready" capability record with
//   measured evidence behind it. An unprobed record confirms nothing.

import {
  AdapterError,
  CapabilityMatrix,
  Engine,
  EngineCapabilityRecord,
  ProductionEngine,
  PRODUCTION_ENGINES,
} from "./types";

export type { CapabilityMatrix, EngineCapabilityRecord } from "./types";

/** The Section 3.2 scene-requirement classes. */
export type SceneKind =
  | "editorial_image"
  | "product_ui"
  | "spatial_reveal"
  | "parallax"
  | "data_chart"
  | "data_variants"
  | "parameterized_infographic"
  | "existing_react_scene"
  | "existing_hyperframes_composition"
  | "three_dimensional"
  | "generic";

export interface SceneRequirement {
  sceneId: string | null;
  kind: SceneKind;
  /** Scene-level explicit engine (for example the V2 scene spec's engine
   * field). Wins over every default when compatible. */
  explicitEngine?: Engine | null;
  /** True when the delivery profile carries alpha (prores_4444_alpha or
   * vp9_alpha). Must be confirmed by a ready capability record. */
  requiresAlpha?: boolean;
  /** Codecs beyond the H.264 baseline that the export requires. Each must
   * be confirmed by a ready capability record. */
  extraCodecs?: string[];
  /** Media types beyond image and font that the scene consumes. Each must
   * be confirmed by a ready capability record. */
  extraMediaTypes?: string[];
  /** Named 3D feature the scene needs (three_dimensional scenes). Must be
   * confirmed by a ready capability record, with the evidence noted. */
  requires3dFeature?: string | null;
}

export interface RoutingRequest {
  scenes: SceneRequirement[];
  /** Caller-level explicit engine choice for the whole job. */
  explicitEngine?: Engine | null;
  /** The job manifest's rendering.default_engine, when one is set. */
  manifestDefaultEngine?: ProductionEngine | null;
  /** The job manifest's rendering.allow_legacy_fallback. Legacy is only
   * reachable when this is true AND an explicit choice names it. */
  allowLegacyFallback: boolean;
}

export interface SceneAssignment {
  sceneId: string | null;
  engine: Engine;
  /** Machine-stable reason code, for example "table_default",
   * "explicit_scene", "explicit_job", "manifest_default",
   * "capability_confirmed", "legacy_compatibility_path". */
  reasonCode: string;
  /** Human-readable reason, including capability evidence where a
   * confirmation decided the assignment. */
  reason: string;
}

export interface RoutingDecision {
  kind: "routed";
  assignments: SceneAssignment[];
  /** The engine that owns coherent sequences in this program. */
  primaryEngine: Engine;
  /** The single final assembly owner. Mixed-engine programs hand
   * normalized scene assets and timeline metadata to this owner; timing,
   * codec, color, audio, and dimensions must match across the handoff. */
  assemblyOwner: Engine;
}

export interface RoutingFailure {
  kind: "error";
  error: AdapterError;
}

export type RoutingResult = RoutingDecision | RoutingFailure;

/** The Section 3.2 default engine per scene kind. Three-dimensional scenes
 * have no brand default: they route by qualified feature support. */
export function tableDefault(kind: SceneKind): ProductionEngine | null {
  switch (kind) {
    case "editorial_image":
    case "product_ui":
    case "spatial_reveal":
    case "parallax":
    case "existing_hyperframes_composition":
      return "hyperframes";
    case "data_chart":
    case "data_variants":
    case "parameterized_infographic":
    case "existing_react_scene":
      return "remotion";
    case "three_dimensional":
    case "generic":
      return null;
  }
}

function recordFor(matrix: CapabilityMatrix, engine: Engine): EngineCapabilityRecord | null {
  return matrix.engines.find((r) => r.engine === engine) ?? null;
}

/** Requirements a ready record must confirm for an engine to take a scene.
 * Returns the list of unconfirmed requirement labels; empty means the
 * engine is confirmed for the scene. Baseline capabilities (H.264, image,
 * font) are contractual and never listed here. */
export function unconfirmedRequirements(
  record: EngineCapabilityRecord | null,
  scene: SceneRequirement
): string[] {
  const missing: string[] = [];
  const needsConfirmation =
    scene.requiresAlpha === true ||
    (scene.extraCodecs !== undefined && scene.extraCodecs.length > 0) ||
    (scene.extraMediaTypes !== undefined && scene.extraMediaTypes.length > 0) ||
    (scene.requires3dFeature !== undefined && scene.requires3dFeature !== null) ||
    scene.kind === "three_dimensional";
  if (!needsConfirmation) return missing;
  if (!record || record.probeStatus !== "ready") {
    missing.push("a ready capability record (engine is unprobed or unavailable)");
    return missing;
  }
  if (scene.requiresAlpha === true && !record.transparency.alphaVideo) {
    missing.push("alpha video export");
  }
  for (const codec of scene.extraCodecs ?? []) {
    if (!record.codecs.includes(codec)) missing.push(`codec ${codec}`);
  }
  for (const media of scene.extraMediaTypes ?? []) {
    if (!record.mediaTypes.includes(media)) missing.push(`media type ${media}`);
  }
  if (scene.kind === "three_dimensional") {
    const feature = scene.requires3dFeature ?? null;
    if (!feature) {
      if (record.features3d.length === 0) missing.push("a qualified 3D integration");
    } else if (!record.features3d.includes(feature)) {
      missing.push(`3D feature ${feature}`);
    }
  }
  return missing;
}

function capabilityError(scene: SceneRequirement, engine: Engine, missing: string[]): AdapterError {
  return new AdapterError({
    category: "MG_CAPABILITY_MISSING",
    engine,
    message:
      `Engine ${engine} cannot confirm required capability for scene ` +
      `${scene.sceneId ?? "(unnamed)"}: ${missing.join(", ")}. ` +
      "Routing does not downgrade imagery, drop alpha, or substitute another " +
      "renderer silently; provision the runtime or record a qualified " +
      "capability before rerouting.",
  });
}

interface Choice {
  engine: Engine;
  reasonCode: string;
  origin: "explicit_scene" | "explicit_job" | "manifest_default" | "table_default" | "capability";
}

function routeScene(
  scene: SceneRequirement,
  request: RoutingRequest,
  matrix: CapabilityMatrix
): SceneAssignment {
  // Legacy gate first: legacy is only an explicit choice made through the
  // declared compatibility path.
  const explicit: Engine | null = scene.explicitEngine ?? request.explicitEngine ?? null;
  if (explicit === "legacy") {
    if (!request.allowLegacyFallback) {
      throw new AdapterError({
        category: "MG_CAPABILITY_MISSING",
        engine: "legacy",
        message:
          "The legacy renderer was requested but this job does not declare " +
          "the compatibility path (rendering.allow_legacy_fallback is " +
          "false). Legacy is never a silent fallback.",
      });
    }
    return {
      sceneId: scene.sceneId,
      engine: "legacy",
      reasonCode: "legacy_compatibility_path",
      reason:
        "Explicit legacy choice through the declared compatibility path; " +
        "the job allows legacy fallback.",
    };
  }

  // Three-dimensional scenes route by qualified feature support, not by
  // brand: an explicit or default engine that confirms the feature wins,
  // otherwise any production engine whose ready record confirms it.
  if (scene.kind === "three_dimensional") {
    const preference: Array<{ engine: ProductionEngine; reasonCode: string }> = [];
    const named: Engine | null = explicit ?? request.manifestDefaultEngine ?? null;
    if (named === "hyperframes" || named === "remotion") {
      preference.push({ engine: named, reasonCode: explicit ? "explicit" : "manifest_default" });
    }
    for (const engine of PRODUCTION_ENGINES) {
      if (!preference.some((p) => p.engine === engine)) {
        preference.push({ engine, reasonCode: "capability_confirmed" });
      }
    }
    for (const candidate of preference) {
      const missing = unconfirmedRequirements(recordFor(matrix, candidate.engine), scene);
      if (missing.length === 0) {
        const record = recordFor(matrix, candidate.engine);
        return {
          sceneId: scene.sceneId,
          engine: candidate.engine,
          reasonCode: candidate.reasonCode,
          reason:
            `3D scene routed by qualified feature support: ${candidate.engine} ` +
            `record (version ${record?.installedVersion ?? "unknown"}, probed ` +
            `${record?.probedAt ?? "unknown"}) confirms ` +
            `${scene.requires3dFeature ?? "a qualified 3D integration"}. ` +
            `Evidence: ${(record?.evidence ?? []).join("; ") || "none recorded"}.`,
        };
      }
    }
    throw capabilityError(scene, named === "remotion" ? "remotion" : "hyperframes", [
      `3D feature ${scene.requires3dFeature ?? "(unspecified)"} confirmed by no production engine`,
    ]);
  }

  // Preferred engine by precedence: scene explicit, job explicit, the
  // table's preservation rows (an existing React scene stays Remotion, an
  // existing Hyperframes composition stays Hyperframes, because those rows
  // describe what the scene already is), manifest default, the remaining
  // table defaults, and finally the first production engine for an
  // otherwise generic scene.
  let choice: Choice;
  const table = tableDefault(scene.kind);
  const isPreservation =
    scene.kind === "existing_react_scene" || scene.kind === "existing_hyperframes_composition";
  if (explicit === "hyperframes" || explicit === "remotion") {
    choice = {
      engine: explicit,
      reasonCode: scene.explicitEngine ? "explicit_scene" : "explicit_job",
      origin: scene.explicitEngine ? "explicit_scene" : "explicit_job",
    };
  } else if (isPreservation && table) {
    choice = { engine: table, reasonCode: "table_default", origin: "table_default" };
  } else if (request.manifestDefaultEngine) {
    choice = { engine: request.manifestDefaultEngine, reasonCode: "manifest_default", origin: "manifest_default" };
  } else {
    const fallback = table ?? "hyperframes";
    choice = { engine: fallback, reasonCode: "table_default", origin: "table_default" };
  }

  const missing = unconfirmedRequirements(recordFor(matrix, choice.engine), scene);
  if (missing.length === 0) {
    return {
      sceneId: scene.sceneId,
      engine: choice.engine,
      reasonCode: choice.reasonCode,
      reason: `Scene kind ${scene.kind} routed to ${choice.engine} (${choice.reasonCode}).`,
    };
  }

  // The preferred engine cannot confirm a required capability. An explicit
  // or manifest choice is never overridden silently, so it fails here. A
  // table default may yield to the other production engine only when that
  // engine confirms every requirement (the Section 3.2 chart row states the
  // same contract in reverse), and the substitution is recorded.
  if (choice.origin !== "table_default") {
    throw capabilityError(scene, choice.engine, missing);
  }
  const other: ProductionEngine = choice.engine === "hyperframes" ? "remotion" : "hyperframes";
  const otherMissing = unconfirmedRequirements(recordFor(matrix, other), scene);
  if (otherMissing.length === 0) {
    return {
      sceneId: scene.sceneId,
      engine: other,
      reasonCode: "capability_confirmed",
      reason:
        `Table default ${choice.engine} cannot confirm ${missing.join(", ")}; ` +
        `${other} confirms every requirement, so the scene routes there.`,
    };
  }
  throw capabilityError(scene, choice.engine, missing);
}

/**
 * Route every scene in a program. Returns a RoutingDecision with one
 * assignment per scene, or a RoutingFailure carrying a structured
 * AdapterError (exit class 3). Pure: no I/O, no clock.
 */
export function route(request: RoutingRequest, matrix: CapabilityMatrix): RoutingResult {
  try {
    if (request.scenes.length === 0) {
      throw new AdapterError({
        category: "MG_CAPABILITY_MISSING",
        message: "Routing request contains no scenes.",
      });
    }
    const assignments = request.scenes.map((scene) => routeScene(scene, request, matrix));
    const primaryEngine = assignments[0].engine;
    return {
      kind: "routed",
      assignments,
      primaryEngine,
      assemblyOwner: primaryEngine,
    };
  } catch (err) {
    if (err instanceof AdapterError) return { kind: "error", error: err };
    throw err;
  }
}

/** Route, or throw the structured AdapterError. */
export function routeOrThrow(request: RoutingRequest, matrix: CapabilityMatrix): RoutingDecision {
  const result = route(request, matrix);
  if (result.kind === "error") throw result.error;
  return result;
}
