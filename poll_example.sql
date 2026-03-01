-- Create a new poll (this becomes the active poll automatically)
WITH new_poll AS (
    INSERT INTO public.polls (question)
    VALUES ('Who will replace Keir Starmer as Labour Leader?')
    RETURNING id
)
INSERT INTO public.poll_options (poll_id, label, display_order)
SELECT id, label, display_order
FROM new_poll, (VALUES
    ('Emily Thornberry', 0),
    ('Andy Burnham',     1),
    ('Wes Streeting',    2),
    ('Angela Rayner',    3)
) AS opts(label, display_order);
