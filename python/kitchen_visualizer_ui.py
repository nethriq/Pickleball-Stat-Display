"""UI-focused snapshots for player kitchen data."""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = DATA_DIR / "graphics"
OUT_DIR.mkdir(exist_ok=True)

TILE_BG = "#f7f7f7"
PLAYER_COLORS = {
	0: "#1f4cff",  # blue
	1: "#00bcd4",  # cyan
	2: "#f5c400",  # yellow
	3: "#ff6f00",  # orange
}

GUTTER = 0.15
COURT_W = 0.7
COURT_X = GUTTER
MID_X = COURT_X + COURT_W / 2
MID_Y = 0.5
TILE_W = COURT_W / 2
TILE_H = 0.5
KITCHEN_FRAC = 0.32
KITCHEN_LINE_COLOR = "#d0d0d0"
TOKEN_RADIUS = 0.0285
TOKEN_TEXT_GAP = 0.02
GLOW_LW = 6
GLOW_ALPHA = 0.18

def draw_player_tile(ax, x, y, w, h, pct, color, fills_from_left, max_fill_w):
	"""Draw a simple tile with a flat bar fill and percentage text."""
	ax.add_patch(
		patches.Rectangle((x, y), w, h, facecolor=TILE_BG, edgecolor="none", lw=0)
	)

	pct = max(0.0, min(1.0, float(pct)))
	bar_h = h
	bar_y = y
	bar_w = max(0.001, max_fill_w * pct)
	bar_x = x if fills_from_left else x + w - bar_w
	ax.add_patch(patches.Rectangle((bar_x, bar_y), bar_w, bar_h, facecolor=color, edgecolor="none"))

	text_y = bar_y + bar_h * 0.52
	text_color = "black"

	ax.text(
		bar_x + bar_w / 2,
		text_y,
		f"{int(round(pct * 100))}%",
		ha="center",
		va="center",
		fontsize=14,
		fontweight="bold",
		color=text_color,
	)

def draw_player_token(ax, cx, cy, color, label, align, is_selected=False):
	"""Draw a simple identity token in the gutter."""
	if is_selected:
		ax.add_patch(
			patches.Circle(
				(cx, cy),
				TOKEN_RADIUS * 1.35,
				facecolor="none",
				edgecolor=color,
				lw=GLOW_LW,
				alpha=GLOW_ALPHA,
			)
		)
	ax.add_patch(patches.Circle((cx, cy), TOKEN_RADIUS, facecolor=color, edgecolor="none"))
	text_x = cx
	text_ha = "center"
	ax.text(
		text_x,
		cy - TOKEN_RADIUS - TOKEN_TEXT_GAP,
		label,
		ha=text_ha,
		va="center",
		fontsize=11,
		fontweight="semibold",
		color="#222222",
	)

def render_player_kitchen(player_id: int):
	df = pd.read_csv(DATA_DIR / "player_data/kitchen_role_stats.csv")

	df = df[df["perspective"] == "oneself"]

	serve = df[df["role"] == "serving"]
	ret = df[df["role"] == "returning"]

	# Detect if singles or doubles
	all_player_ids = set(df["player_id"].unique())
	is_singles = 1 not in all_player_ids and 3 not in all_player_ids
	
	fig, (ax_serve, ax_ret) = plt.subplots(1, 2, figsize=(14, 7))

	for ax, role_df, title in [
		(ax_serve, serve, "Kitchen Arrival: When Serving"),
		(ax_ret, ret, "Kitchen Arrival: When Returning"),
	]:
		ax.set_xlim(0, 1)
		ax.set_ylim(0, 1)
		ax.set_aspect("equal")
		ax.set_title(title, fontsize=13, fontweight="semibold", color="#222222", pad=20)
		ax.axis("off")

		tile_w = TILE_W
		tile_h = TILE_H
		
		# Define positions: always 4 tiles, but only populate data for present players
		positions = [
			(COURT_X, MID_Y, 0),
			(COURT_X, 0, 1),
			(MID_X, MID_Y, 2),
			(MID_X, 0, 3),
		]

		left_kitchen_x = MID_X - TILE_W * KITCHEN_FRAC
		right_kitchen_x = MID_X + TILE_W * KITCHEN_FRAC

		# In singles mode, create extended positions for P0 and P2
		if is_singles:
			positions = [
				(COURT_X, 0, 0),      # P0: extend full height on left
				(MID_X, 0, 2),        # P2: extend full height on right
			]
			tile_h_display = 1.0    # Extended height
		else:
			tile_h_display = tile_h

		for x_off, y_off, pid in positions:
			# In doubles mode, skip P1 and P3
			if not is_singles and pid in [1, 3]:
				continue
			
			player_data = role_df[role_df["player_id"] == pid]
			kitchen_pct = player_data["kitchen_pct"].values[0] if len(player_data) > 0 else 0
			fills_from_left = x_off < MID_X
			if fills_from_left:
				max_fill_w = max(0.0, left_kitchen_x - x_off)
			else:
				max_fill_w = max(0.0, x_off + tile_w - right_kitchen_x)
			draw_player_tile(
				ax,
				x_off,
				y_off,
				tile_w,
				tile_h_display,
				kitchen_pct,
				PLAYER_COLORS[pid],
				fills_from_left,
				max_fill_w,
			)

			# Center token vertically in singles mode
			token_y = y_off + tile_h_display / 2
			if x_off < MID_X:
				token_x = GUTTER / 2
				align = "left"
			else:
				token_x = COURT_X + COURT_W + GUTTER / 2
				align = "right"
			draw_player_token(
				ax,
				token_x,
				token_y,
				PLAYER_COLORS[pid],
				f"P{pid}",
				align,
				is_selected=(pid == player_id),
			)

		ax.plot([MID_X, MID_X], [0, 1], color="black", lw=3)
		ax.plot([left_kitchen_x, left_kitchen_x], [0, 1], color="black", lw=2.0)
		ax.plot([right_kitchen_x, right_kitchen_x], [0, 1], color="black", lw=2.0)
		ax.plot([0, 1], [MID_Y, MID_Y], color="#efefef", lw=0)
		ax.plot([COURT_X, left_kitchen_x], [MID_Y, MID_Y], color="black", lw=2.0)
		ax.plot([right_kitchen_x, COURT_X + COURT_W], [MID_Y, MID_Y], color="black", lw=2.0)

	plt.tight_layout()
	output_file = OUT_DIR / f"kitchen_player_{player_id}.png"
	plt.savefig(output_file, dpi=300, bbox_inches="tight")
	print(f"Saved: {output_file}")
	plt.close()


if __name__ == "__main__":
	for player_id in range(4):
		render_player_kitchen(player_id)
