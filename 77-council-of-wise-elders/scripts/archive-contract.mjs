// Verification mode is selected by the caller, never by mutable manifest data.
// This is package consistency checking, not a signature or publisher attestation.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export function checkArchiveContract(root, manifest, distribution = false) {
  const file = "council-of-wise-elders.skill";
  const path = join(root, file);
  const errors = [];
  const expected = distribution ? "extracted_distribution" : "generated";
  if (manifest.archive?.status !== expected) {
    errors.push(`${distribution ? "distribution" : "source"} verification requires archive status ${expected}`);
  }
  if (manifest.archive?.file !== file) {
    errors.push(`archive file must be ${file}`);
  }
  if (distribution) {
    if (existsSync(path)) errors.push("extracted distribution unexpectedly contains a nested archive");
  } else if (!existsSync(path)) {
    errors.push("source verification requires the distributable archive");
  } else {
    const actual = createHash("sha256").update(readFileSync(path)).digest("hex");
    if (actual !== manifest.archive?.sha256) {
      errors.push("distributable archive SHA-256 is missing or does not match the source manifest");
    }
  }
  return errors;
}
