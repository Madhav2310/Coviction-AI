"""

Global search router — full-text search across all observations.

Uses PostgreSQL to_tsvector/to_tsquery with GIN index, ILIKE fallback.

"""

from uuid import UUID



from fastapi import APIRouter, Depends, Query

from sqlalchemy import select, text

from sqlalchemy.ext.asyncio import AsyncSession



from db.postgres import get_db

from models.tables import User

from schemas.session import ObservationOut, SearchResult, SearchResultGroup

from core.auth import DEMO_USER_EMAIL



router = APIRouter(tags=["search"])





@router.get("/search")

async def global_search(

    q: str = Query(..., min_length=2, description="Search query"),

    limit: int = Query(20, ge=1, le=100),

    db: AsyncSession = Depends(get_db),

):

    """Full-text search across all observations for the demo user.



    Uses PostgreSQL full-text search with ts_rank for relevance ordering.

    Falls back to ILIKE if the query can't be parsed as a tsquery.

    Results are grouped by session for easy navigation.

    """

    # Get demo user

    user_result = await db.execute(

        select(User).where(User.email == DEMO_USER_EMAIL)

    )

    user = user_result.scalar_one_or_none()

    if not user:

        return []



    # Try full-text search first

    try:

        # Build tsquery from user input — plainto_tsquery handles natural language

        fts_query = text(

            """

            SELECT o.id, o.session_id, o.title, o.body, o.sector_tags,

                   o.has_image, o.has_voice, o.voice_transcript, o.image_summary,

                   o.created_at, o.updated_at,

                   ts_rank(

                       to_tsvector('english',

                           coalesce(o.title, '') || ' ' ||

                           coalesce(o.body, '') || ' ' ||

                           coalesce(o.voice_transcript, '') || ' ' ||

                           coalesce(o.image_summary, '')

                       ),

                       plainto_tsquery('english', :query)

                   ) AS rank,

                   s.id AS sid, s.session_date, s.name AS session_name

            FROM observations o

            JOIN daily_sessions s ON o.session_id = s.id

            WHERE s.user_id = :user_id

              AND to_tsvector('english',

                  coalesce(o.title, '') || ' ' ||

                  coalesce(o.body, '') || ' ' ||

                  coalesce(o.voice_transcript, '') || ' ' ||

                  coalesce(o.image_summary, '')

              ) @@ plainto_tsquery('english', :query)

            ORDER BY rank DESC

            LIMIT :limit

            """

        )

        result = await db.execute(

            fts_query,

            {"query": q, "user_id": str(user.id), "limit": limit},

        )

        rows = result.fetchall()

    except Exception:

        rows = []



    # Fallback to ILIKE if FTS returned nothing

    if not rows:

        like_pattern = f"%{q}%"

        ilike_query = text(

            """

            SELECT o.id, o.session_id, o.title, o.body, o.sector_tags,

                   o.has_image, o.has_voice, o.voice_transcript, o.image_summary,

                   o.created_at, o.updated_at,

                   1.0 AS rank,

                   s.id AS sid, s.session_date, s.name AS session_name

            FROM observations o

            JOIN daily_sessions s ON o.session_id = s.id

            WHERE s.user_id = :user_id

              AND (

                  o.title ILIKE :pattern

                  OR o.body ILIKE :pattern

                  OR o.voice_transcript ILIKE :pattern

                  OR o.image_summary ILIKE :pattern

              )

            ORDER BY o.created_at DESC

            LIMIT :limit

            """

        )

        result = await db.execute(

            ilike_query,

            {"user_id": str(user.id), "pattern": like_pattern, "limit": limit},

        )

        rows = result.fetchall()



    # Group results by session

    groups: dict[str, SearchResultGroup] = {}

    for row in rows:

        sid = str(row.sid)

        obs = ObservationOut(

            id=row.id,

            session_id=row.session_id,

            title=row.title,

            body=row.body or "",

            sector_tags=row.sector_tags if isinstance(row.sector_tags, list) else (

                [row.sector_tags] if row.sector_tags else []

            ),

            has_image=row.has_image,

            has_voice=row.has_voice,

            voice_transcript=row.voice_transcript or "",

            image_summary=row.image_summary or "",

            created_at=row.created_at,

            updated_at=row.updated_at,

        )

        search_result = SearchResult(

            observation=obs,

            session_id=row.sid,

            session_name=row.session_name or row.session_date.strftime("%B %d, %Y"),

            session_date=row.session_date,

            rank=float(row.rank),

        )



        if sid not in groups:

            groups[sid] = SearchResultGroup(

                session_id=row.sid,

                session_name=row.session_name or row.session_date.strftime("%B %d, %Y"),

                session_date=row.session_date,

                results=[],

            )

        groups[sid].results.append(search_result)



    return [g.model_dump(mode="json") for g in groups.values()]
