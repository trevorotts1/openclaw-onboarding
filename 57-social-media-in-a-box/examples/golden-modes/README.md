# Golden regression sample — golden-modes (v0.2.0 new modes)

The fictional brand **Northwind Bakehouse** (not a fleet client) exercising the v0.2.0 FOLD +
publisher modes end-to-end, each through the ONE sanctioned entry, each with **genuinely authored**
content (no padding, no filler-to-hit-a-floor). `../../verify.sh` step 2b runs every one in a fresh
read-only temp copy and asserts the deterministic certificate reproduces the committed sha.

| run | mode | phases | proves | artifact |
|---|---|---|---|---|
| `newsletter/` | `newsletter` (C4) | P0 → P9 → P5 → P6 | subject ≤60 / preview ≤120 / table-based inline-CSS html | signed certificate |
| `blog/` | `blog` (C5) | P0 → P10 → P5 → P6 | title ≤80 / meta ≤160 / body ≥700 words (real 756-word essay) | signed certificate |
| `podcast/` | `podcast` (C3) | P0 → P11 → P5 → P6 | 1,543-word `[emotion]`-tagged script / 617 s / 192 kbps / 1400×1400 JPEG cover (audio+cover, NOT deferred) | signed certificate |
| `twitter-thread/` | `day` (C1 `twitter` sub-mode) | P0 → P2 → P3 → P4 → P5 → P6 → P7 | a real 7-tweet thread posts GHL-direct via the client PIT; `publish_result.platform == twitter` | signed certificate |
| `engage/` | `engage` (C6) | P0 → P12 | a read-only 7-day anomaly report; **mints NO certificate and blocks no publish** (by design) | `working/qc/engage_report.json` |

## Reproduce

```
bash social-media-entry.sh --run-dir examples/golden-modes/newsletter     --mode newsletter
bash social-media-entry.sh --run-dir examples/golden-modes/blog           --mode blog
bash social-media-entry.sh --run-dir examples/golden-modes/podcast        --mode podcast
bash social-media-entry.sh --run-dir examples/golden-modes/twitter-thread --mode day
bash social-media-entry.sh --run-dir examples/golden-modes/engage         --mode engage
```

Each of the first four ends with `ALL REQUESTED PHASES PASSED` and a `PROCESS-CERTIFICATE` carrying
`zero_anthropic: true / prompt_hashes_ok: true / all_gates_pass: true`. `engage` ends read-only with
the anomaly report and no certificate.

## Content authenticity (NO padding)

Every content file is real, distinct prose written for this fictional brand and this theme ("your
first 100 customers matter more than your next 10,000"):

- **newsletter** — a table-based inline-CSS digest of the week with real links, subject 45 chars,
  preview 100 chars, plain hyphens only (the em-dash content ban holds by default).
- **blog** — a genuine 756-word essay (measured), no repeated filler, no vocab dumps, clears
  `blog_body_words` ≥700 honestly.
- **podcast** — a genuine 1,543-word spoken script (measured with `[emotion]` tags stripped), one
  `[emotion]` tag per paragraph minimum, 617 s at 150 wpm inside the 600-900 s band. `scriptWords`
  and `durationSeconds` are the true measured values, never fabricated to satisfy a band.
- **twitter-thread** — a real 7-tweet thread, every tweet inside the 280-char platform limit,
  authored to stand alone as a thread.
- **engage** — a real read-only report with per-platform metrics, week-over-week deltas, and two
  labeled anomalies (one strong-positive, one watch), plus concrete action suggestions.

Client runtime uses the client's OWN provider chain (OpenRouter model + fallbacks, Google Gemini
vision QC, Kie.ai / Fish-Audio media) — the `provenance/calls.json` in each run records ZERO
Anthropic, and `build_manifest.py` refuses to sign a certificate without that proof.
