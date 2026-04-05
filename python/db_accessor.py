#!/usr/bin/env python3
"""
Database accessor for subprocess scripts.
Allows pipeline stages to fetch job data directly from Django database.
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nethriq.settings')
django.setup()

from nethriq.models import VideoJob


def get_job_data(job_id=None):
    """
    Fetch job data from database.
    
    Args:
        job_id: VideoJob ID (if None, reads from JOB_ID env var)
    
    Returns:
        dict with keys:
            - pbvision_response: PB Vision JSON payload
            - selected_player_index: User's selected player (0-3)
            - video_url: Source video path/URL
            - job_dir: Job directory path
    
    Raises:
        RuntimeError: If job_id not provided and JOB_ID env var not set
        ValueError: If job not found in database
    """
    if job_id is None:
        job_id = os.environ.get("JOB_ID")
    
    if not job_id:
        raise RuntimeError(
            "JOB_ID must be provided as argument or JOB_ID environment variable"
        )
    
    try:
        job = VideoJob.objects.get(id=job_id)
    except VideoJob.DoesNotExist:
        raise ValueError(f"VideoJob with ID {job_id} not found in database")
    
    if not job.pbvision_response:
        raise ValueError(f"VideoJob {job_id} has no pbvision_response data")
    
    return {
        'pbvision_response': job.pbvision_response,
        'selected_player_index': job.selected_player_index,
        'video_url': job.video_url,
        'job_dir': os.environ.get("JOB_DATA_DIR"),
        'job_id': job.id,
    }


if __name__ == "__main__":
    # Test the accessor
    test_job_id = os.environ.get("JOB_ID")
    if test_job_id:
        data = get_job_data(test_job_id)
        print(f"✅ Successfully fetched data for Job {data['job_id']}")
        print(f"   Selected Player: {data['selected_player_index']}")
        print(f"   Video URL: {data['video_url']}")
        print(f"   PB Vision data present: {bool(data['pbvision_response'])}")
    else:
        print("⚠️ Set JOB_ID environment variable to test")
