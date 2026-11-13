"""Project compatibility rows into one client question per answer field.

PD-013 also owns the QUICK/IN-DEPTH depth split: the bank tags every answer
field ``"depth": "both"`` (the build cannot run without it) or
``"depth": "in-depth"`` (the client may decide it), and ``quick_skip()``
narrows a QUICK interview to the fields it truly needs.
"""
from copy import deepcopy

#: Fields the build cannot run without (PD-013 item 2). Everything else in
#: the bank is "in-depth"; the bank is the source of truth and this set is the
#: agreement test's expectation, never the runtime reader.
BOTH_DEPTH = frozenset("""
presentation_type pitch_included signature_source extracted_substance
recipient_name audience representation_mix grounded_content goal cta_action
transformation_promise duration_min deadline standard_mode offer_name
offer_stack final_price price_mode proof_assets delivery_destinations
want_teleprompter want_speech_script want_audio_deliverable want_ghl_upload
want_sales_checkout""".split())

#: The eight model-choice fields. Only an explicit "customize" opens them.
MODEL_CHOICE_FIELDS = frozenset("""
workhorse_model reasoning_model qc_model thinking_mode run_mode
deepseek_variant openrouter_model ollama_plan""".split())

#: Asked in QUICK whatever their depth: the pace question is the mode switch
#: itself, and the plan tier keeps its own capacity-probe rule.
QUICK_ALWAYS = frozenset({"standard_mode", "provider_plan"})

DEFAULTS_REVIEW_ID = "defaults_review"


def atomic_questions(schema):
    rows = schema.get("questions", [])
    aliases = {q["id"]: q for q in rows if q.get("alias")}
    questions = []
    derivations = {"duration_min": "slide_count", "event_price": "access_free",
                   "speech_speed_preference": "target_wpm"}
    for row in rows:
        if row.get("alias"):
            continue
        sub = row.get("subfields")
        if not sub:
            questions.append(deepcopy(row))
            continue
        for index, (field, annotation) in enumerate(sub.items()):
            if annotation.get("derived"):
                continue
            copy = annotation.get("question")
            if not copy or not copy.get("prompt"):
                raise ValueError(f"Missing single-question copy: {row['id']}.{field}")
            q = deepcopy(aliases.get(field, {}))
            q.pop("alias", None)
            q.update(id=field, order=row.get("order", 0) + index / 100,
                     kind="text", required=row.get("required", False),
                     block_gate=row.get("block_gate", False),
                     legacy_parent=row["id"], answer_field=field,
                     subfields={field: deepcopy(annotation)},
                     storeOn=annotation.get("storeOn", field))
            for key in ("stage", "stage_beat", "pitchless_skip"):
                if key in row:
                    q[key] = deepcopy(row[key])
            for key in ("conditional_on", "ask_if", "default", "depth",
                        "refuse_values", "refuse_message"):
                if key in annotation:
                    q[key] = deepcopy(annotation[key])
            if annotation.get("enum"):
                q.update(kind="enum", allowed_values=annotation["enum"])
            elif annotation.get("boolish") or annotation.get("kind") == "boolean":
                q.update(kind="enum", allowed_values=["yes", "no"])
            elif annotation.get("kind") == "integer":
                q["kind"] = "integer"
            if field in aliases:
                for key in ("required", "block_gate"):
                    if key in aliases[field]:
                        q[key] = aliases[field][key]
            if annotation.get("default") == "" or (row["id"] == "resource_plan" and field != "resource_plan"):
                q.update(required=False, block_gate=False)
            if row["id"] == "audio_settings":
                q["ask_if"] = {"question_id": "want_audio_deliverable", "equals": "yes"}
            # Brand preferences used to bundle a logo and colors. Each
            # surface now requests one brand reference in this field.
            if field == "brand_primary":
                q["help"] = "Provide one brand reference, such as a logo link or primary color."
            q["help"] = copy.get("help", q.get("help", ""))
            q.update(copy)
            # PD-014: declining a toggle that DEFAULTS to "no" is not a
            # waiver, so its reason is asked only when the client's
            # preference record shows a YES for that toggle. This ask_if is
            # the prior-YES half; conditional_on keeps the answer=="no"
            # half, so a client who merely accepts the default is never
            # asked why not.
            if (annotation.get("ask_only_if_previously_wanted")
                    or q.get("ask_only_if_previously_wanted")):
                toggle = (q.get("conditional_on") or {}).get("id")
                if toggle:
                    q["ask_if"] = {"question_id": toggle, "equals": "yes"}
            if field in derivations and derivations[field] in sub:
                derived = derivations[field]
                q["derived_fields"] = {derived: deepcopy(sub[derived])}
            # Existing ledgers use RESOURCE_PLAN; the old resource_plan ID
            # remains reserved for importing a merged provider/model answer.
            questions.append(q)
    return sorted(questions, key=lambda q: q.get("order", 999))


# ---------------------------------------------------------------------------
# PD-013 -- the QUICK depth filter
# ---------------------------------------------------------------------------
def depth_of(question):
    """Bank depth for one projected question; old banks read as in-depth."""
    return question.get("depth") or "in-depth"


def has_default(question):
    """True when the bank already answers this field."""
    return question.get("default") not in (None, "")


