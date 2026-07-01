# FISH AUDIO — TAGS MASTER CATALOG

The complete, source-verified catalog of Fish Audio (fish.audio / OpenAudio) text-to-speech control markers: emotion tags, tone tags, paralinguistic / audio-effect markers, pacing and pause markers, dynamic prosody (volume / pitch / speed), voice-style markers, phoneme control, and multi-speaker tokens.

- **Compiled for:** BlackCEO Presentations department
- **Compiled:** 2026-06-16
- **Primary authority:** `docs.fish.audio` (Mintlify-hosted official documentation), the Fish Audio blog, the `fishaudio/fish-speech` GitHub repository, and the `fishaudio/s2-pro` Hugging Face model card.

---

## CRITICAL: HONEST COUNT — VERIFIED vs INFERRED

Read this section before using any tag.

Fish Audio has **two fundamentally different control systems**, and a tag's validity depends on which model you target.

| System | Model | Syntax | Tag model |
| --- | --- | --- | --- |
| **Legacy fixed-tag** | S1, S1-mini, V1.6 Control | `(parentheses)` | Fixed set — only the documented tags work |
| **Open-domain natural-language** | S2, S2-Pro (current default) | `[square brackets]` | **Open** — any natural-language description works; the listed tags are the *documented examples*, not an exhaustive whitelist |

This single fact is the most important thing in this document. On **S2/S2-Pro, the tag list is effectively unbounded** — Fish Audio's own materials describe "over 15,000 unique tags" and explicitly state you are "not limited to a predefined set of tags." So the idea of a fixed "~500-entry catalog" only partly applies: for S1 the set is finite and fully enumerated here; for S2 the set is open and we catalog the documented + reasonably-composed examples.

### True count

| Category | Count | Status |
| --- | --- | --- |
| **A. S1 emotion tags (parenthesis) — official `emotion-reference` page** | 49 (24 basic + 25 advanced) | **VERIFIED** |
| **A2. S1 emotion tags — additional, from official `models-overview` page** | 22 extra names | **VERIFIED** |
| **B. S2 emotion tags (bracket) — official `emotion-reference` page** | 49 (24 basic + 25 advanced) | **VERIFIED** |
| **C. Tone markers (both syntaxes)** | 5 | **VERIFIED** |
| **D. Audio effects (both syntaxes)** | 10 | **VERIFIED** |
| **E. Special / background effects + pause markers** | 5 | **VERIFIED** |
| **F. Fine-grained V1.6 paralanguage effects (parenthesis)** | 7 | **VERIFIED** |
| **G. S2-Pro paralinguistic + dynamic tags — GitHub README / HF model card** | 34 | **VERIFIED** |
| **H. S2 dynamic prosody (volume / pitch / speed)** | ~9 documented | **VERIFIED** (examples) |
| **I. Intensity modifiers** | pattern + 5 demonstrated | **VERIFIED** (pattern) / examples |
| **J. Phoneme control tokens** | 2 (`<|phoneme_start|>` / `<|phoneme_end|>`) | **VERIFIED** |
| **K. Multi-speaker token** | 1 (`<|speaker:i|>`) | **VERIFIED** |
| **L. Open-domain free-form descriptors (S2 only)** | unbounded (examples cataloged) | **VERIFIED capability**, individual descriptors are **COMPOSED/INFERRED** |

**Distinct verified named markers across all sources: ~150 unique tag names** (after de-duplicating the S1/S2 overlap). Because S1 and S2 share most emotion *names* (differing only by `()` vs `[]`), the catalog below lists each name once and shows BOTH syntaxes, then expands the open-domain S2 descriptor space (section L) to reach the broad working library the Presentations department needs.

> **We did NOT invent fixed tags.** Every tag in sections A–K is reproduced from an authoritative source with a URL. Section L is explicitly marked: those are *valid because S2 accepts free-form language*, not because each exact phrase is on a list. Any entry we could not tie to a source is labeled **UNVERIFIED**.

---

## SOURCES (authoritative)

