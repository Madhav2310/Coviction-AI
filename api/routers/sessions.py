"""

Sessions + Observations CRUD router.

Full lifecycle: create, read, edit, delete, quick capture.

"""

import base64

from datetime import date, datetime, timezone

from tempfile import SpooledTemporaryFile

from uuid import UUID



from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form

from pydantic import BaseModel, Field

from sqlalchemy import select, func

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from db.postgres import get_db

from models.tables import DailySession, DailyBrief, Observation, User

from schemas.session import (

    SessionOut, SessionListItem, SessionRename,

    ObservationCreate, ObservationUpdate, ObservationOut,

    DailyBriefOut, QuickCapture,

)

from core.model_client import get_model_client

from core.auth import ensure_demo_user



router = APIRouter(prefix="/sessions", tags=["sessions"])





def _format_date(d: date) -> str:

    return d.strftime("%B %d, %Y")  # "April 12, 2026"





def _session_to_out(session: DailySession) -> dict:

    """Convert session ORM to response dict, including nested brief."""

    obs_list = [ObservationOut.model_validate(o) for o in (session.observations or [])]

    brief = None

    if session.briefs:

        brief = DailyBriefOut.model_validate(session.briefs[-1])  # Latest brief



    return SessionOut(

        id=session.id,

        user_id=session.user_id,

        session_date=session.session_date,

        name=session.name or _format_date(session.session_date),

        created_at=session.created_at,

        updated_at=session.updated_at,

        observations=obs_list,

        brief=brief,

    ).model_dump(mode="json")





# ── Session List ─────────────────────────────────────────



@router.get("/")

async def list_sessions(

    limit: int = 50,

    offset: int = 0,

    db: AsyncSession = Depends(get_db),

):

    """List all sessions for the demo user, newest first.



    Returns lightweight items: id, date, name, observation count,

    brief indicator, and first observation title as preview.

    """

    user = await ensure_demo_user(db)



    # Subquery: observation count per session

    obs_count_sq = (

        select(

            Observation.session_id,

            func.count(Observation.id).label("obs_count"),

            func.min(Observation.title).label("first_title"),

        )

        .group_by(Observation.session_id)

        .subquery()

    )



    # Subquery: has brief per session

    brief_exists_sq = (

        select(DailyBrief.session_id)

        .distinct()

        .subquery()

    )



    result = await db.execute(

        select(

            DailySession,

            func.coalesce(obs_count_sq.c.obs_count, 0).label("obs_count"),

            func.coalesce(obs_count_sq.c.first_title, "").label("first_title"),

            brief_exists_sq.c.session_id.isnot(None).label("has_brief"),

        )

        .outerjoin(obs_count_sq, DailySession.id == obs_count_sq.c.session_id)

        .outerjoin(brief_exists_sq, DailySession.id == brief_exists_sq.c.session_id)

        .where(DailySession.user_id == user.id)

        .order_by(DailySession.session_date.desc())

        .limit(limit)

        .offset(offset)

    )



    items = []

    for row in result.all():

        session = row[0]

        items.append(SessionListItem(

            id=session.id,

            session_date=session.session_date,

            name=session.name or _format_date(session.session_date),

            observation_count=row.obs_count,

            has_brief=bool(row.has_brief),

            preview=row.first_title or "",

            created_at=session.created_at,

        ).model_dump(mode="json"))



    return items





# ── Get Single Session ───────────────────────────────────



@router.get("/{session_id}")

