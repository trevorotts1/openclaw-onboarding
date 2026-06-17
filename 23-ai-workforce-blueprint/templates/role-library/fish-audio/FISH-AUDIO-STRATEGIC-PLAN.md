# FISH AUDIO — STRATEGIC PLAYBOOK FOR SALES-WEBINAR SPEECH

How a speech-writer deploys Fish Audio control tags to maximize emotional power and persuasion across a sales-webinar arc.

- **For:** BlackCEO Presentations department
- **Pairs with:** `FISH-AUDIO-TAGS-MASTER.md` (the verified tag catalog)
- **Author:** Claude Opus 4.8 (1M context) · 2026-06-16
- **Target engine:** Fish Audio **S2 / S2-Pro** (square-bracket, open-domain). S1 fallback notes included.

---

## 0. THE ONE RULE THAT GOVERNS EVERYTHING

**Tags are seasoning, not the meal.** The persuasion lives in the *words and the structure*. Tags make a well-written line *land* — they cannot rescue a flat one. A webinar narrated in a flat monotone fails; a webinar with a tag on every clause sounds like a clown. The win is in the **contrast**: long stretches of grounded, confident calm, broken by *deliberate* spikes of emotion exactly where the persuasion turns.

Persuasion = **earned emotional contrast**. You earn the spike by under-playing the run-up.

---

## 1. ENGINE & SYNTAX DECISION (do this first)

| If you are using… | Then write tags as… | Free-form descriptions? |
| --- | --- | --- |
| **S2 / S2-Pro** (recommended) | `[square brackets]` | **Yes** — `[calm, grounded authority]`, `[lowering voice]`, etc. |
| **S1 / S1-mini** (legacy) | `(parentheses)` | **No** — fixed tag set only (see catalog sections A–E) |

**Always default to S2/S2-Pro for a sales webinar.** The free-form descriptor space is the whole reason this is a competitive advantage: you can direct the voice like a director directs an actor.

Verified placement rules you must obey (from `docs.fish.audio`):
- **Emotion cue → start of the sentence it governs.**
- **Tone / sound-effect / dynamic cue → anywhere** (placement sets the scope; the cue affects text *from that point forward*).
- **Stack up to 3** emotion cues per sentence — no more.
- **Add text after a sound effect** (`[laughing] Ha ha`, `[sighing] sigh`).
- Tags cost **no tokens and add no latency**.

---

## 2. THE WEBINAR ARC → EMOTION MAP

A sales webinar is an emotional journey, not an information dump. Each beat has a *target feeling in the listener*, and the voice must model that feeling first (emotional contagion). Map:

| Beat | Listener should feel | Voice's job | Primary palette |
| --- | --- | --- | --- |
| **1. Hook / Open** | curiosity + "this is for me" | confident, warm, intriguing | `[confident]` `[warm and welcoming]` `[curious]` `[mysterious]` |
| **2. Story** | connection + "that's my situation" | vulnerable → hopeful arc | `[reflective]` `[vulnerable]` `[nostalgic]` → `[hopeful]` `[determined]` |
| **3. Teach / Value** | clarity + "I'm learning, I trust them" | calm authority, generous | `[calm]` `[helpful]` `[enthusiastic]` `[encouraging]` |
| **4. Proof** | belief + "this actually works" | understated confidence | `[confident]` `[proud]` `[satisfied]` (let proof speak — under-tag) |
| **5. Offer / Pitch** | desire + "I want this" | excited, generous, certain | `[excited]` `[confident]` `[delighted]` `[building excitement]` |
| **6. Scarcity / Urgency** | fear of missing out | urgent but controlled | `[in a hurry tone]` `[urgent but controlled]` `[serious]` |
| **7. Close / CTA** | resolve + relief of decision | warm, certain, reassuring | `[sincere]` `[confident]` `[reassuring]` `[grateful]` |

Visual of the energy curve (low = calm, high = peak):

```
Energy
 HIGH |                                  ___           __
      |              __                 /   \   __    /  \
  MID |   __        /  \      _____    /     \_/  \__/    \___
      |  /  \______/    \____/     \__/                       (warm landing)
  LOW |_/  HOOK   STORY   TEACH    PROOF   OFFER  SCARCITY  CLOSE
```

The two true peaks: **the offer reveal** and **the scarcity moment**. Everything else sets them up by staying lower.

---

## 3. DENSITY GUIDELINES (tags per paragraph)

