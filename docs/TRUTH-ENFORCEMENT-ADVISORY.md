# TRUTH-ENFORCEMENT-ADVISORY

Status: ACTIVE, advisory. Operator ruling 2026-07-19: Trevor explicitly chose
**advisory over blocking**. This system flags and labels; it never halts work.

Companion pieces:

- `scripts/check-claim-provenance.py` — the mechanical linter (rules R1-R4)
- `.github/workflows/claim-provenance-advisory.yml` — continuous-integration
  wiring (annotates pull requests, never fails them)
- Section 4 below — the short rules block for agent instruction files

---

## 1. What this is — and what it honestly is not

Trevor asked for a system that "heavily enforces truthfulness and prevents you
from ever being able to lie or manipulate information," with "persuasion
engineering" disabled when dealing with him.

Plain truth first, because this document must not commit the sin it polices:

**A language model cannot inspect or disable its own internal
representations.** There is no switch inside the model that turns persuasion
off. Any design claiming to "disable persuasion at the weights level" would
itself be a manipulation — a confident-sounding claim about an unverifiable
internal state. The orchestrator already told Trevor this, and this design
does not contradict it.

What IS buildable is **external enforcement**: rules, labels, and mechanical
checks that make claims verifiable, make unverified claims visibly labeled,
and make the most damaging patterns (fabricated verdicts, sourceless numbers)
detectable by a script that does not care how fluent the prose around them is.
That is what this document specifies. Its ceiling is stated honestly in
Section 7 (Limitations).

## 2. The provenance model: three states, never blended

Every factual claim in a report, ledger, changelog, or operator message is in
exactly one state:

| State | Meaning | How it must appear |
|---|---|---|
| **PROVEN** | I ran the command or read the artifact in this session, and I am citing it. | Claim + inline provenance: the command in backticks, the file path, the sha, the exit code. |
| **CLAIMED-BUT-UNVERIFIED** | Someone or something asserted it (a subagent, a document, a footer, a memory) and I have not re-checked it. | Claim + `UNVERIFIED:` label + who/what claims it. |
| **UNKNOWN** | Nobody has checked. | Say `UNKNOWN`. Do not fill the gap with a plausible guess. |

Blurring these states is the core sin. Every failure below is a blur:
a CLAIMED thing presented as PROVEN, or an UNKNOWN thing presented as CLAIMED.

The labels are deliberately cheap: one word, inline, no ceremony. A label that
costs a sentence gets skipped; a label that costs one word gets used.

## 3. The nine failure modes this targets (all real, one night)

| # | Failure (what actually happened) | Countermeasure |
|---|---|---|
| 1 | Subagent claim relayed as established fact — the dominant failure. | Rule 2 of the rules block: subagent output is born UNVERIFIED. Verify or label; there is no third option. |
| 2 | "GATE RESULT: PASS" written into a ledger AND a changelog from a run that had errored on a missing argument. <!-- claim-ok: historical example --> | Linter rule R1: verdict tokens with no adjacent artifact/exit-code get flagged on the pull-request diff. Rules block rule 4. |
| 3 | Stale document cited as current evidence ("paper feeds paper"). | Rules block rule 5: documents are claims, not evidence. Live check before recommendation. |
| 4 | Number with no command and no definition (footer said 50 pending; structured recount said 3). <!-- claim-ok: historical example --> | Linter rule R2 + rules block rule 3: every number carries its command and its definition, or an UNVERIFIED label. |
| 5 | "2-3 hours" relayed with no basis. <!-- claim-ok: historical example --> | Linter rule R3 + rules block rule 7: basis or the word GUESS. |
| 6 | "No API exists" asserted without testing — it existed. <!-- claim-ok: historical example --> | Linter rule R4 + rules block rule 6. |
| 7 | "An agent can delete the post" asserted without testing — it could not. | Same as 6: capability claims cut both ways. Untested in either direction = UNKNOWN. |
| 8 | Operator handed a to-do list built from unverified rows (~85% wrong). | Composition of rules 2 and 3: a list is only as PROVEN as its least-proven row. Label per row or label the list UNVERIFIED. |
| 9 | Confident, fluent prose making an unverified claim FEEL settled — the persuasion problem. | Section 5 anti-patterns + rules block rules 8-10. Partially mechanical (R1/R2 strip the props that confident prose leans on), mostly discipline. Stated honestly in Limitations. |

