# Book Writer Mini-App :: U07 — Welcome + Completion screens (Wave B)

Additive screens for the SPA, built on top of U05's config-driven renderer core.

## Files

| File | Role |
|---|---|
| `welcome.js` | The link landing. Warm promise + comfort line + gentle question count **re-grounded to the config** (never a hardcoded `'8 questions'`), "answers save as you go", "you can close this link and come back to it", a single CTA, and the always-visible "Save & come back later — your answers are safe." |
| `complete.js` | The end-of-phase landing. Warm close-out copy re-grounded to the phase: an **intake** phase ("Thank you! Your book team has everything they need."), a **gate** phase ("That's it — your choice is locked in."), the resume-link reminder with copy affordance, and the optional opt-in "Email me my draft" (always skippable — no email wall). |
| `README.md` | This wiring note. |

## Why additive files (not a rewrite of `app.js`)

U05 owns the one-question-per-screen renderer in `pages/app.js` and its shell in
`pages/index.html`. Both already landed on `feat/ma-U05` (commit `ea5f5815`).
U07 keeps that seam by adding two self-contained modules rather than editing the
already-committed renderer — zero merge collisions, each module independently
node-testable.

## Wiring seam (merge-time)

Once the renderer core is merged, three small hooks connect the seam. Each is a
one-line call and is marked in U05's `app.js` with the comment
`// U07 seam: welcome screen`.

1. **Welcome before the first question.** In `App.prototype.init`, before
   `this.render()` runs for the first time, render the welcome card:

   ```js
   // U07 seam: welcome screen
   if (BWWelcome) {
     var wRoot = document.getElementById('app');
     BWWelcome.renderWelcomeInto(wRoot, this.config, this.context, function () {
       self.render();               // begin your book
     });
     return;
   }
   ```

2. **Completion with the full close-out copy.** In `App.prototype.renderComplete`,
   replace the minimal inline completion with:

   ```js
   // U07 seam: completion screen
   if (BWComplete) {
     BWComplete.renderCompleteInto(this.appEl, this.config, this.context, function (email) {
       // U11 owns the email opt-in send (debounced/resumable); no-op here.
     });
     return;
   }
   ```

3. **Script tags.** In `pages/index.html`, after `app.js`:

   ```html
   <script src="welcome.js"></script>
   <script src="complete.js"></script>
   ```

## Copy contract (locked, Plan 2 + MASTER-PLAN section 5)

- Banned strings never render: **Submit / Required / Final / Deadline / You must / Error**.
- Every screen carries: **"Save & come back later — your answers are safe."**
- Welcome landing reassures: **"Take your time — your answers save as you go."**
  and **"You can close this link and come back to it."**
- Completion reassures: **"Thank you! Your book team has everything they need."**
- No signup wall, no email until the very end, and the email offer is opt-in +
  skippable ("Email me my draft (optional)").

## Provider-neutral

Zero provider ids, zero PITs, no Anthropic references. Both modules are dumb
renderers; they never reach outside the Worker's own routes.

## Self-test

```bash
node -c welcome.js
node welcome.js --selftest
node -c complete.js
node complete.js --selftest
```

The self-tests lint every shipped string for the banned list and for forbidden
provider/zone ids (`anthropic`, `claude`, `sk-`, `ak-`, `wrangler`, `cloudflare`),
and assert the progress indicator and copy re-ground to the config-driven schema
field count rather than a hardcoded number.
