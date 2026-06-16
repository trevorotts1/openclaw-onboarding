# SOP-SLIDE-02: AUDIENCE-FACING ONLY

**Cluster:** Slide-Craft Rules
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 4.3 rule 15 "the slide is not the script", Section 4.3 itself as internal build doctrine)
**Owning role at write time:** Slide Copywriter (the AUDIENCE-vs-SAY tagging pass)
**Owning role at render time:** Slide Image Creator (renders only audience copy; never invents captions, never composites build tokens)
**Routing targets:** spoken content -> Presenter's Speech; working notes -> Presenter's Guide
**Enforced at the gate by:** QC Specialist - Presentations (auto-fail AF-AUD, below)
**Status:** DRAFT for integration. Promotes the existing scored "slide-vs-script separation" criterion into a hard battery with named banned categories.

---

## 1. PURPOSE

The face of a slide is for the AUDIENCE. Nothing else is allowed on it. The forensic reference deck committed every audience-facing violation the operator named: it printed the speaker's spoken lines, the AI's own internal pitch doctrine, narration of the photo, meta-telegraphing of the format (including the literal word "webinar"), credential justification dumps, and raw "[owner to confirm]" build tokens, all on the live face. The reason it shipped is that the only check in the system verified the inverse (that the presenter note did not duplicate the slide), which says nothing about whether forbidden categories are ON the slide. This SOP names the forbidden categories explicitly and makes each one a hard auto-fail. The slide is not the script. The slide is not the build log. The slide is not the AI's reasoning.

---

## 2. THE HARD RULE

Only AUDIENCE COPY may appear on the rendered face of a slide. Audience copy is: the one big idea, expressed as a headline, an optional sub-copy line, and an optional single supporting element (stat, label, or CTA chip), plus the dedicated hook line on its dedicated slides (SOP-SLIDE-03).

The following SIX categories are BANNED from the slide face. Each is routed elsewhere, never deleted-into-the-void unless it is build noise:

