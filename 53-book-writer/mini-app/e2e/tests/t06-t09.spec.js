// ============================================================================
// Book Writer mini-app — U18 e2e: T6-T9 (headless, offline)
// ----------------------------------------------------------------------------
// T6  recorder widget renders with permission/camera gates (graceful denial)
// T7  editable transcript + answer-your-way tabs switch modes
// T8  save & resume: reload -> resume at the next-unanswered question
// T9  completion screen + celebration after the last question
//
// Headless: a fake media device stub drives the recorder deterministically —
// no OS webcam/mic, no popups. No real client feeds. No Anthropic ids.
// ============================================================================

import { test, expect } from '@playwright/test';
import { fullUrl, assertNoBannedWords, resetHarness, expectWarmUi, typeAndAdvance, chooseAndAdvance } from './helpers.mjs';

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
});

// Walk the intake to the first media question (Q6 ideal_avatar).
async function goToMediaQuestion(page) {
  await page.goto(fullUrl('alpha'));
  await expectWarmUi(page);
  await chooseAndAdvance(page, 'book', 'Question 1 of 16');
  await chooseAndAdvance(page, 'full', 'Question 2 of 16');
  await typeAndAdvance(page, 'Anne', 'Question 3 of 16');
  await typeAndAdvance(page, 'Example', 'Question 4 of 16');
  await typeAndAdvance(page, 'anne@example.com', 'Question 5 of 16');
  await expect(page.locator('.qcount')).toHaveText('Question 6 of 16');
}

test.describe('T6 — recorder widget renders with permission/camera gates', () => {
  test('the media tab renders the recorder widget with its permission gate', async ({ page }) => {
    await goToMediaQuestion(page);
    await expect(page.locator('.tab', { hasText: 'Audio / video' })).toBeVisible();
    await page.locator('.tab', { hasText: 'Audio / video' }).click();

    await expect(page.locator('.rec')).toBeVisible();
    // Q6 ideal_avatar's media accept is audio+video -> the camera gate renders
    // (video channel): warm expect copy + a "Video" button that stays off until
    // a deliberate tap.
    await expect(page.locator('.rec-expect')).toContainText('camera stays off until you tap');
    await expect(page.locator('.rec-btn')).toHaveText('Video');
    // The timer element exists (empty until recording starts — assert presence).
    await expect(page.locator('.rec-timer')).toHaveCount(1);
    // The editable transcript is present, ready to hold the words.
    await expect(page.locator('textarea.transcript')).toBeVisible();
    await assertNoBannedWords(page);
  });

  test('graceful denial: microphone denied surfaces the warm typing path', async ({ page }) => {
    // Stub getUserMedia to DENY (permission not granted) — the deliberate tap
    // must surface a warm message and keep the typing path, never a blank.
    await page.addInitScript(() => {
      const orig = navigator.mediaDevices;
      if (orig && orig.getUserMedia) {
        orig.getUserMedia = () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
      }
    });
    await goToMediaQuestion(page);
    await page.locator('.tab', { hasText: 'Audio / video' }).click();
    await page.locator('.rec-btn').click();

    // Warm toast: microphone couldn't open, type instead.
    await expect(page.locator('#toast')).toHaveText(/couldn't open the microphone/);
    await expect(page.locator('textarea.transcript')).toBeVisible();
    await assertNoBannedWords(page);
  });

  test('granted permission: a tap starts the recorder (Stop state)', async ({ page, context }) => {
    // Grant the microphone permission. Chromium is launched with a fake media
    // device (--use-fake-device-for-media-stream), so getUserMedia resolves a
    // REAL fake stream — MediaRecorder can record, and the button flips to Stop.
    await context.grantPermissions(['microphone']);
    await goToMediaQuestion(page);
    await page.locator('.tab', { hasText: 'Audio / video' }).click();
    await page.locator('.rec-btn').click();

    // The button flips to "Stop" (recording in progress).
    await expect(page.locator('.rec-btn')).toHaveText('Stop', { timeout: 5000 });
    await assertNoBannedWords(page);
  });
});

test.describe('T7 — editable transcript + answer-your-way tabs switch modes', () => {
  test('the tabs switch modes and the transcript is editable', async ({ page }) => {
    await goToMediaQuestion(page);

    // The tab set for Q6: Type / Upload PDF / Upload text / Audio / video.
    const tabs = page.locator('.tab');
    await expect(tabs).toHaveCount(4);
    await expect(tabs.nth(0)).toHaveText('Type');
    await expect(tabs.nth(3)).toHaveText('Audio / video');

    // Switch to the media tab -> the editable transcript renders.
    await tabs.nth(3).click();
    await expect(page.locator('textarea.transcript')).toBeVisible();

    // Type into the editable transcript — it stages as a transcribed answer.
    await page.locator('textarea.transcript').fill('My words, exactly how I want them.');
    await expect(page.locator('.primary')).toHaveText(/Beautiful — next/);

    // Switch back to Type — the text field is still there, mode switched.
    await page.locator('.tab', { hasText: 'Type' }).click();
    await expect(page.locator('textarea.field-textarea').first()).toBeVisible();
    await assertNoBannedWords(page);
  });
});

test.describe('T8 — save & resume (reload -> resume at next-unanswered)', () => {
  test('answering a few questions, then reloading, resumes at the next-unanswered question', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);

    await chooseAndAdvance(page, 'book', 'Question 1 of 16');
    await chooseAndAdvance(page, 'full', 'Question 2 of 16');
    await typeAndAdvance(page, 'Anne', 'Question 3 of 16');
    await typeAndAdvance(page, 'Example', 'Question 4 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 5 of 16');

    // Reload the same link — answers persisted locally (debounced) and resume
    // lands at the next-unanswered question (email, Q5).
    await page.reload();
    await expect(page.locator('.qcount')).toHaveText('Question 5 of 16');
    await assertNoBannedWords(page);
  });

  test('the save & come back later reassurance is on every screen', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    await expect(page.locator('.savelater')).toHaveText(/Save & come back later — your answers are safe/);
  });
});

test.describe('T9 — completion screen + celebration after the last question', () => {
  test('the intake completes with the warm completion screen', async ({ page }) => {
    // Use the gate1 client (binding scoped to the 2-question GATE-1-title phase)
    // for a fast, deterministic full walk.
    await page.goto(fullUrl('gate1'));
    await expectWarmUi(page);
    await expect(page.locator('.qcount')).toHaveText('Question 1 of 2');

    await typeAndAdvance(page, 'The Calm Morning', 'Question 1 of 2');
    await expect(page.locator('.qcount')).toHaveText('Question 2 of 2');

    // Last question answered -> completion screen with celebration.
    await typeAndAdvance(page, 'A gentle guide to slower starts', 'Question 2 of 2');
    await expect(page.locator('.completion')).toBeVisible();
    // The warm close-out headline (app.js inline completion).
    await expect(page.locator('.completion h2')).toContainText('your book is taking shape');
    // The book resolves with a glow (celebration motif).
    await expect(page.locator('.book.glow')).toBeVisible();
    // Keep-link + email opt-in (skippable).
    await expect(page.locator('.keep-link')).toContainText('Keep this link');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await assertNoBannedWords(page);
  });
});
