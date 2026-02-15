from get_youtube import youtube_cache
from get_bluesky import bluesky_cache
from db import get_db

FEED_PER_SOURCE = 10
FEED_MAX_PAGES = 10


def build_feed_page(page: int):
    """
    Build a single feed page by combining:
      - 10 youtube items (from cache)
      - 10 bluesky items (from cache)
      - up to 10 comments (live from DB)
    """
    offset = (page - 1) * FEED_PER_SOURCE

    youtube_slice = youtube_cache["items"][offset:offset + FEED_PER_SOURCE]
    bluesky_slice = bluesky_cache["items"][offset:offset + FEED_PER_SOURCE]

    # Comments come live from DB so they're always fresh
    comments = []
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT id, user_id, content, created_at, author_name,
                   author_profile_picture, target_id
            FROM comments
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (FEED_PER_SOURCE, offset),
        )
        comments = [
            {
                "id": row[0],
                "user_id": row[1],
                "text": row[2],
                "timestamp": row[3].isoformat(),
                "author": row[4],
                "author_profile_picture": row[5],
                "target_id": row[6],
                "platform": "f27",
            }
            for row in cur.fetchall()
        ]

    items = youtube_slice + bluesky_slice + comments

    return {
        "items": items,
        "page": page,
        "max_pages": FEED_MAX_PAGES,
    }