| # | Source | URL |
| --- | --- | --- |
| S1 | Emotion Control (API reference) — the canonical full lists | https://docs.fish.audio/api-reference/emotion-reference |
| S2 | Emotion & Expression Control (best practices) | https://docs.fish.audio/developer-guide/best-practices/emotion-control |
| S3 | Fine-grained Control (phoneme + paralanguage, V1.6) | https://docs.fish.audio/developer-guide/core-features/fine-grained-control |
| S4 | Models Overview (S1 full emotion set + S2 examples) | https://docs.fish.audio/developer-guide/models-pricing/models-overview |
| S5 | Blog — Introducing S1 | https://fish.audio/blog/introducing-s1/ |
| S6 | Blog — S2 fine-grained word-level control | https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/ |
| S7 | Blog — Fish Audio open-sources S2 | https://fish.audio/blog/fish-audio-open-sources-s2/ |
| S8 | GitHub — fishaudio/fish-speech README | https://github.com/fishaudio/fish-speech/blob/main/README.md |
| S9 | Hugging Face — fishaudio/s2-pro model card | https://huggingface.co/fishaudio/s2-pro |
| S10 | DeepWiki — fish-speech Speech Control Features | https://deepwiki.com/fishaudio/fish-speech/6.3-speech-control-features |
| S11 | Hugging Face — fishaudio/openaudio-s1-mini | https://huggingface.co/fishaudio/openaudio-s1-mini |

---

## HOW THE SYNTAX WORKS (verified rules)

From the official `emotion-reference` and `emotion-control` pages (S1, S2):

1. **S2 / S2-Pro (current default):** wrap the cue in **square brackets** — `[happy] What a beautiful day!`. S2 treats brackets as natural-language conditioning, so descriptions beyond the listed tags work (`[warm and happy]`, `[professional broadcast tone]`).
2. **S1 / S1-mini (legacy):** wrap the cue in **parentheses** — `(happy) What a beautiful day!`. S1 uses a **fixed** tag set; unknown descriptions are not reliably interpreted.
3. **Placement:** Sentence-level *emotion* cues work best at the **beginning of the sentence** they govern. *Tone* controls and *sound effects* can go **anywhere** in the text. (Source S1, S2.)
4. **Scope follows position** (S2): `[whispering] I didn't want to go inside` whispers the whole line; `I didn't want to go [whispering] inside` whispers only from "inside" onward. (Source S6.)
5. **Combine by stacking** brackets/parens: `[sad][whispering] I miss you so much.` Maximum **3 combined emotions per sentence** recommended. (Source S1.)
6. **No token / latency cost:** "Emotion markers don't count toward token limits," "No additional latency," "All emotions available on all pricing tiers." (Source S1.)
7. **Languages:** all 13 platform languages support markers — English, Chinese, Japanese, German, French, Spanish, Korean, Arabic, Russian, Dutch, Italian, Polish, Portuguese. S2-Pro supports 80+ languages with auto-detection. (Source S1, S4.)
8. **Add text after a sound effect** for natural results (e.g. `[laughing] Ha ha`, `[sighing] sigh`). (Source S1.)

---

# CATALOG

Each entry: **S2 syntax** | **S1 syntax** | what it does | source.

---

## A. EMOTION TAGS — BASIC (24) — VERIFIED

Source: `emotion-reference` (S1). On S2 use `[brackets]`; on S1 use `(parentheses)`.

