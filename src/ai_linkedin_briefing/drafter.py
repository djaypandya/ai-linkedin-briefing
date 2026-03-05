from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .exceptions import ValidationError
from .models import DraftStory, NewsletterDraft, PostDraft, StoryCandidate


def _headline_from_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise ValidationError("Story title is empty after normalization.")
    return cleaned


def _body_from_candidate(candidate: StoryCandidate) -> str:
    base = " ".join(candidate.summary.split())
    if not base:
        raise ValidationError(f"Story summary is empty for source: {candidate.url}")
    return base


def draft_newsletter(
    candidates: list[StoryCandidate],
    now: datetime,
    timezone_name: str,
) -> NewsletterDraft:
    if len(candidates) < 5:
        raise ValidationError("At least five candidates are required to draft the newsletter.")

    stories = [
        DraftStory(
            headline=_headline_from_title(candidate.title),
            body=_body_from_candidate(candidate),
            source_url=candidate.url,
            publisher=candidate.publisher,
        )
        for candidate in candidates[:5]
    ]
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
