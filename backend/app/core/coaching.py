"""Validation for mock interviews, skill gaps and portfolio project suggestions."""

from app.core import store
from app.core.jobs import JobError, choice_of, text


class CoachingError(ValueError):
    pass


def _wrap(fn, *args):
    try:
        return fn(*args)
    except JobError as error:
        raise CoachingError(str(error)) from None


def _text(value, field: str, limit: int, required: bool = True) -> str:
    return _wrap(text, value, field, limit, required)


def choice(value, options: list[str], field: str) -> str:
    return _wrap(choice_of, value, options, field)


def _list(values, limit: int = 10, item_chars: int = 300) -> list[str]:
    return [str(v).strip()[:item_chars] for v in values or [] if str(v).strip()][:limit]


def clean_start(args: dict) -> dict:
    planned = int(args.get("planned_questions") or 5)
    if not 1 <= planned <= 15:
        raise CoachingError("planned_questions must be between 1 and 15.")
    return {
        "topic": _text(args.get("topic"), "topic", 200),
        "level": _text(args.get("level") or "junior-mid", "level", 40),
        "planned_questions": planned,
    }


def clean_answer(args: dict) -> dict:
    score = int(args.get("score", -1))
    if not 0 <= score <= 10:
        raise CoachingError("score must be between 0 and 10.")
    return {
        "area": choice(args.get("area") or "other", store.INTERVIEW_AREAS, "area"),
        "question": _text(args.get("question"), "question", 1000),
        "answer": _text(args.get("answer"), "answer", 6000),
        "score": score,
        "feedback": _text(args.get("feedback"), "feedback", 1500),
        "strong_answer": _text(args.get("strong_answer"), "strong_answer", 2000, required=False),
    }


def clean_gap(args: dict) -> dict:
    return {
        "skill": _text(args.get("skill"), "skill", 100),
        "severity": choice(args.get("severity"), store.GAP_SEVERITIES, "severity"),
        "evidence": _text(args.get("evidence"), "evidence", 800),
        "next_step": _text(args.get("next_step"), "next_step", 500, required=False),
    }


def clean_project(args: dict) -> dict:
    steps = _list(args.get("steps"), limit=12)
    if not steps:
        raise CoachingError("steps is empty. Give a concrete build plan.")
    return {
        "title": _text(args.get("title"), "title", 150),
        "pitch": _text(args.get("pitch"), "pitch", 800),
        "closes_gaps": _list(args.get("closes_gaps"), item_chars=100),
        "stack": _list(args.get("stack"), limit=12, item_chars=60),
        "steps": steps,
        "effort": _text(args.get("effort"), "effort", 100, required=False),
    }


def clean_summary(value) -> str:
    return _text(value, "summary", 2000)
