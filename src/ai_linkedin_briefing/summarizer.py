from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timezone

import httpx
from bs4 import BeautifulSoup

from .exceptions import BriefingError
from .models import StoryCandidate


class SummarizationError(BriefingError):
    """Raised when open-source model summarization cannot produce a valid story."""


_DISALLOWED_HEADLINE_PREFIX = re.compile(r"^\s*(exclusive|breaking|analysis|opinion)\s*:?\s*", re.IGNORECASE)


@dataclass(frozen=True)
class StorySummary:
    headline: str
    body: str


def _normalize_text(text: str) -> str:
    compact = " ".join(text.split())
    return compact.replace("—", "-").replace("–", "-").strip()


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _ensure_terminal_punctuation(text: str) -> str:
    value = text.strip()
    if not value:
        return value
    value_without_closers = value.rstrip("\"')]} ")
    if value_without_closers and value_without_closers[-1] in ".!?":
        return value
    return f"{value}."


def _extract_article_text(html: str, max_chars: int = 8000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form"]):
        tag.decompose()
    paragraphs = []
    for node in soup.find_all(["p", "article", "h1", "h2", "h3"]):
        text = _normalize_text(node.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)
    merged = " ".join(paragraphs)
    if len(merged) > max_chars:
        return merged[:max_chars]
    return merged


class OpenSourceStorySummarizer:
    def __init__(
        self,
        base_url: str,
        model: str,
        instruction_context: str,
        ollama_timeout_seconds: int = 120,
        article_fetch_timeout_seconds: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.instruction_context = instruction_context.strip()
        self.ollama_timeout_seconds = ollama_timeout_seconds
        self.article_fetch_timeout_seconds = article_fetch_timeout_seconds

    def summarize(self, candidate: StoryCandidate) -> StorySummary:
        article_text = self._fetch_article_text(str(candidate.url))
        source_facts = {
            "publisher": candidate.publisher,
            "url": str(candidate.url),
            "published_at_utc": candidate.published_at.astimezone(timezone.utc).isoformat(),
            "title": candidate.title,
            "rss_summary": candidate.summary,
            "article_excerpt": article_text,
        }
        prompt = self._build_prompt(source_facts)
        response_json = self._query_ollama(prompt)

        headline = _normalize_text(str(response_json.get("headline", "")))
        headline = _DISALLOWED_HEADLINE_PREFIX.sub("", headline).strip()
        summary_text = _normalize_text(str(response_json.get("summary", "")))
        why_text = _normalize_text(str(response_json.get("why_it_matters", "")))

        if not headline:
            raise SummarizationError(f"Model returned empty headline for source: {candidate.url}")
        if not summary_text:
            raise SummarizationError(f"Model returned empty summary for source: {candidate.url}")
        if not why_text:
            raise SummarizationError(f"Model returned empty why_it_matters for source: {candidate.url}")

        if not why_text.lower().startswith(("this matters because", "this is important because")):
            why_text = f"This matters because {why_text[0].lower() + why_text[1:]}" if len(why_text) > 1 else (
                "This matters because it has practical impact."
            )

        body = (
            f"{_ensure_terminal_punctuation(summary_text)} "
            f"{_ensure_terminal_punctuation(why_text)} "
            f"(Source: {candidate.publisher})"
        )
        return StorySummary(headline=headline, body=body)

    def _build_prompt(self, source_facts: dict[str, str]) -> str:
        facts_json = json.dumps(source_facts, ensure_ascii=True)
        return (
            "You are writing an AI daily briefing for professionals.\n"
            "Return ONLY strict JSON with keys: headline, summary, why_it_matters.\n"
            "Follow the STYLE_AND_RULES exactly.\n"
            "Rules:\n"
            "- Use plain English at roughly sixth-grade reading level.\n"
            "- Active voice, no hype, no jargon, no clickbait.\n"
            "- Do not use these headline prefixes: EXCLUSIVE, BREAKING, ANALYSIS, OPINION.\n"
            "- Do not include URLs.\n"
            "- Do not include source in summary text.\n"
            "- Avoid em dashes.\n"
            "- summary: 1-2 sentences describing what happened.\n"
            "- why_it_matters: exactly 1 sentence starting with 'This matters because'.\n"
            "- Keep factual and anchored to the provided facts only.\n\n"
            f"STYLE_AND_RULES={self.instruction_context}\n\n"
            f"FACTS_JSON={facts_json}\n"
        )

    def _query_ollama(self, prompt: str) -> dict[str, str]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
            },
        }
        try:
            response = httpx.post(url, json=payload, timeout=self.ollama_timeout_seconds)
        except httpx.HTTPError as exc:
            raise SummarizationError(
                f"Could not reach Ollama at {self.base_url}. Is the server running?"
            ) from exc
        if response.status_code >= 400:
            raise SummarizationError(
                f"Ollama returned HTTP {response.status_code} while summarizing."
            )
        data = response.json()
        raw_response = str(data.get("response", "")).strip()
        if not raw_response:
            raise SummarizationError("Ollama returned an empty summarization response.")
        cleaned = _strip_code_fences(raw_response)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SummarizationError("Ollama response was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise SummarizationError("Ollama response JSON must be an object.")
        return parsed

    def _fetch_article_text(self, url: str) -> str:
        try:
            response = httpx.get(
                url,
                follow_redirects=True,
                timeout=self.article_fetch_timeout_seconds,
                headers={
                    "User-Agent": "ai-linkedin-briefing/0.1",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            if response.status_code >= 400:
                return ""
        except httpx.HTTPError:
            return ""
        return _extract_article_text(response.text)


class OpenAIStorySummarizer:
    def __init__(
        self,
        api_key: str,
        model: str,
        instruction_context: str,
        base_url: str = "https://api.openai.com/v1",
        openai_timeout_seconds: int = 120,
        article_fetch_timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.instruction_context = instruction_context.strip()
        self.base_url = base_url.rstrip("/")
        self.openai_timeout_seconds = openai_timeout_seconds
        self.article_fetch_timeout_seconds = article_fetch_timeout_seconds

    def summarize(self, candidate: StoryCandidate) -> StorySummary:
        article_text = self._fetch_article_text(str(candidate.url))
        source_facts = {
            "publisher": candidate.publisher,
            "url": str(candidate.url),
            "published_at_utc": candidate.published_at.astimezone(timezone.utc).isoformat(),
            "title": candidate.title,
            "rss_summary": candidate.summary,
            "article_excerpt": article_text,
        }
        response_json = self._query_openai(source_facts)

        headline = _normalize_text(str(response_json.get("headline", "")))
        headline = _DISALLOWED_HEADLINE_PREFIX.sub("", headline).strip()
        summary_text = _normalize_text(str(response_json.get("summary", "")))
        why_text = _normalize_text(str(response_json.get("why_it_matters", "")))

        if not headline:
            raise SummarizationError(f"Model returned empty headline for source: {candidate.url}")
        if not summary_text:
            raise SummarizationError(f"Model returned empty summary for source: {candidate.url}")
        if not why_text:
            raise SummarizationError(f"Model returned empty why_it_matters for source: {candidate.url}")

        if not why_text.lower().startswith(("this matters because", "this is important because")):
            if len(why_text) > 1:
                why_text = f"This matters because {why_text[0].lower() + why_text[1:]}"
            else:
                why_text = "This matters because it has practical impact."

        body = (
            f"{_ensure_terminal_punctuation(summary_text)} "
            f"{_ensure_terminal_punctuation(why_text)} "
            f"(Source: {candidate.publisher})"
        )
        return StorySummary(headline=headline, body=body)

    def _query_openai(self, source_facts: dict[str, str]) -> dict[str, str]:
        url = f"{self.base_url}/chat/completions"
        system_prompt = (
            "You write a daily AI briefing newsletter.\n"
            "Follow provided rules exactly.\n"
            "Return valid JSON only with keys: headline, summary, why_it_matters."
        )
        user_prompt = (
            "STYLE_AND_RULES:\n"
            f"{self.instruction_context}\n\n"
            "ADDITIONAL_FORMAT_RULES:\n"
            "- Headline must be short, plain English, and not start with EXCLUSIVE/BREAKING/ANALYSIS/OPINION.\n"
            "- summary must be 1-2 factual sentences about what happened.\n"
            "- why_it_matters must be exactly one sentence and must start with 'This matters because'.\n"
            "- No URLs in headline/summary/why_it_matters.\n"
            "- No em dashes.\n"
            "- Use only the facts provided.\n\n"
            f"FACTS_JSON:\n{json.dumps(source_facts, ensure_ascii=True)}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.openai_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise SummarizationError("Could not reach OpenAI API for summarization.") from exc
        if response.status_code >= 400:
            raise SummarizationError(
                f"OpenAI API returned HTTP {response.status_code} while summarizing: {response.text[:300]}"
            )

        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SummarizationError("OpenAI API response did not include completion choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise SummarizationError("OpenAI completion content was empty.")
        cleaned = _strip_code_fences(content)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SummarizationError("OpenAI completion was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise SummarizationError("OpenAI completion JSON must be an object.")
        return parsed

    def _fetch_article_text(self, url: str) -> str:
        try:
            response = httpx.get(
                url,
                follow_redirects=True,
                timeout=self.article_fetch_timeout_seconds,
                headers={
                    "User-Agent": "ai-linkedin-briefing/0.1",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            if response.status_code >= 400:
                return ""
        except httpx.HTTPError:
            return ""
        return _extract_article_text(response.text)
