import os
import json
import hmac
import logging
import secrets
from typing import Tuple, Optional
from django.http import JsonResponse, HttpResponseForbidden, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.utils import timezone
from django.conf import settings
from django.shortcuts import render

from .models import VideoJob, AuthToken
from .tasks import upload_to_pbvision

logger = logging.getLogger(__name__)


# ============================================================================
# Database-Backed Token Management (No In-Memory Store)
# ============================================================================

class SimpleAuthToken:
    """
    Token management using Django database.
    Safe for multi-worker deployments (Gunicorn, etc) and persistent across restarts.
    """
    
    @staticmethod
    def create_token(user):
        """Generate and store a new token for a user in the database"""
        # Delete existing token if present (one token per user)
        AuthToken.objects.filter(user=user).delete()
        
        # Create new token
        token_obj = AuthToken.objects.create(user=user)
        return token_obj.token
    
    @staticmethod
    def get_user_from_token(token):
        """Retrieve user associated with token from database"""
        try:
            token_obj = AuthToken.objects.get(token=token)
            return token_obj.user
        except AuthToken.DoesNotExist:
            return None


# ============================================================================
# Environment & Configuration
# ============================================================================

DJANGO_BASE_URL = os.getenv('DJANGO_BASE_URL', 'http://localhost:8000')


# ============================================================================
# Authentication Endpoints
# ============================================================================

@csrf_exempt
@require_POST
def register(request):
    """
    POST /api/register/
    Body: {"username": "user", "password": "pass", "email": "user@example.com"}
    Returns: {"token": "...", "user_id": ..., "username": "..."}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = data.get('username')
    password = data.get('password')
    email = data.get('email', '')

    if not username or not password:
        return JsonResponse(
            {'error': 'username and password are required'}, 
            status=400
        )

    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email
        )
        token = SimpleAuthToken.create_token(user)
        
        logger.info(f"[Auth] User registered: {username} (ID: {user.id})")
        
        return JsonResponse({
            'token': token,
            'user_id': user.id,
            'username': user.username,
            'email': user.email
        }, status=201)
    
    except IntegrityError:
        return JsonResponse(
            {'error': 'Username already exists'}, 
            status=409
        )


@csrf_exempt
@require_POST
def login(request):
    """
    POST /api/login/
    Body: {"username": "user", "password": "pass"}
    Returns: {"token": "...", "user_id": ..., "username": "..."}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return JsonResponse(
            {'error': 'username and password are required'}, 
            status=400
        )

    user = authenticate(username=username, password=password)
    
    if not user:
        logger.warning(f"[Auth] Failed login attempt for user: {username}")
        return JsonResponse(
            {'error': 'Invalid credentials'}, 
            status=401
        )

    token = SimpleAuthToken.create_token(user)
    
    logger.info(f"[Auth] User logged in: {username} (ID: {user.id})")
    
    return JsonResponse({
        'token': token,
        'user_id': user.id,
        'username': user.username,
        'email': user.email
    })


