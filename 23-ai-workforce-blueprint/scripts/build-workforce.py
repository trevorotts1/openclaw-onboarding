#!/usr/bin/env python3
"""
AI Workforce Blueprint - Scaffold Builder
Creates the full department/role folder structure with starter files.
Auto-detects Coaching Personas Matrix and wires governing personas per department AND per role.
Run: python3 build-workforce.py
"""

import os
import sys
import subprocess
import json

DEPT_SUFFIX = "-dept"

# Pre-built departments with descriptions
PREBUILT_DEPARTMENTS = {
    "marketing": "Content, ads, social media, email campaigns",
    "sales": "Converting leads to customers",
    "billing": "Invoicing, payments, financial tracking",
    "customer-support": "Helping existing clients",
    "operations": "Day-to-day business running",
    "creative": "Graphics, video, content creation",
    "hr-people": "Team management, hiring",
    "legal-compliance": "Contracts, regulations",
    "it-tech": "Software, websites, infrastructure",
    "master-orchestrator": "Routes all work (always included)",
}

# Department → Governing Personas mapping
# Personas listed in priority order (most relevant first)
DEPT_PERSONAS = {
    "sales": [
        ("hormozi-100m-offers", "Offer design, pricing, value stacking"),
        ("voss-never-split-difference", "Negotiation, objection handling, difficult conversations"),
        ("rackham-spin-selling", "Discovery calls, consultative selling, needs analysis"),
        ("pink-to-sell-is-human", "Persuasion, moving people, pitching"),
        ("jones-exactly-what-to-say", "Magic words, closing language, exact phrasing"),
        ("priestley-oversubscribed", "Demand generation, positioning, being sought after"),
        ("kane-hook-point", "Attention, hooks, getting noticed in a crowded market"),
    ],
    "marketing": [
        ("miller-building-storybrand-2", "Brand messaging, clarity, customer story"),
        ("godin-this-is-marketing", "Permission marketing, being seen, serving an audience"),
        ("bly-copywriters-handbook", "Copywriting, conversion copy, direct response"),
        ("wiebe-copy-hackers", "Value proposition, website copy, conversion optimization"),
        ("cialdini-influence", "Persuasion psychology, social proof, reciprocity"),
        ("charvet-words-change-minds", "Language patterns, NLP, communication styles"),
        ("kane-hook-point", "Attention, hooks, getting noticed"),
    ],
    "leadership": [
        ("sinek-start-with-why", "Why-driven leadership, purpose, inspiring action"),
        ("sinek-find-your-why", "Team purpose, finding and articulating why"),
        ("collins-good-to-great", "Building great companies, disciplined strategy"),
        ("grover-relentless", "Elite performance, relentless execution, standards"),
        ("lakhiani-extraordinary-mind", "Rewriting rules, extraordinary thinking"),
        ("samit-disrupt-yourself", "Innovation, personal disruption, reinvention"),
    ],
    "operations": [
        ("clear-atomic-habits", "Habit building, systems, behavior change"),
        ("forte-building-second-brain", "Second brain, PKM, knowledge management"),
        ("forte-para-method", "PARA organization system, folder structure"),
        ("moran-12-week-year", "12-week execution, goal sprints, accountability"),
        ("duhigg-power-of-habit", "Habit loops, cue-routine-reward, organizational habits"),
        ("pink-when", "Timing, when to schedule tasks, energy management"),
    ],
    "ops": [
        ("clear-atomic-habits", "Habit building, systems, behavior change"),
        ("forte-building-second-brain", "Second brain, PKM, knowledge management"),
        ("forte-para-method", "PARA organization system, folder structure"),
        ("moran-12-week-year", "12-week execution, goal sprints, accountability"),
        ("duhigg-power-of-habit", "Habit loops, cue-routine-reward, organizational habits"),
        ("pink-when", "Timing, when to schedule tasks, energy management"),
    ],
    "finance": [
        ("michalowicz-profit-first", "Cash flow, profit first, financial discipline"),
    ],
    "billing": [
        ("michalowicz-profit-first", "Cash flow, profit first, financial discipline"),
        ("voss-never-split-difference", "Negotiating payment terms, handling billing disputes"),
    ],
    "coaching": [
        ("robbins-five-second-rule", "Confidence, 5-second action, overcoming hesitation"),
        ("robbins-let-them-theory", "Control release, boundaries, letting go"),
        ("sharma-5am-club", "Morning routine, discipline, peak performance"),
        ("goggins-cant-hurt-me", "Mental toughness, suffering, pushing limits"),
        ("jakes-instinct", "Instinct, spiritual intelligence, inner knowing"),
        ("pink-drive", "Motivation, intrinsic drive, autonomy mastery purpose"),
        ("attwood-passion-test", "Passion, life purpose, alignment"),
        ("grenny-crucial-conversations", "High-stakes conversations, safety, mutual purpose"),
        ("tawwab-set-boundaries-find-peace", "Boundaries, self-respect, healthy limits"),
        ("brown-atlas-of-heart", "Emotional vocabulary, empathy, human connection"),
    ],
    "support": [
        ("tawwab-set-boundaries-find-peace", "Boundaries, self-respect, healthy limits"),
        ("brown-atlas-of-heart", "Emotional vocabulary, empathy, human connection"),
        ("grenny-crucial-conversations", "Difficult conversations, de-escalation"),
        ("voss-never-split-difference", "Tactical empathy, listening, resolution"),
    ],
    "customer-support": [
        ("tawwab-set-boundaries-find-peace", "Boundaries, self-respect, healthy limits"),
        ("brown-atlas-of-heart", "Emotional vocabulary, empathy, human connection"),
        ("grenny-crucial-conversations", "Difficult conversations, de-escalation"),
        ("voss-never-split-difference", "Tactical empathy, listening, resolution"),
    ],
    "creative": [
        ("miller-building-storybrand-2", "Storytelling, narrative clarity, brand voice"),
        ("godin-this-is-marketing", "Creativity in service of an audience"),
        ("kane-hook-point", "Hooks, attention, creative differentiation"),
        ("bly-copywriters-handbook", "Copy craft, headlines, creative writing standards"),
    ],
    "hr": [
        ("obama-becoming", "Identity, resilience, becoming"),
        ("tawwab-set-boundaries-find-peace", "Boundaries, healthy workplace dynamics"),
        ("brown-atlas-of-heart", "Emotional intelligence, team culture"),
        ("grenny-crucial-conversations", "Performance conversations, feedback"),
        ("pink-drive", "Motivation, intrinsic drive, autonomy mastery purpose"),
    ],
    "hr-people": [
        ("obama-becoming", "Identity, resilience, becoming"),
        ("tawwab-set-boundaries-find-peace", "Boundaries, healthy workplace dynamics"),
        ("brown-atlas-of-heart", "Emotional intelligence, team culture"),
        ("grenny-crucial-conversations", "Performance conversations, feedback"),
        ("pink-drive", "Motivation, intrinsic drive, autonomy mastery purpose"),
    ],
    "legal": [
        ("grenny-crucial-conversations", "Difficult negotiations, high-stakes discussions"),
        ("voss-never-split-difference", "Negotiation tactics for legal discussions"),
    ],
    "legal-compliance": [
        ("grenny-crucial-conversations", "Difficult negotiations, high-stakes discussions"),
        ("voss-never-split-difference", "Negotiation tactics for legal discussions"),
    ],
    "it": [
        ("clear-atomic-habits", "Systematic thinking, process improvement"),
        ("forte-building-second-brain", "Knowledge management, documentation"),
        ("forte-para-method", "PARA organization for technical docs"),
    ],
    "it-tech": [
        ("clear-atomic-habits", "Systematic thinking, process improvement"),
        ("forte-building-second-brain", "Knowledge management, documentation"),
        ("forte-para-method", "PARA organization for technical docs"),
    ],
    "master-orchestrator": [
        ("collins-good-to-great", "Strategic thinking, disciplined execution"),
        ("sinek-start-with-why", "Purpose-driven decision making"),
        ("clear-atomic-habits", "Systems thinking for operations"),
    ],
}

