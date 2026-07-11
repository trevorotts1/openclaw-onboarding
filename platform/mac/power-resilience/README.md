# Mac power-outage resilience

**A fleet audit measured 0 of 11 client Macs surviving a power outage.**
That is not eleven accidents. It is one provisioning-template defect, shipped
eleven times.

This directory is the fix.

---

## The measurement that started it

One client box sat **powered on, networked, both tunnels green — with its
gateway DEAD for 3 days 14 hours.**

- Boot: Jul 7, 17:19
- First console login: Jul 11, 07:20
- Gateway `runs = 1`

It started **the exact second a human logged in.** Every Mac in the fleet is
provisioned the same way.

---

## The three defects

### 1. Every self-healing mechanism is downstream of a human login

The gateway is a **user LaunchAgent** in the `gui/<uid>` domain on 100% of
boxes. There is **not one gateway LaunchDaemon anywhere in the fleet.**

`RunAtLoad=true` and `KeepAlive=true` are set correctly everywhere — **and that
is a red herring.** A LaunchAgent cannot run until a console login *creates* the
`gui/<uid>` domain. **A perfect LaunchAgent at a login window is a dead
process.**

Same defect on **pm2 resurrect** (a LaunchAgent everywhere, under **three**
hand-rolled names — `com.<user>.pm2-resurrect`, `pm2.<user>.plist`,
`io.pm2.launch.plist` = template drift) and on the **Command Center tunnel**
(a LaunchAgent everywhere).

### 2. `pmset` was never touched by the provisioner

`autorestart` sat at the macOS default of **0** on 5 boxes. Mains returns → the
Mac just stays off. The 5 boxes that had it set got it by hand, inconsistently.

### 3. FileVault ON with no auto-login on 7 of 11 boxes — and it breaks the obvious fix

🔴 On Apple Silicon, `/Library` and `/Users` are **firmlinks onto the encrypted
Data volume.** With FileVault ON, a Mac that loses power halts at the **PRE-BOOT
unlock screen.** macOS **never finishes booting**.

**LaunchDaemons do not run either. `sshd` does not run.
"SSH rescue will save us" is FALSE.**

Six boxes already have correctly-built root `cloudflared` LaunchDaemons with
`RunAtLoad=true` and **would still be 100% dark after a power cut.**

---

## THE DECISION: checked LaunchAgent + auto-login — not a blind LaunchDaemon

The tempting fix is "convert the gateway to a LaunchDaemon so it runs at boot
with no login." **We measured before choosing.**

### Evidence that a LaunchDaemon is technically *possible*

| Finding | Source |
|---|---|
| Gateway env is injected by an explicit wrapper + env file under `~/.openclaw/service-env/` — it does **not** inherit the GUI session's environment | the shipped `ai.openclaw.gateway.plist` `ProgramArguments` |
| `ProgramArguments` uses an **absolute** node path — no `PATH` inheritance needed | same |
| The plist carries **no `LimitLoadToSessionType`** key — launchd is not restricting the job to an Aqua session | same |
| Secrets live in `~/.openclaw/secrets/.env` (a **file**). **No Keychain refs.** A daemon has no login keychain; had secrets been in the Keychain this would have been fatal | `~/.openclaw/secrets/.env` |
| `browser.headless = true` — Chrome runs **headless**, which needs **no WindowServer**. The biggest suspected GUI dependency is not one | `openclaw.json` |

### Evidence *against* converting

| Finding | Why it matters |
|---|---|
| The plist carries `ProcessType = Interactive` | upstream deliberately classifies this as a user-interactive job |
| `imessage` + `bluebubbles` are **enabled** on real boxes | iMessage reads `~/Library/Messages/chat.db`, which is **TCC-protected** (Full Disk Access). TCC consent is granted to a binary in the **logged-in user's** TCC database and **cannot be prompted for from the system domain.** A daemon **silently breaks iMessage.** |
| `talk-voice`, `canvas`, `phone-control` are in `plugins.allow` **fleet-wide** | any client can enable them. They genuinely need an Aqua session (audio output routing, screen capture, Accessibility events) |
| 🔴 **The gateway plist is OWNED and REWRITTEN by the upstream `openclaw` CLI** (`openclaw gateway install`) | **this repo does not own that file.** A hand-converted LaunchDaemon is **clobbered on the next `openclaw update`**, and you end up running **both**, fighting over port 18789. A fix that silently un-fixes itself is worse than no fix. |

