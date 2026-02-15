import datetime
import requests

bluesky_cache = {"items": [], "last_updated": None}


def fetch_all_bluesky():
    """
    Fetch up to 100 posts from Bluesky, cache in memory.
    Called on startup and hourly by the scheduler.
    """
    handles = [
        "aidthompsin.bsky.social",
    ]

    all_posts = []

    for handle in handles:
        try:
            url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor={handle}&limit=100"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            for item in data.get("feed", []):
                post = item.get("post", {})
                record = post.get("record", {})

                text = record.get("text")
                if not text:
                    continue

                if item.get("reasonType") == "repost":
                    continue

                if record.get("reply"):
                    continue

                all_posts.append({
                    "title": "bluesky",
                    "platform": "bluesky",
                    "author": post.get("author", {}).get("handle", handle),
                    "text": text,
                    "timestamp": record.get("createdAt", ""),
                })

        except Exception as e:
            print(f"Error fetching Bluesky posts for {handle}: {e}")

    bluesky_cache["items"] = all_posts
    bluesky_cache["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return bluesky_cache
