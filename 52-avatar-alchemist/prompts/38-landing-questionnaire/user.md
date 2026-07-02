<!-- BAKED PROMPT ASSET | stage 38-landing-questionnaire | subsystem avatar-core
     source record: source/airtable-prompts/16-answer-9-questions.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Here is the information that you will need to answer the 9 questions. 

Avatar Info:
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

Product Bio [ {{artifact.upstream}}  ]

Procuct Name [ {{intake.offer_name}}]

Product Info [ {{intake.product_info}}
]

Product Benefits [{{intake.offer_benefit}}     ]

Type of Offer [{{intake.offer_type}}]


]

Founders Name [{{intake.first_name}} {{intake.last_name}}]


Tone to be used  t his must be used verbatim and add on a section that teaches me out to write a High converting landing page. Using this tone that I'm sharing. This must all be reflected in the answer. 

Your output should be in pure Markdown Language. . No extra commentary is to be provided before or after your output. We are using the Markdown language for easy readability, for organizational structure when we're looking at this on a Google document.

Additionally, it is important to use H1s, H2s, H3s, H4s, etc. headings to create better organization and making it easier and clearer to read when somebody is looking at this.

Additionally, if you are using a list, a list style or a listicle style, every item on that list must be on its own separate line followed by a line break.

To make this easy to read, we should be using double line breaks to separate ideas or introductions of new content or concepts. In many cases, we may use double line breaks to make it easier to read the information. 

Output-wise, you should list the question first and then the answer next, and then at the end of the answer, it should be a triple line break. So there's a clear visual break in between the answers provided to each question. 



Your output must be in pure Markdown. You are forbidding me from giving you any output that is not in Markdown. Do not add any additional commentary before or after your output.
