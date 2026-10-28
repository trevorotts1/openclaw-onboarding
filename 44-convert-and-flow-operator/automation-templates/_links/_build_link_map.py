#!/usr/bin/env python3
"""_build_link_map.py — generate funnel-to-automation.json.

Maps each of the 38 shipped Skill-6 funnel templates to its RECOMMENDED follow-up
automation sequence(s) from the Skill-44 automation library. Every link is a
RECOMMENDED DEFAULT — a guide and a resource, NEVER a rule or a requirement. The
user can override, mix, customize, or ignore any of it.

The mapping below is Brunson-doctrine (DotCom Secrets / Expert Secrets / Funnel
Hacker's Cookbook): a funnel captures/converts; the linked automation is the
follow-up that bonds, reminds, recovers, or closes. The script VALIDATES that every
referenced automation id actually exists on disk before writing, so the map can
never point at a phantom template.
"""
from __future__ import annotations
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
AT_ROOT = os.path.dirname(HERE)                     # automation-templates/
FT_ROOT = os.path.join(os.path.dirname(AT_ROOT), "funnel-templates")

# group -> short why the whole group routes where it does (RECOMMENDED, not mandatory)
GROUP_DOCTRINE = {
    "lead": "A lead funnel captures an email. The proven default follow-up is the "
            "Soap Opera Sequence (bond to the Attractive Character) that graduates "
            "into the daily Seinfeld broadcast (ongoing engagement).",
    "buyer": "A buyer funnel takes money. The proven default follow-up is post-purchase "
             "OTO/ascension + cart-abandon recovery for the order form.",
    "event": "An event funnel registers an attendee. The proven default follow-up is "
             "indoctrination + show-up reminders + replay + the Perfect Webinar Stack close.",
    "retention-followup": "A retention funnel saves or re-sells. The proven default "
                          "follow-up is stick/retention or the 3-Closes Follow-Up Funnel.",
    "traffic-advanced": "An advanced/traffic funnel pre-frames or recovers traffic. The "
                        "proven default follow-up is indoctrination/pre-frame, retargeting, "
                        "or front-end OTO depending on the play.",
}

