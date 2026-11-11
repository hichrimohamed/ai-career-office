"""Validation for post ideas and drafts saved by agents or edited on the Drafts board."""

from app.core import store
from app.tools.projects import redact

LINKEDIN_MAX_CHARS = 3000
LIMITS = {"title": 120, "hook": 300, "angle": 600, "why": 600, "proof_missing": 400, "asset_needed": 500,
          "change_note": 300}


class DraftError(ValueError):
    pass


def choice(value: str, options: list[str], field: str) -> str:
    value = (value or "").strip().lower()
    if value not in options:
        raise DraftError(f"{field} must be one of: {', '.join(options)}.")
    return value


def text(value: str | None, field: str, required: bool = True) -> str:
    value = (value or "").strip()
    if required and not value:
        raise DraftError(f"{field} is empty.")
    limit = LIMITS.get(field, LINKEDIN_MAX_CHARS)
    if len(value) > limit:
        raise DraftError(f"{field} is {len(value)} characters; the limit is {limit}.")
    if redact(value) != value:
        raise DraftError(f"{field} contains something that looks like a key or token. Remove it.")
    return value


def clean_idea(args: dict) -> dict:
    return {
        "title": text(args.get("title"), "title"),
        "hook": text(args.get("hook"), "hook"),
        "angle": text(args.get("angle"), "angle"),
        "why": text(args.get("why"), "why"),
        "pillar": choice(args.get("pillar", ""), store.PILLARS, "pillar"),
        "proof_missing": text(args.get("proof_missing"), "proof_missing", required=False),
    }


def clean_draft(args: dict) -> dict:
    idea_id = args.get("idea_id")
    if idea_id is not None and store.get_idea(int(idea_id)) is None:
        raise DraftError(f"No idea with id {idea_id}.")
    return {
        "idea_id": int(idea_id) if idea_id is not None else None,
        "title": text(args.get("title"), "title"),
        "pillar": choice(args.get("pillar", ""), store.PILLARS, "pillar"),
        "format": choice(args.get("format", ""), store.FORMATS, "format"),
        "body": text(args.get("body"), "body"),
        "asset_needed": text(args.get("asset_needed"), "asset_needed", required=False),
    }