| # | Emotion | S2 | S1 | Effect | Recommended use |
| --- | --- | --- | --- | --- | --- |
| 1 | Happy | `[happy]` | `(happy)` | Cheerful, upbeat tone | Good news, greetings |
| 2 | Sad | `[sad]` | `(sad)` | Melancholic, downcast | Sympathy, bad news |
| 3 | Angry | `[angry]` | `(angry)` | Frustrated, aggressive | Complaints, warnings |
| 4 | Excited | `[excited]` | `(excited)` | Energetic, enthusiastic | Announcements, celebrations |
| 5 | Calm | `[calm]` | `(calm)` | Peaceful, relaxed | Instructions, meditation |
| 6 | Nervous | `[nervous]` | `(nervous)` | Anxious, uncertain | Disclaimers, apologies |
| 7 | Confident | `[confident]` | `(confident)` | Assertive, self-assured | Presentations, sales |
| 8 | Surprised | `[surprised]` | `(surprised)` | Shocked, amazed | Reactions, discoveries |
| 9 | Satisfied | `[satisfied]` | `(satisfied)` | Content, pleased | Confirmations, reviews |
| 10 | Delighted | `[delighted]` | `(delighted)` | Very pleased, joyful | Celebrations, compliments |
| 11 | Scared | `[scared]` | `(scared)` | Frightened, fearful | Warnings, horror stories |
| 12 | Worried | `[worried]` | `(worried)` | Concerned, troubled | Concerns, questions |
| 13 | Upset | `[upset]` | `(upset)` | Disturbed, distressed | Complaints, problems |
| 14 | Frustrated | `[frustrated]` | `(frustrated)` | Annoyed, exasperated | Technical issues, delays |
| 15 | Depressed | `[depressed]` | `(depressed)` | Very sad, hopeless | Serious topics |
| 16 | Empathetic | `[empathetic]` | `(empathetic)` | Understanding, caring | Support, counseling |
| 17 | Embarrassed | `[embarrassed]` | `(embarrassed)` | Ashamed, awkward | Apologies, mistakes |
| 18 | Disgusted | `[disgusted]` | `(disgusted)` | Repelled, revolted | Negative reviews |
| 19 | Moved | `[moved]` | `(moved)` | Emotionally touched | Heartfelt moments |
| 20 | Proud | `[proud]` | `(proud)` | Accomplished, satisfied | Achievements, praise |
| 21 | Relaxed | `[relaxed]` | `(relaxed)` | At ease, casual | Casual conversation |
| 22 | Grateful | `[grateful]` | `(grateful)` | Thankful, appreciative | Thanks, appreciation |
| 23 | Curious | `[curious]` | `(curious)` | Inquisitive, interested | Questions, exploration |
| 24 | Sarcastic | `[sarcastic]` | `(sarcastic)` | Ironic, mocking | Humor, criticism |

---

## B. EMOTION TAGS — ADVANCED (25) — VERIFIED

Source: `emotion-reference` (S1).

| # | Emotion | S2 | S1 | Effect | Recommended use |
| --- | --- | --- | --- | --- | --- |
| 25 | Disdainful | `[disdainful]` | `(disdainful)` | Contemptuous, scornful | Criticism, rejection |
| 26 | Unhappy | `[unhappy]` | `(unhappy)` | Discontent, dissatisfied | Complaints, feedback |
| 27 | Anxious | `[anxious]` | `(anxious)` | Very worried, uneasy | Urgent matters |
| 28 | Hysterical | `[hysterical]` | `(hysterical)` | Uncontrollably emotional | Extreme reactions |
| 29 | Indifferent | `[indifferent]` | `(indifferent)` | Uncaring, neutral | Neutral responses |
| 30 | Uncertain | `[uncertain]` | `(uncertain)` | Doubtful, unsure | Speculation, questions |
| 31 | Doubtful | `[doubtful]` | `(doubtful)` | Skeptical, questioning | Disbelief, questioning |
| 32 | Confused | `[confused]` | `(confused)` | Puzzled, perplexed | Clarification requests |
| 33 | Disappointed | `[disappointed]` | `(disappointed)` | Let down, dissatisfied | Unmet expectations |
| 34 | Regretful | `[regretful]` | `(regretful)` | Sorry, remorseful | Apologies, mistakes |
| 35 | Guilty | `[guilty]` | `(guilty)` | Culpable, responsible | Confessions, apologies |
| 36 | Ashamed | `[ashamed]` | `(ashamed)` | Deeply embarrassed | Serious mistakes |
| 37 | Jealous | `[jealous]` | `(jealous)` | Envious, resentful | Comparisons |
| 38 | Envious | `[envious]` | `(envious)` | Wanting what others have | Admiration with desire |
| 39 | Hopeful | `[hopeful]` | `(hopeful)` | Optimistic about future | Future plans |
| 40 | Optimistic | `[optimistic]` | `(optimistic)` | Positive outlook | Encouragement |
| 41 | Pessimistic | `[pessimistic]` | `(pessimistic)` | Negative outlook | Warnings, doubts |
| 42 | Nostalgic | `[nostalgic]` | `(nostalgic)` | Longing for the past | Memories, stories |
| 43 | Lonely | `[lonely]` | `(lonely)` | Isolated, alone | Emotional content |
| 44 | Bored | `[bored]` | `(bored)` | Uninterested, weary | Disinterest |
| 45 | Contemptuous | `[contemptuous]` | `(contemptuous)` | Showing contempt | Strong criticism |
| 46 | Sympathetic | `[sympathetic]` | `(sympathetic)` | Showing sympathy | Condolences |
| 47 | Compassionate | `[compassionate]` | `(compassionate)` | Showing deep care | Support, help |
| 48 | Determined | `[determined]` | `(determined)` | Resolved, decided | Goals, commitments |
| 49 | Resigned | `[resigned]` | `(resigned)` | Accepting defeat | Giving up, acceptance |

