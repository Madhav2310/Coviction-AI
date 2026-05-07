"""
Entity extraction service - LLM-powered extraction from observations.

Uses instructor structured output via ModelClient.extract().
Handles deduplication, mention tracking, and reprocessing utilities.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.model_client import get_model_client
from models.tables import Entity, EntityMention, Observation, utcnow
from schemas.knowledge import ExtractedEntity, ObservationExtraction


logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = """You are an entity extraction engine for a VC's observation notes from demo days and meetings.

These notes are written quickly. They often use shorthand, incomplete sentences, first-name-only references, and Indian English honorifics.

Extract ALL meaningful entities from the observation text:

- **company**: Any startup, company, fund, institution, or product mentioned (e.g., "FlexPay", "Stripe", "Anthropic", "Sequoia", "Accel").

- **person**: Any named individual - full name OR partial name OR informal reference that clearly identifies a person. Examples:
  - Full names: "Sarah Chen", "Raj Patel"
  - First-name only: "Anita", "Raj", "Abhi"
  - Honorific style: "Abhi sir", "Dr Mehta", "Rao sir", "Anita ma'am", "Gupta ji", "Suresh anna", "Rao garu"
  - Role-based references when clearly person-like: "the Sequoia GP", "Accel partner"
  Do NOT extract generic verbs or non-names like "Met", "Talk", "Founder" by themselves.

- **metric**: Specific numbers or KPIs (e.g., "$2M ARR", "40% MoM growth", "Series A").

- **concept**: Investment themes or technologies (e.g., "usage-based pricing", "multi-agent AI", "embedded finance"). Do NOT extract ordinary personal to-do items like "update resume" or "add project".

For each entity:
- Extract the exact name as mentioned.
- Classify the type.
- Pull the surrounding context, ideally the phrase or sentence where it appears.
- Assess sentiment: positive (excitement, opportunity), negative (concern, risk), or neutral.
- Add metadata:
  - For **company** entities: include a "sector" key when possible. Use exactly one of: fintech, ai, saas, health, crypto, climate, infra, devtools, enterprise, consumer, other.
  - For **person** entities: include "role" if mentioned (e.g., "CEO", "founder", "GP", "partner", "sir", "Dr") and "affiliation" if a company/fund is mentioned with them.
  - For **concept** entities: include "sector" if it clearly belongs to one of the sectors above.
  - For **metric** entities: include "value" with the numeric value.

Also detect thesis signals - investment theses the VC seems to be forming or validating:
- "AI infrastructure is underpriced" (if they mention multiple AI infra companies positively)
- "Fintech is overcrowded" (if they express skepticism about another fintech)
- Keep to 1-3 signals max. Only extract if there is real evidence in the text.

Be aggressive on extraction: it is better to extract a borderline named entity than miss a real person, company, metric, or investment concept. Still do not hallucinate entities that are not present in the text."""


@dataclass
class ExtractionMetrics:
    observation_id: str = ""
    model_used: str = ""
    latency_ms: float = 0.0
    entities_extracted: int = 0
    entities_new: int = 0
    entities_existing: int = 0
    uniqueness_guard_hits: int = 0
    types_breakdown: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    def log(self) -> None:
        logger.info(
            "entity_extraction_complete",
            extra={
                "obs_id": self.observation_id,
                "model": self.model_used,
                "latency_ms": round(self.latency_ms, 1),
                "extracted": self.entities_extracted,
                "new": self.entities_new,
                "existing": self.entities_existing,
                "guard_hits": self.uniqueness_guard_hits,
                "types": self.types_breakdown,
                "error": self.error,
            },
        )


def _normalize_canonical(name: str) -> str:
    """Normalize informal person titles/honorifics for deduplication."""
    normalized = name.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)

    suffixes = (
        r"\s+(sir|ma'?am|madam|ji|sahab|uncle|aunty|bhai|didi|"
        r"anna|akka|garu|amma|ayya)$"
    )
    normalized = re.sub(suffixes, "", normalized, flags=re.IGNORECASE)

    prefixes = r"^(dr\.?|mr\.?|mrs\.?|ms\.?|prof\.?|professor|shri\.?)\s+"
    normalized = re.sub(prefixes, "", normalized, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", normalized).strip()


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
    Emits structured ExtractionMetrics on every call.
    """
    metrics = ExtractionMetrics(observation_id=str(observation.id))
    text = _build_extraction_text(observation)
    if not text.strip():
        return []

    mc = get_model_client()
    model = getattr(mc.settings, "entity_extraction_model", mc.settings.default_fast_model)
    metrics.model_used = model

    t0 = time.perf_counter()
    try:
        extraction: ObservationExtraction = await mc.extract(
            prompt=f"Extract entities from this VC observation:\n\n{text}",
            response_model=ObservationExtraction,
            model=model,
            system=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except Exception as e:
        metrics.latency_ms = (time.perf_counter() - t0) * 1000
        metrics.error = str(e)
        metrics.log()
        logger.error("Entity extraction failed for obs %s: %s", observation.id, e)
        return []

    metrics.latency_ms = (time.perf_counter() - t0) * 1000

    if not extraction.entities:
        metrics.log()
        return []

    entities: list[Entity] = []
    for ext_entity in extraction.entities:
        entity, was_new, guard_hit = await _upsert_entity(ext_entity, user_id, observation, db)
        if not entity:
            continue

        entities.append(entity)
        if was_new:
            metrics.entities_new += 1
        else:
            metrics.entities_existing += 1
        if guard_hit:
            metrics.uniqueness_guard_hits += 1

        etype = entity.entity_type
        metrics.types_breakdown[etype] = metrics.types_breakdown.get(etype, 0) + 1

    metrics.entities_extracted = len(entities)
    metrics.log()
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
) -> tuple[Entity | None, bool, bool]:
    """
    Find or create an entity, then create a mention linking it to the observation.

    Returns: (entity, was_new, guard_hit).
    """
    raw_canonical = ext.name.strip().lower()
    if not raw_canonical or len(raw_canonical) < 2:
        return None, False, False

    canonical = _normalize_canonical(raw_canonical)
    if not canonical or len(canonical) < 2:
        return None, False, False

    valid_types = {"company", "person", "metric", "concept"}
    entity_type = ext.entity_type.lower().strip()
    if entity_type not in valid_types:
        entity_type = "concept"

    valid_sentiments = {"positive", "negative", "neutral"}
    sentiment = ext.sentiment.lower().strip()
    if sentiment not in valid_sentiments:
        sentiment = "neutral"

    entity = await _find_entity_by_canonical(user_id, canonical, db)
    if not entity and canonical != raw_canonical:
        entity = await _find_entity_by_canonical(user_id, raw_canonical, db)

    now = utcnow()
    was_new = False

    if entity:
        existing_mention = await db.execute(
            select(EntityMention).where(
                EntityMention.entity_id == entity.id,
                EntityMention.observation_id == observation.id,
            ).limit(1)
        )
        if existing_mention.scalars().first():
            return entity, False, True

        entity.mention_count += 1
        entity.last_seen = now
        if ext.metadata:
            existing_meta = entity.metadata_ or {}
            for key, value in ext.metadata.items():
                if key not in existing_meta:
                    existing_meta[key] = value
            entity.metadata_ = existing_meta
    else:
        was_new = True
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
        await db.flush()

    mention = EntityMention(
        entity_id=entity.id,
        observation_id=observation.id,
        context_snippet=ext.context[:500] if ext.context else "",
        sentiment=sentiment,
    )
    db.add(mention)

    return entity, was_new, False


