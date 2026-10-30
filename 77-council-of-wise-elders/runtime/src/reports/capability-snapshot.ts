/**
 * CTR-146: the installation capability snapshot for the reader-facing
 * "Your installed tools" section of a council report.
 *
 * What this module is allowed to read, and nothing else:
 * - `<openclaw root>/skills/<folder>/SKILL.md` — the YAML frontmatter
 *   `name` and `description` only (first 12 KB of the file);
 * - `<openclaw root>/skills/<folder>` existence — a folder without a
 *   SKILL.md is not a skill;
 * - `<openclaw root>/agents/dept-*` — the folder name only, and only
 *   when it looks operational (it carries `models.json` or an `agent/`
 *   directory). A bare or template directory is not a department;
 * - optionally `<claude root>/skills/<folder>/SKILL.md` frontmatter.
 *
 * It never reads or renders prompts, instructions, private memory,
 * credentials, databases, or configuration values. It never executes a
 * skill. It never reads another box (no network, no remote host).
 *
 * The snapshot is validated again at the report trust boundary so a
 * caller-supplied inventory cannot grow into a catalog dump or smuggle
 * a different installation's list into a client export. Matching to the
 * plan is exact work only (CTR-151): an exact recorded reference on the
 * action proposal, or the step naming the capability's exact name or id.
 * Shared vocabulary is not a match basis, so a backup skill is never
 * suggested for a video step. A match is labelled optional assistance,
 * never a promise that a tool can execute a step.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

export const CAPABILITY_SNAPSHOT_SCHEMA = 'wise-elders.capability-snapshot/v1' as const;

export const CAPABILITY_SNAPSHOT_LIMITS = {
  max_items: 120,
  max_name: 90,
  max_description: 320,
  max_id: 140,
  max_reference_ids: 24,
  max_limitations: 24,
  max_limitation_text: 400,
  max_matched_steps: 6,
} as const;

export type CapabilityKind = 'skill' | 'department';
export type CapabilityAvailability = 'available_now' | 'available_at_sitting';
export type CapabilitySource =
  | 'openclaw.skills'
  | 'openclaw.departments'
  | 'claude.skills';

export interface InstallationCapabilityEntry {
  /** Stable bounded id: `skill:<slug>` or `department:<folder>`. */
  capability_id: string;
  kind: CapabilityKind;
  name: string;
  description: string | null;
  availability: CapabilityAvailability;
  source: CapabilitySource;
  /** Recorded plan references that name this capability, when any. */
  recorded_reference_ids: string[];
}

export interface InstallationCapabilitySnapshot {
  schema_version: typeof CAPABILITY_SNAPSHOT_SCHEMA;
  /**
   * The installation the inventory was read from. The report refuses a
   * snapshot whose installation does not match the session's own.
   */
  installation_id: string;
  /** `YYYY-MM-DD` (sitting date or export date). */
  captured_at: string;
  /**
   * `at_sitting` when a snapshot captured at convene time is supplied;
   * `at_export` when the box was inspected while building this report.
   */
  basis: 'at_sitting' | 'at_export';
  items: InstallationCapabilityEntry[];
  limitations: string[];
}

export class CapabilitySnapshotError extends Error {
  readonly code:
    | 'CAPABILITY_SNAPSHOT_INVALID'
    | 'CAPABILITY_SNAPSHOT_MISMATCH'
    | 'CAPABILITY_SNAPSHOT_TOO_LARGE';

  constructor(code: CapabilitySnapshotError['code'], message: string) {
    super(message);
    this.name = 'CapabilitySnapshotError';
    this.code = code;
  }
}

const CONTROL_CHARS = /[\u0000-\u001f\u007f]/g;

/**
 * A word left dangling by a cut, removed so a reader never sees "... and a".
 * These are function words only: no content word is ever removed after the
 * cut, so the meaning of the kept text does not change.
 */
