# Interview Style Podcast, Mode Module (Skill 58, Podcast Production Engine) v1.0.0
## Mode id: interview_style_podcast. Default output-type preset: interview.

This module governs the narrative perspective and framing for the Interview Style production mode. A mode never changes the Style Engine mechanics (arc beats, word budgets, signature line, forbidden lists); it changes perspective, opening posture, transparency-beat voicing, and the terminal boundary. The four Style Engines (Counter Intuitive, Vulnerable, Provocative, Passionate) run identically inside this mode; only the point of view, the show frame, and the ending action differ from Personal Podcast Style.

Why this mode matters: the Interview Style path is, for the business, primarily a lead-generation engine built on the SHUA principle (Seen, Heard, Understood, Acknowledged). The finished episode is a gift engineered to make the guest feel all four, and the book teaser is the coup de grace of that experience. Precision failures on this path are business failures.

Selection: the Production Mode is carried on the intake payload and read at Step 1 (Ingest). The style selector is contact.podcast_survey_writing_style. Interview Style additionally requires two intake inputs that Personal mode does not: the show name and the host, plus the guest first name used for third-person attribution. Resolving this mode sets the default preset to interview unless the payload explicitly names a different output-type preset (see config/presets.json).

Writing rules binding on every episode this mode produces: zero em dash characters, no triple backtick fences or code-fence markers of any kind, no markdown or labels in the spoken script. These are enforced by qc-tier1-mechanical.py (Episode Gate, Tier 1 checks 1 through 4).

### 1. Definition

The show host (the show owner, for example the owner of a named morning show) invited an everyday person to be featured on the show, typically through an ad. The featured guest answered the survey questions. The episode is written from the HOST's perspective, in the host's voice, sharing what the host learned from interviewing this guest. The host is bringing the guest's ideas to the audience.

### 2. Narrative perspective

The host speaks in first person ("I"). The guest is spoken about in third person by name, for example "I just got a chance to sit down with the guest, and what she told me stopped me cold." The guest's ideas are presented as discoveries the host is now sharing. Core ideas are attributed to the guest by name throughout, using constructions like "she told me," "when I asked her about that, here is what she said," and "then he hit me with this." Every idea attributed to the guest must genuinely come from the guest's survey answers; putting words, claims, stories, or positions in the guest's mouth that the answers do not support is forbidden. This host-first, guest-third structure is enforced by Episode Gate Tier 1 check 13 (MODE PERSPECTIVE: Interview keeps host first person and guest third person by name with the epic guest introduction present, no slippage).

### 3. Opening posture: cold open, then show frame

Interview Style has a mandatory two-part open, in this order:

    Part one, the cold open. Open with a provocative, attention-snatching cold open built from the guest's Q1 answer, BEFORE any show housekeeping. The very first spoken sentence must be engineered to stop a scroll. Mark it with an opening delivery tag so the render sets the energy explicitly.
    Part two, the show frame. Only after the cold open, transition into the spoken show frame, for example "Welcome to another episode of {{show_name}} ...". The show intro is spoken and belongs in the script; these welcome lines are part of the deliverable in this mode. {{show_name}} is filled from the show-name intake input. Never emit the placeholder tokens themselves into the finished script.

This is the sharpest daily contrast with Personal Podcast Style, which carries no show frame and no welcome at all. (See modes/personal.md for the opposite rule.)

### 4. The epic guest introduction

After the provocative cold open and inside the show frame, name the guest as the source of today's insights and say something epic about the guest and their impact on making the world a better place. The audience must know who the main source of the talk is and must feel the host's genuine respect for them. Build this epic framing only from what the guest's answers and provided details actually support: elevate the truth, never invent credentials, accomplishments, titles, or a biography the guest did not give. The presence of this epic guest introduction is a scored element of Tier 1 check 13; an Interview-mode episode that never names and elevates the guest fails the mode-perspective check. Fabricated credentials are caught by Tier 1 check 12 (NO FABRICATION).

### 5. Transparency beat handling

The guest's transparency answer lives in contact.podcast_interview_smiq (the Single Most Important Question, or SMIQ: the answer to "Being Totally Transparent, what is the number 1 thing you are struggling with related to ____"). In this mode it becomes a powerful humanizing reveal delivered by the HOST with respect and empathy, for example "And here is the part that made me respect her even more. She was honest with me about what she is still working on." It is a structural requirement, not an option; removing it is forbidden, including during the Improvement Pass.