# Role-specific persona mappings
# More specific than department-level - narrows down for particular roles
ROLE_PERSONAS = {
    # Marketing roles
    "content-creator": [
        ("miller-building-storybrand-2", "Brand messaging and customer story"),
        ("bly-copywriters-handbook", "Copywriting craft and conversion"),
        ("godin-this-is-marketing", "Permission marketing and audience service"),
        ("kane-hook-point", "Hooks and attention for content"),
    ],
    "social-media-manager": [
        ("kane-hook-point", "Attention and hooks for social"),
        ("godin-this-is-marketing", "Building audience and permission"),
        ("miller-building-storybrand-2", "Consistent brand messaging"),
    ],
    "ads-specialist": [
        ("wiebe-copy-hackers", "Value propositions and conversion optimization"),
        ("cialdini-influence", "Persuasion psychology for ads"),
        ("bly-copywriters-handbook", "Ad copy that converts"),
        ("kane-hook-point", "Stopping the scroll with hooks"),
    ],
    "email-marketing-specialist": [
        ("bly-copywriters-handbook", "Email copywriting craft"),
        ("wiebe-copy-hackers", "Subject lines and open rates"),
        ("cialdini-influence", "Persuasion sequences"),
    ],
    # Sales roles
    "appointment-setter": [
        ("rackham-spin-selling", "Discovery and consultative selling"),
        ("jones-exactly-what-to-say", "Magic words for setting appointments"),
        ("pink-to-sell-is-human", "Moving people to action"),
        ("kane-hook-point", "Getting attention in outreach"),
    ],
    "closer": [
        ("voss-never-split-difference", "Negotiation and objection handling"),
        ("hormozi-100m-offers", "Offer design and value stacking"),
        ("jones-exactly-what-to-say", "Closing language and magic words"),
        ("priestley-oversubscribed", "Creating demand and scarcity"),
    ],
    "account-manager": [
        ("grenny-crucial-conversations", "High-stakes client conversations"),
        ("pink-to-sell-is-human", "Moving people and relationship selling"),
        ("voss-never-split-difference", "Handling difficult client situations"),
        ("tawwab-set-boundaries-find-peace", "Setting healthy client boundaries"),
    ],
    "sdr": [
        ("jones-exactly-what-to-say", "Cold outreach scripts"),
        ("kane-hook-point", "Hooks that get responses"),
        ("rackham-spin-selling", "Discovery questioning"),
    ],
    "sales-development-rep": [
        ("jones-exactly-what-to-say", "Cold outreach scripts"),
        ("kane-hook-point", "Hooks that get responses"),
        ("rackham-spin-selling", "Discovery questioning"),
    ],
    # Support roles
    "support-agent": [
        ("tawwab-set-boundaries-find-peace", "Boundaries in customer interactions"),
        ("brown-atlas-of-heart", "Emotional vocabulary and empathy"),
        ("voss-never-split-difference", "Tactical empathy and listening"),
        ("grenny-crucial-conversations", "De-escalation techniques"),
    ],
    "customer-success-manager": [
        ("grenny-crucial-conversations", "High-stakes retention conversations"),
        ("voss-never-split-difference", "Negotiating renewals"),
        ("brown-atlas-of-heart", "Deep client empathy"),
    ],
    "onboarding-specialist": [
        ("pink-drive", "Motivating new users to take action"),
        ("clear-atomic-habits", "Building product usage habits"),
        ("miller-building-storybrand-2", "Making customer the hero"),
    ],
    # Operations roles
    "project-manager": [
        ("clear-atomic-habits", "Systems and behavior change"),
        ("moran-12-week-year", "Execution sprints and accountability"),
        ("forte-para-method", "Organization and folder structure"),
        ("grenny-crucial-conversations", "Managing stakeholder conversations"),
    ],
    "operations-manager": [
        ("clear-atomic-habits", "Systems and behavior change"),
        ("moran-12-week-year", "Execution sprints and accountability"),
        ("duhigg-power-of-habit", "Organizational habit loops"),
        ("collins-good-to-great", "Disciplined execution"),
    ],
    "systems-admin": [
        ("clear-atomic-habits", "Systematic thinking"),
        ("forte-building-second-brain", "Documentation systems"),
        ("forte-para-method", "PARA organization"),
    ],
    "process-analyst": [
        ("clear-atomic-habits", "Behavior change analysis"),
        ("duhigg-power-of-habit", "Habit loop optimization"),
        ("forte-para-method", "Process organization"),
    ],
    # Creative roles
    "graphic-designer": [
        ("miller-building-storybrand-2", "Visual storytelling and brand voice"),
        ("kane-hook-point", "Visual hooks and attention"),
        ("godin-this-is-marketing", "Design in service of audience"),
    ],
    "video-producer": [
        ("kane-hook-point", "Hooks and attention for video"),
        ("miller-building-storybrand-2", "Storytelling and narrative"),
        ("godin-this-is-marketing", "Video in service of audience"),
    ],
    "copywriter": [
        ("bly-copywriters-handbook", "Copy craft and headlines"),
        ("wiebe-copy-hackers", "Value propositions and conversion copy"),
        ("miller-building-storybrand-2", "Brand storytelling"),
    ],
    # HR roles
    "recruiter": [
        ("grenny-crucial-conversations", "Difficult hiring conversations"),
        ("obama-becoming", "Identity and resilience in candidates"),
        ("jones-exactly-what-to-say", "Candidate outreach language"),
    ],
    "hr-manager": [
        ("grenny-crucial-conversations", "Performance conversations"),
        ("tawwab-set-boundaries-find-peace", "Workplace boundaries"),
        ("pink-drive", "Employee motivation strategies"),
    ],
    "onboarding-coordinator": [
        ("pink-drive", "Motivating new hires"),
        ("clear-atomic-habits", "Building onboarding habits"),
        ("brown-atlas-of-heart", "Emotional welcome and connection"),
    ],
    # Leadership roles
    "team-lead": [
        ("sinek-start-with-why", "Why-driven leadership"),
        ("grenny-crucial-conversations", "Performance conversations"),
        ("grover-relentless", "Elite performance standards"),
    ],
    "ceo": [
        ("collins-good-to-great", "Building great companies"),
        ("sinek-start-with-why", "Purpose-driven leadership"),
        ("grover-relentless", "Relentless execution"),
        ("hormozi-100m-offers", "Offer and revenue strategy"),
    ],
    "founder": [
        ("collins-good-to-great", "Building great companies"),
        ("sinek-start-with-why", "Purpose-driven leadership"),
        ("samit-disrupt-yourself", "Innovation and disruption"),
        ("hormozi-100m-offers", "Offer creation"),
    ],
    # Finance roles
    "bookkeeper": [
        ("michalowicz-profit-first", "Cash flow discipline"),
        ("forte-para-method", "Financial document organization"),
    ],
    "accountant": [
        ("michalowicz-profit-first", "Profit-first accounting"),
        ("clear-atomic-habits", "Systematic financial processes"),
    ],
    "collections-specialist": [
        ("voss-never-split-difference", "Negotiating payments"),
        ("tawwab-set-boundaries-find-peace", "Firm but respectful boundaries"),
    ],
    # IT roles
    "developer": [
        ("clear-atomic-habits", "Systematic problem solving"),
        ("forte-building-second-brain", "Technical documentation"),
        ("forte-para-method", "Code organization"),
    ],
    "sysadmin": [
        ("clear-atomic-habits", "Systematic infrastructure management"),
        ("duhigg-power-of-habit", "Maintenance habit loops"),
    ],
    "helpdesk": [
        ("voss-never-split-difference", "Technical empathy"),
        ("brown-atlas-of-heart", "Patient support"),
        ("grenny-crucial-conversations", "Difficult technical conversations"),
    ],
    # Default - uses department personas
    "general": [],
    "generalist": [],
}

