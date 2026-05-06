# Deploy Coviction AI

This project deploys as one FastAPI web service. The API and frontend run from the same process:

- API routes: `/sessions`, `/ask`, `/knowledge`, `/search`, `/media`
- Frontend: `/app/`
- Health check: `/health`

For the MVP, use Render for the web service and Neon for Postgres.

## 1. Create the Postgres database on Neon

1. Go to https://neon.com
2. Click **Sign up** or **Log in**.
3. Click **New Project**.
4. Use:
   - Project name: `coviction-ai`
   - Database name: `coviction`
   - Region: pick the closest region to where you will deploy Render.
5. Open the project dashboard.
6. Go to **Connection Details**.
7. Copy the pooled or direct connection string.
8. Convert it for SQLAlchemy asyncpg:

```text
postgresql://USER:PASSWORD@HOST/DB?sslmode=require
```

becomes:

```text
postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require
```

Keep this value ready for Render as `DATABASE_URL`.

## 2. Create the Render web service

1. Go to https://dashboard.render.com
2. Click **New**.
3. Click **Web Service**.
4. Connect GitHub if needed.
5. Select `Madhav2310/Coviction-AI`.
6. Use:
   - Name: `coviction-ai`
   - Runtime: `Python`
   - Branch: `main`
   - Root Directory: leave blank
   - Build Command: `pip install -r api/requirements.txt`
   - Start Command: `cd api && uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Choose the free instance type for an MVP demo, or the cheapest paid instance if you want no cold starts.

## 3. Add Render environment variables

In the Render service page:

1. Click **Environment**.
2. Add:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require
OPENAI_API_KEY=your_openai_key
DEFAULT_STRONG_MODEL=gpt-4o-mini
DEFAULT_FAST_MODEL=gpt-4o-mini
DEBUG=False
JWT_SECRET=replace_with_a_long_random_secret
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=2
CORS_ORIGINS=["https://coviction-ai.onrender.com"]
```

Use your actual Render service URL for `CORS_ORIGINS` after Render shows it. If you rename the service, the URL may differ.

## 4. Deploy and verify

1. Click **Manual Deploy**.
2. Click **Deploy latest commit**.
3. Wait for the build to finish.
4. Open:

```text
https://YOUR_RENDER_URL/health
```

Expected:

```json
{"status":"ok","service":"coviction-api"}
```

5. Open:

```text
https://YOUR_RENDER_URL/app/
```

The app should load and create the demo user automatically on startup.

## MVP caveats

- Everyone uses the same hardcoded demo user, `demo@coviction.ai`.
- Uploaded images are stored on the web service filesystem. On free/ephemeral hosting, uploads may disappear after restarts. For a real public app, move uploads to S3, Cloudflare R2, Supabase Storage, or Render persistent disk.
- Render free web services can cold start after inactivity.
