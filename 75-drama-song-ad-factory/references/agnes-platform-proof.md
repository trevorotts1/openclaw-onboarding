TEST - executed on a client VPS as a single-platform test; Contabo validated by identical method (same recipe, same docker flow), not boot-tested separately

# Agnes platform proof — single-platform container recreate test (W4-proof-U2, TEST-01)

Unit **W4-proof-U2** · lane **AGN-901** · label **TEST** · proves **SPEC acceptance 2** ("Platforms") for
the two container rows of SPEC **A12**. Receipt only: one new file, one throwaway container + one
throwaway named volume on one remote VPS, both removed in the same script that created them. No code
change, no version bump, no CHANGELOG edit, no Agnes call, no KIE call, no API spend of any kind.

| | |
|---|---|
| Date | 2026-10-15 (box local time; times not relied on) |
| Authorisation | Overseer order (Trevor GO, 10:40 EDT) naming this box as the test venue and as the validator for Contabo and Hostinger |
| Instrument | Hostinger VPS `a client VPS box` reached over SSH from the operator Mac Mini; docker **29.4.0** daemon on that box |
| Repo / branch | `trevorotts1/openclaw-onboarding`, worktree `/Users/<operator>/agnes-wt/W4-proof-U2`, branch `unit/AGN-W4-proof-U2`, head `0cb71acd9` |
| Container / volume | container `agn-test-901`, volume `agn-test-901-home` — the only two objects this test ever created; both removed before this file was written |
| Verdict | **PASS** — both survival asserts hold across a container recreate, and the box is proven clean afterwards |

---

## 1. Verdict

SPEC acceptance 2 asks for "Hostinger and Contabo container simulation of key lookup, remembered answer
path and quota ledger path surviving a container recreate; tesseract present or `OCR_UNAVAILABLE`".
The BUILD-PLAN `W4-proof-U2` line states the rule for this exact case: **"Docker unavailable → BLOCKED."**

The operator Mac Mini has no docker daemon, which is why the previous revision of this file carried a
**BLOCKED** verdict (its section 2 is unchanged in substance: the local `docker` client is present, the
socket target is missing, no `dockerd`, no Docker Desktop, no alternative runtime). TEST-01 supplied the
one thing that revision said a re-run needed — **a machine with a docker daemon** — by naming the Hostinger
VPS in the header above as the authorised instrument. Everything below was executed there, over SSH, in
one script, and nothing else on that box was touched.

Per unit acceptance, this documented single-platform route satisfies the receipt requirement: one
platform's real outputs are captured here, and Contabo is validated by **identical method** — the same
recipe (image `node:22-bookworm`, `-u node`, fake key in container env, persistent path under `HOME`,
destroy + recreate, re-read) and the same docker flow — **not boot-tested separately** on this run.

---

## 2. Instrument and credential handling

- Transport: SSH from the operator Mac Mini to `a client VPS box`, key authentication
  (`ssh -i ~/.ssh/id_ed25519 -o BatchMode=yes root@<box>`). The root password recorded in the accounts
  file was **never read, echoed, logged or written** anywhere — it was not needed, so it never entered a
  command line, a transcript, this file or the receipt.
- The whole test is one bash script streamed over SSH stdin; it created, asserted, destroyed and proved
  cleanliness in a single pass. Raw capture: `lanes/AGN-901-lane/box-run.txt` — **70 lines**: lines 1–64
  are the original test capture, lines 65–70 are the two REPAIR-1 read-only probes (`docker compose
  version`, tesseract), appended without altering line 1.
- Nothing on the box outside the two test objects: no config edit, no service restart, no package
  install, no touch of the client's own container, no fleet action.
- **No network transfer of any kind, and no image pull.** `node:22-bookworm` was **already present on
  the box** before the script ran; the capture's pre-state `-- images` line reads, verbatim,
  `node:22-bookworm 0e5f90657369 1.65GB`. The test script contains no `docker pull` and none executed.
  No request was made to Agnes or to any provider; the key material is a named fake.

### Pre-state (read-only, before anything was created)

```
$ docker --version
Docker version 29.4.0, build 9d7ad9f
$ docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}'
a-client-vps-box-openclaw-1|76b80d50203e|Up 2 days
traefik-traefik-1|traefik:latest|Up 5 months
$ docker volume ls --format '{{.Name}}'
traefik-letsencrypt
traefik_traefik-letsencrypt
-- images
node:22-bookworm 0e5f90657369 1.65GB
```

**The image was pre-present, not pulled.** The `-- images` line above is quoted verbatim from the
capture (`box-run.txt` line 11): the box already held `node:22-bookworm`, id `0e5f90657369`, 1.65GB,
so the script needed no `docker pull` and issued none.

The client container `a-client-vps-box-openclaw-1` was **Up 2 days** before the test and is **Up 2 days**
after it (section 7) — never stopped, never removed, never restarted.

---

## 3. The recipe (verbatim, as executed)

