# Install Checklist - BlackCEO Voice Call Plugin (Skill 30)

Complete every step in order. Do not skip steps.

---

## Do You Have Your Telnyx and Fish Audio Credentials?

**If YES** - proceed to Step 1 below.

**If NO** - do the following:

1. Run Step 1 and Step 2 (install the plugin and restart)
2. Then run this command to flag setup as pending:

```bash
cat >> ~/.openclaw/skills/.pending-setup.md << 'EOF'

## voice-call-plugin
- Status: PENDING
- What is needed:
  - Telnyx account (sign up at telnyx.com)
  - Telnyx API key
  - Telnyx phone number (purchase one in Mission Control Portal)
  - Telnyx Connection ID (Mission Control Portal → Voice → Connections)
  - Telnyx Public Webhook Key (Mission Control Portal → Auth → Public Keys)
  - Fish Audio account (sign up at fish.audio)
  - Fish Audio API key (fish.audio/app/api-keys)
  - Fish Audio Voice ID (your cloned voice model ID)
  - Public URL for webhooks (VPS domain, ngrok, or Tailscale funnel)
- Resume at: INSTALL.md Step 3
EOF
```

3. The agent will remind you to complete setup once you have your credentials.
4. When ready, come back and start at Step 3.

---

## Before You Start (If Completing Now)

Gather these items before proceeding to Step 3.

- [ ] Telnyx API key
- [ ] Telnyx phone number (purchased in Mission Control Portal)
- [ ] Telnyx Connection ID (from Mission Control Portal → Voice → Connections)
- [ ] Telnyx Public Webhook Key (from Mission Control Portal → Auth)
- [ ] Fish Audio API key (from fish.audio/app/api-keys)
- [ ] Fish Audio Voice ID (from your voice model URL: `fish.audio/app/text-to-speech/?modelId=YOUR_ID`)
- [ ] Public URL for webhooks (your VPS domain, ngrok URL, or Tailscale funnel)

---

## Step 1 - Install the Plugin

Run this command in your terminal:

```bash
openclaw plugins install @openclaw/voice-call
```

You will see warnings about code patterns - this is normal for this plugin. It installs successfully.

---

## Step 2 - Restart the Gateway

**Do NOT skip this step.** The plugin will not load until the gateway restarts.

Type in Telegram:
```
/restart
```

Wait for the gateway to confirm it is back online before continuing.

---

## Step 3 - Add Configuration

Open your OpenClaw config file:
```
~/.openclaw/openclaw.json
```

Under `plugins.entries`, add the voice-call block. See `SKILL.md` for the full config template. Replace all placeholder values with your real credentials.

---

## Step 4 - Restart Gateway Again

```
/restart
```

---

## Step 5 - Test with a Call

Make a test call to verify everything is working:

```bash
openclaw voicecall call --to "+1YOURNUMBER" --message "This is a test call from BlackCEO. The voice call plugin is working correctly."
```

You should receive a phone call within a few seconds. The voice should sound like the Fish Audio voice you configured.

---

## Step 6 - Verify in Logs

Watch the live call log to confirm no errors:

```bash
openclaw voicecall tail
```

---

## Done

If you received the test call with the correct voice, Skill 30 is complete.

**What is now active:**
- AI outbound phone calls via Telnyx
- Fish Audio voice generation on all calls
- Multi-turn conversational call support
- Inbound call handling (if configured)
