# Book Writer Mini-App — Save & Resume (U11)

Wave B, unit U11 of the Book Writer Mini-App Gauntlet. Turns the promise behind
"Save & come back later — your answers are safe." into a real, worker-backed
mechanism (MASTER-PLAN section 5):

1. **Debounced persist** — every answer the reader types is written to the
   Worker ~800ms after they pause, so a closed tab or a locked phone never
   loses a word.
2. **Resume at the next unanswered question** — reopening the same link loads
   the staged answers and jumps straight to the first question with no
   non-empty answer.
3. **Email opt-in for a resume reminder** — only at completion, optional and
   skippable. The default is always "Keep this link — it's your way back" with
   a copy affordance. No signup wall, no email until the end.

## Worker endpoints (edge = dumb relay, zero client PITs)

All routes re-validate the token binding; the KV binding row is the SOLE
authority for the destination. Request bodies never carry `location_id` /
`contact_id` / `client_id` — injected fields are rejected at the boundary.

| Endpoint | Purpose |
|---|---|
| `POST /api/save?tk=<token>` | Persist one draft answer idempotently. Uses the SAME per-step consumed counter as U03 (`/api/answers`) — a replayed save can never duplicate a staged answer; a legit resume edit overwrites in place. Body: `{question_id, answer, source?}` |
| `GET /api/save/resume?tk=<token>` | Fetch staged answers for the run+phase plus a `{total, answered, next_index}` hint. |
| `POST /api/save/reminder?tk=<token>` | Record an OPTIONAL resume-reminder email. Body: `{email}`. Skippable. |

### KV keys (`BW_BINDINGS` namespace)

```
save:<client>:<run>:<phase>:<qid>   -> { qid, answer, source, saved_at, edited_at? }
consumed:<run>:<phase>:<qid>        -> { ts, qid, status:"consumed" }   (shared with U03)
reminder:<run>:<email>              -> { email, run_id, phase_id, created_at }
```

A question counts as **answered** only when its staged answer has non-empty
text. A cleared draft (`""`) is NOT answered — resume goes back to it.

## Files

- `worker/src/save.js` — Worker module: pure decision core (`decideSave`,
  `resumeHint`, `validateSavePayload`, `isValidEmail`) + route handlers
  (`handleSavePost`, `handleResumeGet`, `handleReminderPost`). Runs
  `node src/save.js --selftest`.
- `worker/src/save.test.mjs` — offline unit gate (`node --test`): fresh save,
  idempotent replay (no duplicate), resume edit in place, expired/completed
  rejected, injected-destination rejected, resume hint, email opt-in.
- `pages/save-resume.js` — SPA-side logic layer (no DOM): `Persister`
  (debounced ~800ms coalesced flush with network requeue), `fetchResume`,
  `mergeAnswers`, `firstUnansweredIndex`, `answeredCount`, email validation
  and opt-in, warm copy. Runs `node save-resume.js --selftest`.

## Run the self-tests

```sh
cd 53-book-writer/mini-app/worker
node --test src/save.test.mjs        # worker gate
node src/save.js --selftest          # worker pure core

cd 53-book-writer/mini-app/pages
node save-resume.js --selftest       # SPA logic layer
```

## Integration notes

- The renderer (U05 `pages/app.js`) already resumes locally via `localStorage`
  and shows the "Save & come back later" whisper. This unit adds the worker
  side of that promise: call `BWSaveResume.Persister` on each answer entry and
  `BWSaveResume.fetchResume` on boot to merge worker-staged answers. The route
  wiring into the Worker's `index.js` dispatcher lands in the integration unit
  (U20) alongside the other `/api` routes.
- Isolation (master plan section 3) is unchanged: the binding row is the sole
  authority, the edge holds no PITs, and the GHL write happens on the run box
  (U12 poller / U15 write-back), never here.
- No Anthropic ids anywhere. No real zone/account ids anywhere — all ids in
  `wrangler.toml` are `<PLACEHOLDER>`.
