# AI LinkedIn Briefing Agent Spec

## Purpose
- Build an agent that creates a daily AI newsletter from credible sources and publishes it to LinkedIn at 8:00 AM San Francisco time.
- After publishing the newsletter, create and publish a LinkedIn post that summarizes the same edition.

## Goals
- Run automatically every day on a server.
- Use only approved high-credibility sources.
- Produce output that matches `newsletter_template.md`.
- Follow source rules in `source_criteria.md`.
- Publish consistently at the scheduled time without manual intervention.

## Non-Goals
- Real-time breaking news alerts during the day
- Broad web scraping across unapproved sources
- Human review as a required daily step
- Complex multi-channel publishing in the first version

## Core Agent Model
- Think: use an LLM to rank stories, summarize them, and draft the newsletter and LinkedIn post
- Act: use tools to fetch source content, validate dates, render output, and publish to LinkedIn
- Observe: log each stage, validate outputs, and stop on failure with clear error messages

## Inputs
- `newsletter_template.md`
- `source_criteria.md`
- Runtime clock in `America/Los_Angeles`
- Approved source URLs and feeds
- LinkedIn browser credentials or a persistent authenticated browser session
- Environment variables for secrets and configuration

## Outputs
- One daily newsletter draft in Markdown
- One daily LinkedIn post in plain text
- A run log with timestamps, source URLs, selected stories, and publish results

## Daily Workflow

### 1. Trigger
- Run once per day at 8:00 AM in `America/Los_Angeles`
- Use a server-side scheduler
- Do not depend on a local machine being awake

### 2. Collect Source Candidates
- Query only approved sources
- Pull items published in the last 24 hours
- Capture title, URL, publisher, publish timestamp, and article text or summary
- Reject items with missing publish times unless the source is official and the date can be verified another way

### 3. Validate and Filter
- Exclude duplicate stories about the same event
- Exclude opinion pieces and weak sources
- Exclude items outside the 24-hour window
- Exclude items whose claims cannot be understood clearly enough to summarize safely
- If fewer than five credible candidates remain, fail loudly

### 4. Rank the Stories
- Rank by importance to general professionals
- Prefer clear impact in one of these areas:
- product launches
- model releases
- funding and partnerships
- regulation and legal moves
- infrastructure and chips
- major research developments
- Prefer diversity across themes so the five stories are not all from one company unless the news day truly demands it

### 5. Draft the Newsletter
- Use `newsletter_template.md` as the output contract
- Write exactly five items
- Keep language at a sixth-grade reading level
- Use plain English and active voice
- For each item:
- write a bold headline
- write one compact paragraph of 2 to 4 sentences
- explain what happened
- explain why it matters
- store the supporting source URL internally even if not shown in the final sample format
- Keep the first line as a Markdown heading in the form `# <Day, DD Month YYYY>` because the LinkedIn browser flow starts by pasting the raw Markdown into the editor

### 6. Draft the LinkedIn Post
- Base the post on the completed newsletter
- Summarize the edition as a whole
- Start the first sentence with the exact phrase `In today's AI Briefing,`
- Mention the biggest themes or companies from that day
- Keep it to one short paragraph
- End with a small set of relevant hashtags

### 7. Validate Output
- Confirm there are exactly five items
- Confirm all source URLs are from approved domains
- Confirm publish timestamps are within the last 24 hours
- Confirm the writing style matches the template rules
- Confirm the post is derived from the newsletter and not from unrelated material
- If validation fails, stop and log the reason

### 8. Publish to LinkedIn
- Use browser automation with a stable authenticated session
- Publish the newsletter first
- Publish the LinkedIn post after the newsletter succeeds
- If newsletter publishing fails, do not publish the post
- Reuse the same browser session for both publish actions
- Detect whether LinkedIn is asking for login, checkpoint verification, or extra prompts before attempting to publish
- Stop if the session is not valid rather than trying to guess through auth flows
- In the newsletter editor, paste the raw Markdown body using `Paste and match style`
- After paste, move the date text from the leading `# <date>` line into the LinkedIn article title field
- Treat this raw-paste flow as the source of truth unless LinkedIn changes the editor behavior

### 9. Log and Archive
- Save the final newsletter and post with timestamps
- Save the selected source URLs and article titles
- Save publish response IDs or error messages

## Publishing Strategy

### Chosen Option
- Use LinkedIn browser automation for both the newsletter and the follow-up post

Reason:
- current public LinkedIn documentation supports normal post publishing APIs but does not expose a documented newsletter publishing API
- the required workflow is newsletter first, then post
- one browser session can perform both actions in sequence

### Practical Design
- Build the agent with a publisher interface
- Support:
- `linkedin_browser_publisher`
- Start with `linkedin_browser_publisher` as the production path
- Keep the publisher interface narrow so a future API publisher can be added without changing the drafting pipeline
- Prefer Playwright over ad hoc browser scripting because it gives more reliable selectors, screenshots, and failure diagnostics
- Store browser state securely so the server can reuse an authenticated session

## Scheduling Spec
- Schedule time: `08:00`
- Schedule timezone: `America/Los_Angeles`
- Handle daylight saving time automatically through timezone-aware scheduling
- Prevent duplicate runs on the same day

## Failure Modes
- Not enough credible stories in the last 24 hours
- Approved sources unavailable or changed format
- Publish timestamps missing or ambiguous
- LinkedIn auth expired
- LinkedIn shows a checkpoint, MFA challenge, or consent screen
- LinkedIn page layout changes break the automation flow
- Browser session storage becomes invalid
- Draft fails validation against template or source rules

## Failure Handling
- Fail loudly
- Do not publish partial output
- Record the exact stage and error
- Preserve source and draft artifacts for debugging

## Configuration
- `OPENAI_API_KEY`
- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `LINKEDIN_BROWSER_STATE_PATH`
- `TIMEZONE=America/Los_Angeles`
- `PUBLISH_HOUR=8`

## Suggested First Implementation
- Language: Python
- Scheduler: cron or systemd timer on the server
- Storage: local Markdown and JSON artifacts
- Logging: structured JSON logs plus plain-text run summaries
- Source fetching: RSS where available, otherwise direct fetch from approved pages
- Publishing: Playwright-based browser automation behind a publisher interface

## Acceptance Criteria
- The agent runs on a server without manual intervention
- It selects exactly five stories from approved sources within the last 24 hours
- It creates a newsletter that matches `newsletter_template.md`
- It creates a LinkedIn post that matches the sample style
- It publishes both items through a browser session in the right order
- It publishes at 8:00 AM `America/Los_Angeles`
- It logs every run and fails loudly on bad input or publish errors
