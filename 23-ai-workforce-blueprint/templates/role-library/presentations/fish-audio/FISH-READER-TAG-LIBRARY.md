# FISH READER-TAG LIBRARY — S2 / S2.1-PRO EXPRESSIVE PRESENTER AUDIO (RICH TAXONOMY v2)

**Purpose:** The working reference the speech generator (`speech_fish_tag.py`) and the
audio executor (`synthesize_full_speech.py`) source their expressive tags from. This v2
replaces the flat "basic/advanced" catalog with a **rich grouped taxonomy** — Emotion
(basic / advanced / intensity / blended-instructional), Pacing, Energy, Delivery/Tone,
Direction/Instructional, Pauses, Dynamic Prosody, and Phoneme — so the palettes in the
pipeline can rotate real variety instead of repeating the same handful of tags.

This is a **SOURCE, not a limit.** On Fish S2 / S2.1-Pro the tag system is **open-domain**:
any natural-language description inside `[square brackets]` is interpreted as a delivery
instruction. If a tag isn't landing, rephrase the free-form descriptor rather than assuming
fixed-tag behavior. Exact phrasing is our composition to direct; the *capability* is verified.

## STATUS LEGEND — every tag below is marked

| Mark | Meaning |
|---|---|
| `·V` **VERIFIED** | Reproduced from an authoritative Fish source (docs / blog / model card / GitHub README). |
| `·C` **COMPOSED** | Valid on S2 because the system is open-domain; the phrasing is our direction, not an official list. |
| `·U` **UNVERIFIED** | No source located; test by ear on the target voice before shipping. |

Tags marked VERIFIED are behavioral facts. Tags marked COMPOSED are our directions — they
will *usually* work on S2 but must be spot-checked per voice, because tag adherence is model
behavior ("different voices respond to the same tag with different intensity").

## BASELINE FACTS (VERIFIED)

- **Target engine:** Fish Audio **S2 / S2.1-Pro** — `[square brackets]`, open-domain natural
  language. (S1 uses fixed `(parenthesis)` tags and is NOT the production target.)
- **Model selection:** HTTP **header** `model: s2.1-pro` (not a JSON body field; the raw API
  defaults to s2.1-pro, the Python SDK defaults to s2-pro — always set the header).
- **Placement:** emotion cue → **start** of the sentence it governs; tone / sound / dynamic
  cue → anywhere, scoped from the tag forward. Max **3** stacked cues per sentence.
- **Pauses:** `[pause]` / `[long pause]` are **qualitative only** (docs give no seconds). For
  exact 1–5 s dramatic pauses the audio executor strips the tag and splices a measured silent
  mp3 (ffmpeg) at the concat stage — see §5, not the API.
- **Companion docs:** `FISH-AUDIO-TAG-BEST-PRACTICES.md` (research + sources, §6–7),
  `FISH-AUDIO-TAGS-MASTER.md` (full verified catalog), `FISH-AUDIO-STRATEGIC-PLAN.md`
  (persuasion playbook).

---

## 1. EXPRESSIVE REQUEST CONFIG — LONG-FORM WEBINAR BASELINE (VERIFIED FIELDS)

The recommended "strong read" shape for expressive long-form webinar narration on `s2.1-pro`.
Field names and defaults verified against the Fish OpenAPI spec (`https://api.fish.audio/openapi.json`).

```json
{
  "text": "[warm and welcoming] ... full tagged speech ...",
  "reference_id": "<webinar-host-voice>",
  "format": "mp3",
  "mp3_bitrate": 192,
  "chunk_length": 280,
  "normalize": true,
  "latency": "normal",
  "temperature": 0.9,
  "top_p": 0.8,
  "repetition_penalty": 1.2,
  "prosody": { "speed": 0.98, "volume": 0, "normalize_loudness": true },
  "condition_on_previous_chunks": true
}
```
Header: `model: s2.1-pro`.

