from fastapi import HTTPException
from feedparser import parse

def get_podcast():
    feed = parse("https://pinecast.com/feed/aid-thompsin-other-disappointm")
    if feed.bozo:
        raise HTTPException(
            status_code=502,
            detail=f"RSS parse error: {feed.bozo_exception}"
        )
    return feed.entries