# Persona "When to Use" guidance - for the governing-personas.md template
PERSONA_USAGE_GUIDANCE = {
    "voss-never-split-difference": {
        "use_when": [
            "Negotiating with prospects or clients",
            "Handling objections during sales calls",
            "Difficult conversations with team members",
            "Resolving conflicts or disputes",
            "Getting to 'That's Right' in conversations",
            "De-escalating tense situations",
        ],
        "key_techniques": ["Mirroring", "Labeling", "Calibrated Questions", "Tactical Empathy"],
    },
    "hormozi-100m-offers": {
        "use_when": [
            "Designing offers that can't be compared",
            "Pricing strategies and value stacking",
            "Creating scarcity and urgency",
            "Risk reversal and guarantees",
            "Premium positioning",
            "Offer upgrades and iterations",
        ],
        "key_techniques": ["Grand Slam Offer", "Value Equation", "Scarcity/Urgency", "Risk Reversal"],
    },
    "jones-exactly-what-to-say": {
        "use_when": [
            "Need exact words for outreach",
            "Closing language that works",
            "Cold calling scripts",
            "Handling specific objections word-for-word",
            "Magic words for any situation",
            "Scripts that feel natural",
        ],
        "key_techniques": ["Magic Words", "Phrases that Work", "Exact Scripts"],
    },
    "rackham-spin-selling": {
        "use_when": [
            "Discovery calls with prospects",
            "Consultative selling approach",
            "Needs analysis and problem exploration",
            "Large B2B sales cycles",
            "Uncovering implicit needs",
            "Turning needs into solutions",
        ],
        "key_techniques": ["Situation Questions", "Problem Questions", "Implication Questions", "Need-Payoff Questions"],
    },
    "miller-building-storybrand-2": {
        "use_when": [
            "Clarifying brand messaging",
            "Making customer the hero",
            "Website copy and homepage messaging",
            "Email marketing narratives",
            "Content that connects",
            "Story-driven marketing",
        ],
        "key_techniques": ["SB7 Framework", "Customer as Hero", "Clarity Filter"],
    },
    "bly-copywriters-handbook": {
        "use_when": [
            "Writing headlines that grab attention",
            "Direct response copywriting",
            "Sales letters and landing pages",
            "Email subject lines",
            "Conversion-focused copy",
            "Writing with authority",
        ],
        "key_techniques": ["4-U Headlines", "AIDA Formula", "Copywriting Rules"],
    },
    "cialdini-influence": {
        "use_when": [
            "Understanding persuasion psychology",
            "Using social proof effectively",
            "Creating reciprocity",
            "Authority positioning",
            "Scarcity and commitment",
            "Liking and consistency",
        ],
        "key_techniques": ["6 Principles of Influence", "Social Proof", "Reciprocity", "Commitment"],
    },
    "sinek-start-with-why": {
        "use_when": [
            "Leadership and vision setting",
            "Inspiring team members",
            "Purpose-driven messaging",
            "Organizational culture",
            "Mission statements",
            "Why-driven decisions",
        ],
        "key_techniques": ["Golden Circle", "Start with Why", "Purpose First"],
    },
    "clear-atomic-habits": {
        "use_when": [
            "Building new habits",
            "Breaking bad habits",
            "Systems over goals",
            "Environment design",
            "Behavior change",
            "1% improvements",
        ],
        "key_techniques": ["4 Laws of Behavior Change", "Habit Stacking", "Environment Design", "Identity Change"],
    },
    "grenny-crucial-conversations": {
        "use_when": [
            "High-stakes conversations",
            "Emotional or risky topics",
            "Performance feedback",
            "Difficult team discussions",
            "When stakes are high and opinions differ",
            "Creating psychological safety",
        ],
        "key_techniques": ["STATE Path", "Mutual Purpose", "CRIB Skills", "Contrasting"],
    },
    "tawwab-set-boundaries-find-peace": {
        "use_when": [
            "Setting healthy boundaries",
            "Dealing with boundary violations",
            "Client boundary management",
            "Work-life balance",
            "Difficult family dynamics",
            "Protecting your peace",
        ],
        "key_techniques": ["6 Types of Boundaries", "Boundary Setting Scripts", "Consequences"],
    },
    "forte-para-method": {
        "use_when": [
            "Organizing files and folders",
            "Project management",
            "Information management",
            "Digital organization",
            "Knowledge systems",
            "Workspace setup",
        ],
        "key_techniques": ["PARA System", "Projects/Areas/Resources/Archives"],
    },
    "priestley-oversubscribed": {
        "use_when": [
            "Creating demand",
            "Positioning as sought-after",
            "Campaign-based marketing",
            "Waiting lists and launches",
            "Signaling value",
            "Market positioning",
        ],
        "key_techniques": ["Campaign Driven Enterprise", "Oversubscribed Strategy", "Market Makers"],
    },
    "kane-hook-point": {
        "use_when": [
            "Getting attention quickly",
            "Social media content",
            "Video hooks",
            "Breaking through noise",
            "First impressions",
            "Content that stops the scroll",
        ],
        "key_techniques": ["Hook Point Formula", "Attention Metrics", "Pattern Interrupts"],
    },
    "pink-to-sell-is-human": {
        "use_when": [
            "Understanding modern selling",
            "Moving people to action",
            "Attunement and perspective-taking",
            "Buoyancy and resilience",
            "Clarity through contrast",
            "Service-oriented selling",
        ],
        "key_techniques": ["Attunement", "Buoyancy", "Clarity", "Pixar Pitch"],
    },
    "wiebe-copy-hackers": {
        "use_when": [
            "Website optimization",
            "Value proposition writing",
            "Conversion copywriting",
            "User research for copy",
            "Messaging hierarchy",
            "Copy testing",
        ],
        "key_techniques": ["Value Proposition Canvas", "Messaging Hierarchy", "Copy Optimization"],
    },
    "godin-this-is-marketing": {
        "use_when": [
            "Permission marketing",
            "Building tribes",
            "Marketing as service",
            "Niche selection",
            "Product-market fit",
            "Being seen",
        ],
        "key_techniques": ["Permission Marketing", "Smallest Viable Market", "Marketing as Service"],
    },
    "collins-good-to-great": {
        "use_when": [
            "Strategic planning",
            "Building great organizations",
            "Leadership development",
            "Disciplined execution",
            "Hedgehog concept",
            "Level 5 leadership",
        ],
        "key_techniques": ["Hedgehog Concept", "Level 5 Leadership", "Flywheel Effect"],
    },
    "moran-12-week-year": {
        "use_when": [
            "Goal execution",
            "Sprint-based planning",
            "Accountability systems",
            "Shortening business cycles",
            "Weekly execution score",
            "Tactical weekly planning",
        ],
        "key_techniques": ["12-Week Cycles", "Weekly Score", "Execution System"],
    },
    "brown-atlas-of-heart": {
        "use_when": [
            "Emotional intelligence",
            "Vulnerability in leadership",
            "Empathy and connection",
            "Team culture",
            "Difficult emotions",
            "Human-centered work",
        ],
        "key_techniques": ["Emotional Literacy", "Vulnerability", "Empathy Skills"],
    },
    "michalowicz-profit-first": {
        "use_when": [
            "Cash flow management",
            "Profit allocation",
            "Financial discipline",
            "Small business finance",
            "Bank account architecture",
            "Sustainable profitability",
        ],
        "key_techniques": ["Profit First Formula", "Bank Account System", "Allocation Percentages"],
    },
    "pink-drive": {
        "use_when": [
            "Understanding motivation",
            "Autonomy in teams",
            "Mastery development",
            "Purpose-driven work",
            "Intrinsic motivation",
            "Employee engagement",
        ],
        "key_techniques": ["Autonomy", "Mastery", "Purpose"],
    },
    "robbins-five-second-rule": {
        "use_when": [
            "Overcoming hesitation",
            "Building confidence",
            "Taking immediate action",
            "Breaking procrastination",
            "Courage in moments",
            "Behavior change triggers",
        ],
        "key_techniques": ["5-4-3-2-1 Countdown", "Activation Energy", "Confidence Through Action"],
    },
    "goggins-cant-hurt-me": {
        "use_when": [
            "Mental toughness",
            "Pushing through limits",
            "Callousing the mind",
            "Extreme discipline",
            "Suffering as growth",
            "Accountability mirror",
        ],
        "key_techniques": ["40% Rule", "Accountability Mirror", "Calloused Mind"],
    },
    "charvet-words-change-minds": {
        "use_when": [
            "Language patterns",
            "NLP techniques",
            "Communication styles",
            "Influencing through language",
            "Motivation direction",
            "Meta programs",
        ],
        "key_techniques": ["Toward/Away From", "Options/Procedures", "Meta Programs"],
    },
}

