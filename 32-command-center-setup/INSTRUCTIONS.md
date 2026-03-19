# Command Center - Post-Installation Usage Guide

## Welcome to Your Command Center

Your AI workforce is now live. This guide shows you how to use your Command Center effectively.

---

## How to Talk to Department Heads

Each department has its own dedicated topic in your Telegram Command Center group.

### Finding Department Topics
1. Open your Telegram Command Center group
2. Look for the topics list at the top (it may say "Topics" or show topic names)
3. Tap to see all available topics

### Starting a Conversation
1. Tap the topic for the department you want to reach (e.g., "Marketing")
2. Type your message as you normally would
3. The department head will respond directly in that topic

**Example messages:**
- "We need a social media campaign for our new product launch"
- "Review last month's sales numbers and give me insights"
- "Help me prepare for tomorrow's investor meeting"

### Getting the Best Responses
- Be specific about what you need
- Mention deadlines if there are any
- Ask questions if you need clarification
- The department head will ask follow-up questions if needed

### Cross-Department Topics
Use the "Cross-Department" topic when:
- A project involves multiple departments
- You want to announce something company-wide
- You need departments to coordinate with each other

---

## The Standup Cadence

Your Command Center operates on a 3-check rhythm. Department heads will proactively check in at these times.

### Morning Check-In (9 AM)
**What happens:** Each department head reviews overnight activity and plans the day.

**What you will see:**
- Summary of what was completed overnight
- Today's priorities list
- Any blockers or questions for you

**How to respond:**
- Reply with approvals or changes to priorities
- Answer any questions
- Add new tasks if needed

**Example response:**
> "Focus on the product launch campaign first. The investor presentation can wait until tomorrow."

### Midday Sync (1 PM)
**What happens:** Progress updates and coordination.

**What you will see:**
- Progress on morning priorities
- Any cross-department needs
- Resource requests

**How to respond:**
- Approve resource shifts if needed
- Resolve any conflicts between departments
- Adjust priorities based on new information

### End of Day Report (5 PM)
**What happens:** Summary of the day's work and tomorrow's preview.

**What you will see:**
- Completed work summary
- What is continuing tomorrow
- Any escalations that need your attention

**How to respond:**
- Acknowledge the report
- Set priorities for tomorrow if they have changed
- Address any escalations

### Adjusting the Schedule
If these times do not work for you, tell your department heads:
> "Change standup times to 8 AM, 12 PM, and 4 PM"

The agents will update their schedule and follow the new times.

---

## How to Create Tasks on the Kanban Board

### Accessing the Dashboard
1. Open your web browser
2. Go to http://localhost:3000 (or your Cloudflare URL if set up)
3. You will see your Kanban board with all departments

### Creating a New Task
1. Click the "+" button or "Add Task" in any column
2. Fill in the task details:
   - **Title:** Short description of the task
   - **Department:** Which department should handle this
   - **Description:** More details about what needs to be done
   - **Due Date:** When it needs to be completed (optional)
3. Click "Create"

### Task Status Columns
Your Kanban board has 5 columns:

| Column | Purpose | When to Use |
|--------|---------|-------------|
| **Backlog** | Ideas and future work | Tasks not yet ready to start |
| **Ready** | Approved and waiting | Tasks ready to be worked on |
| **In Progress** | Currently being worked on | Active tasks |
| **Review** | Completed, needs approval | Tasks waiting for your review |
| **Complete** | Finished and approved | Done tasks |

### Moving Tasks
- Drag and drop tasks between columns
- Or click the task and change its status
- Department heads will move tasks as they work on them

### Assigning Tasks
When you create a task:
1. Select the department
2. The department head will automatically see it
3. They may assign it to a specific worker or handle it themselves

---

## How to View the Dashboard

### Local Access
- URL: http://localhost:3000
- Only works when you are on the same computer or network

