"""
Delivery Packager: Creates zipfiles from delivery_staging and logs results.

Stage 6 of the analytics pipeline.
"""
import zipfile
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def zip_player_bundle(player_dir: Path, delivery_out: Path, date_str: str) -> Path:
    """Create a zip file for a player's deliverables.
    
    Args:
        player_dir: Directory containing player's files
        delivery_out: Output directory for zip files
        date_str: Date string for naming (ISO format)
    
    Returns:
        Path to created zip file
    """
    player_name = player_dir.name
    player_id = player_name.split("_", 1)[1] if "_" in player_name else player_name
    zip_name = f"Nethriq_Player_{player_id}_{date_str}.zip"
    zip_path = delivery_out / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in player_dir.rglob("*"):
            z.write(file, file.relative_to(player_dir.parent))

    return zip_path



def package_deliveries(
    job_directory,
    selected_player_index: Optional[int] = None,
    cleanup: bool = True,
) -> Dict[str, Any]:
    """Package player deliverables into zip files.
    
    Args:
        job_directory: Path to job output directory (str or Path)
        selected_player_index: User's selected player (0-3), optional
        cleanup: Whether to remove staging directories after zipping
    
    Returns:
        dict: Summary of packaged deliveries
    """
    print("📦 Starting delivery packaging...\n")
    
    job_dir = Path(job_directory)
    delivery_staging = job_dir / "delivery_staging"
    delivery_out = job_dir / "deliveries"
    log_dir = delivery_out / "logs"
    
    delivery_out.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    if not delivery_staging.exists():
        print(f"⚠️ Delivery staging directory not found: {delivery_staging}")
        return {'packaged': False, 'reason': 'no_staging_directory'}
    
    results = []
    date_str = datetime.now(timezone.utc).date().isoformat()

    for player_dir in delivery_staging.iterdir():
        if not player_dir.is_dir():
            continue
        
        # Extract player ID from directory name
        try:
            player_id = int(player_dir.name.split("_")[-1])
        except (ValueError, IndexError):
            print(f"⚠️ Skipping {player_dir.name}: invalid format")
            continue
        
        # Skip if not the selected player
        if selected_player_index is not None and player_id != int(selected_player_index):
            continue

        zip_path = zip_player_bundle(player_dir, delivery_out, date_str)

        log = {
            "player": player_dir.name,
            "zip": zip_path.name,
            "zip_path": str(zip_path),
            "email": None,
            "upload_status": None,
            "email_status": None,
            "status": "created",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        results.append(log)
        print(f"✓ Packaged: {zip_path.name}")

        if cleanup:
            shutil.rmtree(player_dir)

    # Write delivery log
    log_path = log_dir / f"delivery_{datetime.now(timezone.utc).date()}.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"✓ Delivery log: {log_path}")
    
    print(f"\n✅ Delivery packaging complete! ({len(results)} deliveries)")

    return {
        'packaged': True,
        'count': len(results),
        'delivery_dir': str(delivery_out),
        'log_path': str(log_path),
        'selected_player_index': selected_player_index,
    }


if __name__ == "__main__":
    raise RuntimeError(
        "Direct CLI execution is not supported. "
        "Use package_deliveries(...) from the pipeline."
    )