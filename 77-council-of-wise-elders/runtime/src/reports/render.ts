/**
 * Deterministic renderers for the registered report formats
 * (CWE-038, directive Sections 24.1 to 24.3).
 *
 * All renderers consume the one report model and nothing else: no
 * second model rewrite per format, no clock, no randomness, no locale
 * dependence. The same model always renders to the same bytes, which
 * is what makes the formats agree on scores, decisions, conditions,
 * citations, and report revision (test contract T105).
 *
 * The print HTML is the deterministic document the approved
 * Playwright/Chromium renderer (Section 24.3) will print to PDF under
 * CWE-044: local assets only (one embedded style block), no scripts,
 * no network references, every generated string HTML-escaped, body
 * type at 12.5pt, repeating table headers, controlled page breaks,
 * and page numbers from the print stylesheet.
 */

import { canonicalStringify, sha256Hex } from '../contracts/index.js';
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

// ---------------------------------------------------------------------
// Markdown
// ---------------------------------------------------------------------

function mdList(items: unknown[]): string[] {
  return items.map((item) => `- ${asString(item)}`);
}

export function renderMarkdown(model: Record<string, unknown>): string {
  const verdict = asRecord(model.verdict_block);
  const brief = asRecord(model.brief);
  const lines: string[] = [];
  lines.push(`# Council of Wise Elders: Decision Report`);
  lines.push('');
  lines.push(`Decision: ${asString(model.decision_title)}`);
  lines.push(`Date: ${asString(model.report_date)}`);
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
    lines.push('## Consultation');
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
    pushWebTodayMd(lines, model);
    pushProvenanceMd(lines, model);
    return `${lines.join('\n')}\n`;
  }

  lines.push('## Executive decision');
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
  lines.push('');
  lines.push('Prerequisites:');
  const prerequisites = asArray(model.prerequisites);
  lines.push(...(prerequisites.length > 0 ? mdList(prerequisites) : ['- none']));
  lines.push('');
  lines.push('Why:');
  lines.push(...mdList(asArray(model.main_reasons)));
  lines.push('');

  lines.push('## Alternatives and scores');
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

  lines.push('## Main arguments and strongest dissent');
  lines.push('');
  lines.push('Main arguments:');
  lines.push(...mdList(asArray(model.main_reasons)));
  lines.push('');
  lines.push(`Strongest dissent: ${asStringOrNull(model.strongest_dissent) ?? 'none recorded'}`);
  lines.push('');

  lines.push('## Constraints, assumptions, and unknowns');
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
  lines.push('Assumptions:');
  const assumptions = asArray(brief.assumptions);
  lines.push(...(assumptions.length > 0 ? mdList(assumptions) : ['- none recorded']));
  lines.push('');
  lines.push('Unknowns:');
  const unknowns = [...asArray(brief.unknowns), ...asArray(model.critical_unknowns)];
  lines.push(...(unknowns.length > 0 ? mdList(unknowns) : ['- none recorded']));
  lines.push('');

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
      `Resolution support (weighted counts, not a probability): support ${formatPlainNumber(asNumberOrNull(support.support))}, conditional support ${formatPlainNumber(asNumberOrNull(support.conditional_support))}, opposition ${formatPlainNumber(asNumberOrNull(support.opposition))}, abstention ${formatPlainNumber(asNumberOrNull(support.abstention))}, bound to resolution ${asString(support.resolution_sha256)}.`,
    );
  }
  lines.push('');

  lines.push('## Action proposals and authorization boundaries');
  lines.push('');
  const proposals = asArray(model.action_proposals);
  if (proposals.length === 0) lines.push('- none');
  for (const proposalValue of proposals) {
    const proposal = asRecord(proposalValue);
    lines.push(`### ${asString(proposal.action_id)}: ${asString(proposal.title)}`);
    lines.push('');
    lines.push(asString(proposal.description));
    lines.push('');
    lines.push(`Rationale: ${asString(proposal.rationale)}`);
    lines.push('Acceptance criteria:');
    lines.push(...mdList(asArray(proposal.acceptance_criteria)));
    const depends = asArray(proposal.depends_on_action_ids).map(asString);
    lines.push(`Depends on: ${depends.length > 0 ? depends.join(', ') : 'none'}`);
    lines.push(`Risk class: ${asString(proposal.risk_class)}`);
    lines.push(
      'Execution authorization: separate execution authorization is required before this proposal may be acted on.',
    );
    lines.push('');
  }
  lines.push(`> ${asString(model.authorization_notice)}`);
  lines.push('');

  lines.push('## Test, stop conditions, and review criteria');
  lines.push('');
  lines.push(
    `Cheapest informative test: ${asStringOrNull(model.cheapest_informative_test) ?? 'none recorded'}`,
  );
  lines.push('');
  lines.push('Stop conditions:');
  const stop = asArray(model.stop_criteria);
  lines.push(...(stop.length > 0 ? mdList(stop) : ['- none recorded']));
  lines.push('');
  lines.push('Outcome review criteria:');
  const review = asArray(model.review_criteria);
  lines.push(...(review.length > 0 ? mdList(review) : ['- none recorded']));
  lines.push('');

  pushSeatsMd(lines, model);
  pushWebTodayMd(lines, model);
  pushProvenanceMd(lines, model);
  return `${lines.join('\n')}\n`;
}

