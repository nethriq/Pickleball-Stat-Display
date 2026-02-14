#!/usr/bin/env python3
"""
Orchestrator: runs the full analytics pipeline end-to-end.
Executes: data processing → highlight generation → report creation.
"""

import sys
import subprocess
from pathlib import Path
from kitchen_visualizer_ui import DATA_DIR

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

def run_stage(script_name, description):
    """Run a pipeline stage and handle failures."""
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        print(f"❌ Script not found: {script_name}")
        return False
    print(f"\n{'='*60}")
    print(f"▶️  {description}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            cwd=Path(__file__).parent
        )
        print(f"\n✅ {description} completed\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with exit code {e.returncode}")
        return False

def validate_output(output_paths):
    """Check if expected output files were generated."""
    print("🔍 Validating outputs...")
    for output in output_paths:
        if not output.exists():
            print(f"   ❌ Missing output: {output}")
            return False
        print(f"   ✅ Output generated: {output}")
    return True

def main():
    """Execute full pipeline."""
    print("🎬 NethriQ Analytics Pipeline")
    print(f"📅 Running all stages...\n")
    
    stages = [
        (
            "process_match_data.py",
            "Stage 1: Data Processing",
            [
                DATA_DIR / "player_data" / "player_averages.csv",
                DATA_DIR / "player_data" / "highlight_registry.csv",
                DATA_DIR / "player_data" / "shot_level_data.csv",
                DATA_DIR / "player_data" / "kitchen_role_stats.csv",
            ],
        ),
        (
            "spreadsheet_generator.py",
            "Stage 2: Spreadsheet Generation",
            [
                DATA_DIR / "delivery_staging" / "Reports",
            ],
        ),
        (
            "kitchen_visualizer_ui.py",
            "Stage 3: Kitchen Visualization",
            [
                DATA_DIR / "graphics",
            ],
        ),
        (
            "video_clipper.py",
            "Stage 4: Highlight Generation",
            [
                DATA_DIR / "video_links.json",
            ],
        ),
        (
            "ppt_injector.py",
            "Stage 5: Report Creation",
            [
                DATA_DIR / "delivery_staging" / "Player_0" / "Reports" / "player_report.pptx",
            ],
        ),
        (
            "delivery_packager.py",
            "Stage 6: Delivery Packaging",
            [
                DATA_DIR / "deliveries" / "logs",
            ],
        ),
    ]
    
    for script, description, output_files in stages:
        if not run_stage(script, description):
            #All scripts are dependent, so stop on first failure
            sys.exit(1)
        """if not validate_output(output_files):
            print(f"❌ Output validation failed for {description}")
            sys.exit(1)"""
    
    print("\n" + "="*60)
    
    print("✅ Full pipeline completed successfully!")
    print("📊 Outputs:")
    print(f"   - {DATA_DIR / 'player_averages.csv'}")
    print(f"   - {DATA_DIR / 'highlight_registry.csv'}")
    print(f"   - {DATA_DIR / 'shot_level_data.csv'}")
    print(f"   - {DATA_DIR / 'kitchen_role_stats.csv'}")
    print(f"   - player_*_analysis.xlsx (in {DATA_DIR / 'reports/'})")
    print(f"   - kitchen_player_*.png (in {DATA_DIR / 'graphics/'})")
    print(f"   - {DATA_DIR / 'video_links.json'}")
    print(f"   - {DATA_DIR / 'delivery_staging' / 'Player_0' / 'Reports' / 'player_report.pptx'}")
    print(f"   - delivery zips (in {DATA_DIR / 'deliveries/'})")
    print(f"   - delivery upload logs (in {DATA_DIR / 'deliveries' / 'logs/'})")

if __name__ == "__main__":
    main()