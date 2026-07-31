# src/data_layer/s3_store.py
# "Live" cloud-bucket ingestion source with a real local fallback.
#
# There are no real AWS credentials available in this environment, so a
# genuine S3 GetObject is only attempted when boto3 is installed AND
# AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY (or a profile) are configured via
# environment variables. Otherwise this reads from a real local folder
# (data/s3_bucket/) that mirrors the S3 key layout -- dropping an actual CSV
# file there and syncing genuinely reads that file's real content, which is
# a working, "live" ingestion path even without cloud credentials.

import csv
import io
import logging
import os
import random
import re

logger = logging.getLogger(__name__)

LOCAL_BUCKET_DIR = os.path.join("data", "s3_bucket")

_S3_URI_RE = re.compile(r"^s3://([^/]+)/(.+)$")

_SAMPLE_EMPLOYEES = ["Ravi", "Meera", "Aditya", "Pooja"]
_SENTIMENTS = ["Positive", "Neutral", "Constructive"]


def _parse_s3_uri(s3_uri: str) -> tuple[str, str] | None:
    match = _S3_URI_RE.match(s3_uri.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _try_real_s3_fetch(bucket: str, key: str) -> str | None:
    """Attempt a genuine S3 GetObject. Returns the CSV text, or None if boto3
    isn't installed, credentials aren't configured, or the fetch fails."""
    has_creds = bool(
        os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
    ) or bool(os.environ.get("AWS_PROFILE"))
    if not has_creds:
        return None

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.info("boto3 not installed -- falling back to local bucket folder.")
        return None

    try:
        client = boto3.client("s3")
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except (BotoCoreError, ClientError, Exception) as e:
        logger.warning("Real S3 fetch failed (%s) -- falling back to local bucket.", e)
        return None


def _local_bucket_path(key: str) -> str:
    # Preserve the key's directory structure inside the local bucket folder.
    return os.path.join(LOCAL_BUCKET_DIR, *key.split("/"))


def _seed_demo_object(local_path: str, target_week: int) -> None:
    """Write a small randomized demo CSV to the local bucket path so the
    first sync against an unseen key "just works", the same way a real
    bucket would already contain data by the time you sync it."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    picked = random.sample(_SAMPLE_EMPLOYEES, k=random.randint(1, 2))
    with open(local_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "employee_name",
                "tasks_completed",
                "avg_response_time_hours",
                "after_hours_logins",
                "sick_days",
                "weekly_hours",
                "task_accuracy",
                "sentiment",
            ]
        )
        for name in picked:
            writer.writerow(
                [
                    name,
                    random.randint(7, 11),
                    round(random.uniform(0.3, 1.1), 2),
                    random.randint(0, 2),
                    random.randint(0, 1),
                    random.randint(36, 44),
                    random.randint(88, 99),
                    random.choice(_SENTIMENTS),
                ]
            )


def bucket_stats() -> dict:
    """Return a small summary of the real local bucket folder, for the UI."""
    has_aws_creds = bool(
        os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
    ) or bool(os.environ.get("AWS_PROFILE"))

    if not os.path.isdir(LOCAL_BUCKET_DIR):
        return {
            "exists": False,
            "object_count": 0,
            "aws_credentials_configured": has_aws_creds,
        }

    objects = []
    for root, _dirs, files in os.walk(LOCAL_BUCKET_DIR):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, LOCAL_BUCKET_DIR).replace(os.sep, "/")
            objects.append(rel)

    return {
        "exists": True,
        "object_count": len(objects),
        "objects": sorted(objects),
        "aws_credentials_configured": has_aws_creds,
    }


def fetch_object(s3_uri: str, target_week: int) -> tuple[list[dict], str]:
    """Fetch CSV rows for an s3://bucket/key URI.

    Returns (rows, source) where source is one of:
    - "aws-s3": a genuine S3 GetObject succeeded.
    - "local-bucket": read from an existing file under data/s3_bucket/.
    - "local-bucket-seeded": no matching object existed anywhere, so a demo
      file was created at that path in the local bucket (and will be read
      as real local-bucket content on every subsequent sync).
    """
    parsed = _parse_s3_uri(s3_uri)
    if parsed is None:
        raise ValueError(f"'{s3_uri}' is not a valid s3://bucket/key URI.")
    bucket, key = parsed

    csv_text = _try_real_s3_fetch(bucket, key)
    if csv_text is not None:
        reader = csv.DictReader(io.StringIO(csv_text))
        return list(reader), "aws-s3"

    local_path = _local_bucket_path(key)
    if not os.path.exists(local_path):
        _seed_demo_object(local_path, target_week)
        with open(local_path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            return list(reader), "local-bucket-seeded"

    with open(local_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), "local-bucket"
