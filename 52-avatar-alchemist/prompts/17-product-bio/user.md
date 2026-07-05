<!-- BAKED PROMPT ASSET | stage 17-product-bio | subsystem bios
     source record: source/airtable-prompts/19-product-bio.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Using the following informatiion create a inspiring and provocative product bio. 

Fonders Name [  {{intake.first_name}}  {{intake.last_name}}]

Start Date [ {{intake.brand_start_date}}   ]

Product/offer/mission/Service Information
[
offer name [{{intake.offer_name}}]

typer of offer [{{intake.offer_type}}]

Offer Benefits [{{intake.offer_benefit}}]


Product info [{{intake.product_info}}]
]

Brand Orgin ( your job is to make thisi more compelling) [  {{intake.brand_why}} ]

Brand Info [{{intake.brand_info}}   ]

Who this brand is for [ {{artifact.03-rewrite-avatar}}
{{artifact.01-avatar-questions-1-30}}  ]

Tone to write in when writing the bio [{{artifact.08-blended-tone}}]

Avatar info you should consider when writing about who we do serve:
 [
{{artifact.01-avatar-questions-1-30}}
{{artifact.02-avatar-questions-31-32}}

]

Here is the brand bio so you understand what we do:
[{{artifact.16-brand-bio}}]
