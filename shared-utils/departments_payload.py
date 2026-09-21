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


def normalize_departments(data, path=None):
    """Return the department list carried by a loaded departments.json payload.

    Accepted shapes:
      * ``None``                                -> ``None`` (nothing was loaded)
      * ``[]``                                  -> ``[]``   (the shipped empty default)
      * ``[entry, ...]``                        -> the list itself, untouched
      * ``{"departments": [entry, ...], ...}``  -> the wrapped list (retire-script
        ``{removedWithProvenance, departments}`` shape, and any metadata envelope
        such as ``{company, total_departments, total_roles, departments}``)
      * ``{"<slug>": {...}, ...}``              -> dict-of-dicts keyed by slug, folded
        into a list with the key as ``id`` — ONLY when every value is a dict

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
            raise MalformedDepartmentsError(
                f"departments.json: 'departments' key holds "
                f"{type(wrapped).__name__}, expected a list"
                f"{_where(path)}"
            )
        # dict-of-dicts keyed by slug. Every value must be a dict — a scalar
        # value (a company name, a role count) marks this as a metadata
        # envelope, never a department map. An EMPTY dict is not a department
        # map either: the shipped empty default is `[]`, and the provisioning
        # completeness gate treats `{}` as invalid on purpose.
        if data and all(isinstance(v, dict) for v in data.values()):
            folded = []
            for key, value in data.items():
                entry = dict(value)
                entry.setdefault("id", key)
                folded.append(entry)
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

    # dict-of-dicts keyed by slug
    folded = normalize_departments({"marketing": {"name": "Marketing"}})
    assert folded == [{"name": "Marketing", "id": "marketing"}], folded

    # metadata-only envelope: refuse, never fold the keys in as departments
    for bad in (
        {"company": "Acme", "total_departments": 34, "total_roles": 416},
        {"departments": {"marketing": {}}},
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
