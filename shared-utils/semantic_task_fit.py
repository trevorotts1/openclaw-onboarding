"""
semantic_task_fit.py — Layer 5 (Task Fit) scoring for persona-selector.

Replaces the v10.7.0 text-length heuristic (`0.7 + min(len(task_text)/1000, 0.2)`)
with real semantic similarity between the task description and the persona's
blueprint, using the Gemini Embedding 2 index built by Skill 22.

The 2026-05-20 v2.0 audit (Phase 16 PM1 / Phase 17 IT3) flagged the
text-length fallback as a critical gap — short tasks scored 0.75, long
tasks scored 0.95, regardless of whether the persona had anything to do
with the task. This module fixes that.

Three-step resolution chain:
  1. Gemini Embedding 2 semantic similarity (best — requires
     gemini-index.sqlite populated + GOOGLE_API_KEY available)
  2. Keyword overlap between task and persona name/id/tags (fallback when
     no embedding infra — better than text length, not as good as semantic)
  3. Neutral 0.6 (last resort when neither works) — explicit so the score
     surfaces "we had no signal" rather than masquerading as confident

Module-level task-embedding cache: same task scored against N personas
embeds the task ONCE.
"""
import os
import re
import sqlite3
import sys
from pathlib import Path

_TASK_EMBED_CACHE: dict = {}
_GENAI_AVAILABLE = None  # tri-state: None=unknown, True=imported, False=failed

# G13: number of persona blueprint chunks to AVERAGE into the persona's
# representative vector (was LIMIT 1 — whichever chunk sqlite returned first).
# Averaging a handful of chunks gives a stable, whole-blueprint centroid so the
# Layer-5 cosine reflects the persona as a whole, not one arbitrary fragment.
# Bounded so a huge blueprint can't pull unbounded rows per persona.
_PERSONA_TOPK_CHUNKS = max(1, int(os.environ.get("SEMANTIC_TASK_FIT_TOPK", "8")))


def _try_import_genai():
    global _GENAI_AVAILABLE
    if _GENAI_AVAILABLE is not None:
        return _GENAI_AVAILABLE
    try:
        from google import genai  # noqa: F401
        from google.genai import types  # noqa: F401
        import numpy as np  # noqa: F401
        _GENAI_AVAILABLE = True
    except ImportError:
        _GENAI_AVAILABLE = False
    return _GENAI_AVAILABLE


def _gemini_index_path(paths: dict) -> Path:
    """Return the path to the Gemini index DB. Skill 22 writes it here."""
    workspace = paths.get("workspace")
    if workspace:
        candidate = Path(workspace) / "data" / "coaching-personas" / "gemini-index.sqlite"
        if candidate.exists():
            return candidate
    return paths.get("gemini_index", Path(""))


