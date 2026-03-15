# Telnyx Configuration Reference

## Where to Find Your Credentials

### API Key
1. Log into Telnyx Mission Control Portal: portal.telnyx.com
2. Go to Auth → API Keys
3. Create a new key or copy your existing one

### Connection ID
1. Go to Voice → Connections
2. Create a new connection or use existing
3. Copy the Connection ID (starts with a long number)

### Public Webhook Key
1. Go to Auth → Public Keys
2. Copy the key labeled for webhook verification

### Phone Number
1. Go to Numbers → Search & Buy
2. Purchase a US local number (starts at ~$1/month)
3. Assign it to your connection

---

## Webhook Setup in Telnyx

Your OpenClaw gateway needs to be reachable from the internet to receive call events.

### Option A - VPS (Production)
Use your VPS domain:
```
publicUrl: "https://yourdomain.com/voice/webhook"
```

### Option B - Ngrok (Testing)
```bash
ngrok http 3334
```
Copy the https URL and set:
```
publicUrl: "https://abc123.ngrok.app/voice/webhook"
```
Note: Free ngrok URLs change every restart.

### Option C - Tailscale Funnel
```bash
openclaw voicecall expose --mode funnel
```

---

## Telnyx Pricing (US)

| Service | Cost |
|---------|------|
| Outbound calls | $0.002/min |
| Inbound calls | $0.002/min |
| Local phone number | ~$1.00/month |
| SMS/MMS capability | $0.10/month per number |
| Outbound SMS | ~$0.004-0.008/msg |
| Outbound MMS | ~$0.0079/msg |

Automatic volume discounts apply as usage grows.

---

## Concurrent Call Limits

Telnyx scales based on your account tier and usage. Contact Telnyx support or your account rep for custom concurrent call limits if you need more than the default.

---

## Support

- Telnyx support: Available 24/7 via chat and phone in Mission Control Portal
- Docs: developers.telnyx.com