The single most common failure is **over-tagging**. Follow this:

| Section | Target density | Rationale |
| --- | --- | --- |
| Hook | **1 emotion tag per 2–3 sentences** + 1 pause for the hook line | Establish tone, then get out of the way |
| Story | **1 emotion tag per paragraph** as the arc turns; 1–2 breaths/pauses | Let the words carry; tag the *turns* only |
| Teach | **1 tag per ~4–5 sentences** (lowest density) | Authority sounds *unhurried and untagged*; over-tagging teaching sounds manic |
| Proof | **1 tag per proof point, max** | Under-tag deliberately — restraint reads as truth |
| Offer | **1 emotion tag per 1–2 sentences** (highest density) | Peak energy; this is where you spend tags |
| Scarcity | **1 tag per 2 sentences** + pacing tags | Urgency via *pacing*, not via piling on emotion |
| Close | **1 tag per 2–3 sentences**, warm | Land softly; resolve, don't shout |

**Hard ceiling:** never more than **1 stacked cue (max 3 tags) per sentence**, and never two consecutive sentences both fully tagged outside the Offer peak. If a paragraph has more tags than sentences, cut tags until it doesn't.

**Rule of thumb:** across an entire 45-minute webinar script, aim for roughly **1 emotion tag every 80–120 words**, with the density rising into the Offer and easing on either side.

---

## 4. SECTION-BY-SECTION PLAYBOOK (with concrete examples)

All examples are S2/S2-Pro bracket syntax. Replace bracket→paren for S1.

### 4.1 HOOK / OPEN
Goal: pattern-interrupt + curiosity + instant authority. Open with a confident, slightly warm tone. Use **one** pause to make the hook land.

```
[confident] If you give me the next forty minutes, I'm going to show you something
that took me eleven years and a painful amount of money to figure out. [pause]

[warm and welcoming] And by the end, you'll know exactly whether this is for you
[curious] or not. Either way, you'll leave with something you can use today.
```

Do: lead with `[confident]`. Drop one `[pause]` after the promise so the brain catches up.
Don't: stack `[excited][happy][delighted]` on the first line — you haven't earned energy yet, and it reads as a hard sell.

### 4.2 STORY
Goal: connection through a real low-to-high arc. This is where emotion tags earn their keep — but tag only the *turns*. Mirror the verified official "emotion transition" pattern.

```
[reflective] Three years ago I was sitting in a parking lot at 11pm, [pause]
not wanting to go home and tell my family the launch had failed. [sighing] sigh.

[vulnerable] I'd put everything into it. [sad] And it just... didn't work.

[pause] [hopeful] But that night, something clicked. [building excitement]
I realized I'd been solving the wrong problem the entire time.

[determined] So I rebuilt it from zero. And this time — it worked.
```

Do: let one tag govern a whole paragraph; use `[pause]` and `[sighing]` as the connective tissue of a real human telling a real story.
Don't: tag every sentence — a story narrated with a tag per line sounds like a soap opera, and the listener stops believing it.

### 4.3 TEACH / VALUE
Goal: be the calm expert. **Lowest tag density.** Authority sounds unhurried. Use `[emphasis]` on the one word that matters in a key sentence.

```
[calm] Here's the part most people get wrong. [pause] They optimize the funnel
before they have a single message that actually converts.

[helpful] The order matters. Message first. [emphasis] Then traffic.

[encouraging] When you do it in that order, everything downstream gets easier.
```

Do: trust silence and plain confidence. One `[emphasis]` is worth ten emotion tags here.
Don't: use `[excited]` on teaching content — it makes you sound like an infomercial and destroys the authority you're building.

### 4.4 PROOF
Goal: belief. **Deliberately under-tag.** Restraint = credibility. Let the numbers and names carry it; the voice should be quietly, almost understatedly confident.

```
[confident] Last quarter, one member went from zero to forty-one paying clients. [pause]

[understated, letting the numbers speak] Another did three hundred thousand in ninety days.

[proud] These aren't outliers. This is what happens when the system is followed.
```

Do: `[understated, letting the numbers speak]` is the single best proof tag — it signals "I don't need to oversell this."
Don't: `[excited][shouting]` your proof. Loud proof sounds fake. Quiet proof sounds true.

### 4.5 OFFER / PITCH
Goal: desire + certainty. **Highest tag density.** This is where you *spend* your emotional budget. Build energy, be generous, be certain.