async def _find_entity_by_canonical(
    user_id: UUID,
    canonical_name: str,
    db: AsyncSession,
) -> Entity | None:
    result = await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.canonical_name == canonical_name,
        )
    )
    return result.scalar_one_or_none()


async def reprocess_observation(
    observation_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> list[Entity]:
    """
    Clear entity mentions for an observation and extract them again.

    This repairs mention counts for affected entities and is safe to run more
    than once. It intentionally does not rewind conviction event history.
    """
    result = await db.execute(select(Observation).where(Observation.id == observation_id))
    observation = result.scalar_one_or_none()
    if not observation:
        logger.warning("Observation %s not found for reprocessing", observation_id)
        return []

    old_mentions_result = await db.execute(
        select(EntityMention.entity_id).where(EntityMention.observation_id == observation_id)
    )
    affected_entity_ids = {row[0] for row in old_mentions_result.all()}

    await db.execute(delete(EntityMention).where(EntityMention.observation_id == observation_id))
    await db.flush()

    if affected_entity_ids:
        await repair_entity_counts_for_ids(affected_entity_ids, db)

    entities = await extract_entities_from_observation(observation, user_id, db)
    affected_entity_ids.update(entity.id for entity in entities)

    if affected_entity_ids:
        await repair_entity_counts_for_ids(affected_entity_ids, db)

    await db.commit()
    logger.info(
        "Reprocessed observation %s: %s entities",
        observation_id,
        [entity.name for entity in entities],
    )
    return entities


async def repair_entity_counts(user_id: UUID, db: AsyncSession) -> int:
    """
    Rebuild all entity mention_count values from actual mentions.

    Uses aggregate queries rather than one count query per entity.
    Returns the number of corrected entities.
    """
    count_subq = (
        select(
            Entity.id.label("entity_id"),
            func.count(EntityMention.id).label("real_count"),
        )
        .outerjoin(EntityMention, Entity.id == EntityMention.entity_id)
        .where(Entity.user_id == user_id)
        .group_by(Entity.id)
        .subquery()
    )

    result = await db.execute(
        select(Entity, count_subq.c.real_count)
        .join(count_subq, Entity.id == count_subq.c.entity_id)
        .where(Entity.mention_count != count_subq.c.real_count)
    )
    mismatches = result.all()

    for entity, real_count in mismatches:
        entity.mention_count = int(real_count or 0)

    await db.commit()
    logger.info(
        "Repaired entity counts for user %s: %s entities corrected",
        user_id,
        len(mismatches),
    )
    return len(mismatches)


async def repair_entity_counts_for_ids(entity_ids: set[UUID], db: AsyncSession) -> None:
    if not entity_ids:
        return

    count_result = await db.execute(
        select(
            Entity.id,
            func.count(EntityMention.id).label("real_count"),
        )
        .outerjoin(EntityMention, Entity.id == EntityMention.entity_id)
        .where(Entity.id.in_(entity_ids))
        .group_by(Entity.id)
    )
    counts = {entity_id: int(real_count or 0) for entity_id, real_count in count_result.all()}

    entity_result = await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))
    for entity in entity_result.scalars().all():
        entity.mention_count = counts.get(entity.id, 0)


async def extract_and_commit(
    observation_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> list[Entity]:
    """
    Full extraction pipeline: fetch observation, extract, commit.

    Used by the background task hook.
    """
    result = await db.execute(select(Observation).where(Observation.id == observation_id))
    obs = result.scalar_one_or_none()
    if not obs:
        logger.warning("Observation %s not found for extraction", observation_id)
        return []

    entities = await extract_entities_from_observation(obs, user_id, db)
    await db.commit()

    names = [e.name for e in entities]
    logger.info("Extracted %s entities from obs %s: %s", len(entities), observation_id, names)
    return entities
