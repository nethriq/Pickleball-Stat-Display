# Python Analytics

End-to-end pipeline for pickleball match analytics: data processing, highlight video generation, and player report creation.

## Overview

This module automates three key workflows:

1. **Data Processing** (`process_match_data.py`): Runs the unified processing pipeline that converts raw match data (`stats2.json`) into structured CSVs used elsewhere in the project.
2. **Highlight Generation** (`video_clipper.py`): Extracts highlight clips from match video, uploads to Google Drive, and generates shareable links.
3. **Report Generation** (`ppt_injector.py`): Creates personalized player reports with stats and embedded video links.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Configure rclone for Google Drive uploads:
```bash
rclone config
# Set up "nethriq_drive" as your Google Drive remote
```

## Workflow

### Step 1: Data Processing

```bash
python process_match_data.py
```

Runs the unified pipeline against `../data/stats2.json` (or `stats.json` where applicable) and produces the canonical CSVs consumed by subsequent steps:
- `player_averages.csv`: Player-level statistics (serve/return depth, height, kitchen coverage)
- `highlight_registry.csv`: Highlight event registry (start/end times, type, player, video ID). Contexts may overlap, but they represent 
                            different viewpoints
- `shot_level_data.csv`: Individual shot records with trajectory data
- `kitchen_role_stats.csv`: Role- and perspective-specific kitchen arrival counts and percentages

### Step 2: Highlight Video Generation

```bash
python video_clipper.py
```

Reads `highlight_registry.csv` and `../data/test_video2.mp4` to:
- Extract and concatenate highlight clips by type/player
- Upload compiled reels to Google Drive via rclone
- Generate shareable links saved to `../data/video_links.json`

**Configuration**: Adjust `PAD_MS`, `DRY_RUN`, and `CLEANUP_INTERMEDIATE` in the script as needed.

### Step 3: Player Report Generation

```bash
python ppt_injector.py
```

Injects data into PowerPoint template:
- Player stats from `player_averages.csv`
- Video links from `video_links.json`
- Generates `../data/player_report.pptx` with embedded hyperlinks

## Files

- **`process_match_data.py`**: Unified data processing pipeline (stats -> CSVs)
- **`video_clipper.py`**: Highlight extraction, concatenation, and Google Drive upload
- **`ppt_injector.py`**: PowerPoint report generation with stats and video links
- **`highlight_rules.yaml`**: Highlight detection rules configuration
- **`requirements.txt`**: Python dependencies

## Outputs

- `player_averages.csv`: Player statistics and skill grades
- `highlight_registry.csv`: Highlight event metadata
- `shot_level_data.csv`: Per-shot analytics
- `../data/video_links.json`: Shareable Google Drive video links
- `../data/player_report.pptx`: Final player report with embedded media

## Data Processing Details

### Summary Metrics

Extracts player-level statistics:
- Serve/return depth and height averages
- Kitchen arrival percentages (% of shots reaching kitchen)
- Skill grades: Beginner (0–40%), Intermediate (40–60%), Advanced (60–80%), Pro (80%+)

### Shot-Level Data

Per-shot records with:
- Ball trajectory (depth, height over net)
- Timing (start_ms, end_ms)
- Shot classification (serve, return, rally)
- Player and shot type metadata

## Architecture Notes

- **Intermediate Cleanup**: Video clipper removes intermediate clips and empty directories after upload
- **Video Links Storage**: JSON file stored in `data/` for persistence; output directory is transient
- **Hyperlink Injection**: PPT injector separates display text (token_map) from URLs (link_map) for clean architecture
