// Lint tests for MG-030 (Directive Section 15 MG-030, defect D-LINT-TIMER).
//
// Three proofs, all offline and deterministic:
// 1. Parity corpus: the fixtures under tests/fixtures/lint are run
//    through BOTH the shipped Python linter (scripts/lint-grammar.py,
//    whose input contract is legacy scene HTML) and the TypeScript
//    validation layer (runtime/src/lint), and both must produce the
//    verdicts recorded in tests/evidence/mg030/verdicts.json. The
//    corpus isolates the D-LINT-TIMER shapes: a real setTimeout fails,
//    the same text in a string or a comment passes, and a timer reached
//    by computed access or by alias fails as dynamic in both layers.
// 2. Engine contracts: valid Hyperframes and Remotion sources pass
//    their own engine's checks in the TS layer, and each invalid
//    fixture fails in exactly its named category. The shipped
//    choreography pass fixtures also validate clean as legacy sources.
// 3. Honesty: every report states that the visual audit is PENDING and
//    that static lint does not verify choreography, font size, or
//    semantic motion; attaching recorded visual evidence changes the
//    status wording to RECORDED and never changes a finding.
//
// Exit code 0 when every case passes, 1 otherwise.

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { formatReport, validateSource, type LintEngine } from "../src/lint";

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  if (!ok && detail) console.log(`  ${detail}`);
}

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function skillRoot(): string {
  return resolve(fixturesRoot(), "..", "..");
}

function readFixture(dir: string, name: string): string {
  const path = join(fixturesRoot(), dir, name);
  if (!existsSync(path)) throw new Error(`missing fixture ${path}`);
  return readFileSync(path, "utf8");
}

interface FixtureExpectation {
  file: string;
  engine: LintEngine;
  python: { exit: number; ids: string[] } | null;
  ts: { pass: boolean; categories: string[]; rules?: string[] };
}

