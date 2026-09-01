// ============================================================================
// Book Writer mini-app — U18 e2e helpers (shared by T1-T10)
// ----------------------------------------------------------------------------
// Small builders + assertions shared across the suite. Everything runs against
// the local offline harness (127.0.0.1) — never a real host, never a real
// client feed. No Anthropic ids, no {{...}} placeholders.
// ============================================================================

import { expect } from '@playwright/test';
import { CLIENTS } from '../fixtures/index.mjs';

export function linkFor(clientName, phase = 'P0-INTAKE') {
  const c = CLIENTS[clientName];
  return `/${c.slug}/${phase}?tk=${c.token}`;
}

export function fullUrl(clientName, phase) {
  const c = CLIENTS[clientName];
  // The client's OWN binding phase is authoritative (misfit = 401). When the
  // caller passes a phase, it must match the client's binding phase — for the
  // gate1 client that phase is GATE-1-title by default.
  const ph = phase || c.phaseId;
  return `${process.env.E2E_BASE_URL || 'http://127.0.0.1:9780'}/${c.slug}/${ph}?tk=${c.token}`;
}

// Warm-copy assertions — the anti-anxiety guard words must NEVER render.
export const BANNED = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

export async function assertNoBannedWords(page) {
  const text = await page.locator('body').innerText();
  for (const word of BANNED) {
    if (text.toLowerCase().includes(word)) {
      throw new Error(`BANNED WORD RENDERED: "${word}" (T5 warmth guard failed)`);
    }
  }
}

// Reset the in-memory store + stub GHL between tests.
export async function resetHarness(request) {
  await request.post('/__e2e/reset');
}

// Audit the stub GHL (isolation assertions).
export async function ghlHits(request) {
  const r = await request.get('/__e2e/ghl');
  return r.json();
}

// Flush a client's staged answers to the stub GHL (mirrors U12/U15 write-back).
export async function flushAnswers(request, token) {
  const r = await request.post('/__e2e/flush', { data: { token } });
  return r.json();
}

// The universal-link "warm UI" render check (T1).
export async function expectWarmUi(page, title = '') {
  await page.waitForSelector('.chrome');
  await page.waitForSelector('.card');
  await page.waitForSelector('.qcount');
  if (title) await page.waitForSelector(`h1.q-text:has-text("${title}")`, { timeout: 5000 });
}

// Answer the current question by typing, then advance. Waits for the question
// counter to move so a fast sequence of answers cannot outpace the SPA's async
// answer POST (the button is re-rendered per screen).
export async function typeAndAdvance(page, text, fromCount) {
  const field = page.locator('.tabpanel input.field-input, .tabpanel textarea.field-textarea').first();
  await expect(field).toBeVisible();
  await field.fill(text);
  await expect(page.locator('.primary')).toBeEnabled();
  await page.locator('.primary').click();
  if (fromCount != null) {
    await expect(page.locator('.qcount')).not.toHaveText(fromCount, { timeout: 10_000 });
  }
}

// Select a choice answer then advance (the segmented enum has no default).
export async function chooseAndAdvance(page, label, fromCount) {
  await page.locator('.seg-btn', { hasText: label }).click();
  await expect(page.locator('.primary')).toBeEnabled();
  await page.locator('.primary').click();
  if (fromCount != null) {
    await expect(page.locator('.qcount')).not.toHaveText(fromCount, { timeout: 10_000 });
  }
}

// Count questions on screen — the one-question-per-screen law.
export async function countQuestionCards(page) {
  return page.locator('h1.q-text').count();
}
