"""

Daily Brief router — "Run Coviction" endpoint.

Fetches observations, sends to LLM, returns structured brief.

"""

from uuid import UUID

from pydantic import BaseModel, Field



from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from db.postgres import get_db

from models.tables import DailySession, Observation, DailyBrief

from schemas.session import DailyBriefOut

from core.model_client import get_model_client



router = APIRouter(prefix="/sessions", tags=["brief"])





# ── Structured output model for LLM ──────────────────────



class BriefExtraction(BaseModel):

    """Structured daily brief output from the LLM."""

    summary: str = Field(..., description="2-3 sentence summary of the day's observations")

    tags: list[str] = Field(..., description="3-6 high-level themes/sectors mentioned")

    signals: list[str] = Field(..., description="3-7 notable signals or standout points")

    actions: list[str] = Field(..., description="3-7 concrete follow-up actions")





BRIEF_SYSTEM_PROMPT = """You are Coviction, a cognitive agent for early-stage VC investors.



You receive a day's worth of raw observations — scribbles, quick notes, and titles from a VC at a demo day or throughout their day. Your job is to synthesize these into a structured daily brief.



Rules:

- Be concise and direct. Write like a sharp analyst, not a chatbot.

- Summary: 2-3 sentences capturing the day's key thread. What was the through-line?

- Tags: Extract 3-6 high-level themes (sectors, markets, technologies, people).

- Signals: 3-7 bullets of standout observations worth revisiting. Be specific.

- Actions: 3-7 concrete follow-ups the VC should take this week. Name names when possible.



Do NOT add filler, pleasantries, or generic advice. Every bullet should be actionable or insightful."""





def _build_observation_text(observations: list[Observation]) -> str:

    """Format observations into a numbered text block for the LLM."""

    lines = []

    for i, obs in enumerate(observations, 1):

        parts = [f"{i}. [{obs.title}]"]

        if obs.body:

            parts.append(obs.body)

        tags = obs.sector_tags if isinstance(obs.sector_tags, list) else (

            [obs.sector_tags] if obs.sector_tags else []

        )

        if tags:

            parts.append(f"(Sectors: {', '.join(tags)})")

        attachments = []

        if obs.has_image:

            attachments.append("image attached")

        if obs.has_voice:

            attachments.append("voice note attached")

        if attachments:

            parts.append(f"[{', '.join(attachments)}]")

        lines.append(" — ".join(parts))

    return "\n".join(lines)





@router.post("/{session_id}/daily-brief")

async def generate_daily_brief(

    session_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Generate a daily brief from the session's observations via LLM."""

    result = await db.execute(

        select(DailySession)

        .options(selectinload(DailySession.observations))

        .where(DailySession.id == session_id)

    )

    session = result.scalar_one_or_none()

    if not session:

        raise HTTPException(status_code=404, detail="Session not found")



    if not session.observations:

        raise HTTPException(status_code=400, detail="No observations to summarize")



    obs_text = _build_observation_text(session.observations)

    prompt = f"Here are today's observations from the VC:\n\n{obs_text}\n\nGenerate a structured daily brief."



    mc = get_model_client()

    extraction = await mc.extract(

        prompt=prompt,

        response_model=BriefExtraction,

        system=BRIEF_SYSTEM_PROMPT,

        temperature=0.3,

    )



    brief = DailyBrief(

        session_id=session.id,

        summary=extraction.summary,

        tags=extraction.tags,

        signals=extraction.signals,

        actions=extraction.actions,

    )

    db.add(brief)

    await db.commit()

    await db.refresh(brief)



    return DailyBriefOut.model_validate(brief).model_dump(mode="json")





@router.get("/{session_id}/daily-brief")

async def get_daily_brief(

    session_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Get the latest daily brief for a session."""

    result = await db.execute(

        select(DailyBrief)

        .where(DailyBrief.session_id == session_id)

        .order_by(DailyBrief.created_at.desc())

        .limit(1)

    )

    brief = result.scalar_one_or_none()

    if not brief:

        raise HTTPException(status_code=404, detail="No brief generated yet")



    return DailyBriefOut.model_validate(brief).model_dump(mode="json")
