# WER-013 / Oprah Winfrey - original 2013 Harvard address research candidate

**Scope:** Required anchor `verified-first-person` ("Verified first-person interviews and reflections"). NOT the required book `The Path Made Clear` and NOT a substitution for it.

**Source:** "Winfrey's Commencement address", Harvard Gazette, May 31, 2013, transcript described as Oprah Winfrey's May 30, 2013 address *as delivered*.

- Primary URL: https://news.harvard.edu/gazette/story/2013/05/winfreys-commencement-address/
- University context/report: https://news.harvard.edu/gazette/story/2013/05/winfrey-failure-is-just-movement/
- First-person speaker: Oprah Winfrey
- Authorship/host provenance: a transcript of the speaker's actual address published on the event host's official Harvard site; the companion article is a journalist summary and **not** the first-person primary source
- Retrieval method: externally retrieved rendered official transcript text on 2026-10-17, not a locally retained lawfully acquired full work
- Source-byte SHA-256: **NOT CAPTURED**. Outbound retrieval from the isolated code/build environment failed DNS resolution. Never replace this with a hash of a URL, rewritten paraphrase, publisher description, or derived persona note.
- Rights mode: reference-only, paraphrases; no extended verbatim passages, no distribution of the underlying speech transcript
- Research state: **candidate with manually identified original passages**, not yet verified and ingested as a Section 8.3 `primary_substantive` source record. This file must NOT be counted by the release gate as verified teaching.

## Distinct candidate author-teaching locations

1. **Learning from a professional setback.** Passage following her first-person recollection of OWN's difficult launch and its coverage. She teaches that a setback should be processed and learned from, then followed by the next appropriate choice. Specific locator to confirm on retained source: address segment after her description of the network turnaround and before discussion of the moral/emotional compass. Candidate kind `concept`, mark `paraphrase`.
2. **Purpose distinguishes achievement from identity.** Passage addressing how a resume should describe the kind of person someone intends to be and why, not only accumulated titles. The concept connects enduring direction with resilience under stress. Locator: segment following discussion of the internal moral/emotional compass and before the Angel Network story. Candidate kind `concept`, mark `paraphrase`.
3. **People seek to be seen and understood.** Passage about her long interview career and the human need for validation, including firsthand observations of interview participants. Locator: late speech segment about experience across tens of thousands of interviews, preceding an appeal for face-to-face conversation. Candidate kind `concept`, mark `paraphrase`.
4. **Professional application case: Angel Network.** The address describes how a nine-year-old's small-change collection prompted Oprah to ask her audience for contributions; it grew into a wide philanthropic mobilization and clarified how she intended to use her media platform. Locator: first-person Angel Network recollection in the purpose portion of the speech. Candidate kind `application_case`, mark `reported_example`.

The four locations are different teaching/case passages. They do NOT become four accepted `EvidenceUnit` rows until a verifier obtains the authenticated source version, confirms precise non-duplicated locators and rendition fidelity, records a byte/content digest with its exact normalization basis, assigns traceable evidence IDs and checks adaptation-versus-author distinctions.

## Stage-2 ingestion task for independent source researcher

1. Capture the official HTML/text under lawful source access; record the exact extraction normalization, UTC retrieval time and sha256 of retained **source text**, not book-blurb, URL or a derivative markdown note.
2. Validate the transcript/speaker/host context and accurately identify the four above passages in the retained source with paragraph/section locators.
3. Create a `SourceRecord` for this **talk**, with `credited_authors=['Oprah Winfrey']`, `original_speaker='Oprah Winfrey'`, `source_type='talk'`, `quality='primary_substantive'` **only after that primary-material check passes**, and four candidate `EvidenceUnit` records carrying the identical source version and their own locators.
4. Avoid all quotations unless tuple-verified against the retained text and permitted under rights constraints. Keep publicly distributed pack paraphrase-only.
5. Run `node --import tsx scripts/audit-advisor-sources.ts` and per-seat checks; ensure this first-person anchor can advance while the required *The Path Made Clear* book still correctly remains unqualified.
6. Obtain independent manual fidelity review and a scenario test proving this seat gives empathy, personal mission and human impact guidance, **not** an invented quote, simulated endorsement or a generic business coach.
