import channel_finder
import scraper
import nlp_engine
import cv_layer
import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional


DEFAULT_SEARCH_TERMS = [
    "UK furniture upcycling",
    "UK woodworking restoration",
    "DIY upcycling UK",
    "UK furniture makeover",
]


@dataclass(frozen=True)
class PipelineResult:
    status: str
    output_path: str
    channels_discovered: int
    videos_collected: int
    candidates_scored: int
    rows_written: int
    message: str
    error: Optional[str] = None

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


def write_csv_atomically(final_df, output_path):
    """Replace the output only after a complete CSV has been written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        final_df.to_csv(temporary_path, index=False)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

def _run_pipeline_impl(
    search_terms=None,
    output_path="dremel_final_output.csv",
    discover_channels_fn=None,
    scrape_videos_fn=None,
    process_data_fn=None,
    visual_analysis_fn=None,
    progress=None,
):
    print("--- DREMEL PREDICTIVE TREND ENGINE ---")

    search_terms = list(search_terms or DEFAULT_SEARCH_TERMS)
    output_path = Path(output_path).resolve()
    discover_channels_fn = discover_channels_fn or discover_target_channels
    scrape_videos_fn = scrape_videos_fn or scrape_channel_videos
    process_data_fn = process_data_fn or nlp_engine.process_and_score_data
    visual_analysis_fn = visual_analysis_fn or cv_layer.run_visual_analysis
    progress = progress if progress is not None else {
        "channels_discovered": 0,
        "videos_collected": 0,
        "candidates_scored": 0,
        "rows_written": 0,
    }
    
    # 1. Automated Discovery
    print("Executing Automated UK Channel Discovery...")
    # Increased to pull more channels
    target_channels = discover_channels_fn(search_terms, max_results=5)
    progress["channels_discovered"] = len(target_channels)
    
    print(f"Successfully automated {len(target_channels)} target channels. Beginning scrape...")
    
    # 2. Scrape (Increased to max_results=10 to ensure a massive raw data pool)
    raw_data = scrape_videos_fn(target_channels, max_results=10)
    progress["videos_collected"] = len(raw_data)
    
    # 3. NLP & Velocity Math
    print("Running Semantic Parser...")
    structured_df = process_data_fn(raw_data)
    candidates_scored = len(structured_df)
    progress["candidates_scored"] = candidates_scored

    # PIPELINE OPTIMIZATION: Deduplicate to exactly 10 unique videos BEFORE running CV
    if not structured_df.empty:
        structured_df = structured_df.drop_duplicates(subset=["video_id"])
        structured_df = structured_df.head(10)

    if structured_df.empty or len(structured_df) == 0:
        print("\n[ERROR] Pipeline resulted in 0 matches. No videos mentioned a valid surface material.")
        return PipelineResult(
            status="empty",
            output_path=str(output_path),
            channels_discovered=len(target_channels),
            videos_collected=len(raw_data),
            candidates_scored=0,
            rows_written=0,
            message="Pipeline resulted in 0 matches.",
        )

    print(f"Isolated {len(structured_df)} unique, high-velocity surface trends.")

    # 4. Computer Vision Layer
    final_df = visual_analysis_fn(structured_df, top_n=10)
    final_df = normalize_output_frame(final_df)
    final_df = keep_top_unique_rows(final_df, limit=10)
    
    # 5. Save to static local file
    write_csv_atomically(final_df, output_path)
    progress["rows_written"] = len(final_df)
    print(f"\nPipeline Complete! {len(final_df)} unique videos saved to dremel_final_output.csv.")
    print("You may now launch the UI: 'streamlit run app.py'")
    return PipelineResult(
        status="success",
        output_path=str(output_path),
        channels_discovered=len(target_channels),
        videos_collected=len(raw_data),
        candidates_scored=candidates_scored,
        rows_written=len(final_df),
        message="Pipeline completed successfully.",
    )


def run_pipeline(
    search_terms=None,
    output_path="dremel_final_output.csv",
    discover_channels_fn=None,
    scrape_videos_fn=None,
    process_data_fn=None,
    visual_analysis_fn=None,
):
    """Run the pipeline and always return an inspectable status object."""
    resolved_output_path = Path(output_path).resolve()
    progress = {
        "channels_discovered": 0,
        "videos_collected": 0,
        "candidates_scored": 0,
        "rows_written": 0,
    }
    try:
        return _run_pipeline_impl(
            search_terms=search_terms,
            output_path=resolved_output_path,
            discover_channels_fn=discover_channels_fn,
            scrape_videos_fn=scrape_videos_fn,
            process_data_fn=process_data_fn,
            visual_analysis_fn=visual_analysis_fn,
            progress=progress,
        )
    except Exception as exc:
        message = f"Pipeline failed: {exc}"
        print(f"\n[ERROR] {message}")
        return PipelineResult(
            status="failed",
            output_path=str(resolved_output_path),
            channels_discovered=progress["channels_discovered"],
            videos_collected=progress["videos_collected"],
            candidates_scored=progress["candidates_scored"],
            rows_written=progress["rows_written"],
            message=message,
            error=str(exc),
        )

def main_cli():
    result = run_pipeline()
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())