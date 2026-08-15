from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, Request, Depends, HTTPException, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from PIL import Image

import storage
import auth
import ai_service
import pdf_service
import payment_service
import fal_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("hikayati")

BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

BOOK_PRICE = int(os.environ.get("BOOK_PRICE_DZD", "3400"))

app = FastAPI(title="Hikayati API")
api = APIRouter(prefix="/api")

# ---------------- Status helpers ----------------
STATUS_FLOW = ["awaiting_payment", "paid", "generating", "review", "approved", "printing", "shipped", "delivered"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def push_status(order_id: str, status: str, note: str = ""):
    entry = {"status": status, "note": note, "timestamp": now_iso()}
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": now_iso()}, "$push": {"status_history": entry}},
    )


def public_order(o: dict) -> dict:
    o.pop("_id", None)
    o.pop("reference_photo_b64", None)
    return o


# ---------------- Models ----------------
class LoginBody(BaseModel):
    email: str
    password: str


class PayBody(BaseModel):
    method: str  # "cod" | "chargily"
    payment_method: Optional[str] = "edahabia"


class StatusUpdateBody(BaseModel):
    status: str
    note: Optional[str] = ""


class Character(BaseModel):
    name: str
    age: int = 5
    gender: str = "boy"
    hair_color: str = ""
    hair_type: str = ""
    hair_length: str = ""
    hobbies: str = ""
    favorite_color: str = ""
    favorite_food: str = ""
    relation: str = ""
    photo_path: str = ""
    is_main: bool = False


class Person(BaseModel):
    name: str = ""
    age: str = ""
    relation: str = ""


class OrderCreate(BaseModel):
    characters: list[Character]
    story_type: str
    positive_behaviors: str = ""
    negative_behaviors: str = ""
    special_details: str = ""
    language: str
    language_level: str = "simple"
    story_setting: list[str] = []
    lives_with: str
    mother_name: str = ""
    mother_age: str = ""
    father_name: str = ""
    father_age: str = ""
    mention_parents: bool = True
    siblings: list[Person] = []
    friends: list[Person] = []
    quantity: int = 1
    coupon_code: str = ""
    customer_name: str
    customer_phone: str
    customer_email: str = ""
    shipping_address: str
    wilaya: str
    consent: bool


class CouponBody(BaseModel):
    code: str
    type: str = "percent"  # percent | fixed
    value: float
    max_uses: int = 0  # 0 = unlimited
    expires_at: Optional[str] = None


class SettingsBody(BaseModel):
    base_price: int
    extra_character_price: int


class TicketBody(BaseModel):
    order_id: str = ""
    name: str
    message: str


class TicketReplyBody(BaseModel):
    reply: str


async def get_settings() -> dict:
    s = await db.settings.find_one({"_id": "config"})
    if not s:
        s = {"_id": "config", "base_price": BOOK_PRICE, "extra_character_price": 250}
        await db.settings.insert_one(s)
    return s


async def compute_coupon(code: str, subtotal: int):
    if not code:
        return 0, None
    c = await db.coupons.find_one({"code": code.upper(), "active": True})
    if not c:
        return 0, None
    if c.get("expires_at") and c["expires_at"] < now_iso():
        return 0, None
    if c.get("max_uses", 0) and c.get("used_count", 0) >= c["max_uses"]:
        return 0, None
    if c["type"] == "percent":
        disc = int(subtotal * c["value"] / 100)
    else:
        disc = int(c["value"])
    return min(disc, subtotal), c


