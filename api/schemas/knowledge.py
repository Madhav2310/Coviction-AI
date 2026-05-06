"""

Pydantic schemas for Second Brain: entities, mentions, convictions.

"""

from pydantic import BaseModel, Field

from typing import Optional

from datetime import datetime, date

from uuid import UUID





# ── Entity ───────────────────────────────────────────────



class EntityOut(BaseModel):

    id: UUID

    entity_type: str

    name: str

    metadata_: dict = Field(default_factory=dict, alias="metadata_")

    first_seen: datetime

    last_seen: datetime

    mention_count: int



    model_config = {"from_attributes": True, "populate_by_name": True}





class EntityDetail(EntityOut):

    """Entity with recent mentions and conviction info."""

    mentions: list["MentionOut"] = []

    conviction: Optional["ConvictionOut"] = None





class EntityListItem(BaseModel):

    id: UUID

    entity_type: str

    name: str

    mention_count: int

    last_seen: datetime

    sentiment_summary: Optional[str] = None  # computed: overall sentiment



    model_config = {"from_attributes": True}





# ── EntityMention ────────────────────────────────────────



class MentionOut(BaseModel):

    id: UUID

    entity_id: UUID

    observation_id: UUID

    context_snippet: str

    sentiment: str

    created_at: datetime

    # Denormalized for display

    observation_title: Optional[str] = None

    session_date: Optional[date] = None



    model_config = {"from_attributes": True}





# ── Conviction ───────────────────────────────────────────



class ConvictionOut(BaseModel):

    id: UUID

    entity_id: Optional[UUID] = None

    thesis_text: str

    score: float

    signal_count: int

    last_signal_date: Optional[datetime] = None

    created_at: datetime

    updated_at: Optional[datetime] = None



    model_config = {"from_attributes": True}





class ConvictionDetail(ConvictionOut):

    """Conviction with full log history."""

    entity_name: Optional[str] = None

    logs: list["ConvictionLogOut"] = []





class ConvictionLogOut(BaseModel):

    id: UUID

    old_score: float

    new_score: float

    trigger_observation_id: Optional[UUID] = None

    reasoning: str

    created_at: datetime



    model_config = {"from_attributes": True}





# ── Extraction Models (LLM structured output) ───────────



class ExtractedEntity(BaseModel):

    """Single entity extracted by the LLM from an observation."""

    name: str = Field(..., description="Entity name (company, person, metric, or concept)")

    entity_type: str = Field(..., description="One of: company, person, metric, concept")

    context: str = Field(..., description="The phrase or sentence where this entity appears")

    sentiment: str = Field("neutral", description="One of: positive, negative, neutral")

    metadata: dict = Field(default_factory=dict, description="Extra info: sector, stage, role, value, etc.")





class ObservationExtraction(BaseModel):

    """Full extraction result from a single observation."""

    entities: list[ExtractedEntity] = Field(default_factory=list, description="All entities found in this observation")

    thesis_signals: list[str] = Field(default_factory=list, description="Investment thesis signals detected (1-3 max)")





# ── Pattern Detection Models ─────────────────────────────



class PatternOut(BaseModel):

    """A detected cross-session pattern."""

    pattern_type: str  # trending_entity | conviction_drift | sector_gap | recurring_theme

    title: str

    description: str

    entity_ids: list[UUID] = []

    evidence_count: int = 0

    timespan_days: int = 0





class MorningBriefOut(BaseModel):

    """Daily synthesis from the heartbeat."""

    date: date

    trending_entities: list[EntityListItem] = []

    conviction_shifts: list[ConvictionOut] = []

    patterns: list[PatternOut] = []

    summary: str = ""





# ── Knowledge Panel Aggregate ────────────────────────────



class KnowledgePanelData(BaseModel):

    """All data for the frontend knowledge panel in one shot."""

    entities: list[EntityListItem] = []

    top_convictions: list[ConvictionDetail] = []

    recent_patterns: list[PatternOut] = []

    entity_count: int = 0

    conviction_count: int = 0
