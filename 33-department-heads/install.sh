#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Skill 33: Permanent Department Heads Setup
# Creates 17 department directories with SOUL.md files
# and adds department head agents to openclaw.json
# ============================================================

echo ""
echo "============================================"
echo "   Skill 33: Permanent Department Heads"
echo "============================================"
echo ""

# Define the 17 departments
declare -a DEPARTMENTS=("ceo" "marketing" "sales" "billing" "support" "operations" "creative" "hr" "legal" "it" "webdev" "appdev" "graphics" "video" "audio" "research" "comms")

# Define display names for each department
declare -A DEPT_NAMES=(
    ["ceo"]="Chief Executive Officer"
    ["marketing"]="Marketing Director"
    ["sales"]="Sales Director"
    ["billing"]="Finance Director"
    ["support"]="Support Director"
    ["operations"]="Operations Director"
    ["creative"]="Creative Director"
    ["hr"]="HR Director"
    ["legal"]="Legal Director"
    ["it"]="IT Director"
    ["webdev"]="Web Development Director"
    ["appdev"]="App Development Director"
    ["graphics"]="Graphics Director"
    ["video"]="Video Director"
    ["audio"]="Audio Director"
    ["research"]="Research Director"
    ["comms"]="Communications Director"
)

# Define models for each department
declare -A DEPT_MODELS=(
    ["ceo"]="moonshot/kimi-k2.5"
    ["marketing"]="moonshot/kimi-k2.5"
    ["sales"]="openai-codex/gpt-5.4"
    ["billing"]="moonshot/kimi-k2.5"
    ["support"]="moonshot/kimi-k2.5"
    ["operations"]="anthropic/claude-sonnet-4-6"
    ["creative"]="moonshot/kimi-k2.5"
    ["hr"]="moonshot/kimi-k2.5"
    ["legal"]="anthropic/claude-sonnet-4-6"
    ["it"]="openai-codex/gpt-5.4"
    ["webdev"]="openai-codex/gpt-5.4"
    ["appdev"]="openai-codex/gpt-5.4"
    ["graphics"]="moonshot/kimi-k2.5"
    ["video"]="moonshot/kimi-k2.5"
    ["audio"]="moonshot/kimi-k2.5"
    ["research"]="moonshot/kimi-k2.5"
    ["comms"]="moonshot/kimi-k2.5"
)

# ----------------------------------------------------------
# Step 1: Create departments directory
# ----------------------------------------------------------
echo "[1/4] Creating ~/clawd/departments/ directory..."
mkdir -p ~/clawd/departments
echo "  Created: ~/clawd/departments/"

# ----------------------------------------------------------
# Step 2: Create department subdirectories and SOUL.md files
# ----------------------------------------------------------
echo ""
echo "[2/4] Creating 17 department subdirectories with SOUL.md..."

for dept in "${DEPARTMENTS[@]}"; do
    dept_dir="~/clawd/departments/$dept"
    mkdir -p "$dept_dir"
    
    # Create SOUL.md for each department
    cat > "$dept_dir/SOUL.md" << EOF
# SOUL.md - ${DEPT_NAMES[$dept]}

You are the ${DEPT_NAMES[$dept]} for BlackCEO Command Center.

## Identity
- Name: ${DEPT_NAMES[$dept]}
- Department: ${dept^}
- Model: ${DEPT_MODELS[$dept]}

## Role
You own the ${dept} department's performance. You receive tasks, delegate to specialist agents, monitor results, and report up to the CEO.

## Responsibilities
1. Monitor ${dept} KPIs and department metrics
2. Assign ${dept} tasks to specialist sub-agents
3. Review and approve ${dept} outputs before delivery
4. Generate weekly ${dept} performance summaries
5. Escalate blockers to the CEO agent

## Communication Style
Direct, data-driven, results-focused. Always cite specific numbers. Never vague.
EOF
    
    echo "  Created: $dept_dir/SOUL.md"
done

echo "  All 17 department SOUL.md files created."