def build_story_context(o: OrderCreate) -> str:
    main = o.characters[0]
    parts = []
    hair = " ".join(x for x in [main.hair_length, main.hair_color, main.hair_type] if x).strip()
    if hair:
        parts.append(f"hair: {hair}")
    if main.hobbies:
        parts.append(f"hobbies: {main.hobbies}")
    if main.favorite_color:
        parts.append(f"favorite colour: {main.favorite_color}")
    if main.favorite_food:
        parts.append(f"favorite food: {main.favorite_food}")
    if o.positive_behaviors:
        parts.append(f"gently reinforce these positive behaviours: {o.positive_behaviors}")
    if o.negative_behaviors:
        parts.append(f"gently and indirectly discourage: {o.negative_behaviors}")
    if o.special_details:
        parts.append(f"special details to include: {o.special_details}")
    if o.story_setting:
        parts.append(f"story takes place in: {', '.join(o.story_setting)}")
    if o.lives_with:
        parts.append(f"the child lives with: {o.lives_with}")
    if o.mention_parents:
        if o.mother_name:
            parts.append(f"mother: {o.mother_name} ({o.mother_age})")
        if o.father_name:
            parts.append(f"father: {o.father_name} ({o.father_age})")
    if o.siblings:
        parts.append("siblings: " + ", ".join(f"{s.name} ({s.age})" for s in o.siblings if s.name))
    if o.friends:
        parts.append("friends/relatives: " + ", ".join(f"{s.name} ({s.age}, {s.relation})" for s in o.friends if s.name))
    extra_chars = [c for c in o.characters[1:] if c.name]
    if extra_chars:
        parts.append("other main characters that appear throughout: " +
                     ", ".join(f"{c.name} ({c.age}, {c.gender}, {c.relation})" for c in extra_chars))
    return ". ".join(parts)


# ---------------- Generation pipeline ----------------
async def run_generation(order_id: str):
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order:
            return
        await push_status(order_id, "generating", "بدأ توليد القصة والرسومات")

        # Public URL of the reference photo (fal fetches it as the identity source)
        ref_url = f"{BACKEND_PUBLIC_URL}/api/files/{order['reference_photo_path']}"
        seed = order.get("gen_seed") or (uuid.uuid4().int % 1_000_000)

        story = await ai_service.generate_story(
            order["child_name"], order["child_age"], order["child_gender"],
            order["story_type"], order.get("behavior_focus", ""), order["language"],
            extra_context=order.get("extra_context", ""), level=order.get("story_level", "simple"),
        )

        pages_out = []
        image_count = 0

        # Cover (identity-preserving via fal PuLID)
        cover_scene = story["pages"][0]["scene"] if story["pages"] else f"{order['child_name']} smiling happily"
        cover_bytes = await asyncio.to_thread(
            fal_service.generate_illustration_pulid, ref_url, cover_scene, seed, True)
        cover_path = f"{storage.APP_NAME}/orders/{order_id}/cover.png"
        storage.put_object(cover_path, cover_bytes, "image/png")
        cover_sim = ai_service.mock_face_similarity(f"{order_id}-cover")
        image_count += 1

        # Story pages + coloring-book line art
        pdf_pages = []
        line_pages = []
        for i, pg in enumerate(story["pages"]):
            img_bytes = await asyncio.to_thread(
                fal_service.generate_illustration_pulid, ref_url, pg["scene"], seed, False)
            path = f"{storage.APP_NAME}/orders/{order_id}/page_{i+1}.png"
            storage.put_object(path, img_bytes, "image/png")

            line_bytes = pdf_service.make_line_art(img_bytes)
            line_path = f"{storage.APP_NAME}/orders/{order_id}/coloring_{i+1}.png"
            storage.put_object(line_path, line_bytes, "image/png")
            line_pages.append(line_bytes)

            sim = ai_service.mock_face_similarity(f"{order_id}-{i}")
            image_count += 1
            pages_out.append({
                "page_number": i + 1,
                "text": pg["text"],
                "scene": pg["scene"],
                "image_path": path,
                "coloring_path": line_path,
                "similarity_score": sim,
                "similarity_ok": sim >= ai_service.SIMILARITY_THRESHOLD,
                "moderation_ok": True,
            })
            pdf_pages.append({"text": pg["text"], "image": img_bytes})

        # Assemble story PDF
        pdf_bytes = pdf_service.build_book_pdf(
            story["title"], story.get("moral", ""), pdf_pages, cover_bytes,
            order["language"], order["child_name"],
        )
        pdf_path = f"{storage.APP_NAME}/orders/{order_id}/book.pdf"
        storage.put_object(pdf_path, pdf_bytes, "application/pdf")

        # Assemble free coloring-book PDF
        coloring_bytes = pdf_service.build_coloring_pdf(story["title"], line_pages, order["language"])
        coloring_pdf_path = f"{storage.APP_NAME}/orders/{order_id}/coloring_book.pdf"
        storage.put_object(coloring_pdf_path, coloring_bytes, "application/pdf")

        ai_cost = round(ai_service.COST_PER_TEXT_GEN + image_count * ai_service.COST_PER_IMAGE, 3)
        avg_sim = round(sum([p["similarity_score"] for p in pages_out] + [cover_sim]) / (len(pages_out) + 1), 2)

        await db.orders.update_one({"id": order_id}, {"$set": {
            "story_title": story["title"],
            "story_moral": story.get("moral", ""),
            "cover_path": cover_path,
            "cover_similarity": cover_sim,
            "pages": pages_out,
            "pdf_path": pdf_path,
            "coloring_pdf_path": coloring_pdf_path,
            "gen_seed": seed,
            "ai_cost_usd": ai_cost,
            "avg_similarity": avg_sim,
            "reference_photo_delete_after": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }})
        await push_status(order_id, "review", "اكتمل التوليد، في انتظار المراجعة البشرية")
        logger.info(f"Generation complete for {order_id}, cost=${ai_cost}")
    except Exception as e:
        logger.exception(f"Generation failed for {order_id}: {e}")
        await push_status(order_id, "failed", f"فشل التوليد: {str(e)[:200]}")


