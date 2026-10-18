// Host service integration artifact generator (HYB-04) for THIS Mac.
//
// This module ONLY builds a LaunchAgent plist and the launchctl command
// arrays. It never loads, bootstraps, kickstarts or unloads anything, and it
// never spawns a process. Registering a service is deliberately deferred to a
// later unit that requires explicit host authority.
//
// Every executable is emitted as the real absolute path verified on this host
// (/bin/launchctl, /bin/mkdir, /bin/cp); verifyCommandPaths() re-checks them
// with access(X_OK) so a test can prove the arrays are runnable as written.
import { accessSync, constants } from "node:fs";

export const LAUNCHD_SCHEMA = "wise-elders.hybrid-supervisor-launchd/v1";
export const HOST_COMMAND_PATHS = Object.freeze({
  launchctl: "/bin/launchctl",
  mkdir: "/bin/mkdir",
  cp: "/bin/cp",
});
export const DEFAULT_DOMAIN = "gui";
export const DEFAULT_INTERVAL_SECONDS = 600;

function requireString(value, name) {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${name} must be a non-empty string`);
  }
}

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

/**
 * buildLaunchAgentPlist({ label, program_arguments, plist_path, output_path,
 *   error_path, working_directory, interval_seconds, environment, run_at_load })
 * Returns the plist CONTENT and its intended path. Nothing is written to disk.
 */
export function buildLaunchAgentPlist({
  label,
  program_arguments,
  plist_path,
  output_path,
  error_path,
  working_directory = null,
  interval_seconds = DEFAULT_INTERVAL_SECONDS,
  environment = {},
  run_at_load = false,
}) {
  requireString(label, "label");
  requireString(plist_path, "plist_path");
  requireString(output_path, "output_path");
  requireString(error_path, "error_path");
  requireInteger(interval_seconds, "interval_seconds");
  if (!Array.isArray(program_arguments) || program_arguments.length === 0) {
    throw new TypeError("program_arguments must be a non-empty array of absolute paths");
  }
  for (const [index, argument] of program_arguments.entries()) {
    requireString(argument, `program_arguments[${index}]`);
  }
  if (typeof run_at_load !== "boolean") {
    throw new TypeError("run_at_load must be a boolean");
  }

  const lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
    '<plist version="1.0">',
    "<dict>",
    "  <key>Label</key>",
    `  <string>${escapeXml(label)}</string>`,
    "  <key>ProgramArguments</key>",
    "  <array>",
    ...program_arguments.map((argument) => `    <string>${escapeXml(argument)}</string>`),
    "  </array>",
    "  <key>StartInterval</key>",
    `  <integer>${interval_seconds}</integer>`,
    "  <key>RunAtLoad</key>",
    `  <${run_at_load ? "true" : "false"}/>`,
    "  <key>StandardOutPath</key>",
    `  <string>${escapeXml(output_path)}</string>`,
    "  <key>StandardErrorPath</key>",
    `  <string>${escapeXml(error_path)}</string>`,
  ];
  if (working_directory !== null) {
    requireString(working_directory, "working_directory");
    lines.push("  <key>WorkingDirectory</key>", `  <string>${escapeXml(working_directory)}</string>`);
  }
  const environmentKeys = Object.keys(environment).sort();
  if (environmentKeys.length > 0) {
    lines.push("  <key>EnvironmentVariables</key>", "  <dict>");
    for (const key of environmentKeys) {
      requireString(environment[key], `environment.${key}`);
      lines.push(
        `    <key>${escapeXml(key)}</key>`,
        `    <string>${escapeXml(environment[key])}</string>`,
      );
    }
    lines.push("  </dict>");
  }
  lines.push("</dict>", "</plist>", "");

  return Object.freeze({
    schema: LAUNCHD_SCHEMA,
    label,
    plist_path,
    interval_seconds,
    content: lines.join("\n"),
    installed: false,
    registered: false,
  });
}

/**
 * launchctlCommands({ label, plist_path, uid, domain })
 * Command ARRAYS only; the caller decides whether to run them. Start/stop use
 * the plist path, status and restart address the service by label.
 */
export function launchctlCommands({ label, plist_path, uid, domain = DEFAULT_DOMAIN }) {
  requireString(label, "label");
  requireString(plist_path, "plist_path");
  requireString(domain, "domain");
  requireInteger(uid, "uid");
  if (domain !== DEFAULT_DOMAIN) {
    throw new RangeError(`this unit only emits ${DEFAULT_DOMAIN}/<uid> commands, got ${domain}`);
  }
  const target = `${domain}/${uid}`;
  const service = `${target}/${label}`;
  return Object.freeze({
    schema: LAUNCHD_SCHEMA,
    label,
    plist_path,
    target,
    service,
    start: Object.freeze([HOST_COMMAND_PATHS.launchctl, "bootstrap", target, plist_path]),
    status: Object.freeze([HOST_COMMAND_PATHS.launchctl, "print", service]),
    stop: Object.freeze([HOST_COMMAND_PATHS.launchctl, "bootout", target, plist_path]),
    restart: Object.freeze([HOST_COMMAND_PATHS.launchctl, "kickstart", "-k", service]),
    installed: false,
    registered: false,
  });
}

// Real-path proof: every distinct argv[0] must exist and be executable here.
export function verifyCommandPaths(commands) {
  const paths = new Set();
  for (const value of Object.values(commands)) {
    if (Array.isArray(value) && typeof value[0] === "string") paths.add(value[0]);
  }
  const results = [...paths].sort().map((path) => {
    let executable = false;
    try {
      accessSync(path, constants.X_OK);
      executable = true;
    } catch {
      executable = false;
    }
    return Object.freeze({ path, executable });
  });
  return Object.freeze(results);
}
