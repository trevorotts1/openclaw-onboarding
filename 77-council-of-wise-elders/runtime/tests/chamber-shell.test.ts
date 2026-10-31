/**
 * Chamber shell tests (W29 unit A).
 *
 * Runner:
 *   node --import tsx --test tests/chamber-shell.test.ts
 *
 * Tier A only: loopback HTTP on an ephemeral port, node:vm for the pure
 * helpers, and static reads of the shipped page. Browser behaviour (top bar
 * rows, dialogs, composer) is proven separately with Playwright.
 */

import assert from 'node:assert/strict';
import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

import { SEAT_IDS, validateDecisionBrief } from '../src/contracts/index.js';
import { DriverRefusal } from '../src/service/driver.js';
import { CouncilFrontDoor } from '../src/service/front-door.js';
import { buildServiceIdentity } from '../src/service/identity.js';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');

async function withDoor(run: (origin: string) => Promise<void>): Promise<void> {
  const door = new CouncilFrontDoor({
    identity: buildServiceIdentity({
      tenant_id: 'tenant-w29a',
      company_id: 'company-w29a',
      data_dir: 'w29a-data',
      started_at: '2026-10-19T12:00:00.000Z',
    }),
    ports: [0],
  });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  try {
    await run(started.origin as string);
  } finally {
    await door.stop();
  }
}

const CSS = 'text/css; charset=utf-8';
const JS = 'text/javascript; charset=utf-8';

/** The contract file list with each content type the front door must send. */
const CONTRACT_FILES: Array<[string, string]> = [
  ['chamber-theme.css', CSS],
  ['chamber-shell.css', CSS],
  ['chamber-decision.css', CSS],
  ['chamber-room.css', CSS],
  ['chamber-keypoints.css', CSS],
  ['chamber-seatcard.css', CSS],
  ['chamber-seats.js', JS],
  ['chamber-state.js', JS],
  ['chamber-live.js', JS],
  ['chamber-shell.js', JS],
  ['chamber-decision.js', JS],
  ['chamber-room.js', JS],
  ['chamber-keypoints.js', JS],
  ['chamber-seatcard.js', JS],
  ['demo-replay.json', 'application/json; charset=utf-8'],
  ['blackceo-logo.png', 'image/png'],
];

// ------------------------------------------------------------- front door

test('GET /chamber/ is the new shell page', async () => {
  await withDoor(async (origin) => {
    const res = await fetch(`${origin}/chamber/`);
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type') ?? '', /^text\/html/);
    const page = await res.text();
    assert.ok(page.includes('The chamber'));
    assert.match(page, /id="ch-topbar"/);
  });
});

test('every contract file on disk is served with its content type and nosniff', async () => {
  const mine = ['chamber-shell.css', 'chamber-shell.js', 'chamber-live.js', 'blackceo-logo.png'];
  for (const name of mine) assert.ok(existsSync(join(chamberDir, name)), `${name} ships with this unit`);
  const strict =
    process.env.CHAMBER_REQUIRE_ALL === '1' ||
    ['chamber-decision.js', 'chamber-room.js', 'chamber-keypoints.js', 'chamber-seatcard.js'].every((n) =>
      existsSync(join(chamberDir, n)),
    );
  await withDoor(async (origin) => {
    let served = 0;
    for (const [name, type] of CONTRACT_FILES) {
      const res = await fetch(`${origin}/chamber/${name}`);
      if (!existsSync(join(chamberDir, name))) {
        assert.ok(!strict, `${name} must exist once the chamber is integrated`);
        // Another unit's file that has not merged yet: it is on the allowlist but not on disk.
        assert.equal(res.status, 404, `${name} is absent so it must not be served`);
        continue;
      }
      served += 1;
      assert.equal(res.status, 200, name);
      assert.equal(res.headers.get('content-type'), type, name);
      assert.equal(res.headers.get('x-content-type-options'), 'nosniff', name);
      await res.arrayBuffer();
    }
    assert.ok(served >= mine.length);
  });
});

test('the logo is a real PNG with an alpha channel', () => {
  const bytes = readFileSync(join(chamberDir, 'blackceo-logo.png'));
  assert.equal(bytes.subarray(1, 4).toString('latin1'), 'PNG');
  assert.equal(bytes.readUInt8(25), 6, 'colour type 6 = RGBA, so the CSS mask has alpha to use');
  assert.ok(bytes.length < 20_000);
});

