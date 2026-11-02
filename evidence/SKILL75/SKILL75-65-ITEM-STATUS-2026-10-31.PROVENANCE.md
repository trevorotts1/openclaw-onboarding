# Provenance: SKILL75-65-ITEM-STATUS-2026-10-31.txt (ledger row E07, DOC_ONLY)

E07 is the historical status document. It records evidence gaps and is documentation only, not a software repair.

- Original sha256: `e25513f267f88a2385657e8ce8ac5def336b7af8893357d472ba05be8eb77f05` (76216 bytes). This is the digest pinned by ledger row E07 and by the Skill 75 repair dossier, item R5.
- Original location: the operator's Downloads folder, file `SKILL75-65-ITEM-STATUS-2026-10-31.txt`. The original was not edited.
- The copy beside this file is the original with exactly three byte-substitutions, applied in this order. Owner decision D-27 bans host-specific absolute roots in added lines, and the repo's no-client-names gate bans the operator's home path in any spelling, so these were tokenised:
  - the operator's per-session scratch directory (slash private, slash tmp, slash claude-501, slash, then the dash-separated spelling of the operator's home folder, slash) becomes `<ROOT:SESSION-TMP>/` (66 occurrences)
  - the operator's home folder (slash, the word for users, slash, the operator account name, slash) becomes `<ROOT:OPERATOR-HOME>/` (3 occurrences)
  - the macOS external-volume root (slash, the word for volumes, slash) becomes `<ROOT:VOLUMES>/` (66 occurrences)
- None of the three tokens occurs in the original, so each substitution reverses uniquely.
- Sha256 of the tokenised copy in this repo: `0b709c7ca65841fb3806e1399b21c378ea3250de7e5ce51e5410732457fa94da` (74758 bytes).
- To re-derive the original digest: reverse the three substitutions above (volumes first, then operator home, then session scratch) and hash. This was checked to reproduce `e25513f2...` exactly.
- Status of the content: a 2026-10-31 retrospective audit snapshot (1 COMPLETE (E07), 22 PARTIAL, 23 FAILED, 19 NOT_ESTABLISHED). It is not a fresh retest and states no functional repair as verified.