const TRAILING_FUNCTION_WORDS =
  /\s+(?:and|or|but|nor|to|of|for|with|from|by|in|on|at|as|the|a|an|is|are|was|were|be|been)$/i;

/**
 * Collapse and bound a string for DISPLAY only; the frontmatter source is
 * never modified. A cut lands on a word boundary whenever the text has one
 * near the limit, trailing function words are dropped, and an ellipsis marks
 * the cut, so a reader never sees a half word such as "publishin" or a
 * dangling "and a".
 */
function cleanText(value: string, max: number): string {
  const collapsed = value.replace(CONTROL_CHARS, ' ').replace(/\s+/g, ' ').trim();
  if (collapsed.length <= max) return collapsed;
  // Reserve one character for the ellipsis so the result never exceeds max.
  const budget = Math.max(1, max - 1);
  const sliced = collapsed.slice(0, budget);
  const boundary = Math.max(
    sliced.lastIndexOf(' '),
    sliced.lastIndexOf(','),
    sliced.lastIndexOf(';'),
  );
  let cut = boundary >= Math.floor(budget * 0.6) ? sliced.slice(0, boundary) : sliced;
  cut = cut.replace(/[\s,;]+$/, '');
  let previous = '';
  while (previous !== cut) {
    previous = cut;
    cut = cut.replace(TRAILING_FUNCTION_WORDS, '');
  }
  cut = cut.replace(/[\s,;]+$/, '');
  const trimmedFallback = sliced.trimEnd();
  if (trimmedFallback === '') return '…';
  const marked = cut === '' ? trimmedFallback : cut;
  return marked.endsWith('…') ? marked : `${marked}…`;
}

function nonEmptyString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      `capability snapshot ${field} must be a non-empty string`,
    );
  }
  return value;
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Strict validation at the report boundary. Unknown fields are rejected,
 * every string is bounded, and the item count is capped so a catalog
 * dump can never ride into a client report.
 */
