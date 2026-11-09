"""marketing_quizzes family commands (owner WF34). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "marketing_quizzes"
OWNER = "WF34"
OPERATION_ROOTS: tuple[str, ...] = ()
EXTRA_OPERATION_IDS: tuple[str, ...] = ("courses.quizzes.create", "courses.quizzes.questions.upsert")

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Course lesson quizzes and quiz questions")

def register(cli) -> None:
    register_group(cli, build())
