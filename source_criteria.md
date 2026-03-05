# Source Criteria

## Purpose
- Define which sources the agent may use for the daily AI newsletter and LinkedIn post.
- Keep source selection simple, credible, and easy to audit.

## Approved Source Categories

### 1. Official Provider Blogs
- OpenAI
- Anthropic
- Google
- Perplexity
- Google DeepMind
- Google Research Blog

Use these sources for:
- product launches
- model releases
- feature updates
- pricing changes
- policy statements
- official research announcements

Rules:
- Treat these as primary sources for claims about the company itself.
- Do not treat them as neutral sources about competitors or market impact.
- When an official blog makes a major claim, try to verify the broader significance with an independent news source if one exists.

### 2. Major News Providers
- Reuters
- AP News
- TechCrunch AI

### 3. Research and Academic Sources
- BAIR Blog (Berkeley Artificial Intelligence Research)
- MIT News (Artificial Intelligence topic)

### 4. Industry Roundups (Use Sparingly)
- AI Magazine (News section)
- The Rundown AI

Use these sources for:
- breaking news
- funding
- partnerships
- regulation
- lawsuits
- executive moves
- market reaction
- cross-company developments

Rules:
- Prefer Reuters and AP News over lower-tier coverage when the same story appears in multiple places.
- If Reuters and AP both cover the same event, either is acceptable.
- Use the clearest and most complete version, not both, unless they materially add different facts.
- Use TechCrunch when Reuters/AP have no equivalent item in the required time window, or as a secondary confirmation source.

Rules for research and academic sources:
- Use these for technical breakthroughs, benchmark advances, or peer-reviewed results.
- Do not use them for market claims unless independently confirmed by Reuters/AP/TechCrunch.

Rules for industry roundups:
- Use only when primary and major news sources do not provide enough breadth.
- Do not use roundups as the sole source for high-stakes claims.

## Ranking Rules
- Prefer primary sources when the story is a direct announcement from the company.
- Prefer Reuters or AP News when the story is about external validation, controversy, regulation, partnerships, or financial impact.
- If both an official blog and Reuters or AP cover the same story, use the official source for the precise announcement and the news source to confirm context.

## Exclusions
- Do not use low-trust aggregation sites.
- Do not use opinion pieces as the basis for a newsletter item.
- Do not use social media posts as the sole source unless the account is an official company account and no better source exists.
- Do not use unnamed or second-hand summaries when a primary or top-tier report is available.
- Do not use sponsored content or advertorial pages as source material.

## Deduplication Rules
- Do not include two newsletter items about the same underlying event.
- If several sources cover the same event, select one primary source and at most one confirming source.

## Output Requirements
- Every newsletter item must keep a record of the source URL used by the agent.
- If an item is based on an official provider blog, mark it internally as `primary_source`.
- If an item is based on Reuters or AP News, mark it internally as `independent_source`.
- If source credibility is unclear, exclude the item.

## Failure Rules
- If fewer than five credible stories are available from approved sources in the last 24 hours, the agent must fail loudly and report the shortfall.
- The agent must not fill gaps with weak sources just to reach five items.

## Approved URLs
- https://openai.com/blog
- https://openai.com/index
- https://www.anthropic.com/news
- https://blog.google
- https://blog.research.google
- https://deepmind.google/discover/blog
- https://www.perplexity.ai/hub/blog
- https://www.reuters.com
- https://apnews.com
- https://techcrunch.com/category/artificial-intelligence/
- https://aimagazine.com/news
- https://bair.berkeley.edu/blog/
- https://news.mit.edu/topic/artificial-intelligence2
- https://www.therundown.ai
