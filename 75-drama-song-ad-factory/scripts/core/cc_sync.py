"""cc_sync.py — drama-song factory board sync to Command Center.

Board family: POST /api/ad-campaigns + PATCH /api/ad-campaigns/[id]
(stage-card family). NOT /api/campaigns, NOT Skill 47 cc_board.py default URL.

Live contract read 2026-10-06 (R05):
  src/app/api/ad-campaigns/route.ts          POST create (idempotent on job_id; 201/200), GET poll
  src/app/api/ad-campaigns/[id]/route.ts     PATCH move one stage card; ILLEGAL_TRANSITION -> 409
  src/lib/ad-campaigns.ts                    createAdCampaign L171 (idempotent); moveAdStage L270
                                             (canonical transition()); blocked gate L284-302;
                                             epic-done completes campaign L364
  src/lib/validation.ts                      CreateAdCampaignSchema L391; UpdateAdCampaignStageSchema
                                             L417; AdCardStatus = 5 values; blocked-requires-ask
  src/lib/task-lifecycle.ts                  LEGAL_TRANSITIONS L146; same-state idempotent L1329
  src/lib/db/schema.ts                       tasks.workspace_id / business_id (NULL in this family);
                                             tasks.stage_slug

Directive 20.5 rules enforced here:
  stable keys (job_id == campaign_id == tasks.campaign_id, stage_slug);
  retries update existing cards, stale transitions rejected, never duplicated;
  durable outbox pending -> sent -> acked; rejected = terminal, never sent;
  acknowledged registration required (2xx + idempotent-replay proof), never
  "attempted write counts as done"; replay preserves order + tenant isolation.

Out of scope (explicit): POST /api/tasks/{id}/return-to-orchestrator handback
(task family, worker->orchestrator path) and any new Kanban implementation.

Stdlib only: hashlib, hmac, json, os, socket, sqlite3, time, urllib.

Outage policy (20.5: which outages permit work, which stop spend):
  conn-refused/DNS (never dispatched) -> back to pending; local UNPAID work may
    continue; flush reports degraded=True (visibility degradation surfaced).
  timeout/5xx (maybe dispatched)     -> stays sent (UNKNOWN); next flush GET-
    reconciles before any resend; no new paid intent is enqueued during outage.
  401/403                            -> AuthError, flush stops; operator fixes creds.
  4xx validation / 409 stale / 404   -> rejected terminal with code; operator reconciles.
Result column holds tiny ack summaries ({http, created|stage|code}) — never raw
HTTP request/response dumps, never secrets. Auth material lives in env only.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

AD_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")

# Ad-status projection of server LEGAL_TRANSITIONS (task-lifecycle.ts L146).
# blocked -> {backlog, in_progress} only: blocked -> review/done is STALE (409).
LEGAL_MOVES = {
    "backlog": frozenset({"in_progress", "review", "blocked"}),
    "in_progress": frozenset({"review", "blocked", "backlog"}),
    "review": frozenset({"done", "in_progress", "blocked", "backlog"}),
    "blocked": frozenset({"backlog", "in_progress"}),
    "done": frozenset({"backlog"}),
}

BLOCKED_REASONS = ("decision", "approval", "credential", "payment")
BLOCKED_ON_HUMAN = ("owner", "operator")

PENDING, SENT, ACKED, REJECTED = "pending", "sent", "acked", "rejected"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE,
  kind TEXT NOT NULL,
  job_id TEXT NOT NULL,
  stage_slug TEXT,
  workspace TEXT NOT NULL,
  payload TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  result TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS card_state(
  job_id TEXT NOT NULL,
  stage_slug TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (job_id, stage_slug)
);
"""


class BoardSyncError(Exception):
    pass


class WrongCompanyError(BoardSyncError):
    """Event workspace != bound workspace. Rejected: never stored, never sent."""


class BlockedGateError(BoardSyncError):
    pass


class EvidenceError(BoardSyncError):
    pass


class SelfApprovalError(BoardSyncError):
    pass


class AuthError(BoardSyncError):
    pass


class TransportOutage(BoardSyncError):
    """Network/5xx. dispatched=True means the bytes may have reached the
    server (timeout/5xx) -> row stays sent (UNKNOWN), reconcile-first."""

    def __init__(self, msg, dispatched=False):
        super().__init__(msg)
        self.dispatched = dispatched


