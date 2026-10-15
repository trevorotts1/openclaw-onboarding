// Packaging metadata for exports (MG-040): the record that travels
// with a delivered artifact and states its profile, its measured
// codec, and its measured alpha verdict. The record is BUILT from
// measurement (verify.ts) and can be re-checked against the artifact
// at any time; a record that claims alpha for an opaque encode, or
// the wrong codec for the artifact on disk, fails named checks in
// verifyExportRecord instead of passing silently.
//
// Truth rules enforced here:
// - An alpha profile over an artifact with no alpha channel throws
//   MG_QC_FAILED (check export.alpha_channel_present) and produces
//   no record: the mislabel is impossible, not merely discouraged.
// - An opaque profile over an artifact WITH an alpha channel throws
//   the mirror check (export.alpha_unexpected).
// - The verdict is derived from the measurement only. Content that
//   paints an opaque background into an alpha stream records
//   "alpha_opaque_content", never "verified_alpha".

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import {
  ExportError,
  INTERMEDIATE_POLICY,
  exportProfileById,
  type ExportProfile,
} from "./profiles";
import {
  measureAlpha,
  probeVideoDetailed,
  verdictFromMeasurement,
  type AlphaMeasurement,
  type AlphaVerdict,
} from "./verify";

export interface ExportRecord {
  schemaVersion: "1.0";
  kind: "export-record";
  /** The delivery profile the artifact was produced for. */
  profile: string;
  /** The route that produced it. */
  route: { engine: string; kind: string; detail: string };
  /** Logical artifact path (as recorded in render evidence). */
  artifactPath: string;
  artifactSha256: string;
  /** Measured stream facts, from ffprobe on the artifact itself. */
  stream: {
    codec: string;
    pixelFormat: string;
    width: number;
    height: number;
    frameCount: number;
    fpsNumerator: number;
    fpsDenominator: number;
  };
  alpha: {
    channelPresent: boolean;
    verdict: AlphaVerdict;
    measurement: AlphaMeasurement;
  };
  intermediatePolicy: string;
  generatedAt: string;
}

function sha256File(absPath: string): string {
  return createHash("sha256").update(readFileSync(absPath)).digest("hex");
}

/** Build the packaging record for one artifact by measuring it.
 * Throws ExportError (MG_QC_FAILED) when the artifact contradicts
 * the profile it would be labeled with. */
export function buildExportRecord(opts: {
  profile: ExportProfile;
  route: { engine: string; kind: string; detail: string };
  artifactAbsPath: string;
  artifactLogicalPath: string;
  /** Frames to measure alpha on; defaults to the first and middle
   * frames. */
  framesToMeasure?: number[];
}): ExportRecord {
  const probe = probeVideoDetailed(opts.artifactAbsPath);
  if (opts.profile.alpha && !probe.alphaChannelPresent) {
    throw new ExportError({
      category: "MG_QC_FAILED",
      check: "export.alpha_channel_present",
      message:
        `Artifact ${opts.artifactAbsPath} carries no alpha channel (codec ${probe.codecName}, ` +
        `pixel format ${probe.pixelFormat}) but would be labeled with alpha profile ` +
        `${opts.profile.id}. Refusing to write the record.`,
    });
  }
  if (!opts.profile.alpha && probe.alphaChannelPresent) {
    throw new ExportError({
      category: "MG_QC_FAILED",
      check: "export.alpha_unexpected",
      message:
        `Artifact ${opts.artifactAbsPath} carries an alpha channel (codec ${probe.codecName}, ` +
        `pixel format ${probe.pixelFormat}) but would be labeled with opaque profile ` +
        `${opts.profile.id}. Refusing to write the record.`,
    });
  }
  const framesToMeasure =
    opts.framesToMeasure ??
    (probe.frameCount > 1 ? [0, Math.floor(probe.frameCount / 2)] : [0]);
  const measurement = measureAlpha(opts.artifactAbsPath, probe, framesToMeasure);
  const verdict = verdictFromMeasurement(probe, measurement);
  return {
    schemaVersion: "1.0",
    kind: "export-record",
    profile: opts.profile.id,
    route: opts.route,
    artifactPath: opts.artifactLogicalPath,
    artifactSha256: sha256File(opts.artifactAbsPath),
    stream: {
      codec: probe.codecName,
      pixelFormat: probe.pixelFormat,
      width: probe.width,
      height: probe.height,
      frameCount: probe.frameCount,
      fpsNumerator: probe.fpsNumerator,
      fpsDenominator: probe.fpsDenominator,
    },
    alpha: {
      channelPresent: probe.alphaChannelPresent,
      verdict,
      measurement,
    },
    intermediatePolicy: INTERMEDIATE_POLICY.id,
    generatedAt: new Date().toISOString(),
  };
}

