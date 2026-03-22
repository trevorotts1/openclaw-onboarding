# Command Center Setup - Core File Updates

This document lists the exact additions to make to your core .md files after installing the Command Center.

---

## MEMORY.md Addition

Add this line to MEMORY.md (usually at the top, in the status section):

```markdown
Command Center installed [DATE], [X] departments active, dashboard at [URL]
```

**Example:**
```markdown
Command Center installed March 19 at 3-45 PM, 5 departments active, dashboard at http://localhost:3000
```

**What to replace:**
- `[DATE]` - Use the current date in human-readable format
- `[X]` - The number of departments you activated
- `[URL]` - Either `http://localhost:3000` or your Cloudflare tunnel URL if set up

---

## TOOLS.md Addition

Add this section to TOOLS.md (in the services/tools section):

```markdown
## Command Center Dashboard

**Local URL:** http://localhost:3000
**Remote URL:** [Your Cloudflare URL if configured]
**Telegram Group:** [Your Company Name] Command Center

Departments communicate via dedicated topics in the Telegram group. Each department head responds in their assigned topic.

### Department Topics
- Marketing - Chief Marketing Officer
- Sales - Chief Sales Officer
- Operations - Chief Operating Officer
- [Add your other departments here]
- Cross-Department - For interdepartmental collaboration

### Accessing the Dashboard
- Local: http://localhost:3000
- Requires the PM2 process to be running: `pm2 list` to check
- View logs: `pm2 logs command-center`

### Managing the Dashboard
```bash
# Check if running
pm2 list

# View logs
pm2 logs command-center

# Restart if needed
pm2 restart command-center

# Stop
pm2 stop command-center
```
```

**What to customize:**
- Replace `[Your Cloudflare URL if configured]` with your actual URL or remove if not using Cloudflare
- Replace `[Your Company Name]` with your actual company name
- Update the department list to match your actual departments

---

## HEARTBEAT.md Addition

Add this task to HEARTBEAT.md (in the regular checks section):

```markdown
### Command Center Activation Check

Check twice daily if Skill 23 is complete but Command Center not yet set up.

**How to check:**
1. Look for department folders in ~/Downloads/openclaw-master-files/ (or your master files location)
2. Check if ~/.openclaw/workspaces/command-center/ exists

**If Skill 23 is done and no command-center workspace exists:**
- Prompt user to activate Skill 32: "Your AI Workforce Blueprint is complete. Activate Skill 32 to set up your Command Center with live department agents and dashboard."

**If Command Center exists:**
- Verify dashboard is running: `pm2 list | grep command-center`
- If not running, start it: `cd ~/projects/command-center && pm2 start ecosystem.config.cjs`
```

---

## AGENTS.md - Optional Addition

If your AGENTS.md has a "Multi-Agent Patterns" or "Agent Workflows" section, add this:

```markdown
### Command Center Pattern

The Command Center uses a "Department Head" pattern:
- One persistent agent per department
- Each bound to a dedicated Telegram topic
- Workers spun up on-demand for specific tasks
- Personas assigned from coaching-personas library

See full documentation: ~/Downloads/openclaw-master-files/32-command-center-setup/
```

If you do not have such a section, this addition is optional.

---

## Verification

After making these additions, verify:

1. MEMORY.md shows your Command Center status
2. TOOLS.md has the dashboard information
3. HEARTBEAT.md has the activation check task
4. All paths and URLs are correct for your setup

---

## Notes

- Keep these entries concise (as shown above)
- Full documentation stays in the skill folder
- These are pointers and status updates only
- Update the dashboard URL in TOOLS.md if you change from localhost to Cloudflare
