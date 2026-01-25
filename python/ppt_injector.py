import pandas as pd
from pptx import Presentation
from copy import deepcopy
from os import path


def replace_tokens_in_shape(shape, token_map):
    """
    Replace token placeholders with values in a PowerPoint shape.
    Args:
        shape: PowerPoint shape object
        token_map: Dictionary mapping tokens to replacement values
    """
    if not shape.has_text_frame:
        return

    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            for token, value in token_map.items():
                if token in run.text:
                    run.text = run.text.replace(token, value)


# ============================================================================
# Set up file paths and load data
# ============================================================================
csv_path = path.join(path.dirname(path.abspath(__file__)), '..', 'data', 'player_averages.csv')
ppt_template_path = path.join(path.dirname(path.abspath(__file__)),'..', 'node', 'mixed_doubles', 'NethriQ_Gautham.pptx')
df = pd.read_csv(csv_path)
row = df[df["player_id"] == 0].iloc[0]

# ============================================================================
# Load PowerPoint template and create token replacement map
# ============================================================================
prs = Presentation(ppt_template_path)
token_map = {
    "{{PLAYER}}": row["player_name"] if pd.notna(row["player_name"]) else "Player",
    "{{SERVE_DEPTH_VALUE}}": f"{row['serve_depth_avg']:.2f}",
    "{{SERVE_DEPTH_GRADE}}": row["serve_depth_grade"],
    "{{SERVE_HEIGHT_VALUE}}": f"{row['serve_height_avg']:.2f}",
    "{{SERVE_HEIGHT_GRADE}}": row["serve_height_grade"],
    "{{RETURN_DEPTH_VALUE}}": f"{row['return_depth_avg']:.2f}",
    "{{RETURN_DEPTH_GRADE}}": row["return_depth_grade"],
    "{{RETURN_HEIGHT_VALUE}}": f"{row['return_height_avg']:.2f}",
    "{{RETURN_HEIGHT_GRADE}}": row["return_height_grade"],
    "{{KAS}}": str(int(row["serve_kitchen_pct"] * 100)),
    "{{KAS_GRADE}}": row["serve_kitchen_grade"],
    "{{KAR}}": str(int(row["return_kitchen_pct"] * 100)),
    "{{KAR_GRADE}}": row["return_kitchen_grade"],
    "{{OVERALL_GRADE}}": "Advanced for now"
}

# ============================================================================
# Replace tokens in all slides
# ============================================================================
for slide in prs.slides:
    for shape in slide.shapes:
        replace_tokens_in_shape(shape, token_map)

# ============================================================================
# Save output PowerPoint file
# ============================================================================
output_ppt_path = path.join(path.dirname(path.abspath(__file__)), '..', 'data', 'player_report.pptx')
prs.save(output_ppt_path)
print(f"Generated {output_ppt_path}")