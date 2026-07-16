# U76 (GK-14) audit artifacts — persisted 2026-07-16

Persisted by K6-U76-close (bookkeeping unit; the audit itself is judge-accepted, 9.0 LAND,
round-2 ticket `~/skill6-merge-queue/ONB/U76.json`, and was NOT re-run).

## Contents
- `builtin_report.md` — n8n built-in audit categories (instance-level advisories).
- `n8n-audit-instance-2026-07-16-report.md` — full custom deep-scan report.
- `parsed_workflows.json` — structured parse of the custom-scan output (244 distinct workflows).
- `u76-per-finding-ledger.csv` — one row per finding, 506 rows, 100% dispositioned
  (ACCEPTED 1 / EXCLUDED 1 / NEW-UNIT-RECOMMENDED 493 / "NEW-UNIT-RECOMMENDED (cross-ref existing
  unit)" 11). Severity split: Critical 25 / High 141 / Medium 324 / Low 16.

## Redaction note (K6-U76-close, 2026-07-16)
Before persisting to this fleet-wide repo, all four files were independently re-scanned with a
python (no grep) 16-pattern secret-shape detector plus a curated known-client/human-name scan and
a home-path scan. The secret and home-path scans were clean. The name scan found two client names
embedded in live n8n workflow titles inside three of the four files (`n8n-audit-instance-...md`,
`parsed_workflows.json`, `u76-per-finding-ledger.csv`) — e.g. workflow titles of the shape
"Chapter Rewriter for <client>" and "<client> Book Rewriter". Those two client names were replaced
with the literal token `[CLIENT]` in every occurrence before this commit; `builtin_report.md`
needed no redaction. Structural integrity was re-verified after redaction: the CSV still parses to
506 data rows / 0 blank dispositions / the same disposition and severity split as before redaction,
and `parsed_workflows.json` still parses as valid JSON. The un-redacted originals remain on local
disk only, at `~/Downloads/U76-audit-artifacts/` (not committed anywhere).

No secret values, no operator-home paths, and (after this redaction pass) no client/human names
are present in these committed copies. No live n8n or GHL calls were made to produce this commit —
this is a file-copy-and-redact pass over artifacts an earlier session already generated.
