#!/usr/bin/env python3
"""
AI Workforce Blueprint - Interview Engine & Workspace Builder
Version: 2.1.0
Date: March 22, 2026

TIMEOUT OVERRIDE:
For complex businesses with many departments, the full workforce build
(interview + workspace creation + persona wiring + config updates) can take
significant time. The recommended sub-agent timeout is 1800 seconds (30 minutes).
Set this when spawning the build agent to avoid premature termination on
large builds with 8+ departments and full knowledge base content generation.

This is the core engine for Skill 23 (AI Workforce Blueprint).
It handles:
1. Option A/B/C selection (ALWAYS presented, never skipped)
2. Dynamic interview (3-7 questions per department, plain English)
3. Department workspace creation with core file inheritance
4. Specialist determination (permanent vs on-call, decided by AI silently)
5. Persona alignment using the Act As If Protocol and 5-layer check
6. ORG-CHART.md generation
7. Devil's Advocate auto-creation per department (SOUL.md + SOP.md)
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

        # Create role subfolders, 00-START-HERE.md, governing-personas.md, and SOP stubs
        role_folders = create_role_workspace(dept_id, dept_info, dept_answers)
        print(f"[NON-INTERACTIVE] Created {len(role_folders)} role folders in {dept_id}/", file=sys.stderr)

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

    # Copy departments.json to Command Center config directory (bridge path gap)
    copy_departments_to_command_center(departments_json)

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

    # Generate/update persona-matrix.md for workforce visibility
    generate_persona_matrix(selected_departments, persona_categories, company_name)

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
        use ~/.openclaw/workspace/data/ as the safe fallback location
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
    # Use ~/.openclaw/workspace/data/ as a safe data-side location that survives restarts
    # Use ~/.openclaw/workspace/data as fallback (or /data/clawd/ on VPS)
    workspace_root = os.environ.get("WORKSPACE_ROOT", os.path.join(HOME, ".openclaw", "workspace"))
    if not os.path.isdir(workspace_root):
        workspace_root = os.path.join(HOME, "clawd")  # Legacy fallback
    fallback = os.path.join(workspace_root, "data")
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
    - devils-advocate/SOUL.md (mission, tone, methodology)
    - devils-advocate/SOP.md (review process step-by-step)
    """
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    os.makedirs(dept_dir, exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "devils-advocate"), exist_ok=True)

    # Create Devil's Advocate SOUL.md
    da_soul_path = os.path.join(dept_dir, "devils-advocate", "SOUL.md")
    if not os.path.isfile(da_soul_path):
        da_soul_content = generate_devils_advocate_soul_md(dept_id, dept_info, interview_answers)
        with open(da_soul_path, 'w') as f:
            f.write(da_soul_content)

    # Create Devil's Advocate SOP
    da_sop_path = os.path.join(dept_dir, "devils-advocate", "SOP.md")
    if not os.path.isfile(da_sop_path):
        da_sop_content = generate_devils_advocate_sop_md(dept_id, dept_info, interview_answers)
        with open(da_sop_path, 'w') as f:
            f.write(da_sop_content)

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


