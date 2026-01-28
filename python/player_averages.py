import pandas as pd
import os

# Grading thresholds for player performance metrics
# Lower values are better for depth/height (closer to net)
SERVE_DEPTH_BANDS = [
    (2, "Pro"),
    (4, "Advanced"),
    (6, "Intermediate"),
]

# Height over net grading bands (lower is better)
HEIGHT_BANDS = [
    (2, "Pro"),
    (2.5, "Advanced"),
    (3, "Intermediate"),
]

# Kitchen percentage grading bands for serving (higher is better)
SERVE_KITCHEN_BANDS = [
    (0.9, "Pro"),
    (0.7, "Advanced"),
    (0.5, "Intermediate"),
]

# Kitchen percentage grading bands for returning (higher is better)
RETURN_KITCHEN_BANDS = [
    (0.95, "Pro"),
    (0.85, "Advanced"),
    (0.7, "Intermediate"),
]


def grade_inverse(value, bands):
    """
    Grade a metric where lower values are better (e.g., depth, height).
    Args:
        value: The metric value to grade
        bands: List of (upper_bound, grade) tuples
    Returns:
        Grade string or None if value is NaN
    """
    if pd.isna(value):
        return None
    for upper, grade in bands:
        if value <= upper:
            return grade
    return "Beginner"


def grade_direct(value, bands):
    """
    Grade a metric where higher values are better (e.g., kitchen percentage).
    Args:
        value: The metric value to grade
        bands: List of (lower_bound, grade) tuples
    Returns:
        Grade string or None if value is NaN
    """
    if pd.isna(value):
        return None
    for lower, grade in bands:
        if value >= lower:
            return grade
    return "Beginner"


# ============================================================================
# Load data files
# ============================================================================
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(parent_dir, 'data')
csv_path = os.path.join(data_dir, 'player_averages.csv')
shots = pd.read_csv(os.path.join(data_dir, 'shot_level_data.csv'))
kitchen = pd.read_csv(os.path.join(data_dir, 'kitchen_role_stats.csv'))

shots["depth_from_baseline"]=44-shots["depth"]

# Filter to player's own kitchen stats (not opponent perspective)
kitchen_self = kitchen[kitchen["perspective"] == "oneself"]

# Calculate kitchen arrival percentage by role (serve/return)
kitchen_role_pcts = (
    kitchen_self
    .groupby(["vid", "player_id", "role"], as_index=False)
    .agg(
        kitchen_arrivals=("kitchen_arrivals", "sum"),
        opportunities=("opportunities", "sum"),
    )
)

kitchen_role_pcts["kitchen_pct"] = (
    kitchen_role_pcts["kitchen_arrivals"]
    / kitchen_role_pcts["opportunities"]
)

# Reshape kitchen data from long to wide format
kitchen_wide = (
    kitchen_role_pcts
    .pivot(index=["vid", "player_id"], columns="role", values="kitchen_pct")
    .reset_index()
    .rename(columns={
        "serving": "serve_kitchen_pct",
        "returning": "return_kitchen_pct"
    })
)

# Calculate average serve depth and height per player
serve_averages = shots[shots['shot_role'] == 'serve'].groupby(['vid', 'player_id']).agg(
    serve_depth_avg=('depth_from_baseline', 'mean'),
    serve_height_avg=('height_over_net', 'mean')
).reset_index()

# Calculate average return depth and height per player
return_averages = shots[shots['shot_role'] == 'return'].groupby(['vid', 'player_id']).agg(
    return_depth_avg=('depth_from_baseline', 'mean'),
    return_height_avg=('height_over_net', 'mean')
).reset_index()

# ============================================================================
# Combine all metrics and apply grades
# ============================================================================
player_averages = (
    serve_averages
    .merge(return_averages, on=["vid", "player_id"], how="outer")
    .merge(kitchen_wide, on=["vid", "player_id"], how="left")
)
player_averages["player_name"]=None
df = player_averages.copy()

# Grade serve metrics
df["serve_depth_grade"] = df["serve_depth_avg"].apply(
    lambda x: grade_inverse(x, SERVE_DEPTH_BANDS)
)
df["serve_height_grade"] = df["serve_height_avg"].apply(
    lambda x: grade_inverse(x, HEIGHT_BANDS)
)
df["serve_kitchen_grade"] = df["serve_kitchen_pct"].apply(
    lambda x: grade_direct(x, SERVE_KITCHEN_BANDS)
)

# Grade return metrics
df["return_depth_grade"] = df["return_depth_avg"].apply(
    lambda x: grade_inverse(x, SERVE_DEPTH_BANDS)
)
df["return_height_grade"] = df["return_height_avg"].apply(
    lambda x: grade_inverse(x, HEIGHT_BANDS)
)
df["return_kitchen_grade"] = df["return_kitchen_pct"].apply(
    lambda x: grade_direct(x, RETURN_KITCHEN_BANDS)
)

# ============================================================================
# Save results
# ============================================================================
df.to_csv(csv_path, index=False)
print(f"Generated {csv_path} ({len(df)} rows)")