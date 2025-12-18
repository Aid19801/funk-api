import os
import requests

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
AID_CHANNEL_ID = os.getenv("AID_CHANNEL_ID")
SUPER_CHANNEL_ID = os.getenv("SUPER_CHANNEL_ID")
GRAHAM_CHANNEL_ID = os.getenv("GRAHAM_CHANNEL_ID")


def get_uploads_playlist_id(channel_id: str) -> str:
    """Get the uploads playlist ID for a given YouTube channel."""
    url = (
        f"https://www.googleapis.com/youtube/v3/channels"
        f"?part=contentDetails"
        f"&id={channel_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    res = requests.get(url)
    res.raise_for_status()
    data = res.json()
    return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_videos_from_playlist(playlist_id: str, max_results: int = 5, include_live=False):
    """
    Fetch the most recent videos from a YouTube playlist.
    Optionally exclude live streams if include_live=False.
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

        # fallback if missing
        if not video_id:
            video_id = snippet.get("resourceId", {}).get("videoId")

        if not video_id or not snippet.get("title"):
            continue

        # optionally skip live or premiere titles
        title_lower = snippet["title"].lower()
        if not include_live and ("live" in title_lower or "premiere" in title_lower):
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


def fetch_youtube_feed():
    """
    Fetch recent YouTube videos from AID, Supertanskiii, and Graham.
    Ordered as:
      1. aid most recent
      2. supertanskiii most recent
      3. aid second most recent
      4. graham most recent (includes livestreams)
    """
    try:
        # Get each channel’s uploads playlist
        aid_uploads_id = get_uploads_playlist_id(AID_CHANNEL_ID)
        super_uploads_id = get_uploads_playlist_id(SUPER_CHANNEL_ID)
        graham_uploads_id = get_uploads_playlist_id(GRAHAM_CHANNEL_ID)

        # Fetch videos
        aid_videos = fetch_videos_from_playlist(aid_uploads_id, max_results=5, include_live=False)
        super_videos = fetch_videos_from_playlist(super_uploads_id, max_results=3, include_live=False)
        graham_videos = fetch_videos_from_playlist(graham_uploads_id, max_results=1, include_live=True)

        # Order results
        ordered = []
        if aid_videos:
            ordered.append(aid_videos[0])  # your most recent
        if super_videos:
            ordered.append(super_videos[0])  # Supertanskiii’s most recent
        if len(aid_videos) > 1:
            ordered.append(aid_videos[1])  # your second most recent
        if graham_videos:
            ordered.append(graham_videos[0])  # Graham’s most recent (likely livestream)

        return ordered

    except Exception as e:
        print(f"Error fetching YouTube feed: {e}")
        return []


if __name__ == "__main__":
    from pprint import pprint
    pprint(fetch_youtube_feed())
