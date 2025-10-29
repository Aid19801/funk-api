# app/feed.py
import datetime
from get_youtube import fetch_youtube_feed
from get_bluesky import fetch_bluesky

latest_feed = {"items": [], "last_updated": None}

def fetch_feed():
    global latest_feed
    print("Fetching feed...")
    youtube_items = fetch_youtube_feed()
    bluesky_items = fetch_bluesky()
    f27_comments = [
        {
            "author": "Johnny Davies", 
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it’s inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
         },
        {
            "author": "Davy Johnson", 
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it’s inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
         },
        {
            "author": "Phillip Joanerooo", 
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it’s inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
         },
        {
            "author": "Janet Ballface", 
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it’s inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
         },
    ]

    combined = youtube_items + bluesky_items + f27_comments

    latest_feed = {
        "items": combined,
        "last_updated": datetime.datetime.utcnow().isoformat(),
    }
    print("Feed updated at", latest_feed["last_updated"])
    return combined