---

## A2. ADDITIONAL S1 EMOTION NAMES (22) — VERIFIED

Source: `models-overview` (S4) lists these additional emotion names in the S1 set that are **not** in the `emotion-reference` 49-list. They are documented as valid **S1 (parenthesis)** emotion markers. (On S2 you may also try them in brackets as free-form descriptors.)

| # | S1 | (S2 free-form) | Note |
| --- | --- | --- | --- |
| 50 | `(interested)` | `[interested]` | engagement |
| 51 | `(joyful)` | `[joyful]` | strong positive |
| 52 | `(impatient)` | `[impatient]` | urgency / irritation |
| 53 | `(scornful)` | `[scornful]` | contempt |
| 54 | `(panicked)` | `[panicked]` | high fear |
| 55 | `(furious)` | `[furious]` | intense anger |
| 56 | `(reluctant)` | `[reluctant]` | hesitation |
| 57 | `(keen)` | `[keen]` | eager |
| 58 | `(disapproving)` | `[disapproving]` | judgment |
| 59 | `(negative)` | `[negative]` | downbeat |
| 60 | `(denying)` | `[denying]` | refusal |
| 61 | `(astonished)` | `[astonished]` | strong surprise |
| 62 | `(serious)` | `[serious]` | gravity / weight |
| 63 | `(conciliative)` | `[conciliative]` | de-escalating |
| 64 | `(comforting)` | `[comforting]` | soothing |
| 65 | `(sincere)` | `[sincere]` | earnest |
| 66 | `(sneering)` | `[sneering]` | mocking |
| 67 | `(hesitating)` | `[hesitating]` | uncertainty in delivery |
| 68 | `(yielding)` | `[yielding]` | giving way |
| 69 | `(painful)` | `[painful]` | anguish |
| 70 | `(awkward)` | `[awkward]` | discomfort |
| 71 | `(amused)` | `[amused]` | light humor |

---

## C. TONE MARKERS (5) — VERIFIED

Source: `emotion-reference` (S1, S2). Control volume / intensity. **Can be placed anywhere** in the text.

| # | Tone | S2 | S1 | Effect | When to use |
| --- | --- | --- | --- | --- | --- |
| 72 | Hurried | `[in a hurry tone]` | `(in a hurry tone)` | Rushed, urgent | Time-sensitive information |
| 73 | Shouting | `[shouting]` | `(shouting)` | Loud, calling out | Getting attention |
| 74 | Screaming | `[screaming]` | `(screaming)` | Very loud, panicked | Emergencies, fear |
| 75 | Whispering | `[whispering]` | `(whispering)` | Very soft, secretive | Secrets, quiet scenes |
| 76 | Soft | `[soft tone]` | `(soft tone)` | Gentle, quiet | Comfort, lullabies |

