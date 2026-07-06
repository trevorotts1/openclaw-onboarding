# Module: Research Assistant Stage (Pipeline Step 3)

**Owns:** Step 3 of the canonical 18 step pipeline. This is the mandatory Research Assistant stage.
It runs BEFORE any sizing, blueprinting, or drafting. No draft is written until this stage has
produced a frozen research package.

**State:** on entry the run moves to `researching` via `podcast_state.py`. The package this module
produces is written into the episode record and then frozen.

**Writing rules binding on everything this module produces:** zero em dash characters anywhere; no
triple backtick or code fence markers in any produced output; every claim real and verified; the
respondent's intent is never changed. These are hard rules, not preferences.

---

## 1. Why this stage exists

Respondents rarely bring research of their own. They bring a core idea, a stated tone, a
transparency admission, and sometimes a story or a quote. This stage turns that raw material into
the internal fuel the episode is built from: sharpened answers, three power statements, the missing
takeaways and supporting findings, up to three real verified case studies, and a closing question or
call to action. It feeds the blueprint. It never appears in the deliverable as-is.

The output goes straight from text to speech to a listening audience with no human editor in
between, so a fabricated study is a business failure, not a style note. Everything referenced later
in the episode must be traceable back to a verified source assembled here.

---

## 2. Model and tool routing

Two different resources do two different jobs in this stage. Do not confuse them.

- **Content reasoning** (answer improvement, power statement extraction, gap filling, takeaway
  generation, case study compression for the ear) runs on the runtime content model chain in this
  fixed priority order: Kimi 2.6 on Ollama Cloud (thinking high), then GLM 5.2 on Ollama Cloud
  (thinking high), then the OpenRouter equivalents in the same order (Kimi 2.6, then GLM 5.2), then
  Gemini 3.1 Flash Lite as the final fallback. If none resolve, select a comparable writing model
  and record the substitution in the delivery report; the pipeline never stalls solely because a
  preferred model is unavailable. Zero Anthropic model ids, providers, packages, keys, or hosts ship
  in this path (`guard-no-anthropic-runtime.py` enforces this at the merge gate and refuses runtime
  deny pattern substitutions).
- **Web research** (verifying case studies, confirming findings) runs on whatever web research tool
  the operator's system provides. Tool selection rule: if Perplexity is wired, use Perplexity. If it
  is not, use the best available web research or web search tool wired into the OpenClaw setup. If
  several non Perplexity tools exist, use the most capable one. If no web research tool exists at
  all, state that limitation plainly in the delivery report and build the episode from logic,
  universal experience, and the respondent's own material only, never from invented evidence. Name
  the research tool used in the delivery report.

The content model chain never performs the research tool's job and the research tool never grades or
writes content. Convert and Flow is the client facing name of the downstream data plane; never say
GoHighLevel or GHL on any client visible surface.

---

## 3. Input answers this stage reads

Read the improved-source material from the survey answers already mapped at intake. Field keys are
standardized across clients:

- The per style Q1 answer (and Q2 in the Provocative path) is the content engine: the thesis, the
  argument, any stories, and the takeaways all originate here.
- The stated speaking tone answer is the voice governor and shapes how every improved answer and
  power statement reads.
- The transparency answer, `contact.podcast_interview_smiq` (Single Most Important Question), is the
  mandatory vulnerability material. Improve its clarity, never sanitize away its rawness or honesty.
- The additional information answer, `contact.podcast_survey__additional_info` (note the double
  underscore), is context. Consider it fully when present; if empty, ignore it.
- The preferred pronoun, `contact.my_preferred_pronoun`, governs every reference to the speaker or
  guest in any language this stage produces. Never guess it and never default it.

The visual description answer feeds the separate cover art pipeline only and is never read into the
research package. Contact details and SMS consent language are administrative and never enter the
package.

---

## 4. Part 1: Answer improvement and three power statements

Take every answer the respondent gave and improve the communication of it. Make each answer more
compelling, give it greater clarity, and expand it wherever expansion adds genuine insight or
significance. Two hard boundaries: you must not remove any important detail or point the respondent
made, and you must not change the respondent's intent. Their thesis stays their thesis. The improved
answers, not the raw answers, are the true source material the blueprint and draft are built from.

If the respondent shared a real personal story, reframe and expand it into a more powerful, more
compelling telling while keeping every fact they gave you true to what they gave you. If they shared
no personal story, do not invent one; the improvement here is clarity and force, never fabricated
biography.

