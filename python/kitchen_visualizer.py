"""Script to generate snapshots of player specific kitchen data"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = DATA_DIR / "graphics"
OUT_DIR.mkdir(exist_ok=True)

# Pickleball court dimensions (normalized to 0-1)
COURT_WIDTH = 1.0
COURT_HEIGHT = 1.01
KITCHEN_DEPTH = 0.07  # Kitchen is 7 feet on 44 feet court

# Highlight color semantics
PLAYER_HIGHLIGHT_COLOR = "orange"
PLAYER_DEFAULT_COLOR = "white"
# Blue scale endpoints for performance fill (light -> dark)
LIGHT_BLUE = np.array([0.85, 0.93, 1.0])
DARK_BLUE = np.array([0.0, 0.35, 0.75])

def draw_court_quadrant(ax, x_offset, y_offset, player_id, kitchen_pct, is_highlighted=False):
    """Draw a single court quadrant for a player"""
    # Court boundaries
    rect = patches.Rectangle(
        (x_offset, y_offset), COURT_WIDTH/2, COURT_HEIGHT/2,
        linewidth=2, edgecolor='black', facecolor='lightgreen', alpha=0.3
    )
    ax.add_patch(rect)
    
    # Kitchen zone: orientation depends on player's half (top vs bottom)
    if y_offset > 0:
        # top-half players: kitchen is at the bottom of their half
        kitchen_y = y_offset
    else:
        # bottom-half players: kitchen is at the top of their half
        kitchen_y = y_offset + COURT_HEIGHT/2 - KITCHEN_DEPTH

    kitchen_rect = patches.Rectangle(
        (x_offset, kitchen_y), COURT_WIDTH/2, KITCHEN_DEPTH,
        linewidth=2, edgecolor='red', facecolor='yellow', alpha=0.4
    )
    ax.add_patch(kitchen_rect)
    
    # Center line
    if x_offset == 0:  # Left side
        ax.plot([COURT_WIDTH/2, COURT_WIDTH/2], [y_offset, y_offset + COURT_HEIGHT/2], 
                'k-', linewidth=1)
    
    # Calculate fill height for kitchen percentage (clamped)
    # Calculate fill height for kitchen percentage (clamped)
    pct = float(kitchen_pct)
    pct = max(0.0, min(1.0, pct))
    fill_height = max(0.001, KITCHEN_DEPTH * pct)
    # don't overflow the kitchen zone
    fill_height = min(fill_height, KITCHEN_DEPTH - 0.005)
    fill_x = x_offset + 0.05
    fill_y = kitchen_y + 0.005
    fill_width = COURT_WIDTH/2 - 0.1

    # Linear interpolation in RGB between LIGHT_BLUE and DARK_BLUE
    color_rgb = LIGHT_BLUE + (DARK_BLUE - LIGHT_BLUE) * pct
    color_tuple = (float(color_rgb[0]), float(color_rgb[1]), float(color_rgb[2]))

    edge = PLAYER_HIGHLIGHT_COLOR if is_highlighted else 'darkblue'
    edge_width = 2.0 if is_highlighted else 1.0
    fill_rect = patches.Rectangle(
        (fill_x, fill_y), fill_width, fill_height,
        linewidth=edge_width, edgecolor=edge, facecolor=color_tuple, alpha=0.9
    )
    ax.add_patch(fill_rect)
    
    # Player ID annotation
    text_color = 'white' if is_highlighted else 'black'
    font_weight = 'bold' if is_highlighted else 'normal'
    font_size = 14 if is_highlighted else 12
    
    ax.text(
        x_offset + COURT_WIDTH/4, y_offset + COURT_HEIGHT/4,
        f"P{player_id}",
        ha='center', va='center',
        fontsize=font_size, fontweight=font_weight, color=text_color,
        bbox=dict(boxstyle='round', facecolor=PLAYER_HIGHLIGHT_COLOR if is_highlighted else PLAYER_DEFAULT_COLOR,
             alpha=0.8, edgecolor=PLAYER_HIGHLIGHT_COLOR if is_highlighted else 'gray', linewidth=2 if is_highlighted else 1)
    )
    
    # Kitchen percentage
    # Kitchen percentage (centered within the kitchen zone)
    ax.text(
        x_offset + COURT_WIDTH/4, kitchen_y + KITCHEN_DEPTH/2,
        f"{float(kitchen_pct)*100:.0f}%",
        ha='center', va='center',
        fontsize=11, fontweight='bold', color='white'
    )

def render_player_kitchen(player_id: int):
    df = pd.read_csv(DATA_DIR / "kitchen_role_stats.csv")

    df = df[
        (df["perspective"] == "oneself")
    ]

    # split serving / returning
    serve = df[df["role"] == "serving"]
    ret   = df[df["role"] == "returning"]

    # Create figure with two subplots (serving and returning)
    fig, (ax_serve, ax_ret) = plt.subplots(1, 2, figsize=(14, 7))
    
    for ax, role_df, title in [(ax_serve, serve, "Kitchen Arrival: When Serving"), 
                                 (ax_ret, ret, "Kitchen Arrival: When Returning")]:
        ax.set_xlim(-0.1, 1.1)
        ax.set_ylim(-0.1, 1.1)
        ax.set_aspect('equal')
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.axis('off')
        
        # Draw court and kitchen zones for all 4 players
        # Top-left (Player 0), Top-right (Player 1), Bottom-left (Player 2), Bottom-right (Player 3)
        positions = [
            (0, 0.5, 0),      # Top-left
            (0.5, 0.5, 1),    # Top-right
            (0, 0, 2),        # Bottom-left
            (0.5, 0, 3)       # Bottom-right
        ]
        
        for x_off, y_off, pid in positions:
            # Get kitchen percentage for this player
            player_data = role_df[role_df["player_id"] == pid]
            kitchen_pct = player_data["kitchen_pct"].values[0] if len(player_data) > 0 else 0
            
            is_highlighted = (pid == player_id)
            draw_court_quadrant(ax, x_off, y_off, pid, kitchen_pct, is_highlighted)
        
        # Minimal one-line legend (bottom center)
        fig.text(0.5, 0.03, "Darker bar = more frequent kitchen arrival", ha='center', fontsize=10, color='black')
    
    plt.tight_layout()
    
    # Export PNG
    output_file = OUT_DIR / f"kitchen_player_{player_id}.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    # Generate visualizations for all players
    for player_id in range(4):
        render_player_kitchen(player_id)
