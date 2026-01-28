import pandas as pd
import os
import subprocess
from collections import defaultdict
from datetime import date
import json
# -----------------------
# Configuration
# -----------------------
DRY_RUN = False
CLEANUP_INTERMEDIATE=True
SESSION_ID = date.today().isoformat()
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "nethriq_media")

INPUT_VIDEO = os.path.join(DATA_DIR, "test_video2.mp4")
HIGHLIGHT_CSV = os.path.join(DATA_DIR, "highlight_registry.csv")
PAD_MS = {
    "serve_context":   300,
    "return_context":  300,
    "third_shot_drop": 500,
    "smash_finish":    600,
    "long_rally":      0
}

HIGHLIGHT_DIR_MAP = {
    "serve_context": "serve",
    "return_context": "return"
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

def cleanup_intermediate_clips(clips_by_type):
    deleted = 0
    for clips in clips_by_type.values():
        for _, clip_path in clips:
            if os.path.exists(clip_path):
                os.remove(clip_path)
                deleted += 1
    print(f"🧹 Deleted {deleted} intermediate clips")

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
        
        # Setup rclone command
        rclone_cmd = [
            "rclone", "rcat", "--progress", rclone_path
        ]
        
        print(" ".join(ffmpeg_cmd) + " | " + " ".join(rclone_cmd))
        print(f"⏳ Uploading {link_key}... (this may take a while)")
        
        # Pipe ffmpeg output to rclone
        p1 = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=None)
        p2 = subprocess.Popen(rclone_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=None)
        p1.stdout.close()
        
        # Wait for both processes to complete
        p1_returncode = p1.wait()
        p2_returncode = p2.wait()
        
        # Check for errors
        if p1_returncode != 0:
            p1_stderr = p1.stderr.read().decode('utf-8', errors='ignore')
            print(f"⚠️ ffmpeg error: {p1_stderr}")
            return False, None
        
        if p2_returncode != 0:
            p2_stderr = p2.stderr.read().decode('utf-8', errors='ignore')
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

# -----------------------
# Load highlights
# -----------------------
highlights = pd.read_csv(HIGHLIGHT_CSV)

# -----------------------
# Concatenate reels
# -----------------------
def main():
    """Main orchestration function for generating and uploading highlight reels."""
    clips_by_type = defaultdict(list)
    list_files = []  # Track concat list files for cleanup
    video_links = {}  # Store rclone links for PPT placeholders
    
    print(f"📋 Total highlights to process: {len(highlights)}")
    
    if len(highlights) == 0:
        print("⚠️ No highlights found in CSV!")
        return
    
    # Generate clips
    for _, row in highlights.iterrows():
        start_ms = row["start_ms"]
        end_ms = row["end_ms"]
        highlight_type = row["highlight_type"]
        rally_idx = row["rally_idx"]
        player_id = row["player_id"]
        vid = row["vid"]

        pad = PAD_MS.get(highlight_type, 300)

        clip_start = max(0, start_ms - pad)
        clip_end = end_ms + pad

        # For serves and returns, group by player_id; for others, group by type only
        if highlight_type in ["serve_context", "return_context"]:
            group_key = (highlight_type, player_id)
            dir_name = HIGHLIGHT_DIR_MAP.get(highlight_type, highlight_type)
            clip_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", dir_name)
        else:
            group_key = (highlight_type,)
            clip_dir = OUTPUT_DIR
        
        os.makedirs(clip_dir, exist_ok=True)
        clip_path = os.path.join(clip_dir, highlight_type, f"{vid}_r{rally_idx}.mp4")
        os.makedirs(os.path.dirname(clip_path), exist_ok=True)
        
        clips_by_type[group_key].append((rally_idx, clip_path))

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
    for group_key, clips in clips_by_type.items():
        # sort by rally index
        clips.sort(key=lambda x: x[0])
        clip_paths = [c[1] for c in clips]

        # Generate output filename based on group key
        if isinstance(group_key, tuple) and len(group_key) == 2:
            # Player-specific (serve or return)
            highlight_type, player_id = group_key
            dir_name = HIGHLIGHT_DIR_MAP.get(highlight_type, highlight_type)
            output_dir = os.path.join(OUTPUT_DIR, "players", normalize_player_id(player_id), "sessions", SESSION_ID, "highlights", dir_name)
            os.makedirs(output_dir, exist_ok=True)
            list_file = os.path.join(output_dir, f"{highlight_type}.txt")
            rclone_path = f"nethriq_drive:nethriq_media/players/{normalize_player_id(player_id)}/sessions/{SESSION_ID}/highlights/{dir_name}/{highlight_type}_highlights.mp4"
            link_key = f"{normalize_player_id(player_id)}_{highlight_type}"
        else:
            # Type-specific (other highlights)
            highlight_type = group_key[0]
            list_file = os.path.join(OUTPUT_DIR, f"{highlight_type}.txt")
            rclone_path = f"nethriq_drive:nethriq_media/{highlight_type}_highlights.mp4"
            link_key = highlight_type

        # Write concat file and upload
        write_concat_file(clip_paths, list_file)
        list_files.append(list_file)

        # Upload video and get shareable link
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
    
    # Cleanup intermediate clips
    if CLEANUP_INTERMEDIATE:
        cleanup_intermediate_clips(clips_by_type)

    # Save video links to JSON file for later use in PPT
    links_file = os.path.join(OUTPUT_DIR, "video_links.json")
    with open(links_file, "w") as f:
        json.dump(video_links, f, indent=2)
    
    print(f"💾 Video links saved to {links_file}")
    print("✅ Highlight reels generated successfully.")

if __name__ == "__main__":
    print("🎬 Starting video clipper...")
    print(f"📊 Loading highlights from {HIGHLIGHT_CSV}")
    main()