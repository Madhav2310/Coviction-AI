-- Coviction MVP Schema

-- Run via docker-compose init or manually.



CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE EXTENSION IF NOT EXISTS "pgcrypto";



-- Users

CREATE TABLE IF NOT EXISTS users (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    email TEXT UNIQUE NOT NULL

);



-- Daily Sessions

CREATE TABLE IF NOT EXISTS daily_sessions (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    session_date DATE NOT NULL DEFAULT CURRENT_DATE,

    name TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, session_date)

);



-- Observations

CREATE TABLE IF NOT EXISTS observations (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL REFERENCES daily_sessions(id) ON DELETE CASCADE,

    title TEXT NOT NULL,

    body TEXT DEFAULT '',

    sector_tags JSONB DEFAULT '[]'::jsonb,

    has_image BOOLEAN DEFAULT FALSE,

    has_voice BOOLEAN DEFAULT FALSE,

    voice_transcript TEXT DEFAULT '',

    image_summary TEXT DEFAULT '',

    created_at TIMESTAMPTZ DEFAULT NOW(),

    updated_at TIMESTAMPTZ

);



-- Daily Briefs

CREATE TABLE IF NOT EXISTS daily_briefs (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL REFERENCES daily_sessions(id) ON DELETE CASCADE,

    summary TEXT DEFAULT '',

    tags JSONB DEFAULT '[]'::jsonb,

    signals JSONB DEFAULT '[]'::jsonb,

    actions JSONB DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ DEFAULT NOW()

);



-- Indexes

CREATE INDEX IF NOT EXISTS idx_sessions_user_date ON daily_sessions(user_id, session_date);

CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_briefs_session ON daily_briefs(session_id, created_at DESC);



-- Full-text search GIN index on observations

CREATE INDEX IF NOT EXISTS idx_obs_fts ON observations USING GIN(

    to_tsvector('english',

        coalesce(title, '') || ' ' ||

        coalesce(body, '') || ' ' ||

        coalesce(voice_transcript, '') || ' ' ||

        coalesce(image_summary, '')

    )

);



-- Migration helpers (safe to re-run):

-- Rename old sector_tag column to sector_tags if it exists

DO $$

BEGIN

    IF EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'sector_tag'

    ) THEN

        -- Migrate string data to JSONB array

        ALTER TABLE observations ADD COLUMN IF NOT EXISTS sector_tags JSONB DEFAULT '[]'::jsonb;

        UPDATE observations

            SET sector_tags = CASE

                WHEN sector_tag IS NOT NULL AND sector_tag != ''

                THEN jsonb_build_array(sector_tag)

                ELSE '[]'::jsonb

            END

            WHERE sector_tags IS NULL OR sector_tags = '[]'::jsonb;

        ALTER TABLE observations DROP COLUMN IF EXISTS sector_tag;

    END IF;



    -- Add updated_at if missing

    IF NOT EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'updated_at'

    ) THEN

        ALTER TABLE observations ADD COLUMN updated_at TIMESTAMPTZ;

    END IF;



    -- Add voice_transcript and image_summary if missing (older schema)

    IF NOT EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'voice_transcript'

    ) THEN

        ALTER TABLE observations ADD COLUMN voice_transcript TEXT DEFAULT '';

    END IF;



    IF NOT EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'image_summary'

    ) THEN

        ALTER TABLE observations ADD COLUMN image_summary TEXT DEFAULT '';

    END IF;

END $$;
