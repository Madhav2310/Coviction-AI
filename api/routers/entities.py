"""

Entity + Mention router — CRUD for the knowledge layer.

Browse extracted entities, view mentions across sessions, get entity details.

"""

from uuid import UUID

from typing import Optional



from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select, func, case

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from db.postgres import get_db

from models.tables import Entity, EntityMention, Observation

from schemas.knowledge import EntityDetail, EntityListItem, MentionOut

from core.auth import get_user_id



router = APIRouter(prefix="/knowledge", tags=["knowledge"])





@router.get("/entities")

async def list_entities(

    entity_type: Optional[str] = Query(None, description="Filter by type: company, person, metric, concept"),

    sort: str = Query("recent", description="Sort: recent, mentions, name"),

    limit: int = Query(50, ge=1, le=200),

    offset: int = Query(0, ge=0),

    db: AsyncSession = Depends(get_db),

):

    """List all extracted entities for the user, with mention counts and sentiment summary."""

    user_id = await get_user_id(db)



    # Build query with aggregated sentiment

    query = (

        select(

            Entity,

            func.count(case((EntityMention.sentiment == "positive", 1))).label("pos_count"),

            func.count(case((EntityMention.sentiment == "negative", 1))).label("neg_count"),

            func.count(case((EntityMention.sentiment == "neutral", 1))).label("neu_count"),

        )

        .outerjoin(EntityMention, Entity.id == EntityMention.entity_id)

        .where(Entity.user_id == user_id)

        .group_by(Entity.id)

    )



    if entity_type:

        query = query.where(Entity.entity_type == entity_type)



    if sort == "mentions":

        query = query.order_by(Entity.mention_count.desc())

    elif sort == "name":

        query = query.order_by(Entity.name.asc())

    else:  # recent

        query = query.order_by(Entity.last_seen.desc())



    query = query.offset(offset).limit(limit)

    result = await db.execute(query)

    rows = result.all()



    items = []

    for entity, pos, neg, neu in rows:

        total = pos + neg + neu

        if total == 0:

            sentiment_summary = "neutral"

        elif pos > neg and pos > neu:

            sentiment_summary = "positive"

        elif neg > pos:

            sentiment_summary = "negative"

        else:

            sentiment_summary = "neutral"



        items.append(EntityListItem(

            id=entity.id,

            entity_type=entity.entity_type,

            name=entity.name,

            mention_count=entity.mention_count,

            last_seen=entity.last_seen,

            sentiment_summary=sentiment_summary,

        ))



    return items





@router.get("/entities/{entity_id}")

