# Real-Estate Use Cases (prioritized)

Skill 40's record types are prioritized for real-estate workflows. Skill 40
SURFACES these records (with provenance); Skill 39 decides what to do with them.
Skill 40 never runs outreach.

## Priority order

### 1. Pre-foreclosure / Notice-of-Default (NOD)
The highest-value RE signal. A recorded NOD or lis pendens indicates a homeowner
in default. Feeds Skill 39's `pre-foreclosure-outreach-protocol.md` (care-first
outreach). Surface the record + provenance; Skill 39 handles compliance
(cooling-off / consultant-disclosure pointers) and the empathetic outreach.

### 2. Tax delinquency
Owners behind on property taxes — a distressed-seller signal and a list source
for investor clients. Surface the delinquency record + provenance.

### 3. Comps support
Recorded sale prices + dates (deeds/transfers) to SUPPORT a CMA in Skill 39.
Note: recorded deeds give sale price + date, not a full MLS comp set — combine
with Skill 39's provider comps where available. Never fabricate a comp.

### 4. Permits
Open/closed building permits — condition signals, flip indicators, unpermitted-
work flags. Surface the permit record + provenance.

### 5. Tax records
Assessed value + tax history — baseline valuation context.

### 6. Ownership / deeds
Current owner, recent transfers, recorded liens — the foundation record. Useful
for verifying who actually owns a property before outreach.

## Cross-cutting

- Every record carries `source` + `retrieved_at`. No provenance → not a record.
- The RE use cases all route through the same tier model + compliance + cost
  caps. A county with no online DB for, say, permits is an honest gap for that
  record type, even if ownership is available.
- Skill 40 stays in its lane: find + attribute + cache + log. Outreach,
  qualification, and the CMA conversation are Skill 39's job.
