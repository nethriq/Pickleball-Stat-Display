import json
import csv
from pathlib import Path
def safe_ratio(n, d):
    return round(n / d, 3) if d else None

stats_json = Path(__file__).parent.parent / 'node' / "stats.json"

data_list = []
with open(stats_json, "r") as f:
    for line in f:
        if line.strip():
            try:
                data_list.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Skipping malformed line: {line[:50]}")

if not data_list:
    print("No valid JSON data found")
    exit()

# 🔍 Find the stats object
stats = None

for obj in data_list:
    if isinstance(obj, dict) and "stats" in obj:
        stats = obj["stats"]
        break

    if "payload" in obj and isinstance(obj["payload"], dict):
        if "stats" in obj["payload"]:
            stats = obj["payload"]["stats"]
            break

    if "insights" in obj and isinstance(obj["insights"], dict):
        if "stats" in obj["insights"]:
            stats = obj["insights"]["stats"]
            break

if stats is None:
    print("❌ No summary stats found in JSON file")
    exit()

# 🧮 Build CSV rows
rows = []

players = stats.get("players", [])

for idx, player in enumerate(players):
    kap=player.get("kitchen_arrival_percentage", {})
    serving = kap.get("serving", {}).get("oneself", {})
    returning = kap.get("returning", {}).get("oneself", {})

    serve_pct = safe_ratio(serving.get("numerator"),serving.get("denominator"))

    return_pct = safe_ratio(returning.get("numerator"),returning.get("denominator"))


    rows.append({
        "vid": stats["session"]["vid"],
        "player_id": idx,
        "serve_kitchen_coverage": serve_pct,
        "return_kitchen_coverage": return_pct
    })
output_dir = Path(__file__).parent


with open((output_dir / "summary_metrics.csv"), "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["vid", "player_id", "serve_kitchen_coverage", "return_kitchen_coverage"])
    writer.writeheader()
    writer.writerows(rows)
# 🏓 Extract shot-level data
shot_rows = []

vid = stats["session"]["vid"]

for rally_idx, rally in enumerate(stats.get("rallies", [])):
    for shot_idx, shot in enumerate(rally.get("shots", [])):
        rbm = shot.get("resulting_ball_movement", {})
        traj = rbm.get("trajectory", {})

        if not traj:
            continue

        shot_rows.append({
            "vid": vid,
            "rally_idx": rally_idx,
            "shot_idx": shot_idx,
            "player_id": shot.get("player_id"),
            "shot_type": shot.get("shot_type", "unknown"),
            "start_ms": shot.get("start_ms"),
            "end_ms": shot.get("end_ms"),
            "depth": rbm.get("distance"),
            "height_over_net": rbm.get("height_over_net")
        })

with open((output_dir / "shot_level_data.csv"), "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["vid", "rally_idx", "shot_idx", "player_id", "shot_type", "start_ms", "end_ms", "depth", "height_over_net"])
    writer.writeheader()
    writer.writerows(shot_rows)
print("✅ CSV files generated: summary_metrics.csv, shot_level_data.csv")
