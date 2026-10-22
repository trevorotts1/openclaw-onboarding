/**
 * W74-D: the artifact-renderer entry point (the name the session-close
 * protocol resolves first, `../reports/artifact-renderer.js`).
 *
 * This module wires W74-A's finalize to W74-B's renderer. It holds the
 * one seam between the runtime's stored session and the renderer's
 * session record:
 *
 * - `assembleRenderRecord(session, extras)` builds the renderer's
 *   session record the way W74-B documents it: the session row plus the
 *   runtime data that only exists at run time (client name, model used,
 *   question count, the nine seat takes, the verdict view). Nothing is
 *   invented here: the caller supplies the runtime rows, this projects
 *   them.
 * - `renderArtifact(sessionRecord, options)` delegates to the W74-B
 *   entry point `scripts/render-counsel-artifact.mjs` by export name and
 *   returns its `{ path, link, pdf }`. It accepts either the assembled
 *   render record or a bare `StoredSession` with `options.extras`, so
 *   `resolveRenderArtifact()`'s by-name fallback works unchanged.
 *
 * The repo stays client-name-free: `client_name` enters only as runtime
 * data through `extras`, exactly as W74-B's contract requires.
 */
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import type { StoredSession } from '../cli/host-ports.js';

/** One elder card as the renderer shows it. */
export interface RenderCard {
  seat_id: string;
  take: string;
}

/** The verdict view the renderer shows: one consensus line plus steps. */
export interface RenderVerdictView {
  consensus: string;
  action_steps: string[];
}

/** W74-B's session record: the flat shape `render-counsel-artifact.mjs` validates. */
export interface RenderSessionRecord {
  session_id: string;
  client_name: string;
  date: string;
  decision: string;
  model_used: string;
  question_count: number;
  cards: RenderCard[];
  verdict: RenderVerdictView;
  /** Labeled fixture/replay render; never a production claim. */
  synthetic?: boolean;
}

/** The runtime-only rows the assembler projects; never fabricated. */
export interface RenderExtras {
  client_name: string;
  model_used: string;
  question_count: number;
  cards: RenderCard[];
  verdict: RenderVerdictView;
  /** `YYYY-MM-DD`; defaults to the session's created-at date. */
  date?: string;
}

/** The W74-B result shape (pdf is best effort and may be absent). */
export interface ArtifactRenderResult {
  path: string;
  link: string;
  pdf?: unknown;
}

export interface RenderOptions {
  /** Council data directory; the renderer writes `<dataDir>/artifacts/...`. */
  dataDir?: string;
  assetsDir?: string;
  /** Public origin for an absolute link; relative when omitted. */
  linkBase?: string | null;
  pdf?: boolean;
  env?: NodeJS.ProcessEnv;
  /** Runtime rows, required when the record is a bare StoredSession. */
  extras?: RenderExtras;
}

function isStoredSession(record: unknown): record is StoredSession {
  const r = record as { spec?: unknown; brief?: unknown } | null;
  return typeof r === 'object' && r !== null && 'spec' in r && 'brief' in r;
}

/**
 * The typed state surfaced when a renderer input cannot honestly be
 * derived from the store's own records. Never a guessed value: the
 * renderer contract requires real rows, and a session without them is
 * reported, not papered over.
 */
export const RENDER_INPUT_INCOMPLETE = 'RENDER_INPUT_INCOMPLETE' as const;
export type RenderInputIncompleteCode =
  | typeof RENDER_INPUT_INCOMPLETE
  | 'NO_CARDS'
  | 'NO_VERDICT';

export class RenderInputError extends Error {
  constructor(
    readonly code: RenderInputIncompleteCode,
    message: string,
  ) {
    super(message);
    this.name = 'RenderInputError';
  }
}

/**
 * Project the runtime rows into the renderer's session record. The
 * session supplies identity and the decision; the extras supply the
 * runtime-only rows. Missing extras surface at the renderer's own trust
 * boundary (it validates and throws) — nothing is guessed here.
 */
