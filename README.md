# Coviction



**The Second Brain for VCs.**



Coviction is a purpose-built companion for venture capitalists attending demo days, partner meetings, and sourcing events. Capture messy observations between pitches, generate structured AI briefs, build a knowledge graph of every entity you encounter, and watch conviction scores evolve over time.



---



## What it does



| Feature | Description |

|---------|-------------|

| **Quick Capture** | Title + notes + sector tag in 10 seconds. Supports voice memos and image capture. |

| **AI Briefs** | One-tap synthesis of raw notes into themes, standout signals, and follow-up actions. |

| **Action Tracker** | Auto-generated follow-ups from briefs + manual additions. Check them off as you go. |

| **Knowledge Graph** | Entities (companies, people, concepts, metrics) auto-extracted and linked via co-occurrence. |

| **Conviction Engine** | Living belief scores that compound on signal and decay on silence. Full audit trail. |

| **Deal Memos** | One-click AI-generated memo for any entity using all available context. |

| **Context Search** | Full-text search across all observations, transcripts, and image summaries. |

| **Morning Brief** | Daily heartbeat: new entities, rising convictions, suggested actions. |



---



## Architecture



```

coviction/

├── api/                    # FastAPI backend (async)

│   ├── main.py             # Entry point + static file serving

│   ├── core/

│   │   ├── config.py       # Pydantic settings (all env vars)

│   │   └── model_client.py # Unified LLM client (OpenAI SDK + instructor)

│   ├── db/

│   │   └── postgres.py     # SQLAlchemy 2.0 async engine

│   ├── models/

│   │   └── tables.py       # All database models (7 tables)

│   ├── routers/

│   │   ├── sessions.py     # Sessions + observations CRUD

│   │   ├── brief.py        # Daily brief generation (LLM)

│   │   ├── ask.py          # Context-aware chat (LLM)

│   │   ├── search.py       # Full-text search (Postgres GIN)

│   │   ├── entities.py     # Entity CRUD + extraction trigger

│   │   ├── convictions.py  # Conviction scoring + audit trail

│   │   ├── graph.py        # Knowledge graph + timeline + deal memos

│   │   ├── export.py       # JSON/CSV export

│   │   └── media.py        # Uploaded file serving

│   ├── services/

│   │   ├── entity_extractor.py  # LLM-powered entity extraction

│   │   ├── conviction_engine.py # Score computation + decay

│   │   └── heartbeat.py         # Morning brief + pattern detection

│   └── requirements.txt

├── static/                 # Frontend (pure HTML/CSS/JS — no build step)

│   ├── index.html          # Landing page (marketing)

│   ├── coviction-app.html  # Main app (capture + brief + ask + graph)

│   ├── coviction-memory.html # Memory Map (force-directed knowledge graph)

│   ├── manifest.json       # PWA manifest

│   └── sw.js               # Service worker (offline capture)

├── uploads/                # Local image/voice file storage

├── infra/

│   └── init.sql            # Database schema + indexes

└── migrate.sql             # Schema migrations (idempotent)

```



---



## Quick Start



### Prerequisites



- Python 3.12+

- PostgreSQL 16+

- An OpenAI-compatible API key



### 1. Clone and install



```bash

git clone https://github.com/YOUR_USER/coviction.git

cd coviction

python3 -m venv .venv

source .venv/bin/activate

pip install -r api/requirements.txt

```



### 2. Start PostgreSQL



**Docker:**

```bash

docker run -d --name coviction-pg \

  -e POSTGRES_DB=coviction \

  -e POSTGRES_USER=coviction \

  -e POSTGRES_PASSWORD=dev_password \

  -p 5432:5432 \

  postgres:16

```



**Or local Postgres:**

```bash

createdb coviction

```



### 3. Configure environment



```bash

cat > api/.env <<'EOF'

DATABASE_URL=postgresql+asyncpg://coviction:dev_password@localhost:5432/coviction

OPENAI_API_KEY=sk-your-key-here

DEFAULT_STRONG_MODEL=gpt-4o-mini

DEFAULT_FAST_MODEL=gpt-4o-mini

DEBUG=True

EOF

```



### 4. Run



```bash

cd api

uvicorn main:app --reload --port 8000

```



Open http://localhost:8000 — landing page loads. Click "Start capturing" to enter the app.



Interactive API docs: http://localhost:8000/docs



---



## Environment Variables



| Variable | Required | Default | Description |

|----------|----------|---------|-------------|

| `DATABASE_URL` | Yes | local Postgres | Async Postgres connection string |

| `OPENAI_API_KEY` | Yes | — | OpenAI API key |

| `OPENAI_BASE_URL` | No | `None` (OpenAI direct) | Override for compatible proxies |

| `DEFAULT_STRONG_MODEL` | No | `gpt-4o-mini` | Model for briefs, ask, deal memos |

| `DEFAULT_FAST_MODEL` | No | `gpt-4o-mini` | Model for entity extraction |

