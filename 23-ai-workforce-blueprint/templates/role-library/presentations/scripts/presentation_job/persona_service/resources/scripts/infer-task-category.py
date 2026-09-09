#!/usr/bin/env python3
"""
Infer a task category from the task title and description.

Categories are coarse-grained — they group similar tasks for stickiness
(persona_assignment table in v2.0 Ch 13). When two tasks share a category,
they share their assigned persona unless score differential ≥ 0.15.

Returns: lowercase slug. Defaults to "general" if no clear match.
"""
import re
import sys


CATEGORY_KEYWORDS = {
    "email-outreach":      ["email", "outreach", "follow-up", "follow up", "cold email", "send to", "newsletter"],
    "social-post":         ["social", "instagram", "linkedin", "facebook", "twitter", "tiktok", "pinterest", "post on", "reel", "story"],
    "content-write":       ["article", "blog", "essay", "long form", "long-form", "story", "write a", "writeup"],
    "video-script":        ["script", "video", "reel script", "ad creative", "vsl", "ad copy"],
    # video-edit / montage: the PRODUCTION-craft category. Distinct from video-script
    # (which is copy/writing). These keywords describe the hands-on edit, the cut,
    # the montage rhythm, and footage assembly — NOT writing a script. They route to
    # the production-domain persona pool {editing, montage, visual-storytelling} so an
    # "edit the montage / pace the cut" task surfaces the editing-craft persona, while
    # "write the video script/hook" (which has none of these tokens) keeps routing to
    # the copy personas via video-script. Multi-word keys are weighted to win cleanly.
    "video-edit":          ["montage", "footage", "edit raw", "b-roll", "b roll", "color grade",
                            "color-grade", "rough cut", "pace the cut", "pacing", "cut the",
                            "edit the", "sequence", "splice", "timeline edit", "documentary footage",
                            "assembly cut", "edit documentary", "edit footage"],
    "research":            ["research", "analyze", "study", "investigate", "compile", "find out", "look into"],
    "strategy":            ["strategy", "plan", "roadmap", "vision", "framework", "approach"],
    "design":              ["design", "graphic", "logo", "layout", "mockup", "visual", "illustrate",
                            "sketchnote", "sketchnoting", "sketch", "visually", "visual map", "visual mapping"],
    "ops":                 ["sop", "process", "workflow", "automation", "operations", "procedure"],
    "finance":             ["budget", "p&l", "cashflow", "forecast", "pricing", "invoice", "payment"],
    "legal":               ["contract", "nda", "terms", "policy", "compliance", "agreement"],
    "hr":                  ["hire", "fire", "onboard", "review performance", "recruit"],
    "customer-service":    ["refund", "ticket", "support", "complaint", "service issue", "customer issue"],
    "coaching-prompt":     ["stuck", "decide", "advice", "help me think", "help me decide", "what should i"],
    "review-feedback":     ["review my", "feedback on my", "critique my", "edit my"],
}


def infer_task_category(task_text: str) -> str:
    """Returns a category slug, or 'general' if no clear match."""
    text = (task_text or "").lower()
    best_cat = "general"
    best_score = 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in kws:
            # word-boundary match for short keywords; substring match for multi-word
            if " " in kw:
                if kw in text:
                    score += 1
            else:
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text):
                    score += 1
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: infer-task-category.py <task text>")
        sys.exit(1)
    print(infer_task_category(" ".join(sys.argv[1:])))
