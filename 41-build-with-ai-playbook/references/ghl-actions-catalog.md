# GHL Actions Catalog -- Skill 41 Reference

Source: https://help.gohighlevel.com/support/solutions/articles/155000002294-what-are-workflow-actions-complete-list-

Each action carries what it does and what to use it for (Use when). The If Else action is the
filtering workhorse and has its own deep treatment in references/ghl-conditions-reference.md and
protocols/trigger-filters-protocol.md.

## Contact Actions
- Create Contact: Adds a new contact. Use when: an inbound webhook or external event needs a record created before anything else runs.
- Find Contact: Locates a contact from provided data. Use when: dedupe or attach incoming data to an existing record.
- Update Contact Field: Sets a standard or custom field. Use when: stamp status, source, or a calculated value for later branching.
- Add Contact Tag: Adds a tag. Use when: mark a milestone or segment, e.g. ZHC-welcome-sent. Tags are the cleanest branching signal.
- Remove Contact Tag: Removes a tag. Use when: clear a state so a contact can re-enter a tag-gated flow.
- Assign to User: Assigns the contact to a user. Use when: route a lead to the right rep on entry.
- Remove Assigned User: Clears the assignment. Use when: return a lead to the pool after a stage.
- Edit Conversation: Marks read, archives, or unarchives a conversation. Use when: keep the inbox clean after automation handles a thread.
- Disable/Enable DND: Toggles Do Not Disturb. Use when: pause or resume outreach for compliance.
- Add Note: Adds a note. Use when: log context for the team without messaging the contact.
- Add Task: Creates a task (contact-less when paired with Inbound Webhook). Use when: queue manual follow-up with an owner and due date.
- Copy Contact: Duplicates the contact into another sub-account. Use when: share a lead across locations.
- Delete Contact: Removes the contact. Use when: honor erasure requests or purge test data. Use with caution.
- Modify Contact Engagement Score: Adjusts the score. Use when: weight behavior to feed score-based routing.
- Add/Remove Contact Followers: Adds or removes followers. Use when: keep specific team members notified on a contact.

## Communication Actions
- Send Email: Sends an email. Use when: deliver newsletters, confirmations, or nurture content.
- Send SMS: Sends an SMS. Use when: time-sensitive nudges and reminders. Respect DND.
- WhatsApp: Sends a WhatsApp message. Use when: the contact prefers WhatsApp or replied via Click-to-WhatsApp.
- Call: Places a phone call. Use when: connect a contact to a rep automatically.
- Messenger: Sends a Facebook message. Use when: continue a Messenger conversation.
- Instagram DM: Sends an Instagram Direct Message. Use when: follow up on IG engagement.
- GMB Messaging: Replies to Google Business Profile messages. Use when: answer map-pack inquiries fast.
- Send Live Chat Message: Responds in live chat. Use when: automate a first response on the website widget.
- Send Slack Message: Posts to Slack (if integrated). Use when: alert an internal channel on a key event.
- Send Internal Notification: Notifies assigned users or contacts. Use when: tell the team about a hot lead or failure.
- Send Review Request: Sends a review request. Use when: ask for a review after a positive outcome.
- Manual Action: Prompts a user to do something by hand. Use when: a human must act before automation continues.
- Conversation AI: Hands inbound conversations to the AI bot. Use when: let the bot qualify or book before a human steps in. Pairs with Skill 38.
- Facebook Interactive Messenger: Responds to Facebook comments. Use when: comment-to-DM capture on FB.
- Instagram Interactive Messenger: Responds to Instagram comments. Use when: comment-to-DM capture on IG.
- Reply in Comments: Replies to comments on FB/IG posts. Use when: publicly acknowledge then move to DM.

