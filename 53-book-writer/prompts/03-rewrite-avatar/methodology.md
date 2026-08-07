<!-- BAKED PROMPT ASSET | stage 03-rewrite-avatar | subsystem avatar-core
     source record: source/airtable-prompts/29-rewrite-avatar-niche-and-primary-goal.md (shared avatar-core, sibling Skill 52)
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO provider model ids baked in.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected per BOOK-WRITER-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

You are doing a rewrite of the Avatar's niche and primary goal based on the information provided. You will write a more in-depth and robust Avatar section with deeper psychological insight, so the reader this book is written for is understood at the level a 12-chapter book requires.

## How to think about each rewrite

- **Niche — the bookstore test.** When rewriting the niche, give a more detailed understanding of the category. Think about it this way: if this book were in a bookstore, what category would it sit in? Name the shelf. Make the niche precise enough that the book has a clear, findable home.
- **Primary goal — the reader's own words.** When rewriting the primary goal, capture the reader's primary goal in a way that feels insightful, relatable, and gives a deeper understanding of what success looks like for this specific human. Keep it faithful to the original meaning — the rewrite is a deepening, never a change of direction.

## Input variables

- [Avatar] = provided in the user prompt
- [Niche] = provided in the user prompt
- [Primary Goal] = provided in the user prompt

Base the rewrite on (a) the old [Avatar], [Niche], and [Primary Goal] you are given, and (b) the additional 32-question-and-answer avatar analysis that is injected. You MUST consider the full 32-question analysis before rewriting.

## Process for updating the variables

1. **Analyze information.** Review all provided information, including the answers to the 32 questions and the initial avatar, niche, and primary goal variables.
2. **Update variables.** Create more detailed, descriptive versions of [Avatar], [Niche], and [Primary Goal]. Rename them to [Updated Avatar], [Updated Niche], and [Updated Primary Goal].
3. **[Updated Avatar] guidelines.** Provide a detailed description without using a specific name. Incorporate relevant information from the 32 questions to create a comprehensive profile. If applicable, include cultural and/or gender-specific details.
4. **[Updated Niche] guidelines.** Identify categories aligned with the [Updated Avatar]. Consider book categories in libraries and on platforms like Amazon that would be relevant to the [Updated Avatar]. Name the shelf this book would sit on.
5. **[Updated Primary Goal] guidelines.** Refine and expand on the initial primary goal based on the additional information provided. Keep it faithful to the original; deepen it, do not redirect it.
6. **Cultural and gender relevance.** If a cultural group or gender is specified in the profile, ensure the updated variables are culturally relevant and inclusive, address relevant context and issues, and handle intersections thoughtfully. If none is specified, remain neutral and inclusive.

## Output format

Present the updated variables in this exact format:

# Avatar
[Updated Avatar description]

# Niche
[Updated Niche]

# Primary Goal
[Updated Primary Goal]

Place the variable name (Avatar, Niche, or Primary Goal) in headline-1 markdown format, followed by a line break, then the content, then a double line break before the next variable.

Do not add any extra commentary before or after your output. Output strictly the three updated sections in Markdown.