def _get_google_api_key(paths: dict) -> str:
    """Resolve GOOGLE_API_KEY from env, openclaw.json, or secrets/.env."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    secrets_path = (paths.get("secrets", Path("")) / ".env") if paths.get("secrets") else None
    if secrets_path and secrets_path.exists():
        try:
            for line in secrets_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY=") or line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip('"\' ')
        except OSError:
            pass
    # openclaw.json env block
    for ocj in [Path.home() / ".openclaw" / "openclaw.json",
                Path("/data/.openclaw/openclaw.json")]:
        if ocj.exists():
            try:
                import json
                data = json.loads(ocj.read_text(encoding="utf-8"))
                env = data.get("env", {})
                for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                    if env.get(k):
                        return env[k]
            except (OSError, ValueError):
                continue
    return ""


def _embed_text(text: str, api_key: str):
    """Embed text via Gemini Embedding 2 (GA). Returns numpy array or None.

    Imports GEMINI_MODEL and GEMINI_OUTPUT_DIM from the canonical
    shared-utils/embedding_engine.py so the model slug is never duplicated.
    Any future GA model bump in embedding_engine.py propagates here automatically.
    """
    try:
        from google import genai
        from google.genai import types
        import numpy as np
        import sys as _sys, os as _os
        _su = _os.path.dirname(__file__)
        if _su not in _sys.path:
            _sys.path.insert(0, _su)
        from embedding_engine import GEMINI_MODEL as _GEMINI_MODEL
        from embedding_engine import GEMINI_OUTPUT_DIM as _OUT_DIM
        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model=_GEMINI_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=_OUT_DIM),
        )
        return np.array(response.embeddings[0].values, dtype="float32")
    except Exception as e:
        print(f"[semantic_task_fit] embed failed: {e}", file=sys.stderr)
        return None


def _cosine(v1, v2) -> float:
    """Cosine similarity. Returns float in [-1, 1]."""
    try:
        import numpy as np
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (n1 * n2))
    except ImportError:
        return 0.0


def _current_gemini_model() -> str:
    """Model authority = shared-utils/embedding_engine.GEMINI_MODEL."""
    try:
        import sys as _sys, os as _os
        _su = _os.path.dirname(__file__)
        if _su not in _sys.path:
            _sys.path.insert(0, _su)
        from embedding_engine import GEMINI_MODEL as _M
        return _M
    except Exception:
        return "gemini-embedding-2"


def _provider_filter_sql(cur) -> str:
    """
    EMBED-7: exclude rows whose provider/model metadata is DEFINITELY not the
    current gemini model (e.g. provider='fake' plumbing rows, retired preview
    slugs, openai rows) from the selector's cosine pool. search() in
    embedding_engine already refuses these; this closes the same hole on the
    in-process selector path, which previously cosine-scored ANY row that
    happened to match the query dimension. Legacy rows with NULL/'' provider
    are still allowed (pre-PRD-1.8 indexes carry no metadata); the dimension
    guard remains the backstop for those.
    Returns '' when the index has no provider/model columns.
    """
    try:
        cur.execute("PRAGMA table_info(embeddings)")
        cols = {r[1] for r in cur.fetchall()}
    except sqlite3.Error:
        return ""
    if not {"provider", "model"} <= cols:
        return ""
    model = _current_gemini_model().replace("'", "''")
    return (" AND (provider IS NULL OR provider = '' "
            f"OR (provider = 'gemini' AND model = '{model}'))")


def _persona_embedding_from_index(persona_id: str, db_path: Path, top_k: int = None):
    """Pull the persona's representative embedding from gemini-index.sqlite.

    G13 fix: AVERAGE up to `top_k` chunk vectors for the persona instead of the
    old `LIMIT 1` (which returned whichever single chunk sqlite happened to order
    first — usually the cover/intro, not the methodology). The mean of the first
    `top_k` chunks (ordered by chunk_index for determinism) is a stable centroid
    of the whole blueprint, so the Layer-5 cosine reflects the persona overall.

    Robust to ragged/mixed-dimension legacy rows: keeps only the vectors whose
    dimension matches the modal dimension so np.mean never raises. Returns the
    averaged float32 vector, or None when the persona has no usable rows.
    """
    if not db_path.exists():
        return None
    if top_k is None:
        top_k = _PERSONA_TOPK_CHUNKS
    try:
        import numpy as np
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        cur = conn.cursor()
        # The indexer keys by file_path; persona blueprint files include persona_id.
        # Order by chunk_index so the averaged set is deterministic across calls.
        cur.execute(
            "SELECT vector FROM embeddings WHERE file_path LIKE ? "
            + _provider_filter_sql(cur) +
            " ORDER BY chunk_index ASC LIMIT ?",
            (f"%{persona_id}%", int(top_k)),
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return None
        vecs = []
        for r in rows:
            if not r or r[0] is None:
                continue
            try:
                vecs.append(np.frombuffer(r[0], dtype="float32"))
            except Exception:
                continue
        if not vecs:
            return None
        # Guard against mixed-dim rows (e.g. legacy openai 1536 next to gemini
        # 3072): keep only the modal dimension before averaging.
        from collections import Counter
        modal_dim = Counter(v.shape[0] for v in vecs).most_common(1)[0][0]
        vecs = [v for v in vecs if v.shape[0] == modal_dim]
        if not vecs:
            return None
        if len(vecs) == 1:
            return vecs[0]
        return np.mean(np.stack(vecs), axis=0).astype("float32")
    except sqlite3.Error:
        return None


def _keyword_overlap_score(persona_id: str, task_text: str, persona_summary: str = "") -> float:
    """
    Fallback: keyword overlap between task text and persona name/id/blueprint.
    Returns 0.5–0.85 based on overlap density. Always strictly better than
    "no signal" because we're at least looking at content correlation.
    """
    stop = {"the", "and", "of", "or", "a", "an", "to", "in", "on", "for",
            "is", "are", "be", "with", "by", "as", "at", "from", "this", "that"}
    persona_tokens = set(
        t for t in re.split(r"[\W_]+", persona_id.lower() + " " + persona_summary.lower())
        if t and t not in stop and len(t) >= 3
    )
    task_tokens = set(
        t for t in re.split(r"[\W_]+", task_text.lower())
        if t and t not in stop and len(t) >= 3
    )
    if not persona_tokens or not task_tokens:
        return 0.6
    overlap = len(persona_tokens & task_tokens)
    # Density: overlap relative to the smaller of the two token sets
    denom = max(1, min(len(persona_tokens), len(task_tokens)))
    density = overlap / denom
    # Map density (typically 0.0-0.4) into [0.55, 0.85]
    score = 0.55 + min(density * 0.75, 0.30)
    return round(score, 4)


def semantic_task_fit(
    persona_id: str,
    task_text: str,
    paths: dict,
    persona_summary: str = "",
) -> dict:
    """
    Score how well `persona_id` fits `task_text`. Returns:
        {
          "score":  float in [0.0, 1.0],
          "method": "gemini_embedding" | "keyword_overlap" | "neutral_fallback",
          "detail": str describing why this method was chosen
        }

    Order of attempts:
      1. Gemini embedding similarity (best)
      2. Keyword overlap with persona id + blueprint summary
      3. Neutral 0.6
    """
    # Step 1: try Gemini semantic embedding
    if _try_import_genai():
        api_key = _get_google_api_key(paths)
        db_path = _gemini_index_path(paths)
        if api_key and db_path.exists():
            cache_key = ("task", task_text)
            task_vec = _TASK_EMBED_CACHE.get(cache_key)
            if task_vec is None:
                task_vec = _embed_text(task_text, api_key)
                if task_vec is not None:
                    _TASK_EMBED_CACHE[cache_key] = task_vec
            if task_vec is not None:
                persona_vec = _persona_embedding_from_index(persona_id, db_path)
                if persona_vec is not None:
                    cos = _cosine(task_vec, persona_vec)
                    # Cosine is [-1, 1]; map to [0, 1] via (cos + 1) / 2,
                    # then clamp to [0.2, 0.98] so it never hits hard 0 or 1
                    raw = (cos + 1.0) / 2.0
                    score = max(0.2, min(0.98, raw))
                    return {
                        "score":  round(score, 4),
                        "method": "gemini_embedding",
                        "detail": f"cos={cos:.3f}, db={db_path.name}",
                    }

    # Step 2: keyword overlap fallback
    overlap_score = _keyword_overlap_score(persona_id, task_text, persona_summary)
    if overlap_score != 0.6:  # 0.6 means tokens were empty — escalate to step 3
        return {
            "score":  overlap_score,
            "method": "keyword_overlap",
            "detail": "no embedding infra; using token overlap between task and persona",
        }

    # Step 3: neutral fallback
    return {
        "score":  0.6,
        "method": "neutral_fallback",
        "detail": "no embedding infra and no token overlap signal available",
    }


def semantic_persona_ids(task_text: str, paths: dict, top_k: int = 10) -> "list | None":
    """Programmatic Stage-C retrieval (G13 / PRD item 1.8).

    Return an ordered list of the `top_k` persona IDs most semantically similar
    to `task_text`, computed ENTIRELY IN-PROCESS so the task is embedded ONCE and
    that embedding is SHARED with semantic_task_fit() (Layer 5) via the
    module-level `_TASK_EMBED_CACHE`. This is the whole point of G13: the prior
    selector embedded the task twice per selection — once inside the
    gemini-search.py subprocess (Stage C) and again here in-process (Layer 5).
    Routing Stage C through this function collapses that to a single embed.

    Persona score = MAX cosine over that persona's chunk vectors (standard
    retrieval semantics — a task that strongly matches any one chunk surfaces
    the persona). Returns None — never an empty list — when embedding infra is
    unavailable, so the caller falls back to the subprocess / keyword path
    (never-to-zero).
    """
    if not _try_import_genai():
        return None
    api_key = _get_google_api_key(paths)
    db_path = _gemini_index_path(paths)
    if not api_key or not db_path.exists():
        return None

    # Shared task embedding — SAME cache key semantic_task_fit() uses.
    cache_key = ("task", task_text)
    task_vec = _TASK_EMBED_CACHE.get(cache_key)
    if task_vec is None:
        task_vec = _embed_text(task_text, api_key)
        if task_vec is None:
            return None
        _TASK_EMBED_CACHE[cache_key] = task_vec

    try:
        import numpy as np
        tnorm = np.linalg.norm(task_vec)
        if tnorm == 0:
            return None
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        cur = conn.cursor()
        cur.execute(
            "SELECT file_path, vector FROM embeddings "
            "WHERE file_path LIKE '%coaching-personas/personas/%'"
            + _provider_filter_sql(cur)
        )
        rows = cur.fetchall()
        conn.close()
    except sqlite3.Error:
        return None

    best: dict = {}  # persona_id -> max cosine over its chunks
    for file_path, blob in rows:
        if not file_path or blob is None:
            continue
        try:
            vec = np.frombuffer(blob, dtype="float32")
        except Exception:
            continue
        if vec.shape[0] != task_vec.shape[0]:
            continue  # skip ragged / mixed-provider rows (never cross-dim cosine)
        # persona id == parent folder name (matches embedding_engine.get_persona_name)
        pid = os.path.basename(os.path.dirname(file_path))
        if not pid or pid == "personas":
            continue
        n = np.linalg.norm(vec)
        if n == 0:
            continue
        cos = float(np.dot(task_vec, vec) / (tnorm * n))
        if pid not in best or cos > best[pid]:
            best[pid] = cos

    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    return [pid for pid, _ in ranked[: max(1, int(top_k))]]


def clear_cache():
    """Reset the module-level task-embedding cache. Useful for tests."""
    _TASK_EMBED_CACHE.clear()


if __name__ == "__main__":
    # Smoke test
    import argparse, json
    parser = argparse.ArgumentParser(description="Smoke-test Layer 5 semantic scoring")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--summary", default="")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from detect_platform import get_openclaw_paths
        paths = get_openclaw_paths()
    except Exception:
        paths = {"workspace": Path.home() / "clawd", "secrets": Path.home() / ".openclaw" / "secrets"}

    result = semantic_task_fit(args.persona, args.task, paths, args.summary)
    print(json.dumps(result, indent=2))
