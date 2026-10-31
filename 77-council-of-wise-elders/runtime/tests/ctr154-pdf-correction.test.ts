/**
 * CTR-154 unexecuted regression (Trevor owns the run).
 *
 * Runner:
 *   node --import tsx --test tests/ctr154-pdf-correction.test.ts
 *
 * This is a static + pure-render contract, not a browser, PDF, HTTP or
 * live Council test. It pins the CTR-150 layout fixes and the CTR-154
 * corrections:
 * - no tiled page-frame or 24 mm divider over running text;
 * - nine served chamber portraits in the shared seat order on a full
 *   council cover, never the empty-table cover derivative;
 * - an omitted (`undefined`) consult field renders as a full council, and
 *   a consult renders exactly the one recorded seat with no plan/debate
 *   reading guide and no duplicate "The answer" map label;
 * - a redacted export embeds no image bytes and no static seat name;
 * - the cover is explicitly 255 mm tall, the printable body height;
 * - summary and plan before the long advisor record, with one explicit
 *   Part 2 page break and navigable section ids;
 * - long cards are splittable, small units stay whole;
 * - 15pt body, 14pt floor, safe A4 margins.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  loadReportPortraitDataUri,
  renderPrintHtml,
  REPORT_SEAT_PORTRAITS,
} from '../src/reports/index.js';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const skillDir = join(runtimeDir, '..');
const renderSource = readFileSync(
  join(runtimeDir, 'src', 'reports', 'render.ts'),
  'utf8',
);

function model(): Record<string, unknown> {
  return {
    session_id: 'sess-ctr150',
    decision_title: 'What is the best way to grow the channel?',
    report_date: '2026-10-30',
    session_mode: 'light',
    route_display: 'route-1',
    protocol_version: 'wise-elders.core/1.0.0',
    report_revision_id: 'report-1',
    redacted: false,
    sample: false,
    sample_notice: '',
    // CTR-154: explicit null is the no-consult shape. The renderer also
    // treats an omitted (undefined) field as no-consult; a separate test
    // deletes this key to pin that path.
    consult: null,
    simulation_label: 'Simulated advisory perspectives.',
    authorization_notice: 'Advice only. Every action needs its own approval.',
    verdict_block: {
      revision: 1,
      label: 'WAIT',
      recommended_option_id: 'opt-repurpose',
      recommended_option_label: 'Long-form repurposing',
    },
    summary: {
      in_short: 'The council recommends Long-form repurposing. The verdict was Wait.',
      verdict_label_text: 'Wait',
      reasons: ['Owned assets answer the capacity concern.'],
      biggest_concern: 'Production hours are unknown.',
      confidence: { evidence_strength_text: 'Limited', notes: ['Evidence was limited.'] },
      what_would_change_the_answer: ['If production hours cannot support it.'],
    },
    question_and_context: {
      question: 'What is the best way to grow the channel?',
      options: [],
      facts: [],
      assumptions: [],
      unknowns: [],
      constraints: [],
    },
    score_table: [],
    advisor_contributions: [],
    debate: { rounds_saved: 1, notes: [], rounds: [], changes: [], positions: [] },
    plan: {
      prerequisites: [],
      steps: [
        {
          step_number: 1,
          title: 'Publish one episode per week',
          what_to_do: 'Publish one repurposed episode each week.',
          why: 'It is the cheapest informative test.',
          depends_on_step_numbers: [],
          depends_on_missing_action_ids: [],
          done_when: ['Four episodes have shipped.'],
          risk_text: 'Medium risk',
          due_date: null,
          budget_text: null,
          helpful_tool_names: [],
        },
      ],
      cheapest_test: 'Publish four episodes.',
      stop_if: ['Stop if retention falls.'],
      review_criteria: ['Review retention after four episodes.'],
    },
    how_to_use: ['Read the summary, then the plan.'],
    your_tools: { items: [], note: 'No verified inventory was recorded.', limitations: [] },
    hard_constraints: [],
    amendments: { accepted: [], rejected: [] },
    ratification: { status: 'not_required' },
    provenance: { note: 'Identifiers only.', evidence_manifest: [] },
    web_today: [],
    source_pack_versions: [],
  };
}

test('stylesheet removes the tiled frame and oversized divider', () => {
  assert.equal(renderSource.includes('background-repeat: repeat-y'), false);
  assert.equal(renderSource.includes('data-report-frame'), false);
  assert.equal(renderSource.includes('--report-divider'), false);
  assert.equal(renderSource.includes('class="divider"'), false);
});

test('long cards can split; only small units avoid a page break', () => {
  const longCardRule = renderSource.slice(
    renderSource.indexOf('.option-block, .advisor-card, .tool-card, .plan-step, .round-block {'),
    renderSource.indexOf('.option-block h3, .advisor-card h3'),
  );
  assert.ok(longCardRule.length > 0);
  assert.equal(longCardRule.includes('break-inside: auto'), true);
  assert.equal(longCardRule.includes('break-inside: avoid'), false);
  assert.equal(renderSource.includes('.summary-card {'), true);
  const summaryRule = renderSource.slice(
    renderSource.indexOf('.summary-card {'),
    renderSource.indexOf('.glance {'),
  );
  assert.equal(summaryRule.includes('break-inside: auto'), true);
});

test('cover uses the nine served chamber portraits in shared order', () => {
  const html = renderPrintHtml(model());
  assert.equal((html.match(/class="seat-portrait"/g) ?? []).length, 9);
  assert.equal(html.includes('cover-report.webp'), false);
  assert.equal(html.includes('file://'), false);
  assert.equal(/https?:\/\//.test(html), false);
  assert.ok(html.includes('alt="Simon Sinek"'));
  assert.ok(html.includes('alt="Les Brown"'));

  const config = JSON.parse(
    readFileSync(join(skillDir, 'config', 'advisors.json'), 'utf8'),
  ) as { seats: Array<{ seat_id: string; order: number }> };
  const expected = [...config.seats]
    .sort((a, b) => a.order - b.order)
    .map((seat) => seat.seat_id);
  assert.deepEqual(
    REPORT_SEAT_PORTRAITS.map((seat) => seat.seat_id),
    expected,
  );
  for (const seat of REPORT_SEAT_PORTRAITS) {
    const uri = loadReportPortraitDataUri(seat.seat_id);
    assert.ok(uri !== null && uri.startsWith('data:image/webp;base64,'), seat.seat_id);
    assert.ok((uri ?? '').length < 200000, `${seat.seat_id} stays small`);
  }
  assert.equal(loadReportPortraitDataUri('../../etc/passwd'), null);
});

function consultModel(): Record<string, unknown> {
  const value = model();
  value.consult = {
    seat_id: 'td-jakes',
    display_name: 'T. D. Jakes',
    label: 'Strategist',
    answer: 'Run the two-week test.',
    assumptions: ['The team can publish weekly.'],
    limits: ['No subscriber baseline was recorded.'],
    card_next_step: 'Publish one episode.',
    next_step: 'Publish one episode.',
  };
  return value;
}

test('an omitted consult field renders as a full council report', () => {
  const value = model();
  delete value.consult;
  const html = renderPrintHtml(value);
  assert.equal((html.match(/class="seat-portrait"/g) ?? []).length, 9);
  assert.ok(html.includes('href="#section-your-plan"'));
  assert.ok(html.includes('href="#section-what-each-advisor-said"'));
  assert.equal(html.includes('href="#section-the-consultation-answer"'), false);
});

test('a consult renders only its recorded seat, with no plan or debate guide', () => {
  const html = renderPrintHtml(consultModel());
  assert.equal((html.match(/class="seat-portrait"/g) ?? []).length, 1);
  assert.ok(html.includes('alt="T. D. Jakes"'));
  assert.ok(html.includes('<span>T. D. Jakes</span>'));
  assert.ok(
    html.includes('<a href="#section-the-consultation-answer">The consultation answer</a>'),
  );
  assert.ok(html.includes('<a href="#section-in-short">The answer</a>'));
  assert.equal(html.includes('href="#section-your-plan"'), false);
  assert.equal(html.includes('href="#section-what-each-advisor-said"'), false);
  assert.equal(html.includes('your numbered plan'), false);
  assert.equal(html.includes('each advisor, the debate'), false);
  assert.equal((html.match(/>The answer<\/a>/g) ?? []).length, 1);
});

test('a redacted full-council export embeds no image bytes or static seat name', () => {
  const value = model();
  value.redacted = true;
  value.redaction_profile_id = 'profile-1';
  const html = renderPrintHtml(value);
  assert.equal(html.includes('data:image/'), false);
  assert.equal((html.match(/class="seat-portrait"/g) ?? []).length, 0);
  assert.ok(html.includes('Redacted report: portraits and seat names are not printed.'));
  for (const seat of REPORT_SEAT_PORTRAITS) {
    assert.equal(html.includes(seat.display_name), false, seat.display_name);
    assert.equal(html.includes(seat.seat_id), false, seat.seat_id);
  }
  assert.ok(html.includes('id="section-in-short"'));
});

test('a redacted consult cover embeds no image bytes either', () => {
  const value = consultModel();
  value.redacted = true;
  value.redaction_profile_id = 'profile-1';
  const html = renderPrintHtml(value);
  assert.equal(html.includes('data:image/'), false);
  assert.equal((html.match(/class="seat-portrait"/g) ?? []).length, 0);
  assert.ok(html.includes('Redacted report: portraits and seat names are not printed.'));
});

test('cover is explicitly sized to the 255 mm printable body', () => {
  const coverRule = renderSource.slice(
    renderSource.indexOf('.report-cover {'),
    renderSource.indexOf('.report-cover-band {'),
  );
  assert.ok(coverRule.length > 0);
  assert.equal(coverRule.includes('height: 255mm'), true);
  assert.equal(coverRule.includes('width: 210mm'), true);
  assert.equal(coverRule.includes('min-height: 297mm'), false);
});

test('summary and plan come before the long advisor record', () => {
  const html = renderPrintHtml(model());
  const summary = html.indexOf('id="section-in-short"');
  const plan = html.indexOf('id="section-your-plan"');
  const advisors = html.indexOf('id="section-what-each-advisor-said"');
  const partTwo = html.indexOf('Part 2');
  assert.ok(summary >= 0 && plan > summary && advisors > plan);
  assert.ok(partTwo > plan && partTwo < advisors);
  assert.ok(html.includes('href="#section-your-plan"'));
  assert.ok(html.includes('href="#section-what-each-advisor-said"'));
  assert.ok(html.includes('href="#section-for-your-records"'));
});

test('15pt body, 14pt floor and safe A4 margins', () => {
  assert.match(renderSource, /body\s*\{[^}]*font-size:\s*15pt/s);
  assert.match(renderSource, /@page\s*\{[^}]*size:\s*A4;[^}]*margin:\s*17mm 20mm 22mm 20mm;/s);
  assert.match(renderSource, /@bottom-center\s*\{[^}]*font-size:\s*14pt/s);
  const sizes = [...renderSource.matchAll(/font-size:\s*([0-9.]+)pt/g)].map((match) =>
    Number(match[1]),
  );
  assert.ok(sizes.length >= 10);
  assert.ok(sizes.every((size) => size >= 14), `small sizes: ${sizes.join(', ')}`);
});
