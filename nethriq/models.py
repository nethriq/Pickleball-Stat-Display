from django.db import models
from django.contrib.auth.models import User
import secrets


def generate_token():
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


class AuthToken(models.Model):
    """
    Store authentication tokens in the database.
    Works across multiple Gunicorn worker processes and persists across restarts.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='auth_token')
    token = models.CharField(
        max_length=64, 
        unique=True, 
        default=generate_token,
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token for {self.user.username}"

    class Meta:
        verbose_name = "Authentication Token"
        verbose_name_plural = "Authentication Tokens"


class UserProfile(models.Model):
    """Lifecycle metadata for app-specific account onboarding state."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_stub = models.BooleanField(default=False, db_index=True)
    stub_created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_stub_profiles',
        help_text='Attendant/admin who created this stub account.',
    )
    stub_created_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_source_ip = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"Profile for {self.user.username}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


class VideoJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('AWAITING_PLAYER_SELECTION', 'Awaiting Player Selection'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    # Basic file & upload info
    video_file = models.FileField(upload_to='videos/')
    filename = models.CharField(max_length=255, blank=True)  # Original filename from upload
    file_size = models.BigIntegerField(null=True, blank=True)  # Size in bytes
    video_url = models.URLField(
        max_length=1000, 
        blank=True, 
        null=True,
        help_text="S3 URL for production, or absolute local path for testing."
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Job tracking & naming
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_video_jobs')
    uploader = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_video_jobs',
        help_text='Attendant who uploaded on behalf of the owner. Null when owner uploaded directly.'
    )
    
    # Status tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results & error handling
    result_json = models.JSONField(null=True, blank=True)  # Store pipeline output here
    pbvision_response = models.JSONField(null=True, blank=True)  # Store PB Vision JSON response
    thumbnail_urls = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Stores the generated PB Vision player thumbnails."
    )
    error_message = models.TextField(blank=True)  # Quick access to failure reason
    logs = models.TextField(blank=True)
    
    # Retry & async job tracking
    retry_count = models.IntegerField(default=0)  # How many times was it attempted?
    task_id = models.CharField(max_length=255, null=True, blank=True)  # Celery task ID for async jobs
    
    # Player identification
    selected_player_index = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="The PB Vision playerIndex (0-3) selected by the user."
    )
    
    # Webhook validation (for strict signature verification)
    webhook_signature_secret = models.CharField(
        max_length=255,
        default=generate_token,
        editable=False,
        help_text="Unique secret for validating incoming PB Vision webhook. Generated on creation."
    )
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.name} - {self.status}"

