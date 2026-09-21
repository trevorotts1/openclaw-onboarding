#!/usr/bin/env python3
"""departments_payload.py — the ONE normalizer every departments.json reader uses.

WHY THIS EXISTS
---------------
`<company_dir>/departments.json` ships in two legitimate top-level shapes:

  1. a bare LIST of department entries — what
     build-workforce.py::generate_departments_json() returns and what
     write_chosen_departments_artifact() writes on a first-ever build; and

  2. an OBJECT that WRAPS that list under a "departments" key. Two producers
     emit this:
       * 23-ai-workforce-blueprint/scripts/retire-confirmed-decline.sh, which
         writes {"removedWithProvenance": [...], "departments": [...]} so the
         retirement audit trail survives (build-workforce.py's
         _make_artifact_payload preserves that dict shape on every later
         apply-diff build); and
       * an envelope carrying build metadata alongside the list, e.g.
         {"company": ..., "total_departments": N, "total_roles": N,
          "departments": [...]}.

The envelope's "departments" key is not always a LIST. On a real client Mac it
holds an OBJECT keyed by department slug:

    {"company": ..., "total_departments": 34, "total_roles": N,
     "departments": {"account-management-dept": {...}, ...}}

That file is valid and must seed. Before v25.1.61 it was refused outright, so
34 real departments read as a hard error. A slug-keyed object is now folded
into a list wherever it appears — under the "departments" key or at the top
level — with the key filling "id"/"slug" only when the entry lacks its own.
The fold is refused unless EVERY value is an object, which is what keeps a
metadata envelope from ever being mistaken for a department map.

Every reader used to gate on `isinstance(data, list)` and silently treat shape
2 as "no departments" — a false negative on a perfectly valid artifact. One
reader was worse: seed-workspaces.py folded ANY dict's KEYS in as department
ids, so an envelope seeded bogus workspaces literally named "Company",
"Total Departments", "Total Roles" and "Departments" onto a client board.

So: unwrap the envelope here, at the single load boundary, and REFUSE (loudly,
naming the path and the top-level type) any dict that carries no usable
department list. A dict's metadata keys are never departments.

This module handles the ENVELOPE layer only. Per-entry coercion (bare strings,
missing "name", etc.) stays with the caller that needs it — see
seed-workspaces.py::_normalize_departments, which runs on top of this.
"""

__all__ = ["MalformedDepartmentsError", "normalize_departments",
           "departments_or_empty"]


class MalformedDepartmentsError(ValueError):
    """A departments.json payload carries no readable department list.

    Subclasses ValueError so callers that already widen to ValueError (and
    json.JSONDecodeError handlers that were widened alongside) catch it.
    """


def _describe(data):
    t = type(data).__name__
    if isinstance(data, dict):
        keys = list(data.keys())
        shown = ", ".join(repr(k) for k in keys[:8])
        if len(keys) > 8:
            shown += f", ... (+{len(keys) - 8} more)"
        return f"{t} with keys [{shown}]"
    return t


def _fold_slug_keyed(mapping):
    """Fold a slug-keyed object of department objects into a list, else ``None``.

    ``None`` means "this is not a department map, refuse it": anything that is
    not a dict, an EMPTY dict, or a dict with any non-object value. A scalar
    value (a company name, a role count) is what marks an object as a metadata
    envelope, and an envelope's keys are never departments — that is the whole
    bug this module exists to make impossible. An empty dict is not a department
    map either: the shipped empty default is ``[]``, and the provisioning
    completeness gate treats ``{}`` as invalid on purpose.

    The key fills ``id`` and ``slug`` only when the entry does not already carry
    its own, so an entry that names itself keeps its own identity. Insertion
    order is preserved, so the folded list reads in the file's own order.
    """
    if not isinstance(mapping, dict) or not mapping:
        return None
    if not all(isinstance(v, dict) for v in mapping.values()):
        return None
    folded = []
    for key, value in mapping.items():
        entry = dict(value)
        entry.setdefault("id", key)
        entry.setdefault("slug", key)
        folded.append(entry)
    return folded