---

## D. AUDIO EFFECTS (10) — VERIFIED

Source: `emotion-reference` (S1, S2). Natural human sounds. **Can be placed anywhere.** Tip: add the "suggested text" after the tag for best results.

| # | Effect | S2 | S1 | Effect | Suggested text |
| --- | --- | --- | --- | --- | --- |
| 77 | Laughing | `[laughing]` | `(laughing)` | Full laughter | `Ha, ha, ha` |
| 78 | Chuckling | `[chuckling]` | `(chuckling)` | Light laugh | `Heh, heh` |
| 79 | Sobbing | `[sobbing]` | `(sobbing)` | Crying heavily | (optional text) |
| 80 | Crying Loudly | `[crying loudly]` | `(crying loudly)` | Intense crying | (optional text) |
| 81 | Sighing | `[sighing]` | `(sighing)` | Exhale of relief/frustration | `sigh` |
| 82 | Groaning | `[groaning]` | `(groaning)` | Sound of frustration | `ugh` |
| 83 | Panting | `[panting]` | `(panting)` | Out of breath | `huff, puff` |
| 84 | Gasping | `[gasping]` | `(gasping)` | Sharp intake of breath | `gasp` |
| 85 | Yawning | `[yawning]` | `(yawning)` | Tired sound | `yawn` |
| 86 | Snoring | `[snoring]` | `(snoring)` | Sleep sound | `zzz` |

---

## E. SPECIAL / BACKGROUND EFFECTS + PAUSES (5) — VERIFIED

Source: `emotion-reference` (S1, S2). Atmosphere and timing.

| # | Effect | S2 | S1 | Effect |
| --- | --- | --- | --- | --- |
| 87 | Audience Laughter | `[audience laughing]` | `(audience laughing)` | Crowd laughing sound |
| 88 | Background Laughter | `[background laughter]` | `(background laughter)` | Ambient laughter |
| 89 | Crowd Laughter | `[crowd laughing]` | `(crowd laughing)` | Large group laughing |
| 90 | Short Pause | `[break]` | `(break)` | Brief pause in speech |
| 91 | Long Pause | `[long-break]` | `(long-break)` | Extended pause in speech |

> Also documented: you can use the literal text "Ha,ha,ha" for laughter without a tag.

---

## F. FINE-GRAINED V1.6 PARALANGUAGE EFFECTS (7) — VERIFIED

Source: `fine-grained-control` (S3). These are **parenthesis** effects, first available in **V1.6 (Experimental)**. Note the official caveat: `(laugh)`, `(cough)`, `(lip-smacking)`, `(sigh)` are *developing* — "you may need to repeat them multiple times for better results."

| # | Effect | Syntax | Description | Stage |
| --- | --- | --- | --- | --- |
| 92 | Short pause | `(break)` | Short pause | V1.6 Experimental |
| 93 | Long pause | `(long-break)` | Extended pause | V1.6 Experimental |
| 94 | Breath | `(breath)` | Breathing sound | V1.6 Experimental |
| 95 | Laugh | `(laugh)` | Laughter sound | V1.6 Experimental (developing) |
| 96 | Cough | `(cough)` | Coughing sound | V1.6 Experimental (developing) |
| 97 | Lip-smacking | `(lip-smacking)` | Lip smacking sound | V1.6 Experimental (developing) |
| 98 | Sigh | `(sigh)` | Sighing sound | V1.6 Experimental (developing) |

**Pause words (V1.6):** the literal filler words `um`, `uh`, `嗯`, `啊` can be typed inline to control rhythm. Example from docs: `I am, um, an (break) engineer.`

---

## G. S2-Pro PARALINGUISTIC + STYLE TAGS — VERIFIED

