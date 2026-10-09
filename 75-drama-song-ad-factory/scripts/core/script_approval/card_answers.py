"""Write $RUN/card-answers.json when the client confirms the intake card recap.
stage.run_stage reads it (missing file = not asked). Kept separate from the
song-approval and storyboard recorders so the branches merge cleanly."""
import json
import os

ANSWERS = "card-answers.json"


def write(run_dir, answers, questions):
    """answers: the `answers` list of intake_card.conversation; each entry gets its question id."""
    rows = [dict(a, id=q.get("id")) for q, a in zip(questions, answers)]
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, ANSWERS)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return path
