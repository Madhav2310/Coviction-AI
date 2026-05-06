"""

Heartbeat service — periodic synthesis and pattern detection.

Runs as background tasks: daily (morning brief) and weekly (deep synthesis).

"""

import logging

from datetime import date, datetime, timedelta, timezone

from uuid import UUID



from sqlalchemy import select, func

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from models.tables import (

    Entity, EntityMention, Conviction, ConvictionLog,

    DailySession, Observation, User, utcnow,

)

from core.model_client import get_model_client

from schemas.knowledge import PatternOut, MorningBriefOut, EntityListItem, ConvictionOut



logger = logging.getLogger(__name__)





async def generate_morning_brief(user_id: UUID, db: AsyncSession) -> MorningBriefOut:

    """

    Daily heartbeat: analyze recent activity and produce a morning brief.

    Surfaces trending entities, conviction shifts, and detected patterns.

    """

    today = date.today()

    week_ago = today - timedelta(days=7)

    week_ago_dt = datetime(week_ago.year, week_ago.month, week_ago.day, tzinfo=timezone.utc)



    # 1. Trending entities — most mentioned in the last 7 days

    trending_result = await db.execute(

        select(

            Entity,

            func.count(EntityMention.id).label("recent_mentions"),

        )

        .join(EntityMention, Entity.id == EntityMention.entity_id)

        .where(

            Entity.user_id == user_id,

            EntityMention.created_at >= week_ago_dt,

        )

        .group_by(Entity.id)

        .order_by(func.count(EntityMention.id).desc())

        .limit(10)

    )

    trending_rows = trending_result.all()



    trending_entities = [

        EntityListItem(

            id=entity.id,

            entity_type=entity.entity_type,

            name=entity.name,

            mention_count=entity.mention_count,

            last_seen=entity.last_seen,

        )

        for entity, _count in trending_rows

    ]



    # 2. Conviction shifts — biggest score changes in the last 7 days

    shift_result = await db.execute(

        select(Conviction)

        .options(selectinload(Conviction.logs))

        .where(

            Conviction.user_id == user_id,

            Conviction.updated_at >= week_ago_dt,

        )

        .order_by(Conviction.updated_at.desc())

        .limit(10)

    )

    shifted_convictions = shift_result.scalars().all()



    # Calculate drift for each

    conviction_shifts = []

    for c in shifted_convictions:

        recent_logs = [l for l in c.logs if l.created_at and l.created_at.date() >= week_ago]

        if recent_logs:

            earliest = min(recent_logs, key=lambda l: l.created_at)

            drift = abs(c.score - earliest.old_score)

            if drift > 0.05:  # Only report meaningful shifts

                conviction_shifts.append(ConvictionOut.model_validate(c))



    # 3. Pattern detection

    patterns = await detect_patterns(user_id, db, lookback_days=7)



    # 4. Generate summary via LLM

    summary = await _generate_morning_summary(

        trending_entities, conviction_shifts, patterns

    )



    return MorningBriefOut(

        date=today,

        trending_entities=trending_entities,

        conviction_shifts=conviction_shifts,

        patterns=patterns,

        summary=summary,

    )





