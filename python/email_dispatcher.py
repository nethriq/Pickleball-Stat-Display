"""Email and delivery helpers.

Primary use (Phase 1): callable backend service to email delivery zip files.
"""

import os
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Dict, List, Optional

DEFAULT_MAX_EMAIL_BYTES = 25 * 1024 * 1024


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_email(email: Optional[str]) -> bool:
    if not email:
        return False
    _, parsed = parseaddr(email)
    if not parsed:
        return False
    # Minimal syntax check; strict verification can be added later.
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", parsed))


def discover_zip_attachments(deliveries_dir: str, include_master_zip: bool = False) -> List[Dict[str, Any]]:
    """Discover zip files under a deliveries directory for email attachments."""
    if not os.path.isdir(deliveries_dir):
        return []

    zipfiles: List[Dict[str, Any]] = []
    for entry in sorted(os.listdir(deliveries_dir)):
        if not entry.endswith(".zip"):
            continue
        if not include_master_zip and entry.startswith("Nethriq_All_"):
            continue

        file_path = os.path.join(deliveries_dir, entry)
        if not os.path.isfile(file_path):
            continue

        zipfiles.append(
            {
                "name": entry,
                "path": file_path,
                "size": os.path.getsize(file_path),
            }
        )

    return zipfiles


def send_delivery_email_with_attachments(
    recipient_email: Optional[str],
    zipfiles: List[Dict[str, Any]],
    *,
    job_id: Optional[int] = None,
    job_name: Optional[str] = None,
    selected_player_index: Optional[int] = None,
    from_email: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    max_total_attachment_bytes: int = DEFAULT_MAX_EMAIL_BYTES,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Send delivery zip files to a recipient using Django's EmailMessage API.

    Returns a structured payload suitable for persistence in `result_json`.
    """
    attempted_at = _utc_now_iso()

    result: Dict[str, Any] = {
        "status": "failed_send",
        "recipient": recipient_email,
        "attempted_at": attempted_at,
        "sent_at": None,
        "error": None,
        "subject": None,
        "attachment_count": 0,
        "total_attachment_bytes": 0,
        "attachments": [],
        "job_id": job_id,
        "job_name": job_name,
        "selected_player_index": selected_player_index,
    }

    if not recipient_email:
        result["status"] = "skipped_no_email"
        result["error"] = "missing_recipient_email"
        return result

    if not _is_valid_email(recipient_email):
        result["status"] = "skipped_invalid_email"
        result["error"] = "invalid_recipient_email"
        return result

    normalized_zipfiles: List[Dict[str, Any]] = []
    for item in zipfiles or []:
        path = item.get("path")
        name = item.get("name") or (os.path.basename(path) if path else None)
        if not path or not os.path.isfile(path):
            continue
        normalized_zipfiles.append(
            {
                "name": name,
                "path": path,
                "size": os.path.getsize(path),
            }
        )

    if not normalized_zipfiles:
        result["status"] = "skipped_no_attachments"
        result["error"] = "no_valid_zip_attachments"
        return result

    total_size = sum(item["size"] for item in normalized_zipfiles)
    result["attachments"] = normalized_zipfiles
    result["attachment_count"] = len(normalized_zipfiles)
    result["total_attachment_bytes"] = total_size

    if total_size > max_total_attachment_bytes:
        result["status"] = "skipped_attachment_budget"
        result["error"] = (
            f"attachments_exceed_budget:{total_size}>{max_total_attachment_bytes}"
        )
        return result

    email_subject = subject or f"Your Nethriq delivery is ready (Job {job_id})"
    email_body = body or (
        "Your Nethriq analytics delivery is complete. "
        "The generated zip packages are attached to this email."
    )
    result["subject"] = email_subject

    if dry_run:
        result["status"] = "dry_run"
        result["sent_at"] = _utc_now_iso()
        return result

    try:
        from django.core.mail import EmailMessage

        message = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email=from_email,
            to=[recipient_email],
        )
        for attachment in normalized_zipfiles:
            message.attach_file(attachment["path"])

        sent_count = message.send(fail_silently=False)
        if sent_count > 0:
            result["status"] = "sent"
            result["sent_at"] = _utc_now_iso()
        else:
            result["status"] = "failed_send"
            result["error"] = "email_backend_returned_zero"
    except Exception as exc:
        result["status"] = "failed_send"
        result["error"] = str(exc)

    return result


def dispatch_delivery_email_from_job_dir(
    job_directory: str,
    recipient_email: Optional[str],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Convenience wrapper for pipeline jobs that stores artifacts in `<job>/deliveries`."""
    deliveries_dir = os.path.join(job_directory, "deliveries")
    zipfiles = discover_zip_attachments(deliveries_dir=deliveries_dir, include_master_zip=False)
    return send_delivery_email_with_attachments(
        recipient_email=recipient_email,
        zipfiles=zipfiles,
        **kwargs,
    )
