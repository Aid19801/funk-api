import os
import requests
from dotenv import load_dotenv

load_dotenv()

def fetch_bluesky():
    handles = [
        "aidthompsin.bsky.social",
        "supertanskiiii.bsky.social",
        "grahamdavidhughes.bsky.social",
    ]

    bluesky_posts = []

    for handle in handles:
        try:
            url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor={handle}&limit=5"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            feed_items = data.get("feed", [])

            for item in feed_items:
                post = item.get("post", {})
                record = post.get("record", {})

                # ✅ Skip if no text
                text = record.get("text")
                if not text:
                    continue

                # ✅ Skip reposts
                if item.get("reasonType") == "repost":
                    continue

                # ✅ Skip replies
                if record.get("reply"):
                    continue

                bluesky_posts.append({
                    "title": "bluesky",
                    "platform": "bluesky",
                    "author": post.get("author", {}).get("handle", handle),
                    "text": text,
                    "timestamp": record.get("createdAt", ""),
                })

        except Exception as e:
            print(f"Error fetching Bluesky posts for {handle}: {e}")

    return bluesky_posts
