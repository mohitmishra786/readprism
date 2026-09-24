"""Provider registry. Rows record which model produced their vector.

MiniLM is 384-d and is the default, including the lite profile. Nomic is
registered at 768-d with the required task prefixes, but it is not activated
unless the cutover flag is on and the golden check has been recorded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

MINILM = "all-MiniLM-L6-v2"
NOMIC = "nomic-embed-text-v1.5"
MINILM_DIM = 384
NOMIC_DIM = 768
VERSION = "1"


@dataclass(frozen=True)
class EmbeddingSpec:
    name: str
    dim: int
    version: str
    prefix_document: str = ""
    prefix_query: str = ""


SPECS = {
    MINILM: EmbeddingSpec(MINILM, MINILM_DIM, VERSION),
    NOMIC: EmbeddingSpec(
        NOMIC,
        NOMIC_DIM,
        VERSION,
        prefix_document="search_document: ",
        prefix_query="search_query: ",
    ),
}


def spec_for(name: str) -> EmbeddingSpec:
    try:
        return SPECS[name]
    except KeyError as exc:
        raise KeyError(f"unknown embedding model {name}") from exc


def active_spec(*, model: str, cutover: bool) -> EmbeddingSpec:
    """Cutover selects Nomic only when the operator has turned the flag on."""
    if cutover and model == NOMIC:
        return spec_for(NOMIC)
    return spec_for(MINILM)


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
    return row_model == active.name and row_dim == active.dim
