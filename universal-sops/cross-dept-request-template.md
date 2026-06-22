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

---

## Full-Funnel Pipeline P-Boundary Handoffs

When a cross-department handoff occurs at a full-funnel pipeline P-boundary (P0→P1, P1→P2, P1→P2e, P2→P3, P2+P3→P4, P2e+P4→P5), the handoff ALSO emits a **board handoff event** in addition to the standard CC message above.

The board handoff event is emitted by the completing stage agent immediately after its task status changes to `done` or `APPROVED`. Format:

```json
{
  "event_type": "board_handoff",
  "from_dept": "<completing department slug>",
  "to_dept": "<receiving department slug>",
  "artifact": "<artifact name and path, e.g. 'offer-spec.json at working/funnels/<slug>/offer-spec.json'>",
  "job_id": "<receiving stage task_id (the child card to be dispatched next)>",
  "parent_task_id": "<parent funnel_epic task_id>",
  "timestamp": "<ISO 8601>"
}
```

This event is posted to `POST {COMMAND_CENTER_URL}/api/tasks/{parent_task_id}/events` and bumps `last_progress_at` on the parent epic. The orchestrator listens for it via the SSE stream (`/api/events`) to trigger the depends_on gate check for the next stage.

**The board handoff event does NOT replace the CC message.** Both are emitted. The CC message is for human-readable activity logging; the board event is for the orchestrator's gate check and stale-detection reset.
