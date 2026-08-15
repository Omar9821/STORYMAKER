"""Quick visual/logical check that Arabic paragraph lines are in correct top-to-bottom order."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from PIL import Image, ImageDraw
import io
import pdf_service

# Build a fake cover image (solid colour) so _dominant_color works
def _img(color):
    im = Image.new("RGB", (400, 300), color)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

cover = _img((240, 200, 150))

# A long Arabic paragraph with clearly ORDERED sentences (1..6) that must wrap onto several lines.
pages = [
    {"text": "أولاً استيقظ الطفل من نومه في الصباح الباكر. ثانياً غسل وجهه وأسنانه بعناية شديدة. ثالثاً تناول فطوره اللذيذ مع عائلته المحبة. رابعاً ارتدى ملابسه المدرسية النظيفة. خامساً ذهب إلى المدرسة سعيداً. سادساً عاد إلى المنزل في المساء فرحاً.",
     "image": _img((150, 200, 240))},
]

pdf_bytes = pdf_service.build_book_pdf(
    "قصة الترتيب الصحيح", "العبرة الأولى ثم العبرة الثانية ثم العبرة الثالثة الأخيرة",
    pages, cover, "ar", "أحمد",
)
out = "/app/backend/tests/rtl_order_check.pdf"
with open(out, "wb") as f:
    f.write(pdf_bytes)
print("WROTE", out, len(pdf_bytes), "bytes")
