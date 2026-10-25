/**
 * Load a real, checked-in advisor pack from the owning installed skill tree.
 *
 * Only the explicit nine approved seat IDs may be resolved. Pack files must
 * exist inside the canonical advisors tree AND match that installation's
 * manifest checksums. Shared prompts never expose private_scope sources.
 * This is source loading, not independent source-quality qualification:
 * WER-013 must still verify the substantive references and claims.
 */
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { SEAT_IDS, type SeatId } from '../contracts/index.js';
import { validateAdvisorPack } from '../sources/packs.js';
import { CouncilError } from './errors.js';

const REQUIRED_FILES = [
  'profile.json', 'briefing.md', 'frameworks.json',
  'decision-rules.json', 'failure-patterns.json',
  'questions.json', 'communication.md', 'sources.json',
  'coverage.json', 'evals.json',
] as const;
const MAX_CONTEXT_CHARS = 20000;
const MAX_EVIDENCE_PER_WORK = 4;
const MAX_EVIDENCE_TOTAL = 20;
const STRUCTURED_SECTION_CHARS = 2500;
const approvedSeats = new Set<string>(SEAT_IDS);

type JsonObject = Record<string, unknown>;

export interface InstalledSeatPack {
  pack_version: string;
  briefing_text: string;
}

function error(message: string): never {
  throw new CouncilError('COUNCIL_STORE_UNAVAILABLE', message, {
    retryable: false,
    exitCode: 3,
    action: 'Restore or reinstall the Council advisor pack from the verified Skill 77 source before starting a Council run.',
  });
}

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseObject(text: string, rel: string): JsonObject {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    error(`Installed Council advisor file is not valid JSON: ${rel}`);
  }
  if (!isObject(parsed)) error(`Installed Council advisor JSON is not an object: ${rel}`);
  return parsed;
}