## Internal Tools Actions
- If Else: Branches the workflow on conditions into Yes/No and additional branches. Use when: send different contacts down different paths from a single workflow. This is the primary filtering tool. See references/ghl-conditions-reference.md for the full treatment.
- Wait Step: Delays the workflow for a time, until an event, or until a condition. Use when: pace a sequence or wait for a reply/booking before evaluating an If Else.
- Goal Event: Moves contacts forward when they hit a defined goal. Use when: short-circuit a sequence once the desired action happens.
- Go To: Sends contacts to another step or workflow. Use when: reuse a shared sub-sequence or restructure long flows.
- Remove from Workflow: Removes the contact from this or other workflows. Use when: stop messaging once a lead converts or opts out.
- Split: Runs an A/B split test. Use when: test two paths and compare performance.
- Drip Mode: Releases contacts through the workflow in batches. Use when: throttle volume to protect deliverability or staffing.
- Update Custom Value: Updates a location custom value. Use when: change a shared value (note: the Workflow AI Builder does not create custom values, so create them first).
- Arrays: Handles multiple values as a unit. Use when: loop or store list-like data within a flow.
- Text Formatter: Formats text (case, trim, replace). Use when: normalize names or inputs before use.
- Custom Code: Executes custom JavaScript. Use when: a transform or calculation has no native action.

## Send Data Actions
- Webhook/Custom Webhook: Sends data to an external app via POST/GET with headers and a body. Use when: push events to N8N, Make, or any API. See protocols/webhook-configuration-protocol.md.
- Google Sheets: Creates or updates rows in a sheet. Use when: log or sync workflow data to a sheet without code.

## Workflow AI / Eliza Actions
- AI Prompt (GPT Powered): Generates an AI response from a prompt and stores it. Use when: draft a reply or classify text mid-workflow.
- Eliza AI Appointment Booking: Books appointments using AI. Use when: let the AI handle scheduling end to end.
- Send to Eliza Agent Platform: Sends the contact to the Eliza Agent Platform. Use when: hand off to the agent platform for handling.

## Appointments Actions
- Update Appointment Status: Sets an appointment status. Use when: mark showed/no-show to drive branching.
- Generate One Time Booking Link: Creates a single-use booking link. Use when: send a personalized link in a message.

## Opportunities Actions
- Create/Update Opportunity: Creates or updates a deal in a pipeline. Use when: open a deal on a qualified lead or advance its stage.
- Remove Opportunity: Removes a deal. Use when: clean up lost or duplicate deals.

## Payments Actions
- Stripe One-Time Charge: Charges a one-time fee via Stripe. Use when: collect a deposit or fee inside a flow.
- Send Invoice: Sends an invoice. Use when: bill after an estimate is accepted.
- Send Documents and Contracts: Sends a document or contract from a template. Use when: get agreements signed as part of onboarding.

## Marketing Actions
- Add to Custom Audience (Facebook): Adds the contact to a FB custom audience. Use when: retarget a segment with ads.
- Remove from Custom Audience (Facebook): Removes from the audience. Use when: stop retargeting converts.
- Facebook Conversion API: Sends conversion data to Facebook. Use when: feed server-side conversions for better ad optimization.
- Add to Google Analytics: Sends contact data to GA. Use when: track funnel events in analytics.
- Add to Google AdWords: Adds the contact to Google Ads. Use when: build search/display audiences.

## Affiliate Actions
- Add to Affiliate Manager: Adds a new affiliate. Use when: auto-enroll approved partners.
- Update Affiliate: Updates affiliate details. Use when: change tier or payout data.
- Add/Remove from Affiliate Campaign: Moves an affiliate in or out of a campaign. Use when: manage which campaigns a partner promotes.

## Courses Actions
- Course Grant Offer: Grants a course offer. Use when: deliver access after purchase.
- Course Revoke Offer: Revokes a course offer. Use when: pull access on refund or chargeback.

## Communities Actions
- Grant Group Access: Grants access to a community group. Use when: add buyers to a members group.
- Revoke Group Access: Removes access. Use when: offboard churned members.

## IVR Actions
- Gather Input on Call: Collects caller key presses for branching. Use when: build a phone menu.
- Play Message: Plays a message in the IVR. Use when: greet or inform callers.
- Connect to Call: Connects the call to a user or number. Use when: route to the right person.
- End Call: Ends the call. Use when: close a path cleanly.
- Record Voicemail: Records a voicemail. Use when: capture after-hours messages.