```sh
C=agn-test-901
V=agn-test-901-home
IMG=node:22-bookworm

docker volume create "$V"

# RUN 1 — -u node, HOME on the persistent path, fake Agnes key in env
docker run -d --name "$C" --user node \
  -e HOME=/home/node \
  -e AGNES_AI_API_KEY=fake-agnes-key-AGN-901-NOT-A-SECRET \
  -v "$V":/home/node \
  "$IMG" sleep 600

docker exec -i -e HOME=/home/node "$C" sh <<'EOS'
  # key_present assert, then write the remembered answer and the quota ledger
  # to $HOME/.agnes/ on the mounted volume, then assert both back
EOS

docker rm -f "$C"                 # destroy

# RUN 2 — identical image, identical flags, identical mount
docker run -d --name "$C" --user node \
  -e HOME=/home/node \
  -e AGNES_AI_API_KEY=fake-agnes-key-AGN-901-NOT-A-SECRET \
  -v "$V":/home/node \
  "$IMG" sleep 600

docker exec -i -e HOME=/home/node "$C" sh <<'EOS'
  # read-only asserts: key_present, remembered answer, quota ledger
EOS
```

Persistent paths inside the container HOME:

| Artefact | Path inside container | Backing |
|---|---|---|
| Fake Agnes key | container env `AGNES_AI_API_KEY` | recreate re-supplies it (same `-e` on run 2) |
| Remembered "pays for Agnes" answer | `/home/node/.agnes/remembered.json` | named volume `agn-test-901-home` mounted at `/home/node` |
| Daily quota ledger | `/home/node/.agnes/quota-ledger.json` | same named volume |

`HOME=/home/node` is the Contabo row's `HOME` (the row `timer-artifacts/README.md` calls "the trap").
Here it is mounted, so this run proves the **method** — persist under `HOME`, recreate, re-read — which
is the identical recipe Contabo runs with `HOME=/home/node` and the volume on `~/.openclaw`.

---

## 4. Run 1 — captured output (verbatim)

```
===== RUN 1 =====
dd9bfbf912cd687879e3b50d177ea6a7ff95d2e766d6eacaf0b6f2aa307aabd2
run1_container_id=dd9bfbf912cd
run=1 user=node uid=1000 gid=1000 HOME=/home/node
key_present=true
remembered_answer={"pays_for_agnes":"yes","saved_by":"TEST-01","saved_at":"2026-10-15"}
quota_ledger={"ledger":"daily-quota","date":"2026-10-15","used":7,"limit":100}
remembered_answer_match=true
quota_ledger_present=true
node_version=v22.23.3
docker_host_version_on_box= --version      # stray echo line: `$docker` is empty inside the container;
                                           # the real host version is in section 6
run1_exit=0
-- container id after run 1
agn-test-901|dd9bfbf912cd|Up Less than a second
```

Container created as user `node` (uid 1000, gid 1000), `HOME=/home/node`, both files written onto the
mounted volume, all three asserts true, `run1_exit=0`.

### Destroy

```
===== DESTROY =====
agn-test-901
removed_container=agn-test-901
-- container gone?
container_still_present=false
```

---

## 5. Run 2 — recreate, captured output (verbatim)

Same image digest, same `-u node`, same `-e HOME`, same `-e AGNES_AI_API_KEY`, same `-v` mount; only the
container is new.

```
===== RUN 2 (recreate, same image, same mounts) =====
1158e15e2e170264028bd5962456aca2525bfff5f5f4486e1859a9b60e5b056b
run2_container_id=1158e15e2e17
run=2 user=node uid=1000 gid=1000 HOME=/home/node
key_present=true
remembered_answer={"pays_for_agnes":"yes","saved_by":"TEST-01","saved_at":"2026-10-15"}
quota_ledger={"ledger":"daily-quota","date":"2026-10-15","used":7,"limit":100}
remembered_answer_match=true
quota_ledger_present=true
node_version=v22.23.3
run2_exit=0
```

### Survival asserts

| Assert | Run 1 | Run 2 (after recreate) |
|---|---|---|
| `key_present` — fake key in container env | `true` | `true` |
| remembered "pays for Agnes" answer matches | `true` | `true` |
| daily quota ledger present | `true` | `true` |
| exit code | `0` | `0` |

Run 2's `remembered_answer=` and `quota_ledger=` lines are byte-identical to run 1's — the two objects
were read back, not rewritten.

---

## 6. Versions (captured)

```
===== VERSIONS =====
docker_host=Docker version 29.4.0, build 9d7ad9f
node_in_container=v22.23.3
image=[node@sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8]
```

| | |
|---|---|
| docker (host daemon on the VPS) | `Docker version 29.4.0, build 9d7ad9f` |
| node (inside the container) | `v22.23.3` |
| image | `docker.io/library/node:22-bookworm`, digest `sha256:0e5f906573693feaa1e21057ebdcfdb5bd5021f050b2dc7c9deceb629c7da2a8` |
| docker compose (host) | `Docker Compose version v5.1.2` — capture lines 66–67 (`$ docker compose version`, read-only REPAIR-1 probe) |

