# Command Center Setup - Installation Guide

## Overview

This guide walks you through activating your AI workforce as a live Command Center. The process has 8 phases. Some phases you do manually (like setting up Telegram). Other phases the agent does automatically.

**Important:** This skill requires Skill 23 (AI Workforce Blueprint) to be complete first. The agent will check for this before proceeding.

---

## Phase 1: Prerequisites Check

The agent will verify these before starting:

### 1.1 Check Node.js Version
```bash
node --version
```
Expected: v18 or higher. If lower, update Node.js first.

### 1.2 Check Git Installation
```bash
git --version
```
Expected: Git is installed. If not, install Git first.

### 1.3 Check PM2 Installation
```bash
pm2 --version
```
Expected: PM2 is installed. If not, install it:
```bash
npm install -g pm2
```

### 1.4 Verify Skill 23 Is Complete

The agent will scan for department folders in your master files area. These folders indicate Skill 23 was completed.

**What the agent looks for:**
- Folders like `marketing/`, `sales/`, `operations/` in your workforce directory
- Each folder should contain role definitions

**If Skill 23 is NOT found:**
The agent will STOP and tell you:
> "Skill 23 (AI Workforce Blueprint) must be completed first. Please finish that skill, then return to activate your Command Center."

**If Skill 23 IS found:**
The agent will identify which departments you chose and proceed.

---

## Phase 2: Telegram Setup (You Do This Manually)

This phase requires you to use the Telegram app on your phone or computer. The agent will guide you step by step.

### Step 1: Open Telegram and Start a New Group
1. Open the Telegram app on your device
2. Tap the compose icon (looks like a pencil in a box)
3. Tap "New Group" from the menu

**What you should see:** A screen asking you to add members to the new group.

### Step 2: Add Your Bot to the Group
1. Search for your bot's name (the one you use with OpenClaw, like @clawdbot)
2. Tap on your bot to add it as a member
3. Tap the arrow or "Next" to continue

**What you should see:** The bot is now listed as a selected member.

### Step 3: Name Your Group
1. Type the group name: "[Your Company Name] Command Center"
   - For example: "BlackCEO Command Center" or "Acme Inc Command Center"
2. Tap "Create" to create the group

**What you should see:** Your new group is created and you are now in the chat.

### Step 4: Enable Topics (Converts to Supergroup)
1. Tap the group name at the top to open Group Info
2. Tap the edit icon (looks like a pencil)
3. Scroll down and find "Topics"
4. Toggle the switch to turn Topics ON
5. Tap "Save" or the back arrow

**What you should see:**
- Telegram will convert the group to a "supergroup"
- You may see a brief loading indicator
- The group now supports organized topics

### Step 5: Promote Your Bot to Admin
1. Go back to Group Info (tap the group name again)
2. Find "Members" and tap it
3. Find your bot in the member list and tap it
4. Tap "Promote to Admin"

**What you should see:** A list of admin permissions.

### Step 6: Enable Required Permissions
Enable these permissions by toggling each one ON:
- [x] Manage Topics
- [x] Delete Messages
- [x] Pin Messages
- [x] Send Messages

Tap "Save" when done.

**What you should see:** Your bot is now listed as an administrator.

### Step 7: Activate the Group
1. Send any message in the group (like "Hello" or "Testing")
2. This allows the agent to detect the group ID

**What you should see:** Your message appears in the chat.

**What happens next:** The agent detects the group and can now create topics automatically.

---

## Phase 3: Workspace Creation (Agent Does This Automatically)

The agent will now create the workspace structure for your Command Center.

### 3.1 Create Base Directory
```bash
mkdir -p ~/.openclaw/workspaces/command-center/
```

### 3.2 Create Department Subdirectories
For each department you chose in Skill 23, the agent will create:
- A subdirectory named after the department
- IDENTITY.md with a unique 5-line identity
- MEMORY.md with department-specific memory
- A memory/ folder for daily logs

Example structure:
```
~/.openclaw/workspaces/command-center/
├── marketing/
│   ├── IDENTITY.md
│   ├── MEMORY.md
│   └── memory/
├── sales/
│   ├── IDENTITY.md
│   ├── MEMORY.md
│   └── memory/
└── operations/
    ├── IDENTITY.md
    ├── MEMORY.md
    └── memory/
```

### 3.3 Create Symlinks to Shared Files
Each department workspace will have symlinks to shared files from your main workspace:
- TOOLS.md
- AGENTS.md
- HEARTBEAT.md
- SOUL.md

**Important:** The agent uses absolute paths (like `/Users/username/clawd/TOOLS.md`), not tilde paths (`~/clawd/TOOLS.md`). This ensures symlinks work correctly.

---

## Phase 4: Agent Configuration (Agent Does This Automatically)

The agent will configure OpenClaw to recognize your department agents.

### 4.1 Backup Your Config First
The agent follows the backup protocol:
```bash
# Creates a timestamped backup
cp ~/.openclaw/openclaw.json ~/Downloads/openclaw-backups/openclaw-backup-[DATE].json
```

### 4.2 Add Department Agents
For each department, the agent adds an entry to `agents.list[]`:

```json
{
  "id": "cc/marketing",
  "name": "Chief Marketing Officer",
  "workspace": "/Users/username/.openclaw/workspaces/command-center/marketing",
  "memorySearch": {
    "extraPaths": ["/Users/username/Downloads/openclaw-master-files"],
    "multimodal": {
      "enabled": true,
      "modalities": ["all"]
    },
    "fallback": "none"
  }
}
```

