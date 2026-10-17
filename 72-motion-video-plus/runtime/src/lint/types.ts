// Types for the engine-aware lint layer (Directive MG-030).
//
// The legacy regex linter (scripts/lint-grammar.py) checks legacy
// __setTime scene files. This layer is its counterpart for new code: it
// parses TypeScript/JavaScript and Hyperframes HTML with the TypeScript
// compiler API and checks each source against the rules of the engine
// that will run it, instead of requiring window.__setTime everywhere.
//
// A report separates findings into named categories. One category is
// deliberately never produced by static analysis: visual audit. Static
// lint verifies code validity only. It does not verify choreography,
// font size, or semantic motion, so every report carries the visual
// audit status PENDING unless a caller attaches the path of a recorded
// visual audit produced by the review-evidence path (MG-031/MG-034),
// in which case the status is "recorded" and names that evidence. The
// static layer can never mint a visual pass.

/** The engines a source can be validated against. "legacy" is the V1
 * __setTime scene contract in references/animation-contract.md. */
export type LintEngine = "legacy" | "hyperframes" | "remotion";

export type FindingCategory =
  | "parser_error"
  | "prohibited_clock"
  | "dynamic_timer_usage"
  | "asset_readiness"
  | "composition_structure";

export interface LintFinding {
  category: FindingCategory;
  /** Short rule id inside the category, for example "timer-call". */
  rule: string;
  /** 1-based line in the original file. */
  line: number;
  /** 1-based column in the original file. */
  column: number;
  message: string;
}

export interface VisualAuditStatus {
  /** "pending": no visual audit has run. "recorded": a caller attached
   * evidence of one; the findings of that audit live in the evidence,
   * not in this report. Never "passed": static lint does not issue
   * visual verdicts. */
  status: "pending" | "recorded";
  /** Path of the recorded visual audit evidence, when recorded. */
  evidence: string | null;
  /** The standing honesty note, printed with every report. */
  note: string;
}

export const VISUAL_AUDIT_NOTE =
  "visual audit: PENDING (static lint verifies code validity only; " +
  "it does not verify choreography, font size, or semantic motion)";

export interface LintReport {
  engine: LintEngine;
  fileName: string;
  findings: LintFinding[];
  counts: Record<FindingCategory, number>;
  visualAudit: VisualAuditStatus;
  /** True when no finding blocks: the source is code-valid for its
   * engine. Says nothing about visual quality (see visualAudit). */
  pass: boolean;
}

export interface ValidateOptions {
  /** Path of a recorded visual audit (MG-031/MG-034 evidence) to attach
   * to the report. The lint layer records it; it does not read it. */
  visualAuditEvidence?: string;
}