async def detect_patterns(

    user_id: UUID,

    db: AsyncSession,

    lookback_days: int = 14,

) -> list[PatternOut]:

    """

    Cross-session pattern detection.

    Looks for recurring themes, sector concentration, conviction drift, and gaps.

    """

    patterns = []

    cutoff = date.today() - timedelta(days=lookback_days)

    cutoff_dt = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc)



    # Pattern 1: Sector concentration

    # Are they looking at one sector disproportionately?

    try:

        sector_result = await db.execute(

            select(Entity)

            .where(

                Entity.user_id == user_id,

                Entity.entity_type == "company",

                Entity.last_seen >= cutoff_dt,

            )

        )

        companies = sector_result.scalars().all()



        sector_counts: dict[str, list] = {}

        for c in companies:

            meta = c.metadata_ or {}

            sector = meta.get("sector", "unknown")

            if sector != "unknown":

                sector_counts.setdefault(sector, []).append(c)



        for sector, entities in sector_counts.items():

            if len(entities) >= 3:

                patterns.append(PatternOut(

                    pattern_type="sector_concentration",

                    title=f"Deep in {sector.title()}",

                    description=f"You've seen {len(entities)} {sector} companies in the last {lookback_days} days: {', '.join(e.name for e in entities[:5])}",

                    entity_ids=[e.id for e in entities],

                    evidence_count=len(entities),

                    timespan_days=lookback_days,

                ))

    except Exception as e:

        logger.debug(f"Sector concentration pattern failed: {e}")



    # Pattern 2: Conviction drift

    # Any conviction moved >0.15 in the lookback period?

    try:

        conv_result = await db.execute(

            select(Conviction)

            .options(selectinload(Conviction.entity), selectinload(Conviction.logs))

            .where(

                Conviction.user_id == user_id,

                Conviction.signal_count >= 2,

            )

        )

        convictions = conv_result.scalars().all()



        for c in convictions:

            recent_logs = [l for l in c.logs if l.created_at and l.created_at.date() >= cutoff]

            if len(recent_logs) >= 2:

                earliest = min(recent_logs, key=lambda l: l.created_at)

                drift = c.score - earliest.old_score

                if abs(drift) > 0.15:

                    direction = "growing" if drift > 0 else "cooling"

                    entity_name = c.entity.name if c.entity else "Unknown"

                    patterns.append(PatternOut(

                        pattern_type="conviction_drift",

                        title=f"{direction.title()} conviction: {entity_name}",

                        description=f"Your conviction on {entity_name} has {direction} from {earliest.old_score:.0%} to {c.score:.0%} over {len(recent_logs)} signals",

                        entity_ids=[c.entity_id] if c.entity_id else [],

                        evidence_count=len(recent_logs),

                        timespan_days=lookback_days,

                    ))

    except Exception as e:

        logger.debug(f"Conviction drift pattern failed: {e}")



    # Pattern 3: Recurring names (person mentioned across multiple sessions)

    try:

        recurring_result = await db.execute(

            select(

                Entity,

                func.count(func.distinct(Observation.session_id)).label("session_count"),

            )

            .join(EntityMention, Entity.id == EntityMention.entity_id)

            .join(Observation, EntityMention.observation_id == Observation.id)

            .where(

                Entity.user_id == user_id,

                Entity.entity_type == "person",

                Entity.last_seen >= cutoff_dt,

            )

            .group_by(Entity.id)

            .having(func.count(func.distinct(Observation.session_id)) >= 3)

        )

        recurring = recurring_result.all()



        for entity, session_count in recurring:

            patterns.append(PatternOut(

                pattern_type="recurring_person",

                title=f"{entity.name} keeps coming up",

                description=f"{entity.name} mentioned across {session_count} different sessions — worth a deeper look",

                entity_ids=[entity.id],

                evidence_count=entity.mention_count,

                timespan_days=lookback_days,

            ))

    except Exception as e:

        logger.debug(f"Recurring person pattern failed: {e}")



    return patterns





async def _generate_morning_summary(

    trending: list[EntityListItem],

    shifts: list[ConvictionOut],

    patterns: list[PatternOut],

) -> str:

    """Use LLM to synthesize morning brief into a concise summary."""

    if not trending and not shifts and not patterns:

        return "No significant activity to report. Your knowledge graph is quiet."



    parts = []

    if trending:

        names = [e.name for e in trending[:5]]

        parts.append(f"Trending: {', '.join(names)}")

    if shifts:

        parts.append(f"{len(shifts)} conviction(s) shifted recently")

    if patterns:

        titles = [p.title for p in patterns[:3]]

        parts.append(f"Patterns: {'; '.join(titles)}")



    context = "\n".join(parts)



    try:

        mc = get_model_client()

        summary = await mc.chat(

            messages=[

                {"role": "system", "content": "You are Coviction's morning brief writer. Synthesize activity data into 2-3 sharp sentences for a VC. Be direct, no filler."},

                {"role": "user", "content": f"Generate a morning brief summary from this activity data:\n\n{context}"},

            ],

            model=mc.settings.default_fast_model,

            temperature=0.3,

        )

        return summary.strip()

    except Exception:

        return f"Active tracking: {len(trending)} entities trending, {len(shifts)} conviction shifts, {len(patterns)} patterns detected."





async def run_daily_heartbeat(user_id: UUID, db: AsyncSession) -> MorningBriefOut:

    """Entry point for the daily heartbeat cron."""

    logger.info(f"Running daily heartbeat for user {user_id}")

    brief = await generate_morning_brief(user_id, db)

    logger.info(f"Morning brief generated: {len(brief.trending_entities)} trending, {len(brief.patterns)} patterns")

    return brief
