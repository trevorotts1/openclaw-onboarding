# Drama Song Ad Factory mini-app — Approvals + producer hand-off (Unit U8, version 0)

The approvals layer of the client mini app, and the one gate in front of the
producer. Wave 2, version 0.

Service home: `75-drama-song-ad-factory/mini-app/`. **This unit owns
`mini-app/approvals/` only.** It writes none of `mini-app/service/**` (U2),
`mini-app/ui/**` (U3), `mini-app/deploy/**` (U4), the pairing surface (U12) or
the `intake_card` files (U1/U11).

## What is here (version 0)

| File | What it is |
|---|---|
| `approvals.mjs` | The approvals layer: register/dedup an item, record an answer (first answer wins), the nudge→reminder→silence ladder, and the producer hand-off gate. Pure, over an injected store. |
| `ui.mjs` | The three approval cards and the studio-lines region. Renders the service's lines verbatim. Reuses U3's page patterns (an `el()` builder, real `<button>`/`<h2>`, `textContent` never `innerHTML`, every state in words). |
| `producer-handoff.mjs` | The CLI that carries one approved item to the producer, and refuses an unapproved one with a real non-zero exit. |
| `prove/approvals.prove.mjs` | The five runnable proofs (four behaviours + the UI), TRUE exit codes. |
| `prove/planted-bad.sh` | The planted-bad control: mutates a LOCAL copy and shows each proof can fail, then the clean control. |
| `package.json` | `{"type":"module"}` marker. No dependencies. |

## The four behaviours this unit owns (joint plan section 5, row U8)

1. **First answer wins.** Once an answer is recorded for an approval item, a
   second competing answer is **refused by name** (`APPROVAL_ANSWER_TAKEN`) and
   the recorded answer is left untouched. The loser is refused, not silently
   accepted.
2. **Version dedup.** The same item arriving with the **same version** returns
   the existing approval item (`created:false`) — never a second one. A
   **genuinely new version** creates a new item (`created:true`).
3. **One nudge, then reminder, then silence.** The escalation ladder is exactly
   `["nudge", "reminder"]`; every later event returns `null` no matter how many
   arrive. An answered item is always silent.
4. **Producer hand-off refuses an unapproved item** with a real non-zero exit
   (`5`, the same refusal exit the skill's existing gates use) and nothing on
   stdout.

## Built to the measured contracts

- **U2 service** (`unit/U2`, head `8f344a1dfa192115afbf9cab59ea706c86977ca6`) —
  `service/README.md` and `schema.sql`. The store adapter mirrors U2's
  "pure module + injected adapter" shape; the refusal dict mirrors the service
  shape `{ok:false, code, message}` with the skill gate's
  `{reason_code, detail, next_action}`.
- **U3 UI** (`unit/U3-U1`, head `594668c3ed09c073a2c091cbd03560cec0d34138`) —
  `ui/`. The page patterns are reused; no U3 file is edited and no U3 module is
  imported (it is a distinct path).
- **U11 send** (`unit/U11-U1`, head `4ef736fe1e62a22f054f53e5a7351e8ccba64b2c`) —
  skill 75 `channel_send`. The escalation step decides **how many** notices
  (one nudge, one reminder, then silence); the actual channel-neutral send is
  U11's, injected as a sink by the caller. This unit re-implements no sender.

## Run the proofs

```bash
node 75-drama-song-ad-factory/mini-app/approvals/prove/approvals.prove.mjs
#   exit 0 = every case passed, 2 = a named case failed

bash 75-drama-song-ad-factory/mini-app/approvals/prove/planted-bad.sh
#   exit 0 = every planted defect went red and the clean run is green
```

## The producer hand-off CLI

```bash
node 75-drama-song-ad-factory/mini-app/approvals/producer-handoff.mjs \
  --store <file> --client-id <id> --item <script|song|storyboard> --version <n>
#   exit 0 = approved, the payload is printed on stdout
#   exit 5 = refused (unknown or unapproved item), nothing on stdout
#   exit 2 = bad input
```

## Deliberate limits

- No new framework, scheduler, dashboard or management app (section 5.1). Three
  cards, four behaviours, one gate.
- No schema or control-service expansion: the store is the injected adapter
  (a JSON file for the CLI, memory for the checks), not a new service table.
- No credentials, no network, no client-box write. The checks send nowhere.
