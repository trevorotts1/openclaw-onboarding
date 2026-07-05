<!-- BAKED PROMPT ASSET | stage 40-landing-image-prompts | subsystem landing-hero
     source record: source/airtable-prompts/08-write-image-prompts-for-landing-page.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Here is the LANDING page copy that you are creating image prompts for. [{{artifact.39-hero-page}}]

Use these brand colors in your image prompt (ignore if nothing is here): [{{intake.brand_colors}}]

Here is the event/service/product/or mission that I want to promote
[  
Name of product/offer/mission{{intake.offer_name}}

Type Of offer:{{intake.offer_type}}

Offer Benefits and additional information
{{intake.offer_benefit}} 

  
{{intake.product_info}}
             ]


Here is the product im promoting here is the product bio: [{{artifact.17-product-bio}}] (the ads are written towards or leads to this)

brand bio [ {{artifact.16-brand-bio}}]

 



No extra output is allowed before or after your commentary, just the pure output only.
