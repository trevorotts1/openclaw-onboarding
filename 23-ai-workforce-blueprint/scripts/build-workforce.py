#!/usr/bin/env python3
"""
AI Workforce Blueprint - Interview Engine & Workspace Builder
Version: 2.0.0
Date: March 22, 2026

This is the core engine for Skill 23 (AI Workforce Blueprint).
It handles:
1. Option A/B/C selection (ALWAYS presented, never skipped)
2. Dynamic interview (3-7 questions per department, plain English)
3. Department workspace creation with core file inheritance
4. Specialist determination (permanent vs on-call, decided by AI silently)
5. Persona alignment using the Act As If Protocol and 5-layer check
6. ORG-CHART.md generation
7. Devil's Advocate auto-creation per department
8. Command Center departments.json generation
9. Flush after every question (resume capability via handoff file)
10. Config safety (backup before edits, validate JSON after)

IMPORTANT:
- This script is executed BY the AI agent, not run directly by the client
- The AI reads this file to understand the interview flow and executes it conversationally
- Questions are generated dynamically based on industry and context, not from a static list
- The AI MUST be running on a high reasoning model (Opus, Sonnet, MiMo V2 Pro, Gemini 3.1 Pro, GPT 5.4)
- Research best practices uses openrouter/perplexity/sonar-pro-search

FORBIDDEN CLIENT-FACING LANGUAGE:
- Never say: SOPs, handoffs, tech stack, permanent agent, sub-agent, agent
- Instead say: step-by-step instructions, what departments share, tools you use, team member, specialist, director
"""

import os
import sys
import json
import shutil
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

HOME = os.path.expanduser("~")
WORKSPACE_ROOT = os.path.join(HOME, "clawd")
DEPARTMENTS_DIR = os.path.join(WORKSPACE_ROOT, "departments")
SUBAGENTS_DIR = os.path.join(WORKSPACE_ROOT, "subagents", "templates")
MASTER_FILES = None  # Detected at runtime
OPENCLAW_CONFIG = os.path.join(HOME, ".openclaw", "openclaw.json")
BACKUP_DIR = os.path.join(HOME, "Downloads", "openclaw-backups")
COMPANY_DISCOVERY_DIR = None  # Set after master files detected

# Files inherited from main CEO workspace
INHERITED_FILES = ["TOOLS.md", "AGENTS.md", "USER.md"]

# Files to check for existing context before asking questions
CONTEXT_FILES = ["USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"]

# Recommended departments with plain-English descriptions
# This is a SUGGESTION list, not hardcoded. The client chooses what they need.
RECOMMENDED_DEPARTMENTS = {
    "marketing": {"name": "Marketing", "emoji": "📢", "head": "Chief Marketing Officer", "description": "Getting the word out about your business - social media, ads, email, content"},
    "sales": {"name": "Sales", "emoji": "💰", "head": "Chief Sales Officer", "description": "Turning interested people into paying customers"},
    "billing": {"name": "Billing / Finance", "emoji": "💳", "head": "Chief Financial Officer", "description": "Invoices, payments, tracking your money"},
    "support": {"name": "Customer Support", "emoji": "🎧", "head": "Chief Customer Officer", "description": "Helping your existing customers when they need it"},
    "operations": {"name": "Operations", "emoji": "⚙️", "head": "Chief Operating Officer", "description": "Making sure the day-to-day runs smoothly"},
    "creative": {"name": "Creative", "emoji": "✍️", "head": "Chief Creative Officer", "description": "All the writing - blogs, emails, scripts, copy"},
    "hr": {"name": "HR / People", "emoji": "👥", "head": "Chief People Officer", "description": "Managing your team, hiring, culture"},
    "legal": {"name": "Legal / Compliance", "emoji": "⚖️", "head": "General Counsel", "description": "Contracts, regulations, keeping you protected"},
    "it": {"name": "IT / Tech", "emoji": "🖥️", "head": "Chief Technology Officer", "description": "Your technology, servers, software, security"},
    "webdev": {"name": "Web Development", "emoji": "🌐", "head": "Chief Web Officer", "description": "Your website, landing pages, funnels"},
    "appdev": {"name": "App Development", "emoji": "📱", "head": "Chief App Officer", "description": "Mobile apps, software applications"},
    "graphics": {"name": "Graphics", "emoji": "🎨", "head": "Chief Graphics Officer", "description": "Visual content - logos, images, brand assets"},
    "video": {"name": "Video", "emoji": "🎬", "head": "Chief Video Officer", "description": "Video production, editing, AI video"},
    "audio": {"name": "Audio", "emoji": "🎙️", "head": "Chief Audio Officer", "description": "Podcasts, voiceovers, music, audio production"},
    "research": {"name": "Research", "emoji": "🔬", "head": "Chief Research Officer", "description": "Market research, competitor analysis, data insights"},
    "comms": {"name": "Communications", "emoji": "📣", "head": "Chief Communications Officer", "description": "PR, announcements, internal and external messaging"},
    "ceo": {"name": "CEO / COM", "emoji": "👔", "head": "Chief Executive Officer", "description": "Executive strategy, vision, high-level decisions"},
}

