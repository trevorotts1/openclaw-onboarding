/**
 * W74-D: the wired convene flow — the one place the three W74 builds
 * come together, in this exact order (load-bearing):
 *
 *   1. brief-builder FIRST (permitted context): `assembleBrief` reads
 *      the door's permitted memory files through the door's own adapter
 *      (W74-C) and assembles the brief the elders read — selective
 *      facts, explicit unknowns, private detail excluded.
 *   2. deliberation, then 3. verdict: the injected deliberation port
 *      runs the session on that brief and returns the settled result.
 *   4. session-close manages the sitting (W74-A): the soft-close
 *      question after five quiet minutes, an explicit close phrase
 *      finalizes now, ten minutes of silence auto-finalizes. The
 *      sitting controls below are that protocol, over store timestamps.
 *   5. finalize calls `renderArtifact(sessionRecord)` (W74-B, resolved
 *      and called by export name) and the delivery carries the artifact
 *      link in the reply beside the chamber link.
 *
 * W77S auto-mode: before deliberation, the sitting's mode (light /
 * medium / heavy) is resolved through the ONE selector,
 * `selectMode(question, explicitMode)`. An explicit client mode always
 * wins verbatim; with no client mode the question's complexity decides.
 * The chosen mode, its source (`client` / `auto`) and the reason travel
 * with the sitting on the returned session record and the convene
 * result. What a mode DOES (rounds, concurrency, request caps) is
 * contracts/modes.ts and is not reinterpreted here.
 *
 * Doors: the OpenClaw door runs the OpenClaw adapter; the
 * claude-nine / Claude Code (999) door runs its adapter. `doorForEnv`
 * selects by harness marker, and every adapter feeds the SAME
 * assembler, so the brief shape and the rest of the flow are identical
 * across doors.
 */
import {
  assembleBrief,
  type DoorKind,
  type PermittedContextBrief,
} from '../brief/permitted-brief.js';
import { isCouncilSize, type CouncilSize } from '../contracts/modes.js';
import { selectMode } from './mode-select.js';
import {
  SessionCloseService,
  SOFT_CLOSE_QUESTION,
  type CloseAction,
  type CloseReason,
  type FinalizeResult,
  type RenderArtifactFn,
  type SessionClosePort,
} from '../protocol/session-close.js';
import {
  assembleRenderRecord,
  renderArtifactWithExtras,
  type RenderCard,
  type RenderExtras,
  type RenderOptions,
  type RenderVerdictView,
} from '../reports/artifact-renderer.js';

export type { DoorKind, PermittedContextBrief };
export { SOFT_CLOSE_QUESTION };

/** Harness markers the doors recognize (same rules as the CLI's detectHarness). */
export type HarnessKind = 'openclaw' | 'claude-nine' | 'claude-code' | 'deepseek' | 'unknown';

/**
 * The door -> adapter map. The OpenClaw door uses the OpenClaw adapter
 * (memory.md, agents.md, soul.md, user.md); the claude-nine / Claude
 * Code (999) door uses its adapter (CLAUDE.md, AGENTS.md,
 * memory/MEMORY.md). One assembler behind both.
 */
export function doorAdapterFor(door: DoorKind): DoorKind {
  return door;
}

/** Select the door from the running harness's environment markers. */
export function doorForEnv(env: NodeJS.ProcessEnv): DoorKind {
  const configDir = env.CLAUDE_CONFIG_DIR ?? '';
  const parts = configDir.split(/[\\/]+/).filter((p) => p.length > 0);
  if (parts[parts.length - 1] === '.claude-nine') return 'claude-nine';
  if (env.CLAUDECODE === '1') return 'claude-nine';
  return 'openclaw';
}

/** Who chose the sitting's mode: the client explicitly, or the system. */
export type ModeSource = 'client' | 'auto';

/**
 * The resolved mode and WHY — shown to the client with the sitting. The
 * shape is the selector's own return: `selectMode` decides it, this flow
 * only carries it.
 */
export interface ModeSelection {
  mode: CouncilSize;
  source: ModeSource;
  reason: string;
}

/** The deliberation leg: runs the session on the prepared brief. */
export interface DeliberationResult {
  sessionId: string;
  /** The settled session row (identity and the decision). */
  session: import('../cli/host-ports.js').StoredSession;
  /** Runtime-only rows; the client's name enters here and nowhere else. */
  clientName: string;
  modelUsed: string;
  questionCount: number;
  cards: RenderCard[];
  verdict: RenderVerdictView;
  /** The chamber link the convene command printed, when the box has one. */
  chamberUrl: string | null;
}

/**
 * The settled session record as this flow hands it back: the store's own
 * row plus the mode provenance for the sitting. SessionSpec has no
 * council-size seat yet (its `mode` is the older four-mode enum), so the
 * provenance rides here rather than in a field the store cannot validate.
 */
export type ConveneSessionRecord = DeliberationResult['session'] & {
  mode_selection: ModeSelection;
};

export interface ConveneFlowInput {
  door: DoorKind;
  /** The client's context root for the door (their memory files). */
  contextRoot: string;
  decision: string;
  options?: readonly string[];
  /**
   * The client's explicit mode — a `--mode` flag or a `mode` field on the
   * request. It ALWAYS wins, verbatim: the system never second-guesses a
   * mode the client asked for. Omitted or null means the system picks
   * from the question's complexity. One of `light`, `medium`, `heavy`.
   */
  mode?: string | null;
}

