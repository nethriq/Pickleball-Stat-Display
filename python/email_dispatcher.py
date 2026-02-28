import json
import os
import subprocess
from datetime import datetime, timezone

DRY_RUN = False  # Set to True to skip actual uploads and use dummy links
MAX_RETRIES = 3

def upload_zip_to_drive(zip_path, rclone_path):
    """
    Upload a zipfile to Google Drive via rclone and get a shareable link.

    Args:
        zip_path: Local path to the zipfile.
        rclone_path: Destination path on rclone remote (e.g., nethriq_drive:deliveries/file.zip)

    Returns:
        tuple: (success: bool, shareable_link: str or None, error: str or None)
    """
    if DRY_RUN:
        return True, "https://drive.google.com/file/d/DRY_RUN_ID/view", None

    try:
        upload_cmd = ["rclone", "copyto", zip_path, rclone_path]
        print(" ".join(upload_cmd))
        subprocess.run(upload_cmd, check=True)

        link_cmd = ["rclone", "link", rclone_path]
        result = subprocess.run(link_cmd, capture_output=True, text=True, check=True, timeout=30)
        shareable_link = result.stdout.strip()
        return True, shareable_link, None
    except subprocess.TimeoutExpired:
        message = f"Timeout while getting link for {rclone_path}"
        print(f"⚠️ {message}")
        return False, None, message
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else str(e)
        message = f"Upload/link failed for {rclone_path}: {stderr}"
        print(f"⚠️ {message}")
        return False, None, message
    except Exception as e:
        message = f"Unexpected error for {rclone_path}: {str(e)}"
        print(f"⚠️ {message}")
        return False, None, message


def load_latest_log(log_dir):
    if not os.path.isdir(log_dir):
        return []

    log_files = [
        name for name in os.listdir(log_dir)
        if name.startswith("delivery_upload_") and name.endswith(".json")
    ]
    if not log_files:
        return []

    log_files.sort()
    latest_path = os.path.join(log_dir, log_files[-1])
    try:
        with open(latest_path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def dispatch_emails(delivery_records, email_lookup: dict, local_zip_dir, remote_zip_dir):
    results = []

    for record in delivery_records:
        player = record["player"]
        zip_name = record["zip"]

        zip_path = os.path.join(local_zip_dir, zip_name)
        remote_root = "nethriq_drive"
        rclone_path = f"{remote_root}:{remote_zip_dir.rstrip('/')}/{zip_name}"

        record.setdefault("retry_count", 0)
        record.setdefault("last_error", None)

        # upload zip to storage
        if not os.path.isfile(zip_path):
            record["upload_status"] = "failed"
            record["last_error"] = "zip_not_found"
            record["delivery_stage"] = "upload_failed"
            results.append(record)
            continue
        upload_success, download_link, error = upload_zip_to_drive(zip_path, rclone_path)
        record["upload_status"] = "success" if upload_success else "failed"
        record["last_error"] = error

        # send email (future)
        # success = send_email(recipient, download_link)

        recipient = email_lookup.get(player)
        record["email"] = recipient
        record["download_link"] = download_link if upload_success else None

        if not upload_success:
            record["email_status"] = "skipped_upload_failed"
            record["delivery_stage"] = "upload_failed"
        elif recipient:
            record["email_status"] = "pending"
            record["delivery_stage"] = "email_pending"
        else:
            record["email_status"] = "no_email"
            record["delivery_stage"] = "uploaded"

        results.append(record)

    return results

if __name__ == "__main__":
    default_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    job_dir = os.environ.get("JOB_DATA_DIR", default_data_dir)
    local_zip_dir = os.path.join(job_dir, "deliveries")
    remote_zip_dir = "deliveries"
    log_dir = os.path.join(local_zip_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    prior_records = load_latest_log(log_dir)
    prior_by_zip = {
        record.get("zip"): record
        for record in prior_records
        if record.get("zip")
    }

    delivery_records = []
    for zip_name in sorted(os.listdir(local_zip_dir)):
        if not zip_name.endswith(".zip"):
            continue

        base_name = os.path.splitext(zip_name)[0]
        player_id = None
        if base_name.startswith("Nethriq_Player_"):
            remainder = base_name[len("Nethriq_Player_"):]
            if "_" in remainder:
                player_id = remainder.split("_", 1)[0]
            else:
                player_id = remainder

        player = f"player_{player_id}" if player_id else "unknown"

        prior = prior_by_zip.get(zip_name)
        if prior and prior.get("upload_status") == "success":
            continue

        if prior and prior.get("retry_count", 0) >= MAX_RETRIES:
            print(f"⚠️ Skipping {zip_name} for {player} due to max retries reached")
            continue

        retry_count = prior.get("retry_count", 0) + 1 if prior else 0
        delivery_records.append({
            "player": player,
            "zip": zip_name,
            "delivery_stage": "created",
            "retry_count": retry_count,
            "last_error": prior.get("last_error") if prior else None,
        })

    email_lookup = {}

    results = dispatch_emails(delivery_records, email_lookup, local_zip_dir, remote_zip_dir)
    for result in results:
        print(result)

    timestamp = datetime.now(timezone.utc).date().isoformat().replace(":", "-")
    log_path = os.path.join(log_dir, f"delivery_upload_{timestamp}.json")
    tmp_path = log_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(tmp_path, log_path)