START_HERE_TEMPLATE = """# {role_title} - Start Here

## What This Role Does
[Describe what this role is responsible for]

## Who Owns This Role
{dept_name} > {role_name}

## Top Tasks
[List the numbered task files this role uses, in order]
1. 01-[task-name].md

## Tools This Role Uses
[List the tools, software, and logins this role needs]

## Rules for This Role
[List any non-negotiable rules for how this role operates]

{governing_personas_section}
## Where to Find Examples
- Good examples: good-examples.md
- Bad examples: bad-examples.md
"""

GOVERNING_PERSONAS_SECTION = """## Governing Personas

This role draws from multiple coaching personas. Choose based on the specific task and context.

{persona_list}

**How to find the right persona for your task:**
```bash
qmd search "<describe your task>" -c coaching-personas
```

This searches the coaching personas collection and returns the best match. Load that persona's Task Mode and execute through that methodology.

**For detailed guidance:** See `governing-personas.md` in this folder for decision trees on when to use which persona.

"""

GOOD_EXAMPLES_TEMPLATE = """# Good Examples - {role_title}

## What Great Output Looks Like
[Add examples of excellent work from this role]

## Why These Are Good
[Explain what makes these examples the standard to meet]
"""

BAD_EXAMPLES_TEMPLATE = """# Bad Examples - {role_title}

## What Poor Output Looks Like
[Add examples of work that does not meet the standard]

## Why These Are Bad
[Explain what went wrong and what to do instead]
"""

TOOLS_TEMPLATE = """# Tools - {role_title}

## Tools This Role Uses

| Tool | Purpose | Where to Find Login |
|------|---------|-------------------|
| [Tool Name] | [What it does] | [Where credentials are stored] |

## Rules for Tool Use
[Any restrictions, permissions, or usage rules]
"""

TASK_TEMPLATE = """# {task_title}

## Purpose
[What this task accomplishes]

## When to Do This
[What triggers this task]

## Step by Step
1. [Step 1]
2. [Step 2]
3. [Step 3]

## What Good Output Looks Like
[Describe the result when this task is done correctly]

## Common Mistakes
[What usually goes wrong and how to avoid it]
"""

ROUTING_TEMPLATE = """# Task Routing - Which Department Handles What

## How to Use This File
When a task comes in, find the matching category below.
Go directly to that department folder and read the role's 00-START-HERE.md.

{routing_sections}

## When You Are Unsure
If the task does not match any category above:
1. Ask: "What is the end goal of this task?"
2. Route to the department whose purpose most closely matches that goal
3. If still unsure, default to ops-dept/ and let the Operations team route it further
"""


def telegram_print(message):
    """Print in Telegram-friendly format - no tables, short lines, bullets."""
    print(message)


def show_options():
    """Present the 3 options to the user."""
    telegram_print("""
🎯 AI WORKFORCE BLUEPRINT - Choose Your Path

I will help you build the folder and file system that turns your AI into a trained workforce.

📋 OPTION A - Full Automated Build (Recommended)
   • I interview you about your business
   • I build everything automatically based on your answers
   • Most personalized results
   • Best for: First-time setup

🛠️ OPTION B - Manual Build
   • You build everything yourself using the blueprint
   • Read ai-workforce-blueprint-full.md for guidance
   • Best for: Hands-on users who want full control

🔍 OPTION C - Audit / Resume Mode
   • I scan your existing workforce folder
   • Add missing files, wire personas if available
   • Never overwrites existing content
   • Best for: Returning users, adding personas later
""")


def show_prebuilt_departments():
    """Show the pre-built departments available."""
    telegram_print("""
📁 PRE-BUILT DEPARTMENTS AVAILABLE:

• marketing-dept - Content, ads, social media, email campaigns
• sales-dept - Converting leads to customers
• billing-dept - Invoicing, payments, financial tracking
• customer-support-dept - Helping existing clients
• operations-dept - Day-to-day business running
• creative-dept - Graphics, video, content creation
• hr-people-dept - Team management, hiring
• legal-compliance-dept - Contracts, regulations
• it-tech-dept - Software, websites, infrastructure
• master-orchestrator-dept - Routes all work (always included)
""")


def check_personas_installed():
    """Check if coaching-personas QMD collection exists on this machine."""
    try:
        result = subprocess.run(
            ["qmd", "status"],
            capture_output=True, text=True, timeout=10
        )
        return "coaching-personas" in result.stdout
    except Exception:
        return False