def generate_devils_advocate_soul_md(dept_id, dept_info, interview_answers):
    """
    Generate a SOUL.md for the Devil's Advocate role within a department.
    The Devil's Advocate exists to stress-test ideas, find blind spots,
    and prevent groupthink - not to block progress, but to strengthen it.
    """
    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    kpis = interview_answers.get('department_kpis', '')
    challenges = interview_answers.get('department_challenges', '')

    soul = f"""# SOUL.md - Devil's Advocate ({dept_info['name']} Department)

You are the Devil's Advocate for the {dept_info['name']} department at {company_name}.

## Mission
Your job is to make every decision stronger by finding what others missed.
You do NOT exist to say no. You exist to make sure the yes is earned.

## Identity
- Role: Devil's Advocate
- Department: {dept_info['name']}
- Company: {company_name}
- Industry: {industry}

## Tone
- Respectful but relentless. Challenge the idea, never the person.
- Curious, not cynical. Ask "what would make this fail?" not "this will fail."
- Specific, not vague. Point to the exact risk, not a general unease.
- Constructive. Every critique comes with a "here's what would fix it" option.
- Brief. State the risk, the evidence, and the fix. Move on.

## Methodology
1. **Assumption Test**: List every assumption the plan depends on. Flag any that are unproven.
2. **Failure Mode Analysis**: For each step, ask "what is the most likely way this breaks?"
3. **Second-Order Effects**: What happens AFTER the intended result? What ripple does it cause?
4. **Alternative View**: If you had to argue the opposite position, what is the strongest case?
5. **Worst Case**: What does the worst realistic scenario look like? Can the business survive it?
6. **Missing Voices**: Who is affected by this decision who is NOT in the room?
"""

    if kpis:
        soul += f"""\n## Department KPIs to Protect\n{kpis}\n"""

    if challenges:
        soul += f"""\n## Known Vulnerabilities (Start Here)\nThese are already-identified weak spots. Prioritize these in reviews:\n{challenges}\n"""

    soul += """\n## Hard Rules\n- Never approve something you have not challenged.\n- Never challenge without offering a path forward.\n- Never let a deadline override a real risk.\n- If you are the only voice of dissent, that is exactly when you must speak.\n- If you cannot find a real risk, say so explicitly: "I see no significant risk here."\n- Dissent is data. Silence is not safety.\n"""

    return soul


def generate_devils_advocate_sop_md(dept_id, dept_info, interview_answers):
    """
    Generate an SOP for the Devil's Advocate review process within a department.
    This is the step-by-step operating procedure for how DA reviews work.\n    """
    company_name = interview_answers.get('company_name', 'the company')

    sop = f"""# Devil's Advocate Review SOP - {dept_info['name']} Department

## When a Review Is Triggered\n\nA Devil's Advocate review is required before any of the following:\n1. Launching a new campaign, product, or service\n2. Making a financial commitment above the department's threshold\n3. Changing a process that affects customers\n4. Approving a strategy shift or pivot\n5. Publishing content that represents the company publicly\n\nA review is optional (but encouraged) for:\n- Routine operational tasks\n- Internal communications\n- Minor adjustments to existing processes\n\n## Review Process\n\n### Step 1: Receive the Proposal\nThe department head sends the proposal to the Devil's Advocate with context:\n- What is being proposed\n- Why it is being proposed\n- What success looks like\n- What the timeline is\n\n### Step 2: Assumption Mapping\nList every assumption the proposal depends on. For each:\n- Is it stated or unstated?\n- Is it proven or unproven?\n- What happens if it is wrong?\n\nFlag any unproven assumptions as risks.\n\n### Step 3: Failure Mode Identification\nFor each major component of the proposal, answer:\n- What is the most likely way this fails?\n- How would we detect that failure early?\n- What is the recovery plan if it fails?\n\n### Step 4: Second-Order Effects\nTrace the proposal's impact one step beyond the intended result:\n- What does success cause next?\n- Who or what else is affected?\n- Are there unintended consequences?\n\n### Step 5: Alternative View\nBuild the strongest case for the opposite decision.\nThis is not to reverse the decision, but to test whether the original\nreasoning holds up against a real challenge.\n\n### Step 6: Write the Review\nFormat the review as:\n\n**Proposal**: [brief summary]\n**Verdict**: PROCEED / PROCEED WITH CONDITIONS / DO NOT PROCEED\n**Top Risks**:\n1. [risk] - [severity: high/medium/low] - [mitigation]\n2. [risk] - [severity: high/medium/low] - [mitigation]\n3. [risk] - [severity: high/medium/low] - [mitigation]\n**Assumptions Flagged**: [count] unproven\n**Missing Voices**: [who is not in the room]\n**Conditions** (if any): [what must change or be added before proceeding]\n\n### Step 7: Department Head Decision\nThe department head reads the review and makes the final call.\nThe Devil's Advocate does not have veto power. The role is advisory.\n\nIf the department head overrides a "DO NOT PROCEED" or "PROCEED WITH CONDITIONS":\n- They must document their reasoning in writing\n- The override and reasoning are logged in the department's memory file\n\n## Escalation\n\nIf the Devil's Advocate identifies a risk that could affect the entire company\n(not just this department), escalate to the CEO agent immediately.\nDo not wait for the department head's decision cycle.\n\n## Cadence\n\n- **Active Review**: Triggered by any qualifying proposal (see above)\n- **Standing Review**: Weekly scan of department operations for emerging risks\n- **Deep Dive**: Monthly review of department KPIs and strategic direction\n\n## Log Format\n\nEach review is logged in the department's memory folder:\n- File: memory/da-reviews-YYYY-MM.md\n- Entry: date, proposal summary, verdict, top risks, override (if any)\n"""

    return sop