export function validateCapabilitySnapshot(
  value: unknown,
): InstallationCapabilitySnapshot {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      'capability snapshot must be an object',
    );
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set([
    'schema_version',
    'installation_id',
    'captured_at',
    'basis',
    'items',
    'limitations',
  ]);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot carries an unknown field: ${key}`,
      );
    }
  }
  if (record.schema_version !== CAPABILITY_SNAPSHOT_SCHEMA) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      `capability snapshot schema_version must be ${CAPABILITY_SNAPSHOT_SCHEMA}`,
    );
  }
  const installationId = cleanText(
    nonEmptyString(record.installation_id, 'installation_id'),
    200,
  );
  const capturedAt = nonEmptyString(record.captured_at, 'captured_at');
  if (!DATE_RE.test(capturedAt)) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      'capability snapshot captured_at must be YYYY-MM-DD',
    );
  }
  if (record.basis !== 'at_sitting' && record.basis !== 'at_export') {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      'capability snapshot basis must be at_sitting or at_export',
    );
  }
  if (!Array.isArray(record.items)) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      'capability snapshot items must be an array',
    );
  }
  if (record.items.length > CAPABILITY_SNAPSHOT_LIMITS.max_items) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_TOO_LARGE',
      `capability snapshot carries ${record.items.length} items; the report limit is ${CAPABILITY_SNAPSHOT_LIMITS.max_items}`,
    );
  }
  const seen = new Set<string>();
  const items: InstallationCapabilityEntry[] = record.items.map((raw, index) => {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}] must be an object`,
      );
    }
    const item = raw as Record<string, unknown>;
    const itemAllowed = new Set([
      'capability_id',
      'kind',
      'name',
      'description',
      'availability',
      'source',
      'recorded_reference_ids',
    ]);
    for (const key of Object.keys(item)) {
      if (!itemAllowed.has(key)) {
        throw new CapabilitySnapshotError(
          'CAPABILITY_SNAPSHOT_INVALID',
          `capability snapshot items[${index}] carries an unknown field: ${key}`,
        );
      }
    }
    const capabilityId = cleanText(
      nonEmptyString(item.capability_id, `items[${index}].capability_id`),
      CAPABILITY_SNAPSHOT_LIMITS.max_id,
    );
    if (!/^(skill|department):[a-z0-9][a-z0-9._-]*$/.test(capabilityId)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}].capability_id must be skill:<slug> or department:<slug>`,
      );
    }
    if (seen.has(capabilityId)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot repeats capability_id ${capabilityId}`,
      );
    }
    seen.add(capabilityId);
    if (item.kind !== 'skill' && item.kind !== 'department') {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}].kind must be skill or department`,
      );
    }
    if (capabilityId.split(':')[0] !== item.kind) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}] kind does not match its capability_id`,
      );
    }
    const name = cleanText(
      nonEmptyString(item.name, `items[${index}].name`),
      CAPABILITY_SNAPSHOT_LIMITS.max_name,
    );
    let description: string | null = null;
    if (item.description !== null && item.description !== undefined) {
      if (typeof item.description !== 'string') {
        throw new CapabilitySnapshotError(
          'CAPABILITY_SNAPSHOT_INVALID',
          `capability snapshot items[${index}].description must be a string or null`,
        );
      }
      const cleaned = cleanText(
        item.description,
        CAPABILITY_SNAPSHOT_LIMITS.max_description,
      );
      description = cleaned === '' ? null : cleaned;
    }
    if (
      item.availability !== 'available_now' &&
      item.availability !== 'available_at_sitting'
    ) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}].availability is not recognised`,
      );
    }
    const sources: readonly CapabilitySource[] = [
      'openclaw.skills',
      'openclaw.departments',
      'claude.skills',
    ];
    if (!sources.includes(item.source as CapabilitySource)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}].source is not recognised`,
      );
    }
    const refsRaw = item.recorded_reference_ids;
    if (!Array.isArray(refsRaw)) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_INVALID',
        `capability snapshot items[${index}].recorded_reference_ids must be an array`,
      );
    }
    if (refsRaw.length > CAPABILITY_SNAPSHOT_LIMITS.max_reference_ids) {
      throw new CapabilitySnapshotError(
        'CAPABILITY_SNAPSHOT_TOO_LARGE',
        `capability snapshot items[${index}] carries too many recorded references`,
      );
    }
    const recordedReferenceIds = refsRaw.map((ref, refIndex) =>
      cleanText(
        nonEmptyString(ref, `items[${index}].recorded_reference_ids[${refIndex}]`),
        CAPABILITY_SNAPSHOT_LIMITS.max_id,
      ),
    );
    return {
      capability_id: capabilityId,
      kind: item.kind as CapabilityKind,
      name,
      description,
      availability: item.availability as CapabilityAvailability,
      source: item.source as CapabilitySource,
      recorded_reference_ids: recordedReferenceIds,
    };
  });
  const limitationsRaw = record.limitations;
  if (!Array.isArray(limitationsRaw)) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_INVALID',
      'capability snapshot limitations must be an array',
    );
  }
  if (limitationsRaw.length > CAPABILITY_SNAPSHOT_LIMITS.max_limitations) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_TOO_LARGE',
      'capability snapshot carries too many limitation notes',
    );
  }
  const limitations = limitationsRaw.map((text, index) =>
    cleanText(
      nonEmptyString(text, `limitations[${index}]`),
      CAPABILITY_SNAPSHOT_LIMITS.max_limitation_text,
    ),
  );
  return {
    schema_version: CAPABILITY_SNAPSHOT_SCHEMA,
    installation_id: installationId,
    captured_at: capturedAt,
    basis: record.basis === 'at_sitting' ? 'at_sitting' : 'at_export',
    items,
    limitations,
  };
}

