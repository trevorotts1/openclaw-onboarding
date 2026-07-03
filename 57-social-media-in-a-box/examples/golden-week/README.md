# Golden regression sample — golden-week

A fictional brand (**Northwind Bakehouse** — not a fleet client) running mode `week` on the theme
"Why your first 100 customers matter more than your next 10,000". It PASSES the full P0→P8 pipeline
end-to-end and issues a `PROCESS-CERTIFICATE` proving ZERO Anthropic; the `broken-variants/` prove
fail-closed rejection.

## Reproduce

```
bash social-media-entry.sh --run-dir examples/golden-week --mode week
```

Expected: all nine phases `[OK]`, `ALL REQUESTED PHASES PASSED`, a certificate with
`zero_anthropic: true / prompt_hashes_ok: true / all_gates_pass: true`.

## Content authenticity

`working/content/bands/fb-carousel.json` is **genuinely authored** (real caption + 10 distinct,
non-padded slide image prompts inside the 1,000–1,700-char band). It is the content-authenticity
anchor — no filler phrase repeated to hit a floor, no vocab-list dumps, no mid-phrase cutoffs — and
it clears the same bands `prove_bands.py` enforces.

## Broken variants (`broken-variants/`)

Six DISTINCT fail-closed trips, each executed for real by `../../verify.sh` step 4 (which
asserts the exact exit code + AF-SM-* code and leaves every fixture read-only). See
`broken-variants/REJECTION-RESULTS.json` for the reproducible per-variant commands.

| variant | prover / stage | exit | code |
|---|---|---|---|
| `out-of-band-caption` | prove_bands / P3 | 2 | `AF-SM-CAPTION-BAND` |
| `bad-hashtag-count` | prove_bands / P3 | 2 | `AF-SM-HASHTAG-COUNT` |
| `client-key-leak` (materialized to temp) | scrub_gate / P5 | 2 | `AF-SM-SECRET` |
| `anthropic-call` (materialized to temp) | scrub_gate / P5 | 2 | `AF-SM-NOANTHROPIC` |
| `missing-provenance` | build_manifest / P6 | 2 | `AF-SM-PROVENANCE-MISSING` |
| `unapproved-phase-skip` | build_manifest / P6 | 2 | `AF-SM-PROCESS-INTEGRITY` |
| `direct-orchestrator-no-nonce` | run_social_media front-door | 4 | nonce mismatch |

The `out-of-band-caption` / `bad-hashtag-count` fixtures reuse the AUTHENTIC golden carousel
with a single isolated defect (a truncated caption / two hashtags), so only the intended band
trips. The `client-key-leak` and `anthropic-call` negatives are never shipped as literals —
`verify.sh` materializes a fabricated (all-`a`) key / a `claude-*` id into a read-only temp file,
proves the scrub catches it, and deletes it. `missing-provenance` proves the certificate's
zero-Anthropic claim is fail-closed: a run with no `working/provenance/calls.json` cannot be
signed (you cannot certify zero-Anthropic with no per-call model record).
