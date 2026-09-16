import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
import pandas as pd

load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not YOUTUBE_API_KEY:
    raise ValueError("Missing YouTube API Key.")

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

def discover_uk_diy_channels(keywords, max_results=5):
    """
    Searches YouTube for specific keywords, filtering by region (UK)
    and returning a list of automated Channel IDs.
    """
    print(f"Hunting for channels using keywords: '{keywords}'...")
    
    # Execute the Search API Call
    search_response = youtube.search().list(
        q=keywords,
        part="snippet",
        type="channel",         # We only want entire channels, not single videos
        relevanceLanguage="en", # English language
        regionCode="GB",        # Crucial: Restricts search focus to Great Britain
        maxResults=max_results
    ).execute()
    
    discovered_channels = []
    
    for item in search_response.get('items', []):
        channel_id = item['snippet']['channelId']
        channel_title = item['snippet']['title']
        description = item['snippet']['description']
        
        discovered_channels.append({
            "Channel Name": channel_title,
            "Channel ID": channel_id,
            "Description Snippet": description[:100] + "..."
        })
        
    return discovered_channels

# ==========================================
# Testing the Automation 
# ==========================================
if __name__ == "__main__":
    target_search = "UK DIY furniture upcycle"
    
    results = discover_uk_diy_channels(target_search, max_results=3)
    df = pd.DataFrame(results)
    
    print("\n--- Discovered Channel IDs ---")
    print(df)