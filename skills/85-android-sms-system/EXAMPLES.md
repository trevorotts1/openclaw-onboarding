# Android SMS System - Real Examples

Five worked examples, each answered from a real article in the offline myCRMSIM support set. Every step below is taken from the article named in the **Opened** line; nothing is added from outside it. Paths are absolute on this machine so they can be opened directly.

Docs root: `$HOME/Downloads/openclaw-master-files/mycrmsim`

---

## Example 1: "I installed the SMS app on my Android phone but nothing sends. What did I miss?"

**Opened:** folder `01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Device Setup/`, article **MCS-131 - Setting Up Your Android Device with myCRMSIM SMS Gateway.md**

**Answer:**

The setup order matters, and two steps are the usual culprits:

1. **Disable Play Protect.** Google Play Store > profile icon > Play Protect > turn OFF all Play Protect settings. Keep it off when installing or updating.
2. **Turn off RCS.** Google Messages: profile picture > Messages settings > General > RCS chats > OFF. On Samsung: three-dot menu > Settings > Chat settings or Advanced messaging > Chat features / RCS > OFF. Incoming RCS cannot be received by the gateway app, so SMS must not be routed through RCS.
3. **Download the APK** from `https://get.mysmsgateway.app` in Chrome, then open the downloaded file and tap Install.
4. **Allow ALL permissions** when the app first opens: SMS, Phone, Call logs, Contacts, Background activity, and disable battery optimisation. The app must be allowed to run in the background at all times.
5. **Allow Restricted Settings** (Settings > Apps > myCRMSIM app > three dots > Allow Restricted Settings) and turn **OFF** "Pause app activity if unused".
6. **Log in** by scanning the QR code or entering the token in the app.
7. **Connect the device in the dashboard:** Devices > Android Devices > Add New Device > scan QR code or paste the token > name the device > Save.
8. **Assign a SIM:** Subaccount SIM > find the sub-account > orange (+) in the SIM Card column > set the **Workspace SIM** as the default, and optionally "Assign new SIM" per user. Workspace SIM is the sub-account default; a user SIM overrides it for that user.
9. **Set Message Routing** for the sub-account with SMS selected, then Save.
10. **Set the SMS Gateway app as the Default SMS app** (phone Settings > Default Apps). The article marks this VERY IMPORTANT because it prevents Google Messages / RCS conflicts.
11. **Inside the app:** Keep Alive in Background = ON, Sync Received = ON. On dual SIM, pick the correct SIM for sending.
12. **Test** from the CRM and confirm both send and reply.

If it still fails, the article's own troubleshooting table maps: Play Protect ON > turn OFF; RCS Chat Features > turn OFF; permissions missing > allow ALL; app paused > disable pause setting; not default SMS app > set it; device not assigned > check dashboard. It also says to check device status, battery, connection, permission status and last ping in the dashboard.

**Article path:** `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Device Setup/MCS-131 - Setting Up Your Android Device with myCRMSIM SMS Gateway.md`

---

## Example 2: "My iMessage gateway stopped sending, and the Mac app looks like it won't open."

**Opened:** folder `01-Devices and Installation/01-myCRMSIM iMessage Installation and Setup/`, article **MCS-081 - iMessage Trouble Shooting.md**

**Answer:**

Work the article's steps in order:

1. **Review installation and setup** and confirm the iPhone, iMessage and the iMessage integration were each set up correctly, using the correct conversation providers.
2. **Mac Gateway app will not open because it is already running** — after an update, an existing copy can still be running in the background. Quit the existing myCRMSIM/MySMSGateway copy from the menu bar or Activity Monitor, then open it again. Only one copy runs per macOS user account; separate macOS user accounts may each run their own. If it still will not open, contact support with the macOS version, app version and a screenshot or description.
3. **Verify Apple ID and iMessage login** — log into the Apple ID on the phone and be logged into iMessage with the same Apple ID; check iCloud settings have "Enable Messages in iCloud" on and "Send as Text Message" enabled.
4. **"SMS fallback is off for this device"** — SMS fallback is disabled on the iPhone handling the iMessage/SMS handoff. It is a device-level setting and is **not** fixed by adding or changing a Message Routing row. On the paired iPhone: Settings > Apps > Messages > turn on **Send as Text Message**. Then confirm the correct iPhone line is active, the iPhone has cellular service or supported Wi-Fi Calling, the carrier supports SMS for the line, and the iPhone and connected Mac are online. Retry after the change; SMS may appear as a green bubble and may carry carrier charges.
5. **Send a test message via iMessage.** If messages only send as green bubbles rather than blue, the iMessage setup is wrong per Apple's guidance.
6. **Enable Full Disk Access** for the MySMSGateway iMessage app under System Settings > Privacy.
7. **Check custom provider settings** — the correct custom provider must be selected and configured.
8. **Log out and reconnect** iMessage in the SMS Gateway app: log out, retrieve the authentication code, reconnect the account.
9. If the gateway pauses after inactivity, check power settings so the machine does not sleep.
10. If all of that fails, submit a support ticket with details and a Loom video if possible.

**Article path:** `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM iMessage Installation and Setup/MCS-081 - iMessage Trouble Shooting.md`

---

## Example 3: "WhatsApp restricted my number. What do I do now?"

**Opened:** folder `01-Devices and Installation/01-myCRMSIM WhatsApp Installation and Setup/`, article **MCS-104 - What to Do If Your WhatsApp Number Gets Restricted.md**

**Answer:**

A restriction does not always mean the number is lost, but the article treats it as a warning that the sending pattern has to change.

1. **Stop sending immediately.** Pause all sending activity at once and do not continue campaigns while diagnosing.
2. **Review what likely triggered it.** Look at recent sending patterns: sudden volume increases, repetitive copy, weak contact quality, or messages that generated complaints or low engagement.
3. **Return carefully after the restriction ends.** Do not resume normal activity immediately — restart with a lighter warm-up pattern, use more natural conversations, and rebuild slowly before attempting scale again.
4. **Separate temporary restrictions from permanent loss.** A temporary restriction may be recoverable with a safer process. A fully banned number is much harder to restore, and recovery may be limited to official appeal channels or replacing the number entirely.
5. **Improve the prevention process.** After any restriction, review contact consent, sending pace, personalisation, campaign timing and message quality before using the number again.

The article's settings recap: temporary restriction > stop sending, review the trigger, restart slowly; weak delivery before a restriction > reduce pace and improve contact quality immediately; permanent ban > use official appeal options if available and prepare a safer replacement process. Final note: strong opt-in practices, gradual pacing, relevant content and close monitoring keep a number healthy; document what happened and what changed so the team does not repeat it.

**Article path:** `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM WhatsApp Installation and Setup/MCS-104 - What to Do If Your WhatsApp Number Gets Restricted.md`

---

## Example 4: "How do I connect myCRMSIM to HighLevel, and where do I pick the provider in HighLevel?"

**Opened:** folder `04-Integrations/04-HighLevel Setup/`, article **MCS-042 - myCRMSIM HighLevel Integration Guide.md**

**Answer:**

Prerequisites per the article: an active myCRMSIM account, access to the HighLevel agency or sub-account, and you must be logged in to the **main** HighLevel app, not a white-label domain.

