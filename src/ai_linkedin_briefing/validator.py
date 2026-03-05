from __future__ import annotations

import re
from urllib.parse import urlparse

from .exceptions import ValidationError
from .models import NewsletterDraft, PostDraft


APPROVED_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "blog.google",
    "googleblog.com",
    "google.com",
    "perplexity.ai",
    "reuters.com",
    "apnews.com",
    "techcrunch.com",
    "aimagazine.com",
    "bair.berkeley.edu",
    "research.google",
    "deepmind.google",
    "news.mit.edu",
    "therundown.ai",
}

MIN_BRIEFING_STORIES = 3
MAX_BRIEFING_STORIES = 5
MATTERS_PHRASES = ("this matters because", "this is important because")
DISALLOWED_HEADLINE_PREFIX_PATTERN = re.compile(r"^\s*(exclusive|breaking|analysis|opinion)\b", re.IGNORECASE)


def _domain_allowed(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in APPROVED_DOMAINS)


def validate_newsletter(draft: NewsletterDraft) -> None:
    story_count = len(draft.stories)
    if story_count < MIN_BRIEFING_STORIES or story_count > MAX_BRIEFING_STORIES:
        raise ValidationError(
            "Newsletter must contain between "
            f"{MIN_BRIEFING_STORIES} and {MAX_BRIEFING_STORIES} stories, found {story_count}."
        )

    for story in draft.stories:
        if not story.headline.strip():
            raise ValidationError("Newsletter contains a story with an empty headline.")
        if DISALLOWED_HEADLINE_PREFIX_PATTERN.search(story.headline):
            raise ValidationError(f"Newsletter headline has a disallowed editorial label: {story.headline}")
        if "—" in story.headline or "—" in story.body:
            raise ValidationError("Newsletter output must not contain em dashes.")
        if not story.body.strip():
            raise ValidationError(f"Newsletter story body is empty for: {story.headline}")
        normalized_body = " ".join(story.body.lower().split())
        if not any(phrase in normalized_body for phrase in MATTERS_PHRASES):
            raise ValidationError(
                f"Newsletter story must include a why-it-matters sentence: {story.headline}"
            )
        source_pattern = re.compile(r"\(source:\s*([^)]+)\)\s*$", re.IGNORECASE)
        source_match = source_pattern.search(story.body.strip())
        if source_match is None:
            raise ValidationError(
                "Newsletter story must end with source attribution in format '(Source: Publisher)': "
                f"{story.headline}"
            )
        source_publisher = source_match.group(1).strip().lower()
        if source_publisher != story.publisher.lower():
            raise ValidationError(
                f"Newsletter story source attribution must include publisher name: {story.headline}"
            )
        if not _domain_allowed(str(story.source_url)):
            raise ValidationError(f"Newsletter story uses an unapproved domain: {story.source_url}")


def validate_post(post: PostDraft) -> None:
    if not post.body.strip():
        raise ValidationError("LinkedIn post draft is empty.")
    if len(post.body.splitlines()) < 3:
        raise ValidationError("LinkedIn post draft must include a summary paragraph and hashtags.")
