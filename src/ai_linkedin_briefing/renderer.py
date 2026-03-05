from __future__ import annotations

from .models import NewsletterDraft


def render_newsletter_markdown(draft: NewsletterDraft) -> str:
    sections = [f"# {draft.date_label}", ""]
    for story in draft.stories:
        sections.append(f"**{story.headline}**")
        sections.append("")
        sections.append(story.body)
        sections.append("")
    return "\n".join(sections).strip() + "\n"
