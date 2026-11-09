# GHL Workflow AI Builder Reference -- Skill 41

## Compile-time, not runtime

The Workflow AI Builder turns a prompt into a workflow DEFINITION. It does not configure a native
Conversation AI responder, a voice agent, or knowledge retrieval, and it does not prove runtime
behavior. Those are separate operations with their own activation evidence (active responder,
channel/phone assignment, agent version) and their own controlled test. Treat a generated workflow
as definition proof only; read-back and runtime proof remain separate tiers.

## What It Is

Converts natural-language prompts into end-to-end workflows. Generates triggers, actions, and structure from plain English.

## Entry Points

1. Workflow List Page: Automation > Workflows > Build using AI button
2. Prompt Box Inside Workflow Builder: Type requirements in AI prompt box
3. AI Chatbot Assistant: Use chatbot inside workflow builder

## How It Works

1. Enter prompt (custom or from templates)
2. Click Build Workflow / Send
3. AI generates workflow (under 30 seconds average)
4. Review and customize
5. Edit using AI (conversational edits, Point and Edit, Chat Mode)

## What You Can Edit with AI

- Add/remove/replace/move actions
- Modify action configurations
- Add/remove/replace triggers
- Edit If/Else conditions (add/remove segments, change AND/OR)
- Edit Wait actions (update attributes, timeout branches)
- Combine multiple changes in single prompt
- Rename workflow
- Enable/disable workflow settings

## Workflow Settings Manageable by AI

- Allow Re-entry
- Allow Multiple Opportunities
- Stop on Response
- Timezone and Time Window (business hours)
- Sender Details (From Name, From Email, From Number)
- Conversations - Mark as Read
- Workflow name (rename)

## Key Features

- Clarifying Agent: Asks up to 3 clarifying questions when prompt lacks detail
- Chat Mode: Brainstorm without building, then build when ready
- Point and Edit: Select specific actions visually, apply changes only to those
- Autosave: AI-generated workflows auto-saved
- Post-Generation To-Do List: Items needing manual input before publishing

## Beta Limitations

- Manual review required before publishing
- Some complex configurations need manual adjustments
- AI cannot test workflows
- Marketplace triggers/actions NOT supported
- AI-generated workflows can land in Recent list rather than chosen folder

## Enabling/Disabling

- Agency level: Settings > Labs > enable/disable Workflow AI Builder
- Sub-Account level: Automations > Global Workflow Settings > Workflow AI > toggle
- For white-label (Convert and Flow): agency must activate before sub-account can use

## Critical Facts for Playbook

- Builder inserts placeholder custom value syntax but does NOT create the custom values
- Tags, custom fields, and custom values must be created FIRST
- Advanced nested logic and complex integrations still need manual configuration
- AI-generated workflows can land in Recent list rather than chosen folder
- The feature is free for all HighLevel users
- Not available for marketplace triggers/actions
- A trigger/action catalog entry, a docs page, or an MCP discovery result is NOT capability
  evidence; enablement is per `(operation_id, tenant)`
- The builder is an authoring surface (`skill06_authoring` for form/survey/page authoring rows); it
  is not a public create API
