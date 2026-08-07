// ============================================================================
// Book Writer mini-app — U18 stub GHL endpoint (browser-level isolation proof)
// ----------------------------------------------------------------------------
// In-process stand-in for GoHighLevel. It RECORDS EVERY write it sees, keyed by
// the `location_id` that travels with the request, so T10 can PROVE — in the
// browser flow — that alpha's answers land ONLY on location-alpha and beta's
// ONLY on location-beta. It also REFUSES any write whose bearer token does not
// match the payload's location (defense in depth at the transport, mirroring
// U15/Skill-44 rails).
//
// The stub never leaves this process: no real GHL is ever contacted, no real
// creds/hosts, no Anthropic ids. Fictitious locations only.
// ============================================================================

// location -> { token, notes: [], contacts: [] , refused: [] }
export class GhlStub {
  constructor() {
    this.locations = new Map();
    this.sequence = 0;
  }

  registerLocation(locationId, token) {
    this.locations.set(locationId, {
      token,
      notes: [],
      contacts: [],
      refused: [],
    });
  }

  // Record every request the stub sees (contact write, note write, refused
  // attempt) so a PROVEN NEGATIVE is auditable: alpha never sees beta.
  hits() {
    const out = { total: 0, byLocation: {} };
    for (const [loc, row] of this.locations.entries()) {
      const n = row.notes.length + row.contacts.length + row.refused.length;
      out.byLocation[loc] = {
        notes: row.notes.length,
        contacts: row.contacts.length,
        refused: row.refused.length,
        total: n,
      };
      out.total += n;
    }
    return out;
  }

  // One contact write per client+email, then the answer fields as notes.
  async writeContact(payload) {
    this.sequence += 1;
    const seq = this.sequence;
    const locationId = payload.location_id;
    const row = this.locations.get(locationId);
    if (!row) {
      return { ok: false, status: 404, error: 'unknown location' };
    }
    if (payload.auth_token && payload.auth_token !== row.token) {
      row.refused.push({ seq, reason: 'auth-mismatch', payload });
      return { ok: false, status: 401, error: 'auth mismatch' };
    }
    row.contacts.push({ seq, ...payload, received_at: Date.now() });
    return { ok: true, status: 201, contact_id: `contact_${locationId}_${seq}` };
  }

  async writeNote(payload) {
    this.sequence += 1;
    const seq = this.sequence;
    const locationId = payload.location_id;
    const row = this.locations.get(locationId);
    if (!row) {
      return { ok: false, status: 404, error: 'unknown location' };
    }
    if (payload.auth_token && payload.auth_token !== row.token) {
      row.refused.push({ seq, reason: 'auth-mismatch', payload });
      return { ok: false, status: 401, error: 'auth mismatch' };
    }
    row.notes.push({ seq, ...payload, received_at: Date.now() });
    return { ok: true, status: 201, note_id: `note_${locationId}_${seq}` };
  }

  // All answers a given location ever received (for assertions).
  answersFor(locationId) {
    const row = this.locations.get(locationId);
    if (!row) return [];
    return row.notes.concat(row.contacts);
  }

  reset() {
    for (const row of this.locations.values()) {
      row.notes = [];
      row.contacts = [];
      row.refused = [];
    }
    this.sequence = 0;
  }
}

export const GHL = new GhlStub();
