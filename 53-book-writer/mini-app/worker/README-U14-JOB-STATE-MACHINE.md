# Book Writer Mini-App — per-run JOB STATE MACHINE + intake assembly gate (U14)

Wave C, unit U14 of the Book Writer Mini-App Gauntlet. Turns the master-plan
section 4 job model into a fail-closed state machine + assembly gate that the
box assembler consults BEFORE it ever mints an `intake.json`.

## The two invariants this unit locks

1. **NEVER assemble while queued.** If ANY required step's job is `queued` /
   `processing`, the intake assembly gate REFUSES with `AF-BW-MA-JOB-PENDING`.
   A pending job is never treated as a missing field (that would false-fail the
   skill's `AF-BK-INTAKE-MISSING` prover) and is never assembled (that would
   mint an incomplete intake).
2. **EXTRACT-NO-TEXT.** A media answer whose job reached `done` with NO extracted
   text NEVER trips `assembly-ready` — it fails closed with
   `AF-BW-MA-EXTRACT-NO-TEXT`. There is no silent blank, ever.

Every violation names an explicit AF code — never a silent pass:
`AF-BW-MA-JOB-PENDING`, `AF-BW-MA-EXTRACT-NO-TEXT`, `AF-BW-MA-CAPABILITY`,
`AF-BW-MA-REJECT-FIELD`. `AF-BW-MA-ANTHROPIC` is reserved.

## Run state machine

```
queued -> collecting -> assembly-ready -> completed / failed
```

- `queued` — run created, no required field present yet.
- `collecting` — answers arriving; the gate is closed (any required step is
  pending / no-text / failed / missing). This is the "Transcribing…" state for
  the run as a whole.
- `assembly-ready` — every required field is present; the assembler MAY run.
  Reverts to `collecting` if evidence is edited back to blank.
- `completed` — terminal. Only an `assembly-ready` run may complete
  (`markCompleted` refuses otherwise with `AF-BW-MA-JOB-PENDING` — the
  machine-level guard on "never assemble while queued").
- `failed` — terminal. Set only by an explicit assembly failure.

## Endpoint

`POST /api/job?tk=<token>`

Re-validates the token binding (KV `binding:<token>` — unknown/expired →
401, completed → 410), derives the required qids (caller-supplied, else the
phase config's `required` questions), reads authoritative evidence, and runs the
gate.

- **Authoritative evidence:**
  - typed answers → KV `answer:<client>:<run>:<phase>:<qid>` and the `save:`
    draft rows U11 writes (resume path);
  - media → the `MEDIA_JOBS` KV row for `media_answer_ids[qid]`. When
    `MEDIA_JOBS` is bound, that row WINS over any raw `media` row supplied in
    the request body — a forged body can never self-attest a `done` job.
- **Responses:** 200 `assembly-ready`, or 409 with the closed gate's AF code +
  the run parked in `collecting`. Injected `location_id` / `contact_id` /
  `client_id` are rejected at the boundary (isolation by construction).

The edge Worker stays a DUMB RELAY: this unit stages nothing and holds zero PITs.
It only reports whether the intake may assemble — the actual assembly + GHL
write stay on the box (U13/U15).

## Files

- `src/job.js` — pure state machine + gate + `/api/job` handler.
- `src/job.test.mjs` — offline unit gate, 40 tests (negatives: queued → gate
  closed, no-text → gate closed, forged-body can't self-attest, missing/failed
  fail closed, terminal states can't reopen).
- `src/index.js` — routes `/api/job` to the U14 handler.
- `package.json` — `test` script includes `src/job.test.mjs`.

## Run the self-test

```sh
cd 53-book-writer/mini-app/worker
node src/job.js --self-test
node --test src/job.test.mjs
node --test src/*.test.mjs      # full regression
```

Expected: 40/40 U14 + 90/90 prior = 130/130 pass.

## Integration

The box assembler (U13/U15 path) calls `/api/job` (or the pure
`assemblyGate`/`markCompleted` functions directly) and only runs
`book-writer-entry.sh --run-dir <RUN_DIR>` when the verdict is
`assembly-ready`; the receipt-backed `completed` transition is the box's proof
that no step was still queued at assembly time.
