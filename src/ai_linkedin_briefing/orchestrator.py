from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig, DocumentPaths
from .documents import read_required_text
from .drafter import draft_newsletter, draft_post
from .exceptions import ConfigurationError
from .logging_utils import write_json_log
from .output_store import store_outputs
from .publishers.browser import LinkedInBrowserPublisher
from .source_loader import collect_candidates
from .summarizer import OpenAIStorySummarizer, OpenSourceStorySummarizer
from .validator import validate_newsletter, validate_post


def prepare_browser_session(config: AppConfig, headless: bool = False) -> dict[str, str]:
    publisher = LinkedInBrowserPublisher(
        browser_state_path=config.linkedin_browser_state_path,
        email=config.linkedin_email,
        password=config.linkedin_password,
        keychain_service=config.linkedin_keychain_service,
    )
    result = publisher.ensure_session(headless=headless)
    return {
        "session_status": result.detail,
        "state_path": result.state_path,
    }


def run_staging_publish(
    config: AppConfig,
    newsletter_path: Path,
    post_path: Path,
    headless: bool = False,
) -> dict[str, str]:
    if not newsletter_path.exists():
        raise ConfigurationError(f"Staging newsletter file not found: {newsletter_path}")
    if not post_path.exists():
        raise ConfigurationError(f"Staging post file not found: {post_path}")

    newsletter_text = newsletter_path.read_text(encoding="utf-8")
    post_text = post_path.read_text(encoding="utf-8")

    publisher = LinkedInBrowserPublisher(
        browser_state_path=config.linkedin_browser_state_path,
        email=config.linkedin_email,
        password=config.linkedin_password,
        keychain_service=config.linkedin_keychain_service,
    )
    newsletter_result = publisher.publish_newsletter_text(
        newsletter_markdown=newsletter_text,
        companion_post_text=post_text,
        headless=headless,
    )
    return {
        "staging_newsletter_path": str(newsletter_path),
        "staging_post_path": str(post_path),
        "publish_status": newsletter_result.detail,
        "post_status": (
            "Companion post text was included in the LinkedIn newsletter publish step; "
            "separate feed-post publish was not executed."
        ),
    }


def run_agent(config: AppConfig, paths: DocumentPaths, publish: bool = False) -> dict[str, str]:
    now = datetime.now(timezone.utc)

    newsletter_template = read_required_text(paths.newsletter_template)
    source_criteria = read_required_text(paths.source_criteria)
    agent_spec = read_required_text(paths.agent_spec)

    candidates = collect_candidates(now=now)
    instruction_context = _build_instruction_context(
        newsletter_template=newsletter_template,
        source_criteria=source_criteria,
        agent_spec=agent_spec,
    )
    summarizer = _build_summarizer(config, instruction_context=instruction_context)
    newsletter = draft_newsletter(
        candidates=candidates,
        now=now,
        timezone_name=config.timezone,
        summarizer=summarizer,
    )
    post = draft_post(newsletter)

    validate_newsletter(newsletter)
    validate_post(post)

    stored_paths = store_outputs(paths.output_dir, newsletter, post)
    log_path = write_json_log(
        paths.log_dir,
        f"{now.strftime('%Y%m%dT%H%M%SZ')}_run.json",
        {
            "candidate_count": len(candidates),
            "selected_candidates": [
                {
                    "title": candidate.title,
                    "publisher": candidate.publisher,
                    "published_at": candidate.published_at.isoformat(),
                    "url": str(candidate.url),
                    "importance_score": candidate.importance_score,
                }
                for candidate in candidates[:5]
            ],
            "newsletter_path": str(stored_paths["newsletter"]),
            "post_path": str(stored_paths["post"]),
            "publish_attempted": publish,
            "documents_loaded": {
                "newsletter_template_chars": len(newsletter_template),
                "source_criteria_chars": len(source_criteria),
                "agent_spec_chars": len(agent_spec),
            },
            "summarizer_backend": config.summarizer_backend,
            "summarizer_model": _selected_model_name(config),
        },
    )

    results = {
        "newsletter_path": str(stored_paths["newsletter"]),
        "post_path": str(stored_paths["post"]),
        "log_path": str(log_path),
    }

    if publish:
        publisher = LinkedInBrowserPublisher(
            browser_state_path=config.linkedin_browser_state_path,
            email=config.linkedin_email,
            password=config.linkedin_password,
            keychain_service=config.linkedin_keychain_service,
        )
        newsletter_result = publisher.publish_newsletter(newsletter, companion_post=post)
        if not newsletter_result.success:
            results["publish_status"] = newsletter_result.detail
            return results

        post_result = publisher.publish_post(post)
        results["publish_status"] = post_result.detail

    return results


def _build_summarizer(config: AppConfig, instruction_context: str):
    backend = config.summarizer_backend.strip().lower()
    if backend == "none":
        return None
    if backend == "openai":
        if not (config.openai_api_key or "").strip():
            raise ConfigurationError(
                "OPENAI_API_KEY is required when SUMMARIZER_BACKEND=openai."
            )
        return OpenAIStorySummarizer(
            api_key=config.openai_api_key or "",
            model=config.openai_model,
            instruction_context=instruction_context,
            base_url=config.openai_base_url,
            openai_timeout_seconds=config.openai_timeout_seconds,
            article_fetch_timeout_seconds=config.article_fetch_timeout_seconds,
        )
    if backend == "ollama":
        return OpenSourceStorySummarizer(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            instruction_context=instruction_context,
            ollama_timeout_seconds=config.ollama_timeout_seconds,
            article_fetch_timeout_seconds=config.article_fetch_timeout_seconds,
        )
    raise ConfigurationError(f"Unsupported summarizer backend: {config.summarizer_backend}")


def _selected_model_name(config: AppConfig) -> str | None:
    backend = config.summarizer_backend.strip().lower()
    if backend == "openai":
        return config.openai_model
    if backend == "ollama":
        return config.ollama_model
    return None


def _build_instruction_context(
    newsletter_template: str,
    source_criteria: str,
    agent_spec: str,
) -> str:
    return (
        "NEWSLETTER_TEMPLATE:\n"
        f"{newsletter_template.strip()}\n\n"
        "SOURCE_CRITERIA:\n"
        f"{source_criteria.strip()}\n\n"
        "AGENT_SPEC:\n"
        f"{agent_spec.strip()}"
    )
