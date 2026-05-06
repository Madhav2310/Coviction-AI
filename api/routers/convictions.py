"""

Conviction router — view and manage evolving belief scores.

Supports listing, detail with audit trail, manual score adjustments.

"""

from uuid import UUID

from typing import Optional



from fastapi import APIRouter, Depends, HTTPException, Query

from pydantic import BaseModel, Field

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from db.postgres import get_db

from models.tables import Conviction, ConvictionLog, Entity, utcnow

from schemas.knowledge import ConvictionOut, ConvictionDetail, ConvictionLogOut

from services.conviction_engine import apply_passive_decay

from core.auth import get_user_id



router = APIRouter(prefix="/knowledge", tags=["knowledge"])





@router.get("/convictions")

async def list_convictions(

    sort: str = Query("score", description="Sort: score, recent, signals"),

    limit: int = Query(30, ge=1, le=100),

    offset: int = Query(0, ge=0),

    db: AsyncSession = Depends(get_db),

):

    """List all convictions for the user, sorted by score/recency/signals."""

    user_id = await get_user_id(db)



    query = (

        select(Conviction)

        .options(selectinload(Conviction.entity))

        .where(Conviction.user_id == user_id)

    )



    if sort == "recent":

        query = query.order_by(Conviction.updated_at.desc())

    elif sort == "signals":

        query = query.order_by(Conviction.signal_count.desc())

    else:  # score (highest conviction first)

        query = query.order_by(Conviction.score.desc())



    query = query.offset(offset).limit(limit)

    result = await db.execute(query)

    convictions = result.scalars().all()



    items = []

    now = utcnow()

    for c in convictions:

        # Apply passive decay based on time since last signal

        days_silent = 0.0

        if c.last_signal_date:

            days_silent = (now - c.last_signal_date).total_seconds() / 86400.0

        display_score = apply_passive_decay(c.score, days_silent)



        items.append(ConvictionDetail(

            id=c.id,

            entity_id=c.entity_id,

            thesis_text=c.thesis_text,

            score=round(display_score, 4),

            signal_count=c.signal_count,

            last_signal_date=c.last_signal_date,

            created_at=c.created_at,

            updated_at=c.updated_at,

            entity_name=c.entity.name if c.entity else None,

            logs=[],  # Don't load logs for list view

        ))



    return items





@router.get("/convictions/{conviction_id}")

async def get_conviction_detail(

    conviction_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Get full conviction detail with audit trail (score history)."""

    user_id = await get_user_id(db)



    result = await db.execute(

        select(Conviction)

        .options(selectinload(Conviction.entity), selectinload(Conviction.logs))

        .where(Conviction.id == conviction_id, Conviction.user_id == user_id)

    )

    conviction = result.scalar_one_or_none()

    if not conviction:

        raise HTTPException(status_code=404, detail="Conviction not found")



    log_outs = [

        ConvictionLogOut(

            id=log.id,

            old_score=round(log.old_score, 4),

            new_score=round(log.new_score, 4),

            trigger_observation_id=log.trigger_observation_id,

            reasoning=log.reasoning,

            created_at=log.created_at,

        )

        for log in sorted(conviction.logs, key=lambda x: x.created_at, reverse=True)

    ]



    return ConvictionDetail(

        id=conviction.id,

        entity_id=conviction.entity_id,

        thesis_text=conviction.thesis_text,

        score=round(conviction.score, 4),

        signal_count=conviction.signal_count,

        last_signal_date=conviction.last_signal_date,

        created_at=conviction.created_at,

        updated_at=conviction.updated_at,

        entity_name=conviction.entity.name if conviction.entity else None,

        logs=log_outs,

    )





class ManualScoreAdjust(BaseModel):

    score: float = Field(..., ge=0.0, le=1.0, description="New conviction score")

    reason: str = Field(..., min_length=1, description="Why are you adjusting this score?")





@router.patch("/convictions/{conviction_id}/score")

async def adjust_conviction_score(

    conviction_id: UUID,

    body: ManualScoreAdjust,

    db: AsyncSession = Depends(get_db),

):

    """Manually adjust a conviction score (VC override). Creates audit log entry."""

    user_id = await get_user_id(db)



    result = await db.execute(

        select(Conviction).where(Conviction.id == conviction_id, Conviction.user_id == user_id)

    )

    conviction = result.scalar_one_or_none()

    if not conviction:

        raise HTTPException(status_code=404, detail="Conviction not found")



    old_score = conviction.score

    conviction.score = body.score

    conviction.updated_at = utcnow()



    log_entry = ConvictionLog(

        conviction_id=conviction.id,

        old_score=round(old_score, 4),

        new_score=round(body.score, 4),

        trigger_observation_id=None,  # Manual adjustment

        reasoning=f"Manual adjustment: {body.reason}",

    )

    db.add(log_entry)

    await db.commit()

    await db.refresh(conviction)



    return ConvictionOut.model_validate(conviction)





class ThesisCreate(BaseModel):

    thesis_text: str = Field(..., min_length=3, description="The thesis statement")

    entity_id: Optional[UUID] = Field(None, description="Link to an entity (optional)")

    initial_score: float = Field(0.5, ge=0.0, le=1.0)





@router.post("/convictions")

async def create_conviction(

    body: ThesisCreate,

    db: AsyncSession = Depends(get_db),

):

    """Manually create a thesis conviction (user-initiated)."""

    user_id = await get_user_id(db)



    # Validate entity if provided

    if body.entity_id:

        ent_result = await db.execute(

            select(Entity).where(Entity.id == body.entity_id, Entity.user_id == user_id)

        )

        if not ent_result.scalar_one_or_none():

            raise HTTPException(status_code=404, detail="Entity not found")



        # Dedup guard: check if conviction already exists for this entity

        existing = await db.execute(

            select(Conviction).where(

                Conviction.user_id == user_id,

                Conviction.entity_id == body.entity_id,

            ).limit(1)

        )

        if existing.scalars().first():

            raise HTTPException(

                status_code=409,

                detail="A conviction already exists for this entity. Use PATCH to adjust the score instead.",

            )



    conviction = Conviction(

        user_id=user_id,

        entity_id=body.entity_id,

        thesis_text=body.thesis_text,

        score=body.initial_score,

        signal_count=0,

    )

    db.add(conviction)

    await db.commit()

    await db.refresh(conviction)



    return ConvictionOut.model_validate(conviction)