function pushSeatsMd(lines: string[], model: Record<string, unknown>): void {
  lines.push('## Advisor detail');
  lines.push('');
  for (const seatValue of asArray(model.participating_seats)) {
    const seat = asRecord(seatValue);
    lines.push(
      `Participating seat: ${asString(seat.display_name)} (${asString(seat.seat_id)}), source qualification: ${qualificationText(seat.qualification)}`,
    );
  }
  lines.push('');
  for (const seatValue of asArray(model.seats)) {
    const seat = asRecord(seatValue);
    lines.push(`### ${asString(seat.display_name)}`);
    lines.push('');
    lines.push(asString(seat.label));
    lines.push('');
    lines.push(`Source qualification: ${qualificationText(seat.qualification)}`);
    lines.push(`Stance: ${asString(seat.stance)}`);
    lines.push(`Preferred option: ${asStringOrNull(seat.preferred_option_id) ?? 'none'}`);
    const abstained = asArray(seat.abstained_option_ids).map(asString);
    if (abstained.length > 0) {
      lines.push(`Abstained on: ${abstained.join(', ')}`);
    }
    lines.push('Decisive arguments:');
    lines.push(...mdList(asArray(seat.decisive_arguments)));
    lines.push(`Strongest objection: ${asString(seat.strongest_objection)}`);
    lines.push(`What would change my mind: ${asString(seat.change_my_mind)}`);
    const conditions = asArray(seat.conditions);
    if (conditions.length > 0) {
      lines.push('Conditions:');
      for (const conditionValue of conditions) {
        const condition = asRecord(conditionValue);
        lines.push(
          `- ${asString(condition.id)}: ${asString(condition.description)} (${asString(condition.kind)}, ${asString(condition.status)}${condition.blocking === true ? ', blocking' : ''})`,
        );
      }
    }
    const stance = asStringOrNull(seat.resolution_stance);
    if (stance !== null) lines.push(`Resolution stance: ${stance}`);
    lines.push('');
  }
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
  lines.push('| Evidence | Kind | Locator | SHA-256 |');
  lines.push('| --- | --- | --- | --- |');
  for (const entryValue of asArray(provenance.evidence_manifest)) {
    const entry = asRecord(entryValue);
    lines.push(
      `| ${asString(entry.evidence_id)} | ${asString(entry.source_kind)} | ${asString(entry.locator)} | ${asString(entry.sha256)} |`,
    );
  }
  lines.push('');
}

// ---------------------------------------------------------------------
// Print HTML
// ---------------------------------------------------------------------

const PRINT_CSS = [
  '@page { size: A4; margin: 20mm 18mm 20mm 18mm; @bottom-center { content: "Page " counter(page) " of " counter(pages); font-size: 9pt; color: #444; } }',
  'body { font-family: Georgia, "Times New Roman", serif; font-size: 12.5pt; line-height: 1.45; color: #111; }',
  'h1 { font-size: 20pt; } h2 { font-size: 15pt; page-break-after: avoid; } h3 { font-size: 13pt; page-break-after: avoid; }',
  'table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #666; padding: 4px 6px; text-align: left; vertical-align: top; }',
  'thead { display: table-header-group; } tr { page-break-inside: avoid; }',
  '.label { border: 1px solid #666; padding: 8px 10px; } .meta { color: #333; }',
].join('\n');

function hList(items: unknown[]): string {
  return `<ul>${items.map((item) => `<li>${escapeHtml(asString(item))}</li>`).join('')}</ul>`;
}