From this improved material, extract exactly three unique power statements or quotes suitable to be
spoken inside the episode. Each power statement is built from the respondent's own ideas, phrased in
their voice and tone, quotable, and short enough to land aloud. They are candidates the blueprint
places at high leverage moments; they are not invented positions the respondent never took.

---

## 5. Part 2: Gap filling

Using the respondent's core answer and stated tone as the guide, generate what the respondent did
not provide, in the spirit of the original intake questions and relevant to the audience's
entrepreneurial, professional, or personal journeys:

- The three key insights or takeaways the audience should remember.
- The supporting research findings and examples for each main point.
- The thought provoking closing question or call to action.

Everything generated here must stay in service of the respondent's thesis and be practical for the
listener. Gap filling adds reinforcement and structure; it never substitutes a new argument for the
respondent's.

---

## 6. Part 3: Case study research

Conduct web research and produce up to three relevant case studies that align with the main topic.
Zero, one, two, or three is acceptable. For each case study, gather this structure for your own
understanding before writing (this is research scaffolding, not script format):

- Overview: a brief summary of the case study, the people, setting, and context.
- Challenges: the primary obstacles or conflicts faced.
- Solutions: the strategies implemented to address the challenges.
- Outcomes: the positive results or lessons learned.
- Backstory: the journey leading up to the case study.
- Accomplishments: key milestones achieved.
- Impact: the broader impact on the industry or community.

**Case study rules (binding):**

- Every case study must reflect real people or real organizations, verified through research. You
  are forbidden from inventing a case study, a person, a company, a statistic, or an outcome. If
  research cannot confirm enough real case studies, use fewer, or use none and lean on the
  respondent's material. A shorter, honest episode beats a padded, fabricated one.
- Demographic matching: if the topic involves or is addressed to a specific group (for example Black
  women entrepreneurs, Black men in corporate leadership, veterans, single mothers), the case
  studies must reflect that demographic wherever credible real examples exist.
- Case studies enter the episode later as spoken story material, compressed and dramatized for the
  ear by the Style Engine, never recited as a report. The structured breakdown above stays in the
  package as scaffolding.
- Represent every real finding honestly. Simplify for the ear, never distort. Spoken attribution is
  natural and brief, for example "researchers at a major university found," or the actual confirmed,
  pronounceable institution or person's name.

---

## 7. The 12 call cap and the research freeze

- **Hard cap:** web research is capped at 12 calls per episode (furnace Guardrail 4).
  `podcast-cost-ledger.py` prechecks and records every billable research call against this cap and
  against the shared 400,000 token episode budget. When the cap is reached, stop researching and
  build the package from what has already been verified.
- **Freeze after this step:** once assembled, the research package is written into the episode
  record and FROZEN. Every downstream QC retry reuses the same frozen package; a QC failure does not
  re-open research. `qc-attempt-gate.py` enforces frozen research reuse across attempts.
- **Single supplemental exception:** only a Tier 1 fabrication failure (episode QC check 12) may
  unlock one supplemental research pass of at most 4 additional calls, solely to replace or verify
  the flagged item. `qc-attempt-gate.py` owns this exception. No other failure re-opens research.

Running research once and freezing it is what bounds the three strike revision loop to roughly 1.6
times a single write cost instead of three full rewrites.

---

## 8. Output: the internal research package

The output of this stage is a single internal research package containing:

1. The improved and expanded answers (the true source material).
2. The three power statements or quotes, in the respondent's voice.
3. The three key takeaways.
4. The supporting research findings and examples for each main point.
5. Up to three verified case studies with their structured breakdown and sources.
6. The closing question or call to action.

This package feeds the blueprint and sizing module and the draft. It is stored in the Episode
Package document later, but it never appears verbatim in the Speech Script deliverable. The
respondent's intent, tone, and pronoun are preserved throughout.

---

## 9. Downstream hooks and hard rules recap

- Everything referenced later must be verified here. Episode QC Tier 1 check 12 (no fabrication) is
  the deterministic downstream gate; it runs on the cheap judge tier, never on the writer model, and
  it will fail the episode if any study, statistic, institution, or claim cannot be traced to a
  verified source in this package.
- No fabricated study, statistic, person, company, or outcome anywhere in the package.
- No em dash characters and no triple backtick or code fence markers in any produced output.
- Never change the respondent's intent; elevate the truth, never replace it.
- The package is frozen after this step and reused by all QC retries.
