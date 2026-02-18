"""
    3. Writes a README file with instructions for the client.
    4. Zips the delivery directory and saves it to the specified location.
    5. Returns zip path for reference.
    6. Produces JSON logs for each delivery.
    7. Cleanup.
"""
import zipfile
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent.parent
DELIVERY_STAGING = BASE_DIR / "data" / "delivery_staging"
DELIVERY_OUT = BASE_DIR / "data" / "deliveries"
LOG_DIR = DELIVERY_OUT / "logs"

DELIVERY_OUT.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

def zip_player_bundle(player_dir: Path, date_str: str) -> Path:
    player_name = player_dir.name
    player_id = player_name.split("_", 1)[1] if "_" in player_name else player_name
    zip_name = f"Nethriq_Player_{player_id}_{date_str}.zip"
    zip_path = DELIVERY_OUT / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in player_dir.rglob("*"):
            z.write(file, file.relative_to(player_dir.parent))

    return zip_path

def build_delivery_bundles(cleanup: bool = True):
    results = []
    date_str = datetime.now(timezone.utc).date().isoformat()

    for player_dir in DELIVERY_STAGING.iterdir():
        if not player_dir.is_dir():
            continue

        zip_path = zip_player_bundle(player_dir, date_str)

        log = {
            "player": player_dir.name,
            "zip": zip_path.name,
            "email": None,
            "upload_status": None,
            "email_status": None,
            "status": "created",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        results.append(log)

        if cleanup:
            shutil.rmtree(player_dir)

    # Write delivery log
    log_path = LOG_DIR / f"delivery_{datetime.now(timezone.utc).date()}.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)

    return results

if __name__ == "__main__":
    build_delivery_bundles()