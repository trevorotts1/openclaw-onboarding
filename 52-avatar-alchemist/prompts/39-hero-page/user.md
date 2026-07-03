<!-- BAKED PROMPT ASSET | stage 39-hero-page | subsystem landing-hero
     source record: source/airtable-prompts/09-write-the-hero-page.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R6: consumes artifact.38-landing-questionnaire (Answer-9-Questions) as SUPPORTING research —
     this stage's OWN deliverable is the 12-section Hero Landing Page System (see methodology.md),
     NOT a restatement of the 9 questionnaire answers. (Fix: this file used to be byte-identical to
     38-landing-questionnaire/user.md and told the model to "answer the 9 questions" — the wrong
     deliverable for this stage.) R7: runs on the client TIER-A model (the source's sole
     Anthropic-Sonnet chain is removed here per the client-path rule).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Write the complete "Trevor Otts Hero Landing Page System" — all 12 sections, in order, using
EXACTLY these 12 section names (never rename them): "The Big Bold Claim", "The Big Bold Pain 1",
"The Big Bold Pain 2", "The Big Bold Pain 3", "The Big Bold Why", "The Big Bold Who",
"The Big Bold What", "The Big Bold Benefit 1", "The Big Bold Benefit 2", "The Big Bold Benefit 3",
"The Big How To", "The Big Bold Heartfelt Message". Follow every word/character-count and
formatting rule in the system/methodology instructions for this stage.

Here is the information you need to write the page:

Avatar Info (who this page is for):
[
{{artifact.upstream}}

{{artifact.upstream}}
]

Brand Info:
[
{{artifact.upstream}}
]

Product Info:
[
Product Bio [ {{artifact.upstream}} ]

Product Name [ {{intake.offer_name}} ]

Product Info [ {{intake.product_info}} ]

Product Benefits [ {{intake.offer_benefit}} ]

Type of Offer [ {{intake.offer_type}} ]
]

Supporting research (the 9-question landing-page questionnaire answers — use these as SOURCE
MATERIAL for the pain points, benefits, and story; do NOT reproduce them question-by-question,
this stage's output is the 12-section hero page, not the questionnaire):
[
{{artifact.upstream}}
]

Founder's Name [ {{intake.first_name}} {{intake.last_name}} ]

Tone to be used — this must be used verbatim throughout: [ {{intake.tone}} ]

Output format: pure Markdown. Label every section exactly `## Section N: <name>` (N = 1-12, name
from the list above, verbatim). Use H1/H2/H3 headings for internal structure within a section
where helpful. Separate sections with a triple line break. Label every CTA button on its own line
as `CTA button: <text>` where the spec calls for one. No commentary before or after the 12
sections — pure Markdown output only.
