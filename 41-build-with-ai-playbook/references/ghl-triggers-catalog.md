# GHL Triggers Catalog -- Skill 41 Reference

Source: https://help.gohighlevel.com/support/solutions/articles/155000002292-a-list-of-workflow-triggers

Every trigger entry below carries three things the agent needs: what fires it, what to use it for
(Use when), and the filters that narrow who actually enters. Filters are optional but strongly
recommended on almost every trigger. For the mechanics of setting filters correctly, the agent MUST
follow protocols/trigger-filters-protocol.md. A trigger with no filter fires for everyone, which is
the single most common cause of runaway or mis-targeted workflows.

## Contact Triggers
- Contact Created: Fires when a new contact record is added. Use when: onboard or welcome every new lead the moment they land. Filters: source, tag, assigned user.
- Contact Changed: Fires when specified contact fields change to defined values. Use when: react to a tag being added or a custom field being set (it does NOT detect removals). Filters: which field changed (tag, custom field, DND), and the target value. Multiple filters can track several change types at once.
- Contact Tag: Fires when a selected tag is added or removed. Use when: a tag is your "start this sequence" switch, e.g. tag ZHC-webinar-registered starts a reminder series. Filters: specific tag(s), added vs removed.
- Contact DND: Fires when the Do Not Disturb preference is toggled. Use when: stop outreach the instant a contact opts out, or re-engage when DND is lifted. Filters: DND status (enabled/disabled), channel (email/SMS/call), direction (inbound/outbound).
- Birthday Reminder: Fires on or around a contact birthday using an offset. Use when: send a birthday offer a set number of days before the date. Filters: day offset.
- Custom Date Reminder: Fires before, on, or after a selected date field. Use when: drive renewal, anniversary, or policy-expiry reminders off any date field. Filters: which date field, offset direction and amount.
- Note Added: Fires when a new note is added to a contact. Use when: alert a manager when staff log a note. Filters: none beyond the event.
- Note Changed: Fires when an existing note is edited. Use when: audit changes to logged notes. Filters: none beyond the event.
- Task Added: Fires when a task is created for a contact. Use when: notify the assignee that work was queued. Filters: assigned user.
- Task Reminder: Fires when a task reminder time is reached. Use when: nudge the owner just before a task is due. Filters: assigned user.
- Task Completed: Fires when a task is marked complete. Use when: advance a process once a manual step is done. Filters: assigned user.
- Contact Engagement Score: Fires when an engagement score meets a rule. Use when: route hot leads to sales the moment they heat up. Filters: score threshold and direction.

## Events Triggers
- Inbound Webhook: Fires when data is received at the workflow webhook URL. Use when: an external app (Zapier, a form, an order system) should kick off automation, including contact-less runs. Filters: payload-field matching once a sample is captured.
- Scheduler: Fires on a time-based schedule with no contact attached. Use when: run a recurring batch job, daily digest, or maintenance task. Filters: schedule definition.
- Customer Replied: Fires when a contact replies on any connected channel. Use when: stop a nurture sequence the moment someone responds, or alert a rep. Filters: channel (SMS, email, etc.).
- Email Events: Fires on email delivered, opened, clicked, bounced, complained, or unsubscribed. Use when: branch follow-up on engagement, or suppress bounced addresses. Filters: event type, specific campaign/email.
- Call Details: Fires when a call log matches selected details or outcomes. Use when: follow up on missed or completed calls by outcome. Filters: call status, direction, duration.
- Conversation AI Trigger: Fires when a configured Conversation AI event occurs. Use when: hand a thread to or from the AI bot at a defined point. Filters: the configured AI event.
- Custom Trigger: Fires from a custom event for non-standard cases. Use when: nothing built-in fits and another system signals a custom event. Filters: custom event match.
- Form Submitted: Fires when a selected HighLevel form is submitted. Use when: start intake the instant a form is completed. Filters: specific form.
- Survey Submitted: Fires when a selected survey is submitted. Use when: route based on survey completion. Filters: specific survey.
- Trigger Link Clicked: Fires when a contact clicks a defined trigger link. Use when: register interest from a link click and branch accordingly. Filters: specific trigger link.
- Facebook Lead Form Submitted: Fires when a Facebook Lead Ad form is received. Use when: instant-follow-up on paid social leads. Filters: specific page/form.
- TikTok Form Submitted: Fires when a TikTok lead form is submitted. Use when: speed-to-lead on TikTok ads. Filters: specific form.
- LinkedIn Lead Form Submitted: Fires when a LinkedIn Lead Gen form is received. Use when: route B2B leads to sales fast. Filters: specific form.
- Google Lead Form Submitted: Fires when a Google Ads lead form submission is received. Use when: follow up on search-ad leads. Filters: specific form.
- Video Tracking: Fires when a viewer reaches a chosen percentage of a video. Use when: trigger an offer once someone watches enough to be warm. Filters: video, percentage watched.
- Number Validation: Fires based on a phone-number validation result. Use when: only send SMS to numbers validated as mobile, to cut wasted spend. Filters: validation result.
- Messaging Error - SMS: Fires when an outbound SMS returns a specific error. Use when: auto-handle carrier failures or fall back to email. Filters: error type.
- Funnel/Website PageView: Fires when a contact views a specified page, URL, or UTM. Use when: retarget visitors who hit a pricing or checkout page. Filters: page/URL/UTM match.
- Quiz Submitted: Fires when a selected quiz is submitted. Use when: score and segment quiz takers. Filters: specific quiz.
- New Review Received: Fires when a new review arrives. Use when: thank reviewers or alert the team on low ratings. Filters: rating, source.
- Prospect Generated: Fires when a new prospect record is created. Use when: work prospecting-sourced leads separately. Filters: source.
- Click To WhatsApp Ads: Fires when an inbound WhatsApp thread starts from an ad. Use when: instantly engage WhatsApp ad responders. Filters: ad/campaign.
- External Tracking Event: Fires when a named client or server-side tracking event is captured. Use when: act on events sent from your own analytics layer. Filters: event name.

