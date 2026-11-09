# The DM door: what it is, the agreed flow, and what is and is not proven

<!-- Condensed from the BlackCEO "DM Door handoff" brief and the AI SOP's DM-door chapter. Account identifiers, workflow names, person names and incident narrative were removed on purpose: this file carries the method and the evidence states only. Where it differs from ../spec/SPEC.md or ../safety-boundaries.md, those win. -->

## What the door is

A personal profile cannot fire any automation: no comment trigger, no keyword trigger. A Facebook Page can. So the Bonus comment on a profile post points the reader to the business Page, where automation and the conversation brain live. The link is the bridge from a place with no automation to a place with automation.

The door is a Messenger link in the Bonus comment:

    https://m.me/<PAGE_ID>?ref=pb-<MON><DD>-<YYYY>-<CATEGORY>

Example shape (placeholders only): `pb-OCT23-2026-LISTINGS`.

- `PAGE_ID` is recorded once per tenant on the setup record (digits only, 5 to 20). It is never typed from memory, never copied from an old link, never guessed. The recorder is `shared-utils/routes/page/messenger_link.py` (`record_page_binding`, `build_ref`, `build_messenger_link`).
- `DATE` is the placement's own local date: three-letter month, day, four-digit year.
- `CATEGORY` is one fixed word from the client's fixed category list (for example a destination such as LISTINGS, COMMUNITY, APPOINTMENTS, or a named offer). One spelling forever. The AI never invents a category.
- The link is built when the pack is written, never at posting time, and logged beside the hook in the used-log.
- One link per post, in the Bonus comment only. Never shorten it, never rewrite it.
- The link points at the business Page, never at a personal profile.

## The keyword and the code are different tools

- The keyword is the word the reader sends. It routes the conversation.
- The ref code labels the post, its date and its door. It routes nothing by itself.
- Do not assume a tagged link or code identifies the offer. That is NOT PROVEN: in testing, clicking differently tagged links did not expose the ref in the inspected normalized Convert and Flow data, and the platform does not document the ref as readable or stored. The repository records this as `REF_ATTRIBUTION = "NOT_PROVEN"` (see `35-social-media-planner/references/playbook.md`, section "Bonus Comments"). Never report a Bonus click as attributed.
- The keyword printed in the Bonus call to action must match the pack's routing word. Old keywords are never recycled for a different giveaway (the permanent keyword registry is `DurableStore.register_keyword` in `38-conversational-ai-system/tools/durable_store.py`).

## The agreed flow (governs over any older design description)

1. Personal Facebook posts direct people to the business Messenger conversation and name the keyword to send. The link alone is never assumed to identify what the person wants.
2. Business Page comment-to-DM and Instagram paths are separate routes with their own permissions. They are not described as identical to personal-profile posting.
3. Unknown item: ask, word for word, "Hey! I'm looking forward to sharing what I promised you. What keyword did you see in the post?" If the keyword identifies the item, do not ask again.
4. Deliver the original promised item in chat FIRST. Email or mobile is never a surprise requirement and never gates delivery.
5. Then offer genuinely available additional value. Offer to text a one-time access pass, asking MOBILE first. The pass and the collection must actually exist; a return-access method after redemption must exist before it is claimed.
6. EMAIL is asked ONCE, by SMS with the pass, with the benefit stated (backup access and a guide directory that is easy to find later or open on a computer). Every other email ask stays in the original Messenger or Instagram thread.
7. Follow-up is ONE shared three-reminder sequence across all missing contact information, proposed at 2, 8 and 20 hours, only while the channel permits messaging, stopping after refusal, capture, or the final unanswered message. The approved final mobile request is in `../spec/CLIENT-EXPERIENCE.md`. The timing is a PROPOSED policy (DEC-15) and is not active until an exact policy is adopted.
8. Reuse the profile name and saved details; ask only for what is missing. After delivery, hold a helpful, needs-based conversation and recommend an appropriate next step. People who decline contact details still get the promised item.

The conversation brain is OpenClaw Skill 38. Convert and Flow (GoHighLevel) carries messaging, records, workflows and appointments. Native Convert and Flow AI is never presented as the brain.

## Platform facts relied on (from the platform's own documentation, high confidence)

- A comment earns the Page exactly one private reply, within 7 days of the comment. A comment alone does not open the 24-hour messaging window. The window opens when the person replies; a tap on a link or button does not count as a reply. So a comment opener carries the gift in its body text and ends with a question a person answers by typing.
- There is no conversation-opened or arrival trigger in the workflow product: a workflow cannot speak first when someone merely opens a chat. Conversation AI replies only to inbound messages.
- The Interactive Messenger action is real: at most 3 buttons and 13 quick replies, each tap its own branch, and a mandatory Wait with a Default Timeout branch.
- The Page's own greeting, away message and FAQ automation are separate Meta-side settings; whether an FAQ "Add to Menu" entry renders as a tappable chip and what its tap delivers to the connected platform was never settled.

## Evidence states (from the handoff, restated without identifiers)

| Claim | State |
|---|---|
| A person typing the keyword in Messenger reached the test flow | Worked in testing |
| A tagged m.me ref is visible in normalized Convert and Flow data | NOT PROVEN (not exposed in the inspected data) |
| The "entry button" trial gives a reliable returning-user route | NOT established |
| Test-flow fulfillment and routing | Unfinished in the test flow; welcome wording alone is not a completed system |
| Ice Breaker or FAQ taps arrive as a matchable message | Unproven |
| Unattended monthly posting on a personal profile | Unproven |
| Ongoing monitoring of comments on a personal profile | Unproven |

## Lessons the method keeps

- Research before the first build order, not after.
- Do not assert a capability that is not documented, then walk it back. Label every platform mechanic VERIFIED (named source) or UNVERIFIED (named test that settles it).
- An unverified negative is not a fact. "Not found in the places searched" is not "does not exist". Name the sources checked and the control run.
- Do not hand over a door link as a deliverable before the machinery behind it is proven. The one clean proof is a real reader (not the admin seat) sending the keyword and the welcome landing. A workflow with zero execution history is not evidence that it works.
- Contact lookups for any send start in the CRM of record, not in email or address books, and one person must never become two records or two people become one (never merge by name; see `38-conversational-ai-system/tools/tenant_identity.py`).
