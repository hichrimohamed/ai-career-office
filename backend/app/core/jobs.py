"""Validation for saved jobs and outreach notes."""

from urllib.parse import urlparse

from app.core import store
from app.core.drafts import DraftError, choice
from app.core.linkedin import SectionError, check_text


class JobError(ValueError):
    pass


def text(value: str | None, field: str, limit: int, required: bool = False) -> str:
    try:
        return check_text(value, field, limit, required)
    except SectionError as error:
        raise JobError(str(error)) from None


def choice_of(value: str | None, options: list[str], field: str) -> str:
    try:
        return choice(value or "", options, field)
    except DraftError as error:
        raise JobError(str(error)) from None


def _tags(values: list | None) -> list[str]:
    return [str(v).strip()[:120] for v in values or [] if str(v).strip()][:15]


def clean_url(url: str | None) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JobError("url must be a full http(s) link to the posting.")
    return url


def clean_job(args: dict) -> dict:
    origin = choice_of(args.get("origin") or "search", store.JOB_ORIGINS, "origin")
    url = clean_url(args.get("url"))
    if origin == "search" and not url:
        # A searched job without a link can't be checked, so it might not exist.
        raise JobError("A job found by search needs the url where you found it.")
    fit_score = args.get("fit_score")
    if fit_score is not None:
        fit_score = int(fit_score)
        if not 0 <= fit_score <= 100:
            raise JobError("fit_score must be between 0 and 100.")
    return {
        "title": text(args.get("title"), "title", 150, required=True),
        "company": text(args.get("company"), "company", 120, required=True),
        "url": url,
        "location": text(args.get("location"), "location", 120),
        "work_mode": choice_of(args.get("work_mode") or "unknown", store.WORK_MODES, "work_mode"),
        "posted": text(args.get("posted") or "unknown", "posted", 80),
        "origin": origin,
        "summary": text(args.get("summary"), "summary", 1000),
        "fit_score": fit_score,
        "matched": _tags(args.get("matched")),
        "gaps": _tags(args.get("gaps")),
        "notes": text(args.get("notes"), "notes", 1000),
    }


def clean_outreach(args: dict) -> dict:
    job_id = args.get("job_id")
    if job_id is not None and store.get_job(int(job_id)) is None:
        raise JobError(f"No job with id {job_id}.")
    return {
        "job_id": int(job_id) if job_id is not None else None,
        "target": text(args.get("target"), "target", 200, required=True),
        "how_to_find": text(args.get("how_to_find"), "how_to_find", 300),
        "message": text(args.get("message"), "message", store.OUTREACH_MAX_CHARS, required=True),
    }