export function renderPrintHtml(model: Record<string, unknown>): string {
  const verdict = asRecord(model.verdict_block);
  const brief = asRecord(model.brief);
  const out: string[] = [];
  out.push('<!DOCTYPE html>');
  out.push('<html lang="en">');
  out.push('<head>');
  out.push('<meta charset="utf-8">');
  out.push(`<title>Council report ${escapeHtml(asString(model.session_id))} revision ${escapeHtml(String(verdict.revision))}</title>`);
  out.push(`<style>${PRINT_CSS}</style>`);
  out.push('</head>');
  out.push('<body>');
  out.push('<h1>Council of Wise Elders: Decision Report</h1>');
  out.push(`<p class="meta">Decision: ${escapeHtml(asString(model.decision_title))}<br>`);
  out.push(`Date: ${escapeHtml(asString(model.report_date))}<br>`);
  out.push(`Session: ${escapeHtml(asString(model.session_id))}<br>`);
  out.push(`Mode: ${escapeHtml(asStringOrNull(model.session_mode) ?? 'not recorded')}<br>`);
  out.push(`Route: ${escapeHtml(asString(model.route_display))}<br>`);
  out.push(`Report revision: ${escapeHtml(asString(model.report_revision_id))}<br>`);
  out.push(`Verdict revision: ${escapeHtml(String(verdict.revision))}<br>`);
  out.push(`Verdict content SHA-256: ${escapeHtml(asString(verdict.content_sha256))}<br>`);
  out.push(`Brief SHA-256: ${escapeHtml(asString(verdict.brief_sha256))}<br>`);
  out.push(`Protocol version: ${escapeHtml(asString(model.protocol_version))}</p>`);
  if (model.redacted === true) {
    out.push(`<p class="meta">Redacted report: yes (profile ${escapeHtml(asString(model.redaction_profile_id))})</p>`);
  }
  if (model.sample === true) {
    out.push('<p class="meta">Sample session: SAMPLE</p>');
  }
  out.push(`<p class="label">${escapeHtml(asString(model.simulation_label))}</p>`);
  out.push(`<p class="label">${escapeHtml(asString(model.authorization_notice))}</p>`);
  if (model.sample === true) {
    out.push(`<p class="label">${escapeHtml(asString(model.sample_notice))}</p>`);
  }

  const consult = model.consult as Record<string, unknown> | null;
  if (consult) {
    out.push('<h2>Consultation</h2>');
    out.push(`<p>${escapeHtml(asString(consult.display_name))}: ${escapeHtml(asString(consult.label))}</p>`);
    out.push(`<p>${escapeHtml(asString(consult.answer))}</p>`);
    out.push('<h3>Assumptions</h3>');
    out.push(hList(asArray(consult.assumptions)));
    out.push('<h3>Limits</h3>');
    out.push(hList(asArray(consult.limits)));
    out.push(`<p>Next step: ${escapeHtml(asString(consult.next_step))}</p>`);
    pushWebTodayHtml(out, model);
    pushProvenanceHtml(out, model);
    out.push('</body>');
    out.push('</html>');
    return `${out.join('\n')}\n`;
  }

  out.push('<h2>Executive decision</h2>');
  out.push(`<p>Verdict: ${escapeHtml(asString(verdict.label))}<br>`);
  const recommended = asStringOrNull(verdict.recommended_option_id);
  out.push(
    `Recommendation: ${escapeHtml(recommended === null ? 'none' : `${recommended} (${asString(verdict.recommended_option_label)})`)}</p>`,
  );
  out.push('<h3>Prerequisites</h3>');
  const prerequisites = asArray(model.prerequisites);
  out.push(prerequisites.length > 0 ? hList(prerequisites) : '<ul><li>none</li></ul>');
  out.push('<h3>Why</h3>');
  out.push(hList(asArray(model.main_reasons)));

  out.push('<h2>Alternatives and scores</h2>');
  out.push('<table><thead><tr><th>Option</th><th>Weighted sum</th><th>Denominator</th><th>Score</th><th>Display score</th><th>Coverage</th><th>Spread</th><th>Abstentions</th></tr></thead><tbody>');
  for (const rowValue of asArray(model.score_table)) {
    const row = asRecord(rowValue);
    const abstained = asArray(row.abstained_seat_ids).map(asString).join(', ') || 'none';
    out.push(
      `<tr><td>${escapeHtml(asString(row.option_id))} (${escapeHtml(asString(row.option_label))})</td><td>${escapeHtml(formatPlainNumber(asNumberOrNull(row.weighted_sum)))}</td><td>${escapeHtml(formatPlainNumber(asNumberOrNull(row.denominator)))}</td><td>${escapeHtml(formatScore(asNumberOrNull(row.score)))}</td><td>${escapeHtml(formatDisplayScore(asNumberOrNull(row.display_score)))}</td><td>${escapeHtml(formatCoverage(asNumberOrNull(row.coverage)))}</td><td>${escapeHtml(formatPlainNumber(asNumberOrNull(row.spread)))}</td><td>${escapeHtml(abstained)}</td></tr>`,
    );
  }
  out.push('</tbody></table>');

  out.push('<h2>Main arguments and strongest dissent</h2>');
  out.push(hList(asArray(model.main_reasons)));
  out.push(`<p>Strongest dissent: ${escapeHtml(asStringOrNull(model.strongest_dissent) ?? 'none recorded')}</p>`);

  out.push('<h2>Constraints, assumptions, and unknowns</h2>');
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
  out.push('<h3>Assumptions</h3>');
  const assumptions = asArray(brief.assumptions);
  out.push(assumptions.length > 0 ? hList(assumptions) : '<ul><li>none recorded</li></ul>');
  out.push('<h3>Unknowns</h3>');
  const unknowns = [...asArray(brief.unknowns), ...asArray(model.critical_unknowns)];
  out.push(unknowns.length > 0 ? hList(unknowns) : '<ul><li>none recorded</li></ul>');

  out.push('<h2>Amendments and ratification</h2>');
  const amendments = asRecord(model.amendments);
  const describeAmendment = (value: unknown): string => {
    const amendment = asRecord(value);
    return `${asString(amendment.amendment_id)} by ${asString(amendment.proposing_seat_id)}: ${asString(amendment.statement)} (${asString(amendment.materiality)}, ${asString(amendment.disposition)})`;
  };
  const accepted = asArray(amendments.accepted);
  out.push('<h3>Accepted amendments</h3>');
  out.push(accepted.length > 0 ? `<ul>${accepted.map((a) => `<li>${escapeHtml(describeAmendment(a))}</li>`).join('')}</ul>` : '<ul><li>none</li></ul>');
  const rejected = asArray(amendments.rejected);
  out.push('<h3>Rejected amendments</h3>');
  out.push(rejected.length > 0 ? `<ul>${rejected.map((a) => `<li>${escapeHtml(describeAmendment(a))}</li>`).join('')}</ul>` : '<ul><li>none</li></ul>');
  const ratification = asRecord(model.ratification);
  out.push(`<p>Ratification status: ${escapeHtml(asStringOrNull(ratification.status) ?? 'not applicable')}</p>`);
  const support = ratification.resolution_support as Record<string, unknown> | null;
  if (support) {
    out.push(
      `<p>Resolution support (weighted counts, not a probability): support ${escapeHtml(formatPlainNumber(asNumberOrNull(support.support)))}, conditional support ${escapeHtml(formatPlainNumber(asNumberOrNull(support.conditional_support)))}, opposition ${escapeHtml(formatPlainNumber(asNumberOrNull(support.opposition)))}, abstention ${escapeHtml(formatPlainNumber(asNumberOrNull(support.abstention)))}, bound to resolution ${escapeHtml(asString(support.resolution_sha256))}.</p>`,
    );
  }

  out.push('<h2>Action proposals and authorization boundaries</h2>');
  const proposals = asArray(model.action_proposals);
  if (proposals.length === 0) out.push('<ul><li>none</li></ul>');
  for (const proposalValue of proposals) {
    const proposal = asRecord(proposalValue);
    out.push(`<h3>${escapeHtml(asString(proposal.action_id))}: ${escapeHtml(asString(proposal.title))}</h3>`);
    out.push(`<p>${escapeHtml(asString(proposal.description))}</p>`);
    out.push(`<p>Rationale: ${escapeHtml(asString(proposal.rationale))}</p>`);
    out.push('<p>Acceptance criteria:</p>');
    out.push(hList(asArray(proposal.acceptance_criteria)));
    const depends = asArray(proposal.depends_on_action_ids).map(asString);
    out.push(`<p>Depends on: ${escapeHtml(depends.length > 0 ? depends.join(', ') : 'none')}<br>`);
    out.push(`Risk class: ${escapeHtml(asString(proposal.risk_class))}<br>`);
    out.push('Execution authorization: separate execution authorization is required before this proposal may be acted on.</p>');
  }
  out.push(`<p class="label">${escapeHtml(asString(model.authorization_notice))}</p>`);

  out.push('<h2>Test, stop conditions, and review criteria</h2>');
  out.push(`<p>Cheapest informative test: ${escapeHtml(asStringOrNull(model.cheapest_informative_test) ?? 'none recorded')}</p>`);
  out.push('<h3>Stop conditions</h3>');
  const stop = asArray(model.stop_criteria);
  out.push(stop.length > 0 ? hList(stop) : '<ul><li>none recorded</li></ul>');
  out.push('<h3>Outcome review criteria</h3>');
  const review = asArray(model.review_criteria);
  out.push(review.length > 0 ? hList(review) : '<ul><li>none recorded</li></ul>');

  out.push('<h2>Advisor detail</h2>');
  for (const seatValue of asArray(model.participating_seats)) {
    const seat = asRecord(seatValue);
    out.push(
      `<p>Participating seat: ${escapeHtml(asString(seat.display_name))} (${escapeHtml(asString(seat.seat_id))}), source qualification: ${escapeHtml(qualificationText(seat.qualification))}</p>`,
    );
  }
  for (const seatValue of asArray(model.seats)) {
    const seat = asRecord(seatValue);
    out.push(`<h3>${escapeHtml(asString(seat.display_name))}</h3>`);
    out.push(`<p>${escapeHtml(asString(seat.label))}</p>`);
    out.push(`<p>Source qualification: ${escapeHtml(qualificationText(seat.qualification))}<br>`);
    out.push(`Stance: ${escapeHtml(asString(seat.stance))}<br>`);
    out.push(`Preferred option: ${escapeHtml(asStringOrNull(seat.preferred_option_id) ?? 'none')}</p>`);
    const abstained = asArray(seat.abstained_option_ids).map(asString);
    if (abstained.length > 0) {
      out.push(`<p>Abstained on: ${escapeHtml(abstained.join(', '))}</p>`);
    }
    out.push('<p>Decisive arguments:</p>');
    out.push(hList(asArray(seat.decisive_arguments)));
    out.push(`<p>Strongest objection: ${escapeHtml(asString(seat.strongest_objection))}<br>`);
    out.push(`What would change my mind: ${escapeHtml(asString(seat.change_my_mind))}</p>`);
    const conditions = asArray(seat.conditions);
    if (conditions.length > 0) {
      out.push('<p>Conditions:</p><ul>');
      for (const conditionValue of conditions) {
        const condition = asRecord(conditionValue);
        out.push(
          `<li>${escapeHtml(asString(condition.id))}: ${escapeHtml(asString(condition.description))} (${escapeHtml(asString(condition.kind))}, ${escapeHtml(asString(condition.status))}${condition.blocking === true ? ', blocking' : ''})</li>`,
        );
      }
      out.push('</ul>');
    }
    const stance = asStringOrNull(seat.resolution_stance);
    if (stance !== null) out.push(`<p>Resolution stance: ${escapeHtml(stance)}</p>`);
  }

  pushWebTodayHtml(out, model);
  pushProvenanceHtml(out, model);
  out.push('</body>');
  out.push('</html>');
  return `${out.join('\n')}\n`;
}

function pushProvenanceHtml(out: string[], model: Record<string, unknown>): void {
  const provenance = asRecord(model.provenance);
  out.push('<h2>Source and provenance appendix</h2>');
  out.push(`<p>${escapeHtml(asString(provenance.note))}</p>`);
  out.push('<table><thead><tr><th>Evidence</th><th>Kind</th><th>Locator</th><th>SHA-256</th></tr></thead><tbody>');
  for (const entryValue of asArray(provenance.evidence_manifest)) {
    const entry = asRecord(entryValue);
    out.push(
      `<tr><td>${escapeHtml(asString(entry.evidence_id))}</td><td>${escapeHtml(asString(entry.source_kind))}</td><td>${escapeHtml(asString(entry.locator))}</td><td>${escapeHtml(asString(entry.sha256))}</td></tr>`,
    );
  }
  out.push('</tbody></table>');
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
 * the exact bytes of the Markdown and print HTML produced from the
 * same validated revision, and names the PDF deliverable as not ready
 * with its missing piece instead of omitting it silently.
 */
export function renderRecordJson(
  model: Record<string, unknown>,
  siblings: SiblingArtifact[],
): string {
  const record = {
    ...model,
    sibling_artifacts: [
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
