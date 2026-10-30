/**
 * Deterministic renderers for the registered report formats
 * (CWE-038, directive Sections 24.1 to 24.3; CTR-146 reader pass).
 *
 * All renderers consume the one report model and nothing else: no
 * second model rewrite per format, no clock, no randomness, no locale
 * dependence. The same model always renders to the same bytes, which
 * is what makes the formats agree on scores, decisions, conditions,
 * citations, and report revision (test contract T105).
 *
 * CTR-146 changes the READER surface, not the data. CTR-154 corrects this
 * comment to match the order CTR-150 actually renders (the old text still
 * described the CTR-146 order):
 * - the print document (the PDF's source) opens with a plain-language
 *   summary, then the question, the ordered plan, how you will know it
 *   worked, how to use the report, and the installed helpers that fit the
 *   plan; Part 2 then holds the options, each advisor, the debate, the
 *   conditions and amendments, the sources, and the records;
 * - a consult report has no plan, debate, or nine-seat record: it prints
 *   the one recorded seat, its answer, assumptions, limits, and next step,
 *   then how to use it, the installed helpers, the sources, and the
 *   records;
 * - every printable character is at least 14pt, including tables,
 *   footnotes, and the page number. There is no hidden small print and
 *   no shrink-to-fit trick: wide tables are replaced by stacked blocks;
 * - section headings are common-sense language, and technical
 *   identifiers (session id, revisions, hashes) live only in the final
 *   "For your records" block;
 * - the cover band exposes the nine served chamber portraits in the
 *   shared seat order (CTR-150); the empty-table hero is not printed.
 *
 * CTR-150 changes the print LAYOUT, not the saved record:
 * - the cover is the exact nine served chamber portraits in the shared
 *   seat order (3 x 3), composed from `public/chamber/portraits`; the
 *   empty-table `assets/seats/cover.png` is never printed;
 * - the repeating KIE page-frame plate and the 24 mm section divider are
 *   removed from running pages. They were painted from the continuous
 *   body box, so their 297 mm tile drifted against the physical page and
 *   landed on top of live text. Restrained gold rules and cream callouts
 *   carry the brand instead;
 * - the main report is summary -> question -> plan -> review -> how to
 *   use -> installed help, and the long advisor/option/debate record is
 *   Part 2 behind one explicit page break. Nothing is truncated and no
 *   saved value is rewritten; the same sections are only reordered and
 *   de-duplicated by exact text;
 * - long cards may split across pages. `break-inside: avoid` is kept
 *   only on small units (labels, glance tiles, the read map), so a tall
 *   advisor card no longer leaves a half-empty page;
 * - section headings, their one-line reader cue and the first block stay
 *   together; a heading is never printed alone at the foot of a page;
 * - white reading pages, cream callouts, ink text, 20-22 mm side margins,
 *   15pt body and a 14pt floor everywhere, including page numbers.
 *
 * The print document stays offline and deterministic: one embedded
 * style block, no scripts, no network references, every generated string
 * HTML-escaped.
 */

import { canonicalStringify, sha256Hex } from '../contracts/index.js';
import {
  loadReportPortraitDataUri,
  REPORT_SEAT_PORTRAITS,
} from './asset-embed.js';
import { PDF_MISSING_PIECE } from './registry.js';

