# Module: Fish Audio Delivery Tagging (Pipeline Step 6)

**Owns:** the delivery tag strategy embedded during Step 6 (Draft in Final Draft format) of the
canonical 18 step pipeline. This module governs which tags are written, where, at what density, and
in which syntax. The draft module writes the prose; this module governs the tags inside it.

**Model:** the render step (Step 11) synthesizes on Fish Audio model `s2.1-pro`, selected via the
HTTP header, using the client's own private voice `reference_id`. The `s2.1-pro-free` tier has no
service level agreement and may train on inputs and is forbidden for client content. Because the
production model is in the S2 family, the DEFAULT tag syntax for every script is the S2.1 Pro square
bracket palette below. The legacy S1 parentheses palette is used only when the account is explicitly
specified as S1.

**Hard rules:** a flat script with no tags is a quality failure, and an over tagged script that
fights itself is also a quality failure. Tags are excluded from the spoken word count. No em dash
characters and no triple backtick or code fence markers anywhere.

---

## 1. The S2.1 Pro square bracket palette (default)

- Tags are written in square brackets, for example `[excited]`, `[long pause]`, `[voice breaking]`.
- Tags accept free form natural language. You are not limited to a fixed menu. `[warm and confident]`,
  `[leaning in like sharing a secret]`, `[building intensity]`, and `[professional broadcast tone]`
  are all valid.
- A tag affects the speech that comes AFTER it. Place the tag at the exact point where the delivery
  shift should happen, including mid sentence. The model holds the last direction until it is
  redirected.
- Tags can be layered for compound delivery, for example `[sad][whispering]` before a line.
- Intensity modifiers are supported, for example `[slightly amused]`, `[very excited]`,
  `[extremely serious]`.
- `[emphasis]` placed immediately before a word or short phrase stresses it, for example: This is
  `[emphasis]` exactly why most people fail.
- Pacing tags: `[pause]` for a beat, `[long pause]` for dramatic silence. Use these at reveals,
  before thesis statements, and after gut punch lines.
- Human sound tags: `[sigh]`, `[laughing]`, `[chuckling]`, `[clear throat]`. Natural onomatopoeia
  also works untagged, for example writing "Ha, ha" for a small laugh.
- Direct the energy with a tag, never with punctuation abuse. Do not stack exclamation points and do
  not write in all capitals to force energy.

---

## 2. Density target

- One delivery tag roughly every two to five sentences, concentrated at emotional pivot points.
- Long stable passages need no tags; the model holds the last direction until redirected, so do not
  re tag a steady stretch just to fill it.
- The density enhances delivery rather than cluttering it. Too few tags leaves the read flat; too
  many makes it fight itself. Both are quality failures.
- Tags are excluded from the spoken word count but they do consume file characters, so keep each tag
  to a few words.

---

## 3. Mandatory tag locations

At minimum, a delivery tag is present at each of these locations:

- The cold open. Set the opening energy explicitly with the first tag.
- Every major beat transition in the Style Engine arc.
- The vulnerability and transparency beat. Soften and slow it.
- Each big reveal. A pause before, an energy shift after.
- The closing passage. Build, then land.

A script missing a tag at any mandatory location is incompletely directed and is sent back.

---

## 4. Palette selection: the respondent's stated tone governs

The respondent's speaking tone answer (the voice governor) chooses the tag palette:

- An edgy and passionate speaker gets tags like `[fired up]`, `[emphasis]`, `[building intensity]`.
- A calm and wise speaker gets tags like `[warm]`, `[soft tone]`, `[measured and steady]`.

Match the tags to the energy a person with that stated tone would actually deliver. The tone answer
governs the palette across the whole script; the style tendencies below refine it beat by beat.

---

## 5. Style Engine tag tendencies

Layer these style tendencies on top of the tone driven palette:

- Counter Intuitive: `[dry]`, `[deadpan]`, `[slightly amused]`, and `[pause]` before punchlines.
- Vulnerable: `[soft]`, `[voice trembling slightly]`, `[gentle]`, `[long pause]`, with `[light laugh]`
  as pressure release after the heaviest moments.
