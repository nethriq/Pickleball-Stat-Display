import pandas as pd
import os
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path
import shutil
# Configuration: These are now function parameters instead of module-level constants
# to support in-memory processing without environment variable race conditions
DRY_RUN = False
HERO_MODE = "static"  # Options: "video" (generate hero clips) or "static" (use a placeholder image for hero slide)
CLEANUP_INTERMEDIATE = True
MAX_BEST_SHOT_CLIPS = 10
MAX_SERVE_CLIPS = 10
MAX_RETURN_CLIPS = 10
HERO_CLIP_NAME = "hero_clip.mp4"
HERO_THUMBNAIL_NAME = "hero_thumbnail.jpg"
HERO_PAD_MS = 300
SESSION_ID = date.today().isoformat()

# Default paths (used only if called via legacy main())
BASE_DIR = os.path.dirname(__file__)
DEFAULT_JOB_DIR = os.path.join(BASE_DIR, "..", "data")
DEFAULT_VIDEO_URL = os.path.join(BASE_DIR, "data", "test_vids", "test_video3.mp4")

PAD_MS = {
    "serve_context": 300,
    "return_context": 300,
    "result_context": 300,
    "highlight": 1000,  # Generic padding for quality highlights
}

# -----------------------
# Helpers
# -----------------------
def normalize_player_id(raw_id):
    """Normalize player ID to standard format."""
    return f"player_{raw_id}"

