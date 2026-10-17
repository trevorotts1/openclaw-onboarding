/**
 * WER-013 read-only primary-source qualification intake report.
 *
 * Reads all nine installed-source candidates from the canonical checkout.
 * No URL fetches, no model queries, no quote invention and no writes to
 * sources.json/coverage.json. Each missing anchor is named exactly.
 *
 * Usage:
 * node --import tsx scripts/audit-advisor-sources.ts --json
 * node --import tsx scripts/audit-advisor-sources.ts --require-ready
 */
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SEAT_IDS } from '../src/contracts/enums.js';
import { validateAdvisorPack } from '../src/sources/packs.js';
import {
  MIN_APPLICATION_CASES,
  MIN_TRACEABLE_CONCEPTS,
} from '../src/sources/coverage.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const requiredJson = [
  'profile.json', 'sources.json', 'coverage.json',
  'frameworks.json', 'decision-rules.json', 'failure-patterns.json',
  'questions.json', 'evals.json',
] as const;

interface WorkNeed {
  title: string;
  work_key: string;
  work_class: string;
  matched_source_ids: string[];
  verified_concepts: number;
  verified_application_cases: number;
  missing_concepts: number;
  missing_application_cases: number;
  accepted: boolean;
}

function readText(path: string): string {
  return readFileSync(path, { encoding: 'utf8' });
}

function auditSeat(seatId: (typeof SEAT_IDS)[number]) {
  const base = join(root, 'advisors', seatId);
  const jsonFiles: Record<string, Record<string, unknown>> = {};
  for (const name of requiredJson) {
    const data: unknown = JSON.parse(readText(join(base, name)));
    if (data === null || typeof data !== 'object' || Array.isArray(data)) {
      throw new Error(`Invalid advisor JSON object: ${seatId}/${name}`);
    }
    jsonFiles[name] = data as Record<string, unknown>;
  }
  const result = validateAdvisorPack({
    folder: seatId,
    profile: jsonFiles['profile.json'],
    sources: jsonFiles['sources.json'],
    coverage: jsonFiles['coverage.json'],
    frameworks: jsonFiles['frameworks.json'],
    decisionRules: jsonFiles['decision-rules.json'],
    failurePatterns: jsonFiles['failure-patterns.json'],
    questions: jsonFiles['questions.json'],
    evals: jsonFiles['evals.json'],
    markdownTexts: [readText(join(base, 'briefing.md')), readText(join(base, 'communication.md'))],
  });
  const works: WorkNeed[] = result.works.map((work) => ({
    title: work.title,
    work_key: work.work_key,
    work_class: work.work_class,
    matched_source_ids: work.matched_source_ids,
    verified_concepts: work.traceable_concepts,
    verified_application_cases: work.application_cases,
    missing_concepts: Math.max(0, MIN_TRACEABLE_CONCEPTS - work.traceable_concepts),
    missing_application_cases: Math.max(0, MIN_APPLICATION_CASES - work.application_cases),
    accepted: work.gate_met,
  }));
  return {
    seat_id: seatId,
    structure_valid: result.valid,
    qualification: result.qualification,
    requirements_met: works.every((work) => work.accepted),
    works,
    diagnostics: result.diagnostics.map((d) => ({
      severity: d.severity, code: d.code, path: d.path ?? null,
    })),
  };
}

function run() {
  const requireReady = process.argv.includes('--require-ready');
  const asJson = process.argv.includes('--json');
  const seats = SEAT_IDS.map(auditSeat);
  const works = seats.flatMap((seat) => seat.works);
  const summary = {
    schema: 'wise-elders.source-audit/v1',
    required_seats: SEAT_IDS.length,
    structurally_valid_seats: seats.filter((seat) => seat.structure_valid).length,
    ready_seats: seats.filter((seat) => seat.structure_valid && seat.requirements_met).length,
    required_work_anchors: works.length,
    accepted_work_anchors: works.filter((work) => work.accepted).length,
    unaccepted_work_anchors: works.filter((work) => !work.accepted).length,
    total_missing_traceable_concepts: works.reduce((n, work) => n + work.missing_concepts, 0),
    total_missing_application_cases: works.reduce((n, work) => n + work.missing_application_cases, 0),
    source_quality_gate_met: seats.every((seat) => seat.structure_valid && seat.requirements_met),
    note: 'Counts are validated provenance-qualified locators, not bibliographic references, screenshots, AI inventions or proof of a full book.',
  };
  if (asJson) {
    process.stdout.write(JSON.stringify({ summary, seats }, null, 2) + '\n');
  } else {
    process.stdout.write(`WER-013: ${summary.accepted_work_anchors}/${summary.required_work_anchors} foundation anchors verified; ${summary.ready_seats}/${summary.required_seats} seats source-ready.\n`);
    for (const seat of seats) {
      process.stdout.write(`  ${seat.seat_id} [${seat.qualification ?? 'unavailable'}]: ${seat.works.filter((work) => work.accepted).length}/${seat.works.length} anchors\n`);
      for (const work of seat.works.filter((work) => !work.accepted)) {
        process.stdout.write(`    ${work.title}: requires +${work.missing_concepts} verified concepts, +${work.missing_application_cases} author-grounded application cases\n`);
      }
    }
  }
  if (seats.some((seat) => !seat.structure_valid)) {
    process.stderr.write('WER-013 FAIL: structural validation errors in source packs.\n');
    process.exitCode = 2;
  } else if (requireReady && !summary.source_quality_gate_met) {
    process.stderr.write('WER-013 NOT READY: source qualification remains below required minimum.\n');
    process.exitCode = 1;
  }
}

run();