def load_existing_context():
    """Load existing context from memory files to avoid asking known questions."""
    context = {
        "business_name": None,
        "departments": [],
        "tools": [],
        "industry": None,
    }
    
    # Check common context file locations
    context_files = [
        os.path.expanduser("~/clawd/MEMORY.md"),
        os.path.expanduser("~/clawd/USER.md"),
        os.path.expanduser("~/clawd/AGENTS.md"),
        os.path.expanduser("~/clawd/HEARTBEAT.md"),
        os.path.expanduser("~/clawd/IDENTITY.md"),
    ]
    
    for file_path in context_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Look for business name patterns
                    if "blackceo" in content.lower() or "BlackCEO" in content:
                        context["business_name"] = "BlackCEO"
                        context["industry"] = "coaching/consulting"
                    # Look for known tools
                    if "GoHighLevel" in content or "GHL" in content:
                        context["tools"].append("GoHighLevel")
                    if "Slack" in content:
                        context["tools"].append("Slack")
                    if "Google" in content:
                        context["tools"].append("Google Workspace")
            except Exception:
                pass
    
    return context


def ask_interview_style(question, example=None, default=None, context_value=None):
    """Ask a question in interview style with examples."""
    # If we already know the answer from context, skip the question
    if context_value:
        telegram_print(f"✓ Using known info: {context_value}")
        return context_value
    
    if example:
        full_question = f"{question}\n   Example: {example}"
    else:
        full_question = question
    
    if default:
        answer = input(f"{full_question}\n   [Default: {default}]: ").strip()
        return answer if answer else default
    return input(f"{full_question}: ").strip()


def get_department_selection():
    """Ask user which departments they want to use."""
    telegram_print("""
🎯 DEPARTMENT SELECTION

You can:
• Keep all pre-built departments
• Keep some + remove others
• Keep all + add custom departments
• Start from scratch with custom departments only
""")
    
    options = [
        "Keep all pre-built departments",
        "Keep some + remove others",
        "Keep all + add custom departments",
        "Start from scratch (custom only)"
    ]
    
    telegram_print("\nChoose an option:")
    for i, opt in enumerate(options, 1):
        telegram_print(f"  {i}. {opt}")
    
    choice = input("\nEnter 1-4: ").strip()
    
    if choice == "1":
        return list(PREBUILT_DEPARTMENTS.keys())
    elif choice == "2":
        telegram_print("\n📋 Available departments:")
        for dept, desc in PREBUILT_DEPARTMENTS.items():
            telegram_print(f"  • {dept} - {desc}")
        remove = input("\nWhich departments should I REMOVE? (comma-separated): ").strip()
        removed = [d.strip() for d in remove.split(",") if d.strip()]
        return [d for d in PREBUILT_DEPARTMENTS.keys() if d not in removed]
    elif choice == "3":
        custom = input("\nWhat custom departments do you want to add? (comma-separated): ").strip()
        custom_list = [d.strip() for d in custom.split(",") if d.strip()]
        return list(PREBUILT_DEPARTMENTS.keys()) + custom_list
    elif choice == "4":
        custom = input("\nWhat custom departments do you want to create? (comma-separated): ").strip()
        return [d.strip() for d in custom.split(",") if d.strip()]
    else:
        telegram_print("Invalid choice. Using all pre-built departments.")
        return list(PREBUILT_DEPARTMENTS.keys())


def interview_user(context):
    """Conduct interview-style questions with examples."""
    telegram_print("\n" + "="*50)
    telegram_print("🎤 INTERVIEW TIME - Let's understand your business")
    telegram_print("="*50)
    
    # Question 1: Business name
    business_name = ask_interview_style(
        "What is your business name?",
        example="Acme Coaching, BlackCEO, Otts Consulting",
        default=context.get("business_name", "My Business"),
        context_value=context.get("business_name")
    )
    
    telegram_print("\n" + "-"*30)
    
    # Question 2: What does your business do?
    business_purpose = ask_interview_style(
        "In one sentence, what does your business do?",
        example="I help coaches book more clients through better marketing"
    )
    
    telegram_print("\n" + "-"*30)
    
    # Question 3: Current team size
    team_size = ask_interview_style(
        "What is your current team size?",
        example="Just me, 2-5 people, 10-20 people, 50+ people",
        default="Just me"
    )
    
    telegram_print("\n" + "-"*30)
    
    # Question 4: Main tools
    tools_answer = ask_interview_style(
        "What are the main tools your business uses?",
        example="GoHighLevel, Slack, Google Workspace, QuickBooks, Calendly",
        default=", ".join(context.get("tools", [])) if context.get("tools") else None
    )
    tools = [t.strip() for t in tools_answer.split(",") if t.strip()]
    
    telegram_print("\n" + "-"*30)
    
    # Question 5: Biggest challenge
    challenge = ask_interview_style(
        "What is your biggest challenge right now?",
        example="Following up with leads, creating content, managing invoices"
    )
    
    telegram_print("\n" + "-"*30)
    
    # Question 6: Existing SOPs
    has_sops = ask_interview_style(
        "Do you have existing SOPs, checklists, or training materials?",
        example="Yes, in Google Docs / No, starting from scratch / Some, but scattered"
    )
    
    return {
        "business_name": business_name,
        "business_purpose": business_purpose,
        "team_size": team_size,
        "tools": tools,
        "challenge": challenge,
        "has_sops": has_sops,
    }


def create_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Created: {os.path.basename(path)}")


def ask(question, default=None):
    if default:
        answer = input(f"{question} [{default}]: ").strip()
        return answer if answer else default
    return input(f"{question}: ").strip()


def build_governing_personas_content(dept_key, for_file=False):
    """Generate governing personas content for a department."""
    personas = DEPT_PERSONAS.get(dept_key, [])
    if not personas:
        # Try partial match
        for key in DEPT_PERSONAS:
            if key in dept_key or dept_key in key:
                personas = DEPT_PERSONAS[key]
                break
    if not personas:
        return None, None

    if for_file:
        entries = []
        for folder, description in personas:
            entries.append(f"### {folder}\n**Focus:** {description}\n**Query:** `qmd search \"{description.lower()}\" -c coaching-personas`\n")
        return '\n'.join(entries), personas

    # For 00-START-HERE.md section
    lines = []
    for folder, description in personas:
        lines.append(f"- **{folder}**: {description}")
    return '\n'.join(lines), personas


def detect_existing_workspace():
    """Scan common locations for an existing workforce folder."""
    common_paths = [
        os.path.expanduser("~/Downloads/my-ai-workforce"),
        os.path.expanduser("~/Downloads/ai-workforce"),
        os.path.expanduser("~/Downloads/openclaw-master-files/ai-workforce"),
        os.path.expanduser("~/clawd/workforce"),
    ]
    for path in common_paths:
        if os.path.isdir(path) and any(d.endswith(DEPT_SUFFIX) for d in os.listdir(path)):
            return path
    return None


