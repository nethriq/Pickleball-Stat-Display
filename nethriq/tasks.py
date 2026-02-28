import os
import logging
import requests
import re
import shutil
import zipfile
from datetime import datetime
from celery import shared_task
from django.conf import settings
from .models import VideoJob

logger = logging.getLogger(__name__)

CLEANUP_ON_DELIVERY = os.getenv('CLEANUP_ON_DELIVERY', 'false').lower() == 'true'

# Retry configuration: exponential backoff, max 3 attempts
RETRY_KWARGS = {
    'autoretry_for': (Exception,),
    'retry_kwargs': {'max_retries': 3},
    'retry_backoff': True,
    'retry_backoff_max': 600,  # 10 minutes max backoff
    'retry_jitter': True,
}


@shared_task(bind=True, **RETRY_KWARGS)
def upload_to_pbvision(self, job_id, file_url):
    """
    Task 1: Initiate PB Vision upload via Node endpoint.
    
    Waits for Node to finish streaming the file to PB Vision (not the final stats).
    The webhook will arrive later to trigger pipeline processing.
    
    Args:
        job_id: VideoJob primary key
        file_url: S3 signed URL or local file path to video
    
    Returns:
        dict: Confirmation that upload stream has been initiated
    """
    try:
        job = VideoJob.objects.get(id=job_id)
        logger.info(f"[Job {job_id}] Initiating PB Vision upload with file_url: {file_url}")
        
        job.status = 'PROCESSING'
        job.task_id = self.request.id
        job.save()
        
        node_endpoint = os.getenv('NODE_ENDPOINT', 'http://localhost:3000/api/process-video')
        payload = {
            'jobId': job_id,
            'videoUrl': file_url,
            'webhookSecret': job.webhook_signature_secret,
        }
        
        logger.info(f"[Job {job_id}] Calling Node to stream upload: {node_endpoint}")
        # Wait for Node to finish streaming the file to PB Vision.
        response = requests.post(node_endpoint, json=payload, timeout=1800)
        response.raise_for_status()
        
        logger.info(f"[Job {job_id}] Upload complete. Waiting for webhook callback.")
        return {'status': 'upload_finished', 'job_id': job_id}
        
    except VideoJob.DoesNotExist:
        logger.error(f"[Job {job_id}] Job not found in database")
        raise Exception(f"VideoJob {job_id} does not exist")
    except Exception as e:
        logger.error(f"[Job {job_id}] Error initiating upload: {str(e)}", exc_info=True)
        job.status = 'FAILED'
        job.error_message = f'upload_to_pbvision failed: {str(e)}'
        job.save()
        raise


@shared_task(bind=True, **RETRY_KWARGS)
def process_pbvision_results(self, job_id, pbvision_json):
    """
    Task 2: Process PB Vision JSON output through Python pipeline.
    
    Triggered by Django webhook endpoint once PB Vision callback arrives.
    Creates isolated job directory, runs pipeline orchestrator, and saves results.
    
    Args:
        job_id: VideoJob primary key
        pbvision_json: JSON response from PB Vision webhook
    
    Returns:
        dict: Pipeline output summary
    """
    try:
        job = VideoJob.objects.get(id=job_id)
        logger.info(f"[Job {job_id}] Starting Python pipeline with PB Vision data")
        
        # Store PB Vision response for reference
        job.result_json = pbvision_json
        job.save()
        
        # Create isolated job directory
        job_dir = os.path.join(settings.BASE_DIR, 'data', f'job_{job_id}')
        os.makedirs(job_dir, exist_ok=True)
        logger.info(f"[Job {job_id}] Created job directory: {job_dir}")
        
        # Import and run pipeline orchestrator
        from python.run_pipeline import run_pipeline
        logger.info(f"[Job {job_id}] Imported pipeline_orchestrator")
        
        # Grab the video URL from the database
        source_video_url = job.video_url
        if not source_video_url:
            logger.warning(f"[Job {job_id}] No video_url found! Clipper may fail.")
            #Remove when AWS configuration is complete and video_url is guaranteed to be present
            source_video_url = os.path.join(settings.BASE_DIR, 'data', 'test_vids', 'test_video3.mp4')

        # Run pipeline with job isolation AND the video URL
        pipeline_output = run_pipeline(
            pbvision_json=pbvision_json,
            job_directory=job_dir,
            user_email=job.user.email,
            job_id=job_id,
            video_url=source_video_url  # <-- NEW ARGUMENT
        )
        logger.info(f"[Job {job_id}] Pipeline output summary: {pipeline_output}")
        logger.info(f"[Job {job_id}] Pipeline completed successfully")
        
        # Store results
        job.result_json = {
            'pbvision': pbvision_json,
            'pipeline_output': pipeline_output,
        }
        job.completed_at = datetime.now()
        job.status = 'COMPLETED'
        job.save()
        
        # Chain to next task: deliver_results
        deliver_results.delay(job_id)
        
        return pipeline_output
        
    except VideoJob.DoesNotExist:
        logger.error(f"[Job {job_id}] Job not found in database")
        raise Exception(f"VideoJob {job_id} does not exist")
    except Exception as e:
        logger.error(f"[Job {job_id}] Error in process_pbvision_results: {str(e)}", exc_info=True)
        job.status = 'FAILED'
        job.error_message = f'process_pbvision_results failed: {str(e)}'
        job.save()
        raise