async def get_entity_detail(

    entity_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Get full entity detail with recent mentions and conviction."""

    user_id = await get_user_id(db)



    result = await db.execute(

        select(Entity)

        .options(selectinload(Entity.mentions), selectinload(Entity.convictions))

        .where(Entity.id == entity_id, Entity.user_id == user_id)

    )

    entity = result.scalar_one_or_none()

    if not entity:

        raise HTTPException(status_code=404, detail="Entity not found")



    # Enrich mentions with observation titles and session dates (batch load)

    recent_mentions = sorted(entity.mentions, key=lambda x: x.created_at, reverse=True)[:20]

    obs_ids = [m.observation_id for m in recent_mentions]

    obs_result = await db.execute(

        select(Observation)

        .options(selectinload(Observation.session))

        .where(Observation.id.in_(obs_ids))

    )

    obs_map = {o.id: o for o in obs_result.scalars().all()}



    mention_outs = []

    for m in recent_mentions:

        obs = obs_map.get(m.observation_id)

        mention_outs.append(MentionOut(

            id=m.id,

            entity_id=m.entity_id,

            observation_id=m.observation_id,

            context_snippet=m.context_snippet,

            sentiment=m.sentiment,

            created_at=m.created_at,

            observation_title=obs.title if obs else None,

            session_date=obs.session.session_date if obs and obs.session else None,

        ))



    # Get conviction (first one, if any)

    conviction_out = None

    if entity.convictions:

        from schemas.knowledge import ConvictionOut

        conviction_out = ConvictionOut.model_validate(entity.convictions[0])



    return EntityDetail(

        id=entity.id,

        entity_type=entity.entity_type,

        name=entity.name,

        metadata_=entity.metadata_ or {},

        first_seen=entity.first_seen,

        last_seen=entity.last_seen,

        mention_count=entity.mention_count,

        mentions=mention_outs,

        conviction=conviction_out,

    )





@router.get("/entities/{entity_id}/mentions")

async def list_entity_mentions(

    entity_id: UUID,

    limit: int = Query(20, ge=1, le=100),

    offset: int = Query(0, ge=0),

    db: AsyncSession = Depends(get_db),

):

    """List all mentions of an entity across observations."""

    user_id = await get_user_id(db)



    # Verify entity belongs to user

    ent_result = await db.execute(

        select(Entity).where(Entity.id == entity_id, Entity.user_id == user_id)

    )

    if not ent_result.scalar_one_or_none():

        raise HTTPException(status_code=404, detail="Entity not found")



    result = await db.execute(

        select(EntityMention)

        .where(EntityMention.entity_id == entity_id)

        .order_by(EntityMention.created_at.desc())

        .offset(offset)

        .limit(limit)

    )

    mentions = result.scalars().all()



    # Batch-load observations to avoid N+1

    obs_ids = [m.observation_id for m in mentions]

    obs_result = await db.execute(

        select(Observation)

        .options(selectinload(Observation.session))

        .where(Observation.id.in_(obs_ids))

    )

    obs_map = {o.id: o for o in obs_result.scalars().all()}



    mention_outs = []

    for m in mentions:

        obs = obs_map.get(m.observation_id)

        mention_outs.append(MentionOut(

            id=m.id,

            entity_id=m.entity_id,

            observation_id=m.observation_id,

            context_snippet=m.context_snippet,

            sentiment=m.sentiment,

            created_at=m.created_at,

            observation_title=obs.title if obs else None,

            session_date=obs.session.session_date if obs and obs.session else None,

        ))



    return mention_outs





@router.get("/panel")

async def get_knowledge_panel(

    db: AsyncSession = Depends(get_db),

):

    """

    Aggregate endpoint for the frontend knowledge panel.

    Returns entities, top convictions, and recent patterns in one call.

    """

    from models.tables import Conviction

    from schemas.knowledge import KnowledgePanelData, ConvictionDetail, ConvictionLogOut, PatternOut



    user_id = await get_user_id(db)



    # Top entities (by mention count)

    ent_result = await db.execute(

        select(Entity)

        .where(Entity.user_id == user_id)

        .order_by(Entity.mention_count.desc())

        .limit(20)

    )

    entities_list = ent_result.scalars().all()



    entity_items = [

        EntityListItem(

            id=e.id,

            entity_type=e.entity_type,

            name=e.name,

            mention_count=e.mention_count,

            last_seen=e.last_seen,

        )

        for e in entities_list

    ]



    # Top convictions (highest score)

    conv_result = await db.execute(

        select(Conviction)

        .options(selectinload(Conviction.entity), selectinload(Conviction.logs))

        .where(Conviction.user_id == user_id)

        .order_by(Conviction.score.desc())

        .limit(10)

    )

    convictions_list = conv_result.scalars().all()



    conviction_items = []

    for c in convictions_list:

        logs = [

            ConvictionLogOut(

                id=l.id,

                old_score=round(l.old_score, 4),

                new_score=round(l.new_score, 4),

                trigger_observation_id=l.trigger_observation_id,

                reasoning=l.reasoning,

                created_at=l.created_at,

            )

            for l in sorted(c.logs, key=lambda x: x.created_at, reverse=True)[:5]

        ]

        conviction_items.append(ConvictionDetail(

            id=c.id,

            entity_id=c.entity_id,

            thesis_text=c.thesis_text,

            score=round(c.score, 4),

            signal_count=c.signal_count,

            last_signal_date=c.last_signal_date,

            created_at=c.created_at,

            updated_at=c.updated_at,

            entity_name=c.entity.name if c.entity else None,

            logs=logs,

        ))



    # Count totals

    ent_count_res = await db.execute(

        select(func.count(Entity.id)).where(Entity.user_id == user_id)

    )

    conv_count_res = await db.execute(

        select(func.count(Conviction.id)).where(Conviction.user_id == user_id)

    )



    # Patterns: detect from data (lightweight, synchronous)

    patterns = await _detect_quick_patterns(user_id, db)



    return KnowledgePanelData(

        entities=entity_items,

        top_convictions=conviction_items,

        recent_patterns=patterns,

        entity_count=ent_count_res.scalar() or 0,

        conviction_count=conv_count_res.scalar() or 0,

    )





async def _detect_quick_patterns(user_id: UUID, db: AsyncSession) -> list:

    """Quick pattern detection from entity/conviction data."""

    from schemas.knowledge import PatternOut

    patterns = []



    # Pattern: Trending entities (3+ mentions)

    try:

        trending_result = await db.execute(

            select(Entity)

            .where(

                Entity.user_id == user_id,

                Entity.mention_count >= 3,

            )

            .order_by(Entity.mention_count.desc())

            .limit(5)

        )

        trending = trending_result.scalars().all()

        if trending:

            names = [e.name for e in trending]

            patterns.append(PatternOut(

                pattern_type="trending_entity",

                title="Trending Entities",

                description=f"Frequently mentioned: {', '.join(names)}",

                entity_ids=[e.id for e in trending],

                evidence_count=sum(e.mention_count for e in trending),

            ))

    except Exception:

        pass  # Patterns are best-effort



    # Pattern: High conviction entities

    try:

        from models.tables import Conviction

        high_conv_result = await db.execute(

            select(Conviction)

            .options(selectinload(Conviction.entity))

            .where(

                Conviction.user_id == user_id,

                Conviction.score >= 0.7,

            )

            .order_by(Conviction.score.desc())

            .limit(5)

        )

        high_convictions = high_conv_result.scalars().all()

        if high_convictions:

            names = [c.entity.name for c in high_convictions if c.entity]

            if names:

                patterns.append(PatternOut(

                    pattern_type="high_conviction",

                    title="High Conviction",

                    description=f"Strong belief in: {', '.join(names)}",

                    entity_ids=[c.entity_id for c in high_convictions if c.entity_id],

                    evidence_count=sum(c.signal_count for c in high_convictions),

                ))

    except Exception:

        pass



    return patterns





@router.get("/morning-brief")

async def get_morning_brief(

    db: AsyncSession = Depends(get_db),

):

    """Generate a morning brief — trending entities, conviction shifts, patterns."""

    user_id = await get_user_id(db)



    from services.heartbeat import generate_morning_brief

    brief = await generate_morning_brief(user_id, db)

    return brief
