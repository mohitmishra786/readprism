from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ContentItemRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    source_id: uuid.UUID | None
    creator_platform_id: uuid.UUID | None
    url: str
    title: str
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    summary_headline: str | None
    summary_brief: str | None
    summary_detailed: str | None
    reading_time_minutes: int | None
    content_depth_score: float | None
    word_count: int | None
    has_citations: bool
    is_original_reporting: bool | None
    topic_clusters: list
    summarization_cached: bool
    created_at: datetime


class UserContentInteractionCreate(BaseModel):
    content_item_id: uuid.UUID
    read_completion_pct: float | None = None
    time_on_page_seconds: int | None = None
    explicit_rating: int | None = None
    explicit_rating_reason: str | None = None
    saved: bool = False
    skipped: bool = False


class UserContentInteractionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    content_item_id: uuid.UUID
    prs_score: float | None
    was_suggested: bool
    surfaced_in_digest: bool
    read_completion_pct: float | None
    time_on_page_seconds: int | None
    explicit_rating: int | None
    explicit_rating_reason: str | None
    saved: bool
    skipped: bool
    created_at: datetime


class FeedItem(BaseModel):
    model_config = {"from_attributes": True}

    content: ContentItemRead
    prs_score: float | None
    signal_breakdown: dict
