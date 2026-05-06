"""

Coviction API — Main application entry point.

FastAPI with async Postgres and CORS.

"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from fastapi.responses import RedirectResponse

from starlette.middleware.base import BaseHTTPMiddleware

import os
from sqlalchemy import text



from core.config import get_settings

from db.postgres import engine, Base

from routers import sessions, brief, ask, search, export, entities, convictions, graph, media





@asynccontextmanager

async def lifespan(app: FastAPI):

    """Startup/shutdown lifecycle — create tables on boot."""

    # Import models so Base.metadata knows about them

    import models.tables  # noqa: F401



    settings = get_settings()

    print(f"Coviction API starting (debug={settings.debug})")



    async with engine.begin() as conn:

        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:email) "
                "ON CONFLICT (email) DO NOTHING"
            ),
            {"email": "demo@coviction.ai"},
        )

    print("Database tables created/verified and demo user seeded")



    yield



    print("Coviction API shutting down")





settings = get_settings()



app = FastAPI(

    title="Coviction API",

    description="Demo day companion for VCs — capture, brief, ask",

    version="0.1.0",

    lifespan=lifespan,

)



# CORS

app.add_middleware(

    CORSMiddleware,

    allow_origins=settings.cors_origins,

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



# Routers

app.include_router(sessions.router)

app.include_router(brief.router)

app.include_router(ask.router)

app.include_router(search.router)

app.include_router(export.router)

app.include_router(entities.router)

app.include_router(convictions.router)

app.include_router(graph.router)

app.include_router(media.router)



# No-cache middleware for static HTML (dev mode — prevents stale JS)

class NoCacheHTMLMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        response = await call_next(request)

        if request.url.path.startswith("/app") and (

            request.url.path.endswith(".html") or request.url.path.endswith("/")

        ):

            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

            response.headers["Pragma"] = "no-cache"

        return response



app.add_middleware(NoCacheHTMLMiddleware)



# Serve static files (HTML prototypes)

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.isdir(static_dir):

    app.mount("/app", StaticFiles(directory=static_dir, html=True), name="static")





@app.get("/")

async def root():

    """Redirect root to landing page."""

    return RedirectResponse(url="/app/")





@app.get("/health")

async def health():

    return {"status": "ok", "service": "coviction-api"}
