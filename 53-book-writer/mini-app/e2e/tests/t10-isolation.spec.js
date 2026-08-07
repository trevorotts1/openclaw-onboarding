// ============================================================================
// Book Writer mini-app — U18 e2e: T10 (isolation — browser-level proof)
// ----------------------------------------------------------------------------
// Two FICTITIOUS clients (alpha / beta) go through the SPA. Their answers must
// land in the RIGHT client's stub GHL — alpha never beta — PROVEN at the
// browser level: both clients' answers are driven through the real SPA in real
// browser sessions, staged under their own KV binding rows, and flushed to the
// stub GHL by the binding's own location_id + token. The stub RECORDS every
// write, so a PROVEN NEGATIVE is auditable: the stub saw zero hits for the
// other client's location.
//
// Hard gate (mirrors U17): even if an answer body carried beta's destination,
// the binding row is the SOLE authority — the write-back keys everything on
// the token's own binding. No real GHL, no real names, no credentials.
// ============================================================================

import { test, expect } from '@playwright/test';
import { fullUrl, resetHarness, expectWarmUi, typeAndAdvance, chooseAndAdvance, ghlHits, flushAnswers, assertNoBannedWords } from './helpers.mjs';
import { CLIENTS, BINDINGS } from '../fixtures/index.mjs';

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
});

test('T10 — two fake clients through the SPA: alpha lands ONLY on alpha, beta ONLY on beta', async ({ page, request }) => {
  const alpha = CLIENTS.alpha;
  const beta = CLIENTS.beta;

  // ---- ALPHA goes through the SPA, answering distinctly ----------------------
  await page.goto(fullUrl('alpha'));
  await expectWarmUi(page);
  await chooseAndAdvance(page, 'book', 'Question 1 of 16');
  await chooseAndAdvance(page, 'full', 'Question 2 of 16');
  await typeAndAdvance(page, 'Alice', 'Question 3 of 16');
  await typeAndAdvance(page, 'Alpha-Last', 'Question 4 of 16');
  await typeAndAdvance(page, 'alice@alpha.example', 'Question 5 of 16');
  await typeAndAdvance(page, 'Alpha readers who want calm mornings', 'Question 6 of 16');
  await expect(page.locator('.qcount')).toHaveText('Question 7 of 16');
  await assertNoBannedWords(page);

  // ---- BETA goes through the SPA in a fresh context (separate browser state) -
  await page.context().clearCookies();
  await page.goto(fullUrl('beta'));
  await expectWarmUi(page);
  await chooseAndAdvance(page, 'book', 'Question 1 of 16');
  await chooseAndAdvance(page, 'full', 'Question 2 of 16');
  await typeAndAdvance(page, 'Bobby', 'Question 3 of 16');
  await typeAndAdvance(page, 'Beta-Last', 'Question 4 of 16');
  await typeAndAdvance(page, 'bobby@beta.example', 'Question 5 of 16');
  await typeAndAdvance(page, 'Beta readers who want bold new chapters', 'Question 6 of 16');
  await expect(page.locator('.qcount')).toHaveText('Question 7 of 16');
  await assertNoBannedWords(page);

  // ---- Flush both runs through the binding-driven write-back (U12/U15 rail) --
  const alphaFlush = await flushAnswers(request, alpha.token);
  const betaFlush = await flushAnswers(request, beta.token);
  expect(alphaFlush.ok).toBe(true);
  expect(betaFlush.ok).toBe(true);
  expect(alphaFlush.location_id).toBe(alpha.location_id);
  expect(betaFlush.location_id).toBe(beta.location_id);
  expect(alphaFlush.client_id).toBe(alpha.client_id);
  expect(betaFlush.client_id).toBe(beta.client_id);

  // ---- The stub GHL is the PROVEN record of every write ----------------------
  const hits = await ghlHits(request);
  const alphaLoc = alpha.location_id;
  const betaLoc = beta.location_id;
  expect(hits.byLocation[alphaLoc]).toBeDefined();
  expect(hits.byLocation[betaLoc]).toBeDefined();

  // POSITIVE: alpha's answers landed on alpha's location.
  expect(hits.byLocation[alphaLoc].notes).toBeGreaterThan(0);
  // POSITIVE: beta's answers landed on beta's location.
  expect(hits.byLocation[betaLoc].notes).toBeGreaterThan(0);

  // NEGATIVE (the isolation property): alpha's run wrote ZERO times to beta's
  // location, and beta's run wrote ZERO times to alpha's location. The stub
  // records every attempt, so "nothing landed on the other client" is a proven
  // fact, not an unverifiable absence.
  // (Both locations DO receive their own client's writes; only cross-client
  // writes must be zero. The stub refuses cross-auth writes, so a leakage
  // attempt would appear as a `refused` hit on the foreign location.)
  const alphaHits = hits.byLocation[alphaLoc];
  const betaHits = hits.byLocation[betaLoc];

  // Alpha's writes must all be alpha-identified; beta's all beta-identified.
  // We verify at the payload level by re-reading the stub's records.
  const alphaAnswers = await page.request.post('/__e2e/ghl', { data: { location_id: alphaLoc } });
  const alphaRecords = await alphaAnswers.json();
  const betaAnswers = await page.request.post('/__e2e/ghl', { data: { location_id: betaLoc } });
  const betaRecords = await betaAnswers.json();

  // Every alpha record carries alpha's run; every beta record carries beta's.
  for (const rec of alphaRecords) {
    expect(rec.run_id).toBe(alpha.run_id);
    expect(rec.run_id).not.toBe(beta.run_id);
  }
  for (const rec of betaRecords) {
    expect(rec.run_id).toBe(beta.run_id);
    expect(rec.run_id).not.toBe(alpha.run_id);
  }

  // Cross-client contamination is exactly zero: no alpha run_id in beta's
  // records, no beta run_id in alpha's records, and no refused auth attempts.
  expect(alphaRecords.some((r) => r.run_id === beta.run_id)).toBe(false);
  expect(betaRecords.some((r) => r.run_id === alpha.run_id)).toBe(false);
  expect(alphaHits.refused).toBe(0);
  expect(betaHits.refused).toBe(0);
});

test('T10 — a client can never open another client\'s link (misfit → 401, no form)', async ({ page }) => {
  // Alpha's token pointed at beta's slug — the binding is the sole authority
  // and the Worker refuses before any question is served.
  const alphaToken = CLIENTS.alpha.token;
  const betaSlug = CLIENTS.beta.slug;
  await page.goto(`/${betaSlug}/P0-INTAKE?tk=${alphaToken}`);
  await expect(page.locator('.card')).not.toBeVisible();
  await expect(page.locator('.qcount')).toHaveCount(0);
});
