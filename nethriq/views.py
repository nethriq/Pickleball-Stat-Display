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
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from django.db.models import Q
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from django.shortcuts import render

from .models import VideoJob, AuthToken, UserProfile
from .tasks import upload_to_pbvision, send_stub_claim_email

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
CLAIM_SIGNER_SALT = 'nethriq.stub-claim'


def create_stub_claim_token(user: User) -> str:
    """Create a signed claim token for a stub account using Django signer."""
    signer = TimestampSigner(salt=CLAIM_SIGNER_SALT)
    return signer.sign(str(user.id))


def resolve_stub_claim_token(token: str) -> Optional[User]:
    """Resolve a signed claim token to a user if valid and unexpired."""
    signer = TimestampSigner(salt=CLAIM_SIGNER_SALT)
    max_age = getattr(settings, 'CLAIM_LINK_TTL_SECONDS', 86400)

    try:
        user_id = signer.unsign(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

    try:
        return User.objects.get(id=int(user_id))
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def _request_client_ip(request) -> Optional[str]:
    """Extract best-effort client IP for lightweight audit trails."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def build_claim_url(claim_token: str) -> str:
    """Build absolute claim URL from configured base and token."""
    claim_url_base = getattr(settings, 'CLAIM_URL_BASE', '').strip() or DJANGO_BASE_URL
    return f"{claim_url_base.rstrip('/')}/claim/?token={claim_token}"


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
            'email': user.email,
            'is_stub': is_stub_user(user),
            'role': get_user_role(user),
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
        'email': user.email,
        'is_stub': is_stub_user(user),
        'role': get_user_role(user),
    })


@csrf_exempt
@require_POST
def claim_verify(request):
    """Verify signed claim token and issue an auth token for one-click login."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    claim_token = (data.get('token') or '').strip()
    if not claim_token:
        return JsonResponse({'error': 'token is required'}, status=400)

    signer = TimestampSigner(salt=CLAIM_SIGNER_SALT)
    max_age = getattr(settings, 'CLAIM_LINK_TTL_SECONDS', 86400)

    try:
        user_id = signer.unsign(claim_token, max_age=max_age)
    except SignatureExpired:
        return JsonResponse({'error': 'Claim link has expired'}, status=400)
    except BadSignature:
        return JsonResponse({'error': 'Invalid claim token'}, status=400)

    try:
        user = User.objects.get(id=int(user_id))
    except (User.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid claim token'}, status=400)

    profile = getattr(user, 'profile', None)
    if not profile or not profile.is_stub:
        return JsonResponse({'error': 'Account is already claimed'}, status=400)

    token = SimpleAuthToken.create_token(user)

    return JsonResponse({
        'token': token,
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'is_stub': True,
        'role': get_user_role(user),
    })


@csrf_exempt
@require_POST
def set_password(request):
    """Set password for authenticated user and convert stub to active account."""
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    profile = getattr(user, 'profile', None)
    if not profile or not profile.is_stub:
        return JsonResponse({'error': 'Password setup is only allowed for unclaimed stub users'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    new_password = data.get('new_password')
    if not new_password:
        return JsonResponse({'error': 'new_password is required'}, status=400)

    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    user.set_password(new_password)
    user.save(update_fields=['password'])

    profile.is_stub = False
    profile.claimed_at = timezone.now()
    profile.claim_source_ip = _request_client_ip(request)
    profile.save(update_fields=['is_stub', 'claimed_at', 'claim_source_ip'])

    token = SimpleAuthToken.create_token(user)

    return JsonResponse({
        'status': 'success',
        'token': token,
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'is_stub': False,
        'role': get_user_role(user),
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


def get_user_role(user: User) -> str:
    """Resolve app role from Django auth flags for RBAC checks."""
    if user.is_superuser:
        return 'admin'
    if user.is_staff:
        return 'attendant'
    return 'player'


def is_attendant(user: User) -> bool:
    """Return True when user has attendant-level access."""
    return get_user_role(user) in {'attendant', 'admin'}


def is_stub_user(user: User) -> bool:
    """Return True when the user's profile marks them as a stub account."""
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.is_stub)


def _build_stub_username(seed_text: str) -> str:
    """Build a unique, Django-safe username for quick stub account creation."""
    base = ''.join(ch.lower() if ch.isalnum() else '_' for ch in seed_text).strip('_')
    if not base:
        base = 'player'
    base = base[:20]

    while True:
        candidate = f"{base}_{secrets.token_hex(3)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


def _get_accessible_job_for_user(user: User, job_id: int) -> Optional[VideoJob]:
    """Return job if user can access it, else None."""
    query = VideoJob.objects.filter(id=job_id)
    if not is_attendant(user):
        query = query.filter(user=user)
    return query.first()


def extract_active_player_indices(pbvision_response):
    """Return sorted PB Vision player indices that contain actual player data."""
    insights = (pbvision_response or {}).get('insights', {})
    player_data = insights.get('player_data') or []

    player_data_indices = [
        idx for idx, player in enumerate(player_data)
        if isinstance(player, dict)
    ]

    # Fallback for payload variants missing player_data: infer from rally shot ownership.
    rally_indices = set()
    for rally in insights.get('rallies', []):
        for shot in rally.get('shots', []):
            player_id = shot.get('player_id')
            if isinstance(player_id, int):
                rally_indices.add(player_id)

    # Use the union so sparse singles payloads (e.g. player_data partial + rallies 0/2)
    # still return all truly active players.
    return sorted(set(player_data_indices).union(rally_indices))


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

    role = get_user_role(user)
    owner_user = user
    uploader_user = None

    if is_attendant(user):
        player_id_raw = request.POST.get('player_id') or request.POST.get('target_player_id')
        if not player_id_raw:
            return JsonResponse({'error': 'player_id is required for attendant uploads'}, status=400)

        try:
            player_id = int(player_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'player_id must be an integer'}, status=400)

        try:
            owner_user = User.objects.get(id=player_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Invalid player_id. Please choose a valid player from search results.'}, status=400)

        if owner_user.is_staff or owner_user.is_superuser:
            return JsonResponse({'error': 'Attendant uploads must target a non-staff player account'}, status=400)

        uploader_user = user

    try:
        # Create VideoJob record
        job = VideoJob.objects.create(
            user=owner_user,
            uploader=uploader_user,
            video_file=video_file,
            name=name,
            filename=video_file.name,
            file_size=video_file.size,
            status='PENDING'
        )
        
        logger.info(
            f"[Upload] Job {job.id} created for owner {owner_user.username} "
            f"by uploader {user.username}: "
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
            'owner_user_id': owner_user.id,
            'uploader_user_id': uploader_user.id if uploader_user else None,
            'request_user_role': role,
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
def list_global_jobs(request):
    """
    GET /api/jobs/global/
    Headers: Authorization: Token <token>
    Staff-only endpoint for the attendant global dashboard.
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    if not is_attendant(user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    jobs = VideoJob.objects.select_related('user', 'uploader').values(
        'id',
        'name',
        'filename',
        'status',
        'uploaded_at',
        'completed_at',
        'user_id',
        'user__username',
        'uploader_id',
        'uploader__username',
    ).order_by('-uploaded_at')

    return JsonResponse({
        'jobs': list(jobs),
        'count': len(jobs),
    })


@require_http_methods(["GET"])
def search_players(request):
    """
    GET /api/players/search/?q=<query>
    Headers: Authorization: Token <token>
    Staff-only endpoint for player lookup in attendant flow.
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    if not is_attendant(user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    query = (request.GET.get('q') or '').strip()
    if len(query) < 2:
        return JsonResponse({'error': 'Query must be at least 2 characters'}, status=400)

    players = User.objects.filter(
        Q(is_staff=False),
        Q(is_superuser=False),
    ).filter(
        Q(username__icontains=query)
        | Q(email__icontains=query)
        | Q(first_name__icontains=query)
    ).order_by('username')[:25]

    return JsonResponse({
        'players': [
            {
                'id': player.id,
                'username': player.username,
                'email': player.email,
                'name': player.first_name or player.username,
            }
            for player in players
        ],
        'count': players.count(),
    })


@require_http_methods(["GET"])
def get_job_status(request, job_id):
    """
    GET /api/jobs/<job_id>/status
    Headers: Authorization: Token <token>
    Returns: {"id": ..., "status": "...", "result_json": ..., "pbvision_response": ..., "thumbnail_urls": ...}
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    job = _get_accessible_job_for_user(user, job_id)
    if not job:
        return JsonResponse({'error': 'Job not found'}, status=404)

    return JsonResponse({
        'id': job.id,
        'name': job.name,
        'status': job.status,
        'uploaded_at': job.uploaded_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'result_json': job.result_json,
        'pbvision_response': job.pbvision_response,
        'thumbnail_urls': job.thumbnail_urls,
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

    job = _get_accessible_job_for_user(user, job_id)
    if not job:
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

    job = _get_accessible_job_for_user(user, job_id)
    if not job:
        return JsonResponse({'error': 'Job not found'}, status=404)

    if job.status != 'COMPLETED':
        return JsonResponse(
            {'error': f'Job is {job.status}. Only COMPLETED jobs can be downloaded.'},
            status=400
        )

    deliverables = (job.result_json or {}).get('deliverables')
    if not deliverables:
        return JsonResponse({'error': 'No deliverables available for this job'}, status=400)

    zip_meta = next(
        (z for z in deliverables.get('zipfiles', []) if str(z.get('id')) == str(zip_id)),
        None,
    )
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

    job = _get_accessible_job_for_user(user, job_id)
    if not job:
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
        job.status = 'AWAITING_PLAYER_SELECTION'  # Changed: pause for player selection
        job.save()
        logger.info(
            f"[Job {job_id}] PB Vision response stored. "
            f"Status set to AWAITING_PLAYER_SELECTION (legacy webhook path)."
        )
    except Exception as e:
        logger.error(f"[Job {job_id}] Error storing PB Vision response: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    # 7. Note: Pipeline processing will be triggered when user selects their player
    # via the POST /api/jobs/<job_id>/select-player/ endpoint
    logger.warning(
        f"[Job {job_id}] Legacy webhook path used. "
        f"User must select player to continue processing."
    )

    # 8. Acknowledge receipt immediately to close the connection
    return JsonResponse({
        'status': 'received', 
        'job_id': job_id,
        'message': 'Data saved. Awaiting player selection to start processing.'
    })


# ============================================================================
# Internal Node Server Webhook Endpoint
# ============================================================================

@csrf_exempt
@require_POST
def save_pbvision_results_internal(request, job_id):
    """
    POST /api/internal/jobs/<job_id>/save-results/
    Internal endpoint for Node server to POST PB Vision data and thumbnails.
    Validates via Authorization bearer token (webhook_signature_secret).
    
    Body: {
        "pbvision_response": {...},
        "thumbnail_urls": [{"playerIndex": 0, "url": "..."}, ...]
    }
    
    Does NOT trigger Celery. Instead, pauses the pipeline and waits for user
    to identify themselves (select which player they are) before processing.
    """
    # 1. Retrieve the job
    try:
        job = VideoJob.objects.get(id=job_id)
    except VideoJob.DoesNotExist:
        logger.warning(f"[Job {job_id}] Save results rejected: Job not found")
        return JsonResponse({'error': 'Job not found'}, status=404)

    # 2. Validate the internal Bearer Token for security
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        logger.warning(f"[Job {job_id}] Save results rejected: Missing bearer token")
        return JsonResponse({'error': 'Missing or invalid token'}, status=401)

    token = auth_header.split(' ')[1]
    if not hmac.compare_digest(token, str(job.webhook_signature_secret)):
        logger.warning(f"[Job {job_id}] Save results rejected: Token mismatch")
        return JsonResponse({'error': 'Unauthorized: Token mismatch'}, status=403)

    # 3. Enforce Idempotency - if we already have the response, don't overwrite it
    if job.pbvision_response is not None:
        logger.info(f"[Job {job_id}] Save results ignored: Data already saved")
        return JsonResponse({'message': 'Job data already saved'}, status=200)

    # 4. Parse the incoming JSON from Node
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error(f"[Job {job_id}] Save results error: Invalid JSON payload")
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    # 5. Save data to the database
    try:
        job.pbvision_response = data.get('pbvision_response')

        active_indices = set(extract_active_player_indices(job.pbvision_response))
        incoming_thumbnails = data.get('thumbnail_urls', [])
        if active_indices:
            job.thumbnail_urls = [
                thumb for thumb in incoming_thumbnails
                if isinstance(thumb, dict) and thumb.get('playerIndex') in active_indices
            ]
        else:
            job.thumbnail_urls = incoming_thumbnails
        
        # 6. Create the "Pause" state
        # Do NOT trigger Celery here. Change status so the frontend knows to prompt the user.
        job.status = 'AWAITING_PLAYER_SELECTION'
        job.save()
        
        logger.info(
            f"[Job {job_id}] PB Vision data and thumbnails saved. "
            f"Pipeline paused for user identification."
        )
    except Exception as e:
        logger.error(f"[Job {job_id}] Error saving results: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'status': 'success',
        'message': 'PB Vision data and thumbnails saved. Pipeline paused for user identification.',
        'job_id': job_id
    })


# ============================================================================
# Player Selection & Pipeline Trigger Endpoint
# ============================================================================

@csrf_exempt
@require_POST
def select_player_and_process(request, job_id):
    """
    POST /api/jobs/<job_id>/select-player/
    Headers: Authorization: Token <token>
    Body: {"playerIndex": 2}
    
    Accepts the user's player identification, saves their selection,
    updates job status, and triggers the Celery pipeline.
    """
    # 1. Authenticate the user
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    # 2. Retrieve and verify access to the job
    job = _get_accessible_job_for_user(user, job_id)
    if not job:
        logger.warning(f"[Job {job_id}] Player selection rejected: Job not found or unauthorized")
        return JsonResponse({'error': 'Job not found'}, status=404)

    # 3. Verify job is in the correct state
    if job.status != 'AWAITING_PLAYER_SELECTION':
        logger.warning(
            f"[Job {job_id}] Player selection rejected: "
            f"Job is {job.status}, expected AWAITING_PLAYER_SELECTION"
        )
        return JsonResponse({
            'error': f'Invalid state. Job is currently {job.status}, expected AWAITING_PLAYER_SELECTION.'
        }, status=400)

    # 4. Parse and validate the request body
    try:
        data = json.loads(request.body)
        player_index = data.get('playerIndex')
        
        if player_index is None or not isinstance(player_index, int):
            return JsonResponse(
                {'error': 'Valid playerIndex (integer) is required.'}, 
                status=400
            )
        
        # Validate playerIndex is in valid range (0-3)
        if player_index < 0 or player_index > 3:
            return JsonResponse(
                {'error': 'playerIndex must be between 0 and 3.'}, 
                status=400
            )

        active_player_indices = extract_active_player_indices(job.pbvision_response)
        if active_player_indices and player_index not in active_player_indices:
            logger.warning(
                f"[Job {job_id}] Player selection rejected: "
                f"playerIndex {player_index} not in active indices {active_player_indices}"
            )
            return JsonResponse(
                {
                    'error': 'Selected player has no PB Vision data for this match.',
                    'valid_player_indices': active_player_indices,
                },
                status=400,
            )

    except json.JSONDecodeError:
        logger.error(f"[Job {job_id}] Player selection error: Invalid JSON body")
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    # 5. Save the user's selection and update status
    try:
        job.selected_player_index = player_index
        job.status = 'PROCESSING'
        job.save()
        
        logger.info(
            f"[Job {job_id}] User selected playerIndex {player_index}. "
            f"Status changed to PROCESSING."
        )
    except Exception as e:
        logger.error(f"[Job {job_id}] Error saving player selection: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

    # 6. Trigger the Celery Task
    # Pass only job_id so Celery fetches pbvision_response and selected_player_index from DB
    try:
        from .tasks import process_pbvision_results
        task = process_pbvision_results.delay(job.id)
        job.task_id = task.id
        job.save()
        
        logger.info(
            f"[Job {job_id}] Celery task {task.id} triggered for processing."
        )
    except Exception as e:
        logger.error(f"[Job {job_id}] Error triggering Celery task: {str(e)}")
        return JsonResponse(
            {'error': 'Failed to start processing pipeline'}, 
            status=500
        )

    return JsonResponse({
        'status': 'success',
        'message': 'Player selected successfully. Processing pipeline started.',
        'job_id': job.id,
        'selected_player_index': player_index,
        'task_id': task.id
    })


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

    job = _get_accessible_job_for_user(user, job_id)
    if not job:
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


@csrf_exempt
@require_POST
def create_player_stub(request):
    """
    POST /api/players/stub/
    Headers: Authorization: Token <token>
    Body: {"name": "Player Name", "email": "player@example.com"}
    Creates a quick player account with generated username/password.
    """
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    if not is_attendant(user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()

    if not name or not email:
        return JsonResponse({'error': 'name and email are required'}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({'error': 'A user with this email already exists'}, status=409)

    username = _build_stub_username(f"{name}_{email.split('@')[0]}")
    random_password = secrets.token_urlsafe(12)

    try:
        player_user = User.objects.create_user(
            username=username,
            email=email,
            password=random_password,
            first_name=name,
        )

        UserProfile.objects.update_or_create(
            user=player_user,
            defaults={
                'is_stub': True,
                'stub_created_by': user,
                'stub_created_at': timezone.now(),
                'claimed_at': None,
                'claim_source_ip': None,
            },
        )

        claim_token = create_stub_claim_token(player_user)
        SimpleAuthToken.create_token(player_user)
    except IntegrityError:
        return JsonResponse({'error': 'Failed to create stub player'}, status=500)

    claim_url = build_claim_url(claim_token)

    try:
        send_stub_claim_email.delay(
            recipient_email=player_user.email,
            player_name=player_user.first_name or player_user.username,
            claim_url=claim_url,
        )
    except Exception:
        logger.warning(
            f"[StubCreate] Failed to enqueue claim email for user={player_user.id}",
            exc_info=True,
        )

    return JsonResponse({
        'player_id': player_user.id,
        'username': player_user.username,
        'email': player_user.email,
        'temporary_password': random_password,
        'is_stub': True,
        'claim_expires_in_seconds': getattr(settings, 'CLAIM_LINK_TTL_SECONDS', 86400),
        'claim_url': claim_url,
        'role': get_user_role(player_user),
        'created_by': user.username,
    }, status=201)


@csrf_exempt
@require_POST
def resend_stub_claim(request):
    """Resend claim email for an existing unclaimed stub user (attendant/admin only)."""
    user, auth_error = get_authenticated_user(request)
    if auth_error:
        return auth_error

    if not is_attendant(user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    email = (data.get('email') or '').strip().lower()
    if not email:
        return JsonResponse({'error': 'email is required'}, status=400)

    try:
        player_user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'error': 'No user found for this email'}, status=404)

    profile = getattr(player_user, 'profile', None)
    if not profile or not profile.is_stub:
        return JsonResponse({'error': 'This account is already claimed or is not a stub'}, status=400)

    claim_token = create_stub_claim_token(player_user)
    claim_url = build_claim_url(claim_token)

    try:
        send_stub_claim_email.delay(
            recipient_email=player_user.email,
            player_name=player_user.first_name or player_user.username,
            claim_url=claim_url,
        )
    except Exception:
        logger.warning(
            f"[StubClaimResend] Failed to enqueue claim email for user={player_user.id}",
            exc_info=True,
        )
        return JsonResponse({'error': 'Failed to queue claim email'}, status=500)

    return JsonResponse({
        'status': 'queued',
        'message': 'Claim email has been queued for delivery.',
        'email': player_user.email,
        'claim_expires_in_seconds': getattr(settings, 'CLAIM_LINK_TTL_SECONDS', 86400),
        'queued_by': user.username,
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
