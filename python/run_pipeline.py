#!/usr/bin/env python3
"""
Orchestrator: runs the full analytics pipeline end-to-end.
Executes: data processing → highlight generation → report creation.
"""

import sys
import subprocess
import json
import os
from pathlib import Path

def run_stage(script_name, description, job_dir, video_url=None):
    """Run a pipeline stage and handle failures."""
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        print(f"❌ Script not found: {script_name}")
        return False
    print(f"\n{'='*60}")
    print(f"▶️  {description}")
    print(f"{'='*60}\n")
    
    env = os.environ.copy()
    env["JOB_DATA_DIR"] = str(job_dir)
    if video_url:
        env["SOURCE_VIDEO_URL"] = video_url

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            env=env,
            check=True,
            cwd=Path(__file__).parent
        )
        print(f"\n✅ {description} completed\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with exit code {e.returncode}")
        return False

def run_pipeline(pbvision_json, job_directory, user_email, job_id, video_url=None):
    """Entry point for the Celery task."""
    print(f"🎬 NethriQ Analytics Pipeline for Job {job_id}")
    print(f"📁 Isolated Job Directory: {job_directory}")
    if video_url:
        print(f"🎥 Source Video URL: {video_url}")

    job_dir_path = Path(job_directory)
    job_dir_path.mkdir(parents=True, exist_ok=True)

    input_json_path = job_dir_path / "pbvision_input.json"
    with open(input_json_path, "w") as f:
        json.dump(pbvision_json, f)

    stages = [
        ("process_match_data.py", "Stage 1: Data Processing"),
        ("spreadsheet_generator.py", "Stage 2: Spreadsheet Generation"),
        ("kitchen_visualizer_ui.py", "Stage 3: Kitchen Visualization"),
        ("video_clipper.py", "Stage 4: Highlight Generation"),
        ("ppt_injector.py", "Stage 5: Report Creation"),
        ("delivery_packager.py", "Stage 6: Delivery Packaging"),
    ]

    for script, description in stages:
        if not run_stage(script, description, job_dir_path, video_url):
            raise RuntimeError(f"Pipeline execution failed at {description}")

    print("\n" + "="*60)
    print(f"✅ Full pipeline completed successfully for Job {job_id}!")

    return {
        "job_id": job_id,
        "status": "SUCCESS",
        "job_directory": job_directory,
        "user_email": user_email,
        "message": "All pipeline stages completed successfully.",
    }


if __name__ == "__main__":
    mock_job_dir = "/tmp/local_test_job"
    run_pipeline({}, mock_job_dir, "test@example.com", "TEST-1", video_url=None)