async def get_session(

    session_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Get a single session with all observations and latest brief."""

    result = await db.execute(

        select(DailySession)

        .options(selectinload(DailySession.observations), selectinload(DailySession.briefs))

        .where(DailySession.id == session_id)

    )

    session = result.scalar_one_or_none()

    if not session:

        raise HTTPException(status_code=404, detail="Session not found")



    return _session_to_out(session)





# ── Get or Create Today ──────────────────────────────────



@router.post("/today")

async def get_or_create_today(db: AsyncSession = Depends(get_db)):

    """Get or create today's session for the demo user."""

    user = await ensure_demo_user(db)

    today = date.today()



    result = await db.execute(

        select(DailySession)

        .options(selectinload(DailySession.observations), selectinload(DailySession.briefs))

        .where(DailySession.user_id == user.id, DailySession.session_date == today)

    )

    session = result.scalar_one_or_none()



    if not session:

        session = DailySession(

            user_id=user.id,

            session_date=today,

            name=_format_date(today),

        )

        db.add(session)

        await db.commit()

        await db.refresh(session, ["observations", "briefs"])



    return _session_to_out(session)





# ── Rename Session ───────────────────────────────────────



@router.patch("/{session_id}")

async def rename_session(

    session_id: UUID,

    body: SessionRename,

    db: AsyncSession = Depends(get_db),

):

    """Rename a session."""

    result = await db.execute(select(DailySession).where(DailySession.id == session_id))

    session = result.scalar_one_or_none()

    if not session:

        raise HTTPException(status_code=404, detail="Session not found")



    session.name = body.name

    session.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {"id": str(session.id), "name": session.name}





# ── Create Observation ───────────────────────────────────



@router.post("/{session_id}/observations")

async def create_observation(

    session_id: UUID,

    body: ObservationCreate,

    background_tasks: BackgroundTasks,

    db: AsyncSession = Depends(get_db),

):

    """Create a new observation in the session."""

    result = await db.execute(select(DailySession).where(DailySession.id == session_id))

    session = result.scalar_one_or_none()

    if not session:

        raise HTTPException(status_code=404, detail="Session not found")



    # Auto-generate title from body if not provided

    title = body.title.strip() if body.title else ""

    if not title and body.body:

        # Take first line or first 80 chars of body

        first_line = body.body.strip().split('\n')[0]

        title = first_line[:80] if first_line else "Untitled"

    title = title or "Untitled"



    obs = Observation(

        session_id=session.id,

        title=title,

        body=body.body,

        sector_tags=body.sector_tags,

        has_image=body.has_image,

        has_voice=body.has_voice,

    )

    db.add(obs)

    session.updated_at = datetime.now(timezone.utc)

    await db.commit()

    await db.refresh(obs)



    # Background: extract entities + update convictions

    background_tasks.add_task(_extract_entities_background, obs.id, session.user_id)



    return ObservationOut.model_validate(obs).model_dump(mode="json")





# ── Edit Observation ─────────────────────────────────────



@router.patch("/{session_id}/observations/{obs_id}")

async def edit_observation(

    session_id: UUID,

    obs_id: UUID,

    body: ObservationUpdate,

    db: AsyncSession = Depends(get_db),

):

    """Edit an existing observation. All fields optional — only provided fields are updated."""

    result = await db.execute(

        select(Observation).where(

            Observation.id == obs_id,

            Observation.session_id == session_id,

        )

    )

    obs = result.scalar_one_or_none()

    if not obs:

        raise HTTPException(status_code=404, detail="Observation not found")



    update_data = body.model_dump(exclude_unset=True)

    for field, value in update_data.items():

        setattr(obs, field, value)

    obs.updated_at = datetime.now(timezone.utc)



    # Touch parent session

    sess_result = await db.execute(select(DailySession).where(DailySession.id == session_id))

    sess = sess_result.scalar_one_or_none()

    if sess:

        sess.updated_at = datetime.now(timezone.utc)



    await db.commit()

    await db.refresh(obs)

    return ObservationOut.model_validate(obs).model_dump(mode="json")





# ── Delete Observation ───────────────────────────────────



@router.delete("/{session_id}/observations/{obs_id}")

async def delete_observation(

    session_id: UUID,

    obs_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """Delete an observation. Hard delete — the frontend handles undo timing."""

    result = await db.execute(

        select(Observation).where(

            Observation.id == obs_id,

            Observation.session_id == session_id,

        )

    )

    obs = result.scalar_one_or_none()

    if not obs:

        raise HTTPException(status_code=404, detail="Observation not found")



    await db.delete(obs)



    # Touch parent session

    sess_result = await db.execute(select(DailySession).where(DailySession.id == session_id))

    sess = sess_result.scalar_one_or_none()

    if sess:

        sess.updated_at = datetime.now(timezone.utc)



    await db.commit()

    return {"deleted": True, "id": str(obs_id)}





# ── List Observations ────────────────────────────────────



@router.get("/{session_id}/observations")

async def list_observations(

    session_id: UUID,

    db: AsyncSession = Depends(get_db),

):

    """List all observations for a session, ordered by created_at."""

    result = await db.execute(

        select(Observation)

        .where(Observation.session_id == session_id)

        .order_by(Observation.created_at)

    )

    observations = result.scalars().all()

    return [ObservationOut.model_validate(o).model_dump(mode="json") for o in observations]





# ── Quick Capture ────────────────────────────────────────



class _EnrichmentPayload(BaseModel):

    """Internal model for structured enrichment from fast LLM."""

    title: str = Field(..., description="Concise title extracted from text (<10 words)")

    sector_tags: list[str] = Field(

        default_factory=list,

        description="1-3 sector tags from: fintech, ai, saas, health, crypto, climate, infra, devtools, personal, enterprise, consumer",

    )





async def _enrich_observation(obs_id: UUID, text: str, user_id: UUID):

    """Background task: AI-enrich a quick-captured observation with title + tags, then extract entities."""

    from db.postgres import async_session_factory



    try:

        mc = get_model_client()

        enrichment = await mc.extract(

            prompt=(

                f"Extract from this VC demo day note:\n"

                f"1. A concise title (company name or key topic, <10 words)\n"

                f"2. Sector tags (1-3 from: fintech, ai, saas, health, crypto, climate, infra, devtools, enterprise, consumer)\n\n"

                f'Note: "{text}"'

            ),

            response_model=_EnrichmentPayload,

            model=mc.settings.default_fast_model,

            temperature=0.1,

        )



        async with async_session_factory() as db:

            result = await db.execute(select(Observation).where(Observation.id == obs_id))

            obs = result.scalar_one_or_none()

            if obs:

                obs.title = enrichment.title

                obs.sector_tags = enrichment.sector_tags

                obs.updated_at = datetime.now(timezone.utc)

                await db.commit()

    except Exception as e:

        print(f"Quick capture enrichment failed for {obs_id}: {e}")



    # Entity extraction runs after enrichment so we get the real title/tags

    await _extract_entities_background(obs_id, user_id)





async def _extract_entities_background(obs_id: UUID, user_id: UUID):

    """Background task: extract entities + update convictions for an observation."""

    from db.postgres import async_session_factory

    from services.entity_extractor import extract_entities_from_observation

    from services.conviction_engine import process_conviction_updates

    from models.tables import EntityMention



    try:

        async with async_session_factory() as db:

            result = await db.execute(select(Observation).where(Observation.id == obs_id))

            obs = result.scalar_one_or_none()

            if not obs:

                return



            # Skip entity extraction for personal notes (non-VC content creates noise)

            tags = obs.sector_tags if isinstance(obs.sector_tags, list) else []

            if tags == ["personal"]:

                return



            entities = await extract_entities_from_observation(obs, user_id, db)



            # Build entity-sentiment pairs from the mentions just created

            entity_sentiments = []

            for entity in entities:

                # Get the sentiment from the mention we just created

                m_result = await db.execute(

                    select(EntityMention).where(

                        EntityMention.entity_id == entity.id,

                        EntityMention.observation_id == obs_id,

                    )

                )

                mention = m_result.scalar_one_or_none()

                sentiment = mention.sentiment if mention else "neutral"

                entity_sentiments.append((entity, sentiment))



            # Update convictions

            await process_conviction_updates(entity_sentiments, obs, user_id, db)

            await db.commit()

    except Exception as e:

        print(f"Entity extraction background task failed for obs {obs_id}: {e}")





@router.post("/today/quick")

async def quick_capture(

    body: QuickCapture,

    background_tasks: BackgroundTasks,

    db: AsyncSession = Depends(get_db),

):

    """Single-field quick capture. Saves instantly, enriches with AI in background.



    The observation is saved immediately with raw text as both title and body.

    A background task then extracts a proper title and infers sector tags using

    the fast model. The frontend can poll or just update when enrichment completes.

    """

    user = await ensure_demo_user(db)

    today = date.today()



    # Get or create today's session

    result = await db.execute(

        select(DailySession)

        .where(DailySession.user_id == user.id, DailySession.session_date == today)

    )

    session = result.scalar_one_or_none()

    if not session:

        session = DailySession(

            user_id=user.id,

            session_date=today,

            name=_format_date(today),

        )

        db.add(session)

        await db.flush()



    # Save immediately — raw text as title (truncated) and full body

    obs = Observation(

        session_id=session.id,

        title=body.text[:80],

        body=body.text,

        sector_tags=[],

    )

    db.add(obs)

    session.updated_at = datetime.now(timezone.utc)

    await db.commit()

    await db.refresh(obs)



    # Fire background AI enrichment (includes entity extraction)

    background_tasks.add_task(_enrich_observation, obs.id, body.text, user.id)



    return ObservationOut.model_validate(obs).model_dump(mode="json")





# ── Media Upload ─────────────────────────────────────────



# Size limits

MAX_AUDIO_MB = 25  # Whisper API limit

MAX_IMAGE_MB = 10





@router.post("/{session_id}/observations/media")

async def create_observation_with_media(

    session_id: UUID,

    background_tasks: BackgroundTasks,

    title: str = Form(""),

    body: str = Form(""),

    sector_tags: str = Form("[]"),  # JSON array string from frontend

    voice_transcript_from_browser: str = Form(""),  # Live transcript from Web Speech API

    voice: UploadFile | None = File(None),

    image: UploadFile | None = File(None),

    db: AsyncSession = Depends(get_db),

):

    """Create an observation with optional voice/image attachments.



    Voice transcription prefers browser-provided transcript (Web Speech API).

    Falls back to Whisper API if no browser transcript is provided.

    Images are analyzed via GPT-4o Vision.

    """

    import json



    result = await db.execute(select(DailySession).where(DailySession.id == session_id))

    session = result.scalar_one_or_none()

    if not session:

        raise HTTPException(status_code=404, detail="Session not found")



    # Parse sector_tags from JSON string

    try:

        tags = json.loads(sector_tags) if sector_tags else []

        if isinstance(tags, str):

            tags = [tags] if tags else []

    except (json.JSONDecodeError, TypeError):

        tags = [sector_tags] if sector_tags else []



    mc = get_model_client()

    voice_transcript = ""

    image_summary = ""



    # ── Voice transcription ───────────────────────────

    if voice_transcript_from_browser.strip():

        # Browser provided live transcript via Web Speech API — use it directly

        voice_transcript = voice_transcript_from_browser.strip()

    elif voice and voice.filename:

        # Fallback: try Whisper API for server-side transcription

        spooled = SpooledTemporaryFile(max_size=1024 * 1024)

        size = 0

        while chunk := await voice.read(64 * 1024):

            size += len(chunk)

            if size > MAX_AUDIO_MB * 1024 * 1024:

                spooled.close()

                raise HTTPException(status_code=413, detail=f"Audio file too large (max {MAX_AUDIO_MB}MB)")

            spooled.write(chunk)

        spooled.seek(0)

        audio_file = (voice.filename, spooled, voice.content_type or "audio/webm")

        try:

            voice_transcript = await mc.transcribe(audio_file)

        except Exception as e:

            print(f"Whisper transcription failed: {e}")

            voice_transcript = "[transcription failed]"

        finally:

            spooled.close()



    # ── Image -> save to disk + GPT Vision analysis ───

    img_bytes = None

    if image and image.filename:

        img_bytes = await image.read()

        if len(img_bytes) > MAX_IMAGE_MB * 1024 * 1024:

            raise HTTPException(status_code=413, detail=f"Image file too large (max {MAX_IMAGE_MB}MB)")

        b64 = base64.b64encode(img_bytes).decode("utf-8")

        mime = image.content_type or "image/jpeg"

        data_url = f"data:{mime};base64,{b64}"

        try:

            image_summary = await mc.vision(

                data_url,

                "You are a VC analyst. Describe what this image shows in the context of "

                "a startup demo day. Extract any key metrics, text, or product details visible. "

                "Be concise — 2-3 sentences max."

            )

        except Exception as e:

            print(f"Vision analysis failed: {e}")

            image_summary = "[image analysis failed]"



    # ── Enrich body with extracted content ────────────

    enriched_body = body

    if voice_transcript and voice_transcript != "[transcription failed]":

        enriched_body += ("\n\n" if enriched_body else "") + f"Transcription: {voice_transcript}"

    if image_summary and image_summary != "[image analysis failed]":

        enriched_body += ("\n\n" if enriched_body else "") + f"Visual analysis: {image_summary}"



    obs = Observation(

        session_id=session.id,

        title=title or "Untitled",

        body=enriched_body,

        sector_tags=tags,

        has_image=bool(image and image.filename),

        has_voice=bool(voice and voice.filename),

        voice_transcript=voice_transcript,

        image_summary=image_summary,

    )

    db.add(obs)

    session.updated_at = datetime.now(timezone.utc)

    await db.commit()

    await db.refresh(obs)



    # Persist image to disk (after commit so we have the obs ID)

    if img_bytes:

        import os

        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

        os.makedirs(uploads_dir, exist_ok=True)

        ext = (image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else "jpg")

        filepath = os.path.join(uploads_dir, f"{obs.id}.{ext}")

        with open(filepath, "wb") as f:

            f.write(img_bytes)



    # Background: extract entities + update convictions

    background_tasks.add_task(_extract_entities_background, obs.id, session.user_id)



    return ObservationOut.model_validate(obs).model_dump(mode="json")
