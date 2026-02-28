"""
URL configuration for nethriq project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from nethriq import views

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),
    
    # ========================================================================
    # Authentication Endpoints
    # ========================================================================
    path('api/register/', views.register, name='register'),
    path('api/login/', views.login, name='login'),
    
    # ========================================================================
    # Upload & Job Management Endpoints
    # ========================================================================
    path('api/upload/', views.upload_video, name='upload_video'),
    path('api/jobs/', views.list_jobs, name='list_jobs'),
    path('api/jobs/<int:job_id>/status/', views.get_job_status, name='get_job_status'),
    path('api/jobs/<int:job_id>/download/', views.download_job_results, name='download_job_results'),
    path('api/jobs/<int:job_id>/download-zip/<str:zip_id>/', views.download_job_zip, name='download_job_zip'),
    path('api/jobs/<int:job_id>/download-all/', views.download_job_all, name='download_job_all'),
    
    # ========================================================================
    # Webhook Endpoint
    # ========================================================================
    path('api/webhook/pbvision/<int:job_id>/', views.pbvision_webhook, name='pbvision_webhook'),
    
    # ========================================================================
    # Health & Debug Endpoints
    # ========================================================================
    path('api/health/', views.health_check, name='health_check'),
    path('api/debug/webhook-url/<int:job_id>/', views.debug_webhook_url, name='debug_webhook_url'),
    
    # ========================================================================
    # Frontend SPA Routes (serves index.html for all non-API routes)
    # ========================================================================
    path('', views.serve_frontend, name='frontend_home'),
    # Catch-all route for SPA: serves index.html for any non-API/admin/static routes
    # This allows React Router / Vue Router style navigation with page refreshes
    re_path(r'^(?!api/)(?!admin/)(?!staticfiles/)(?!media/).*$', views.serve_frontend, name='spa_fallback'),
]

# Serve media files (user uploads) in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
