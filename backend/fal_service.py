"""fal.ai identity-preserving image generation via Emergent Universal Key (queue proxy).
Uses fal-ai/flux-pulid to keep the real child's facial identity across illustrations."""
import os
import time
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
INTEGRATION_PROXY_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
CONTROL_BASE = INTEGRATION_PROXY_BASE.rstrip("/") + "/api/v1/fal"
PUBLIC_QUEUE_BASE = f"{CONTROL_BASE}/queue"
QUEUE_ORIGIN = "https://queue.fal.run"

PULID_ENDPOINT = "fal-ai/flux-pulid"


def _image_size():
    """Default portrait_4_3 (768x1024). Set FAL_IMAGE_W / FAL_IMAGE_H (e.g. 1152 x 1536) for sharper
    prints if your fal plan allows it (review item L7). Multiples of 8 only."""
    try:
        w, h = int(os.environ.get("FAL_IMAGE_W", "0")), int(os.environ.get("FAL_IMAGE_H", "0"))
    except ValueError:
        return "portrait_4_3"
    if w >= 512 and h >= 512 and w % 8 == 0 and h % 8 == 0:
        return {"width": w, "height": h}
    return "portrait_4_3"


IMAGE_SIZE = _image_size()
MULTI_REF_ENDPOINT = os.environ.get("MULTI_REF_ENDPOINT", "fal-ai/nano-banana/edit")
UPSCALE_ENDPOINT = os.environ.get("UPSCALE_ENDPOINT", "").strip()  # e.g. an ESRGAN / clarity upscaler on fal


class FalError(Exception):
    pass


def _headers(extra=None):
    h = {"Authorization": f"Bearer {EMERGENT_LLM_KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _trusted(url: str) -> str:
    c = urlparse(url)
    b = urlparse(PUBLIC_QUEUE_BASE)
    if c.scheme != b.scheme or c.netloc != b.netloc or not c.path.startswith(b.path.rstrip("/") + "/"):
        raise FalError("Untrusted queue URL")
    return url


def _get_retry(url, timeout, attempts=10):
    import random
    delay = 2
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers=_headers(), timeout=timeout)
            if r.status_code in (502, 503, 504):
                last = r
                time.sleep(delay + random.uniform(0, 1.5)); delay = min(delay * 2, 20); continue
            return r
        except (requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError) as e:
            last = e
            time.sleep(delay + random.uniform(0, 1.5)); delay = min(delay * 2, 20)
    if isinstance(last, requests.Response):
        return last
    raise FalError(f"GET failed after retries: {last}")


FAL_KEY = os.environ.get("FAL_KEY", "").strip()   # set it to call fal.ai directly instead of the Emergent proxy (L12)


def _run_direct(endpoint_id: str, payload: dict, timeout_seconds: int) -> dict:
    """fal.ai queue REST API with your own key (https://docs.fal.ai/model-endpoints/queue)."""
    hdr = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
    sub = requests.post(f"{QUEUE_ORIGIN}/{endpoint_id}", headers=hdr, json=payload, timeout=60)
    sub.raise_for_status()
    j = sub.json()
    status_url, response_url = j["status_url"], j["response_url"]
    if not (status_url.startswith(QUEUE_ORIGIN) and response_url.startswith(QUEUE_ORIGIN)):
        raise FalError("Untrusted queue URL")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        st = requests.get(status_url, headers=hdr, timeout=30)
        st.raise_for_status()
        status = (st.json().get("status") or "").upper()
        if status == "COMPLETED":
            res = requests.get(response_url, headers=hdr, timeout=60)
            res.raise_for_status()
            return res.json()
        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise FalError(f"fal generation {status}")
        time.sleep(2.5)
    raise FalError("Timed out waiting for generation")


def run_media_generation(endpoint_id: str, payload: dict, timeout_seconds: int = 480) -> dict:
    if FAL_KEY:
        return _run_direct(endpoint_id, payload, timeout_seconds)
    submit = None
    delay = 3
    for _ in range(5):
        submit = requests.post(
            f"{CONTROL_BASE}/proxy",
            headers=_headers({"X-Fal-Target-Url": f"{QUEUE_ORIGIN}/{endpoint_id}"}),
            json=payload, timeout=60,
        )
        if submit.status_code in (502, 503, 504):
            time.sleep(delay); delay = min(delay * 2, 20); continue
        break
    if submit.status_code == 402:
        raise FalError("Insufficient Universal Key credits")
    submit.raise_for_status()
    sub = submit.json()
    status_url = _trusted(sub["status_url"])
    response_url = _trusted(sub["response_url"])

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        st = _get_retry(status_url, 30)
        st.raise_for_status()
        status = (st.json().get("status") or "").upper()
        if status in {"COMPLETED", "OK"}:
            res = _get_retry(response_url, 60)
            if res.status_code in (502, 503, 504):
                # result briefly unavailable behind the gateway; keep re-polling within deadline
                time.sleep(4)
                continue
            res.raise_for_status()
            return res.json()
        if status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            raise FalError(f"Generation failed: {status}")
        time.sleep(2)
    raise FalError("Timed out waiting for generation")


