#!/usr/bin/env python3
"""
Detect a client's industry vertical from pre-interview research and/or interview answers.

Returns (industry_slug, confidence_0_to_1, matched_signals).

Used by Skill 23 Phase 0 to auto-select an industry vertical pack
(Personal/Pro Dev, Real Estate, Service Industry, etc.).

If confidence < 0.7, the interview asks a confirmation question (C-4).
"""
import argparse
import json
import re
import sys
from pathlib import Path


INDUSTRY_KEYWORDS = {
    "personal-pro-dev": {
        "weight": 1.0,
        "keywords": [
            "coach", "coaching", "mentor", "mentorship", "speaker", "thought leader",
            "consultant", "mastermind", "course creator", "online course",
            "transformation", "keynote", "workshop", "training program",
            "personal development", "professional development", "business coach",
            "life coach", "wellness coach", "executive coach",
        ],
    },
    "real-estate": {
        "weight": 1.0,
        "keywords": [
            "realtor", "real estate", "broker", "brokerage", "listings",
            "mls", "property", "homes for sale", "rental", "investor property",
            "real estate agent", "closing", "showings", "open house",
            "zillow", "realtor.com",
        ],
    },
    "service-industry": {
        "weight": 1.0,
        "keywords": [
            "spa", "salon", "barbershop", "plumber", "plumbing", "electrician",
            "maid service", "cleaning service", "lawn care", "landscaping",
            "hvac", "pest control", "auto repair", "mobile detail",
            "restaurant", "catering", "food truck", "dental", "chiropractor",
            "massage therapist", "personal trainer",
        ],
    },
    "ecommerce": {
        "weight": 1.0,
        "keywords": [
            "shop", "store", "products", "shipping", "skus", "inventory",
            "shopify", "amazon", "etsy", "woocommerce", "fulfillment",
            "dropship", "private label", "physical product", "d2c", "direct to consumer",
        ],
    },
    "saas": {
        "weight": 1.0,
        "keywords": [
            "software", "saas", "platform", "subscription software", "users",
            "freemium", "free trial", "api", "integrations", "developer",
            "engineering team", "product roadmap", "user signups",
        ],
    },
    "agency": {
        "weight": 1.0,
        "keywords": [
            "agency", "client work", "marketing agency", "ad agency",
            "white label", "fractional", "done for you", "done-for-you",
            "account manager", "retainer client", "project work",
        ],
    },
    "content-creator": {
        "weight": 1.0,
        "keywords": [
            "influencer", "creator", "youtube channel", "podcast host",
            "blogger", "tiktok creator", "instagram creator", "sponsorship",
            "brand deal", "patreon", "substack", "subscribers", "audience",
        ],
    },
}


def detect_industry(text: str) -> dict:
    """
    Args:
        text: combined pre-interview research + interview answers as a single blob.
    Returns:
        dict with: industry_slug, confidence (0-1), matched_signals (list),
        all_scores (dict of industry_slug -> raw match count).
    """
    text_lower = text.lower()
    scores = {}
    matched_per_industry = {}

    for industry, config in INDUSTRY_KEYWORDS.items():
        hits = []
        for kw in config["keywords"]:
            # Word boundary match — avoid partial-word false positives
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            count = len(re.findall(pattern, text_lower))
            if count > 0:
                hits.append({"keyword": kw, "count": count})
        scores[industry] = sum(h["count"] for h in hits) * config["weight"]
        matched_per_industry[industry] = hits

    if not scores or max(scores.values()) == 0:
        return {
            "industry_slug": "unknown",
            "confidence": 0.0,
            "matched_signals": [],
            "all_scores": scores,
            "needs_confirmation": True,
        }

    top = max(scores, key=scores.get)
    top_score = scores[top]
    total = sum(scores.values())
    # Confidence = top's share of total mass, scaled by absolute volume
    relative_confidence = top_score / total if total > 0 else 0
    # Discount confidence if total signal is weak
    volume_discount = min(top_score / 5.0, 1.0)
    confidence = round(relative_confidence * volume_discount, 3)

    return {
        "industry_slug": top,
        "confidence": confidence,
        "matched_signals": matched_per_industry[top],
        "all_scores": scores,
        "needs_confirmation": confidence < 0.7,
    }


def main():
    parser = argparse.ArgumentParser(description="Detect industry vertical from pre-interview text.")
    parser.add_argument("--text", help="Inline text to analyze")
    parser.add_argument("--file", help="Path to text file to analyze")
    parser.add_argument("--format", choices=["json", "human"], default="json")
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    result = detect_industry(text)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Industry: {result['industry_slug']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Needs confirmation: {result['needs_confirmation']}")
        print(f"Matched signals: {len(result['matched_signals'])}")
        for sig in result["matched_signals"]:
            print(f"  - {sig['keyword']} (x{sig['count']})")


if __name__ == "__main__":
    main()
