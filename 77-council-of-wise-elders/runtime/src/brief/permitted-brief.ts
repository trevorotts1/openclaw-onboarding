/**
 * Permitted-context brief builder (W74-C).
 *
 * At convene, ONE shared builder assembles the BRIEF the elders read:
 * the decision, the real options, the constraints, the known facts, and
 * the explicit unknowns. Facts are drawn SELECTIVELY from the client's
 * permitted context files because they bear on THIS decision — never a
 * file dump.
 *
 * Two source adapters read the two harness doors and feed the SAME
 * assembler, so the brief shape is identical regardless of door:
 *   - 'openclaw'    — the OpenClaw door: memory.md, agents.md, soul.md,
 *                     user.md (W74-C: plus one hop of their pointer links)
 *   - 'claude-nine' — the 999 door (claude-nine / Claude Code):
 *                     CLAUDE.md, AGENTS.md, memory/MEMORY.md (plus one
 *                     hop of their pointer links)
 *
 * Rules enforced here (load-bearing, the same rules the skill carries):
 * - permitted context only: exactly the door's root files and at most
 *   ONE hop of the pointer links inside them are ever read; recursion
 *   never. Anything else on disk is untouchable by construction.
 * - private preferences stay in the private store: anything under a
 *   private heading, marked `private:`, in a `private/` path, or in a
 *   `*.private.md` file never enters the brief. The brief carries only
 *   `private_preference_ref`, an opaque handle with no content.
 * - unknowns marked explicitly: what the permitted context does not
 *   state is recorded as an explicit unknown, never guessed, and never
 *   silently dropped.
 * - bloat protection: BRIEF_WORD_CAP (2000 words) is a hard cap on the
 *   brief's text; facts are selected decision-relevant first, newest
 *   first inside a relevance class, and the least relevant fall off
 *   first when the cap bites.
 */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';

/** Hard cap on the brief's text, in words. */
export const BRIEF_WORD_CAP = 2000;

export type DoorKind = 'openclaw' | 'claude-nine';

export interface BriefFact {
  /** The selected fact, as it appears in the brief. */
  readonly statement: string;
  /** Relative path of the permitted file it came from. */
  readonly source: string;
  /** Decision-relevance score (distinct decision/option word overlap). */
  readonly relevance: number;
  /** Newest-first tiebreaker: the file's `updated: YYYY-MM-DD` date, if any. */
  readonly as_of: string | null;
}

export interface PermittedContextBrief {
  readonly schema: 'cwe-permitted-brief/1';
  readonly door: DoorKind;
  readonly decision: string;
  readonly options: readonly string[];
  readonly constraints: readonly string[];
  readonly facts: readonly BriefFact[];
  readonly unknowns: readonly string[];
  /** Opaque handle to the separate private-preference record; content never here. */
  readonly private_preference_ref: string | null;
  readonly meta: {
    readonly word_cap: number;
    readonly word_count: number;
    readonly truncated: boolean;
    /** Permitted files actually read (roots plus at most one hop). */
    readonly sources_read: readonly string[];
    readonly pointer_hops_followed: 1;
  };
}

export interface BriefInput {
  readonly door: DoorKind;
  /** The client context root (e.g. the OpenClaw or claude-nine state dir). */
  readonly rootDir: string;
  readonly decision: string;
  readonly options?: readonly string[];
  /** Test seam; production callers use BRIEF_WORD_CAP. */
  readonly wordCap?: number;
}

/** Permitted root files per door. Nothing outside these is ever read. */
const DOOR_ROOTS: Record<DoorKind, readonly string[]> = {
  openclaw: ['memory.md', 'agents.md', 'soul.md', 'user.md'],
  'claude-nine': ['CLAUDE.md', 'AGENTS.md', 'memory/MEMORY.md'],
};

export interface ContextDocument {
  readonly rel: string;
  readonly text: string;
  readonly depth: 0 | 1;
  readonly updated: string | null;
}

const STOPWORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'but', 'by', 'can',
  'do', 'for', 'from', 'has', 'have', 'how', 'if', 'in', 'into', 'is',
  'it', 'its', 'not', 'of', 'on', 'or', 'our', 'should', 'so', 'that',
  'the', 'their', 'them', 'then', 'there', 'these', 'they', 'this',
  'those', 'to', 'was', 'we', 'were', 'what', 'when', 'where', 'which',
  'who', 'will', 'with', 'would', 'year',
]);

function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

function isPrivatePath(rel: string): boolean {
  return rel.split('/').includes('private') || rel.endsWith('.private.md');
}

