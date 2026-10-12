# Shared studio bridge (U5)

The box-side half of the drama studio, one implementation for OpenClaw boxes and
Claude Code computers. Joint plan section 5, row U5:

> Shared bridge/key/atomic claim/replay/photos/Windows-safe lease/quiet
> board/status/delivery; one approval nudge plus reminder then silence;
> owned-run cleanup receipt

It reuses the mint/renew/sync shape of
`23-ai-workforce-blueprint/.../intake-miniapp/bridge/intake_bridge.py`, the
durable-outbox shape of `scripts/core/cc_sync.py`, and the atomic-claim /
time-limited-lease shape of the skill-23 `launch_ledger.py` pattern. It is not a
new framework, scheduler, dashboard or management app.

## Files

| File | Owns |
| --- | --- |
| `studio_claim.py` | the ledger: atomic single-winner order claim, replay guard, Windows-safe lease, notice gate, receipts |
| `studio_bridge.py` | the bridge: key handshake, status, delivery, photo handling, quiet board, owned-run cleanup receipt, CLI |
| `checks/run_checks.py` | the six runnable checks (A–F), each with a true exit code and a control |

This unit owns `75-drama-song-ad-factory/shared-bridge/**` only. U1/U11 own the
`choice_card/intake_card` area, U2 owns `mini-app/service/**`, U3 the mini-app
UI, U4 `mini-app/deploy/**`, U12 the pairing/admin surface. No file here edits
another unit's path.

## Service contract it speaks (U2, branch `unit/U2`, head `8f344a1d`)

```
POST /api/studio/checkin              header x-ds-key   -> { ok, checked_in_at, line }
POST /api/studio/orders/<id>/state    header x-ds-key   -> { ok, order }   { event }
POST /api/studio/uploads              header x-ds-key   -> { ok, upload_id, upload: { method, url, ... } }
```

`event` is one of `claim | needs_you | answer | ready | deliver | done`. The
presented key lives **only** in the `x-ds-key` header, never a query string.
Photos go phone → storage DIRECT through the presigned PUT the worker returns;
the bytes never pass through the bridge.

## The three guarantees

- **Atomic claim.** `INSERT OR IGNORE` against a `UNIQUE` order id is the whole
  arbitration — the database decides, so two runs racing one order cannot both
  win. The loser exits `2`. Proven under a 10-way concurrent race.
- **Replay.** Every emitted message carries a message id; `UNIQUE(run_id,
  message_id)` makes a second delivery a refusal, never a duplicate.
- **Windows-safe lease.** The lease is a single `UPSERT ... WHERE` in SQLite, so
  no lock file is ever named from a key like `order:<client>:<order>`. A live
  holder refuses the next owner with exit `2`. The liveness probe never calls
  `os.kill` on Windows, where `os.kill(pid, 0)` **terminates** the process — the
  exact fault the plan names ("fixed in U5 before any Windows use"). On Windows
  it uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and fails closed.

## Notice discipline (trevor-approved decision, plan row 6)

Exactly **one** approval nudge, then at most **one** reminder (default 24 hours
later), then **silence** — after the reminder the studio page's own chip is the
only signal. `ClaimLedger.notice_gate()` returns `"nudge"`, `"reminder"`, or
`None`; `None` means stay silent, never re-word it.

## Secrets

The presented key is read from env `DS_KEY` only — never argv, never a file named
on the command line, never a log line. Nothing here prints, echoes or receipts a
key value; check E proves it with a positive control on the same detector.

## The one explicit User-Agent (CHECKIN-UA)

Cloudflare in front of the studio refuses Python's default User-Agent
(`Python-urllib/3.x`) with HTTP 403 and the body `error code: 1010`; any
explicit User-Agent gets 200. Every request `studio_bridge._http` sends
therefore carries exactly
`drama-studio-client/2.7.48 (+https://studio.zerohumanworkforce.com)`.
Check F drives the real `_http` at a fake studio on `127.0.0.1` and requires
both the 200 and that exact string on the wire, with two controls on the same
server: bare urllib is refused 403/1010, and a planted-bad bridge copy with
the header line removed is refused too.

## Run the checks

```bash
python3 75-drama-song-ad-factory/shared-bridge/checks/run_checks.py
# exit 0 = all six pass; 1 = a check failed (the failing check is named)
```

## Deliberate limits

- No deploy files, no pages, no admin surface — those are U3/U4/U12 paths.
- `Board` takes an injected sender; it does not hard-bind `cc_sync`'s tenant
  binding, so a caller that already owns an `Outbox` supplies it.
- `cleanup-receipt` writes the receipt and plans the removal; it removes only
  the disposable entries, only inside the run dir, and only with `--apply`.
  Final media and the small receipts a completed run keeps are never touched.
