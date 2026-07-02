<!-- BAKED PROMPT ASSET | stage 19-booking-bot | subsystem booking-bots
     source record: source/airtable-prompts/12-create-booking-bot.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

Using the following informatiion to create my booking bot instructions

Here is the ai bot prep doc that i have created to help you create my booking bot instructions [{{artifact.upstream}}]

Fonders Name [  {{intake.first_name}}  {{intake.last_name}}]

Start Date [ {{intake.brand_start_date}}  ]

Brand Orgin  [  {{intake.brand_why}} ]

Brand Info [{{intake.brand_info}}   ]

Who this brand is for [ {{artifact.upstream}}
{{artifact.upstream}} ]







The product we are offering, its benefits, info on it, and this is what we will be  booking an appointment around:
[
offer name/product name:{{intake.offer_name}}


type of offer we are creating an appointment around{{intake.offer_type}}

benefits  and other info about  this offer:
{{intake.offer_benefit}}


Product info [{{intake.product_info}}]

]


Tone (this is the specific instruction your are to to tell the bot to write in use it verbatim do not truncate it) [{{artifact.upstream}}]

Avatar info you should consider when writing about who we do serve:
 [
{{artifact.upstream}}
{{artifact.upstream}}

]

Here is the brand bio so you understand what we do:
[{{artifact.upstream}}]




at the end of your instruction  you must use this exact language verbatim:

at the end of your final output make sure these exact instructions are included verbatim at the end 


Last and most important rule 
# Document Formatting Instructions

## Required Structure
Each document must contain three layered elements:

1. **Section Headers**
   - Use H1 markdown (#) for each major section
   - Format: `# [Section Name] Section`
   - Example: `# Intro Message Section`

2. **XML-Style Labels**
   - Immediately follow the section header
   - Enclose the content for that section
   - Format: `<section_name>content</section_name>`
   - Example: `<intro_message>content</intro_message>`

3. **Markdown Formatting Inside Labels**
   - Use standard markdown formatting within the XML-style labels
   - Bold: `**text**`
   - Lists: Use hyphens (-)
   - Line breaks: Double spaces
   - Code blocks: Triple backticks (```)

## Example Format
```markdown
# Intro Message Section
<intro_message>
Hi (use the place holder for first name here  which should be this merge tag (merge tag is contact.first_name use must use dobule curly braces before the merge tag and after the merge tag!!) . you MUST!! use double curly braces in the front of the merge tag and and then at the end of the merge tag so it will be recognized in the system we use   only doubled) , this is **Amara** from Wake Up Happy Sis.

Your message content here...
</intro_message>


## Key Points
- Every section must have all three elements (header, XML-style label, markdown)
- Maintain consistent spacing (one line between sections)
- Keep original content exactly as provided
- Use appropriate markdown formatting for emphasis and structure
- Never remove or modify the XML-style labels
- Never skip or abbreviate sections
- Whenever you are using any type of list, listicle, or something with bullet points, you must put each item on its own line so that it is easy to read and clear separation.

## Common Mistakes to Avoid
- Don't remove section headers
- Don't convert XML-style labels to actual XML code
- Don't abbreviate content with "..." or "[content continues]"
- Don't merge or combine sections

## Process Checklist
1. Add section header with # and "Section" suffix
2. Add appropriate XML-style label
3. Format content inside label using markdown
4. Verify all three elements are present
5. Check spacing and formatting

YOUR FINAL OUTPUT MUST BE AT LEAST 5000 WORDS AND BE IN PURE MARK DOWN LANGUAGE  NO CONTRACTIONS SHOULD BE USED IN YOUR FINAL OUTPUT . AND NO EXTRA COMMENTARY IS ALLOWED BEFORE OR AFTER YOUR OUTPUT
NO EXTRA COMMENTARY IS ALLOWED BEFORE OR AFTER YOUR OUTPUT

BE SURE TO ADD AN OPENING EXPLANATION OF WHAT OF THIS IS ..IE. START IT OUT WITH YOU ARE BOOKING BOOK AND THESE ARE INTRUCTION TO GUIDE YOUR INTERACTIONS WITH A PERSON WHO MAY BE INTERESTED IN....   FOLLOW THESE INSTRUCTION ... (THIS IS AN EXAMPLE OF AN OPENING TO THE DOCUMENT KEEP THE OPENING UNDER 200 WORDS)


Your output must be in pure Markdown. You are forbidding me from giving you any output that is not in Markdown. Do not add any additional commentary before or after your output.