```
[building excitement] So here's everything you get when you join today.

[excited] You get the full system — every template, every script, every funnel.
[confident] You get the weekly coaching calls where we build it with you live.
[delighted] And you get the private community that honestly might be worth the whole thing on its own.

[confident] This is the exact system that produced the results I just showed you.
[sincere] Nothing held back.
```

Do: ramp `[building excitement]` → `[excited]` → `[delighted]`, then *land* on `[confident][sincere]` so desire is anchored by trust, not just hype.
Don't: stay at peak excitement through the price — see the next section. Excitement sells the *value*; calm certainty sells the *price*.

### 4.6 SCARCITY / URGENCY
Goal: real urgency without sleaze. Urgency is carried by **pacing and a serious tone**, not by emotional volume. Quicken the pace, lower the theatrics.

```
[serious] Now, I have to be straight with you about something.

[urgent but controlled] This enrollment closes Friday at midnight, and I'm not reopening it
until next quarter. [in a hurry tone] The bonuses come off the table at the same time.

[pause] [confident] I'm not going to chase you. [sincere] But if you've been waiting
for the right moment — this is it.
```

Do: `[urgent but controlled]` + `[in a hurry tone]` quicken delivery; the `[pause]` then `[confident]` "I'm not going to chase you" is the power move — controlled scarcity reads as honest.
Don't: `[screaming]` or `[shouting]` scarcity. Panic-selling kills trust. Urgency should feel like a *deadline*, not a *threat*.

### 4.7 CLOSE / CTA — THE PRICE-DROP & DECISION MOMENT
Goal: make the decision feel safe and right. This is the most important pacing section in the entire script. **Slow down. Lower the voice. Use pauses around the price.**

#### The price-drop technique (pacing for the close)
The number must land in a pocket of **calm certainty**, framed by pauses, *after* the value has been stacked at high energy. The contrast — high-energy value → quiet, slow price — is what makes the price feel small.

```
[excited] So all of that — the system, the coaching, the community, the bonuses —
[confident] if you bought these separately, you're easily past twelve thousand dollars. [pause]

[calm] But you're not going to pay twelve thousand. [short pause]

[sincere] [slowing down for weight] Today, to join us, it's [pause] nineteen ninety-seven. [pause]

[warm and welcoming] One payment. [reassuring] And you're in.
```

Why this works:
- **Value stacked at high energy** (`[excited]` → big anchor number) makes the brain expect a big price.
- **`[pause]` before the price** creates anticipation.
- **`[calm]` + `[slowing down for weight]`** delivers the real number *quietly and slowly* — calm delivery signals "this is fair, I'm not nervous about it."
- **`[pause]` mid-sentence around the number** ("it's [pause] nineteen ninety-seven [pause]") lets the number sit alone, which makes it feel deliberate and small relative to the anchor.
- **`[reassuring]` close** removes the last friction.

#### The final CTA
```
[confident] Click the button below this video right now.

[warm and welcoming] It takes about sixty seconds. [reassuring] You'll get an email
with everything immediately.

[sincere] I genuinely can't wait to work with you. [grateful] Thank you for spending
this time with me today — [confident] now go click that button.
```

Do: end on `[grateful]` + a final `[confident]` directive. Warmth + certainty = the highest-converting close tone.
Don't: end loud. Don't pile urgency on the final line. The last impression should be *trust and warmth*, with a clear, calm instruction.

---

## 5. THE PACING TOOLKIT (pauses, breaths, emphasis)

These are your highest-leverage, lowest-risk tools. Use them far more freely than emotion tags.

| Tool | S2 tag | Use it for |
| --- | --- | --- |
| Beat / let it land | `[pause]` | After every promise, before every reveal, around the price |
| Quick beat | `[short pause]` | Mid-sentence rhythm, lists, "are you sure? … really sure?" |
| Big silence | `[long-break]` | Before a major pivot or the single biggest line of the talk |
| Human breath | `[inhale]` / `[exhale]` / `[breath]` | Start of an intimate/story line; makes the voice human |
| Reset / honesty signal | `[sighing] sigh` | Before a vulnerable admission ("I have to be honest…") |
| Stress one word | `[emphasis]` | The ONE word in a sentence that carries the meaning |

**Pause placement is the close-rate lever.** A webinar with great words and no pauses converts worse than a decent webinar with surgical pauses. Pauses around the price, around the CTA, and after the hook are non-negotiable.