## Appointments Triggers
- Customer Booked Appointment: Fires when a customer books. Use when: send confirmations, prep, and reminder sequences. Filters: calendar, appointment type. (Required if you want appointment filters inside a later If/Else.)
- Appointment Status: Fires on status changes (booked, confirmed, rescheduled, canceled, no-show, showed). Use when: branch follow-up by outcome, e.g. re-engage no-shows. Filters: calendar, status.
- Service Booking: Fires when a booking is made using Services v2. Use when: automate service-based scheduling. Filters: service, calendar.
- Rental Booking: Fires when a rental reservation is booked. Use when: drive rental confirmations and checkout reminders. Filters: rental, date.

## Opportunities Triggers
- Opportunity Created: Fires when a new opportunity is created. Use when: notify sales on new deals, especially high value. Filters: pipeline, assigned user, lead value, tag (tag supports Any of / None of).
- Opportunity Status Changed: Fires when an opportunity status changes (open, won, lost, abandoned). Use when: trigger won/lost playbooks. Filters: pipeline, status.
- Opportunity Changed: Fires when selected opportunity fields change (value, stage, assignment, custom fields). Use when: catch broader edits that Status Changed misses, e.g. high-value reassignments. Filters: pipeline, the field changed.
- Pipeline Stage Changed: Fires when an opportunity moves to a different stage. Use when: stage-specific outreach, e.g. send a contract when it hits Negotiation. Filters: in pipeline, from/to stage, assigned user, lead value.
- Stale Opportunities: Fires when opportunities meet an inactivity rule. Use when: re-engage deals with no movement for N days. Filters: pipeline, days stale.

## Payments Triggers
- Payment Received: Fires when a payment is successfully captured. Use when: deliver product access and receipts on payment. Filters: product, amount.
- Invoice: Fires on invoice lifecycle events (created, sent, due, paid, void). Use when: chase unpaid invoices or confirm paid ones. Filters: event, status.
- Order Form Submission: Fires when a checkout or order form is submitted. Use when: fulfill and onboard buyers. Filters: product/form.
- Order Submitted: Fires when an order is successfully submitted at checkout. Use when: confirm orders and start fulfillment. Filters: product.
- Subscription: Fires on subscription create, update, pause, resume, or cancel. Use when: run dunning, win-back, or access changes. Filters: product, status (active, failed, trial, expired).
- Refund: Fires when a refund is issued. Use when: revoke access and log the reason. Filters: product, amount.
- Documents and Contracts: Fires on document status events (sent, viewed, signed, declined). Use when: progress deals as contracts are signed. Filters: status.
- Estimates: Fires on estimate events (sent, accepted, declined). Use when: convert accepted estimates to invoices. Filters: status.
- Coupon Code Applied: Fires when a coupon is applied to a purchase. Use when: track promo performance. Filters: coupon.
- Coupon Code Redeemed: Fires when a coupon is redeemed. Use when: reward or cap promo usage. Filters: coupon.
- Coupon Redemption Limit Reached: Fires when a coupon hits its redemption limit. Use when: auto-expire or swap a promo. Filters: coupon.
- Coupon Code Expired: Fires when a coupon expires. Use when: notify and offer a replacement. Filters: coupon.

