# Conversation Playbook Template -- Skill 41 (Pairs with Skill 38)

## Purpose

When a workflow triggers a conversation (e.g., Customer Replied trigger, Conversation AI action), this playbook governs how the agent responds. Register this playbook in Skill 38's conversation-workflows/registry.md.

## Workflow pairing

| Field | Value |
|---|---|
| Workflow name | [Name of the GHL workflow] |
| Workflow trigger | [Trigger type] |
| Conversation trigger | [What starts the conversation: inbound SMS, email reply, etc.] |
| Playbook ID | [Unique identifier, e.g., workflow-name-conversation] |

## Tone and voice

- [Describe the tone: professional, friendly, urgent, empathetic, etc.]
- [Signature style: how the agent signs off]
- [Channel-specific formatting: SMS = short paragraphs, no markdown; Email = subject line + signature]

## Greeting

[How the agent greets the contact when the conversation starts.]

Example: "Hi {{contact.first_name}}, this is <Business>. I saw you [trigger context]. How can I help?"

## Conversation flow

### Phase 1: Acknowledge
[Acknowledge the contact's message or the workflow trigger.]

### Phase 2: Gather context
[Ask 1-2 smart questions to understand what the contact needs.]

### Phase 3: Provide value
[Give the contact useful information, a resource, or a next step.]

### Phase 4: Close or escalate
[Close with a clear next step, or escalate to a human if needed.]

## Escalation triggers

Escalate to a human operator when:
- [Condition 1, e.g., "contact asks to speak to a person"]
- [Condition 2, e.g., "contact uses abusive language"]
- [Condition 3, e.g., "request is outside agent's capabilities"]

## FAQ scope

[Link to the FAQ file that covers common questions for this workflow context.]

Example: KnowledgeBases/business/faqs.md

## Interrupt handling

[How to handle interruptions during the conversation flow.]

- Save workflow state
- Handle the interrupt (FAQ, compliance keyword, aggression)
- Return to the saved state with a soft transition

## ZHC tags

Tags this conversation playbook may apply:
- [Tag 1 and when it fires]
- [Tag 2 and when it fires]

## Event logging

Every conversation turn appends to the contact's conversation log file per Skill 38's conversation-log-protocol.md.

## Example conversation

```
Contact: "I got your email but I have a question."
Agent: "Hi {{contact.first_name}}, thanks for reaching out! I'm here to help. What's your question?"
Contact: "[Question]"
Agent: "[Answer based on FAQ scope]. Does that help?"
Contact: "Yes, thanks!"
Agent: "Great! If you need anything else, just reply. Have a wonderful day!"
```