# funnel id -> {group, primary, secondary[], graduation?, why}
# automations are referenced as "category/id" and validated against disk.
LINKS = {
  # ---------------- BUYER ----------------
  "2-step-tripwire-free-plus-shipping": {
    "primary": "funnel-specific-followups/free-plus-shipping-book-oto-followup",
    "secondary": ["sales-close-sequences/abandoned-cart-recovery",
                  "multichannel-automation/abandoned-cart-multichannel-recovery",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "Free+shipping tripwire -> immediate OTO/ascension follow-up; recover order-form "
           "abandons; bond new buyers with a Soap Opera Sequence."},
  "book-funnel": {
    "primary": "funnel-specific-followups/free-plus-shipping-book-oto-followup",
    "secondary": ["funnel-specific-followups/cart-abandon-recovery",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "Free+shipping book -> post-purchase OTO ladder; recover abandons; indoctrinate "
           "the new reader."},
  "daily-deal": {
    "primary": "sales-close-sequences/scarcity-deadline-close",
    "secondary": ["engagement-broadcast/daily-seinfeld-sequence",
                  "engagement-broadcast/email-teaser-click-driver",
                  "funnel-specific-followups/cart-abandon-recovery"],
    "why": "Recurring daily deal lives on real deadline scarcity + a daily broadcast that "
           "drives the click; recover abandons."},
  "membership-continuity": {
    "primary": "funnel-specific-followups/membership-stick-retention",
    "secondary": ["welcome-indoctrination/new-subscriber-indoctrination",
                  "engagement-broadcast/daily-seinfeld-sequence"],
    "why": "Continuity stands or falls on stick/retention; onboard new members, keep them "
           "engaged with ongoing broadcasts."},
  "sales-letter": {
    "primary": "sales-close-sequences/three-closes-master-followup",
    "secondary": ["funnel-specific-followups/cart-abandon-recovery",
                  "sales-close-sequences/scarcity-deadline-close"],
    "why": "Long-form sales letter -> the 3 Closes (Emotion/Logic/Fear) follow-up; recover "
           "abandons; add an honest deadline close."},
  "self-liquidating-offer-slo": {
    "primary": "funnel-specific-followups/free-plus-shipping-book-oto-followup",
    "secondary": ["funnel-specific-followups/cart-abandon-recovery",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "SLO is a front-end + OTO ascension play; recover abandons; bond the buyer."},
  "storefront": {
    "primary": "multichannel-automation/abandoned-cart-multichannel-recovery",
    "secondary": ["sales-close-sequences/abandoned-cart-recovery",
                  "multichannel-automation/behavioral-retargeting-page-visit-fire",
                  "engagement-broadcast/daily-seinfeld-sequence"],
    "why": "Ecommerce storefront -> multichannel cart recovery + browse retargeting + an "
           "ongoing broadcast to drive repeat visits."},
  "video-sales-letter-vsl": {
    "primary": "sales-close-sequences/three-closes-master-followup",
    "secondary": ["funnel-specific-followups/cart-abandon-recovery",
                  "sales-close-sequences/scarcity-deadline-close"],
    "why": "VSL -> 3 Closes follow-up for non-buyers; recover abandons; deadline close."},

  # ---------------- EVENT ----------------
  "autowebinar-funnel": {
    "primary": "funnel-specific-followups/autowebinar-watch-segmented-followup",
    "secondary": ["multichannel-automation/autowebinar-behavioral-branching",
                  "sales-close-sequences/perfect-webinar-stack-close"],
    "why": "Evergreen auto-webinar -> watch-segmented follow-up + behavioral branching + "
           "the Stack close."},
  "five-minute-perfect-webinar-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["sales-close-sequences/perfect-webinar-stack-close",
                  "funnel-specific-followups/autowebinar-watch-segmented-followup"],
    "why": "5-minute perfect webinar -> registration/reminder/replay wrap + the Stack close."},
  "hotel-meeting-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "sales-close-sequences/perfect-webinar-stack-close"],
    "why": "Live hotel meeting -> registration + show-up reminders + replay; pre-frame "
           "attendees; close with the Stack."},
  "invisible-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["funnel-specific-followups/autowebinar-watch-segmented-followup",
                  "sales-close-sequences/perfect-webinar-stack-close"],
    "why": "Invisible (pay-what-it's-worth webinar) -> reminder/replay wrap + watch-segmented "
           "follow-up + Stack close."},
  "live-demo-home-party-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "sales-close-sequences/scarcity-deadline-close"],
    "why": "Live demo / home party -> registration + reminders + replay; pre-frame; deadline "
           "close on the offer."},
  "perfect-webinar-shortcut-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["sales-close-sequences/perfect-webinar-stack-close",
                  "funnel-specific-followups/autowebinar-watch-segmented-followup"],
    "why": "Perfect Webinar shortcut -> registration/reminder/replay wrap + the Stack close."},
  "product-launch-funnel": {
    "primary": "sales-close-sequences/cart-open-cart-close-launch-sequence",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "sales-close-sequences/scarcity-deadline-close",
                  "sales-close-sequences/three-closes-master-followup"],
    "why": "Jeff-Walker-style PLF -> the cart-open/cart-close launch sequence; pre-frame the "
           "list first; deadline + 3 Closes at close."},
  "summit-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "engagement-broadcast/value-broadcast-3-closes-campaign"],
    "why": "Summit -> registration + session reminders + replay; pre-frame; all-access-pass "
           "close via a value+3-closes campaign."},
  "teleseminar-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["sales-close-sequences/perfect-webinar-stack-close",
                  "multichannel-automation/indoctrination-multichannel-preframe"],
    "why": "Teleseminar -> registration + reminders + replay; close with the Stack; pre-frame."},
  "telesummit-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "engagement-broadcast/value-broadcast-3-closes-campaign"],
    "why": "Telesummit (multi-session) -> registration + reminders + replay; pre-frame; "
           "all-access close."},
  "webinar-funnel": {
    "primary": "funnel-specific-followups/webinar-registration-reminder-replay-stack",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "sales-close-sequences/perfect-webinar-stack-close",
                  "sales-close-sequences/soap-opera-sequence"],
    "why": "Live Perfect Webinar -> the canonical reg/indoctrinate/remind/replay/Stack wrap; "
           "pre-frame; Soap Opera indoctrination before the event."},

  # ---------------- LEAD ----------------
  "application": {
    "primary": "funnel-specific-followups/application-homework-booking-nurture",
    "secondary": ["sales-close-sequences/scarcity-deadline-close",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "High-ticket application -> homework + booking nurture to drive show-up to the "
           "call; deadline urgency; pre-call bonding."},
  "ask-campaign": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["welcome-indoctrination/new-subscriber-indoctrination",
                  "engagement-broadcast/three-ms-content-broadcast"],
    "why": "Ask-Method survey -> bond responders with a Soap Opera Sequence, indoctrinate, "
           "then deliver Market/Message/Media-matched content."},
  "bridge": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["multichannel-automation/indoctrination-multichannel-preframe",
                  "welcome-indoctrination/new-subscriber-indoctrination"],
    "why": "Bridge page warms cold/borrowed traffic -> pre-frame then bond with the Soap "
           "Opera Sequence."},
  "hero": {
    "primary": "welcome-indoctrination/attractive-character-intro-sequence",
    "secondary": ["welcome-indoctrination/soap-opera-sequence",
                  "engagement-broadcast/daily-seinfeld-sequence"],
    "why": "Hero / personal-brand opt-in -> introduce the Attractive Character, bond via Soap "
           "Opera, graduate to daily Seinfeld."},
  "homepage": {
    "primary": "welcome-indoctrination/new-subscriber-indoctrination",
    "secondary": ["engagement-broadcast/daily-seinfeld-sequence",
                  "engagement-broadcast/three-ms-content-broadcast"],
    "why": "Homepage-as-funnel captures + indoctrinates; ongoing broadcast keeps the brand "
           "top-of-mind."},
  "lead-magnet": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["welcome-indoctrination/new-subscriber-indoctrination",
                  "multichannel-automation/post-optin-multichannel-stack"],
    "graduation": "engagement-broadcast/daily-seinfeld-sequence",
    "why": "Lead magnet opt-in -> Soap Opera Sequence (deliver + bond), multichannel post-optin "
           "stack, then graduate to the daily Seinfeld broadcast."},
  "reverse-squeeze-page": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["welcome-indoctrination/new-subscriber-indoctrination",
                  "multichannel-automation/post-optin-multichannel-stack"],
    "graduation": "engagement-broadcast/daily-seinfeld-sequence",
    "why": "Value-first reverse squeeze -> bond with the Soap Opera Sequence; multichannel "
           "post-optin; graduate to Seinfeld."},
  "squeeze-page": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["welcome-indoctrination/new-subscriber-indoctrination",
                  "multichannel-automation/post-optin-multichannel-stack"],
    "graduation": "engagement-broadcast/daily-seinfeld-sequence",
    "why": "The classic squeeze -> Soap Opera Sequence (THE textbook pairing); then graduate "
           "to the daily Seinfeld broadcast."},
  "survey-quiz": {
    "primary": "welcome-indoctrination/new-subscriber-indoctrination",
    "secondary": ["multichannel-automation/post-optin-multichannel-stack",
                  "welcome-indoctrination/soap-opera-sequence",
                  "multichannel-automation/behavioral-retargeting-page-visit-fire"],
    "why": "Quiz segments the lead -> result-segmented indoctrination + multichannel stack; "
           "bond via Soap Opera; retarget by result."},

  # ---------------- RETENTION-FOLLOWUP ----------------
  "cancellation-funnel": {
    "primary": "funnel-specific-followups/membership-stick-retention",
    "secondary": ["engagement-broadcast/re-engagement-winback-broadcast",
                  "sales-close-sequences/scarcity-deadline-close"],
    "why": "Cancellation save -> stick/retention to save the sale; win-back the churned; "
           "deadline-close a win-back offer."},
  "follow-up-funnel": {
    "primary": "sales-close-sequences/three-closes-master-followup",
    "secondary": ["sales-close-sequences/soap-opera-sequence",
                  "sales-close-sequences/seinfeld-daily-sequence",
                  "engagement-broadcast/re-engagement-winback-broadcast"],
    "why": "The DotCom Secrets Follow-Up Funnel IS Soap Opera + Seinfeld + the 3 Closes; "
           "win-back the cold."},

  # ---------------- TRAFFIC-ADVANCED ----------------
  "break-even-front-end": {
    "primary": "funnel-specific-followups/free-plus-shipping-book-oto-followup",
    "secondary": ["funnel-specific-followups/cart-abandon-recovery",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "Break-even front end profits on the OTO/backend -> OTO ascension follow-up; "
           "recover abandons; bond the buyer."},
  "client-acquisition": {
    "primary": "funnel-specific-followups/application-homework-booking-nurture",
    "secondary": ["welcome-indoctrination/soap-opera-sequence",
                  "sales-close-sequences/scarcity-deadline-close"],
    "why": "Agency/client-acquisition funnel books calls -> homework + booking nurture; bond; "
           "deadline urgency on the proposal."},
  "cold-traffic-article-preframe": {
    "primary": "multichannel-automation/indoctrination-multichannel-preframe",
    "secondary": ["welcome-indoctrination/soap-opera-sequence",
                  "multichannel-automation/behavioral-retargeting-page-visit-fire"],
    "why": "Article pre-frame warms cold traffic -> multichannel indoctrination/pre-frame; "
           "bond; retarget readers who didn't opt in."},
  "funnel-hub": {
    "primary": "engagement-broadcast/daily-seinfeld-sequence",
    "secondary": ["engagement-broadcast/three-ms-content-broadcast",
                  "engagement-broadcast/attractive-character-story-rotation",
                  "multichannel-automation/behavioral-retargeting-page-visit-fire"],
    "why": "A funnel hub is the brand home -> ongoing Seinfeld broadcast + 3 Ms content + "
           "Attractive-Character story rotation; retarget visitors."},
  "pop-up-ad": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["multichannel-automation/behavioral-retargeting-page-visit-fire",
                  "engagement-broadcast/email-teaser-click-driver"],
    "why": "Pop-up/exit capture -> bond with the Soap Opera Sequence; retarget; teaser emails "
           "to drive the click back."},
  "pre-funnel-social-preframe": {
    "primary": "multichannel-automation/indoctrination-multichannel-preframe",
    "secondary": ["multichannel-automation/behavioral-retargeting-page-visit-fire",
                  "welcome-indoctrination/soap-opera-sequence"],
    "why": "Social pre-frame -> multichannel indoctrination/pre-frame; retarget; bond once "
           "they opt in."},
  "shadow-funnel": {
    "primary": "multichannel-automation/behavioral-retargeting-page-visit-fire",
    "secondary": ["multichannel-automation/abandoned-cart-multichannel-recovery",
                  "engagement-broadcast/re-engagement-winback-broadcast",
                  "funnel-specific-followups/cart-abandon-recovery"],
    "why": "The DotCom Secrets Shadow Funnel is retargeting + abandonment follow-up "
           "everywhere -> page-visit retargeting + multichannel cart recovery + win-back."},
  "viral-front-end": {
    "primary": "welcome-indoctrination/soap-opera-sequence",
    "secondary": ["engagement-broadcast/email-teaser-click-driver",
                  "engagement-broadcast/daily-seinfeld-sequence",
                  "multichannel-automation/post-optin-multichannel-stack"],
    "why": "Viral front end captures at scale -> bond with the Soap Opera Sequence; teaser "
           "click-drivers; graduate to Seinfeld; multichannel post-optin."},
}

