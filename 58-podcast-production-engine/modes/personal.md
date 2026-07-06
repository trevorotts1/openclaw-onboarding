# Personal Podcast Style, Mode Module (Skill 58, Podcast Production Engine) v1.0.0
## Mode id: personal_podcast_style. Default output-type preset: solo.

This module governs the narrative perspective and framing for the Personal Podcast Style production mode. A mode never changes the Style Engine mechanics (arc beats, word budgets, signature line, forbidden lists); it changes perspective, opening posture, transparency-beat voicing, and the terminal boundary. The four Style Engines (Counter Intuitive, Vulnerable, Provocative, Passionate) run identically inside this mode; only the point of view and the ending action differ from Interview Style.

Selection: the Production Mode is carried on the intake payload and read at Step 1 (Ingest). The primary style selector is contact.podcast_survey_writing_style. Where a Personal Podcast style variant selector is present (contact.select_your_presentation_style_personal_podcast), only Counter Intuitive and Passionate are offered on that path; honor whichever selector the payload actually carries and never invent a style the respondent did not choose. Resolving this mode sets the default preset to solo unless the payload explicitly names a different output-type preset (see config/presets.json).

Writing rules binding on every episode this mode produces: zero em dash characters, no triple backtick fences or code-fence markers of any kind, no markdown or labels in the spoken script. These are enforced by qc-tier1-mechanical.py (Episode Gate, Tier 1 checks 1 through 4).

### 1. Definition

The person who answered the survey IS the podcast host. The episode is their own episode, delivered in their own voice, in their own cloned Fish Audio voice at render time. There is no interviewer and no third party; the respondent conceived it, wrote it, and is delivering it.

### 2. Narrative perspective

First person throughout. The word "I" belongs to the survey respondent. The entire episode reads as though the respondent is speaking directly to the listener. There is no host-and-guest structure and no reporter framing. Any drift into third-person narration of the speaker as a separate character is a mode-perspective failure and is caught by Episode Gate Tier 1 check 13 (MODE PERSPECTIVE: Personal is first person throughout, no slippage).

### 3. Opening posture: cold open and show frame

Personal Podcast Style carries NO show frame and NO canned welcome. There is no "Welcome to another episode of ..." line, no station identification, no host housekeeping, and no self-introduction beyond what the selected Style Engine's own opening mechanic requires. The episode opens straight into that Style Engine open:

    Counter Intuitive: the reversal-led open that sets up the assumption to be overturned.
    Vulnerable: the disarming personal confession open.
    Provocative: the confession or arresting-scenario open, then the frame that a case is about to be made.
    Passionate: the powerful provocative question aimed at the listener, hook first.

This is the sharpest daily contrast with Interview Style, which mandates a cold open followed by a spoken show frame. In Personal mode there is no show frame at all. Do not add one. (See modes/interview.md for the opposite rule.)

### 4. Transparency beat handling

The respondent's transparency answer lives in contact.podcast_interview_smiq (the Single Most Important Question, or SMIQ: the answer to "Being Totally Transparent, what is the number 1 thing you are struggling with related to ____"). In this mode it must be woven into the episode as a first person vulnerable admission. This is a structural requirement, not an option; removing it is forbidden, including during the Improvement Pass.

Division of ownership: the MODE owns the voice of the beat (first person, the speaker naming their own live struggle, for example "I am still working on this myself"). The selected STYLE ENGINE owns the placement of the beat within the arc:

    Vulnerable: inside the breakdown and surrender beat.
    Passionate: immediately before the universal principle, so the principle reads as earned.
    Counter Intuitive and Provocative: at that engine's designated vulnerability beat position.

Deliver it with real rawness: the resistance, the fight, and the reluctant, honest surrender. Humor is permitted as pressure release, never as deflection that dodges the admission. The beat exists to humanize the speaker and to make the audience know the speaker is still working on themselves too.

### 5. Fabrication boundary

Use only the personal stories, quotes, affirmations, and details the respondent actually provided in their answers. Inventing a personal story, a childhood memory, a family member, a business failure, or any biographical detail the respondent did not give is absolutely forbidden. If the respondent provided no personal story, build the episode on their ideas, on verified research from the Research Assistant stage, and on clearly framed hypothetical or universal scenarios ("imagine a woman who ..."), never on fabricated first person biography. If the respondent DID share a personal story, reframe it, expand it, and present it more powerfully than they told it while keeping every fact they gave true to what they gave. This boundary is scored by Episode Gate Tier 1 check 12 (NO FABRICATION); the judge tier, never the writer, decides it.

### 6. Pronoun governance

contact.my_preferred_pronoun governs how the speaker is referred to everywhere a third-person reference occurs. In this mode the speaker is mostly "I", but any third-person self-reference and every honorific must match the stated pronoun. Never guess a pronoun and never default to one. Enforced by Episode Gate Tier 1 check 14 (PRONOUN CORRECTNESS).

### 7. Preset and terminal boundary

Default output-type preset: solo (config/presets.json). Book teaser: NONE. Personal Podcast episodes never receive a book teaser; that bonus is exclusive to the Interview Style lead-generation path.

Terminal action at Step 17 (Trigger and Enroll): append the finished episode as a new row to the client's running episode spreadsheet (the running document created once at onboarding), storing the episode links there. This mode HARD-REFUSES workflow enrollment: the two customer-notification workflows (06-Podcast_Episode_Is_Ready and 04-Podcast is Completed) are the Interview lead-generation path only and are never triggered here. The enrollment layer enforces this refusal in code; a Personal-mode job that reaches enrollment must no-op the workflows and update the spreadsheet instead.

Silence boundary: zero customer messages of any kind, no SMS and no email, are sent from the engine on this path, and on this path there is nothing to send. The engine stops at the running-document update. Convert and Flow owns all messaging on every path; it is never bypassed, and it is never invoked to message a Personal Podcast listener.

Scheduling: if contact.date_for_release is present and in the future, use it as the Podbean publish timestamp so the episode is scheduled rather than published immediately.

### 8. What this mode does NOT change

The Style Engine mechanics, the canonical 18-step pipeline order, both QC gates and their thresholds, the Fish Audio tag syntax, the sizing table (7 to 15 minutes at 140 words per minute, 10 minutes the default), and the runtime model routing all stay exactly as defined elsewhere in the skill. Content work routes to the client's own runtime models per the routing policy (Ollama Cloud Kimi 2.6, then GLM 5.2, then the OpenRouter equivalents, then Gemini 3.1 Flash Lite). This mode is perspective and terminal boundary only.

### 9. Gate hooks (Episode Gate and Part A checklist)

    Tier 1 check 13 MODE PERSPECTIVE: first person throughout, no slippage.
    Tier 1 check 14 PRONOUN CORRECTNESS: matches contact.my_preferred_pronoun.
    Tier 1 check 12 NO FABRICATION: no invented first person biography.
    Part A: Production Mode identified as Personal Podcast Style; preferred pronoun captured and governing; transparency beat placed per the Style Engine; running spreadsheet updated with no workflows and no messages; engine stopped at the boundary with zero customer messages.

The Book Teaser block of the Part A checklist is skipped entirely in this mode and must not be reported as completed or as failed; it is simply not applicable.

### 10. Deliverables

Published episode (Podbean), cover art, Episode Package document, Speech Script document, and a new row in the running episode spreadsheet. No book teaser and no workflow enrollment.
