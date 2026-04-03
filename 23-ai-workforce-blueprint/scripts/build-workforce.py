#!/usr/bin/env python3
"""
AI Workforce Blueprint - Interview Engine & Workspace Builder
Version: 2.1.0
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

NON-INTERACTIVE MODE:
- Pass --non-interactive to read all config from a JSON file instead of prompting
- Use --config-file to specify the JSON config path (default: workforce-config.json)
- This is required when running via AI agent that cannot handle interactive prompts

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
import argparse
import shutil
from datetime import datetime
from pathlib import Path


# ============================================================
# ARGUMENT PARSING
# ============================================================

def parse_args():
    """Parse command-line arguments. Supports --non-interactive for AI agent use."""
    parser = argparse.ArgumentParser(
        description="AI Workforce Blueprint - Interview Engine & Workspace Builder"
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Read config from --config-file instead of prompting interactively'
    )
    parser.add_argument(
        '--config-file',
        default='workforce-config.json',
        help='JSON config file for non-interactive mode (default: workforce-config.json)'
    )
    return parser.parse_args()


def load_non_interactive_config(config_file):
    """
    Load workforce config from a JSON file for non-interactive mode.

    Expected JSON structure:
    {
        "company_name": "Acme Corp",
        "company_description": "We sell widgets online",
        "industry": "e-commerce",
        "tools": "Stripe, Convert and Flow, Shopify",
        "biggest_challenge": "Customer retention after first purchase",
        "departments": {
            "marketing": {
                "enabled": true,
                "activities": "Daily social media posts, weekly email campaigns",
                "kpis": "10K followers by Q3, 25% email open rate",
                "tools": "Convert and Flow, Canva, Later",
                "challenges": "No consistent posting schedule"
            },
            "sales": {
                "enabled": true,
                "activities": "Inbound lead follow-up, demo calls",
                "kpis": "Close 10 deals per month",
                "tools": "Convert and Flow, Calendly",
                "challenges": "Slow response time to inbound leads"
            }
        },
        "option": "A"
    }
    """
    if not os.path.isfile(config_file):
        print(f"[NON-INTERACTIVE ERROR] Config file not found: {config_file}", file=sys.stderr)
        print(f"[NON-INTERACTIVE ERROR] Create a workforce-config.json or use --config-file to specify path.",
              file=sys.stderr)
        sys.exit(1)

    with open(config_file, 'r') as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[NON-INTERACTIVE ERROR] Invalid JSON in {config_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Validate required fields
    required = ["company_name", "industry", "departments"]
    missing = [k for k in required if k not in config]
    if missing:
        print(f"[NON-INTERACTIVE ERROR] Missing required config keys: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


def build_from_config(config):
    """
    Build the full workforce from a non-interactive config JSON.

    This replaces the conversational interview flow with a direct build
    from the provided configuration. All department workspaces, specialists,
    and supporting files are created without any interactive prompts.
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # Detect environment
    MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")

    company_name = config["company_name"]
    industry = config.get("industry", "")
    company_description = config.get("company_description", "")
    tools = config.get("tools", "")
    biggest_challenge = config.get("biggest_challenge", "")

    # Build core interview answers dict (used by all department functions)
    core_answers = {
        "company_name": company_name,
        "industry": industry,
        "company_description": company_description,
        "tools": tools,
        "biggest_challenge": biggest_challenge,
    }

    print(f"[NON-INTERACTIVE] Building workforce for: {company_name}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Industry: {industry}", file=sys.stderr)

    # Save the config as the interview answers
    discovery_dir = _ensure_company_discovery_dir()
    if discovery_dir:
        answers_path = os.path.join(discovery_dir, "workforce-interview-answers.md")
        with open(answers_path, 'w') as f:
            f.write(f"# Workforce Interview Answers (Non-Interactive)\n\n")
            f.write(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")
            f.write(f"**Q:** What is the name of your business?\n**A:** {company_name}\n\n---\n\n")
            f.write(f"**Q:** What industry are you in?\n**A:** {industry}\n\n---\n\n")
            if company_description:
                f.write(f"**Q:** What does your business do?\n**A:** {company_description}\n\n---\n\n")
            if tools:
                f.write(f"**Q:** What tools do you use?\n**A:** {tools}\n\n---\n\n")
            if biggest_challenge:
                f.write(f"**Q:** What is your biggest challenge?\n**A:** {biggest_challenge}\n\n---\n\n")

    # Process departments
    departments_config = config.get("departments", {})
    selected_departments = {}

    for dept_id, dept_config in departments_config.items():
        if dept_config.get("enabled", True):
            if dept_id in RECOMMENDED_DEPARTMENTS:
                selected_departments[dept_id] = RECOMMENDED_DEPARTMENTS[dept_id].copy()
            else:
                # Custom department
                selected_departments[dept_id] = {
                    "name": dept_config.get("name", dept_id.replace("-", " ").title()),
                    "emoji": dept_config.get("emoji", "\U0001f4c1"),
                    "head": dept_config.get("head", f"Chief {dept_id.replace('-', ' ').title()} Officer"),
                    "description": dept_config.get("activities", ""),
                }

    print(f"[NON-INTERACTIVE] Departments: {', '.join(selected_departments.keys())}", file=sys.stderr)

    # Create department workspaces
    specialists_by_dept = {}
    for dept_id, dept_info in selected_departments.items():
        dept_config = departments_config.get(dept_id, {})

        # Build per-department interview answers
        dept_answers = {
            **core_answers,
            "department_activities": dept_config.get("activities", dept_info["description"]),
            "department_kpis": dept_config.get("kpis", ""),
            "department_tools": dept_config.get("tools", tools),
            "department_challenges": dept_config.get("challenges", ""),
        }

        # Create workspace
        dept_dir = create_department_workspace(dept_id, dept_info, dept_answers)
        print(f"[NON-INTERACTIVE] Created workspace: {dept_dir}", file=sys.stderr)

        # Log department answers
        if discovery_dir:
            with open(answers_path, 'a') as f:
                f.write(f"**Q:** Tell me about your {dept_info['name']} department.\n")
                f.write(f"**A:** Activities: {dept_config.get('activities', 'N/A')}\n")
                f.write(f"KPIs: {dept_config.get('kpis', 'N/A')}\n")
                f.write(f"Challenges: {dept_config.get('challenges', 'N/A')}\n\n---\n\n")

        # Determine specialists
        specialists, decision_ctx = determine_specialists(dept_id, dept_info, dept_answers)
        specialists_by_dept[dept_id] = specialists

    # Load persona categories and create governing personas
    persona_categories = load_persona_categories()
    for dept_id, dept_info in selected_departments.items():
        personas_md = create_governing_personas_md(dept_id, dept_info, persona_categories)
        personas_path = os.path.join(DEPARTMENTS_DIR, dept_id, "governing-personas.md")
        with open(personas_path, 'w') as f:
            f.write(personas_md)

    # Generate ORG-CHART.md
    org_chart = generate_org_chart(selected_departments, specialists_by_dept)
    org_chart_path = os.path.join(WORKSPACE_ROOT, "ORG-CHART.md")
    with open(org_chart_path, 'w') as f:
        f.write(org_chart)
    print(f"[NON-INTERACTIVE] Created ORG-CHART.md", file=sys.stderr)

    # Generate departments.json for Command Center
    departments_json = generate_departments_json(selected_departments)
    if discovery_dir:
        dept_json_path = os.path.join(discovery_dir, "departments.json")
        with open(dept_json_path, 'w') as f:
            json.dump(departments_json, f, indent=2)
        print(f"[NON-INTERACTIVE] Created departments.json", file=sys.stderr)

    # Update openclaw.json config
    if os.path.isfile(OPENCLAW_CONFIG):
        try:
            backup_path = backup_config()
            print(f"[NON-INTERACTIVE] Config backed up to: {backup_path}", file=sys.stderr)

            config_data = load_openclaw_config()
            for dept_id, dept_info in selected_departments.items():
                add_agent_to_config(config_data, dept_id, dept_info)
            save_openclaw_config(config_data)
            print(f"[NON-INTERACTIVE] Config updated with {len(selected_departments)} department agents", file=sys.stderr)
        except Exception as e:
            print(f"[NON-INTERACTIVE WARNING] Config update failed: {e}", file=sys.stderr)
    else:
        print(f"[NON-INTERACTIVE WARNING] openclaw.json not found at {OPENCLAW_CONFIG} - skipping agent config",
              file=sys.stderr)

    # Save handoff as completed
    create_handoff(
        option=config.get("option", "A"),
        departments_done=list(selected_departments.keys()),
        departments_remaining=[],
        progress_pct=100
    )

    print(f"\n[NON-INTERACTIVE] Build complete!", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Company: {company_name}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Departments: {len(selected_departments)}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Workspace: {DEPARTMENTS_DIR}", file=sys.stderr)


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
    """
    Find the master files folder in ~/Downloads/ (case-insensitive search).
    
    FALLBACK BEHAVIOR (hardened):
    - If ~/Downloads/ exists and a matching folder is found: use it (normal path)
    - If ~/Downloads/ exists but no matching folder: create ~/Downloads/openclaw-master-files/
    - If ~/Downloads/ does NOT exist (e.g., VPS, Docker, headless):
        use ~/clawd/data/ as the safe fallback location
    - ALWAYS print a warning to stderr when falling back so the agent knows.
    - NEVER returns None. A persistence path is always guaranteed.
    """
    downloads = os.path.join(HOME, "Downloads")
    
    # Primary search: ~/Downloads/
    if os.path.isdir(downloads):
        for name in os.listdir(downloads):
            lower = name.lower().replace(" ", "-").replace("_", "-")
            if "openclaw" in lower and ("master" in lower or "files" in lower or "documents" in lower):
                path = os.path.join(downloads, name)
                if os.path.isdir(path):
                    return path
        # ~/Downloads exists but no matching folder found - create default
        path = os.path.join(downloads, "openclaw-master-files")
        os.makedirs(path, exist_ok=True)
        return path
    
    # FALLBACK: ~/Downloads/ does not exist (VPS, Docker, headless environment)
    # Use ~/clawd/data/ as a safe data-side location that survives restarts
    fallback = os.path.join(HOME, "clawd", "data")
    os.makedirs(fallback, exist_ok=True)
    print(f"[PERSISTENCE WARNING] ~/Downloads/ not found. Using fallback persistence path: {fallback}",
          file=sys.stderr)
    print(f"[PERSISTENCE WARNING] Interview answers and handoff files will be saved to: {fallback}/company-discovery/",
          file=sys.stderr)
    return fallback


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


def _ensure_company_discovery_dir():
    """
    Ensure COMPANY_DISCOVERY_DIR is set and the directory exists.
    If MASTER_FILES was not detected, force re-detection with fallback.
    Returns the path or None if truly impossible (should never happen after hardening).
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR
    if not COMPANY_DISCOVERY_DIR:
        # Re-detect with fallback guarantee
        MASTER_FILES = find_master_files_folder()
        if MASTER_FILES:
            COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")
    if not COMPANY_DISCOVERY_DIR:
        print("[PERSISTENCE ERROR] Cannot determine company-discovery path. "
              "Interview answers will NOT be saved this session.", file=sys.stderr)
        return None
    os.makedirs(COMPANY_DISCOVERY_DIR, exist_ok=True)
    return COMPANY_DISCOVERY_DIR


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
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] create_handoff() - handoff file NOT saved.", file=sys.stderr)
        return
    handoff_path = os.path.join(discovery_dir, "interview-handoff.md")
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
    print(f"[PERSISTENCE] Handoff saved to: {handoff_path}", file=sys.stderr)


def log_fallback(question, client_response, fallback_type):
    """
    Log when a client hesitates or doesn't know an answer.
    This data improves the interview for future clients.

    fallback_type: 'offered_research' | 'presented_options' | 'skipped' | 'client_stopped'
    """
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] log_fallback() - analytics NOT saved.", file=sys.stderr)
        return
    analytics_dir = os.path.join(discovery_dir, "interview-analytics")
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
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] log_answer() - answer NOT saved. Progress may be lost if session ends.",
              file=sys.stderr)
        return
    answers_path = os.path.join(discovery_dir, "workforce-interview-answers.md")

    # Create file with header if it doesn't exist
    if not os.path.isfile(answers_path):
        with open(answers_path, 'w') as f:
            f.write(f"# Workforce Interview Answers\n\nStarted: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")

    # Append the Q&A
    with open(answers_path, 'a') as f:
        f.write(f"**Q:** {question}\n")
        f.write(f"**A:** {answer}\n")
        f.write(f"**Logged:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")
    print(f"[PERSISTENCE] Answer logged to: {answers_path}", file=sys.stderr)


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

    # Step 1: Detect environment (guaranteed non-None after hardening)
    MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")
    print(f"[PERSISTENCE] Master files folder: {MASTER_FILES}", file=sys.stderr)
    print(f"[PERSISTENCE] Interview answers will be saved to: {COMPANY_DISCOVERY_DIR}/", file=sys.stderr)

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
    args = parse_args()
    if args.non_interactive:
        config = load_non_interactive_config(args.config_file)
        build_from_config(config)
    else:
        main()
