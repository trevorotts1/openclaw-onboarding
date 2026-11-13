#!/usr/bin/env node
// =============================================================================
// producer-handoff.mjs — the PRODUCER HAND-OFF (U8)
// -----------------------------------------------------------------------------
// 75-drama-song-ad-factory/mini-app/approvals/producer-handoff.mjs
//
// Carries ONE approved item to the producer, and REFUSES an item that has not
// been approved with a real non-zero exit. This is the reuse of the skill's
// existing gate shape ({reason_code, detail, next_action}) and its existing
// refusal exit code (5, the one song_choices and channel_send already use) —
// not a new gate framework.
//
//   node producer-handoff.mjs --store <file> --client-id <id> --item <itemId> --version <v>
//
// Exit codes:
//   0  approved — the payload is printed as JSON on stdout
//   5  refused  — the item is unknown or unapproved; nothing on stdout
//   2  bad input (an argument is missing or malformed)
// =============================================================================
import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { fileStore, producerPayload, ApprovalError, REFUSED_EXIT } from "./approvals.mjs";

function parse(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    if (!flag.startsWith("--")) throw new ApprovalError(`unexpected argument ${flag}`);
    out[flag.slice(2)] = argv[i + 1];
  }
  return out;
}

export function main(argv = process.argv.slice(2)) {
  let a;
  try {
    a = parse(argv);
  } catch (e) {
    process.stderr.write(`producer-handoff: ${e.message}\n`);
    return 2;
  }
  const { store: storePath, "client-id": clientId, item, version } = a;
  if (!storePath || !clientId || !item || version == null) {
    process.stderr.write("usage: producer-handoff.mjs --store FILE --client-id ID --item ID --version N\n");
    return 2;
  }
  try {
    const verdict = producerPayload(fileStore(storePath), { clientId, itemId: item, version });
    if (!verdict.ok) {
      // Refused: a named refusal on stderr, nothing on stdout, non-zero exit.
      process.stderr.write(`REFUSED ${verdict.reason_code}: ${verdict.detail}\n`);
      process.stderr.write(`next: ${verdict.next_action}\n`);
      return REFUSED_EXIT;
    }
    process.stdout.write(JSON.stringify(verdict.payload) + "\n");
    return 0;
  } catch (e) {
    if (e instanceof ApprovalError) {
      process.stderr.write(`producer-handoff: ${e.message}\n`);
      return 2;
    }
    throw e;
  }
}

// Run only when executed directly. Node puts the RESOLVED realpath in
// import.meta.url, so argv[1] is resolved the same way first: a symlinked
// invocation must still run main(), not exit 0 doing nothing.
if (process.argv[1]) {
  let selfUrl = null;
  try {
    selfUrl = pathToFileURL(realpathSync(process.argv[1])).href;
  } catch {
    selfUrl = null;
  }
  if (import.meta.url === selfUrl) process.exit(main());
}
