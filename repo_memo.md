# Memo: AI LinkedIn Briefing Repo

This repo runs your daily AI briefing workflow. It finds recent AI news, picks the top stories, writes a newsletter draft, creates a LinkedIn post draft, and can publish both through a browser flow.

It exists to save time and keep your output consistent. Instead of manually searching many sites, summarizing articles, and formatting posts, you run one command and follow a repeatable process.

Here is how it works:
1. It loads your rules from `newsletter_template.md`, `source_criteria.md`, and `agent_spec.md`.
2. It pulls AI-related stories from approved sources and filters them to recent items.
3. It ranks stories and drafts a five-item newsletter plus a companion LinkedIn post.
4. It writes outputs to local files so you can review them.
5. If publish mode is on, it opens LinkedIn, fills the newsletter editor, adds the companion post text, and completes the publish flow.

In short, this repo is your daily AI briefing assistant: research, draft, and publish in one pipeline with clear guardrails.
