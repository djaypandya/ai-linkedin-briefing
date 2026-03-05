from __future__ import annotations

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
}


def _domain_allowed(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in APPROVED_DOMAINS)


def validate_newsletter(draft: NewsletterDraft) -> None:
    if len(draft.stories) != 5:
        raise ValidationError(f"Newsletter must contain exactly five stories, found {len(draft.stories)}.")

    for story in draft.stories:
        if not story.headline.strip():
            raise ValidationError("Newsletter contains a story with an empty headline.")
        if not story.body.strip():
            raise ValidationError(f"Newsletter story body is empty for: {story.headline}")
        if not _domain_allowed(str(story.source_url)):
            raise ValidationError(f"Newsletter story uses an unapproved domain: {story.source_url}")


def validate_post(post: PostDraft) -> None:
    if not post.body.strip():
        raise ValidationError("LinkedIn post draft is empty.")
    if len(post.body.splitlines()) < 3:
        raise ValidationError("LinkedIn post draft must include a summary paragraph and hashtags.")
