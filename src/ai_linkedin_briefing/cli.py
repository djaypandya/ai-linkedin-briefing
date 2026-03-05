from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from .config import build_document_paths, load_config
from .exceptions import BriefingError, ConfigurationError
from .orchestrator import prepare_browser_session, run_agent, run_staging_publish
from .secrets_manager import store_linkedin_password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI LinkedIn briefing agent.")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Attempt LinkedIn publishing after drafting and validation.",
    )
    parser.add_argument(
        "--prepare-browser-session",
        action="store_true",
        help="Open LinkedIn in Playwright, validate login, and save browser session state.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser automation with a visible browser window.",
    )
    parser.add_argument(
        "--publish-staging-newsletter-file",
        type=Path,
        help="Publish a specific staging newsletter markdown file through the browser publisher.",
    )
    parser.add_argument(
        "--publish-staging-post-file",
        type=Path,
        help="Companion staging post text file used in the LinkedIn publish dialog.",
    )
    parser.add_argument(
        "--set-linkedin-credentials",
        action="store_true",
        help="Prompt for LinkedIn credentials and store the password in macOS Keychain.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config()
        paths = build_document_paths()
        if args.set_linkedin_credentials:
            email = (config.linkedin_email or "").strip()
            if not email:
                email = input("LinkedIn email: ").strip()
            if not email:
                raise ConfigurationError("LinkedIn email is required.")
            password = getpass.getpass("LinkedIn password (input hidden): ")
            store_linkedin_password(
                email=email,
                password=password,
                service=config.linkedin_keychain_service,
            )
            results = {
                "credentials_status": "Stored LinkedIn password in macOS Keychain.",
                "email": email,
                "service": config.linkedin_keychain_service,
            }
        elif args.publish_staging_newsletter_file or args.publish_staging_post_file:
            if not args.publish_staging_newsletter_file or not args.publish_staging_post_file:
                parser.error(
                    "--publish-staging-newsletter-file and --publish-staging-post-file must be provided together."
                )
            results = run_staging_publish(
                config=config,
                newsletter_path=args.publish_staging_newsletter_file,
                post_path=args.publish_staging_post_file,
                headless=not args.headed,
            )
        elif args.prepare_browser_session:
            results = prepare_browser_session(config=config, headless=not args.headed)
        else:
            results = run_agent(config=config, paths=paths, publish=args.publish)
    except (BriefingError, PydanticValidationError) as exc:
        print(f"ERROR: {exc}")
        return 1

    if "credentials_status" in results:
        print(f"Credentials: {results['credentials_status']}")
        print(f"Email: {results['email']}")
        print(f"Service: {results['service']}")
        return 0
    if "session_status" in results:
        print(f"Session: {results['session_status']}")
        print(f"State: {results['state_path']}")
        return 0
    if "staging_newsletter_path" in results:
        print(f"Staging newsletter: {results['staging_newsletter_path']}")
        print(f"Staging post: {results['staging_post_path']}")
        print(f"Publish: {results['publish_status']}")
        print(f"Post: {results['post_status']}")
        return 0

    print(f"Newsletter: {results['newsletter_path']}")
    print(f"Post: {results['post_path']}")
    print(f"Log: {results['log_path']}")
    if "publish_status" in results:
        print(f"Publish: {results['publish_status']}")
    return 0
