# Python Analytics

Converts pickleball match analytics data from `stats.json` into structured CSV files for analysis.

## Overview

This module processes JSON lines data from the Node server and extracts two datasets:

1. **Summary Metrics** (`summary_metrics.csv`): Player-level kitchen coverage statistics aggregated across the match.
2. **Shot-Level Data** (`shot_level_data.csv`): Individual shot records with ball trajectory and metadata.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python convert.py
```

This reads `../node/stats.json` and generates CSVs in the current directory.

## Files

- **`convert.py`**: Main conversion script. Extracts and validates data from JSONL input.
- **`requirements.txt`**: Python dependencies (numpy, pandas, requests, etc.).
- **`summary_metrics.csv`**: Output. Player stats with kitchen coverage percentages and skill bands.
- **`shot_level_data.csv`**: Output. Per-shot data with timing, depth, and height metrics.

## Data Processing

### Summary Metrics Extraction

Processes `stats.players[].kitchen_arrival_percentage` to compute:
- `serve_kitchen_coverage`: % of serves reaching the kitchen (0–1)
- `return_kitchen_coverage`: % of returns reaching the kitchen (0–1)
- Skill bands: Beginner (0–0.4), Intermediate (0.4–0.6), Advanced (0.6–0.8), Pro (0.8+)

### Shot-Level Extraction

Iterates through `insights.rallies[].shots[]` and extracts:
- Ball trajectory metadata (depth, height over net)
- Shot timing (start_ms, end_ms)
- Shot classification (serve, return, rally)
- Player ID and shot type

## Error Handling

- **Malformed JSON**: Logs line number and skips invalid records.
- **Missing fields**: Warnings logged for incomplete player or shot data.
- **Missing video ID**: Prevents shot-level CSV generation if `vid` is absent.
- **Empty datasets**: Skips CSV generation if no valid rows extracted.

## Dependencies

- **pandas**: Data manipulation
- **numpy**: Numerical operations
- **requests**: HTTP utilities
- **Other**: Standard library utilities (json, csv, pathlib)
