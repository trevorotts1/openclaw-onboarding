// Engine-aware source validation (Directive MG-030).
//
// Where the legacy linter regexes raw text, this layer parses each
// source with the TypeScript compiler API and walks the AST, so a
// timer named inside a string or a comment is not a finding, and a
// timer reached through computed access or an alias is. Rules follow
// the selected engine's contract (references/animation-contract.md,
// "Engine render rules"): the legacy engine requires window.__setTime
// and forbids GPU-layer tricks; Remotion requires frame-clock purity
// and forbids CSS transitions; Hyperframes requires a registered,
// paused, seekable timeline. No engine's rules are imposed on another.
//
// Findings are grouped in the categories from types.ts. The layer is a
// pure function of (engine, fileName, text): it reads no files, runs
// no renders, and never reports a visual verdict.

import * as ts from "typescript";
import { LineIndex, scanHtml, type HtmlChunk } from "./html";
import {
  VISUAL_AUDIT_NOTE,
  type FindingCategory,
  type LintEngine,
  type LintFinding,
  type LintReport,
  type ValidateOptions,
} from "./types";

const CLOCK_NAMES = new Set(["setTimeout", "setInterval", "requestAnimationFrame"]);
const GLOBAL_ROOTS = new Set(["window", "globalThis", "self"]);
const TIMER_FRAGMENTS = new Set(["set", "timeout", "interval", "requestanimationframe"]);
const CSS_ANIM_PROPS = new Map<string, "css-transition" | "css-animation">([
  ["transition", "css-transition"],
  ["transitionProperty", "css-transition"],
  ["transitionDuration", "css-transition"],
  ["transitionDelay", "css-transition"],
  ["animation", "css-animation"],
  ["animationName", "css-animation"],
  ["animationDuration", "css-animation"],
  ["animationDelay", "css-animation"],
]);

interface ParsedUnit {
  sf: ts.SourceFile;
  /** Byte offset of this unit's text inside the whole file. */
  baseOffset: number;
  parseOk: boolean;
}

interface ParsedDiagSource extends ts.SourceFile {
  parseDiagnostics?: ReadonlyArray<ts.DiagnosticWithLocation>;
}

function scriptKindFor(fileName: string): ts.ScriptKind {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (lower.endsWith(".ts")) return ts.ScriptKind.TS;
  if (lower.endsWith(".jsx")) return ts.ScriptKind.JSX;
  return ts.ScriptKind.JS;
}

function isGlobalRoot(expr: ts.Expression): boolean {
  return ts.isIdentifier(expr) && GLOBAL_ROOTS.has(expr.text);
}

function propertyNameText(name: ts.PropertyName): string | null {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return name.text;
  }
  return null;
}

/** Collect the string fragments of a `+` concatenation, flagging any
 * non-literal part as unknown. */
function concatFragments(
  expr: ts.Expression,
  out: string[],
  unknown: { flag: boolean }
): void {
  if (ts.isStringLiteral(expr)) {
    out.push(expr.text);
    return;
  }
  if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    concatFragments(expr.left, out, unknown);
    concatFragments(expr.right, out, unknown);
    return;
  }
  unknown.flag = true;
}

/** The clock named by an expression used as a value: a bare clock
 * identifier, a member access (`window.setTimeout`), or computed
 * access with a literal or concatenated clock name. */
function clockNameOfExpression(expr: ts.Expression | undefined): string | null {
  if (expr === undefined) return null;
  if (ts.isIdentifier(expr)) {
    return CLOCK_NAMES.has(expr.text) ? expr.text : null;
  }
  if (ts.isPropertyAccessExpression(expr)) {
    return CLOCK_NAMES.has(expr.name.text) ? expr.name.text : null;
  }
  if (ts.isElementAccessExpression(expr)) {
    const arg = expr.argumentExpression;
    if (ts.isStringLiteral(arg) && CLOCK_NAMES.has(arg.text)) return arg.text;
    if (ts.isBinaryExpression(arg)) {
      const fragments: string[] = [];
      const unknown = { flag: false };
      concatFragments(arg, fragments, unknown);
      const joined = fragments.join("");
      if (!unknown.flag && CLOCK_NAMES.has(joined)) return joined;
    }
  }
  return null;
}