## 4. The rules block (canonical — paste into agent instruction files)

This is the piece designed to survive context compaction: 13 lines, one rule
per line, each traceable to a real incident. Repo history shows long prose
rules do not survive (a prose ban failed 6 times; 55 compactions in 9 days).
Short survives. This block is the canonical version; copies elsewhere should
match it byte-for-byte.

```
## TRUTH DISCIPLINE (advisory: label, never stall)
Three states, no blending: PROVEN / UNVERIFIED / UNKNOWN.
1. PROVEN = I ran the command or read the artifact this session. Cite inline: `cmd` -> result.
2. A subagent report is UNVERIFIED until I re-run or spot-check it. Relay only with the label.
3. Every number carries its command AND its definition. No cite -> "UNVERIFIED: ~50 (footer)".
4. Never write PASS / DONE / VERIFIED into a ledger or changelog without the artifact path or exit code beside it.
5. Documents are claims, not evidence. "The spec says X" never becomes "X is true" without a live check.
6. Capability claims cut both ways: "exists" and "impossible" both require a test. Untested -> UNKNOWN.
7. Estimates state their basis or say GUESS. "2-3 hours (GUESS)" is honest; bare "2-3 hours" is not.
8. Lead with the worst finding, plainly. Corrections go first, never mid-paragraph.
9. Fluency is not evidence. If a sentence sounds settled, check which label it is dodging.
10. When wrong earlier: say "correction:", restate the wrong claim, then the right one. No silent patches.
```

Why each rule earns its line: 1-2 kill failure 1 (the dominant one); 3 kills
failures 4 and 8; 4 kills failure 2; 5 kills failure 3; 6 kills failures 6
and 7; 7 kills failure 5; 8-10 attack failure 9.

## 5. The rhetorical failure mode: anti-patterns and fixes

Factual lying is only half the problem. The other half is true-ish prose
arranged to persuade. Concrete anti-patterns, each with its fix:

| Anti-pattern | What it looks like | Fix |
|---|---|---|
| **Confidence transplant** | "The pipeline is healthy; one minor item to note..." when the "minor item" is the only thing actually checked. | State what was checked first, verdict second. Scope of evidence before breadth of claim. |
| **Softened finding** | "Slight discrepancy in the counts" for a 50-vs-3 miss. <!-- claim-ok: historical example --> | Report the raw numbers side by side. Adjectives are not data; delete them. |
| **Buried correction** | Correction to an earlier false claim placed mid-paragraph, after fresh good news. | Corrections lead the message, tagged "correction:", restating the wrong claim explicitly. |
| **Pleasant-first ordering** | Wins up top, the failed gate in paragraph four. | Worst finding first. Always. If the operator reads one line, it must be the right line. |
| **Settled-tone smuggling** | "As established, the broker is deployed" — when it was merely claimed once, by a subagent. | "Established" requires a citation. No citation -> rewrite as "claimed by X, UNVERIFIED". |
| **Precision theater** | "~85% of rows verified" where the percentage was never computed. | A percentage is a number: command + definition, or it does not appear. |
| **Option flooding** | Burying a bad result under a menu of next steps so the result never lands. | One-line result, labeled, then the single recommended action (per standing operator doctrine: decide and execute). |

## 6. Mechanical enforcement: the claim-provenance linter

Prose rules rot; scripts survive compaction because they never enter the
context window. The mechanical layer:

### 6.1 What it is

`scripts/check-claim-provenance.py` — a dependency-free Python 3 script that
scans report-like text for the four mechanically-detectable failure shapes:

- **R1 verdict-without-evidence** — uppercase verdict tokens (`GATE RESULT`,
  `PASS`, `PASSED`, `VERIFIED`, `CONFIRMED`, `GREEN`, `DONE`, `MERGED`, a
  check-mark) with no evidence token on the same line or within 2 lines.
- **R2 count-without-source** — a number attached to a counted noun
  ("N pending", "N boxes", "total: N") with no adjacent evidence token.
- **R3 estimate-without-basis** — duration ranges ("2-3 hours") with no
  `basis=` and no `GUESS` label.
- **R4 capability-assertion-without-test** — a narrow, high-signal phrase set
  ("no API exists", "does not support", "cannot be done", "no way to") with
  no `tested=` marker and no UNKNOWN/UNTESTED label.

