import pandas as pd
import os
import subprocess
from collections import defaultdict
from datetime import date
import json
import time
import shutil
# -----------------------
# Configuration
# -----------------------
DRY_RUN = False
HERO_MODE="static" #Options: "video" (generate hero clips) or "static" (use a placeholder image for hero slide)
UPLOAD=False
CLEANUP_INTERMEDIATE=True
MAX_BEST_SHOT_CLIPS = 10
MAX_SERVE_CLIPS = 10
MAX_RETURN_CLIPS = 10
HERO_CLIP_NAME = "hero_clip.mp4"
HERO_THUMBNAIL_NAME = "hero_thumbnail.jpg"
HERO_PAD_MS = 300
SESSION_ID = date.today().isoformat()
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "nethriq_media")
DELIVERY_DIR = os.path.join(DATA_DIR, "delivery_staging")

INPUT_VIDEO = os.path.join(DATA_DIR, "test_vids" ,"test_video4.mp4")
BEST_SHOTS_CSV = os.path.join(DATA_DIR, "player_data", "player_best_shots.csv")
SERVE_RETURN_CSV = os.path.join(DATA_DIR, "player_data", "highlight_registry.csv")
PAD_MS = {
    "serve_context":   300,
    "return_context":  300,
    "result_context":  300,
    "highlight":       1000,  # Generic padding for quality highlights
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

def upload_video_to_drive(list_file, rclone_path, link_key):
    """
    Upload a video to Google Drive via rclone and get a shareable link.
    
    Args:
        list_file: Path to the ffmpeg concat list file
        rclone_path: Destination path on rclone remote (e.g., nethriq_drive:path/to/video.mp4)
        link_key: Descriptive key for storing the link (e.g., player_2_serve_context)
    
    Returns:
        tuple: (success: bool, shareable_link: str or None)
    """
    if DRY_RUN:
        return True, "https://drive.google.com/file/d/DRY_RUN_ID/view"
    
    try:
        # Setup ffmpeg command
        ffmpeg_cmd = [
            "ffmpeg", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-movflags", "frag_keyframe+empty_moov",
            "-f", "mp4", "pipe:1"
        ]
        
        # Setup rclone command with increased verbosity for progress
        rclone_cmd = [
            "rclone", "rcat", "-v", rclone_path
        ]
        
        print(" ".join(ffmpeg_cmd) + " | " + " ".join(rclone_cmd))
        print(f"⏳ Uploading {link_key}...")
        
        # Pipe ffmpeg output to rclone
        p1 = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p2 = subprocess.Popen(rclone_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p1.stdout:
            p1.stdout.close()
        
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        spinner_idx = 0
        
        # Wait for both processes with spinner
        while p2.poll() is None:
            print(f"\r  {spinner[spinner_idx % len(spinner)]} uploading...", end='', flush=True)
            spinner_idx += 1
            time.sleep(0.1)
        
        print("\r                           ", end='\r', flush=True)
        
        # Get any remaining output
        p1_returncode = p1.wait()
        p2_returncode = p2.returncode
        
        # Check for errors
        if p1_returncode != 0:
            p1_stderr = p1.stderr.read().decode('utf-8', errors='ignore') if p1.stderr else ""
            print(f"⚠️ ffmpeg error: {p1_stderr}")
            return False, None
        
        if p2_returncode != 0:
            p2_stderr = p2.stderr.read() if p2.stderr else ""
            print(f"⚠️ rclone error: {p2_stderr}")
            return False, None
        
        print(f"✅ Upload complete for {link_key}")
        
        # Get shareable link from rclone
        link_cmd = f"rclone link {rclone_path}"
        result = subprocess.run(link_cmd, shell=True, capture_output=True, text=True, check=True, timeout=30)
        shareable_link = result.stdout.strip()
        
        print(f"✅ Link for {link_key}: {shareable_link}")
        return True, shareable_link
        
    except subprocess.TimeoutExpired:
        print(f"⚠️ Timeout while getting link for {rclone_path}")
        return False, None
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Failed to get link for {rclone_path}: {e.stderr}")
        return False, None
    except Exception as e:
        print(f"⚠️ Unexpected error for {link_key}: {str(e)}")
        return False, None

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

def generate_hero_clips(best_shots_df: pd.DataFrame):
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

        hero_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "hero")
        os.makedirs(hero_dir, exist_ok=True)
        hero_path = os.path.join(hero_dir, HERO_CLIP_NAME)
        compressed_path = os.path.join(hero_dir, f"compressed_{HERO_CLIP_NAME}")
        raw_path = os.path.join(hero_dir, "hero_raw.mp4")
        thumbnail_path = os.path.join(hero_dir, HERO_THUMBNAIL_NAME)

        cmd = [
            "ffmpeg",
            "-ss", f"{clip_start/1000:.3f}",
            "-to", f"{clip_end/1000:.3f}",
            "-i", INPUT_VIDEO,
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
# Load highlights
# -----------------------
best_shots = pd.read_csv(BEST_SHOTS_CSV)
serve_return = pd.read_csv(SERVE_RETURN_CSV)

# -----------------------
# Concatenate reels
# -----------------------
def main():
    """Main orchestration function for generating and uploading highlight reels."""
    best_shot_reels = defaultdict(list)
    serve_return_clips = defaultdict(list)
    list_files = []  # Track concat list files for cleanup
    video_links = {}  # Store rclone links for PPT placeholders
    
    print(f"📋 Total best shot segments: {len(best_shots)}")
    print(f"📋 Total serve/return highlights: {len(serve_return)}")
    
    if len(best_shots) == 0 and len(serve_return) == 0:
        print("⚠️ No highlights found in CSVs!")
        return

    # Step 1: Generate a single hero clip per player for Slide 1 embedding
    generate_hero_clips(best_shots)
    
    # Generate best-shot clips (PB Vision) - limited to top N per player
    best_shots_sorted = best_shots.sort_values(["player_id", "start_ms"], kind="stable")
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
        clip_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "best_shots", "clips")

        os.makedirs(clip_dir, exist_ok=True)
        highlight_idx = f"ms{start_ms}_to_{end_ms}"
        clip_path = os.path.join(clip_dir, f"{highlight_idx}_{idx}.mp4")

        best_shot_reels[group_key].append((start_ms, clip_path, idx))

        cmd = [
            "ffmpeg",
            "-ss", f"{clip_start/1000:.3f}",
            "-to", f"{clip_end/1000:.3f}",
            "-i", INPUT_VIDEO,
            "-c", "copy",
            "-y",
            clip_path
        ]

        run_cmd(cmd)

    # Generate serve/return clips (player context reels) - limited to top N per type/player
    if len(serve_return) > 0:
        serve_return_filtered = serve_return[serve_return["highlight_type"].isin(["serve_context", "return_context"])]
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
            clip_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", highlight_type)
            os.makedirs(clip_dir, exist_ok=True)
            clip_path = os.path.join(clip_dir, f"{vid}_r{rally_idx}.mp4")

            serve_return_clips[group_key].append((rally_idx, clip_path))

            cmd = [
                "ffmpeg",
                "-ss", f"{clip_start/1000:.3f}",
                "-to", f"{clip_end/1000:.3f}",
                "-i", INPUT_VIDEO,
                "-c", "copy",
                "-y",
                clip_path
            ]

            run_cmd(cmd)
    # Concatenate and upload reels
    for player_id, segments in best_shot_reels.items():
        segments.sort(key=lambda x: x[0])
        clip_paths = [s[1] for s in segments]

        # Create per-player best-shots reel
        output_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "best_shots")
        os.makedirs(output_dir, exist_ok=True)
        list_file = os.path.join(output_dir, "best_shots.txt")
        output_video = os.path.join(output_dir, "best_shots.mp4")
        rclone_path = f"nethriq_drive:nethriq_media/players/{normalize_player_id(player_id)}/best_shots/best_shots.mp4"
        link_key = f"{normalize_player_id(player_id)}_best_shots"

        # Write concat file
        write_concat_file(clip_paths, list_file)
        list_files.append(list_file)

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

        # Upload video and get shareable link
        if UPLOAD:
            success, shareable_link = upload_video_to_drive(list_file, rclone_path, link_key)
            if success and shareable_link:
                video_links[link_key] = {
                    "link": shareable_link,
                    "status": "success"
                }
            else:
                video_links[link_key] = {
                    "link": None,
                    "status": "failure"
                }

            # Cleanup list file after upload
            if os.path.exists(list_file):
                os.remove(list_file)

    # Concatenate and upload serve/return reels
    for group_key, clips in serve_return_clips.items():
        clips.sort(key=lambda x: x[0])
        clip_paths = [c[1] for c in clips]

        highlight_type, player_id = group_key
        output_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", highlight_type)
        os.makedirs(output_dir, exist_ok=True)
        list_file = os.path.join(output_dir, f"{highlight_type}.txt")
        output_video = os.path.join(output_dir, f"{highlight_type}_highlights.mp4")
        rclone_path = f"nethriq_drive:nethriq_media/players/{normalize_player_id(player_id)}/sessions/{SESSION_ID}/highlights/{highlight_type}/{highlight_type}_highlights.mp4"
        link_key = f"{normalize_player_id(player_id)}_{highlight_type}"

        write_concat_file(clip_paths, list_file)
        list_files.append(list_file)

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

        if UPLOAD:
            success, shareable_link = upload_video_to_drive(list_file, rclone_path, link_key)
            if success and shareable_link:
                video_links[link_key] = {
                    "link": shareable_link,
                    "status": "success"
                }
            else:
                video_links[link_key] = {
                    "link": None,
                    "status": "failure"
                }

            if os.path.exists(list_file):
                os.remove(list_file)
    
    # Cleanup all videos and directories
    if CLEANUP_INTERMEDIATE:
        cleanup_all_videos(OUTPUT_DIR)
        cleanup_empty_directories(OUTPUT_DIR)

    # Build delivery staging layout from final reels
    stage_delivery_layout(OUTPUT_DIR, DELIVERY_DIR, SESSION_ID)

    # Save video links to JSON file for later use in PPT
    links_file = os.path.join(DATA_DIR, "video_links.json")
    with open(links_file, "w") as f:
        json.dump(video_links, f, indent=2)
    
    print(f"💾 Video links saved to {links_file}")
    print("✅ Highlight reels generated successfully.")

if __name__ == "__main__":
    print("🎬 Starting video clipper...")
    print(f"📊 Loading best shots from {BEST_SHOTS_CSV}")
    print(f"📊 Loading serve/return highlights from {SERVE_RETURN_CSV}")
    main()