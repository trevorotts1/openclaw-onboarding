/**
 * Council-first chamber layout (CTR-137) and its completion (CTR-140).
 * Unexecuted by the lane that wrote it: Trevor runs it. Static source reads
 * only, no browser, no HTTP.
 *
 * Order under test, in every state: compact question and short status, then the
 * nine seats and the live discussion, then the option detail bars, then the
 * detailed answer, then the follow-up controls. Idle, active, blocked and
 * completed all read the same way: the bars hang below the council, never in
 * the header above the portraits. The side activity history is a native,
 * collapsed disclosure, and the PDF lane keeps one documented mount point
 * inside the results.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-layout.test.ts
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const read = (name: string): string => readFileSync(join(chamberDir, name), 'utf8');
const html = read('index.html');
const advisoryJs = read('chamber-advisory.js');
const decisionJs = read('chamber-decision.js');
const decisionCss = read('chamber-decision.css');
const advisoryCss = read('chamber-advisory.css');
const keypointsCss = read('chamber-keypoints.css');

const LITERAL = /#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b|\b(?:rgba?|hsla?)\(\s*[^)]*\)/;

/** Index of a marker, with a message naming the marker when it is absent. */
function at(text: string, marker: string): number {
  const i = text.indexOf(marker);
  assert.ok(i >= 0, `${marker} is missing`);
  return i;
}

test('document order is question, council, options, answer, activity rail', () => {
  const order = ['id="ch-decision"', 'class="ch-stage-grid"', 'id="ch-room"', 'id="ch-keypoints"', 'id="ch-options"', 'id="ch-advisory"', 'class="ch-foot"'];
  let previous = -1;
  for (const marker of order) {
    const next = at(html, marker);
    assert.ok(next > previous, `${marker} must come after the previous mount point`);
    previous = next;
  }
  // No long answer or option detail above the room: neither the advisory panel
  // nor the option panel is inside the stage grid.
  assert.ok(at(html, 'id="ch-advisory"') > at(html, 'id="ch-room"'), 'the answer sits below the council');
  const grid = html.slice(at(html, 'class="ch-stage-grid"'), html.indexOf('</div>', at(html, 'id="ch-keypoints"')));
  assert.equal(grid.includes('id="ch-advisory"'), false, 'the answer is not a grid column');
  assert.equal(grid.includes('id="ch-options"'), false, 'the option bars are not a grid column');
  assert.equal(html.split('id="ch-options"').length, 2, 'exactly one option mount point');
});

test('the side activity history is a native disclosure, collapsed by default', () => {
  assert.match(
    html,
    /<details class="ch-panel ch-activity">\s*<summary class="ch-activity-summary">Activity history<\/summary>\s*<aside id="ch-keypoints"/,
  );
  const open = html.slice(at(html, '<details class="ch-panel ch-activity"'), html.indexOf('>', at(html, '<details class="ch-panel ch-activity"')));
  assert.equal(/\sopen(\s|=|>)/.test(open), false, 'the disclosure starts closed');
  // Event content and the live wiring stay exactly as they were.
  const keypointsJs = read('chamber-keypoints.js');
  assert.match(keypointsJs, /getElementById\('ch-keypoints'\)/);
  assert.match(keypointsJs, /aria-live/);
  assert.match(keypointsCss, /\.ch-activity-summary\s*{[^}]*min-height:\s*44px/);
  assert.match(keypointsCss, /\.ch-activity \.ch-kp\s*{[^}]*background:\s*none/);
});

test('the advisory panel renders results before the follow-up controls', () => {
  const order = [
    'host.appendChild(head)',
    'host.appendChild(els.reasons.node)',
    'host.appendChild(els.conditions.node)',
    'host.appendChild(els.objection.node)',
    'host.appendChild(els.steps.node)',
    'host.appendChild(els.unknowns.node)',
    'host.appendChild(els.optionsWrap)',
    'host.appendChild(next)',
    'host.appendChild(els.pdf)',
    'host.appendChild(actions)',
    'host.appendChild(els.follow)',
  ];
  let previous = -1;
  for (const marker of order) {
    const next = at(advisoryJs, marker);
    assert.ok(next > previous, `${marker} must come after the previous block`);
    previous = next;
  }
});

