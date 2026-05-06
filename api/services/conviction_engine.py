"""

Conviction scoring engine — signal-based belief updates with passive decay.

When new observations mention an entity, the conviction score moves

based on sentiment, frequency, and recency.

Without new signals, scores passively decay toward 0.5 (uncertainty).

"""

import math

import logging

from uuid import UUID

from datetime import datetime, timezone



from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from models.tables import (

    Entity, EntityMention, Conviction, ConvictionLog, Observation, utcnow

)



logger = logging.getLogger(__name__)



# ── Score Update Parameters ──────────────────────────────



# How much a single signal can move the score (max per update)

BASE_SIGNAL_STRENGTH = 0.08



# Sentiment multipliers

SENTIMENT_WEIGHT = {

    "positive": 1.0,    # Full upward push

    "neutral": 0.3,     # Slight upward (attention = mild interest)

    "negative": -0.7,   # Strong downward push

}



# Decay: signals lose weight over time (days since last signal)

RECENCY_HALF_LIFE_DAYS = 14.0



# Passive decay: score drifts toward 0.5 when silent

# After PASSIVE_DECAY_HALF_LIFE days of silence, half the distance to 0.5 decays

PASSIVE_DECAY_HALF_LIFE_DAYS = 30.0





def apply_passive_decay(score: float, days_silent: float) -> float:

    """

    Decay score toward 0.5 based on how long since the last signal.

    Uses exponential decay: after PASSIVE_DECAY_HALF_LIFE_DAYS, half the

    distance from 0.5 is lost.



    Returns the decayed score (clamped to [0.05, 0.95]).

    """

    if days_silent <= 0:

        return score

    # decay_factor goes from 1.0 (no decay) to 0.0 (full decay to 0.5)

    decay_factor = math.exp(-0.693 * days_silent / PASSIVE_DECAY_HALF_LIFE_DAYS)

    # Score drifts toward 0.5

    decayed = 0.5 + (score - 0.5) * decay_factor

    return max(0.05, min(0.95, decayed))





def _compute_score_delta(

    current_score: float,

    sentiment: str,

    signal_count: int,

    days_since_last: float,

) -> float:

    """

    Signal-based score update.



    Key properties:

    - Positive signals push score toward 1.0, negative toward 0.0

    - Diminishing returns: more signals = smaller individual impact

    - Recency matters: long gaps between signals dampen the update

    """

    # Base strength attenuated by signal count (diminishing returns)

    # First signal is full strength, 10th signal is ~30% strength

    diminishing = BASE_SIGNAL_STRENGTH / (1 + math.log1p(signal_count) * 0.5)



    # Sentiment direction

    direction = SENTIMENT_WEIGHT.get(sentiment, 0.3)



    # Recency decay — if it's been a while, the update is dampened

    recency_factor = math.exp(-0.693 * days_since_last / RECENCY_HALF_LIFE_DAYS)

    recency_factor = max(recency_factor, 0.2)  # floor at 20%



    # The delta pushes toward 1.0 (positive) or 0.0 (negative)

    raw_delta = diminishing * direction * recency_factor



    # Apply ceiling/floor to keep score in [0.05, 0.95]

    new_score = current_score + raw_delta

    new_score = max(0.05, min(0.95, new_score))



    return new_score - current_score





async def update_conviction_for_entity(

    entity: Entity,

    observation: Observation,

    sentiment: str,

    user_id: UUID,

    db: AsyncSession,

) -> Conviction | None:

    """

    Update (or create) the conviction for an entity based on a new observation mention.

    Returns the updated conviction, or None if no update was needed.

    """

    # Find existing conviction for this entity

    result = await db.execute(

        select(Conviction).where(

            Conviction.user_id == user_id,

            Conviction.entity_id == entity.id,

        )

    )

    conviction = result.scalar_one_or_none()

    now = utcnow()



    if not conviction:

        # Auto-generate thesis text for new convictions

        thesis = await _generate_thesis(entity)

        conviction = Conviction(

            user_id=user_id,

            entity_id=entity.id,

            thesis_text=thesis,

            score=0.5,  # Start neutral

            signal_count=0,

            last_signal_date=now,

        )

        db.add(conviction)

        await db.flush()



    # Calculate time since last signal

    days_since = 0.0

    if conviction.last_signal_date:

        delta_time = now - conviction.last_signal_date

        days_since = delta_time.total_seconds() / 86400.0



    # Apply passive decay first (score drifts toward 0.5 during silence)

    conviction.score = apply_passive_decay(conviction.score, days_since)



    old_score = conviction.score

    delta = _compute_score_delta(old_score, sentiment, conviction.signal_count, days_since)



    if abs(delta) < 0.001:

        return conviction  # No meaningful change



    # Update conviction

    conviction.score = old_score + delta

    conviction.signal_count += 1

    conviction.last_signal_date = now



    # Create audit log

    reasoning = _build_reasoning(entity, observation, sentiment, old_score, conviction.score)

    log_entry = ConvictionLog(

        conviction_id=conviction.id,

        old_score=round(old_score, 4),

        new_score=round(conviction.score, 4),

        trigger_observation_id=observation.id,

        reasoning=reasoning,

    )

    db.add(log_entry)



    return conviction





async def _generate_thesis(entity: Entity) -> str:

    """Generate a thesis statement for a new entity conviction."""

    type_templates = {

        "company": f"{entity.name} is a compelling investment opportunity",

        "person": f"{entity.name} is a high-signal founder/operator to track",

        "metric": f"The metric pattern around {entity.name} signals market direction",

        "concept": f"{entity.name} is an emerging theme worth conviction-building",

    }

    return type_templates.get(entity.entity_type, f"Tracking conviction on {entity.name}")





def _build_reasoning(

    entity: Entity,

    observation: Observation,

    sentiment: str,

    old_score: float,

    new_score: float,

) -> str:

    """Build a human-readable explanation for the score change."""

    direction = "increased" if new_score > old_score else "decreased"

    sentiment_label = {

        "positive": "positive signal",

        "negative": "negative signal",

        "neutral": "neutral mention",

    }.get(sentiment, "mention")



    return (

        f"Score {direction} from {old_score:.2f} to {new_score:.2f} — "

        f"{sentiment_label} in observation \"{observation.title[:60]}\". "

        f"Entity '{entity.name}' now has {entity.mention_count} total mentions."

    )





async def process_conviction_updates(

    entities_with_sentiments: list[tuple[Entity, str]],

    observation: Observation,

    user_id: UUID,

    db: AsyncSession,

) -> list[Conviction]:

    """

    Process conviction updates for all entities extracted from an observation.

    Called after entity extraction completes.

    """

    convictions = []

    for entity, sentiment in entities_with_sentiments:

        # Only create convictions for companies and concepts (not every person/metric)

        if entity.entity_type in ("company", "concept"):

            conviction = await update_conviction_for_entity(

                entity, observation, sentiment, user_id, db

            )

            if conviction:

                convictions.append(conviction)



    return convictions