function string(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function manifestHashes(skillRoot: string): Map<string, string> {
  let manifestText: string;
  try {
    manifestText = readFileSync(join(skillRoot, 'manifest.json'), 'utf8');
  } catch {
    error('Installed Council source manifest is missing.');
  }
  const manifest = parseObject(manifestText, 'manifest.json');
  if (manifest.skill !== 'council-of-wise-elders' || !Array.isArray(manifest.files)) {
    error('Installed Council source manifest does not describe Skill 77 files.');
  }
  const hashes = new Map<string, string>();
  for (const raw of manifest.files) {
    if (!isObject(raw)) continue;
    const path = string(raw.path);
    const hash = string(raw.sha256);
    if (path && hash && /^[a-f0-9]{64}$/i.test(hash)) hashes.set(path, hash.toLowerCase());
  }
  return hashes;
}

function checkedFile(
  skillRoot: string,
  advisorRoot: string,
  relativePath: string,
  hashes: ReadonlyMap<string, string>,
): string {
  const expected = hashes.get(relativePath);
  if (!expected) error(`Advisor asset is absent from installed manifest: ${relativePath}`);
  const full = resolve(skillRoot, relativePath);
  let real: string;
  try {
    real = realpathSync(full);
    if (!(real === advisorRoot || real.startsWith(advisorRoot + sep)) || !statSync(real).isFile()) {
      error(`Advisor asset resolves outside the installed advisors tree: ${relativePath}`);
    }
  } catch (cause) {
    if (cause instanceof CouncilError) throw cause;
    error(`Advisor asset is missing or inaccessible: ${relativePath}`);
  }
  const bytes = readFileSync(real);
  const digest = createHash('sha256').update(bytes).digest('hex');
  if (digest !== expected) error(`Advisor asset checksum disagrees with the installed manifest: ${relativePath}`);
  return bytes.toString('utf8');
}

/** Do not inject private-scope commentary into shared advisor prompts. */
function sharedOnlyBriefing(text: string): string {
  return text.split(/\n\n+/)
    .filter((paragraph) => !/user_private|private_scope|private-scope/i.test(paragraph))
    .join('\n\n');
}

function sharedEvidenceLines(sources: JsonObject): string[] {
  const lines: string[] = [];
  let included = 0;
  for (const raw of Array.isArray(sources.records) ? sources.records : []) {
    if (!isObject(raw) || raw.allowed_scope !== 'shared_pack') continue;
    const title = string(raw.work_title);
    const sourceId = string(raw.source_id);
    if (!title || !sourceId) continue;
    const entries = Array.isArray(raw.evidence) ? raw.evidence : [];
    let inWork = 0;
    for (const item of entries) {
      if (!isObject(item) || item.kind !== 'concept' || item.mark !== 'paraphrase') continue;
      const paraphrase = string(item.paraphrase);
      const id = string(item.evidence_id);
      const locator = isObject(item.locator) ? string(item.locator.value) : null;
      if (!paraphrase || !id || !locator) continue;
      const quality = string(raw.quality) ?? 'unverified';
      lines.push(`- ${title} [${sourceId}; ${id}; ${locator}; quality=${quality}]: ${paraphrase.slice(0, 650)}`);
      included += 1;
      inWork += 1;
      if (included >= MAX_EVIDENCE_TOTAL || inWork >= MAX_EVIDENCE_PER_WORK) break;
    }
    if (included >= MAX_EVIDENCE_TOTAL) break;
  }
  return lines;
}

/** Bounded excerpts of existing shared material, with its original attribution. */
function sharedStructuredContext(document: JsonObject): string {
  const entries: JsonObject[] = [];
  const fields = ['id', 'framework_id', 'name', 'summary', 'concept', 'application', 'description', 'rule', 'applies_when', 'attribution_kind', 'source_evidence_ids'];
  const eligible = (Array.isArray(document.items) ? document.items : []).filter(
    (item): item is JsonObject => isObject(item) &&
      (!('scope' in item) || item.scope === 'shared_pack') &&
      item.distribution_ready !== false && !('private_evidence_refs' in item),
  );
  for (const item of eligible) {
    const excerpt = Object.fromEntries(fields.filter((key) => key in item).map((key) => [key, item[key]]));
    if (JSON.stringify([...entries, excerpt]).length > STRUCTURED_SECTION_CHARS - 100) break;
    entries.push(excerpt);
  }
  return JSON.stringify({ items: entries, omitted_for_context_budget: eligible.length - entries.length });
}

export function loadInstalledSeatPack(skillRoot: string, seatId: SeatId): InstalledSeatPack {
  if (!approvedSeats.has(seatId)) error(`Unsupported Council advisor seat: ${seatId}`);
  let skillReal: string;
  let advisorsReal: string;
  try {
    skillReal = realpathSync(skillRoot);
    advisorsReal = realpathSync(join(skillReal, 'advisors'));
  } catch {
    error('Council skill/advisors directory is missing from the installed runtime.');
  }
  const hashes = manifestHashes(skillReal);
  const sourceFiles = new Map<string, string>();
  for (const file of REQUIRED_FILES) {
    const rel = `advisors/${seatId}/${file}`;
    sourceFiles.set(file, checkedFile(skillReal, advisorsReal, rel, hashes));
  }
  const json = (name: string) => parseObject(sourceFiles.get(name)!, `advisors/${seatId}/${name}`);
  const profile = json('profile.json');
  const sources = json('sources.json');
  const coverage = json('coverage.json');
  const frameworks = json('frameworks.json');
  const decisionRules = json('decision-rules.json');
  const failurePatterns = json('failure-patterns.json');
  const questions = json('questions.json');
  const evals = json('evals.json');
  const briefing = sourceFiles.get('briefing.md')!;
  const communication = sourceFiles.get('communication.md')!;
  if (profile.seat_id !== seatId || sources.seat_id !== seatId) {
    error(`Advisor pack identity mismatch: expected ${seatId}`);
  }
  const verification = validateAdvisorPack({
    folder: seatId,
    profile,
    sources,
    coverage,
    frameworks,
    decisionRules,
    failurePatterns,
    questions,
    evals,
    markdownTexts: [briefing, communication],
  });
  if (!verification.valid) {
    error(`Advisor pack ${seatId} fails structural/source integrity validation: ${verification.diagnostics.filter((d) => d.severity === 'error').map((d) => d.code).join(', ')}`);
  }
  const baseVersion = string(profile.pack_version);
  if (!baseVersion) error(`Advisor pack ${seatId} has no pack_version`);

  const hash = createHash('sha256');
  for (const file of REQUIRED_FILES) {
    hash.update(`${file}\n`).update(sourceFiles.get(file)!).update('\n');
  }
  const version = `${baseVersion}+sha256.${hash.digest('hex').slice(0, 16)}`;
  const sections = [
    `Council advisor: ${string(profile.name) ?? seatId}; seat_id=${seatId}; pack_identity=${version}`,
    'Attribution: AI perspective inspired by published work, not the real individual or an endorsement.',
    `Source qualification (coverage gate): ${string(coverage.qualification) ?? 'unverified'}. Existing Skill 22 derivatives may be preserved and referenced, but bibliographic/quality-unverified materials do NOT establish verified quotations or full-work coverage.`,
    'ADVISOR BRIEFING (installed source):\n' + sharedOnlyBriefing(briefing),
    'COMMUNICATION RULES (installed source):\n' + communication,
    'TRACEABLE, PARAPHRASE-ONLY SOURCE REFERENCES (not certified against original works):\n' + (sharedEvidenceLines(sources).join('\n') || 'No qualified shared-source paraphrase records are available.'),
  ];
  let combined = '';
  for (const section of sections) {
    const candidate = combined ? combined + '\n\n' + section : section;
    if (candidate.length > MAX_CONTEXT_CHARS - 2 * STRUCTURED_SECTION_CHARS - 100) {
      if (!combined) error(`Advisor briefing for ${seatId} exceeds the bounded context allowance`);
      break;
    }
    combined = candidate;
  }
  combined += '\n\nSHARED FRAMEWORK EXCERPTS (existing pack; attribution unchanged):\n' + sharedStructuredContext(frameworks);
  combined += '\n\nSHARED DECISION RULE EXCERPTS (existing pack; attribution unchanged):\n' + sharedStructuredContext(decisionRules);
  return { pack_version: version, briefing_text: combined };
}
