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
        c.setFont(font, size)
        c.setFillColorRGB(*color)
        max_w = W - 2 * margin
        shaped = _shape(text, rtl)
        lines = _wrap(c, shaped, font, size, max_w)
        y = y_top
        for line in lines:
            if rtl:
                c.drawRightString(W - margin, y, line)
            else:
                c.drawString(margin, y, line)
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
    c.setFillColorRGB(0.98, 0.98, 0.97)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    draw_image_area(cover_image, margin, H * 0.32, W - 2 * margin, H * 0.55)
    c.setFont(bold_font, 34)
    c.setFillColorRGB(0.88, 0.48, 0.37)
    shaped_title = _shape(title, rtl)
    c.drawCentredString(W / 2, H * 0.22, shaped_title)
    c.setFont(body_font, 14)
    c.setFillColorRGB(0.24, 0.25, 0.36)
    c.drawCentredString(W / 2, H * 0.17, _shape("حكايتي" if rtl else "Hikayati", rtl))
    c.showPage()

    # ---- Story pages ----
    for pg in pages:
        c.setFillColorRGB(0.99, 0.99, 0.98)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        if pg.get("image"):
            draw_image_area(pg["image"], margin, H * 0.42, W - 2 * margin, H * 0.5)
        draw_text_block(pg.get("text", ""), H * 0.34, 18, body_font)
        c.showPage()

    # ---- Moral / closing ----
    if moral:
        c.setFillColorRGB(0.51, 0.70, 0.60)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFont(bold_font, 24)
        c.setFillColorRGB(1, 1, 1)
        shaped_moral = _shape(moral, rtl)
        lines = _wrap(c, shaped_moral, bold_font, 24, W - 2 * margin)
        y = H / 2 + len(lines) * 18
        for line in lines:
            c.drawCentredString(W / 2, y, line)
            y -= 36
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()



def make_line_art(image_bytes: bytes) -> bytes:
    """Convert a coloured illustration into a bold black-and-white coloring-book line drawing (PNG)."""
    from PIL import Image, ImageFilter, ImageOps
    import numpy as np
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = ImageOps.autocontrast(img)
    # denoise a little so soft watercolour areas don't speckle
    smooth = img.filter(ImageFilter.MedianFilter(3))
    # pencil-sketch (dodge) to lift line structure
    inv = ImageOps.invert(smooth)
    blur = inv.filter(ImageFilter.GaussianBlur(10))
    g = np.asarray(smooth, dtype=np.float32)
    b = np.asarray(blur, dtype=np.float32)
    sketch = np.minimum(255.0, g * 255.0 / np.maximum(255.0 - b, 1.0))
    # emphasise real edges
    edges = np.asarray(smooth.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    combined = np.clip(sketch - edges * 1.4, 0, 255)
    # crisp threshold -> bold pure-black outlines on white
    out = np.where(combined < 205, 0, 255).astype("uint8")
    result = Image.fromarray(out, "L").filter(ImageFilter.MinFilter(3))  # thicken lines slightly
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
