"""Security helpers (review items C3, H1, H2, H3, H5, H10).

* Signed, expiring file URLs   -> no more anonymous access to child photos / PDFs.
* Safe image upload            -> size cap, format whitelist, EXIF stripped by re-encoding.
* In-memory rate limiting      -> login brute force, uploads, tickets (single-process deployment).
* Text sanitising              -> length caps and control-character stripping for free-text fields.
"""
import hashlib
import hmac
import io
import os
import re
import time
from collections import defaultdict, deque
from typing import Optional, Tuple

from fastapi import HTTPException, Request
from PIL import Image, ImageOps

APP_PREFIX = "hikayati/"
FILE_TTL_SECONDS = int(os.environ.get("FILE_URL_TTL_SECONDS", str(24 * 3600)))
FAL_REF_TTL_SECONDS = int(os.environ.get("FAL_REF_URL_TTL_SECONDS", "3600"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "8")) * 1024 * 1024
MAX_IMAGE_SIDE = 2048
MIN_IMAGE_SIDE = 400

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


def _secret() -> bytes:
    return os.environ["JWT_SECRET"].encode("utf-8")


# ---------------------------------------------------------------- signed URLs
def _mac(path: str, exp: int) -> str:
    return hmac.new(_secret(), f"{path}|{exp}".encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def strip_query(path: str) -> str:
    """Remove a ?exp=..&sig=.. suffix that the frontend may send back."""
    return (path or "").split("?", 1)[0]


def sign_path(path: str, ttl: Optional[int] = None) -> str:
    """Return `path?exp=..&sig=..`; the frontend only prefixes it with /api/files/."""
    if not path:
        return path
    path = strip_query(path)
    exp = int(time.time()) + int(ttl or FILE_TTL_SECONDS)
    return f"{path}?exp={exp}&sig={_mac(path, exp)}"


def verify_signature(path: str, exp: Optional[str], sig: Optional[str]) -> bool:
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()) or not sig:
        return False
    return hmac.compare_digest(_mac(path, exp_i), sig)


_SIGN_EXCLUDE_PUBLIC = {"reference_photo_path", "pet_photo_path", "photo_path"}


def sign_tree(obj, include_sensitive: bool = False):
    """Recursively replace every `*_path` string that points into our storage with a signed
    path. Reference photos are only signed for admins (`include_sensitive=True`)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and k.endswith("_path") and v.startswith(APP_PREFIX):
                if k in _SIGN_EXCLUDE_PUBLIC and not include_sensitive:
                    continue  # never expose
                out[k] = sign_path(v)
            else:
                out[k] = sign_tree(v, include_sensitive)
        return out
    if isinstance(obj, list):
        return [sign_tree(x, include_sensitive) for x in obj]
    return obj


def valid_reference_path(path: str) -> bool:
    """H2: client-supplied photo paths must be one of OUR uploaded reference photos."""
    p = strip_query(path)
    return bool(re.fullmatch(r"hikayati/references/[0-9a-f\-]{36}/photo\.(jpg|png)", p))


# ---------------------------------------------------------------- upload hygiene
def process_upload(data: bytes) -> Tuple[Optional[bytes], dict]:
    """Validate and re-encode an uploaded photo.

    Returns (clean_jpeg_bytes | None, info). Re-encoding drops EXIF/GPS and any appended payload.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        return None, {"ok": False, "code": "too_large",
                      "message": f"حجم الصورة كبير (الحد {MAX_UPLOAD_BYTES // (1024 * 1024)} ميغابايت)"}
    try:
        im = Image.open(io.BytesIO(data))
        fmt = (im.format or "").upper()
        if fmt not in ("JPEG", "PNG", "WEBP"):
            return None, {"ok": False, "code": "bad_format", "message": "صيغة الصورة غير مدعومة (JPG أو PNG أو WEBP)"}
        im.load()
    except Exception:
        return None, {"ok": False, "code": "not_image", "message": "الملف ليس صورة صالحة"}
    im = ImageOps.exif_transpose(im)  # honour orientation BEFORE stripping metadata
    w, h = im.size
    if min(w, h) < MIN_IMAGE_SIDE:
        return None, {"ok": False, "code": "low_res", "width": w, "height": h,
                      "message": "دقة الصورة منخفضة. استخدم صورة أوضح (400 بكسل على الأقل)"}
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if max(im.size) > MAX_IMAGE_SIDE:
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92, optimize=True)  # no exif= argument => metadata dropped
    return buf.getvalue(), {"ok": True, "width": im.size[0], "height": im.size[1], "message": "الصورة مناسبة"}


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)

    def check(self, key: str, limit: int, window: int, code: str = "rate_limited"):
        now = time.time()
        q = self._hits[key]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="طلبات كثيرة، حاول لاحقاً")
        q.append(now)
        if len(self._hits) > 5000:  # crude memory guard
            for k in [k for k, v in self._hits.items() if not v][:2000]:
                self._hits.pop(k, None)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "?"))


class LoginThrottle:
    """Lock an (ip,email) pair for 15 minutes after 5 failed attempts."""
    MAX_FAILS = 5
    LOCK_SECONDS = 15 * 60

    def __init__(self):
        self._fails = defaultdict(list)

    def check(self, key: str):
        now = time.time()
        self._fails[key] = [t for t in self._fails[key] if t > now - self.LOCK_SECONDS]
        if len(self._fails[key]) >= self.MAX_FAILS:
            raise HTTPException(status_code=429, detail="محاولات كثيرة. حاول بعد 15 دقيقة")

    def fail(self, key: str):
        self._fails[key].append(time.time())

    def ok(self, key: str):
        self._fails.pop(key, None)


login_throttle = LoginThrottle()


# ---------------------------------------------------------------- text hygiene
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def clean_text(s: Optional[str], max_len: int = 300) -> str:
    """Strip control/bidi-override characters, collapse whitespace, cap length."""
    s = _CTRL.sub("", s or "")
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:max_len]


# A conservative blocklist used to flag (never silently publish) problematic generated text.
_BLOCK = [
    r"\bsex(?:ual|y)?\b", r"\bnaked\b", r"\bnude\b", r"\bporn", r"\bkill(?:ed|ing)?\b", r"\bmurder", r"\bblood(?:y)?\b",
    r"\bsuicide\b", r"\bdrugs?\b", r"\bgun\b", r"\bweapon",
    r"جنس", r"عار[يٍ]", r"قتل", r"دم[اء]", r"انتحار", r"مخدر", r"سلاح", r"مسدس",
    r"\bsexe\b", r"\bnu(?:e|es|s)?\b", r"\btuer\b", r"\bmeurtre\b", r"\bsang\b", r"\bsuicide\b", r"\bdrogue",
]
_BLOCK_RX = re.compile("|".join(_BLOCK), re.IGNORECASE)


def text_flagged(text: str) -> bool:
    return bool(_BLOCK_RX.search(text or ""))