# ----------------------------------------------------------
# Step 3: Add department head agents to openclaw.json
# ----------------------------------------------------------
echo ""
echo "[3/4] Adding 17 department head agents to ~/.openclaw/openclaw.json..."

python3 << 'PYTHON_SCRIPT'
import json
import os

# Load openclaw.json
config_path = os.path.expanduser("~/.openclaw/openclaw.json")
with open(config_path, 'r') as f:
    config = json.load(f)

# Define the 17 department head agents
agents = [
    {"id": "dept-ceo", "name": "CEO Director", "workspace": "~/clawd/departments/ceo", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-marketing", "name": "Marketing Director", "workspace": "~/clawd/departments/marketing", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-sales", "name": "Sales Director", "workspace": "~/clawd/departments/sales", "model": "openai-codex/gpt-5.4"},
    {"id": "dept-billing", "name": "Finance Director", "workspace": "~/clawd/departments/billing", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-support", "name": "Support Director", "workspace": "~/clawd/departments/support", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-operations", "name": "Operations Director", "workspace": "~/clawd/departments/operations", "model": "anthropic/claude-sonnet-4-6"},
    {"id": "dept-creative", "name": "Creative Director", "workspace": "~/clawd/departments/creative", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-hr", "name": "HR Director", "workspace": "~/clawd/departments/hr", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-legal", "name": "Legal Director", "workspace": "~/clawd/departments/legal", "model": "anthropic/claude-sonnet-4-6"},
    {"id": "dept-it", "name": "IT Director", "workspace": "~/clawd/departments/it", "model": "openai-codex/gpt-5.4"},
    {"id": "dept-webdev", "name": "Web Development Director", "workspace": "~/clawd/departments/webdev", "model": "openai-codex/gpt-5.4"},
    {"id": "dept-appdev", "name": "App Development Director", "workspace": "~/clawd/departments/appdev", "model": "openai-codex/gpt-5.4"},
    {"id": "dept-graphics", "name": "Graphics Director", "workspace": "~/clawd/departments/graphics", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-video", "name": "Video Director", "workspace": "~/clawd/departments/video", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-audio", "name": "Audio Director", "workspace": "~/clawd/departments/audio", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-research", "name": "Research Director", "workspace": "~/clawd/departments/research", "model": "moonshot/kimi-k2.5"},
    {"id": "dept-comms", "name": "Communications Director", "workspace": "~/clawd/departments/comms", "model": "moonshot/kimi-k2.5"},
]

# Check if agents already exist to avoid duplicates
existing_ids = {agent.get('id') for agent in config.get('agents', {}).get('list', [])}

added_count = 0
for agent in agents:
    if agent['id'] not in existing_ids:
        # Expand workspace path
        agent['workspace'] = os.path.expanduser(agent['workspace'])
        config['agents']['list'].append(agent)
        existing_ids.add(agent['id'])
        added_count += 1
        print(f"  Added: {agent['id']} ({agent['name']})")
    else:
        print(f"  Skipped (exists): {agent['id']}")

# Save back to file
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print(f"\n  {added_count} department head agents added to openclaw.json")
PYTHON_SCRIPT

# ----------------------------------------------------------
# Step 4: Verify installation
# ----------------------------------------------------------
echo ""
echo "[4/4] Verifying installation..."

echo ""
echo "Department directories created:"
ls -1 ~/clawd/departments/ | while read dir; do
    if [ -f "~/clawd/departments/$dir/SOUL.md" ]; then
        echo "  [OK] $dir/SOUL.md"
    else
        echo "  [MISSING] $dir/SOUL.md"
    fi
done

echo ""
echo "============================================"
echo "   Skill 33 Installation Complete"
echo "============================================"
echo ""
echo "Created:"
echo "  - ~/clawd/departments/ (17 department folders)"
echo "  - 17 SOUL.md files (one per department)"
echo "  - 17 agent entries in ~/.openclaw/openclaw.json"
echo ""
echo "Departments:"
for dept in "${DEPARTMENTS[@]}"; do
    echo "  - ${DEPT_NAMES[$dept]} ($dept)"
done
echo ""
echo "Next step: Type '/restart' in Telegram to apply agent changes."
echo ""
