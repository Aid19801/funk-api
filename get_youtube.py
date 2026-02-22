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


def _fetch_stats_for_video_ids(video_ids: list) -> dict:
    """
    Batch-fetch like_count and comment_count for up to 50 video IDs in one API call.
    Returns a dict mapping video_id -> { like_count, comment_count }.
    """
    if not video_ids:
        return {}
    ids_param = ",".join(video_ids)
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=statistics"
        f"&id={ids_param}"
        f"&key={YOUTUBE_API_KEY}"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"Error fetching video stats: {e}")
        return {}

    result = {}
    for item in data.get("items", []):
        vid_id = item.get("id")
        stats = item.get("statistics", {})
        like_raw = stats.get("likeCount")
        comment_raw = stats.get("commentCount")
        result[vid_id] = {
            "like_count": int(like_raw) if like_raw is not None else None,
            "comment_count": int(comment_raw) if comment_raw is not None else None,
        }
    return result


def fetch_videos_from_playlist(playlist_id: str, max_results: int = 50):
    """
    Fetch the most recent videos from a YouTube playlist.
    Returns a list of dicts containing video metadata including like/comment counts.
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
            "like_count": None,
            "comment_count": None,
        })

    # Single batch API call to get stats for all videos
    video_ids = [v["id"] for v in videos]
    stats_map = _fetch_stats_for_video_ids(video_ids)
    for v in videos:
        s = stats_map.get(v["id"], {})
        v["like_count"] = s.get("like_count")
        v["comment_count"] = s.get("comment_count")

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


def fetch_single_video(video_id: str) -> dict | None:
    """
    Look up a single video by ID.
    Checks the in-memory cache first; falls back to a direct YouTube API call.
    """
    for item in youtube_cache["items"]:
        if item.get("id") == video_id:
            return item

    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics"
        f"&id={video_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        like_raw = stats.get("likeCount")
        comment_raw = stats.get("commentCount")
        return {
            "id": video_id,
            "title": snippet.get("title", ""),
            "platform": "youtube",
            "external_link": f"https://www.youtube.com/watch?v={video_id}",
            "text": snippet.get("description", ""),
            "image": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            "published_at": snippet.get("publishedAt"),
            "channel_title": snippet.get("channelTitle"),
            "channel_id": snippet.get("channelId"),
            "like_count": int(like_raw) if like_raw is not None else None,
            "comment_count": int(comment_raw) if comment_raw is not None else None,
        }
    except Exception as e:
        print(f"Error fetching single video {video_id}: {e}")
        return None


def fetch_video_details(video_id: str) -> dict:
    """
    Fetch like count and top-level comments for a single YouTube video.
    Returns { like_count, comments: [{ author, avatar, text, published_at, likes }] }
    """
    comments_url = (
        f"https://www.googleapis.com/youtube/v3/commentThreads"
        f"?part=snippet"
        f"&videoId={video_id}"
        f"&maxResults=20"
        f"&order=relevance"
        f"&key={YOUTUBE_API_KEY}"
    )

    stats_map = _fetch_stats_for_video_ids([video_id])
    like_count = stats_map.get(video_id, {}).get("like_count")

    comments = []
    try:
        res = requests.get(comments_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        for item in data.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            comments.append({
                "author": snippet.get("authorDisplayName", ""),
                "avatar": snippet.get("authorProfileImageUrl", ""),
                "text": snippet.get("textDisplay", ""),
                "published_at": snippet.get("publishedAt", ""),
                "likes": snippet.get("likeCount", 0),
            })
    except Exception as e:
        print(f"Error fetching video comments: {e}")

    return {"like_count": like_count, "comments": comments}
