"""Object storage with pluggable backends (review item L12).

STORAGE_BACKEND = emergent (default, unchanged behaviour) | local | s3
  local : files under LOCAL_STORAGE_DIR (default ./storage_data)  -> development / single VPS
  s3    : any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze...):
          S3_BUCKET, S3_ENDPOINT_URL (optional), S3_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

All functions are synchronous (the callers wrap them with asyncio.to_thread).
`delete_object` / `delete_prefix` really remove files (review item C2).
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

APP_NAME = "hikayati"
BACKEND = os.environ.get("STORAGE_BACKEND", "emergent").strip().lower()

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
}

# ------------------------------------------------------------------ emergent
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
_storage_key = None


def _em_init(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _em_put(path, data, content_type):
    for attempt in (0, 1):
        key = _em_init(force=bool(attempt))
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
        if resp.status_code != 404:
            break
    resp.raise_for_status()
    return resp.json()


def _em_get(path):
    for attempt in (0, 1):
        key = _em_init(force=bool(attempt))
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
        if resp.status_code != 404:
            break
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def _em_delete(path) -> bool:
    """The Emergent object store's delete API is not documented in this repo. We try the
    conventional DELETE; if the service rejects it we report False so the caller can flag
    the file as `purge_pending` instead of pretending it was deleted."""
    try:
        key = _em_init()
        resp = requests.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=30)
        return resp.status_code in (200, 202, 204, 404)
    except Exception as e:  # pragma: no cover
        logger.warning(f"emergent delete failed for {path}: {e}")
        return False


# ------------------------------------------------------------------ local
LOCAL_DIR = os.environ.get("LOCAL_STORAGE_DIR", os.path.join(os.path.dirname(__file__), "storage_data"))


def _safe_local(path: str) -> str:
    full = os.path.abspath(os.path.join(LOCAL_DIR, path))
    if not full.startswith(os.path.abspath(LOCAL_DIR) + os.sep):
        raise ValueError("invalid path")
    return full


def _local_put(path, data, content_type):
    full = _safe_local(path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)
    with open(full + ".ct", "w") as f:
        f.write(content_type)
    return {"path": path}


def _local_get(path):
    full = _safe_local(path)
    with open(full, "rb") as f:
        data = f.read()
    ct = "application/octet-stream"
    if os.path.exists(full + ".ct"):
        ct = open(full + ".ct").read().strip() or ct
    return data, ct


def _local_delete(path) -> bool:
    full = _safe_local(path)
    for p in (full, full + ".ct"):
        if os.path.exists(p):
            os.remove(p)
    return True


# ------------------------------------------------------------------ s3
_s3 = None


def _s3c():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
                           region_name=os.environ.get("S3_REGION") or None)
    return _s3


def _s3_put(path, data, content_type):
    _s3c().put_object(Bucket=os.environ["S3_BUCKET"], Key=path, Body=data, ContentType=content_type)
    return {"path": path}


def _s3_get(path):
    o = _s3c().get_object(Bucket=os.environ["S3_BUCKET"], Key=path)
    return o["Body"].read(), o.get("ContentType", "application/octet-stream")


def _s3_delete(path) -> bool:
    _s3c().delete_object(Bucket=os.environ["S3_BUCKET"], Key=path)
    return True


# ------------------------------------------------------------------ public API
def init_storage(force: bool = False):
    if BACKEND == "emergent":
        return _em_init(force)
    if BACKEND == "local":
        os.makedirs(LOCAL_DIR, exist_ok=True)
    return BACKEND


def put_object(path: str, data: bytes, content_type: str) -> dict:
    return {"emergent": _em_put, "local": _local_put, "s3": _s3_put}[BACKEND](path, data, content_type)


def get_object(path: str):
    return {"emergent": _em_get, "local": _local_get, "s3": _s3_get}[BACKEND](path)


def delete_object(path: str) -> bool:
    if not path:
        return True
    try:
        return {"emergent": _em_delete, "local": _local_delete, "s3": _s3_delete}[BACKEND](path)
    except Exception as e:
        logger.warning(f"delete_object failed for {path}: {e}")
        return False
