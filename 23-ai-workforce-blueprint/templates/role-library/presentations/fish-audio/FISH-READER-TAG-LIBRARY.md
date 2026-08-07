# FISH READER-TAG LIBRARY — S2 / S2.1-Pro EXPRESSIVE PRESENTER AUDIO

**Purpose:** The working reference the speech generator (`speech_fish_tag.py`) and the
audio executor (`synthesize_full_speech.py`) source their expressive tags from. This is a
**SOURCE, not a limit** — on Fish S2 / S2.1-Pro the tag system is open-domain: any
natural-language description inside `[square brackets]` is interpreted. If a tag isn't
landing, rephrase the free-form descriptor rather than assuming fixed-tag behavior.

- **Target engine:** Fish Audio **S2 / S2.1-Pro** (square brackets, open-domain).
- **Selection:** HTTP header `model: s2.1-pro` (already the harness default).
- **Placement:** emotion cue → **start** of the sentence it governs; tone / sound /
  dynamic cue → anywhere, scoped from the tag forward. Max **3** stacked cues per sentence.
- **Pauses:** `[pause]` / `[long pause]` are qualitative (docs give no seconds). For
  **exact 1–5 s dramatic pauses** the audio executor strips the tag and splices a
  measured silent mp3 (ffmpeg) at the concat stage — see the executor, not the API.
- **Verification status is marked** the way it is in `FISH-AUDIO-TAGS-MASTER.md`:
  VERIFIED = reproduced from an authoritative Fish source; COMPOSED = valid on S2 because
  it is open-domain, individual phrasing is our direction, not an official list.
- **Companion docs:** `FISH-AUDIO-TAGS-MASTER.md` (full verified tag catalog) and
  `FISH-AUDIO-STRATEGIC-PLAN.md` (persuasion playbook).

---

## 1. EXPRESSIVE REQUEST SHAPE (what the executor now sends)

`synth_chunk()` sends, per chunk, alongside `text` / `format` / `mp3_bitrate` /
`chunk_length` / `normalize` / `latency` / `reference_id` and the `model` header:

| Field | Value | Why |
|---|---|---|
| `temperature` | `0.9` (API default 0.7) | Fish docs literally say temperature *"controls expressiveness."* Higher = more varied. |
| `top_p` | `0.8` (API default 0.7) | Nucleus-sampling diversity. |
| `repetition_penalty` | `1.2` | >1.0 suppresses repeating audio patterns. |
| `prosody.speed` | `1.0` (0.5–2.0) | Global speaking-rate multiplier. |
| `prosody.volume` | `0` (≈ −20…+20 dB) | Global loudness. |
| `prosody.normalize_loudness` | `true` | S2-family loudness normalization. |

Field names verified against the Fish OpenAPI spec (`https://api.fish.audio/openapi.json`,
`TTSRequest` schema). The model is still the `model` HTTP header `s2.1-pro`.

---

## 2. QUICK-PICK VERIFIED SINGLE-PURPOSE TAGS

| Purpose | Tag | Verified |
|---|---|---|
| Stress one word | `[emphasis]` (place immediately before the word) | VERIFIED |
| Whisper | `[whispering]` / `[whisper]` | VERIFIED |
| Shout | `[shouting]` | VERIFIED |
| Scream | `[screaming]` | VERIFIED |
| Soft / gentle | `[soft voice]` / `[soft tone]` | VERIFIED |
| Deeper register | `[low voice]` | VERIFIED |
| Loud | `[loud voice]` | VERIFIED |
| Beat / let it land | `[pause]` / `[break]` | VERIFIED (qualitative) |
| Big silence | `[long pause]` / `[long-break]` | VERIFIED (qualitative) |
| Breath | `[inhale]` / `[exhale]` / `[sigh]` / `[breath]` | VERIFIED |
| Laugh | `[laughing]` + "Ha, ha, ha" | VERIFIED |
| Sigh | `[sighing]` + "sigh" | VERIFIED |
| Slower | `[speaking slowly, almost hesitant]` | COMPOSED (open-domain) |
| Faster | `[quickening pace]` / `[in a hurry tone]` | COMPOSED / VERIFIED |

## 3. EMOTION TAGS — BASIC (24) — VERIFIED

`[happy] [sad] [angry] [excited] [calm] [nervous] [confident] [surprised]
[satisfied] [delighted] [scared] [worried] [upset] [frustrated] [depressed]
[empathetic] [embarrassed] [disgusted] [moved] [proud] [relaxed] [grateful]
[curious] [sarcastic]`

## 4. EMOTION TAGS — ADVANCED (25) — VERIFIED

`[disdainful] [unhappy] [anxious] [hysterical] [indifferent] [uncertain] [doubtful]
[confused] [disappointed] [regretful] [guilty] [ashamed] [jealous] [envious] [hopeful]
[optimistic] [pessimistic] [nostalgic] [lonely] [bored] [contemptuous] [sympathetic]
[compassionate] [determined] [resigned]`