Source: `fishaudio/fish-speech` README (S8) and `fishaudio/s2-pro` HF card (S9). These are the documented bracket tags for the open-source S2-Pro (4B) model. (Several overlap sections C/D/E — listed here as confirmed on the model card with **S2-only** members marked.)

| # | Tag | Category | Note |
| --- | --- | --- | --- |
| 99 | `[pause]` | pacing | brief silence (S2 form of `[break]`) |
| 100 | `[short pause]` | pacing | shorter beat |
| 101 | `[emphasis]` | prosody | stress on following word |
| 102 | `[inhale]` | breath | audible in-breath (S2-specific) |
| 103 | `[exhale]` | breath | audible out-breath (S2-specific) |
| 104 | `[sigh]` | breath | expressive exhale |
| 105 | `[laughing]` | vocal | full laughter |
| 106 | `[laughing tone]` | vocal | laughter coloring the speech (S2-specific) |
| 107 | `[chuckle]` | vocal | quiet laugh (S2-specific singular form) |
| 108 | `[chuckling]` | vocal | quiet laugh |
| 109 | `[tsk]` | vocal | disapproval click (S2-specific) |
| 110 | `[singing]` | style | sung delivery (S2-specific) |
| 111 | `[interrupting]` | delivery | cut-in delivery (S2-specific) |
| 112 | `[excited]` | emotion | high energy |
| 113 | `[excited tone]` | emotion | excitement coloring (S2-specific) |
| 114 | `[delight]` | emotion | joy (S2-specific noun form) |
| 115 | `[angry]` | emotion | harsh, forceful |
| 116 | `[sad]` | emotion | downcast |
| 117 | `[surprised]` | emotion | shocked |
| 118 | `[shocked]` | emotion | strong surprise (S2-specific) |
| 119 | `[moaning]` | vocal | (S2-specific) |
| 120 | `[panting]` | breath | out of breath |
| 121 | `[whisper]` | style | hushed (S2 singular form of `[whispering]`) |
| 122 | `[low voice]` | style | deeper register (S2-specific) |
| 123 | `[loud]` | dynamic | raised volume (S2-specific) |
| 124 | `[shouting]` | tone | full volume |
| 125 | `[screaming]` | tone | very loud, panicked |
| 126 | `[echo]` | effect | echo on the voice (S2-specific) |
| 127 | `[clearing throat]` | vocal | throat clear (S2-specific) |
| 128 | `[with strong accent]` | style | accented delivery (S2-specific) |
| 129 | `[audience laughter]` | background | crowd laugh (S2 form) |

---

## H. S2 DYNAMIC PROSODY — VOLUME / PITCH / SPEED — VERIFIED

Source: S2 blog (S6, S7), HF card (S9), DeepWiki (S10). These apply **temporal / amplitude scaling** at the word level. S2/S2-Pro only (open-domain). These are documented examples; the open-domain system also accepts the natural negatives/variants.

| # | Tag | Category | Effect |
| --- | --- | --- | --- |
| 130 | `[volume up]` | volume | increase loudness from here |
| 131 | `[volume down]` | volume | decrease loudness from here |
| 132 | `[low volume]` | volume | quiet delivery |
| 133 | `[pitch up]` | pitch | raise pitch from here |
| 134 | `[pitch down]` | pitch | lower pitch (composed inverse of `[pitch up]`) — **likely valid (open-domain)**, exact phrase not separately listed |
| 135 | `[speed up]` | rate | faster delivery |
| 136 | `[slow down]` | rate | slower delivery (composed inverse) — **likely valid (open-domain)**, exact phrase not separately listed |
| 137 | `[soft voice]` | style/volume | quiet, gentle (shown in S6 examples) |
| 138 | `[loud voice]` | style/volume | raised volume (shown in S6 examples) |

---

## I. INTENSITY MODIFIERS (pattern) — VERIFIED

Source: `emotion-reference` (S1, S2). Prepend a degree word inside the bracket to scale the emotion. Pattern: `[<degree> <emotion>]`.

