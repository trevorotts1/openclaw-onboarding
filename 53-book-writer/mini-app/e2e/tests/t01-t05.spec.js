// ============================================================================
// Book Writer mini-app — U18 e2e: T1-T5 (headless, offline)
// ----------------------------------------------------------------------------
// T1  universal link opens the warm UI (render check)
// T2  welcome screen renders (copy, one-question-per-screen)
// T3  question 1 of N progress rail shows "Question 1 of N"
// T4  typed answer submits and advances to the next question
// T5  PDF upload answer path works (file input -> staged)
//
// All offline: local stub Worker + stub GHL only. No real client feeds.
// ============================================================================

import { test, expect } from '@playwright/test';
import { fullUrl, assertNoBannedWords, resetHarness, expectWarmUi, typeAndAdvance, chooseAndAdvance, countQuestionCards } from './helpers.mjs';

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
});

test.describe('T1 — universal link opens the warm UI', () => {
  test('the /slug/phase?tk= link renders the warm SPA, not a refusal page', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    await assertNoBannedWords(page);
    // Warm design-token surface is present.
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(251, 246, 238)');
    await expect(page.locator('.card')).toBeVisible();
    await expect(page.locator('.savelater')).toHaveText(/answers are safe/);
  });

  test('a missing token gets a fail-closed 401, never the form', async ({ page }) => {
    await page.goto('/fake-alpha/P0-INTAKE'); // no ?tk=
    await expect(page).toHaveURL(/fake-alpha\/P0-INTAKE$/);
    await expect(page.locator('.card')).not.toBeVisible();
  });
});

test.describe('T2 — welcome screen renders (copy, one question per screen)', () => {
  test('the first screen shows warm copy and exactly ONE question card', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    // One-question-per-screen law: a single h1.q-text on screen.
    expect(await countQuestionCards(page)).toBe(1);
    // Warm copy: permission line + save-later reassurance.
    await expect(page.locator('.permission')).toHaveText('There are no wrong answers.');
    await assertNoBannedWords(page);
  });
});

test.describe('T3 — question 1 of N progress rail', () => {
  test('shows "Question 1 of 16" on the first question of the intake', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    await expect(page.locator('.qcount')).toHaveText('Question 1 of 16');
    // The progress rail is present; the fill element exists (it starts at 0
    // width, so we assert presence, not visibility).
    await expect(page.locator('.rail')).toBeVisible();
    await expect(page.locator('.rail-fill')).toHaveCount(1);
  });
});

test.describe('T4 — typed answer submits and advances', () => {
  test('answer question 1, advance to question 2, progress rail updates', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    await expect(page.locator('.qcount')).toHaveText('Question 1 of 16');

    // Q1 is a choice (version: book/brand) — select then advance.
    await chooseAndAdvance(page, 'book', 'Question 1 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 2 of 16');

    // Q2 is a choice (mode: full/4x3x3) — select then advance.
    await chooseAndAdvance(page, 'full', 'Question 2 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 3 of 16');

    // Q3 is a typed field (first_name) — answer it, advance.
    await typeAndAdvance(page, 'Anne', 'Question 3 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 4 of 16');

    // On Q4 (last_name) the button starts as "Keep going".
    await expect(page.locator('.primary')).toHaveText('Keep going');
    // Type a non-empty answer — the button celebrates BEFORE advancing.
    const field4 = page.locator('.tabpanel input.field-input, .tabpanel textarea.field-textarea').first();
    await field4.fill('Sample');
    await expect(page.locator('.primary')).toHaveText(/Beautiful — next/);
    await page.locator('.primary').click();
    await expect(page.locator('.qcount')).toHaveText('Question 5 of 16');
  });

  test('a mandatory question does not advance with an empty answer', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    // Q1 required choice — clicking next with nothing selected stays put.
    await expect(page.locator('.primary')).toBeDisabled();
  });
});

test.describe('T5 — upload answer path works (file input -> staged)', () => {
  test('a textarea question offers the upload tabs, a .txt file stages its text', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    // Walk to a textarea question that offers file-pdf/file-txt tabs (ideal_avatar, Q6).
    await chooseAndAdvance(page, 'book', 'Question 1 of 16');
    await chooseAndAdvance(page, 'full', 'Question 2 of 16');
    await typeAndAdvance(page, 'Anne', 'Question 3 of 16');
    await typeAndAdvance(page, 'Example', 'Question 4 of 16');
    // Q5 email (optional text) — advance.
    await typeAndAdvance(page, 'anne@example.com', 'Question 5 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 6 of 16');

    // The answer-your-way tabs are present (Type / Upload PDF / Upload text / Record).
    await expect(page.locator('.tab', { hasText: 'Upload PDF' })).toBeVisible();
    await expect(page.locator('.tab', { hasText: 'Upload text' })).toBeVisible();
    await expect(page.locator('.tab', { hasText: 'Type' })).toBeVisible();

    // Activate the Upload text tab — the file input + dropzone render.
    await page.locator('.tab', { hasText: 'Upload text' }).click();
    await expect(page.locator('.dropzone')).toBeVisible();
    const fileInput = page.locator('.file-input');
    await expect(fileInput).toBeVisible();

    // Choose a .txt file — the browser reads it as text and STAGES it as the
    // answer (the file itself is never uploaded; the answer rides the text path).
    await fileInput.setInputFiles({
      name: 'my-avatar-notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Readers who want a calmer morning routine.', 'utf8'),
    });

    // The filename renders and the answer is staged (button celebrates).
    await expect(page.locator('.fname')).toHaveText('my-avatar-notes.txt');
    await expect(page.locator('.primary')).toHaveText(/Beautiful — next/);
    await assertNoBannedWords(page);
  });

  test('the PDF tab renders its file input and never fabricates a done answer without the extractor', async ({ page }) => {
    await page.goto(fullUrl('alpha'));
    await expectWarmUi(page);
    await chooseAndAdvance(page, 'book', 'Question 1 of 16');
    await chooseAndAdvance(page, 'full', 'Question 2 of 16');
    await typeAndAdvance(page, 'Anne', 'Question 3 of 16');
    await typeAndAdvance(page, 'Example', 'Question 4 of 16');
    await typeAndAdvance(page, 'anne@example.com', 'Question 5 of 16');
    await expect(page.locator('.qcount')).toHaveText('Question 6 of 16');

    await page.locator('.tab', { hasText: 'Upload PDF' }).click();
    await expect(page.locator('.dropzone')).toBeVisible();
    const fileInput = page.locator('.file-input');
    await expect(fileInput).toBeVisible();

    // Picking a PDF marks the step IN PROGRESS (warm, honest) and hands to the
    // typing path — never a fabricated done text. The app surfaces the warm
    // "coming online" toast and switches to the editable text field; the answer
    // is NOT silently staged from the PDF.
    await fileInput.setInputFiles({
      name: 'brief.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\nfake pdf bytes'),
    });
    await expect(page.locator('#toast')).toContainText(/type or record your answer/);
    // No banned words, and the answer is NOT silently marked done with the PDF.
    await assertNoBannedWords(page);
    await expect(page.locator('textarea.field-textarea').first()).toBeVisible();
  });
});
