# OPERATIONS-HEARTBEAT.md — Operations Admin Recurring Duty Schedule

## Duty 1: Calendar Conflict Check
**Source:** Google Calendar API | **Schedule:** Every 4h @ :00 | **Escalation:** Telegram

## Duty 2: Urgent Email Triage
**Source:** Gmail API | **Schedule:** Every 4h @ :15 | **Escalation:** Telegram

## Duty 3: Overdue Task Scan
**Source:** CC task API | **Schedule:** Every 4h @ :30 | **Escalation:** Kanban -> Telegram at 7+ days

## Duty 4: Pending Items Sweep
**Source:** CC task API + ledger | **Schedule:** Every 4h @ :45 | **Escalation:** Dept channel / reassign
