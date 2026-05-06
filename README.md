<p align="center">

  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-GPT--4o-412991?style=flat-square&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/Architecture-Agentic-FF6F00?style=flat-square" />
</p>

<h1 align="center">Coviction</h1>
<p align="center"><strong>Agentic second brain for venture capital.</strong></p>
<p align="center">
  <em>Capture raw signal between pitches. Let autonomous AI agents extract entities, build a living knowledge graph, compute evolving conviction scores, and synthesize institutional-grade deal memos — all in real time.</em>
</p>

---

## Why Coviction Exists

VCs attend 200+ pitches a year but retain maybe 30% of what they hear. Notes rot in Apple Notes. Conviction fades without reinforcement. Pattern recognition stays locked in your head instead of compounding in a system.

**Coviction is an agentic intelligence layer that turns raw observations into structured, queryable institutional memory** — with conviction scores that evolve like a living thesis document.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER (PWA)                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐ │
│  │ Quick Capture│  │  AI Chat/Ask │  │Memory Map   │  │  Action Tracker  │ │
│  │ (10s input) │  │ (RAG agent)  │  │(Force Graph)│  │  (Auto-gen)      │ │
│  └─────────────┘  └──────────────┘  └─────────────┘  └──────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ REST API
┌──────────────────────────────┼──────────────────────────────────────────────┐
│                         ORCHESTRATION LAYER                                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    FastAPI Async Router Mesh                            │ │
│  │  sessions • brief • ask • search • entities • convictions • graph      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                               │                                              │
│  ┌────────────────────────────┼────────────────────────────────────────────┐│
│  │              AUTONOMOUS AGENT SERVICES                                   ││
│  │                                                                          ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  ││
│  │  │ Entity Extractor │  │ Conviction Engine │  │  Heartbeat Agent     │  ││
│  │  │ Agent            │  │                   │  │                      │  ││
│  │  │                  │  │ • Bayesian score   │  │ • Pattern detection  │  ││
│  │  │ • NER extraction │  │   accumulation    │  │ • Morning brief gen  │  ││
│  │  │ • Sentiment      │  │ • Passive decay   │  │ • Trend surfacing    │  ││
│  │  │   analysis       │  │   (time-weighted) │  │ • Action generation  │  ││
│  │  │ • Co-occurrence  │  │ • Audit trail     │  │                      │  ││
│  │  │   linking        │  │   logging         │  │                      │  ││
│  │  │ • Structured     │  │                   │  │                      │  ││
│  │  │   output (inst.) │  │                   │  │                      │  ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                               │                                              │
│  ┌────────────────────────────┼────────────────────────────────────────────┐│
│  │                    AI INFRASTRUCTURE                                      ││
│  │                                                                          ││
│  │  ModelClient (singleton) ─── OpenAI SDK + Instructor (structured gen)   ││
│  │       │                                                                  ││
│  │       ├── Structured outputs via Pydantic response models               ││
│  │       ├── Multi-model routing (strong/fast/embedding)                   ││
│  │       ├── Custom CA cert bridging for enterprise proxies                ││
│  │       └── Graceful degradation (core features work without LLM)         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────────┐
│                        DATA LAYER                                             │
│                                                                              │
│  PostgreSQL 16 (async via asyncpg)                                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────────────┐ │
│  │   Users    │ │  Sessions  │ │Observations│ │  Entities + Mentions     │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────────────────────────┐ │
│  │   Briefs   │ │Convictions │ │  ConvictionLogs (immutable audit trail)  │ │
│  └────────────┘ └────────────┘ └──────────────────────────────────────────┘ │
│                                                                              │
│  Indexes: GIN full-text • B-tree composite • UUID primary keys • JSONB      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Agentic AI Pipeline

Coviction operates as a **multi-agent system** where autonomous services react to user input in real time:

### 1. Entity Extraction Agent
Fires as a background task on every observation. Uses `instructor` for structured LLM output with Pydantic validation:

```python
# Structured output schema — LLM must conform to this contract
class ExtractedEntity(BaseModel):
    name: str
    entity_type: Literal["company", "person", "concept", "metric"]
    sentiment: Literal["positive", "negative", "neutral"]
    context_snippet: str
```

- Extracts companies, people, concepts, and metrics from unstructured notes
- Performs sentiment classification per-mention
- Deduplicates against existing entity store (fuzzy match)
- Creates co-occurrence edges automatically (same observation = linked)

### 2. Conviction Engine
A **time-decay Bayesian scoring system** that models belief strength:

```
conviction_score = base_score × decay_factor(days_since_last_signal)
```

- Every reinforcing mention **compounds** the score upward
- Silence **passively decays** conviction (configurable half-life)
- Full immutable audit trail — every score change logged with trigger observation
- Manual override with mandatory reasoning (VC can always pull rank)

### 3. Heartbeat / Pattern Detection Agent
Runs on-demand or as a scheduled morning brief:

