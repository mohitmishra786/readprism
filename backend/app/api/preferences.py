from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.user import User
from app.schemas.ranking import InterestGraphEdge, InterestGraphNode, InterestGraphResponse
from app.schemas.user import UserRead, UserUpdate
from app.utils.logging import get_logger

router = APIRouter(prefix="/preferences", tags=["preferences"])
logger = get_logger(__name__)


@router.get("", response_model=UserRead)
async def get_preferences(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    return UserRead.model_validate(current_user)


@router.put("", response_model=UserRead)
async def update_preferences(
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.digest_frequency is not None:
        current_user.digest_frequency = body.digest_frequency
    if body.digest_time_morning is not None:
        current_user.digest_time_morning = body.digest_time_morning
    if body.digest_max_items is not None:
        current_user.digest_max_items = body.digest_max_items
    if body.serendipity_percentage is not None:
        current_user.serendipity_percentage = max(0, min(50, body.serendipity_percentage))
    if body.timezone is not None:
        current_user.timezone = body.timezone
    await session.flush()
    return UserRead.model_validate(current_user)


@router.get("/interest-graph", response_model=InterestGraphResponse)
async def get_interest_graph(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterestGraphResponse:
    nodes_result = await session.execute(
        select(InterestNode)
        .where(InterestNode.user_id == current_user.id)
        .order_by(InterestNode.weight.desc())
        .limit(50)
    )
    nodes = list(nodes_result.scalars().all())

    node_ids = {n.id for n in nodes}
    edges_result = await session.execute(
        select(InterestEdge)
        .where(
            InterestEdge.user_id == current_user.id,
            InterestEdge.from_node_id.in_(node_ids),
            InterestEdge.to_node_id.in_(node_ids),
        )
    )
    edges = list(edges_result.scalars().all())

    node_label_map = {n.id: n.topic_label for n in nodes}
    return InterestGraphResponse(
        nodes=[
            InterestGraphNode(label=n.topic_label, weight=n.weight, is_core=n.is_core)
            for n in nodes
        ],
        edges=[
            InterestGraphEdge(
                from_label=node_label_map.get(e.from_node_id, ""),
                to_label=node_label_map.get(e.to_node_id, ""),
                weight=e.edge_weight,
            )
            for e in edges
            if e.from_node_id in node_label_map and e.to_node_id in node_label_map
        ],
    )
