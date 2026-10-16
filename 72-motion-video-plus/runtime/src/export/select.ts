// Capability selection for export profiles (MG-040): the gate that
// runs BEFORE any authoring or rendering. A job requesting alpha is
// routed to a route that can actually deliver measured alpha, or
// selection fails by name (MG_CAPABILITY_UNSUPPORTED, Section 16.9
// exit class 3) before a single frame is rendered.
//
// Two independent confirmations can qualify a route:
// - the capability matrix (references/renderer-capabilities.json),
//   when an engine's probe record confirms the alpha profile and its
//   codec for that engine; this confirms the engine-native route;
// - the live export toolchain probe (probe.ts), which measured the
//   profile's image-sequence encode end to end on this machine; this
//   confirms the image-sequence-plus-encode route for either engine.
// The shipped matrix confirms no alpha profile today (both adapters'
// probes measured launch and stills only, and say so), so alpha jobs
// select the image-sequence route here until an engine probe record
// measures alpha and the matrix is refreshed from it. The default
// opaque profile is the baseline contract: it always selects the
// engine-native route.

import type { CapabilityMatrix } from "../adapters/types";
import {
  ExportError,
  exportProfileById,
  type ExportProfile,
  type ProfileRoute,
  type VideoProfileId,
} from "./profiles";
import type { ExportToolchainProbe } from "./probe";

export interface ExportSelection {
  profile: ExportProfile;
  engine: "hyperframes" | "remotion";
  route: ProfileRoute;
  /** What confirmed the route: "baseline_contract",
   * "capability_matrix", or "export_toolchain_probe". */
  confirmedBy: string;
}

export function selectExportRoute(opts: {
  profileId: string;
  engine: "hyperframes" | "remotion";
  matrix: CapabilityMatrix | null;
  toolchain: ExportToolchainProbe | null;
}): ExportSelection {
  const profile = exportProfileById(opts.profileId);
  const declared = profile.routes[opts.engine];

  if (!profile.alpha) {
    return { profile, engine: opts.engine, route: declared, confirmedBy: "baseline_contract" };
  }

  const record = opts.matrix?.engines.find((e) => e.engine === opts.engine) ?? null;
  const matrixConfirms =
    record !== null &&
    record.probeStatus === "ready" &&
    record.transparency.profiles.includes(profile.id) &&
    record.codecs.includes(profile.streamCodec);
  if (matrixConfirms && declared.kind === "engine_native") {
    return { profile, engine: opts.engine, route: declared, confirmedBy: "capability_matrix" };
  }

  const qualification = opts.toolchain?.profiles[profile.id as VideoProfileId] ?? null;
  if (qualification && qualification.qualified) {
    return {
      profile,
      engine: opts.engine,
      route: {
        kind: "image_sequence_encode",
        detail:
          `Image-sequence-plus-encode route confirmed by the live toolchain probe ` +
          `(${qualification.measuredCodec ?? "unknown codec"}, ` +
          `${qualification.distinctAlphaValues ?? 0} distinct alpha values measured). ` +
          `The engine supplies PNG frames; the export layer encodes with ` +
          `${profile.sequenceEncoder ?? "the profile encoder"}.`,
      },
      confirmedBy: "export_toolchain_probe",
    };
  }

  throw new ExportError({
    category: "MG_CAPABILITY_UNSUPPORTED",
    check: "export.route_qualified",
    message:
      `No qualified route can deliver profile ${profile.id} on engine ${opts.engine}: ` +
      `the capability matrix does not confirm it for that engine` +
      (record
        ? ` (probe status ${record.probeStatus}, transparency profiles ` +
          `[${record.transparency.profiles.join(", ")}], codecs [${record.codecs.join(", ")}])`
        : " (no matrix record)") +
      ` and the export toolchain probe did not qualify its image-sequence encode` +
      (qualification ? ` (${qualification.evidence.join(" ")})` : " (no probe record)") +
      `. Selection fails before any rendering starts.`,
  });
}