| `DEFAULT_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model |

| `GENAI_CA_CERT` | No | — | Custom CA cert path (proxy setups) |

| `JWT_SECRET` | No | dev default | **Change in production** |

| `JWT_EXPIRY_HOURS` | No | `72` | Token lifetime |

| `WHISPER_MODEL` | No | `whisper-1` | Audio transcription model |

| `DEBUG` | No | `True` | Debug mode (SQL echo, etc.) |

| `CORS_ORIGINS` | No | `["*"]` | Allowed CORS origins |



---



## API Endpoints



| Method | Path | Description |

|--------|------|-------------|

| GET | `/health` | Health check |

| GET | `/sessions/` | List all sessions |

| POST | `/sessions/today/quick` | Get/create today's session |

| PATCH | `/sessions/{id}` | Rename session |

| POST | `/sessions/{id}/observations` | Create observation |

| POST | `/sessions/{id}/observations/media` | Create with voice/image |

| DELETE | `/sessions/{id}/observations/{obs_id}` | Delete observation |

| POST | `/sessions/{id}/daily-brief` | Generate AI brief |

| GET | `/sessions/{id}/daily-brief` | Get latest brief |

| POST | `/ask` | Ask your notes a question |

| GET | `/search?q=...` | Full-text search |

| GET | `/sessions/{id}/export` | Export session (JSON/CSV) |

| GET | `/knowledge/entities` | List extracted entities |

| GET | `/knowledge/convictions` | List conviction theses |

| GET | `/knowledge/convictions/{id}` | Conviction detail + audit trail |

| POST | `/knowledge/convictions` | Create thesis manually |

| PATCH | `/knowledge/convictions/{id}/score` | Adjust conviction score |

| GET | `/knowledge/graph` | Full knowledge graph (nodes + edges) |

| GET | `/knowledge/graph/timeline` | Session activity heatmap data |

| POST | `/knowledge/graph/deal-memo/{entity_id}` | Generate deal memo |

| GET | `/knowledge/morning-brief` | Morning brief + patterns |

| GET | `/media/{obs_id}` | Serve uploaded media |



---



## GenAI Dependency Map



All LLM calls route through `api/core/model_client.py` — a single `ModelClient` singleton.



| Feature | File | Without LLM |

|---------|------|-------------|

| Daily brief generation | `routers/brief.py` | Returns error |

| Ask / chat | `routers/ask.py` | Returns error |

| Entity extraction | `services/entity_extractor.py` | Fails silently, capture still works |

| Voice transcription | `routers/sessions.py` | Falls back to browser Web Speech API |

| Image analysis | `routers/sessions.py` | Falls back to placeholder |

| Deal memo generation | `routers/graph.py` | Returns error message |

| Morning brief | `services/heartbeat.py` | Falls back to counts-only text |



**Core features that work without LLM**: Observation capture, sessions, search, export, entities CRUD, convictions CRUD, knowledge graph queries, media serving.



---



## Deployment



### Compute options



| Provider | Cost | Notes |

|----------|------|-------|

| **Render** | Free tier or $7/mo | Deploy from Git, auto-SSL |

| **Railway** | $5/mo | Easiest Postgres add-on |

| **Fly.io** | $0-5/mo | Edge deployment |

| **Firebase (Cloud Run)** | Pay-per-use | Good for low traffic |

| **VPS (Hetzner, DigitalOcean)** | $4-6/mo | Full control |



### Database options



| Provider | Cost | Notes |

|----------|------|-------|

| **Neon** | Free tier (0.5GB) | Serverless Postgres, generous free |

| **Supabase** | Free tier (500MB) | Postgres + extras |

| **Railway** | Included in $5 plan | Simplest if using Railway compute |

| **PlanetScale** | — | MySQL only, won't work |



### Start command for production



```bash

cd api && gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:$PORT

```



Or simpler:

```bash

cd api && uvicorn main:app --host 0.0.0.0 --port $PORT

```



### Production env vars



```bash

DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/coviction

OPENAI_API_KEY=sk-...

JWT_SECRET=$(openssl rand -hex 32)

DEBUG=False

CORS_ORIGINS=https://your-domain.com

DEFAULT_STRONG_MODEL=gpt-4o-mini

DEFAULT_FAST_MODEL=gpt-4o-mini

```



### What's NOT needed



- No Redis / message queue — uses FastAPI BackgroundTasks

- No build step for frontend — static HTML served directly

- No CDN — static files are <200KB total

- No vector database — uses Postgres full-text search (GIN index)

- No Celery / workers — fully async single process

- No Docker required — single `uvicorn` process



---



## Tech Stack



- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + asyncpg

- **Database**: PostgreSQL 16 (full-text search, JSONB, uuid-ossp)

- **LLM**: OpenAI SDK + instructor (structured outputs)

- **Frontend**: Vanilla HTML/CSS/JS (no framework, no build, no node_modules)

- **Auth**: JWT (PyJWT) — configured but not enforced in demo mode

- **Deployment**: Single uvicorn process, ~256MB RAM



---



## License



MIT