def is_quick(answers):
    """True for a QUICK interview. The bank stores STANDARD_MODE uppercase."""
    return str((answers or {}).get("standard_mode") or "").strip().upper() in (
        "QUICK", "Q")


def quick_skip(question, answers):
    """(skip?, reason) for one projected question in a QUICK interview.

    QUICK asks only the fields it truly needs: a both-depth field with no
    bank default, the pace switch, and a plan tier the capacity probe owes.
    A field the bank already answers is recorded as a default instead of
    asked, and an in-depth field is never asked at all.
    """
    if not is_quick(answers):
        return False, None
    qid = question.get("id")
    if qid == DEFAULTS_REVIEW_ID or qid in QUICK_ALWAYS:
        return False, None
    if qid in MODEL_CHOICE_FIELDS:
        if str((answers or {}).get("build_settings_choice") or "").strip() \
                .lower() == "customize":
            return False, None
        return True, "quick: recommended build settings kept"
    # ponytail: a both-depth field carrying a bank default is answered by
    # that default in QUICK. Raise one to an ask when a default proves wrong
    # for a real deck; the review question is where the client overrides it.
    if depth_of(question) == "both" and has_default(question):
        return True, "quick: default"
    if depth_of(question) == "both":
        return False, None
    return True, "quick: in-depth"


def defaulted_in_quick(question, answers):
    """True when QUICK records this field as a default instead of asking."""
    if not is_quick(answers):
        return False
    if question.get("id") in QUICK_ALWAYS or question.get("id") in MODEL_CHOICE_FIELDS:
        return False
    return has_default(question) and (
        depth_of(question) in ("both", "in-depth"))


# ---------------------------------------------------------------------------
# PD-013 -- the measured ceilings (never typed into the bank)
# ---------------------------------------------------------------------------
def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("yes", "true", "1", "y")
    return bool(value)


def _gate_met(question, answers):
    """Minimal conditional_on / ask_if evaluation for the budget walk."""
    cond = question.get("conditional_on")
    if cond:
        val = answers.get(cond.get("id"))
        if "equals" in cond and val != cond["equals"]:
            return False
        if "in" in cond and val not in cond["in"]:
            return False
        if "truthy" in cond and not _truthy(val):
            return False
    ask_if = question.get("ask_if")
    if ask_if:
        val = answers.get(ask_if.get("question_id"))
        if "equals" in ask_if and val != ask_if["equals"]:
            return False
        if "contains" in ask_if and (
                not isinstance(val, str) or ask_if["contains"] not in val):
            return False
        if "truthy" in ask_if and not val:
            return False
    return True


def _pitchless(answers):
    return answers.get("pitch_included") is False


#: The answer axes the ask sequence actually branches on.
_BRANCH_AXES = (
    ("presentation_type", ["from_scratch", "content_personal",
                           "content_general", "signature"]),
    ("pitch_included", [True, False]),
    ("build_settings_choice", ["ok", "customize"]),
    ("price_mode", ["drop", "straight"]),
    ("vip_tier", [True, False]),
    ("want_sales_checkout", ["yes", "no"]),
    ("want_vsl_page", ["yes", "no"]),
    ("want_email_sequences", ["yes", "no"]),
    ("want_motion_graphics", ["yes", "no"]),
    ("want_audio_deliverable", ["yes", "no"]),
    ("want_audio_demo", [True, False]),
    ("want_teleprompter", ["yes", "no"]),
    ("want_speech_script", ["yes", "no"]),
    ("want_ghl_upload", ["yes", "no"]),
)


def _walk_count(questions, answers, quick):
    """Questions asked for one assignment, by the same gates the driver uses."""
    count = 0
    for q in questions:
        if not _gate_met(q, answers):
            continue
        if q.get("pitchless_skip") and _pitchless(answers):
            continue
        if q.get("id") == "audio_settings" and not (
                _truthy(answers.get("want_audio_deliverable"))
                or _truthy(answers.get("want_audio_demo"))):
            continue
        if q.get("id") == "decline_context":
            declined = any(
                str(answers.get(k, "yes")).strip().lower() == "no"
                for k in ("want_teleprompter", "want_speech_script",
                          "want_ghl_upload", "want_audio_deliverable",
                          "want_sales_checkout", "want_vsl_page",
                          "want_email_sequences", "want_motion_graphics"))
            if not declined:
                continue
        if quick:
            skip, _reason = quick_skip(q, answers)
            if skip:
                continue
        count += 1
    return count + 1 if quick else count


def measure_budget(schema):
    """Measure the two ceilings by walking the projected sequence.

    max_turns is the IN-DEPTH ceiling: every projected question can be asked
    under some branch, so it is the length of the projected sequence.
    quick_max_turns is the worst QUICK branch, counted over every answer axis
    the sequence branches on, plus the one ``defaults_review`` turn.
    """
    questions = atomic_questions(schema)
    quick_max = 0
    axes = list(_BRANCH_AXES)
    for combo in _product([v for _k, v in axes]):
        answers = {"standard_mode": "QUICK"}
        answers.update({k: v for (k, _vals), v in zip(axes, combo)})
        quick_max = max(quick_max, _walk_count(questions, answers, True))
    return {"max_turns": len(questions), "quick_max_turns": quick_max}


def _product(columns):
    """Cartesian product without importing itertools semantics twice."""
    from itertools import product
    return product(*columns)
