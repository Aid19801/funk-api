import os
import datetime
import requests

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
AID_CHANNEL_ID = os.getenv("AID_CHANNEL_ID")
AID_CLIPS_CHANNEL_ID = os.getenv("AID_CLIPS_CHANNEL_ID")

youtube_cache = {"items": [], "last_updated": None}


def get_uploads_playlist_id(channel_id: str) -> str:
    """Get the uploads playlist ID for a given YouTube channel."""
    url = (
        f"https://www.googleapis.com/youtube/v3/channels"
        f"?part=contentDetails"
        f"&id={channel_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_videos_from_playlist(playlist_id: str, max_results: int = 50):
    """
    Fetch the most recent videos from a YouTube playlist.
    Returns a list of dicts containing video metadata.
    """
    url = (
        f"https://www.googleapis.com/youtube/v3/playlistItems"
        f"?part=snippet,contentDetails"
        f"&maxResults={max_results}"
        f"&playlistId={playlist_id}"
        f"&key={YOUTUBE_API_KEY}"
    )

    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching playlist: {e}")
        return []

    data = res.json()
    items = data.get("items", [])

    videos = []
    for item in items:
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        video_id = content_details.get("videoId")

        if not video_id:
            video_id = snippet.get("resourceId", {}).get("videoId")

        if not video_id or not snippet.get("title"):
            continue

        videos.append({
            "id": video_id,
            "title": snippet["title"],
            "platform": "youtube",
            "external_link": f"https://www.youtube.com/watch?v={video_id}",
            "text": snippet.get("description", ""),
            "image": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            "published_at": snippet.get("publishedAt"),
            "channel_title": snippet.get("channelTitle"),
            "channel_id": snippet.get("channelId"),
        })

    return videos


def fetch_all_youtube():
    """
    Fetch 50 videos from AID main channel + 50 from clips channel.
    Combine, sort by date, and update the in-memory cache.
    Called on startup and every hour by the scheduler.
    """
    try:
        aid_playlist = get_uploads_playlist_id(AID_CHANNEL_ID)
        clips_playlist = get_uploads_playlist_id(AID_CLIPS_CHANNEL_ID)

        aid_videos = fetch_videos_from_playlist(aid_playlist, max_results=50)
        clips_videos = fetch_videos_from_playlist(clips_playlist, max_results=50)

        combined = aid_videos + clips_videos
        combined.sort(key=lambda v: v.get("published_at", ""), reverse=True)

        youtube_cache["items"] = combined
        youtube_cache["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception as e:
        print(f"Error fetching YouTube data: {e}")

    return youtube_cache


def fetch_youtube_feed():
    """Return a handful of recent videos for the homepage feed."""
    if youtube_cache["items"]:
        return youtube_cache["items"][:4]

    # Fallback: populate cache first if empty
    fetch_all_youtube()
    return youtube_cache["items"][:4]