---

## 6. CONTRAST CHOREOGRAPHY (the advanced move)

Persuasion is contrast. Engineer it:

- **Before a high point, go low.** Two calm/`[serious]` sentences make the next `[excited]` line hit twice as hard.
- **Drop volume to raise attention.** `[lowering voice]` / `[whisper] / [soft tone]` on a key secret pulls the listener *in* far more than shouting.
- **Speed contrast at the close:** fast, energetic value stack → sudden slow, quiet price.
- **The "honesty drop":** `[sighing] [serious] Look, I'll be straight with you…` — dropping to a slower, plainer register signals truth and is one of the most persuasive transitions in selling.

---

## 7. DO / DON'T MASTER LIST

### DO
- Default to **S2/S2-Pro brackets** and use **free-form descriptors** for nuanced direction.
- **Tag the turns, not every line.** One tag per paragraph in narrative sections.
- Put **emotion cues at the start** of the sentence they govern.
- Use **pauses and `[emphasis]` liberally** — they are safe and high-leverage.
- **Under-tag proof** and **under-tag teaching** — restraint reads as authority and truth.
- **Spend your emotion budget at the Offer**, then drop to calm certainty for the price.
- **Deliver the price slowly, quietly, with pauses around the number.**
- **Land the close on warmth + a clear calm directive** (`[grateful]` → `[confident]` CTA).
- **Read it aloud / generate and listen.** Tags are predictions; verify the actual audio.
- Add **text after sound effects** (`[laughing] Ha ha`).

### DON'T
- Don't **over-tag** — if a paragraph has more tags than sentences, cut.
- Don't **stack more than 3** cues on one sentence.
- Don't **mix conflicting emotions** (`[happy][angry]`) — pick one primary.
- Don't **`[shouting]` / `[screaming]` the scarcity or the price** — panic kills trust.
- Don't **`[excited]` the teaching section** — it destroys authority.
- Don't **end loud** — the final impression must be trust and warmth.
- Don't put a **sentence-level emotion cue far from its sentence**.
- Don't **rely on S1 free-form descriptors** — S1 only honors the fixed tag set; use S2 for anything beyond the named tags.
- Don't write **bracket descriptions so long they read as a paragraph** — keep them tight.
- Don't **forget the brackets** — un-bracketed direction words get *spoken aloud*.

---

## 8. COPY-PASTE STARTER FRAMES

**Hook frame:**
`[confident] {bold promise}. [pause] [warm and welcoming] {who this is for}. [curious] {open loop}.`

**Story turn frame:**
`[reflective] {the low point}. [sighing] sigh. [pause] [hopeful] {the realization}. [determined] {the rebuild}.`

**Proof frame:**
`[confident] {result #1}. [pause] [understated, letting the numbers speak] {result #2}. [proud] {the pattern, not luck}.`

**Offer ramp frame:**
`[building excitement] {what they get, part 1}. [excited] {part 2}. [delighted] {the surprising bonus}. [confident] [sincere] {the certainty line}.`

**Price-drop frame:**
`[excited] {value stack + anchor price}. [pause] [calm] But you're not paying that. [short pause] [sincere] [slowing down for weight] Today it's [pause] {price}. [pause] [reassuring] {payment terms}.`

**Close frame:**
`[confident] {clear instruction}. [warm and welcoming] {how easy/fast}. [sincere] {personal line}. [grateful] {thank you} — [confident] {final directive}.`

---

## 9. QA CHECKLIST BEFORE YOU SHIP THE AUDIO

1. Engine confirmed (S2/S2-Pro → brackets)?
2. Any paragraph with more tags than sentences? → cut.
3. Emotion cues at sentence starts?
4. No stacked sentence exceeds 3 tags?
5. No conflicting-emotion stacks?
6. Pauses present around: the hook, every reveal, the price, the CTA?
7. Proof and teaching deliberately under-tagged?
8. Offer is the energy peak; price is delivered calm/slow?
9. Close lands warm with a clear calm directive (not loud)?
10. **Generated and listened to** — does the actual audio match intent? Adjust tags that didn't land (S1 effects like `(laugh)` may need repeating; on S2, rephrase the free-form descriptor if it's ignored).

> Tag choices are hypotheses about how the model will sound. The only ground truth is the rendered audio. Always generate, listen, and iterate before the webinar goes live.
