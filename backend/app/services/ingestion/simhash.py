"""64-bit simhash for near-duplicate titles and bodies.

Stored as 16 hex chars. A Hamming distance of 3 or less is a near duplicate.
Embedding similarity stays in ``semantic_dedup`` (cosine >= 0.92).
"""

from __future__ import annotations

import hashlib

NEAR_DUP_BITS = 3


def simhash_text(text: str) -> str:
    bits = [0] * 64
    for token in _tokens(text):
        digest = hashlib.blake2s(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for index in range(64):
            bits[index] += 1 if value & (1 << index) else -1
    packed = 0
    for index, weight in enumerate(bits):
        if weight > 0:
            packed |= 1 << index
    return f"{packed:016x}"


def hamming(left: str, right: str) -> int:
    try:
        distance = int(left, 16) ^ int(right, 16)
    except ValueError:
        return 64
    return distance.bit_count()


def is_near_duplicate(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hamming(left, right) <= NEAR_DUP_BITS


def _tokens(text: str) -> list[str]:
    found: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found or ["empty"]
