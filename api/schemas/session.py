"""

Pydantic schemas for sessions, observations, and briefs.

"""

from pydantic import BaseModel, Field, field_validator

from typing import Optional

from datetime import date, datetime

from uuid import UUID





# ── Observation ───────────────────────────────────────────



class ObservationCreate(BaseModel):

    title: str = ""

    body: str = ""

    sector_tags: list[str] = []

    has_image: bool = False

    has_voice: bool = False





class ObservationUpdate(BaseModel):

    title: Optional[str] = None

    body: Optional[str] = None

    sector_tags: Optional[list[str]] = None





class ObservationOut(BaseModel):

    id: UUID

    session_id: UUID

    title: str

    body: str

    sector_tags: list[str] = []

    has_image: bool

    has_voice: bool

    voice_transcript: str = ""

    image_summary: str = ""

    created_at: datetime

    updated_at: Optional[datetime] = None



    model_config = {"from_attributes": True}



    @field_validator("sector_tags", mode="before")

    @classmethod

    def coerce_sector_tags(cls, v):

        """Backward compat: old string values become single-element arrays."""

        if v is None:

            return []

        if isinstance(v, str):

            return [v] if v else []

        return v





class QuickCapture(BaseModel):

    text: str = Field(..., min_length=1)





# ── Daily Brief ───────────────────────────────────────────



class DailyBriefOut(BaseModel):

    id: UUID

    session_id: UUID

    summary: str

    tags: list[str]

    signals: list[str]

    actions: list[str]

    created_at: datetime



    model_config = {"from_attributes": True}





# ── Session ───────────────────────────────────────────────



class SessionRename(BaseModel):

    name: str = Field(..., min_length=1)





class SessionListItem(BaseModel):

    id: UUID

    session_date: date

    name: Optional[str]

    observation_count: int

    has_brief: bool

    preview: str  # First observation title or ""

    created_at: datetime





class SessionOut(BaseModel):

    id: UUID

    user_id: UUID

    session_date: date

    name: Optional[str]

    created_at: datetime

    updated_at: Optional[datetime]

    observations: list[ObservationOut] = []

    brief: Optional[DailyBriefOut] = None



    model_config = {"from_attributes": True}





# ── Ask ───────────────────────────────────────────────────



class AskRequest(BaseModel):

    question: str = Field(..., min_length=1)

    session_id: UUID

    include_brief: bool = True

    cross_session: bool = False





class AskResponse(BaseModel):

    answer: str

    sources_used: int = 0





# ── Search ────────────────────────────────────────────────



class SearchResult(BaseModel):

    observation: ObservationOut

    session_id: UUID

    session_name: str

    session_date: date

    rank: float





class SearchResultGroup(BaseModel):

    session_id: UUID

    session_name: str

    session_date: date

    results: list[SearchResult]
