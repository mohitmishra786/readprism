from dataclasses import dataclass, field

from app.models.interest_graph import InterestEdge, InterestNode


@dataclass
class UserInterestGraph:
    nodes: list[InterestNode] = field(default_factory=list)
    edges: list[InterestEdge] = field(default_factory=list)


def cosine_to_unit_score(sim: float) -> float:
    """Map a cosine similarity in [-1, 1] to a signal score in [0, 1].

    Note the *intentional* compression (audit 05-7): sentence-transformer cosine
    similarities are almost always in [0, 1] in practice (near-orthogonal, not
    anti-parallel, for unrelated text), so the effective output range is roughly
    [0.5, 1.0] and genuine mismatch lands near 0.5 (neutral) rather than 0. This
    is deliberate — the ranking treats "unrelated" as neutral, not actively
    negative, and lets the learned weights and other signals do the discriminating.
    Anti-parallel embeddings (sim < 0) do map below 0.5. Centralized here so the
    choice is documented in one place instead of duplicated across every signal.
    """
    return (sim + 1.0) / 2.0