# ============================================================
# ROLE WORKSPACE CREATION (Phase: post-department, pre-specialist)
# ============================================================

# Mapping from department ID to suggested-roles filename
DEPT_TO_SUGGESTED_ROLES = {
    "marketing": "marketing-suggested-roles.md",
    "sales": "sales-suggested-roles.md",
    "billing": "billing-suggested-roles.md",
    "support": "customer-support-suggested-roles.md",
    "operations": "operations-suggested-roles.md",
    "creative": "creative-suggested-roles.md",
    "hr": "hr-people-suggested-roles.md",
    "legal": "legal-compliance-suggested-roles.md",
    "it": "it-tech-suggested-roles.md",
    "webdev": "web-development-suggested-roles.md",
    "appdev": "app-development-suggested-roles.md",
    "graphics": "graphics-suggested-roles.md",
    "video": "video-suggested-roles.md",
    "audio": "audio-suggested-roles.md",
    "research": "research-suggested-roles.md",
    "comms": "communications-suggested-roles.md",
    "ceo": "master-orchestrator-suggested-roles.md",
}


def parse_suggested_roles(dept_id):
    """
    Read and parse the suggested-roles markdown file for a department.
    Returns a list of role dicts with keys:
      - number: int (role number, 0 = department head)
      - name: str
      - description: str ("What it does")
      - sops: list of str (SOP filenames)
      - persona_traits: str
      - is_qc: bool (True if this is the QC Agent role)
    Returns empty list if no file found.
    """
    filename = DEPT_TO_SUGGESTED_ROLES.get(dept_id)
    if not filename:
        # Fallback: try pattern-based lookup
        filename = f"{dept_id}-suggested-roles.md"

    # Search for the file in suggested-roles folder
    suggested_roles_dir = None
    search_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "suggested-roles"),
        os.path.join(WORKSPACE_ROOT, "23-ai-workforce-blueprint", "suggested-roles"),
    ]
    if MASTER_FILES:
        search_paths.insert(0, os.path.join(MASTER_FILES, "23-ai-workforce-blueprint", "suggested-roles"))

    for sp in search_paths:
        if os.path.isdir(sp):
            suggested_roles_dir = sp
            break

    if not suggested_roles_dir:
        print(f"[ROLE-WORKSPACE WARNING] No suggested-roles directory found for {dept_id}", file=sys.stderr)
        return []

    filepath = os.path.join(suggested_roles_dir, filename)
    if not os.path.isfile(filepath):
        # Try exact match by scanning directory
        for f in os.listdir(suggested_roles_dir):
            if dept_id.replace("-", "") in f.replace("-", "").replace("_", ""):
                filepath = os.path.join(suggested_roles_dir, f)
                break

    if not os.path.isfile(filepath):
        print(f"[ROLE-WORKSPACE WARNING] No suggested-roles file for dept '{dept_id}' (tried {filename})",
              file=sys.stderr)
        return []

    with open(filepath, 'r') as f:
        content = f.read()

    roles = []
    current_role = None

    for line in content.split('\n'):
        # Detect role headers: ### N. Role Name
        if line.startswith('### ') and not line.startswith('### Quality Control'):
            if current_role:
                roles.append(current_role)

            header = line[4:].strip()
            is_qc = 'quality control' in header.lower() or 'qc agent' in header.lower()

            # Parse number and name
            parts = header.split('. ', 1)
            try:
                number = int(parts[0])
                name = parts[1] if len(parts) > 1 else header
            except ValueError:
                number = len(roles)
                name = header

            current_role = {
                'number': number,
                'name': name.strip(),
                'description': '',
                'sops': [],
                'persona_traits': '',
                'is_qc': is_qc,
            }

        elif line.startswith('### Quality Control Agent'):
            # QC agent section - save current role if any, start QC role
            if current_role:
                roles.append(current_role)
            current_role = {
                'number': 99,
                'name': 'Quality Control Agent',
                'description': '',
                'sops': [],
                'persona_traits': '',
                'is_qc': True,
            }

        elif current_role:
            # Parse role content
            if line.startswith('**What it does:**'):
                current_role['description'] = line.replace('**What it does:**', '').strip()
            elif line.startswith('- ') and current_role['sops'] is not None:
                # Collect SOP items under "Core SOPs to build:"
                sop = line[2:].strip()
                if sop and sop.startswith('0'):
                    current_role['sops'].append(sop)
            elif line.startswith('**Persona Trait Suggestions:**'):
                current_role['persona_traits'] = line.replace('**Persona Trait Suggestions:**', '').strip()
            elif line.startswith('**Core SOPs to build:**'):
                # SOPs follow on subsequent lines starting with '- '
                pass  # collected above

    # Don't forget the last role
    if current_role:
        roles.append(current_role)

    return roles


