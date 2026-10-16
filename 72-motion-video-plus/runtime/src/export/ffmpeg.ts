// Checked subprocess access to the pinned ffmpeg/ffprobe for the
// export layer (MG-040). Same discipline as src/remotion/decode.ts:
// argument arrays only, never shell strings, and a nonzero exit is an
// error carrying the stderr tail.

import { spawnSync } from "node:child_process";

export function runTool(
  command: string,
  args: string[],
  maxBuffer = 128 * 1024 * 1024
): Buffer {
  const result = spawnSync(command, args, { maxBuffer });
  if (result.error) {
    throw new Error(`${command} could not run: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString("utf8").slice(-1200) : "";
    throw new Error(`${command} exited ${result.status}: ${stderr}`);
  }
  return result.stdout;
}

export function runToolText(command: string, args: string[]): string {
  return runTool(command, args).toString("utf8");
}
