# SOP-PODCAST-05: EPISODE QC (THE EPISODE GATE, GATE B)

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Skill:** 58-podcast-production-engine (the Podcast Production Engine)
**Owning role:** qc-specialist-podcast (the verifier, who is NEVER the persona that drafted the episode)
**Stage:** Pipeline Step 9 (quality control), before cover art, audio, and publishing
**Produces:** the Tier 1 verdict, the ten-dimension rubric scores, the attempt ledger, an ACCEPT / RETRY / STOP decision
**Enforcement pointer:** `58-podcast-production-engine/scripts/qc-tier1-mechanical.py` (the deterministic Tier 1 subset at zero model cost) AND `58-podcast-production-engine/scripts/qc-attempt-gate.py` (the three-strike cap, targeted retries, and frozen research).

---

## 0. WHY THIS SOP EXISTS, AND WHICH GATE THIS IS

The finished episode goes directly from text to speech to a listening audience with no human editing between the AI and the listener, so a precision failure is a business failure. Quality is not negotiable, and the writer never grades its own work as the deciding vote. This SOP is the independent EPISODE gate.

THE CARDINAL RULE: this project has TWO quality control gates and they are never conflated, never substituted, and never averaged into each other.

- GATE A, the BUILD or MERGE gate, is the fleet ten-category rubric at the 8.5 threshold. It decides whether BUILD WORK merges into the onboarding repo. A build unit scoring 9.0 says nothing about an episode.
- GATE B, the EPISODE gate and the subject of THIS SOP, is the sixteen Tier 1 hard-fail checks plus the ten-dimension rubric at eight or higher per dimension plus the three-strike cap. It decides whether an EPISODE ships to a listener. A perfect episode says nothing about merge readiness.

The 8.5 number belongs to Gate A only. The per-dimension eight belongs to Gate B only. Never move a number from one gate to the other. The two enforcement scripts named above both carry this warning in their own headers and refuse to be read as the other gate.

## 1. THE THREE-PASS READING PROTOCOL

QC is a deterministic measurer plus a disciplined reading, not an agent self-score. The verifier reads the deliverable three times, each pass with a different job, and no pass is skipped because the episode feels done:

- PASS A, mechanics and forbidden content: em dash, code fences, markdown, labels, title placement, speakable characters, tag syntax, tag-excluded word count, word-count honesty, forbidden names and works, forbidden word by style, pure deliverable, and intake contamination.
- PASS B, structure and fidelity: arc execution, thesis traceability, mode perspective, pronoun correctness, transparency-beat presence, research integration, and no fabrication.
- PASS C, full read-aloud at speaking pace: anything a mouth would stumble on, the opening and closing power, captivation throughout, and audio direction quality.

The deterministic half of Pass A is executed by `qc-tier1-mechanical.py` at zero dollars before any model judging begins, so a mechanically broken draft fails cheap and never spends a judge call.

## 2. TIER 1: THE SIXTEEN HARD FAILS (ANY ONE FAILURE MEANS NOT DELIVERABLE)

All sixteen are binary. Checks 1 to 11, 15, and 16 are deterministic string and count work owned by `qc-tier1-mechanical.py` at zero model cost; it emits an autofail code (an AF-EP prefix) and exit code 2 for any breach:

1. EM DASH: zero em dash class characters anywhere in the deliverable.
2. NO CODE FENCES: no triple backtick or triple tilde markers of any kind.
3. NO MARKDOWN: no asterisks, underscores, headers, bullets, ordered lists, blockquotes, or link syntax in the script.
4. NO LABELS: no all-caps speaker prefix, no Intro or Host or Guest or Narrator label, no Music or SFX production cue.
5. TITLE PLACEMENT: the word Title never precedes the title; a spoken title is woven into natural speech.
6. SPEAKABLE CHARACTERS ONLY: no raw digits and no unspoken symbols in the spoken text; numbers, symbols, units, and abbreviations are written as spoken.
7. TAG SYNTAX INTEGRITY: balanced, non-nested, non-empty delivery tags in the target model's delimiter, and no tag wearing the other model's delimiter.
8. TAG-EXCLUDED WORD COUNT: the spoken word count with tags stripped falls inside the target band (roughly 980 to 2100 words for a seven to fifteen minute episode at 140 words per minute).
9. WORD-COUNT HONESTY: the reported spoken count equals the true stripped count exactly; misreporting is an absolute failure.
10. FORBIDDEN NAMES: none of the four reference speakers, their books, or their talks appear anywhere.
11. FORBIDDEN WORD BY STYLE: the word paradox never appears in a Counter Intuitive episode.
15. PURE DELIVERABLE: no delivery-report or checklist or rubric metadata bleeds into the script.
16. NO INTAKE CONTAMINATION: no contact email or phone, no consent or SMIQ language, and no visual-brief text in the script.

Checks 12 (no fabrication), 13 (mode perspective), and 14 (pronoun correctness) are SEMANTIC. They are never deterministic and are run on the CHEAP judge tier (Gemini 3.1 Flash Lite or GLM 5.2 on Ollama Cloud), never on the writer model and never on a build-time reasoning model. `qc-tier1-mechanical.py` reports checks 12 to 14 as DEFERRED so no caller ever mistakes a green mechanical result for a fully cleared Tier 1. A green mechanical result means the deterministic subset is clean; the three semantic checks and the ten-dimension rubric still gate deliverability.

## 3. TIER 2: THE TEN-DIMENSION RUBRIC (EIGHT OR HIGHER, NO AVERAGING)

