from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from .exceptions import SourceCollectionError
from .models import SourceKind, StoryCandidate


DEFAULT_FEEDS = (
    {
        "publisher": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "Anthropic",
        "url": "https://www.anthropic.com/news/rss.xml",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "Google",
        "url": "https://blog.google/rss/",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "Perplexity",
        "url": "https://www.perplexity.ai/hub/blog/rss.xml",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "Reuters",
        "url": "https://feeds.reuters.com/reuters/technologyNews",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "AP News",
        "url": "https://apnews.com/hub/technology/rss",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "AI Magazine",
        "url": "https://aimagazine.com/news/rss",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "OpenAI Blog",
        "url": "https://openai.com/news/rss.xml",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "BAIR Blog",
        "url": "https://bair.berkeley.edu/blog/feed.xml",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "Google Research Blog",
        "url": "https://research.google/blog/rss/",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "source_kind": SourceKind.PRIMARY,
    },
    {
        "publisher": "MIT News AI Topic",
        "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
        "source_kind": SourceKind.INDEPENDENT,
    },
    {
        "publisher": "The Rundown AI",
        "url": "https://www.therundown.ai/rss",
        "source_kind": SourceKind.INDEPENDENT,
    },
)

AI_KEYWORDS = {
    "ai",
    "artificial intelligence",
    "model",
    "models",
    "llm",
    "openai",
    "anthropic",
    "google",
    "gemini",
    "perplexity",
    "chip",
    "chips",
    "inference",
    "training",
    "compute",
    "agent",
    "agents",
    "reasoning",
    "deep learning",
    "machine learning",
    "gpu",
    "xai",
}

HIGH_IMPACT_KEYWORDS = {
    "launch",
    "release",
    "partner",
    "partnership",
    "funding",
    "investment",
    "regulation",
    "rule",
    "lawsuit",
    "acquisition",
    "chip",
    "chips",
    "earnings",
    "infrastructure",
    "research",
    "model",
    "models",
}

NOISE_KEYWORDS = {
    "podcast",
    "event recap",
    "webinar",
    "hiring",
    "careers",
}


def _to_datetime(entry: feedparser.FeedParserDict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is not None:
        return datetime(*parsed[:6], tzinfo=timezone.utc)

    for key in ("published", "updated", "created"):
        raw_value = entry.get(key)
        if not raw_value:
            continue
        try:
            parsed_value = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, IndexError):
            continue
        if parsed_value.tzinfo is None:
            parsed_value = parsed_value.replace(tzinfo=timezone.utc)
        return parsed_value.astimezone(timezone.utc)
    return None


def _strip_html(value: str) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = unescape(text)
    return " ".join(text.split())


def _normalize_text(value: str) -> str:
    text = _strip_html(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _is_ai_relevant(title: str, summary: str, publisher: str) -> bool:
    combined = f"{title} {summary} {publisher}".lower()
    if any(noise in combined for noise in NOISE_KEYWORDS):
        return False
    return any(keyword in combined for keyword in AI_KEYWORDS)


def _dedupe_key(url: str, title: str) -> str:
    hostname = urlparse(url).hostname or ""
    normalized_title = _normalize_text(title)
    shortened_title = " ".join(normalized_title.split()[:12])
    return f"{hostname}:{shortened_title}"


def _score_candidate(
    title: str,
    summary: str,
    published_at: datetime,
    now: datetime,
    source_kind: SourceKind,
) -> int:
    combined = f"{title} {summary}".lower()
    score = 0

    if source_kind == SourceKind.INDEPENDENT:
        score += 30
    else:
        score += 25

    score += sum(10 for keyword in HIGH_IMPACT_KEYWORDS if keyword in combined)
    score += sum(4 for keyword in AI_KEYWORDS if keyword in combined)

    age_hours = max((now - published_at).total_seconds() / 3600, 0)
    if age_hours <= 6:
        score += 20
    elif age_hours <= 12:
        score += 12
    elif age_hours <= 24:
        score += 6

    return score


def _parse_feed(feed: dict[str, Any]) -> feedparser.FeedParserDict:
    url = feed["url"]
    headers = {
        "User-Agent": "ai-linkedin-briefing/0.1 (+https://www.linkedin.com)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    try:
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=20.0)
    except httpx.HTTPError as exc:
        raise SourceCollectionError(f"Feed could not be fetched: {url}") from exc
    if response.status_code >= 400:
        raise SourceCollectionError(f"Feed returned HTTP {response.status_code}: {url}")

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise SourceCollectionError(f"Feed could not be parsed: {url}")
    return parsed


def collect_candidates(now: datetime, lookback_hours: int = 24) -> list[StoryCandidate]:
    window_start = now - timedelta(hours=lookback_hours)
    raw_candidates: list[StoryCandidate] = []
    seen_keys: set[str] = set()
    feed_failures: list[str] = []

    for feed in DEFAULT_FEEDS:
        try:
            parsed = _parse_feed(feed)
        except SourceCollectionError as exc:
            feed_failures.append(str(exc))
            continue

        for entry in parsed.entries:
            title = _strip_html(entry.get("title", ""))
            summary = _strip_html(entry.get("summary", "")) or title
            published_at = _to_datetime(entry)
            link = entry.get("link", "").strip()

            if not title or not link:
                continue
            if published_at is None or published_at < window_start or published_at > now:
                continue
            if not _is_ai_relevant(title, summary, feed["publisher"]):
                continue

            key = _dedupe_key(link, title)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            raw_candidates.append(
                StoryCandidate(
                    title=title,
                    url=link,
                    publisher=feed["publisher"],
                    published_at=published_at,
                    summary=summary,
                    source_kind=feed["source_kind"],
                    importance_score=_score_candidate(
                        title=title,
                        summary=summary,
                        published_at=published_at,
                        now=now,
                        source_kind=feed["source_kind"],
                    ),
                )
            )

    minimum_candidates_required = 3
    if len(raw_candidates) < minimum_candidates_required:
        failure_detail = "; ".join(feed_failures) if feed_failures else "No feed parsing failures were recorded."
        raise SourceCollectionError(
            "Fewer than three AI-relevant candidates were collected from approved feeds in the last 24 hours. "
            f"Collected={len(raw_candidates)}. {failure_detail}"
        )

    ranked_candidates = sorted(
        raw_candidates,
        key=lambda item: (item.importance_score, item.published_at),
        reverse=True,
    )
    return ranked_candidates
