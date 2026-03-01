# SuperDesign - Examples

This document shows real examples of SuperDesign in action. Each example includes what you would type, what happens, and what to expect. These are practical scenarios you are likely to encounter.


## Example 1: Design a Landing Page from Scratch (Web App)

**Scenario:** You need a landing page for a wellness membership community at $197/month.

**What you type in the SuperDesign chatbox:**

"Design a premium landing page for a wellness membership community. Color palette: deep plum (#5B2E91), cream (#FFF8F0), and gold (#C9A84C). Modern serif for headlines, clean sans-serif for body text. Sections in this order: 1) Hero with bold headline and CTA button, 2) Three benefit cards with icons, 3) Testimonial carousel with three quotes, 4) Pricing section showing $197/month membership, 5) FAQ accordion with 5 questions, 6) Footer with social links and email signup. Design feel: warm, premium, luxurious with lots of whitespace."

**What happens:** SuperDesign generates a complete page design on the canvas within 15 to 60 seconds. You will see a full-length page with all six sections rendered in your specified colors.

**What to do next:** Review the design. Then generate variations:

"Create a branch with a darker background and bolder typography"

Then another:

"Create a branch with more organic, rounded shapes and softer colors"

Compare the three versions (original plus two branches), pick the best one, and refine it.


## Example 2: Clone a Website and Redesign It (Chrome Extension)

**Scenario:** You found a coaching website you love at some-coaching-site.com and want something similar for your brand.

**Step by step:**

1. Open Chrome and navigate to some-coaching-site.com.
2. Scroll all the way down to load all content, then scroll back up.
3. Click the SuperDesign extension icon in your toolbar.
4. Click "Clone page."
5. Wait 10 to 20 seconds for the import.
6. You are now on app.superdesign.dev with the cloned design on your canvas.
7. In the chatbox, type:

   "Keep the overall layout but change the color palette to deep burgundy, cream, and gold. Redesign this for a wellness coaching brand targeting professional Black women. Make it feel warm and premium."

8. The design updates with your new colors and style while keeping the layout structure.

**What you end up with:** A professional design based on a proven layout, customized for your brand.


## Example 3: Build a Complete Sales Funnel (CLI)

**Scenario:** You need four pages - opt-in landing page, sales page, checkout page, and thank you page - all matching the same design style.

**Step 1: Extract the brand guide from a reference site:**

   superdesign extract-brand-guide --url https://reference-site-you-like.com --json > .superdesign/design-system.md

**Step 2: Create the project:**

   superdesign create-project --title "Complete Sales Funnel" --set-project-prompt-file .superdesign/design-system.md --json

Save the draftId from the response.

**Step 3: Generate all four pages at once:**

   superdesign execute-flow-pages --draft-id YOUR_DRAFT_ID --pages '[
     {"title": "Opt-In Landing Page", "prompt": "Lead capture with email form, freebie headline, 3 benefits"},
     {"title": "Sales Page", "prompt": "Long-form sales with problem, solution, testimonials, pricing at $197/month, FAQ"},
     {"title": "Checkout Page", "prompt": "Clean checkout with order summary, payment form placeholder, trust badges"},
     {"title": "Thank You Page", "prompt": "Celebration page with next steps, community invite, social sharing"}
   ]' --json

**Step 4: Review all pages in the gallery:**

   superdesign gallery

This opens an interactive HTML gallery in your browser where you can see all four pages side by side.

**Step 5: Export each page:**

   superdesign get-design --draft-id LANDING_DRAFT_ID --output ./funnel/landing.html
   superdesign get-design --draft-id SALES_DRAFT_ID --output ./funnel/sales.html
   superdesign get-design --draft-id CHECKOUT_DRAFT_ID --output ./funnel/checkout.html
   superdesign get-design --draft-id THANKYOU_DRAFT_ID --output ./funnel/thankyou.html


## Example 4: Generate Three Variations of a Page (CLI)

**Scenario:** You have a landing page design but want to see three different style directions before committing.

   superdesign iterate-design-draft --draft-id YOUR_DRAFT_ID -p "Dark theme with neon accents and bold sans-serif type" -p "Soft pastels with rounded corners and gentle serif headlines" -p "Minimal black and white with one bold accent color" --mode branch --json