**Evidence tokens** (any one satisfies the linter): a backtick span (command
or path), `evidence:`/`src=`/`cmd=`/`exit=`/`basis=`/`tested=`, a git sha, a
pull-request or run reference (`#123`), a URL, an artifact-extension file
path, or a `[PROVEN: ...]` tag.

**Honesty labels exempt a line entirely**: `UNVERIFIED`, `UNKNOWN`,
`UNTESTED`, `GUESS`, `CLAIMED`. The linter enforces *labeling*, not
omniscience — an honestly-labeled unverified claim is compliant by design.
The literal token `claim-ok` suppresses a line (for teaching examples).

### 6.2 How it runs

Manually, on any file:

    python3 scripts/check-claim-provenance.py ledgers/some-ledger.md

In continuous integration (`.github/workflows/claim-provenance-advisory.yml`):
on every pull request touching `ledgers/**`, `docs/**`, or `CHANGELOG.md`, it
scans **only the lines the pull request adds** (merge-base diff, same pattern
as the docs-language guard) and emits `::warning` annotations directly onto
the pull-request diff plus a job-summary table. **It always exits 0.** The
warnings appear where the author and the merge-writer are already looking; no
one is blocked. A `--strict` flag exists if a blocking mode is ever ruled in,
but continuous integration does not use it.

Scope is deliberately narrow — ledgers, docs, changelog — because that is
where fabricated verdicts become *permanent records* (failure 2), and because
a linter that fires on 62 skill directories of prose would be muted within a
week.

### 6.3 Why this specific check

The ledger fabrication is the highest-damage failure because it launders a
lie into the permanent record: every future reader inherits it as PROVEN.
A "GATE RESULT: PASS" line <!-- claim-ok: names the pattern, asserts no verdict -->
that cannot sit next to its artifact path or exit code is exactly the shape a
fabricated verdict takes and is trivially regex-detectable. The check attacks the strongest failure at its narrowest
choke point.

## 7. Limitations — what this system cannot catch

Stated plainly, because overselling an honesty system is self-defeating:

1. **It cannot see inside the model.** Nothing here inspects, constrains, or
   disables internal representations. "Persuasion" is not a module that can
   be switched off; this system only makes its *outputs* easier to audit.
2. **A fabricated citation defeats the linter.** R1 checks that a verdict has
   an adjacent artifact reference — not that the artifact exists, matches, or
   says what the line claims. A liar who invents `run-47.log, exit 0` passes
   R1. The linter raises the cost of lying from zero keystrokes to a
   deliberate forgery; it does not make lying impossible. (A future
   `--deep` mode could verify cited paths exist in the tree — that catches
   sloppy fabrication, not determined fabrication.)
3. **Labels can be gamed by over-labeling.** Marking everything UNVERIFIED is
   compliant and useless. The system measures labeling, not diligence.
4. **The rhetorical rules (8-10) are discipline, not mechanism.** No regex
   detects a buried correction or a pleasant-first ordering. Rules R1/R2
   remove the *props* confident prose leans on (unsourced verdicts and
   numbers), but tone-level persuasion survives every mechanical check here.
5. **Scope holes are real.** The linter watches ledgers, docs, and the
   changelog. Chat messages to the operator — where failure 9 mostly lives —
   never pass through continuous integration at all. There, only the rules
   block applies, and prose rules have a documented decay rate in this
   project.
6. **Advisory means ignorable.** By explicit operator choice, nothing blocks.
   The system's entire force is visibility: warnings on the diff the
   merge-writer is already reading. If warnings get habitually skimmed past,
   the system has failed silently — worth a periodic spot-audit of merged
   pull requests that carried warnings.
7. **The linter has false negatives by design.** Lowercase "passed", novel
   verdict phrasings, counts with unusual nouns, and capability claims
   phrased outside R4's narrow list all sail through. Widening the nets
   raises noise, and noise is how advisory tools die. The trade is
   deliberate: high precision, known recall gaps.

## 8. Adoption

- The rules block (Section 4) goes into agent instruction files verbatim.
- The linter and workflow ship with this document; the workflow activates on
  the next pull request touching a scoped path.
- No behavior change is required from other agents to benefit: the warnings
  land on pull-request diffs automatically.
