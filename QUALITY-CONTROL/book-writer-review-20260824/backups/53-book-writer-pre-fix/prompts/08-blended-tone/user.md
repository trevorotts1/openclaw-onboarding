<!-- BAKED PROMPT ASSET | stage 08-blended-tone | subsystem tone
     source record: source/airtable-prompts/11-write-blended-tone.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R1: `<tone_style_1..4>` now receive the four tone-style ANALYSIS documents (artifact.04..07), not raw names (source passed only names -> dead compute).
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You are an expert at analyzing speaking and communication styles. Your task is to create a new, unique writing tone by blending five different tones, and then provide detailed instructions on how to write in this new style. Follow these steps carefully:

1. Read and analyze the following five tones:

<tone_style_1>
{{artifact.04-tone-style-1}}
</tone_style_1>

<tone_style_2>{{artifact.05-tone-style-2}}

</tone_style_2>

<tone_style_3>{{artifact.06-tone-style-3}}

</tone_style_3>

<tone_style_4>{{artifact.07-tone-style-4}}

</tone_style_4>

<original_tone>
{{intake.tone}}
</original_tone>

2. Create a new blended tone by combining unique attributes from each of the five tones provided. This new tone should be called "The {{intake.first_name}} {{intake.last_name}}Tone".

3. Write a detailed description of The  {{intake.first_name}} {{intake.last_name}}Tone, explaining its unique characteristics and how it incorporates elements from each of the five original tones. This description should be clear, allowing readers to understand the essence of the new tone.

4. Provide step-by-step instructions on how to write using The {{intake.first_name}} {{intake.last_name}} Tone. These instructions should be detailed enough for any writer to understand and implement the new style consistently. Include guidance on:
   - Sentence structure and length
   - Vocabulary choices
   - Rhythm and pacing
   - Use of literary devices
   - Emotional tone and impact

5. List and explain the specific literary devices that should be used when writing in The {{intake.first_name}} {{intake.last_name}} Tone. Indicate how these devices relate to the original tones and how they should be incorporated into the new style.

6. Provide at least two short examples (2-3 sentences each) of writing in The {{intake.first_name}} {{intake.last_name}} Tone. These examples should clearly demonstrate the unique attributes of the new style.

7. Conclude with a summary of the key points to remember when writing in The {{intake.first_name}} {{intake.last_name}} Tone.


This must achieve a minimum of 2000 words. Focus on creating a clear, actionable guide that will allow writers to consistently produce content in this new, blended tone across various formats such as books, blogs, emails, and social media posts.

Present your response in the following format:

<new_tone_description>
[Your description of The {{intake.first_name}} {{intake.last_name}} Tone]
</new_tone_description>

<writing_instructions>
[Your step-by-step instructions for writing in The {{intake.first_name}} {{intake.last_name}} Tone]
</writing_instructions>

<literary_devices>
[List and explanation of literary devices to be used]
</literary_devices>

<examples>
[Your two short paragraph examples of writing in The {{intake.first_name}} {{intake.last_name}} based off of this: [{{intake.primary_goal}}] Tone]
</examples>

<summary>
[Brief summary of key points to remember]
</summary>

Final output should be a minimum of 3,000 words.