/** The report refuses a snapshot from another installation (fail closed). */
export function assertSnapshotInstallation(
  snapshot: InstallationCapabilitySnapshot,
  installationId: string | null | undefined,
): void {
  if (installationId === null || installationId === undefined || installationId === '') {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_MISMATCH',
      'a capability snapshot was supplied without the report installation binding',
    );
  }
  if (snapshot.installation_id !== installationId) {
    throw new CapabilitySnapshotError(
      'CAPABILITY_SNAPSHOT_MISMATCH',
      'the capability snapshot belongs to a different installation than this council session; it will not be attached to the report',
    );
  }
}

// ---------------------------------------------------------------------
// Discovery: this installation's own folders only
// ---------------------------------------------------------------------

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function sortedEntries(dir: string): string[] {
  try {
    return readdirSync(dir).sort();
  } catch {
    return [];
  }
}

/** YAML frontmatter, top of file only; folded indented lines are joined. */
function frontmatter(text: string): Record<string, string> {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match) return {};
  const out: Record<string, string> = {};
  let key: string | null = null;
  for (const line of match[1].split(/\r?\n/)) {
    if (key !== null && /^\s+\S/.test(line)) {
      out[key] = `${out[key]} ${line.trim()}`;
      continue;
    }
    const pair = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (!pair) {
      key = null;
      continue;
    }
    key = pair[1];
    out[key] = pair[2].trim();
  }
  for (const [name, value] of Object.entries(out)) {
    out[name] = value.replace(/^(["'])(.*)\1$/, '$2').trim();
  }
  return out;
}

const TEMPLATE_NAME_RE = /^(?:_|\.)|(^|[-_.])(template|templates|example|examples|sample)([-_.]|$)/i;

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-');
  return slug === '' ? 'unnamed' : slug;
}

function skillSlug(folder: string): string {
  return slugify(folder.replace(/^\d+[-_]/, ''));
}

const ACRONYMS: ReadonlySet<string> = new Set([
  'ai', 'api', 'ceo', 'cfo', 'cmo', 'coo', 'crm', 'cto', 'ghl', 'hr',
  'kpi', 'llm', 'pr', 'qa', 'qc', 'seo', 'sop', 'ui', 'ux', 'vsl',
]);

function humanizeDepartment(folder: string): string {
  return folder
    .replace(/^dept-/, '')
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : `${word.charAt(0).toUpperCase()}${word.slice(1)}`,
    )
    .join(' ');
}

function readSkillEntry(
  skillsRoot: string,
  folder: string,
  source: CapabilitySource,
  availability: CapabilityAvailability,
): InstallationCapabilityEntry | null {
  if (TEMPLATE_NAME_RE.test(folder)) return null;
  const dir = join(skillsRoot, folder);
  if (!isDirectory(dir)) return null;
  const skillFile = join(dir, 'SKILL.md');
  if (!isFile(skillFile)) return null;
  let head = '';
  try {
    head = readFileSync(skillFile, 'utf8').slice(0, 12_000);
  } catch {
    return null;
  }
  const meta = frontmatter(head);
  const slug = skillSlug(folder) || folder.toLowerCase();
  const name = cleanText(
    meta.name && meta.name.trim().length > 0 ? meta.name : (slug || folder),
    CAPABILITY_SNAPSHOT_LIMITS.max_name,
  );
  const rawDescription = meta.description ?? '';
  const description =
    rawDescription.trim() === ''
      ? null
      : cleanText(rawDescription, CAPABILITY_SNAPSHOT_LIMITS.max_description);
  return {
    capability_id: `skill:${slug}`,
    kind: 'skill',
    name: name || slug,
    description,
    availability,
    source,
    recorded_reference_ids: [],
  };
}