**Important notes:**
- Agent ID format: `cc/[dept-name]` (cc stands for Command Center)
- Workspace paths are absolute (not tilde paths)
- extraPaths points to your master files folder using absolute path
- Sandboxing is NOT enabled (department heads need full access)

### 4.3 Add Telegram Group to Channels
The agent adds your Telegram group to the channels configuration:

```json
{
  "telegram": {
    "groups": [
      {
        "id": "-1001234567890",
        "name": "BlackCEO Command Center",
        "groupPolicy": "open",
        "requireMention": false
      }
    ]
  }
}
```

### 4.4 Validate Configuration
The agent runs validation:
```bash
openclaw config validate
```

**If validation fails:**
- The agent restores the backup config
- Stops and reports the error
- Does NOT proceed until you fix the issue

**If validation passes:**
- Proceeds to Phase 5

---

## Phase 5: Telegram Topic Creation (Agent Does This Automatically)

The agent creates one topic per department, plus a Cross-Department topic.

### 5.1 Create Department Topics
For each department (e.g., Marketing, Sales, Operations), the agent:

```bash
# Example: Create Marketing topic
# Uses the message tool with action: "topic-create"
```

The agent records each topic ID returned by Telegram.

### 5.2 Create Cross-Department Topic
The agent creates a general topic for interdepartmental collaboration:
- Name: "Cross-Department"
- Purpose: Messages that span multiple departments

### 5.3 Record Topic IDs
The agent saves all topic IDs for the binding step.

### 5.4 Add Topic Bindings to Config
For each topic, the agent adds a binding to `openclaw.json`:

```json
{
  "bindings": [
    {
      "agentId": "cc/marketing",
      "peer": {
        "kind": "group",
        "id": "-1001234567890",
        "topic": 2
      }
    }
  ]
}
```

**Note:** Each department agent is bound to its specific topic. Messages in that topic go directly to that agent.

---

## Phase 6: Dashboard Deployment (Agent Does This Automatically)

The agent deploys the visual Kanban dashboard.

### 6.1 Clone the Dashboard Repository
```bash
cd ~/projects
mkdir -p command-center
cd command-center
git clone https://github.com/trevorotts1/blackceo-command-center.git .
```

### 6.2 Install Dependencies
```bash
npm install
```

### 6.3 Configure the Dashboard
The agent updates the configuration file with:
- Your company name
- Your department list
- Your agent IDs

### 6.4 Start with PM2
```bash
pm2 start ecosystem.config.cjs
```

### 6.5 Verify Dashboard is Accessible
The agent checks that the dashboard loads at:
```
http://localhost:3000
```

**What you should see:** A Kanban board with all your departments and 5 columns (Backlog, Ready, In Progress, Review, Complete).

---

## Phase 7: Verification (Agent Does This Automatically)

The agent runs tests to verify everything works.

### 7.1 Test Department Response
1. Agent sends a test message in one department topic
2. Verifies the correct department head responds

**Expected result:** The department head for that topic responds within 30 seconds.

### 7.2 Test Memory System
```bash
openclaw memory status cc/marketing
```

**Expected result:** Status shows memory system active for the department agent.

### 7.3 Test Dashboard
The agent verifies:
- Dashboard loads at localhost:3000
- All departments appear in the sidebar
- All 5 Kanban columns are visible
- Task creation works

### 7.4 Report Results
The agent sends you a summary in Telegram:
- Which departments are active
- Dashboard URL
- How to access each department topic

---

## Phase 8: Optional - Cloudflare Tunnel for Remote Access

If you want to access your dashboard from outside your local network, the agent can set up a Cloudflare tunnel.

### 8.1 Install cloudflared (if not present)
```bash
# On macOS
brew install cloudflared

# On Linux
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

### 8.2 Create the Tunnel
```bash
cloudflared tunnel create command-center
```

### 8.3 Configure the Tunnel
```bash
cloudflared tunnel route dns command-center command-center.yourdomain.com
```

### 8.4 Start the Tunnel
```bash
cloudflared tunnel run command-center --url http://localhost:3000
```

### 8.5 Alternative: Tailscale
If you already use Tailscale, you can use that instead:
- Install Tailscale on the machine running the dashboard
- Access the dashboard via the Tailscale IP at port 3000

---

## Completion Checklist

After all phases are complete, verify:

- [ ] Telegram group created and named correctly
- [ ] Topics enabled (group is a supergroup)
- [ ] Bot is admin with Manage Topics permission
- [ ] One topic per department exists
- [ ] Cross-Department topic exists
- [ ] Department workspaces created at ~/.openclaw/workspaces/command-center/
- [ ] Each department has IDENTITY.md, MEMORY.md, and memory/ folder
- [ ] Agent config entries added for each department
- [ ] Telegram bindings configured for each topic
- [ ] Dashboard accessible at localhost:3000
- [ ] Test message received response from correct department head
- [ ] Memory status shows all department agents active

## What to Do Next

1. **Read INSTRUCTIONS.md** for how to use your Command Center daily
2. **Bookmark your dashboard** at http://localhost:3000
3. **Pin the Telegram group** for quick access
4. **Schedule your first standup** with your department heads

Your AI workforce is now live and ready to work.