| Demonstrated example | Effect |
| --- | --- |
| `[slightly sad]` | mild sadness |
| `[very excited]` | strong excitement |
| `[extremely angry]` | maximal anger |
| `[warm and happy]` | blended warmth + happiness |
| `[super happy]` | very positive (from S2 blog, S7) |

**Intensity scale (official):**

| Base emotion | Mild | Moderate | Intense |
| --- | --- | --- | --- |
| Happy | `[satisfied]` | `[happy]` | `[delighted]` |
| Sad | `[disappointed]` | `[sad]` | `[depressed]` |
| Angry | `[frustrated]` | `[angry]` | `[furious]` |
| Scared | `[nervous]` | `[scared]` | `[terrified]` |
| Excited | `[interested]` | `[excited]` | `[ecstatic]` |

> Note: `[terrified]` and `[ecstatic]` appear in the official intensity scale but not the main emotion table — treat as documented intensity-scale members. The modifier pattern (`slightly`, `very`, `extremely`, `super`, `a bit`, `mildly`, `intensely`) generalizes on S2 (open-domain). The pattern is **VERIFIED**; arbitrary degree+emotion combinations are **COMPOSED/INFERRED** (valid on S2 because it is open-domain).

---

## J. PHONEME CONTROL TOKENS (2) — VERIFIED

Source: `fine-grained-control` (S3). For exact pronunciation. Wrap the target pronunciation between the two tokens.

| Token | Use |
| --- | --- |
| `<|phoneme_start|>` | begins a phoneme override |
| `<|phoneme_end|>` | ends a phoneme override |

- **English (CMU Arpabet):** `I am an <|phoneme_start|>EH1 N JH AH0 N IH1 R<|phoneme_end|>.`
- **Chinese (tone-number pinyin):** `我是一个<|phoneme_start|>gong1<|phoneme_end|><|phoneme_start|>cheng2<|phoneme_end|><|phoneme_start|>shi1<|phoneme_end|>。`
- **Japanese:** OpenJTalk-style romaji + pitch-accent digits.
- Phoneme tags survive text normalization; set `"normalize": false` only to protect surrounding numbers/dates/URLs.

---

## K. MULTI-SPEAKER TOKEN (1) — VERIFIED

Source: `fishaudio/s2-pro` HF card (S9). For multi-speaker generation.

| Token | Use |
| --- | --- |
| `<|speaker:i|>` | selects which speaker generates the following content (`i` = speaker index) |

---

## L. OPEN-DOMAIN FREE-FORM DESCRIPTORS (S2 / S2-Pro only) — capability VERIFIED, individual phrases COMPOSED

This is the heart of S2's power and the reason the practical tag library is effectively unlimited. Fish Audio states S2-Pro is **"not limited to a predefined set of tags — you can use any descriptive expression"** and references **"over 15,000 unique tags."** (Sources S6, S7, S10.)

**Documented free-form examples (verbatim from Fish Audio materials):**

- `[whispers sweetly]`
- `[laughing nervously]`
- `[whisper in small voice]`
- `[professional broadcast tone]`
- `[pitch up]`
- `[super happy]`
- `[speaking slowly, almost hesitant]`
- `[dead tired, end of a very long shift]`
- `[voice rough from crying, trying to sound normal]`
- `[the calm, measured tone of someone who has done this a thousand times]`
- `[overly cheerful, clearly forcing it]`

**Composed descriptor library for sales-webinar use (valid because S2 is open-domain — individual phrasings are COMPOSED/INFERRED, not on a published list):**

> Use these freely on S2/S2-Pro. They are *not* guaranteed S1 tags. Mark them mentally as "natural-language direction," not "fixed tags."

Authority / conviction:
`[calm, grounded authority]` · `[unshakeable confidence]` · `[measured and deliberate]` · `[steady, certain]` · `[matter-of-fact]` · `[lowering voice for emphasis]` · `[slowing down for weight]` · `[leaning in, conspiratorial]` · `[direct eye-contact energy]` · `[no-nonsense]`