def write_concat_file(clip_paths, outfile):
    with open(outfile, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{os.path.abspath(clip)}'\n")

def run_cmd(cmd):
    print(" ".join(cmd))
    if not DRY_RUN:
        subprocess.run(cmd, check=True)

def cleanup_all_videos(root_dir):
    """Recursively delete intermediate .mp4 files from root_dir, keeping final reels."""
    deleted = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith(".mp4"):
                continue

            is_final_best_shots = filename == "best_shots.mp4"
            is_final_highlights = filename.endswith("_highlights.mp4")
            is_hero_clip = filename == HERO_CLIP_NAME
            if is_final_best_shots or is_final_highlights or is_hero_clip:
                continue

            file_path = os.path.join(dirpath, filename)
            try:
                os.remove(file_path)
                deleted += 1
            except OSError:
                pass
    print(f"🧹 Deleted {deleted} intermediate video files")

def cleanup_empty_directories(root_dir):
    """Recursively remove empty directories from root_dir downwards."""
    removed = 0
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        if not dirnames and not filenames and dirpath != root_dir:
            try:
                os.rmdir(dirpath)
                removed += 1
            except OSError:
                pass
    if removed > 0:
        print(f"🧹 Deleted {removed} empty directories")

def compress_clip(input_path: str, output_path: str):
    """Compress a clip for lightweight PPT embedding."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.0",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "96k",
        output_path,
    ]
    subprocess.run(cmd, check=True)

def get_video_duration_seconds(video_path: str) -> float:
    """Return video duration in seconds, or 0.0 on failure."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0

def extract_midpoint_frame(video_path: str, output_path: str):
    """Extract a midpoint frame for a sharp hero thumbnail."""
    duration = get_video_duration_seconds(video_path)
    midpoint = max(0.0, duration / 2.0)
    cmd = [
        "ffmpeg",
        "-ss", f"{midpoint:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
    ]
    run_cmd(cmd)

def pick_best_shot_rows(best_shots_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank best shots per player and return the top row per player.
    Priority:
      1) short_description contains "exciting exchange" (case-insensitive)
      2) highest score
      3) longest rally by shot span (shot_end_idx - shot_start_idx)
      4) longest duration (end_ms - start_ms)
    """
    if best_shots_df.empty:
        return best_shots_df

    df = best_shots_df.copy()
    df["short_description"] = df["short_description"].fillna("")
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["shot_start_idx"] = pd.to_numeric(df["shot_start_idx"], errors="coerce").fillna(0)
    df["shot_end_idx"] = pd.to_numeric(df["shot_end_idx"], errors="coerce").fillna(0)
    df["start_ms"] = pd.to_numeric(df["start_ms"], errors="coerce").fillna(0)
    df["end_ms"] = pd.to_numeric(df["end_ms"], errors="coerce").fillna(0)

    df["is_exciting"] = df["short_description"].str.contains("exciting exchange", case=False)
    df["rally_span"] = (df["shot_end_idx"] - df["shot_start_idx"]).clip(lower=0)
    df["duration_ms"] = (df["end_ms"] - df["start_ms"]).clip(lower=0)

    df = df.sort_values(
        by=["player_id", "is_exciting", "score", "rally_span", "duration_ms"],
        ascending=[True, False, False, False, False],
        kind="stable",
    )

    return df.groupby("player_id", as_index=False).head(1)

def generate_hero_clips(best_shots_df: pd.DataFrame, output_dir: str, video_url: str):
    """Generate a single hero clip per player for PPT embedding."""
    hero_rows = pick_best_shot_rows(best_shots_df)
    if hero_rows.empty:
        return

    for _, row in hero_rows.iterrows():
        start_ms = row.get("start_ms")
        end_ms = row.get("end_ms")
        player_id = row.get("player_id")
        if pd.isna(start_ms) or pd.isna(end_ms) or pd.isna(player_id):
            continue

        start_ms = int(start_ms)
        end_ms = int(end_ms)
        player_id = int(float(player_id))

        clip_start = max(0, start_ms - HERO_PAD_MS)
        clip_end = end_ms + HERO_PAD_MS

        hero_dir = os.path.join(output_dir, "players", normalize_player_id(player_id), "hero")
        os.makedirs(hero_dir, exist_ok=True)
        hero_path = os.path.join(hero_dir, HERO_CLIP_NAME)
        compressed_path = os.path.join(hero_dir, f"compressed_{HERO_CLIP_NAME}")
        raw_path = os.path.join(hero_dir, "hero_raw.mp4")
        thumbnail_path = os.path.join(hero_dir, HERO_THUMBNAIL_NAME)

        cmd = [
            "ffmpeg",
            "-ss", f"{clip_start/1000:.3f}",
            "-to", f"{clip_end/1000:.3f}",
            "-i", video_url,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-y",
            raw_path,
        ]
        run_cmd(cmd)

        if HERO_MODE == "static":
            extract_midpoint_frame(raw_path, thumbnail_path)
            if os.path.exists(raw_path):
                os.remove(raw_path)
            continue

        compress_clip(raw_path, compressed_path)
        os.replace(compressed_path, hero_path)
        if os.path.exists(raw_path):
            os.remove(raw_path)

def stage_delivery_layout(output_dir, delivery_dir, session_id):
    """Create a delivery staging layout with copied final reels."""
    players_root = os.path.join(output_dir, "players")
    if not os.path.isdir(players_root):
        return

    for player_dir in os.listdir(players_root):
        if not player_dir.startswith("player_"):
            continue

        player_id = player_dir.split("_", 1)[1]
        delivery_player_dir = os.path.join(delivery_dir, f"Player_{player_id}")
        videos_dir = os.path.join(delivery_player_dir, "Videos")
        reports_dir = os.path.join(delivery_player_dir, "Reports")
        data_dir = os.path.join(delivery_player_dir, "Data")

        os.makedirs(videos_dir, exist_ok=True)
        os.makedirs(reports_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)

        best_shots_src = os.path.join(players_root, player_dir, "best_shots", "best_shots.mp4")
        if os.path.exists(best_shots_src):
            shutil.copy2(best_shots_src, os.path.join(videos_dir, "Best_Shots.mp4"))

        for highlight_type, dest_name in [
            ("serve_context", "Serve_Context.mp4"),
            ("return_context", "Return_Context.mp4"),
        ]:
            highlights_src = os.path.join(
                players_root,
                player_dir,
                "sessions",
                session_id,
                "highlights",
                highlight_type,
                f"{highlight_type}_highlights.mp4",
            )
            if os.path.exists(highlights_src):
                shutil.copy2(highlights_src, os.path.join(videos_dir, dest_name))

        report_path = os.path.join(reports_dir, "player_report.pptx")
        if not os.path.exists(report_path):
            with open(report_path, "wb"):
                pass

# -----------------------
# Load highlights (legacy: for backwards compatibility)
# -----------------------
best_shots = None
serve_return = None


def _load_highlight_csvs(job_directory):
    """Load best shots and serve/return CSVs from job directory."""
    global best_shots, serve_return
    
    data_dir = str(job_directory)
    best_shots_csv = os.path.join(data_dir, "player_data", "player_best_shots.csv")
    serve_return_csv = os.path.join(data_dir, "player_data", "highlight_registry.csv")
    
    best_shots = pd.read_csv(best_shots_csv)
    serve_return = pd.read_csv(serve_return_csv)


# -----------------------
# Concatenate reels
# -----------------------
def generate_highlights(job_directory, video_url, selected_player_index=None):
    """
    Generate highlight reels for all players.
    
    Args:
        job_directory: Path to job output directory (str or Path)
        video_url: URL or path to source video file
        selected_player_index: User's selected player (0-3), optional
    
    Returns:
        dict: Summary of generated highlights
    """
    print("🎬 Starting highlight generation...\n")
    
    job_dir = Path(job_directory)
    data_dir = str(job_dir)
    output_dir = os.path.join(data_dir, "nethriq_media")
    delivery_dir = os.path.join(data_dir, "delivery_staging")
    
    # Load CSV data from job directory
    best_shots_csv = os.path.join(data_dir, "player_data", "player_best_shots.csv")
    serve_return_csv = os.path.join(data_dir, "player_data", "highlight_registry.csv")
    
    best_shots_df = pd.read_csv(best_shots_csv)
    serve_return_df = pd.read_csv(serve_return_csv)

    # When a player is selected, generate only that player's assets.
    if selected_player_index is not None:
        try:
            selected_player_id = int(selected_player_index)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid selected_player_index: {selected_player_index}")

        best_shots_df = best_shots_df[
            pd.to_numeric(best_shots_df["player_id"], errors="coerce") == selected_player_id
        ]
        serve_return_df = serve_return_df[
            pd.to_numeric(serve_return_df["player_id"], errors="coerce") == selected_player_id
        ]
        print(f"🎯 Generating clips only for player_{selected_player_id}")
    
    if len(best_shots_df) == 0 and len(serve_return_df) == 0:
        if selected_player_index is not None:
            print(f"⚠️ No highlights found for player_{int(selected_player_index)}")
        else:
            print("⚠️ No highlights found in CSVs!")
        return

    # Initialize tracking dictionaries
    best_shot_reels = defaultdict(list)
    serve_return_clips = defaultdict(list)

    # Step 1: Generate a single hero clip per player for Slide 1 embedding
    generate_hero_clips(best_shots_df, output_dir, video_url)
    
    # Generate best-shot clips (PB Vision) - limited to top N per player
    best_shots_sorted = best_shots_df.sort_values(["player_id", "start_ms"], kind="stable")
    best_shots_limited = best_shots_sorted.groupby("player_id", as_index=False).head(MAX_BEST_SHOT_CLIPS)
    for idx, row in best_shots_limited.iterrows():
        start_ms = row.get("start_ms")
        end_ms = row.get("end_ms")
        player_id = row.get("player_id")
        if pd.isna(start_ms) or pd.isna(end_ms) or pd.isna(player_id):
            continue

        start_ms = int(start_ms)
        end_ms = int(end_ms)
        player_id = int(float(player_id))

        clip_start = max(0, start_ms) - PAD_MS["highlight"]
        clip_end = end_ms + PAD_MS["highlight"]

        group_key = player_id
        clip_dir = os.path.join(output_dir, "players", normalize_player_id(player_id), "best_shots", "clips")

        os.makedirs(clip_dir, exist_ok=True)
        highlight_idx = f"ms{start_ms}_to_{end_ms}"
        clip_path = os.path.join(clip_dir, f"{highlight_idx}_{idx}.mp4")

        best_shot_reels[group_key].append((start_ms, clip_path, idx))

        cmd = [
            "ffmpeg",
            "-ss", f"{clip_start/1000:.3f}",
            "-to", f"{clip_end/1000:.3f}",
            "-i", video_url,
            "-c", "copy",
            "-y",
            clip_path
        ]

        run_cmd(cmd)

    # Generate serve/return clips (player context reels) - limited to top N per type/player
    if len(serve_return_df) > 0:
        serve_return_filtered = serve_return_df[serve_return_df["highlight_type"].isin(["serve_context", "return_context"])]
        serve_limited = serve_return_filtered[serve_return_filtered['highlight_type'] == 'serve_context'].groupby('player_id', as_index=False).head(MAX_SERVE_CLIPS)
        return_limited = serve_return_filtered[serve_return_filtered['highlight_type'] == 'return_context'].groupby('player_id', as_index=False).head(MAX_RETURN_CLIPS)
        serve_return_filtered = pd.concat([serve_limited, return_limited], ignore_index=True)
        for _, row in serve_return_filtered.iterrows():
            start_ms = row["start_ms"]
            end_ms = row["end_ms"]
            highlight_type = row["highlight_type"]
            rally_idx = row["rally_idx"]
            player_id = row["player_id"]
            vid = row["vid"]

            pad = PAD_MS.get(highlight_type, 300)

            clip_start = max(0, start_ms - pad)
            clip_end = end_ms + pad

            group_key = (highlight_type, player_id)
            clip_dir = os.path.join(output_dir, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", highlight_type)
            os.makedirs(clip_dir, exist_ok=True)
            clip_path = os.path.join(clip_dir, f"{vid}_r{rally_idx}.mp4")

            serve_return_clips[group_key].append((rally_idx, clip_path))

            cmd = [
                "ffmpeg",
                "-ss", f"{clip_start/1000:.3f}",
                "-to", f"{clip_end/1000:.3f}",
                "-i", video_url,
                "-c", "copy",
                "-y",
                clip_path
            ]

            run_cmd(cmd)
    # Concatenate best shot reels
    for player_id, segments in best_shot_reels.items():
        segments.sort(key=lambda x: x[0])
        clip_paths = [s[1] for s in segments]

        # Create per-player best-shots reel
        best_shots_dir = os.path.join(output_dir, "players", normalize_player_id(player_id), "best_shots")
        os.makedirs(best_shots_dir, exist_ok=True)
        list_file = os.path.join(best_shots_dir, "best_shots.txt")
        output_video = os.path.join(best_shots_dir, "best_shots.mp4")

        # Write concat file
        write_concat_file(clip_paths, list_file)

        # Concatenate clips locally
        concat_cmd = [
            "ffmpeg", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-y",
            output_video
        ]
        run_cmd(concat_cmd)
        print(f"✅ Created {output_video}")

    # Concatenate serve/return reels
    for group_key, clips in serve_return_clips.items():
        clips.sort(key=lambda x: x[0])
        clip_paths = [c[1] for c in clips]

        highlight_type, player_id = group_key
        highlights_dir = os.path.join(output_dir, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", highlight_type)
        os.makedirs(highlights_dir, exist_ok=True)
        list_file = os.path.join(highlights_dir, f"{highlight_type}.txt")
        output_video = os.path.join(highlights_dir, f"{highlight_type}_highlights.mp4")

        write_concat_file(clip_paths, list_file)

        # Concatenate clips locally
        concat_cmd = [
            "ffmpeg", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-y",
            output_video
        ]
        run_cmd(concat_cmd)
        print(f"✅ Created {output_video}")
    
    # Cleanup all videos and directories
    if CLEANUP_INTERMEDIATE:
        cleanup_all_videos(output_dir)
        cleanup_empty_directories(output_dir)

    # Build delivery staging layout from final reels
    stage_delivery_layout(output_dir, delivery_dir, SESSION_ID)
    
    print("✅ Highlight reels generated successfully.")
    
    return {
        'status': 'success',
        'highlights_count': len(best_shots_df) + len(serve_return_df),
        'output_dir': str(output_dir)
    }


def main():
    """Legacy entry point for command-line execution."""
    job_dir = os.environ.get("JOB_DATA_DIR", DEFAULT_JOB_DIR)
    video_url = os.environ.get("SOURCE_VIDEO_URL", DEFAULT_VIDEO_URL)
    
    print("🎬 Starting video clipper...")
    print(f"📊 Loading best shots from {os.path.join(job_dir, 'player_data', 'player_best_shots.csv')}")
    print(f"📊 Loading serve/return highlights from {os.path.join(job_dir, 'player_data', 'highlight_registry.csv')}")
    
    result = generate_highlights(job_dir, video_url)
    return result


if __name__ == "__main__":
    main()