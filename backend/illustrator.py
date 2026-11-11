"""Illustration orchestration (review items H16 + L6).

Problem before: every picture was generated from the FIRST character's photo only, the text could mention
parents/siblings/pet who never appeared, and clothes changed from page to page.

Now:
  * the story declares who is in each page (`characters`) and one fixed look per character (`character_sheet`);
  * pages with the main child alone use PuLID (best face fidelity);
  * pages with 2+ people/animals that HAVE photos use a multi-reference image model (default
    fal-ai/nano-banana/edit, configurable) so each person keeps their own face;
  * if the multi-reference model is unavailable or fails, the job falls back to PuLID for the rest of the
    book (circuit breaker) and records it — the order is never blocked.
"""
import io
import os
import re
import logging
from typing import Dict, List, Optional, Tuple

from PIL import Image

import fal_service
import security

logger = logging.getLogger(__name__)

BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "")
MULTI_REF_ENABLED = os.environ.get("MULTI_REF_ENABLED", "true").strip().lower() not in ("0", "false", "no")


def ref_url(path: str) -> str:
    """Short-lived signed URL that fal can fetch (C3: files are no longer anonymous)."""
    return f"{BACKEND_PUBLIC_URL}/api/files/{security.sign_path(path, security.FAL_REF_TTL_SECONDS)}"


def build_cast(order: dict) -> List[dict]:
    """Everyone who may appear in the book, with their photo if the family uploaded one."""
    cast = []
    for i, c in enumerate(order.get("characters", [])):
        if not c.get("name"):
            continue
        cast.append({"name": c["name"], "role": "main child" if i == 0 else (c.get("relation") or "family member"),
                     "age": c.get("age"), "gender": c.get("gender", ""), "photo_path": c.get("photo_path", ""),
                     "main": i == 0})
    if order.get("pet_name") or order.get("pet_type"):
        cast.append({"name": order.get("pet_name") or order.get("pet_type"),
                     "role": f"pet ({order.get('pet_type') or 'animal'})", "age": None, "gender": "",
                     "photo_path": order.get("pet_photo_path", ""), "main": False})
    known = {c["name"].strip().lower() for c in cast}
    if order.get("mention_parents", True):
        for key, role in (("mother_name", "mother"), ("father_name", "father")):
            n = (order.get(key) or "").strip()
            if n and n.lower() not in known:
                cast.append({"name": n, "role": role, "age": order.get(key.replace("name", "age")), "gender": "",
                             "photo_path": "", "main": False})
                known.add(n.lower())
    for grp, role in (("siblings", "sibling"), ("friends", "friend/relative")):
        for p in order.get(grp, []) or []:
            n = (p.get("name") or "").strip()
            if n and n.lower() not in known:
                cast.append({"name": n, "role": p.get("relation") or role, "age": p.get("age"), "gender": "",
                             "photo_path": "", "main": False})
                known.add(n.lower())
    return cast


def cast_for_story(cast: List[dict]) -> List[dict]:
    return [{"name": c["name"], "role": c["role"], "age": c.get("age"), "gender": c.get("gender"),
             "has_photo": bool(c.get("photo_path"))} for c in cast]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def match_cast(names: List[str], cast: List[dict]) -> List[dict]:
    """Map the names Claude listed for a page to cast entries (exact, else containment)."""
    out, seen = [], set()
    for n in names:
        nn = _norm(n)
        if not nn:
            continue
        hit = next((c for c in cast if _norm(c["name"]) == nn), None) or \
              next((c for c in cast if _norm(c["name"]) and (_norm(c["name"]) in nn or nn in _norm(c["name"]))), None)
        if hit and hit["name"] not in seen:
            out.append(hit)
            seen.add(hit["name"])
    return out


def sheet_text(sheet: Dict[str, str], present: List[dict]) -> str:
    names = {_norm(c["name"]) for c in present}
    parts = [f"{n}: {d}" for n, d in sheet.items() if not names or _norm(n) in names or
             any(_norm(n) in x or x in _norm(n) for x in names)]
    return "; ".join(parts)


def _fit_portrait(img_bytes: bytes) -> bytes:
    """Centre-crop to 3:4 so every page has the same proportions."""
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    target = 3 / 4
    if abs(w / h - target) <= 0.03:
        return img_bytes
    if w / h > target:  # too wide
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:               # too tall
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class JobContext:
    """Per-generation state: circuit breaker for the multi-reference model + counters for the cost ledger."""

    def __init__(self):
        self.multi_ok = MULTI_REF_ENABLED
        self.multi_error: Optional[str] = None
        self.counts = {"image_pulid": 0, "image_multi": 0}
        self.modes: List[str] = []


def _multi_prompt(style_desc: str, present: List[dict], scene: str, sheet: str) -> str:
    refs = "; ".join(f"Image {i + 1} is {c['name']} ({c['role']})" for i, c in enumerate(present))
    return (
        f"Create ONE children's-book illustration {style_desc}. Reference photos: {refs}. "
        f"Turn each reference into a cartoon character in this style while keeping that person's own face, skin tone "
        f"and hair faithful to their photo (a pet keeps its own fur colour and markings). "
        f"Scene: {scene}. Outfits and hair, identical on every page: {sheet or 'everyday modest clothing'}. "
        f"Portrait 3:4 composition, all referenced people clearly visible, no text, no watermark, no extra people."
    )


def render(ctx: JobContext, order: dict, cast: List[dict], sheet: Dict[str, str], scene: str,
           page_characters: List[str], seed: int, is_cover: bool = False) -> bytes:
    """Blocking (called through asyncio.to_thread)."""
    style = order.get("art_style", "cartoon")
    style_desc, _ = fal_service._style_bits(style)
    main = next((c for c in cast if c.get("main")), cast[0])
    present = match_cast(page_characters, cast)
    if not any(c is main for c in present):
        present.insert(0, main)
    else:
        present.sort(key=lambda c: 0 if c is main else 1)
    if is_cover:
        present = [main]
    with_photo = [c for c in present if c.get("photo_path")]
    sheet_str = sheet_text(sheet, present)
    scene_full = scene + (f" Keep these exact looks: {sheet_str}." if sheet_str else "")

    if len(with_photo) >= 2 and ctx.multi_ok:
        try:
            urls = [ref_url(c["photo_path"]) for c in with_photo]
            img = fal_service.generate_multi_reference(urls, _multi_prompt(style_desc, with_photo, scene, sheet_str), seed)
            ctx.counts["image_multi"] += 1
            ctx.modes.append("multi")
            return _fit_portrait(img)
        except Exception as e:  # circuit breaker: never block the order because of the optional model
            ctx.multi_ok = False
            ctx.multi_error = str(e)[:200]
            logger.warning(f"multi-reference illustration failed, falling back to PuLID for this job: {e}")

    if is_cover:
        scene_full += " Full body, centered."
    img = fal_service.generate_illustration_pulid(ref_url(main["photo_path"]), scene_full, seed, is_cover, 1.0, style)
    ctx.counts["image_pulid"] += 1
    ctx.modes.append("pulid")
    return img
