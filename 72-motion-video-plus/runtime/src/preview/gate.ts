// The full-fps motion gate (Directive MG-024 acceptance: "layout-
// approved 15 fps evidence cannot satisfy the full-fps motion gate").
//
// A review gate that judges MOTION (timing, easing, synchronization)
// must be fed evidence rendered at the final's frame rate with the
// final's aspect ratio. This check reads only the preview's review
// record: it refuses rough-layout records by label, refuses any record
// whose preview fps differs from the final fps even if the label was
// lost, and refuses aspect changes. A scaled full-fps preview passes:
// spatial resolution is the one thing a preview is allowed to reduce.

import type { PreviewReviewRecord } from "./types";

export interface PreviewGateFinding {
  code: string;
  message: string;
}

export interface PreviewGateVerdict {
  accepted: boolean;
  findings: PreviewGateFinding[];
}

export const PREVIEW_GATE_ROUGH_LAYOUT = "MG_PREVIEW_ROUGH_LAYOUT_ONLY";
export const PREVIEW_GATE_FPS_MISMATCH = "MG_PREVIEW_FPS_MISMATCH";
export const PREVIEW_GATE_ASPECT_MISMATCH = "MG_PREVIEW_ASPECT_MISMATCH";

export function checkPreviewMotionGate(record: PreviewReviewRecord): PreviewGateVerdict {
  const findings: PreviewGateFinding[] = [];
  if (record.roughLayoutOnly || record.label === "rough_layout_only") {
    findings.push({
      code: PREVIEW_GATE_ROUGH_LAYOUT,
      message:
        `Preview for job ${record.jobId} is labeled rough_layout_only: it was rendered ` +
        `at ${record.preview.fps} fps for layout review and cannot satisfy the ` +
        `full-fps motion gate (final fps ${record.final.fps}).`,
    });
  }
  if (record.preview.fps !== record.final.fps) {
    findings.push({
      code: PREVIEW_GATE_FPS_MISMATCH,
      message:
        `Preview for job ${record.jobId} runs at ${record.preview.fps} fps but the ` +
        `final runs at ${record.final.fps} fps; motion evidence must be full-fps.`,
    });
  }
  const finalAspect = record.final.width / record.final.height;
  const previewAspect = record.preview.width / record.preview.height;
  if (Math.abs(previewAspect - finalAspect) > 0.01) {
    findings.push({
      code: PREVIEW_GATE_ASPECT_MISMATCH,
      message:
        `Preview for job ${record.jobId} has aspect ${record.preview.width}x` +
        `${record.preview.height}, which does not preserve the final's aspect ` +
        `${record.final.width}x${record.final.height}.`,
    });
  }
  return { accepted: findings.length === 0, findings };
}