## Ecommerce Stores Triggers
- Order Fulfilled: Fires when a store order is fulfilled. Use when: send shipping/access confirmations. Filters: product/store.
- Abandoned Checkout: Fires when a checkout session is abandoned. Use when: run cart-recovery sequences. Filters: product, value.
- Product Review Submitted: Fires when a product review is submitted. Use when: thank reviewers or flag low scores. Filters: product, rating.
- Shopify Order Placed: Fires when a Shopify order is placed. Use when: sync Shopify buyers into nurture. Filters: product.
- Shopify Abandoned Cart (Deprecating Soon): Fires when a legacy Shopify cart is abandoned. Use when: legacy stores only; migrate to Abandoned Checkout. Filters: product.
- Shopify Order Fulfilled (Deprecating Soon): Fires when a legacy Shopify order is fulfilled. Use when: legacy stores only. Filters: product.

## Courses / Memberships Triggers
- New Signup: Fires when a user signs up for a course or offer. Use when: welcome and orient new members. Filters: offer.
- Offer Access Granted: Fires when access to an offer is granted. Use when: kick off onboarding for the specific offer. Filters: offer.
- Offer Access Removed: Fires when access to an offer is removed. Use when: run win-back or exit surveys. Filters: offer.
- Product Access Granted: Fires when access to a product is granted. Use when: deliver product-specific onboarding. Filters: product.
- Product Access Removed: Fires when access to a product is removed. Use when: handle downgrades or churn. Filters: product.
- Product Started: Fires when a learner starts a product or course. Use when: encourage momentum early. Filters: product.
- Product Completed: Fires when a learner completes a product or course. Use when: upsell the next course or request a review. Filters: product.
- Category Started: Fires when a learner starts a course category. Use when: section-level encouragement. Filters: category.
- Category Completed: Fires when a learner completes a category. Use when: unlock the next section or reward. Filters: category.
- Lesson Started: Fires when a learner starts a lesson. Use when: granular progress nudges. Filters: lesson.
- Lesson Completed: Fires when a learner completes a lesson. Use when: drip the next lesson. Filters: lesson.
- User Login: Fires when a learner logs in to the portal. Use when: re-engage based on activity or inactivity. Filters: none beyond the event.

## Affiliate Triggers
- Affiliate Created: Fires when a new affiliate account is created. Use when: onboard affiliates with assets and terms. Filters: campaign.
- Affiliate Enrolled In Campaign: Fires when an affiliate is added to a campaign. Use when: send campaign-specific materials. Filters: campaign.
- New Affiliate Sales: Fires when a sale is attributed to an affiliate. Use when: notify and credit affiliates. Filters: campaign, amount.
- Lead Created: Fires when a new affiliate-attributed lead is created. Use when: track affiliate top-of-funnel. Filters: campaign.

## Communities Triggers
- Group Access Granted: Fires when a member is granted group access. Use when: welcome members into a group. Filters: group.
- Group Access Revoked: Fires when group access is revoked. Use when: handle removals and feedback. Filters: group.
- Private Channel Access Granted: Fires when private channel access is granted. Use when: orient members to a channel. Filters: channel.
- Private Channel Access Revoked: Fires when private channel access is revoked. Use when: manage channel offboarding. Filters: channel.
- Community Group Member Leaderboard Level Changed: Fires when a member leaderboard level changes. Use when: reward gamified milestones. Filters: level.

## Conversations and Social Triggers
- Facebook - Comments On A Post: Fires when comments are added to a selected Facebook post. Use when: auto-reply or DM commenters on an ad/post. Filters: specific post.
- Instagram - Comments On A Post: Fires when comments are added to a selected Instagram post. Use when: comment-to-DM lead capture. Filters: specific post.
- TikTok - Comments On A Video: Fires when comments are added to a selected TikTok video. Use when: engage TikTok commenters. Filters: specific video.
- Transcript Generated: Fires when a call or conversation transcript is created. Use when: summarize or QC conversations downstream. Filters: none beyond the event.

## Other Triggers
- Start IVR Trigger: Fires when a caller reaches a configured IVR entry or option. Use when: branch inbound phone journeys. Filters: IVR option.
- Certificates Issued: Fires when a course certificate is generated. Use when: deliver and celebrate certificates. Filters: course.
