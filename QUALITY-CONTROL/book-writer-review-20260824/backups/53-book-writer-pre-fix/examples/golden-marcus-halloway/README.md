# Golden Marcus Halloway — Book Writer regression sample

A reusable **golden regression sample** for the Skill 53 Book Writer engine: a complete, method-faithful
**12-chapter nonfiction book** that PASSES every fail-closed prover and drives `book-writer-entry.sh` →
`run_book_writer.py` to a signed process certificate.

- **Fictional subject:** *The Quiet Authority — How the Best New Leaders Trade Control for Trust*, a
  leadership book by the invented author **Marcus Halloway** for newly-promoted first-time engineering
  managers. **No real client names, brands, URLs, or private details ship** (`marcus@example.com` is
  invented). Public figures named as tone influences (e.g. Simon Sinek) are style references, not clients.
- **The SACRED contract** is pinned in `../../GOLDEN-BOOK-BIBLE.md` (author, intake, locked title +
  subtitle, blended-tone voice + rules, 12 chapter titles, per-chapter outline, two verbatim stories +
  their chapters, the 30-day structure, the 4x3x3 numbers, and the exact golden file layout).

## Zones

| Zone | Path | Who authors |
|---|---|---|
| **Authored — DATA anchors (shipped by Agent A)** | `run/intake.json`, `run/stories.json`, `run/artifacts/APPROVED-TITLE.txt`, `run/433/433_Deck_Data.json` | Agent A |
| **Authored — PROSE (Wave-2)** | `run/artifacts/{01-avatar,08-blended-tone,10-suggested-titles,11-blurb,12-chapter-titles,13-outline,21-30day-challenge,22-cover-prompt}.md`, `run/chapters/ch01..ch12.md`, `run/receipts/*`, `run/RUN-LEDGER.json`, `run/433/*` | Wave-2 authors |
| **Assembled (Agent D)** | `delivery/Marcus_Halloway-Book/` (manuscript, named deliverables, `00-INDEX.md`, `MANIFEST.json`, `PROCESS-CERTIFICATE.{json,md}`) | `run_book_writer.py`, run by Agent D |
| **Fail-closed proof** | `broken-variants/make_broken.py` + `REJECTION-RESULTS.json` | authored by Agent A; run by Agent D once prose exists |

## Status

- ✅ DATA anchors shipped and validated (`prove_bw_intake.py` PASSES `run/intake.json`; deck-data
  schema-valid).
- ✅ `make_broken.py` proves the 10 DATA-anchor / process AF-BK codes fail-closed NOW; the 8
  prose-dependent codes are marked `blocked_on_prose` until Wave-2 authors the prose.
- ⏳ **TODO (Wave-2 + Agent D):** author the golden prose to the pinned floors, run
  `bash ../../book-writer-entry.sh --run-dir <this dir>` to assemble `delivery/` + mint the
  certificate, then re-run `make_broken.py` to light all 18 variants. `../../verify.sh` sections 2 + 4
  (golden-bundle PASS + certificate_sha idempotency) light up automatically once the certificate exists.