def get_authenticated_user(request) -> Tuple[Optional[User], Optional[JsonResponse]]:
    """
    Helper function to extract & validate the authenticated user from request.
    Expects Authorization header: "Token <token>"
    Returns (User, None) or (None, JsonResponse) if auth fails
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    
    if not auth_header.startswith('Token '):
        return None, JsonResponse(
            {'error': 'Missing or invalid Authorization header'}, 
            status=401
        )
    
    token_key = auth_header.split(' ')[1]
    user = SimpleAuthToken.get_user_from_token(token_key)
    
    if not user:
        return None, JsonResponse(
            {'error': 'Invalid token'}, 
            status=401
        )
    
    return user, None


# ============================================================================
# Video Upload Endpoint
# ============================================================================

@csrf_exempt
@require_POST
def upload_video(request):
    """
    POST /api/upload/
    Form data: video_file (required), name (optional)
    Headers: Authorization: Token <token>
    Returns: {"job_id": ..., "status": "PENDING", "webhook_secret": "..."}
    """
    # Authenticate user
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    # Check for video file
    if 'video_file' not in request.FILES:
        return JsonResponse({'error': 'video_file is required'}, status=400)

    video_file = request.FILES['video_file']
    name = request.POST.get('name', video_file.name)

    try:
        # Create VideoJob record
        job = VideoJob.objects.create(
            user=user,
            video_file=video_file,
            name=name,
            filename=video_file.name,
            file_size=video_file.size,
            status='PENDING'
        )
        
        logger.info(
            f"[Upload] Job {job.id} created for user {user.username}: "
            f"{video_file.name} ({video_file.size} bytes)"
        )

        # Set video_url to the actual file path for pipeline processing
        try:
            # Local FileSystemStorage uses .path
            video_file_path = job.video_file.path 
        except NotImplementedError:
            # S3 / Remote storage throws an error on .path, so use .url
            video_file_path = job.video_file.url
        
        # Store the path in video_url for use in process_pbvision_results
        job.video_url = video_file_path
        job.save()
        
        logger.info(
            f"[Upload] Job {job.id} video_url set to: {video_file_path}"
        )

        # Trigger async task to upload to PB Vision
        # Get the correct file location (Path for local dev, URL for S3)
        try:
            # Local FileSystemStorage uses .path
            file_target = job.video_file.path 
        except NotImplementedError:
            # S3 / Remote storage throws an error on .path, so use .url
            file_target = job.video_file.url

        # Trigger async task to upload to PB Vision with BOTH arguments
        upload_to_pbvision.delay(job.id, file_target)
        return JsonResponse({
            'job_id': job.id,
            'status': job.status,
            'webhook_secret': job.webhook_signature_secret,
            'message': 'Video uploaded. Processing will begin shortly.'
        }, status=201)

    except Exception as e:
        logger.error(f"[Upload] Error creating job: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# Job Management Endpoints
# ============================================================================

@require_http_methods(["GET"])
def list_jobs(request):
    """
    GET /api/jobs/
    Headers: Authorization: Token <token>
    Returns: [{"id": ..., "name": "...", "status": "...", ...}]
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    jobs = VideoJob.objects.filter(user=user).values(
        'id', 'name', 'filename', 'status', 'uploaded_at', 'completed_at'
    )

    return JsonResponse({
        'jobs': list(jobs),
        'count': len(jobs)
    })


@require_http_methods(["GET"])
def get_job_status(request, job_id):
    """
    GET /api/jobs/<job_id>/status
    Headers: Authorization: Token <token>
    Returns: {"id": ..., "status": "...", "result_json": ..., "pbvision_response": ...}
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    try:
        job = VideoJob.objects.get(id=job_id, user=user)
    except VideoJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    return JsonResponse({
        'id': job.id,
        'name': job.name,
        'status': job.status,
        'uploaded_at': job.uploaded_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'result_json': job.result_json,
        'pbvision_response': job.pbvision_response,
        'error_message': job.error_message,
        'retry_count': job.retry_count
    })


@require_http_methods(["GET"])
def download_job_results(request, job_id):
    """
    GET /api/jobs/<job_id>/download
    Headers: Authorization: Token <token>
    Returns: Deliverables metadata for completed jobs
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    try:
        job = VideoJob.objects.get(id=job_id, user=user)
    except VideoJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    # Check if job has results
    if job.status != 'COMPLETED':
        return JsonResponse(
            {'error': f'Job is {job.status}. Only COMPLETED jobs can be downloaded.'},
            status=400
        )

    deliverables = (job.result_json or {}).get('deliverables')
    if not deliverables:
        return JsonResponse(
            {'error': 'No deliverables available for this job'},
            status=400
        )

    return JsonResponse({'deliverables': deliverables})


@require_http_methods(["GET"])
def download_job_zip(request, job_id, zip_id):
    """
    GET /api/jobs/<job_id>/download-zip/<zip_id>/
    Headers: Authorization: Token <token>
    Returns: Zipfile binary download
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    try:
        job = VideoJob.objects.get(id=job_id, user=user)
    except VideoJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    if job.status != 'COMPLETED':
        return JsonResponse(
            {'error': f'Job is {job.status}. Only COMPLETED jobs can be downloaded.'},
            status=400
        )

    deliverables = (job.result_json or {}).get('deliverables')
    if not deliverables:
        return JsonResponse({'error': 'No deliverables available for this job'}, status=400)

    zip_meta = next((z for z in deliverables.get('zipfiles', []) if z.get('id') == zip_id), None)
    if not zip_meta:
        return JsonResponse({'error': 'Zipfile not found'}, status=404)

    job_dir = os.path.join(settings.BASE_DIR, 'data', f'job_{job_id}')
    deliveries_dir = os.path.join(job_dir, 'deliveries')
    safe_name = os.path.basename(zip_meta.get('name', ''))
    file_path = os.path.join(deliveries_dir, safe_name)

    if not safe_name or not os.path.isfile(file_path):
        return JsonResponse({'error': 'Zipfile missing on server'}, status=404)

    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=safe_name)
    response['Content-Type'] = 'application/zip'
    return response


@require_http_methods(["GET"])
def download_job_all(request, job_id):
    """
    GET /api/jobs/<job_id>/download-all/
    Headers: Authorization: Token <token>
    Returns: Master zipfile binary download
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    try:
        job = VideoJob.objects.get(id=job_id, user=user)
    except VideoJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    if job.status != 'COMPLETED':
        return JsonResponse(
            {'error': f'Job is {job.status}. Only COMPLETED jobs can be downloaded.'},
            status=400
        )

    deliverables = (job.result_json or {}).get('deliverables')
    if not deliverables or not deliverables.get('master_zip'):
        return JsonResponse({'error': 'No bundled zip available for this job'}, status=400)

    master_zip = deliverables['master_zip']
    job_dir = os.path.join(settings.BASE_DIR, 'data', f'job_{job_id}')
    deliveries_dir = os.path.join(job_dir, 'deliveries')
    safe_name = os.path.basename(master_zip.get('name', ''))
    file_path = os.path.join(deliveries_dir, safe_name)

    if not safe_name or not os.path.isfile(file_path):
        return JsonResponse({'error': 'Bundled zip missing on server'}, status=404)

    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=safe_name)
    response['Content-Type'] = 'application/zip'
    return response