## 5. TONE MARKERS — VERIFIED

`[in a hurry tone]` (rushed) · `[shouting]` (loud) · `[screaming]` (very loud) ·
`[whispering]` (very soft) · `[soft tone]` (gentle) · `[emphasis]` (stress next word)

## 6. AUDIO / PARALANGUAGE EFFECTS — VERIFIED

`[laughing]` "Ha, ha, ha" · `[chuckling]` "Heh, heh" · `[sobbing]` · `[crying loudly]` ·
`sighing]` "sigh" · `[groaning]` "ugh" · `[panting]` "huff, puff" · `[gasping]` "gasp" ·
`[yawning]` "yawn" · `[snoring]` "zzz" · `[inhale]` · `[exhale]` · `[sigh]` ·
`[clears throat]` / `[clear throat]` · `[audience laughing]` · `[background laughter]` ·
`[crowd laughing]`

---

## 7. OPEN-DOMAIN DELIVERY DIRECTIONS — PER WEBINAR-ARC STAGE

These are **COMPOSED but valid** (S2 is open-domain — the exact phrasing is our direction,
the capability is verified). Use them as the primary palette in `speech_fish_tag.py` and
the speech-writer's copy. **Rotate within a stage so consecutive lines don't read flat.**

### 7.1 HOOK / OPEN — curiosity + "this is for me"
Target listener feeling: curiosity, instant relevance. Voice: confident, warm, intriguing.
Spend **one** deliberate pause on the hook line.

```
[confident] If you give me the next forty minutes, I'm going to show you something
that took me eleven years and a painful amount of money to figure out. [pause]
[warm and welcoming] And by the end, you'll know exactly whether this is for you.
```

Palette: `[confident]` · `[warm and welcoming]` · `[curious]` · `[mysterious]` ·
`[deliberate and measured]` · `[calm, grounded authority]` · `[smiling while speaking]`
Pacing: one `[pause]` after the promise. Don't stack excitement you haven't earned.

### 7.2 STORY — connection, low-to-high arc
Target feeling: "that's my situation." Voice: vulnerable → hopeful. Tag the **turns**, not
every line.

```
[reflective, looking back] Three years ago I was sitting in a parking lot at 11pm,
not wanting to go home and tell my family the launch had failed. [sighing] sigh.
[vulnerable, almost confessional] I'd put everything into it. And it just... didn't work.
[pause] [hopeful rising] But that night, something clicked.
```

Palette: `[reflective, looking back]` · `[vulnerable, almost confessional]` · `[nostalgic]` ·
`[wistful]` · `[hopeful rising]` · `[determined]` · `[a knowing smile]` · `[bittersweet]`
Connective tissue: `[pause]`, `[sighing] sigh`, `[inhale]`.

### 7.3 TEACH / VALUE — calm authority
Target feeling: "I'm learning, I trust them." **Lowest tag density.** Authority sounds
unhurried. One `[emphasis]` on the word that matters beats ten emotion tags.

```
[calm, clear] Here's the part most people get wrong. [pause] They optimize the funnel
before they have a single message that actually converts.
[helpful, generous] The order matters. Message first. [emphasis] Then traffic.
```

Palette: `[calm, clear]` · `[helpful, generous]` · `[measured and deliberate]` ·
`[enthusiastic]` · `[encouraging]` · `[matter-of-fact]`
Don't: `[excited]` teaching content — it reads as an infomercial.

### 7.4 PROOF — understated credibility
Target feeling: "this actually works." **Deliberately under-tag.** Restraint = credibility.
Quiet proof sounds true; loud proof sounds fake.

```
[confident and factual] Last quarter, one member went from zero to forty-one paying clients. [pause]
[understated, letting the numbers speak] Another did three hundred thousand in ninety days.
[proud but humble] These aren't outliers. This is what happens when the system is followed.
```

Palette: `[confident and factual]` · `[understated, letting the numbers speak]` ·
`[proud but humble]` · `[clinical precision]` · `[proud]` · `[satisfied]`

### 7.5 OFFER / PITCH — desire + certainty (energy peak)
Target feeling: "I want this." **Highest tag density** — this is where you spend the budget.
Ramp energy, then land on certainty so desire is anchored by trust.

```
[building excitement] So here's everything you get when you join today.
[excited] You get the full system — every template, every script, every funnel.
[confident] And you get the weekly coaching calls where we build it with you live.
[delighted] And the private community that honestly might be worth the whole thing on its own.
[confident] This is the exact system that produced the results I just showed you.
[sincere, warm] Nothing held back.
```

