// W74-B runnable check: render one SYNTHETIC fixture session (clearly
// labeled synthetic) through the counsel artifact renderer and assert
// the artifact contract:
//   1. the five sections appear in order (header, consensus, elders,
//      actions, footer),
//   2. the nine seat images are present (plus the cover band),
//   3. no absolute paths anywhere in the HTML (assets are relative),
// plus the surrounding guarantees: assets are copied beside the page,
// the render is deterministic, a hostile session_id is rejected, a
// missing seat emblem fails before any HTML is written, runtime strings
// are HTML-escaped, and PDF probing degrades to print-from-browser
// without ever blocking or faking a PDF.
//
// Run: node --test scripts/tests/render-counsel-artifact.test.mjs

import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import {
  SEAT_IDS,
  maybeRenderPdf,
  probePdfRenderer,
  renderArtifact,
} from '../render-counsel-artifact.mjs';

// A real 1x1 PNG (67 bytes) used as a synthetic stand-in for the seat
// art, so this check runs anywhere and never depends on generated art.
const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

function makeSyntheticAssets() {
  const dir = mkdtempSync(join(tmpdir(), 'w74b-assets-'));
  writeFileSync(join(dir, 'cover.png'), PNG_1X1);
  for (const seat of SEAT_IDS) {
    writeFileSync(join(dir, `seat-${seat}.png`), PNG_1X1);
  }
  return dir;
}

/** The synthetic fixture session, clearly labeled synthetic. */
function syntheticSessionRecord() {
  return {
    session_id: 'sess-w74b-synthetic-fixture',
    client_name: 'SYNTHETIC CLIENT (fixture)',
    date: 'January 1, 2026',
    decision: 'SYNTHETIC DECISION: should the fixture council convene?',
    question_count: 4,
    model_used: 'SYNTHETIC MODEL (fixture)',
    synthetic: true,
    cards: SEAT_IDS.map((seat) => ({
      seat_id: seat,
      take: `SYNTHETIC TAKE from ${seat}: <strong>unescaped probe</strong> & more.`,
    })),
    verdict: {
      consensus: 'SYNTHETIC CONSENSUS: convene the fixture council.',
      action_steps: ['SYNTHETIC STEP one.', 'SYNTHETIC STEP two.', 'SYNTHETIC STEP three.'],
    },
  };
}

function renderFixture() {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  const assetsDir = makeSyntheticAssets();
  const result = renderArtifact(syntheticSessionRecord(), {
    dataDir,
    assetsDir,
    pdf: false,
    linkBase: 'https://council.example',
  });
  const html = readFileSync(result.path, 'utf8');
  return { dataDir, assetsDir, result, html };
}

