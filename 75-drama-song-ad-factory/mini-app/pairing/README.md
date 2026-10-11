# Pairing and admin surface (U12)

The operator's half of the drama studio: mint a pairing code for a client and
show it as a QR, check a key, set the option behind the Option 3 approval gate,
and see the cutoff. Joint plan section 5 table row U12 — *"Pairing/admin/key/
cutoff/options behind approval/QR"* — at the service home fixed by section 5.4,
`75-drama-song-ad-factory/mini-app/`.

It is a page and its library, not a product: no framework, no bundler, no
scheduler, no dashboard, no fourth repository. The page is one self-contained
shell with inline CSS, exactly the shape `53-book-writer/mini-app/pages/` uses.

## Ownership — disjoint paths (section 5.1, one writer per file)

| Unit | Owns |
| --- | --- |
| U2 | `75-drama-song-ad-factory/mini-app/service/**` — **never edited here** |
| U3 | `75-drama-song-ad-factory/mini-app/ui/**` — the client pages |
| U4 | `75-drama-song-ad-factory/mini-app/deploy/**` |
| **U12 (this unit)** | `75-drama-song-ad-factory/mini-app/pairing/**` — nothing else |

Every file this unit created is listed under **Files** below, so a batch writer
can isolate a conflict by exact file name rather than guessing. Nothing in U2's
service, U3's ui or U4's deploy directory is written.

## What it talks to — U2's measured contract

Read from `service/README.md` and verified against the live code at base
`8f344a1dfa192115afbf9cab59ea706c86977ca6`. The verbatim shapes this surface
sends and reads:

| Route | Caller here | Request | Response it reads |
| --- | --- | --- | --- |
| `POST /api/studio/admin/pairing-code` | "Mint pairing code" | `{ admin_key, client_id }` | `201 { ok, code: "ABCD-2345", expires_in: 900 }` |
| `GET /api/studio/options` | "Check this key" | header `x-ds-key` | `200 { ok, option, line }` |
| `POST /api/studio/options` | "Set option" | `{ admin_key, target_client_id, option, approval? }` | `200 { ok, option, line }` |

`POST /api/studio/pair` is **U13's `studio.py pair`** — the client's computer
calls it. This surface prints the code and its QR and stops there; it never
pairs on the client's behalf.

Refusals are read, never invented: every failure is `{ ok: false, code, message }`
and the page shows the service's own `code`. Two codes this surface owns are
new and use the same `AF-DS-` prefix, declared in `lib/admin_client.js`:
`AF-DS-PAIR-SHAPE` (a code that is not `ABCD-2345`-shaped) and
`AF-DS-CUTOFF-NO-ROUTE` (below).

### Option 3

Setting Option 3 needs `approval: { option3: true, client_name: <non-empty> }`.
This surface refuses a missing or malformed approval **locally**, and rebuilds
the approval object before sending it, so a caller cannot smuggle extra fields
past the gate. The service's own gate is the authority, and the prover proves
that by sending raw requests that skip this surface entirely.

### The cutoff, and what is deliberately not persisted

U2's service ships **no** cutoff route and **no** cutoff field on the client
record (`schema.sql`: `client_id, created_at, option, option_set_at,
option_approval, timezone`). So the cutoff control:

- **computes and shows** the cutoff in the client's own timezone, and says
  whether now is before or after it (`cutoffVerdict`), and
- **refuses by name** — `AF-DS-CUTOFF-NO-ROUTE` — to claim it was saved.

The same is true of "cut this key off": `AF-DS-CUTOFF-NO-ROUTE`, naming the
route that does not exist. A control that printed "Saved" here would be exactly
the silent lie the plan forbids. Upgrade paths, named in the refusals and here:
`POST /api/studio/admin/cutoff { admin_key, client_id, cutoff_minutes, timezone }`
and `POST /api/studio/admin/revoke { admin_key, fingerprint }`. When those land,
the local gates lose their branch and the round trip is added; nothing else in
this unit changes.

## Files

