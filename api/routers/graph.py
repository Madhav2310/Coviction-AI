"""

Knowledge Graph router — returns nodes and edges for the memory map visualization.

Nodes: entities (companies, people, concepts).

Edges: co-occurrence in same observation or shared sector tags.

"""

from datetime import datetime, timezone

from uuid import UUID

from typing import Optional



from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select, func, text

from sqlalchemy.ext.asyncio import AsyncSession



from db.postgres import get_db

from models.tables import (

    Entity, EntityMention, Observation, DailySession, Conviction

)

from services.conviction_engine import apply_passive_decay

from core.auth import get_user_id



router = APIRouter(prefix="/knowledge", tags=["knowledge-graph"])





@router.get("/graph")

async def get_knowledge_graph(

    min_mentions: int = Query(0, ge=0, description="Minimum mentions to include entity"),

    entity_type: Optional[str] = Query(None, description="Filter: company, person, concept, metric"),

    db: AsyncSession = Depends(get_db),

):

    """

    Returns the full knowledge graph: nodes (entities) and edges (co-occurrence).

    Edges connect entities that are mentioned in the same observation.

    Also includes sector tag nodes as lightweight connectors.

    """

    user_id = await get_user_id(db)



    # ── Fetch entities as nodes ──

    entity_query = (

        select(Entity)

        .where(Entity.user_id == user_id)

    )

    if min_mentions > 0:

        entity_query = entity_query.where(Entity.mention_count >= min_mentions)

    if entity_type:

        entity_query = entity_query.where(Entity.entity_type == entity_type)



    result = await db.execute(entity_query)

    entities = result.scalars().all()



    # Fetch conviction scores for all entities

    conv_result = await db.execute(

        select(Conviction).where(Conviction.user_id == user_id)

    )

    convictions = conv_result.scalars().all()

    now = datetime.now(timezone.utc)

    conviction_map: dict[str, float] = {}

    for c in convictions:

        if c.entity_id:

            days_silent = 0.0

            if c.last_signal_date:

                days_silent = (now - c.last_signal_date).total_seconds() / 86400.0

            conviction_map[str(c.entity_id)] = apply_passive_decay(c.score, days_silent)



    nodes = []

    entity_id_set = set()

    for e in entities:

        nodes.append({

            "id": str(e.id),

            "label": e.name,

            "type": e.entity_type,

            "mentions": e.mention_count,

            "conviction_score": round(conviction_map.get(str(e.id), 0), 4),

            "first_seen": e.first_seen.isoformat() if e.first_seen else None,

            "last_seen": e.last_seen.isoformat() if e.last_seen else None,

            "metadata": e.metadata_ or {},

        })

        entity_id_set.add(e.id)



    # ── Build edges: co-occurrence in same observation ──

    # Find all (entity_a, entity_b) pairs that share an observation

    co_occurrence_query = text("""

        SELECT

            a.entity_id AS source,

            b.entity_id AS target,

            COUNT(DISTINCT a.observation_id) AS weight

        FROM entity_mentions a

        JOIN entity_mentions b

            ON a.observation_id = b.observation_id

            AND a.entity_id < b.entity_id

        JOIN entities ea ON a.entity_id = ea.id

        JOIN entities eb ON b.entity_id = eb.id

        WHERE ea.user_id = :user_id

          AND eb.user_id = :user_id

        GROUP BY a.entity_id, b.entity_id

        ORDER BY weight DESC

        LIMIT 500

    """)



    edge_result = await db.execute(co_occurrence_query, {"user_id": str(user_id)})

    edge_rows = edge_result.fetchall()



    edges = []

    for row in edge_rows:

        source_id = str(row[0])

        target_id = str(row[1])

        # Only include edges where both nodes are in our filtered set

        if source_id in {str(eid) for eid in entity_id_set} and target_id in {str(eid) for eid in entity_id_set}:

            edges.append({

                "source": source_id,

                "target": target_id,

                "weight": row[2],

            })



    # ── Sector tag nodes (virtual — connect entities sharing sectors) ──

    # Pull sector tags from observations that have entities

    sector_query = text("""

        SELECT DISTINCT

            jsonb_array_elements_text(o.sector_tags::jsonb) AS tag,

            em.entity_id

        FROM observations o

        JOIN entity_mentions em ON o.id = em.observation_id

        JOIN entities e ON em.entity_id = e.id

        WHERE e.user_id = :user_id

          AND o.sector_tags IS NOT NULL

          AND o.sector_tags::text != '[]'

    """)



    try:

        sector_result = await db.execute(sector_query, {"user_id": str(user_id)})

        sector_rows = sector_result.fetchall()



        # Group entities by sector tag

        sector_entities: dict[str, list[str]] = {}

        for row in sector_rows:

            tag = row[0]

            eid = str(row[1])

            if eid in {str(x) for x in entity_id_set}:

                sector_entities.setdefault(tag, []).append(eid)



        # Create sector nodes and edges

        for tag, entity_ids in sector_entities.items():

            if len(entity_ids) >= 1:

                sector_node_id = f"sector:{tag}"

                nodes.append({

                    "id": sector_node_id,

                    "label": tag,

                    "type": "sector",

                    "mentions": len(entity_ids),

                    "first_seen": None,

                    "last_seen": None,

                    "metadata": {},

                })

                for eid in entity_ids:

                    edges.append({

                        "source": sector_node_id,

                        "target": eid,

                        "weight": 1,

                    })

    except Exception:

        pass  # Sector enrichment is best-effort



    return {

        "nodes": nodes,

        "edges": edges,

        "meta": {

            "total_nodes": len(nodes),

            "total_edges": len(edges),

            "entity_types": list(set(n["type"] for n in nodes)),

        },

    }





