import datetime
from get_youtube import fetch_youtube_feed
from get_bluesky import fetch_bluesky

latest_feed = {"items": [], "last_updated": None}


def fetch_feed():
    youtube_items = fetch_youtube_feed()
    bluesky_items = fetch_bluesky()
    f27_comments = [
        {
            "author": "Johnny Davies",
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it's inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
        },
        {
            "author": "Davy Johnson",
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it's inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
        },
        {
            "author": "Phillip Joanerooo",
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it's inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
        },
        {
            "author": "Janet Ballface",
            "platform": "f27",
            "author_profile_picture": "/default-profile.png",
            "text": "Lorum ipsom and foo bar and other stuff. New video just dropped about and badgers are great. ALSO: why I think it's inevitable now that Keir Starmer will be ousted and probably sooner rather than later. Check it…",
            "timestamp": "1756920114014",
        },
    ]

    combined = youtube_items + bluesky_items + f27_comments

    # Mutate in place so importers keep a live reference
    latest_feed["items"] = combined
    latest_feed["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return latest_feed
