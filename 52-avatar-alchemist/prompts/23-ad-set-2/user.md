<!-- BAKED PROMPT ASSET | stage 23-ad-set-2 | subsystem facebook-ads
     source record: source/airtable-prompts/04-ad-set-2.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R4 category (restored from Airtable User field): category 2 - Who+ (Plus) Style Ads
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You are writing Ads for category 2  which is the Who+ (Plus) Style Ads

also here is the other ad that were written so things are in harmony:
[{{artifact.upstream}}]

here is the info needed  for you to write the visual ads

Brand Info
brand bio:
 [{{artifact.upstream}}] 

Product info
product bio:
 [{{artifact.upstream}}]

Offer/Product Name (Product or Service or Mission bein promoted): [{{intake.offer_name}}]
Offer/Product Benefits: [{{intake.offer_benefit}}]
Offer/Product Type:[{{intake.offer_type}}]


Additonal Product Info:

Avatar/ Customer Intellegenge info (this should help you when trying to determine the who)
:
 [
{{artifact.upstream}}

{{artifact.upstream}}
] (This represents the type of people that are attempting to attract with our visual ads. This is our target audience:)


---
## R4 CATEGORY DIRECTIVE (restored, machine-enforced by AF-AV-ADSET-CAT)
This ad set writes exactly 10 ads for: **category 2 - Who+ (Plus) Style Ads**. Do NOT default to 'category 2'. Inject all previously written ad sets so the voice stays in harmony.
