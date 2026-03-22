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

### 6.5 Seed Department Workspaces into Database (MANDATORY)

After the dashboard starts, run the workspace seeding script to populate the database with all 17 department workspaces. Without this step, the workspace selector will only show the default workspace.

```bash
python3 ~/.openclaw/onboarding/32-command-center-setup/scripts/seed-workspaces.py
```

Expected output: "Seeding complete. Inserted: 17 | Skipped (already existed): 0"

If it says "Could not find mission-control.db" -- verify the dashboard started correctly in step 6.4 before running this.

### 6.6 Verify Dashboard is Accessible
The agent checks that the dashboard loads at:
```
http://localhost:3000
```

**What you should see:** The workspace selector screen showing all your department workspaces as cards you can click into. Each card shows task counts and agent count for that department.

---

## Phase 6b: Cloudflare Tunnel and Domain Registration (Agent Does This Automatically)

This phase connects your local dashboard to the internet with a custom subdomain. Your Command Center will be accessible from anywhere.

### 6b.1 Check if cloudflared is Installed

The agent checks if Cloudflare's tunnel software is installed:

```bash
which cloudflared
```

**If cloudflared is NOT found, the agent installs it:**

**On macOS:**
```bash
brew install cloudflared
```

**On Linux or VPS:**
```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

**What you should see:** Installation completes without errors.

### 6b.2 Create the Cloudflare Tunnel

The agent creates a named tunnel for your Command Center:

```bash
cloudflared tunnel create [clientName]-command-center
```

Replace [clientName] with your chosen name (for example: laura, acme, johnsmith).

**Naming rule (required):** Use the approved Option C pattern for the hostname slug: `[company-slug]-[shortid]`.

Examples:
- `laura-coaching-a7f3`
- `acme-dental-m42k`

**Why this matters:** Two clients can have the same or similar company names. The short ID prevents subdomain collisions while keeping the name readable.

**What you should see:**
- A tunnel is created
- A tunnel ID is displayed (this is a long UUID string)
- A credentials file is saved to ~/.cloudflared/

**Important:** Save the tunnel ID. The agent will use it in the next steps.

### 6b.3 Create the Tunnel Configuration File

The agent creates a config file at ~/.cloudflared/config-command-center.yml:

```yaml
tunnel: [TUNNEL_ID]
credentials-file: ~/.cloudflared/[TUNNEL_ID].json
ingress:
  - hostname: [clientName].zerohumanworkforce.com
    service: http://localhost:3000
  - service: http_status:404
```

Replace [TUNNEL_ID] with the actual tunnel UUID from Step 6b.2.
Replace [clientName] with your chosen client name.

**What you should see:** A new file is created with the correct settings.

### 6b.4 Start the Tunnel

The agent starts the tunnel to connect your local dashboard to the internet:

```bash
cloudflared tunnel run --config ~/.cloudflared/config-command-center.yml [clientName]-command-center
```

**What you should see:**
- The tunnel connects to Cloudflare
- Connection status messages appear
- The tunnel is now active

### 6b.5 Send Webhook to Register the Subdomain

The agent sends a registration message to Trevor's system to create the DNS route:

```
COMMAND_CENTER_REGISTRATION
clientName: [name]
tunnelId: [tunnel UUID]
companyName: [company]
contactEmail: [email]
```

**What happens on Trevor's side:**
1. Trevor's agent receives the registration message
2. The agent runs the command-center-webhook.sh script
3. The script creates the DNS route: [clientName].zerohumanworkforce.com
4. The client registry checks that the hostname is unique before finalizing the route
5. Your client information is added to the registry

**What you should see:** A confirmation that the registration was sent.

### 6b.6 Wait for DNS Propagation

DNS changes take a short time to spread across the internet. The agent waits for this to complete.

```bash
# Wait 30 seconds
sleep 30
```

**What you should see:** A brief pause while DNS updates.

### 6b.7 Verify the URL Works

The agent tests your new subdomain to confirm it is live:

```bash
curl -s -o /dev/null -w "%{http_code}" https://[clientName].zerohumanworkforce.com
```

**Expected result:** The command returns "200" (meaning the site is accessible).

**What you should see:**
- The HTTP status code 200
- Your dashboard is now live on the internet

### 6b.8 Report the Live URL to the Client

The agent tells you your Command Center is ready:

**What you should see:**
> "Your Command Center is now live at: https://[clientName].zerohumanworkforce.com"

You can now access your dashboard from any device, anywhere.

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

**Important requirement:** The Command Center must use the free self-hosted Mem0 / GitHub version, not a paid hosted account path. The agent must confirm the memory layer is running in the free OSS path and must fail the install if memory falls back to an inactive billed account.

### 7.3 Verify the 5-Layer Memory Setup
The agent verifies that each department workspace has the required memory architecture:

1. Memory Flush
2. Session indexing
3. Google Embedding 2 or equivalent local retrieval layer
4. Mem0 semantic memory in free self-hosted mode
5. Cognee / graph layer when enabled for the workspace

**Expected result:** Each department workspace is isolated and ready to store its own memory without mixing with Trevor's private memory or another client's workspace.

### 7.4 Test Dashboard
The agent verifies:
- Dashboard loads at localhost:3000
- All departments appear in the sidebar
- All 5 Kanban columns are visible
- Task creation works

### 7.5 Report Results
The agent sends you a summary in Telegram:
- Which departments are active
- Dashboard URL
- How to access each department topic

---

## Persona Integration

The Command Center task cards display which AI persona each agent is using. Personas are coaching blueprints extracted from books (Skill 22 / Book-to-Persona system).

Each agent selects a persona based on the task type:
- Content tasks: copywriting personas (Russell B., Seth G.)
- Sales tasks: persuasion personas (Alex H., Dean G.)
- Creative tasks: storytelling personas (Donald M., Austin K.)
- Leadership tasks: strategy personas (Simon S., Jim C.)

The persona is displayed as a purple pill on each task card with the format: first name + last initial.

To populate personas for clients:
- Complete the 70-question business interview
- Match interview answers to persona trait suggestions in suggested-roles files
- The department head selects the right persona for each task

---

## Phase 8: Optional - Manual Cloudflare Tunnel Setup (if Phase 6b was skipped)

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
- [ ] Cloudflare tunnel created and running
- [ ] DNS route registered for [clientName].zerohumanworkforce.com
- [ ] Hostname follows Option C pattern: [company-slug]-[shortid]
- [ ] Free self-hosted Mem0 path verified (not hosted billed mode)
- [ ] 5-layer memory setup verified per department workspace
- [ ] Live URL accessible from the internet
- [ ] Test message received response from correct department head
- [ ] Memory status shows all department agents active

## What to Do Next

1. **Read INSTRUCTIONS.md** for how to use your Command Center daily
2. **Bookmark your dashboard** at http://localhost:3000
3. **Pin the Telegram group** for quick access
4. **Schedule your first standup** with your department heads

Your AI workforce is now live and ready to work.