def build_role_personas_content(role_key, dept_key, for_file=False):
    """Generate governing personas content specific to a role."""
    # Try role-specific personas first
    personas = ROLE_PERSONAS.get(role_key, [])
    
    # Fall back to department personas if no role-specific mapping
    if not personas:
        personas = DEPT_PERSONAS.get(dept_key, [])
        if not personas:
            # Try partial match on dept_key
            for key in DEPT_PERSONAS:
                if key in dept_key or dept_key in key:
                    personas = DEPT_PERSONAS[key]
                    break
    
    if not personas:
        return None, None

    if for_file:
        # Build the full governing-personas.md content with "When to Use Which Persona"
        sections = []
        sections.append("# Governing Personas - {role_name}\n".format(role_name=role_key.replace('_', ' ').title()))
        sections.append("This role can draw from the following coaching personas.")
        sections.append("Choose based on the specific task and context.\n")
        
        sections.append("## Available Personas\n")
        for folder, description in personas:
            sections.append(f"- **{folder}** - {description}")
        sections.append("")
        
        sections.append("## When to Use Which Persona\n")
        
        for folder, description in personas:
            guidance = PERSONA_USAGE_GUIDANCE.get(folder, {})
            use_when = guidance.get("use_when", ["Tasks related to " + description])
            
            # Get clean persona name for display
            persona_name = folder.split('-')[0].title()
            if 'hormozi' in folder:
                persona_name = "Hormozi"
            elif 'voss' in folder:
                persona_name = "Voss"
            elif 'jones' in folder:
                persona_name = "Jones"
            elif 'rackham' in folder:
                persona_name = "Rackham"
            elif 'miller' in folder:
                persona_name = "Miller"
            elif 'bly' in folder:
                persona_name = "Bly"
            elif 'cialdini' in folder:
                persona_name = "Cialdini"
            elif 'sinek' in folder:
                persona_name = "Sinek"
            elif 'clear' in folder:
                persona_name = "Clear"
            elif 'grenny' in folder:
                persona_name = "Grenny"
            elif 'tawwab' in folder:
                persona_name = "Tawwab"
            elif 'forte' in folder:
                persona_name = "Forte"
            elif 'priestley' in folder:
                persona_name = "Priestley"
            elif 'kane' in folder:
                persona_name = "Kane"
            elif 'pink' in folder:
                if 'sell' in folder:
                    persona_name = "Pink (Sales)"
                elif 'drive' in folder:
                    persona_name = "Pink (Drive)"
                else:
                    persona_name = "Pink"
            elif 'wiebe' in folder:
                persona_name = "Wiebe"
            elif 'godin' in folder:
                persona_name = "Godin"
            elif 'collins' in folder:
                persona_name = "Collins"
            elif 'moran' in folder:
                persona_name = "Moran"
            elif 'brown' in folder:
                persona_name = "Brown"
            elif 'michalowicz' in folder:
                persona_name = "Michalowicz"
            elif 'robbins' in folder:
                persona_name = "Robbins"
            elif 'goggins' in folder:
                persona_name = "Goggins"
            elif 'charvet' in folder:
                persona_name = "Charvet"
            elif 'obama' in folder:
                persona_name = "Obama"
            elif 'jakes' in folder:
                persona_name = "Jakes"
            elif 'sharma' in folder:
                persona_name = "Sharma"
            elif 'samit' in folder:
                persona_name = "Samit"
            elif 'lakhiani' in folder:
                persona_name = "Lakhiani"
            elif 'grover' in folder:
                persona_name = "Grover"
            elif 'attwood' in folder:
                persona_name = "Attwood"
            
            sections.append(f"Use **{persona_name}** when:")
            for use_case in use_when[:3]:  # Top 3 use cases
                sections.append(f"- {use_case}")
            sections.append("")
        
        sections.append("## How to Query")
        sections.append("```")
        sections.append('qmd search "<describe your task>" -c coaching-personas')
        sections.append("```")
        sections.append("")
        
        return '\n'.join(sections), personas

    # For 00-START-HERE.md section
    lines = []
    for folder, description in personas:
        lines.append(f"- **{folder}**: {description}")
    return '\n'.join(lines), personas