STORYBOOK_STYLE = (
    "in the style of a warm hand-painted children's storybook illustration, soft watercolour and "
    "gouache, gentle rounded cartoon style, cozy warm palette, whimsical and adorable, cute cartoon child"
)

# Per-order selectable art styles (customer choice)
STYLE_PROMPTS = {
    "cartoon": (
        "in the style of a warm hand-painted children's storybook illustration, gentle rounded 2D cartoon "
        "style, bold clean outlines, flat cheerful colours, cozy warm palette, whimsical and adorable, cute cartoon child"
    ),
    "watercolor": (
        "in the style of a soft watercolour children's storybook painting, delicate washes and gentle gradients, "
        "hand-painted gouache texture, dreamy pastel palette, soft edges, whimsical and adorable"
    ),
    "3d": (
        "in the style of a cute Pixar-like 3D rendered animation, soft global illumination, subsurface skin shading, "
        "rounded friendly character design, glossy playful colours, cinematic depth of field, adorable 3D cartoon child"
    ),
}
STYLE_NEGATIVES = {
    "cartoon": "photorealistic, photograph, 3d render",
    "watercolor": "photorealistic, photograph, harsh outlines, 3d render",
    "3d": "flat 2d, photorealistic photograph, harsh outlines",
}


def _style_bits(style: str):
    style = (style or "cartoon").lower()
    return STYLE_PROMPTS.get(style, STORYBOOK_STYLE), STYLE_NEGATIVES.get(style, "photorealistic, photograph, 3d render")


def generate_illustration_pulid(reference_image_url: str, scene: str, seed: int,
                                is_cover: bool = False, id_weight: float = 1.0,
                                style: str = "cartoon") -> bytes:
    """Generate one illustration preserving the child's identity from reference_image_url.
    `style` is the customer-selected art style (cartoon | watercolor | 3d). Returns PNG/JPEG bytes.

    Wrapped in a retry loop so a transient fal proxy 503 / timeout on a single image does not
    abort the whole book generation."""
    style_desc, style_neg = _style_bits(style)
    prompt = (
        f"An illustration of the same child from the reference photo, keeping their real face, "
        f"skin tone and hairstyle, {style_desc}. Scene: {scene}."
    )
    if is_cover:
        prompt += " Full body, centered, happy expression, empty space at the top."
    payload = {
        "reference_image_url": reference_image_url,
        "prompt": prompt,
        "id_weight": id_weight,
        "image_size": IMAGE_SIZE,
        "num_inference_steps": 20,
        "guidance_scale": 4,
        "seed": seed,
        "negative_prompt": f"{style_neg}, realistic skin texture, deformed, ugly, extra fingers, text, watermark, blurry",
    }
    last_err = None
    for attempt in range(3):
        try:
            result = run_media_generation(PULID_ENDPOINT, payload)
            images = result.get("images") or []
            if not images or not images[0].get("url"):
                raise FalError("No image returned")
            img_url = images[0]["url"]
            r = requests.get(img_url, timeout=60)
            r.raise_for_status()
            return r.content
        except FalError as e:
            # Never retry a hard credit failure — surface it immediately.
            if "credits" in str(e).lower():
                raise
            last_err = e
            logger.warning(f"fal illustration attempt {attempt + 1}/3 failed: {e}")
        except (requests.HTTPError, requests.RequestException) as e:
            last_err = e
            logger.warning(f"fal illustration attempt {attempt + 1}/3 network error: {e}")
        time.sleep(5 * (attempt + 1))
    raise FalError(f"Illustration failed after 3 attempts: {last_err}")


def _download_first_image(result: dict) -> bytes:
    images = result.get("images") or ([result["image"]] if result.get("image") else [])
    if not images or not images[0].get("url"):
        raise FalError("No image returned")
    r = requests.get(images[0]["url"], timeout=90)
    r.raise_for_status()
    return r.content


def generate_multi_reference(image_urls: list, prompt: str, seed: int, endpoint: str = None) -> bytes:
    """Several identity photos in ONE picture (child + siblings / parents / pet) — review item H16.

    Uses an image-edit model that accepts a list of reference images (default fal-ai/nano-banana/edit;
    override with MULTI_REF_ENDPOINT, e.g. fal-ai/flux-pro/kontext/max/multi). Raises FalError on failure so the
    caller can fall back to the single-identity PuLID path.
    """
    endpoint = endpoint or MULTI_REF_ENDPOINT
    payload = {"prompt": prompt, "image_urls": image_urls, "num_images": 1, "output_format": "png"}
    if "kontext" in endpoint:
        payload.update({"aspect_ratio": "3:4", "seed": seed})
    result = run_media_generation(endpoint, payload, timeout_seconds=300)
    return _download_first_image(result)


def upscale_image(image_url: str, scale: int = 2) -> bytes:
    """Optional AI upscaler (UPSCALE_ENDPOINT). Raises FalError if not configured."""
    if not UPSCALE_ENDPOINT:
        raise FalError("UPSCALE_ENDPOINT not configured")
    result = run_media_generation(UPSCALE_ENDPOINT, {"image_url": image_url, "scale": scale}, timeout_seconds=300)
    return _download_first_image(result)