# funnel id -> group (from disk, derived below)
def _funnel_groups():
    groups = {}
    for g in sorted(os.listdir(FT_ROOT)):
        gd = os.path.join(FT_ROOT, g)
        if not os.path.isdir(gd) or g.startswith("_"):
            continue
        for fn in os.listdir(gd):
            if fn.endswith(".json") and not fn.startswith("_"):
                try:
                    doc = json.load(open(os.path.join(gd, fn), encoding="utf-8"))
                except Exception:
                    continue
                tid = doc.get("id") or os.path.splitext(fn)[0]
                groups[tid] = g
    return groups

def _automation_index():
    """category/id -> {name, path} for every automation on disk."""
    idx = {}
    for c in sorted(os.listdir(AT_ROOT)):
        cd = os.path.join(AT_ROOT, c)
        if not os.path.isdir(cd) or c.startswith("_"):
            continue
        for fn in os.listdir(cd):
            if fn.endswith(".json") and not fn.startswith("_"):
                try:
                    doc = json.load(open(os.path.join(cd, fn), encoding="utf-8"))
                except Exception:
                    continue
                aid = doc.get("id") or os.path.splitext(fn)[0]
                idx[f"{c}/{aid}"] = {"name": doc.get("name", aid),
                                     "path": os.path.join("automation-templates", c, fn)}
    return idx

