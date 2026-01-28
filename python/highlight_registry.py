import pandas as pd
from os import path

csv_path=path.join(path.dirname(__file__), '..','data','shot_level_data.csv')
shot_data = pd.read_csv(csv_path)[['vid','start_ms', 'end_ms', 'rally_idx', 'shot_idx', 'player_id']]
grouped = shot_data.groupby(['vid', 'rally_idx'], sort=False)
serve_highlights = []

for (vid, rally_idx), rally in grouped:
    rally = rally.sort_values('shot_idx')

    if 0 not in rally['shot_idx'].values:
        continue

    start_row = rally[rally['shot_idx'] == 0].iloc[0]

    end_row = rally[rally['shot_idx'] == 1].iloc[0] \
        if 1 in rally['shot_idx'].values else start_row

    serve_highlights.append({
        'vid': vid,
        'rally_idx': rally_idx,
        'highlight_type': 'serve_context',
        'start_ms': start_row['start_ms'],
        'end_ms': end_row['end_ms'],
        'player_id': start_row['player_id'],
        'start_shot_idx': start_row['shot_idx'],
        'end_shot_idx': end_row['shot_idx']
    })
return_highlights = []

for (vid, rally_idx), rally in grouped:
    rally = rally.sort_values('shot_idx')

    if 0 not in rally['shot_idx'].values:
        continue

    start_row = rally[rally['shot_idx'] == 0].iloc[0]

    if 3 in rally['shot_idx'].values:
        end_row = rally[rally['shot_idx'] == 3].iloc[0]
    elif 2 in rally['shot_idx'].values:
        end_row = rally[rally['shot_idx'] == 2].iloc[0]
    elif 1 in rally['shot_idx'].values:
        end_row = rally[rally['shot_idx'] == 1].iloc[0]
    else:
        continue

    return_highlights.append({
        'vid': vid,
        'rally_idx': rally_idx,
        'highlight_type': 'return_context',
        'start_ms': start_row['start_ms'],
        'end_ms': end_row['end_ms'],
        'player_id': start_row['player_id'],
        'start_shot_idx': start_row['shot_idx'],
        'end_shot_idx': end_row['shot_idx']
    })
highlights_df = pd.DataFrame(
    serve_highlights + return_highlights
).sort_values(['vid', 'rally_idx', 'start_ms'])
highlights_df.to_csv(
    path.join(path.dirname(__file__), '..','data','highlight_registry.csv'),
    index=False
)
print("Highlight registry saved to data/highlight_registry.csv")