---

## 7. Box-cleanup proof (verbatim)

Immediately after the run-2 asserts, in the same script:

```
===== HYGIENE =====
agn-test-901                 # docker rm -f agn-test-901
rm_container_done=0
agn-test-901-home            # docker volume rm agn-test-901-home
rm_volume_done=0

===== POST-STATE =====
-- containers AFTER (read-only)
a-client-vps-box-openclaw-1|76b80d50203e|Up 2 days
traefik-traefik-1|traefik:latest|Up 5 months
-- volumes AFTER (read-only)
traefik-letsencrypt
traefik_traefik-letsencrypt
-- test container present?
test_container_present=false
-- test volume present?
test_volume_present=false
===== DONE =====
```

Before → after, compared name by name:

| Object | BEFORE | AFTER | Change |
|---|---|---|---|
| `a-client-vps-box-openclaw-1` (client) | present, `Up 2 days` | present, `Up 2 days` | **untouched** |
| `traefik-traefik-1` | present, `Up 5 months` | present, `Up 5 months` | **untouched** |
| `traefik-letsencrypt` (volume) | present | present | **untouched** |
| `traefik_traefik-letsencrypt` (volume) | present | present | **untouched** |
| `agn-test-901` (test container) | absent | absent (`test_container_present=false`) | created and removed by this test |
| `agn-test-901-home` (test volume) | absent | absent (`test_volume_present=false`) | created and removed by this test |

The only two names that differ between the before and after listings are this test's own. No
pre-existing container or volume was stopped, removed, created or modified. No `docker volume` other
than `agn-test-901-home` was ever created; no config file, service or package was touched.

---

## 8. OCR (optional line of SPEC acceptance 2)

Read-only probe on the box, nothing installed (capture lines 68–70):

```
$ command -v tesseract >/dev/null 2>&1 && tesseract --version | head -1 || echo "tesseract or OCR_UNAVAILABLE"
tesseract or OCR_UNAVAILABLE
```

So the platform answer for this box is **`OCR_UNAVAILABLE`**, which SPEC A12 accepts. The in-container
line was not probed separately (it is optional for this TEST and would have meant a second container,
which the spec forbids); `node:22-bookworm` does not ship tesseract, so the expected in-container answer
is the same `OCR_UNAVAILABLE`, never PASS. That expectation is stated as an expectation, not as a result.

---

## 9. Status of each acceptance line

| SPEC acceptance 2 item | Status | Evidence |
|---|---|---|
| key lookup, fake key in container env → `key_present: true` | **PASS** | section 4 (`key_present=true`) and section 5 (`key_present=true`) |
| remembered answer on the platform's persistent path | **PASS** | section 4 write + section 5 read-back, byte-identical |
| quota ledger on the platform's persistent path | **PASS** | section 4 write + section 5 read-back, byte-identical |
| container recreate → both survive | **PASS** | run 1 `dd9bfbf912cd` destroyed (`container_still_present=false`), run 2 `1158e15e2e17` re-read both |
| tesseract present or `OCR_UNAVAILABLE` | **PASS** (`OCR_UNAVAILABLE`) | section 8 |
| no network to Agnes, no KIE call, no spend, no image pull | **held** | image pre-present on the box (capture `-- images`, line 11: `node:22-bookworm 0e5f90657369 1.65GB`); the script contains no `docker pull`; key material is a named fake |
| box left clean | **PASS** | section 7 |
| both platforms' outputs OR this documented route | **satisfied by this route** | header line: Contabo validated by identical method, not boot-tested separately |

---

## 10. What stays true for Contabo (identical method, not boot-tested here)

The recipe in section 3 is platform-independent: image, `-u node`, fake key in env, persist under
`HOME`, destroy, recreate, re-read. On Contabo the same script runs with the volume on `~/.openclaw`
instead of on `/home/node`, which is the one difference the trap in `timer-artifacts/README.md` names —
there `$HOME` itself is the throwaway container layer, so anything written directly under `$HOME`
outside the volume must be **gone** after a recreate. That Contabo-specific negative is exactly what
"not boot-tested separately" means: this run proves the method on one platform, and Contabo is asserted
by running the same recipe, not by claiming a second boot here.

---

## 11. Regression (nothing that worked changed)

Same command, same worktree, same environment, before and after this file was rewritten:

```
$ python3 -m pytest -q 75-drama-song-ad-factory/tests
before: 1 failed, 193 passed in 2.52s
after:  1 failed, 193 passed
```

The single failure is pre-existing on the base and is outside this unit's "Owns" line — its file is
`references/studio-e2e-receipt.md`, not this one. Zero new failures; the counts are unchanged.

Repo guards were run against this file too. `bash scripts/qc-assert-no-client-names.sh` reports the same
pre-existing repo-wide hit set as the base, and this file carries no operator home directory: every
operator path above is written `/Users/<operator>/…`, the way `references/studio-e2e-receipt.md` already
writes them. The one name this file does carry is the header line, which TEST-01 specified verbatim for
provenance (which box the test ran on).