export interface ConveneFlowDeps {
  /**
   * Step 2-3: deliberation, then verdict. `mode` is the resolved sitting
   * mode: the deliberation leg reads its rounds and concurrency from the
   * mode policy (contracts/modes.ts) — this flow does not.
   */
  deliberate(input: {
    permittedBrief: PermittedContextBrief;
    mode: ModeSelection;
  }): Promise<DeliberationResult>;
  /** The store-backed close port (W74-A storeSessionClosePort in production). */
  closePort: SessionClosePort;
  /** W74-B renderer; resolved by export name when omitted. */
  renderArtifact?: RenderArtifactFn;
  renderOptions?: RenderOptions;
}

export interface ConveneFlowResult {
  /** The permitted-context brief the elders read (step 1). */
  permittedBrief: PermittedContextBrief;
  sessionId: string;
  chamberUrl: string | null;
  /** The resolved mode, its source and the reason — the convene output says why. */
  modeSelection: ModeSelection;
  /** The settled session record, carrying the same mode provenance. */
  session: ConveneSessionRecord;
  /** The sitting controls (step 4): session-close manages the sitting. */
  sitting: {
    status(nowIso: string): CloseAction;
    tick(nowIso: string): Promise<import('../protocol/session-close.js').TickResult>;
    handleClientMessage(
      text: string,
      nowIso: string,
    ): Promise<{ finalized: FinalizeResult | null }>;
  };
  /** Step 5: finalize -> renderArtifact(sessionRecord) -> the delivery. */
  finalize(
    reason: CloseReason,
    nowIso: string,
  ): Promise<{ delivery: { reply_link: string | null; chamber_url: string | null } | null } & FinalizeResult>;
}

/**
 * Resolve the sitting's mode through the ONE selector. The client's
 * explicit mode wins verbatim; with none, the question's complexity
 * decides. An explicit value that is not a council size is a client
 * error, refused by name — never silently replaced by an auto pick,
 * because that would override the client's choice.
 */
function resolveMode(input: ConveneFlowInput): ModeSelection {
  const explicit = input.mode ?? null;
  if (explicit !== null && !isCouncilSize(explicit)) {
    throw new Error(
      `INVALID_MODE: ${JSON.stringify(explicit)} is not a council size; ` +
        'expected one of light, medium, heavy.',
    );
  }
  return selectMode(input.decision, explicit ?? undefined);
}

/**
 * Run the wired convene flow once: brief-builder first (permitted
 * context, through the door's adapter), deliberation and verdict, then
 * the session-close protocol manages the sitting and finalize renders
 * the counsel artifact. Deliberation is injected; everything else is
 * the three landed W74 modules, wired.
 */
export async function conveneFlow(
  input: ConveneFlowInput,
  deps: ConveneFlowDeps,
): Promise<ConveneFlowResult> {
  // 1. brief-builder FIRST: permitted context only, through the door's adapter.
  const permittedBrief = assembleBrief({
    door: doorAdapterFor(input.door),
    rootDir: input.contextRoot,
    decision: input.decision,
    ...(input.options === undefined ? {} : { options: input.options }),
  });

  // Mode next, still before deliberation: it decides the rounds the
  // sitting runs. Pure question-text work — it reads no client context.
  const modeSelection = resolveMode(input);

  // 2-3. deliberation, then verdict.
  const settled = await deps.deliberate({ permittedBrief, mode: modeSelection });

  // 4-5. session-close manages the sitting; finalize renders the
  // artifact through the W74-B entry point (`renderArtifact`, called by
  // export name), bound to this session's runtime rows and render
  // options. A caller-supplied renderer wins (tests, alternate hosts).
  const extras: RenderExtras = {
    client_name: settled.clientName,
    model_used: settled.modelUsed,
    question_count: settled.questionCount,
    cards: settled.cards,
    verdict: settled.verdict,
  };
  const render: RenderArtifactFn =
    deps.renderArtifact ?? renderArtifactWithExtras(extras, deps.renderOptions ?? {});

  // The close port hands finalize the ASSEMBLED render record (the
  // session row plus the runtime rows), which is exactly the
  // `sessionRecord` renderArtifact takes.
  const closePort: SessionClosePort = {
    ...deps.closePort,
    sessionRecord: (sessionId: string) => {
      const record = deps.closePort.sessionRecord(sessionId);
      if (record === null) return null;
      if ('spec' in record && 'brief' in record) {
        // StoredSession: assemble the render record around it.
        return assembleRenderRecord(record, extras);
      }
      return record;
    },
  };
  const close = new SessionCloseService({ port: closePort, renderArtifact: render });

  return {
    permittedBrief,
    sessionId: settled.sessionId,
    chamberUrl: settled.chamberUrl,
    modeSelection,
    session: { ...settled.session, mode_selection: modeSelection },
    sitting: {
      status: (nowIso) => close.status(settled.sessionId, nowIso),
      tick: (nowIso) => close.tick(settled.sessionId, nowIso),
      handleClientMessage: (text, nowIso) =>
        close.handleClientMessage(settled.sessionId, text, nowIso),
    },
    finalize: async (reason, nowIso) => {
      const finalized = await close.finalize(settled.sessionId, reason, nowIso);
      const delivery =
        finalized.artifact === null
          ? null
          : {
              reply_link: finalized.artifact.link,
              chamber_url: settled.chamberUrl,
            };
      return { ...finalized, delivery };
    },
  };
}