- Identifies trending entities (acceleration detection)
- Surfaces high-conviction theses ready for action
- Generates follow-up actions from accumulated context
- Cross-session pattern recognition (repeated themes, evolving sentiment)

### 4. RAG-Powered Conversational Agent
Context-aware chat that retrieves from the user's full observation history:

- Single-session mode: scoped to one demo day
- Cross-session mode: pulls from 30 days of context
- Observation-grounded answers with source attribution
- System prompt enforces sharp, investor-grade tone

### 5. Deal Memo Generator
One-click synthesis that pulls:
- All mentions + sentiment breakdown
- Current conviction score + thesis
- Connected entities from knowledge graph
- Raw observation snippets as evidence

Produces a structured memo: Summary → Bull Case → Bear Case → Key Connections → Recommended Next Step.

---

## Knowledge Graph Engine

The knowledge graph is built automatically through co-occurrence analysis:

- **Nodes**: Entities (companies, people, concepts, metrics) + virtual sector tag nodes
- **Edges**: Weighted by co-occurrence frequency across observations
- **Conviction overlay**: Node size/color driven by real-time conviction scores
- **Force-directed visualization**: D3.js physics simulation with interactive exploration

```sql
-- Co-occurrence edge computation (real query from the codebase)
SELECT a.entity_id AS source, b.entity_id AS target,
       COUNT(DISTINCT a.observation_id) AS weight
FROM entity_mentions a
JOIN entity_mentions b ON a.observation_id = b.observation_id
  AND a.entity_id < b.entity_id
GROUP BY a.entity_id, b.entity_id
ORDER BY weight DESC
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Runtime** | Python 3.12 + FastAPI (async) | Native async/await, 10k+ req/s single process |
| **Database** | PostgreSQL 16 + asyncpg | Full-text search (GIN), JSONB, UUID native, zero external deps |
| **ORM** | SQLAlchemy 2.0 (async) | Type-safe queries, relationship loading, migration-ready |
| **AI Framework** | OpenAI SDK + Instructor | Structured outputs with Pydantic validation, retry logic |
| **Search** | PostgreSQL `ts_vector` + GIN index | No Elasticsearch needed — Postgres handles it natively |
| **Frontend** | Vanilla HTML/CSS/JS | Zero build step, zero node_modules, PWA-capable, <200KB total |
| **Auth** | JWT (PyJWT) | Stateless, configured for multi-tenant (demo mode bypasses) |
| **Deployment** | Single uvicorn process | ~256MB RAM, no Redis, no Celery, no Docker required |

---

## Features

| Feature | Description |
|---------|-------------|
| **Quick Capture** | Title + notes + sector tags in <10 seconds. Voice memo transcription (Whisper). Image analysis (GPT-4V). |
| **AI Daily Briefs** | One-tap synthesis → themes, standout signals, contradictions, follow-up actions |
| **Knowledge Graph** | Auto-extracted entities linked by co-occurrence. Force-directed interactive visualization. |
| **Conviction Scores** | Time-decay belief system. Compounds on signal, decays on silence. Full audit trail. |
| **Deal Memos** | One-click LLM-generated memos with bull/bear case, connections, and recommended action |
| **Cross-Session RAG** | Ask questions across 30 days of observations with source attribution |
| **Full-Text Search** | PostgreSQL GIN-indexed search across all text fields + ILIKE fallback |
| **Morning Brief** | Pattern detection: trending entities, rising convictions, suggested actions |
| **Action Tracker** | Auto-generated follow-ups from briefs + manual items. Priority and status tracking. |
| **PWA + Offline** | Service worker caches app shell. Works on mobile between pitches. |
| **Export** | JSON + CSV export per session for downstream analysis |

---

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USER/coviction.git && cd coviction

# Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt

# Database (Docker one-liner)
docker run -d --name coviction-pg \
  -e POSTGRES_DB=coviction -e POSTGRES_USER=coviction \
  -e POSTGRES_PASSWORD=dev_password -p 5432:5432 postgres:16

# Configure
cp api/.env.example api/.env  # Edit with your OpenAI key

# Run
cd api && uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` — landing page loads. Click **"Start Capturing"** to enter the app.

API docs: `http://localhost:8000/docs`

---

## API Surface

