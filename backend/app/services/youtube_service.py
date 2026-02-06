import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


def extract_channel_info_from_url(url: str) -> Dict[str, str]:
    """Extract channel identifier and type from URL."""
    patterns = [
        (r"youtube\.com/@([\w-]+)", "handle"),
        (r"youtube\.com/channel/([\w-]+)", "channel_id"),
        (r"youtube\.com/c/([\w-]+)", "custom"),
        (r"youtube\.com/user/([\w-]+)", "user"),
    ]
    for pattern, id_type in patterns:
        match = re.search(pattern, url)
        if match:
            return {"identifier": match.group(1), "type": id_type}
    raise ValueError("Could not extract channel identifier from URL")


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL."""
    patterns = [
        r"youtube\.com/watch\?v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/embed/([\w-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_transcript(video_id: str, max_retries: int = 3) -> Optional[str]:
    """Get transcript for a video with retry logic for rate limiting."""
    import time

    for attempt in range(max_retries):
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            # Combine all transcript segments
            full_transcript = " ".join(
                segment["text"] for segment in transcript_list
            )
            return full_transcript
        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception as e:
            error_str = str(e)
            # Check for rate limiting (429 error)
            if "429" in error_str or "Too Many Requests" in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 5s, 10s, 20s
                    wait_time = 5 * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
            return None
    return None


def get_channel_videos_mock(
    channel_identifier: str,
    identifier_type: str,
    months_back: int = 12
) -> List[Dict[str, Any]]:
    """
    Mock function to get channel videos.
    In production, this would use the YouTube Data API.
    For now, returns empty list (real implementation needs API key).
    """
    # TODO: Implement using YouTube Data API
    # This requires a valid YOUTUBE_API_KEY
    return []


def get_channel_metadata_mock(
    channel_identifier: str,
    identifier_type: str
) -> Optional[Dict[str, Any]]:
    """
    Mock function to get channel metadata.
    In production, this would use the YouTube Data API.
    """
    # TODO: Implement using YouTube Data API
    return {
        "channel_id": f"{identifier_type}:{channel_identifier}",
        "name": channel_identifier,
        "thumbnail_url": None,
    }


# Production implementation using YouTube Data API
def get_channel_videos_with_api(
    api_key: str,
    channel_id: str,
    months_back: int = 12
) -> List[Dict[str, Any]]:
    """
    Get channel videos using YouTube Data API.
    Requires valid API key.
    """
    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", developerKey=api_key)

        # Calculate date cutoff
        cutoff_date = datetime.utcnow() - timedelta(days=months_back * 30)
        cutoff_str = cutoff_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        videos = []
        next_page_token = None

        while True:
            # Search for videos from this channel
            request = youtube.search().list(
                part="snippet",
                channelId=channel_id,
                maxResults=50,
                order="date",
                publishedAfter=cutoff_str,
                type="video",
                pageToken=next_page_token,
            )
            response = request.execute()

            for item in response.get("items", []):
                videos.append({
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return videos
    except Exception as e:
        raise ValueError(f"Failed to fetch videos: {str(e)}")


def resolve_channel_id(api_key: str, identifier: str, id_type: str) -> str:
    """Resolve channel handle/custom URL to channel ID."""
    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", developerKey=api_key)

        if id_type == "channel_id":
            return identifier

        if id_type == "handle":
            # Search for channel by handle
            request = youtube.search().list(
                part="snippet",
                q=f"@{identifier}",
                type="channel",
                maxResults=1,
            )
            response = request.execute()
            items = response.get("items", [])
            if items:
                return items[0]["snippet"]["channelId"]

        if id_type in ["custom", "user"]:
            # Search for channel
            request = youtube.search().list(
                part="snippet",
                q=identifier,
                type="channel",
                maxResults=1,
            )
            response = request.execute()
            items = response.get("items", [])
            if items:
                return items[0]["snippet"]["channelId"]

        raise ValueError(f"Could not resolve channel: {identifier}")
    except Exception as e:
        raise ValueError(f"Failed to resolve channel: {str(e)}")


def get_channel_metadata(api_key: str, channel_id: str) -> Dict[str, Any]:
    """Get channel metadata using YouTube Data API."""
    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", developerKey=api_key)

        request = youtube.channels().list(
            part="snippet,statistics",
            id=channel_id,
        )
        response = request.execute()

        items = response.get("items", [])
        if not items:
            raise ValueError("Channel not found")

        channel = items[0]
        snippet = channel.get("snippet", {})

        return {
            "channel_id": channel_id,
            "name": snippet.get("title", "Unknown"),
            "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "description": snippet.get("description"),
        }
    except Exception as e:
        raise ValueError(f"Failed to fetch channel metadata: {str(e)}")
