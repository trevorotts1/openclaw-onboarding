<!-- BAKED PROMPT ASSET | stage 29-ad-set-8 | subsystem facebook-ads
     source record: source/airtable-prompts/32-ad-set-8.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R4 category (restored from Airtable User field): category 6 - Benefit Style Ads
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You are writing Ads for category 6  which is the Benefit Style Ads

also here is the other ad that were written so things are in harmony:
[{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}{{artifact.28-ad-set-7}}]



here is the info needed  for you to write the visual ads

Brand Info
brand bio:
 [{{artifact.16-brand-bio}}] 

Product info
product bio:
 [{{artifact.17-product-bio}}]

Offer/Product Name (Product or Service or Mission being promoted):
Offer/ Product name [{{intake.offer_name}}]

Offer/Product Benefits: [{{intake.offer_benefit}}]


Offer/Product Type:[{{intake.offer_type}}]

Product info [{{intake.product_info}}]


Additonal Product Info:

Avatar/ Customer Intellegenge info (this should help you when trying to determine the who)
:
 [
{{artifact.03-rewrite-avatar}}

{{artifact.01-avatar-questions-1-30}}
] (This represents the type of people that are attempting to attract with our visual ads. This is our target audience:)


---
## R4 CATEGORY DIRECTIVE (restored, machine-enforced by AF-AV-ADSET-CAT)
This ad set writes exactly 10 ads for: **category 6 - Benefit Style Ads**. Do NOT default to 'category 2'. Inject all previously written ad sets so the voice stays in harmony.