# ---------------- Partial regeneration + versioning ----------------
async def snapshot_version(order: dict):
    version = {
        "version": len(order.get("versions", [])) + 1,
        "timestamp": now_iso(),
        "story_title": order.get("story_title"),
        "story_moral": order.get("story_moral"),
        "cover_path": order.get("cover_path"),
        "pages": order.get("pages", []),
        "pdf_path": order.get("pdf_path"),
        "coloring_pdf_path": order.get("coloring_pdf_path"),
    }
    await db.orders.update_one({"id": order["id"]}, {"$push": {"versions": version}})


def _rebuild_pdfs(order: dict):
    """Read current images from storage and rebuild story + coloring PDFs. Returns (pdf_bytes, coloring_bytes)."""
    cover_bytes, _ = storage.get_object(order["cover_path"])
    pdf_pages, line_pages = [], []
    for p in order["pages"]:
        img_bytes, _ = storage.get_object(p["image_path"])
        pdf_pages.append({"text": p["text"], "image": img_bytes})
        if p.get("coloring_path"):
            line_bytes, _ = storage.get_object(p["coloring_path"])
            line_pages.append(line_bytes)
    pdf_bytes = pdf_service.build_book_pdf(
        order.get("story_title", ""), order.get("story_moral", ""), pdf_pages, cover_bytes,
        order["language"], order["child_name"])
    coloring_bytes = pdf_service.build_coloring_pdf(order.get("story_title", ""), line_pages, order["language"])
    return pdf_bytes, coloring_bytes


async def regenerate_single_page(order_id: str, page_number: int):
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order or order.get("reference_photo_deleted"):
            return
        await snapshot_version(order)
        await push_status(order_id, "generating", f"إعادة توليد الصفحة {page_number}")
        ref_url = f"{BACKEND_PUBLIC_URL}/api/files/{order['reference_photo_path']}"
        new_seed = (order.get("gen_seed") or 0) + page_number * 7 + uuid.uuid4().int % 1000
        pages = order["pages"]
        idx = next((i for i, p in enumerate(pages) if p["page_number"] == page_number), None)
        if idx is None:
            return
        scene = pages[idx]["scene"]
        img_bytes = await asyncio.to_thread(fal_service.generate_illustration_pulid, ref_url, scene, new_seed, False)
        storage.put_object(pages[idx]["image_path"], img_bytes, "image/png")
        line_bytes = pdf_service.make_line_art(img_bytes)
        storage.put_object(pages[idx]["coloring_path"], line_bytes, "image/png")
        order["pages"] = pages
        pdf_bytes, coloring_bytes = _rebuild_pdfs(order)
        storage.put_object(order["pdf_path"], pdf_bytes, "application/pdf")
        storage.put_object(order["coloring_pdf_path"], coloring_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {"pages": pages}})
        await push_status(order_id, "review", f"تمت إعادة توليد الصفحة {page_number}")
    except Exception as e:
        logger.exception(f"regen page failed: {e}")
        await push_status(order_id, "review", f"فشل إعادة توليد الصفحة: {str(e)[:120]}")


