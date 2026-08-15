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


def run_media_generation(endpoint_id: str, payload: dict, timeout_seconds: int = 480) -> dict:
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


def generate_illustration_pulid(reference_image_url: str, scene: str, seed: int,
                                is_cover: bool = False, id_weight: float = 1.0) -> bytes:
    """Generate one illustration preserving the child's identity from reference_image_url.
    Returns PNG/JPEG bytes."""
    prompt = (
        f"A cartoon illustration of the same child from the reference photo, keeping their real face, "
        f"skin tone and hairstyle, {STORYBOOK_STYLE}. Scene: {scene}."
    )
    if is_cover:
        prompt += " Full body, centered, happy expression, empty space at the top."
    payload = {
        "reference_image_url": reference_image_url,
        "prompt": prompt,
        "id_weight": id_weight,
        "image_size": "portrait_4_3",
        "num_inference_steps": 20,
        "guidance_scale": 4,
        "seed": seed,
        "negative_prompt": "photorealistic, photograph, realistic skin texture, deformed, ugly, extra fingers, text, watermark, blurry",
    }
    result = run_media_generation(PULID_ENDPOINT, payload)
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise FalError("No image returned")
    img_url = images[0]["url"]
    r = requests.get(img_url, timeout=60)
    r.raise_for_status()
    return r.content