export function sha256OfText(text: string): string {
  return sha256Hex(new TextEncoder().encode(text));
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function asRecord(value: unknown): Record<string, unknown> {
  return value as Record<string, unknown>;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asStringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

/**
 * A consult report is present when `model.consult` is a defined value. Both
 * `null` and `undefined` mean "no consult": older saved report models
 * simply omit the field, so treating only `null` as absent flipped an
 * omitted field into the consult reading guide with no consult section.
 * The model builder emits either the consult object or no field at all, so
 * this looser check matches every live record.
 */
function isConsultModel(model: Record<string, unknown>): boolean {
  const consult = model.consult;
  return consult !== null && consult !== undefined;
}

/** Full-precision score, trimmed deterministically for display. */
export function formatScore(score: number | null): string {
  if (score === null) return 'not scored';
  return String(Number(score.toFixed(4)));
}

export function formatDisplayScore(display: number | null): string {
  if (display === null) return 'not scored';
  return display.toFixed(1);
}

export function formatCoverage(coverage: number | null): string {
  if (coverage === null) return 'n/a';
  return `${(coverage * 100).toFixed(2)}%`;
}

function formatPlainNumber(value: number | null): string {
  if (value === null) return 'n/a';
  return String(Number(value.toFixed(4)));
}

function qualificationText(value: unknown): string {
  return typeof value === 'string' ? value : 'not recorded';
}

/** Reader-facing qualification line; keeps the recorded token verbatim. */
function qualificationSentence(value: unknown): string {
  const raw = qualificationText(value);
  if (raw === 'bibliographic_only') {
    return 'bibliographic_only — built from published bibliographic sources; it is not a verified practitioner record';
  }
  if (raw === 'not recorded') return 'not recorded';
  return raw;
}

// ---------------------------------------------------------------------
// Markdown
// ---------------------------------------------------------------------

function mdList(items: unknown[]): string[] {
  return items.map((item) => `- ${asString(item)}`);
}

export function renderMarkdown(model: Record<string, unknown>): string {
  const verdict = asRecord(model.verdict_block);
  const brief = asRecord(model.brief);
  const summary = asRecord(model.summary ?? {});
  const context = asRecord(model.question_and_context ?? {});
  const debate = asRecord(model.debate ?? {});
  const plan = asRecord(model.plan ?? {});
  const tools = asRecord(model.your_tools ?? {});
  const lines: string[] = [];
  lines.push('# Council of Wise Elders: Decision Report');
  lines.push('');
  lines.push(`Decision: ${asString(model.decision_title)}`);
  lines.push(`Date: ${asString(model.report_date)}`);
  if (model.redacted === true) {
    lines.push(`Redacted report: yes (profile ${asString(model.redaction_profile_id)})`);
  }
  if (model.sample === true) {
    lines.push('Sample session: SAMPLE');
  }
  lines.push('');
  lines.push(`> ${asString(model.simulation_label)}`);
  lines.push('');
  lines.push(`> ${asString(model.authorization_notice)}`);
  if (model.sample === true) {
    lines.push('');
    lines.push(`> ${asString(model.sample_notice)}`);
  }
  lines.push('');

  const consult = model.consult as Record<string, unknown> | null;
  if (consult) {
    lines.push('## In short');
    lines.push('');
    lines.push(asString(summary.in_short));
    lines.push('');
    lines.push('## The question');
    lines.push('');
    lines.push(asString(context.question) || asString(model.decision_title));
    lines.push('');
    lines.push('## The consultation answer');
    lines.push('');
    lines.push(`${asString(consult.display_name)}: ${asString(consult.label)}`);
    lines.push('');
    lines.push(asString(consult.answer));
    lines.push('');
    lines.push('Assumptions:');
    lines.push(...mdList(asArray(consult.assumptions)));
    lines.push('');
    lines.push('Limits:');
    lines.push(...mdList(asArray(consult.limits)));
    lines.push('');
    lines.push(`Next step: ${asString(consult.next_step)}`);
    lines.push('');
    pushHowToUseMd(lines, model);
    pushToolsMd(lines, model);
    pushWebTodayMd(lines, model);
    pushProvenanceMd(lines, model);
    pushReportRecordMd(lines, model);
    return `${lines.join('\n')}\n`;
  }

  lines.push('## In short');
  lines.push('');
  lines.push(asString(summary.in_short));
  lines.push('');
  lines.push(`Verdict: ${asString(verdict.label)}`);
  const recommended = asStringOrNull(verdict.recommended_option_id);
  lines.push(
    `Recommendation: ${
      recommended === null
        ? 'none'
        : `${recommended} (${asString(verdict.recommended_option_label)})`
    }`,
  );
  if (asStringOrNull(summary.ratification_text) !== null) {
    lines.push(asString(summary.ratification_text));
  }
  lines.push('');
  lines.push('Why:');
  const reasons = asArray(summary.reasons);
  lines.push(...(reasons.length > 0 ? mdList(reasons) : ['- none recorded']));
  lines.push('');
  lines.push(
    `Biggest concern: ${asStringOrNull(summary.biggest_concern) ?? 'none recorded'}`,
  );
  lines.push('');
  // CTR-158: the Markdown production export carries the same readiness and
  // information-needed reader fields as the HTML export, from the one shared
  // projection. Dropping them here loses user-critical status.
  pushReadinessMd(lines, model);
  pushInformationMd(lines, model);

  lines.push('## The question');
  lines.push('');
  lines.push(`Question: ${asString(context.question) || asString(model.decision_title)}`);
  lines.push('');
  lines.push('Facts recorded in the brief:');
  const facts = asArray(context.facts);
  if (facts.length === 0) lines.push('- none recorded');
  for (const factValue of facts) {
    const fact = asRecord(factValue);
    const evidence = asArray(fact.evidence_ids).map(asString);
    lines.push(
      `- ${asString(fact.statement)}${evidence.length > 0 ? ` (evidence: ${evidence.join(', ')})` : ''}`,
    );
  }
  lines.push('');
  lines.push('Assumptions:');
  const assumptions = asArray(context.assumptions);
  lines.push(...(assumptions.length > 0 ? mdList(assumptions) : ['- none recorded']));
  lines.push('');
  lines.push('Unknowns:');
  const unknowns = asArray(context.unknowns);
  lines.push(...(unknowns.length > 0 ? mdList(unknowns) : ['- none recorded']));
  // CTR-158: where the question section's list is de-duplicated, state the
  // recorded total, the distinct rows shown, and the collapse note.
  const unknownsNote = asStringOrNull(context.unknowns_note);
  if (unknownsNote !== null) {
    const recorded = asNumberOrNull(context.unknowns_count) ?? unknowns.length;
    const shown = asNumberOrNull(context.unknowns_shown) ?? unknowns.length;
    lines.push(`- ${recorded} recorded; ${shown} distinct shown. ${unknownsNote}`);
  }
  lines.push('');
  const constraints = asArray(context.constraints);
  if (constraints.length > 0) {
    lines.push('Constraints:');
    for (const constraintValue of constraints) {
      const constraint = asRecord(constraintValue);
      const applies = asArray(constraint.applies_to_option_labels).map(asString);
      lines.push(
        `- ${asString(constraint.description)} (${constraint.hard === true ? 'hard constraint' : 'guideline'}${applies.length > 0 ? `; applies to: ${applies.join(', ')}` : ''})`,
      );
    }
    lines.push('');
  }

  lines.push('## Options and scores');
  lines.push('');
  lines.push(
    '| Option | Weighted sum | Denominator | Score | Display score | Coverage | Spread | Abstentions |',
  );
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- |');
  for (const rowValue of asArray(model.score_table)) {
    const row = asRecord(rowValue);
    const abstained = asArray(row.abstained_seat_ids).map(asString).join(', ') || 'none';
    lines.push(
      `| ${asString(row.option_id)} (${asString(row.option_label)}) | ${formatPlainNumber(asNumberOrNull(row.weighted_sum))} | ${formatPlainNumber(asNumberOrNull(row.denominator))} | ${formatScore(asNumberOrNull(row.score))} | ${formatDisplayScore(asNumberOrNull(row.display_score))} | ${formatCoverage(asNumberOrNull(row.coverage))} | ${formatPlainNumber(asNumberOrNull(row.spread))} | ${abstained} |`,
    );
  }
  lines.push('');

  lines.push('## What each advisor said');
  lines.push('');
  pushParticipatingSeatsMd(lines, model);
  pushAdvisorContributionsMd(lines, model);

  lines.push('## How the debate went');
  lines.push('');
  lines.push(
    `Rounds of advisor cards saved: ${String(asNumberOrNull(debate.rounds_saved) ?? 0)}`,
  );
  for (const note of asArray(debate.notes)) lines.push(`- ${asString(note)}`);
  lines.push('');
  const roundEntries = asArray(debate.rounds);
  for (const roundValue of roundEntries) {
    const round = asRecord(roundValue);
    lines.push(`Round ${String(asNumberOrNull(round.round) ?? '?')}:`);
    for (const seatValue of asArray(round.seats)) {
      const seat = asRecord(seatValue);
      lines.push(
        `- ${asString(seat.display_name)} ${asString(seat.stance_text)}${asStringOrNull(seat.preferred_option_label) === null ? '' : `; preferred ${asString(seat.preferred_option_label)}`}.`,
      );
    }
    lines.push('');
  }
  const changes = asArray(debate.changes);
  if (changes.length > 0) {
    lines.push('Changed between rounds:');
    for (const changeValue of changes) {
      const change = asRecord(changeValue);
      lines.push(
        `- Round ${String(asNumberOrNull(change.round) ?? '?')}: ${asString(change.display_name)} moved from ${asString(change.from_stance_text)} to ${asString(change.to_stance_text)}${asStringOrNull(change.from_option_label) === asStringOrNull(change.to_option_label) ? '' : `; preferred option ${asStringOrNull(change.from_option_label) ?? 'none'} to ${asStringOrNull(change.to_option_label) ?? 'none'}`}.`,
      );
    }
    lines.push('');
  }
  const positions = asArray(debate.positions);
  if (positions.length > 0) {
    lines.push('Where they stood on the preferred option:');
    for (const positionValue of positions) {
      const position = asRecord(positionValue);
      lines.push(
        `- ${asString(position.option_label)}: ${asArray(position.seat_names).map(asString).join(', ')}`,
      );
    }
    lines.push('');
  }

  lines.push('## Your plan');
  lines.push('');
  const steps = asArray(plan.steps);
  // CTR-158: the Markdown export carries the same recorded start action and
  // the same honest parallel/dependency notes as the HTML export.
  const startNumber = asNumberOrNull(plan.start_here_step_number);
  if (startNumber !== null) {
    const startStep = steps
      .map((value) => asRecord(value))
      .find((step) => asNumberOrNull(step.step_number) === startNumber);
    if (startStep !== undefined) {
      lines.push(
        `Start here: Step ${startNumber} — ${asString(startStep.title)}`,
      );
      lines.push('');
    }
  }
  const parallelNote = asStringOrNull(plan.parallel_eligible_note);
  if (parallelNote !== null) {
    lines.push(parallelNote);
    lines.push('');
  }
  const dependencyNote = asStringOrNull(plan.dependency_note);
  if (dependencyNote !== null) {
    lines.push(dependencyNote);
    lines.push('');
  }
  if (steps.length === 0) lines.push('- No action steps were recorded for this sitting.');
  for (const stepValue of steps) {
    const step = asRecord(stepValue);
    lines.push(`### Step ${String(asNumberOrNull(step.step_number) ?? '?')}: ${asString(step.title)}`);
    lines.push('');
    lines.push(asString(step.what_to_do));
    lines.push('');
    lines.push(`Why: ${asString(step.why)}`);
    const deps = asArray(step.depends_on_step_numbers).map((value) => String(value));
    const missingDeps = asArray(step.depends_on_missing_action_ids).map(asString);
    lines.push(
      `Depends on: ${deps.length > 0 ? `step ${deps.join(', step ')}` : 'nothing earlier in this plan'}${missingDeps.length > 0 ? `; a recorded dependency is not in this plan: ${missingDeps.join(', ')}` : ''}`,
    );
    lines.push('Done when:');
    // CTR-158: an empty acceptance list is an honest gap, never a blank
    // label. Use the model's recorded note (or its concise display text),
    // exactly as the HTML and screen exports already do.
    const doneWhen = asArray(step.done_when);
    if (doneWhen.length > 0) {
      lines.push(...mdList(doneWhen));
    } else {
      lines.push(
        `- ${asStringOrNull(step.done_when_note) ?? asStringOrNull(step.done_when_display) ?? 'Not recorded. Decide your own finish line before starting.'}`,
      );
    }
    lines.push(
      `Risk: ${asString(step.risk_text)}${asStringOrNull(step.due_date) === null ? '' : `; due ${asString(step.due_date)}`}${asStringOrNull(step.budget_text) === null ? '' : `; budget ${asString(step.budget_text)}`}`,
    );
    const stepTools = asArray(step.helpful_tool_names).map(asString);
    if (stepTools.length > 0) {
      lines.push(
        `Installed help that fits this step: ${stepTools.join(', ')} (optional; confirm with your OpenClaw agent before relying on it).`,
      );
    }
    lines.push('Needs separate approval before anyone acts on it.');
    lines.push('');
  }
  const prerequisites = asArray(plan.prerequisites);
  if (prerequisites.length > 0) {
    lines.push('Before you start:');
    lines.push(...mdList(prerequisites));
    lines.push('');
  }

  lines.push('## How you’ll know it worked');
  lines.push('');
  lines.push(
    `Cheapest informative test: ${asStringOrNull(plan.cheapest_test) ?? 'none recorded'}`,
  );
  lines.push('');
  lines.push('Stop if:');
  const stop = asArray(plan.stop_if);
  lines.push(...(stop.length > 0 ? mdList(stop) : ['- none recorded']));
  lines.push('');
  lines.push('Look again at:');
  const review = asArray(plan.review_criteria);
  lines.push(...(review.length > 0 ? mdList(review) : ['- none recorded']));
  lines.push('');

  pushHowToUseMd(lines, model);
  pushToolsMd(lines, model);
  pushConditionsMd(lines, model);
  pushAmendmentsMd(lines, model);
  pushWebTodayMd(lines, model);
  pushProvenanceMd(lines, model);
  pushReportRecordMd(lines, model);
  return `${lines.join('\n')}\n`;
}

function pushParticipatingSeatsMd(lines: string[], model: Record<string, unknown>): void {
  for (const seatValue of asArray(model.participating_seats)) {
    const seat = asRecord(seatValue);
    lines.push(
      `Participating seat: ${asString(seat.display_name)} (${asString(seat.seat_id)}), source qualification: ${qualificationText(seat.qualification)}`,
    );
  }
  lines.push('');
}

function pushAdvisorContributionsMd(lines: string[], model: Record<string, unknown>): void {
  for (const seatValue of asArray(model.advisor_contributions)) {
    const seat = asRecord(seatValue);
    lines.push(`### ${asString(seat.display_name)}`);
    lines.push('');
    lines.push(asString(seat.label));
    if (asStringOrNull(seat.lane) !== null) lines.push(`Focus: ${asString(seat.lane)}`);
    if (asStringOrNull(seat.owned_question) !== null) {
      lines.push(`The question this seat exists to answer: ${asString(seat.owned_question)}`);
    }
    lines.push(`Last saved round: ${String(asNumberOrNull(seat.round) ?? 'not recorded')}`);
    lines.push(`Source qualification: ${qualificationSentence(seat.qualification)}`);
    lines.push(`Position: ${asString(seat.stance_text)}`);
    lines.push(`Preferred option: ${asStringOrNull(seat.preferred_option_label) ?? 'none stated'}`);
    lines.push('What they argued:');
    lines.push(...mdList(asArray(seat.what_they_argued)));
    lines.push(`Strongest objection: ${asString(seat.strongest_objection)}`);
    lines.push(`What would change their mind: ${asString(seat.what_would_change_their_mind)}`);
    if (asStringOrNull(seat.minority_position) !== null) {
      lines.push(`Minority position: ${asString(seat.minority_position)}`);
    }
    const conditions = asArray(seat.conditions);
    if (conditions.length > 0) {
      lines.push('Conditions:');
      for (const conditionValue of conditions) {
        const condition = asRecord(conditionValue);
        lines.push(
          `- ${asString(condition.id)}: ${asString(condition.description)} (${asString(condition.kind)}, ${asString(condition.status_text)}${condition.blocking === true ? ', blocking' : ''})`,
        );
      }
    }
    if (asStringOrNull(seat.resolution_stance_text) !== null) {
      lines.push(`Resolution: ${asString(seat.resolution_stance_text)}`);
    }
    lines.push('');
  }
  // Fallback for a model without the reader projection.
  if (asArray(model.advisor_contributions).length === 0) {
    for (const seatValue of asArray(model.seats)) {
      const seat = asRecord(seatValue);
      lines.push(`### ${asString(seat.display_name)}`);
      lines.push('');
      lines.push(asString(seat.label));
      lines.push(`Source qualification: ${qualificationText(seat.qualification)}`);
      lines.push(`Stance: ${asString(seat.stance)}`);
      lines.push(`Preferred option: ${asStringOrNull(seat.preferred_option_id) ?? 'none'}`);
      lines.push('Decisive arguments:');
      lines.push(...mdList(asArray(seat.decisive_arguments)));
      lines.push(`Strongest objection: ${asString(seat.strongest_objection)}`);
      lines.push(`What would change my mind: ${asString(seat.change_my_mind)}`);
      lines.push('');
    }
  }
}

/**
 * CTR-158: the Markdown mirror of the HTML readiness card. It reads only the
 * shared `decision_vs_readiness` projection; it never infers readiness from
 * the verdict here.
 */
function pushReadinessMd(lines: string[], model: Record<string, unknown>): void {
  const dvr = asRecord(model.decision_vs_readiness ?? {});
  const readiness = asRecord(dvr.readiness ?? {});
  const status = asString(readiness.status);
  if (status === '') return;
  lines.push(`Can you act on this yet? ${readinessStatusText(status)}`);
  const headline = asStringOrNull(readiness.headline);
  if (headline !== null) lines.push(headline);
  const reasons = asArray(readiness.status_reasons);
  if (reasons.length > 0) {
    lines.push('Why:');
    lines.push(...mdList(reasons));
  }
  const describeCondition = (value: unknown): string => {
    const row = asRecord(value);
    const advisor = asStringOrNull(row.advisor);
    return `${asString(row.text)}${advisor === null ? '' : ` — recorded by ${advisor}`}`;
  };
  const blockers = asArray(readiness.blockers);
  if (blockers.length > 0) {
    lines.push(`Open blocking conditions (${blockers.length}):`);
    lines.push(...mdList(blockers.map(describeCondition)));
  }
  const safeguards = asArray(readiness.safeguards);
  if (safeguards.length > 0) {
    lines.push(`Recorded safeguards (${safeguards.length}):`);
    lines.push(...mdList(safeguards.map(describeCondition)));
  }
  const hardFindings = asArray(readiness.hard_constraint_findings);
  if (hardFindings.length > 0) {
    lines.push(
      `Hard-constraint findings on the recommended option (${hardFindings.length}):`,
    );
    lines.push(
      ...mdList(
        hardFindings.map((value) => {
          const row = asRecord(value);
          return `${asString(row.constraint_id)}: ${asString(row.result_text)}`;
        }),
      ),
    );
  }
  const ratification = asRecord(readiness.ratification ?? {});
  const ratStatus = asStringOrNull(ratification.status);
  if (ratStatus !== null) {
    lines.push(
      `Ratification: ${asStringOrNull(ratification.status_text) ?? ratStatus} ${ratification.blocks_readiness === true ? '(blocks readiness)' : '(does not block readiness)'}`,
    );
  }
  const note = asStringOrNull(readiness.note);
  if (note !== null) lines.push(note);
  lines.push('');
}

/**
 * CTR-158: the Markdown mirror of the HTML information-needed and council
 * unknown-count blocks. Totals, distinct rows, and the collapse note stay
 * explicit; no row is sliced.
 */
function pushInformationMd(lines: string[], model: Record<string, unknown>): void {
  const summary = asRecord(model.summary ?? {});
  const needed = asArray(summary.information_needed);
  const note = asStringOrNull(summary.information_needed_note);
  if (needed.length > 0 || note !== null) {
    lines.push('Information needed:');
    lines.push(...(needed.length > 0 ? mdList(needed) : ['- none recorded']));
    if (note !== null) lines.push(note);
    lines.push('');
  }
  const council = asArray(summary.council_unknowns);
  const recorded = asNumberOrNull(summary.council_unknowns_count) ?? council.length;
  const removed = asNumberOrNull(summary.council_unknowns_removed) ?? 0;
  if (council.length > 0 || recorded > 0) {
    lines.push("The council's unknown record:");
    const countLine =
      recorded > council.length
        ? `${recorded} recorded council statement(s); ${removed} repeat(s) collapsed after removing the "Unknown:" framing; ${council.length} distinct shown.`
        : `${council.length} distinct council statement(s).`;
    lines.push(countLine);
    if (council.length > 0) lines.push(...mdList(council));
    lines.push('');
  }
}

function pushHowToUseMd(lines: string[], model: Record<string, unknown>): void {
  lines.push('## How to use this report');
  lines.push('');
  const how = asArray(model.how_to_use);
  lines.push(...(how.length > 0 ? mdList(how) : ['- none recorded']));
  lines.push('');
}

/**
 * CTR-156: the EXACT basis for one capability row, per matched step. This
 * replaces the old shared-terms sentence in both the HTML and Markdown
 * renderers. No generic word overlap can reach the reader, so a backup or GHL
 * skill is never linked to an unrelated step through "before" or "search".
 */
function capabilityBasisLines(item: Record<string, unknown>): string[] {
  const actions = asArray(item.matched_actions);
  if (actions.length > 0) {
    return actions.map((value) => {
      const action = asRecord(value);
      const basis =
        action.basis === 'recorded_reference'
          ? 'this step records the department or role'
          : 'this step names the capability exactly';
      const evidence = asArray(action.evidence).map(asString).join('; ');
      return `${asString(action.action_title)} (${asString(action.action_id)}): ${basis}${
        evidence === '' ? '' : ` — exact record: ${evidence}`
      }`;
    });
  }
  const evidence = asArray(item.match_evidence).map(asString);
  return evidence.length > 0 ? [`Exact record: ${evidence.join('; ')}`] : [];
}

function pushToolsMd(lines: string[], model: Record<string, unknown>): void {
  const tools = asRecord(model.your_tools ?? {});
  lines.push('## Skills and departments on your OpenClaw');
  lines.push('');
  if (asStringOrNull(tools.basis_text) !== null) {
    lines.push(asString(tools.basis_text));
    lines.push('');
  }
  // CTR-158: the display bound is stated, never silent.
  const itemsTotal = asNumberOrNull(tools.items_total);
  const itemsShown =
    asNumberOrNull(tools.items_shown) ?? asArray(tools.items).length;
  if (itemsTotal !== null && itemsTotal > itemsShown) {
    lines.push(
      `${itemsTotal} exact-matched installed item(s) were found; ${itemsShown} are listed here and ${itemsTotal - itemsShown} further item(s) are not shown.`,
    );
    lines.push('');
  }
  for (const itemValue of asArray(tools.items)) {
    const item = asRecord(itemValue);
    lines.push(
      `### ${asString(item.name)} (${asString(item.kind)})`,
    );
    lines.push('');
    lines.push(
      item.availability === 'available_at_sitting'
        ? 'Available when this council sat.'
        : 'Available now on this installation.',
    );
    if (asStringOrNull(item.description) !== null) {
      lines.push(asString(item.description));
    }
    const titles = asArray(item.matched_action_titles).map(asString);
    if (titles.length > 0) {
      lines.push(`Where it fits: ${titles.join('; ')}`);
    }
    lines.push('Why it is linked:');
    const basisLines = capabilityBasisLines(item);
    if (basisLines.length === 0) {
      lines.push('- no exact match evidence recorded');
    } else {
      lines.push(...basisLines.map((line) => `- ${line}`));
    }
    lines.push(
      'A match is an exact record or an exact name, never shared wording, and never a promise that the tool can run this step.',
    );
    lines.push('');
  }
  lines.push(asString(tools.note));
  const limitations = asArray(tools.limitations);
  if (limitations.length > 0) {
    lines.push('');
    lines.push('How this list was read:');
    lines.push(...mdList(limitations));
  }
  lines.push('');
}

function pushConditionsMd(lines: string[], model: Record<string, unknown>): void {
  lines.push('## Conditions');
  lines.push('');
  lines.push('Hard constraints:');
  const findings = asArray(model.hard_constraints);
  if (findings.length === 0) lines.push('- none recorded');
  for (const findingValue of findings) {
    const finding = asRecord(findingValue);
    lines.push(
      `- ${asString(finding.constraint_id)} on option ${asString(finding.option_id)}: ${asString(finding.result)} (checker: ${asString(finding.checker)})`,
    );
  }
  lines.push('');
}

function pushAmendmentsMd(lines: string[], model: Record<string, unknown>): void {
  lines.push('## Amendments and ratification');
  lines.push('');
  const amendments = asRecord(model.amendments);
  const describeAmendment = (value: unknown): string => {
    const amendment = asRecord(value);
    return `${asString(amendment.amendment_id)} by ${asString(amendment.proposing_seat_id)}: ${asString(amendment.statement)} (${asString(amendment.materiality)}, ${asString(amendment.disposition)})`;
  };
  lines.push('Accepted amendments:');
  const accepted = asArray(amendments.accepted);
  lines.push(
    ...(accepted.length > 0 ? accepted.map((a) => `- ${describeAmendment(a)}`) : ['- none']),
  );
  lines.push('');
  lines.push('Rejected amendments:');
  const rejected = asArray(amendments.rejected);
  lines.push(
    ...(rejected.length > 0 ? rejected.map((a) => `- ${describeAmendment(a)}`) : ['- none']),
  );
  lines.push('');
  const ratification = asRecord(model.ratification);
  lines.push(`Ratification status: ${asStringOrNull(ratification.status) ?? 'not applicable'}`);
  const support = ratification.resolution_support as Record<string, unknown> | null;
  if (support) {
    lines.push(
      `Resolution support (weighted counts, not a probability): support ${formatPlainNumber(asNumberOrNull(support.support))}, conditional support ${formatPlainNumber(asNumberOrNull(support.conditional_support))}, opposition ${formatPlainNumber(asNumberOrNull(support.opposition))}, abstention ${formatPlainNumber(asNumberOrNull(support.abstention))}.`,
    );
  }
  lines.push('');
}

function pushReportRecordMd(lines: string[], model: Record<string, unknown>): void {
  const verdict = asRecord(model.verdict_block);
  lines.push('## For your records');
  lines.push('');
  lines.push(`Session: ${asString(model.session_id)}`);
  lines.push(`Mode: ${asStringOrNull(model.session_mode) ?? 'not recorded'}`);
  lines.push(`Route: ${asString(model.route_display)}`);
  lines.push(`Report revision: ${asString(model.report_revision_id)}`);
  lines.push(`Verdict revision: ${String(verdict.revision)}`);
  lines.push(`Verdict content SHA-256: ${asString(verdict.content_sha256)}`);
  lines.push(`Brief SHA-256: ${asString(verdict.brief_sha256)}`);
  lines.push(`Protocol version: ${asString(model.protocol_version)}`);
  lines.push(
    `Source pack versions: ${asArray(model.source_pack_versions).map(asString).join(', ') || 'none recorded'}`,
  );
  lines.push('');
}

/**
 * Web findings gathered for this session (model.web_today: claim, url,
 * title, retrieved_at). They are rendered apart from the source and
 * provenance appendix because they are not from the elder's books.
 * Nothing is rendered when the session has none.
 */
function webTodayFacts(model: Record<string, unknown>): Record<string, unknown>[] {
  return asArray(model.web_today).map(asRecord);
}

// Web text is untrusted: collapse every line break so a fact cannot forge a heading.
const oneLine = (v: unknown): string => asString(v).replace(/\s+/g, ' ').trim();

function pushWebTodayMd(lines: string[], model: Record<string, unknown>): void {
  const facts = webTodayFacts(model);
  if (facts.length === 0) return;
  lines.push('## From the web today');
  lines.push('');
  lines.push("These findings were gathered from the web for this session. They are not from the elder's books.");
  lines.push('');
  for (const fact of facts) {
    lines.push(`- ${oneLine(fact.claim)}`);
    lines.push(`  - URL: ${oneLine(fact.url)}`);
    lines.push(`  - Retrieved: ${oneLine(fact.retrieved_at)}`);
  }
  lines.push('');
}

function pushWebTodayHtml(out: string[], model: Record<string, unknown>): void {
  const facts = webTodayFacts(model);
  if (facts.length === 0) return;
  out.push('<h2>From the web today</h2>');
  out.push("<p>These findings were gathered from the web for this session. They are not from the elder's books.</p>");
  out.push('<ul>');
  for (const fact of facts) {
    out.push(
      `<li>${escapeHtml(oneLine(fact.claim))}<br>URL: ${escapeHtml(oneLine(fact.url))}<br>Retrieved: ${escapeHtml(oneLine(fact.retrieved_at))}</li>`,
    );
  }
  out.push('</ul>');
}

function pushProvenanceMd(lines: string[], model: Record<string, unknown>): void {
  const provenance = asRecord(model.provenance);
  lines.push('## Source and provenance appendix');
  lines.push('');
  lines.push(asString(provenance.note));
  lines.push('');
  lines.push('Reference list (locator, kind, evidence id):');
  const entries = asArray(provenance.evidence_manifest);
  if (entries.length === 0) lines.push('- none recorded');
  for (const entryValue of entries) {
    const entry = asRecord(entryValue);
    lines.push(
      `- ${asString(entry.locator)} (${asString(entry.source_kind)}; ${asString(entry.evidence_id)})`,
    );
  }
  lines.push('');
}

// ---------------------------------------------------------------------
// Print HTML
//
// Reader-first, 14pt floor. No table is wider than the page: the score
// table is rendered as stacked option blocks, so nothing has to be
// shrunk to fit. Brand tokens match the Council chamber and the shipped
// seat art. Design/asset integration replaces or extends the token block
// and `.report-cover` only; the semantic class names below are the
// stable anchors.
// ---------------------------------------------------------------------

/**
 * Reader projection interface (CTR-150). `renderPrintHtml` consumes only
 * the already-built model fields below and never recomputes a verdict,
 * score, round, quote, or skill match:
 *   decision_title, report_date, session_id, session_mode, route_display,
 *   protocol_version, report_revision_id, verdict_block, summary,
 *   question_and_context, score_table, advisor_contributions, debate,
 *   plan, how_to_use, your_tools, hard_constraints, amendments,
 *   ratification, provenance, web_today, source_pack_versions.
 * Reordering, exact-text de-duplication and styling happen here; saved
 * values are printed as recorded. A caller that wants a shorter report
 * must supply a shorter model, not a global string replacement.
 */
const PRINT_CSS = `
:root {
  --paper: #FFFFFF;
  --paper-band: #FBF6E9;
  --paper-deep: #F4EBD5;
  --ink: #1C1C1C;
  --ink-secondary: #3A3934;
  --navy: #16233D;
  --navy-deep: #101B30;
  --gold-rule: #B08A3E;
  --gold-text: #7A5C1F;
  --gold-light: #D8B76A;
  --cream-on-navy: #F7F1E1;
  --rule-hairline: #C9BFA8;
}
* { box-sizing: border-box; }
html {
  font-size: 15pt;
  background-color: var(--paper);
}
body {
  margin: 0;
  background-color: var(--paper);
  color: var(--ink);
  font-family: Georgia, "Iowan Old Style", "Times New Roman", serif;
  font-size: 15pt;
  line-height: 1.55;
  text-align: left;
  hyphens: manual;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}
p, li, dt, dd, blockquote, figcaption, td, th, dl, ul, ol,
footer, figcaption, caption, address, label, summary,
code, pre, kbd, samp, small, sub, sup, .note, .basis,
.qualification, .seat-label, .page-note, .meta, .cover-meta,
.label-box, .summary-card, .option-block, .advisor-card,
.tool-card, .plan-step, .round-block, .record, .report-footer {
  font-size: 15pt;
}
small, sub, sup, .note, .basis, .qualification, .seat-label,
.meta, .cover-meta, .page-note, .record dt, .record dd {
  font-size: 14pt;
  line-height: 1.45;
}
h1 { font-size: 27pt; line-height: 1.15; margin: 0 0 4mm 0; color: var(--navy); overflow-wrap: anywhere; }
h2 {
  font-size: 22pt;
  line-height: 1.25;
  color: var(--navy);
  border-bottom: 1pt solid var(--gold-rule);
  padding-bottom: 2mm;
  margin: 0;
  break-after: avoid;
  page-break-after: avoid;
}
h3 { font-size: 17pt; line-height: 1.3; color: var(--navy); margin: 5mm 0 2mm 0; break-after: avoid; page-break-after: avoid; }
ul, ol { margin: 0 0 3mm 0; padding-left: 7mm; break-inside: auto; }
li { margin: 0 0 1.5mm 0; }
p { margin: 0 0 3mm 0; orphans: 3; widows: 3; }
.section-head {
  margin: 9mm 0 3mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
  break-after: avoid;
  page-break-after: avoid;
}
.section-head h2 { margin: 0; }
.section-lead { margin: 2mm 0 0 0; color: var(--ink-secondary); font-size: 15pt; }
.part-banner {
  margin: 0 0 6mm 0;
  padding: 4mm 5mm;
  background: var(--navy);
  color: var(--cream-on-navy);
  border-left: 5mm solid var(--gold-rule);
  font-size: 16pt;
  font-weight: bold;
  letter-spacing: 0.04em;
  break-inside: avoid;
  page-break-inside: avoid;
}
.part-banner .part-kicker { color: var(--gold-light); }
.part-banner.part-start { break-before: page; page-break-before: always; }
.sec-n { display: inline-block; min-width: 9mm; color: var(--gold-text); }
.eyebrow {
  margin: 0 0 2mm 0;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 14pt;
  color: var(--gold-text);
}
.verdict-label { color: var(--gold-text); font-weight: bold; }
.report-cover {
  page-break-after: always;
  break-after: page;
  box-sizing: border-box;
  /* CTR-154: the cover box is a CONSERVATIVE 255 mm, not a measured
     printable height. A4 body height after the 17 mm top and 22 mm bottom
     running-page margins is 297 - 17 - 22 = 258 mm; 255 mm sits inside that
     with 3 mm spare so the cover cannot overflow onto a second page. The old
     min-height of 297 mm let the cover overflow. No pixel measurement is
     claimed. */
  width: 210mm;
  height: 255mm;
  overflow: visible;
  padding: 0 0 4mm 0;
  margin: 0;
  background: var(--paper);
}
.report-cover-band {
  background: var(--navy);
  border-bottom: 5pt solid var(--gold-rule);
  padding: 6mm 12mm 5mm 12mm;
}
.cover-kicker {
  margin: 0 0 3mm 0;
  color: var(--gold-light);
  font-size: 14pt;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  text-align: center;
}
.cover-redaction {
  margin: 0 auto;
  max-width: 158mm;
  border: 1pt solid var(--gold-light);
  padding: 5mm 6mm;
  color: var(--cream-on-navy);
  text-align: center;
}
.cover-redaction p { margin: 0; font-size: 15pt; }
.cover-portraits {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3mm 6mm;
  max-width: 158mm;
  margin: 0 auto;
}
.cover-portraits-single {
  grid-template-columns: 1fr;
  max-width: 42mm;
}
.seat-portrait {
  margin: 0;
  text-align: center;
  break-inside: avoid;
  page-break-inside: avoid;
}
.seat-portrait img,
.seat-portrait-fallback {
  display: block;
  width: 16mm;
  height: 16mm;
  margin: 0 auto 1mm auto;
  border-radius: 50%;
  border: 1.5pt solid var(--gold-light);
  background: var(--navy-deep);
  object-fit: cover;
  object-position: center top;
}
.seat-portrait-fallback {
  color: var(--cream-on-navy);
  font-size: 14pt;
  line-height: 16mm;
  text-align: center;
}
.seat-portrait span {
  display: block;
  color: var(--cream-on-navy);
  font-size: 14pt;
  line-height: 1.2;
}
.cover-body { padding: 6mm 20mm 0 20mm; }
.cover-body h1 { font-size: 24pt; }
.cover-meta { margin: 0 0 2mm 0; color: var(--ink-secondary); }
.cover-verdict {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3mm;
  margin: 3mm 0;
}
.cover-verdict p {
  margin: 0;
  border-top: 3pt solid var(--gold-rule);
  background: var(--paper-band);
  padding: 2.5mm 3mm;
  font-size: 15pt;
}
.cover-verdict span {
  display: block;
  color: var(--gold-text);
  font-size: 14pt;
  font-weight: bold;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.cover-readfirst {
  margin: 2.5mm 0 3mm 0;
  padding: 2.5mm 4mm 2.5mm 11mm;
  border: 1pt solid var(--rule-hairline);
  background: var(--paper-band);
  font-size: 14pt;
  break-inside: avoid;
  page-break-inside: avoid;
}
.cover-readfirst li { margin: 0 0 1mm 0; }
.cover-legal { margin: 2mm 0 0 0; }
.label-box {
  border: 1pt solid var(--rule-hairline);
  border-left: 4mm solid var(--gold-rule);
  background: var(--paper-band);
  padding: 4mm 5mm;
  margin: 4mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
.label-box p:last-child { margin-bottom: 0; }
.summary-card {
  border: 1pt solid var(--gold-rule);
  border-left: 4mm solid var(--gold-rule);
  background: var(--paper-band);
  padding: 5mm 6mm;
  margin: 0 0 5mm 0;
  break-inside: auto;
  page-break-inside: auto;
}
.glance {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2.5mm 4mm;
  margin: 0 0 4mm 0;
}
.glance div {
  border-top: 2.5pt solid var(--gold-rule);
  padding: 2mm 0 0 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
.summary-card .glance dt {
  margin: 0;
  color: var(--gold-text);
  font-size: 14pt;
  font-weight: bold;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.summary-card .glance dd { margin: 1mm 0 0 0; font-size: 15pt; overflow-wrap: anywhere; }
.read-map {
  border: 1pt solid var(--rule-hairline);
  background: var(--paper-band);
  padding: 4mm 5mm;
  margin: 0 0 5mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
.read-map-title { margin: 0 0 2mm 0; color: var(--navy); font-weight: bold; }
.read-map ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2mm 6mm;
}
.read-map li { display: flex; gap: 2.5mm; align-items: flex-start; margin: 0; font-size: 14pt; }
.read-map svg { width: 5mm; height: 5mm; flex: 0 0 5mm; margin-top: 1mm; color: var(--gold-text); }
.read-map a { color: var(--navy); text-decoration: none; border-bottom: 0.6pt solid var(--gold-rule); }
.summary-card dt { font-weight: bold; color: var(--navy); margin-top: 3mm; font-size: 15pt; }
.summary-card dt:first-child { margin-top: 0; }
.summary-card dd { margin: 0; overflow-wrap: anywhere; font-size: 15pt; }
.in-short { font-size: 17pt; line-height: 1.45; color: var(--navy); margin: 0 0 4mm 0; }
.verdict-line { font-size: 17pt; font-weight: bold; color: var(--navy); margin: 0 0 2mm 0; }
.recommendation-line { font-size: 17pt; margin: 0 0 3mm 0; }
/* CTR-156: readiness is a separate card after the decision lines. It stays
   splittable when long; every declared size is at least 14pt. */
.readiness-card {
  border: 1pt solid var(--gold-rule);
  border-left: 4mm solid var(--gold-rule);
  background: var(--paper-band);
  padding: 4mm 5mm;
  margin: 0 0 4mm 0;
  break-inside: auto;
  page-break-inside: auto;
}
.readiness-status { font-size: 16pt; font-weight: bold; color: var(--navy); margin: 0 0 2mm 0; }
.start-here {
  font-size: 16pt;
  margin: 3mm 0;
  padding: 2.5mm 3mm;
  background: var(--paper-band);
  border-top: 2.5pt solid var(--gold-rule);
  break-inside: avoid;
  page-break-inside: avoid;
}
.match-basis { margin: 0 0 2mm 0; }
.advisor-summary { margin: 0 0 3mm 0; }
.option-block, .advisor-card, .tool-card, .plan-step, .round-block {
  border: 1pt solid var(--rule-hairline);
  border-top: 4pt solid var(--navy);
  background: var(--paper);
  padding: 4mm 5mm;
  margin: 0 0 4mm 0;
  break-inside: auto;
  page-break-inside: auto;
}
.option-block h3, .advisor-card h3, .tool-card h3, .plan-step h3 { margin-top: 0; }
.advisor-card { border-top-color: var(--gold-rule); }
.plan-step { border-top-color: var(--navy-deep); }
.plan-overview {
  margin: 0 0 5mm 0;
  padding: 4mm 5mm 4mm 10mm;
  border: 1pt solid var(--rule-hairline);
  background: var(--paper-band);
}
.plan-overview li { margin: 0 0 1.5mm 0; }
.plan-overview strong { color: var(--navy); }
.step-number {
  display: inline-block;
  background: var(--navy);
  color: var(--cream-on-navy);
  font-weight: bold;
  font-size: 16pt;
  padding: 1mm 3mm;
  margin: 0 0 2mm 0;
}
.plan-step ol { padding-left: 7mm; }
.fact-list, .condition-list { margin: 0 0 3mm 0; padding-left: 7mm; }
.qualification, .seat-label { color: var(--ink-secondary); font-style: italic; }
.basis, .note { color: var(--ink-secondary); }
.record dt { font-weight: bold; color: var(--navy); margin-top: 3mm; }
.record dd { margin: 0; overflow-wrap: anywhere; }
footer.report-footer {
  margin-top: 8mm;
  padding: 4mm 0 0 0;
  border-top: 1pt solid var(--gold-rule);
  break-inside: avoid;
  page-break-inside: avoid;
  color: var(--ink-secondary);
}
@page {
  size: A4;
  margin: 17mm 20mm 22mm 20mm;
  @bottom-center {
    content: "Page " counter(page) " of " counter(pages);
    font-family: Georgia, "Iowan Old Style", "Times New Roman", serif;
    font-size: 14pt;
    color: #3A3934;
  }
}
@page :first { margin: 0; }
`;

/**
 * Print-only list. Exact duplicate strings are printed once; no recorded
 * value is rewritten, truncated or dropped unless the exact same text
 * already appeared earlier in the same list. This is exact-string dedupe
 * only: it does not collapse paraphrases such as "Weekly production hours
 * ... are unknown." against "Unknown: weekly production hours ...". The
 * canonical de-duplication of those framed restatements happens upstream in
 * the model (CTR-155), so this helper must not be read as closing that.
 */
function hList(items: unknown[]): string {
  const seen = new Set<string>();
  const rendered: string[] = [];
  for (const item of items) {
    const text = asString(item);
    if (seen.has(text)) continue;
    seen.add(text);
    rendered.push(`<li>${escapeHtml(text)}</li>`);
  }
  return `<ul>${rendered.join('')}</ul>`;
}

function sectionSlug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

/**
 * One numbered top-level section. Numbering is positional per render.
 * CTR-150: h2, its one-line cue and the first block stay together; the
 * old 24 mm KIE divider is gone because it forced the heading alone onto
 * a page and consumed a third of the next one.
 */
function pushSection(
  out: string[],
  counter: { n: number },
  title: string,
  lead?: string,
): void {
  counter.n += 1;
  const slug = sectionSlug(title);
  out.push('<div class="section-head">');
  out.push(
    `<h2 class="sec" id="section-${slug}" data-section="${escapeHtml(slug)}"><span class="sec-n">${counter.n}.</span> ${escapeHtml(title)}</h2>`,
  );
  if (lead !== undefined && lead !== '') {
    out.push(`<p class="section-lead">${escapeHtml(lead)}</p>`);
  }
  out.push('</div>');
}

function pushPartBanner(out: string[], part: string, label: string, startsPage: boolean): void {
  out.push(
    `<div class="part-banner${startsPage ? ' part-start' : ''}"><span class="part-kicker">${escapeHtml(part)}</span> — ${escapeHtml(label)}</div>`,
  );
}

function readMapIcon(kind: 'answer' | 'plan' | 'reasoning' | 'record'): string {
  const paths: Record<typeof kind, string> = {
    answer: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16.5 9"/>',
    plan: '<path d="M8 6h11M8 12h11M8 18h11"/><circle cx="4.5" cy="6" r="1.2"/><circle cx="4.5" cy="12" r="1.2"/><circle cx="4.5" cy="18" r="1.2"/>',
    reasoning: '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M2.5 20c.8-3 3-4.5 5.5-4.5S12.7 17 13.5 20M10.5 20c.8-3 3-4.5 5.5-4.5S20.2 17 21 20"/>',
    record: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5M10 12h6M10 16h6"/>',
  };
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[kind]}</svg>`;
}

function pushReadMap(out: string[], fullRecord: boolean): void {
  out.push('<nav class="read-map" aria-label="What is inside">');
  out.push('<p class="read-map-title">What is inside</p>');
  out.push('<ol>');
  out.push(
    `<li>${readMapIcon('answer')}<span><a href="#section-in-short">The answer</a> — verdict, why, confidence</span></li>`,
  );
  if (fullRecord) {
    out.push(
      `<li>${readMapIcon('plan')}<span><a href="#section-your-plan">Your plan</a> — numbered steps and approvals</span></li>`,
    );
    out.push(
      `<li>${readMapIcon('reasoning')}<span><a href="#section-what-each-advisor-said">The reasoning</a> — each advisor and the debate</span></li>`,
    );
  } else {
    out.push(
      `<li>${readMapIcon('plan')}<span><a href="#section-the-consultation-answer">The consultation answer</a> — recorded next step and limits</span></li>`,
    );
    out.push(
      `<li>${readMapIcon('reasoning')}<span><a href="#section-skills-and-departments-on-your-openclaw">Installed help</a> — optional skills on this box</span></li>`,
    );
  }
  out.push(
    `<li>${readMapIcon('record')}<span><a href="#section-for-your-records">The record</a> — sources, hashes, versions</span></li>`,
  );
  out.push('</ol>');
  out.push('</nav>');
}

/** CTR-156: the readiness status in words, never a bare enum. */
function readinessStatusText(status: string): string {
  switch (status) {
    case 'ready':
      return 'Ready to act';
    case 'ready_with_conditions':
      return 'Ready with conditions';
    case 'blocked':
      return 'Not ready yet';
    case 'not_ready':
      return 'Not ready to act';
    case 'not_applicable':
      return 'No plan readiness for a consultation';
    default:
      return status === '' ? 'Readiness not recorded' : status;
  }
}

/**
 * CTR-156: readiness is printed as its OWN fact, after the verdict, from the
 * shared `decision_vs_readiness` projection. The verdict word is never
 * relabelled and no readiness is inferred here. A WAIT, RESHAPE, DONT_DO_IT or
 * INSUFFICIENT_EVIDENCE sitting is never printed as ready; the model decides
 * that and this renderer only reproduces it.
 */
function pushReadinessHtml(out: string[], model: Record<string, unknown>): void {
  const dvr = asRecord(model.decision_vs_readiness ?? {});
  const readiness = asRecord(dvr.readiness ?? {});
  const status = asString(readiness.status);
  if (status === '') return;
  out.push('<div class="readiness-card" data-section="readiness">');
  out.push(
    `<p class="readiness-status"><strong>Can you act on this yet?</strong> ${escapeHtml(readinessStatusText(status))}</p>`,
  );
  const headline = asStringOrNull(readiness.headline);
  if (headline !== null) out.push(`<p>${escapeHtml(headline)}</p>`);
  const reasons = asArray(readiness.status_reasons);
  if (reasons.length > 0) {
    out.push('<p><strong>Why:</strong></p>');
    out.push(hList(reasons));
  }
  const describeCondition = (value: unknown): string => {
    const row = asRecord(value);
    const advisor = asStringOrNull(row.advisor);
    return `${asString(row.text)}${advisor === null ? '' : ` — recorded by ${advisor}`}`;
  };
  const blockers = asArray(readiness.blockers);
  if (blockers.length > 0) {
    out.push(`<p><strong>Open blocking conditions (${blockers.length}):</strong></p>`);
    out.push(hList(blockers.map(describeCondition)));
  }
  const safeguards = asArray(readiness.safeguards);
  if (safeguards.length > 0) {
    out.push(`<p><strong>Recorded safeguards (${safeguards.length}):</strong></p>`);
    out.push(hList(safeguards.map(describeCondition)));
  }
  const hardFindings = asArray(readiness.hard_constraint_findings);
  if (hardFindings.length > 0) {
    out.push(
      `<p><strong>Hard-constraint findings on the recommended option (${hardFindings.length}):</strong></p>`,
    );
    out.push(
      hList(
        hardFindings.map((value) => {
          const row = asRecord(value);
          return `${asString(row.constraint_id)}: ${asString(row.result_text)}`;
        }),
      ),
    );
  }
  const ratification = asRecord(readiness.ratification ?? {});
  const ratStatus = asStringOrNull(ratification.status);
  if (ratStatus !== null) {
    out.push(
      `<p><strong>Ratification:</strong> ${escapeHtml(asStringOrNull(ratification.status_text) ?? ratStatus)} ${ratification.blocks_readiness === true ? '(blocks readiness)' : '(does not block readiness)'}</p>`,
    );
  }
  const note = asStringOrNull(readiness.note);
  if (note !== null) out.push(`<p class="note">${escapeHtml(note)}</p>`);
  out.push('</div>');
}

/**
 * CTR-156: the canonical Information needed list (the brief's own unknowns),
 * the council's separate restated unknown record with a transparent
 * total/collapsed/shown count, and the what-would-change count semantics.
 * Every distinct row is printed in full; nothing is sliced.
 */
function pushInformationHtml(out: string[], model: Record<string, unknown>): void {
  const summary = asRecord(model.summary ?? {});
  const needed = asArray(summary.information_needed);
  const note = asStringOrNull(summary.information_needed_note);
  if (needed.length > 0 || note !== null) {
    out.push('<dt>Information needed</dt>');
    out.push(`<dd>${needed.length > 0 ? hList(needed) : '<p>none recorded</p>'}`);
    if (note !== null) out.push(`<p class="note">${escapeHtml(note)}</p>`);
    out.push('</dd>');
  }
  const council = asArray(summary.council_unknowns);
  const recorded = asNumberOrNull(summary.council_unknowns_count) ?? council.length;
  const removed = asNumberOrNull(summary.council_unknowns_removed) ?? 0;
  if (council.length > 0 || recorded > 0) {
    out.push("<dt>The council's unknown record</dt>");
    const countLine =
      recorded > council.length
        ? `${recorded} recorded council statement(s); ${removed} repeat(s) collapsed after removing the "Unknown:" framing; ${council.length} distinct shown.`
        : `${council.length} distinct council statement(s).`;
    out.push(
      `<dd><p>${escapeHtml(countLine)}</p>${council.length > 0 ? hList(council) : ''}</dd>`,
    );
  }
}

function pushSummaryHtml(
  out: string[],
  model: Record<string, unknown>,
  fullRecord: boolean,
): void {
  const summary = asRecord(model.summary ?? {});
  const verdict = asRecord(model.verdict_block);
  const plan = asRecord(model.plan ?? {});
  const confidence = asRecord(summary.confidence ?? {});
  const consult = isConsultModel(model)
    ? (model.consult as Record<string, unknown>)
    : null;
  out.push('<div class="summary-card" data-section="summary">');
  if (consult) {
    out.push(`<p class="in-short">${escapeHtml(asString(summary.in_short))}</p>`);
    out.push('<dl class="glance">');
    out.push(
      `<div><dt>Answered by</dt><dd>${escapeHtml(asString(consult.display_name))} (${escapeHtml(asString(consult.label))})</dd></div>`,
    );
    out.push(
      `<div><dt>Next step recorded</dt><dd>${escapeHtml(asString(consult.next_step))}</dd></div>`,
    );
    out.push('</dl>');
    out.push('</div>');
    pushReadMap(out, fullRecord);
    return;
  }
  out.push(`<p class="in-short">${escapeHtml(asString(summary.in_short))}</p>`);
  out.push('<dl class="glance">');
  out.push(
    `<div><dt>Verdict</dt><dd>${escapeHtml(asString(verdict.label))}${asStringOrNull(summary.verdict_label_text) === null ? '' : ` — ${escapeHtml(asString(summary.verdict_label_text))}`}</dd></div>`,
  );
  out.push(
    `<div><dt>Recommended</dt><dd>${escapeHtml(asStringOrNull(verdict.recommended_option_label) ?? 'none recorded')}</dd></div>`,
  );
  out.push(
    `<div><dt>Confidence</dt><dd>${escapeHtml(asStringOrNull(confidence.evidence_strength_text) ?? 'not recorded')}</dd></div>`,
  );
  out.push(
    `<div><dt>Plan</dt><dd>${escapeHtml(String(asArray(plan.steps).length))} recorded step(s)</dd></div>`,
  );
  out.push('</dl>');
  out.push(
    `<p class="verdict-line"><span class="verdict-label">Verdict:</span> ${escapeHtml(asString(verdict.label))}${asStringOrNull(summary.verdict_label_text) === null ? '' : ` — ${escapeHtml(asString(summary.verdict_label_text))}`}</p>`,
  );
  const recommended = asStringOrNull(verdict.recommended_option_id);
  out.push(
    `<p class="recommendation-line">Recommendation: ${escapeHtml(
      recommended === null
        ? 'none'
        : `${recommended} (${asString(verdict.recommended_option_label)})`,
    )}</p>`,
  );
  if (asStringOrNull(summary.ratification_text) !== null) {
    out.push(`<p>${escapeHtml(asString(summary.ratification_text))}</p>`);
  }
  // CTR-156: readiness is its own fact, immediately after the decision lines.
  pushReadinessHtml(out, model);
  out.push('<dl>');
  const reasons = asArray(summary.reasons);
  if (reasons.length > 0) {
    out.push('<dt>Why the council said this</dt>');
    out.push(`<dd>${hList(reasons)}</dd>`);
  }
  out.push(
    `<dt>Biggest concern</dt><dd>${escapeHtml(asStringOrNull(summary.biggest_concern) ?? 'none recorded')}</dd>`,
  );
  const confidenceNotes = asArray(confidence.notes);
  if (confidenceNotes.length > 0) {
    out.push('<dt>How confident this is</dt>');
    out.push(`<dd>${hList(confidenceNotes)}</dd>`);
  }
  const change = asArray(summary.what_would_change_the_answer);
  if (change.length > 0) {
    const recorded =
      asNumberOrNull(summary.what_would_change_the_answer_count) ?? change.length;
    const removed =
      asNumberOrNull(summary.what_would_change_the_answer_removed) ?? 0;
    const countLine =
      recorded > change.length
        ? `<p>${escapeHtml(String(recorded))} recorded seat statement(s); ${escapeHtml(String(removed))} exact repeat(s) collapsed; ${escapeHtml(String(change.length))} distinct shown.</p>`
        : '';
    out.push('<dt>What would change the answer</dt>');
    out.push(`<dd>${countLine}${hList(change)}</dd>`);
  }
  // CTR-156: canonical information needed and the council's separate record.
  pushInformationHtml(out, model);
  out.push('</dl>');
  out.push('</div>');
  pushReadMap(out, fullRecord);
}

function pushQuestionHtml(out: string[], model: Record<string, unknown>): void {
  const context = asRecord(model.question_and_context ?? {});
  out.push(`<p><strong>Your question:</strong> ${escapeHtml(asString(context.question) || asString(model.decision_title))}</p>`);
  if (asArray(context.options).length > 0) {
    out.push('<h3>The options you considered</h3>');
    out.push('<ul>');
    for (const optionValue of asArray(context.options)) {
      const option = asRecord(optionValue);
      out.push(
        `<li>${escapeHtml(asString(option.option_label))} <span class="basis">(option ${escapeHtml(asString(option.option_id))})</span></li>`,
      );
    }
    out.push('</ul>');
  }
  out.push('<h3>The facts the council worked from</h3>');
  const facts = asArray(context.facts);
  if (facts.length === 0) out.push('<ul><li>none recorded</li></ul>');
  else {
    out.push('<ul>');
    for (const factValue of facts) {
      const fact = asRecord(factValue);
      out.push(`<li>${escapeHtml(asString(fact.statement))}</li>`);
    }
    out.push('</ul>');
  }
  out.push('<h3>Assumptions</h3>');
  const assumptions = asArray(context.assumptions);
  out.push(assumptions.length > 0 ? hList(assumptions) : '<ul><li>none recorded</li></ul>');
  out.push('<h3>Unknowns</h3>');
  const unknowns = asArray(context.unknowns);
  out.push(unknowns.length > 0 ? hList(unknowns) : '<ul><li>none recorded</li></ul>');
  // CTR-158: this section de-duplicates exact or framed repeats, so the
  // recorded total, the distinct rows shown, and the collapse note are stated.
  const unknownsNote = asStringOrNull(context.unknowns_note);
  if (unknownsNote !== null) {
    const recorded = asNumberOrNull(context.unknowns_count) ?? unknowns.length;
    const shown = asNumberOrNull(context.unknowns_shown) ?? unknowns.length;
    out.push(
      `<p class="note">${escapeHtml(String(recorded))} recorded; ${escapeHtml(String(shown))} distinct shown. ${escapeHtml(unknownsNote)}</p>`,
    );
  }
  const constraints = asArray(context.constraints);
  if (constraints.length > 0) {
    out.push('<h3>Constraints</h3>');
    out.push('<ul>');
    for (const constraintValue of constraints) {
      const constraint = asRecord(constraintValue);
      const applies = asArray(constraint.applies_to_option_labels).map(asString);
      out.push(
        `<li>${escapeHtml(asString(constraint.description))} <span class="basis">(${constraint.hard === true ? 'hard constraint' : 'guideline'}${applies.length > 0 ? `; applies to ${escapeHtml(applies.join(', '))}` : ''})</span></li>`,
      );
    }
    out.push('</ul>');
  }
}

function pushOptionsHtml(out: string[], model: Record<string, unknown>): void {
  const rows = asArray(model.score_table);
  if (rows.length === 0) {
    out.push('<p>No scored options are recorded for this sitting.</p>');
    return;
  }
  for (const rowValue of rows) {
    const row = asRecord(rowValue);
    const abstainedNames = asArray(row.abstained_seat_names).map(asString);
    const abstainedIds = asArray(row.abstained_seat_ids).map(asString);
    const abstainedLabel =
      abstainedNames.length > 0
        ? abstainedNames.join(', ')
        : abstainedIds.map((seat) => seat.replace(/-/g, ' ')).join(', ');
    out.push('<div class="option-block">');
    out.push(
      `<h3>${escapeHtml(asString(row.option_label))} <span class="basis">(option ${escapeHtml(asString(row.option_id))})</span></h3>`,
    );
    out.push(
      `<p>Score: ${escapeHtml(formatDisplayScore(asNumberOrNull(row.display_score)))} out of 10. Weighted total ${escapeHtml(formatPlainNumber(asNumberOrNull(row.weighted_sum)))} over ${escapeHtml(formatPlainNumber(asNumberOrNull(row.denominator)))}; coverage ${escapeHtml(formatCoverage(asNumberOrNull(row.coverage)))}; spread ${escapeHtml(formatPlainNumber(asNumberOrNull(row.spread)))}.</p>`,
    );
    out.push(
      `<p>${abstainedIds.length === 0 ? 'Every participating seat scored this option.' : `Abstained: ${escapeHtml(abstainedLabel)}.`}</p>`,
    );
    out.push('</div>');
  }
}

function pushAdvisorHtml(out: string[], model: Record<string, unknown>): void {
  const contributions = asArray(model.advisor_contributions);
  if (contributions.length === 0) {
    out.push('<p>No advisor detail is saved for this sitting.</p>');
    return;
  }
  // CTR-156: a concise line per seat first (every saved seat), then the full
  // card. The detail is the saved record, quoted as recorded, never a
  // rewritten summary dressed up as fluent prose.
  out.push(`<h3>${contributions.length} seats at a glance</h3>`);
  out.push('<ul class="advisor-summary">');
  for (const seatValue of contributions) {
    const seat = asRecord(seatValue);
    out.push(
      `<li><strong>${escapeHtml(asString(seat.display_name))}</strong>: ${escapeHtml(asString(seat.stance_text))}; preferred ${escapeHtml(asStringOrNull(seat.preferred_option_label) ?? 'none stated')}.</li>`,
    );
  }
  out.push('</ul>');
  out.push(
    '<p class="note">Each box below reproduces the saved advisor-card fields as recorded. Nothing here is a rewritten summary; unusual or technical wording stays as the seat wrote it.</p>',
  );
  for (const seatValue of contributions) {
    const seat = asRecord(seatValue);
    out.push('<div class="advisor-card">');
    out.push(`<h3>${escapeHtml(asString(seat.display_name))}</h3>`);
    if (asStringOrNull(seat.lane) !== null) {
      out.push(`<p class="basis">Focus: ${escapeHtml(asString(seat.lane))}</p>`);
    }
    if (asStringOrNull(seat.owned_question) !== null) {
      out.push(
        `<p>${escapeHtml(asString(seat.owned_question))}</p>`,
      );
    }
    out.push(
      `<p class="basis">Last saved round: ${escapeHtml(String(asNumberOrNull(seat.round) ?? 'not recorded'))}</p>`,
    );
    out.push(
      `<p><strong>Position:</strong> ${escapeHtml(asString(seat.stance_text))}. <strong>Preferred option:</strong> ${escapeHtml(asStringOrNull(seat.preferred_option_label) ?? 'none stated')}.</p>`,
    );
    out.push('<p><strong>What they argued:</strong></p>');
    out.push(hList(asArray(seat.what_they_argued)));
    out.push(
      `<p><strong>Their strongest objection:</strong> ${escapeHtml(asString(seat.strongest_objection))}</p>`,
    );
    out.push(
      `<p><strong>What would change their mind:</strong> ${escapeHtml(asString(seat.what_would_change_their_mind))}</p>`,
    );
    if (asStringOrNull(seat.minority_position) !== null) {
      out.push(
        `<p><strong>Minority position:</strong> ${escapeHtml(asString(seat.minority_position))}</p>`,
      );
    }
    const conditions = asArray(seat.conditions);
    if (conditions.length > 0) {
      out.push('<p><strong>Conditions they set:</strong></p>');
      out.push('<ul class="condition-list">');
      for (const conditionValue of conditions) {
        const condition = asRecord(conditionValue);
        out.push(
          `<li>${escapeHtml(asString(condition.id))}: ${escapeHtml(asString(condition.description))} <span class="basis">(${escapeHtml(asString(condition.kind))}, ${escapeHtml(asString(condition.status_text))}${condition.blocking === true ? ', blocking' : ''})</span></li>`,
        );
      }
      out.push('</ul>');
    }
    if (asStringOrNull(seat.resolution_stance_text) !== null) {
      out.push(
        `<p><strong>On the final resolution:</strong> ${escapeHtml(asString(seat.resolution_stance_text))}</p>`,
      );
    }
    out.push(
      `<p class="seat-label">${escapeHtml(asString(seat.label))}</p>`,
    );
    out.push(
      `<p class="qualification">Source qualification: ${escapeHtml(qualificationSentence(seat.qualification))}</p>`,
    );
    out.push('</div>');
  }
}

function pushDebateHtml(out: string[], model: Record<string, unknown>): void {
  const debate = asRecord(model.debate ?? {});
  out.push(
    `<p><strong>Rounds of advisor cards saved:</strong> ${String(asNumberOrNull(debate.rounds_saved) ?? 0)}</p>`,
  );
  out.push('<ul>');
  for (const note of asArray(debate.notes)) {
    out.push(`<li>${escapeHtml(asString(note))}</li>`);
  }
  out.push('</ul>');
  // CTR-156: the saved-round split and the honest repeat note are shown, so
  // the debate section carries actual round evidence rather than a promise of
  // a narrative.
  const condensedNote = asStringOrNull(debate.condensed_note);
  if (condensedNote !== null) {
    out.push(`<p class="note">${escapeHtml(condensedNote)}</p>`);
  }
  const roundSupport = asArray(debate.round_support);
  if (roundSupport.length > 0) {
    out.push('<h3>How each saved round split</h3>');
    out.push('<ul>');
    for (const supportValue of roundSupport) {
      const row = asRecord(supportValue);
      out.push(
        `<li>Round ${escapeHtml(String(asNumberOrNull(row.round) ?? '?'))}: ${escapeHtml(String(asNumberOrNull(row.support) ?? 0))} support, ${escapeHtml(String(asNumberOrNull(row.conditional) ?? 0))} conditional, ${escapeHtml(String(asNumberOrNull(row.oppose) ?? 0))} oppose, ${escapeHtml(String(asNumberOrNull(row.abstain) ?? 0))} abstain${row.identical_to_previous === true ? '; identical to the previous saved round' : ''}.</li>`,
      );
    }
    out.push('</ul>');
  }
  for (const roundValue of asArray(debate.rounds)) {
    const round = asRecord(roundValue);
    out.push('<div class="round-block">');
    out.push(`<h3>Round ${escapeHtml(String(asNumberOrNull(round.round) ?? '?'))}</h3>`);
    out.push('<ul>');
    for (const seatValue of asArray(round.seats)) {
      const seat = asRecord(seatValue);
      out.push(
        `<li>${escapeHtml(asString(seat.display_name))} ${escapeHtml(asString(seat.stance_text))}${asStringOrNull(seat.preferred_option_label) === null ? '' : `; preferred ${escapeHtml(asString(seat.preferred_option_label))}`}.</li>`,
      );
    }
    out.push('</ul>');
    out.push('</div>');
  }
  const changes = asArray(debate.changes);
  if (changes.length > 0) {
    out.push('<h3>What changed between rounds</h3>');
    out.push('<ul>');
    for (const changeValue of changes) {
      const change = asRecord(changeValue);
      const optionChanged =
        asStringOrNull(change.from_option_label) !== asStringOrNull(change.to_option_label);
      out.push(
        `<li>Round ${escapeHtml(String(asNumberOrNull(change.round) ?? '?'))}: ${escapeHtml(asString(change.display_name))} moved from ${escapeHtml(asString(change.from_stance_text))} to ${escapeHtml(asString(change.to_stance_text))}${optionChanged ? `; preferred option ${escapeHtml(asStringOrNull(change.from_option_label) ?? 'none')} to ${escapeHtml(asStringOrNull(change.to_option_label) ?? 'none')}` : ''}.</li>`,
      );
    }
    out.push('</ul>');
  }
  const positions = asArray(debate.positions);
  if (positions.length > 0) {
    out.push('<h3>Where they stood on the preferred option</h3>');
    out.push('<ul>');
    for (const positionValue of positions) {
      const position = asRecord(positionValue);
      out.push(
        `<li>${escapeHtml(asString(position.option_label))}: ${escapeHtml(asArray(position.seat_names).map(asString).join(', '))}</li>`,
      );
    }
    out.push('</ul>');
  }
}

function pushPlanHtml(out: string[], model: Record<string, unknown>): void {
  const plan = asRecord(model.plan ?? {});
  const steps = asArray(plan.steps);
  const prerequisites = asArray(plan.prerequisites);
  if (steps.length > 1) {
    out.push('<ol class="plan-overview">');
    for (const stepValue of steps) {
      const step = asRecord(stepValue);
      out.push(
        `<li><strong>Step ${escapeHtml(String(asNumberOrNull(step.step_number) ?? '?'))}:</strong> ${escapeHtml(asString(step.title))}</li>`,
      );
    }
    out.push('</ol>');
  }
  // CTR-156: one recorded first action, plus the honest note that more than
  // one step may have no recorded dependency. The saved order is kept.
  const startNumber = asNumberOrNull(plan.start_here_step_number);
  if (startNumber !== null) {
    const startStep = steps
      .map((value) => asRecord(value))
      .find((step) => asNumberOrNull(step.step_number) === startNumber);
    if (startStep !== undefined) {
      out.push(
        `<p class="start-here"><strong>Start here:</strong> Step ${escapeHtml(String(startNumber))} — ${escapeHtml(asString(startStep.title))}</p>`,
      );
    }
  }
  const parallelNote = asStringOrNull(plan.parallel_eligible_note);
  if (parallelNote !== null) {
    out.push(`<p class="note">${escapeHtml(parallelNote)}</p>`);
  }
  const dependencyNote = asStringOrNull(plan.dependency_note);
  if (dependencyNote !== null) {
    out.push(`<p class="note">${escapeHtml(dependencyNote)}</p>`);
  }
  if (prerequisites.length > 0) {
    out.push('<h3>Before you start</h3>');
    out.push(hList(prerequisites));
  }
  if (steps.length === 0) {
    out.push('<p>No action steps were recorded for this sitting.</p>');
  }
  for (const stepValue of steps) {
    const step = asRecord(stepValue);
    out.push('<div class="plan-step">');
    out.push(
      `<p class="step-number">Step ${escapeHtml(String(asNumberOrNull(step.step_number) ?? '?'))}</p>`,
    );
    out.push(`<h3>${escapeHtml(asString(step.title))}</h3>`);
    out.push(`<p>${escapeHtml(asString(step.what_to_do))}</p>`);
    out.push(`<p><strong>Why:</strong> ${escapeHtml(asString(step.why))}</p>`);
    const deps = asArray(step.depends_on_step_numbers).map((value) => String(value));
    const missingDeps = asArray(step.depends_on_missing_action_ids).map(asString);
    const dependencyText = `${deps.length > 0 ? `step ${deps.join(', step ')}` : 'nothing earlier in this plan'}${missingDeps.length > 0 ? `; a recorded dependency is not in this plan: ${missingDeps.join(', ')}` : ''}`;
    out.push(`<p><strong>Depends on:</strong> ${escapeHtml(dependencyText)}</p>`);
    out.push('<p><strong>Done when:</strong></p>');
    const doneWhen = asArray(step.done_when);
    // CTR-156: never leave a blank "Done when". Use the recorded finish line,
    // else the model's honest note that the saved record stated none.
    out.push(
      doneWhen.length > 0
        ? hList(doneWhen)
        : `<p class="note">${escapeHtml(asStringOrNull(step.done_when_note) ?? 'No completion check is recorded for this step.')}</p>`,
    );
    const extra: string[] = [];
    if (asStringOrNull(step.due_date) !== null) extra.push(`due ${asString(step.due_date)}`);
    if (asStringOrNull(step.budget_text) !== null) extra.push(`budget ${asString(step.budget_text)}`);
    out.push(
      `<p><strong>Risk:</strong> ${escapeHtml(asString(step.risk_text))}${extra.length > 0 ? `; ${escapeHtml(extra.join('; '))}` : ''}</p>`,
    );
    const stepTools = asArray(step.helpful_tool_names).map(asString);
    if (stepTools.length > 0) {
      out.push(
        `<p><strong>Installed help that fits this step:</strong> ${escapeHtml(stepTools.join(', '))} <span class="basis">(optional; confirm with your OpenClaw agent before relying on it)</span></p>`,
      );
    }
    out.push(
      '<p class="label-box">This step needs its own approval before anyone acts on it. A council recommendation is not an execution authorization.</p>',
    );
    out.push('</div>');
  }
}

function pushReviewHtml(out: string[], model: Record<string, unknown>): void {
  const plan = asRecord(model.plan ?? {});
  out.push(
    `<p><strong>Cheapest useful test:</strong> ${escapeHtml(asStringOrNull(plan.cheapest_test) ?? 'none recorded')}</p>`,
  );
  out.push('<p><strong>Stop if:</strong></p>');
  const stop = asArray(plan.stop_if);
  out.push(stop.length > 0 ? hList(stop) : '<ul><li>none recorded</li></ul>');
  out.push('<p><strong>Look again at:</strong></p>');
  const review = asArray(plan.review_criteria);
  out.push(review.length > 0 ? hList(review) : '<ul><li>none recorded</li></ul>');
}

function pushHowToUseHtml(out: string[], model: Record<string, unknown>): void {
  const how = asArray(model.how_to_use);
  out.push(how.length > 0 ? hList(how) : '<ul><li>none recorded</li></ul>');
}

function pushToolsHtml(out: string[], model: Record<string, unknown>): void {
  const tools = asRecord(model.your_tools ?? {});
  if (asStringOrNull(tools.basis_text) !== null) {
    out.push(`<p class="basis">${escapeHtml(asString(tools.basis_text))}</p>`);
  }
  // CTR-158: the display bound is stated, never silent.
  const itemsTotal = asNumberOrNull(tools.items_total);
  const itemsShown =
    asNumberOrNull(tools.items_shown) ?? asArray(tools.items).length;
  if (itemsTotal !== null && itemsTotal > itemsShown) {
    out.push(
      `<p class="note">${escapeHtml(String(itemsTotal))} exact-matched installed item(s) were found; ${escapeHtml(String(itemsShown))} are listed here and ${escapeHtml(String(itemsTotal - itemsShown))} further item(s) are not shown.</p>`,
    );
  }
  for (const itemValue of asArray(tools.items)) {
    const item = asRecord(itemValue);
    out.push('<div class="tool-card">');
    out.push(
      `<h3>${escapeHtml(asString(item.name))} <span class="basis">(${escapeHtml(asString(item.kind))})</span></h3>`,
    );
    out.push(
      `<p>${item.availability === 'available_at_sitting' ? 'Available when this council sat.' : 'Available now on this installation.'}</p>`,
    );
    if (asStringOrNull(item.description) !== null) {
      out.push(`<p>${escapeHtml(asString(item.description))}</p>`);
    }
    const titles = asArray(item.matched_action_titles).map(asString);
    if (titles.length > 0) {
      out.push(`<p><strong>Where it fits:</strong> ${escapeHtml(titles.join('; '))}</p>`);
    }
    // CTR-156: exact per-step basis and match evidence replace the old
    // shared-terms sentence. No generic word overlap reaches the reader.
    out.push('<p><strong>Why it is linked:</strong></p>');
    const basisLines = capabilityBasisLines(item);
    out.push(
      basisLines.length === 0
        ? '<p class="note">No exact match evidence is recorded for this row.</p>'
        : `<ul class="match-basis">${basisLines.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>`,
    );
    out.push(
      '<p class="note">A match is an exact record or an exact name, never shared wording, and never a promise that the tool can run this step.</p>',
    );
    out.push('</div>');
  }
  out.push(`<p class="note">${escapeHtml(asString(tools.note))}</p>`);
  const limitations = asArray(tools.limitations);
  if (limitations.length > 0) {
    out.push('<h3>How this list was read</h3>');
    out.push(hList(limitations));
  }
}

function pushConditionsHtml(out: string[], model: Record<string, unknown>): void {
  out.push('<h3>Hard constraints</h3>');
  const findings = asArray(model.hard_constraints);
  if (findings.length === 0) out.push('<ul><li>none recorded</li></ul>');
  else {
    out.push('<ul>');
    for (const findingValue of findings) {
      const finding = asRecord(findingValue);
      out.push(
        `<li>${escapeHtml(asString(finding.constraint_id))} on option ${escapeHtml(asString(finding.option_id))}: ${escapeHtml(asString(finding.result))} (checker: ${escapeHtml(asString(finding.checker))})</li>`,
      );
    }
    out.push('</ul>');
  }
}

function pushAmendmentsHtml(out: string[], model: Record<string, unknown>): void {
  const amendments = asRecord(model.amendments);
  const describeAmendment = (value: unknown): string => {
    const amendment = asRecord(value);
    return `${asString(amendment.amendment_id)} by ${asString(amendment.proposing_seat_id)}: ${asString(amendment.statement)} (${asString(amendment.materiality)}, ${asString(amendment.disposition)})`;
  };
  const accepted = asArray(amendments.accepted);
  const rejected = asArray(amendments.rejected);
  if (accepted.length === 0 && rejected.length === 0) {
    out.push('<p>No amendments were recorded for this sitting.</p>');
  } else {
    out.push('<h3>Accepted amendments</h3>');
    out.push(accepted.length > 0 ? `<ul>${accepted.map((a) => `<li>${escapeHtml(describeAmendment(a))}</li>`).join('')}</ul>` : '<ul><li>none</li></ul>');
    out.push('<h3>Rejected amendments</h3>');
    out.push(rejected.length > 0 ? `<ul>${rejected.map((a) => `<li>${escapeHtml(describeAmendment(a))}</li>`).join('')}</ul>` : '<ul><li>none</li></ul>');
  }
  const ratification = asRecord(model.ratification);
  out.push(
    `<p><strong>Ratification:</strong> ${escapeHtml(asStringOrNull(ratification.status) ?? 'not applicable')}</p>`,
  );
  const support = ratification.resolution_support as Record<string, unknown> | null;
  if (support) {
    out.push(
      `<p>Resolution support (weighted counts, not a probability): support ${escapeHtml(formatPlainNumber(asNumberOrNull(support.support)))}, conditional support ${escapeHtml(formatPlainNumber(asNumberOrNull(support.conditional_support)))}, opposition ${escapeHtml(formatPlainNumber(asNumberOrNull(support.opposition)))}, abstention ${escapeHtml(formatPlainNumber(asNumberOrNull(support.abstention)))}.</p>`,
    );
  }
}

function pushProvenanceHtml(out: string[], model: Record<string, unknown>): void {
  const provenance = asRecord(model.provenance);
  out.push('<h3>Reference list</h3>');
  out.push(`<p>${escapeHtml(asString(provenance.note))}</p>`);
  const entries = asArray(provenance.evidence_manifest);
  if (entries.length === 0) out.push('<ul><li>none recorded</li></ul>');
  else {
    out.push('<ul>');
    for (const entryValue of entries) {
      const entry = asRecord(entryValue);
      out.push(
        `<li>${escapeHtml(asString(entry.locator))} <span class="basis">(${escapeHtml(asString(entry.source_kind))}; ${escapeHtml(asString(entry.evidence_id))})</span></li>`,
      );
    }
    out.push('</ul>');
  }
}

/** The recorded session frame: what produced this document, verbatim. */
function pushReportRecordHtml(out: string[], model: Record<string, unknown>): void {
  const verdict = asRecord(model.verdict_block);
  out.push('<dl class="record">');
  const row = (term: string, value: string): void => {
    out.push(`<dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd>`);
  };
  row('Decision', asString(model.decision_title));
  row('Date', asString(model.report_date));
  row('Session', asString(model.session_id));
  row('Mode', asStringOrNull(model.session_mode) ?? 'not recorded');
  row('Recorded route / model', asString(model.route_display));
  row('Report revision', asString(model.report_revision_id));
  row('Verdict revision', String(verdict.revision));
  row('Verdict content SHA-256', asString(verdict.content_sha256));
  row('Brief SHA-256', asString(verdict.brief_sha256));
  row('Protocol version', asString(model.protocol_version));
  row('Source pack versions', asArray(model.source_pack_versions).map(asString).join(', ') || 'none recorded');
  row('Redacted', model.redacted === true ? `yes (profile ${asString(model.redaction_profile_id)})` : 'no');
  row('Sample session', model.sample === true ? 'SAMPLE' : 'no');
  out.push('</dl>');
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((part) => part.length > 0)
    .map((part) => part[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

/**
 * CTR-150 cover, corrected by CTR-154:
 * - a full council prints the nine served chamber portraits in the shared
 *   seat order, composed from `public/chamber/portraits`;
 * - a consult prints only the one seat the saved record consulted, never
 *   the nine and never a fictional plan or debate;
 * - a redacted export prints no image bytes and no static roster name at
 *   all. `service.ts` states that policy because a redaction target cannot
 *   be proven absent from compressed pixels; the cover must not route
 *   around it with names the renderer supplies itself.
 * Each portrait is read through the fixed allowlist in `asset-embed.ts`;
 * there is no screenshot, browser, network call or arbitrary-file read. A
 * missing portrait falls back to initials rather than the empty-table art.
 */
function pushCoverSeatFigure(
  out: string[],
  seatId: string,
  displayName: string,
): void {
  const seat = REPORT_SEAT_PORTRAITS.find((entry) => entry.seat_id === seatId);
  const uri = seat === undefined ? null : loadReportPortraitDataUri(seat.seat_id);
  out.push('<figure class="seat-portrait">');
  if (uri !== null) {
    out.push(`<img src="${escapeHtml(uri)}" alt="${escapeHtml(displayName)}">`);
  } else {
    out.push(
      `<div class="seat-portrait-fallback" aria-hidden="true">${escapeHtml(initials(displayName))}</div>`,
    );
  }
  out.push(`<span>${escapeHtml(displayName)}</span>`);
  out.push('</figure>');
}

function pushCoverHtml(out: string[], model: Record<string, unknown>): void {
  const summary = asRecord(model.summary ?? {});
  const verdict = asRecord(model.verdict_block);
  const consult = isConsultModel(model)
    ? (model.consult as Record<string, unknown>)
    : null;
  const redacted = model.redacted === true;
  out.push('<div class="report-cover" data-section="cover">');
  out.push('<div class="report-cover-band">');
  out.push('<p class="cover-kicker">Council of Wise Elders</p>');
  if (redacted) {
    out.push('<div class="cover-redaction" role="note">');
    out.push('<p>Redacted report: portraits and seat names are not printed.</p>');
    out.push('</div>');
  } else if (consult !== null) {
    const recordedName = asString(consult.display_name);
    const rosterSeat = REPORT_SEAT_PORTRAITS.find(
      (entry) => entry.seat_id === asString(consult.seat_id),
    );
    out.push(
      '<div class="cover-portraits cover-portraits-single" aria-label="The Council seat that answered">',
    );
    pushCoverSeatFigure(
      out,
      asString(consult.seat_id),
      recordedName !== '' ? recordedName : (rosterSeat?.display_name ?? 'Recorded seat'),
    );
    out.push('</div>');
  } else {
    out.push('<div class="cover-portraits" aria-label="The nine Council seats">');
    for (const seat of REPORT_SEAT_PORTRAITS) {
      pushCoverSeatFigure(out, seat.seat_id, seat.display_name);
    }
    out.push('</div>');
  }
  out.push('</div>');
  out.push('<div class="cover-body">');
  out.push('<p class="eyebrow">Decision report</p>');
  out.push(`<h1>${escapeHtml(asString(model.decision_title))}</h1>`);
  out.push(
    `<p class="cover-meta">${escapeHtml(asString(model.report_date))} · prepared from your saved council sitting.</p>`,
  );
  if (model.redacted === true) {
    out.push(
      `<p class="cover-meta">Redacted report: yes (profile ${escapeHtml(asString(model.redaction_profile_id))})</p>`,
    );
  }
  if (model.sample === true) {
    out.push('<p class="cover-meta">Sample session: SAMPLE</p>');
  }
  if (consult === null) {
    out.push('<div class="cover-verdict">');
    out.push(
      `<p><span>Verdict</span>${escapeHtml(asString(verdict.label))}${asStringOrNull(summary.verdict_label_text) === null ? '' : ` — ${escapeHtml(asString(summary.verdict_label_text))}`}</p>`,
    );
    out.push(
      `<p><span>Recommended</span>${escapeHtml(asStringOrNull(verdict.recommended_option_label) ?? 'none recorded')}</p>`,
    );
    out.push('</div>');
  }
  out.push('<ol class="cover-readfirst">');
  if (consult !== null) {
    out.push(
      '<li><strong>Start here:</strong> the named answer and its recorded limits.</li>',
    );
    out.push(
      '<li><strong>Then read:</strong> the assumptions, the limits, and the recorded next step.</li>',
    );
    out.push(
      '<li><strong>The record:</strong> the saved sources and versions behind this answer.</li>',
    );
  } else {
    out.push(
      '<li><strong>Start here:</strong> the answer, why, and what would change it.</li>',
    );
    out.push(
      '<li><strong>Then act:</strong> your numbered plan. Every step needs its own approval.</li>',
    );
    out.push(
      '<li><strong>Check the reasoning:</strong> each advisor, the debate, and the sources.</li>',
    );
  }
  out.push('</ol>');
  out.push('<div class="cover-legal">');
  out.push('<div class="label-box">');
  out.push(`<p>${escapeHtml(asString(model.simulation_label))}</p>`);
  out.push(`<p>${escapeHtml(asString(model.authorization_notice))}</p>`);
  if (model.sample === true) {
    out.push(`<p>${escapeHtml(asString(model.sample_notice))}</p>`);
  }
  out.push('</div>');
  out.push('</div>');
  out.push('</div>');
  out.push('</div>');
}

export interface PrintRenderOptions {
  /**
   * Retained for callers built against CTR-146/147. CTR-150/CTR-154
   * ignore all three: the cover is composed from the packaged portraits
   * that match the report kind (nine for a council, one for a consult,
   * none for a redacted export), and the tiled frame/divider were removed
   * because they printed over live text. Keeping the fields avoids a
   * breaking service change; they never reach the report model or the
   * record JSON.
   */
  cover_image_data_uri?: string | null;
  frame_image_data_uri?: string | null;
  divider_image_data_uri?: string | null;
}

export function renderPrintHtml(
  model: Record<string, unknown>,
  _options: PrintRenderOptions = {},
): string {
  const verdict = asRecord(model.verdict_block);
  const out: string[] = [];
  out.push('<!DOCTYPE html>');
  out.push('<html lang="en">');
  out.push('<head>');
  out.push('<meta charset="utf-8">');
  out.push('<meta name="viewport" content="width=device-width, initial-scale=1">');
  out.push(`<title>Council report ${escapeHtml(asString(model.session_id))} revision ${escapeHtml(String(verdict.revision))}</title>`);
  out.push(`<style>${PRINT_CSS}</style>`);
  out.push('</head>');
  out.push('<body>');
  pushCoverHtml(out, model);

  const counter = { n: 0 };
  const consult = isConsultModel(model)
    ? (model.consult as Record<string, unknown>)
    : null;
  pushPartBanner(out, 'Part 1', 'Decision and plan', false);
  pushSection(out, counter, 'In short', 'The answer, why, and what would change it.');
  pushSummaryHtml(out, model, consult === null);

  if (consult) {
    pushSection(out, counter, 'The question', 'What the council was asked and what it knew.');
    pushQuestionHtml(out, model);
    pushSection(out, counter, 'The consultation answer', 'The named answer and its recorded limits.');
    out.push(`<p>${escapeHtml(asString(consult.display_name))}: ${escapeHtml(asString(consult.label))}</p>`);
    out.push(`<p>${escapeHtml(asString(consult.answer))}</p>`);
    out.push('<h3>Assumptions</h3>');
    out.push(hList(asArray(consult.assumptions)));
    out.push('<h3>Limits</h3>');
    out.push(hList(asArray(consult.limits)));
    out.push(`<p>Next step: ${escapeHtml(asString(consult.next_step))}</p>`);
    pushSection(out, counter, 'How to use this report', 'Advice is not permission; re-convene when the facts change.');
    pushHowToUseHtml(out, model);
    pushSection(out, counter, 'Skills and departments on your OpenClaw', 'Optional helpers already installed on this box; a match is a suggestion only.');
    pushToolsHtml(out, model);
    pushSection(out, counter, 'Where this came from', 'The saved evidence, kept separate from the advice.');
    pushWebTodayHtml(out, model);
    pushProvenanceHtml(out, model);
    pushSection(out, counter, 'For your records', 'Identifiers and hashes for this exact saved report.');
    pushReportRecordHtml(out, model);
    out.push('<footer class="report-footer">');
    out.push(`<p class="note">${escapeHtml(asString(model.simulation_label))}</p>`);
    out.push(`<p class="note">${escapeHtml(asString(model.authorization_notice))}</p>`);
    out.push('</footer>');
    out.push('</body>');
    out.push('</html>');
    return `${out.join('\n')}\n`;
  }

  pushSection(out, counter, 'The question', 'What the council was asked and what it knew.');
  pushQuestionHtml(out, model);

  pushSection(out, counter, 'Your plan', 'Do these in order. Each step needs its own approval before anyone acts.');
  pushPlanHtml(out, model);

  pushSection(out, counter, 'How you will know it worked', 'The cheapest test, the stop conditions, and when to look again.');
  pushReviewHtml(out, model);

  pushSection(out, counter, 'How to use this report', 'Advice is not permission; re-convene when the facts change.');
  pushHowToUseHtml(out, model);

  pushSection(out, counter, 'Skills and departments on your OpenClaw', 'Optional helpers already installed on this box; a match is a suggestion only.');
  pushToolsHtml(out, model);

  pushPartBanner(out, 'Part 2', 'The full council record', true);
  pushSection(out, counter, 'Options the council weighed', 'Every scored option and how the seats split.');
  pushOptionsHtml(out, model);

  pushSection(out, counter, 'What each advisor said', 'The saved reasoning from every seat. Read the names first; each box is one advisor card.');
  pushAdvisorHtml(out, model);

  pushSection(out, counter, 'How the debate went', 'The rounds that actually happened, and what changed between them.');
  pushDebateHtml(out, model);

  pushSection(out, counter, 'Conditions and amendments', 'Hard-constraint findings and recorded amendments.');
  pushConditionsHtml(out, model);
  pushAmendmentsHtml(out, model);

  pushSection(out, counter, 'Where this came from', 'The saved evidence, kept separate from the advice.');
  pushWebTodayHtml(out, model);
  pushProvenanceHtml(out, model);

  pushSection(out, counter, 'For your records', 'Identifiers and hashes for this exact saved report.');
  pushReportRecordHtml(out, model);

  out.push('<footer class="report-footer">');
  out.push(
    `<p class="note">${escapeHtml(asString(model.simulation_label))}</p>`,
  );
  out.push(
    `<p class="note">${escapeHtml(asString(model.authorization_notice))}</p>`,
  );
  out.push('</footer>');
  out.push('</body>');
  out.push('</html>');
  return `${out.join('\n')}\n`;
}

// ---------------------------------------------------------------------
// Canonical record JSON
// ---------------------------------------------------------------------

export interface SiblingArtifact {
  format: string;
  filename: string;
  sha256: string;
  status: 'ready' | 'not_ready';
  missing_piece: string | null;
}

/**
 * The canonical record JSON: the full report model in canonical
 * serialized form, plus the sibling artifact index so the record binds
 * the exact bytes of the Markdown, print HTML, and rendered PDF
 * produced from the same validated revision. When no PDF was rendered
 * the record names the deliverable as not ready with its missing piece
 * instead of omitting it silently.
 */
export function renderRecordJson(
  model: Record<string, unknown>,
  siblings: SiblingArtifact[],
): string {
  const record = {
    ...model,
    sibling_artifacts: siblings.some((sibling) => sibling.format === 'pdf')
      ? [...siblings]
      : [
          ...siblings,
          {
            format: 'pdf',
            filename: null,
            sha256: null,
            status: 'not_ready',
            missing_piece: PDF_MISSING_PIECE,
          },
        ],
  };
  return `${canonicalStringify(record)}\n`;
}
