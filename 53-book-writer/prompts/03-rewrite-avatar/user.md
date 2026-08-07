<!-- BAKED PROMPT ASSET | stage 03-rewrite-avatar | subsystem avatar-core
     source record: source/airtable-prompts/29-rewrite-avatar-niche-and-primary-goal.md (shared avatar-core, sibling Skill 52)
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO provider model ids baked in.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Based on these variables, rewrite ONLY the Avatar, Niche, and Primary Goal sections:
[
My Ideal Avatar / Dream Customer = [{{intake.ideal_avatar}}]

My Niche = [{{intake.niche}}]

My Ideal Avatar's Primary Goal = [{{intake.primary_goal}}]

My Name = [{{intake.first_name}} {{intake.last_name}}]
]

Here is the full 32-question avatar analysis to help you deeply understand the avatar before you rewrite only the sections requested:
[{{artifact.01-avatar-questions-1-30}}
{{artifact.02-avatar-questions-31-32}}]

DO NOT ADD ANY ADDITIONAL COMMENTARY BEFORE OR AFTER YOUR OUTPUT. OUTPUT ONLY THE THREE UPDATED SECTIONS: AVATAR, NICHE, PRIMARY GOAL.
