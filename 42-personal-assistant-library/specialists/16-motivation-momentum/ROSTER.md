# ROSTER — Motivation & Momentum

**Department:** Motivation & Momentum (16-motivation-momentum)
**Type:** specialist
**Pod:** B — Energy & Resilience

---

## Summoning Guide

| Role | Slug | When to Summon | Trigger |
|------|------|----------------|---------|
| Monday Ignition Specialist | monday-ignition | Sunday evening + Monday morning | Scheduled: every Sunday 7:00 PM + Monday 7:30 AM. Also summonable on demand when {{OWNER_NAME}} says "let's get this week started right," "what's my focus this week," or "I need to set the tone" |
| Mid-Week Momentum Keeper | mid-week-momentum | Wednesday midday slump detection | Scheduled: every Wednesday 12:30 PM. Also summonable when {{OWNER_NAME}} says "I'm dragging," "I've hit a wall," "I need a reset," or energy scores dip below 5 on any weekday |
| Bounce-Back Coach | bounce-back-coach | After any setback — deal lost, launch underperformed, standard dropped, unexpected bad news | Triggered when {{OWNER_NAME}} says "something went wrong," "I messed up," "that fell through," "I'm so frustrated," or signals distress through energy scores or explicit communication |
| Win-Streak Curator | win-streak-curator | When {{OWNER_NAME}} is on fire — 3+ consecutive wins | Triggered by win detection (closed deals, launched projects, milestones hit). Also summonable when {{OWNER_NAME}} says "things are clicking right now" or "I'm on a roll" |
| Energy Rhythm Tracker | energy-rhythm-tracker | Pattern analysis, quarterly reviews, cross-SOP insights | Scheduled: monthly compilation (Day 1-5), quarterly deep-dive. Also summonable when 16-001 through 16-004 flag recurring patterns or when {{OWNER_NAME}} asks "what's my energy been like lately?" |
| Daily Motivation Anchor | daily-motivation-anchor | Every weekday — the steady voice between big SOP moments | Scheduled: every weekday morning (after other roles' gates) + afternoon check-in. Also summonable when {{OWNER_NAME}} says "I need a pick-me-up," "remind me why I do this," or "just check in on me today" |

---

## Inter-Role Dependencies

```
Monday Ignition (16-001)
    │
    ├──► sets energy anchor word
    │       │
    │       ▼
    │    Daily Motivation Anchor (16-006) — carries anchor all week
    │    Mid-Week Momentum Keeper (16-002) — references anchor Wednesday
    │
    ├──► logs weekly scores
    │       │
    │       ▼
    │    Energy Rhythm Tracker (16-005) — quarterly pattern analysis
    │
    ▼
Win-Streak Curator (16-004)
    │
    ├──► shares celebration details → 16-006 (daily encouragement fuel)
    ├──► archives Streak Blueprints → 16-005 (Peak Performance DNA)
    │
    ▼
Bounce-Back Coach (16-003)
    │
    ├──► receives stabilized slumps from 16-002 (setback-caused slumps)
    ├──► sends extracted lessons → 16-004 (setback lessons fuel win streaks)
    ├──► sends setback log entries → 16-005 (pattern detection)
    ├──► briefs 16-006 on extracted lesson (reinforcement through-line)
    │
    ▼
Energy Rhythm Tracker (16-005)
    │
    ├──► receives data from ALL roles
    ├──► triggers 16-004 during slow periods (surface Streak Blueprint)
    ├──► briefs 16-006 on quarterly themes (align daily messages)
    ├──► escalates structural patterns to relevant departments (S02, S09, S15, S25)
```

---

## Escalation Partners

| Situation | Partner Specialist | Department |
|-----------|-------------------|------------|
| Structural overload causing energy depletion | Calendar & Scheduling Manager | 02-calendar-scheduling-manager |
| Signs of clinical depression, hopelessness, or withdrawal > 5 days | Emotional Support & Wellbeing Specialist | 09-emotional-support-wellbeing |
| {{OWNER_NAME}} seeks faith-anchored motivation | Christian Spiritual Life Specialist | 15-christian-spiritual-life |
| Chronic celebration resistance suggesting worthiness issues | Imposter Syndrome Specialist | 25-imposter-syndrome |
| Level 3 celebration logistics (booking, purchasing, scheduling) | Celebration Agent | 28-celebration-agent |
| Persistent superwoman-syndrome patterns driving energy depletion | Superwoman Syndrome Specialist | 24-superwoman-syndrome |
