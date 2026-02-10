"""
    1. Create temp delivery directory
    2. Copies PPT, Excel sheets, CSVs and final clips.
    3. Writes a README file with instructions for the client.
    4. Zips the delivery directory and saves it to the specified location.
    5. Returns zip path for reference.
    6. Produces JSON logs for each delivery.
    7. Cleanup.
"""
import zipfile
import shutil
from pathlib import Path
from video_clipper import BASE_DIR, DATA_DIR, SESSION_ID
DELIVERY_DIR = BASE_DIR / "deliveries"

def build_delivery_bundle()->Path:
    bundle_root = DELIVERY_DIR / f"NethriQ_Report_{SESSION_ID}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    # Subfolders
    (bundle_root / "Reports").mkdir()
    (bundle_root / "Videos").mkdir()
    (bundle_root / "Data").mkdir()

    # Copy files
    shutil.copy(DATA_DIR / "reports" / "player_report.pptx", bundle_root / "Reports")
    shutil.copy(DATA_DIR / "reports" / "player_analysis.xlsx", bundle_root / "Reports")

    for csv in ["player_averages.csv", "shot_level_data.csv", "highlight_registry.csv"]:
        shutil.copy(DATA_DIR / "player_data" / csv, bundle_root / "Data")

    # Copy final videos (NOT raw clips)
    videos_dir = DATA_DIR / "nethriq_media"
    for video in videos_dir.glob("*.mp4"):
        shutil.copy(video, bundle_root / "Videos")

    # Zip
    zip_path = DELIVERY_DIR / f"{bundle_root.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in bundle_root.rglob("*"):
            z.write(file, file.relative_to(bundle_root.parent))

    return zip_path    