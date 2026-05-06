"""

Coviction database models.

Core tables: users, daily_sessions, observations, daily_briefs.

Second Brain tables: entities, entity_mentions, convictions, conviction_logs.

"""

import uuid

from datetime import date, datetime, timezone

from sqlalchemy import (

    Column, String, Text, Boolean, Date, DateTime, Float, Integer,

    ForeignKey, JSON, Index, func,

)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import relationship



from db.postgres import Base





def utcnow():

    return datetime.now(timezone.utc)





class User(Base):

    __tablename__ = "users"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String, unique=True, nullable=False)



    sessions = relationship("DailySession", back_populates="user")





class DailySession(Base):

    __tablename__ = "daily_sessions"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    session_date = Column(Date, nullable=False, default=date.today)

    name = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



    user = relationship("User", back_populates="sessions")

    observations = relationship("Observation", back_populates="session", order_by="Observation.created_at")

    briefs = relationship("DailyBrief", back_populates="session", order_by="DailyBrief.created_at")





class Observation(Base):

    __tablename__ = "observations"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    session_id = Column(UUID(as_uuid=True), ForeignKey("daily_sessions.id"), nullable=False)

    title = Column(Text, nullable=False)

    body = Column(Text, default="")

    sector_tags = Column(JSON, default=list)  # JSONB array of strings

    has_image = Column(Boolean, default=False)

    has_voice = Column(Boolean, default=False)

    voice_transcript = Column(Text, default="")

    image_summary = Column(Text, default="")

    created_at = Column(DateTime(timezone=True), default=utcnow)

    updated_at = Column(DateTime(timezone=True), nullable=True)



    session = relationship("DailySession", back_populates="observations")





# Full-text search index (created via raw SQL in init.sql for GIN support)

# Index('idx_obs_fts', ...) — see init.sql





class DailyBrief(Base):

    __tablename__ = "daily_briefs"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    session_id = Column(UUID(as_uuid=True), ForeignKey("daily_sessions.id"), nullable=False)

    summary = Column(Text, default="")

    tags = Column(JSON, default=list)

    signals = Column(JSON, default=list)

    actions = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), default=utcnow)



    session = relationship("DailySession", back_populates="briefs")





# ── Second Brain: Knowledge Layer ─────────────────────────



class Entity(Base):

    """A company, person, metric, or concept extracted from observations."""

    __tablename__ = "entities"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    entity_type = Column(String, nullable=False)  # company | person | metric | concept

    name = Column(String, nullable=False)

    canonical_name = Column(String, nullable=False)  # lowercase, deduplication key

    metadata_ = Column("metadata", JSON, default=dict)  # sector, stage, website, role, etc.

    first_seen = Column(DateTime(timezone=True), default=utcnow)

    last_seen = Column(DateTime(timezone=True), default=utcnow)

    mention_count = Column(Integer, default=0)



    user = relationship("User")

    mentions = relationship("EntityMention", back_populates="entity", cascade="all, delete-orphan")

    convictions = relationship("Conviction", back_populates="entity", cascade="all, delete-orphan")



    __table_args__ = (

        Index("ix_entity_user_canonical", "user_id", "canonical_name", unique=True),

        Index("ix_entity_user_type", "user_id", "entity_type"),

    )





class EntityMention(Base):

    """Links an entity to the specific observation where it was mentioned."""

    __tablename__ = "entity_mentions"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)

    observation_id = Column(UUID(as_uuid=True), ForeignKey("observations.id", ondelete="CASCADE"), nullable=False)

    context_snippet = Column(Text, default="")  # the sentence/phrase where entity was mentioned

    sentiment = Column(String, default="neutral")  # positive | negative | neutral

    created_at = Column(DateTime(timezone=True), default=utcnow)



    entity = relationship("Entity", back_populates="mentions")

    observation = relationship("Observation")



    __table_args__ = (

        Index("ix_mention_entity", "entity_id"),

        Index("ix_mention_observation", "observation_id"),

    )





class Conviction(Base):

    """Evolving belief score about an entity or thesis — Bayesian-updated."""

    __tablename__ = "convictions"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)

    thesis_text = Column(Text, nullable=False)  # "AI infrastructure is underpriced"

    score = Column(Float, default=0.5)  # 0.0 to 1.0, starts neutral

    signal_count = Column(Integer, default=0)

    last_signal_date = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



    user = relationship("User")

    entity = relationship("Entity", back_populates="convictions")

    logs = relationship("ConvictionLog", back_populates="conviction", cascade="all, delete-orphan",

                        order_by="ConvictionLog.created_at")



    __table_args__ = (

        Index("ix_conviction_user", "user_id"),

        Index("ix_conviction_entity", "entity_id"),

    )





class ConvictionLog(Base):

    """Audit trail of conviction score changes — why did the score move?"""

    __tablename__ = "conviction_logs"



    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conviction_id = Column(UUID(as_uuid=True), ForeignKey("convictions.id", ondelete="CASCADE"), nullable=False)

    old_score = Column(Float, nullable=False)

    new_score = Column(Float, nullable=False)

    trigger_observation_id = Column(UUID(as_uuid=True), ForeignKey("observations.id", ondelete="SET NULL"), nullable=True)

    reasoning = Column(Text, default="")  # AI-generated explanation of score change

    created_at = Column(DateTime(timezone=True), default=utcnow)



    conviction = relationship("Conviction", back_populates="logs")

    trigger_observation = relationship("Observation")