def normalize_departments(data, path=None):
    """Return the department list carried by a loaded departments.json payload.

    Accepted shapes:
      * ``None``                                -> ``None`` (nothing was loaded)
      * ``[]``                                  -> ``[]``   (the shipped empty default)
      * ``[entry, ...]``                        -> the list itself, untouched
      * ``{"departments": [entry, ...], ...}``  -> the wrapped list (retire-script
        ``{removedWithProvenance, departments}`` shape, and any metadata envelope
        such as ``{company, total_departments, total_roles, departments}``)
      * ``{"departments": {"<slug>": {...}, ...}, ...}`` -> the wrapped map, folded
        to a list. This is the shape a real client box carries: the envelope's
        ``departments`` key holds an OBJECT keyed by slug, not a list.
      * ``{"<slug>": {...}, ...}``              -> the same map at the top level,
        folded the same way — ONLY when every value is an object

    Raises:
      MalformedDepartmentsError — for any other dict (an envelope whose keys are
        metadata, not departments) and for any non-list/non-dict payload. The
        message names ``path`` and the top-level type so the operator can find the
        file. Never iterate a dict's keys as departments; that is the bug this
        function exists to make impossible.
    """
    if data is None:
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "departments" in data:
            wrapped = data["departments"]
            if isinstance(wrapped, list):
                return wrapped
            folded = _fold_slug_keyed(wrapped)
            if folded is not None:
                return folded
            raise MalformedDepartmentsError(
                f"departments.json: 'departments' key holds "
                f"{type(wrapped).__name__}, expected a list or an object keyed by "
                f"slug whose values are all objects"
                f"{_where(path)}"
            )
        folded = _fold_slug_keyed(data)
        if folded is not None:
            return folded
        raise MalformedDepartmentsError(
            f"departments.json: expected a list, or an object with a 'departments' "
            f"list; got {_describe(data)}{_where(path)}"
        )
    raise MalformedDepartmentsError(
        f"departments.json: expected a list, or an object with a 'departments' "
        f"list; got {_describe(data)}{_where(path)}"
    )


def departments_or_empty(data, path=None, stream=None):
    """Lenient `normalize_departments` for readers that must emit a verdict.

    Same unwrapping, but a malformed payload NEVER raises: it prints one loud
    line naming the path and the top-level type, then returns ``[]`` — which is
    the empty/RED result those callers already produce today. Use this in QC
    provers, gates and reporters. Use `normalize_departments` (which raises)
    anywhere the alternative is writing garbage to a client's board or file.
    """
    try:
        out = normalize_departments(data, path=path)
    except MalformedDepartmentsError as exc:
        import sys as _sys
        print(f"  [departments.json] MALFORMED: {exc}", file=stream or _sys.stderr)
        return []
    return out or []


def _where(path):
    return f" (path: {path})" if path else ""


def _demo():
    """Runnable self-check: python3 departments_payload.py"""
    assert normalize_departments(None) is None
    assert normalize_departments([]) == []

    depts = [{"id": "dept-marketing", "slug": "marketing", "name": "Marketing"}]
    assert normalize_departments(depts) is depts

    # retire-confirmed-decline.sh shape
    assert normalize_departments(
        {"removedWithProvenance": [{"slug": "legal"}], "departments": depts}
    ) == depts

    # the metadata envelope seen on a client box
    assert normalize_departments(
        {"company": "Acme", "total_departments": 1, "total_roles": 9,
         "departments": depts}
    ) == depts

    # dict-of-dicts keyed by slug, at the top level
    folded = normalize_departments({"marketing": {"name": "Marketing"}})
    assert folded == [
        {"name": "Marketing", "id": "marketing", "slug": "marketing"}], folded

    # the shape a real client box carries: the ENVELOPE's "departments" key
    # holds an object keyed by slug, not a list. The metadata keys around it
    # (company / total_departments / total_roles) must never become departments.
    client = normalize_departments({
        "company": "Acme", "total_departments": 2, "total_roles": 18,
        "departments": {
            "account-management-dept": {"name": "Account Management"},
            "audio-dept": {"name": "Audio"},
        },
    })
    assert [d["id"] for d in client] == ["account-management-dept", "audio-dept"], client
    assert all(d["slug"] == d["id"] for d in client), client
    for meta in ("company", "total_departments", "total_roles", "departments"):
        assert meta not in [d["id"] for d in client], meta

    # an entry that names itself keeps its own id/slug; the key never overrides
    own = normalize_departments(
        {"departments": {"acct": {"id": "dept-account", "slug": "account"}}})
    assert own == [{"id": "dept-account", "slug": "account"}], own

    # metadata-only envelope: refuse, never fold the keys in as departments
    for bad in (
        {"company": "Acme", "total_departments": 34, "total_roles": 416},
        {"departments": {"marketing": "not-an-object"}},
        {"departments": {}},   # empty is not a department map; [] is the default
        {},          # the shipped empty default is [], never {} — see the
                     # provisioning-completeness gate's "object departments" case
        "marketing",
        42,
    ):
        try:
            normalize_departments(bad, path="/tmp/departments.json")
        except MalformedDepartmentsError as exc:
            assert "/tmp/departments.json" in str(exc) or "'departments' key" in str(exc), exc
        else:
            raise AssertionError(f"expected a refusal for {bad!r}")

    # departments_or_empty never raises; it degrades to [] with a loud line.
    import io as _io
    sink = _io.StringIO()
    assert departments_or_empty(
        {"company": "Acme", "total_roles": 9},
        path="/tmp/departments.json", stream=sink) == []
    assert "/tmp/departments.json" in sink.getvalue()
    assert departments_or_empty({"departments": depts}) == depts
    assert departments_or_empty(None) == []

    print("departments_payload: all self-checks pass")


if __name__ == "__main__":
    _demo()
