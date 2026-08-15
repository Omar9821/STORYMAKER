"""PDF book assembly — qessati-style: integrated card pages, scene-harmonised
gradient backgrounds, playful rounded Arabic typography, a designed cover with the
child in a circle, a festive ending page, and a clean coloring book."""
import os
import io
import math
import re
import unicodedata
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFilter, ImageOps
import numpy as np

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONTS_REGISTERED = False

# Fonts: Lemonada (rounded, friendly, playful — full Arabic+Latin). Static
# instances: regular=500, bold=700. Renders correctly in reportlab.
BODY = "Lemonada"
DISPLAY = "Lemonada-Bold"


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Lemonada", os.path.join(FONT_DIR, "Lemonada-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Lemonada-Bold", os.path.join(FONT_DIR, "Lemonada-Bold.ttf")))
    _FONTS_REGISTERED = True


def _fix_isolated(s: str) -> str:
    """Modern fonts omit ISOLATED presentation forms (they use the base letter).
    Map any <isolated> presentation form back to its base codepoint so standalone
    Arabic letters render instead of showing empty boxes."""
    out = []
    for ch in s:
        d = unicodedata.decomposition(ch)
        out.append(chr(int(d.split()[-1], 16)) if d.startswith("<isolated>") else ch)
    return "".join(out)


def _shape(text: str, rtl: bool) -> str:
    return get_display(_fix_isolated(arabic_reshaper.reshape(text))) if rtl else text


def _wrap(text, font, size, max_width):
    lines, cur = [], ""
    for w in (text or "").split():
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


def _mix(color, amt):
    """Mix an (r,g,b) 0..1 color toward white by amt (0=color, 1=white)."""
    return tuple(v + (1.0 - v) * amt for v in color)


def _dominant_color(image_bytes):
    """Average colour of an illustration, slightly saturated, as (r,g,b) 0..1."""
    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((32, 32))
        arr = np.asarray(im, dtype=np.float32).reshape(-1, 3) / 255.0
        r, g, b = arr[:, 0].mean(), arr[:, 1].mean(), arr[:, 2].mean()
        return (float(r), float(g), float(b))
    except Exception:
        return (0.95, 0.78, 0.55)