### The decisive argument

> **A LaunchDaemon does not fix the 7 FileVault boxes at all.**

With FileVault ON on Apple Silicon, the machine never reaches the point where
launchd starts system daemons. The daemon conversion buys **literally nothing**
on the majority of the broken fleet — while costing GUI capability and fighting
the upstream CLI for ownership of the plist.

**Auto-login, by contrast, makes the GUI session EXIST at boot.** It fixes
**100% of the login-gated services at once** — gateway, pm2 resurrect, the
Command Center tunnel, the self-heal remediator — with **zero divergence** from
the upstream-managed plist, and with full GUI capability retained.

**Auto-login strictly dominates the daemon conversion**, provided FileVault is
off — which is *already required* for any unattended recovery at all.

### Therefore

- **PRIMARY PATH** — LaunchAgent + **auto-login as a CHECKED PRECONDITION**.
  The provisioner **FAILS LOUD** (exit `78`, `EX_CONFIG`) if it is about to lay
  a login-gated service onto a box that never logs in.
- **FALLBACK PATH** — an explicit, **opt-in**, capability-gated LaunchDaemon
  (`pr_render_gateway_daemon_plist`) for a genuinely headless box that enables
  **no** session-coupled plugin. Guarded by `pr_gateway_can_be_daemon`.
  Never automatic.
- **Tunnels** — these have **zero** GUI dependency, so they *are* converted to
  root LaunchDaemons unconditionally. A tunnel should never have been an agent.

### The trade-off, stated plainly

| | Unattended recovery | Disk encrypted at rest |
|---|---|---|
| **FileVault OFF + auto-login** | ✅ box returns from a power cut with **no human present** | ❌ anyone with physical access to a powered-on box lands on an unlocked desktop |
| **FileVault ON** | ❌ **impossible** — a person with the disk password must be **physically on site** after **every** power loss | ✅ |

**Pick one. There is no configuration that gives you both.** The gate says so
out loud in its failure message, and refuses to guess on the client's behalf.

---

## Files

| File | What it does |
|---|---|
| `lib-power-resilience.sh` | Sourceable library. The gate, pmset policy, cloudflared resolution, token-file migration, pm2 canonicalization, session-coupling probe, acceptance gate. Every system call is behind an injectable seam so it is testable offline with no root. |
| `../bootstrap.sh` §5 | Wires the gate into the Mac provisioner as a **hard pre-flight**. Exits `78` rather than shipping another undead Mac. |
| `../../../scripts/fix-power-resilience.sh` | **Fleet remediation** for boxes that are already broken. Idempotent. Dry-run by default. **Refuses** on a FileVault-ON box and prints exactly what a human must do on site. |
| `../../../tests/unit/power-resilience-gate.test.sh` | 49 assertions. Proves the gate **fails closed**. |

## Usage

```bash
# Remediate an existing box (DRY-RUN — shows what it would change)
bash scripts/fix-power-resilience.sh <box>

# Actually apply it
bash scripts/fix-power-resilience.sh <box> --apply

# This box
bash scripts/fix-power-resilience.sh --local --apply
```

## What software cannot fix

**FileVault.** Turning it off requires the disk password and a human at the
keyboard. `autoLoginUser` alone is *also* not enough — macOS needs
`/etc/kcpassword`, which **only** System Settings → Users & Groups can create.

The remediation script sets what it can, and **says out loud** what it cannot.
It never claims a box is resilient when it is not. **That claim is the bug that
shipped 11 undead Macs.**

## The only proof that counts

Pull the power cord. Plug it back in. Walk away.

If the box does not come back on its own, it is not fixed — no matter what any
script printed.