/** Does this expression's access chain pass through a member with the
 * given name (for example any chain through __timelines)? */
function chainMentions(expr: ts.Expression, name: string): boolean {
  if (ts.isPropertyAccessExpression(expr)) {
    return expr.name.text === name || chainMentions(expr.expression, name);
  }
  if (ts.isElementAccessExpression(expr)) {
    return chainMentions(expr.expression, name);
  }
  return false;
}

export function validateSource(
  engine: LintEngine,
  fileName: string,
  text: string,
  options: ValidateOptions = {}
): LintReport {
  const lineIndex = new LineIndex(text);
  const findings: LintFinding[] = [];
  const add = (
    category: FindingCategory,
    rule: string,
    absoluteOffset: number,
    message: string
  ): void => {
    const { line, column } = lineIndex.lineCol(Math.max(0, absoluteOffset));
    findings.push({ category, rule, line, column, message });
  };

  const isHtml = /\.html?$/i.test(fileName);
  const units: ParsedUnit[] = [];
  const scriptChunks: HtmlChunk[] = [];
  let styleChunks: HtmlChunk[] = [];
  let htmlTags: ReturnType<typeof scanHtml>["tags"] = [];

  const parseUnit = (unitText: string, baseOffset: number, kind: ts.ScriptKind): ParsedUnit => {
    const sf = ts.createSourceFile(
      fileName,
      unitText,
      ts.ScriptTarget.ES2022,
      true,
      kind
    ) as ParsedDiagSource;
    const diags = sf.parseDiagnostics ?? [];
    for (const d of diags) {
      add(
        "parser_error",
        "parse",
        baseOffset + (d.start ?? 0),
        `source does not parse: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`
      );
    }
    return { sf, baseOffset, parseOk: diags.length === 0 };
  };

  if (isHtml) {
    const scan = scanHtml(text);
    htmlTags = scan.tags;
    for (const err of scan.errors) {
      add("parser_error", "html-structure", err.offset, err.message);
    }
    for (const chunk of scan.chunks) {
      if (chunk.kind === "script") scriptChunks.push(chunk);
      else styleChunks.push(chunk);
    }
    for (const chunk of scriptChunks) {
      units.push(parseUnit(chunk.text, chunk.contentOffset, ts.ScriptKind.JS));
    }
    // Tag-level asset readiness: a remote script, stylesheet, or image
    // is a network fetch the composition does not control.
    for (const tag of scan.tags) {
      if (tag.name !== "script" && tag.name !== "link" && tag.name !== "img") continue;
      for (const attr of tag.attrs) {
        if (attr.name !== "src" && attr.name !== "href") continue;
        const value = attr.value.trim();
        if (/^(https?:)?\/\//i.test(value)) {
          add(
            "asset_readiness",
            "remote-asset",
            attr.valueOffset,
            `<${tag.name}> loads ${attr.name} from the network (${value.split("/")[2] ?? "remote host"}): compositions must vendor assets locally so every asset is ready before frame 0`
          );
        }
      }
    }
    // CSS checks over style blocks and style attributes. CSS has no
    // string/comment ambiguity for these tokens in practice, and the
    // checks mirror the legacy linter's CSS determinism rules.
    const cssSources: Array<{ css: string; base: number }> = styleChunks.map((c) => ({
      css: c.text,
      base: c.contentOffset,
    }));
    for (const tag of scan.tags) {
      for (const attr of tag.attrs) {
        if (attr.name === "style") cssSources.push({ css: attr.value, base: attr.valueOffset });
      }
    }
    checkCss(engine, cssSources, add);
  } else {
    units.push(parseUnit(text, 0, scriptKindFor(fileName)));
  }

  // Per-unit AST checks.
  const assignedProps = new Set<string>();
  const timelineCalls: Array<{ node: ts.CallExpression; unit: ParsedUnit }> = [];
  let anyPauseCall = false;
  let timelineRegistration = false;

  for (const unit of units) {
    if (!unit.parseOk) continue;
    const aliases = collectAliases(unit.sf);
    visit(unit.sf, (node) => {
      // Record structural evidence.
      if (
        ts.isBinaryExpression(node) &&
        node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      ) {
        const left = node.left;
        if (ts.isPropertyAccessExpression(left)) {
          assignedProps.add(left.name.text);
          if (chainMentions(left, "__timelines")) timelineRegistration = true;
        } else if (ts.isElementAccessExpression(left)) {
          if (ts.isStringLiteral(left.argumentExpression)) {
            assignedProps.add(left.argumentExpression.text);
          }
          if (chainMentions(left, "__timelines")) timelineRegistration = true;
        }
        // element.style.transition = "..." style imperative CSS animation.
        if (
          ts.isPropertyAccessExpression(left) &&
          CSS_ANIM_PROPS.has(left.name.text) &&
          ts.isPropertyAccessExpression(left.expression) &&
          left.expression.name.text === "style"
        ) {
          const rule = CSS_ANIM_PROPS.get(left.name.text) as string;
          add(
            "composition_structure",
            rule,
            unit.baseOffset + left.name.getStart(unit.sf),
            `imperative style assignment sets ${left.name.text}: CSS ${rule === "css-transition" ? "transitions" : "animations"} run on the wall clock, so the same frame can paint differently depending on when it is sampled`
          );
        }
      }
      if (ts.isCallExpression(node)) {
        checkCall(node, unit, aliases, add);
        const callee = node.expression;
        if (ts.isPropertyAccessExpression(callee)) {
          if (callee.name.text === "timeline") timelineCalls.push({ node, unit });
          if (callee.name.text === "pause") anyPauseCall = true;
        }
      }
      if (ts.isNewExpression(node)) {
        const callee = node.expression;
        if (ts.isIdentifier(callee) && callee.text === "Function") {
          add(
            "dynamic_timer_usage",
            "dynamic-code",
            unit.baseOffset + callee.getStart(unit.sf),
            "the Function constructor builds code at runtime: its time behavior cannot be verified statically"
          );
        }
        if (ts.isIdentifier(callee) && callee.text === "XMLHttpRequest") {
          add(
            "asset_readiness",
            "network-xhr",
            unit.baseOffset + callee.getStart(unit.sf),
            "XMLHttpRequest fetches during the timeline: assets must be loaded before frame 0"
          );
        }
      }
      if (engine === "remotion" && ts.isPropertyAssignment(node)) {
        const name = propertyNameText(node.name);
        if (name !== null && CSS_ANIM_PROPS.has(name)) {
          const rule = CSS_ANIM_PROPS.get(name) as string;
          add(
            "composition_structure",
            rule,
            unit.baseOffset + node.name.getStart(unit.sf),
            `style property ${name}: CSS ${rule === "css-transition" ? "transitions" : "animations"} run on the wall clock; in Remotion every animated value must be a function of the frame number`
          );
        }
      }
    });
  }

  // Engine composition structure.
  const anyScriptUnit = units.length > 0;
  const allParsed = units.every((u) => u.parseOk);
  if (engine === "legacy" && (allParsed || !anyScriptUnit)) {
    const required: Array<[string, string, string]> = [
      [
        "__setTime",
        "missing-settime",
        "window.__setTime is not assigned: the legacy frame driver cannot render this scene (the requirement is this engine's, checked only for legacy sources)",
      ],
      [
        "__sceneDuration",
        "missing-scene-duration",
        "window.__sceneDuration is not assigned: the animation contract requires it to match the manifest duration",
      ],
      [
        "__choreography",
        "missing-choreography",
        "window.__choreography is not assigned: legacy scenes declare one intent and its behaviors (policy itself is enforced by scripts/lint-grammar.py)",
      ],
    ];
    for (const [prop, rule, message] of required) {
      if (!assignedProps.has(prop)) add("composition_structure", rule, 0, message);
    }
  }
  if (engine === "hyperframes" && isHtml) {
    const hasRoot = htmlTags.some((t) => t.attrs.some((a) => a.name === "data-composition-id"));
    if (!hasRoot) {
      add(
        "composition_structure",
        "missing-composition-root",
        0,
        "no element carries data-composition-id: a Hyperframes project root must declare its composition id, width, height, start, and duration"
      );
    }
  }
  if (engine === "hyperframes" && (allParsed || !anyScriptUnit)) {
    if (timelineCalls.length === 0) {
      add(
        "composition_structure",
        "missing-timeline",
        0,
        "no gsap.timeline is created: Hyperframes motion must live in a registered, seekable timeline the renderer steps deterministically"
      );
    } else {
      const pausedOk =
        anyPauseCall ||
        timelineCalls.some(({ node }) => {
          const first = node.arguments[0];
          if (first === undefined || !ts.isObjectLiteralExpression(first)) return false;
          return first.properties.some((p) => {
            if (!ts.isPropertyAssignment(p)) return false;
            return (
              propertyNameText(p.name) === "paused" &&
              p.initializer.kind === ts.SyntaxKind.TrueKeyword
            );
          });
        });
      if (!pausedOk) {
        const first = timelineCalls[0];
        add(
          "composition_structure",
          "timeline-not-paused",
          first.unit.baseOffset + first.node.getStart(first.unit.sf),
          "the GSAP timeline is not created paused and is never paused: an unpaused timeline runs on the wall clock instead of the renderer's frame steps"
        );
      }
    }
    if (!timelineRegistration) {
      add(
        "composition_structure",
        "missing-timeline-registration",
        0,
        "the timeline is never registered on window.__timelines: the Hyperframes renderer steps timelines it finds registered under their composition id"
      );
    }
  }

  const counts: Record<FindingCategory, number> = {
    parser_error: 0,
    prohibited_clock: 0,
    dynamic_timer_usage: 0,
    asset_readiness: 0,
    composition_structure: 0,
  };
  for (const f of findings) counts[f.category] += 1;

  const recorded = options.visualAuditEvidence !== undefined;
  return {
    engine,
    fileName,
    findings,
    counts,
    visualAudit: {
      status: recorded ? "recorded" : "pending",
      evidence: options.visualAuditEvidence ?? null,
      note: recorded
        ? `visual audit: RECORDED in ${options.visualAuditEvidence} (static lint verifies code validity only; it does not verify choreography, font size, or semantic motion)`
        : VISUAL_AUDIT_NOTE,
    },
    pass: findings.length === 0,
  };
}