test('the PDF lane keeps one empty, documented mount point inside the results', () => {
  assert.match(advisoryJs, /els\.pdf\.id = 'ch-adv-pdf-slot'/);
  assert.match(advisoryJs, /data-integration-anchor', 'ctr136-pdf'/);
  assert.match(advisoryJs, /els\.pdf = el\('div', 'ch-adv-pdf'\)/);
  assert.match(advisoryCss, /\.ch-adv-pdf:empty\s*{\s*display:\s*none/);
  // No button and no endpoint are invented here. The only URL-shaped literal
  // allowed is the inert SVG namespace, and only as one complete quoted string.
  // The scan is honestly broad: after that literal is removed, no URI scheme in
  // `scheme://` form (http(s), ws(s), ftp, file, data, custom) and no quoted
  // protocol-relative `//` may remain. Line comments are not URL literals.
  const svgNamespace = "'http://www.w3.org/2000/svg'";
  assert.equal(advisoryJs.split(svgNamespace).length - 1, 1, 'exactly one complete quoted SVG namespace literal');
  const withoutNamespace = advisoryJs.split(svgNamespace).join('');
  assert.equal(/[a-z][a-z0-9+.-]*:\/\//i.test(withoutNamespace), false, 'no URI scheme in URL form other than the inert SVG namespace');
  assert.equal(/["']\s*\/\//.test(withoutNamespace), false, 'no quoted protocol-relative URL');
  assert.equal(advisoryJs.includes('ch-adv-pdf-slot') && advisoryJs.includes('fetch('), false, 'no request from the anchor');
});

test('the compact header carries the view status, and stays one line once answered', () => {
  assert.match(decisionJs, /ch-decision-status/);
  assert.match(decisionJs, /session\.statusText/);
  assert.match(decisionCss, /\.ch-dec-status\s*{/);
  assert.match(decisionCss, /\.ch-dec\.ch-dec--answered\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
});

test('option bars sit below the council in idle, active, blocked and completed states', () => {
  // Placement is structural, not per status: the compact header receives only
  // the title column, and the rows are appended to #ch-options on every render.
  assert.match(decisionJs, /var optionsHost = document\.getElementById\('ch-options'\) \|\| host;/);
  assert.match(decisionJs, /host\.appendChild\(titleCol\)/);
  assert.match(decisionJs, /optionsHost\.appendChild\(list\)/);
  assert.equal(
    decisionJs.includes('host.appendChild(list)'),
    false,
    'the bars never return to the header above the portraits',
  );

  // Idle: the panel is hidden with the empty state, so no bare box is left behind.
  assert.match(decisionJs, /setHidden\(optionsHost, empty \|\| model\.length === 0\)/);

  // Active and blocked: the same partial bars stay visible below the council,
  // under a caption that says they are not the verdict. No status branch moves
  // them above the room, and the caption word choice for rejected responses is
  // left to the lane that owns it.
  assert.match(decisionJs, /var note = el\('p', 'ch-dec-note'\)/);
  assert.match(decisionJs, /These shares are a live snapshot, not the final verdict\./);
  assert.equal(/ch-dec--active|ch-dec--blocked/.test(decisionCss), false, 'no status-specific placement');

  // Completed: hidden only when the advisory panel carries the full options, so
  // the choices are never printed twice. A completed session with no verdict has
  // no advisory panel and keeps its bars below the council.
  assert.match(advisoryJs, /classList\.toggle\('ch-has-answer', on\)/);
  assert.match(advisoryJs, /markDecision\(true\)/);
  assert.match(decisionCss, /\.ch-has-answer \.ch-dec-options-panel\s*{\s*display:\s*none/);
  assert.equal(decisionCss.includes('.ch-has-answer .ch-dec {'), false, 'the header itself is never hidden');

  // IDs and listeners survive the move.
  assert.match(decisionJs, /title\.id = 'ch-decision-title'/);
  assert.match(decisionJs, /statusLine\.id = 'ch-decision-status'/);
  assert.match(decisionJs, /list\.setAttribute\('aria-label', 'Options'\)/);
  assert.match(decisionJs, /ns\.live\.subscribe\(render\)/);

  // No empty second column or gap in any state.
  assert.equal(decisionCss.includes('46%'), false, 'no leftover two-column header');
  const base = decisionCss.slice(at(decisionCss, '.ch-dec {'), decisionCss.indexOf('}', at(decisionCss, '.ch-dec {')));
  assert.match(base, /grid-template-columns:\s*minmax\(0,\s*1fr\)/);

  // The CTR-136 PDF anchor inside the results is preserved untouched.
  assert.match(advisoryJs, /els\.pdf\.id = 'ch-adv-pdf-slot'/);
  assert.match(advisoryJs, /data-integration-anchor', 'ctr136-pdf'/);
});

test('every touched stylesheet still uses tokens only', () => {
  for (const [name, css] of [['chamber-decision.css', decisionCss], ['chamber-advisory.css', advisoryCss], ['chamber-keypoints.css', keypointsCss]] as const) {
    assert.deepEqual(css.match(LITERAL) ?? [], [], `${name} carries a raw colour`);
    assert.ok(/var\(--ch-/.test(css), `${name} uses the theme tokens`);
  }
});