/** One hop of markdown pointer links: `[text](target.md)`. Never recursive. */
function pointerLinks(text: string, fromRel: string, rootDir: string): string[] {
  const out: string[] = [];
  const re = /\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const target = m[1].trim();
    if (!target.toLowerCase().endsWith('.md')) continue;
    const fromDir = dirname(resolve(rootDir, fromRel));
    const abs = isAbsolute(target) ? target : resolve(fromDir, target);
    const rel = relative(resolve(rootDir), abs).split('\\').join('/');
    // Trust boundary: a link may never escape the context root, and a
    // private path is never followed at any hop.
    if (rel.startsWith('..') || isAbsolute(rel) || isPrivatePath(rel)) continue;
    out.push(rel);
  }
  return out;
}

function readDoc(rootDir: string, rel: string, depth: 0 | 1): ContextDocument | null {
  const abs = resolve(rootDir, rel);
  const contained = relative(resolve(rootDir), abs).split('\\').join('/');
  if (contained.startsWith('..') || isAbsolute(contained) || isPrivatePath(contained)) return null;
  if (!existsSync(abs) || !statSync(abs).isFile()) return null;
  const text = readFileSync(abs, 'utf8');
  const updated = /updated:\s*(\d{4}-\d{2}-\d{2})/i.exec(text)?.[1] ?? null;
  return { rel: contained, text, depth, updated };
}

/** The two door adapters: root lists plus at-most-one-hop link following. */
export function collectPermittedDocuments(door: DoorKind, rootDir: string): ContextDocument[] {
  const docs: ContextDocument[] = [];
  const seen = new Set<string>();
  const hopQueue: string[] = [];
  for (const root of DOOR_ROOTS[door]) {
    const doc = readDoc(rootDir, root, 0);
    if (doc && !seen.has(doc.rel)) {
      seen.add(doc.rel);
      docs.push(doc);
      for (const link of pointerLinks(doc.text, doc.rel, rootDir)) {
        if (!seen.has(link)) hopQueue.push(link);
      }
    }
  }
  // Exactly one hop: targets of root links are read, their own links are
  // never followed (recursion never).
  for (const link of hopQueue) {
    if (seen.has(link)) continue;
    const doc = readDoc(rootDir, link, 1);
    if (doc) {
      seen.add(doc.rel);
      docs.push(doc);
    }
  }
  return docs;
}

/**
 * Strip private material from a permitted document: sections under a
 * private heading (until the next heading) and `private:` lines. The
 * stripped content never reaches any output of this module.
 */
function stripPrivate(text: string): { cleaned: string; sawPrivate: boolean } {
  let sawPrivate = false;
  let inPrivateSection = false;
  let sectionLevel = 0;
  const kept: string[] = [];
  for (const line of text.split('\n')) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      if (/private/i.test(heading[2])) {
        sawPrivate = true;
        inPrivateSection = true;
        sectionLevel = level;
        continue;
      }
      if (inPrivateSection && level <= sectionLevel) inPrivateSection = false;
    }
    if (/^\s*private\s*:/i.test(line)) {
      sawPrivate = true;
      continue;
    }
    if (inPrivateSection) {
      if (line.trim()) sawPrivate = true;
      continue;
    }
    kept.push(line);
  }
  return { cleaned: kept.join('\n'), sawPrivate };
}

