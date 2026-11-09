#!/usr/bin/env npx tsx
/**
 * scripts/stage-receipts-report.ts — claim-gate style READ-ONLY reporter for
 * six-stage distribution receipts. The consumer half of src/lib/
 * stage-receipts.ts: prints one line per (slug, stage) — BEHIND/UNKNOWN per
 * axis, never conflated — plus the fail-closed roll-up, in the same
 * read-only posture as check-updates.sh and the fleet-status.sh lineage.
 *
 * Input: a JSON file of per-slug measurements:
 *   {
 *     "<slug>": { "<stage>": { "ok": true, "evidence": "..." } | null }
 *   }
 * Stages may be omitted (unmeasured → UNKNOWN). See StageMeasurements in
 * src/lib/stage-receipts.ts for the measurement shape.
 *
 * Usage:
 *   npx tsx scripts/stage-receipts-report.ts <measurements.json>
 *
 * Exit codes: 0 report printed; 2 usage or parse error. Read-only — writes
 * nothing.
 */

import fs from 'node:fs';
import process from 'node:process';

import {
  buildStageRows,
  projectStageRows,
  rollUpStatus,
  type StageMeasurements,
} from '../src/lib/stage-receipts';

function main(): number {
  const file = process.argv[2];
  if (!file || process.argv.includes('-h') || process.argv.includes('--help')) {
    console.error('usage: npx tsx scripts/stage-receipts-report.ts <measurements.json>');
    return 2;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    console.error(`cannot read measurements JSON: ${(err as Error).message}`);
    return 2;
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    console.error('measurements JSON must be an object keyed by slug');
    return 2;
  }

  const measuredUtc = new Date().toISOString();
  for (const [slug, measurements] of Object.entries(parsed as Record<string, StageMeasurements>)) {
    const rows = buildStageRows(measurements ?? {});
    for (const r of projectStageRows(slug, rows, measuredUtc)) {
      const ev = r.evidence === null ? '-' : r.evidence;
      console.log(
        `${slug} ${r.stage}: ${r.status}  evidence_type=${r.evidence_type} evidence=${ev}${r.note ? `  ${r.note}` : ''}`
      );
    }
    console.log(`${slug} overall: ${rollUpStatus(rows)}`);
  }
  return 0;
}

process.exit(main());
