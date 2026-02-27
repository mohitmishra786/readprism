from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SignalBreakdown(BaseModel):
    semantic: float = 0.0
    reading_depth: float = 0.0
    suggestion: float = 0.0
    explicit_feedback: float = 0.0
    source_trust: float = 0.0
    content_quality: float = 0.0
    temporal_context: float = 0.0
    novelty: float = 0.0


class PRSResult(BaseModel):
    content_item_id: uuid.UUID
    prs_score: float
    signal_breakdown: SignalBreakdown


class InterestAdjustment(BaseModel):
    topic: str
    action: str  # "boost" | "suppress" | "remove"
    duration_days: int | None = None


class InterestGraphNode(BaseModel):
    label: str
    weight: float
    is_core: bool


class InterestGraphEdge(BaseModel):
    from_label: str
    to_label: str
    weight: float


class InterestGraphResponse(BaseModel):
    nodes: list[InterestGraphNode]
    edges: list[InterestGraphEdge]


class SampleRating(BaseModel):
    article_url: str
    title: str
    rating: int  # 1=would read, 0=maybe, -1=not for me


class OnboardingRequest(BaseModel):
    interest_text: str
    sample_ratings: list[SampleRating] = []
    source_opml: str | None = None