**What happens:** Three separate design branches are created, one for each prompt. Each branch is independent - your original design stays untouched.

**How to review them:**

   superdesign gallery

Pick your favorite, then refine it:

   superdesign iterate-design-draft --draft-id CHOSEN_DRAFT_ID -p "Add more breathing room between sections and make the CTA buttons larger" --mode replace --json


## Example 5: Hand Off to OpenClaw for Content Injection

**Scenario:** You have exported your SuperDesign HTML file and style.md. Now you want OpenClaw to add your real content.

**What you say to OpenClaw (via WhatsApp, Telegram, or whatever channel you use):**

"I have a website design exported from SuperDesign. The HTML file is at ~/Desktop/my-landing-page.html and the style guide is at ~/Desktop/my-style.md. I need you to:
- Read both files
- Replace the placeholder headline with: 'Drop the Cape. Breathe Again.'
- Replace the placeholder subheadline with: 'A sanctuary for professional women who are done performing strength and ready to experience rest.'
- Change the CTA button text to 'Join the Sanctuary'
- Replace the three benefit cards with these: 1) Monthly live breathwork sessions, 2) Private community of like-minded women, 3) On-demand wellness library
- Keep all the existing styling exactly as it is
- Save the final version to ~/Desktop/sanctuary-final.html"

**What OpenClaw does:** It reads both files, makes the exact changes you requested, keeps all the CSS and layout intact, and saves the finished version.


## Example 6: Use the style.md to Build Additional Pages

**Scenario:** You designed your homepage in SuperDesign but need three more pages (About, Services, Contact) that match the same look.

**What you say to OpenClaw or Claude:**

"Here is my style.md file from SuperDesign [paste the content or provide file path]. This is my brand's design system. Now build me the following pages using these exact design rules:
- An About page with my bio, mission statement, and credentials
- A Services page with three service cards showing my coaching packages
- A Contact page with a booking form placeholder and my social media links

Make sure every page matches the colors, fonts, and spacing in the style.md."

**Why this works:** The style.md contains every design rule, so the AI can build pages that look like they came from the same designer - without going back to SuperDesign for each one.


## Example 7: Clone Individual Components from Multiple Sites

**Scenario:** You love the navigation bar from one website, the hero section from another, and the pricing table from a third.

1. Go to Site A in Chrome. Click the SuperDesign extension. Hover over the navigation bar until it highlights. Click to capture just that component.

2. Open a new tab. Go to Site B. Click the SuperDesign extension. Hover over the hero section. Click to capture it.

3. Open another tab. Go to Site C. Click the SuperDesign extension. Hover over the pricing table. Click to capture it.

4. In SuperDesign, you now have three separate components. Use the chatbox to combine them:

   "Combine these three components into one cohesive landing page. Unify the color scheme to deep plum and gold. Match the typography across all sections. Add a testimonial section and a footer."

**What you end up with:** A custom page built from the best pieces of three different websites, all unified into one cohesive design.


## Example 8: Design Prompt for a Lead Capture Page

**A ready-to-use prompt you can paste directly into SuperDesign:**

"Design a premium lead capture landing page for Breathe Again Coaching.