export function assembleRenderRecord(
  session: StoredSession,
  extras: RenderExtras,
): RenderSessionRecord {
  return {
    session_id: session.spec.session_id,
    client_name: extras.client_name,
    date: extras.date ?? String(session.spec.created_at).slice(0, 10),
    decision: session.brief.question,
    model_used: extras.model_used,
    question_count: extras.question_count,
    cards: extras.cards.map((c) => ({ seat_id: c.seat_id, take: c.take })),
    verdict: { consensus: extras.verdict.consensus, action_steps: [...extras.verdict.action_steps] },
    synthetic: session.sample,
  };
}

/**
 * Locate the skill folder (SKILL.md beside advisors/ and manifest.json),
 * the same signature the CLI's data-dir guard measures. ponytail: local
 * walk duplicated from cli/dispatcher.ts to keep the protocol->reports
 * edge type-only; unify through a shared helper if a third caller lands.
 */
function skillRoot(): string | null {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let depth = 0; depth < 8; depth += 1) {
    if (
      existsSync(join(dir, 'SKILL.md')) &&
      existsSync(join(dir, 'advisors')) &&
      existsSync(join(dir, 'manifest.json'))
    ) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

interface RendererModule {
  renderArtifact: (record: unknown, options?: Record<string, unknown>) => ArtifactRenderResult;
}

let cached: Promise<RendererModule> | null = null;

/** Load the W74-B renderer module once (scripts/render-counsel-artifact.mjs). */
function loadRenderer(): Promise<RendererModule> {
  cached ??= (async () => {
    const root = skillRoot();
    const script = root === null ? null : join(root, 'scripts', 'render-counsel-artifact.mjs');
    if (script === null || !existsSync(script)) {
      throw new Error('RENDERER_UNAVAILABLE: scripts/render-counsel-artifact.mjs not found beside this skill');
    }
    const mod = (await import(pathToFileURL(script).href)) as Partial<RendererModule>;
    if (typeof mod.renderArtifact !== 'function') {
      throw new Error('RENDERER_UNAVAILABLE: scripts/render-counsel-artifact.mjs has no renderArtifact export');
    }
    return mod as RendererModule;
  })();
  return cached;
}

/**
 * renderArtifact(sessionRecord) -> { path, link, pdf }
 *
 * The W74-B entry point, called by export name. Accepts the assembled
 * render record, or a bare StoredSession plus `options.extras` (the
 * session-close protocol hands over what its close port assembled).
 * A bare StoredSession WITHOUT extras is a contract violation, not a
 * default: it carries none of the runtime rows the renderer validates,
 * and this seam reports it with the typed `RenderInputError` instead of
 * casting undefined through (the R1 defect: `options.extras as
 * RenderExtras` let a bare record dereference undefined in
 * assembleRenderRecord). Delegates to the fixed-template renderer
 * unchanged.
 */
export async function renderArtifact(
  sessionRecord: RenderSessionRecord | StoredSession,
  options: RenderOptions = {},
): Promise<ArtifactRenderResult> {
  let record: RenderSessionRecord;
  if (isStoredSession(sessionRecord)) {
    if (options.extras === undefined) {
      throw new RenderInputError(
        RENDER_INPUT_INCOMPLETE,
        'renderArtifact received a bare StoredSession without options.extras: ' +
          `the close-to-render contract requires the runtime rows (client name, model, question count, cards, verdict) for session ${sessionRecord.spec.session_id}.`,
      );
    }
    record = assembleRenderRecord(sessionRecord, options.extras);
  } else {
    record = sessionRecord;
  }
  const renderer = await loadRenderer();
  const rendererOptions: Record<string, unknown> = {};
  if (options.dataDir !== undefined) rendererOptions['dataDir'] = options.dataDir;
  if (options.assetsDir !== undefined) rendererOptions['assetsDir'] = options.assetsDir;
  if (options.linkBase !== undefined) rendererOptions['linkBase'] = options.linkBase;
  if (options.pdf !== undefined) rendererOptions['pdf'] = options.pdf;
  if (options.env !== undefined) rendererOptions['env'] = options.env;
  return renderer.renderArtifact(record, rendererOptions);
}

/** Resolve a render function bound to one session's runtime extras. */
export function renderArtifactWithExtras(extras: RenderExtras, options: RenderOptions = {}) {
  return (sessionRecord: StoredSession | RenderSessionRecord): Promise<ArtifactRenderResult> =>
    renderArtifact(sessionRecord, { ...options, extras });
}
