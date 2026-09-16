import channel_finder
import scraper
import nlp_engine
import cv_layer
import pandas as pd

def discover_target_channels(search_terms, max_results=3):
    discovered_data = []
    seen_channel_ids = set()

    for search_term in search_terms:
        try:
            results = channel_finder.discover_uk_diy_channels(search_term, max_results=max_results)
        except Exception as exc:
            print(f"Channel discovery failed for '{search_term}': {exc}")
            continue

        for channel in results:
            channel_id = channel["Channel ID"]
            if channel_id in seen_channel_ids:
                continue
            seen_channel_ids.add(channel_id)
            discovered_data.append(channel)

    if not discovered_data:
        raise RuntimeError("Automated channel discovery returned no channels. Try broader keywords or verify the YouTube API key.")

    return [channel["Channel ID"] for channel in discovered_data]

def scrape_channel_videos(target_channels, max_results=5):
    raw_data = []

    for channel in target_channels:
        try:
            videos = scraper.get_channel_videos(channel, max_results=max_results)
        except Exception as exc:
            print(f"Skipping channel {channel} due to scrape error: {exc}")
            continue

        for vid in videos:
            try:
                vid['transcript'] = scraper.get_video_transcript(vid['video_id'])
            except Exception as exc:
                vid['transcript'] = ""

            vid['content_text'] = " ".join(
                part for part in [
                    vid.get('transcript', ''),
                    vid.get('title', ''),
                    vid.get('description', ''),
                ]
                if part
            )
            raw_data.append(vid)

    return raw_data

def normalize_output_frame(final_df):
    expected_columns = [
        "video_id", "video_title", "thumbnail_url", "detected_verb",
        "detected_material", "action_pair", "velocity_score",
        "cv_color_hex", "cv_emotion",
    ]

    for column in expected_columns:
        if column not in final_df.columns:
            final_df[column] = pd.NA

    return final_df[expected_columns]

def keep_top_unique_rows(final_df, limit=10):
    if final_df.empty:
        return final_df
    # FIXED: Deduplicate strictly by video_id to enforce 100% video uniqueness
    deduped = final_df.drop_duplicates(subset=["video_id"])
    return deduped.head(limit)

def run_pipeline():
    print("--- DREMEL PREDICTIVE TREND ENGINE ---")
    
    # 1. Automated Discovery
    print("Executing Automated UK Channel Discovery...")
    search_terms = [
        "UK furniture upcycling",
        "UK woodworking restoration",
        "DIY upcycling UK",
        "UK furniture makeover",
    ]
    # Increased to pull more channels
    target_channels = discover_target_channels(search_terms, max_results=5) 
    
    print(f"Successfully automated {len(target_channels)} target channels. Beginning scrape...")
    
    # 2. Scrape (Increased to max_results=10 to ensure a massive raw data pool)
    raw_data = scrape_channel_videos(target_channels, max_results=10)
    
    # 3. NLP & Velocity Math
    print("Running Semantic Parser...")
    structured_df = nlp_engine.process_and_score_data(raw_data)

    # PIPELINE OPTIMIZATION: Deduplicate to exactly 10 unique videos BEFORE running CV
    if not structured_df.empty:
        structured_df = structured_df.drop_duplicates(subset=["video_id"])
        structured_df = structured_df.head(10)

    if structured_df.empty or len(structured_df) == 0:
        print("\n[ERROR] Pipeline resulted in 0 matches. No videos mentioned a valid surface material.")
        return

    print(f"Isolated {len(structured_df)} unique, high-velocity surface trends.")

    # 4. Computer Vision Layer
    final_df = cv_layer.run_visual_analysis(structured_df, top_n=10)
    final_df = normalize_output_frame(final_df)
    final_df = keep_top_unique_rows(final_df, limit=10)
    
    # 5. Save to static local file
    final_df.to_csv("dremel_final_output.csv", index=False)
    print(f"\nPipeline Complete! {len(final_df)} unique videos saved to dremel_final_output.csv.")
    print("You may now launch the UI: 'streamlit run app.py'")

if __name__ == "__main__":
    run_pipeline()