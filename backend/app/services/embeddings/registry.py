"""Provider registry. Rows record which model produced their vector.

MiniLM is 384-d and is the default, including the lite profile.
bge-small-en-v1.5 is 384-d and is the upgraded semantic model (#244).
Nomic is registered at 768-d with the required task prefixes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

MINILM = "all-MiniLM-L6-v2"
BGE_SMALL = "BAAI/bge-small-en-v1.5"
BGE_SMALL_SHORT = "bge-small-en-v1.5"
NOMIC = "nomic-embed-text-v1.5"

MINILM_DIM = 384
BGE_SMALL_DIM = 384
NOMIC_DIM = 768
VERSION = "1"

BGE_SMALL_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass(frozen=True)
class EmbeddingSpec:
    name: str
    dim: int
    version: str
    prefix_document: str = ""
    prefix_query: str = ""
    max_tokens: int = 512


BGE_SPEC = EmbeddingSpec(
    BGE_SMALL,
    BGE_SMALL_DIM,
    VERSION,
    prefix_document="",
    prefix_query=BGE_SMALL_QUERY_PREFIX,
    max_tokens=512,
)

SPECS: dict[str, EmbeddingSpec] = {
    MINILM: EmbeddingSpec(MINILM, MINILM_DIM, VERSION, max_tokens=256),
    BGE_SMALL: BGE_SPEC,
    BGE_SMALL_SHORT: BGE_SPEC,
    NOMIC: EmbeddingSpec(
        NOMIC,
        NOMIC_DIM,
        VERSION,
        prefix_document="search_document: ",
        prefix_query="search_query: ",
        max_tokens=8192,
    ),
}

ALIASES: dict[str, str] = {
    BGE_SMALL_SHORT: BGE_SMALL,
    "sentence-transformers/all-MiniLM-L6-v2": MINILM,
}


def spec_for(name: str) -> EmbeddingSpec:
    canonical = ALIASES.get(name, name)
    try:
        return SPECS[canonical]
    except KeyError as exc:
        raise KeyError(f"unknown embedding model {name}") from exc


def resolve_stored_model(requested: str) -> EmbeddingSpec:
    """Return a 384-d spec. Nomic stays registered until a 768-d column exists."""
    canonical = ALIASES.get(requested, requested)
    spec = SPECS.get(canonical)
    if spec is None:
        if not requested:
            return SPECS[MINILM]
        return EmbeddingSpec(requested, MINILM_DIM, VERSION)
    if spec.dim != MINILM_DIM:
        return SPECS[MINILM]
    return spec


def active_spec(*, model: str, cutover: bool) -> EmbeddingSpec:
    """Selection: EMBEDDING_MODEL=bge-small-en-v1.5 + EMBEDDING_CUTOVER_ENABLED=true makes it active.
    Defaults stay MiniLM; cutover off keeps MiniLM.
    """
    if not cutover:
        return SPECS[MINILM]
    canonical = ALIASES.get(model, model)
    spec = resolve_stored_model(canonical)
    return spec


def hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic stand-in used by tests and the offline retrieval check."""
    vector = [0.0] * dim
    for token in text.lower().split():
        digest = hashlib.blake2s(token.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[slot] += sign
    norm = sum(value * value for value in vector) ** 0.5 or 1.0
    return [value / norm for value in vector]


def prepare_text(text: str, spec: EmbeddingSpec, *, query: bool) -> str:
    prefix = spec.prefix_query if query else spec.prefix_document
    return f"{prefix}{text}"


def encode_with_spec(text: str, spec: EmbeddingSpec, *, query: bool = False) -> list[float]:
    return hash_embed(prepare_text(text, spec, query=query), spec.dim)


def same_model(row_model: str | None, row_dim: int | None, active: EmbeddingSpec) -> bool:
    if row_dim is not None and row_dim != active.dim:
        return False
    if not row_model:
        return active.name == MINILM
    row_canonical = ALIASES.get(row_model, row_model)
    active_canonical = ALIASES.get(active.name, active.name)
    return row_canonical == active_canonical
