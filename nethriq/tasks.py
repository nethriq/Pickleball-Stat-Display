import os
import logging
import requests
import re
import shutil
import zipfile
from datetime import datetime
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from .models import VideoJob
from python.email_dispatcher import send_delivery_email_with_attachments

logger = logging.getLogger(__name__)

PRESERVE_SOURCE_VIDEO = os.getenv('PRESERVE_SOURCE_VIDEO', 'false').lower() == 'true'
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
def send_stub_claim_email(self, recipient_email, player_name, claim_url):
    """Send a branded claim-account email asynchronously for newly created stubs."""
    club_name = getattr(settings, 'CLUB_NAME', 'PB Vision Athletics')
    subject = f"Your match at {club_name} is ready"

    text_body = (
        f"Hi {player_name},\n\n"
        f"Your match at {club_name} has been analyzed by PB Vision.\n"
        "Use this one-time secure link to claim your account and view your stats:\n\n"
        f"{claim_url}\n\n"
        "This link expires in 24 hours.\n\n"
        "If you were not expecting this, you can ignore this email."
    )

    html_body = (
        f"<div style='font-family:Arial,sans-serif;line-height:1.5;color:#1b1f23;'>"
        f"<h2 style='margin-bottom:8px;'>Your stats are ready at {club_name}</h2>"
        f"<p>Hi {player_name},</p>"
        "<p>Your match has been analyzed by PB Vision. "
        "Click below to claim your account and view your stats.</p>"
        f"<p><a href='{claim_url}' "
        "style='display:inline-block;padding:10px 16px;background:#0d6efd;color:#ffffff;"
        "text-decoration:none;border-radius:6px;font-weight:600;'>Claim Account</a></p>"
        "<p style='margin-top:12px;'>This one-time link expires in 24 hours.</p>"
        "<p style='font-size:12px;color:#5a5f66;'>"
        "If the button does not work, copy and paste this URL into your browser:</p>"
        f"<p style='font-size:12px;color:#5a5f66;word-break:break-all;'>{claim_url}</p>"
        "</div>"
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        to=[recipient_email],
    )
    message.attach_alternative(html_body, 'text/html')
    sent = message.send(fail_silently=False)

    logger.info(
        f"[StubClaimEmail] sent={sent} recipient={recipient_email} club={club_name}"
    )
    return {
        'status': 'sent' if sent > 0 else 'failed_send',
        'recipient': recipient_email,
        'club_name': club_name,
        'attempted_at': datetime.now().isoformat(),
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
def process_pbvision_results(self, job_id):
    """
    Task 2: Process PB Vision JSON output through Python pipeline.
    
    Triggered after user selects their player index.
    Fetches pbvision_response and selected_player_index from database,
    creates isolated job directory, runs pipeline orchestrator, and saves results.
    
    Args:
        job_id: VideoJob primary key
    
    Returns:
        dict: Pipeline output summary
    """
    try:
        job = VideoJob.objects.get(id=job_id)
        logger.info(f"[Job {job_id}] Starting Python pipeline with PB Vision data from database")
        
        # Fetch PB Vision response from database
        pbvision_json = job.pbvision_response
        if not pbvision_json:
            raise ValueError(f"Job {job_id} has no pbvision_response in database")
        
        # Fetch selected player index
        selected_player_index = job.selected_player_index
        if selected_player_index is None:
            raise ValueError(f"Job {job_id} has no selected_player_index")
        
        logger.info(
            f"[Job {job_id}] Fetched data from database: "
            f"selected_player_index={selected_player_index}"
        )
        
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
            video_url=source_video_url,
            selected_player_index=selected_player_index  # Pass the user's selection
        )
        logger.info(f"[Job {job_id}] Pipeline output summary: {pipeline_output}")
        logger.info(f"[Job {job_id}] Pipeline completed successfully")
        
        # Store intermediate pipeline results.
        # Do not mark COMPLETED yet; deliver_results will finalize deliverables first.
        job.result_json = {
            'pbvision': pbvision_json,
            'pipeline_output': pipeline_output,
        }
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
    Task 3: Finalize deliverables and dispatch completion email.
    
    Called after process_pbvision_results completes (chained task).
    Handles final packaging metadata, best-effort email delivery, and cleanup.
    
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
        deliverables_payload = result_payload.get('deliverables') or {}

        existing_email_delivery = deliverables_payload.get('email_delivery')
        email_already_sent = (
            isinstance(existing_email_delivery, dict)
            and existing_email_delivery.get('status') == 'sent'
        )

        email_enabled = getattr(settings, 'EMAIL_DELIVERY_ENABLED', True)
        max_attachment_bytes = getattr(
            settings,
            'EMAIL_DELIVERY_MAX_ATTACHMENT_BYTES',
            25 * 1024 * 1024,
        )

        if not email_enabled:
            email_delivery = {
                'status': 'skipped_disabled',
                'recipient': user_email,
                'attempted_at': datetime.now().isoformat(),
                'sent_at': None,
                'error': 'email_delivery_disabled',
            }
        elif email_already_sent:
            email_delivery = existing_email_delivery
            logger.info(f"[Job {job_id}] Skipping email dispatch: already sent")
        else:
            try:
                email_delivery = send_delivery_email_with_attachments(
                    recipient_email=user_email,
                    zipfiles=zipfiles,
                    job_id=job.id,
                    job_name=job.name,
                    selected_player_index=job.selected_player_index,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    max_total_attachment_bytes=max_attachment_bytes,
                )
                logger.info(
                    f"[Job {job_id}] Email delivery status={email_delivery.get('status')} "
                    f"recipient={user_email}"
                )
            except Exception as e:
                logger.warning(
                    f"[Job {job_id}] Email delivery failed unexpectedly: {str(e)}",
                    exc_info=True,
                )
                email_delivery = {
                    'status': 'failed_send',
                    'recipient': user_email,
                    'attempted_at': datetime.now().isoformat(),
                    'sent_at': None,
                    'error': str(e),
                    'job_id': job.id,
                    'job_name': job.name,
                    'selected_player_index': job.selected_player_index,
                }

        result_payload['deliverables'] = {
            **deliverables_payload,
            'zipfiles': zipfiles,
            'master_zip': master_zip,
            'generated_at': datetime.now().isoformat(),
            'email_delivery': email_delivery,
        }
        job.result_json = result_payload
        job.completed_at = datetime.now()
        job.status = 'COMPLETED'

        if job.video_file and not PRESERVE_SOURCE_VIDEO:
            try:
                job.video_file.delete(save=False)
                job.video_file = ''
                job.video_url = None
                logger.info(f"[Job {job_id}] Deleted source video from storage after successful delivery")
            except Exception:
                logger.warning(f"[Job {job_id}] Failed to delete source video", exc_info=True)
        elif job.video_file:
            logger.info(f"[Job {job_id}] Preserving source video (PRESERVE_SOURCE_VIDEO=true)")

        if CLEANUP_ON_DELIVERY:
            _cleanup_job_temp_dirs(job_dir)
        else:
            logger.info(f"[Job {job_id}] Temp directory cleanup disabled (CLEANUP_ON_DELIVERY=false)")

        email_status = email_delivery.get('status') if isinstance(email_delivery, dict) else 'unknown'
        email_error = email_delivery.get('error') if isinstance(email_delivery, dict) else None
        log_suffix = f" email_status={email_status}"
        if email_error:
            log_suffix += f" email_error={email_error}"

        job.logs += f'\n[{datetime.now().isoformat()}] Delivery task completed;{log_suffix}'
        job.save()

        logger.info(
            f"[Job {job_id}] Delivery completed zip_count={len(zipfiles)} "
            f"email_status={email_status}"
        )
        return {
            'status': 'delivered',
            'job_id': job_id,
            'zip_count': len(zipfiles),
            'email_status': email_status,
        }
        
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