/** Write the record as a JSON sidecar; returns the sidecar path. */
export function writeExportRecordSidecar(record: ExportRecord, sidecarAbsPath: string): string {
  writeFileSync(sidecarAbsPath, JSON.stringify(record, null, 2) + "\n", "utf8");
  return sidecarAbsPath;
}

export interface ExportRecordFinding {
  check: string;
  ok: boolean;
  detail: string;
}

/** Re-check a record against the artifact on disk. Every claim in
 * the record is re-measured; findings name the stable check that
 * failed so a forged or stale record is caught by name:
 * export.label_match (profile vs measured codec and pixel format),
 * export.alpha_verdict_match (recorded verdict vs re-measured
 * verdict), export.artifact_hash (recorded hash vs the file). */
export function verifyExportRecord(
  record: ExportRecord,
  artifactAbsPath: string
): ExportRecordFinding[] {
  const findings: ExportRecordFinding[] = [];
  let profile: ExportProfile | null = null;
  try {
    profile = exportProfileById(record.profile);
    findings.push({ check: "export.profile_known", ok: true, detail: `profile ${record.profile}` });
  } catch {
    findings.push({
      check: "export.profile_known",
      ok: false,
      detail: `record names unknown profile "${record.profile}"`,
    });
  }

  const actualHash = sha256File(artifactAbsPath);
  findings.push({
    check: "export.artifact_hash",
    ok: actualHash === record.artifactSha256,
    detail:
      actualHash === record.artifactSha256
        ? "artifact hash matches the record"
        : `artifact hash ${actualHash} differs from the recorded ${record.artifactSha256}`,
  });

  const probe = probeVideoDetailed(artifactAbsPath);
  const labelOk =
    profile !== null &&
    probe.codecName === profile.streamCodec &&
    probe.codecName === record.stream.codec &&
    probe.pixelFormat.startsWith(profile.streamPixelFormatPrefix) &&
    probe.pixelFormat === record.stream.pixelFormat;
  findings.push({
    check: "export.label_match",
    ok: labelOk,
    detail: labelOk
      ? `artifact probes as ${probe.codecName}/${probe.pixelFormat}, matching profile ${record.profile}`
      : `record labels the artifact ${record.stream.codec}/${record.stream.pixelFormat} for profile ` +
        `${record.profile}, but the artifact probes as ${probe.codecName}/${probe.pixelFormat}` +
        (profile ? ` and the profile requires codec ${profile.streamCodec}` : ""),
  });

  const frames =
    record.alpha.measurement.framesMeasured.length > 0
      ? record.alpha.measurement.framesMeasured
      : [0];
  const measurement = measureAlpha(artifactAbsPath, probe, frames);
  const verdict = verdictFromMeasurement(probe, measurement);
  const verdictMatches = verdict === record.alpha.verdict;
  const channelMatches = probe.alphaChannelPresent === record.alpha.channelPresent;
  const profileConsistent = profile === null || profile.alpha === probe.alphaChannelPresent;
  findings.push({
    check: "export.alpha_verdict_match",
    ok: verdictMatches && channelMatches && profileConsistent,
    detail: !verdictMatches
      ? `record claims verdict ${record.alpha.verdict} but the artifact measures ${verdict}`
      : !channelMatches
        ? `record claims channelPresent ${record.alpha.channelPresent} but the artifact probes ` +
          `channelPresent ${probe.alphaChannelPresent}`
        : !profileConsistent
          ? `record's profile ${record.profile} (alpha ${profile?.alpha}) contradicts the ` +
            `artifact's measured channel presence ${probe.alphaChannelPresent}`
          : `re-measured verdict ${verdict} matches the record`,
  });
  return findings;
}