function sortedUnique(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function sameSet(a: string[], b: string[]): boolean {
  const sa = sortedUnique(a);
  const sb = sortedUnique(b);
  return sa.length === sb.length && sa.every((v, i) => v === sb[i]);
}

// ---------------------------------------------------------------------
// 1. Parity corpus against the recorded verdicts.
// ---------------------------------------------------------------------
{
  const record = JSON.parse(
    readFileSync(join(skillRoot(), "tests", "evidence", "mg030", "verdicts.json"), "utf8")
  ) as { fixtures: FixtureExpectation[] };
  const linter = join(skillRoot(), "scripts", "lint-grammar.py");

  for (const fx of record.fixtures) {
    const text = readFixture("lint", fx.file);
    const tsReport = validateSource(fx.engine, fx.file, text);
    const tsCategories = sortedUnique(tsReport.findings.map((f) => f.category));
    report(
      tsReport.pass === fx.ts.pass && sameSet(tsCategories, fx.ts.categories),
      `${fx.file}: TS layer verdict matches the record (pass=${fx.ts.pass}, categories=${fx.ts.categories.join("|") || "none"})`,
      `got pass=${tsReport.pass}, categories=${tsCategories.join("|") || "none"}; findings=${JSON.stringify(tsReport.findings)}`
    );
    if (fx.ts.rules !== undefined) {
      const tsRules = sortedUnique(tsReport.findings.map((f) => f.rule));
      report(
        sameSet(tsRules, fx.ts.rules),
        `${fx.file}: TS rule set is exactly ${fx.ts.rules.join(", ")}`,
        `got ${tsRules.join(", ")}`
      );
    }
    if (fx.python !== null) {
      const proc = spawnSync("python3", [linter, join(fixturesRoot(), "lint", fx.file)], {
        encoding: "utf8",
      });
      const ids = sortedUnique(
        [...proc.stdout.matchAll(/VIOLATION \[([a-z-]+)\]/g)].map((m) => m[1])
      );
      report(
        proc.status === fx.python.exit && sameSet(ids, fx.python.ids),
        `${fx.file}: Python linter verdict matches the record (exit=${fx.python.exit}, ids=${fx.python.ids.join("|") || "none"})`,
        `got exit=${proc.status}, ids=${ids.join("|") || "none"}; stdout=${proc.stdout.trim()}`
      );
      // Cross-layer agreement, not just agreement with the record:
      // the two implementations must classify the same source alike.
      const pyClock = ids.includes("timer");
      const tsClock = tsReport.findings.some((f) => f.category === "prohibited_clock");
      const pyDynamic = ids.includes("dynamic-timer");
      const tsDynamic = tsReport.findings.some((f) => f.category === "dynamic_timer_usage");
      report(
        pyClock === tsClock && pyDynamic === tsDynamic && (proc.status === 0) === tsReport.pass,
        `${fx.file}: Python and TS layers agree with each other`,
        `python exit=${proc.status} ids=${ids.join("|")}; ts pass=${tsReport.pass}`
      );
    }
  }
}

// ---------------------------------------------------------------------
// 2. Shipped choreography pass fixtures validate clean as legacy.
// ---------------------------------------------------------------------
{
  for (const name of [
    "pass-linear-chart.html",
    "pass-dissolve.html",
    "pass-presenter-hold.html",
    "pass-depth.html",
  ]) {
    const text = readFixture("choreography", name);
    const result = validateSource("legacy", name, text);
    report(
      result.pass,
      `legacy TS validation is clean on the shipped fixture ${name}`,
      JSON.stringify(result.findings)
    );
  }
}

// ---------------------------------------------------------------------
// 3. Inline cases: the classification rules in miniature.
// ---------------------------------------------------------------------
{
  const remotionCases: Array<{
    name: string;
    source: string;
    categories: string[];
  }> = [
    {
      name: "a timer named in a string literal passes",
      source: 'export const note = "setTimeout(fn, 400) is forbidden here";\n',
      categories: [],
    },
    {
      name: "a timer named in a comment passes",
      source: "// setTimeout(fn, 400) must never advance this scene\nexport const x = 1;\n",
      categories: [],
    },
    {
      name: "Date.now is a prohibited wall clock",
      source: "export const now = Date.now();\n",
      categories: ["prohibited_clock"],
    },
    {
      name: "performance.now is a prohibited wall clock",
      source: "export const now = performance.now();\n",
      categories: ["prohibited_clock"],
    },
    {
      name: "Math.random is a prohibited unseeded source",
      source: "export const r = Math.random();\n",
      categories: ["prohibited_clock"],
    },
    {
      name: "window.setInterval by member access is a direct timer",
      source: "export function f(): void { window.setInterval(function () {}, 5); }\n",
      categories: ["prohibited_clock"],
    },
    {
      name: "a timer reached by literal computed access is dynamic",
      source: 'export function f(): void { window["setInterval"](function () {}, 5); }\n',
      categories: ["dynamic_timer_usage"],
    },
    {
      name: "a timer reached through a destructured alias is dynamic",
      source:
        "const { setTimeout: st } = window;\nexport function f(): void { st(function () {}, 5); }\n",
      categories: ["dynamic_timer_usage"],
    },
    {
      name: "a timer called by its own destructured name stays direct",
      source:
        "const { setTimeout } = window;\nexport function f(): void { setTimeout(function () {}, 5); }\n",
      categories: ["prohibited_clock"],
    },
    {
      name: "a timer reached through an imported alias is dynamic",
      source:
        'import { setTimeout as st } from "node:timers";\nexport function f(): void { st(function () {}, 5); }\n',
      categories: ["dynamic_timer_usage"],
    },
    {
      name: "eval is dynamic code",
      source: 'export function f(): void { eval("1 + 1"); }\n',
      categories: ["dynamic_timer_usage"],
    },
  ];
  for (const c of remotionCases) {
    const result = validateSource("remotion", "inline.ts", c.source);
    const categories = sortedUnique(result.findings.map((f) => f.category));
    report(
      sameSet(categories, c.categories),
      `inline remotion: ${c.name}`,
      `expected categories ${c.categories.join("|") || "none"}, got ${categories.join("|") || "none"}; findings=${JSON.stringify(result.findings)}`
    );
  }

  const legacyMissing = validateSource(
    "legacy",
    "inline.html",
    "<!DOCTYPE html>\n<html><body><script>\nvar x = 1;\n</script></body></html>\n"
  );
  const legacyRules = sortedUnique(legacyMissing.findings.map((f) => f.rule));
  report(
    !legacyMissing.pass &&
      sameSet(legacyRules, [
        "missing-choreography",
        "missing-scene-duration",
        "missing-settime",
      ]),
    "inline legacy: a scene with no driver hooks fails on exactly the three missing-structure rules",
    `got rules ${legacyRules.join(", ")}`
  );

  const hfNoRegistration = validateSource(
    "hyperframes",
    "inline.html",
    [
      "<!DOCTYPE html>",
      "<html><body>",
      '<div data-composition-id="x" data-width="1920" data-height="1080"></div>',
      "<script>",
      "const tl = gsap.timeline({ paused: true });",
      "</script>",
      "</body></html>",
    ].join("\n")
  );
  const hfRules = sortedUnique(hfNoRegistration.findings.map((f) => f.rule));
  report(
    !hfNoRegistration.pass && sameSet(hfRules, ["missing-timeline-registration"]),
    "inline hyperframes: a paused but unregistered timeline fails on exactly the registration rule",
    `got rules ${hfRules.join(", ")}`
  );
}

// ---------------------------------------------------------------------
// 4. Report honesty: the visual audit is never minted by static lint.
// ---------------------------------------------------------------------
{
  const clean = validateSource("remotion", "remotion-pass.tsx", readFixture("lint", "remotion-pass.tsx"));
  const dirty = validateSource("remotion", "remotion-fail-clock.tsx", readFixture("lint", "remotion-fail-clock.tsx"));
  for (const [label, result] of [
    ["clean", clean],
    ["dirty", dirty],
  ] as const) {
    const formatted = formatReport(result);
    report(
      result.visualAudit.status === "pending" &&
        result.visualAudit.evidence === null &&
        formatted.includes("visual audit: PENDING") &&
        formatted.includes("does not verify choreography, font size, or semantic motion"),
      `report honesty (${label}): visual audit is PENDING and the report says what lint does not prove`,
      formatted
    );
  }
  const withEvidence = validateSource("remotion", "remotion-pass.tsx", readFixture("lint", "remotion-pass.tsx"), {
    visualAuditEvidence: "tests/evidence/mg031/coverage.json",
  });
  report(
    withEvidence.visualAudit.status === "recorded" &&
      withEvidence.visualAudit.evidence === "tests/evidence/mg031/coverage.json" &&
      withEvidence.findings.length === clean.findings.length &&
      withEvidence.pass === clean.pass &&
      formatReport(withEvidence).includes("RECORDED"),
    "report honesty: attaching recorded visual evidence marks the audit RECORDED and changes no finding",
    formatReport(withEvidence)
  );
}

// ---------------------------------------------------------------------
// 5. The shipped Python pattern is the fixed one (mirror of the
//    Python-side pin in tests/unit/test_choreography.py).
// ---------------------------------------------------------------------
{
  const source = readFileSync(join(skillRoot(), "scripts", "lint-grammar.py"), "utf8");
  report(
    source.includes("\\bset(Timeout|Interval)\\s*\\(") &&
      !source.includes("\\bset(TimeOut|Interval)"),
    "lint-grammar.py carries the fixed timer pattern and not the D-LINT-TIMER defect"
  );
}

console.log(`Lint: ${passed}/${passed + failed} checks passed, ${failed} failed.`);
process.exit(failed === 0 ? 0 : 1);
