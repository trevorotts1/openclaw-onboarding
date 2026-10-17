// Structured failures for the render isolation layer (MG-029).
//
// Every refusal this layer raises carries a stable machine-readable code
// so callers and tests name the exact rule that fired instead of matching
// prose. Codes raised here:
//   NETWORK_ISOLATION_UNAVAILABLE  a requested network policy cannot be
//                                  enforced on this platform; the launch
//                                  is refused rather than run open.
//   NETWORK_MODE_INVALID           MOTION_RENDER_NETWORK names no mode.
//   ASSET_FETCH_REFUSED            an approved-asset fetch violated the
//                                  fetch policy (scheme, size, redirect).
//   ASSET_HASH_MISMATCH            fetched bytes do not match the sha256
//                                  recorded for the approved asset.
//   ASSET_NAME_INVALID             a staged asset name is not a single
//                                  safe path segment.
//   LAUNCH_USAGE                   the isolation launcher CLI was called
//                                  without a command to run.

export class IsolationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "IsolationError";
    this.code = code;
  }
}