async def regenerate_text_only(order_id: str):
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order:
            return
        await snapshot_version(order)
        await push_status(order_id, "generating", "إعادة صياغة نص القصة")
        story = await ai_service.generate_story(
            order["child_name"], order["child_age"], order["child_gender"],
            order["story_type"], order.get("behavior_focus", ""), order["language"],
            extra_context=order.get("extra_context", ""), level=order.get("story_level", "simple"))
        pages = order["pages"]
        for i, p in enumerate(pages):
            if i < len(story["pages"]):
                p["text"] = story["pages"][i]["text"]
        order["pages"] = pages
        order["story_title"] = story["title"]
        order["story_moral"] = story.get("moral", "")
        pdf_bytes, coloring_bytes = _rebuild_pdfs(order)
        storage.put_object(order["pdf_path"], pdf_bytes, "application/pdf")
        storage.put_object(order["coloring_pdf_path"], coloring_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {
            "pages": pages, "story_title": story["title"], "story_moral": story.get("moral", "")}})
        await push_status(order_id, "review", "تمت إعادة صياغة النص")
    except Exception as e:
        logger.exception(f"regen text failed: {e}")
        await push_status(order_id, "review", f"فشل إعادة صياغة النص: {str(e)[:120]}")


# ---------------- Public routes ----------------
@api.get("/")
async def root():
    return {"message": "Hikayati API", "price": BOOK_PRICE}


@api.get("/config")
async def config():
    s = await get_settings()
    return {"price": s["base_price"], "base_price": s["base_price"],
            "extra_character_price": s["extra_character_price"],
            "currency": "DZD", "payment_mock": payment_service.MOCK_MODE}


def _validate_image_dims(data: bytes):
    """Returns (w, h, error_dict|None)."""
    try:
        w, h = Image.open(io.BytesIO(data)).size
    except Exception:
        return None, None, {"ok": False, "message": "الملف ليس صورة صالحة"}
    if min(w, h) < 400:
        return w, h, {"ok": False, "width": w, "height": h,
                      "message": "دقة الصورة منخفضة. استخدم صورة أوضح (400 بكسل على الأقل)"}
    return w, h, None


@api.post("/orders/check-photo")
async def check_photo(file: UploadFile = File(...)):
    data = await file.read()
    w, h, err = _validate_image_dims(data)
    if err:
        return err
    return {"ok": True, "width": w, "height": h, "message": "الصورة مناسبة"}