1. **Log in to the myCRMSIM dashboard** — you land on the Dashboard page.
2. **Connect HighLevel** — left sidebar > Integrations > "Connect with Agency" or "Connect with Your Account" (use "Reconnect" if reconnecting). You are redirected to the HighLevel Marketplace App.
3. **Log in to HighLevel** with your credentials, click Sign in, and if prompted complete verification: Send Security Code > enter the OTP sent to your registered email > Verify. The article repeats that using a white-label domain may cause the integration to fail.
4. **Authorize and install the app** — on the Install Confirmation screen review the permissions and click Next, select your agency or location on the Select an Account screen. Agency users: select "Install under all locations in [your agency name]", enable automatic installation to future locations, then Proceed.
5. **Install conversation providers** — select the required providers from Android SMS, WhatsApp, iMessage. They are white-labeled under **My SMS Gateway App**, so clients do not see myCRMSIM branding.
6. **Select the conversation provider in HighLevel** — HighLevel > Settings (bottom-left) > Phone System > Additional Settings tab > Telephony Provider > choose Twilio, LeadConnector, or **mySMS Gateway App - SMS, WhatsApp & Message**, and make sure it is marked **Default**.
7. **Verify** — back in the myCRMSIM dashboard, open Integrations and confirm the HighLevel card shows Connected.
8. **Sync and connect sub-accounts** — left sidebar > Subaccount SIM > Sync Locations > wait for locations > search if needed > turn ON the toggle for the sub-account > Yes, Confirm > wait for the success message > Back to List to verify it shows connected. The article notes that turning on a sub-account in myCRMSIM does not change or override settings in HighLevel.

The integration is then complete and the connected providers can be used inside the HighLevel sub-account.

**Article path:** `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/04-Integrations/04-HighLevel Setup/MCS-042 - myCRMSIM HighLevel Integration Guide.md`

---

## Example 5: "Messages are sitting on Pending or Queued and never go out. What does that mean?"

**Opened:** folder `01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/`, articles **MCS-015 - What Happens If Messages Fail.md** and **MCS-126 - SMS Staying in Pending after updating android OS to latest version.md**

**Answer:**

Per MCS-015, the two statuses mean different things:

- **Pending** = the message has been received from the CRM by the gateway.
- **Queued** = the message has been sent from the gateway to the mobile app on the phone, but has not yet gone out to the recipient.

Messages that show "Pending" in the HighLevel conversation provider may appear as Pending or Queued in the myCRMSIM dashboard, because HighLevel has no "Queued" status to display. If the dashboard shows **"Max Reached - Delete Only"**, the system tried to send the message multiple times and failed, and the message can now only be deleted.

**Why messages queue** (from the article): the SMS Gateway app works sequentially and sends one message at a time, so new messages wait their turn. Specific causes listed:

- **High sending rate** — slow the sending configuration.
- **Device manufacturer limits** — if you get an error about a large number of messages, increase the delay between messages to over 60 seconds.
- **SIM card blocks** — a blocked SIM prevents sending.
- **MMS configuration** — when sending MMS, the SMS Gateway app must be the default messaging app.
- **Insufficient balance** on the phone.
- **Connection failures** — if the app cannot report status to the server, messages queue but should send once the connection returns.
- **Older device issues** — older Oppo or Realme models may prompt for confirmation on every message; newer devices are recommended.

**How to clear the queue:** either wait and let the app keep sending (new messages are not processed until the current queue clears), or delete the queued messages manually — the article warns that deleting permanently removes them from the sending pipeline.

For the specific case of messages staying Pending **after an Android OS update**, MCS-126 gives the correct update procedure because the app is distributed outside the Play Store: delete the old device from the dashboard (Devices > remove; it reconnects after the new install), turn off Play Protect (Scan apps with Play Protect and Improve harmful app detection — note Play Protect will refuse to disable during a call or meeting; restart the phone if it turns back on), install the new APK (allowing "Install unknown apps" if prompted), allow ALL in-app permissions, then grant the remaining permissions from Android settings including Battery > Unrestricted / Allow background activity and Auto Start. Once permissions are fully granted the app generates a new Firebase token, registers the device and connects to the dashboard with no extra action.

**Article paths:**
- `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/MCS-015 - What Happens If Messages Fail.md`
- `$HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/MCS-126 - SMS Staying in Pending after updating android OS to latest version.md`
