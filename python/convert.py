#!/usr/bin/env python3
"""Converts stats.json to CSV files for analysis."""

import json
import csv
import sys
from pathlib import Path

# Level thresholds for kitchen coverage skill bands.
KITCHEN_BANDS = [
    ("Beginner", 0.0, 0.4),
    ("Intermediate", 0.4, 0.6),
    ("Advanced", 0.6, 0.8),
    ("Pro", 0.8, float('inf'))
]

SERVE_INDEX = 0
RETURN_INDEX = 1

# Helpers to find objects and calculate ratios.
def find_object(data_list, key):
    for obj in data_list:
        source = obj.get("payload", obj)
        if key in source:
            return source[key]
    return None

def safe_ratio(n, d):
    return round(n / d, 3) if d else None

def skill_band(value, thresholds):
    if value is None:
        return None
    for label, low, high in thresholds:
        if low <= value < high:
            return label
    return thresholds[-1][0]

def load_json_lines(file_path):
    """Load JSONL file with validation."""
    data_list = []
    line_num = 0
    try:
        with open(file_path, "r") as f:
            for line_num, line in enumerate(f, start=1):
                if line.strip():
                    try:
                        data_list.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"WARNING: Malformed JSON at line {line_num}: {e}")
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read file: {e}")
        sys.exit(1)
    
    if not data_list:
        print("ERROR: No valid JSON data found")
        sys.exit(1)
    
    return data_list

def extract_summary_metrics(stats, vid, output_dir):
    """Extract and write summary metrics CSV."""
    if not stats:
        print("WARNING: Summary stats not found. Skipping summary metrics CSV.")
        return 0
    
    players = stats.get("players", [])
    if not players:
        print("WARNING: No players found in stats")
        return 0
    
    rows = []
    for idx, player in enumerate(players):
        kitchen_arrival_percentage = player.get("kitchen_arrival_percentage", {})
        serving = kitchen_arrival_percentage.get("serving", {}).get("oneself", {})
        returning = kitchen_arrival_percentage.get("returning", {}).get("oneself", {})
        
        # Validate required fields
        if serving.get("denominator") is None and returning.get("denominator") is None:
            print(f"WARNING: Player {idx} has no kitchen coverage data (both serve and return missing)")
            continue
        
        serve_pct = safe_ratio(serving.get("numerator"), serving.get("denominator"))
        return_pct = safe_ratio(returning.get("numerator"), returning.get("denominator"))
        
        rows.append({
            "vid": vid,
            "player_id": idx,
            "serve_kitchen_coverage": serve_pct,
            "serve_kitchen_level": skill_band(serve_pct, KITCHEN_BANDS),
            "return_kitchen_coverage": return_pct,
            "return_kitchen_level": skill_band(return_pct, KITCHEN_BANDS)
        })
    
    if not rows:
        print("WARNING: No valid player data extracted")
        return 0
    
    csv_path = output_dir / "summary_metrics.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["vid", "player_id", "serve_kitchen_coverage", "serve_kitchen_level", "return_kitchen_coverage", "return_kitchen_level"])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Generated {csv_path} ({len(rows)} rows)")
    return len(rows)

def extract_shot_level_data(insights, vid, output_dir):
    """Extract and write shot-level data CSV."""
    if not insights:
        print("WARNING: Insights not found. Skipping shot-level data CSV.")
        return 0
    
    if not vid:
        print("WARNING: Video ID is missing. Cannot generate shot-level data.")
        return 0
    
    rallies = insights.get("rallies", [])
    if not rallies:
        print("WARNING: No rallies found in insights")
        return 0
    
    shot_rows = []
    skipped_shots = 0
    
    for rally_idx, rally in enumerate(rallies):
        shots = rally.get("shots", [])
        if not shots:
            print(f"WARNING: Rally {rally_idx} has no shots")
            continue
        
        for shot_idx, shot in enumerate(shots):
            ball_movement = shot.get("resulting_ball_movement", {})
            trajectory = ball_movement.get("trajectory", {})
            
            if not trajectory:
                skipped_shots += 1
                continue
            
            player_id = shot.get("player_id")
            if player_id is None:
                print(f"WARNING: Shot at rally {rally_idx}, shot {shot_idx} missing player_id")
            
            shot_role = "serve" if shot_idx == SERVE_INDEX else "return" if shot_idx == RETURN_INDEX else "rally"
            
            shot_rows.append({
                "vid": vid,
                "rally_idx": rally_idx,
                "shot_idx": shot_idx,
                "player_id": player_id,
                "shot_type": shot.get("shot_type", "unknown"),
                "shot_role": shot_role,
                "start_ms": shot.get("start_ms"),
                "end_ms": shot.get("end_ms"),
                "depth": ball_movement.get("distance"),
                "height_over_net": ball_movement.get("height_over_net")
            })
    
    if not shot_rows:
        print("WARNING: No valid shots with trajectory data found")
        return 0
    
    if skipped_shots > 0:
        print(f"INFO: Skipped {skipped_shots} shots with missing trajectory data")
    
    csv_path = output_dir / "shot_level_data.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["vid", "rally_idx", "shot_idx", "player_id", "shot_type", "shot_role", "start_ms", "end_ms", "depth", "height_over_net"])
        writer.writeheader()
        writer.writerows(shot_rows)
    
    print(f"Generated {csv_path} ({len(shot_rows)} rows)")
    return len(shot_rows)

def main():
    """Main entry point."""
    stats_json = Path(__file__).parent.parent / 'node' / "stats.json"
    output_dir = Path(__file__).parent
    
    # Load data
    data_list = load_json_lines(stats_json)
    
    # Extract top-level objects
    stats = find_object(data_list, "stats")
    insights = find_object(data_list, "insights")
    
    # Extract session info safely
    session = stats.get("session", {}) if stats else {}
    vid = session.get("vid")
    
    if not vid:
        print("WARNING: Video ID not found in session data")
    
    # Generate CSVs
    summary_count = extract_summary_metrics(stats, vid, output_dir)
    shot_count = extract_shot_level_data(insights, vid, output_dir)
    
    print(f"\nCSV generation complete: {summary_count + shot_count} total rows written")

if __name__ == "__main__":
    main()