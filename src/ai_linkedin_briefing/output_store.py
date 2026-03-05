from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .logging_utils import ensure_dir
from .models import NewsletterDraft, PostDraft
from .renderer import render_newsletter_markdown


def store_outputs(output_dir: Path, newsletter: NewsletterDraft, post: PostDraft) -> dict[str, Path]:
    ensure_dir(output_dir)
    stamp = newsletter.run_at.strftime("%Y%m%dT%H%M%SZ")
    newsletter_path = output_dir / f"{stamp}_newsletter.md"
    post_path = output_dir / f"{stamp}_post.txt"

    newsletter_path.write_text(render_newsletter_markdown(newsletter), encoding="utf-8")
    post_path.write_text(post.body.strip() + "\n", encoding="utf-8")

    return {
        "newsletter": newsletter_path,
        "post": post_path,
    }
