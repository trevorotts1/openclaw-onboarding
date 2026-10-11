// =============================================================================
// RUNNABLE CHECK — a redirect is NOT an actual download
// -----------------------------------------------------------------------------
// mini-app/ui/checks/download-bytes-check.mjs
//
// Runs the SHIPPED verifier (../download.js — the same module the page loads)
// against a local fixture server and demands real file bytes.
//
//   POSITIVE   /delivery/master.mp4       200 + attachment + Content-Length + real bytes
//                                             -> the verifier must PASS
//   NEG A      /share/master              302 -> landing page
//                                             -> must FAIL (redirect only)
//   NEG B      /share/to-file             302 -> the REAL file (bytes really do exist
//                                             -- behind a redirect is still not a download)
//                                             -> must FAIL  <- the exact trap from the plan
//   NEG C      /nodisposition/master.mp4  200 + bytes, but no Content-Disposition
//                                             -> must FAIL (bytes that are not offered as a file)
//   NEG D      /lying-length/master.mp4   200 + attachment, Content-Length 5000, body 100
//                                             -> must FAIL (declared != received)
//
// Exit codes:  0 = every case behaved as required, 2 = a case misbehaved.
//
//   node checks/download-bytes-check.mjs
// =============================================================================
import { createServer } from "node:http";
import { verifyDownload } from "../download.js";

const PAYLOAD = Buffer.concat([
  // ftyp box + a deterministic body, so the "file" is a real byte sequence.
  Buffer.from([0x00, 0x00, 0x00, 0x18]),
  Buffer.from("ftypmp42", "latin1"),
  Buffer.from([0x00, 0x00, 0x00, 0x00]),
  Buffer.from("mp42isom", "latin1"),
  Buffer.alloc(200000, 0x5a),
]);

function sendAttachment(res, bytes, { disposition = 'attachment; filename="05 - Video Captioned.mp4"', type = "video/mp4", declaredLength = bytes.length } = {}) {
  const headers = { "Content-Type": type };
  if (declaredLength != null) headers["Content-Length"] = String(declaredLength);
  if (disposition != null) headers["Content-Disposition"] = disposition;
  res.writeHead(200, headers);
  res.end(bytes);
}

function startFixtureServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const path = req.url.split("?")[0];
      switch (path) {
        case "/delivery/master.mp4":
          return sendAttachment(res, PAYLOAD);
        case "/share/master":
          res.writeHead(302, { Location: "/landing" });
          return res.end();
        case "/share/to-file":
          res.writeHead(302, { Location: "/delivery/master.mp4" });
          return res.end();
        case "/landing":
          res.writeHead(200, { "Content-Type": "text/html", "Content-Length": "42" });
          return res.end("<html><body>Watch the video here</body></html>");
        case "/nodisposition/master.mp4":
          return sendAttachment(res, PAYLOAD, { disposition: null, type: "application/octet-stream" });
        case "/lying-length/master.mp4":
          return sendAttachment(res, PAYLOAD.subarray(0, 100), { declaredLength: PAYLOAD.length });
        default:
          res.writeHead(404, { "Content-Type": "text/plain", "Content-Length": "9" });
          return res.end("not found");
      }
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

const { server, port } = await startFixtureServer();
const base = `http://127.0.0.1:${port}`;

const CASES = [
  { name: "POSITIVE  real file", path: "/delivery/master.mp4", want: "pass" },
  { name: "NEG A     redirect to a landing page", path: "/share/master", want: "fail", mustMention: /redirect|attachment/i },
  { name: "NEG B     redirect to the real file", path: "/share/to-file", want: "fail", mustMention: /redirect/i },
  { name: "NEG C     200 bytes, no attachment", path: "/nodisposition/master.mp4", want: "fail", mustMention: /Content-Disposition|Content-Type/i },
  { name: "NEG D     Content-Length lies", path: "/lying-length/master.mp4", want: "fail", mustMention: /Content-Length/i },
];

let failures = 0;
for (const c of CASES) {
  const url = base + c.path;
  const result = await verifyDownload(url, { expectedBytes: c.want === "pass" ? PAYLOAD.length : null });
  const observed = result.ok ? "pass" : "fail";
  const metExpectation = observed === c.want;
  const mentionOk = !c.mustMention || c.mustMention.test(result.reasons.join(" "));
  const good = metExpectation && mentionOk;
  if (!good) failures++;
  const detail = result.ok
    ? `bytes=${result.receivedBytes} declared=${result.declaredBytes} type=${result.contentType}`
    : result.reasons.join("; ");
  console.log(`${good ? "PASS" : "FAIL"}  ${c.name.padEnd(34)} want=${c.want} got=${observed}  ${detail}`);
}

server.close();

if (failures > 0) {
  console.log(`\ndownload-bytes check FAILED: ${failures} of ${CASES.length} case(s) misbehaved`);
  process.exit(2);
}
console.log(`\ndownload-bytes check OK: positive yields real bytes (${PAYLOAD.length} B); `
  + `redirect-only, redirect-to-file, no-disposition and lying-length all refused`);
process.exit(0);