test('synthetic fixture renders the five sections in order, nine images, no absolute paths', () => {
  const { dataDir, assetsDir, result, html } = renderFixture();
  try {
    // Labeled synthetic.
    assert.match(html, /SYNTHETIC FIXTURE/);
    assert.match(html, /SYNTHETIC CLIENT \(fixture\)/);

    // 1. Five sections in order.
    const markers = [
      '<header data-section="header">',
      '<section data-section="consensus">',
      '<section data-section="elders">',
      '<section data-section="actions">',
      '<footer data-section="footer">',
    ];
    const order = markers.map((marker) => html.indexOf(marker));
    for (const index of order) {
      assert.notEqual(index, -1, 'every section marker is present');
    }
    for (let i = 1; i < order.length; i += 1) {
      assert.ok(order[i] > order[i - 1], 'section markers appear in the fixed order');
    }

    // 2. Nine elder images (seat emblems) plus the cover band.
    const seatImgs = [...html.matchAll(/src="assets\/seat-([a-z-]+)\.png"/g)].map((m) => m[1]);
    assert.equal(seatImgs.length, 9, 'nine seat emblem images');
    assert.deepEqual([...seatImgs].sort(), [...SEAT_IDS].sort(), 'one image per seat');
    assert.match(html, /src="assets\/cover\.png"/, 'cover band image present');

    // 3. No absolute paths: every asset reference is relative and the
    // rendered page never leaks a filesystem path.
    assert.doesNotMatch(html, /src="\/|href="\//, 'no root-absolute references');
    assert.doesNotMatch(html, /file:\/\//, 'no file: URLs');
    assert.doesNotMatch(html, /\/Users\//, 'no home-directory paths');
    assert.doesNotMatch(html, /C:\\/, 'no Windows absolute paths');
    const escapeRe = (s) => new RegExp(s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    assert.doesNotMatch(html, escapeRe(dataDir), 'no leaked data dir');
    assert.doesNotMatch(html, escapeRe(assetsDir), 'no leaked assets dir');

    // The rest of the contract.
    assert.equal(
      result.link,
      'https://council.example/artifacts/sess-w74b-synthetic-fixture/index.html',
    );
    assert.equal(
      result.path,
      join(dataDir, 'artifacts', 'sess-w74b-synthetic-fixture', 'index.html'),
    );
    assert.ok(existsSync(result.path), 'index.html written');

    // Assets copied beside the page (relative paths only).
    const assetsOut = join(dataDir, 'artifacts', 'sess-w74b-synthetic-fixture', 'assets');
    assert.ok(existsSync(join(assetsOut, 'cover.png')), 'cover copied');
    for (const seat of SEAT_IDS) {
      assert.ok(existsSync(join(assetsOut, `seat-${seat}.png`)), `seat-${seat} copied`);
    }

    // Header content comes from runtime data, footer carries the sitting facts.
    assert.match(html, /The decision/);
    assert.match(html, /Model: SYNTHETIC MODEL \(fixture\)/);
    assert.match(html, /Questions in the sitting: 4/);
    assert.match(html, /January 1, 2026/);

    // Action steps render as a numbered list in record order.
    const ol = html.slice(
      html.indexOf('data-section="actions"'),
      html.indexOf('data-section="footer"'),
    );
    assert.ok(ol.indexOf('SYNTHETIC STEP one.') < ol.indexOf('SYNTHETIC STEP two.'));
    assert.ok(ol.indexOf('SYNTHETIC STEP two.') < ol.indexOf('SYNTHETIC STEP three.'));

    // Nine elder cards, each with name, lane, take, and honesty label.
    assert.equal([...html.matchAll(/class="elder-card"/g)].length, 9, 'nine elder cards');
    assert.equal([...html.matchAll(/class="lane"/g)].length, 9, 'a lane per card');
    assert.equal([...html.matchAll(/class="seat-label"/g)].length, 9, 'a honesty label per card');

    // Runtime strings are escaped, never raw markup.
    assert.doesNotMatch(html, /<strong>unescaped probe<\/strong>/);
    assert.match(html, /&lt;strong&gt;unescaped probe&lt;\/strong&gt;/);

    // Print-ready CSS with page-break rules per elder card.
    assert.match(html, /page-break-inside: avoid/);
    assert.match(html, /@media print/);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
    rmSync(assetsDir, { recursive: true, force: true });
  }
});

test('the render is deterministic: same record, same bytes', () => {
  const a = renderFixture();
  const b = renderFixture();
  try {
    assert.equal(a.html, b.html, 'HTML is a pure function of the record');
  } finally {
    for (const r of [a, b]) {
      rmSync(r.dataDir, { recursive: true, force: true });
      rmSync(r.assetsDir, { recursive: true, force: true });
    }
  }
});

test('a hostile session_id is rejected before anything is written', () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  const assetsDir = makeSyntheticAssets();
  try {
    for (const bad of ['../escape', 'a/b', '', '.hidden', 'x y']) {
      assert.throws(
        () =>
          renderArtifact(
            { ...syntheticSessionRecord(), session_id: bad },
            { dataDir, assetsDir, pdf: false },
          ),
        TypeError,
        `session_id ${JSON.stringify(bad)} is refused`,
      );
    }
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
    rmSync(assetsDir, { recursive: true, force: true });
  }
});

test('a missing seat emblem fails the render before any HTML is written', () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  const assetsDir = makeSyntheticAssets();
  rmSync(join(assetsDir, 'seat-les-brown.png'));
  try {
    assert.throws(
      () => renderArtifact(syntheticSessionRecord(), { dataDir, assetsDir, pdf: false }),
      /seat-les-brown/,
    );
    assert.equal(
      existsSync(join(dataDir, 'artifacts', 'sess-w74b-synthetic-fixture', 'index.html')),
      false,
      'no artifact page written when assets are incomplete',
    );
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
    rmSync(assetsDir, { recursive: true, force: true });
  }
});

test('a record missing seats or carrying a duplicate seat is rejected', () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  const assetsDir = makeSyntheticAssets();
  try {
    const oneMissing = syntheticSessionRecord();
    oneMissing.cards = oneMissing.cards.slice(0, 8);
    assert.throws(
      () => renderArtifact(oneMissing, { dataDir, assetsDir, pdf: false }),
      /missing seats/,
    );

    const duplicate = syntheticSessionRecord();
    duplicate.cards[1] = { ...duplicate.cards[0] };
    assert.throws(
      () => renderArtifact(duplicate, { dataDir, assetsDir, pdf: false }),
      /duplicate seat_id/,
    );
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
    rmSync(assetsDir, { recursive: true, force: true });
  }
});

test('PDF degrades to print-from-browser without blocking when no renderer exists', () => {
  const outcome = maybeRenderPdf('/nonexistent/index.html', {
    probe: { method: null, command: null },
  });
  assert.deepEqual(outcome, { status: 'print-from-browser', method: null, pdfPath: null });
});

test('PDF degrades to print-from-browser when the renderer fails, and never fakes a PDF', () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  try {
    writeFileSync(join(dataDir, 'index.html'), '<!doctype html><title>x</title>');
    const failingSpawn = () => {
      throw new Error('renderer exploded');
    };
    const outcome = maybeRenderPdf(join(dataDir, 'index.html'), {
      probe: { method: 'chrome-headless', command: '/fake/chrome' },
      spawnImpl: failingSpawn,
    });
    assert.equal(outcome.status, 'print-from-browser');
    assert.equal(outcome.pdfPath, null);
    assert.equal(existsSync(join(dataDir, 'index.pdf')), false, 'no PDF is invented');
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('PDF renders through a real renderer when the spawn succeeds', () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w74b-data-'));
  try {
    writeFileSync(join(dataDir, 'index.html'), '<!doctype html><title>x</title>');
    const fakeSpawn = (_cmd, args) => {
      const out = args.find((a) => a.startsWith('--print-to-pdf='))?.slice('--print-to-pdf='.length);
      writeFileSync(out, '%PDF-1.4 synthetic');
      return { status: 0 };
    };
    const outcome = maybeRenderPdf(join(dataDir, 'index.html'), {
      probe: { method: 'chrome-headless', command: '/fake/chrome' },
      spawnImpl: fakeSpawn,
    });
    assert.equal(outcome.status, 'rendered');
    assert.ok(existsSync(outcome.pdfPath));
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('probePdfRenderer returns a structured answer and never throws', () => {
  const probe = probePdfRenderer({ PATH: '/nonexistent-bin-dir', HOME: '/nonexistent-home' });
  assert.ok(['chrome-headless', 'cupsfilter', null].includes(probe.method));
  assert.equal(typeof probe.command === 'string' || probe.command === null, true);
});
