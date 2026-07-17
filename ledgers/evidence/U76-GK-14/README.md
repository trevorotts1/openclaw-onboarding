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

## Redaction note (K6-U76-close, 2026-07-16, PASS 1)
Before persisting to this fleet-wide repo, all four files were independently re-scanned with a
python (no grep) 16-pattern secret-shape detector plus a curated known-client/human-name scan and
a home-path scan. The secret and home-path scans were clean. The name scan found two client names
embedded in live n8n workflow titles inside three of the four files (`n8n-audit-instance-...md`,
`parsed_workflows.json`, `u76-per-finding-ledger.csv`) — e.g. workflow titles of the shape
"Chapter Rewriter for <client>" and "<client> Book Rewriter". Those two client names were replaced
with the literal token `[CLIENT]` in every occurrence before this commit; `builtin_report.md`
needed no redaction. Structural integrity was re-verified after redaction: the CSV still parses to
506 data rows / 0 blank dispositions / the same disposition and severity split as before redaction,
and `parsed_workflows.json` still parses as valid JSON.

**PASS 1's claim of completeness was FALSE and was caught by round-3 QC** (`~/skill6-merge-queue/ONB/U76.json`,
`closeOutRound3`): pass 1 redacted only the two names it had already observed, not the full set. It
did not constitute a general-purpose name scan.

## Redaction note (K6-U76-close, 2026-07-16, PASS 2 — QC send-back fix)
Independently re-derived from scratch, NOT by searching for previously-known names: (a) a curated
roster cross-reference built structurally from `~/clawd/accounts/accounts.md` (name-bearing section
headers only, never printed), filtered against a system dictionary to separate proper-noun-shaped
tokens from common English words; (b) a general capitalized-name-pair / solo-token heuristic applied
to every n8n workflow title, JSON string value, and CSV cell across all three non-`builtin_report.md`
files, reviewing pipe-delimited (`... | Name`) and `for`-suffixed title shapes specifically. This
found **6 additional distinct identity tokens (first names, one full first+last name, and one
business name) spanning 16 workflow_ids**, all un-redacted by pass 1, with zero overlap with pass 1's
2 names. All were replaced with the literal token `[CLIENT]`, matching pass 1's style. Exact
locations (file/line, JSON path, CSV row + workflow_id) are recorded in the round-3 QC ticket and in
this unit's close-out report, never as printed name text per the standing never-print-a-name rule.
`builtin_report.md` remains genuinely clean (0 hits in either pass). Structural integrity re-verified
after pass 2: CSV still 506 data rows / 0 blank dispositions / disposition split ACCEPTED 1 / EXCLUDED
1 / NEW-UNIT-RECOMMENDED 493 / "NEW-UNIT-RECOMMENDED (cross-ref existing unit)" 11 / severity split
Critical 25 / High 141 / Medium 324 / Low 16 — byte-identical to pre-redaction; `parsed_workflows.json`
still valid JSON, 244 entries; secret battery and operator-home-path scans re-run post-redaction, both
clean. The un-redacted originals remain on local disk only, at `~/Downloads/U76-audit-artifacts/` (not
committed anywhere, not modified by this pass).

**No claim of exhaustiveness is made here.** Two independent redaction passes have now each found
names the previous pass missed. Absent a roster-backed, CI-enforced check (see the round-3 ticket's
`systemicFinding_OUTRANKS_THIS_UNITS_SCORE`), a future reader should treat "no names found by this
scan" as "no names found by *this* scan," not as a guarantee. No secret values and no operator-home
paths were found in either pass. No live n8n or GHL calls were made to produce either pass — both are
file-copy-and-redact passes over artifacts an earlier session already generated.
