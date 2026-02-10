#!/usr/bin/env python3
"""
Unified match data processing pipeline.
Converts stats.json → shot/kitchen CSVs → highlight registry → player averages.
"""

import json
import csv
import pandas as pd
import sys
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================
SERVE_INDEX = 0
RETURN_INDEX = 1

SERVE_DEPTH_BANDS = [(2, "Pro"), (4, "Advanced"), (6, "Intermediate")]
HEIGHT_BANDS = [(2, "Pro"), (2.5, "Advanced"), (3, "Intermediate")]
SERVE_KITCHEN_BANDS = [(0.9, "Pro"), (0.7, "Advanced"), (0.5, "Intermediate")]
RETURN_KITCHEN_BANDS = [(0.95, "Pro"), (0.85, "Advanced"), (0.7, "Intermediate")]

# ============================================================================
# Helper Functions
# ============================================================================
def find_object(data_list, key):
    """Find object with key in data list."""
    for obj in data_list:
        source = obj.get("payload", obj)
        if key in source:
            return source[key]
    return None

def safe_ratio(n, d):
    """Calculate ratio safely."""
    return round(n / d, 3) if d else None

def collect_all_rallies(data_list):
    rallies = []
    for obj in data_list:
        payload = obj.get("payload", {})
        insights = payload.get("insights")
        if insights and "rallies" in insights:
            rallies.extend(insights["rallies"])
    return rallies

def load_json_lines(file_path):
    """Load JSONL file with validation."""
    data_list = []
    try:
        with open(file_path, "r") as f:
            for line_num, line in enumerate(f, start=1):
                if line.strip():
                    try:
                        data_list.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Malformed JSON at line {line_num}: {e}")
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        sys.exit(1)
    
    if not data_list:
        print("❌ No valid JSON data found")
        sys.exit(1)
    
    return data_list

def grade_inverse(value, bands):
    """Grade metric where lower values are better (depth, height)."""
    if pd.isna(value):
        return None
    for upper, grade in bands:
        if value <= upper:
            return grade
    return "Beginner"

def grade_direct(value, bands):
    """Grade metric where higher values are better (kitchen %)."""
    if pd.isna(value):
        return None
    for lower, grade in bands:
        if value >= lower:
            return grade
    return "Beginner"

def score_shot(shot):
    score = 0.0

    quality = shot.get("quality", {}).get("overall")
    if quality is not None:
        score += quality * 2.0

    if shot.get("winner_type") == "winner":
        score += 3.0

    wt = shot.get("winner_type")
    if wt in {"winner", "clean"}:
        score += 3.0

    elif wt == "forced_fault":
        score += 2.0


    if shot.get("is_final"):
        score += 1.0

    if shot.get("is_passing"):
        score += 0.5

    if shot.get("is_volley"):
        score += 0.5

    if shot.get("vertical_type") in {"dig", "half_volley"}:
        score += 0.3

    return score

def classify_shot(score):
    if score >= 3.0:
        return "elite"
    if score >= 2.0:
        return "pressure"
    if score >= 1.2:
        return "context"
    return "discard"


# ============================================================================
# Stage 1: Extract Kitchen Role Stats
# ============================================================================
def extract_kitchen_role_stats(insights, vid, output_dir):
    """Extract kitchen arrival percentages by role and perspective."""
    print("📊 Stage 1: Extracting kitchen role stats...")

    players = insights.get("player_data", []) if insights else []
    rows = []

    for idx, player in enumerate(players):
        if not isinstance(player, dict):
            continue
        kap = player.get("kitchen_arrival_percentage", {})
        player_id = idx
        team_id = player.get("team", idx)
        for role_key, role_data in kap.items():
            role = "returning" if role_key == "receiving" else role_key
            for perspective in ("oneself", "partner"):
                ctx = role_data.get(perspective, {})
                num = ctx.get("numerator")
                den = ctx.get("denominator")
                pct = safe_ratio(num, den) if den else None

                if pct is None:
                    continue
                rows.append({
                    "vid": vid,
                    "player_id": player_id,
                    "team_id": team_id,
                    "role": role,
                    "perspective": perspective,
                    "kitchen_arrivals": num,
                    "opportunities": den,
                    "kitchen_pct": pct,
                })

    csv_path = output_dir / "kitchen_role_stats.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["vid", "player_id", "team_id", "role", "perspective", "kitchen_arrivals", "opportunities", "kitchen_pct"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Generated kitchen_role_stats.csv ({len(rows)} rows)")
    return pd.DataFrame(rows)