def create_role_workspace(dept_id, dept_info, interview_answers):
    """
    Create role subfolders inside a department workspace.

    For each role in the suggested-roles file:
    1. Create a subfolder named after the role (slugified)
    2. Create 00-START-HERE.md with role description
    3. Create governing-personas.md with persona trait suggestions
    4. Create SOP stub files listed in the suggested-roles file

    Args:
        dept_id: Department identifier (e.g., 'marketing')
        dept_info: Department info dict (name, emoji, head, description)
        interview_answers: Interview answers dict (company_name, industry,
                          department_activities, department_kpis, etc.)

    Returns:
        List of created role folder paths
    """
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[ROLE-WORKSPACE WARNING] Department directory does not exist: {dept_dir}", file=sys.stderr)
        return []

    # Parse the suggested-roles file
    roles = parse_suggested_roles(dept_id)
    if not roles:
        print(f"[ROLE-WORKSPACE] No roles found for {dept_id}, skipping role workspace creation."
              f" If roles are expected, check suggested-roles/{DEPT_TO_SUGGESTED_ROLES.get(dept_id, 'unknown')}",
              file=sys.stderr)
        return []

    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    department_tools = interview_answers.get('department_tools', '')
    department_kpis = interview_answers.get('department_kpis', '')
    department_challenges = interview_answers.get('department_challenges', '')

    created_folders = []

    for role in roles:
        # Build slug folder name: '00-chief-marketing-officer' or '02-social-media-manager'
        role_slug = role['name'].lower()
        role_slug = role_slug.replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')
        role_slug = role_slug.replace('--', '-').strip('-')
        folder_name = f"{role['number']:02d}-{role_slug}"
        role_dir = os.path.join(dept_dir, folder_name)
        os.makedirs(role_dir, exist_ok=True)

        # 1. Create 00-START-HERE.md
        start_here_path = os.path.join(role_dir, "00-START-HERE.md")
        if not os.path.isfile(start_here_path):
            role_type = "QC Agent" if role['is_qc'] else "Specialist"
            if role['number'] == 0:
                role_type = "Department Head"

            content = f"""# {role['name']}

**Department:** {dept_info['name']} ({dept_info['emoji']})
**Company:** {company_name}
**Industry:** {industry}
**Role Type:** {role_type}

## What This Role Does
{role['description']}

## Department Context
"""
            if department_tools:
                content += f"**Department Tools:** {department_tools}\n"
            if department_kpis:
                content += f"**Department KPIs:** {department_kpis}\n"
            if department_challenges:
                content += f"**Current Challenges:** {department_challenges}\n"

            content += f"\n## SOPs (Standard Operating Procedures)\n"
            if role['sops']:
                content += "Each file below is a step-by-step instruction set. Follow them in order.\n\n"
                for sop in role['sops']:
                    content += f"- {sop}\n"
            else:
                content += "No SOPs defined yet. The department head will assign SOPs as tasks come in.\n"

            content += f"\n## Persona Trait Suggestions\n"
            if role['persona_traits']:
                content += f"{role['persona_traits']}\n"
            else:
                content += "No specific traits defined. Use the department's governing-personas.md as a reference.\n"

            content += f"\n---\n\n*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*\n"

            with open(start_here_path, 'w') as f:
                f.write(content)

        # 2. Create governing-personas.md for this role
        personas_path = os.path.join(role_dir, "governing-personas.md")
        if not os.path.isfile(personas_path):
            personas_content = f"""# Governing Personas - {role['name']}

**Department:** {dept_info['name']}
**Role:** {role['name']}
**Company:** {company_name}

## Persona Alignment
This role's persona selection is guided by the trait suggestions below.
At runtime, the AI selects the best persona PER TASK using 5-layer alignment.
The instruction is: 'Act as if you are [persona] executing this task.'

## Trait Suggestions for This Role
{role['persona_traits'] if role['persona_traits'] else 'Use department-level governing-personas.md as the primary reference.'}

## Department-Level Personas
See the parent department's `governing-personas.md` for the full pre-qualified persona pool.
This file adds role-specific filtering on top of the department pool.

---

*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*\n"""
            with open(personas_path, 'w') as f:
                f.write(personas_content)

        # 3. Create SOP stub files
        for sop_filename in role['sops']:
            sop_path = os.path.join(role_dir, sop_filename)
            if not os.path.isfile(sop_path):
                sop_name = sop_filename.replace('.md', '').replace('-', ' ').title()
                sop_content = f"""# {sop_name}

**Role:** {role['name']}
**Department:** {dept_info['name']}
**Company:** {company_name}
**Industry:** {industry}
**Version:** 1.0 | {datetime.now().strftime('%B %d, %Y')}

## Purpose
This SOP provides step-by-step instructions for: {sop_name.lower()}.

## Who This Is For
The {role['name']} in the {dept_info['name']} department.

## Prerequisites
- Access to department tools: {department_tools if department_tools else 'See department TOOLS.md'}
- Understanding of department KPIs: {department_kpis if department_kpis else 'See department SOUL.md'}

## Step-by-Step Instructions

> **TODO:** This SOP needs to be populated with industry-specific best practices.
> The AI agent should research best practices using Perplexity and personalize
> these steps using the client's interview answers (tools, KPIs, challenges).
>
> **Interview context:**
> - Industry: {industry}
> - Department challenges: {department_challenges if department_challenges else 'Not specified'}
> - Department tools: {department_tools if department_tools else 'Not specified'}
> - Department KPIs: {department_kpis if department_kpis else 'Not specified'}

1. [Step 1 - to be personalized based on research]
2. [Step 2 - to be personalized based on research]
3. [Step 3 - to be personalized based on research]

## What to Do If Something Goes Wrong
- Check department SOUL.md for escalation procedures
- Report to the department head
- Log the issue in the department memory/ folder

## Escalation
If this task cannot be completed at the specialist level, escalate to the {dept_info['head']}.

---

*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*
*Status: STUB - Needs research + personalization*
"""
                with open(sop_path, 'w') as f:
                    f.write(sop_content)

        created_folders.append(role_dir)
        print(f"[ROLE-WORKSPACE] Created role: {folder_name} in {dept_id}/", file=sys.stderr)

    print(f"[ROLE-WORKSPACE] {len(created_folders)} roles created for {dept_id}", file=sys.stderr)
    return created_folders


