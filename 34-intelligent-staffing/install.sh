#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Skill 34: Intelligent Workspace Staffing
# Asks 6 questions per department, creates permanent specialist
# agents or marks sub-agent roles based on answers.
#
# Decision Rule:
#   YES to a question where type=permanent -> Create permanent agent
#   YES to a question where type=subagent  -> Log as available sub-agent
#   NO  -> Skip
#
# Depends on: Skill 33 (Department Heads) already installed
# Safe to run: creates files under ~/clawd only, modifies
#              ~/.openclaw/openclaw.json agents.list[]
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUESTIONS_FILE="$SCRIPT_DIR/questions.json"
TEMPLATES_DIR="$SCRIPT_DIR/specialist-templates"

echo ""
echo "============================================"
echo "   Skill 34: Intelligent Workspace Staffing"
echo "============================================"
echo ""
echo "This skill asks 6 questions per department to determine"
echo "which specialist roles should be permanent agents vs"
echo "temporary sub-agents."
echo ""
echo "Decision Rule:"
echo "  - Recurring task (daily/weekly/monthly) + needs memory = PERMANENT agent"
echo "  - One-time or occasional task with no memory need = SUB-AGENT (skip)"
echo "  - Client-facing ongoing relationship = PERMANENT agent"
echo ""

# ----------------------------------------------------------
# Validate prerequisites
# ----------------------------------------------------------
if [ ! -f "$QUESTIONS_FILE" ]; then
    echo "[ERROR] questions.json not found at: $QUESTIONS_FILE"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 is required but not installed."
    exit 1
fi

# Check that jq or python3 can parse the questions file
python3 -c "import json; json.load(open('$QUESTIONS_FILE'))" 2>/dev/null || {
    echo "[ERROR] questions.json is not valid JSON."
    exit 1
}

# Check that Skill 33 has been run (departments exist)
if [ ! -d "$HOME/clawd/departments" ]; then
    echo "[WARNING] ~/clawd/departments/ not found."
    echo "  Skill 33 (Department Heads) should be installed first."
    echo "  Continuing anyway - specialist folders will be created."
    echo ""
fi

# ----------------------------------------------------------
# Step 1: Ask questions and collect answers
# ----------------------------------------------------------
echo "[1/4] Running department staffing interview..."
echo ""

# Use Python for the interactive interview since it handles
# JSON parsing and complex logic better than bash
python3 << 'PYTHON_INTERVIEW' 
import json
import os
import sys

script_dir = os.path.dirname(os.path.abspath("__file__")) if "__file__" in dir() else os.environ.get("SCRIPT_DIR", ".")
questions_file = os.environ.get("QUESTIONS_FILE", os.path.join(script_dir, "questions.json"))

# Load questions
with open(questions_file, 'r') as f:
    data = json.load(f)

departments = data["departments"]

# Collect all responses
responses = {}
permanent_specialists = []
subagent_roles = []

print("=" * 50)
print("  INTELLIGENT STAFFING INTERVIEW")
print("=" * 50)
print()
print("Answer YES or NO for each question.")
print("YES = this function is active in your business")
print("NO = skip this function")
print()
print("Based on your answers, we will create:")
print("  - Permanent agents for recurring tasks that need memory")
print("  - Sub-agent templates for one-time/occasional tasks")
print()

total_questions = sum(len(d["questions"]) for d in departments)
current_question = 0

for dept in departments:
    dept_name = dept["display_name"]
    dept_id = dept["department"]
    
    print(f"\n{'=' * 50}")
    print(f"  DEPARTMENT: {dept_name.upper()}")
    print(f"{'=' * 50}\n")
    
    dept_permanent = []
    dept_subagent = []
    
    for q in dept["questions"]:
        current_question += 1
        question_text = q["question"]
        specialist = q["specialist"]
        spec_type = q["type"]
        folder = q["folder"]
        model = q["model"]
        qid = q["id"]
        
        print(f"  [{current_question}/{total_questions}] {question_text}")
        
        while True:
            answer = input("  Your answer (yes/no): ").strip().lower()
            if answer in ("yes", "y", "no", "n"):
                break
            print("  Please answer yes or no.")
        
        is_yes = answer in ("yes", "y")
        
        if is_yes:
            if spec_type == "permanent":
                specialist_info = {
                    "id": f"spec-{folder}",
                    "name": specialist,
                    "department": dept_id,
                    "department_display": dept_name,
                    "type": "permanent",
                    "model": model,
                    "folder": folder,
                    "question_id": qid
                }
                permanent_specialists.append(specialist_info)
                dept_permanent.append(specialist)
                print(f"    -> {specialist} will be a PERMANENT agent\n")
            else:
                specialist_info = {
                    "id": f"sub-{folder}",
                    "name": specialist,
                    "department": dept_id,
                    "department_display": dept_name,
                    "type": "subagent",
                    "model": model,
                    "folder": folder,
                    "question_id": qid
                }
                subagent_roles.append(specialist_info)
                dept_subagent.append(specialist)
                print(f"    -> {specialist} will be a SUB-AGENT template\n")
        else:
            print(f"    -> Skipped\n")
    
    # Department summary
    if dept_permanent or dept_subagent:
        print(f"  --- {dept_name} Summary ---")
        if dept_permanent:
            print(f"  Permanent: {', '.join(dept_permanent)}")
        if dept_subagent:
            print(f"  Sub-agents: {', '.join(dept_subagent)}")

