// =============================================================================
// Drama Song Ad Factory mini-app — U3 delivery download
// -----------------------------------------------------------------------------
// mini-app/ui/download.js
//
// The ONE place that decides whether a delivery link is an actual download.
//
// THE TRAP THIS CLOSES (JOINT PLAN row U3): a REDIRECT is NOT an actual
// download. A share link that 302s to a landing page, or even to the file,
// gives the client a page to look at — not a file. v0 therefore requires, on
// the exact URL the client taps:
//   * HTTP 200 (a 3xx is refused outright, follow-the-redirect never happens);
//   * `Content-Disposition: attachment` (the server says "this is a file");
//   * a positive `Content-Length`;
//   * the received body to be exactly that many bytes, and non-zero;
//   * a media/binary `Content-Type`.
// Only then does the UI offer the button, and only then does it fire the
// browser save. Anything else names the failure in plain words.
//
// Pure: no DOM here except the opt-in `triggerSave` helper, so the same code
// runs in the page and in checks/download-bytes-check.mjs.
// =============================================================================

const BINARY_TYPE = /^(video|audio|image)\/|^application\/(octet-stream|zip|pdf|mp4)/i;

export function verifyBytes({
  status,
  contentLengthHeader,
  contentType,
  disposition,
  byteLength,
  expectedBytes = null,
}) {
  const reasons = [];

  if (status >= 300 && status < 400) {
    reasons.push(`the link redirects (HTTP ${status}); a redirect is not an actual download`);
  } else if (status !== 200) {
    reasons.push(`the server answered HTTP ${status}, not 200`);
  }

  if (!/\battachment\b/i.test(disposition || "")) {
    reasons.push("no Content-Disposition: attachment — the server is not offering a file to save");
  }

  if (!BINARY_TYPE.test(contentType || "")) {
    reasons.push(`Content-Type ${JSON.stringify(contentType || "")} is not a media or binary type`);
  }

  const declared = contentLengthHeader == null ? null : Number(contentLengthHeader);
  if (contentLengthHeader == null) {
    reasons.push("no Content-Length header");
  } else if (!Number.isFinite(declared) || declared <= 0) {
    reasons.push(`Content-Length ${JSON.stringify(contentLengthHeader)} is not a positive number`);
  } else if (declared !== byteLength) {
    reasons.push(`Content-Length says ${declared} bytes but ${byteLength} arrived`);
  }

  if (byteLength === 0) reasons.push("zero file bytes arrived");
  if (expectedBytes != null && byteLength !== expectedBytes) {
    reasons.push(`expected ${expectedBytes} bytes for this delivery, got ${byteLength}`);
  }

  return {
    ok: reasons.length === 0,
    reasons,
    status,
    declaredBytes: declared,
    receivedBytes: byteLength,
    contentType: contentType || "",
  };
}

// Probe one URL. `redirect: "manual"` is the load-bearing choice — the check
// must SEE a redirect and refuse it, never silently follow it.
export async function verifyDownload(url, { fetchImpl = fetch, expectedBytes = null } = {}) {
  let res;
  try {
    res = await fetchImpl(url, { redirect: "manual", method: "GET" });
  } catch (err) {
    return { ok: false, reasons: [`the link could not be reached: ${err.message}`], url };
  }

  // A browser returns an opaque redirect (status 0, no headers) for manual
  // redirects; that is our redirect signal there.
  if (res.type === "opaqueredirect" || res.status === 0) {
    return {
      ok: false,
      reasons: ["the link redirects; a redirect is not an actual download"],
      url,
      status: res.status,
    };
  }

  // A body that dies mid-stream (a server whose Content-Length over-promises)
  // is a refusal, not a crash: fall through to verifyBytes with 0 bytes so the
  // Content-Length mismatch is named in the reasons.
  let byteLength = 0;
  let readError = null;
  try {
    const buf = new Uint8Array(await res.arrayBuffer());
    byteLength = buf.byteLength;
  } catch (err) {
    readError = err.message;
  }

  const verdict = verifyBytes({
    status: res.status,
    contentLengthHeader: res.headers.get("content-length"),
    contentType: res.headers.get("content-type"),
    disposition: res.headers.get("content-disposition"),
    byteLength,
    expectedBytes,
  });
  if (readError) verdict.reasons.push(`the file body stopped early: ${readError}`);
  verdict.ok = verdict.reasons.length === 0;
  return { url, ...verdict };
}

// Fired only after verifyDownload said ok. The `download` attribute is what
// makes the browser save rather than navigate.
export function triggerSave(url, filename, doc = document) {
  const a = doc.createElement("a");
  a.href = url;
  a.setAttribute("download", filename || "");
  a.rel = "noopener";
  doc.body.appendChild(a);
  a.click();
  a.remove();
}