<details>
<summary><strong>Full endpoint reference (21 routes)</strong></summary>

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/sessions/` | List all sessions |
| `POST` | `/sessions/today/quick` | Get/create today's session |
| `PATCH` | `/sessions/{id}` | Rename session |
| `POST` | `/sessions/{id}/observations` | Create observation |
| `POST` | `/sessions/{id}/observations/media` | Create with voice/image upload |
| `DELETE` | `/sessions/{id}/observations/{obs_id}` | Delete observation |
| `POST` | `/sessions/{id}/daily-brief` | Generate AI brief |
| `GET` | `/sessions/{id}/daily-brief` | Get latest brief |
| `POST` | `/ask` | Context-aware chat |
| `GET` | `/search?q=...` | Full-text search |
| `GET` | `/sessions/{id}/export` | Export (JSON/CSV) |
| `GET` | `/knowledge/entities` | List entities |
| `GET` | `/knowledge/entities/{id}` | Entity detail + mentions |
| `GET` | `/knowledge/convictions` | List convictions |
| `GET` | `/knowledge/convictions/{id}` | Conviction + audit trail |
| `POST` | `/knowledge/convictions` | Create thesis |
| `PATCH` | `/knowledge/convictions/{id}/score` | Manual score adjust |
| `GET` | `/knowledge/graph` | Full knowledge graph |
| `GET` | `/knowledge/graph/timeline` | Session heatmap |
| `POST` | `/knowledge/graph/deal-memo/{entity_id}` | Generate deal memo |
| `GET` | `/knowledge/panel` | Aggregate knowledge panel |
| `GET` | `/knowledge/morning-brief` | Morning brief + patterns |

</details>

---

## Environment Variables

<details>
<summary><strong>Configuration reference</strong></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | `postgresql+asyncpg://user:pass@host:5432/coviction` |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key (or compatible provider) |
| `OPENAI_BASE_URL` | No | OpenAI direct | Override for Azure, Anyscale, local models |
| `DEFAULT_STRONG_MODEL` | No | `gpt-4o-mini` | Brief generation, chat, deal memos |
| `DEFAULT_FAST_MODEL` | No | `gpt-4o-mini` | Entity extraction, classification |
| `DEFAULT_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Future: semantic search |
| `GENAI_CA_CERT` | No | — | Custom CA cert for enterprise proxy |
| `JWT_SECRET` | No | dev default | **Must change in production** |
| `WHISPER_MODEL` | No | `whisper-1` | Audio transcription |
| `DEBUG` | No | `True` | SQL echo, verbose errors |
| `CORS_ORIGINS` | No | `["*"]` | Restrict in production |

</details>

---

## Graceful Degradation

The system is designed to operate **with or without LLM access**:

| Feature | With LLM | Without LLM |
|---------|----------|-------------|
| Observation capture | Full | Full |
| Entity extraction | Auto (background agent) | Manual only |
| Daily briefs | AI-generated | Unavailable |
| Conviction scores | Auto-compound on signal | Manual adjustment only |
| Search | Full | Full |
| Knowledge graph | Full | Full (no new auto-edges) |
| Deal memos | AI-generated | Unavailable |
| Export | Full | Full |

Core data capture and retrieval always works. AI features enhance but don't gate the workflow.

---

## Deployment

**Single process. No infrastructure complexity.**

```bash
# Production start
cd api && gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:$PORT
```

**What you DON'T need:**
- No Redis / message queue — FastAPI `BackgroundTasks`
- No Elasticsearch — PostgreSQL GIN indexes
- No vector database — full-text search is sufficient for this scale
- No Celery / worker processes — fully async single process
- No Docker required — single `uvicorn` command
- No CDN — static assets are <200KB
- No build step — HTML served directly

**Recommended hosting:** Railway ($5/mo with Postgres) or Render (free tier).

---

## Project Structure

```
coviction/
├── api/
│   ├── main.py                    # FastAPI app + static mount + lifespan
│   ├── core/
│   │   ├── auth.py                # User resolution (shared across all routers)
│   │   ├── config.py              # Pydantic Settings (env → typed config)
│   │   └── model_client.py        # Unified LLM client singleton
│   ├── db/
│   │   └── postgres.py            # SQLAlchemy async engine + session factory
│   ├── models/
│   │   └── tables.py              # 7 ORM models (User → ConvictionLog)
│   ├── routers/
│   │   ├── sessions.py            # Session + observation CRUD
│   │   ├── brief.py               # AI brief generation
│   │   ├── ask.py                 # RAG chat agent
│   │   ├── search.py              # Full-text search (GIN + ILIKE)
│   │   ├── entities.py            # Entity CRUD + knowledge panel
│   │   ├── convictions.py         # Conviction scoring + audit
│   │   ├── graph.py               # Knowledge graph + deal memos
│   │   ├── export.py              # JSON/CSV export
│   │   └── media.py               # File serving
│   ├── services/
│   │   ├── entity_extractor.py    # Autonomous NER agent
│   │   ├── conviction_engine.py   # Bayesian decay scoring
│   │   └── heartbeat.py           # Pattern detection + morning brief
│   ├── schemas/
│   │   ├── session.py             # Request/response models
│   │   └── knowledge.py           # Entity/conviction schemas
│   └── requirements.txt
├── static/
│   ├── index.html                 # Marketing landing page
│   ├── coviction-app.html         # Main application UI
│   ├── coviction-memory.html      # Knowledge graph visualization
│   ├── manifest.json              # PWA manifest
│   └── sw.js                      # Service worker (offline support)
├── infra/
│   └── init.sql                   # Full schema + indexes + seed
├── migrate.sql                    # Idempotent migrations
└── uploads/                       # Local media storage
```

---

## License

MIT

---

<p align="center">
  <em>Built for investors who think in theses, not spreadsheets.</em>
</p>