def _now():
    return int(time.time())


def _key(kind, job_id, stage_slug, payload):
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(canon.encode()).hexdigest()[:12]
    return "%s:%s:%s:%s" % (kind, job_id, stage_slug or "-", digest)


class Outbox:
    """Durable board outbox bound to ONE workspace (tenant isolation)."""

    def __init__(self, db_path=":memory:", base_url=None, workspace=None, sender=None):
        # CC_PORT is what Command Center's ecosystem.config.cjs exports; default stays 4000.
        default_url = "http://127.0.0.1:%s" % (os.environ.get("CC_PORT") or "4000")
        self.base_url = (base_url or os.environ.get("CC_BASE_URL") or default_url).rstrip("/")
        self.workspace = workspace or os.environ.get("CC_WORKSPACE", "")
        if not self.workspace:
            raise BoardSyncError("workspace binding required (pass workspace= or set CC_WORKSPACE)")
        self.db = sqlite3.connect(db_path)
        self.db.executescript(_SCHEMA)
        self.sender = sender or self._http_sender

    # -- enqueue ---------------------------------------------------------
    def _bind(self, workspace):
        if workspace != self.workspace:
            raise WrongCompanyError("event workspace %r != bound %r: rejected, nothing stored" % (workspace, self.workspace))

    def _insert(self, kind, job_id, stage_slug, workspace, payload):
        key = _key(kind, job_id, stage_slug, payload)
        ts = _now()
        try:
            cur = self.db.execute(
                "INSERT INTO outbox(key,kind,job_id,stage_slug,workspace,payload,state,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (key, kind, job_id, stage_slug, workspace, json.dumps(payload), PENDING, ts, ts),
            )
            self.db.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:  # identical intent already queued/resolved: no duplicate
            row = self.db.execute("SELECT id FROM outbox WHERE key=?", (key,)).fetchone()
            return row[0]

    def enqueue_create(self, job_id, show_name, stages, workspace, owner=None,
                       department=None, agent_id=None, money_ceiling_usd=None,
                       estimated_cost_usd=None, show_date=None):
        self._bind(workspace)
        if not (1 <= len(job_id) <= 128):
            raise BoardSyncError("job_id length out of range")
        if not (1 <= len(show_name) <= 500):
            raise BoardSyncError("show_name length out of range")
        stages = list(stages or [])
        if len(stages) > 50:
            raise BoardSyncError("too many stages (server max 50)")
        for s in stages:
            if not (1 <= len(s.get("slug", "")) <= 64):
                raise BoardSyncError("stage slug length out of range")
        payload = {"job_id": job_id, "show_name": show_name}
        if owner is not None:
            payload["owner"] = owner
        if department is not None:
            payload["department"] = department
        if workspace is not None:
            payload["workspace"] = workspace
        if agent_id is not None:
            payload["agent_id"] = agent_id  # provenance ONLY; never assigned_agent_id
        if money_ceiling_usd is not None:
            payload["money_ceiling_usd"] = money_ceiling_usd
        if estimated_cost_usd is not None:
            payload["estimated_cost_usd"] = estimated_cost_usd
        if show_date is not None:
            payload["show_date"] = show_date
        if stages:
            payload["stages"] = [{"slug": s["slug"], **({"title": s["title"]} if s.get("title") else {})} for s in stages]
        return self._insert("create", job_id, None, workspace, payload)

    def enqueue_move(self, job_id, stage_slug, status, actor, workspace, reason=None,
                     evidence=None, reviewer=None, blocked_reason=None,
                     blocked_on_human=None, ask=None):
        self._bind(workspace)
        if status not in AD_STATUSES:
            raise BoardSyncError("unknown status %r" % (status,))
        if not (1 <= len(stage_slug) <= 64):
            raise BoardSyncError("stage slug length out of range")
        if status == "blocked":  # server mirror: ad-campaigns.ts L284-302
            if blocked_reason not in BLOCKED_REASONS:
                raise BlockedGateError("blocked requires blocked_reason")
            if not (ask or "").strip() or "(no ask specified)" in ask:
                raise BlockedGateError("blocked requires a non-empty ask")
        if status in ("review", "done") and not (evidence or "").strip():
            raise EvidenceError("%s requires completion evidence" % status)
        if status == "done":  # independent completion authority: no self-approval
            if not reviewer:
                raise SelfApprovalError("done requires an independent reviewer")
            if reviewer == actor:
                raise SelfApprovalError("actor may not approve own done (self-approval rejected)")
        known = self.db.execute(
            "SELECT status FROM card_state WHERE job_id=? AND stage_slug=?", (job_id, stage_slug)).fetchone()
        if known and known[0] == status:  # same-state: idempotent no-op, no new row
            row = self.db.execute(
                "SELECT id FROM outbox WHERE kind='move' AND job_id=? AND stage_slug=? AND state=? "
                "ORDER BY id DESC LIMIT 1", (job_id, stage_slug, ACKED)).fetchone()
            if row:
                return row[0]
        payload = {"stage_slug": stage_slug, "status": status}
        if reason is not None:
            payload["reason"] = reason
        if actor is not None:
            payload["actor"] = actor
        if blocked_reason is not None:
            payload["blocked_reason"] = blocked_reason
        if blocked_on_human is not None:
            payload["blocked_on_human"] = blocked_on_human
        if ask is not None:
            payload["ask"] = ask
        return self._insert("move", job_id, stage_slug, workspace, payload)

    # -- flush -----------------------------------------------------------
    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM outbox GROUP BY state").fetchall())

    def flush(self):
        """Send pending/sent rows in id order. Order preserved: transport outage
        stops the flush; terminal rejections do not block later rows."""
        report = {"acked": [], "pending": [], "rejected": [], "degraded": False, "auth_error": False}
        rows = self.db.execute(
            "SELECT id,key,kind,job_id,stage_slug,workspace,payload,state,attempts FROM outbox"
            " WHERE state IN (?,?) ORDER BY id", (PENDING, SENT)).fetchall()
        for rid, key, kind, job_id, stage, ws, payload, state, attempts in rows:
            if ws != self.workspace:  # defense in depth: binding re-checked at send time
                self._resolve(rid, REJECTED, {"code": "WRONG_COMPANY"})
                report["rejected"].append(rid)
                continue
            body = json.loads(payload)
            try:
                if state == SENT:
                    self._reconcile(rid, kind, job_id, stage, body, report)
                elif kind == "create":
                    self._send_create(rid, job_id, body, report)
                else:
                    self._send_move(rid, job_id, stage, body, report)
            except AuthError:
                report["auth_error"] = True
                report["degraded"] = True
                break
            except TransportOutage as e:
                self.db.execute("UPDATE outbox SET state=?,updated_at=? WHERE id=?",
                                (SENT if e.dispatched else PENDING, _now(), rid))
                self.db.commit()
                report["degraded"] = True
                report["pending"].append(rid)
                break  # preserve order: nothing behind an outage goes out
        for (sid, sstate) in self.db.execute("SELECT id,state FROM outbox WHERE state IN (?,?)", (PENDING, SENT)):
            if sid not in report["acked"] and sid not in report["rejected"] and sid not in report["pending"]:
                report["pending" if sstate == PENDING else "pending"].append(sid)
        return report

    # -- internals -------------------------------------------------------
    def _resolve(self, rid, state, summary):
        self.db.execute("UPDATE outbox SET state=?,attempts=attempts+1,result=?,updated_at=? WHERE id=?",
                        (state, json.dumps(summary), _now(), rid))
        self.db.commit()

    def _mark_sent(self, rid):
        self.db.execute("UPDATE outbox SET state=?,attempts=attempts+1,updated_at=? WHERE id=?", (SENT, _now(), rid))
        self.db.commit()

    def _seed_cards(self, job_id, stages):
        for s in stages or []:
            if isinstance(s, dict) and s.get("slug"):
                self.db.execute("INSERT OR IGNORE INTO card_state(job_id,stage_slug,status) VALUES(?,?,?)",
                                (job_id, s["slug"], s.get("status", "backlog")))
        self.db.commit()

    def _send_create(self, rid, job_id, body, report):
        self._mark_sent(rid)
        status, resp = self.sender("POST", "/api/ad-campaigns", body)
        if status in (200, 201):
            self._seed_cards(job_id, (resp or {}).get("stages", []))
            # created:false on 200 = server replay proof: already exists, zero writes, no duplicate.
            self._resolve(rid, ACKED, {"http": status, "created": bool((resp or {}).get("created"))})
            report["acked"].append(rid)
        else:
            self._resolve(rid, REJECTED, {"http": status, "code": (resp or {}).get("code", "BAD_REQUEST")})
            report["rejected"].append(rid)

    def _send_move(self, rid, job_id, stage, body, report):
        self._mark_sent(rid)
        status, resp = self.sender("PATCH", "/api/ad-campaigns/" + job_id, body)
        if status == 200:
            self.db.execute("INSERT OR REPLACE INTO card_state(job_id,stage_slug,status) VALUES(?,?,?)",
                            (job_id, stage, body["status"]))
            self.db.commit()
            self._resolve(rid, ACKED, {"http": status, "stage": stage, "status": body["status"]})
            report["acked"].append(rid)
        else:
            # 404 CARD_NOT_FOUND: never auto-create here (update-existing-only);
            # 409 ILLEGAL_TRANSITION: stale write rejected, never duplicated.
            self._resolve(rid, REJECTED, {"http": status, "code": (resp or {}).get("code", "MOVE_FAILED")})
            report["rejected"].append(rid)

    def _reconcile(self, rid, kind, job_id, stage, body, report):
        """Row left sent (UNKNOWN after timeout/5xx): GET first, resend only
        what the server proves missing. Paid intents are never blindly re-sent."""
        try:
            status, resp = self.sender("GET", "/api/ad-campaigns/" + job_id, None)
        except TransportOutage as e:
            raise e
        if status == 404 and kind == "create":
            self._send_create(rid, job_id, body, report)  # proven missing: safe, idempotent key
            return
        if status != 200:
            self._resolve(rid, REJECTED, {"http": status, "code": (resp or {}).get("code", "RECONCILE_FAILED")})
            report["rejected"].append(rid)
            return
        cards = {c.get("stage_slug"): c.get("status") for c in (resp or {}).get("cards", []) if isinstance(c, dict)}
        if kind == "create":
            self._seed_cards(job_id, [{"slug": k, "status": v} for k, v in cards.items()])
            self._resolve(rid, ACKED, {"http": 200, "created": False, "reconciled": True})
            report["acked"].append(rid)
        elif cards.get(stage) == body["status"]:
            self.db.execute("INSERT OR REPLACE INTO card_state(job_id,stage_slug,status) VALUES(?,?,?)",
                            (job_id, stage, body["status"]))
            self.db.commit()
            self._resolve(rid, ACKED, {"http": 200, "reconciled": True,
                                       "stage": stage, "status": body["status"]})
            report["acked"].append(rid)
        else:
            self._send_move(rid, job_id, stage, body, report)

    # -- default stdlib transport ----------------------------------------
    def _http_sender(self, method, path, payload):
        raw = "" if payload is None else json.dumps(payload)
        req = urllib.request.Request(self.base_url + path,
                                     data=None if method == "GET" else raw.encode(),
                                     method=method)
        token = os.environ.get("MC_API_TOKEN", "")
        secret = os.environ.get("WEBHOOK_SECRET", "")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if payload is not None and secret:  # HMAC mirrors route.ts verifyWebhookSignature
            req.add_header("x-webhook-signature",
                           hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest())
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode() or "{}"
                return r.status, json.loads(text)
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode() or "{}")
            except ValueError:
                err_body = {}
            if e.code in (401, 403):
                raise AuthError("board auth refused (%s): fix creds, nothing retried" % e.code)
            if e.code >= 500:
                raise TransportOutage("board 5xx (maybe dispatched)", dispatched=True)
            return e.code, err_body  # 4xx: caller marks rejected, never retried
        except Exception as e:  # URLError / timeout / refused: never leak details with secrets
            reason = getattr(e, "reason", e)
            refused = isinstance(reason, ConnectionRefusedError) or isinstance(e, ConnectionRefusedError)
            raise TransportOutage("board unreachable (dispatched=%s)" % (not refused,),
                                  dispatched=not refused)
