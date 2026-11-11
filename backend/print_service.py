"""Print-ready production files (review item L7).

The screen PDF (A4, RGB, no bleed) is NOT suitable for a printer. This module builds:
  * interior PDF : trim size (A5 by default) + 3 mm bleed, TrimBox/BleedBox set, images resampled to 300 dpi
  * cover spread : back | spine | front with bleed (front/back mirrored for Arabic)
Resampling uses an AI upscaler when UPSCALE_ENDPOINT is configured (see fal_service.upscale_image) and
otherwise Lanczos + unsharp mask. NOTE: resampling cannot add real detail — for the sharpest print, generate
at a higher resolution (FAL_IMAGE_W / FAL_IMAGE_H) as well.
Colour: output is RGB. Most digital printers convert RGB->CMYK themselves; ask your printer if they need
a specific ICC profile.
"""
import io
import logging
import os
from typing import Callable, Optional

from PIL import Image, ImageFilter

import fal_service
import pdf_service

logger = logging.getLogger(__name__)

TARGET_DPI = 300
IMAGE_DESIGN_WIDTH = pdf_service.DESIGN_W - 60 - 32      # card image width in design units (see build_book_pdf)


def _resample(img_bytes: bytes, target_w: int, signed_url: Optional[Callable[[], str]] = None) -> tuple:
    """Returns (jpeg_bytes, mode)."""
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    mode = "none"
    if im.size[0] < target_w:
        if fal_service.UPSCALE_ENDPOINT and signed_url:
            try:
                up = fal_service.upscale_image(signed_url(), 2)
                im = Image.open(io.BytesIO(up)).convert("RGB")
                mode = "ai"
            except Exception as e:
                logger.warning(f"AI upscale failed, using Lanczos: {e}")
        if im.size[0] < target_w:
            ratio = target_w / im.size[0]
            im = im.resize((target_w, int(im.size[1] * ratio)), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))
            mode = "lanczos" if mode == "none" else mode + "+lanczos"
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=93, optimize=True)
    return buf.getvalue(), mode


def build(order: dict, get_bytes: Callable[[str], bytes], url_for: Optional[Callable[[str], str]] = None,
          trim: str = "A5", bleed_mm: float = 3.0, spine_mm: float = 3.0) -> dict:
    """Blocking. Returns {'interior': bytes, 'cover': bytes, 'info': {...}}."""
    tw_pt, th_pt = pdf_service.trim_points(trim)
    bleed_pt = bleed_mm * pdf_service.MM
    page = (tw_pt + 2 * bleed_pt, th_pt + 2 * bleed_pt)
    s = tw_pt / pdf_service.DESIGN_W
    img_inches = IMAGE_DESIGN_WIDTH * s / 72.0
    target_w = int(img_inches * TARGET_DPI)

    modes = set()
    pages = []
    for p in order["pages"]:
        raw = get_bytes(p["image_path"])
        jpg, mode = _resample(raw, target_w, (lambda path=p["image_path"]: url_for(path)) if url_for else None)
        modes.add(mode)
        pages.append({"text": p["text"], "image": jpg})
    cover_raw = get_bytes(order["cover_path"])
    cover_w = int(2 * 0.30 * pdf_service.DESIGN_W * s / 72.0 * TARGET_DPI)
    cover_jpg, cmode = _resample(cover_raw, cover_w, (lambda: url_for(order["cover_path"])) if url_for else None)
    modes.add(cmode)

    interior = pdf_service.build_book_pdf(order.get("story_title", ""), order.get("story_moral", ""), pages, cover_jpg,
                                          order["language"], order["child_name"], pagesize=page, bleed=bleed_pt, pad_to=4)
    spread = pdf_service.build_cover_spread_pdf(order.get("story_title", ""), cover_jpg, order["language"],
                                                order["child_name"], trim, bleed_mm, spine_mm)
    src_w = Image.open(io.BytesIO(get_bytes(order["pages"][0]["image_path"]))).size[0]
    return {"interior": interior, "cover": spread, "info": {
        "trim": trim, "bleed_mm": bleed_mm, "spine_mm": spine_mm, "target_dpi": TARGET_DPI,
        "source_px_width": src_w, "native_ppi": round(src_w / img_inches), "resample_modes": sorted(modes),
        "page_count": len(pages) + 2 + ((-(len(pages) + 2)) % 4), "binding_side": "right" if order["language"] == "ar" else "left"}}