Division of ownership: the MODE owns the voice of the beat (the host reporting the guest's admission with respect, third person by name). The selected STYLE ENGINE owns the placement of the beat within the arc:

    Vulnerable: inside the breakdown and surrender beat.
    Passionate: immediately before the universal principle, so the principle reads as earned.
    Counter Intuitive and Provocative: at that engine's designated vulnerability beat position.

### 6. Host connective tissue and close

The host adds their own reactions, reflections, and takeaways; the host's commentary is the connective tissue of the episode. The Style Engine governs HOW the host builds the argument and the arc. Close with the host's synthesis and a direct call to action for the audience, consistent with the chosen Style Engine's closing mechanics. The episode must still feel like a presentation with a driving thesis, not a news report: the host is making a case and taking the audience on a journey, using the guest's material as the fuel.

### 7. Pronoun governance

contact.my_preferred_pronoun governs how the guest is referred to everywhere. Because the guest is referred to in third person throughout this mode, the pronoun is used constantly; every he, she, or they and every honorific must match the stated pronoun. Never guess a pronoun and never default to one; calling someone Mr. when they are Mrs., or he when they are she, is a serious error. Enforced by Episode Gate Tier 1 check 14 (PRONOUN CORRECTNESS).

### 8. Preset and terminal boundary

Default output-type preset: interview (config/presets.json). Book teaser: REQUIRED. The book teaser PDF is produced only for Interview Style participants, at Step 13, from the guest's answers, their improved answers, and the verified research, in the guest's own voice, ending on a cliffhanger. It is written on the client's runtime models (Kimi 2.6 or GLM 5.2 on Ollama Cloud, thinking high, then the same routing fallbacks) and rendered as a book-typeset PDF. Its link is written to contact.book_teaser when that field exists; if the field is absent it is surfaced as a founder reminder and never silently created, and its absence never fails the episode.

Terminal action at Step 17 (Trigger and Enroll), only after the episode is genuinely published to Podbean and the link-back field writes are complete: enroll the guest into BOTH customer-notification workflows, 06-Podcast_Episode_Is_Ready and 04-Podcast is Completed, using Skill 44. The exact workflow names and their trigger mechanism (tag-triggered, field-triggered, or direct add) are discovered per client at setup, never guessed. Note that 04-Podcast is Completed is field-triggered by contact.podcast_survey_episode_url changing, so writing that field may itself begin enrollment; verify whether it already triggered before enrolling explicitly, and guard against double enrollment. Enrollment is confirmed with caf verification reads. Enrolling before the episode exists is forbidden, because it would notify the guest about something that is not there.

Silence boundary: the engine's responsibility ends at enrollment. Convert and Flow owns all guest messaging; it sends any notification text at the scheduled time and runs the follow-up sequence. The engine sends no SMS, no email, and no follow-up messages directly. Enrollment is only for people who did the Interview Style podcast; Personal Podcast respondents are never enrolled into these workflows.

### 9. What this mode does NOT change

The Style Engine mechanics, the canonical 18-step pipeline order, both QC gates and their thresholds, the Fish Audio tag syntax, the sizing table (7 to 15 minutes at 140 words per minute, 10 minutes the default), and the runtime model routing all stay exactly as defined elsewhere in the skill. Content work routes to the client's own runtime models per the routing policy (Ollama Cloud Kimi 2.6, then GLM 5.2, then the OpenRouter equivalents, then Gemini 3.1 Flash Lite). This mode is perspective, show frame, and terminal boundary only.

### 10. Gate hooks (Episode Gate and Part A checklist)

    Tier 1 check 13 MODE PERSPECTIVE: host first person, guest third person by name, epic guest introduction present, no slippage.
    Tier 1 check 14 PRONOUN CORRECTNESS: matches contact.my_preferred_pronoun, used constantly.
    Tier 1 check 12 NO FABRICATION: no invented guest credentials, accomplishments, or biography.
    Part A: Production Mode identified as Interview Style; show name and host present; guest name present; preferred pronoun captured and governing; transparency beat placed per the Style Engine; teaser written and its link written to book_teaser or the founder reminder surfaced; enrollment into both workflows verified after publish and field writes only, double-enrollment guarded; engine stopped at the boundary with zero customer messages.

### 11. Deliverables

Published episode (Podbean), cover art, Episode Package document, Speech Script document, book teaser PDF, and confirmed enrollment into both customer-notification workflows.
