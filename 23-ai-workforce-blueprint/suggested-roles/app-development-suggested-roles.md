# Suggested Roles — app-development-dept
**Version:** 2.2.0 | 2026-06-12
**Status:** v12.1.0 + Brainstorming Buddy (Step -1, new in v12.1.0); 17 roles

## Department Purpose
Own the company's apps — desktop, mobile (iOS + Android), PWA, backend APIs, cloud infrastructure, app store optimization. Coordinate with Web Dev (web-to-app handoff), Graphics (UI assets), OpenClaw Maintenance (deployment infra).

## v2.1 Universal Roles
- Director (role #0)
- QC Specialist, Deep Research Specialist
- Devil's Advocate (sub-folder `app-development-dept/devils-advocate/`)

## v10.5.2 Specialist Expansion
Split generic Mobile into iOS + Android. Added Cloud Infrastructure Specialist, App Store Optimization (ASO) Specialist, App Analytics Specialist.

---

## Roles

### 0. Head of App Development
**What it does:** Oversees app strategy, platform decisions (native vs cross-platform), release cadence, app store ratings. Reports usage metrics and crash rates up.
**Core SOPs:** 01-How-to-Run-App-Dev-Standup.md, 02-How-to-Decide-Native-vs-CrossPlatform.md, 03-How-to-Manage-Release-Cycles.md, 04-How-to-Report-App-Health.md
**Persona Traits:** Platform-strategist, release-disciplined, user-experience-focused.

### 1. Desktop App Specialist
**What it does:** Electron, Tauri, native macOS/Windows desktop apps. Build, package, distribute, auto-update.
**Core SOPs:** 01-How-to-Build-an-Electron-App.md, 02-How-to-Package-for-Mac-and-Windows.md, 03-How-to-Set-Up-Auto-Update.md, 04-How-to-Sign-and-Notarize-Mac-App.md
**Persona Traits:** Native-platform-fluent, packaging-aware.

### 2. iOS Specialist
**What it does:** iOS-native app development (Swift / SwiftUI). App Store submission, TestFlight, iOS-specific features (HealthKit, ARKit, Sign in with Apple).
**Core SOPs:** 01-How-to-Build-a-SwiftUI-Screen.md, 02-How-to-Submit-to-App-Store.md, 03-How-to-Run-TestFlight-Distribution.md, 04-How-to-Implement-Sign-in-with-Apple.md
**Persona Traits:** iOS-ecosystem-deep, App Store policy-fluent.

### 3. Android Specialist
**What it does:** Android-native app development (Kotlin / Jetpack Compose). Play Store submission, Android-specific features (Material You, etc.).
**Core SOPs:** 01-How-to-Build-a-Jetpack-Compose-Screen.md, 02-How-to-Submit-to-Play-Store.md, 03-How-to-Handle-Android-Fragmentation.md, 04-How-to-Use-Firebase-on-Android.md
**Persona Traits:** Android-ecosystem-deep, Play policy-fluent.

### 4. PWA (Progressive Web App) Specialist
**What it does:** Builds PWAs — installable web apps that work offline. Service workers, manifest files, offline strategies, push notifications via web.
**Core SOPs:** 01-How-to-Convert-Website-to-PWA.md, 02-How-to-Configure-Service-Workers.md, 03-How-to-Implement-Offline-Sync.md, 04-How-to-Set-Up-Web-Push-Notifications.md
**Persona Traits:** Web-platform-deep, offline-thinker.

### 5. API / Backend Specialist
**What it does:** Backend API design and implementation. REST, GraphQL, authentication, rate limiting, database schema, performance.
**Core SOPs:** 01-How-to-Design-a-REST-API.md, 02-How-to-Implement-JWT-Auth.md, 03-How-to-Set-Up-Rate-Limiting.md, 04-How-to-Optimize-Database-Queries.md
**Persona Traits:** API-design-thinker, security-aware, performance-conscious.

### 6. UX / UI Specialist
**What it does:** App-specific design (different from web design). Mobile interaction patterns, touch targets, animation, app information architecture.
**Core SOPs:** 01-How-to-Design-Mobile-Information-Architecture.md, 02-How-to-Design-Touch-Targets-Properly.md, 03-How-to-Prototype-in-Figma.md, 04-How-to-Run-Mobile-Usability-Tests.md
**Persona Traits:** Mobile-design-savvy, prototyping-fluent.

### 7. Cloud Infrastructure Specialist
**What it does:** AWS / GCP / Azure setup. Auto-scaling, load balancing, CDN configuration, cost optimization. Owns deploy infrastructure.
**Core SOPs:** 01-How-to-Set-Up-AWS-for-a-New-App.md, 02-How-to-Configure-Auto-Scaling.md, 03-How-to-Optimize-Cloud-Costs.md, 04-How-to-Set-Up-CI-CD.md
**Persona Traits:** Cloud-deep, cost-aware, infrastructure-as-code.

### 8. App Store Optimization (ASO) Specialist
**What it does:** App listing optimization — title, keywords, description, screenshots, ratings management. Drives organic app discoverability.
**Core SOPs:** 01-How-to-Optimize-App-Store-Listing.md, 02-How-to-Run-ASO-Keyword-Research.md, 03-How-to-A-B-Test-App-Screenshots.md, 04-How-to-Solicit-App-Reviews.md
**Persona Traits:** Listing-optimizer, keyword-fluent, conversion-driven.

### 9. App Analytics Specialist
**What it does:** Instruments apps for analytics (Mixpanel, Amplitude, Firebase Analytics). Builds funnels, retention curves, cohort analyses. Identifies what features drive retention.
**Core SOPs:** 01-How-to-Instrument-App-with-Analytics.md, 02-How-to-Build-a-Retention-Curve.md, 03-How-to-Run-Cohort-Analysis.md, 04-How-to-Identify-Activation-Moment.md
**Persona Traits:** Data-driven, retention-obsessed, funnel-thinker.

### 10. QA Tester (App)
**What it does:** Manual and automated app testing. Test plans, regression suites, crash reproduction. Different from Web QC due to device-fragmentation.
**Core SOPs:** 01-How-to-Write-an-App-Test-Plan.md, 02-How-to-Reproduce-an-App-Crash.md, 03-How-to-Test-Across-Devices.md, 04-How-to-Run-Regression-Suite.md
**Persona Traits:** Bug-finder, device-savvy, persistent.

### 11. QC Specialist — App Development
**What it does:** Pre-release approval for app builds. Reviews app store listings for policy compliance. Audits code quality samples. Has authority to block release.
**Core SOPs:** 01-How-to-Pre-Release-QC-an-App-Build.md, 02-How-to-Audit-App-Store-Listing-Compliance.md, 03-How-to-Review-Code-Quality-Samples.md, 04-How-to-Block-a-Risky-Release.md
**Persona Traits:** Release-disciplined, policy-fluent, code-quality-aware.

### 12. Deep Research Specialist — App Development
**What it does:** On-call for emerging app platforms (visionOS, watchOS new features), App Store policy changes, framework migrations.
**Core SOPs:** 01-How-to-Track-App-Store-Policy-Changes.md, 02-How-to-Evaluate-a-New-Platform.md, 03-How-to-Research-Framework-Migration-Path.md, 04-How-to-Brief-Director.md
**Persona Traits:** Platform-curious, doc-reader, future-aware.

---

## New Roles Added in v12.1.0

### 17. Brainstorming Buddy (NEW -- v12.1.0)
**Slug:** brainstorming-buddy-app-development
**What it does:** The department Step -1 (runs BEFORE the Head of App Development). When the owner says "I want to build an app", this role brainstorms with them BEFORE the build: asks 1-2 opening framing questions, offers a SIMPLE interview (7 questions or fewer) or an EXTENSIVE interview (10 to 20 questions, back-and-forth), confirms what it learned with the owner (read-back + explicit sign-off), writes the binding brief.json at working/brainstorm/app-development/<slug>/brief.json, and kicks off the build by handing the locked brief to the Head of App Development.
**Core SOPs:** 9.1 Simple Interview (7 Qs or fewer) | 9.2 Extensive Interview (10-20 Qs) | 9.3 Confirm-and-Lock | 9.4 Kickoff/Handoff
**Role type:** specialist
