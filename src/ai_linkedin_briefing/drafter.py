from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from .exceptions import ValidationError
from .models import DraftStory, NewsletterDraft, PostDraft, StoryCandidate

MIN_BRIEFING_STORIES = 3
MAX_BRIEFING_STORIES = 5
DISALLOWED_HEADLINE_PREFIXES = ("exclusive", "breaking", "analysis", "opinion")
MATTERS_PHRASES = ("this matters because", "this is important because")


class StorySummarizer(Protocol):
    def summarize(self, candidate: StoryCandidate): ...


def _normalize_text(value: str) -> str:
    normalized = " ".join(value.split())
    # Keep punctuation simple for readability and template compliance.
    normalized = normalized.replace("—", "-").replace("–", "-")
    return normalized.strip()


def _ensure_sentence(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    text_without_closers = text.rstrip("\"')]} ")
    if text_without_closers and text_without_closers[-1] in ".!?":
        return text
    return f"{text}."


def _headline_from_title(title: str) -> str:
    cleaned = _normalize_text(title)
    # Remove editorial labels like "EXCLUSIVE:" at the start of headlines.
    cleaned = re.sub(
        r"^\s*(?:\[)?(?:exclusive|breaking|analysis|opinion)(?:\])?\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*(?:exclusive|breaking|analysis|opinion)\s+", "", cleaned, flags=re.IGNORECASE)
    if not cleaned:
        raise ValidationError("Story title is empty after normalization.")
    lowered = cleaned.lower()
    if lowered.startswith(DISALLOWED_HEADLINE_PREFIXES):
        raise ValidationError(f"Story headline still starts with a disallowed label: {cleaned}")
    return cleaned


def _body_from_candidate(candidate: StoryCandidate) -> str:
    base = _normalize_text(candidate.summary)
    if not base:
        raise ValidationError(f"Story summary is empty for source: {candidate.url}")
    summary_sentence = _ensure_sentence(base)
    lower_summary = summary_sentence.lower()
    if any(phrase in lower_summary for phrase in MATTERS_PHRASES):
        matters_sentence = ""
    else:
        matters_sentence = "This matters because it affects how AI tools are built and used."

    source_sentence = f"(Source: {candidate.publisher})"
    parts = [summary_sentence]
    if matters_sentence:
        parts.append(matters_sentence)
    parts.append(source_sentence)
    return " ".join(parts)


def draft_newsletter(
    candidates: list[StoryCandidate],
    now: datetime,
    timezone_name: str,
    summarizer: StorySummarizer | None = None,
) -> NewsletterDraft:
    if len(candidates) < MIN_BRIEFING_STORIES:
        raise ValidationError(
            f"At least {MIN_BRIEFING_STORIES} candidates are required to draft the newsletter."
        )

    stories: list[DraftStory] = []
    for candidate in candidates[:MAX_BRIEFING_STORIES]:
        if summarizer is None:
            headline = _headline_from_title(candidate.title)
            body = _body_from_candidate(candidate)
        else:
            summarized = summarizer.summarize(candidate)
            headline = _headline_from_title(summarized.headline)
            body = _normalize_text(summarized.body)
        stories.append(
            DraftStory(
                headline=headline,
                body=body,
                source_url=candidate.url,
                publisher=candidate.publisher,
            )
        )
    local_now = now.astimezone(ZoneInfo(timezone_name))
    return NewsletterDraft(
        run_at=now,
        date_label=local_now.strftime("%A, %d %B %Y"),
        stories=stories,
    )


def draft_post(newsletter: NewsletterDraft) -> PostDraft:
    top_headlines = [story.headline for story in newsletter.stories[:3]]
    summary = ", ".join(top_headlines[:-1]) + f", and {top_headlines[-1]}."
    body = (
        f"In today's AI Briefing, the top stories include {summary} "
        "These stories show how quickly AI products, infrastructure, and policy are moving.\n\n"
        "#AI\n#TechNews\n#Innovation"
    )
    return PostDraft(body=body)