# ============================================================================
# Stage 2: Extract Shot-Level Data
# ============================================================================
def extract_shot_level_data(insights, vid, output_dir):
    """Extract shot-level trajectory data."""
    print("📊 Stage 2: Extracting shot-level data...")
    
    if not insights or not vid:
        print("⚠️ Missing insights or video ID")
        return pd.DataFrame()
    
    rallies = insights.get("rallies", [])
    shot_rows = []
    skipped = 0
    
    for rally_idx, rally in enumerate(rallies):
        shots = rally.get("shots", [])
        
        # Find serve index by checking tags
        serve_idx = None
        for idx, shot in enumerate(shots):
            tags = shot.get("tags", {})
            if any("type;serve" in key for key in tags.keys()):
                serve_idx = idx
                break
        
        for shot_idx, shot in enumerate(shots):
            ball_movement = shot.get("resulting_ball_movement", {})
            if not ball_movement.get("trajectory"):
                skipped += 1
                continue

            # Determine shot role based on serve position
            if serve_idx is not None:
                if shot_idx == serve_idx:
                    shot_role = "serve"
                elif shot_idx == serve_idx + 1:
                    shot_role = "return"
                else:
                    shot_role = "rally"
            else:
                # Fallback to old method if no serve found
                shot_role = "serve" if shot_idx == SERVE_INDEX else "return" if shot_idx == RETURN_INDEX else "rally"
            
            shot_rows.append({
                "vid": vid,
                "rally_idx": rally_idx,
                "shot_idx": shot_idx,
                "player_id": shot.get("player_id"),
                "shot_type": shot.get("shot_type", "unknown"),
                "shot_role": shot_role,
                "start_ms": shot.get("start_ms"),
                "end_ms": shot.get("end_ms"),
                "depth": ball_movement.get("distance"),
                "height_over_net": ball_movement.get("height_over_net"),
                "quality": shot.get("quality", {}).get("overall") if isinstance(shot.get("quality"), dict) else None,
                "advantage_scale": shot.get("advantage_scale", [None])[shot.get("player_id")] if isinstance(shot.get("advantage_scale"), list) and shot.get("player_id") is not None else None,
                "is_final": shot.get("is_final", False),
                "speed": ball_movement.get("speed"),
                "is_volleyed": shot.get("is_volley", False)
            })

    csv_path = output_dir / "shot_level_data.csv"
    with open(csv_path, "w", newline="") as f:
        fieldnames = ["vid", "rally_idx", "shot_idx", "player_id", "shot_type", "shot_role", "start_ms", "end_ms", 
                      "depth", "height_over_net", "quality", "advantage_scale", "is_final", "speed", "is_volleyed"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(shot_rows)

    print(f"✅ Generated shot_level_data.csv ({len(shot_rows)} rows, skipped {skipped})")
    return pd.DataFrame(shot_rows)

# ============================================================================
# Stage 3: Generate Serve and receive contexts
# ============================================================================
def generate_serves_and_receives(shot_df, output_dir):
    """Generate serve/return context highlights from shot-level data."""
    print("📊 Stage 3: Generating serves and receives...")
    
    sr_list = []
    grouped = shot_df.groupby(['vid', 'rally_idx'], sort=False)
    
    for (vid, rally_idx), rally in grouped:
        rally = rally.sort_values('shot_idx')
        
        # Find serve shot
        serve_shots = rally[rally['shot_role'] == 'serve']
        if serve_shots.empty:
            continue
        
        serve_row = serve_shots.iloc[0]
        
        # Serve context: serve + return (if exists)
        return_shots = rally[rally['shot_role'] == 'return']
        end_row = return_shots.iloc[0] if not return_shots.empty else serve_row
        
        sr_list.append({
            'vid': vid,
            'rally_idx': rally_idx,
            'highlight_type': 'serve_context',
            'start_ms': serve_row['start_ms'],
            'end_ms': end_row['end_ms'],
            'player_id': serve_row['player_id'],
            'start_shot_idx': serve_row['shot_idx'],
            'end_shot_idx': end_row['shot_idx'],
        })
        
        # Return context: serve + return + next 2 rally shots (if they exist)
        rally_shots = rally[rally['shot_role'] == 'rally'].head(2)
        
        if not rally_shots.empty:
            end_row = rally_shots.iloc[-1]
        elif not return_shots.empty:
            end_row = return_shots.iloc[0]
        else:
            end_row = serve_row
        
        sr_list.append({
            'vid': vid,
            'rally_idx': rally_idx,
            'highlight_type': 'return_context',
            'start_ms': serve_row['start_ms'],
            'end_ms': end_row['end_ms'],
            'player_id': serve_row['player_id'],
            'start_shot_idx': serve_row['shot_idx'],
            'end_shot_idx': end_row['shot_idx'],
        })
        
    
    sr_df = pd.DataFrame(sr_list).sort_values(['vid', 'rally_idx', 'start_ms'])
    csv_path = output_dir / "highlight_registry.csv"
    sr_df.to_csv(csv_path, index=False)
    
    print(f"✅ Generated serves_and_receives.csv ({len(sr_df)} rows)")
    return sr_df

# ============================================================================
# Stage 4: Generate Player Best Shots Compilation (with context)
# ============================================================================
def generate_player_best_shots(insights, vid,output_dir, top_n=50):
    """
    Uses the data stored in JSON returned by PB Vision API to store start and end times of clips.
    If highlights structure exists in insights, uses that; otherwise falls back to manual scoring.
    Returns a data frame.
    """
    print("📊 Stage 4: Generating player best-shot registry...")

    if not insights:
        print("⚠️ Missing insights")
        return pd.DataFrame()

    if not vid:
        print("❌ Missing vid for best-shot clips")
        sys.exit(1)
    
    # Check if PB Vision highlights exist
    highlights = insights.get("highlights", [])
    
    if highlights:
        print(f"✨ Using PB Vision highlights ({len(highlights)} found)")
        rows = []
        rallies = insights.get("rallies", [])
        
        for highlight in highlights:
            rally_idx = highlight.get("rally_idx")
            shot_start_idx = highlight.get("shot_start_idx")
            shot_end_idx = highlight.get("shot_end_idx")
            
            # Find player_id from the rally's shots
            player_id = None
            if rally_idx is not None and rally_idx < len(rallies):
                rally = rallies[rally_idx]
                shots = rally.get("shots", [])
                if shot_start_idx is not None and shot_start_idx < len(shots):
                    player_id = shots[shot_start_idx].get("player_id")
            
            rows.append({
                "vid": vid,
                "player_id": player_id,
                "rally_idx": rally_idx,
                "shot_start_idx": shot_start_idx,
                "shot_end_idx": shot_end_idx,
                "start_ms": highlight.get("s"),
                "end_ms": highlight.get("e"),
                "kind": highlight.get("kind"),
                "score": highlight.get("score"),
                "rally_ending": highlight.get("rally_ending"),
                "short_description": highlight.get("short_description"),
            })
        
        best_df = pd.DataFrame(rows)
        
        # Sort by player and score
        if not best_df.empty:
            best_df = best_df.sort_values(
                ["player_id", "score", "start_ms"],
                ascending=[True, False, True],
            )
            best_df = best_df.groupby("player_id", as_index=False).head(top_n)
            
            score_stats = best_df["score"].describe()
            print(score_stats)
            print(f"Max score: {best_df['score'].max()}")
            print(f"Median score: {best_df['score'].median()}")
    else:
        print("⚠️ No PB Vision highlights found, using fallback scoring method")
        rows = []
        rallies = insights.get("rallies", [])
        for rally_idx, rally in enumerate(rallies):
            shots = rally.get("shots", [])
            for shot_idx, shot in enumerate(shots):
                quality_overall = shot.get("quality", {}).get("overall")
                score = score_shot(shot)
                start_ms = shot.get("start_ms")
                end_ms = shot.get("end_ms")

                rows.append({
                    "vid": vid,
                    "player_id": shot.get("player_id"),
                    "rally_idx": rally_idx,
                    "shot_idx": shot_idx,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "winner_type": shot.get("winner_type"),
                    "quality_overall": quality_overall,
                    "score": score,
                    "tier": classify_shot(score),
                    "shot_raw": shot,
                })

        if not rows:
            print("⚠️ No shots found in insights")
            empty_cols = [
                "vid",
                "player_id",
                "rally_idx",
                "shot_idx",
                "start_ms",
                "end_ms",
                "winner_type",
                "quality_overall",
                "score",
                "tier",
            ]
            best_df = pd.DataFrame(columns=empty_cols)
        else:
            best_df = pd.DataFrame(rows)
            best_df = best_df.sort_values(
                ["player_id", "score", "start_ms"],
                ascending=[True, False, True],
            )
            best_df = best_df.groupby("player_id", as_index=False).head(top_n)

            score_stats = best_df["score"].describe()
            print(score_stats)
            print(f"Max score: {best_df['score'].max()}")
            print(f"Median score: {best_df['score'].median()}")

            top_shot_raw = best_df.iloc[0]["shot_raw"] if not best_df.empty else None
            if top_shot_raw is not None:
                print("Top-ranked shot JSON:")
                print(json.dumps(top_shot_raw, indent=2, ensure_ascii=True))

        if "shot_raw" in best_df.columns:
            best_df = best_df.drop(columns=["shot_raw"])

    csv_path = output_dir / "player_best_shots.csv"
    best_df.to_csv(csv_path, index=False)

    print(f"✅ Generated player_best_shots.csv ({len(best_df)} rows)")
    return best_df

# ============================================================================
# Stage 5: Calculate Player Averages & Grades
# ============================================================================
def calculate_player_averages(shot_df, kitchen_df, output_dir):
    """Calculate player-level statistics and assign grades."""
    print("📊 Stage 5: Calculating player averages...")
    
    # Use raw depth values (no conversion needed)
    
    # Filter kitchen data
    kitchen_self = kitchen_df[kitchen_df["perspective"] == "oneself"]
    kitchen_role_pcts = (
        kitchen_self
        .groupby(["vid", "player_id", "role"], as_index=False)
        .agg(kitchen_arrivals=("kitchen_arrivals", "sum"), opportunities=("opportunities", "sum"))
    )
    kitchen_role_pcts["kitchen_pct"] = kitchen_role_pcts["kitchen_arrivals"] / kitchen_role_pcts["opportunities"]
    
    kitchen_wide = (
        kitchen_role_pcts
        .pivot(index=["vid", "player_id"], columns="role", values="kitchen_pct")
        .reset_index()
        .rename(columns={"serving": "serve_kitchen_pct", "returning": "return_kitchen_pct"})
    )
    if "serve_kitchen_pct" not in kitchen_wide.columns:
        kitchen_wide["serve_kitchen_pct"] = pd.NA
    if "return_kitchen_pct" not in kitchen_wide.columns:
        kitchen_wide["return_kitchen_pct"] = pd.NA
    
    # Serve metrics
    serve_stats = shot_df[shot_df['shot_role'] == 'serve'].copy()
    serve_stats['depth'] = pd.to_numeric(serve_stats['depth'], errors='coerce')
    serve_avg = (
        serve_stats
        .groupby(['vid', 'player_id'])
        .agg(
            serve_depth_avg=('depth', 'mean'),
            serve_height_avg=('height_over_net', 'mean')
        )
        .reset_index()
    )
    serve_avg['serve_depth_avg'] = 44 - serve_avg['serve_depth_avg']
    
    # Return metrics
    return_stats = shot_df[shot_df['shot_role'] == 'return'].copy()
    return_stats['depth'] = pd.to_numeric(return_stats['depth'], errors='coerce')
    return_avg = (
        return_stats
        .groupby(['vid', 'player_id'])
        .agg(
            return_depth_avg=('depth', 'mean'),
            return_height_avg=('height_over_net', 'mean')
        )
        .reset_index()
    )
    return_avg['return_depth_avg'] = 44 - return_avg['return_depth_avg']
    
    # Combine
    player_avg = (
        serve_avg
        .merge(return_avg, on=["vid", "player_id"], how="outer")
        .merge(kitchen_wide, on=["vid", "player_id"], how="left")
    )
    player_avg["player_name"] = None
    
    # Apply grades
    player_avg["serve_depth_grade"] = player_avg["serve_depth_avg"].apply(lambda x: grade_inverse(x, SERVE_DEPTH_BANDS))
    player_avg["serve_height_grade"] = player_avg["serve_height_avg"].apply(lambda x: grade_inverse(x, HEIGHT_BANDS))
    player_avg["serve_kitchen_grade"] = player_avg["serve_kitchen_pct"].apply(lambda x: grade_direct(x, SERVE_KITCHEN_BANDS))
    player_avg["return_depth_grade"] = player_avg["return_depth_avg"].apply(lambda x: grade_inverse(x, SERVE_DEPTH_BANDS))
    player_avg["return_height_grade"] = player_avg["return_height_avg"].apply(lambda x: grade_inverse(x, HEIGHT_BANDS))
    player_avg["return_kitchen_grade"] = player_avg["return_kitchen_pct"].apply(lambda x: grade_direct(x, RETURN_KITCHEN_BANDS))
    
    csv_path = output_dir / "player_averages.csv"
    player_avg.to_csv(csv_path, index=False)
    
    print(f"✅ Generated player_averages.csv ({len(player_avg)} rows)")
    return player_avg

def stage_delivery_data(output_dir, data_dir, player_ids):
    """Copy generated CSVs into each player's delivery staging Data folder."""
    csv_names = [
        "kitchen_role_stats.csv",
        "player_best_shots.csv",
        "player_averages.csv",
    ]

    dataframes = {}
    for csv_name in csv_names:
        src = output_dir / csv_name
        if not src.exists():
            continue
        try:
            df = pd.read_csv(src)
        except Exception:
            continue
        if "player_id" not in df.columns:
            continue
        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
        dataframes[csv_name] = df

    for player_id in sorted(player_ids):
        delivery_data_dir = data_dir / "delivery_staging" / f"Player_{player_id}" / "Data"
        delivery_data_dir.mkdir(parents=True, exist_ok=True)

        for csv_name, df in dataframes.items():
            player_df = df[df["player_id"] == player_id]
            if player_df.empty:
                continue
            dst = delivery_data_dir / csv_name
            player_df.to_csv(dst, index=False)

# ============================================================================
# Main Orchestration
# ============================================================================
def main():
    """Execute unified pipeline."""
    print("🎬 Starting unified match data processing...\n")
    
    data_dir = Path(__file__).parent.parent / 'data'
    output_dir = data_dir / 'player_data'
    stats_json = data_dir / 'stats' / "stats4.json"
    
    # Load raw data
    print(f"📂 Loading {stats_json}...")
    data_list = load_json_lines(stats_json)
    
    stats = find_object(data_list, "stats")
    insights = find_object(data_list, "insights") or {}
    all_rallies = collect_all_rallies(data_list)
    rally_insights = {
        "rallies": all_rallies
    }
    print(f"TOTAL rallies: {len(rally_insights['rallies'])}")
    vid = stats.get("session", {}).get("vid") if stats else None
    
    if not vid:
        print("⚠️ Video ID not found")
    
    # Execute pipeline stages
    kitchen_df = extract_kitchen_role_stats(insights, vid, output_dir)
    shot_df = extract_shot_level_data(insights, vid, output_dir)
    highlight_df = generate_serves_and_receives(shot_df, output_dir)
    best_shots_df = generate_player_best_shots(insights, vid, output_dir, top_n=50)
    player_avg_df = calculate_player_averages(shot_df, kitchen_df, output_dir)

    if not player_avg_df.empty:
        player_ids = set(int(pid) for pid in player_avg_df["player_id"].dropna().unique())
        stage_delivery_data(output_dir, data_dir, player_ids)
    
    print(f"\n✅ Pipeline complete!")
    print(
        f"📊 Generated CSVs: {len(shot_df)} shots, "
        f"{len(highlight_df)} serve/return contexts, "
        f"{len(best_shots_df)} PB Vision best-shot segments, "
        f"{len(player_avg_df)} players"
    )

if __name__ == "__main__":
    main()