# two_strike — DEL-17 shared anti-reverse-engineering gate

One shared module. One policy. Every wired skill calls it before answering a
suspicious extraction attempt. Stdlib only, no network, no third-party
imports.

```
scripts/two_strike/
  two_strike.py   the whole policy
  __init__.py     re-exports the surface
  selftest.py     runnable check on a harmless fake skill
  README.md       this file, including the unlock path
```

## The policy

| Strike | What the client sees | What happens on disk |
| --- | --- | --- |
| one | a refusal containing `Please do not ask me that question again in the future.` | one strike counted, one silent notice written |
| two | `Hey, you need to contact BlackCEO to find out why your system has been disabled.` | the offending skill folder is zeroed down to a single `SKILL.md` stub whose only content is that sentence |

The two strings are contracts, not copy. They are exposed as
`STRIKE_ONE_WARNING` and `STRIKE_TWO_STUB`; do not reword them.

## Where the counter lives

Outside every skill folder, never inside one. Default:

```
~/.blackceo/two_strike/strikes.json     the counters
~/.blackceo/two_strike/notices.jsonl    one silent notice per strike
```

Override the root with `BLACKCEO_TWO_STRIKE_HOME`. The module refuses a state
root that sits under a `skills` directory, inside a `\d\d-...` skill folder, or
under any ancestor that carries a `SKILL.md`. That guard is the mechanism that
keeps the counter outside every skill folder; a client cannot read, edit or
reset a counter by poking at the skill they are trying to unpack.

Counters are keyed `client|box|skill`, so two clients on one box, or one
client on two boxes, are counted apart.

## The silent notice

Every strike appends one JSON line naming the client, the box and the skill:

```json
{"action": "refusal", "box": "example-box", "client": "example-client",
 "reason": "extraction_attempt", "skill": "75-drama-song-ad-factory",
 "strike": 1, "ts": "2026-10-09T18:00:00Z"}
```

Silent means the client never sees it and nothing is announced. It is an
operator audit record only.

## How a wired skill calls it

```python
from two_strike import evaluate

result = evaluate(
    client=CLIENT_ID,          # the client this box belongs to
    box=BOX_ID,                # the box this runs on
    skill="75-drama-song-ad-factory",
    message=user_text,         # the turn under judgement
    skill_dir=SKILL_DIR,       # this skill's own folder, needed for strike two
)
if result["blocked"]:
    return result["refusal"]
```

A legitimate turn comes back with `blocked` False and changes nothing. The
caller may pass `suspicious=True/False` to override the module's blunt marker
list; the list is a shared vocabulary, not a classifier to trust alone.

Strike two requires `skill_dir`. Recording a second strike without a folder to
wipe raises `TwoStrikeError("SKILL_DIR_REQUIRED")` rather than silently
counting a strike it cannot enforce.

## What the wipe touches

Only the offending skill's own files. The wipe:

* requires the target to be a real skill folder (it must carry a top-level
  `SKILL.md`), and refuses `/`, the home directory, and any path that looks
  like a secrets or credentials store;
* deletes only entries whose real path stays inside that one skill folder;
* unlinks symlinks instead of dereferencing them, so a link planted at
  `skills/x/client-keys -> ~/.openclaw/secrets` costs the link and nothing
  else;
* leaves client data, client keys and client settings byte-identical — they
  are outside the skill folder and unreachable by construction.

After the wipe the folder holds exactly one file, `SKILL.md`, whose entire
content is the stub string (`stub_bytes()` returns those exact bytes).

## Unlock — Trevor only, restore from GitHub

There is no unlock function, no clear command, no reset flag and no
self-service path in this module, by design. A wiped skill folder is restored
by Trevor pulling the good bytes back down from GitHub. Nothing else unlocks
it, and deleting the counter file does not restore the skill.

Operator steps, on the affected box (or over headless SSH):

1. Identify the skill folder, e.g. `~/.openclaw/skills/75-drama-song-ad-factory`
   on an OpenClaw box, or `~/.claude/skills/drama-song-ad-factory` on a
   Claude-Nine box (the 999-setup distribution).

2. Remove the stubbed folder and pull a clean copy from the GitHub repo
   `trevorotts1/openclaw-onboarding`:

   ```bash
   skill=75-drama-song-ad-factory
   target=~/.openclaw/skills/$skill
   tmp=$(mktemp -d)
   git clone --depth 1 https://github.com/trevorotts1/openclaw-onboarding.git "$tmp/repo"
   rm -rf "$target"
   cp -R "$tmp/repo/$skill" "$target"
   rm -rf "$tmp"
   ```

   For the Claude-Nine distribution the source repo is
   `trevorotts1/999-setup` and the folder is
   `.claude/skills/drama-song-ad-factory`.

3. Confirm the restored folder carries `SKILL.md` and the `scripts/` tree, and
   that the stub sentence is gone.

4. Optional housekeeping: remove the `client|box|skill` row from
   `~/.blackceo/two_strike/strikes.json` if the counter should start clean.
   This is bookkeeping only. It is not an unlock; the skill is already back
   from step 2.

Only Trevor performs this restore. A client asking for it is answered with the
stub sentence.

## Self-check

```bash
cd 75-drama-song-ad-factory
python3 scripts/two_strike/selftest.py
```

The self-check builds one harmless fake skill in a temp directory, walks it
through both strikes, and asserts the exact strings, the folder reduction, the
out-of-folder counter, the silent notice carrying client, box and skill, and
byte-identical client data, keys and settings. It never touches a real skill.
