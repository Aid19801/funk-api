-- Poll feature setup
-- Run this against your PostgreSQL database

CREATE TABLE public.polls (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    question text NOT NULL,
    yes_votes integer DEFAULT 0 NOT NULL,
    no_votes integer DEFAULT 0 NOT NULL,
    created_at timestamp DEFAULT now() NOT NULL
);

-- Tracks who voted on what, prevents double-voting
CREATE TABLE public.poll_votes (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    poll_id uuid NOT NULL REFERENCES public.polls(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    vote text NOT NULL CHECK (vote IN ('yes', 'no')),
    created_at timestamp DEFAULT now() NOT NULL,
    UNIQUE (poll_id, user_id)
);

-- Initial poll question
INSERT INTO public.polls (question)
VALUES ('Will Prince Andrew become a weird Alt Right Fake Christian by 2027?');