test('webp portraits are served as image/webp; a nested or odd path is not', async () => {
  const name = 'zz-shell-test.webp';
  const file = join(chamberDir, 'portraits', name);
  // Smallest valid RIFF/WEBP header; the front door sends bytes, it does not decode them.
  writeFileSync(file, Buffer.from('RIFF\u0016\u0000\u0000\u0000WEBPVP8L', 'latin1'));
  try {
    await withDoor(async (origin) => {
      const res = await fetch(`${origin}/chamber/portraits/${name}`);
      assert.equal(res.status, 200);
      assert.equal(res.headers.get('content-type'), 'image/webp');
      assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
      await res.arrayBuffer();

      const svg = await fetch(`${origin}/chamber/portraits/simon-sinek.svg`);
      assert.equal(svg.status, 200);
      assert.match(svg.headers.get('content-type') ?? '', /^image\/svg\+xml/);
      await svg.arrayBuffer();

      for (const bad of ['portraits/nested/x.webp', 'portraits/x.png', 'portraits/..%2Findex.html.webp']) {
        const miss = await fetch(`${origin}/chamber/${bad}`);
        assert.notEqual(miss.status, 200, bad);
        await miss.arrayBuffer();
      }
    });
  } finally {
    rmSync(file, { force: true });
  }
});

test('an unknown chamber file is a 404', async () => {
  await withDoor(async (origin) => {
    for (const path of ['nope.js', 'chamber-shell.js.map', '..%2Fpackage.json']) {
      const res = await fetch(`${origin}/chamber/${path}`);
      assert.equal(res.status, 404, path);
      await res.arrayBuffer();
    }
  });
});

// ------------------------------------------------------------- page structure

test('index.html has the contract skeleton, tags in contract order and the honest footer', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  assert.match(html, /<title>[^<]*The chamber[^<]*<\/title>/);

  const css = [...html.matchAll(/<link rel="stylesheet" href="\.\/([^"]+)">/g)].map((m) => m[1]);
  assert.deepEqual(css, [
    'chamber-theme.css',
    'chamber-shell.css',
    'chamber-decision.css',
    'chamber-advisory.css',
    'chamber-room.css',
    'chamber-keypoints.css',
    'chamber-seatcard.css',
    'chamber-cue.css',
  ]);
  const js = [...html.matchAll(/<script src="\.\/([^"]+)"><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(js, [
    'chamber-seats.js',
    'chamber-state.js',
    'chamber-live.js',
    'chamber-shell.js',
    'chamber-decision.js',
    'chamber-room.js',
    'chamber-keypoints.js',
    'chamber-seatcard.js',
    'chamber-advisory.js',
    'chamber-cue.js',
  ]);

  // Mount points in document order.
  const order = [
    '<body class="ch">',
    'class="ch-app"',
    'id="ch-topbar"',
    'id="ch-stepper"',
    'id="ch-banner"',
    'class="ch-main"',
    'id="ch-decision"',
    'class="ch-stage-grid"',
    'id="ch-room"',
    'id="ch-keypoints"',
    'class="ch-foot"',
    'id="ch-seatcard"',
    'id="ch-how"',
    'id="ch-sessions"',
    'id="ch-composer"',
  ];
  let at = -1;
  for (const marker of order) {
    const next = html.indexOf(marker);
    assert.ok(next > at, `${marker} must appear after the previous mount point`);
    at = next;
  }
  assert.match(html, /<header id="ch-topbar"/);
  assert.match(html, /<nav id="ch-stepper"/);
  assert.match(html, /<div id="ch-banner"[^>]*\shidden/);
  assert.match(html, /<section id="ch-decision"/);
  assert.match(html, /<section id="ch-room"/);
  assert.match(html, /<aside id="ch-keypoints"/);
  assert.match(html, /<footer class="ch-foot"/);
  for (const id of ['ch-seatcard', 'ch-how', 'ch-sessions', 'ch-composer']) {
    assert.match(html, new RegExp(`<dialog id="${id}"`), `${id} is a native dialog`);
  }

  assert.ok(
    html.includes(
      'Each council member is an AI perspective inspired by the published work of the named author. Not the individual and not an endorsement.',
    ),
  );
  for (const label of ['Brief', 'Openings', 'Fault lines', 'Debate', 'Vote', 'Verdict']) {
    assert.ok(html.includes(`<span class="ch-step-label">${label}</span>`), label);
  }
  for (const label of ['How it works', 'Past sessions', 'New question']) {
    assert.ok(html.includes(`>${label}</button>`), label);
  }
  assert.match(html, /<button type="submit"[^>]*id="ch-composer-submit"[^>]*\sdisabled/);
  assert.ok(html.includes("Leave empty to use this route's default."));
  assert.ok(html.includes('href="./advisors.html"'));
  assert.ok(html.includes('href="/status"'));
});

