"""PDF book assembly with RTL (Arabic) + LTR (English/French) support using reportlab."""
import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONTS_REGISTERED = False


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Amiri", os.path.join(FONT_DIR, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Amiri-Bold", os.path.join(FONT_DIR, "Amiri-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Tajawal", os.path.join(FONT_DIR, "Tajawal-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Tajawal-Bold", os.path.join(FONT_DIR, "Tajawal-Bold.ttf")))
    _FONTS_REGISTERED = True


def _shape(text: str, rtl: bool) -> str:
    if rtl:
        return get_display(arabic_reshaper.reshape(text))
    return text


def _wrap(c, text, font, size, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_book_pdf(title: str, moral: str, pages: list, cover_image: bytes,
                   language: str, child_name: str) -> bytes:
    """pages: list of {'text': str, 'image': bytes}. Returns PDF bytes."""
    _register_fonts()
    rtl = language == "ar"
    body_font = "Amiri" if rtl else "Helvetica"
    bold_font = "Amiri-Bold" if rtl else "Helvetica-Bold"

    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin = 40

    def draw_text_block(text, y_top, size, font, color=(0.17, 0.18, 0.26)):
        import re
        text = re.sub(r'([:.،,!؟?])(?=\S)', r'\1 ', (text or "").strip())
        c.setFont(font, size)
        c.setFillColorRGB(*color)
        max_w = W - 2 * margin
        # Wrap the LOGICAL text first (preserves natural top-to-bottom order),
        # then reshape each line for correct RTL glyph joining.
        lines = _wrap(c, text, font, size, max_w)
        y = y_top
        for line in lines:
            disp = _shape(line, rtl)
            if rtl:
                c.drawRightString(W - margin, y, disp)
            else:
                c.drawString(margin, y, disp)
            y -= size * 1.5
        return y

    def draw_image_area(img_bytes, x, y, w, h):
        try:
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            ratio = min(w / iw, h / ih)
            dw, dh = iw * ratio, ih * ratio
            c.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, mask="auto")
        except Exception:
            pass

    # ---- Cover ----
    c.setFillColorRGB(0.96, 0.85, 0.62)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColorRGB(0.98, 0.93, 0.80)
    c.rect(0, 0, W, H * 0.62, fill=1, stroke=0)
    # logo badge (top)
    c.setFillColorRGB(0.88, 0.48, 0.37)
    c.roundRect(W / 2 - 60, H - 70, 120, 34, 16, fill=1, stroke=0)
    c.setFont(bold_font, 16); c.setFillColorRGB(1, 1, 1)
    c.drawCentredString(W / 2, H - 60, _shape("حكايتي" if rtl else "Hikayati", rtl))
    # hero image
    draw_image_area(cover_image, margin, H * 0.30, W - 2 * margin, H * 0.52)
    # title on a soft band
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(margin, H * 0.15, W - 2 * margin, H * 0.12, 20, fill=1, stroke=0)
    c.setFont(bold_font, 34); c.setFillColorRGB(0.88, 0.48, 0.37)
    c.drawCentredString(W / 2, H * 0.19, _shape(title, rtl))
    c.showPage()

    # ---- Story pages: near full-bleed image + coloured text band + logo badge ----
    for i, pg in enumerate(pages):
        c.setFillColorRGB(0.99, 0.985, 0.97)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        if pg.get("image"):
            draw_image_area(pg["image"], 0, H * 0.34, W, H * 0.66)
        # coloured text band at the bottom
        c.setFillColorRGB(0.95, 0.90, 0.78)
        c.roundRect(margin * 0.6, H * 0.05, W - margin * 1.2, H * 0.26, 18, fill=1, stroke=0)
        draw_text_block(pg.get("text", ""), H * 0.27, 18, body_font)
        # logo badge + page number
        c.setFillColorRGB(0.88, 0.48, 0.37)
        c.roundRect(W - 120, H - 44, 96, 26, 12, fill=1, stroke=0)
        c.setFont(bold_font, 12); c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(W - 72, H - 37, _shape("حكايتي" if rtl else "Hikayati", rtl))
        c.setFont(body_font, 11); c.setFillColorRGB(0.55, 0.55, 0.5)
        c.drawCentredString(W / 2, 24, str(i + 1))
        c.showPage()

    # ---- Moral / closing ----
    if moral:
        c.setFillColorRGB(0.51, 0.70, 0.60)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFont(body_font, 40); c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(W / 2, H * 0.72, "★  ✿  ★")
        c.setFont(bold_font, 24); c.setFillColorRGB(1, 1, 1)
        lines = _wrap(c, moral, bold_font, 24, W - 2 * margin)
        y = H / 2 + len(lines) * 18
        for line in lines:
            c.drawCentredString(W / 2, y, _shape(line, rtl))
            y -= 36
        c.setFont(bold_font, 16)
        c.drawCentredString(W / 2, H * 0.2, _shape("حكايتي" if rtl else "Hikayati", rtl))
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()



def make_line_art(image_bytes: bytes) -> bytes:
    """Convert a coloured illustration into a clean medium-weight coloring-book line drawing (PNG)."""
    from PIL import Image, ImageFilter, ImageOps
    import numpy as np
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = ImageOps.autocontrast(img)
    # strong denoise first so soft watercolour areas don't produce speckle noise
    smooth = img.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    inv = ImageOps.invert(smooth)
    blur = inv.filter(ImageFilter.GaussianBlur(12))
    g = np.asarray(smooth, dtype=np.float32)
    b = np.asarray(blur, dtype=np.float32)
    sketch = np.minimum(255.0, g * 255.0 / np.maximum(255.0 - b, 1.0))
    edges = np.asarray(smooth.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    combined = np.clip(sketch - edges * 1.2, 0, 255)
    # higher threshold keeps only confident outlines (removes faint background noise)
    out = np.where(combined < 165, 0, 255).astype("uint8")
    result = Image.fromarray(out, "L")
    # clean isolated specks, then give medium line weight
    result = result.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MinFilter(3))
    buf = io.BytesIO()
    result.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def build_coloring_pdf(title: str, line_pages: list, language: str) -> bytes:
    """line_pages: list of image bytes (line art). Returns a coloring-book PDF."""
    _register_fonts()
    rtl = language == "ar"
    bold_font = "Amiri-Bold" if rtl else "Helvetica-Bold"
    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin = 30

    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFont(bold_font, 30)
    c.setFillColorRGB(0.17, 0.18, 0.26)
    heading = _shape(("كراس تلوين: " + title) if rtl else ("Coloring Book: " + title), rtl)
    c.drawCentredString(W / 2, H * 0.55, heading)
    c.showPage()

    for img_bytes in line_pages:
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        try:
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            aw, ah = W - 2 * margin, H - 2 * margin
            ratio = min(aw / iw, ah / ih)
            dw, dh = iw * ratio, ih * ratio
            c.drawImage(img, (W - dw) / 2, (H - dh) / 2, dw, dh)
        except Exception:
            pass
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
