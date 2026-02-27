from __future__ import annotations

import uuid
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

INDEX_NAME = "content_items"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.meilisearch_master_key}",
        "Content-Type": "application/json",
    }


async def ensure_index() -> None:
    """Create the Meilisearch index and configure searchable attributes if needed."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"{settings.meilisearch_url}/indexes/{INDEX_NAME}",
                headers=_headers(),
            )
            if resp.status_code == 404:
                await client.post(
                    f"{settings.meilisearch_url}/indexes",
                    headers=_headers(),
                    json={"uid": INDEX_NAME, "primaryKey": "id"},
                )
                # Configure searchable attributes
                await client.put(
                    f"{settings.meilisearch_url}/indexes/{INDEX_NAME}/settings/searchable-attributes",
                    headers=_headers(),
                    json=["title", "summary_headline", "summary_brief", "author", "topic_clusters"],
                )
                await client.put(
                    f"{settings.meilisearch_url}/indexes/{INDEX_NAME}/settings/filterable-attributes",
                    headers=_headers(),
                    json=["source_id", "creator_platform_id", "topic_clusters"],
                )
        except Exception as e:
            logger.warning(f"Meilisearch index setup failed (non-fatal): {e}")


async def index_content_item(item_id: uuid.UUID, doc: dict[str, Any]) -> None:
    """Index or update a single content item document."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{settings.meilisearch_url}/indexes/{INDEX_NAME}/documents",
                headers=_headers(),
                json=[{"id": str(item_id), **doc}],
            )
        except Exception as e:
            logger.warning(f"Meilisearch index failed for {item_id} (non-fatal): {e}")


async def search_content(
    query: str,
    user_source_ids: list[str],
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Full-text search across the user's ingested content archive."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            payload: dict[str, Any] = {
                "q": query,
                "limit": limit,
                "offset": offset,
                "attributesToHighlight": ["title", "summary_brief"],
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>",
            }
            if user_source_ids:
                payload["filter"] = " OR ".join(
                    [f'source_id = "{sid}"' for sid in user_source_ids]
                )
            resp = await client.post(
                f"{settings.meilisearch_url}/indexes/{INDEX_NAME}/search",
                headers=_headers(),
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("hits", [])
            return []
        except Exception as e:
            logger.warning(f"Meilisearch search failed (non-fatal): {e}")
            return []
