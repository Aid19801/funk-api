-- Migration: yes/no poll → multi-option poll
-- Run against your live PostgreSQL database.
-- Wrapped in a transaction — rolls back entirely if anything fails.

BEGIN;

-- 1. Create the new poll_options table
CREATE TABLE public.poll_options (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    poll_id uuid NOT NULL REFERENCES public.polls(id) ON DELETE CASCADE,
    label text NOT NULL,
    display_order int NOT NULL DEFAULT 0,
    vote_count int NOT NULL DEFAULT 0
);

-- 2. Seed one Yes/No option row per existing poll,
--    carrying forward the current vote counts
INSERT INTO public.poll_options (poll_id, label, display_order, vote_count)
SELECT id, 'Yes', 0, yes_votes FROM public.polls
UNION ALL
SELECT id, 'No',  1, no_votes  FROM public.polls;

-- 3. Add option_id to poll_votes (nullable while we back-fill)
ALTER TABLE public.poll_votes
    ADD COLUMN option_id uuid REFERENCES public.poll_options(id) ON DELETE CASCADE;

-- 4. Back-fill option_id from the old vote text ('yes' → Yes row, 'no' → No row)
UPDATE public.poll_votes pv
SET option_id = po.id
FROM public.poll_options po
WHERE po.poll_id = pv.poll_id
  AND po.label = CASE pv.vote
                     WHEN 'yes' THEN 'Yes'
                     WHEN 'no'  THEN 'No'
                 END;

-- 5. Enforce NOT NULL now that every row has an option_id
ALTER TABLE public.poll_votes
    ALTER COLUMN option_id SET NOT NULL;

-- 6. Drop the old vote column (also removes its CHECK constraint)
ALTER TABLE public.poll_votes DROP COLUMN vote;

-- 7. Drop the old vote counters from polls
ALTER TABLE public.polls DROP COLUMN yes_votes;
ALTER TABLE public.polls DROP COLUMN no_votes;

COMMIT;