```
pairing/README.md                        this file
pairing/admin.html                       the page (inline CSS, no dependencies)
pairing/lib/qr.js                        the QR encoder (ISO/IEC 18004, byte mode)
pairing/lib/admin_client.js              request builders + the local gates
pairing/test/pairing.test.mjs            18 tests
pairing/prove/prove_pairing_guardrails.mjs   the security prover
pairing/prove/prove_qr_against_apple.mjs     the QR cross-check
```

## Security: what is enforced, and how it is proven

1. **A key never reaches a URL.** The presented key travels in the `x-ds-key`
   header; the admin key travels in a POST body. No builder emits a query
   string, and `keyLabel` is the only way the page may mention a key — as a
   character count. Nothing is written to `localStorage`, `sessionStorage` or a
   cookie.
2. **Option 3 is refused without a well-formed approval.**
3. **A pairing code is single use.** U2 burns the record on use; the second use
   is refused with the service's own `AF-DS-PAIR-UNKNOWN`.
4. **A wrong or absent admin key is refused** with `AF-DS-ADMIN-REFUSED` on
   both admin routes, and writes nothing.

### Runnable checks (real commands, real exit codes)

```bash
# Behaviour + accessibility floor — 18 tests
node --test 75-drama-song-ad-factory/mini-app/pairing/test/pairing.test.mjs
#   exit 0 = all pass

# Security prover: the three gates above, each with a positive control on the
# same instrument AND a planted-defect run that must go red
node 75-drama-song-ad-factory/mini-app/pairing/prove/prove_pairing_guardrails.mjs
#   exit 0 = 16 checks pass, 2 = a named check failed, 3 = the prover could not run

# The QR encoder against Apple's own CIQRCodeGenerator
node 75-drama-song-ad-factory/mini-app/pairing/prove/prove_qr_against_apple.mjs
#   exit 0 = every case identical, 2 = a case differed, 3 = no Swift toolchain
```

**Why the prover is not vacuous.** Each of the three gates is checked three
ways: the refusal itself, a positive control proving a 200 is reachable on the
same route with the same store, and a run against a copy of the service with
that specific gate neutered — if the check stays green with the gate removed,
the prover reports the check as vacuous and exits 2. The three planted defects
are the approval branch in `options.js`, the pair-record delete in `index.js`,
and `isAdmin` in `index.js`. Planted copies are made under
`/tmp/trevor-macmini-U12-U1-planted-*` and removed on every exit path.

**Why the QR is not self-certified.** `test/pairing.test.mjs` decodes the
encoder's own output back to the pairing code (format info, mask, zigzag,
de-interleave, Reed-Solomon syndromes), which can only prove the encoder agrees
with itself. `prove/prove_qr_against_apple.mjs` is the real check: it compiles a
small Swift program that asks **Apple's `CIQRCodeGenerator`** for the same
payload and compares every module. Its payload set is byte-mode-only by
construction, because a conformant encoder may split a message into segments —
Apple encodes `ABCD-2345` in *alphanumeric* mode, a different but equally valid
QR of the same text. Both facts are stated in the prover's own output rather
than smoothed over.

## Accessibility

Every control has a `<label>`; the option choice is a native radio group in a
`fieldset`, so arrow keys work with no script; each section carries a
`role="status"` line for results and a `role="alert"` line for refusals; focus
is visible on every control and the tab order is the reading order. The QR is
`role="img"` with an `aria-label`, and the code is printed as text beside it —
the square is the convenience, the text is the accessible content.
`test/pairing.test.mjs` checks the static floor (unique ids, every `<label for>`
resolving, every id the wiring reaches for existing, one live region pair per
section), so it cannot rot silently.

## Deliberate limits

- No revoke route, no cutoff route and no key-listing route exist in version 0;
  the surfaces are present and refuse by name. See above.
- `lib/qr.js` is byte mode, versions 1–6, EC levels L/M/Q/H — everything this
  surface shows. A longer payload is refused with `AF-DS-QR-TOO-LONG`, never
  truncated. Larger versions (7–40, which add a version-info block) are the
  upgrade path if a long studio link ever needs encoding.
- The page takes its studio origin from `<meta name="studio-origin">`, which
  U4's deploy files own; it is same-origin until they set it.
- No service worker, no offline cache, no client-side storage of anything.
