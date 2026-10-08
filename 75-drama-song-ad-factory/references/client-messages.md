# Client messages for every stop — reason code to plain English

Status: reference table, both distributions (Skill 75 / 999 twin) — manual 02 B8.
Source files for every code: `scripts/core/kie_dispatch/kie_dispatch.py`,
`scripts/core/intake_preflight/preflight.py`,
`scripts/core/retake_manager/retake_manager.py`.

**Rule:** always show the client the sentence below, never the code. The code
is for logs and receipts only. $X means the actual dollar shortfall from the
envelope; fill it in before sending.

| reason_code | Client sentence |
|---|---|
| `preflight-shortfall` | Your KIE balance is short by $X for this video. Top up at kie.ai and say go. |
| `REPAIR_CAP_EXHAUSTED` | One shot failed its check twice. I have paused the ad so you are not charged more. Here is what failed. |
| `approval-missing` | Please approve the card above so I can start. |
| `preflight-pass` | Everything checked out, so I am starting your video now. |
| `KIE_DISPATCH_OK` | Good news — your video is done and saved. I am sending it over now. |
| `MODEL_REQUIRED` | I need to know which video style to use before I can start. Please pick one from the card. |
| `UNKNOWN_PRICE` | I do not have the price for this video yet, so I stopped before spending anything. Tell me to continue once the price is set. |
| `adapter-not-found` | The payment tool for video generation is not installed yet, so I stopped before spending anything. |
| `adapter-health-unreadable` | The video generation tool is not answering, so I stopped before spending anything. Give it a minute and say go again. |
| `adapter-mode-unknown` | The video generation tool is in a state I do not recognize, so I stopped before spending anything. |
| `generation-not-switched-on` | Video generation is not switched on for your account yet — nothing was made and nothing was charged. Say go once it is switched on. |
| `preflight-unreadable` | The last balance check before your video came back garbled, so I stopped to be safe. Nothing was charged. |
| `preflight-failed` | A pre-spending check on your account failed, so I stopped before spending anything. Nothing was charged. |
| `prompt-budget-unreadable` | The script length check came back garbled, so I stopped to be safe. Nothing was charged. |
| `prompt-over-max` | The script for this video is too long, so I stopped before spending anything. I will trim the script and show it to you for approval. |
| `prompt-below-floor` | The script for this video is too short to make a good ad, so I stopped before spending anything. |
| `prompt-budget-failed` | The script failed its length rules, so I stopped before spending anything. I will fix the script and show you. |
| `generation-skipped-not-generated` | The video generation tool skipped this job, so nothing was made and nothing was charged. |
| `kie-submit-failed` | The video generator refused this job before starting, so nothing was made and nothing was charged. Here is what it said. |
| `kie-run-failed` | The video generator stopped partway through. I have paused everything so you are not charged more, and here is what went wrong. |
| `unknown-outcome-no-retry` | The video generator stopped answering before it confirmed the result. I have paused everything rather than guess or pay again — I am checking with the provider before doing anything more. |
| `ledger-settle-failed` | Your video finished, but the accounting step hit a snag. Hold on while I double-check nothing gets charged twice. |
| `dispatch-internal-error` | Something inside my system hiccupped, so I stopped before spending anything. Nothing was charged. |
| `schema-untrusted` | This video request uses a form I do not recognize, so I stopped for safety. Please resend it in the standard form. |
| `delivery-profile-unknown` | The video shape or length you picked is not one of the offered options. Please choose one from the list and we can start. |
| `reference-outside-approved-storage` | Some of the pictures or files for this video are outside the approved folders, so I paused. Please move them into the project folder. |
| `reference-missing-or-truncated` | One or more of the pictures or files for this video came up missing or damaged, so I paused. Please resend them. |
| `tool-unavailable` | A tool needed to make your video is not installed on this machine, so I paused. It needs to be set up first. |
| `module-unavailable` | A piece of the video software is missing on this machine, so I paused. It needs to be set up first. |
| `storage-not-writable` | The project folder will not accept new files right now, so I paused. Once it is fixed, say go. |
| `disk-limit` | Your machine is low on storage, so I paused to protect your files. Please free up some space and say go. |
| `credential-missing` | I am missing the sign-in needed to start, so I paused. Please add it and say go. |
| `approval-expired` | Your approval has timed out, so I paused. Please approve again and I will start. |
| `approval-out-of-scope` | Your approval does not cover this exact video, so I paused. Please approve this one and I will start. |
| `ACCEPTED_ARTIFACT` | This shot already passed its check, so I am not redoing it — your approved version stays as is. |
| `INVALID_REQUEST` | The instructions for this step came through garbled, so I paused. I am re-preparing them before trying again. |
| `PROFILE_UNAVAILABLE` | The quality-rule file is missing or unreadable, so I stopped before spending anything. It must be published before work starts. |
| `UNKNOWN_ARTIFACT` | The shot name in this request does not match any real shot, so I paused. Please check the shot list. |