# ============================================================
# SPECIALIST DETERMINATION (Silent - no client questions)
# ============================================================

def determine_specialists(dept_id, dept_info, interview_answers):
    activities = interview_answers.get('department_activities', '')
    activities_lower = activities.lower()
    PERMANENT_SIGNALS = [
        'daily', 'weekly', 'every day', 'every week', 'regular',
        'recurring', 'ongoing', 'continuous', 'always', 'consistently',
        'schedule', 'routine', 'maintain', 'manage', 'track', 'monitor',
        'relationship', 'client', 'customer', 'follow up', 'follow-up',
        'campaign', 'pipeline', 'inbox', 'respond', 'report',
    ]
    ONCALL_SIGNALS = [
        'occasionally', 'sometimes', 'once', 'one-time', 'one time',
        'quarterly', 'annually', 'yearly', 'as needed', 'when needed',
        'project-based', 'project based', 'single', 'audit', 'review',
    ]
    permanent_score = sum(1 for signal in PERMANENT_SIGNALS if signal in activities_lower)
    oncall_score = sum(1 for signal in ONCALL_SIGNALS if signal in activities_lower)

    specialists = []
    suggested_roles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'suggested-roles',
        f'{dept_id}-suggested-roles.md'
    )
    if os.path.isfile(suggested_roles_path):
        with open(suggested_roles_path, 'r') as f:
            content = f.read()
        import re
        role_blocks = re.split(r'###\s+\d+\.\s+', content)
        for block in role_blocks[1:]:
            lines = block.strip().split('\n')
            if not lines:
                continue
            role_name = lines[0].strip()
            role_slug = role_name.lower().replace(' ', '-').replace('/', '-')
            role_type = 'permanent' if permanent_score >= oncall_score else 'on-call'
            block_lower = block.lower()
            if any(s in block_lower for s in ['daily', 'weekly', 'ongoing', 'manages', 'monitors']):
                role_type = 'permanent'
            elif any(s in block_lower for s in ['occasionally', 'one-time', 'as needed', 'quarterly']):
                role_type = 'on-call'
            specialists.append({
                'id': role_slug,
                'name': role_name,
                'type': role_type,
                'model': 'moonshot/kimi-k2.5',
                'reason': f'From suggested roles for {dept_id}, type={role_type} based on activity signals'
            })
    else:
        print(f"[WARNING] No suggested-roles file for {dept_id} at {suggested_roles_path}", file=sys.stderr)

    decision_context = {
        'department': dept_id,
        'permanent_signals_found': permanent_score,
        'oncall_signals_found': oncall_score,
        'activities_text': activities,
        'specialists_count': len(specialists),
        'suggested_roles_file': suggested_roles_path if os.path.isfile(suggested_roles_path) else 'NOT FOUND',
    }
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
    Schema: [{ "id": str, "emoji": str, "name": str, "headTitle": str, "workspacePath": str }]
    IDs use "dept-" prefix to match Command Center expectations.
    """
    entries = []
    for dept_id, dept_info in departments.items():
        entries.append({
            "id": f"dept-{dept_id}",
            "emoji": dept_info["emoji"],
            "name": dept_info["name"],
            "headTitle": dept_info["head"],
            "workspacePath": f"departments/{dept_id}",
        })
    return entries


def copy_departments_to_command_center(departments_json):
    """
    Copy departments.json to the Command Center config directory.
    The build-workforce script writes to company-discovery/ but the CC
    reads from its own config/ directory. This function bridges the gap.
    """
    # Common CC install locations to try (in order of preference)
    cc_search_paths = [
        os.path.join(HOME, "clawd", "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "clawd", "blackceo-command-center", "config"),
        os.path.join(HOME, "Downloads", "blackceo-command-center", "config"),
    ]

    # Also check for a symlink or env var pointing to CC
    cc_root = os.environ.get("BLACKCEO_COMMAND_CENTER_ROOT", "")
    if cc_root:
        cc_search_paths.insert(0, os.path.join(cc_root, "config"))

    copied_to = []
    for cc_config_dir in cc_search_paths:
        if os.path.isdir(cc_config_dir):
            dest_path = os.path.join(cc_config_dir, "departments.json")
            try:
                with open(dest_path, 'w') as f:
                    json.dump(departments_json, f, indent=2)
                copied_to.append(dest_path)
                print(f"[CC-SYNC] Copied departments.json to: {dest_path}", file=sys.stderr)
            except Exception as e:
                print(f"[CC-SYNC WARNING] Failed to copy to {dest_path}: {e}", file=sys.stderr)

    if not copied_to:
        print("[CC-SYNC WARNING] No Command Center config directory found. "
              "Set BLACKCEO_COMMAND_CENTER_ROOT or ensure CC is installed.", file=sys.stderr)
        print("[CC-SYNC] departments.json is still available at the company-discovery path.",
              file=sys.stderr)

    return copied_to


def generate_persona_matrix(departments, persona_categories, company_name):
    """
    Generate persona-matrix.md - a mapping of departments to their pre-qualified personas.
    This creates visibility into which personas are available for which departments,
    supporting the 5-layer matching protocol (Layers 1-2 pre-qualified pool).

    The matrix is regenerated whenever the workforce is built or updated.
    If persona-matrix.md exists, this function updates it; otherwise creates it.
    """
    matrix_path = os.path.join(DEPARTMENTS_DIR, "persona-matrix.md")

    # Build department-to-persona mapping
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

    content = f"""# Persona Matrix - {company_name}
