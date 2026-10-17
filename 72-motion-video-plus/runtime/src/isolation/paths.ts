// Asset reference validation for the render isolation layer (MG-029).
//
// A scene or job names its assets by reference. At render time a
// reference is data, and data gets validated before it is resolved:
// anything that is not a plain job-relative path is refused with a
// named finding BEFORE the filesystem is touched for content. This is
// the runtime-side companion to the preparation layer
// (scripts/prepare_assets.py, MG-011): preparation proves the declared
// bytes are the recorded bytes; this module proves the reference
// itself cannot point outside the job, cannot be a URL the renderer
// would fetch at render time, and cannot smuggle a traversal past a
// string check through percent-encoding or a symlink.
//
// Finding categories follow the pipeline's existing vocabulary:
// MG_SECURITY_VIOLATION (exit class 9) for hostile shapes, and
// MG_SCHEMA_INVALID (exit class 2) for plain contract problems such as
// an empty or missing reference.

import { existsSync, realpathSync } from "node:fs";
import { isAbsolute, join, resolve, sep } from "node:path";

export type AssetRefCode =
  | "ASSET_REF_EMPTY"
  | "ASSET_REF_NULL_BYTE"
  | "ASSET_REF_BACKSLASH"
  | "ASSET_REF_ABSOLUTE"
  | "ASSET_REF_EXTERNAL"
  | "ASSET_REF_TRAVERSAL"
  | "ASSET_REF_ESCAPE"
  | "ASSET_REF_MISSING";

export interface AssetRefFinding {
  category: "MG_SECURITY_VIOLATION" | "MG_SCHEMA_INVALID";
  /** Stable rule code, for example "ASSET_REF_TRAVERSAL". */
  code: AssetRefCode;
  /** The reference as supplied, echoed for diagnosis. References are
   * paths, never secrets; echoing them is safe. */
  path: string;
  message: string;
}

export interface AssetRefValidation {
  ok: boolean;
  /** Absolute, symlink-resolved path inside the job directory. Present
   * only when the reference is valid (and, when the file exists,
   * resolved through symlinks). */
  resolvedPath: string | null;
  findings: AssetRefFinding[];
}

const SCHEME_PATTERN = /^[A-Za-z][A-Za-z0-9+.-]*:/;
const WINDOWS_DRIVE_PATTERN = /^[A-Za-z]:($|[\\/])/;

function finding(
  category: AssetRefFinding["category"],
  code: AssetRefCode,
  path: string,
  message: string
): AssetRefFinding {
  return { category, code, path, message };
}

/**
 * Validate one asset reference against a job directory.
 *
 * Checks run from the cheapest string rules to the filesystem rules,
 * and the first failure wins: the returned findings list has exactly
 * one entry on failure, so callers can name the rule that fired.
 * When `mustExist` is set, a validly shaped reference to a file that
 * does not exist fails as ASSET_REF_MISSING.
 */
export function validateAssetRef(
  ref: unknown,
  opts: { jobDir: string; mustExist?: boolean }
): AssetRefValidation {
  const fail = (f: AssetRefFinding): AssetRefValidation => ({
    ok: false,
    resolvedPath: null,
    findings: [f],
  });
  if (typeof ref !== "string" || ref.trim() === "") {
    return fail(
      finding("MG_SCHEMA_INVALID", "ASSET_REF_EMPTY", String(ref ?? ""), "asset reference is empty")
    );
  }
  if (ref.includes("\0")) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_NULL_BYTE",
        ref,
        "asset reference contains a NUL byte"
      )
    );
  }
  if (ref.includes("\\")) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_BACKSLASH",
        ref,
        "asset reference contains a backslash; job-relative references use forward slashes only"
      )
    );
  }
  if (ref.startsWith("//")) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_EXTERNAL",
        ref,
        "asset reference is a protocol-relative URL; render-time fetching is forbidden, " +
          "assets enter the job at preparation time as verified local files"
      )
    );
  }
  if (WINDOWS_DRIVE_PATTERN.test(ref) || isAbsolute(ref)) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_ABSOLUTE",
        ref,
        "asset reference is an absolute path; references must be relative to the job directory"
      )
    );
  }
  if (SCHEME_PATTERN.test(ref)) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_EXTERNAL",
        ref,
        "asset reference is an external or URL reference; render-time fetching is forbidden, " +
          "assets enter the job at preparation time as verified local files"
      )
    );
  }
  // Percent-encoded traversal (%2e%2e) must not slip past the segment
  // check: decode once for inspection. A malformed escape is treated
  // as an ordinary (if odd) filename, not decoded further.
  let decoded = ref;
  try {
    decoded = decodeURIComponent(ref);
  } catch {
    decoded = ref;
  }
  const segments = decoded.split("/");
  if (segments.some((s) => s === "..")) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_TRAVERSAL",
        ref,
        "asset reference contains a parent-directory segment"
      )
    );
  }
  if (decoded !== ref && (isAbsolute(decoded) || SCHEME_PATTERN.test(decoded))) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_EXTERNAL",
        ref,
        "asset reference decodes to an absolute or URL reference"
      )
    );
  }
  // Filesystem containment: resolve through symlinks when the target
  // exists, so a symlinked directory inside the job cannot smuggle the
  // reference outside it.
  let jobRoot = resolve(opts.jobDir);
  try {
    jobRoot = realpathSync(jobRoot);
  } catch {
    // The job directory itself does not exist; containment is then
    // judged lexically against the resolved path.
  }
  const joined = resolve(jobRoot, ref);
  let resolvedPath = joined;
  if (existsSync(joined)) {
    resolvedPath = realpathSync(joined);
  }
  if (resolvedPath !== jobRoot && !resolvedPath.startsWith(jobRoot + sep)) {
    return fail(
      finding(
        "MG_SECURITY_VIOLATION",
        "ASSET_REF_ESCAPE",
        ref,
        `asset reference resolves outside the job directory: ${resolvedPath}`
      )
    );
  }
  if (opts.mustExist && !existsSync(resolvedPath)) {
    return fail(
      finding(
        "MG_SCHEMA_INVALID",
        "ASSET_REF_MISSING",
        ref,
        `asset reference points at a file that does not exist: ${ref}`
      )
    );
  }
  return { ok: true, resolvedPath, findings: [] };
}

/** Sanitize one job id into a single safe path segment for registry
 * file names and work directory names. */
export function sanitizeJobSegment(jobId: string): string {
  const cleaned = jobId.replace(/[^A-Za-z0-9._:-]/g, "_").replace(/^\.+/, "_");
  return cleaned === "" ? "job" : cleaned.slice(0, 96);
}

/** Join path segments under a root the caller already trusts. Small
 * helper so isolation code never hand-rolls separators. */
export function joinUnder(root: string, ...segments: string[]): string {
  return join(root, ...segments);
}