def _ref(key, aidx, role, why=""):
    if key not in aidx:
        raise SystemExit(f"BROKEN LINK: automation '{key}' not found on disk")
    cat, aid = key.split("/", 1)
    return {"automation_id": aid, "category": cat, "role": role,
            "name": aidx[key]["name"], "ref": aidx[key]["path"],
            **({"why": why} if why else {})}

def main():
    fgroups = _funnel_groups()
    aidx = _automation_index()
    missing = set(fgroups) - set(LINKS)
    extra = set(LINKS) - set(fgroups)
    if missing:
        raise SystemExit(f"funnels with no link entry: {sorted(missing)}")
    if extra:
        raise SystemExit(f"link entries with no funnel on disk: {sorted(extra)}")

    links = []
    for fid in sorted(LINKS, key=lambda x: (fgroups[x], x)):
        spec = LINKS[fid]
        entry = {
            "funnel_template_id": fid,
            "funnel_group": fgroups[fid],
            "funnel_ref": os.path.join("funnel-templates", fgroups[fid], f"{fid}.json"),
            "recommended": True,
            "mandatory": False,
            "primary_followup": _ref(spec["primary"], aidx, "primary"),
            "secondary_followups": [_ref(k, aidx, "secondary") for k in spec.get("secondary", [])],
            "why": spec["why"],
            "group_doctrine": GROUP_DOCTRINE.get(fgroups[fid], ""),
            "flexibility": {
                "principle": "RECOMMENDED DEFAULT, never mandatory. The linked automations are a "
                             "guide and a resource; they must not dominate the user's desire.",
                "explicit_user_spec": "If the user named their own follow-up, build THAT; this map "
                                      "is an optional reference only — do not impose it.",
                "unsure": "If the user is unsure, suggest the primary follow-up and explain why, "
                          "then let them decide.",
                "hands_off": "If the user said 'just do it', build the primary (and, if desired, "
                             "the secondary) automations from these defaults.",
                "always": "Overridable, mixable, customizable, ignorable. Any automation the user "
                          "overrides is dropped from the auto-build."
            },
        }
        if "graduation" in spec:
            entry["graduation_followup"] = _ref(spec["graduation"], aidx, "graduation",
                                                why="Auto-responder bonding graduates into this "
                                                    "ongoing broadcast.")
        links.append(entry)

    out = {
        "_meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "Funnel <-> Automation recommended-followup link map. Maps each Skill-6 "
                           "funnel template to its recommended Skill-44 follow-up automation(s).",
            "core_principle": "Every link is a RECOMMENDED DEFAULT and a RESOURCE — never a rule or "
                              "a requirement. The template/sequence assists; it never dominates the "
                              "user's stated desire. Always overridable, mixable, customizable, "
                              "ignorable.",
            "intent_modes": {
                "EXPLICIT_USER_SPEC": "User named their own follow-up -> honor it; this map is only "
                                      "an optional reference.",
                "UNSURE_WANTS_SUGGESTION": "User is unsure -> suggest the primary follow-up + why, "
                                           "await confirm.",
                "HANDS_OFF_DO_IT_ALL": "User said 'just do it' -> auto-build the linked automations "
                                       "(minus any the user overrode)."
            },
            "funnel_template_count": len(links),
            "automation_template_count": len(aidx),
            "consumed_by": [
                "44-convert-and-flow-operator automation_matcher.step0 (intent-mode routing)",
                "06-ghl-install-pages funnel_matcher.step0_match -> emits linked_automations for "
                "Skill 44 to build the complete funnel (minus user overrides)"
            ],
        },
        "links": links,
    }
    out_path = os.path.join(HERE, "funnel-to-automation.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=2)
    # coverage assertions
    assert len(links) == 38, f"expected 38 funnel links, got {len(links)}"
    prim = {l["primary_followup"]["category"] + "/" + l["primary_followup"]["automation_id"] for l in links}
    print(f"wrote {out_path}")
    print(f"funnel links: {len(links)} (expected 38)")
    print(f"distinct automations referenced as primary: {len(prim)}")
    print(f"automations on disk: {len(aidx)}")
    print("VALID: every referenced automation id exists on disk")

if __name__ == "__main__":
    main()
