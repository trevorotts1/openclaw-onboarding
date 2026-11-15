# Approve This Client's Voice

`FISH_AUDIO_VOICE_ID` is the active setting, not evidence that the voice is correct.
Keep the owner's confirmed voice selection as a separate approval record. Never
derive that record from the active setting, a successful API response, a voice
name, or a model-list result. A voice visible to an API key may still be wrong.

1. Obtain the intended Fish Audio voice/model ID from the client's approved voice
   selection, and the message or ticket recording that approval. Confirm it with
   the owner against their sample. Do not print it or put it in source control.
2. Resolve this installation with `lib-shared.sh`. Use its exact `MC_COMPANY_ID`,
   which must also be set in Command Center's service environment. No company
   name guess, placeholder, other client's record or global fallback is allowed.
3. Create `<resolved root>/config/fish-audio-voice.json` with permissions `600`.
   The record has this schema (placeholders below are intentionally invalid):

```json
{
  "schema_version": 1,
  "company_id": "<this installation's MC_COMPANY_ID>",
  "voice_id_sha256": "<lowercase SHA-256 of the independently approved voice ID>",
  "approval_ref": "<owner confirmation message or ticket reference>"
}
```

To create the record without putting the voice in shell history or stdout, run
this locally after resolving `OC_ROOT`. Enter the voice from the approval source,
not from `FISH_AUDIO_VOICE_ID`. The script never reads the active voice variable.

```bash
export OC_ROOT
python3 - <<'PY'
import getpass, hashlib, json, os
from pathlib import Path
root = Path(os.environ['OC_ROOT'])
assert root.is_absolute()
company = input('Exact installed MC_COMPANY_ID: ').strip()
approval = input('Owner approval message/ticket reference: ').strip()
voice = getpass.getpass('Voice ID from that independent approval: ').strip()
assert company and approval and voice and '<' not in company + approval + voice
record = {'schema_version': 1, 'company_id': company,
          'voice_id_sha256': hashlib.sha256(voice.encode()).hexdigest(),
          'approval_ref': approval}
target = root / 'config/fish-audio-voice.json'
target.parent.mkdir(parents=True, exist_ok=True)
# Refuse to replace an existing approval; review a voice change separately.
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    json.dump(record, output, indent=2)
    output.write('\n')
print('Independent voice approval saved; run Skill 30 configuration QC.')
PY
```

An absolute `FISH_AUDIO_VOICE_BINDING_FILE` may select another record belonging
to this installation. Set the same path in both runtimes. Never search other
roots for approval. Keep the file outside the skill tree so skill updates preserve
it. This is an operator-maintained approval record, not a signature that can
independently authenticate who approved it.

4. Configure the active `FISH_AUDIO_VOICE_ID` separately in the canonical secret
   store. Keep live service environment and stored settings consistent. An
   explicit live setting wins, including an empty or wrong value; stale env must
   fail rather than borrow a value from another store. Run bundled QC.
5. Omit `FISH_AUDIO_MODEL` for the BlackCEO `drama-3` default. A client/operator
   may explicitly choose `s2.1-pro`; empty, misspelled, free and other model IDs
   fail. Every request sends the model header; errors never trigger a downgrade.
6. Perform the separately approved live smoke test and listening review before
   declaring the client's voice ready. A matching ID cannot prove acoustic
   similarity or availability. Record NOT RUN for checks that have not happened.

## Command Center and Existing Installations

Command Center vendors `production-policy.json` as
`config/fish-audio-policy.vendored.json` with a SHA-256 pin and source provenance.
Its TTS route reads the same local approval record and compares the runtime voice
and any request override to it before sending audio. Explicit/default Fish Audio
selection fails closed when unready, including browser fallback. The model
catalog lists provider resources; it is not proof of client voice approval.

Updating code does not approve an existing voice. There is no automatic backfill
from `FISH_AUDIO_VOICE_ID`. Until independent approval is present, configuration
QC fails and Fish Audio is unavailable. Do not mark pending setup COMPLETE, roll
out, restart a service, or claim a fleet repair merely because a branch or test
passes. Skill 32/fleet rolls deploy the pinned Command Center release in
`cc-compat.json`; a separate Command Center PR is required. These changes do not
advance that deployment pin.
