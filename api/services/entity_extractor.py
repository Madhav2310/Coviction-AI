"""

Entity extraction service — LLM-powered extraction from observations.

Uses instructor structured output via ModelClient.extract().

Handles deduplication, mention tracking, and conviction signal detection.

"""

import logging

from uuid import UUID

from datetime import datetime, timezone



from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from core.model_client import get_model_client

from models.tables import Entity, EntityMention, Observation, utcnow

from schemas.knowledge import ObservationExtraction, ExtractedEntity



logger = logging.getLogger(__name__)



EXTRACTION_SYSTEM_PROMPT = """You are an entity extraction engine for a VC's observation notes from demo days and meetings.



Extract ALL meaningful entities from the observation text:

- **company**: Any startup, company, or product mentioned (e.g., "FlexPay", "Stripe", "Anthropic")

- **person**: Named individuals with proper names (e.g., "Sarah Chen", "John Smith"). Do NOT extract generic words like "Met" or partial verbs.

- **metric**: Specific numbers or KPIs (e.g., "$2M ARR", "40% MoM growth", "Series A")

- **concept**: Investment themes or technologies (e.g., "usage-based pricing", "multi-agent AI", "embedded finance"). Do NOT extract personal to-do items (like "Update resume", "add project").



For each entity:

- Extract the exact name as mentioned

- Classify the type

- Pull the surrounding context (the phrase/sentence where it appears)

- Assess sentiment: positive (excitement, opportunity), negative (concern, risk), or neutral

- Add metadata — IMPORTANT rules:

  - For **company** entities: you MUST include a "sector" key in metadata. Use exactly one of: fintech, ai, saas, health, crypto, climate, infra, devtools, enterprise, consumer, other

  - For **person** entities: include "role" if mentioned (e.g., "CEO", "founder", "GP")

  - For **concept** entities: include "sector" if it clearly belongs to one (same values as above)

  - For **metric** entities: include "value" with the numeric value



Also detect thesis signals — investment theses the VC seems to be forming or validating:

- "AI infrastructure is underpriced" (if they mention multiple AI infra companies positively)

- "Fintech is overcrowded" (if they express skepticism about another fintech)

- Keep to 1-3 signals max. Only extract if there's real evidence in the text.



Be precise. Do not hallucinate entities that aren't in the text. Only extract entities that are genuinely named in the observation."""





async def extract_entities_from_observation(

    observation: Observation,

    user_id: UUID,

    db: AsyncSession,

) -> list[Entity]:

    """

    Extract entities from a single observation via LLM.

    Deduplicates against existing entities for this user.

    Creates EntityMentions linking entities to this observation.

    Returns the list of entities (new + existing) that were mentioned.

    """

    text = _build_extraction_text(observation)

    if not text.strip():

        return []



    mc = get_model_client()



    try:

        extraction: ObservationExtraction = await mc.extract(

            prompt=f"Extract entities from this VC observation:\n\n{text}",

            response_model=ObservationExtraction,

            model=mc.settings.default_fast_model,

            system=EXTRACTION_SYSTEM_PROMPT,

            temperature=0.0,

        )

    except Exception as e:

        logger.error(f"Entity extraction failed for obs {observation.id}: {e}")

        return []



    if not extraction.entities:

        return []



    entities = []

    for ext_entity in extraction.entities:

        entity = await _upsert_entity(ext_entity, user_id, observation, db)

        if entity:

            entities.append(entity)



    return entities





def _build_extraction_text(obs: Observation) -> str:

    """Build the text to send to the LLM for extraction."""

    parts = []

    if obs.title:

        parts.append(f"Title: {obs.title}")

    if obs.body:

        parts.append(f"Notes: {obs.body}")

    if obs.voice_transcript:

        parts.append(f"Voice transcript: {obs.voice_transcript}")

    if obs.image_summary:

        parts.append(f"Image description: {obs.image_summary}")

    tags = obs.sector_tags if isinstance(obs.sector_tags, list) else []

    if tags:

        parts.append(f"Sector tags: {', '.join(tags)}")

    return "\n".join(parts)





async def _upsert_entity(

    ext: ExtractedEntity,

    user_id: UUID,

    observation: Observation,

    db: AsyncSession,

) -> Entity | None:

    """

    Find or create an entity, then create a mention linking it to the observation.

    Uses canonical_name (lowercased) for deduplication.

    """

    canonical = ext.name.strip().lower()

    if not canonical:

        return None



    # Validate entity_type

    valid_types = {"company", "person", "metric", "concept"}

    entity_type = ext.entity_type.lower().strip()

    if entity_type not in valid_types:

        entity_type = "concept"



    # Validate sentiment

    valid_sentiments = {"positive", "negative", "neutral"}

    sentiment = ext.sentiment.lower().strip()

    if sentiment not in valid_sentiments:

        sentiment = "neutral"



    # Look for existing entity

    result = await db.execute(

        select(Entity).where(

            Entity.user_id == user_id,

            Entity.canonical_name == canonical,

        )

    )

    entity = result.scalar_one_or_none()

    now = utcnow()



    if entity:

        # Update existing: bump mention count and last_seen

        entity.mention_count += 1

        entity.last_seen = now

        # Merge metadata (don't overwrite, only add new keys)

        if ext.metadata:

            existing_meta = entity.metadata_ or {}

            for k, v in ext.metadata.items():

                if k not in existing_meta:

                    existing_meta[k] = v

            entity.metadata_ = existing_meta

    else:

        # Create new entity

        entity = Entity(

            user_id=user_id,

            entity_type=entity_type,

            name=ext.name.strip(),

            canonical_name=canonical,

            metadata_=ext.metadata or {},

            first_seen=now,

            last_seen=now,

            mention_count=1,

        )

        db.add(entity)

        await db.flush()  # Get the ID



    # Create mention

    mention = EntityMention(

        entity_id=entity.id,

        observation_id=observation.id,

        context_snippet=ext.context[:500] if ext.context else "",

        sentiment=sentiment,

    )

    db.add(mention)



    return entity





async def extract_and_commit(

    observation_id: UUID,

    user_id: UUID,

    db: AsyncSession,

) -> list[Entity]:

    """

    Full extraction pipeline: fetch observation, extract, commit.

    Used by the background task hook.

    """

    result = await db.execute(

        select(Observation).where(Observation.id == observation_id)

    )

    obs = result.scalar_one_or_none()

    if not obs:

        logger.warning(f"Observation {observation_id} not found for extraction")

        return []



    entities = await extract_entities_from_observation(obs, user_id, db)

    await db.commit()



    names = [e.name for e in entities]

    logger.info(f"Extracted {len(entities)} entities from obs {observation_id}: {names}")

    return entities