## Department-to-Persona Mapping for 5-Layer Matching

**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
**Version:** 1.0

---

## Overview

This matrix maps each department to its pre-qualified persona pool (Layers 1-2 of the 5-layer matching protocol).
Personas listed here have passed company mission and owner alignment checks.

**How to use:**
1. For each task, query the personas listed for that department
2. Apply Layers 3-5 (company goals, department goals, task fit) to select the best match
3. Log selection in persona-selection-log.md

---

## Department Mappings

"""

    for dept_id, dept_info in departments.items():
        domains = dept_to_domains.get(dept_id, ["leadership"])
        matched_personas = []

        if persona_categories and "personas" in persona_categories:
            seen = set()
            for domain in domains:
                for persona_id, data in persona_categories["personas"].items():
                    if domain in data.get("domain", []) and persona_id not in seen:
                        matched_personas.append({
                            "id": persona_id,
                            "author": data.get("author", ""),
                            "book": data.get("book", ""),
                            "domains": data.get("domain", []),
                            "perspective": data.get("perspective", []),
                        })
                        seen.add(persona_id)

        content += f"### {dept_info['emoji']} {dept_info['name']} ({dept_id})\n\n"
        content += f"**Head:** {dept_info['head']}\n"
        content += f"**Domain Tags:** {', '.join(domains)}\n\n"

        if matched_personas:
            content += "**Pre-Qualified Personas:**\n\n"
            for p in matched_personas[:10]:  # Limit to top 10 per department
                perspective = ', '.join(p['perspective']) if p['perspective'] else 'general'
                content += f"- **{p['author']}** ({p['book']}) - {perspective}\n"
            if len(matched_personas) > 10:
                content += f"- *...and {len(matched_personas) - 10} more*\n"
        else:
            content += "**Pre-Qualified Personas:** None yet. Run Skill 22 (Book-to-Persona) to add personas.\n"

        content += "\n---\n\n"

    # Add usage instructions
    content += """## Using This Matrix

### Step 1: Pre-Qualification (Layers 1-2)
Personas in this matrix have already been validated against:
- Company mission alignment
- Owner values and style alignment

### Step 2: Per-Task Matching (Layers 3-5)
For each task, score candidates on:
- Layer 3: Company goals/KPIs alignment
- Layer 4: Department goals/KPIs alignment
- Layer 5: Task-specific fit

### Step 3: Selection and Logging
After selecting a persona, log it:
```
[date] [task-id] "candidates" "selected" "layer-3-reason" "layer-4-reason" "layer-5-reason"
```

---

## Updating This Matrix

This matrix is auto-generated by build-workforce.py whenever the workforce is built.
To regenerate after adding new personas (via Skill 22):
1. Re-run build-workforce.py, or
2. Manually run: `python3 build-workforce.py --non-interactive --config-file workforce-config.json`

---

*This is a living document. Update it whenever personas or departments change.*
"""

    try:
        with open(matrix_path, 'w') as f:
            f.write(content)
        print(f"[PERSONA-MATRIX] Updated: {matrix_path}", file=sys.stderr)
    except Exception as e:
        print(f"[PERSONA-MATRIX WARNING] Could not write matrix: {e}", file=sys.stderr)

    return matrix_path


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
