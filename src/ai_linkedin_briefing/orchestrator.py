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
    newsletter = draft_newsletter(candidates=candidates, now=now, timezone_name=config.timezone)
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
