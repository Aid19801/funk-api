-- Poll feature setup
-- Run this against your PostgreSQL database

CREATE TABLE public.polls (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    question text NOT NULL,
    created_at timestamp DEFAULT now() NOT NULL
);

-- Stores the selectable options for each poll (up to 4)
CREATE TABLE public.poll_options (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    poll_id uuid NOT NULL REFERENCES public.polls(id) ON DELETE CASCADE,
    label text NOT NULL,
    display_order int NOT NULL DEFAULT 0,
    vote_count int NOT NULL DEFAULT 0
);

-- Tracks who voted on what, prevents double-voting
CREATE TABLE public.poll_votes (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    poll_id uuid NOT NULL REFERENCES public.polls(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    option_id uuid NOT NULL REFERENCES public.poll_options(id) ON DELETE CASCADE,
    created_at timestamp DEFAULT now() NOT NULL,
    UNIQUE (poll_id, user_id)
);

-- Initial poll (replace labels and question as needed)
-- Inserting a new poll row automatically becomes the active poll (latest by created_at)
WITH new_poll AS (
    INSERT INTO public.polls (question)
    VALUES ('blah blah')
    RETURNING id
)
INSERT INTO public.poll_options (poll_id, label, display_order)
SELECT id, label, display_order
FROM new_poll, (VALUES ('Yes', 0), ('No', 1)) AS opts(label, display_order);
