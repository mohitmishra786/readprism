from __future__ import annotations

import hashlib
import json
from typing import Optional

import numpy as np

from app.config import get_settings
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_embedding_service: Optional["EmbeddingService"] = None


class EmbeddingService:
    def __init__(self, model_name: str, device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {model_name} on {device}")
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.dimension = 384

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    async def encode_single(self, text: str) -> list[float]:
        cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
        vector = self.encode([text])[0].tolist()
        await cache_set(cache_key, vector, ttl_seconds=7 * 24 * 3600)
        return vector

    async def encode_batch_cached(self, texts: list[str]) -> list[list[float]]:
        results = []
        to_encode: list[tuple[int, str]] = []

        for i, text in enumerate(texts):
            cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
            cached = await cache_get(cache_key)
            if cached is not None:
                results.append((i, cached))
            else:
                to_encode.append((i, text))

        if to_encode:
            indices, raw_texts = zip(*to_encode)
            vectors = self.encode(list(raw_texts))
            for idx, vec in zip(indices, vectors):
                vec_list = vec.tolist()
                results.append((idx, vec_list))
                cache_key = f"emb:{hashlib.sha256(raw_texts[list(indices).index(idx)].encode()).hexdigest()[:16]}"
                await cache_set(cache_key, vec_list, ttl_seconds=7 * 24 * 3600)

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    @staticmethod
    def build_embedding_text(title: str, summary_brief: str | None) -> str:
        text = title
        if summary_brief:
            text += ". " + summary_brief
        return text[:2048]


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
        )
    return _embedding_service
