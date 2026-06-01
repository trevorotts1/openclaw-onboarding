# Verification Checklist Template -- Skill 41

## Copy-paste this checklist after every build

### Pre-publish verification (run before toggling to Published)

- [ ] 1. Workflow name matches the prompt
- [ ] 2. Trigger is correct type and filters are applied
- [ ] 3. All referenced tags exist and are spelled correctly
- [ ] 4. All referenced custom fields exist and have correct data type
- [ ] 5. All referenced custom values exist and have values set
- [ ] 6. Action sequence matches the prompt (order, configuration)
- [ ] 7. If/Else conditions evaluate the right fields with correct operators
- [ ] 8. Wait steps have correct duration
- [ ] 9. Webhook URL is correct and method matches the prompt
- [ ] 10. Webhook headers include Content-Type: application/json (for raw JSON body)
- [ ] 11. Settings: re-entry, stop on response, time windows are correct
- [ ] 12. Test the workflow with a test contact before going live

### Scoring

- Score: ___ / 12
- 12/12 = ready to publish
- 10-11/12 = minor fixes needed
- Below 10/12 = significant issues; rebuild or manual fix required

### Notes

[Record any issues found and how they were fixed.]

---

## Post-publish verification (run after going live)

- [ ] Workflow shows as Published (not Draft)
- [ ] Test contact successfully triggered the workflow
- [ ] Execution logs show no errors for the test run
- [ ] All actions fired in the correct order
- [ ] If/Else branches evaluated correctly
- [ ] Webhook received the expected payload (if applicable)
- [ ] Event logged to build-with-ai-events.jsonl
