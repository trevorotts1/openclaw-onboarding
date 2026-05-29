# Cloudflare & GoDaddy Setup Guide

## SCHOOL OF AI

Everything you need to do BEFORE your AI agent sets up your OpenClaw tunnel

> **Where this lives:** This guide is shipped INSIDE skill 38 (`references/cloudflare-godaddy-setup-guide.md`). When a client's install hits the missing-Cloudflare-API-token halt in `scripts/00-verify-prerequisites.sh` (Rule 13 of QC-PROTOCOL.md), the agent points the client at THIS document — locally, no external link required. The Google Doc credentials reference remains the canonical source for any updates Christy makes; this in-skill copy is the embedded fallback so the install can walk a client through the entire flow without leaving the skill.

You'll do four things in this guide:

1. Create a free Cloudflare account
2. Connect your domain (from GoDaddy) to Cloudflare
3. Update your domain's nameservers at GoDaddy
4. Create your Cloudflare API token for your AI agent

**Estimated time:** 25–40 minutes
**You will need:** Your GoDaddy login, your email address, and a quiet 30 minutes

---

## Before You Start

This guide walks you through everything you need to set up before your AI agent can build your OpenClaw tunnel for you.

Take it slow. Each step has clear instructions. If you get stuck, you can pause anywhere — your progress saves automatically at each website.

**What you'll need open in your browser:**

- Your GoDaddy account (to manage your domain)
- A web browser (Google Chrome works best)
- Your email inbox (for the Cloudflare confirmation email)
- A safe place to write things down (or your password manager)

> **ℹ️ NOTE** When you see something that looks like this, that's the exact text or button name on the website. Match it exactly. Capital letters and small letters matter.

> **⚠️ PAY ATTENTION** You'll create some passwords, tokens, and codes during this setup. Write them ALL down — or save them in your password manager. You'll need to give some of these to your AI agent later.

---

## PART 1: Create Your Free Cloudflare Account

Cloudflare is the company that helps your AI agent connect to your computer safely. The free account gives you everything you need.

### Sign up — step by step

**Step 1**
Open your web browser. Go to this exact website address:

```
https://dash.cloudflare.com/sign-up
```

(Type that into the address bar at the very top of your browser — the bar that usually says "Search Google or type a URL.")

**Step 2**
You'll see a page with the Cloudflare logo and a form. Fill in:

- **Email** — your real email address (you'll need to verify it)
- **Password** — pick a strong one and write it down NOW

Then click the big blue button that says **Sign Up**.

**Step 3**
Cloudflare will send you a confirmation email. Switch over to your email inbox, open the message from Cloudflare, and click the verification link inside it.

**Step 4**
After clicking the link, you'll land back on the Cloudflare website. You may see a screen asking you to pick a plan or add a site. Don't pick anything yet — just close that screen or click **Skip for now** if you see that option. We'll add your domain in Part 2.

**✓ SUCCESS — You are done with Part 1 when:**

- You see the Cloudflare dashboard (the main screen after you log in)
- Your email is verified
- You wrote down your Cloudflare email + password somewhere safe

---

## PART 2: Add Your GoDaddy Domain to Cloudflare

Your domain (like yourname.com) lives at GoDaddy right now. To use it with your AI agent, we have to tell Cloudflare it exists, then tell GoDaddy to send your traffic through Cloudflare.

We do this in two halves: first the Cloudflare half (Part 2), then the GoDaddy half (Part 3). You will switch back and forth between two browser tabs — keep them both open.

### Add the domain on Cloudflare

**Step 1**
Make sure you're on the Cloudflare dashboard. If you closed the tab, go to:

```
https://dash.cloudflare.com
```

and log in with the email and password from Part 1.

**Step 2**
Look in the middle of the screen for a button that says **Add a domain**, or **+ Add site**. Click it.

**Step 3**
Type your domain name in the box. Type only the main part — no www, no https, just the name and the ending.

- ✅ Correct: `yourname.com`
- ✗ Wrong: `www.yourname.com`
- ✗ Wrong: `https://yourname.com`

Then click **Continue**.

**Step 4**
On the next screen, Cloudflare asks you to pick a plan. Scroll down and click the **Free** plan (the cheapest one — it costs $0). Then click **Continue**.

**Step 5**
Cloudflare will now scan your domain. This takes 30 seconds to a minute. You may see a list of "DNS records" appear — these are settings from your current domain. Don't change anything here. Just click **Continue** at the bottom.

**Step 6**
Cloudflare will now show you something very important: two name servers. They look something like this:

```
andy.ns.cloudflare.com
jane.ns.cloudflare.com
```

(Your actual names will be different — those are just examples.)

Write both of these name servers down EXACTLY — every letter, every dot. Or take a screenshot. You'll need them in Part 3.

> **⚠️ PAY ATTENTION** Don't close this Cloudflare tab yet. Leave it open. You'll come back to it after Part 3.

**✓ SUCCESS — You are done with Part 2 when:**

- Your domain is added to Cloudflare
- You picked the Free plan
- You wrote down your two Cloudflare name servers exactly

---

## PART 3: Update Your Nameservers at GoDaddy

Now we tell GoDaddy: "Send my domain's traffic through Cloudflare from now on." This is the most important step. Take your time.

### Get to your domain's settings at GoDaddy

**Step 1**
Open a new browser tab (don't close Cloudflare). Go to:

```
https://www.godaddy.com
```

Log in with your GoDaddy username and password.

**Step 2**
After logging in, look at the top-right corner of the screen. You'll see your name or a little person icon. Click on it — a menu will drop down.

**Step 3**
In that drop-down menu, click **My Products**.

**Step 4**
You'll land on a page that shows everything you own at GoDaddy. Scroll until you see the section labeled **Domains** (or **All Products and Services → Domains**).

Find the domain you added to Cloudflare in Part 2.

**Step 5**
Click on that domain name. You'll land on its settings page.

Scroll down the page until you see a section called **DNS** (sometimes it says **Manage DNS** or **DNS Management**).

**Step 6**
Click the **DNS** button or link. This opens your domain's DNS settings page — where the nameservers live.

### Change the nameservers

**Step 7**
On the DNS page, scroll down until you find a section called **Nameservers** (it's usually below the main DNS records).

You'll see your current nameservers — they probably end with `domaincontrol.com`. Right next to them is a button that says **Change** or **Edit**. Click it.

**Step 8**
GoDaddy will ask: "What kind of nameservers do you want?"

Choose the option that says **I'll use my own nameservers** (or **Custom**, depending on which screen GoDaddy shows you).

**Step 9**
Two empty boxes will appear. Now type — very carefully — the two Cloudflare nameservers you wrote down in Part 2.

- **Nameserver 1:** type the first Cloudflare name
- **Nameserver 2:** type the second Cloudflare name

Match every letter and every dot exactly. No spaces before, no spaces after. No extra periods at the end.

**Step 10**
Click **Save**. GoDaddy may ask you to confirm — say yes.

You may see a warning that says something like "this could interrupt your services." Click confirm anyway — that's expected.

### Back to Cloudflare — tell it you're done

**Step 11**
Switch back to the Cloudflare browser tab (the one you left open).

Scroll to the bottom of the page. There's a button that says **Done, check nameservers** (or similar). Click it.

**Step 12**
Cloudflare will check your nameservers. This can take anywhere from 5 minutes to several hours — but usually it's done within 30 minutes. You can close the page; Cloudflare will send you an email when it's ready.

> **ℹ️ NOTE** Your domain is now "on Cloudflare." You don't have to wait at your computer. Cloudflare will email you when activation is complete. You can come back later and do Part 4.

**✓ SUCCESS — You are done with Part 3 when:**

- GoDaddy is showing your two Cloudflare nameservers
- You clicked "Done, check nameservers" on Cloudflare
- You're waiting for Cloudflare's confirmation email (or you've already received it)

---

## PART 4: Create Your Cloudflare API Token

An API token is a special password you give to your AI agent so it can set up your tunnel for you. We're going to create one with the exact permissions it needs — no more, no less.

> **⚠️ PAY ATTENTION** Wait for the Cloudflare email first. The email subject is something like "your domain is now active on Cloudflare." If you haven't received it yet, give it a few more minutes or check the spam folder.

### Get to the API tokens page

**Step 1**
Open your browser. Go to this exact address:

```
https://dash.cloudflare.com/profile/api-tokens
```

(Log in if Cloudflare asks you to.)

**Step 2**
You'll see a page titled **API Tokens**. Click the orange button in the middle that says **Create Token**.

**Step 3**
Cloudflare will show you a list of templates. Scroll all the way to the bottom. The very last option is called **"Create Custom Token"**. Click the **Get started** button next to it.

Do not use the templates above — they give too much or too little permission.

### Fill in the token settings

**Step 4**
**Token name:** Type a name you'll recognize, like:

```
OpenClaw Tunnel Setup
```

(This is just a label so you know what this token is for later. It doesn't affect anything technical.)

### Add permissions (this is the important part)

You'll see a section called **Permissions**. Each permission has three drop-down menus. Click **+ Add more** after each one to add another row. Set them up exactly like the table below.

| Drop-down 1 (Type) | Drop-down 2 (Permission) | Drop-down 3 (Access) |
| --- | --- | --- |
| Account | Cloudflare Tunnel | Edit |
| Account | Zero Trust | Edit |
| Account | Access: Apps and Policies | Edit |
| Account | Access: Service Tokens | Edit |
| Account | Access: Organizations, Identity Providers, and Groups | Edit |
| Account | Access: SSH Auditing | Edit |
| Account | Account Settings | Read |
| Zone | DNS | Edit |
| Zone | Zone | Read |

> **⚠️ PAY ATTENTION** After adding all 9 permission rows above, double-check each one. If one is missing or set wrong, your AI agent will get blocked partway through the setup.

### Set the account and zone resources

**Step 5**
Below permissions you'll see **Account Resources**. The drop-downs should be set to:

- First drop-down: **Include**
- Second drop-down: pick your account name

Then below that, find **Zone Resources**. Set:

- First drop-down: **Include**
- Second drop-down: **All zones from an account**
- Third drop-down: pick your account name again

**Step 6**
Scroll to the bottom. Skip the optional sections for "Client IP Address Filtering" and "TTL" (we don't need those).

Click the blue button at the very bottom that says **Continue to summary**.

**Step 7**
Cloudflare shows you a summary of everything you picked. Look it over. If anything is wrong, click **Back** and fix it.

When everything matches the table above, click **Create Token**.

**Step 8**
**STOP and READ THIS CAREFULLY.**

Cloudflare will now show you your token — a long string of random letters and numbers. It looks like this:

```
abc123XYZ_4F5g6H7iJ8kLmNop-qRsTuVwXyZ_123abc
```

This is the ONLY time you will ever see this token. If you close this page without copying it, you'll have to delete the token and create a new one from scratch.

Click the **Copy** button right next to the token, then paste it somewhere safe — your password manager is best. A sticky note on the fridge is fine for now if you have to.

**✓ SUCCESS — You are done with Part 4 when:**

- Your token is created
- You copied it and saved it somewhere safe
- You can still see it on screen until you click away

---

## All Done. What's Next?

Congratulations. You have everything your AI agent needs to set up your OpenClaw tunnel.

### Final checklist

Before you hand things over to your agent, make sure you have:

- [ ] Cloudflare email + password (from Part 1)
- [ ] Your domain is active on Cloudflare (check your email for the activation message)
- [ ] Your Cloudflare API token (the long code from Part 4)
- [ ] The exact domain name you added to Cloudflare (e.g. `yourname.com`)

### Hand it off to your AI agent

Open your AI agent (the one your School of AI coach set up for you). Tell it you're ready to set up your OpenClaw tunnel. Your agent will ask for three things:

- Your **Cloudflare API token** — paste it in when asked
- A **subdomain name** for your OpenClaw — for example `claw.yourname.com`
- A short **label** like `ghl-inbound` — or just keep what your agent suggests

The agent saves your token to its secrets file (at `~/.openclaw/.env` on a Mac or the equivalent on a VPS) under the variable name `CLOUDFLARE_API_TOKEN`. From that moment on, your agent has everything it needs to create your tunnel, your DNS record, your Cloudflare Access policy, and the rest of the OpenClaw setup automatically.

> **ℹ️ NOTE** If you get stuck at ANY point during setup, take a screenshot of where you're stuck and send it to your School of AI coach. Don't guess. It's faster to ask than to undo a mistake.

---

## SCHOOL OF AI

Helping you put AI to work — one careful step at a time.

---

## Operator notes (for the AI agent running skill 38, not the client)

Per the OpenClaw QC-PROTOCOL.md (Part 3 Rule 13), when `scripts/00-verify-prerequisites.sh` cannot find a Cloudflare API token in any of the 10 documented locations, the agent halts and points the client at THIS document. The four parts of this guide map to the install flow:

- Parts 1-3 (account + domain + nameservers) prepare Cloudflare to manage the client's domain. Skill 38's Phase 1 (per `references/v6.0-source-playbook.md` Steps 1-2) then creates the Cloudflare Tunnel via API and installs `cloudflared` as a persistent system service. Without the Cloudflare account + active domain, that Phase will fail.
- Part 4 (API token creation) produces the credential the agent reads from `~/.openclaw/.env` as `CLOUDFLARE_API_TOKEN`. The 9 permission rows map 1-to-1 to what the v5.14 playbook actually calls into:
  - **Cloudflare Tunnel Edit** — create + configure the tunnel (Step 1)
  - **Zero Trust Edit** — for the broader Access integration
  - **Access: Apps and Policies Edit** — to wrap the tunnel's public hostname in an Access app (Command Center login, etc.)
  - **Access: Service Tokens Edit** — to mint service tokens for fleet operator access (used by `08-shopify-setup-wizard.sh` and operator-side scripts when applicable)
  - **Access: Organizations, Identity Providers, and Groups Edit** — to add Google SSO or email-OTP IdP to the Access app
  - **Access: SSH Auditing Edit** — for the SSH-over-tunnel pattern (per `references/cloudflare-tunnel-troubleshooting.md`)
  - **Account Settings Read** — to read account id for API calls that scope by account
  - **DNS Edit** (Zone) — to create the proxied CNAME pointing at `<tunnel-id>.cfargotunnel.com`
  - **Zone Read** — to resolve the zone id for DNS calls

Once the client completes all four parts and pastes the token into `~/.openclaw/.env` (or the equivalent), the agent re-runs `00-verify-prerequisites.sh` per QC-PROTOCOL.md Rule 14 (restart flow). The check passes Step A and falls through to Steps B-E (skill presence, skill 10 version, skill 19 / 29 functional checks).
