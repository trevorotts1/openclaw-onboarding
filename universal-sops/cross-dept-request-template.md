# Cross-Department Request Template
**Version:** 1.0 | March 16, 2026

## Purpose
Every request sent from one department to another uses this format. Keeps communication clean, traceable, and automatically logged to the master orchestrator.

---

## Standard Request Format

```
FROM: [dept-name]
TO: [dept-name]
ROLE REQUESTED: [specific role being asked to handle this]
REQUEST: [clear one-sentence description of what is needed]
DEADLINE: [specific date/time or "ASAP"]
CONTEXT: [any background info, links, files, or references needed]
JOB ID: [auto-assigned: DEPT-YYYYMMDD-###]
CC: master-orchestrator (auto-logged)
```

---

## Example Requests

### Video → Audio (Voiceover Request)
```
FROM: video-dept
TO: audio-dept
ROLE REQUESTED: TTS Specialist
REQUEST: Generate a 90-second voiceover for the Product Launch video
DEADLINE: March 18 at 5 PM
CONTEXT: Script attached — use Trevor's voice profile, normal latency, 192kbps mp3
JOB ID: VIDEO-20260316-001
CC: master-orchestrator
```

### Sales → Creative (Email Copy Request)
```
FROM: sales-dept
TO: creative-dept
ROLE REQUESTED: Copywriter
REQUEST: Write a 3-email follow-up sequence for leads who didn't show up to the call
DEADLINE: March 19
CONTEXT: Leads are coaches and consultants. Tone: warm but direct. Goal: rebook the call.
JOB ID: SALES-20260316-002
CC: master-orchestrator
```

### Marketing → Graphics (Ad Creative Request)
```
FROM: marketing-dept
TO: graphics-dept
ROLE REQUESTED: Ad Creative Designer
REQUEST: Create 3 static ad creative variants for the spring campaign
DEADLINE: March 20
CONTEXT: Campaign brief in Google Drive [link]. Brand colors only. Size: 1080x1080 and 1080x1920.
JOB ID: MKTG-20260316-003
CC: master-orchestrator
```

---

## Delivery Format

When fulfilling a request, reply using this format:

```
FROM: [dept-name]
TO: [requesting dept-name]
JOB ID: [original Job ID]
STATUS: DELIVERED ✅
DELIVERABLE: [link, file path, or inline content]
NOTES: [anything the requesting dept should know]
CC: master-orchestrator (auto-logged)
```

---

## Rules

1. Every cross-dept request uses this format. No exceptions.
2. Job ID is always assigned. Format: DEPT-YYYYMMDD-###
3. Master orchestrator is always CC'd. It does not need to approve — it just needs to know.
4. If a request cannot be fulfilled by the deadline, the receiving dept must notify the requesting dept immediately with a revised timeline.
5. If fulfilling the request requires input from a third department, the receiving dept coordinates that — not the requesting dept.