function visit(node: ts.Node, cb: (node: ts.Node) => void): void {
  cb(node);
  node.forEachChild((child) => visit(child, cb));
}

/** Names bound to a clock through anything but the clock's own name:
 * renamed aliases are the dynamic case. A binding that keeps the
 * clock's own name is not recorded: calls through that name are direct
 * clock calls, exactly as the legacy linter treats them. */
function collectAliases(sf: ts.SourceFile): Map<string, string> {
  const aliases = new Map<string, string>();
  visit(sf, (node) => {
    if (ts.isVariableDeclaration(node)) {
      if (ts.isObjectBindingPattern(node.name)) {
        // Destructuring: the binding element's source name is the
        // evidence, whatever object it is destructured from.
        for (const el of node.name.elements) {
          if (!ts.isBindingElement(el) || !ts.isIdentifier(el.name)) continue;
          const source =
            el.propertyName !== undefined ? propertyNameText(el.propertyName) : el.name.text;
          if (source !== null && CLOCK_NAMES.has(source) && el.name.text !== source) {
            aliases.set(el.name.text, source);
          }
        }
      } else if (node.initializer !== undefined && ts.isIdentifier(node.name)) {
        const clock = clockNameOfExpression(node.initializer);
        if (clock !== null && node.name.text !== clock) {
          aliases.set(node.name.text, clock);
        }
      }
    }
    if (ts.isImportDeclaration(node) && node.importClause?.namedBindings !== undefined) {
      const bindings = node.importClause.namedBindings;
      if (ts.isNamedImports(bindings)) {
        for (const spec of bindings.elements) {
          const imported =
            spec.propertyName !== undefined ? propertyNameText(spec.propertyName) : spec.name.text;
          if (imported !== null && CLOCK_NAMES.has(imported) && spec.name.text !== imported) {
            aliases.set(spec.name.text, imported);
          }
        }
      }
    }
  });
  return aliases;
}