Only after Tier 1 fully passes, the verifier scores all ten dimensions, and EVERY dimension must score eight or higher with no averaging: 1 Authorial Voice Fidelity, 2 Arc Execution, 3 Persuasion Mechanics, 4 Opening Power, 5 Closing Power, 6 Captivation Throughout, 7 Fidelity to the Respondent, 8 Research Integration Quality, 9 Delivery Craft, 10 Audio Direction Quality. A single dimension at seven is a failure of the whole gate, exactly as a single Tier 1 breach is. Rubric scoring runs on the mid or judge tier, never on the primary creative model with high thinking.

## 4. INDEPENDENCE (THE NON-NEGOTIABLE)

The qc-specialist-podcast persona that stamps QC MUST NOT be the persona that drafted the episode, and the judge model tier MUST be distinct from the writer tier. This is a hard wiring rule, not a preference: the writer never grades its own work as the deciding vote. Persona binding for this independence is wired at the department level; this SOP is the standing statement of why the verifier and the author are always two.

## 5. THE FAILURE LOOP: TARGETED RETRIES, FROZEN RESEARCH, THREE-STRIKE CAP

`qc-attempt-gate.py` owns the persisted attempt counter for one episode and enforces four bounds. It is the sole writer of its own per-episode attempt ledger; it never writes the episode record or the dashboard database (that remains `podcast_state.py`), and it emits a state patch for the sole writer to mirror. It never sends a Telegram message; the founder notification it decides on is routed by the caller through `alert-dedup.py`.

1. THREE-STRIKE CAP. Hard stop at `qc_max_attempts` (default 3) failed attempts: stop, and hand the founder the failing checks and the BEST draft (the highest-scoring attempt so far). Standards are NEVER relaxed to clear a three-strike failure. The gate emits a STOP_NOTIFY_FOUNDER decision and exit code 2 (halt); the caller sends the decision notice through alert dedup, which always sends decision-class notices even past the storm cap.
2. FROZEN RESEARCH. The research package is frozen after Step 3; QC retries REUSE it and never re-run research. The sole exception: a Tier 1 check 12 fabrication failure unlocks ONE supplemental research pass of at most `web_research_bonus_on_fabrication_fail` (default 4) calls, once per episode. A retry that proposes to re-run research without a fabrication failure is REJECTED, as is a second supplemental pass.
3. TARGETED RETRIES. Attempts 2 and 3 revise only the failing sections and dimensions; the gate passes the failure list into the revision prompt. A full Step 6 to 8 rewrite is permitted ONLY on attempt 2 when MORE THAN four rubric dimensions failed (default threshold five); attempt 3 is always targeted. Worst case is roughly 1.6 times a single write, never three times.
4. ACCEPT ONLY WHEN Tier 1 is fully clean AND every rubric dimension scores eight or higher. The gate emits ACCEPT and exit code 0; the episode advances to cover art.

All attempts draw from the ONE shared per-episode content-token budget metered by `podcast-cost-ledger.py`, so even a pathological retry loop cannot spend past the ceiling.

## 6. THE CLOSING GATE

An episode is deliverable only when all sixteen Tier 1 checks pass AND all ten rubric dimensions score eight or higher AND the per-episode checklist is honestly complete and reproduced in the delivery report. A genuine input limitation is noted plainly in the delivery report, never faked into a pass. Misreporting any check is an absolute failure.

## 7. OPERATOR RUNBOOK (PROVE THE GATE)

- Run the deterministic Tier 1 prover on a deliverable, machine-readable:

      python3 58-podcast-production-engine/scripts/qc-tier1-mechanical.py deliverable.json --json

  Exit 0 means the deterministic subset is clean (semantic checks still pending). Exit 2 means one or more Tier 1 violations and the episode is not deliverable. Exit 3 is a usage or input error, still fail-closed.

- Prove the whole check battery, clean fixture plus one violation per check:

      python3 58-podcast-production-engine/scripts/qc-tier1-mechanical.py --self-test

- Record one attempt result and read the decision:

      python3 58-podcast-production-engine/scripts/qc-attempt-gate.py record --episode <job-key> --result result.json --json

  The action field is ACCEPT, RETRY, or STOP_NOTIFY_FOUNDER; exit 0 is a legal forward action, exit 2 is a halt or escalate.

- Validate a proposed retry against policy without changing state:

      python3 58-podcast-production-engine/scripts/qc-attempt-gate.py authorize-retry --episode <job-key> --scope targeted --rerun-research false --json

- Prove every decision path (accept, low-dimension retry, full-rewrite eligibility, three-strike stop with best draft, frozen-research rejection, single-use supplemental pass, post-cap rejection):

      python3 58-podcast-production-engine/scripts/qc-attempt-gate.py --self-test

## 8. ENFORCEMENT POINTER (BINDING)

- Deterministic Tier 1 (checks 1 to 11, 15, 16) at zero model cost: `58-podcast-production-engine/scripts/qc-tier1-mechanical.py`, fail-closed, exit 2 on any AF-EP breach, with checks 12 to 14 reported DEFERRED to the judge tier.
- Attempt counter, targeted-retry policy, frozen research, and the three-strike stop with the best draft: `58-podcast-production-engine/scripts/qc-attempt-gate.py`, exit 0 proceed, exit 2 halt or escalate.
- Semantic checks 12 to 14 and the ten-dimension rubric run on the cheap judge tier under the qc-specialist-podcast persona, distinct from the writer.
- This is the EPISODE gate (Gate B), never the 8.5 BUILD gate (Gate A); the two are never conflated. Without these gates this document would be only a suggestion.