@api.post("/orders/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    data = await file.read()
    w, h, err = _validate_image_dims(data)
    if err:
        return err
    ext = (file.filename.split(".")[-1].lower() if "." in file.filename else "png")
    ct = storage.MIME_TYPES.get(ext, "image/png")
    path = f"{storage.APP_NAME}/references/{uuid.uuid4()}/photo.{ext}"
    storage.put_object(path, data, ct)
    return {"ok": True, "path": path, "width": w, "height": h, "message": "الصورة مناسبة"}


@api.post("/orders/validate-coupon")
async def validate_coupon(body: dict):
    code = (body.get("code") or "").strip()
    subtotal = int(body.get("subtotal") or 0)
    disc, c = await compute_coupon(code, subtotal)
    if not c:
        return {"valid": False, "discount": 0}
    return {"valid": True, "discount": disc, "type": c["type"], "value": c["value"]}


@api.post("/orders")
async def create_order(body: OrderCreate):
    if not body.consent:
        raise HTTPException(status_code=400, detail="الموافقة على سياسة الخصوصية مطلوبة")
    if not body.characters or not body.characters[0].name or not body.characters[0].photo_path:
        raise HTTPException(status_code=400, detail="الشخصية الأساسية وصورتها مطلوبة")

    settings = await get_settings()
    n_extra = max(0, len(body.characters) - 1)
    unit = settings["base_price"] + n_extra * settings["extra_character_price"]
    subtotal = unit * max(1, body.quantity)
    discount, coupon = await compute_coupon(body.coupon_code, subtotal)
    amount = subtotal - discount

    order_id = str(uuid.uuid4())
    main = body.characters[0]
    behavior_focus = "; ".join(x for x in [body.positive_behaviors, body.negative_behaviors] if x)

    order = {
        "id": order_id,
        "characters": [c.model_dump() for c in body.characters],
        "child_name": main.name,
        "child_age": main.age,
        "child_gender": main.gender,
        "story_type": body.story_type,
        "behavior_focus": behavior_focus,
        "positive_behaviors": body.positive_behaviors,
        "negative_behaviors": body.negative_behaviors,
        "special_details": body.special_details,
        "language": body.language,
        "story_level": body.language_level,
        "story_setting": body.story_setting,
        "extra_context": build_story_context(body),
        "lives_with": body.lives_with,
        "mother_name": body.mother_name, "mother_age": body.mother_age,
        "father_name": body.father_name, "father_age": body.father_age,
        "mention_parents": body.mention_parents,
        "siblings": [s.model_dump() for s in body.siblings],
        "friends": [s.model_dump() for s in body.friends],
        "quantity": max(1, body.quantity),
        "customer_name": body.customer_name,
        "customer_phone": body.customer_phone,
        "customer_email": body.customer_email,
        "shipping_address": body.shipping_address,
        "wilaya": body.wilaya,
        "consent": True,
        "consent_at": now_iso(),
        "reference_photo_path": main.photo_path,
        "reference_photo_deleted": False,
        "base_price": settings["base_price"],
        "extra_characters": n_extra,
        "extra_character_price": settings["extra_character_price"],
        "subtotal": subtotal,
        "coupon_code": (body.coupon_code or "").upper() if coupon else "",
        "discount": discount,
        "amount": amount,
        "currency": "DZD",
        "payment_method": None,
        "payment_status": "pending",
        "status": "awaiting_payment",
        "status_history": [{"status": "awaiting_payment", "note": "تم إنشاء الطلب", "timestamp": now_iso()}],
        "pages": [],
        "versions": [],
        "ai_cost_usd": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.orders.insert_one(order)
    if coupon:
        await db.coupons.update_one({"code": coupon["code"]}, {"$inc": {"used_count": 1}})
    return public_order(order)


@api.post("/orders/{order_id}/pay")
async def pay_order(order_id: str, body: PayBody):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order["status"] not in ("awaiting_payment",):
        return public_order(order)

    if body.method == "cod":
        await db.orders.update_one({"id": order_id}, {"$set": {
            "payment_method": "cod", "payment_status": "cod_pending"}})
        await push_status(order_id, "paid", "تم تأكيد الطلب (الدفع عند الاستلام)")
        asyncio.create_task(run_generation(order_id))
        return {"method": "cod", "order_id": order_id, "redirect": f"/track/{order_id}"}

    # Chargily / online
    checkout = await payment_service.create_checkout(order_id, order["amount"], body.payment_method)
    await db.orders.update_one({"id": order_id}, {"$set": {
        "payment_method": "chargily",
        "chargily_checkout_id": checkout["checkout_id"],
        "checkout_url": checkout["checkout_url"],
    }})
    return {"method": "chargily", "checkout_url": checkout["checkout_url"], "mock": checkout["mock"]}


@api.post("/payments/mock-confirm/{order_id}")
async def mock_confirm(order_id: str):
    if not payment_service.MOCK_MODE:
        raise HTTPException(status_code=400, detail="Mock confirmation disabled")
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order["status"] == "awaiting_payment":
        await db.orders.update_one({"id": order_id}, {"$set": {"payment_status": "paid"}})
        await push_status(order_id, "paid", "تم استلام الدفع (محاكاة)")
        asyncio.create_task(run_generation(order_id))
    return {"ok": True, "order_id": order_id}


@api.post("/payments/webhook")
async def chargily_webhook(request: Request):
    import json
    raw = await request.body()
    signature = request.headers.get("signature")
    if not payment_service.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    event = json.loads(raw)
    checkout_id = event.get("data", {}).get("id")
    etype = event.get("type")
    order = await db.orders.find_one({"chargily_checkout_id": checkout_id})
    if not order:
        raise HTTPException(status_code=404, detail="Unknown checkout")
    if etype == "checkout.paid" and order["status"] == "awaiting_payment":
        await db.orders.update_one({"id": order["id"]}, {"$set": {"payment_status": "paid"}})
        await push_status(order["id"], "paid", "تم استلام الدفع")
        asyncio.create_task(run_generation(order["id"]))
    return {"received": True}


@api.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return public_order(order)


@api.get("/files/{path:path}")
async def get_file(path: str):
    try:
        data, ct = storage.get_object(path)
        return Response(content=data, media_type=ct)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")


# ---------------- Admin routes ----------------
@api.post("/auth/login")
async def admin_login(body: LoginBody):
    admin = await db.admins.find_one({"email": body.email.lower()})
    if not admin or not auth.verify_password(body.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    token = auth.create_access_token(str(admin["_id"]), admin["email"])
    return {"token": token, "email": admin["email"], "name": admin.get("name", "Admin")}


@api.get("/auth/me")
async def admin_me(payload: dict = Depends(auth.require_admin)):
    return {"email": payload["email"], "role": payload["role"]}


@api.get("/admin/orders")
async def admin_list_orders(payload: dict = Depends(auth.require_admin), status: Optional[str] = None):
    q = {"status": status} if status else {}
    orders = await db.orders.find(q).sort("created_at", -1).to_list(500)
    return [public_order(o) for o in orders]


@api.get("/admin/stats")
async def admin_stats(payload: dict = Depends(auth.require_admin)):
    orders = await db.orders.find({}).to_list(2000)
    total_cost = sum(o.get("ai_cost_usd", 0) for o in orders)
    by_status, by_type, by_behavior = {}, {}, {}
    revenue = 0
    from datetime import date
    today = date.today().isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rev_today = rev_week = rev_month = 0
    for o in orders:
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
        by_type[o.get("story_type", "?")] = by_type.get(o.get("story_type", "?"), 0) + 1
        for b in filter(None, [o.get("positive_behaviors"), o.get("negative_behaviors")]):
            by_behavior[b] = by_behavior.get(b, 0) + 1
        if o.get("payment_status") in ("paid", "cod_pending"):
            amt = o.get("amount", 0)
            revenue += amt
            created = o.get("created_at", "")
            if created[:10] == today:
                rev_today += amt
            if created >= week_ago:
                rev_week += amt
            if created >= month_ago:
                rev_month += amt
    paid = [o for o in orders if o.get("payment_status") in ("paid", "cod_pending")]
    aov = round(revenue / len(paid)) if paid else 0
    top_behaviors = sorted(by_behavior.items(), key=lambda x: -x[1])[:5]
    return {
        "total_orders": len(orders),
        "total_ai_cost_usd": round(total_cost, 2),
        "revenue_dzd": revenue,
        "revenue_today": rev_today, "revenue_week": rev_week, "revenue_month": rev_month,
        "avg_order_value": aov,
        "by_status": by_status,
        "by_type": by_type,
        "top_behaviors": top_behaviors,
    }


@api.get("/admin/orders/{order_id}")
async def admin_get_order(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return public_order(order)


@api.post("/admin/orders/{order_id}/status")
async def admin_update_status(order_id: str, body: StatusUpdateBody, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    await push_status(order_id, body.status, body.note or "")
    # Auto-delete reference photo once approved (privacy)
    if body.status == "approved" and not order.get("reference_photo_deleted"):
        await db.orders.update_one({"id": order_id}, {"$set": {"reference_photo_deleted": True}})
    return {"ok": True}


@api.post("/admin/orders/{order_id}/regenerate")
async def admin_regenerate(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order.get("reference_photo_deleted"):
        raise HTTPException(status_code=400, detail="تم حذف صورة المرجع، لا يمكن إعادة التوليد")
    asyncio.create_task(run_generation(order_id))
    return {"ok": True}


@api.delete("/admin/orders/{order_id}/reference-photo")
async def admin_delete_reference(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    await db.orders.update_one({"id": order_id}, {"$set": {"reference_photo_deleted": True}})
    await db.privacy_logs.insert_one({
        "id": str(uuid.uuid4()), "order_id": order_id, "action": "reference_photo_deleted",
        "by": payload["email"], "timestamp": now_iso(),
    })
    return {"ok": True}


@api.get("/admin/privacy-logs")
async def admin_privacy_logs(payload: dict = Depends(auth.require_admin)):
    logs = await db.privacy_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return logs


@api.get("/admin/settings")
async def admin_get_settings(payload: dict = Depends(auth.require_admin)):
    s = await get_settings()
    return {"base_price": s["base_price"], "extra_character_price": s["extra_character_price"]}


@api.put("/admin/settings")
async def admin_put_settings(body: SettingsBody, payload: dict = Depends(auth.require_admin)):
    await db.settings.update_one({"_id": "config"}, {"$set": {
        "base_price": body.base_price, "extra_character_price": body.extra_character_price}}, upsert=True)
    return {"ok": True}


@api.get("/admin/coupons")
async def admin_list_coupons(payload: dict = Depends(auth.require_admin)):
    return await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/admin/coupons")
async def admin_create_coupon(body: CouponBody, payload: dict = Depends(auth.require_admin)):
    doc = {"code": body.code.upper(), "type": body.type, "value": body.value,
           "max_uses": body.max_uses, "used_count": 0, "expires_at": body.expires_at,
           "active": True, "created_at": now_iso()}
    await db.coupons.update_one({"code": doc["code"]}, {"$set": doc}, upsert=True)
    return {"ok": True}


@api.delete("/admin/coupons/{code}")
async def admin_delete_coupon(code: str, payload: dict = Depends(auth.require_admin)):
    await db.coupons.update_one({"code": code.upper()}, {"$set": {"active": False}})
    return {"ok": True}


@api.post("/admin/orders/{order_id}/regenerate-page/{page_number}")
async def admin_regenerate_page(order_id: str, page_number: int, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order.get("reference_photo_deleted"):
        raise HTTPException(status_code=400, detail="تم حذف صورة المرجع")
    asyncio.create_task(regenerate_single_page(order_id, page_number))
    return {"ok": True}


@api.post("/admin/orders/{order_id}/regenerate-text")
async def admin_regenerate_text(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    asyncio.create_task(regenerate_text_only(order_id))
    return {"ok": True}


@api.post("/tickets")
async def create_ticket(body: TicketBody):
    ticket = {"id": str(uuid.uuid4()), "order_id": body.order_id, "name": body.name,
              "message": body.message, "status": "open", "reply": None, "created_at": now_iso()}
    await db.tickets.insert_one(ticket)
    ticket.pop("_id", None)
    return ticket


@api.get("/tickets/{order_id}")
async def order_tickets(order_id: str):
    return await db.tickets.find({"order_id": order_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api.get("/admin/tickets")
async def admin_tickets(payload: dict = Depends(auth.require_admin)):
    return await db.tickets.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@api.post("/admin/tickets/{ticket_id}/reply")
async def admin_reply_ticket(ticket_id: str, body: TicketReplyBody, payload: dict = Depends(auth.require_admin)):
    await db.tickets.update_one({"id": ticket_id}, {"$set": {
        "reply": body.reply, "status": "answered", "replied_at": now_iso()}})
    return {"ok": True}


# ---------------- App wiring ----------------
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        storage.init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await auth.seed_admin(db)
    await get_settings()
    await db.orders.create_index("id", unique=True)
    await db.coupons.create_index("code", unique=True)
    await db.tickets.create_index("order_id")
    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    client.close()