function checkCall(
  node: ts.CallExpression,
  unit: ParsedUnit,
  aliases: Map<string, string>,
  add: (
    category: FindingCategory,
    rule: string,
    absoluteOffset: number,
    message: string
  ) => void
): void {
  const callee = node.expression;
  const at = (n: ts.Node) => unit.baseOffset + n.getStart(unit.sf);

  if (callee.kind === ts.SyntaxKind.ImportKeyword) {
    const arg = node.arguments[0];
    const spec = arg !== undefined && ts.isStringLiteral(arg) ? ` "${arg.text}"` : "";
    add(
      "asset_readiness",
      "dynamic-import",
      at(callee),
      `dynamic import${spec} loads code at runtime: scene assets and code must be in place before frame 0, not fetched during the timeline`
    );
    return;
  }

  if (ts.isIdentifier(callee)) {
    const name = callee.text;
    if (CLOCK_NAMES.has(name)) {
      add(
        "prohibited_clock",
        name === "requestAnimationFrame" ? "raf-call" : "timer-call",
        at(callee),
        `${name} call: the frame clock owns time on every engine; the page must not advance itself`
      );
      return;
    }
    const aliasOf = aliases.get(name);
    if (aliasOf !== undefined) {
      add(
        "dynamic_timer_usage",
        "aliased-timer",
        at(callee),
        `call through the alias ${name} (bound to ${aliasOf}): a renamed timer is still a timer, and static analysis flags the alias rather than letting the rename pass it`
      );
      return;
    }
    if (name === "eval") {
      add(
        "dynamic_timer_usage",
        "dynamic-code",
        at(callee),
        "eval executes code built at runtime: its time behavior cannot be verified statically"
      );
      return;
    }
    if (name === "Function") {
      add(
        "dynamic_timer_usage",
        "dynamic-code",
        at(callee),
        "the Function constructor builds code at runtime: its time behavior cannot be verified statically"
      );
      return;
    }
    if (name === "fetch") {
      add(
        "asset_readiness",
        "network-fetch",
        at(callee),
        "fetch during the timeline: assets must be loaded before frame 0, not requested while frames render"
      );
    }
    return;
  }

  if (ts.isPropertyAccessExpression(callee)) {
    const name = callee.name.text;
    if (CLOCK_NAMES.has(name) && isGlobalRoot(callee.expression)) {
      add(
        "prohibited_clock",
        name === "requestAnimationFrame" ? "raf-call" : "timer-call",
        at(callee.name),
        `${name} call: the frame clock owns time on every engine; the page must not advance itself`
      );
      return;
    }
    if (name === "now") {
      const obj = callee.expression;
      const isDate = ts.isIdentifier(obj) && obj.text === "Date";
      const isPerformance =
        (ts.isIdentifier(obj) && obj.text === "performance") ||
        (ts.isPropertyAccessExpression(obj) && obj.name.text === "performance");
      if (isDate || isPerformance) {
        add(
          "prohibited_clock",
          "wall-clock-now",
          at(callee.name),
          `${isDate ? "Date.now" : "performance.now"} reads the wall clock: a frame must be a pure function of its frame number, not of when it happens to render`
        );
        return;
      }
    }
    if (name === "random" && ts.isIdentifier(callee.expression) && callee.expression.text === "Math") {
      add(
        "prohibited_clock",
        "unseeded-random",
        at(callee.name),
        "Math.random is unseeded: the same frame must render identically on every pass, so randomness must be seeded from the frame or time value"
      );
      return;
    }
    if (name === "fetch" && isGlobalRoot(callee.expression)) {
      add(
        "asset_readiness",
        "network-fetch",
        at(callee.name),
        "fetch during the timeline: assets must be loaded before frame 0, not requested while frames render"
      );
      return;
    }
    if (name === "eval" && isGlobalRoot(callee.expression)) {
      add(
        "dynamic_timer_usage",
        "dynamic-code",
        at(callee.name),
        "eval executes code built at runtime: its time behavior cannot be verified statically"
      );
    }
    return;
  }

  if (ts.isElementAccessExpression(callee)) {
    const arg = callee.argumentExpression;
    if (ts.isStringLiteral(arg) && CLOCK_NAMES.has(arg.text)) {
      add(
        "dynamic_timer_usage",
        "computed-timer-access",
        at(callee),
        `timer reached by computed access (${arg.text} in brackets): renaming the access does not rename the clock`
      );
      return;
    }
    if (ts.isBinaryExpression(arg)) {
      const fragments: string[] = [];
      const unknown = { flag: false };
      concatFragments(arg, fragments, unknown);
      const joined = fragments.join("");
      if (
        CLOCK_NAMES.has(joined) ||
        fragments.some((f) => TIMER_FRAGMENTS.has(f.toLowerCase()))
      ) {
        add(
          "dynamic_timer_usage",
          "computed-timer-access",
          at(callee),
          "timer reached by concatenated computed access: the name is assembled at runtime, so static analysis flags the construction rather than guessing the result"
        );
        return;
      }
    }
    if (isGlobalRoot(callee.expression)) {
      add(
        "dynamic_timer_usage",
        "computed-timer-access",
        at(callee),
        "a member of the global object is called through a computed name: static analysis cannot prove the member is not a timer, so the call is flagged as dynamic"
      );
    }
  }
}