# ============================================================================
# Webhook Endpoint
# ============================================================================

@csrf_exempt
@require_POST
def pbvision_webhook(request, job_id):
    """
    POST /api/webhook/pbvision/<job_id>/?token=<webhook_signature_secret>
    Receives PB Vision JSON, validates signature, and triggers pipeline task.
    """
    # 1. Extract the token from the query string
    incoming_token = request.GET.get('token')
    
    if not incoming_token:
        logger.warning(f"[Job {job_id}] Webhook rejected: Missing token")
        return HttpResponseForbidden("Missing webhook token")

    # 2. Retrieve the job
    try:
        job = VideoJob.objects.get(id=job_id)
    except VideoJob.DoesNotExist:
        logger.warning(f"[Job {job_id}] Webhook rejected: Job not found")
        return JsonResponse({'error': 'Job not found'}, status=404)

    # 3. Securely validate the token (prevent timing attacks)
    expected_token = str(job.webhook_signature_secret)
    if not hmac.compare_digest(incoming_token, expected_token):
        logger.warning(f"[Job {job_id}] Webhook rejected: Invalid token signature")
        return HttpResponseForbidden("Invalid webhook token")

    # 4. Enforce Idempotency (prevent duplicate processing)
    if job.status in ['COMPLETED', 'FAILED']:
        logger.info(
            f"[Job {job_id}] Webhook ignored: Job already in {job.status} state"
        )
        # Return 200 OK so PB Vision stops retrying
        return JsonResponse({
            'status': 'ignored',
            'reason': f'Job already {job.status}'
        })

    # 5. Parse the JSON payload
    try:
        pbvision_json = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error(f"[Job {job_id}] Webhook error: Invalid JSON payload")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # 6. Store the PB Vision response
    try:
        job.pbvision_response = pbvision_json
        job.status = 'PROCESSING'
        job.save()
        logger.info(
            f"[Job {job_id}] PB Vision response stored. "
            f"Triggering process_pbvision_results task."
        )
    except Exception as e:
        logger.error(f"[Job {job_id}] Error storing PB Vision response: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    # 7. Trigger the pipeline processing task
    from .tasks import process_pbvision_results
    process_pbvision_results.delay(job_id, pbvision_json)

    # 8. Acknowledge receipt immediately to close the connection
    return JsonResponse({'status': 'received', 'job_id': job_id})


# ============================================================================
# Health & Debug Endpoints
# ============================================================================

@require_http_methods(["GET"])
def health_check(request):
    """
    GET /api/health/
    Simple health check endpoint
    """
    return JsonResponse({'status': 'healthy'})


@require_http_methods(["GET"])
def debug_webhook_url(request, job_id):
    """
    GET /api/debug/webhook-url/<job_id>/
    Returns the formatted webhook URL for testing (requires user auth)
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    try:
        job = VideoJob.objects.get(id=job_id, user=user)
    except VideoJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    webhook_url = (
        f"{DJANGO_BASE_URL}/api/webhook/pbvision/{job_id}/"
        f"?token={job.webhook_signature_secret}"
    )

    return JsonResponse({
        'webhook_url': webhook_url,
        'job_id': job_id,
        'status': job.status
    })


# ============================================================================
# Frontend Views
# ============================================================================

@require_http_methods(["GET"])
def serve_frontend(request):
    """
    Serve the single-page application (index.html).
    Used for frontend routing and initial page load.
    """
    return render(request, 'index.html')