@router.get("/graph/timeline")

async def get_graph_timeline(

    db: AsyncSession = Depends(get_db),

):

    """

    Returns session activity by date for the calendar heatmap.

    Each entry: date, observation count, has_brief, session name.

    """

    user_id = await get_user_id(db)



    result = await db.execute(

        select(

            DailySession.id,

            DailySession.session_date,

            DailySession.name,

            func.count(Observation.id).label("obs_count"),

        )

        .outerjoin(Observation, DailySession.id == Observation.session_id)

        .where(DailySession.user_id == user_id)

        .group_by(DailySession.id, DailySession.session_date, DailySession.name)

        .order_by(DailySession.session_date.desc())

    )

    rows = result.all()



    timeline = []

    for row in rows:

        timeline.append({

            "session_id": str(row[0]),

            "date": row[1].isoformat(),

            "name": row[2] or row[1].strftime("%B %d, %Y"),

            "observation_count": row[3],

        })



    return {"timeline": timeline}





@router.post("/graph/deal-memo/{entity_id}")

async def generate_deal_memo(

    entity_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """

    Generate a 1-page deal memo for a company entity using all available signals:

    mentions, conviction score, connected entities, and observation context.

    """

    from core.model_client import get_model_client



    user_id = await get_user_id(db)



    # Fetch entity

    ent_result = await db.execute(

        select(Entity).where(Entity.id == entity_id, Entity.user_id == user_id)

    )

    entity = ent_result.scalar_one_or_none()

    if not entity:

        raise HTTPException(status_code=404, detail="Entity not found")



    # Get all mentions with context

    mentions_result = await db.execute(

        select(EntityMention)

        .where(EntityMention.entity_id == entity_id)

        .order_by(EntityMention.created_at.desc())

        .limit(15)

    )

    mentions = mentions_result.scalars().all()



    # Get conviction

    conv_result = await db.execute(

        select(Conviction).where(

            Conviction.user_id == user_id,

            Conviction.entity_id == entity_id,

        ).limit(1)

    )

    conviction = conv_result.scalars().first()

    conviction_score = None

    if conviction:

        now = datetime.now(timezone.utc)

        days_silent = 0.0

        if conviction.last_signal_date:

            days_silent = (now - conviction.last_signal_date).total_seconds() / 86400.0

        conviction_score = apply_passive_decay(conviction.score, days_silent)



    # Get connected entities (co-occurring)

    connected_result = await db.execute(text("""

        SELECT DISTINCT e.name, e.entity_type

        FROM entity_mentions a

        JOIN entity_mentions b ON a.observation_id = b.observation_id AND a.entity_id != b.entity_id

        JOIN entities e ON b.entity_id = e.id

        WHERE a.entity_id = :entity_id

        LIMIT 10

    """), {"entity_id": str(entity_id)})

    connected = connected_result.fetchall()



    # Build context for LLM

    mention_texts = [m.context_snippet for m in mentions if m.context_snippet]

    sentiments = [m.sentiment for m in mentions]

    pos_count = sentiments.count("positive")

    neg_count = sentiments.count("negative")

    neu_count = sentiments.count("neutral")



    context = f"""Entity: {entity.name}

Type: {entity.entity_type}

Sector: {(entity.metadata_ or {}).get('sector', 'unknown')}

Total mentions: {entity.mention_count}

First seen: {entity.first_seen.strftime('%B %d, %Y') if entity.first_seen else 'unknown'}

Last seen: {entity.last_seen.strftime('%B %d, %Y') if entity.last_seen else 'unknown'}

Conviction score: {f'{conviction_score:.0%}' if conviction_score else 'no conviction yet'}

Thesis: {conviction.thesis_text if conviction else 'none'}

Sentiment breakdown: {pos_count} positive, {neg_count} negative, {neu_count} neutral



Connected entities: {', '.join(f'{r[0]} ({r[1]})' for r in connected)}



Observation snippets:

{chr(10).join(f'- {t}' for t in mention_texts[:10])}"""



    mc = get_model_client()

    try:

        memo = await mc.chat(

            messages=[

                {"role": "system", "content": """You are a VC analyst writing a concise deal memo. Structure your output as:



## [Company Name] — Deal Memo



**Sector:** [sector]

**Conviction:** [score as %] | **Signals:** [count]



### Summary

2-3 sentences on what this company does and why it's on the radar.



### Bull Case

3 bullet points — why invest.



### Bear Case

2-3 bullet points — risks and concerns.



### Key Connections

Who/what else in the portfolio or pipeline is related.



### Recommended Next Step

One concrete action (take a meeting, pass, dig deeper on X).



Be direct and sharp. No filler. Write like a partner memo, not a blog post."""},

                {"role": "user", "content": f"Generate a deal memo from this data:\n\n{context}"},

            ],

            model=mc.settings.default_fast_model,

            temperature=0.3,

        )

        return {"entity_id": str(entity_id), "entity_name": entity.name, "memo": memo.strip()}

    except Exception as e:

        return {"entity_id": str(entity_id), "entity_name": entity.name, "memo": f"Failed to generate memo: {str(e)}"}