const CSS_CHECKS: Array<{
  rule: "css-transition" | "css-animation" | "gpu-layer";
  re: RegExp;
  engines: LintEngine[];
  message: string;
}> = [
  {
    rule: "css-transition",
    re: /(?<![-a-zA-Z])transition\s*:/g,
    engines: ["legacy", "hyperframes"],
    message:
      "CSS transition in a style block: transitions run on the wall clock, outside any frame clock or registered timeline",
  },
  {
    rule: "css-animation",
    re: /@keyframes\b/g,
    engines: ["legacy", "hyperframes"],
    message:
      "CSS @keyframes in a style block: keyframe animation runs on the wall clock, outside any frame clock or registered timeline",
  },
  {
    rule: "css-animation",
    re: /(?<![-a-zA-Z])animation\s*:/g,
    engines: ["legacy", "hyperframes"],
    message:
      "CSS animation in a style block: animation runs on the wall clock, outside any frame clock or registered timeline",
  },
  {
    rule: "gpu-layer",
    re: /translate3d\s*\(|translateZ\s*\(\s*0|will-change\s*:/g,
    engines: ["legacy"],
    message:
      "GPU-layer trick in a style block (translate3d, translateZ(0), or will-change): composited layers cache rasters, so one t can paint differently depending on the previous frame (legacy engine rule)",
  },
];

function checkCss(
  engine: LintEngine,
  sources: Array<{ css: string; base: number }>,
  add: (
    category: FindingCategory,
    rule: string,
    absoluteOffset: number,
    message: string
  ) => void
): void {
  for (const { css, base } of sources) {
    for (const check of CSS_CHECKS) {
      if (!check.engines.includes(engine)) continue;
      check.re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = check.re.exec(css)) !== null) {
        add("composition_structure", check.rule, base + m.index, check.message);
      }
    }
  }
}

/** Human-readable rendering of a report, in the spirit of the legacy
 * linter's output: one line per finding, then the standing visual
 * audit line, then the result. The result line never claims more than
 * code validity. */
export function formatReport(report: LintReport): string {
  const lines: string[] = [];
  lines.push(`LINT ${report.fileName} (engine: ${report.engine})`);
  for (const f of report.findings) {
    lines.push(
      `FINDING [${f.category}/${f.rule}] line ${f.line}, column ${f.column}: ${f.message}`
    );
  }
  lines.push(report.visualAudit.note);
  if (report.pass) {
    lines.push("RESULT: PASS (code validity only; visual audit has not run)");
  } else {
    lines.push(
      `RESULT: FAIL (${report.findings.length} finding(s); code validity only, visual audit has not run)`
    );
  }
  return lines.join("\n");
}
