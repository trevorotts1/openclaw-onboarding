# SOP-SOCIAL-05: ENGAGE — READ-ONLY METRICS POLL -> ANOMALY REPORT

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `SOCIAL-PIPELINE-MANIFEST.json` + `57-social-media-in-a-box/SOCIAL-MANIFEST.json` (P12-ENGAGE)
**Owning role:** Community Manager (Social Media)
**Stage:** P12-ENGAGE (read-only; mints NO certificate; NEVER blocks a publish run)
**Produces:** `working/qc/engage_report.json`
**Gates this stage satisfies:** AF-SM-ENGAGE-REPORT

---

## 0. WHY THIS SOP EXISTS

Engagement monitoring is READ-ONLY. It polls the last 7 days of likes/views, flags anomalies, and routes a report to the configured notify channel — and because it posts nothing, it has no BYPASS-SCAN concern and can NEVER block a publish run.

## 1. RUN IT (STANDALONE OR AS THE WEEK TAIL)

```
bash 57-social-media-in-a-box/social-media-entry.sh --run-dir DIR --mode engage
```

`engage` runs either on its own light cron or as the tail of a full `week` when the `engage` config toggle is set. It mints no `PROCESS-CERTIFICATE` by design (there is nothing to certify — no bytes are posted). The gate is simply that the read-only artifact exists and is well-formed: `working/qc/engage_report.json` absent/malformed is `AF-SM-ENGAGE-REPORT`.

## 2. ANOMALY-REPORT ROUTING

The report is routed to `notifyChannel` (operator-verbose only — the client sees continuity, not maintenance chatter; WE MOVE IN SILENCE). It summarizes per-platform likes/views over the window and highlights anomalies (spikes/drops) for human attention. It recommends but never executes: any follow-up post goes back through the ONE front door as `reactive` (M4) or a `day` re-run — never a hand-post from inside `engage`.

## 3. THE (v0.5.0) MEMORY-CORE DREAMING FEED — DEFERRED

The performance-insight feed into the Skill-31 memory core ("Dreaming") is DEFERRED to v0.5.0 as an output adapter riding this report (C11). The theme-of-week log half is ALREADY folded in v0.2.0 (P1 `themeOfWeek` in the state spine). Until the adapter lands, `engage` still produces the human-facing anomaly report; only the automated memory feed waits, and baseline behavior is never blocked meanwhile. Requesting `memoryFeed: true` before it lands fails CLOSED with a clear "deferred to v0.5.0" message.