class BookCanvas:
    def __init__(self, buf):
        self.W, self.H = A4
        self.c = canvas.Canvas(buf, pagesize=A4)

    # ---- primitives ----
    def bg_gradient(self, top_c, bottom_c):
        c, W, H = self.c, self.W, self.H
        c.saveState()
        p = c.beginPath(); p.rect(0, 0, W, H); c.clipPath(p, stroke=0, fill=0)
        c.linearGradient(0, H, 0, 0, [Color(*top_c), Color(*bottom_c)], (0, 1), extend=True)
        c.restoreState()

    def image_cover(self, img_bytes, x, y, w, h):
        try:
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            ratio = max(w / iw, h / ih)
            dw, dh = iw * ratio, ih * ratio
            self.c.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, mask="auto")
        except Exception:
            pass

    def rounded_image(self, img_bytes, x, y, w, h, radius):
        c = self.c
        c.saveState()
        p = c.beginPath(); p.roundRect(x, y, w, h, radius); c.clipPath(p, stroke=0, fill=0)
        self.image_cover(img_bytes, x, y, w, h)
        c.restoreState()

    def circle_image(self, img_bytes, cx, cy, r):
        c = self.c
        c.saveState()
        p = c.beginPath(); p.circle(cx, cy, r); c.clipPath(p, stroke=0, fill=0)
        self.image_cover(img_bytes, cx - r, cy - r, 2 * r, 2 * r)
        c.restoreState()

    def logo_badge(self, rtl, accent):
        c, W, H = self.c, self.W, self.H
        label = _shape("حكايتي" if rtl else "Hikayati", rtl)
        c.setFont(DISPLAY, 15)
        tw = pdfmetrics.stringWidth(label, DISPLAY, 15)
        pad = 14
        bw = tw + pad * 2
        x = W - bw - 26
        c.setFillColor(Color(*accent))
        c.roundRect(x, H - 52, bw, 30, 15, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(x + pad, H - 45, label)

    def star(self, cx, cy, r, color):
        c = self.c
        pts = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        p = c.beginPath(); p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.close()
        c.setFillColor(Color(*color)); c.drawPath(p, fill=1, stroke=0)

    def paragraph(self, text, x, y_bottom, box_w, box_h, size, font, color):
        c = self.c
        text = re.sub(r'([:.،,!؟?])(?=\S)', r'\1 ', (text or "").strip())
        lines = _wrap(text, font, size, box_w)
        line_h = size * 1.55
        total = len(lines) * line_h
        cx = x + box_w / 2
        y = y_bottom + (box_h + total) / 2 - line_h
        c.setFont(font, size); c.setFillColor(Color(*color))
        rtl = font == BODY  # shaping handled by caller; we pass already-logical text
        for ln in lines:
            c.drawCentredString(cx, y, ln)
            y -= line_h


def build_book_pdf(title: str, moral: str, pages: list, cover_image: bytes,
                   language: str, child_name: str) -> bytes:
    _register_fonts()
    rtl = language == "ar"
    buf = io.BytesIO()
    bc = BookCanvas(buf)
    c, W, H = bc.c, bc.W, bc.H

    def shp(t):
        return _shape(t, rtl)

    # ---------------- Cover ----------------
    dom = _dominant_color(cover_image)
    bc.bg_gradient(_mix(dom, 0.35), _mix(dom, 0.70))
    # decorative stars
    bc.star(60, H - 110, 16, _mix(dom, 0.15))
    bc.star(W - 70, H - 160, 12, _mix(dom, 0.15))
    bc.star(48, 120, 11, _mix(dom, 0.2))
    # child inside a circle with a soft ring
    r = W * 0.30
    cx, cy = W / 2, H * 0.60
    c.setFillColor(Color(*_mix(dom, 0.85)))
    c.circle(cx, cy, r + 16, fill=1, stroke=0)
    c.setStrokeColor(Color(1, 1, 1)); c.setLineWidth(8)
    c.circle(cx, cy, r + 4, fill=0, stroke=1)
    bc.circle_image(cover_image, cx, cy, r)
    # logo badge
    bc.logo_badge(rtl, _mix(dom, 0.05))
    # title (big playful display)
    dark = (0.16, 0.17, 0.28)
    title_lines = _wrap(shp(title), DISPLAY, 46, W - 90)
    c.setFillColor(Color(*dark)); c.setFont(DISPLAY, 46)
    ty = cy - r - 70
    for ln in title_lines:
        c.drawCentredString(W / 2, ty, ln)
        ty -= 52
    # subtitle
    sub = shp(f"قصة مخصّصة لـ {child_name}" if rtl else f"A special story for {child_name}")
    c.setFont(BODY, 16); c.setFillColor(Color(*_mix(dark, 0.35)))
    c.drawCentredString(W / 2, ty - 4, sub)
    c.showPage()

    # ---------------- Story pages (integrated cards) ----------------
    for i, pg in enumerate(pages):
        img = pg.get("image")
        dom = _dominant_color(img) if img else (0.95, 0.8, 0.6)
        bc.bg_gradient(_mix(dom, 0.55), _mix(dom, 0.88))
        # card
        cm = 30
        card_x, card_w = cm, W - 2 * cm
        card_y, card_h = 56, H - 56 - 78
        c.setFillColor(Color(*_mix(dom, 0.93)))
        c.roundRect(card_x, card_y, card_w, card_h, 26, fill=1, stroke=0)
        # image occupies top ~60% of card (rounded)
        pad = 16
        img_h = card_h * 0.60
        img_y = card_y + card_h - img_h - pad
        if img:
            bc.rounded_image(img, card_x + pad, img_y, card_w - 2 * pad, img_h, 18)
        # text in the lower portion of the card
        txt_bottom = card_y + pad
        txt_h = img_y - txt_bottom
        bc.paragraph(shp(pg.get("text", "")), card_x + pad + 6, txt_bottom,
                     card_w - 2 * pad - 12, txt_h, 19, BODY, (0.18, 0.19, 0.30))
        # logo + page number
        bc.logo_badge(rtl, _mix(dom, 0.02))
        c.setFillColor(Color(*_mix(dom, 0.1)))
        c.circle(W / 2, 30, 15, fill=1, stroke=0)
        c.setFont(DISPLAY, 14); c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(W / 2, 25, str(i + 1))
        c.showPage()

    # ---------------- Festive ending page ----------------
    end_dom = (0.55, 0.72, 0.62)
    bc.bg_gradient(_mix(end_dom, 0.25), _mix(end_dom, 0.55))
    # scattered stars
    for (sx, sy, sr) in [(70, H - 130, 16), (W - 80, H - 120, 13), (100, 150, 12),
                          (W - 110, 180, 15), (W / 2 - 140, H - 90, 10), (W / 2 + 150, H - 100, 11)]:
        bc.star(sx, sy, sr, (1, 1, 1))
    # framed card
    fm = 55
    c.setFillColor(Color(1, 1, 1))
    c.roundRect(fm, H * 0.30, W - 2 * fm, H * 0.40, 28, fill=1, stroke=0)
    c.setStrokeColor(Color(*_mix(end_dom, 0.1))); c.setLineWidth(3)
    c.roundRect(fm + 10, H * 0.30 + 10, W - 2 * fm - 20, H * 0.40 - 20, 22, fill=0, stroke=1)
    # "The End" headline
    c.setFont(DISPLAY, 44); c.setFillColor(Color(*_mix(end_dom, 0.05)))
    c.drawCentredString(W / 2, H * 0.60, shp("النهاية" if rtl else "The End"))
    # moral
    if moral:
        c.setFont(DISPLAY, 22); c.setFillColor(Color(0.20, 0.22, 0.30))
        y = H * 0.52
        for ln in _wrap(shp(moral), DISPLAY, 22, W - 2 * fm - 70):
            c.drawCentredString(W / 2, y, ln)
            y -= 34
    bc.star(W / 2, H * 0.355, 18, _mix(end_dom, 0.0))
    bc.logo_badge(rtl, _mix(end_dom, 0.0))
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


def make_line_art(image_bytes: bytes) -> bytes:
    """Colour illustration -> clean coloring-book outline with COMPLETE, BOLD, uniform lines
    that keep both the full characters and the key background elements (adaptive local
    thresholding + morphological closing, instead of a sketch filter that drops parts)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = ImageOps.autocontrast(img)
    # denoise while preserving edges
    base = img.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    g = np.asarray(base, dtype=np.float32)
    # local mean (large blur) -> adaptive threshold keeps outlines of ALL elements (character
    # body, clothes, window, plants...) as closed dark lines, not just high-contrast edges.
    local_mean = np.asarray(base.filter(ImageFilter.GaussianBlur(9)), dtype=np.float32)
    C = 9.0
    dark = g < (local_mean - C)
    out = np.where(dark, 0, 255).astype("uint8")
    res = Image.fromarray(out, "L")
    # morphological CLOSE (dilate then erode) to seal small gaps -> complete closed contours
    res = res.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    # despeckle stray dots, then set a BOLD uniform line weight
    res = res.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MinFilter(3))
    buf = io.BytesIO()
    res.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def build_coloring_pdf(title: str, line_pages: list, language: str) -> bytes:
    _register_fonts()
    rtl = language == "ar"
    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin = 34

    def logo_badge():
        label = _shape("حكايتي" if rtl else "Hikayati", rtl)
        c.setFont(DISPLAY, 15)
        tw = pdfmetrics.stringWidth(label, DISPLAY, 15)
        bw = tw + 28
        x = W - bw - 26
        c.setFillColor(Color(0.88, 0.48, 0.37))
        c.roundRect(x, H - 52, bw, 30, 15, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(x + 14, H - 45, label)

    # cover
    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(Color(0.99, 0.86, 0.55)); c.roundRect(40, H * 0.42, W - 80, H * 0.18, 24, fill=1, stroke=0)
    c.setFont(DISPLAY, 34); c.setFillColor(Color(0.17, 0.18, 0.26))
    c.drawCentredString(W / 2, H * 0.52, _shape("كراس التلوين" if rtl else "Coloring Book", rtl))
    c.setFont(DISPLAY, 22); c.setFillColor(Color(0.55, 0.45, 0.2))
    c.drawCentredString(W / 2, H * 0.455, _shape(title, rtl))
    c.showPage()

    for i, img_bytes in enumerate(line_pages):
        c.setFillColorRGB(1, 1, 1); c.rect(0, 0, W, H, fill=1, stroke=0)
        logo_badge()
        # framed drawing area
        top = H - 80
        bottom = 70
        c.setStrokeColor(Color(0.85, 0.85, 0.82)); c.setLineWidth(2)
        c.roundRect(18, bottom - 12, W - 36, (top - bottom) + 24, 18, fill=0, stroke=1)
        try:
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            aw, ah = W - 2 * margin, (top - bottom)
            ratio = min(aw / iw, ah / ih)
            dw, dh = iw * ratio, ih * ratio
            c.drawImage(img, (W - dw) / 2, bottom + (ah - dh) / 2, dw, dh)
        except Exception:
            pass
        # page number badge (matches story pages)
        c.setFillColor(Color(0.88, 0.48, 0.37)); c.circle(W / 2, 34, 15, fill=1, stroke=0)
        c.setFont(DISPLAY, 14); c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(W / 2, 29, str(i + 1))
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
