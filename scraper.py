import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

transcript_api = YouTubeTranscriptApi()

def create_youtube_client(api_key=None):
    """Create a YouTube client only when collection is requested."""
    load_dotenv()
    resolved_key = api_key or os.getenv("YOUTUBE_API_KEY")
    if not resolved_key:
        raise ValueError("Missing YouTube API Key. Check your .env file.")
    return build("youtube", "v3", developerKey=resolved_key)


def get_channel_videos(channel_id, max_results=5, youtube_client=None):
    """Fetches video IDs, metrics, and thumbnail URLs."""
    print(f"Scraping Channel ID: {channel_id}...")
    
    youtube = youtube_client or create_youtube_client()
    channel_response = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    if not channel_response.get('items'):
        # Treat missing items as an API/channel error
        raise RuntimeError(f"YouTube API: no channel data returned for {channel_id}. Response: {channel_response}")
    uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    
    playlist_response = youtube.playlistItems().list(
        part="snippet", playlistId=uploads_playlist_id, maxResults=max_results
    ).execute()
    if not playlist_response.get('items'):
        raise RuntimeError(f"YouTube API: no playlist items for uploads playlist {uploads_playlist_id}. Response: {playlist_response}")
    
    video_data = []
    for item in playlist_response['items']:
        video_id = item['snippet']['resourceId']['videoId']
        title = item['snippet']['title']
        publish_date = item['snippet']['publishedAt']
        thumbnails = item['snippet'].get('thumbnails', {})
        thumbnail_url = thumbnails.get('high', thumbnails.get('default', {})).get('url', '')
        
        video_response = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
        if not video_response.get('items'):
            # Non-fatal for single videos; record with zeroed stats but log via exception
            stats = {}
            full_description = item['snippet'].get('description', '')
        else:
            video_item = video_response['items'][0]
            stats = video_item.get('statistics', {})
            full_description = video_item.get('snippet', {}).get('description', item['snippet'].get('description', ''))
        
        video_data.append({
            "video_id": video_id,
            "title": title,
            "description": full_description,
            "publish_date": publish_date,
            "views": int(stats.get('viewCount', 0)),
            "comments": int(stats.get('commentCount', 0)),
            "thumbnail_url": thumbnail_url
        })
    return video_data

def get_video_transcript(video_id):
    """Extracts spoken transcript."""
    try:
        transcript = transcript_api.fetch(video_id)
        formatter = TextFormatter()
        return formatter.format_transcript(transcript).replace("\n", " ")
    except Exception as exc:
        # Surface transcript errors to the caller so they can decide how to handle
        raise RuntimeError(f"Transcript error for video {video_id}: {exc}") from exc