1. **Speaker SAY lines.** The words the presenter speaks. These go to the **Presenter's Speech** (word for word) and the **Presenter's Guide** (the beat). They never appear on the slide. Examples from the reference failure case: "When you come into our program, this is where we start." / "Remember this number. We come back to it." / "Stay right here. Something is about to change." / "Hold on. The value is still climbing." / "This is the door. Are you walking through it?"
2. **The AI's own internal pitch doctrine, as a caption.** The build-logic the system reasons with (Section 4.3 of the master SOP) is INTERNAL. It is never slide copy. Examples from the reference failure case: "The lower the price, the greater the value." / "Still climbing in value as the price falls." / "Now let us talk about what you actually pay." / "In the next breath, the real number." These are the sales mechanics, printed where the room can read the trick.
3. **Image narration.** Captions that describe what the photo already shows. The audience can see the picture; narrating it is a tell. Examples from the reference failure case: "Same parent, same child. Two completely different rooms to grow up in." (the photo already shows that) / "Step 1 . Step 2 . Step 3" labeling three notebooks already in frame.
4. **Meta-telegraphing.** Any line that announces the structure, the technique, or the format. Includes the literal word **"webinar"** and any technique self-label. Examples from the reference failure case: "This Is Not Just A Webinar." / "ONE LAST PROOF BEFORE YOU DECIDE." / "Hold onto this line. We will keep coming back to it." / "An intrigue gap, on purpose."
5. **Justification / credential dumps.** Paragraphs that argue why-you-should-believe-us with resumes and clinical credentials. These go to the Presenter's Speech. Examples from the reference failure case: the co-founder-licensed-counselor and founder-years-in-executive-recruitment credential paragraphs; "the co-founder's clinical observation, as a licensed counselor." (Per master rule 1, the T.D. Jakes rule, quote slides carry the NAME ONLY, not the resume.)
6. **Build tokens / placeholders rendered into the image.** Any bracket build token baked onto a rendered slide. Examples from the reference failure case: "[INSERT REAL RESULT - owner to confirm]", "[ENDORSEMENT - owner to confirm]", "[CLIENT WIN - owner to confirm]". A placeholder is a copy-stage device; it must be RESOLVED (filled with the client's real interview-sourced content) or the slide is PULLED before render. A placeholder must never reach a rendered image.

---

## 3. THE ENFORCEMENT CHECK (what auto-fails the slide)

**Write-time gate (Slide Copywriter, SOP self-check before Phase 1Q):** the Copywriter runs the AUDIENCE / SAY tagging pass on every line of every slide. Every line is tagged either `AUDIENCE` (stays on the slide) or `SAY` (routed to the Presenter's Speech and Guide). Any line that is neither audience copy nor a genuine spoken line, meta / doctrine / image-narration, is DELETED from both (it is build noise that belongs nowhere). The pass output is written to working/copy/audience_say_tags.json so QC can verify it ran.

**Gate (QC Specialist) auto-fail code AF-AUD (Audience-Facing). Checked on slides_copy.md at Phase 1Q and on the rendered image at Phase 5/6. Triggers, any one of which fails the slide:**

| Trigger | How it is detected | Failure message |
|---|---|---|
| AUD-1: Speaker SAY line on the slide face | The line is phrased as something the presenter speaks (first person "we"/"I", direct address that narrates the moment, "remember this", "stay right here", "hold on") and appears in HEADLINE/SUB-COPY/SUPPORTING or on the rendered image. | "AF-AUD (AUD-1): slide N carries a speaker SAY line on the face: '[line]'. Move to the Presenter's Speech and Presenter's Guide. The slide keeps only the one big idea." |
| AUD-2: Internal pitch-doctrine caption | The line restates a master Section 4.3 doctrine principle as a caption (value-vs-price mechanics, "the lower the price the greater the value", "in the next breath the real number"). | "AF-AUD (AUD-2): slide N prints internal build doctrine as a caption: '[line]'. Section 4.3 is build-logic, never slide copy. Delete from the slide." |
| AUD-3: Image-narration caption | The caption describes what the photo already depicts (cross-checked against the slide's image brief). | "AF-AUD (AUD-3): slide N caption narrates the image: '[line]'. The audience can see it. Delete the caption." |
| AUD-4: Meta-telegraphing or the word "webinar" or a technique self-label | Literal string match on "webinar" (case-insensitive) anywhere in slide copy or rendered text; plus detection of format/structure/technique announcements ("this is not just", "one last proof", "an intrigue gap", "hold onto this line"). | "AF-AUD (AUD-4): slide N telegraphs the structure / uses a banned meta line: '[line]'. The word 'webinar' and all technique labels are banned on the face. Replace with a neutral, non-telegraphing label or delete." |
| AUD-5: Justification / credential dump | A credential or resume paragraph (licensed, clinical, years in, certified) rendered as body copy on the face. | "AF-AUD (AUD-5): slide N dumps credentials on the face: '[line]'. Move to the Presenter's Speech. Quote slides carry the NAME ONLY (master rule 1)." |
| AUD-6: Bracket / placeholder / build token on a RENDERED slide | Regex on rendered text for `\[.*\]`, the strings "owner to confirm", "INSERT", "TBD", "PLACEHOLDER", "CLIENT WIN", "ENDORSEMENT", "REAL RESULT". Any match on a rendered image = fail. (At copy stage a `[CLIENT TO SUPPLY]` placeholder is allowed; it must be resolved or the slide pulled before render. It is NEVER allowed on a rendered face.) | "AF-AUD (AUD-6): slide N rendered with a build token on the face: '[token]'. Fill with the client's real interview-sourced content or pull the slide. A bracket token must never be composited into an image." |

AF-AUD-6 (the rendered placeholder) is the single most embarrassing tell and is double-flagged: it also trips the design-craft finishing-failure rule and the master QC ruleset (see MASTER-QC-AUTOFAIL-RULESET.md). It blocks final status on its own.

---

## 4. PASS vs FAIL EXAMPLES (drawn from the actual reference-case defects)

**FAIL (reference failure case slide 44):** headline "This Is Not Just A Webinar." -> AF-AUD-4 (the word "webinar" plus a meta announcement).
**PASS:** delete the meta framing entirely; if the slide needs a close label, use a neutral non-telegraphing line that states the one idea, not the format.

**FAIL (reference failure case slide 10):** caption "Same parent, same child. Two completely different rooms to grow up in." over a photo of one parent and child in two rooms -> AF-AUD-3 (narrates the image).
**PASS:** let the image carry it; the slide keeps only the one-idea headline, no caption.

**FAIL (reference failure case slide 34):** caption "The lower the price, the greater the value." -> AF-AUD-2 (internal doctrine printed as copy).
**PASS:** the doctrine drives how the price slide is BUILT (the drop adds value); it is never written on the slide. Delete.

**FAIL (reference failure case slides 28/30/35/38/40/42):** rendered images containing "[CLIENT WIN - owner to confirm]" and "[INSERT REAL RESULT - owner to confirm]" -> AF-AUD-6 on every one.
**PASS:** fill each tile with the client's real interview-sourced win (name + result), or, if the interview has not yet supplied it, the slide stays at the copy stage with a `[CLIENT TO SUPPLY]` placeholder and is NOT rendered until resolved.

**FAIL (reference failure case slide 9):** "When you come into our program, this is where we start." on the face -> AF-AUD-1 (speaker SAY line).
**PASS:** that sentence is exactly what the presenter SAYS; route it to the Presenter's Speech. The slide shows the one idea (where the program starts) with a handful of words.

---

## 5. ESCALATION / REPAIR PATH

1. The Copywriter's AUDIENCE/SAY tagging pass is the first line of defense and runs at write time. If audience_say_tags.json is missing at Phase 1Q, the gate fails the whole deck for a missing required artifact (the pass did not run).
2. On any AF-AUD trigger, QC routes the repair: SAY lines and credentials go to the **Presenter's Speech Writer** (and the beat to the **Presenter's Guide Specialist**); meta / doctrine / image-narration lines are DELETED (they belong nowhere); placeholders go to the **Director** to source the real content from the client interview or to authorize pulling the slide.
3. AF-AUD-6 on a rendered image always routes back through the **Slide Image Creator** with the instruction to never composite the token, plus a Director flag because a placeholder reaching render means the copy gate let an unresolved placeholder through to Phase 2.
4. Re-run AF-AUD on the revised slide only. Loop up to 3 times (shared Phase 1Q / Phase 5 loop budget). On the 4th failure, escalate to the Director and the ROLE-16 Healer per the existing QC SOP 9.4.
5. Standing rule for the Slide Image Creator: render ONLY the three approved copy blocks plus the dedicated hook line where applicable. Never invent a step list, a credential paragraph, a caption that describes the photo, or any text not present in slides_copy.md. Never composite a bracket token. This is also enforced in the slide-image-creator role file.