function readDepartmentEntry(
  agentsRoot: string,
  folder: string,
  availability: CapabilityAvailability,
): InstallationCapabilityEntry | null {
  if (!folder.startsWith('dept-')) return null;
  if (TEMPLATE_NAME_RE.test(folder.slice('dept-'.length))) return null;
  const dir = join(agentsRoot, folder);
  if (!isDirectory(dir)) return null;
  // Operational only: a configured department carries its model config or
  // an agent runtime directory. A bare template folder is not a department.
  const operational =
    isFile(join(dir, 'models.json')) || isDirectory(join(dir, 'agent'));
  if (!operational) return null;
  const slug = slugify(folder);
  return {
    capability_id: `department:${slug}`,
    kind: 'department',
    name: humanizeDepartment(slug),
    description: null,
    availability,
    source: 'openclaw.departments',
    recorded_reference_ids: [],
  };
}

export interface DiscoverCapabilitiesOptions {
  /** The box's own OpenClaw root (`openclawRoot()` in the CLI). */
  openclaw_root: string;
  installation_id: string;
  /** `YYYY-MM-DD`; the sitting date or the export date. */
  captured_at: string;
  availability?: CapabilityAvailability;
  /** Optional claude-nine / Claude Code skills root on the same box. */
  claude_skills_root?: string | null;
  max_items?: number;
}

/**
 * Read this installation's inventory. Never throws: an unreadable folder
 * is reported in `limitations`, never turned into an invented entry.
 */
export function discoverInstallationCapabilities(
  options: DiscoverCapabilitiesOptions,
): InstallationCapabilitySnapshot {
  const availability = options.availability ?? 'available_now';
  const limit = Math.max(
    1,
    Math.min(options.max_items ?? CAPABILITY_SNAPSHOT_LIMITS.max_items, CAPABILITY_SNAPSHOT_LIMITS.max_items),
  );
  const items: InstallationCapabilityEntry[] = [];
  const limitations: string[] = [
    'Read from this installation\'s own skill and department folders. Skill instructions, prompts, private memory, credentials, databases, and configuration values were not read.',
  ];

  const skillsRoot = join(options.openclaw_root, 'skills');
  if (isDirectory(skillsRoot)) {
    for (const folder of sortedEntries(skillsRoot)) {
      const entry = readSkillEntry(skillsRoot, folder, 'openclaw.skills', availability);
      if (entry) items.push(entry);
    }
  } else {
    limitations.push(
      'No OpenClaw skills folder was found on this installation, so no skills are listed.',
    );
  }

  const agentsRoot = join(options.openclaw_root, 'agents');
  if (isDirectory(agentsRoot)) {
    for (const folder of sortedEntries(agentsRoot)) {
      const entry = readDepartmentEntry(agentsRoot, folder, availability);
      if (entry) items.push(entry);
    }
  } else {
    limitations.push(
      'No OpenClaw agents folder was found on this installation, so no departments are listed.',
    );
  }

  const claudeRoot = options.claude_skills_root;
  if (claudeRoot && isDirectory(claudeRoot)) {
    for (const folder of sortedEntries(claudeRoot)) {
      const entry = readSkillEntry(claudeRoot, folder, 'claude.skills', availability);
      if (entry) items.push(entry);
    }
  }

  const byId = new Map<string, InstallationCapabilityEntry>();
  for (const entry of items) {
    if (!byId.has(entry.capability_id)) byId.set(entry.capability_id, entry);
  }
  const ordered = [...byId.values()].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'department' ? -1 : 1;
    const byName = a.name.localeCompare(b.name);
    return byName !== 0 ? byName : a.capability_id.localeCompare(b.capability_id);
  });
  const kept = ordered.slice(0, limit);
  if (ordered.length > kept.length) {
    limitations.push(
      `${ordered.length - kept.length} further installed item(s) were left out to keep the report readable.`,
    );
  }
  limitations.push(
    'Descriptions are the skill\'s own frontmatter description, shortened to 320 characters when longer. Departments are listed by their configured folder name because this installation records no separate department description.',
  );
  return {
    schema_version: CAPABILITY_SNAPSHOT_SCHEMA,
    installation_id: options.installation_id,
    captured_at: options.captured_at,
    basis: 'at_export',
    items: kept,
    limitations,
  };
}