# Model assignments per department type
# Creative/content departments use Kimi (fast, good for writing)
# Technical departments use GPT 5.4 (strong at code and systems)
# Legal/operations use Sonnet (careful, precise reasoning)
DEFAULT_MODEL_ASSIGNMENTS = {
    "creative": "moonshot/kimi-k2.5",
    "marketing": "moonshot/kimi-k2.5",
    "graphics": "moonshot/kimi-k2.5",
    "video": "moonshot/kimi-k2.5",
    "audio": "moonshot/kimi-k2.5",
    "research": "moonshot/kimi-k2.5",
    "comms": "moonshot/kimi-k2.5",
    "ceo": "moonshot/kimi-k2.5",
    "sales": "openai-codex/gpt-5.4",
    "it": "openai-codex/gpt-5.4",
    "webdev": "openai-codex/gpt-5.4",
    "appdev": "openai-codex/gpt-5.4",
    "operations": "anthropic/claude-sonnet-4-6",
    "legal": "anthropic/claude-sonnet-4-6",
    "support": "moonshot/kimi-k2.5",
    "billing": "moonshot/kimi-k2.5",
    "hr": "moonshot/kimi-k2.5",
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def find_master_files_folder():
    """Find the master files folder in ~/Downloads/ (case-insensitive search)."""
    downloads = os.path.join(HOME, "Downloads")
    if not os.path.isdir(downloads):
        return None
    for name in os.listdir(downloads):
        lower = name.lower().replace(" ", "-").replace("_", "-")
        if "openclaw" in lower and ("master" in lower or "files" in lower or "documents" in lower):
            path = os.path.join(downloads, name)
            if os.path.isdir(path):
                return path
    # Create if not found
    path = os.path.join(downloads, "openclaw-master-files")
    os.makedirs(path, exist_ok=True)
    return path


def backup_config():
    """Backup openclaw.json before any edits. Self-verifying."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%I%M%p")
    backup_name = f"openclaw-json-backup-{timestamp}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(OPENCLAW_CONFIG, backup_path)

    # Self-verify: check backup exists in the right place
    if not os.path.isfile(backup_path):
        raise RuntimeError(f"Backup failed: {backup_path} does not exist after copy")

    # Verify it's not in a hidden folder
    if "/." in backup_path:
        # Wrong location - re-backup to correct location
        correct_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(OPENCLAW_CONFIG, correct_path)
        if os.path.isfile(correct_path):
            backup_path = correct_path

    return backup_path


def validate_json(filepath):
    """Validate that a JSON file is parseable."""
    with open(filepath, 'r') as f:
        json.load(f)
    return True


def load_openclaw_config():
    """Load openclaw.json."""
    with open(OPENCLAW_CONFIG, 'r') as f:
        return json.load(f)


def save_openclaw_config(config):
    """Save openclaw.json with validation."""
    with open(OPENCLAW_CONFIG, 'w') as f:
        json.dump(config, f, indent=2)
    validate_json(OPENCLAW_CONFIG)


def read_existing_context():
    """Read existing workspace files for context before asking questions."""
    context = {}
    for filename in CONTEXT_FILES:
        filepath = os.path.join(WORKSPACE_ROOT, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'r') as f:
                context[filename] = f.read()
    return context


def read_previous_answers():
    """Read workforce-interview-answers.md if it exists (resume capability)."""
    if COMPANY_DISCOVERY_DIR:
        answers_file = os.path.join(COMPANY_DISCOVERY_DIR, "workforce-interview-answers.md")
        if os.path.isfile(answers_file):
            with open(answers_file, 'r') as f:
                return f.read()
    return None


def read_handoff():
    """Read interview-handoff.md if it exists (resume capability)."""
    if COMPANY_DISCOVERY_DIR:
        handoff_file = os.path.join(COMPANY_DISCOVERY_DIR, "interview-handoff.md")
        if os.path.isfile(handoff_file):
            with open(handoff_file, 'r') as f:
                return f.read()
    return None


# ============================================================
# WORKSPACE CREATION
# ============================================================

def create_department_workspace(dept_id, dept_info, interview_answers):
    """
    Create a full department workspace with all core files.

    Creates:
    - SOUL.md (unique, generated from interview answers)
    - MEMORY.md (empty)
    - HEARTBEAT.md (department-specific priorities)
    - memory/ folder
    - TOOLS.md (inherited from main workspace)
    - AGENTS.md (inherited from main workspace)
    - USER.md (inherited from main workspace)
    - governing-personas.md (pre-qualified persona pool)
    - devils-advocate/ folder
    """
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    os.makedirs(dept_dir, exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "devils-advocate"), exist_ok=True)

    # Inherit files from main workspace
    for filename in INHERITED_FILES:
        src = os.path.join(WORKSPACE_ROOT, filename)
        dst = os.path.join(dept_dir, filename)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst)

    # Create SOUL.md (generated from interview, not a template)
    soul_path = os.path.join(dept_dir, "SOUL.md")
    if not os.path.isfile(soul_path):
        soul_content = generate_soul_md(dept_id, dept_info, interview_answers)
        with open(soul_path, 'w') as f:
            f.write(soul_content)

    # Create empty MEMORY.md
    memory_path = os.path.join(dept_dir, "MEMORY.md")
    if not os.path.isfile(memory_path):
        with open(memory_path, 'w') as f:
            f.write(f"# MEMORY.md - {dept_info['name']} Department\n\n> Long-term state, decisions, and metrics for this department.\n> Updated by the department head after each work session.\n")

    # Create HEARTBEAT.md with department-specific priorities
    heartbeat_path = os.path.join(dept_dir, "HEARTBEAT.md")
    if not os.path.isfile(heartbeat_path):
        heartbeat_content = generate_heartbeat_md(dept_id, dept_info, interview_answers)
        with open(heartbeat_path, 'w') as f:
            f.write(heartbeat_content)

    return dept_dir


def generate_soul_md(dept_id, dept_info, interview_answers):
    """
    Generate a SOUL.md specific to this department based on interview answers.
    This is NOT a generic template. It reflects what the client actually said.

    interview_answers is a dict with keys like:
    - 'company_name': str
    - 'industry': str
    - 'department_activities': str (what the client said this dept does)
    - 'department_kpis': str (what success looks like)
    - 'department_tools': str (what tools this dept uses)
    - 'department_challenges': str (what's not working)
    """
    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    activities = interview_answers.get('department_activities', dept_info['description'])
    kpis = interview_answers.get('department_kpis', '')
    tools = interview_answers.get('department_tools', '')
    challenges = interview_answers.get('department_challenges', '')

    soul = f"""# SOUL.md - {dept_info['head']}

You are the {dept_info['head']} for {company_name}.

## Identity
- Title: {dept_info['head']}
- Department: {dept_info['name']}
- Company: {company_name}
- Industry: {industry}

## Role
You own the {dept_info['name'].lower()} department's performance. You receive tasks, delegate to specialists, monitor results, and report to the CEO.

## What This Department Does
{activities}
"""

    if kpis:
        soul += f"""
## What Success Looks Like
{kpis}
"""

    if tools:
        soul += f"""
## Tools This Department Uses
{tools}
"""

    if challenges:
        soul += f"""
## Current Challenges to Address
{challenges}
"""

    soul += """
## Responsibilities
1. Monitor department KPIs and metrics
2. Assign tasks to specialist team members
3. Review and approve outputs before delivery
4. Generate weekly performance summaries
5. Escalate blockers to the CEO
6. Operate under the Act As If Protocol - select the right persona for each task

## Communication Style
Direct, data-driven, results-focused. Always cite specific numbers. Never vague.
"""
    return soul


def generate_heartbeat_md(dept_id, dept_info, interview_answers):
    """Generate department-specific HEARTBEAT.md."""
    return f"""# HEARTBEAT.md - {dept_info['name']} Department

## Current Priorities
- Department just created. Awaiting first tasks.
- Review SOUL.md to understand role and responsibilities.
- Review governing-personas.md for available coaching personas.

## Standing Checks
- Check department KPIs weekly
- Review specialist output quality
- Report status to CEO agent

## Notes
- This department was created on {datetime.now().strftime('%B %d, %Y')}
"""


# ============================================================
# SPECIALIST DETERMINATION (Silent - no client questions)
# ============================================================

def determine_specialists(dept_id, dept_info, interview_answers):
    """
    Determine which specialist roles this department needs and whether
    each should be a permanent team member or on-call specialist.

    This runs SILENTLY. The client is never asked about agents vs sub-agents.
    The AI reads the interview answers and applies these rules.

    Returns a list of specialist dicts with 'type': 'permanent' or 'on-call'
    """
    activities = interview_answers.get('department_activities', '')
    activities_lower = activities.lower()

    # Decision keywords that indicate PERMANENT (recurring, memory-dependent)
    PERMANENT_SIGNALS = [
        'daily', 'weekly', 'every day', 'every week', 'regular',
        'recurring', 'ongoing', 'continuous', 'always', 'consistently',
        'schedule', 'routine', 'maintain', 'manage', 'track', 'monitor',
        'relationship', 'client', 'customer', 'follow up', 'follow-up',
        'campaign', 'pipeline', 'inbox', 'respond', 'report',
    ]

    # Decision keywords that indicate ON-CALL (occasional, no memory needed)
    ONCALL_SIGNALS = [
        'occasionally', 'sometimes', 'once', 'one-time', 'one time',
        'quarterly', 'annually', 'yearly', 'as needed', 'when needed',
        'project-based', 'project based', 'single', 'audit', 'review',
    ]

    specialists = []

    # The AI agent uses these signals PLUS its own reasoning about the
    # interview answers to determine specialists. This function provides
    # the framework and keyword detection. The AI adds judgment.
    #
    # Example flow:
    # 1. Client said "we post on social media every day" → permanent Social Media Manager
    # 2. Client said "we occasionally need a logo designed" → on-call Graphic Designer
    # 3. Client said "we send email campaigns weekly" → permanent Email Specialist
    # 4. Client said "we need a one-time website audit" → on-call Site Auditor

    # Count signals to help the AI make decisions
    permanent_score = sum(1 for signal in PERMANENT_SIGNALS if signal in activities_lower)
    oncall_score = sum(1 for signal in ONCALL_SIGNALS if signal in activities_lower)

    # Store scores for the AI to use in its reasoning
    decision_context = {
        'department': dept_id,
        'permanent_signals_found': permanent_score,
        'oncall_signals_found': oncall_score,
        'activities_text': activities,
        'recommendation': 'permanent' if permanent_score > oncall_score else 'on-call' if oncall_score > 0 else 'permanent',
    }

    # The AI reads decision_context and uses it alongside its own
    # understanding of the interview to build the specialist list.
    # Each specialist in the returned list should have:
    # {
    #     'id': 'social-media-manager',
    #     'name': 'Social Media Manager',
    #     'type': 'permanent' or 'on-call',
    #     'model': 'moonshot/kimi-k2.5',
    #     'reason': 'Client said they post daily on social media'
    # }

    return specialists, decision_context


# ============================================================
# PERSONA ALIGNMENT (Act As If Protocol)
# ============================================================

def load_persona_categories():
    """Load persona-categories.json for tag-based filtering."""
    # Check multiple possible locations
    paths = [
        os.path.join(HOME, "Downloads", "openclaw-master-files", "coaching-personas", "persona-categories.json"),
    ]
    if MASTER_FILES:
        paths.insert(0, os.path.join(MASTER_FILES, "coaching-personas", "persona-categories.json"))

    for path in paths:
        if os.path.isfile(path):
            with open(path, 'r') as f:
                return json.load(f)
    return None


def get_personas_for_category(categories_data, domain_tag):
    """Get all personas tagged with a specific domain."""
    if not categories_data or "personas" not in categories_data:
        return []
    matches = []
    for persona_id, data in categories_data["personas"].items():
        if domain_tag in data.get("domain", []):
            matches.append({
                "id": persona_id,
                "author": data.get("author", ""),
                "book": data.get("book", ""),
                "domain": data.get("domain", []),
                "perspective": data.get("perspective", []),
            })
    return matches


def create_governing_personas_md(dept_id, dept_info, categories_data):
    """
    Create governing-personas.md for a department.
    Lists the pre-qualified persona pool (passed Layers 1-2 at setup).
    Layers 3-5 run fresh per task at runtime.
    """
    # Map department IDs to relevant domain tags
    dept_to_domains = {
        "marketing": ["marketing", "copywriting", "communication"],
        "sales": ["sales", "communication", "strategy-innovation"],
        "billing": ["finance", "operations"],
        "support": ["communication", "coaching"],
        "operations": ["operations", "productivity-systems", "leadership"],
        "creative": ["copywriting", "marketing", "communication"],
        "hr": ["leadership", "coaching", "communication"],
        "legal": ["communication", "strategy-innovation"],
        "it": ["productivity-systems", "strategy-innovation", "operations"],
        "webdev": ["strategy-innovation", "marketing", "productivity-systems"],
        "appdev": ["strategy-innovation", "productivity-systems"],
        "graphics": ["marketing", "communication"],
        "video": ["marketing", "communication"],
        "audio": ["marketing", "communication"],
        "research": ["strategy-innovation", "operations"],
        "comms": ["communication", "leadership", "marketing"],
        "ceo": ["leadership", "strategy-innovation", "coaching", "mindset"],
    }

    domains = dept_to_domains.get(dept_id, ["leadership"])
    all_matches = []
    seen = set()

    if categories_data:
        for domain in domains:
            for persona in get_personas_for_category(categories_data, domain):
                if persona["id"] not in seen:
                    all_matches.append(persona)
                    seen.add(persona["id"])

    content = f"# Governing Personas - {dept_info['name']} Department\n\n"
    content += "These personas have been pre-qualified for this department (passed company mission and owner alignment).\n"
    content += "At runtime, the AI selects the best persona PER TASK using 5-layer alignment.\n"
    content += "The instruction is: 'Act as if you are [persona] executing this task.'\n\n"

    if all_matches:
        content += "## Available Personas\n\n"
        for p in all_matches:
            domains_str = ", ".join(p["domain"])
            perspective_str = ", ".join(p["perspective"]) if p["perspective"] else "general"
            content += f"- **{p['author']}** ({p['book']}) - domains: {domains_str} | perspective: {perspective_str}\n"
    else:
        content += "## No Personas Available\n\n"
        content += "Install Skill 22 (Book-to-Persona Coaching Leadership System) to add coaching personas.\n"
        content += "Then re-run this skill in Option C (audit mode) to wire personas in.\n"

    return content


# ============================================================
# ORG CHART GENERATION
# ============================================================

def generate_org_chart(departments, specialists_by_dept):
    """Generate ORG-CHART.md showing the full company structure."""
    content = "# Company Org Chart\n\n"
    content += f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
    content += "## CEO / Master Orchestrator (main agent)\n\n"

    for dept_id, dept_info in departments.items():
        content += f"### {dept_info['emoji']} {dept_info['name']} - {dept_info['head']}\n"
        specialists = specialists_by_dept.get(dept_id, [])
        if specialists:
            for spec in specialists:
                type_label = "full-time" if spec.get("type") == "permanent" else "on-call"
                content += f"  - {spec['name']} ({type_label})\n"
        else:
            content += "  - (specialists to be determined based on workload)\n"
        content += "\n"

    return content


# ============================================================
# COMMAND CENTER CONFIG GENERATION
# ============================================================

def generate_departments_json(departments):
    """
    Generate departments.json for the BlackCEO Command Center.
    Exact schema: [{ "id": str, "emoji": str, "name": str, "headTitle": str }]
    """
    entries = []
    for dept_id, dept_info in departments.items():
        entries.append({
            "id": dept_id,
            "emoji": dept_info["emoji"],
            "name": dept_info["name"],
            "headTitle": dept_info["head"],
        })
    return entries


# ============================================================
# AGENTS.LIST MANAGEMENT
# ============================================================

def add_agent_to_config(config, dept_id, dept_info):
    """Add a department head agent to openclaw.json agents.list."""
    agents_list = config.get("agents", {}).get("list", [])
    agent_id = f"dept-{dept_id}"

    # Check if already exists
    existing_ids = {a.get("id") for a in agents_list}
    if agent_id in existing_ids:
        return False  # Already exists, skip

    model = DEFAULT_MODEL_ASSIGNMENTS.get(dept_id, "moonshot/kimi-k2.5")
    workspace = os.path.join(DEPARTMENTS_DIR, dept_id)

    agent_entry = {
        "id": agent_id,
        "name": dept_info["head"],
        "workspace": workspace,
        "model": model,
    }

    agents_list.append(agent_entry)
    config["agents"]["list"] = agents_list
    return True


# ============================================================
# HANDOFF FILE MANAGEMENT
# ============================================================

def create_handoff(option, departments_done, departments_remaining, progress_pct):
    """Create or update the interview handoff file for resume capability."""
    if not COMPANY_DISCOVERY_DIR:
        return
    os.makedirs(COMPANY_DISCOVERY_DIR, exist_ok=True)
    handoff_path = os.path.join(COMPANY_DISCOVERY_DIR, "interview-handoff.md")
    content = f"""# Interview Handoff
## Last Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

## Option Selected: {option}
## Progress: {progress_pct}%

## Departments Completed:
{chr(10).join(f'- {d}' for d in departments_done) if departments_done else '- (none yet)'}

## Departments Remaining:
{chr(10).join(f'- {d}' for d in departments_remaining) if departments_remaining else '- (all done)'}
"""
    with open(handoff_path, 'w') as f:
        f.write(content)


def log_fallback(question, client_response, fallback_type):
    """
    Log when a client hesitates or doesn't know an answer.
    This data improves the interview for future clients.

    fallback_type: 'offered_research' | 'presented_options' | 'skipped' | 'client_stopped'
    """
    if not COMPANY_DISCOVERY_DIR:
        return
    analytics_dir = os.path.join(COMPANY_DISCOVERY_DIR, "interview-analytics")
    os.makedirs(analytics_dir, exist_ok=True)
    log_path = os.path.join(analytics_dir, "fallback-log.json")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "client_response": client_response,
        "fallback_type": fallback_type,
    }

    # Load existing log or create new
    entries = []
    if os.path.isfile(log_path):
        with open(log_path, 'r') as f:
            try:
                entries = json.load(f)
            except json.JSONDecodeError:
                entries = []

    entries.append(entry)

    with open(log_path, 'w') as f:
        json.dump(entries, f, indent=2)


def log_answer(question, answer):
    """Append a Q&A to workforce-interview-answers.md."""
    if not COMPANY_DISCOVERY_DIR:
        return
    os.makedirs(COMPANY_DISCOVERY_DIR, exist_ok=True)
    answers_path = os.path.join(COMPANY_DISCOVERY_DIR, "workforce-interview-answers.md")

    # Create file with header if it doesn't exist
    if not os.path.isfile(answers_path):
        with open(answers_path, 'w') as f:
            f.write(f"# Workforce Interview Answers\n\nStarted: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")

    # Append the Q&A
    with open(answers_path, 'a') as f:
        f.write(f"**Q:** {question}\n")
        f.write(f"**A:** {answer}\n")
        f.write(f"**Logged:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")


# ============================================================
# MAIN EXECUTION FLOW
# ============================================================

def main():
    """
    Main execution flow. This is called BY the AI agent, not directly by the client.
    The AI reads this file and executes the flow conversationally.

    FLOW:
    1. Detect environment (master files folder, existing context)
    2. ALWAYS present Option A/B/C (never skip)
    3. If Option A: run dynamic interview
    4. If Option B: read existing files, propose structure, get approval
    5. If Option C: scan existing structure, find gaps, fill them
    6. Create department workspaces with full core files
    7. Determine specialists (permanent vs on-call) silently
    8. Run persona alignment (Act As If Protocol, 5-layer check)
    9. Generate ORG-CHART.md
    10. Generate Command Center departments.json
    11. Create Devil's Advocate per department
    12. Update openclaw.json (backup first, validate after)
    13. Report completion with summary

    INTERVIEW RULES:
    - Dynamic questions (3-7 per department)
    - Plain English only, no jargon
    - Check existing files before asking
    - Confirm known info: "We already know X. Still correct?"
    - Offer research: "Not sure? I can research best practices for your industry."
    - Flush after every answered question
    - Update handoff file after every answer
    - Progress indicators at milestones
    - Use Perplexity sonar-pro-search for best practices research
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # Step 1: Detect environment
    MASTER_FILES = find_master_files_folder()
    if MASTER_FILES:
        COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")

    # Step 2: Read existing context
    existing_context = read_existing_context()
    previous_answers = read_previous_answers()
    handoff = read_handoff()

    # Step 3: Check for Skill 22 (Book-to-Persona)
    persona_categories = load_persona_categories()
    personas_available = persona_categories is not None

    # Step 4: Present options (MANDATORY - NEVER SKIP)
    # The AI agent presents these conversationally, not as code output
    print("""
    ==============================================
    AI WORKFORCE BLUEPRINT - COMPANY SETUP
    ==============================================

    Welcome! I'm going to help you set up your AI company.

    You have three options:

    Option A - Full Interview (Recommended)
    I'll ask you about your business and build everything
    based on your answers. Most personalized results.

    Option B - Quick Setup
    I'll use what I already know about you plus industry
    best practices. You review and adjust. Fastest path.

    Option C - Audit / Resume
    If you already have a workforce set up, or if we
    got interrupted last time, I'll pick up where we left off.

    Which option would you like?
    """)

    # The AI agent handles the response conversationally from here.
    # The functions above provide the building blocks.
    # The AI uses:
    #   - log_answer() after every question
    #   - create_handoff() after every answer
    #   - create_department_workspace() for each department
    #   - determine_specialists() for specialist decisions
    #   - create_governing_personas_md() for persona wiring
    #   - generate_org_chart() at the end
    #   - generate_departments_json() for the Command Center
    #   - add_agent_to_config() for each department head
    #   - backup_config() before ANY config edits
    #   - save_openclaw_config() with validation after edits


if __name__ == "__main__":
    main()