test('the old page markup is gone', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  for (const gone of ['live-root', 'live-room', 'sample-root', 'sample-toggle', 'council-journey-wrap', 'chamber-nav']) {
    assert.equal(html.includes(gone), false, `${gone} must be removed`);
  }
});

test('index.html and chamber-shell.js carry no external URL, no innerHTML and no fixture or demo text', () => {
  for (const name of ['index.html', 'chamber-shell.js']) {
    const text = readFileSync(join(chamberDir, name), 'utf8');
    assert.equal(/https?:\/\//.test(text), false, `${name}: no http(s) URL`);
    assert.equal(text.includes('innerHTML'), false, `${name}: textContent only`);
    assert.equal(text.includes('/Users/'), false, `${name}: no operator path`);
    for (const fixture of [
      'Pilot the revised',
      'Pilot with 10 clients',
      'done-for-you AI workforce',
      'Austin in-person',
      'Simon Sinek',
      '6 of 9 perspectives',
    ]) {
      assert.equal(text.includes(fixture), false, `${name}: no fixture text "${fixture}"`);
    }
  }
});

test('chamber-shell.css has no colour literal; colours come from the --ch tokens', () => {
  const css = readFileSync(join(chamberDir, 'chamber-shell.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  assert.equal(/#[0-9a-fA-F]{3,8}\b/.test(css), false, 'no hex colour');
  assert.equal(/\b(?:rgb|rgba|hsl|hsla)\(/.test(css), false, 'no rgb or hsl colour');
  assert.ok(css.includes('var(--ch-'));
});

// ------------------------------------------------------------- pure helpers

interface Brief {
  schema_version: string;
  brief_id: string;
  session_id: string;
  revision: number;
  question: string;
  facts: Array<{ id: string; statement: string; evidence_ids: string[] }>;
  options: Array<{ id: string; label: string; kind: string }>;
  relevance_weights: Record<string, number>;
  assumptions: unknown[];
  unknowns: unknown[];
  constraints: unknown[];
  critical_domains: unknown[];
  evidence_manifest: unknown[];
  private_preference_ref: null;
  created_at: string;
  display_timezone: string;
}
interface Shell {
  buildBrief(input: Record<string, unknown>): Brief;
  stepperModel(view: unknown): Array<{ key: string; label: string; status: string }>;
}

function loadShell(): Shell {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-shell.js'), 'utf8'), sandbox);
  const ns = sandbox.councilChamber as { shell: Shell };
  return ns.shell;
}

/** Across the vm boundary prototypes differ; compare and validate plain JSON. */
function plain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const NOW = '2026-10-19T18:30:00.123Z';
const KINDS = [
  { label: 'Launch to everyone in January', kind: 'change' },
  { label: 'Keep things as they are', kind: 'status_quo' },
  { label: 'Run a small test first', kind: 'bounded_test' },
  { label: 'Something else entirely', kind: 'other' },
];

test('buildBrief passes validateDecisionBrief for 2, 3 and 4 options, with and without context', () => {
  const shell = loadShell();
  for (const count of [2, 3, 4]) {
    for (const context of ['', 'We have 40 clients.\n\n  Delivery is two people.  \r\nBudget is fixed.']) {
      const brief = plain(
        shell.buildBrief({
          question: '  Should we do it?  ',
          options: KINDS.slice(0, count),
          context,
          now: NOW,
          timeZone: 'America/Chicago',
          seatIds: [...SEAT_IDS],
        }),
      );
      const checked = validateDecisionBrief(brief);
      assert.equal(checked.ok, true, JSON.stringify(checked));
      assert.equal(brief.schema_version, 'wise-elders.brief/v1');
      assert.equal(brief.brief_id, 'brief-draft');
      assert.equal(brief.session_id, 'draft');
      assert.equal(brief.revision, 1);
      assert.equal(brief.question, 'Should we do it?');
      assert.deepEqual(
        brief.options.map((o) => o.id),
        ['A', 'B', 'C', 'D'].slice(0, count),
      );
      assert.deepEqual(
        brief.options.map((o) => o.kind),
        KINDS.slice(0, count).map((o) => o.kind),
      );
      assert.deepEqual(Object.keys(brief.relevance_weights).sort(), [...SEAT_IDS].sort());
      assert.equal(Object.keys(brief.relevance_weights).length, 9);
      assert.ok(Object.values(brief.relevance_weights).every((w) => w === 2));
      assert.equal(brief.created_at, NOW);
      assert.equal(brief.display_timezone, 'America/Chicago');
      assert.equal(brief.private_preference_ref, null);
      for (const key of ['assumptions', 'unknowns', 'constraints', 'critical_domains', 'evidence_manifest'] as const) {
        assert.deepEqual(brief[key], [], key);
      }
      assert.deepEqual(
        brief.facts,
        context
          ? [
              { id: 'fact-1', statement: 'We have 40 clients.', evidence_ids: [] },
              { id: 'fact-2', statement: 'Delivery is two people.', evidence_ids: [] },
              { id: 'fact-3', statement: 'Budget is fixed.', evidence_ids: [] },
            ]
          : [],
      );
    }
  }
});

test('buildBrief defaults: kind from the select label, unknown kind is other, blank options skipped, max four', () => {
  const shell = loadShell();
  const brief = plain(
    shell.buildBrief({
      question: 'Q?',
      options: [
        { label: 'One', kind: 'Keep as is' },
        { label: '   ', kind: 'change' },
        { label: 'Two', kind: 'Small test' },
        { label: 'Three', kind: 'Change' },
        { label: 'Four' },
        { label: 'Five', kind: 'Other' },
      ],
      seatIds: ['simon-sinek'],
    }),
  );
  assert.deepEqual(
    brief.options.map((o) => [o.id, o.label, o.kind]),
    [
      ['A', 'One', 'status_quo'],
      ['B', 'Two', 'bounded_test'],
      ['C', 'Three', 'change'],
      ['D', 'Four', 'other'],
    ],
  );
  assert.deepEqual(brief.relevance_weights, { 'simon-sinek': 2 });
  assert.equal(validateDecisionBrief(brief).ok, true);
  assert.equal(brief.display_timezone.length > 0, true);
  assert.match(brief.created_at, /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/);
});

test('buildBrief does not weaken the contract: an empty seat list or no options still fails validation, never silently passes', () => {
  const shell = loadShell();
  const noOptions = plain(shell.buildBrief({ question: 'Q?', options: [], seatIds: [...SEAT_IDS], now: NOW }));
  assert.equal(validateDecisionBrief(noOptions).ok, false);
  assert.deepEqual(plain(shell.buildBrief({ question: 'Q?', options: KINDS, now: NOW })).relevance_weights, {});
});

test('stepperModel: no session means Brief is current; a session passes its steps through', () => {
  const shell = loadShell();
  for (const view of [null, undefined, { session: null }, { mode: 'empty', session: null }]) {
    const model = plain(shell.stepperModel(view));
    assert.deepEqual(
      model.map((s) => s.label),
      ['Brief', 'Openings', 'Fault lines', 'Debate', 'Vote', 'Verdict'],
    );
    assert.deepEqual(
      model.map((s) => s.status),
      ['current', 'todo', 'todo', 'todo', 'todo', 'todo'],
    );
  }
  const steps = [
    { key: 'brief', label: 'Brief', status: 'done' },
    { key: 'openings', label: 'Openings', status: 'done' },
    { key: 'fault_lines', label: 'Fault lines', status: 'skipped' },
    { key: 'debate', label: 'Debate', status: 'current' },
    { key: 'vote', label: 'Vote', status: 'todo' },
    { key: 'verdict', label: 'Verdict', status: 'todo' },
  ];
  const model = plain(shell.stepperModel({ session: { steps } }));
  assert.deepEqual(model.map((s) => s.status), ['done', 'done', 'skipped', 'current', 'todo', 'todo']);
  assert.equal(model.filter((s) => s.status === 'current').length, 1);
  // An unknown status degrades to todo rather than rendering something odd.
  const odd = plain(shell.stepperModel({ session: { steps: [{ key: 'brief', label: 'Brief', status: 'weird' }] } }));
  assert.equal(odd[0].status, 'todo');
});

test('stepperModel: a completed session (every step done) still has exactly one current step, Verdict', () => {
  const shell = loadShell();
  const steps = ['brief', 'openings', 'fault_lines', 'debate', 'vote', 'verdict'].map((key) => ({ key, label: key, status: 'done' }));
  const model = plain(shell.stepperModel({ session: { steps } }));
  assert.equal(model.filter((s) => s.status === 'current').length, 1);
  assert.equal(model[5].status, 'current');
  assert.deepEqual(model.slice(0, 5).map((s) => s.status), ['done', 'done', 'done', 'done', 'done']);
});

test('chamber-shell.css: the single row starts at 1280px, the compact phone rule at 374px and the stepper strip is a positioned box', () => {
  const css = readFileSync(join(chamberDir, 'chamber-shell.css'), 'utf8');
  assert.match(css, /@media \(min-width: 1280px\)\s*\{\s*\.ch-top \{/);
  assert.match(css, /\.ch-top-steps \{[^}]*position: relative/);
  assert.match(css, /@media \(max-width: 374px\)\s*\{\s*\.ch-top-actions \{ gap: 4px/);
});

test('chamber-shell.css: on a phone the six steps wrap instead of scrolling sideways', () => {
  const css = readFileSync(join(chamberDir, 'chamber-shell.css'), 'utf8');
  const phone = css.slice(css.indexOf('@media (max-width: 599px)'), css.indexOf('@media (max-width: 374px)'));
  assert.match(phone, /\.ch-step-list \{[^}]*flex-wrap: wrap/);
  assert.equal(/overflow-x:\s*auto/.test(phone), false);
  assert.equal(phone.includes('max-content'), false);
});

test('the composer speaks plainly: no approval or allowance wording, no raw route codes', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  const js = readFileSync(join(chamberDir, 'chamber-shell.js'), 'utf8');
  assert.ok(html.includes('Convening starts the council now on the model you chose.'));
  const open = html.indexOf('class="ch-composer-approval"');
  const note = html.slice(html.indexOf('>', open) + 1, html.indexOf('</p>', open)).toLowerCase();
  for (const word of ['allowance', 'approv', 'budget']) assert.equal(note.includes(word), false, word);
  assert.ok(js.includes("'Not available for the council yet'"));
  assert.equal(js.includes('failure_code'), false, 'a raw failure code never reaches the screen');
});

test('index.html: every sr-only span in the stepper is the one the renderer reuses, so (current) is never announced twice', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  const nav = html.slice(html.indexOf('id="ch-stepper"'), html.indexOf('</nav>', html.indexOf('id="ch-stepper"')));
  const spans = nav.match(/<span class="[^"]*ch-sr-only[^"]*"/g) ?? [];
  assert.ok(spans.length > 0);
  for (const span of spans) assert.match(span, /ch-step-sr/);
  const brief = nav.slice(nav.indexOf('data-step="brief"'), nav.indexOf('</li>', nav.indexOf('data-step="brief"')));
  assert.equal((brief.match(/\(current\)/g) ?? []).length, 1);
});

test('chamber-shell.js: a past-sessions error never doubles its full stop', () => {
  const js = readFileSync(join(chamberDir, 'chamber-shell.js'), 'utf8');
  assert.ok(js.includes("String(list.error).replace(/\\.+\\s*$/, '')"));
});

test('chamber-shell.js never shows a literal {} or raw JSON as a refusal detail', () => {
  const js = readFileSync(join(chamberDir, 'chamber-shell.js'), 'utf8');
  assert.equal(js.includes('JSON.stringify(detail)'), false);
  assert.ok(js.includes('function detailText('));
});

test('a route refusal built without a detail reaches the browser with a readable detail, not {}', async () => {
  const door = new CouncilFrontDoor({
    identity: buildServiceIdentity({
      tenant_id: 'tenant-w29a',
      company_id: 'company-w29a',
      data_dir: 'w29a-data',
      started_at: '2026-10-19T12:00:00.000Z',
    }),
    ports: [0],
    convening: {
      routes: () => ({}) as never,
      convene: async () => {
        throw new DriverRefusal('ROUTE_NOT_COMPOSABLE', 'No approved budget covers ollama-cloud.', 'Approve the route budget.', 409);
      },
    },
  });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  try {
    const res = await fetch(`${started.origin as string}/api/council/convene`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sample: true, route_id: 'x', requested_by: 'chamber-composer' }),
    });
    assert.equal(res.status, 409);
    const body = (await res.json()) as { code: string; detail: unknown };
    assert.equal(body.code, 'ROUTE_NOT_COMPOSABLE');
    assert.equal(body.detail, 'No approved budget covers ollama-cloud.');
  } finally {
    await door.stop();
  }
});
