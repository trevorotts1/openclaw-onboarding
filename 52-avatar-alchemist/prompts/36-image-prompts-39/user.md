<!-- BAKED PROMPT ASSET | stage 36-image-prompts-39 | subsystem landing-hero
     source record: source/airtable-prompts/20-image-prompt-writer.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Here is the ad copy for each of the ads below

[      {{artifact.35-top-39}}                    ]

Use these brand colors in your image prompt (ignore if nothing is here): [{{intake.brand_colors}}]


Here is the event/service/product/or mission that I want to promote
[  
Name of product/offer/mission{{intake.offer_name}}

Type f offer:{{intake.offer_type}}

Offer Benefits and additional information
{{intake.offer_benefit}}                ]


Here is the product im promoting: [{{artifact.17-product-bio}}
] (the ads are written towards or leads to this)

brand bio [ {{artifact.16-brand-bio}}]

We have shared with you a total of 39 different ads, three from each of the main ad area types. That means that we should have a total of 39 Image Prompts. You are forbidden to give me less than 39 Image Prompts. I must have one Image Prompt to match each of the different ads being represented. Remember, each image prompt should feel different and create a different or unique image so that there's variety and creativity. Never use the same artist twice. Never use the same style twice. Never used the same movie producer twice. Never used the same photographer twice. 



No extra output is allowed before or after your commentary, just the pure output only. 


Your output must be in pure Markdown. You are forbidding me from giving you any output that is not in Markdown. Do not add any additional commentary before or after your output.
