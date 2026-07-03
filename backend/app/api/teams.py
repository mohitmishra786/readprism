"""Team endpoints — create teams, manage members, build team digests.

Team capability is gated to the `team` tier. Only team owners can add/remove
members; any member can trigger a digest build.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.teams.builder import build_team_digest
from app.utils.logging import get_logger

router = APIRouter(prefix="/teams", tags=["teams"])
logger = get_logger(__name__)


class TeamCreate(BaseModel):
    name: str


class TeamRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    member_count: int


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


def _require_team_tier(user: User) -> None:
    if user.tier != "team":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team features require the Team plan.",
        )


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TeamRead:
    _require_team_tier(current_user)
    team = Team(name=body.name[:200], created_by=current_user.id)
    session.add(team)
    await session.flush()

    # Creator becomes the owner member.
    owner = TeamMember(team_id=team.id, user_id=current_user.id, role="owner")
    session.add(owner)
    await session.flush()
    return TeamRead(id=team.id, name=team.name, created_by=team.created_by, member_count=1)


@router.get("", response_model=list[TeamRead])
async def list_my_teams(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TeamRead]:
    result = await session.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current_user.id)
    )
    teams = list(result.scalars().all())
    out = []
    for t in teams:
        count_result = await session.execute(
            select(TeamMember).where(TeamMember.team_id == t.id)
        )
        out.append(
            TeamRead(
                id=t.id,
                name=t.name,
                created_by=t.created_by,
                member_count=len(count_result.scalars().all()),
            )
        )
    return out


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    team_id: uuid.UUID,
    body: AddMemberRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_team_tier(current_user)
    # Only an owner can add members.
    owner_check = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
            TeamMember.role == "owner",
        )
    )
    if owner_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can add members.")

    exists = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == body.user_id
        )
    )
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member.")

    member = TeamMember(team_id=team_id, user_id=body.user_id, role="member")
    session.add(member)
    await session.flush()
    return {"status": "ok", "user_id": str(body.user_id)}


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _require_team_tier(current_user)
    owner_check = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
            TeamMember.role == "owner",
        )
    )
    if owner_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can remove members.")

    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    await session.delete(member)
    await session.flush()


@router.post("/{team_id}/digest")
async def trigger_team_digest(
    team_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_team_tier(current_user)
    # Any member may trigger.
    member_check = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == current_user.id
        )
    )
    if member_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member.")

    result = await build_team_digest(team_id, session)
    return result
