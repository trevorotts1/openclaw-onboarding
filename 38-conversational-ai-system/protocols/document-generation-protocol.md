# Document Generation Protocol

The agent generates customer-facing documents from operator-provided
templates and delivers them via the customer's channel.

## Template registry

Templates live in `<MASTER_FILES_DIR>/document-templates/`. Each
template has:

```yaml
- id: <short identifier, e.g., "quote-standard">
  type: <quote | proposal | contract | agreement | other>
  name: <human-readable name>
  template_file: <path to .docx, .gdoc, or .pdf>
  variables:
    - name: customer_name
      source: contact.first_name + " " + contact.last_name
    - name: amount
      source: ask_agent  # agent infers from conversation
    - name: date
      source: today
    - name: <other>
      source: <static | ask_agent | from_contact | from_log>
  trigger_phrases:
    - "can you send me a quote"
    - "I'd like a proposal"
    - "send me a contract"
  approval_required: <true | false>  # if true, operator must approve
                                       # before document is sent
```

## Generation flow

1. Customer asks for a document (matching a trigger phrase OR the
   agent recognizes intent from conversation).
2. Agent identifies the matching template.
3. Agent fills variables:
   - Static values from template
   - Customer data from contact record (via GHL skill)
   - Inferred values from conversation context (amount, scope, etc.)
   - If any variable can't be resolved, agent asks customer or operator
4. If `approval_required: true`, agent shows the filled draft to the
   operator, waits for approval, then sends.
5. Agent generates the document (Word fill via python-docx, Google Doc
   via Docs API, PDF via reportlab or by converting Word).
6. Agent sends the document to the customer via the channel they
   contacted on (or email if document is too large for SMS/social).
7. Agent tags contact as `document-sent-<template-id>`.
8. Agent logs the generation event to the contact's conversation log.

## Variable resolution

For variables marked `source: ask_agent`, the agent uses the
conversation context to infer the value. Example: customer says "I'm
looking at the 6-month package," agent infers `amount: $X` from the
products knowledge source (Step 9.14).

If inference confidence is low (< 0.7 — see confidence-threshold-
protocol.md), the agent escalates rather than guessing.

## Output

Generated documents are sent to the customer. A copy is saved to
`<MASTER_FILES_DIR>/generated-documents/<contact_id>/<timestamp>-<template-id>.pdf`
for the operator's records.

## Capabilities playbook integration

This adds a new capability to agent-capabilities-playbook.md Section 2:

  2.6 — Generate documents from templates
  When customer requests a quote, proposal, contract, or other document
  the operator has templated, the agent fills the template with
  customer-specific values and sends it.
```

**C. Update agent-capabilities-playbook.md** with Section 2.6.

**D. Append to Run Manifest:** "Step 9.18 complete — document-generation-protocol.md created, <N> templates registered (or 0 with deferred setup), capabilities playbook updated with Section 2.6."

