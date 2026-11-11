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


def _clean_text(text: str, rtl: bool = True) -> str:
    """Deterministic text hygiene applied to EVERY story (LLM-independent).

    Arabic (rtl=True): strip all quote glyphs (they float wrongly in RTL reshaping), fix spacing around
    Arabic punctuation.  Latin languages (rtl=False): only strip double quotes / guillemets / back-ticks and
    collapse whitespace — apostrophes inside words (l'histoire, d'un, it's) are KEPT (review item H15).
    """
    t = (text or "").strip()
    if rtl:
        t = re.sub(r"[\"'“”‘’`´«»]", "", t)
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"\s+([،.!؟:,;])", r"\1", t)
        t = re.sub(r"([،.!؟:,;])(?=\S)", r"\1 ", t)
    else:
        t = re.sub(r"[\"“”«»`´]", "", t)
        t = t.replace("’", "'").replace("‘", "'")
        t = re.sub(r"\s+", " ", t)
    return t.strip()


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


def _wrap_shaped(text, font, size, max_width, rtl):
    """Wrap the LOGICAL text into lines in natural top-to-bottom reading order FIRST,
    then reshape + apply the bidi algorithm to EACH line individually.

    This is the fix for reversed Arabic narratives: applying get_display() to a whole
    multi-line paragraph reverses the entire string, so splitting it afterwards puts the
    END of the text on the first line. Wrapping the logical text first and shaping each
    line keeps sentences in the correct chronological order (line 1 = first words)."""
    words = _clean_text(text, rtl).split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(_shape(trial, rtl), font, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return [_shape(ln, rtl) for ln in lines]


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


DESIGN_W = A4[0]


class _ScaledCanvas(canvas.Canvas):
    """A canvas whose pages are drawn in A4-design units and uniformly scaled to any page size
    (A5, square, with bleed...). Layout code therefore stays untouched."""

    def __init__(self, *args, design_scale: float = 1.0, **kw):
        self._design_scale = design_scale
        super().__init__(*args, **kw)

    def _make_preamble(self):
        super()._make_preamble()
        if self._design_scale != 1.0:
            self._preamble += " %.6f 0 0 %.6f 0 0 cm" % (self._design_scale, self._design_scale)


class BookCanvas:
    def __init__(self, buf, pagesize=A4, bleed: float = 0.0):
        self.pagesize = pagesize
        self.s = pagesize[0] / DESIGN_W
        self.W, self.H = DESIGN_W, pagesize[1] / self.s
        self.bleed = bleed
        self.c = _ScaledCanvas(buf, pagesize=pagesize, design_scale=self.s)
        if bleed:
            self.c.setTrimBox((bleed, bleed, pagesize[0] - bleed, pagesize[1] - bleed))
            self.c.setBleedBox((0, 0, pagesize[0], pagesize[1]))

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

    def logo_badge(self, rtl, accent, right=None):
        c, W, H = self.c, self.W, self.H
        W = right if right is not None else W
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

    def paragraph(self, text, rtl, x, y_bottom, box_w, box_h, size, font, color):
        c = self.c
        lines = _wrap_shaped(text, font, size, box_w, rtl)
        line_h = size * 1.55
        total = len(lines) * line_h
        cx = x + box_w / 2
        y = y_bottom + (box_h + total) / 2 - line_h
        c.setFont(font, size); c.setFillColor(Color(*color))
        for ln in lines:
            c.drawCentredString(cx, y, ln)
            y -= line_h


def _draw_cover(bc, x0, pw, title, cover_image, rtl, child_name):
    """Front cover drawn inside the panel [x0, x0+pw] (design units). Used by the book and by the
    print cover spread."""
    c, H = bc.c, bc.H

    def shp(t):
        return _shape(t, rtl)

    dom = _dominant_color(cover_image)
    bc.star(x0 + 60, H - 110, 16, _mix(dom, 0.15))
    bc.star(x0 + pw - 70, H - 160, 12, _mix(dom, 0.15))
    bc.star(x0 + 48, 120, 11, _mix(dom, 0.2))
    r = pw * 0.30
    cx, cy = x0 + pw / 2, H * 0.60
    c.setFillColor(Color(*_mix(dom, 0.85)))
    c.circle(cx, cy, r + 16, fill=1, stroke=0)
    c.setStrokeColor(Color(1, 1, 1)); c.setLineWidth(8)
    c.circle(cx, cy, r + 4, fill=0, stroke=1)
    bc.circle_image(cover_image, cx, cy, r)
    bc.logo_badge(rtl, _mix(dom, 0.05), right=x0 + pw)
    dark = (0.16, 0.17, 0.28)
    title_lines = _wrap_shaped(title, DISPLAY, 46, pw - 90, rtl)
    c.setFillColor(Color(*dark)); c.setFont(DISPLAY, 46)
    ty = cy - r - 70
    for ln in title_lines:
        c.drawCentredString(cx, ty, ln)
        ty -= 52
    sub = shp(f"قصة مخصّصة لـ {child_name}" if rtl else f"A special story for {child_name}")
    c.setFont(BODY, 16); c.setFillColor(Color(*_mix(dark, 0.35)))
    c.drawCentredString(cx, ty - 4, sub)


def build_book_pdf(title: str, moral: str, pages: list, cover_image: bytes,
                   language: str, child_name: str, pagesize=A4, bleed: float = 0.0, pad_to: int = 0) -> bytes:
    """Story book PDF. Default = A4 screen version. For print pass pagesize=(trim+2*bleed) and bleed (pt)."""
    _register_fonts()
    rtl = language == "ar"
    buf = io.BytesIO()
    bc = BookCanvas(buf, pagesize, bleed)
    c, W, H = bc.c, bc.W, bc.H

    def shp(t):
        return _shape(t, rtl)

    # ---------------- Cover ----------------
    dom = _dominant_color(cover_image)
    bc.bg_gradient(_mix(dom, 0.35), _mix(dom, 0.70))
    _draw_cover(bc, 0, W, title, cover_image, rtl, child_name)
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
        bc.paragraph(pg.get("text", ""), rtl, card_x + pad + 6, txt_bottom,
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
        for ln in _wrap_shaped(moral, DISPLAY, 22, W - 2 * fm - 70, rtl):
            c.drawCentredString(W / 2, y, ln)
            y -= 34
    bc.star(W / 2, H * 0.355, 18, _mix(end_dom, 0.0))
    bc.logo_badge(rtl, _mix(end_dom, 0.0))
    c.showPage()

    # pad with blank pages so the page count is a multiple of `pad_to` (printers bind in 4-page signatures)
    if pad_to:
        for _ in range((-(len(pages) + 2)) % pad_to):
            c.setFillColorRGB(1, 1, 1); c.rect(0, 0, W, H, fill=1, stroke=0)
            c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


def make_line_art(image_bytes: bytes) -> bytes:
    """Colour illustration -> clean coloring-book outlines (review item L8).

    Old method: adaptive threshold on luminance -> thick blobs (hair, shoes, shadows) and speckle in textured
    areas (grass, trees). New method:
      1. work at 2x resolution (crisp lines when printed);
      2. edge strength = max Sobel magnitude over R,G,B after a light blur (so colour boundaries count, flat
         shading and soft gradients do not);
      3. hysteresis threshold: weak edges are kept only when connected to strong ones;
      4. drop tiny disconnected fragments (texture noise);
      5. one uniform stroke width, black on white (mode L).
    """
    from scipy import ndimage as ndi
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float32)
    arr = np.stack([ndi.gaussian_filter(arr[..., k], 1.4) for k in range(3)], axis=-1)
    mag = np.zeros(arr.shape[:2], dtype=np.float32)
    for k in range(3):
        gx, gy = ndi.sobel(arr[..., k], axis=1), ndi.sobel(arr[..., k], axis=0)
        mag = np.maximum(mag, np.hypot(gx, gy))
    mag /= (mag.max() + 1e-6)
    hi, lo = np.percentile(mag, 94), np.percentile(mag, 86)
    strong, weak = mag >= hi, mag >= lo
    lab, n = ndi.label(weak, structure=np.ones((3, 3)))
    keep = np.unique(lab[strong])
    keep = keep[keep > 0]
    edges = np.isin(lab, keep)
    # texture suppression: short fragments sitting inside DENSE edge areas (grass, leaves, fur) are noise;
    # short fragments in sparse areas (eyes, mouth, buttons) are real details and are kept.
    lab2, n2 = ndi.label(edges, structure=np.ones((3, 3)))
    if n2:
        sizes = np.bincount(lab2.ravel(), minlength=n2 + 1)
        density = ndi.uniform_filter(edges.astype(np.float32), size=int(edges.shape[1] * 0.04) | 1)
        dense = density > 0.10
        dense_frac = ndi.mean(dense, labels=lab2, index=np.arange(n2 + 1))
        area = edges.size
        tiny = sizes < max(40, int(area * 0.00005))
        texture = (sizes < int(area * 0.0012)) & (dense_frac > 0.35)
        drop = tiny | texture
        drop[0] = False
        edges = edges & ~drop[lab2]
    edges = ndi.binary_dilation(edges, iterations=2)  # uniform, print-visible stroke (~0.5 mm at A5)
    out = np.where(edges, 0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(out, "L").save(buf, "PNG", optimize=True)
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


# ====================================================================== print production (L7)
MM = 72.0 / 25.4
TRIM_SIZES_MM = {"A5": (148, 210), "A4": (210, 297), "square21": (210, 210), "square15": (152, 152)}


def trim_points(name: str):
    w, h = TRIM_SIZES_MM.get(name, TRIM_SIZES_MM["A5"])
    return w * MM, h * MM


def build_cover_spread_pdf(title: str, cover_image: bytes, language: str, child_name: str,
                           trim: str = "A5", bleed_mm: float = 3.0, spine_mm: float = 3.0) -> bytes:
    """Flat cover for the printer: back cover | spine | front cover, with bleed around the whole spread."""
    _register_fonts()
    rtl = language == "ar"
    tw, th = trim_points(trim)
    bleed, spine = bleed_mm * MM, spine_mm * MM
    total_w, total_h = 2 * tw + spine + 2 * bleed, th + 2 * bleed
    s = tw / DESIGN_W
    buf = io.BytesIO()
    cv = _ScaledCanvas(buf, pagesize=(total_w, total_h), design_scale=s)
    cv.setTrimBox((bleed, bleed, total_w - bleed, total_h - bleed))
    cv.setBleedBox((0, 0, total_w, total_h))

    class _B:  # duck-typed BookCanvas for the shared helpers
        pass

    bc = BookCanvas.__new__(BookCanvas)
    bc.c, bc.s, bc.W, bc.H, bc.pagesize, bc.bleed = cv, s, total_w / s, total_h / s, (total_w, total_h), bleed
    dom = _dominant_color(cover_image)
    bc.bg_gradient(_mix(dom, 0.35), _mix(dom, 0.70))
    # panels in design units; with RTL books the front cover is on the RIGHT, otherwise on the right too
    # (printers expect front = right half of the spread for left-bound books; for Arabic the binding side
    # flips, so the order is mirrored).
    panel = tw / s
    spine_d, bleed_d = spine / s, bleed / s
    left_x0 = bleed_d
    right_x0 = bleed_d + panel + spine_d
    front_x0, back_x0 = (left_x0, right_x0) if rtl else (right_x0, left_x0)
    _draw_cover(bc, front_x0, panel, title, cover_image, rtl, child_name)
    # back cover: tagline + logo
    c = cv
    dark = (0.16, 0.17, 0.28)
    tag = _shape("قصة صُنعت خصيصاً لطفلك" if rtl else "A story made just for your child", rtl)
    c.setFont(DISPLAY, 24); c.setFillColor(Color(*dark))
    c.drawCentredString(back_x0 + panel / 2, bc.H * 0.55, tag)
    bc.logo_badge(rtl, _mix(dom, 0.05), right=back_x0 + panel)
    # spine title (only if wide enough)
    if spine_mm >= 6:
        c.saveState()
        c.translate(bleed_d + panel + spine_d / 2, bc.H / 2)
        c.rotate(90 if not rtl else -90)
        c.setFont(DISPLAY, 14); c.setFillColor(Color(*dark))
        c.drawCentredString(0, -5, _shape(title, rtl))
        c.restoreState()
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