/** Candidate entries: bullet lines, else whole non-heading lines. */
function entries(cleaned: string, source: string): Array<{ statement: string; source: string }> {
  const out: Array<{ statement: string; source: string }> = [];
  for (const raw of cleaned.split('\n')) {
    const line = raw.trim();
    if (!line || /^#{1,6}\s/.test(line)) continue;
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    out.push({ statement: (bullet ? bullet[1] : line).trim(), source });
  }
  return out;
}

const CONSTRAINT_RE = /^constraint\b|\bconstraint\b|\bcannot\b|\bcan't\b|\bmust not\b|\bonly if\b|\bbudget cap\b/i;
const UNKNOWN_RE = /\bunknown\b|\bnot yet known\b|\bto be determined\b|\bTBD\b/i;
const OPTION_RE = /^option\s*\d*\s*[:.-]\s*/i;

function tokenize(text: string): Set<string> {
  return new Set(
    text.toLowerCase().split(/[^a-z0-9$]+/).filter((t) => t.length >= 3 && !STOPWORDS.has(t)),
  );
}

export function assembleBrief(input: BriefInput): PermittedContextBrief {
  const decision = input.decision.trim();
  if (!decision) throw new TypeError('assembleBrief: decision must be a non-empty string');
  const wordCap = input.wordCap ?? BRIEF_WORD_CAP;
  if (!Number.isInteger(wordCap) || wordCap <= 0) {
    throw new TypeError('assembleBrief: wordCap must be a positive integer');
  }
  const callerOptions = (input.options ?? []).map((o) => o.trim()).filter(Boolean);

  const docs = collectPermittedDocuments(input.door, input.rootDir);
  const query = tokenize([decision, ...callerOptions].join(' '));

  const constraints: string[] = [];
  const unknowns: string[] = [];
  const contextOptions: string[] = [];
  const candidates: BriefFact[] = [];
  let sawPrivate = false;
  const seenStatements = new Set<string>();

  for (const doc of docs) {
    const { cleaned, sawPrivate: priv } = stripPrivate(doc.text);
    sawPrivate = sawPrivate || priv;
    for (const entry of entries(cleaned, doc.rel)) {
      const { statement, source } = entry;
      if (seenStatements.has(statement)) continue;
      seenStatements.add(statement);
      if (OPTION_RE.test(statement)) {
        contextOptions.push(statement.replace(OPTION_RE, ''));
        continue;
      }
      if (CONSTRAINT_RE.test(statement)) {
        constraints.push(statement);
        continue;
      }
      if (UNKNOWN_RE.test(statement)) {
        unknowns.push(statement);
        continue;
      }
      let relevance = 0;
      for (const token of tokenize(statement)) if (query.has(token)) relevance += 1;
      if (relevance > 0) {
        candidates.push({ statement, source, relevance, as_of: doc.updated });
      }
      // relevance 0 = does not bear on THIS decision: excluded, never a
      // file dump.
    }
  }

  // Newest / relevant first: relevance descending, then newest as_of.
  candidates.sort((a, b) => {
    if (b.relevance !== a.relevance) return b.relevance - a.relevance;
    const aDate = a.as_of ?? '';
    const bDate = b.as_of ?? '';
    if (aDate !== bDate) return aDate < bDate ? 1 : -1;
    return a.statement < b.statement ? -1 : 1;
  });

  const options = callerOptions.length > 0
    ? callerOptions
    : contextOptions;
  if (options.length === 0) {
    unknowns.unshift('The real options are not stated in the permitted context; this is an explicit unknown.');
  }
  if (constraints.length === 0) {
    unknowns.unshift('The applicable constraints are not stated in the permitted context; this is an explicit unknown.');
  }

  const sourcesRead = docs.map((d) => d.rel).sort();
  const privatePreferenceRef = sawPrivate
    ? `pref-${createHash('sha256').update(`cwe-private-pref:${input.door}`).digest('hex').slice(0, 16)}`
    : null;

  // Hard cap: drop the least-relevant facts first, then constraints,
  // then options, then unknowns, then clip the decision — never over
  // the cap. Every rung counts as a drop, so `truncated` is accurate on
  // every trimming path including the decision clip.
  let facts: BriefFact[] = [...candidates];
  const keptConstraints = [...constraints];
  const keptOptions = [...options];
  let keptUnknowns = [...unknowns];
  let keptDecision = decision;
  let dropped = 0;
  const measure = (f: BriefFact[], c: string[], o: string[], u: string[], d: string): number => {
    const omissionNote = dropped > 0
      ? `${dropped} permitted-context item(s) omitted under the brief word cap.`
      : '';
    return countWords([d, ...o, ...c, ...f.map((x) => x.statement), ...u, omissionNote].join(' '));
  };
  while (measure(facts, keptConstraints, keptOptions, keptUnknowns, keptDecision) > wordCap) {
    if (facts.length > 0) {
      facts = facts.slice(0, -1);
    } else if (keptConstraints.length > 0) {
      keptConstraints.pop();
    } else if (keptOptions.length > 0) {
      keptOptions.pop();
    } else if (keptUnknowns.length > 0) {
      keptUnknowns.pop();
    } else {
      // Last resort: clip the decision. Counts as a drop like every
      // other rung (the break is only the loop's termination guard for
      // an already-clipped decision).
      keptDecision = keptDecision.split(/\s+/).slice(0, Math.max(1, Math.floor(wordCap / 2))).join(' ');
      dropped += 1;
      break;
    }
    dropped += 1;
  }

  const finalUnknowns = [...keptUnknowns];
  if (dropped > 0) {
    finalUnknowns.push(`${dropped} permitted-context item(s) omitted under the brief word cap.`);
  }

  const wordCount = countWords(
    [keptDecision, ...keptOptions, ...keptConstraints, ...facts.map((f) => f.statement), ...finalUnknowns].join(' '),
  );

  return {
    schema: 'cwe-permitted-brief/1',
    door: input.door,
    decision: keptDecision,
    options: keptOptions,
    constraints: keptConstraints,
    facts,
    unknowns: finalUnknowns,
    private_preference_ref: privatePreferenceRef,
    meta: {
      word_cap: wordCap,
      word_count: wordCount,
      truncated: dropped > 0,
      sources_read: sourcesRead,
      pointer_hops_followed: 1,
    },
  };
}
