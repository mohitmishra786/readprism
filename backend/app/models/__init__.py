from app.models.billing import BillingEvent
from app.models.content import ContentItem, UserContentInteraction
from app.models.creator import Creator, CreatorPlatform
from app.models.creator_trust import CreatorTopicTrust
from app.models.digest import (
    Digest,
    DigestFeedbackPrompt,
    DigestImpression,
    DigestItem,
    ImpressionRollup,
    RankerWeightRevision,
)
from app.models.feed import Feed
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.meta_weights import UserMetaWeights
from app.models.source import Source
from app.models.user import User

# Importing every model here registers it on Base.metadata. This is required so
# that Base.metadata.create_all / drop_all (used by tests/conftest.py) see the
# full schema — otherwise tables created only by Alembic migrations (but not
# imported anywhere on the app import path) are missing from metadata, and
# drop_all fails on dependent FKs (e.g. creator_topic_trust → creators).
__all__ = [
    "BillingEvent",
    "Feed",
    "User",
    "Source",
    "Creator",
    "CreatorPlatform",
    "CreatorTopicTrust",
    "ContentItem",
    "UserContentInteraction",
    "InterestNode",
    "InterestEdge",
    "Digest",
    "DigestItem",
    "DigestImpression",
    "ImpressionRollup",
    "DigestFeedbackPrompt",
    "RankerWeightRevision",
    "UserMetaWeights",
]
