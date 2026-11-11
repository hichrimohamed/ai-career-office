"""Validation for LinkedIn profile section rewrites."""

from app.core import store
from app.tools.projects import redact


class SectionError(ValueError):
    pass


def check_text(value: str | None, field: str, limit: int, required: bool = True) -> str:
    value = (value or "").strip()
    if required and not value:
        raise SectionError(f"{field} is empty.")
    if len(value) > limit:
        raise SectionError(f"{field} is {len(value)} characters; LinkedIn's limit here is {limit}. Shorten it.")
    if redact(value) != value:
        raise SectionError(f"{field} contains something that looks like a key or token. Remove it.")
    return value


def clean_section(args: dict) -> dict:
    section = (args.get("section") or "").strip().lower()
    if section not in store.LINKEDIN_SECTIONS:
        raise SectionError(f"section must be one of: {', '.join(store.LINKEDIN_SECTIONS)}.")
    label = (args.get("label") or "").strip()
    if section in ("experience", "featured") and not label:
        raise SectionError("label is required for experience and featured, e.g. 'Software Engineer, Thales'.")
    sources = [str(s).strip() for s in args.get("sources") or [] if str(s).strip()]
    if not sources:
        raise SectionError(
            "sources is empty. List what each claim rests on: 'original', 'fact #N', or 'project <name>: <file>'."
        )
    limit = store.LINKEDIN_SECTIONS[section]
    return {
        "section": section,
        "label": check_text(label, "label", 120, required=False),
        "original": check_text(args.get("original"), "original", 5000, required=False),
        "rewrite": check_text(args.get("rewrite"), "rewrite", limit),
        "rationale": check_text(args.get("rationale"), "rationale", 800),
        "keywords": [str(k).strip() for k in args.get("keywords") or [] if str(k).strip()][:20],
        "sources": sources[:20],
    }
