<!-- BAKED PROMPT ASSET | stage 37-fb-headline-copy | subsystem facebook-ads
     source record: source/airtable-prompts/22-facebook-headline-and-primary-textwriter.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R5: 'Name of product/offer/mission:' filled from {{intake.offer_name}} / {{intake.product_info}} (source left it empty).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Here is the ad copy those are on the images that we are going to be using in combination with the ad. Some of the types of ad copy that's going to be on the images, and you should be considering this when you're writing the copy we requested. 

[                          
{{artifact.22-ad-set-1}}
{{artifact.23-ad-set-2}}
{{artifact.24-ad-set-3}}
{{artifact.25-ad-set-4}}
{{artifact.26-ad-set-5}}
{{artifact.27-ad-set-6}}
{{artifact.28-ad-set-7}}
{{artifact.29-ad-set-8}}
{{artifact.30-ad-set-9}}
{{artifact.31-ad-set-10}}
{{artifact.32-ad-set-11}}
{{artifact.33-ad-set-12}}
{{artifact.34-ad-set-13}} ]

Here is the event/service/product/or mission that I want to promote
[  
Name of product/offer/mission{{intake.offer_name}}

Type f offer:{{intake.offer_type}}

Offer Benefits and additional information
{{intake.offer_benefit}} 

product info [{{intake.product_info}}]               ]


Here is the product im promoting: [{{artifact.17-product-bio}}
] (the ads are written towards or leads to this)

brand bio [ {{artifact.16-brand-bio}}]

Here is the infor about the problem, solution, and product aware  [{{artifact.09-problem-aware}}
{{artifact.10-problem-aware-pt2}}

{{artifact.11-solution-aware}}
{{artifact.12-solution-aware-pt2}}

{{artifact.13-product-aware}}
{{artifact.14-product-aware-pt2}}]




No extra output is allowed before or after your commentary, just the pure output only. 



Your output must be in pure Markdown. You are forbidding me from giving you any output that is not in Markdown. Do not add any additional commentary before or after your output.
