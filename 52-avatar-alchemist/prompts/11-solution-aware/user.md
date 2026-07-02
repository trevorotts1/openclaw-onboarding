<!-- BAKED PROMPT ASSET | stage 11-solution-aware | subsystem awareness
     source record: source/airtable-prompts/26-solution-aware.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Go to the section of my instruction labeled "Solution Aware Avatar" and use the instructions and examples there write the output for the solution aware avatar. 

here is the input data you are to use when writing this avatar
[niche=[{{intake.niche}}]
offer name= [{{intake.offer_name}}]
type of offer= [{{intake.offer_type}}]
offer benefit = [{{intake.offer_benefit}}]
target market= [{{intake.target_market}}]
brand info=[{{intake.brand_info}}] 
Product info [{{intake.product_info}}]
]


Additonal info you consider and infuse in to your output  
[
{{artifact.upstream}}

{{artifact.upstream}}
{{artifact.upstream}}

]




You must achieve a minimum word count of 1500 words.

I only want a pure output  of just the content and nothing else do not add any addional commentary before or after your output. 

Your output must be in pure markdown language . Be sure to h1, h2, h3, h4 , h5 headings to organize the information for easy reading. when using list or listicle style items each item must be on its own line seperated by line breaks for easy reading 
Use bold fonts & italics where relevant to highlight important info
Use line breaks and double line breaks to clearly seperate ideas to make for easy reading