// ---------------------------------------------------------------------
// Grounded matching to the plan
// ---------------------------------------------------------------------

export interface PlanProposalReference {
  action_id: string;
  title: string;
  description: string;
  department_id?: string | null;
  sop_id?: string | null;
  persona_id?: string | null;
  assigned_agent_id?: string | null;
}

/** The bases a match may rest on. All are exact, not statistical. */
export type CapabilityMatchBasis =
  | 'recorded_reference'
  | 'named_in_step'
  /** CTR-155: at least one step recorded a reference and another only named it. */
  | 'mixed';

/** CTR-155: one step's own match basis and exact literals, never merged. */
export interface CapabilityMatchedAction {
  action_id: string;
  action_title: string;
  basis: 'recorded_reference' | 'named_in_step';
  /** The exact literals this one step supplied, prefixed with its action id. */
  evidence: string[];
}

export interface CapabilityPlanMatch extends InstallationCapabilityEntry {
  matched_action_ids: string[];
  matched_action_titles: string[];
  match_basis: CapabilityMatchBasis;
  /** The exact literals that justified the match, for the reader. */
  match_evidence: string[];
  /**
   * CTR-155: the per-step basis, so a renderer can say "this step records
   * it" without claiming the same for a step that only named the tool.
   */
  matched_actions: CapabilityMatchedAction[];
  recorded_reference_action_ids: string[];
  named_in_step_action_ids: string[];
  /**
   * Retained only so older readers keep their shape; always empty.
   *
   * CTR-151 removed the previous generic word-overlap rule. It matched on
   * any two shared tokens of four or more letters, so the observed report
   * linked a backup-protocol skill to a video step through "before" and
   * "every", and a GHL setup skill to a production-hours step through
   * "before" and "search". Shared vocabulary is not task fit.
   */
  shared_terms: string[];
}

/** A named match must be long enough to be a real capability name. */
const MIN_NAMED_CAPABILITY_CHARS = 8;

function referenceCandidates(proposal: PlanProposalReference): string[] {
  return [
    proposal.department_id,
    proposal.sop_id,
    proposal.persona_id,
    proposal.assigned_agent_id,
  ].filter((value): value is string => typeof value === 'string' && value.length > 0);
}

function referencesEntry(proposal: PlanProposalReference, entry: InstallationCapabilityEntry): string[] {
  const bareId = entry.capability_id.split(':')[1];
  const entryNameSlug = entry.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const hits: string[] = [];
  for (const ref of referenceCandidates(proposal)) {
    const normalized = ref.trim().toLowerCase();
    if (
      normalized === entry.capability_id.toLowerCase() ||
      normalized === bareId ||
      normalized === entryNameSlug ||
      normalized === `dept-${entryNameSlug}`
    ) {
      hits.push(ref);
    }
  }
  return hits;
}

/**
 * Whole-phrase, case-insensitive presence: the capability's exact name or
 * id appears in the step text with a non-alphanumeric boundary on each
 * side. A stem, a partial word, or a shared adjective never counts.
 */
function containsExactPhrase(haystack: string, needle: string): boolean {
  const phrase = needle.trim().toLowerCase();
  if (phrase.length < MIN_NAMED_CAPABILITY_CHARS) return false;
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, 'i').test(haystack);
}

/** The exact literal a step names, or null when it names nothing exact. */
function namedEntryInStep(
  proposal: PlanProposalReference,
  entry: InstallationCapabilityEntry,
): string | null {
  const stepText = `${proposal.title} ${proposal.description}`;
  const bareId = entry.capability_id.split(':')[1];
  const candidates = [entry.name, bareId, entry.capability_id]
    .filter((value): value is string => typeof value === 'string' && value.trim() !== '');
  for (const candidate of candidates) {
    if (containsExactPhrase(stepText, candidate)) return candidate;
  }
  return null;
}