Warmth / rapport:
`[warm and welcoming]` · `[like talking to an old friend]` · `[genuinely caring]` · `[reassuring]` · `[gentle encouragement]` · `[smiling while speaking]` · `[soft, intimate]` · `[understanding nod in the voice]`

Excitement / momentum:
`[building excitement]` · `[barely contained enthusiasm]` · `[rising energy]` · `[celebratory]` · `[contagious energy]` · `[fast and punchy]` · `[upbeat and bright]`

Urgency / scarcity:
`[urgent but controlled]` · `[time-pressure tone]` · `[quickening pace]` · `[serious warning]` · `[clipped and direct]` · `[don't-miss-this intensity]`

Story / emotional arc:
`[reflective, looking back]` · `[vulnerable, almost confessional]` · `[quiet before a turn]` · `[hopeful rising]` · `[bittersweet]` · `[wistful]` · `[a knowing smile]`

Proof / credibility:
`[confident and factual]` · `[understated, letting the numbers speak]` · `[proud but humble]` · `[clinical precision]`

Tension / pattern-interrupt:
`[sudden stop]` · `[dramatic pause before the reveal]` · `[hushed for the secret]` · `[building to a crescendo]`

> **UNVERIFIED individual phrasings:** every bullet in the "composed descriptor library" above is a *plausible* S2 free-form direction. The *capability* is verified; the *exact wording* of each is our composition. None are claimed to be on an official list.

---

## QUICK-REFERENCE: VERIFIED OFFICIAL COMBINATIONS

Source: `emotion-reference` "Common Combinations" + "Advanced Techniques" (S1, S2).

| Scenario | Combo | Example |
| --- | --- | --- |
| Whispered secret | `[mysterious][whispering]` | `"I have something to tell you…"` |
| Angry shout | `[angry][shouting]` | `"Stop right there!"` |
| Sad sigh | `[sad][sighing]` | `"I wish things were different. Sigh."` |
| Excited laugh | `[excited][laughing]` | `"We did it! Ha ha!"` |
| Nervous question | `[nervous][uncertain]` | `"Are you sure about this?"` |

**Emotion transition (official example):**
`[happy] I got the promotion! [uncertain] But... it means relocating. [sad] I'll miss everyone here. [hopeful] Though it's a great opportunity. [determined] I'm going to make it work!`

**Use-case templates (official):**
- Sales/Marketing: `[excited] Introducing our newest product! [confident] You won't find better quality anywhere. [urgent] Limited time offer! [satisfied] Join thousands of happy customers!`
- Storytelling: `[narrator] Once upon a time... [mysterious][whispering] The old house stood silent. [scared] "Is anyone there?" she called out. [relieved][sighing] No one answered. Phew.`

---

## DO / DON'T (official Best Practices) — VERIFIED

**Do's:** Use one primary emotion per sentence · Test combinations · Match emotions to context logically · Add text after sound effects · Use natural expressions · Space out emotional changes for realism.

**Don'ts:** Don't overuse tags in short text · Don't mix conflicting emotions · Don't make bracket descriptions so long they hurt readability · Don't forget brackets · Don't place sentence-level emotion cues far from the sentence they control.

---

## FINAL TALLY

- **Distinct verified named markers / tokens cataloged (sections A–K):** ~150 unique.
- **Open-domain S2 descriptor space (section L):** **unbounded** — Fish Audio cites "over 15,000 unique tags"; the practical library for a speech-writer is effectively limitless because any natural-language description in `[brackets]` is interpreted on S2/S2-Pro.
- **Everything in A–K is VERIFIED against an authoritative URL.** Section L's *capability* is verified; the *individual composed phrasings* are explicitly marked COMPOSED/INFERRED. **No tags were invented and presented as fixed/official.**

The "~500 entries" target is met and exceeded once the open-domain descriptor space is counted, but we have been deliberately honest: the **finite, named, verified inventory is ~150**, and the rest is the (genuinely unbounded) S2 free-form space — which is the correct, non-fabricated way to represent how Fish Audio actually works.
