# Posting routes, how approvals really work, and the 30-day plan

<!-- Condensed from the BlackCEO "What We Discovered: Posting, Approvals, and the 30-Day Plan" teaching note, which recorded two live posting tests on a personal profile in October 2026. Test post links, account names, dates of the individual runs and person names were removed on purpose; the method, the lesson and the evidence states are kept. Where this differs from ../spec/SPEC.md or ../safety-boundaries.md, those win. -->

## What was tested, and why

The daily move is simple to say and hard to run: one billboard post on a personal Facebook profile, then the numbered comments under it, in order, immediately. To run every day without the owner babysitting it, two things had to be learned. First, can an agent run the whole pattern alone. Second, what will the approval system demand along the way.

Two routes were tried on a personal profile, as tests only (not real content).

## Route 1: the platform connector

- The connector posted to the personal profile and its test comment went live. It works.
- The catch is fatal to the daily design: the connector demands a fresh approval tap for every single post and every single comment. Seven comments plus the post is eight taps a day, every day. There is no standing approval on this route and no bulk action.

## Route 2: the signed-in browser (limited test)

- In the owner's own signed-in browser session, the post went live on a solid purple background, then the numbered comments went up one at a time in order, a few seconds apart, in about two minutes in total. After the last comment the post was reloaded fresh and verified: the right comment count, the right order, every comment visible.
- No approval card, login wall or verification screen interrupted the run once the session was signed in. Work inside a signed-in session behaves like the owner's own hands on the keyboard, because to the platform that is what it is.
- Status of this route: demonstrated in a limited test only. Unattended monthly operation across a full month has NOT been run and remains unproven. Ongoing monitoring of comments on a personal profile also remains unproven. SPEC.md says the same: one reported browser test is not a month-long service.

## How approvals really work in this system

- "Always allow" on a send approval saves a grant tied to the ACCOUNT and the ACTION (for example, sending email from one account). It is never tied to a recipient.
- The saved grant is marked permanent, yet new runs can still raise fresh approval cards. Some write actions (platform connector writes) offer no standing option at all.
- The browser route raises no cards because the actions happen inside the owner's own signed-in session.
- The lesson: an approval tap approves a KIND of action from an account, once, in that moment. It does not create a durable "this person is approved" rule, whatever the button says. Judge every plan against that model.

## The method the browser test demonstrated (repeatable steps, limited evidence)

1. Sign in once in the browser with the owner's saved login (a texted code may be needed once).
2. Open the post composer on the profile.
3. Set the solid brand-color background.
4. Paste the post text exactly as approved and publish.
5. Open the published post.
6. Add the numbered comments one at a time, in order, a few seconds apart. Comments 1 to N are the reveal; the Bonus is posted last and unnumbered.
7. Reload the post fresh. Verify the comment count and the order.
8. Report the post link to the owner.

The rule over the whole method: verify on a fresh load every time. An action receipt alone is never proof. The receipt says the action was accepted; the fresh load shows what the world actually sees. (In code this is the "true receipt" rule in `shared-utils/receipts/publication_receipts.py`.)

## The approval model going forward

- One approval matters: the owner approves 30 days of content, one time, in one monthly approval. The plan is for scheduled runs to post each day's approved pack afterward with no further taps. That unattended monthly operation is planned and unproven.
- Two hard rules protect the design:
  1. Never post content the owner has not approved.
  2. Never post a pack whose Bonus comment still carries a placeholder where a link belongs.
- The order of operations is fixed: content first, one monthly approval, then the daily runs under that plan. Posting stays unscheduled until the owner gives the word. The daily run time is the owner's choice.

## The 30-day plan

- Content is prepared as 30 days for one monthly approval: one pack per day, approved as a single monthly set. The first banked batch awaits that approval; nothing in a banked batch has been posted.
- Every pack follows the grammar the playbook teaches: a solid-color billboard with a numbered promise; the reveal comments deliver the promised items one per comment, written out in full; the Bonus comment is last and unnumbered and carries the two Convert and Flow doors (list signup and community).
- The single blocker named in the test: every Bonus comment carried two placeholders because the owner had not yet supplied the two real links. Under the hard rules no pack posts until real links replace the placeholders.

## Findings from the DM entry tests (unchanged evidence states)

- Typed keyword entry worked in the test.
- Clicking differently tagged Messenger links did not expose the ref in the inspected Convert and Flow data, so no plan may assume a tagged link identifies the offer.
- The entry-button trial did not establish a reliable returning-user route.
- The test flow had unfinished fulfillment and routing. Welcome wording alone is not a completed system.
- The conversation brain is OpenClaw Skill 38. Convert and Flow handles messaging, records, workflows and appointments. Native Convert and Flow AI is not the brain.
