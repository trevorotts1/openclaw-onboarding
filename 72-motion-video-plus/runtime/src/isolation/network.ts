// Render-time network restriction (Directive MG-029).
//
// Mechanism on this platform: a Linux network namespace per render
// process tree, created with unshare(1). The render command runs as
// the namespace's init command; every process it spawns (the engine
// CLI, its Chromium, encoders) inherits the namespace. Two policies:
//
//   loopback  the namespace's loopback interface is raised. Processes
//             can talk to each other on 127.0.0.1 inside the namespace
//             (browser DevTools pipes and sockets, local helper
//             servers) and to NOTHING else: the namespace has no route
//             to the LAN, to the internet, or even to services on the
//             host's own loopback, which is a different loopback.
//   deny      loopback stays down. No IP traffic at all. Suitable for
//             pure file-and-pipe tools (ffmpeg, ffprobe); browser
//             engines may need loopback for their own control channel,
//             which is why loopback is the render policy.
//
// Flavor selection: as root, a plain network namespace (unshare -n)
// keeps the caller's user namespace, so Chromium's own sandboxing is
// untouched. Unprivileged callers fall back to a user+network
// namespace (unshare -rn), which maps the caller to root inside; the
// document references/render-isolation.md records what that means for
// browser sandboxes (the browser must then run with its sandbox off
// or a setuid helper, a container-specific requirement this layer
// does not silently satisfy).
//
// Fail closed: when a policy is requested but no namespace flavor
// works on this machine, applyNetworkPolicy throws
// NETWORK_ISOLATION_UNAVAILABLE and the caller must refuse the launch.
// Running unrestricted while claiming a policy would be worse than
// not running.

import { spawnSync } from "node:child_process";
import { IsolationError } from "./errors";

export type RenderNetworkMode = "off" | "loopback" | "deny";

export interface NamespaceProbe {
  supported: boolean;
  /** unshare argument set that works here, or null when none does. */
  flavor: "-n" | "-rn" | null;
  /** Loopback can be raised inside the namespace (iproute2 present). */
  canRaiseLoopback: boolean;
  detail: string;
}

let cachedProbe: NamespaceProbe | null = null;

function tryUnshare(flavor: "-n" | "-rn", raiseLoopback: boolean): boolean {
  const script = raiseLoopback
    ? "ip link set lo up 2>/dev/null; exec true"
    : "exec true";
  const res = spawnSync("unshare", [flavor, "sh", "-c", script], {
    timeout: 15000,
    stdio: "ignore",
  });
  return !res.error && res.status === 0;
}

/** Probe namespace support once per process. Loopback support is
 * probed with the interface raise included, because a namespace whose
 * loopback cannot be raised is not a loopback policy. */
export function probeNetworkNamespace(): NamespaceProbe {
  if (cachedProbe) return cachedProbe;
  const flavors: Array<"-n" | "-rn"> =
    typeof process.getuid === "function" && process.getuid() === 0
      ? ["-n", "-rn"]
      : ["-rn", "-n"];
  for (const flavor of flavors) {
    if (tryUnshare(flavor, true)) {
      cachedProbe = {
        supported: true,
        flavor,
        canRaiseLoopback: true,
        detail: `unshare ${flavor} creates a network namespace and iproute2 raises loopback inside it`,
      };
      return cachedProbe;
    }
    if (tryUnshare(flavor, false)) {
      cachedProbe = {
        supported: true,
        flavor,
        canRaiseLoopback: false,
        detail:
          `unshare ${flavor} creates a network namespace, but loopback could not be raised ` +
          "inside it (iproute2 missing or not permitted); only the deny policy is available",
      };
      return cachedProbe;
    }
  }
  cachedProbe = {
    supported: false,
    flavor: null,
    canRaiseLoopback: false,
    detail:
      "neither unshare -n nor unshare -rn could create a network namespace on this machine " +
      "(unprivileged namespace creation may be disabled by sysctl)",
  };
  return cachedProbe;
}

/** Test hook: forget the cached probe (used after environment changes
 * in tests). */
export function resetNetworkNamespaceProbe(): void {
  cachedProbe = null;
}

/** Parse MOTION_RENDER_NETWORK. An unrecognized value is a hard error
 * at launch time (NETWORK_MODE_INVALID), never a silent "off": a
 * mistyped policy must not become an open render. */
export function networkModeFromEnv(env: NodeJS.ProcessEnv): RenderNetworkMode {
  const raw = env.MOTION_RENDER_NETWORK;
  if (raw === undefined || raw === "" || raw === "off") return "off";
  if (raw === "loopback" || raw === "deny") return raw;
  throw new IsolationError(
    "NETWORK_MODE_INVALID",
    `MOTION_RENDER_NETWORK="${raw}" is not a render network policy (expected off, loopback, or deny)`
  );
}

export interface WrappedCommand {
  bin: string;
  args: string[];
}

/**
 * Wrap a command in the namespace for the requested policy. The inner
 * shell script is fixed text; the command and its arguments travel as
 * positional parameters ("$@"), so no caller data is ever interpolated
 * into a shell string. Throws NETWORK_ISOLATION_UNAVAILABLE when the
 * policy cannot be enforced here.
 */
export function applyNetworkPolicy(
  bin: string,
  args: string[],
  mode: RenderNetworkMode
): WrappedCommand {
  if (mode === "off") return { bin, args };
  const probe = probeNetworkNamespace();
  if (!probe.supported || !probe.flavor) {
    throw new IsolationError(
      "NETWORK_ISOLATION_UNAVAILABLE",
      `render network policy "${mode}" was requested but cannot be enforced: ${probe.detail}. ` +
        "Refusing to launch unrestricted."
    );
  }
  if (mode === "loopback" && !probe.canRaiseLoopback) {
    throw new IsolationError(
      "NETWORK_ISOLATION_UNAVAILABLE",
      `render network policy "loopback" was requested but ${probe.detail}. ` +
        "Refusing to launch with a dead loopback and call it loopback policy."
    );
  }
  const script =
    mode === "loopback" ? "ip link set lo up 2>/dev/null; exec \"$@\"" : "exec \"$@\"";
  return {
    bin: "unshare",
    args: [probe.flavor, "sh", "-c", script, "motion-render", bin, ...args],
  };
}