| Field | Value | Why (all VERIFIED) |
|---|---|---|
| `temperature` | **0.9** (default 0.7) | Fish docs: *"controls expressiveness."* The single biggest lever — higher = more varied, which long-form needs. |
| `top_p` | **0.8** (default 0.7) | Nucleus-sampling diversity; mild variety increase. Keep < 0.9 to avoid instability. |
| `repetition_penalty` | **1.2** (default 1.2) | >1.0 suppresses repeating audio patterns; long-form audio degrades/repeats toward the end — keep ≥1.2. |
| `prosody.speed` | **0.95–1.0** (range 0.5–2.0) | Webinar authority reads unhurried; the close may go slower. |
| `prosody.volume` | 0 (≈ −20…+20 dB) | 0 is fine; whisper segments are a per-line tag job, not global gain. |
| `prosody.normalize_loudness` | true | S2-family loudness normalization. |
| `chunk_length` | **280–300** (100–300) | Larger = more efficient for long text; pipeline already chunks at 300. |
| `condition_on_previous_chunks` | **true** | Uses previous audio as context — this is your **cross-chunk voice consistency** in long-form. |
| `normalize` | true | Clean number/date reads (needed for price lines). |
| `latency` | normal | Best quality. |
| `seed` | — | **Does not exist** on TTS (only on Voice Design). Determinism via lower temperature/top_p only. |

> Honesty: Fish documents *what each knob does*, not a "best range." The 0.9 / 0.8 / 1.2
> baseline is our well-grounded synthesis of documented behavior + API defaults + the
> pipeline's already-tuned values in `synthesize_full_speech.py`. Verify by ear per voice.

---

## 2. THE RICH TAG TAXONOMY (every tag marked ·V / ·C / ·U)

### 2.1 EMOTION — BASIC (24) ·V
`[happy]·V [sad]·V [angry]·V [excited]·V [calm]·V [nervous]·V [confident]·V [surprised]·V
[satisfied]·V [delighted]·V [scared]·V [worried]·V [upset]·V [frustrated]·V [depressed]·V
[empathetic]·V [embarrassed]·V [disgusted]·V [moved]·V [proud]·V [relaxed]·V [grateful]·V
[curious]·V [sarcastic]·V`
Source: [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference)

### 2.2 EMOTION — ADVANCED (25) ·V
`[disdainful]·V [unhappy]·V [anxious]·V [hysterical]·V [indifferent]·V [uncertain]·V
[doubtful]·V [confused]·V [disappointed]·V [regretful]·V [guilty]·V [ashamed]·V [jealous]·V
[envious]·V [hopeful]·V [optimistic]·V [pessimistic]·V [nostalgic]·V [lonely]·V [bored]·V
[contemptuous]·V [sympathetic]·V [compassionate]·V [determined]·V [resigned]·V`
Source: [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference)

