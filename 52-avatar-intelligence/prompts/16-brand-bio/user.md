<!-- BAKED PROMPT ASSET | stage 16-brand-bio | subsystem bios
     source record: source/airtable-prompts/10-brand-bio.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Using the following informatiion create a inspiring and provocative bio. 

Fonders Name [  {{intake.first_name}}  {{intake.last_name}}]

Start Date [ {{intake.brand_start_date}}   ]

Brand Orgin ( your job is to make thisi more compelling) [  {{intake.brand_why}} ]

Brand Info [{{intake.brand_info}}   ]

Who this brand is for [ {{artifact.upstream}}
{{artifact.upstream}}  ]

Tone to write in when writing the bio [{{artifact.upstream}}]

Avatar info you should consider when writing about who we do serve:
 [
{{artifact.upstream}}
{{artifact.upstream}}

]