# Write results to a temp file for the bash script to consume
results = {
    "permanent_specialists": permanent_specialists,
    "subagent_roles": subagent_roles,
    "summary": {
        "total_questions": total_questions,
        "permanent_count": len(permanent_specialists),
        "subagent_count": len(subagent_roles),
        "skipped_count": total_questions - len(permanent_specialists) - len(subagent_roles)
    }
}

results_file = os.path.join(os.path.expanduser("~"), ".skill34-results.json")
with open(results_file, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n{'=' * 50}")
print(f"  INTERVIEW COMPLETE")
print(f"{'=' * 50}")
print(f"  Permanent specialists: {len(permanent_specialists)}")
print(f"  Sub-agent roles: {len(subagent_roles)}")
print(f"  Skipped: {total_questions - len(permanent_specialists) - len(subagent_roles)}")
print(f"\n  Results saved. Proceeding to setup...")
PYTHON_INTERVIEW

# ----------------------------------------------------------
# Step 2: Create specialist workspace directories and SOUL.md
# ----------------------------------------------------------
echo ""
echo "[2/4] Creating specialist workspace directories..."

RESULTS_FILE="$HOME/.skill34-results.json"

if [ ! -f "$RESULTS_FILE" ]; then
    echo "[ERROR] Results file not found. Interview may have failed."
    exit 1
fi

PERMANENT_COUNT=$(python3 -c "import json; d=json.load(open('$RESULTS_FILE')); print(d['summary']['permanent_count'])")
SUBAGENT_COUNT=$(python3 -c "import json; d=json.load(open('$RESULTS_FILE')); print(d['summary']['subagent_count'])")

echo "  Creating $PERMANENT_COUNT permanent specialist workspaces..."
echo "  Creating $SUBAGENT_COUNT sub-agent templates..."

python3 << PYTHON_WORKSPACE
import json
import os

results_file = os.path.expanduser("~/.skill34-results.json")
templates_dir = "$TEMPLATES_DIR"

with open(results_file, 'r') as f:
    results = json.load(f)

# Create permanent specialist workspaces
for spec in results["permanent_specialists"]:
    dept = spec["department"]
    folder = spec["folder"]
    name = spec["name"]
    model = spec["model"]

    # Create specialist directory under department
    spec_dir = os.path.expanduser(f"~/clawd/departments/{dept}/specialists/{folder}")
    os.makedirs(spec_dir, exist_ok=True)

    # Create SOUL.md from template
    soul_path = os.path.join(spec_dir, "SOUL.md")
    if not os.path.exists(soul_path):
        # Try to find a matching template
        template_path = os.path.join(templates_dir, f"{folder}.md")
        if os.path.exists(template_path):
            with open(template_path, 'r') as tf:
                soul_content = tf.read()
        else:
            # Use generic template
            generic_path = os.path.join(templates_dir, "SOUL-template.md")
            if os.path.exists(generic_path):
                with open(generic_path, 'r') as tf:
                    soul_content = tf.read()
                soul_content = soul_content.replace("[Specialist Name]", name)
                soul_content = soul_content.replace("[Role Title]", name)
                soul_content = soul_content.replace("[Parent Department]", dept.title())
                soul_content = soul_content.replace("[Department Director name]", f"{dept.title()} Director")
                soul_content = soul_content.replace("[model identifier]", model)
            else:
                soul_content = f"# SOUL.md - {name}\\n\\nYou are the {name} for the {dept.title()} department.\\n"

        with open(soul_path, 'w') as sf:
            sf.write(soul_content)

    # Create MEMORY.md
    memory_path = os.path.join(spec_dir, "MEMORY.md")
    if not os.path.exists(memory_path):
        with open(memory_path, 'w') as mf:
            mf.write(f"# MEMORY.md - {name}\\n\\nLong-term memory for the {name}.\\n\\n## Key Decisions\\n\\n## Performance History\\n\\n## Relationship Notes\\n")

    # Create AGENTS.md
    agents_path = os.path.join(spec_dir, "AGENTS.md")
    if not os.path.exists(agents_path):
        with open(agents_path, 'w') as af:
            af.write(f"# AGENTS.md - {name}\\n\\nOperating rules for the {name}.\\n\\n## Role\\n- Department: {dept.title()}\\n- Type: Permanent Specialist\\n- Model: {model}\\n\\n## Rules\\n- Follow department SOPs\\n- Report to Department Director\\n- Document all work\\n- Escalate when unsure\\n")

    print(f"  [OK] {dept}/{folder} - {name}")

# Create sub-agent template directories
for spec in results["subagent_roles"]:
    dept = spec["department"]
    folder = spec["folder"]
    name = spec["name"]

    sub_dir = os.path.expanduser(f"~/clawd/subagents/templates/{folder}")
    os.makedirs(sub_dir, exist_ok=True)

    # Create sub-agent template SOUL.md
    soul_path = os.path.join(sub_dir, "SOUL.md")
    if not os.path.exists(soul_path):
        with open(soul_path, 'w') as sf:
            sf.write(f"""# Sub-Agent Template: {name}

**Role:** {name}
**Department:** {dept.title()}
**Type:** Sub-Agent (temporary)
**Trigger:** When a one-time {name.lower()} task is needed

## Purpose
Complete a specific one-time {name.lower()} task. No memory retained between executions.

## Input Required
Provide all context in the task description. This agent has no memory of past work.

## Output
Deliverables specific to the task requested.

## Rules
- This is a sub-agent. It does not retain memory.
- All context must be provided in the task description.
- Report results back to the Department Director.
""")

    print(f"  [OK] subagents/{folder} - {name} (sub-agent)")

print(f"\\n  Workspace creation complete.")
PYTHON_WORKSPACE

# ----------------------------------------------------------
# Step 3: Add permanent specialists to openclaw.json
# ----------------------------------------------------------
echo ""
echo "[3/4] Adding permanent specialist agents to ~/.openclaw/openclaw.json..."

python3 << 'PYTHON_CONFIG'
import json
import os

results_file = os.path.expanduser("~/.skill34-results.json")
config_path = os.path.expanduser("~/.openclaw/openclaw.json")

with open(results_file, 'r') as f:
    results = json.load(f)

# Load openclaw.json
if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        config = json.load(f)
else:
    config = {"agents": {"list": []}}

# Ensure agents.list exists
if "agents" not in config:
    config["agents"] = {"list": []}
if "list" not in config["agents"]:
    config["agents"]["list"] = []

# Get existing agent IDs
existing_ids = {agent.get("id") for agent in config["agents"]["list"]}

added_count = 0
for spec in results["permanent_specialists"]:
    agent_id = spec["id"]
    dept = spec["department"]
    folder = spec["folder"]
    name = spec["name"]
    model = spec["model"]

    if agent_id not in existing_ids:
        agent_entry = {
            "id": agent_id,
            "name": name,
            "model": model,
            "system": f"file://~/clawd/departments/{dept}/specialists/{folder}/SOUL.md",
            "workspace": os.path.expanduser(f"~/clawd/departments/{dept}/specialists/{folder}"),
            "parent": f"dept-{dept}"
        }
        config["agents"]["list"].append(agent_entry)
        existing_ids.add(agent_id)
        added_count += 1
        print(f"  Added: {agent_id} ({name})")
    else:
        print(f"  Skipped (exists): {agent_id}")

# Save config
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print(f"\n  {added_count} specialist agents added to openclaw.json")
PYTHON_CONFIG

# ----------------------------------------------------------
# Step 4: Clean up and verify
# ----------------------------------------------------------
echo ""
echo "[4/4] Cleaning up and verifying..."

# Remove temp results file
rm -f "$HOME/.skill34-results.json"

# Count created directories
PERM_DIRS=$(find ~/clawd/departments -path "*/specialists/*" -name "SOUL.md" 2>/dev/null | wc -l | tr -d ' ')
SUB_DIRS=$(find ~/clawd/subagents/templates -name "SOUL.md" 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "============================================"
echo "   Skill 34 Installation Complete"
echo "============================================"
echo ""
echo "Created:"
echo "  - $PERM_DIRS permanent specialist workspaces"
echo "    (under ~/clawd/departments/[dept]/specialists/)"
echo "  - $SUB_DIRS sub-agent templates"
echo "    (under ~/clawd/subagents/templates/)"
echo "  - Specialist agents added to ~/.openclaw/openclaw.json"
echo ""
echo "Each permanent specialist has:"
echo "  - SOUL.md (identity and operating rules)"
echo "  - MEMORY.md (long-term memory)"
echo "  - AGENTS.md (behavior rules)"
echo ""
echo "Next step: Type '/restart' in Telegram to apply agent changes."
echo ""