- Provocative: `[emphasis]`, `[firm]`, `[building intensity]`, and `[pause]` before verdicts.
- Passionate: `[excited]`, `[playful]`, `[whispering]` for intimacy, then `[powerful and rising]` for
  the crescendo.

Never place a tag whose plain text reading would make sense as speech if the engine failed to catch
it. Keep every tag obviously non verbal so a missed tag never reads as a spoken word and embarrasses
the episode.

---

## 6. Legacy S1 parentheses conversion table

Use this ONLY when the request states the account runs the legacy S1 (OpenAudio S1) model. S1 tags
are written in parentheses and come from a FIXED set; free form descriptions are not supported. Place
the marker immediately before the line it modifies. Layering works the same way, for example
`(sad)(whispering)` before the affected line.

**The S1 fixed set:**

- Emotion markers: `(angry)`, `(sad)`, `(excited)`, `(surprised)`, `(sarcastic)`, `(joyful)`,
  `(empathetic)`.
- Tone markers: `(whispering)`, `(soft tone)`, `(shouting)`, `(screaming)`, `(in a hurry tone)`.
- Special markers: `(laughing)`, `(chuckling)`, `(sobbing)`, `(sighing)`, `(panting)`.

**Converting an S2.1 Pro script to S1:** map each free form square bracket tag to the nearest fixed
S1 marker, and drop any tag that has no reasonable equivalent rather than inventing a new S1 tag.
Reference mapping for the tags this engine uses most:

| S2.1 Pro square bracket tag | Nearest fixed S1 marker |
|---|---|
| `[excited]`, `[fired up]`, `[energetic]` | `(excited)` |
| `[powerful and rising]`, `[building intensity]` | `(excited)` |
| `[emphasis]`, `[firm]` | no fixed equivalent, drop the tag and carry the stress in the wording |
| `[warm]`, `[gentle]`, `[soft]`, `[soft tone]`, `[measured and steady]` | `(soft tone)` |
| `[whispering]`, `[leaning in like sharing a secret]` | `(whispering)` |
| `[voice breaking]`, `[voice trembling slightly]` | `(sobbing)` |
| `[sad]`, `[somber]` | `(sad)` |
| `[dry]`, `[deadpan]`, `[slightly amused]` | `(sarcastic)` |
| `[playful]`, `[joyful]` | `(joyful)` |
| `[light laugh]`, `[laughing]` | `(laughing)` |
| `[chuckling]` | `(chuckling)` |
| `[sigh]` | `(sighing)` |
| `[warm and confident]`, `[professional broadcast tone]` | no fixed equivalent, drop the tag |
| `[pause]`, `[long pause]` | no fixed equivalent, drop the tag and let sentence length and a full stop carry the beat |

S1 has no pacing tag, so pacing that mattered in S2.1 Pro is carried by prose rhythm and punctuation
in an S1 script, never by an invented parenthesis tag.

---

## 7. Downstream episode QC hooks

The tags this module places are checked deterministically at the episode gate:

- Tier 1 check 7, tag syntax integrity: every tag uses the correct syntax for the target model
  (square brackets for S2.1 Pro by default, parentheses for S1 only when specified). No orphaned or
  malformed brackets, and no plain text stage direction masquerading as a tag.
- Tier 1 check 8, tag count exclusion: spoken word and character counts are recomputed with every tag
  stripped, and the count must sit inside the chosen target from the sizing table.
- Tier 1 check 4, no labels: no plain text stage directions such as "pause here" or "said warmly"
  survive. Anything a mouth would otherwise speak must be a real tag or be removed; an untagged stage
  direction is spoken aloud and ruins the episode.
- Rubric dimension 10, Audio Direction Quality: beyond correct syntax, judges whether the tags are
  artfully placed to heighten delivery at the right moments, matched to the respondent's tone palette
  and the style tendencies, at a density that enhances rather than clutters. This runs on the cheap
  judge tier, distinct from the writer model.

These checks are deterministic string work at zero model cost for syntax and counts; only the
expressive quality judgment runs on the judge tier. Keep the palette, density, and mandatory
locations correct here and those gates pass on the first read.