def run_qmd_update():
    """Auto-run QMD update and embed after wiring personas."""
    telegram_print("\n🔄 Running QMD update after persona wiring...")
    try:
        result = subprocess.run(["qmd", "update"], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            telegram_print("  ✓ python3 ~/clawd/scripts/gemini-indexer.py complete")
        else:
            telegram_print(f"  ⚠️ python3 ~/clawd/scripts/gemini-indexer.py: {result.stderr[:100]}")
    except Exception as e:
        telegram_print(f"  ⚠️ python3 ~/clawd/scripts/gemini-indexer.py failed: {e}")
    
    telegram_print("🔄 Running QMD embed...")
    try:
        result = subprocess.run(["qmd", "embed"], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            telegram_print("  ✓ # Handled by gemini-indexer.py complete")
        else:
            telegram_print(f"  ⚠️ # Handled by gemini-indexer.py: {result.stderr[:100]}")
    except Exception as e:
        telegram_print(f"  ⚠️ # Handled by gemini-indexer.py failed: {e}")


def audit_mode(workspace, personas_installed):
    """Option C - scan existing workspace, fill gaps, wire personas if available."""
    telegram_print(f"\n🔍 AUDIT MODE - Scanning {workspace}\n")
    added = []
    updated = []

    for item in os.listdir(workspace):
        dept_path = os.path.join(workspace, item)
        if not os.path.isdir(dept_path) or not item.endswith(DEPT_SUFFIX):
            continue

        dept_key = item.replace(DEPT_SUFFIX, "")
        print(f"[{item}]")

        # Wire personas if installed and governing-personas.md missing
        if personas_installed:
            gp_file = os.path.join(dept_path, "governing-personas.md")
            if not os.path.exists(gp_file):
                persona_file_content, _ = build_governing_personas_content(dept_key=dept_key, for_file=True)
                if persona_file_content:
                    create_file(gp_file, persona_file_content)
                    added.append(f"{item}/governing-personas.md")

        # Scan role folders
        for role in os.listdir(dept_path):
            role_path = os.path.join(dept_path, role)
            if not os.path.isdir(role_path):
                continue

            role_title = role.replace('-', ' ').title()
            dept_name = f"{dept_key.title()} Department"
            role_key = role.lower().replace('-', '_')

            # Add missing files
            for fname, template, kwargs in [
                ("good-examples.md", GOOD_EXAMPLES_TEMPLATE, {"role_title": role_title}),
                ("bad-examples.md", BAD_EXAMPLES_TEMPLATE, {"role_title": role_title}),
                ("tools.md", TOOLS_TEMPLATE, {"role_title": role_title}),
            ]:
                fpath = os.path.join(role_path, fname)
                if not os.path.exists(fpath):
                    create_file(fpath, template.format(**kwargs))
                    added.append(f"{item}/{role}/{fname}")

            # Add ROLE-LEVEL governing-personas.md if personas installed
            if personas_installed:
                role_gp_file = os.path.join(role_path, "governing-personas.md")
                if not os.path.exists(role_gp_file):
                    role_persona_content, _ = build_role_personas_content(role_key, dept_key, for_file=True)
                    if role_persona_content:
                        create_file(role_gp_file, role_persona_content)
                        added.append(f"{item}/{role}/governing-personas.md")

            # Add/update Governing Personas section to 00-START-HERE.md if personas installed
            if personas_installed:
                start_here = os.path.join(role_path, "00-START-HERE.md")
                if os.path.exists(start_here):
                    with open(start_here, 'r') as f:
                        content = f.read()
                    
                    # Check if old or new governing personas section exists
                    if "Governing Personas" not in content or "Multiple personas govern this role" not in content:
                        # Use role-specific personas if available, fall back to dept
                        persona_lines, _ = build_role_personas_content(role_key, dept_key, for_file=False)
                        if not persona_lines:
                            persona_lines, _ = build_governing_personas_content(dept_key=dept_key, for_file=False)
                        
                        if persona_lines:
                            gov_section = GOVERNING_PERSONAS_SECTION.format(persona_list=persona_lines)
                            
                            # If old section exists, replace it; otherwise append
                            if "Governing Personas" in content:
                                # Find and replace old section
                                import re
                                pattern = r'## Governing Personas.*?(?=\n## |\Z)'
                                content = re.sub(pattern, gov_section.strip(), content, flags=re.DOTALL)
                                with open(start_here, 'w') as f:
                                    f.write(content)
                            else:
                                # Append new section before "Where to Find Examples"
                                content = content.replace("## Where to Find Examples", gov_section + "## Where to Find Examples")
                                with open(start_here, 'w') as f:
                                    f.write(content)
                            
                            updated.append(f"{item}/{role}/00-START-HERE.md")

    telegram_print("\n" + "="*50)
    telegram_print("✅ AUDIT COMPLETE")
    telegram_print("="*50)
    if added:
        telegram_print(f"\n📁 Added {len(added)} missing files:")
        for f in added:
            telegram_print(f"  + {f}")
    if updated:
        telegram_print(f"\n📝 Updated {len(updated)} existing files:")
        for f in updated:
            telegram_print(f"  ~ {f}")
    if not added and not updated:
        telegram_print("\n✓ Everything looks good - no gaps found.")
    if personas_installed:
        telegram_print("\n✅ Persona wiring complete.")
        # Auto-run QMD update after wiring
        run_qmd_update()
    else:
        telegram_print("\nℹ️ Install Skill 22 and re-run to wire personas.")


def build_workforce_automated(context, interview_data, departments):
    """Option A - Build workforce based on interview answers."""
    workspace = ask_interview_style(
        "Where should I build your workforce folder?",
        example="~/Downloads/my-ai-workforce",
        default="~/Downloads/my-ai-workforce"
    )
    workspace = os.path.expanduser(workspace)
    
    business_name = interview_data.get("business_name", "My Business")
    
    telegram_print("\n" + "="*50)
    telegram_print(f"🏗️ BUILDING WORKFORCE FOR: {business_name}")
    telegram_print("="*50)
    
    personas_installed = check_personas_installed()
    
    # Get roles for each department
    dept_roles = {}
    for dept in departments:
        if dept == "master-orchestrator":
            continue  # No roles for master orchestrator
            
        telegram_print(f"\n📋 Let's define roles for {dept}-dept:")
        telegram_print("   Example roles:")
        
        # Show example roles based on department type
        examples = {
            "marketing": "content-creator, social-media-manager, ads-specialist",
            "sales": "appointment-setter, closer, account-manager, sdr",
            "billing": "invoice-specialist, collections, payment-processor",
            "customer-support": "support-agent, onboarding-specialist, customer-success-manager",
            "operations": "project-manager, systems-admin, process-analyst, operations-manager",
            "creative": "graphic-designer, video-producer, copywriter",
            "hr-people": "recruiter, onboarding-coordinator, hr-manager",
            "legal-compliance": "contract-specialist, compliance-officer",
            "it-tech": "developer, sysadmin, helpdesk",
        }
        
        example_roles = examples.get(dept, "generalist, specialist")
        telegram_print(f"   • {example_roles}")
        
        roles_input = input(f"\n   What roles exist in {dept}? (comma-separated, or 'skip' for defaults): ").strip()
        
        if roles_input.lower() == 'skip' or not roles_input:
            # Use smart defaults based on department
            if dept == "marketing":
                roles = ['content-creator', 'social-media-manager']
            elif dept == "sales":
                roles = ['appointment-setter', 'closer']
            elif dept == "operations":
                roles = ['project-manager']
            elif dept == "customer-support":
                roles = ['support-agent']
            else:
                roles = ['general']
        else:
            roles = [r.strip().lower().replace(' ', '-') for r in roles_input.split(",") if r.strip()]
        
        dept_roles[dept] = roles
        telegram_print(f"   ✓ Added roles: {', '.join(roles)}")
    
    telegram_print(f"\n🔨 Creating folders and files at {workspace}...")
    os.makedirs(workspace, exist_ok=True)

    routing_sections = []

    for dept in departments:
        dept_folder = os.path.join(workspace, f"{dept}{DEPT_SUFFIX}")
        os.makedirs(dept_folder, exist_ok=True)
        telegram_print(f"\n📁 [{dept.upper()}-DEPT]")

        # Master orchestrator is special - no roles, just files
        if dept == "master-orchestrator":
            create_file(
                os.path.join(dept_folder, "00-Master-Orchestrator-Start-Here.md"),
                "# Master Orchestrator - Start Here\n\nThis is the Big Boss department.\n\n## What It Does\n- Receives ALL incoming work\n- Decides which department handles each task\n- Routes work to the right place\n- Tracks completion\n- Creates missing SOPs when needed\n\n## Rules\n- All departments report back here\n- If unsure where something goes, decide based on end goal\n- If a department has no training, create the missing how-to file\n"
            )
            create_file(
                os.path.join(dept_folder, "01-How-to-Route-Work.md"),
                "# How to Route Work to Departments\n\n## Decision Tree\n1. Read the incoming task\n2. Identify keywords and intent\n3. Match to department based on task type\n4. Send to the right department/role/file\n\n## Routing Map\n- Marketing tasks → marketing-dept/\n- Sales tasks → sales-dept/\n- Billing tasks → billing-dept/\n- Support tasks → customer-support-dept/\n- Operations tasks → operations-dept/\n"
            )
            continue

        # Build governing personas content if installed
        dept_persona_lines = None
        dept_persona_file_content = None
        if personas_installed:
            dept_persona_lines, _ = build_governing_personas_content(dept_key=dept, for_file=False)
            if dept_persona_lines:
                dept_persona_file_content, _ = build_governing_personas_content(dept_key=dept, for_file=True)
                create_file(
                    os.path.join(dept_folder, "governing-personas.md"),
                    dept_persona_file_content or "# Governing Personas\n\n[No personas mapped for this department yet]\n"
                )

        routing_lines = [f"## {dept.title()} Tasks"]
        routing_lines.append(f"- [describe task type] → {dept}{DEPT_SUFFIX}/[role]/")
        routing_sections.append('\n'.join(routing_lines))

        for role in dept_roles.get(dept, ['general']):
            role_folder = os.path.join(dept_folder, role)
            os.makedirs(role_folder, exist_ok=True)

            role_title = role.replace('-', ' ').title()
            dept_name = f"{dept.title()} Department"
            role_key = role.lower().replace('-', '_')

            # Build ROLE-SPECIFIC governing personas content if installed
            role_persona_lines = None
            role_persona_file_content = None
            if personas_installed:
                # Try to get role-specific personas
                role_persona_lines, _ = build_role_personas_content(role_key, dept, for_file=False)
                role_persona_file_content, _ = build_role_personas_content(role_key, dept, for_file=True)
                
                # Fall back to department personas if no role-specific mapping
                if not role_persona_lines:
                    role_persona_lines = dept_persona_lines

            # Create ROLE-LEVEL governing-personas.md with new template
            if personas_installed and role_persona_file_content:
                create_file(
                    os.path.join(role_folder, "governing-personas.md"),
                    role_persona_file_content
                )

            # Build governing personas section for START-HERE if personas installed
            if personas_installed and role_persona_lines:
                gov_section = GOVERNING_PERSONAS_SECTION.format(persona_list=role_persona_lines)
            else:
                gov_section = ""

            create_file(
                os.path.join(role_folder, "00-START-HERE.md"),
                START_HERE_TEMPLATE.format(
                    role_title=role_title,
                    dept_name=dept_name,
                    role_name=role_title,
                    governing_personas_section=gov_section
                )
            )
            create_file(
                os.path.join(role_folder, "01-first-task.md"),
                TASK_TEMPLATE.format(task_title="First Task")
            )
            create_file(
                os.path.join(role_folder, "good-examples.md"),
                GOOD_EXAMPLES_TEMPLATE.format(role_title=role_title)
            )
            create_file(
                os.path.join(role_folder, "bad-examples.md"),
                BAD_EXAMPLES_TEMPLATE.format(role_title=role_title)
            )
            create_file(
                os.path.join(role_folder, "tools.md"),
                TOOLS_TEMPLATE.format(role_title=role_title)
            )

    # Universal SOPs
    universal_sops = os.path.join(workspace, "universal-sops")
    os.makedirs(universal_sops, exist_ok=True)
    routing_content = ROUTING_TEMPLATE.format(routing_sections='\n\n'.join(routing_sections))
    create_file(os.path.join(universal_sops, "00-ROUTING.md"), routing_content)
    create_file(os.path.join(universal_sops, "tools.md"), "# Universal Tools\n\n[Tools used across all departments]\n")

    # Re-detection after questions: re-check for personas
    telegram_print("\n🔍 Re-detecting coaching personas after build...")
    personas_still_installed = check_personas_installed()
    if personas_still_installed and personas_installed:
        telegram_print("✅ Personas still detected - wiring complete")
        # Auto-run QMD update after wiring personas
        run_qmd_update()
    elif personas_still_installed and not personas_installed:
        telegram_print("✅ Personas detected post-build - wiring now...")
        # Run audit mode to wire personas into existing structure
        audit_mode(workspace, True)
    else:
        telegram_print("ℹ️ Personas not detected - build complete without persona wiring")

    telegram_print("\n" + "="*50)
    telegram_print("✅ BUILD COMPLETE")
    telegram_print("="*50)
    telegram_print(f"\n📁 Workforce folder: {workspace}")
    telegram_print(f"📊 Departments built: {len(departments)}")
    if personas_installed or personas_still_installed:
        telegram_print(f"✅ Governing personas wired to all departments and roles")
    telegram_print(f"\n🎯 Next steps:")
    telegram_print("  1. Open each 00-START-HERE.md and fill in role details")
    telegram_print("  2. Rename 01-first-task.md to match your actual tasks")
    telegram_print("  3. Add your tools to each tools.md")
    telegram_print("  4. Update universal-sops/00-ROUTING.md with your task types")


def preflight_check():
    """Pre-flight check: Skill 23 requires Skill 22 to be fully installed first."""
    try:
        result = subprocess.run(
            ["qmd", "status"],
            capture_output=True, text=True, timeout=10
        )
        if "coaching-personas" in result.stdout:
            return True, "coaching-personas collection found"
    except Exception:
        pass
    
    # Fallback check - skill folder exists
    skill_path = os.path.expanduser("~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/")
    if os.path.exists(skill_path):
        return True, "Skill 22 folder found (collection may need embedding)"
    
    return False, "Skill 22 (Book-to-Persona) not installed"


def main():
    telegram_print("\n" + "="*50)
    telegram_print("🚀 AI WORKFORCE BLUEPRINT - Scaffold Builder")
    telegram_print("="*50)
    
    # PRE-FLIGHT CHECK: Skill 23 requires Skill 22
    telegram_print("\n🔍 Running pre-flight check for Skill 22...")
    skill22_ok, skill22_msg = preflight_check()
    
    if not skill22_ok:
        telegram_print("\n" + "❌"*25)
        telegram_print("❌ PRE-FLIGHT CHECK FAILED")
        telegram_print("❌"*25)
        telegram_print(f"\nReason: {skill22_msg}")
        telegram_print("\nSkill 23 (AI Workforce Blueprint) requires Skill 22 to be fully installed first.")
        telegram_print("\nTo proceed:")
        telegram_print("  1. Navigate to 22-book-to-persona-coaching-leadership-system/")
        telegram_print("  2. Complete all installation steps (including QMD setup)")
        telegram_print("  3. Run: qmd status | grep coaching-personas")
        telegram_print("  4. Return here and re-run this script")
        telegram_print("\n" + "❌"*25)
        sys.exit(1)
    
    telegram_print(f"✅ Pre-flight check passed: {skill22_msg}")

    # Check for personas
    personas_installed = check_personas_installed()
    if personas_installed:
        telegram_print("\n✅ Coaching Personas Matrix detected - personas will be wired automatically.")
    else:
        telegram_print("\nℹ️ Coaching Personas Matrix not detected - building clean structure.")
        telegram_print("   (Install Skill 22 later and re-run to add personas.)")

    # Check for existing workspace
    existing = detect_existing_workspace()
    if existing:
        telegram_print(f"\n📁 Existing workforce found at: {existing}")
        run_audit = input("\nRun in audit mode? Adds missing files, wires personas. (Y/n): ").strip().lower()
        if run_audit != 'n':
            audit_mode(existing, personas_installed)
            return

    # Present options
    show_options()
    
    choice = input("\nEnter your choice (A/B/C): ").strip().upper()
    
    if choice == "B":
        telegram_print("\n📖 MANUAL BUILD SELECTED")
        telegram_print("\nPlease read ai-workforce-blueprint-full.md for step-by-step instructions.")
        telegram_print("Come back and run this script again when you are ready for Option A or C.")
        return
    
    elif choice == "C":
        telegram_print("\n🔍 AUDIT MODE SELECTED")
        workspace = input("Enter path to your workforce folder: ").strip()
        workspace = os.path.expanduser(workspace)
        if os.path.isdir(workspace):
            audit_mode(workspace, personas_installed)
        else:
            telegram_print(f"❌ Folder not found: {workspace}")
        return
    
    else:  # Default to Option A
        telegram_print("\n🚀 FULL AUTOMATED BUILD SELECTED")
        
        # Show pre-built departments
        show_prebuilt_departments()
        
        # Load existing context to avoid asking known questions
        telegram_print("\n📋 Loading your existing context...")
        context = load_existing_context()
        if context.get("business_name"):
            telegram_print(f"✓ Found business info: {context['business_name']}")
        
        # Get department selection
        departments = get_department_selection()
        
        # Always include master orchestrator
        if "master-orchestrator" not in departments:
            departments.append("master-orchestrator")
        
        telegram_print(f"\n✓ Selected {len(departments)} departments")
        
        # Conduct interview
        interview_data = interview_user(context)
        
        # Build the workforce
        build_workforce_automated(context, interview_data, departments)


if __name__ == "__main__":
    main()
