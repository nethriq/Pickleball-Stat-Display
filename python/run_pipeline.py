#!/usr/bin/env python3
"""
Orchestrator: runs the full analytics pipeline end-to-end.
Executes: data processing → spreadsheet generation → highlight generation → report creation.
"""

import sys
import subprocess
import json
import os
from pathlib import Path

# Import Python modules for in-memory processing
from .process_match_data import process_match_data
from .spreadsheet_generator import generate_spreadsheets
from .kitchen_visualizer_ui import generate_kitchen_visualizations
from .video_clipper import generate_highlights
from .ppt_injector import generate_player_reports
from .delivery_packager import package_deliveries


def summarize_stage1_output(stage1_output):
    """Convert Stage 1 payload into a JSON-safe summary."""
    if not isinstance(stage1_output, dict):
        return stage1_output

    # Backwards compatibility: old payload already had scalar counts.
    if "shot_df" not in stage1_output:
        return stage1_output

    shot_df = stage1_output.get("shot_df")
    highlight_df = stage1_output.get("highlight_df")
    best_shots_df = stage1_output.get("best_shots_df")
    player_avg_df = stage1_output.get("player_avg_df")

    return {
        "vid": stage1_output.get("vid"),
        "selected_player_index": stage1_output.get("selected_player_index"),
        "shots_count": len(shot_df) if shot_df is not None else 0,
        "highlights_count": len(highlight_df) if highlight_df is not None else 0,
        "best_shots_count": len(best_shots_df) if best_shots_df is not None else 0,
        "players_count": len(player_avg_df) if player_avg_df is not None else 0,
    }

def run_stage(script_name, description, job_dir, job_id, video_url=None, player_index=None):
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
    env["JOB_ID"] = str(job_id)  # Pass job_id so scripts can query database
    if video_url:
        env["SOURCE_VIDEO_URL"] = video_url
    if player_index is not None:
        env["SELECTED_PLAYER_INDEX"] = str(player_index)

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

def run_pipeline(pbvision_json, job_directory, user_email, job_id, video_url=None, selected_player_index=None):
    """Entry point for the Celery task."""
    print(f"🎬 NethriQ Analytics Pipeline for Job {job_id}")
    print(f"📁 Isolated Job Directory: {job_directory}")
    if video_url:
        print(f"🎥 Source Video URL: {video_url}")
    if selected_player_index is not None:
        print(f"👤 Selected Player Index: {selected_player_index}")

    job_dir_path = Path(job_directory)
    job_dir_path.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # Stage 1: Data Processing (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 1: Data Processing (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        stage1_output = process_match_data(
            pbvision_data=pbvision_json,
            job_directory=job_dir_path,
            selected_player_index=selected_player_index
        )
        stats_summary = summarize_stage1_output(stage1_output)
        print(f"\n✅ Stage 1: Data Processing completed\n")
    except Exception as e:
        print(f"\n❌ Stage 1: Data Processing failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 1: Data Processing") from e

    # ========================================================================
    # Stage 2: Spreadsheet Generation (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 2: Spreadsheet Generation (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        spreadsheet_summary = generate_spreadsheets(
            job_directory=job_dir_path,
            selected_player_index=selected_player_index,
            stage1_output=stage1_output,
        )
        print(f"\n✅ Stage 2: Spreadsheet Generation completed\n")
    except Exception as e:
        print(f"\n❌ Stage 2: Spreadsheet Generation failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 2: Spreadsheet Generation") from e

    # ========================================================================
    # Stage 3: Kitchen Visualization (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 3: Kitchen Visualization (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        kitchen_summary = generate_kitchen_visualizations(
            job_directory=job_dir_path,
            selected_player_index=selected_player_index,
            stage1_output=stage1_output,
        )
        print(f"\n✅ Stage 3: Kitchen Visualization completed\n")
    except Exception as e:
        print(f"\n❌ Stage 3: Kitchen Visualization failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 3: Kitchen Visualization") from e
    
    # ========================================================================
    # Stage 4: Highlight Generation (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 4: Highlight Generation (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        highlights_summary = generate_highlights(
            job_directory=job_dir_path,
            video_url=video_url,
            selected_player_index=selected_player_index
        )
        print(f"\n✅ Stage 4: Highlight Generation completed\n")
    except Exception as e:
        print(f"\n❌ Stage 4: Highlight Generation failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 4: Highlight Generation") from e

    # ========================================================================
    # Stage 5: Report Creation (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 5: Report Creation (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        report_summary = generate_player_reports(
            job_directory=job_dir_path,
            selected_player_index=selected_player_index,
            stage1_output=stage1_output,
            kitchen_summary=kitchen_summary,
            highlights_summary=highlights_summary,
        )
        print(f"\n✅ Stage 5: Report Creation completed\n")
    except Exception as e:
        print(f"\n❌ Stage 5: Report Creation failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 5: Report Creation") from e

    # ========================================================================
    # Stage 6: Delivery Packaging (In-Memory Python Module)
    # ========================================================================
    print(f"\n{'='*60}")
    print(f"▶️  Stage 6: Delivery Packaging (In-Memory)")
    print(f"{'='*60}\n")
    
    try:
        delivery_summary = package_deliveries(
            job_directory=job_dir_path,
            selected_player_index=selected_player_index,
        )
        print(f"\n✅ Stage 6: Delivery Packaging completed\n")
    except Exception as e:
        print(f"\n❌ Stage 6: Delivery Packaging failed: {str(e)}")
        raise RuntimeError(f"Pipeline execution failed at Stage 6: Delivery Packaging") from e

    print("\n" + "="*60)
    print(f"✅ Full pipeline completed successfully for Job {job_id}!")

    return {
        "job_id": job_id,
        "status": "SUCCESS",
        "job_directory": job_directory,
        "user_email": user_email,
        "message": "All pipeline stages completed successfully.",
        "stages": {
            "data_processing": stats_summary,
            "spreadsheets": spreadsheet_summary,
            "kitchen_visualizations": kitchen_summary,
            "highlights": highlights_summary,
            "reports": report_summary,
            "deliveries": delivery_summary,
        }
    }


if __name__ == "__main__":
    # For local testing: set JOB_ID env var to test with real database job
    mock_job_dir = "/tmp/local_test_job"
    test_job_id = os.environ.get("JOB_ID", "TEST-1")
    print(f"⚠️ Running in test mode with job_id={test_job_id}")
    run_pipeline({}, mock_job_dir, "test@example.com", test_job_id, video_url=None, selected_player_index=0)