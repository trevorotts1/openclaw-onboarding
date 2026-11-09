"""Project compatibility rows into one client question per answer field."""
from copy import deepcopy


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
            for key in ("conditional_on", "default", "refuse_values", "refuse_message"):
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
            if field in derivations and derivations[field] in sub:
                derived = derivations[field]
                q["derived_fields"] = {derived: deepcopy(sub[derived])}
            # Existing ledgers use RESOURCE_PLAN; the old resource_plan ID
            # remains reserved for importing a merged provider/model answer.
            questions.append(q)
    return sorted(questions, key=lambda q: q.get("order", 999))