### 2.3 EMOTION — EXTRA NAMES (22) ·V on S1, ·C as S2 free-form
On S1 these are fixed-set names; on S2 they are open-domain free-form (same word, brackets) —
capability VERIFIED, phrasing COMPOSED for S2.
`[interested]·V/C [joyful]·V/C [impatient]·V/C [scornful]·V/C [panicked]·V/C [furious]·V/C
[reluctant]·V/C [keen]·V/C [disapproving]·V/C [negative]·V/C [denying]·V/C [astonished]·V/C
[serious]·V/C [conciliative]·V/C [comforting]·V/C [sincere]·V/C [sneering]·V/C [hesitating]·V/C
[yielding]·V/C [painful]·V/C [awkward]·V/C [amused]·V/C`
Source: [Models overview](https://docs.fish.audio/developer-guide/models-pricing/models-overview.md)

### 2.4 EMOTION — INTENSITY MODIFIERS ·V (official pattern)
Prepend a degree word inside the bracket to scale any base emotion:
`slightly X` · `a bit X` · `mildly X` · `very X` · `extremely X` · `super X` · `increasingly X`
Composed examples: `[slightly sad]·V/C` `[very excited]·V/C` `[extremely angry]·V/C` `[super happy]·V/C`

Official intensity scale (emotion ladder):
| Base | Mild | Moderate | Intense |
|---|---|---|---|
| Happy | satisfied | happy | delighted |
| Sad | disappointed | sad | depressed |
| Angry | frustrated | angry | furious |
| Scared | nervous | scared | terrified |
| Excited | interested | excited | ecstatic |
Source: [Emotion control](https://docs.fish.audio/developer-guide/core-features/emotions.md)

### 2.5 EMOTION — BLENDED / INSTRUCTIONAL (the "instructional emotion tags") ·C (open-domain)
The strongest lever for "genuinely alive" reads: combine a feeling **plus a direction** in one
cue. These are the tags to feed the webinar-arc palettes.
`[warm and confident]·C [sincere and warm]·C [calm, grounded authority]·C [unshakeable confidence]·C
[measured and deliberate]·C [matter-of-fact]·C [genuinely caring]·C [gently encouraging]·C
[quietly proud]·C [quietly triumphant]·C [humble but certain]·C [soft and intimate]·C
[warm and reassuring]·C [grateful and sincere]·C [hopeful rising]·C [bittersweet]·C [wistful]·C
[vulnerable, almost confessional]·C [reflective, looking back]·C
[understated, letting the numbers speak]·C [extremely determined]·C [slightly amused]·C`

Documented siblings in this family — **capability VERIFIED** (on Fish's own materials):
`[warm and happy]·V [whispers sweetly]·V [laughing nervously]·V [whisper in small voice]·V
[speaking slowly, almost hesitant]·V [voice rough from crying, trying to sound normal]·V
[overly cheerful, clearly forcing it]·V [professional broadcast tone]·V`
Sources: [Emotion control](https://docs.fish.audio/developer-guide/core-features/emotions.md) · [S2 fine-grained blog](https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/)

### 2.6 PACING / RHYTHM ·V + ·C
| Tag | Status | Note |
|---|---|---|
| `[pause]` / `[break]` | ·V | brief silence (qualitative only) |
| `[short pause]` | ·V | shorter beat |
| `[long pause]` / `[long-break]` | ·V | extended silence (qualitative only) |
| `[in a hurry tone]` | ·V | rushed, urgent |
| `[speed up]` | ·V | faster |
| `[quickening pace]` | ·C | composed faster-cue |
| `[slow down]` | ·V | slower |
| `[speaking slowly, almost hesitant]` | ·V | documented example — the close |
| `[slowing down for weight]` | ·C | the price-drop / decision moment |
Sources: [S2 blog](https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/) · [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference) · [GitHub README](https://github.com/fishaudio/fish-speech)

### 2.7 ENERGY / MOMENTUM ·C (open-domain)
`[building excitement]·C [barely contained enthusiasm]·C [rising energy]·C [celebratory]·C
[upbeat and bright]·C [contagious energy]·C [fast and punchy]·C [building to a crescendo]·C
[quiet before a turn]·C [sudden stop]·C`
Documented siblings: `[excited]·V [delight]·V [excited tone]·V`.
Sources: [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference) · [HF s2-pro card](https://huggingface.co/fishaudio/s2-pro)

### 2.8 DELIVERY / TONE ·V + ·C
- **VERIFIED:** `[whispering]·V [whisper]·V [shouting]·V [screaming]·V [soft tone]·V [soft voice]·V [low voice]·V [loud voice]·V [emphasis]·V [in a hurry tone]·V`
- **COMPOSED (open-domain):** `[lowering voice for emphasis]·C [leaning in, conspiratorial]·C [hushed for the secret]·C [direct, assured]·C [no-nonsense]·C [clipped and direct]·C [serious, direct]·C [urgent but controlled]·C [smiling while speaking]·C [a knowing smile]·C`
Sources: [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference) · [S2 blog](https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/)

### 2.9 DIRECTION / INSTRUCTIONAL (voice-acting directions) ·V + ·C
"Govern HOW it reads" — direction to the model as a director to an actor.
- **VERIFIED (on Fish's own materials):** `[professional broadcast tone]·V [the calm, measured tone of someone who has done this a thousand times]·V [dead tired, end of a very long shift]·V [overly cheerful, clearly forcing it]·V [whisper in small voice]·V [interrupting]·V [singing]·V [with strong accent]·V [echo]·V`
- **COMPOSED (open-domain):** `[narrator]·C [like talking to an old friend]·C [as if telling a story to a friend]·C`
Sources: [S2 blog](https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/) · [GitHub README](https://github.com/fishaudio/fish-speech) · [HF s2-pro card](https://huggingface.co/fishaudio/s2-pro)

### 2.10 PAUSES ·V (qualitative) + pipeline-measured
- Official tags — **qualitative only, no documented seconds:** `[pause]·V [short pause]·V [long pause]·V [break]·V [long-break]·V`
- **Measured pauses (pipeline mechanism):** strip the tag, splice exact-duration ffmpeg silence.
  Defaults already in the executor: `[short pause]` 0.8 s · `[pause]`/`[break]` 1.2 s ·
  `[BREATHE]` 1.2 s · `[long pause]`/`[long-break]` 2.5 s · `(PAUSE N seconds)` exact.
- Breath / paralanguage — **VERIFIED:** `[inhale]·V [exhale]·V [sigh]·V [gasp]·V [panting]·V [clears throat]·V [breath]·V`
- Community: pause tags are unreliable for long between-sentence gaps → the ffmpeg approach is
  the right call. Stacking pause tags to fake a long silence is **UNVERIFIED** — test first.
Sources: [Emotion reference](https://docs.fish.audio/api-reference/emotion-reference) · [Fine-grained control](https://docs.fish.audio/developer-guide/core-features/fine-grained-control.md) · [Discussion #1286](https://github.com/fishaudio/fish-speech/discussions/1286)

### 2.11 DYNAMIC PROSODY — volume / pitch / speed / echo ·V (documented examples)
`[volume up]·V [volume down]·V [low volume]·V [loud]·V [pitch up]·V [pitch down]·V [speed up]·V
[slow down]·V [soft voice]·V [loud voice]·V [echo]·V`
Per-line levers for the moments you want louder/quieter/higher/lower/faster/slower/echoy —
these are single-word dynamic controls, distinct from the emotional descriptors above.
Sources: [S2 blog](https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/) · [GitHub README](https://github.com/fishaudio/fish-speech)

### 2.12 PHONEME CONTROL ·V (exact pronunciation)
`<|phoneme_start|>…<|phoneme_end|>` — CMU Arpabet for English, tone-number pinyin for Chinese,
OpenJTalk romaji + pitch accent for Japanese. Survives text normalization. Use for brand names
and anything the model mangles, e.g. "engineer" → `EH1 N JH AH0 N IH1 R`.
Source: [Fine-grained control](https://docs.fish.audio/developer-guide/core-features/fine-grained-control.md)

---

## 3. APPLYING IT — WEBINAR-ARC STAGE PALETTES ·C (compositions from ·V tags)

These are **COMPOSED but valid** (S2 is open-domain — the capability is verified, the phrasing
is ours). Use them as the primary palettes in `speech_fish_tag.py` and the speech-writer's copy.
**Rotate within a stage so consecutive lines don't read flat.** The taxonomy in §2 expands each
palette so rotation stays fresh. Densities per the strategic plan: Teach = lowest (~1 tag per
4–5 sentences), Proof = deliberately under-tagged, Offer = highest (1 per 1–2 sentences),
Close = warm and slow.

### USAGE MANDATE (apply before you tag a single line)

1. **Emotional-arc map first, tags second.** Each stage exists to make the listener FEEL one
   thing (arc-to-emotion map below; strategic plan §2). Decide the stage's target emotion,
   then tag the words that dramatize it — a tag with no emotional beat behind it lands flat.
   Only two stages are true energy peaks: the OFFER reveal and the SCARCITY moment. Everything
   else stays lower so those peaks hit.
2. **Dramatic pacing is a separate, higher-leverage job.** The measured silence is the
   close-rate lever. Tag a deliberate beat AFTER the hook/promise line, BEFORE each reveal,
   around the price, and after the CTA — at the sentence seam a human would pause at. The
   executor splices EXACT seconds (0.8 s / 1.2 s / 2.5 s, or `(PAUSE N seconds)`); the
   qualitative `[pause]` tag alone is not the mechanism (see §4). If the written sentence is a
   run-on with no seam, flag it back to the writer rather than forcing a tag mid-clause.
3. **Reference-audio note.** The demo is voiced over a chosen reference voice, and the
   reference sets the voice's DEFAULT emotional tendency; tags add per-line direction ON TOP
   of that baseline (`FISH-AUDIO-TAG-BEST-PRACTICES.md` §4). A calm/warm reference shows
   SUBTLER tag effects — so the words must carry the moments that matter, and if tags fail to
   activate on the chosen voice, recommend a more expressive reference voice rather than
   piling on tags. Verify each new tag by ear on the actual voice (§5.9).

| Stage | Listener should feel | Voice's job | Energy | Density |
|---|---|---|---|---|
| HOOK / OPEN | curiosity + "this is for me" | confident, warm, intriguing | low, steady | 1 tag / 2–3 sentences |
| STORY | connection, "that's my situation" | vulnerable → hopeful; tag the TURNS | rises then settles | 1 tag / paragraph |
| TEACH / VALUE | clarity, "I'm learning, I trust them" | calm authority, generous | LOWEST | ~1 tag / 4–5 sentences |
| PROOF | belief, "this actually works" | understated; let the numbers speak | low | 1 tag / proof point max |
| OFFER / PITCH | desire, "I want this" | excited, generous, certain | **PEAK** | 1 tag / 1–2 sentences |
| SCARCITY / URGENCY | FOMO without sleaze | urgent but controlled; pacing not volume | **PEAK 2** | 1 tag / 2 sentences + pacing |
| CLOSE / CTA | the decision is safe and right | warm, certain; slow, lower the voice | warm landing | 1 tag / 2–3 sentences, warm |

**Hard ceiling:** never two consecutive fully-tagged sentences outside the OFFER peak; a
paragraph with more tags than sentences is over-tagged. Rule of thumb: ~1 emotion tag every
80–120 words across a 45-min script, rising into the Offer and easing either side.

### 3.1 HOOK / OPEN — curiosity + "this is for me"
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

### 3.2 STORY — connection, low-to-high arc
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

### 3.3 TEACH / VALUE — calm authority
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

### 3.4 PROOF — understated credibility
Target feeling: "this actually works." **Deliberately under-tag.** Restraint = credibility.
Quiet proof sounds true; loud proof sounds fake.
```
[confident and factual] Last quarter, one member went from zero to forty-one paying clients. [pause]
[understated, letting the numbers speak] Another did three hundred thousand in ninety days.
[proud but humble] These aren't outliers. This is what happens when the system is followed.
```
Palette: `[confident and factual]` · `[understated, letting the numbers speak]` ·
`[proud but humble]` · `[clinical precision]` · `[proud]` · `[satisfied]`

### 3.5 OFFER / PITCH — desire + certainty (energy peak)
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

### 3.6 SCARCITY / URGENCY — deadline, not threat
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

### 3.7 CLOSE / CTA — the price-drop & decision moment
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
`[pause]` → `[reassuring]` close. **Land warm, never loud.** Slowing + quiet on the price is a
pacing job (`[slowing down for weight]` + measured ffmpeg silence), not a volume job.

---

## 4. PAUSE PLAYBOOK (EXACT SECONDS VIA THE EXECUTOR)

The Fish tags `[pause]` / `[long pause]` have **no documented duration**. The executor
(`synthesize_full_speech.py`) strips pause markers from the API text and splices a measured
silent mp3 at the concat stage. Defaults (override with `--pause-short`, `--pause`, `--pause-long`):

| Tag | Default seconds | Use for |
|---|---|---|
| `[short pause]` | 0.8 | quick beat, mid-sentence rhythm, lists |
| `[pause]` / `[break]` / `[PAUSE]` | 1.2 | let a promise/reveal land, around the price |
| `[BREATHE]` | 1.2 | breath cue treated as a beat |
| `[long pause]` / `[long-break]` | 2.5 | major pivot, single biggest line |
| `(PAUSE N seconds)` | N | director-specified exact silence (parsed) |

Adjacent pause tags merge (e.g. `[pause][long pause]` → 3.7 s). `(OWNER: ...)` director notes
are dropped entirely — they are never spoken.

---

## 5. COMBINING AND PLACEMENT RULES

1. Emotion cue at the **start** of the sentence it governs.
2. Tone / sound / dynamic cue can sit **anywhere**; scope = from the tag forward.
3. Stack up to **3** cues per sentence max (`[sad][whispering] I miss you so much.`).
4. Add spoken text after a sound effect (`[laughing] Ha ha`, `[sighing] sigh`).
5. Keep free-form descriptors tight — a paragraph-long bracket hurts the model.
6. Intensity modifiers: prepend a degree (`[slightly sad]` `[very excited]` `[extremely angry]`).
7. Pair physical tags with emotion tags — physical alone can feel flat (`[panting] [tired] I've
   been running for twenty minutes.`).
8. If a tag isn't landing, **rephrase the free-form descriptor** (S2 open-domain) — don't assume
   fixed-tag behavior.
9. Verify before shipping: generate and listen. Tags are hypotheses; the rendered audio is the
   only ground truth. Test each new tag on the actual voice.

---

## 6. VERIFICATION STATUS SUMMARY

| Category | Status |
|---|---|
| Emotion — basic (24) / advanced (25) | VERIFIED |
| Emotion — extra names (22) | VERIFIED on S1 / COMPOSED as S2 free-form |
| Emotion — intensity modifiers (pattern) | VERIFIED |
| Emotion — blended / instructional | COMPOSED (capability VERIFIED — open-domain) |
| Pacing / rhythm | VERIFIED + COMPOSED |
| Energy / momentum | COMPOSED (siblings VERIFIED) |
| Delivery / tone | VERIFIED + COMPOSED |
| Direction / instructional | VERIFIED + COMPOSED |
| Pause tags (`[pause]`, `[long pause]`, `[break]`, `[long-break]`) | VERIFIED (qualitative only) |
| Exact seconds for any pause tag | **UNVERIFIED** — executor splices measured silence |
| Dynamic prosody (volume / pitch / speed / echo) | VERIFIED (documented examples) |
| Phoneme control | VERIFIED |
| Stage delivery palettes (section 3) | COMPOSED (valid on S2 open-domain) |
| `temperature` / `top_p` / `repetition_penalty` / `prosody` / `chunk_length` / `condition_on_previous_chunks` | VERIFIED against OpenAPI |
| `model: s2.1-pro` header | VERIFIED |

---

## 7. SOURCES (key — full list in `FISH-AUDIO-TAG-BEST-PRACTICES.md` §11)

- Docs — Emotion control (placement, combos, intensity, do/don'ts): https://docs.fish.audio/developer-guide/core-features/emotions.md
- Docs — Emotion reference (24+25 emotions, tones, effects, break/long-break): https://docs.fish.audio/api-reference/emotion-reference
- Docs — TTS REST endpoint (all params, model header): https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech.md
- OpenAPI spec (authoritative TTSRequest schema): https://api.fish.audio/openapi.json
- Docs — Fine-grained control (phoneme tags, paralanguage): https://docs.fish.audio/developer-guide/core-features/fine-grained-control.md
- Blog — S2 fine-grained word-level control (placement, whisper/shout/emphasis, free-form): https://fish.audio/blog/fish-audio-s2-fine-grained-ai-voice-control-at-the-word-level/
- GitHub — fishaudio/fish-speech README: https://github.com/fishaudio/fish-speech
- Hugging Face — s2-pro model card: https://huggingface.co/fishaudio/s2-pro
- Discussion #1302 (no fixed tag list; open-domain): https://github.com/fishaudio/fish-speech/discussions/1302
- Discussion #1286 (pause tags unreliable for long gaps): https://github.com/fishaudio/fish-speech/discussions/1286

*End of reader-tag library (v2 rich taxonomy). Companion: `FISH-AUDIO-TAG-BEST-PRACTICES.md`
(research + sources), `FISH-AUDIO-TAGS-MASTER.md` (verified catalog), `FISH-AUDIO-STRATEGIC-PLAN.md`
(persuasion playbook).*
