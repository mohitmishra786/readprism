from dataclasses import dataclass, field
from app.models.interest_graph import InterestNode, InterestEdge


@dataclass
class UserInterestGraph:
    nodes: list[InterestNode] = field(default_factory=list)
    edges: list[InterestEdge] = field(default_factory=list)
