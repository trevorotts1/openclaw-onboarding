# Book Writer Mini-App — Box side (U12)

The run-box scripts for the Book Writer mini-app. The box that OWNS a run
polls the Worker job registry, pulls completed media, transcribes on the box
(provider-neutral, hard non-Anthropic), and stages output for the GHL
write-back seam (U15, Skill 44 rails).

## Files

- `capability_probe.py` — per-box capability probe (preflight.sh mirror).
  Probes by CAPABILITY + NAME only; honest booleans, never fabricated;
  idempotent on re-run. Writes `capability-map.json` next to itself.
- `capability-map.json` — the probe's current output (committed so the map's
  shape is reviewable; a box re-probes at run time).
- `ingest_poller.py` — the box ingest poller. Polls `GET /api/media/<answerId>`
  (the media.js pollJob contract), pulls completed jobs, hands them to
  `bridge/media_textractor.py` (U13) for transcription, and stages the output
  for the GHL write-back seam. Mirrors preflight.sh's fail-closed discipline.

## Contract notes

- The Worker is a DUMB RELAY: it holds ZERO client PITs and never
  transcribes. The KV binding row is the SOLE destination authority.
- The poller runs on the box that OWNS the run. It talks to the Worker with
  the run token the box already holds; the Worker still validates the binding.
- Fail-closed: no media staged -> honest empty (exit 0); a done job with empty
  text is never trusted; a worker failure is surfaced (exit 2), never a
  silent skip; a capability the box needs but lacks -> AF-BW-MA-CAPABILITY
  hard-fail (exit 7).

## Run the self-tests

```sh
python3 53-book-writer/mini-app/box/capability_probe.py --self-test
python3 53-book-writer/mini-app/box/ingest_poller.py --self-test
```

The poller self-test uses a stubbed poll source (no network). The negative
case — no media, a pending job, a failed job, a done job with empty text, a
dead worker — must produce an HONEST result, never a fabricated job.

## Poll a run

```sh
python3 53-book-writer/mini-app/box/ingest_poller.py poll-spec.json
```

`poll-spec.json` carries `{client_id, run_id, answer_ids, worker_base, token}`.
The client_id/run_id come from the run ledger on the owning box — the poller
never invents a destination; the KV binding row is the authority.
