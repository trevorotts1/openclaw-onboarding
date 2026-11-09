# Skill 6 reusable builder requirements

Owner-approved scope, summarized November 8, 2026.

1. Use a shared deterministic executor with named, reusable job recipes to reduce
   repeated AI reasoning, clicks and token cost.
2. Prefer supported API/MCP/Skill 44 operations. For UI-only work, use a ready
   Playwright recipe; recover through the current OpenClaw extension, then
   Agent Browser, then computer control.
3. Support funnels, funnel pages, website pages, split variants, approved HTML
   imports, hosted-app embeds, SEO and CSS.
4. Keep native checkout and one-click upsell components for payment behavior;
   install approved custom design around them.
5. Cover forms, surveys, marketing quizzes, communities, courses, and built-in
   Meeting Rooms. Distinguish API-supported operations from UI-only settings.
6. Reuse the existing Skill 6 authentication and browser lifecycle. Do not add
   another credential store or login implementation.
7. Support Mac and Linux VPS hosts with capability checks and explicit blockers.
8. Preserve Full Width and Allow Rows to take entire width, verify saved output,
   and distinguish editor completion from functional verification.
9. List recipe names, best uses, evidence levels and unfinished profiles honestly.
10. Save code and progress after meaningful changes. Include a continuation file,
    test results and Downloads source checkpoints so a new chat can resume.

The full conversation is excluded from the repository and exported source bundle.
This file records implementation requirements without private operational details.
