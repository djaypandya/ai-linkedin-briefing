from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, HttpUrl


class SourceKind(str, Enum):
    PRIMARY = "primary_source"
    INDEPENDENT = "independent_source"


class StoryCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: HttpUrl
    publisher: str
    published_at: datetime
    summary: str
    source_kind: SourceKind
    importance_score: int


class DraftStory(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: str
    body: str
    source_url: HttpUrl
    publisher: str


class NewsletterDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_at: datetime
    date_label: str
    stories: list[DraftStory]


class PostDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: str


class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    target: str
    detail: str


class BrowserSessionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    detail: str
    state_path: str