@shared_task(bind=True)
def deliver_results(self, job_id):
    """
    Task 3: Email user and upload final ZIP package to S3.
    
    Called after process_pbvision_results completes (chained task).
    Handles delivery of results and cleanup.
    
    Args:
        job_id: VideoJob primary key
    
    Returns:
        dict: Delivery status
    """
    try:
        job = VideoJob.objects.get(id=job_id)
        user_email = job.user.email
        logger.info(f"[Job {job_id}] Delivering results to {user_email}")
        job_dir = os.path.join(settings.BASE_DIR, 'data', f'job_{job_id}')
        deliveries_dir = os.path.join(job_dir, 'deliveries')

        if not os.path.isdir(deliveries_dir):
            raise FileNotFoundError(f"Deliveries directory not found: {deliveries_dir}")

        zipfiles = _discover_zipfiles(deliveries_dir)
        if not zipfiles:
            job.status = 'FAILED'
            job.error_message = 'deliver_results failed: no deliverables found'
            job.save()
            raise FileNotFoundError(f"No zipfiles found in {deliveries_dir}")

        master_zip = _create_master_zip(zipfiles, deliveries_dir)

        result_payload = job.result_json or {}
        result_payload['deliverables'] = {
            'zipfiles': zipfiles,
            'master_zip': master_zip,
            'generated_at': datetime.now().isoformat(),
        }
        job.result_json = result_payload

        if CLEANUP_ON_DELIVERY:
            if job.video_file:
                try:
                    job.video_file.delete(save=False)
                    logger.info(f"[Job {job_id}] Deleted source video from local storage")
                except Exception:
                    logger.warning(f"[Job {job_id}] Failed to delete source video", exc_info=True)

            _cleanup_job_temp_dirs(job_dir)
        else:
            logger.info(f"[Job {job_id}] Cleanup disabled (CLEANUP_ON_DELIVERY=false)")

        job.logs += f'\n[{datetime.now().isoformat()}] Delivery task completed'
        job.save()

        logger.info(f"[Job {job_id}] Delivery completed")
        return {'status': 'delivered', 'job_id': job_id, 'zip_count': len(zipfiles)}
        
    except VideoJob.DoesNotExist:
        logger.error(f"[Job {job_id}] Job not found in database")
        raise
    except Exception as e:
        logger.error(f"[Job {job_id}] Error in deliver_results: {str(e)}", exc_info=True)
        raise


def _discover_zipfiles(deliveries_dir):
    zipfiles = []
    player_pattern = re.compile(r"Nethriq_Player_(.+?)_\d{4}-\d{2}-\d{2}\.zip$")
    for entry in sorted(os.listdir(deliveries_dir)):
        if not entry.endswith('.zip'):
            continue
        if entry.startswith('Nethriq_All_'):
            continue
        zip_path = os.path.join(deliveries_dir, entry)
        if not os.path.isfile(zip_path):
            continue
        file_size = os.path.getsize(zip_path)
        match = player_pattern.search(entry)
        zip_id = match.group(1) if match else os.path.splitext(entry)[0]
        zipfiles.append({
            'id': zip_id,
            'name': entry,
            'path': zip_path,
            'size': file_size,
        })
    return zipfiles


def _create_master_zip(zipfiles, deliveries_dir):
    date_stamp = datetime.now().strftime('%Y-%m-%d')
    master_name = f"Nethriq_All_{date_stamp}.zip"
    master_path = os.path.join(deliveries_dir, master_name)

    with zipfile.ZipFile(master_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for zip_meta in zipfiles:
            archive.write(zip_meta['path'], arcname=zip_meta['name'])

    return {
        'name': master_name,
        'path': master_path,
        'size': os.path.getsize(master_path),
    }


def _cleanup_job_temp_dirs(job_dir):
    temp_dirs = [
        'nethriq_media',
        'delivery_staging',
        'player_data',
        'stats',
    ]
    for temp_dir in temp_dirs:
        target = os.path.join(job_dir, temp_dir)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