/**
 * Match installed capabilities to plan steps. Two verified bases only:
 *
 * 1. `recorded_reference` — the action proposal itself records this
 *    department, SOP, persona, or agent.
 * 2. `named_in_step` — the step text contains the capability's exact name,
 *    slug, or id as a whole phrase.
 *
 * The basis is recorded PER STEP (`matched_actions`). A capability whose
 * steps split between the two bases reports `mixed`; it is never described
 * as recorded for the whole plan. No token overlap, no scoring, no model
 * call. A step that names no capability gets no suggestion, and "installed"
 * never means "operational".
 */
export function matchCapabilitiesToPlan(
  snapshot: InstallationCapabilitySnapshot,
  proposals: readonly PlanProposalReference[],
): CapabilityPlanMatch[] {
  if (proposals.length === 0) return [];
  const matches: CapabilityPlanMatch[] = [];
  for (const entry of snapshot.items) {
    const matchedActions: CapabilityMatchedAction[] = [];
    const evidence = new Set<string>();
    for (const proposal of proposals) {
      const refs = referencesEntry(proposal, entry);
      const named = namedEntryInStep(proposal, entry);
      if (refs.length === 0 && named === null) continue;
      const basis: CapabilityMatchedAction['basis'] =
        refs.length > 0 ? 'recorded_reference' : 'named_in_step';
      const actionEvidence = refs.map(
        (ref) => `${proposal.action_id}: recorded reference ${ref}`,
      );
      if (named !== null) {
        actionEvidence.push(`${proposal.action_id}: step names "${named}"`);
      }
      for (const line of actionEvidence) evidence.add(line);
      matchedActions.push({
        action_id: proposal.action_id,
        action_title: proposal.title,
        basis,
        evidence: actionEvidence,
      });
    }
    if (matchedActions.length === 0) continue;
    const recorded = matchedActions
      .filter((action) => action.basis === 'recorded_reference')
      .map((action) => action.action_id);
    const namedOnly = matchedActions
      .filter((action) => action.basis === 'named_in_step')
      .map((action) => action.action_id);
    // CTR-155: the capability-wide basis is only "recorded_reference" when
    // EVERY matched step recorded it. One recorded step beside a named-only
    // step is "mixed", so a renderer never says "the plan records this" for
    // a step that merely names the tool.
    const basis: CapabilityMatchBasis =
      recorded.length > 0 && namedOnly.length > 0
        ? 'mixed'
        : recorded.length > 0
          ? 'recorded_reference'
          : 'named_in_step';
    matches.push({
      ...entry,
      matched_action_ids: matchedActions.map((action) => action.action_id),
      matched_action_titles: matchedActions.map((action) => action.action_title),
      match_basis: basis,
      // Every literal is kept; a per-step prefix maps each line to its step.
      match_evidence: [...evidence].sort(),
      matched_actions: matchedActions,
      recorded_reference_action_ids: recorded,
      named_in_step_action_ids: namedOnly,
      shared_terms: [],
    });
  }
  const basisRank: Record<CapabilityMatchBasis, number> = {
    recorded_reference: 0,
    mixed: 1,
    named_in_step: 2,
  };
  matches.sort((a, b) => {
    if (a.match_basis !== b.match_basis) {
      return basisRank[a.match_basis] - basisRank[b.match_basis];
    }
    if (a.matched_action_ids.length !== b.matched_action_ids.length) {
      return b.matched_action_ids.length - a.matched_action_ids.length;
    }
    if (a.kind !== b.kind) return a.kind === 'department' ? -1 : 1;
    const byName = a.name.localeCompare(b.name);
    return byName !== 0 ? byName : a.capability_id.localeCompare(b.capability_id);
  });
  // CTR-158: return every exact match. The display bound is applied by the
  // caller that renders the list, together with an explicit total/shown note,
  // so a reader is never handed a silently truncated count.
  return matches;
}

/** True when a path exists and is a directory (used by the seat loader). */
export function directoryExists(path: string): boolean {
  return existsSync(path) && isDirectory(path);
}
