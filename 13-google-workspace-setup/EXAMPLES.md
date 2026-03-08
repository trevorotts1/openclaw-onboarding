# Google Workspace Setup - Examples

Real examples showing the Google Workspace setup in action, from the setup process itself to day-to-day usage.

---

## Example 1: Telling Your AI to Set Everything Up For You

Instead of doing all the manual steps yourself, you can copy and paste this prompt to your AI and let it guide you:

**What you type:**

```
Set up Google Workspace integration for me. I need you to:

1. Help me create a GCP (Google Cloud Platform) project
2. Enable the necessary APIs (Gmail, Calendar, Drive, Docs, Sheets)
3. Create a service account with domain-wide delegation
4. Generate and download the service account JSON key
5. Configure OpenClaw to use the service account
6. Test the connection

Walk me through each step. Ask me for any information you need.
My Google Workspace email is: trevor@blackceo.com
```

**What your AI does:**

Your AI will walk you through each step one at a time, telling you exactly what to click and where. It will ask you to confirm when each step is done before moving to the next one. If you get stuck, it will help you troubleshoot.

---

## Example 2: Checking If Setup Worked (Gmail Test)

**What you type:**

```
Check my Gmail for unread messages
```

**What you see if it WORKED:**

```
You have 3 unread messages:

1. From: sarah@company.com
   Subject: "Q3 Budget Review"
   Received: Today at 2:15 PM

2. From: newsletter@industry.com
   Subject: "Weekly Industry Update"
   Received: Today at 10:00 AM

3. From: john@vendor.com
   Subject: "Invoice #1234"
   Received: Yesterday at 4:30 PM
```

**What you see if it DID NOT work:**

```
Error: 401 Unauthorized - Could not access Gmail.
```

If you see this error, check:
- Is the OAuth Consent Screen configured? (INSTALL.md Step 3)
- Is Domain-Wide Delegation authorized? (INSTALL.md Step 7)
- Did you enable the Gmail API? (INSTALL.md Step 2)

---

## Example 3: Checking If Setup Worked (Calendar Test)

**What you type:**

```
What is on my calendar today?
```

**What you see if it WORKED:**

```
You have 2 events today:

1. Team Standup
   Time: 9:00 AM - 9:30 AM
   Location: Zoom (link attached)

2. Client Call with Pam Perry
   Time: 2:00 PM - 3:00 PM
   Location: Google Meet
```

**What you see if it DID NOT work:**

```
Error: 403 Forbidden - Insufficient permission for Calendar.
```

If you see this error, the calendar scope may not be in your Domain-Wide Delegation. Go back to INSTALL.md Step 7 Part B and make sure the scope list includes `https://www.googleapis.com/auth/calendar`.

---

## Example 4: Searching Google Drive

**What you type:**

```
Search my Google Drive for anything about "quarterly report"
```

**What you see if it WORKED:**

```
Found 4 files matching "quarterly report":

1. Q3 Quarterly Report - Final.docx (Google Doc)
   Last modified: February 15, 2026

2. Quarterly Report Template.xlsx (Google Sheet)
   Last modified: January 10, 2026

3. Q2 Quarterly Report.pdf (PDF file)
   Last modified: July 5, 2025

4. Quarterly Report Images (Folder)
   Contains 12 items
```

---

## Example 5: Sending an Email

**What you type:**

```
Send an email to sarah@company.com with the subject "Meeting Reschedule" and say:
Hi Sarah, I need to move our meeting from Tuesday to Wednesday at the same time. Does that work for you? Thanks, Trevor
```

**What your AI does:**

```
Email sent successfully!

To: sarah@company.com
Subject: Meeting Reschedule
Body: Hi Sarah, I need to move our meeting from Tuesday to Wednesday
at the same time. Does that work for you? Thanks, Trevor

Message ID: 19c7b789ef2d56f0
```

---

## Example 6: Creating a Calendar Event

**What you type:**

```
Create a calendar event called "Strategy Session" for next Monday from 10 AM to 11:30 AM
```

**What your AI does:**

```
Calendar event created!

Title: Strategy Session
Date: Monday, March 10, 2026
Time: 10:00 AM - 11:30 AM
Calendar: Primary

Link: https://calendar.google.com/event?eid=abc123...
```

---

## Example 7: Checking Environment Variables

If something is not working and you want to check your setup, open Terminal and run these commands:

**What you type in Terminal:**

```bash
echo $GCP_PROJECT_ID
echo $GCP_SERVICE_ACCOUNT_EMAIL
echo $GCP_IMPERSONATE_USER
```

**What you should see:**

```
openclaw-ai-123456
OpenClaw-assistant@openclaw-ai-123456.iam.gserviceaccount.com
trevor@blackceo.com
```

If any of these come back blank, the environment variable is not set. Go back to INSTALL.md Step 8 and add it to your ~/.zshrc file.

---

## Example 8: Verifying API is Enabled

If a specific service is not working (for example, Sheets), check that the API is enabled:

1. Go to: https://console.cloud.google.com/apis/dashboard
2. Look in the list of enabled APIs
3. If "Google Sheets API" is not in the list, go to the API Library and enable it (see INSTALL.md Step 2)

**What the enabled APIs page looks like:**

You will see a list showing:
- Gmail API - Enabled
- Google Calendar API - Enabled
- Google Drive API - Enabled
- Google Docs API - Enabled
- Google Sheets API - Enabled
- People API - Enabled

If any of these are missing, click on the API Library link and enable the missing ones.

---

## Example 9: Revoking Access in an Emergency

If you think your JSON key file has been compromised (someone else got a copy of it):

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click on your service account email
3. Click the "Keys" tab
4. Find the key and click the trash icon to delete it
5. This immediately stops anyone from using that key

Then create a new key (INSTALL.md Step 5) and update your secrets folder with the new file.

---

## Example 10: Quick Setup Checklist

Use this checklist to verify your setup is complete:

```
[ ] Google Cloud Project created
[ ] Gmail API enabled
[ ] Calendar API enabled
[ ] Drive API enabled
[ ] Docs API enabled
[ ] Sheets API enabled
[ ] People API enabled
[ ] OAuth Consent Screen configured (Internal)
[ ] Service Account created
[ ] JSON Key downloaded and saved to ~/clawd/secrets/
[ ] Client ID copied (the long number)
[ ] Domain-Wide Delegation enabled in Cloud Console
[ ] Domain-Wide Delegation authorized in Admin Console with scopes
[ ] Environment variables set (GCP_PROJECT_ID, GCP_SERVICE_ACCOUNT_EMAIL, GCP_IMPERSONATE_USER)
[ ] Test: "Check my Gmail" returns real results
[ ] Test: "What is on my calendar today?" returns real results
```

If all boxes are checked, your Google Workspace setup is complete!
