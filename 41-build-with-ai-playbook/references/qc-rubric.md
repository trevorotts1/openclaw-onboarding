# QC Rubric -- Skill 41 Build With AI Playbook Generator

## 10-Category QC Rubric

Every generated Build With AI prompt and every build session is scored across these 10 categories. Threshold: 8.5/10 to pass.

### 1. Prompt Completeness (1.0 point)
Does the generated prompt contain all 8 required sections?
- Workflow name
- Trigger specification
- Dependency list
- Action sequence
- Conditions
- Webhook configuration
- Settings
- Post-build verification checklist

Scoring: 1.0 = all 8 present; 0.5 = 6-7 present; 0.0 = fewer than 6

### 2. Dependency-First Compliance (1.0 point)
Were all dependencies (tags, fields, values) created BEFORE the workflow prompt was generated?
- Evidence: dependency_created events in build-with-ai-events.jsonl
- Evidence: GET verification calls after each POST

Scoring: 1.0 = all dependencies created and verified first; 0.5 = some created but not all verified; 0.0 = dependencies missing or created after prompt

### 3. ZHC Prefix Discipline (1.0 point)
Do all agent-created tags and fields carry the correct prefix?
- Tags: ZHC- prefix
- Custom fields: ZHC_ prefix
- No existing operator-owned tags/fields were renamed

Scoring: 1.0 = all correct; 0.5 = most correct, one or two missed; 0.0 = multiple missing or wrong prefixes

### 4. No Fabrication (1.0 point)
Did the agent invent any GHL trigger, action, or capability that does not exist?
- Cross-reference against references/ghl-triggers-catalog.md and references/ghl-actions-catalog.md
- Honest gaps reported with operator manual path

Scoring: 1.0 = zero fabrication; 0.0 = any fabricated capability

### 5. Webhook Configuration Accuracy (1.0 point)
If webhooks are present, is the configuration correct?
- Method matches requirement
- URL is HTTPS
- Content-Type header present for JSON body
- Raw body is valid JSON
- Merge fields use correct syntax

Scoring: 1.0 = all correct; 0.5 = minor issue; 0.0 = major misconfiguration

### 6. Condition Logic Correctness (1.0 point)
Are If/Else conditions logically sound?
- Correct field references
- Correct operators
- Both YES and NO branches defined
- AND/OR logic matches intent

Scoring: 1.0 = all correct; 0.5 = minor logic gap; 0.0 = broken or missing logic

### 7. Settings Accuracy (1.0 point)
Do workflow settings match the operator's intent?
- Re-entry: yes/no correct
- Stop on response: yes/no correct
- Time window matches business hours
- Sender details correct

Scoring: 1.0 = all match; 0.5 = one mismatch; 0.0 = multiple mismatches

### 8. Verification Checklist Run (1.0 point)
Was the 12-point verification checklist actually run after build?
- Evidence: build_completed event with verification_score
- Or verification_failed event with failed_items

Scoring: 1.0 = checklist run and score recorded; 0.5 = checklist run but not logged; 0.0 = no verification

### 9. Event Logging (1.0 point)
Was the build session properly logged?
- At minimum: build_completed event
- Ideally: brainstorm_started, dependency_audited, dependency_created, prompt_generated, build_completed

Scoring: 1.0 = full event chain logged; 0.5 = build_completed only; 0.0 = no logging

### 10. Operator Confirmation (1.0 point)
Was operator intent confirmed before building?
- Evidence: brainstorm_started event with operator_intent_summary
- Evidence: operator_confirmed = true in build_initiated event

Scoring: 1.0 = confirmed; 0.5 = partially confirmed; 0.0 = built on guess

## Scoring

- Sum all 10 categories (max 10.0)
- Threshold: 8.5 to pass
- Below 8.5: fix the weakest categories and re-run QC