Palette: `[building excitement]` · `[excited]` · `[delighted]` · `[confident]` ·
`[barely contained enthusiasm]` · `[celebratory]` · `[upbeat and bright]`
Land: `[confident]` + `[sincere, warm]`.

### 7.6 SCARCITY / URGENCY — deadline, not threat
Target feeling: fear of missing out without sleaze. Urgency is carried by **pacing and a
serious tone**, not emotional volume.

```
[urgent but controlled] This enrollment closes Friday at midnight, and I'm not reopening it
until next quarter. [quickening pace] The bonuses come off the table at the same time.
[pause] [confident] I'm not going to chase you. [sincere, warm] But if you've been waiting
for the right moment — this is it.
```

Palette: `[urgent but controlled]` · `[serious, direct]` · `[quickening pace]` ·
`[in a hurry tone]` · `[time-pressure tone]` · `[clipped and direct]`
Don't: `[screaming]` / `[shouting]` scarcity — panic selling kills trust.

### 7.7 CLOSE / CTA — the price-drop & decision moment
Target feeling: the decision is safe and right. **Slow down. Lower the voice. Pause around
the price.** This is the most important pacing section. High-energy value → quiet, slow price.

```
[building excitement] So all of that — the system, the coaching, the community — if you bought
these separately, you're easily past twelve thousand dollars. [pause]
[calm, grounded authority] But you're not going to pay twelve thousand. [short pause]
[sincere, warm] [speaking slowly, almost hesitant] Today, to join us, it's [pause] nineteen ninety-seven. [pause]
[warm and welcoming] One payment. [reassuring] And you're in.
```

Palette: `[sincere, warm]` · `[confident, reassuring]` · `[calm, grounded authority]` ·
`[grateful]` · `[warm and welcoming]` · `[speaking slowly, almost hesitant]`
The price-drop mechanic: value stacked at high energy → `[pause]` → calm, slow, quiet number →
`[pause]` → `[reassuring]` close. **Land warm, never loud.**

---

## 8. PAUSE PLAYBOOK (EXACT SECONDS VIA THE EXECUTOR)

The Fish tags `[pause]` / `[long pause]` have **no documented duration**. The executor
(`synthesize_full_speech.py`) strips pause markers from the API text and splices a
measured silent mp3 at the concat stage. Defaults (override with `--pause-short`,
`--pause`, `--pause-long`):

| Tag | Default seconds | Use for |
|---|---|---|
| `[short pause]` | 0.8 | quick beat, mid-sentence rhythm, lists |
| `[pause]` / `[break]` / `[PAUSE]` | 1.2 | let a promise/reveal land, around the price |
| `[BREATHE]` | 1.2 | breath cue treated as a beat |
| `[long pause]` / `[long-break]` | 2.5 | major pivot, single biggest line |
| `(PAUSE N seconds)` | N | director-specified exact silence (parsed) |

Adjacent pause tags merge (e.g. `[pause][long pause]` → 3.7 s). `(OWNER: ...)` director
notes are dropped entirely — they are never spoken.

---

## 9. COMBINING AND PLACEMENT RULES

1. Emotion cue at the **start** of the sentence it governs.
2. Tone / sound / dynamic cue can sit **anywhere**; scope = from the tag forward.
3. Stack up to **3** cues per sentence max (`[sad][whispering] I miss you so much.`).
4. Add spoken text after a sound effect (`[laughing] Ha ha`, `[sighing] sigh`).
5. Keep free-form descriptors tight — a paragraph-long bracket hurts the model.
6. Intensity modifiers: prepend a degree (`[slightly sad]` `[very excited]` `[extremely angry]`).
7. If a tag isn't landing, **rephrase the free-form descriptor** (S2 open-domain) — don't
   assume fixed-tag behavior.
8. Verify before shipping: generate and listen. Tags are hypotheses; the rendered audio is
   the only ground truth.

---

## 10. VERIFICATION STATUS SUMMARY

| Category | Status |
|---|---|
| 24 basic + 25 advanced emotion tags | VERIFIED |
| Tone markers (`[shouting]`, `[whispering]`, `[emphasis]`, …) | VERIFIED |
| Audio effects + breaths | VERIFIED |
| Pause tags (`[pause]`, `[long pause]`, `[break]`, `[long-break]`) | VERIFIED (qualitative only) |
| Exact seconds for any pause tag | **UNVERIFIED** — executor splices measured silence |
| Stage delivery palettes (section 7) | COMPOSED (valid on S2 open-domain) |
| `temperature` / `top_p` / `repetition_penalty` / `prosody` request fields | VERIFIED against OpenAPI |
| `model: s2.1-pro` header | VERIFIED |

*End of reader-tag library. Companion: `FISH-AUDIO-TAGS-MASTER.md` (verified catalog),
`FISH-AUDIO-STRATEGIC-PLAN.md` (persuasion playbook).*
