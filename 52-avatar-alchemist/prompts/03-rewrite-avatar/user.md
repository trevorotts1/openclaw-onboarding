<!-- BAKED PROMPT ASSET | stage 03-rewrite-avatar | subsystem avatar-core
     source record: source/airtable-prompts/29-rewrite-avatar-niche-and-primary-goal.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

based upon these variable complete complete question 1-30
[
My Ideal Avatar / Dream Customer = [{{intake.ideal_avatar}}]

My Niche=[{{intake.niche}}]

My Ideal Avatar's Primary Goal= [{{intake.primary_goal}}]

My Name = [{{intake.first_name}} {{intake.last_name}}]

Tone= [{{intake.tone}}]

here are 32 questions and answer to help you deeply understand my the avatar before you start your rewrite of only the sections i requested: [{{artifact.upstream}}
{{artifact.upstream}}]

]


DO NOT ADD ANY ADDITIONAL COMMENTARY BEFORE OR AFTER YOUR OUTPUT I WANT JUST THE PURE OUTPUTS OF WHAT I ASKED FOR
