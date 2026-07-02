# SOP-EMAIL-04: QC WITH THE FAIL-CLOSED FLOOR PROVER

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Master authority:** `MASTER-EMAIL-QC-AUTOFAIL-RULESET.md` + `50-email-engine/tools/prove-email.py`
**Owning role:** QC Specialist -- Marketing (verifier != author)
**Stage:** P3-QC
**Produces:** `working/qc/email_qc_report.json`
**Gates this stage satisfies:** the full SACRED battery (see the master ruleset)

---

## 0. WHY THIS SOP EXISTS

QC is a deterministic MEASURER, not an agent self-score — the same principle that makes the presentations char-floor prover trustworthy. The prover measures stripped text and hard-fails on any violation with a named `AF-EMAIL-*` code. Copy cannot advance to P4-DEPLOY until the prover exits 0.

## 1. RUN THE PROVER

```
python3 50-email-engine/tools/prove-email.py working/copy/emails.json
# machine-readable:
python3 50-email-engine/tools/prove-email.py working/copy/emails.json --json
```

- Exit 0 = every SACRED invariant satisfied -> advance to P4.
- Exit 2 = one or more AF-EMAIL-* violations (fail-closed) -> bounce.
- Exit 3 = usage / unreadable JSON (still fail-closed).

The prover auto-detects the input kind (single email / sequence ledger / intake brief); force it with `--kind email|sequence|intake`.

## 2. BOUNCE ONLY THE FAILING ITEM

Each failure names an email (`E7:`) and a code. Re-author ONLY the failing email against the named rule (bounded retry cap), then re-run the prover. Do NOT rewrite passing emails.

## 3. THE VERIFIER IS NOT THE AUTHOR

Independent verification is mandatory: the reviewer that stamps QC is not the copywriter who wrote the email (mirrors the fleet AF-QC-INDEPENDENCE rule). Record the QC report at `working/qc/email_qc_report.json` (the prover `--json` output plus the independence block).

## 4. NEVER FLOOR/CAP-CHANGE THE REQUEST

The bands are exactly as written. If the owner asked for an exact length, that is a logged `word_band_override` on the email (recorded on the certificate) — never a silent relaxation of the SACRED default. The prover is authoritative: reconcile the copy to the prover, never the prover to the copy.