### Remote Access (if Cloudflare tunnel is set up)
- URL: Your custom Cloudflare URL (e.g., https://command-center.yourdomain.com)
- Works from anywhere with internet access

### Dashboard Sections

**Left Sidebar:**
- Department list
- Click any department to filter tasks
- "All Departments" shows everything

**Main Board:**
- 5 Kanban columns
- Tasks displayed as cards
- Click any card to see details

**Top Bar:**
- Company name
- Search function
- Add task button

### Refreshing Data
The dashboard updates automatically every 30 seconds. To force a refresh:
- Press F5 on your keyboard
- Or click the refresh icon if available

---

## How Department Heads Spin Up Workers

When a task requires specialized work, department heads can create worker agents.

### When Workers Are Created
A department head may spin up workers for:
- Research tasks
- Content creation
- Data analysis
- Design work
- Code development
- Any specialized skill

### How It Works
1. The department head identifies the need
2. Creates a worker agent with a specific persona
3. Assigns the task to the worker
4. Reviews the worker's output
5. Delivers the result to you

**You do not need to manage this process.** The department head handles it automatically.

### Worker Personas
Workers use personas from your Book-to-Persona system (Skill 22). Each persona has specific expertise and a proven methodology.

**Example:**
- Marketing department needs copywriting
- Chief Marketing Officer spins up a worker
- Assigns the "David Ogilvy" copywriting persona
- Worker produces ad copy using Ogilvy's proven methods

### Worker Lifecycle
Workers are temporary:
- Created for a specific task
- Complete the work
- Deliver results
- Are then terminated (they do not persist)

This keeps the system efficient. Only department heads persist. Workers are spun up as needed.

---

## How Personas Get Assigned to Workers

### Automatic Assignment
Department heads automatically assign the right persona based on:
- The type of task
- The expertise needed
- The methodology that fits best

**Examples:**
- Writing task → Copywriting persona
- Design task → Design methodology persona
- Strategy task → Business strategy persona
- Research task → Research methodology persona

### From Your Persona Library
Personas come from your coaching-personas folder (created in Skill 22). The department head searches this library to find the best match.

**To add more personas:**
1. Use Skill 22 (Book-to-Persona) to create new personas
2. Save them to the coaching-personas folder
3. Department heads will automatically have access to them

### Custom Personas
If you want a specific persona used for certain work, tell the department head:
> "Use the Seth Godin persona for this marketing campaign"

The department head will honor your request.

---

## Daily Workflow Example

Here is what a typical day looks like with your Command Center:

### 9:00 AM - Morning Check-In
You open Telegram and see messages from each department head:
- Marketing: "Today I will focus on the product launch campaign and social media calendar."
- Sales: "Following up on 3 leads from yesterday and preparing the proposal for ABC Corp."
- Operations: "Reviewing vendor contracts and updating the team handbook."

You reply: "Priority order: ABC Corp proposal first, then product launch. Everything else can wait."

### 10:30 AM - New Task
You think of something and message the Marketing topic:
> "We need a landing page for the product launch. Get that started."

Marketing head replies: "On it. I will spin up a copywriter and designer. Expect a draft by end of day."

### 1:00 PM - Midday Sync
You check the dashboard and see:
- Sales moved the ABC Corp proposal to "In Progress"
- Marketing created a "Landing Page Copy" task
- Operations completed the vendor review

You send a quick message to Operations: "Great work on the vendor review. Send me the summary."

### 3:00 PM - Question from Department
Sales department messages:
> "ABC Corp wants a discount. Standard discount is 10 percent. Should I offer 15 percent to close the deal?"

You reply: "Yes, 15 percent is approved. Get the signature."

### 5:00 PM - End of Day Report
Department heads send summaries:
- Sales: "ABC Corp proposal sent with 15 percent discount. Expecting response tomorrow."
- Marketing: "Landing page copy drafted. Moving to design phase tomorrow."
- Operations: "Vendor review complete. Team handbook updated."

You reply: "Good work today. Tomorrow's priority: ABC Corp response and landing page design."

---

## Tips for Success

### 1. Respond to Standups
Even a quick "Looks good" helps the department heads know you are engaged and their priorities are correct.

### 2. Use the Dashboard for Overview
Check the Kanban board once or twice a day to see the big picture of what is happening.

### 3. Trust the Department Heads
They are designed to handle their domains. Give them direction, then let them execute.

### 4. Escalate When Needed
If a department head brings you an escalation, respond promptly. They are waiting for your decision to proceed.

### 5. Update Priorities as Needed
Business changes. Tell your department heads when priorities shift. They will adjust immediately.

### 6. Keep Personas Updated
As you create new personas with Skill 22, your department heads get more powerful. Invest in building your persona library.

---

## Common Questions

**Q: How many departments can I have?**
A: As many as you created in Skill 23. Each gets its own topic and agent.

**Q: Can I add more departments later?**
A: Yes. Run Skill 23 to add departments, then re-run Skill 32 to activate them.

**Q: What if a department head makes a mistake?**
A: Tell them the correction. They will learn from it and update their approach.

**Q: Can department heads talk to each other?**
A: Yes, in the Cross-Department topic. They will coordinate there when needed.

**Q: What if I am not available during standup times?**
A: The department heads will continue working based on their current priorities. Catch up when you can.

**Q: How do I turn off standups?**
A: Tell your department heads: "Pause standups until I tell you to resume."

**Q: Can I access the dashboard from my phone?**
A: If you set up the Cloudflare tunnel, yes. Otherwise, it is only available on the local network.

---

## Getting Help

If something is not working:
1. Check the troubleshooting section in SKILL.md
2. Verify all installation phases completed
3. Ask the department head directly in their topic
4. Check that the dashboard is running: `pm2 list`

Your Command Center is designed to be self-managing. Once set up, it should run smoothly with minimal intervention.
