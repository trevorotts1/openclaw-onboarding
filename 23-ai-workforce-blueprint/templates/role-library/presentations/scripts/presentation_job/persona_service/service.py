"""PersonaService — explicit portable persona runtime (PRES-053).

Preserves Skill22 runtime blueprints/catalog/section maps and Skill23
voice/topic/governing/per-part blend semantics by delegating to the
vendored Skill23 scripts loaded BY PATH from an explicit resource root.
No monorepo/live-path discovery, no operator SOUL/USER fallback, no
global DB. Scoring/storage/auth are injected adapters with honest
method reporting.

Frozen upstream behavior kept intact (persona.py / blend_voice_governance /
persona_for_job untouched — this is the new explicit entry, not a fork).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import (
    CredentialResolver,
    FileStorage,
    HEURISTIC_METHOD,
    MODULE_MISSING_METHOD,
    NEUTRAL_METHOD,
    NullCredentialResolver,
    NullStorage,
    ScoringAdapter,
    StorageAdapter,
    read_recent_use_counts,
)
from .bundle import PersonaReceipt, verify_bundle_integrity
from .catalog import PackagedCatalog
from .context import PersonaContext, content_hash, scopes_for_context
from .policy import NARRATIVE_PHASE_FOR, policy_for_phase

_HERE = Path(__file__).resolve().parent

# Vendored Skill23 script names (loaded by path from resource_root;
# hyphenated names cannot be imported — same trick the selector uses).
VENDORED_MODULES = (
    "persona-selector-v2.py",
    "persona_blend.py",
    "decompose-task.py",
    "infer-task-category.py",
)

# Transitive shared-utils helpers (provenance-recorded; loaded by path).
# secret_helper.py + secret_names.json = secret-name canon (llm_score);
# embedding_engine.py = model slug + credential-error taxonomy (semantic).
VENDORED_HELPERS = (
    "mechanical-gate.py",
    "llm_score.py",
    "semantic_task_fit.py",
    "adaptive_weights.py",
    "canonical_slug.py",
    "detect_platform.py",
    "resolve_db.py",
    "secret_helper.py",
    "embedding_engine.py",
)
VENDORED_HELPER_DATA = (
    "secret_names.json",
)

# Credential names the service may resolve (explicit allow-list; the
# resolver enforces it — unknown names return '').
CREDENTIAL_NAMES = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_CLOUD_API_KEY",
    "OLLAMA_CLOUD_URL",
    "OPENROUTER_API_KEY",
)


class PersonaServiceError(RuntimeError):
    pass


class PersonaService:
    """Explicit persona runtime bound to one packaged resource root."""

    def __init__(self, resource_root: Path | str, *,
                 storage: Optional[StorageAdapter] = None,
                 credentials: Optional[CredentialResolver] = None,
                 scoring: Optional[ScoringAdapter] = None,
                 scripts_dir: Optional[Path | str] = None,
                 helpers_dir: Optional[Path | str] = None,
                 execution_id: str = "") -> None:
        self.resource_root = Path(resource_root)
        self.catalog = PackagedCatalog(self.resource_root / "personas")
        self.scripts_dir = Path(scripts_dir) if scripts_dir else (
            self.resource_root / "scripts")
        self.helpers_dir = Path(helpers_dir) if helpers_dir else (
            self.resource_root / "helpers")
        self.storage = storage or NullStorage()
        self.credentials = credentials or NullCredentialResolver()
        self.scoring = scoring  # may be None -> selector-native scoring
        self.execution_id = execution_id or f"persona-{os.getpid()}"
        self._modules: Dict[str, Any] = {}
        self._active_paths: Optional[dict] = None

    # -- module loading (by path, cached, never sys.modules-global) --------
    def _load(self, name: str, directory: Path):
        key = f"{directory}/{name}"
        if key not in self._modules:
            path = directory / name
            if not path.is_file():
                raise PersonaServiceError(
                    f"required vendored module missing: {path} — "
                    f"reinstall the packaged persona resources")
            modname = ("persona_service_" +
                       name.replace("-", "_").replace(".py", ""))
            spec = importlib.util.spec_from_file_location(modname, str(path))
            mod = importlib.util.module_from_spec(spec)
            # Vendored scripts do bare `from detect_platform import ...`
            # against the monorepo shared-utils (selector lines 60-61 even
            # prepend <their-own-dir>/../../shared-utils). Keep those imports
            # pointed at the PACKAGED helpers for the whole load: helpers dir
            # must win over anything the module itself prepends, so hold it
            # for the duration AND re-assert after exec (a module-level
            # insert(0) during exec would otherwise outrank it — helpers and
            # scripts have disjoint basenames so order between them is
            # irrelevant, only that both precede foreign shared-utils).
            sys.path.insert(0, str(self.helpers_dir))
            sys.path.insert(0, str(directory))
            try:
                spec.loader.exec_module(mod)
            finally:
                for entry in (str(directory), str(self.helpers_dir)):
                    try:
                        while entry in sys.path:
                            sys.path.remove(entry)
                    except ValueError:
                        pass
            self._modules[key] = mod
        return self._modules[key]


    def _blend(self):
        # Preload packaged helpers under their bare basenames FIRST: the
        # vendored scripts' own `sys.path.insert(../../shared-utils)` would
        # otherwise rebind `detect_platform` etc. to the MONOREPO copies
        # whenever those are importable (pytest runs, operator box).
        # sys.modules hits win over path scans, so preloading pins ours.
        # The vendored decompose-task ALSO re-exports selector-bound
        # get_openclaw_paths/find_dashboard_db (module import time) and its
        # combined_select() calls them with NO paths argument — patch those
        # two bindings to the service's scoped resolvers so the per-part
        # path can never reach a live root either.
        self._preload_pinned_helpers()
        blend = self._load("persona_blend.py", self.scripts_dir)
        self._scope_decompose_bindings()
        return blend

    def _scope_decompose_bindings(self) -> None:
        """Point the vendored decompose-task's live-root bindings at the
        service's scoped resolvers. decompose-task.py binds
        get_openclaw_paths/find_dashboard_db/is_db_found from the selector
        at import time and combined_select() calls them with no arguments —
        without this patch the per-part task-persona path would resolve
        live operator roots (and SystemExit(1) where none exist).

        The decompose/selector modules live INSIDE the blend module's
        namespace (blend._decompose()/_selector() caches: module objects
        named decompose_task_blend / persona_selector_v2_blend), NOT in
        self._modules — so walk those caches too."""
        import pathlib as _pl
        scoped_paths = self._scoped_paths_fn
        scoped_db = self._scoped_db_fn
        scoped_is_found = (lambda p: bool(p) and str(p) not in ("", ".")  # noqa: E731
                           and _pl.Path(p).exists())
        seen = set()

        def _patch(mod) -> None:
            if id(mod) in seen:
                return
            seen.add(id(mod))
            for attr, fn in (("get_openclaw_paths", scoped_paths),
                             ("find_dashboard_db", scoped_db),
                             ("is_db_found", scoped_is_found)):
                try:
                    setattr(mod, attr, fn)
                except Exception:
                    pass
            # record_selection() writes to the GLOBAL selection log
            # (find_selection_log -> ~/.openclaw) AND the passed db. Point
            # the log locator at scoped storage; the db arg is already
            # ours (service passes scoped db / Path('')).
            try:
                _find_log = getattr(mod, "find_selection_log", None)
                if callable(_find_log):
                    _scope = (self._active_paths or {}).get(
                        "workspace", None)
                    def _scoped_log(_s=_scope):
                        import pathlib as _p
                        base = _p.Path(_s) if _s else _p.Path(".")
                        return base / "persona-selection-log.md"
                    mod.find_selection_log = _scoped_log  # type: ignore
            except Exception:
                pass

        for mod in list(self._modules.values()):
            _patch(mod)
            for cache in ("_SEL", "_DT"):
                try:
                    inner = getattr(mod, cache, None)
                except Exception:
                    inner = None
                if inner is not None:
                    _patch(inner)
        # Blend's own module-level _selector()/_decompose() singletons: the
        # functions close over module globals, so patch via the blend module
        # object directly as well.
        try:
            blend = self._modules.get(str(self.scripts_dir / "persona_blend.py"))
            if blend is not None:
                for factory in ("_selector", "_decompose"):
                    try:
                        inner = getattr(blend, factory, lambda: None)()
                    except Exception:
                        inner = None
                    if inner is not None:
                        _patch(inner)
        except Exception:
            pass

    def _scoped_paths_fn(self) -> dict:
        if self._active_paths is None:
            raise PersonaServiceError(
                "scoped paths requested outside resolve() — live-root "
                "discovery is disabled in PersonaService")
        return self._active_paths

    def _scoped_db_fn(self):
        if self._active_paths is None:
            raise PersonaServiceError(
                "scoped db requested outside resolve() — global dashboard "
                "DB is unreachable from PersonaService")
        return self._active_paths.get("dashboard_db")

    def _preload_pinned_helpers(self) -> None:
        """Import packaged helpers by path under their canonical basenames
        so subsequent bare `from X import ...` inside vendored scripts hit
        sys.modules (OUR bytes) instead of scanning sys.path (which the
        monorepo shared-utils may shadow). Pins: detect_platform,
        resolve_db, adaptive_weights, canonical_slug, llm_score,
        semantic_task_fit, secret_helper, embedding_engine. Also pins the
        mechanical-gate/selection helpers via the scripts dir? No — those
        are hyphenated and always loaded by path; only underscored
        basenames need pinning. Idempotent per process."""
        for name in ("detect_platform", "resolve_db", "adaptive_weights",
                     "canonical_slug", "llm_score", "semantic_task_fit",
                     "secret_helper", "embedding_engine"):
            if name in sys.modules:
                continue
            path = self.helpers_dir / f"{name}.py"
            if not path.is_file():
                continue
            spec = importlib.util.spec_from_file_location(name, str(path))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception:
                del sys.modules[name]

    # -- paths dict (explicit; never _live_paths) ---------------------------
    def _paths(self, ctx: PersonaContext) -> dict:
        scope = scopes_for_context(ctx)
        work = self.storage.db_path(scope).parent
        return {
            "persona_categories": self.catalog.catalog_path,
            "coaching_personas": self.resource_root / "personas",
            "company_config": work / "company-config.json",
            "soul_md": work / "SOUL.md",
            "user_md": work / "USER.md",
            "skills": self.resource_root.parent,
            "workspace": work,
            "secrets": work / "secrets",
            "gemini_index": work / "gemini-index.sqlite",
            "dashboard_db": self.storage.db_path(scope),
        }

    def _write_scoped_company_files(self, ctx: PersonaContext, paths: dict) -> None:
        """Materialize the EXPLICIT company config into the scoped dir so
        vendored code that reads paths['company_config'] sees OUR bytes."""
        cfg_path = Path(paths["company_config"])
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg = dict(ctx.company_config or {})
        cfg.setdefault("schema_version", "2.0")
        cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True),
                            encoding="utf-8")

    # -- resolve ------------------------------------------------------------
    def resolve(self, ctx: PersonaContext) -> PersonaReceipt:
        """Resolve the persona bundle for an explicit client context."""
        if not ctx.company_id or not ctx.presentation_id:
            raise PersonaServiceError(
                "company_id and presentation_id are required (no implicit "
                "operator company fallback)")
        policy = policy_for_phase(ctx.phase)
        if policy["kind"] == "human-gate":
            return self._human_gate_receipt(ctx, policy)

        paths = self._paths(ctx)
        self._write_scoped_company_files(ctx, paths)
        self._active_paths = paths
        try:
            blend = self._blend()
        finally:
            pass  # _active_paths stays live for the whole resolve()
        audience_override = ctx.audience_override or ctx.audience or ""

        hermetic = ctx.hermetic
        old_scoring = os.environ.get("SCORING_MODE")
        old_match_log = os.environ.get("OPENCLAW_PERSONA_MATCH_SCORE_LOG")
        try:
            # Match-score observability log -> scoped storage, never the
            # packaged coaching_personas dir (which must stay a pristine
            # content-addressed resource set).
            scope = scopes_for_context(ctx)
            os.environ["OPENCLAW_PERSONA_MATCH_SCORE_LOG"] = str(
                self.storage.db_path(scope).parent / "match-score-log.jsonl")
            if hermetic:
                # Deterministic hermetic mode: heuristic scoring, no LLM,
                # no record writes into foreign stores.
                os.environ["SCORING_MODE"] = "heuristic"
            bundle = blend.build_bundle(
                ctx.task_text(), "presentations",
                paths=paths,
                db_path=(Path("") if hermetic
                         else self.storage.db_path(scopes_for_context(ctx))),
                use_llm=(False if hermetic else True),
                record=False,  # service records into SCOPED storage itself
                variety=(False if hermetic else True),
                topic_hint=(ctx.topic or ""),
                audience_override=audience_override,
                conversion_goal=(ctx.offer or ""),
            )
        finally:
            if old_scoring is None:
                os.environ.pop("SCORING_MODE", None)
            else:
                os.environ["SCORING_MODE"] = old_scoring
            if old_match_log is None:
                os.environ.pop("OPENCLAW_PERSONA_MATCH_SCORE_LOG", None)
            else:
                os.environ["OPENCLAW_PERSONA_MATCH_SCORE_LOG"] = old_match_log

        # Client sovereignty: an express client voice is FINAL.
        if ctx.client_persona_id and (ctx.client_persona_source or "").strip().lower() in (
                "client-choice", "client", "locked", "config-named", "express"):
            bundle = dict(bundle)
            bundle["persona_id"] = ctx.client_persona_id
            bundle["source"] = "client-choice"
            voice = dict(bundle.get("voice") or {})
            voice["collapsed"] = True
            voice["collapsed_persona_id"] = ctx.client_persona_id
            bundle["voice"] = voice

        # Per-part governance (declared parts only — never invented).
        per_part: List[dict] = []
        if ctx.parts:
            per_part = self._resolve_parts(ctx, paths, blend, bundle)

        # QC independence: reviewer must differ from producer voice.
        if policy["kind"] == "qc-independent":
            bundle = self._enforce_qc_independence(ctx, policy, paths, bundle)

        receipt = self._to_receipt(ctx, policy, bundle, per_part, audience_override)
        self._record(ctx, receipt)
        self._active_paths = None
        return receipt

    def _resolve_parts(self, ctx, paths, blend, bundle) -> List[dict]:
        out: List[dict] = []
        for i, part in enumerate(ctx.parts):
            if not isinstance(part, dict):
                continue
            part_id = str(part.get("part_id") or f"part-{i + 1}")
            pb = blend.build_bundle(
                ctx.task_text(), "presentations",
                paths=paths, db_path=Path(""),
                use_llm=False, record=False, variety=False,
                topic_hint=(part.get("topic_hint") or ctx.topic or ""),
                audience_override=(part.get("audience_hint")
                                   or ctx.audience_override or ctx.audience or ""),
                scope_hint={"part_id": part_id},
            )
            voice = pb.get("voice") or {}
            out.append({
                "seq": i + 1,
                "part_id": part_id,
                "part_role": part.get("part_role", ""),
                "persona_id": pb.get("persona_id"),
                "topic_persona_id": (voice.get("topic_persona") or {}).get("id"),
                "why": ((pb.get("rationale") or {}).get("scope")
                        or (pb.get("rationale") or {}).get("collapse", "")),
                "bundle_hash": _hash_dict(pb),
            })
        return out

    def _enforce_qc_independence(self, ctx, policy, paths, bundle) -> dict:
        """A QC reviewer MUST differ from the producer voice.

        When the resolved reviewer voice equals the producer's cached
        voice, the reviewer is re-resolved once with a disjoint topic
        hint (QC craft, not the producer's topic); if it STILL collides,
        the governance reviewer is pinned and the collision is warned.
        Either way the receipt records what actually happened — never a
        claim of independence that did not occur.
        """
        producer_phase = policy.get("independent_of", "")
        producer_voice = ""
        if producer_phase:
            scope = scopes_for_context(ctx)
            prev = self.storage.read_json(scope, f"receipt-{producer_phase}.json")
            if isinstance(prev, dict):
                producer_voice = prev.get("voice_persona_id", "")
        voice = bundle.get("persona_id", "")
        if producer_voice and voice and voice == producer_voice:
            blend = self._blend()
            retry = blend.build_bundle(
                f"QC review craft for phase {producer_phase}. "
                f"Independent reviewer judgement, quality control method.",
                "presentations", paths=paths, db_path=Path(""),
                use_llm=False, record=False, variety=False,
                topic_hint="quality control review method",
                audience_override="",
            )
            new_voice = retry.get("persona_id", "")
            if new_voice and new_voice != producer_voice:
                bundle = dict(retry)
                bundle.setdefault("rationale", {})["qc_independence"] = (
                    f"re-resolved: reviewer '{new_voice}' differs from "
                    f"producer {producer_phase} voice '{producer_voice}'")
            else:
                bundle = dict(bundle)
                bundle["persona_id"] = "covey-7-habits"
                bundle.setdefault("warnings", []).append(
                    f"qc-independence: reviewer voice matched producer voice "
                    f"'{producer_voice}' from {producer_phase} even after "
                    f"re-resolve; pinned to governance reviewer "
                    f"'covey-7-habits'")
                bundle.setdefault("rationale", {})["qc_independence"] = (
                    f"pinned: reviewer is governance 'covey-7-habits', "
                    f"independent of producer {producer_phase} voice "
                    f"'{producer_voice}'")
        else:
            bundle = dict(bundle)
            bundle.setdefault("rationale", {})["qc_independence"] = (
                f"reviewer voice '{voice}' independent of producer "
                f"'{producer_voice or 'unrecorded'}'")
        return bundle

    def _human_gate_receipt(self, ctx, policy) -> PersonaReceipt:
        return PersonaReceipt(
            company_id=ctx.company_id, presentation_id=ctx.presentation_id,
            run_id=ctx.run_id, phase=ctx.phase, role=ctx.role,
            context_hash=ctx.context_hash(),
            content_version=self.catalog.content_version(),
            execution_id=self.execution_id,
            no_persona_required=True,
            governing_persona_id="",
            policy=policy,
            warnings=["human-gate phase: owner decides; no persona resolved"],
            rationale={"note": "human-gate phase — owner decision pending"},
        )

    def _to_receipt(self, ctx, policy, bundle, per_part, audience_override) -> PersonaReceipt:
        voice = bundle.get("voice") or {}
        vp = voice.get("collapsed_persona_id") if voice.get("collapsed") else (
            (voice.get("audience_persona") or {}).get("id")
            or bundle.get("persona_id", ""))
        tp = ((voice.get("topic_persona") or {}).get("id")
              or bundle.get("persona_id", ""))
        fb = bundle.get("fallbacks") or {}
        gov = bundle.get("governance_persona_id") or fb.get("governance", "")
        funnel = bundle.get("funnel") or {}
        layers = bundle.get("layers") or {}
        task_fit_method = layers.get("_task_fit_method", "") if isinstance(layers, dict) else ""
        semantic_evidence = ""
        semantic_claimed = False
        if isinstance(funnel, dict) and funnel.get("semantic"):
            try:
                if int(funnel.get("semantic", 0)) > 0:
                    semantic_claimed = True
                    semantic_evidence = (
                        f"funnel.semantic={funnel.get('semantic')} "
                        f"engine={funnel.get('semantic_engine', '')} "
                        f"task_fit_method={task_fit_method}")
            except (TypeError, ValueError):
                pass
        if task_fit_method in ("gemini_embedding",):
            semantic_claimed = True
            semantic_evidence = (semantic_evidence + f" layer5={task_fit_method}").strip()
        method = self.scoring.method if self.scoring else (
            task_fit_method or ("module-missing"
                                if bundle.get("warning") == "NO_CATALOG"
                                else HEURISTIC_METHOD))
        rationale = dict(bundle.get("rationale") or {})
        rationale["policy_kind"] = policy.get("kind", "")
        rationale["execution_specialist"] = policy.get("execution_specialist", "")
        if audience_override:
            rationale["audience_source"] = "explicit-context"
        receipt = PersonaReceipt(
            company_id=ctx.company_id, presentation_id=ctx.presentation_id,
            run_id=ctx.run_id, phase=ctx.phase, role=ctx.role or policy.get("execution_specialist", ""),
            context_hash=ctx.context_hash(),
            content_version=self.catalog.content_version(),
            execution_id=self.execution_id,
            voice_persona_id=vp or bundle.get("persona_id", ""),
            topic_persona_id=tp or "",
            governing_persona_id=gov,
            scoring_method=method,
            scoring_detail=(f"task_fit_method={task_fit_method}; "
                            f"funnel={json.dumps(funnel, sort_keys=True, default=str)}"),
            semantic_claimed=semantic_claimed,
            semantic_evidence=semantic_evidence,
            source_hashes=self.catalog.resource_hashes(),
            per_part=per_part,
            rationale=rationale,
            policy=policy,
            blend_directive=bundle.get("blend_directive", ""),
            no_persona_required=bool(bundle.get("no_persona_required")),
            confirm_required=bool(bundle.get("confirm_required", False)),
            warnings=list(bundle.get("warnings", []) or []),
            bundle={k: bundle.get(k) for k in (
                "persona_id", "persona_name", "mode", "content_task", "topic",
                "resolved_audience", "confirm_required", "voice",
                "blend_directive", "task_personas", "rationale", "fallbacks",
                "catalog_version", "funnel") if k in bundle},
        )
        if bundle.get("warning"):
            receipt.warnings.append(str(bundle["warning"]))
        return receipt

    def _record(self, ctx, receipt: PersonaReceipt) -> None:
        """Scoped persistence: receipt + selection-log row + variety row."""
        scope = scopes_for_context(ctx)
        phase = ctx.phase or "unphased"
        self.storage.write_json(scope, f"receipt-{phase}.json", receipt.to_dict())
        self.storage.append_log(
            scope, "persona-selection-log.md",
            f"- scope: {ctx.company_id}/{ctx.presentation_id}/{phase} "
            f"- selected_persona: {receipt.voice_persona_id or 'none'} "
            f"- topic: {receipt.topic_persona_id or 'none'} "
            f"- method: {receipt.scoring_method}")
        # Per-company variety/state row (scoped sqlite, never global DB).
        db_path = self.storage.db_path(scope)
        if db_path and str(db_path) not in ("", "."):
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = __import__("sqlite3").connect(str(db_path))
                cur = conn.cursor()
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS persona_selection_log "
                    "(persona_id TEXT, department_id TEXT, layer_scores TEXT, "
                    " selected_at TEXT DEFAULT (datetime('now')))")
                cur.execute(
                    "INSERT INTO persona_selection_log "
                    "(persona_id, department_id, layer_scores) VALUES (?,?,?)",
                    (receipt.voice_persona_id, "presentations",
                     json.dumps({"task_category": ctx.topic or "general",
                                 "context_hash": receipt.context_hash,
                                 "phase": ctx.phase})))
                conn.commit()
                conn.close()
            except Exception:
                pass  # observability never blocks resolution

    # -- resume -------------------------------------------------------------
    def cached_receipt(self, ctx: PersonaContext) -> Optional[PersonaReceipt]:
        """Resume: identical scoped context reuses the stored receipt.

        Only reuses when BOTH the context hash AND the packaged content
        version match — a persona or source change invalidates.
        """
        scope = scopes_for_context(ctx)
        data = self.storage.read_json(scope, f"receipt-{ctx.phase or 'unphased'}.json")
        if not isinstance(data, dict):
            return None
        if data.get("context_hash") != ctx.context_hash():
            return None
        if data.get("content_version") != self.catalog.content_version():
            return None
        try:
            return PersonaReceipt(**{k: data[k] for k in PersonaReceipt.__dataclass_fields__
                                     if k in data})
        except TypeError:
            return None

    # -- doctor (fail-closed, pre-paid) --------------------------------------
    def doctor(self) -> Dict[str, Any]:
        """Pre-paid readiness: catalog closure, vendored modules, storage,
        no operator/global fallback reachability. Nonzero problems = BLOCK."""
        problems: List[str] = []
        checks: Dict[str, Any] = {}
        ok, closure_problems = self.catalog.validate_closure()
        checks["catalog_closure"] = {"ok": ok, "problems": closure_problems}
        problems.extend(closure_problems)
        missing_mods = []
        for name in VENDORED_MODULES:
            if not (self.scripts_dir / name).is_file():
                missing_mods.append(str(self.scripts_dir / name))
        for name in VENDORED_HELPERS + VENDORED_HELPER_DATA:
            if not (self.helpers_dir / name).is_file():
                missing_mods.append(str(self.helpers_dir / name))
        checks["vendored_modules"] = {"ok": not missing_mods, "missing": missing_mods}
        if missing_mods:
            problems.append(
                f"{len(missing_mods)} required vendored module(s) missing: "
                + ", ".join(missing_mods[:5]))
        # Storage writable probe (scoped, harmless).
        try:
            probe = self.storage.write_json(
                {"company_id": "_doctor", "presentation_id": "_probe"},
                "_probe.json", {"ok": True})
            checks["storage_writable"] = {"ok": True, "probe": str(probe)}
        except Exception as exc:
            checks["storage_writable"] = {"ok": False, "error": str(exc)}
            problems.append(f"storage not writable: {exc}")
        # No global fallback: packaged roots must not BE live roots.
        live_markers = [str(Path.home() / ".openclaw"), "/data/.openclaw"]
        for marker in live_markers:
            if str(self.resource_root).startswith(marker):
                problems.append(
                    f"resource_root {self.resource_root} lives under operator "
                    f"root {marker} — package must be self-contained")
        checks["no_operator_root"] = {
            "ok": all(not str(self.resource_root).startswith(m) for m in live_markers)}
        # Policy coverage: every manifest phase has an execution specialist.
        from .policy import EXECUTION_SPECIALIST_FOR
        checks["policy_phases"] = {"count": len(EXECUTION_SPECIALIST_FOR)}
        return {"ok": not problems, "problems": problems, "checks": checks}

    # -- consumption verify ---------------------------------------------------
    def verify_consumption(self, receipt: PersonaReceipt, rendered_text: str,
                           min_token_hit_ratio: float = 0.3) -> List[str]:
        from .bundle import verify_consumption
        return verify_consumption(receipt, rendered_text, self.catalog,
                                  min_token_hit_ratio)


def _hash_dict(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
