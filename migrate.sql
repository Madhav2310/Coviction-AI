-- Migration: sector_tag -> sector_tags + add updated_at + FTS index

DO $$

BEGIN

    -- Migrate sector_tag -> sector_tags

    IF EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'sector_tag'

    ) THEN

        ALTER TABLE observations ADD COLUMN IF NOT EXISTS sector_tags JSONB DEFAULT '[]'::jsonb;

        UPDATE observations

            SET sector_tags = CASE

                WHEN sector_tag IS NOT NULL AND sector_tag != ''

                THEN jsonb_build_array(sector_tag)

                ELSE '[]'::jsonb

            END;

        ALTER TABLE observations DROP COLUMN IF EXISTS sector_tag;

        RAISE NOTICE 'Migrated sector_tag -> sector_tags';

    ELSE

        RAISE NOTICE 'sector_tags column already in place';

        IF NOT EXISTS (

            SELECT 1 FROM information_schema.columns

            WHERE table_name = 'observations' AND column_name = 'sector_tags'

        ) THEN

            ALTER TABLE observations ADD COLUMN sector_tags JSONB DEFAULT '[]'::jsonb;

            RAISE NOTICE 'Added sector_tags column';

        END IF;

    END IF;



    -- Add updated_at if missing

    IF NOT EXISTS (

        SELECT 1 FROM information_schema.columns

        WHERE table_name = 'observations' AND column_name = 'updated_at'

    ) THEN

        ALTER TABLE observations ADD COLUMN updated_at TIMESTAMPTZ;

        RAISE NOTICE 'Added updated_at column';

    ELSE

        RAISE NOTICE 'updated_at already exists';

    END IF;

END $$;



-- Create FTS index if not exists

CREATE INDEX IF NOT EXISTS idx_obs_fts ON observations USING GIN(

    to_tsvector('english',

        coalesce(title, '') || ' ' ||

        coalesce(body, '') || ' ' ||

        coalesce(voice_transcript, '') || ' ' ||

        coalesce(image_summary, '')

    )

);