Colors: deep plum (#5B2E91) as primary, cream (#FFF8F0) as background, gold (#C9A84C) for CTA buttons.

Typography: Modern serif for headlines, clean sans-serif for body text.

Sections in this order:
1. Hero - Bold headline about the free resource, subheadline explaining what they will learn, email opt-in form with name and email fields, CTA button that says 'Get Your Free Guide'
2. What is inside - 3-4 bullet points or cards showing what the free resource covers, with icons
3. Who this is for - Brief paragraph describing the ideal person for this resource
4. About the creator - Small section with founder name, brief 2-sentence bio, headshot placeholder
5. Minimal footer - copyright text and privacy policy link only

Design feel: Warm and inviting. No navigation menu - this is a single-purpose page. The email form and CTA button should be the most prominent elements. Generous whitespace. Mobile-first responsive design.

Target audience: Professional women 38+ dealing with burnout who want practical tools for self-care."


## Example 9: Design Prompt for a Membership Sales Page

**Another ready-to-use prompt:**

"Design a premium membership sales page for The Soft Life Sanctuary - a monthly membership at $197/month.

Colors: deep plum (#5B2E91) as primary, cream (#FFF8F0) as background, gold (#C9A84C) for CTA buttons.

Typography: Elegant serif headlines, clean sans-serif body text.

Sections in this order:
1. Hero - Bold headline about community and transformation, subheadline about belonging, CTA button: 'Join the Sanctuary'
2. The problem - Section addressing isolation, doing it alone, missing support
3. The solution - Introduce the membership with description
4. What is inside - 6-8 feature cards showing membership benefits
5. Testimonials - 3 member testimonials with quotes
6. Your host - Founder bio with headshot placeholder and credentials
7. Pricing - Single pricing card, $197/month, feature list, CTA button, cancel anytime note
8. FAQ - 6-8 questions
9. Final CTA - Emotional closing plus CTA button
10. Footer

Design feel: Warm, premium, inviting. Think spa lobby, not corporate office. Generous whitespace. Rounded corners. Mobile-responsive."


## Example 10: Deploying to Go High Level (GHL) Step by Step

**Scenario:** You have a finished HTML export from SuperDesign and need to put it into GHL.

1. Log in to your GHL (or Convert and Flow) account.
2. Click "Sites" in the left sidebar, then click the "Funnels" tab.
3. Click "+ New Funnel" in the top right.
4. Choose "Blank Funnel" (not AI, not Templates).
5. Give it a name like "Wellness Landing Page" and click "Create."
6. Click "Add New Step" to create your first page.
7. Give it a step name (like "Landing Page") and a URL path (like /landing).
8. Click "Create Funnel Step."
9. Click on the step you just created, then click "Create from Blank."
10. Wait 5 seconds for the builder to load. Do not click anything during this time.
11. Close the "Ask AI" popup on the left by clicking the X.
12. Click the "Blank Section" button in the middle of the canvas.
13. In the blank section, hover over the "+" icon and click "Add."
14. Scroll all the way down in the left panel. Under "Custom," click "Code."
15. Now set the section to full width: hover slowly between elements until you see a green border (not blue). Click the green border. In the right panel, turn on "Allow rows to take entire width."
16. Click the blue "Custom HTML/JavaScript" box in the canvas.
17. Click "Open Code Editor" in the right panel.
18. Paste your entire SuperDesign HTML export into the code editor.
19. Click "Save" in the code editor.
20. Click the floppy disk icon (top right) to save the page.
21. Click the eyeball icon to preview.
22. Check that everything looks correct on desktop, tablet, and mobile sizes.
23. If anything looks wrong, go back to the code editor and fix the HTML. Common issues:
    - Page is narrow: You forgot to turn on "Allow rows to take entire width" in step 15.
    - Styles missing: Make sure all CSS is in a style tag inside the code block.
    - Scripts broken: Make sure script tags are separate from div tags.


## Example 11: Asking the Right Questions Before Designing

**If you are an AI agent helping someone design a page, always ask these five questions first:**

1. "What kind of page do you need? For example: a landing page, a sales page, a booking page, or a full website?"

2. "Do you have specific brand colors? Hex codes are perfect, but even 'purple and gold' works."

3. "Where will this page be hosted? For example: Go High Level, WordPress, Shopify, Vercel, or somewhere else?" (This determines the export format.)

4. "When someone lands on this page, what is the ONE thing you want them to do? Book a call? Join a membership? Download a freebie?"

5. "Describe the person who will see this page. What are they struggling with? What do they want?"

With answers to these five questions, you have everything you need to write a strong SuperDesign prompt.


## Quick Tips

- Be specific in your prompts. "Design a landing page" gives you something generic. Include colors, sections, audience, and feel for dramatically better results.
- Always export the style.md, even if you are not using the code directly. It is the most valuable file for working with any AI tool.
- Use extract-brand-guide on reference sites before designing. It captures the design DNA (colors, fonts, spacing) without using cloning credits.
- One instruction at a time in the Web App. Submit one change, wait for it to finish, then submit the next.
- Never deliver placeholder content. Your job is not done until all "Lorem ipsum" and "Your headline here" text has been replaced with real content.
