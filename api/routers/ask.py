"""

Ask router — context-aware chat using observations and briefs.

Supports single-session and cross-session context.

"""

from datetime import date, timedelta



from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from db.postgres import get_db

from models.tables import DailySession, DailyBrief, User

from schemas.session import AskRequest, AskResponse

from core.model_client import get_model_client

from core.auth import DEMO_USER_EMAIL



router = APIRouter(tags=["ask"])



ASK_SYSTEM_PROMPT = """You are Coviction, a sharp research assistant for early-stage VC investors.



You have access to the investor's observations (raw scribbles/notes) and optionally daily briefs (structured summaries). Use these as context to answer the user's question.



Rules:

- Answer directly. No filler, no "great question."

- If you reference a specific observation, mention it by title or number.

- If you reference a past session, mention the date.

- If you don't know something from the context, say so honestly.

- Write like a fellow investor, not a chatbot.

- Keep answers concise — 2-5 sentences for simple questions, more for complex ones."""



ASK_CROSS_SESSION_PROMPT = """You are Coviction, a sharp research assistant with access to MULTIPLE sessions of VC observations across different days.



You can see observations and briefs from several demo days. Use all available context to give the most informed answer possible.



Rules:

- Answer directly. No filler, no "great question."

- When referencing observations, mention the session date and observation title.

- Draw connections across sessions when relevant.

- If you spot patterns (repeated themes, evolving opinions), surface them.

- Write like a fellow investor, not a chatbot.

- Keep answers concise but substantive."""





def _build_context(session: DailySession, brief: DailyBrief | None) -> str:

    """Build context string from observations and optional brief."""

    parts = []



    if session.observations:

        obs_lines = []

        for i, obs in enumerate(session.observations, 1):

            line = f"{i}. [{obs.title}]"

            if obs.body:

                line += f" — {obs.body}"

            obs_lines.append(line)

        parts.append("TODAY'S OBSERVATIONS:\n" + "\n".join(obs_lines))



    if brief:

        brief_text = f"DAILY BRIEF:\nSummary: {brief.summary}\n"

        if brief.tags:

            brief_text += f"Tags: {', '.join(brief.tags)}\n"

        if brief.signals:

            brief_text += "Signals:\n" + "\n".join(f"- {s}" for s in brief.signals) + "\n"

        if brief.actions:

            brief_text += "Follow-ups:\n" + "\n".join(f"- {a}" for a in brief.actions)

        parts.append(brief_text)



    return "\n\n---\n\n".join(parts) if parts else "No observations yet for today."





def _build_cross_session_context(sessions: list[DailySession]) -> str:

    """Build context from multiple sessions, separated by session headers."""

    parts = []

    for session in sessions:

        date_str = session.session_date.strftime("%B %d, %Y")

        session_name = session.name or date_str

        header = f"=== SESSION: {session_name} ({date_str}) ==="



        obs_lines = []

        for i, obs in enumerate(session.observations or [], 1):

            line = f"  {i}. [{obs.title}]"

            if obs.body:

                line += f" — {obs.body[:300]}"

            obs_lines.append(line)



        brief_text = ""

        if session.briefs:

            brief = session.briefs[-1]

            brief_text = f"\n  Brief: {brief.summary}"

            if brief.signals:

                brief_text += "\n  Signals: " + "; ".join(brief.signals[:5])



        section = header

        if obs_lines:

            section += "\n" + "\n".join(obs_lines)

        if brief_text:

            section += brief_text

        parts.append(section)



    return "\n\n".join(parts) if parts else "No observations found across sessions."





@router.post("/ask")

async def ask_coviction(

    body: AskRequest,

    db: AsyncSession = Depends(get_db),

):

    """Context-aware chat. Single-session by default, cross-session when toggled."""



    if body.cross_session:

        # Cross-session: pull from last 30 days of sessions

        user_result = await db.execute(

            select(User).where(User.email == DEMO_USER_EMAIL)

        )

        user = user_result.scalar_one_or_none()

        if not user:

            raise HTTPException(status_code=404, detail="User not found")



        cutoff = date.today() - timedelta(days=30)

        result = await db.execute(

            select(DailySession)

            .options(selectinload(DailySession.observations), selectinload(DailySession.briefs))

            .where(DailySession.user_id == user.id, DailySession.session_date >= cutoff)

            .order_by(DailySession.session_date.desc())

            .limit(15)  # Cap at 15 sessions to avoid token overflow

        )

        sessions = result.scalars().all()

        if not sessions:

            raise HTTPException(status_code=404, detail="No sessions found")



        context = _build_cross_session_context(sessions)

        sources_used = sum(len(s.observations or []) for s in sessions)

        system_prompt = ASK_CROSS_SESSION_PROMPT

    else:

        # Single-session mode (original behavior)

        result = await db.execute(

            select(DailySession)

            .options(selectinload(DailySession.observations), selectinload(DailySession.briefs))

            .where(DailySession.id == body.session_id)

        )

        session = result.scalar_one_or_none()

        if not session:

            raise HTTPException(status_code=404, detail="Session not found")



        brief = None

        if body.include_brief and session.briefs:

            brief = session.briefs[-1]



        context = _build_context(session, brief)

        sources_used = len(session.observations or []) + (1 if brief else 0)

        system_prompt = ASK_SYSTEM_PROMPT



    messages = [

        {"role": "system", "content": system_prompt},

        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION:\n{body.question}"},

    ]



    mc = get_model_client()

    answer = await mc.chat(messages=messages, temperature=0.3)



    return AskResponse(answer=answer, sources_used=sources_used).model_dump()
