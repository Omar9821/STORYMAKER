from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal

from fastapi import FastAPI, APIRouter, UploadFile, File, Request, Depends, HTTPException, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

import storage
import auth
import payment_service
import security
import jobs
import pipeline
import notify
import illustrator
import errors_i18n

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("hikayati")

BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

BOOK_PRICE = int(os.environ.get("BOOK_PRICE_DZD", "3400"))
RETENTION_UNPAID_DAYS = int(os.environ.get("RETENTION_UNPAID_DAYS", "7"))


def _check_config():
    """Fail fast on missing secrets (review item C1) and warn about risky/misconfigured values."""
    if not os.environ.get("JWT_SECRET"):
        raise RuntimeError("JWT_SECRET is not set")
    if len(os.environ["JWT_SECRET"]) < 24:
        logger.warning("JWT_SECRET is shorter than 24 characters — use a long random value")
    if not BACKEND_PUBLIC_URL:
        logger.warning("BACKEND_PUBLIC_URL is not set: fal cannot fetch reference photos and illustrations will fail")
    if not os.environ.get("CHARGILY_SECRET_KEY") and os.environ.get("PAYMENT_MOCK", "").lower() not in ("1", "true", "yes"):
        logger.warning("No CHARGILY_SECRET_KEY: online payment disabled (cash on delivery only)")
    if not FRONTEND_URL:
        logger.warning("FRONTEND_URL is not set: payment return URLs and CORS default may be wrong")


_check_config()

from contextlib import asynccontextmanager  # noqa: E402

_bg_tasks = []


@asynccontextmanager
async def lifespan(app_: FastAPI):
    try:
        await asyncio.to_thread(storage.init_storage)
        logger.info("Storage initialized")
        app_.state.storage_ok = True
    except Exception as e:
        app_.state.storage_ok = False
        logger.error(f"Storage init failed: {e}")
    await auth.seed_admin(db)
    await get_settings()
    await db.orders.create_index("id", unique=True)
    for field in ("status", "created_at", "customer_phone", "chargily_checkout_id", "chargily_checkout_ids"):
        await db.orders.create_index(field)
    await db.coupons.create_index("code", unique=True)
    await db.tickets.create_index("order_id")
    await db.jobs.create_index([("order_id", 1), ("status", 1)])
    await db.jobs.create_index([("status", 1), ("created_at", 1)])
    await jobs.recover_stale(db, _job_failed)
    # legacy / crashed orders left "generating" with no job behind them
    async for o in db.orders.find({"status": "generating"}, {"id": 1}):
        if not await jobs.active_job(db, o["id"]):
            await pipeline.push_status(db, o["id"], "failed", "توقفت المعالجة بسبب إعادة تشغيل الخادم")
            await notify.alert(f"طلب عالق في حالة التوليد وأُعيد إلى 'فشل': {o['id']}")
    _bg_tasks.append(asyncio.create_task(jobs.worker(db, pipeline.handlers(db), _job_failed)))
    _bg_tasks.append(asyncio.create_task(_privacy_sweeper()))
    logger.info("Startup complete")
    yield
    jobs.stop()
    for t in _bg_tasks:
        t.cancel()
    client.close()


app = FastAPI(title="Hikayati API", lifespan=lifespan)
app.add_exception_handler(StarletteHTTPException, errors_i18n.http_exception_handler)
api = APIRouter(prefix="/api")


async def _job_failed(job: dict, reason: str):
    oid = job.get("order_id")
    if oid:
        await pipeline.push_status(db, oid, "failed", f"فشلت المهمة: {reason[:150]}")
    await notify.alert(f"فشلت مهمة {job.get('kind')} للطلب {oid}: {reason[:300]}")


# ---------------- Status model (H13) ----------------
STATUS_FLOW = ["awaiting_payment", "paid", "generating", "review", "approved", "printing", "shipped", "delivered"]
ALL_STATUSES = STATUS_FLOW + ["failed", "cancelled", "refunded"]
# manual transitions an admin may perform (system transitions bypass this table)
ALLOWED = {
    "awaiting_payment": {"paid", "cancelled"},
    "paid": {"cancelled", "refunded"},
    "generating": {"failed"},
    "review": {"approved", "cancelled"},
    "approved": {"printing", "shipped", "review", "cancelled"},
    "printing": {"shipped", "approved", "cancelled"},
    "shipped": {"delivered", "refunded"},
    "delivered": {"refunded"},
    "failed": {"cancelled", "review"},
    "cancelled": set(),
    "refunded": set(),
}
RELEASED = {"approved", "printing", "shipped", "delivered"}   # customer may see the finished book only now


def now_iso():
    return datetime.now(timezone.utc).isoformat()


PUBLIC_FIELDS = ["id", "status", "child_name", "story_title", "story_moral", "language", "story_type", "add_coloring",
                 "quantity", "subtotal", "discount", "shipping_fee", "amount", "currency", "payment_method",
                 "payment_status", "created_at", "updated_at", "tracking_number"]


def public_view(o: dict) -> dict:
    """C3: what an anonymous visitor holding the order link may see. No phone, address, e-mail, reference
    photo path, internal notes, costs or admin data. Pictures/PDFs appear only after admin approval."""
    out = {k: o[k] for k in PUBLIC_FIELDS if k in o}
    out["status_history"] = [{"status": h["status"], "timestamp": h["timestamp"]} for h in o.get("status_history", [])]
    if o.get("status") in RELEASED:
        out["cover_path"] = o.get("cover_path")
        out["pdf_path"] = o.get("pdf_path")
        if o.get("add_coloring"):
            out["coloring_pdf_path"] = o.get("coloring_pdf_path")
        out["pages"] = [{"page_number": p["page_number"], "text": p["text"], "image_path": p["image_path"]}
                        for p in o.get("pages", [])]
    else:
        out["pages"] = []
    return security.sign_tree(out)


def admin_view(o: dict) -> dict:
    o = dict(o)
    o.pop("_id", None)
    o.pop("reference_photo_b64", None)
    return security.sign_tree(o, include_sensitive=True)


# ---------------- Models (H10 / H13: bounded, typed input) ----------------
Phone = Field(min_length=6, max_length=25, pattern=r"^[0-9+\-\s()]+$")


class LoginBody(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(max_length=200)


class PayBody(BaseModel):
    method: Literal["cod", "chargily"]
    payment_method: Optional[str] = Field(default="edahabia", max_length=30)


class StatusUpdateBody(BaseModel):
    status: str = Field(max_length=30)
    note: Optional[str] = Field(default="", max_length=300)


class BulkActionBody(BaseModel):
    order_ids: List[str] = Field(max_length=200)
    action: Literal["delete", "status"]
    status: Optional[str] = None
    note: Optional[str] = Field(default="", max_length=300)


class Character(BaseModel):
    name: str = Field(max_length=60)
    age: int = Field(default=5, ge=0, le=100)
    gender: str = Field(default="boy", max_length=20)
    hobbies: str = Field(default="", max_length=300)
    favorite_color: str = Field(default="", max_length=60)
    favorite_food: str = Field(default="", max_length=100)
    relation: str = Field(default="", max_length=60)
    photo_path: str = Field(default="", max_length=400)
    is_main: bool = False


class Person(BaseModel):
    name: str = Field(default="", max_length=60)
    age: str = Field(default="", max_length=20)
    relation: str = Field(default="", max_length=60)


class OrderCreate(BaseModel):
    characters: List[Character] = Field(min_length=1, max_length=6)
    story_type: Literal["encouragement", "behavior", "behavior_correction"]
    positive_behaviors: str = Field(default="", max_length=400)
    negative_behaviors: str = Field(default="", max_length=400)
    special_details: str = Field(default="", max_length=600)
    favorite_things: str = Field(default="", max_length=400)
    pet_name: str = Field(default="", max_length=60)
    pet_type: str = Field(default="", max_length=60)
    pet_photo_path: str = Field(default="", max_length=400)
    language: Literal["ar", "fr", "en"]
    language_level: Literal["simple", "medium", "advanced"] = "simple"
    art_style: Literal["cartoon", "watercolor", "3d"] = "cartoon"
    add_coloring: bool = False
    story_setting: List[str] = Field(default=[], max_length=8)
    lives_with: str = Field(max_length=120)
    mother_name: str = Field(default="", max_length=60)
    mother_age: str = Field(default="", max_length=20)
    father_name: str = Field(default="", max_length=60)
    father_age: str = Field(default="", max_length=20)
    mention_parents: bool = True
    siblings: List[Person] = Field(default=[], max_length=8)
    friends: List[Person] = Field(default=[], max_length=8)
    quantity: int = Field(default=1, ge=1, le=20)
    coupon_code: str = Field(default="", max_length=40)
    customer_name: str = Field(min_length=2, max_length=100)
    customer_phone: str = Phone
    customer_email: str = Field(default="", max_length=120)
    shipping_address: str = Field(min_length=3, max_length=300)
    wilaya: str = Field(min_length=2, max_length=60)
    consent: bool


class CouponBody(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    type: Literal["percent", "fixed"] = "percent"
    value: float = Field(gt=0, le=1_000_000)
    max_uses: int = Field(default=0, ge=0, le=1_000_000)
    expires_at: Optional[str] = Field(default=None, max_length=40)


class CouponCheck(BaseModel):
    code: str = Field(default="", max_length=40)
    subtotal: int = Field(default=0, ge=0, le=10_000_000)


class SettingsBody(BaseModel):
    base_price: int = Field(ge=0, le=1_000_000)
    extra_character_price: int = Field(ge=0, le=1_000_000)
    coloring_price: int = Field(default=500, ge=0, le=1_000_000)
    coloring_original_price: int = Field(default=2800, ge=0, le=1_000_000)
    shipping_default_fee: int = Field(default=0, ge=0, le=100_000)
    shipping_fees: dict = Field(default={})


class TicketBody(BaseModel):
    order_id: str = Field(default="", max_length=60)
    name: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)


class TicketReplyBody(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


class ConfirmCodBody(BaseModel):
    shipping_fee: int = Field(ge=0, le=100_000)
    note: str = Field(default="", max_length=300)
    start_generation: bool = True


class PrintBody(BaseModel):
    trim: Literal["A5", "A4", "square21", "square15"] = "A5"
    bleed_mm: float = Field(default=3.0, ge=0, le=10)
    spine_mm: float = Field(default=3.0, ge=0, le=30)


class TextRegenBody(BaseModel):
    with_images: bool = True


# ---------------- Settings / pricing ----------------
async def get_settings() -> dict:
    s = await db.settings.find_one({"_id": "config"})
    if not s:
        s = {"_id": "config", "base_price": BOOK_PRICE, "extra_character_price": 250,
             "coloring_price": 500, "coloring_original_price": 2800}
        await db.settings.insert_one(s)
    defaults = {"coloring_price": 500, "coloring_original_price": 2800, "shipping_default_fee": 0, "shipping_fees": {}}
    patch = {k: v for k, v in defaults.items() if k not in s}
    if patch:
        s.update(patch)
        await db.settings.update_one({"_id": "config"}, {"$set": patch})
    return s


def shipping_fee_for(settings: dict, wilaya: str) -> int:
    fees = settings.get("shipping_fees") or {}
    key = (wilaya or "").strip().lower()
    for k, v in fees.items():
        if str(k).strip().lower() == key:
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                break
    return max(0, int(settings.get("shipping_default_fee", 0) or 0))


def _coupon_discount(c: dict, subtotal: int) -> int:
    disc = int(subtotal * c["value"] / 100) if c["type"] == "percent" else int(c["value"])
    return max(0, min(disc, subtotal))


async def find_coupon(code: str):
    if not code:
        return None
    c = await db.coupons.find_one({"code": code.strip().upper(), "active": True})
    if not c or (c.get("expires_at") and c["expires_at"] < now_iso()):
        return None
    if c.get("max_uses", 0) and c.get("used_count", 0) >= c["max_uses"]:
        return None
    return c


async def reserve_coupon(code: str, subtotal: int):
    """H6: atomic use-count increment (the filter itself enforces max_uses)."""
    c = await find_coupon(code)
    if not c:
        return 0, None
    flt = {"code": c["code"], "active": True}
    if c.get("max_uses", 0):
        flt["used_count"] = {"$lt": c["max_uses"]}
    res = await db.coupons.update_one(flt, {"$inc": {"used_count": 1}})
    if res.modified_count == 0:
        return 0, None
    return _coupon_discount(c, subtotal), c


async def release_coupon(order: dict):
    code = order.get("coupon_code")
    if code and not order.get("coupon_released") and order.get("payment_status") != "paid":
        await db.coupons.update_one({"code": code, "used_count": {"$gt": 0}}, {"$inc": {"used_count": -1}})
        await db.orders.update_one({"id": order["id"]}, {"$set": {"coupon_released": True}})


def build_story_context(o: OrderCreate) -> str:
    main = o.characters[0]
    parts = []
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
    if o.favorite_things:
        parts.append(f"things the child loves that MUST be woven into the plot as meaningful story "
                     f"elements (not passing mentions), used to serve the educational goal: {o.favorite_things}")
    if o.pet_name or o.pet_type:
        pet = " ".join(x for x in [o.pet_name, f"({o.pet_type})" if o.pet_type else ""] if x).strip()
        parts.append(f"the child has a pet named/of type '{pet}' — include it as a recurring companion "
                     f"character that helps advance the story's behavioural lesson")
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
    return security.clean_text(". ".join(parts), 1800)


# ---------------- Public routes ----------------
@api.get("/")
async def root():
    return {"message": "Hikayati API", "price": BOOK_PRICE}


@api.get("/health")
async def health(response: Response):
    """L9: liveness + dependency check (use it for uptime monitors)."""
    checks = {}
    try:
        await client.admin.command("ping")
        checks["mongo"] = "ok"
    except Exception as e:
        checks["mongo"] = f"error: {str(e)[:80]}"
    checks["storage"] = "ok" if getattr(app.state, "storage_ok", False) else "error"
    try:
        checks["jobs_queued"] = await db.jobs.count_documents({"status": "queued"})
        checks["jobs_running"] = await db.jobs.count_documents({"status": "running"})
        checks["jobs_failed_24h"] = await db.jobs.count_documents(
            {"status": "failed", "finished_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}})
    except Exception:
        pass
    healthy = checks["mongo"] == "ok" and checks["storage"] == "ok"
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@api.get("/config")
async def config():
    s = await get_settings()
    return {"price": s["base_price"], "base_price": s["base_price"],
            "extra_character_price": s["extra_character_price"],
            "coloring_price": s["coloring_price"],
            "coloring_original_price": s["coloring_original_price"],
            "shipping_default_fee": s.get("shipping_default_fee", 0), "shipping_fees": s.get("shipping_fees", {}),
            "currency": "DZD", "payment_mock": payment_service.MOCK_MODE, "payment_online": payment_service.ONLINE_ENABLED}


@api.post("/orders/check-photo")
async def check_photo(request: Request, file: UploadFile = File(...)):
    security.limiter.check(f"photo:{security.client_ip(request)}", 30, 60)
    data = await file.read(security.MAX_UPLOAD_BYTES + 1)
    clean, info = await asyncio.to_thread(security.process_upload, data)
    return info


@api.post("/orders/upload-photo")
async def upload_photo(request: Request, file: UploadFile = File(...)):
    security.limiter.check(f"photo:{security.client_ip(request)}", 30, 60)
    data = await file.read(security.MAX_UPLOAD_BYTES + 1)
    clean, info = await asyncio.to_thread(security.process_upload, data)   # H1: validated, re-encoded, EXIF removed
    if not clean:
        return info
    path = f"{storage.APP_NAME}/references/{uuid.uuid4()}/photo.jpg"       # extension is ours, never the client's
    await asyncio.to_thread(storage.put_object, path, clean, "image/jpeg")
    return {**info, "path": security.sign_path(path)}


@api.post("/orders/validate-coupon")
async def validate_coupon(body: CouponCheck, request: Request):
    security.limiter.check(f"coupon:{security.client_ip(request)}", 30, 60)
    c = await find_coupon(body.code)
    if not c:
        return {"valid": False, "discount": 0}
    return {"valid": True, "discount": _coupon_discount(c, body.subtotal), "type": c["type"], "value": c["value"]}


def _clean_photo(path: str) -> str:
    p = security.strip_query(path or "")
    if p and not security.valid_reference_path(p):
        raise HTTPException(status_code=400, detail="مسار الصورة غير صالح")      # H2
    return p


@api.post("/orders")
async def create_order(body: OrderCreate, request: Request):
    security.limiter.check(f"order:{security.client_ip(request)}", int(os.environ.get("ORDER_RATE_LIMIT", "20")), 3600)
    if not body.consent:
        raise HTTPException(status_code=400, detail="يجب الموافقة على الشروط")
    if not body.characters[0].name.strip() or not body.characters[0].photo_path:
        raise HTTPException(status_code=400, detail="صورة الطفل مطلوبة")
    for c in body.characters:
        c.photo_path = _clean_photo(c.photo_path)
        c.name = security.clean_text(c.name, 60)
    body.pet_photo_path = _clean_photo(body.pet_photo_path)
    body.customer_name = security.clean_text(body.customer_name, 100)
    body.shipping_address = security.clean_text(body.shipping_address, 300)

    settings = await get_settings()
    n_extra = max(0, len(body.characters) - 1)
    unit = settings["base_price"] + n_extra * settings["extra_character_price"]
    if body.add_coloring:
        unit += settings["coloring_price"]
    subtotal = unit * body.quantity
    discount, coupon = await reserve_coupon(body.coupon_code, subtotal)
    shipping_fee = shipping_fee_for(settings, body.wilaya)
    amount = subtotal - discount + shipping_fee

    order_id = str(uuid.uuid4())
    main = body.characters[0]
    behavior_focus = security.clean_text("; ".join(x for x in [body.positive_behaviors, body.negative_behaviors] if x), 600)

    order = {
        "id": order_id,
        "characters": [c.model_dump() for c in body.characters],
        "child_name": main.name, "child_age": main.age, "child_gender": main.gender,
        "story_type": body.story_type, "behavior_focus": behavior_focus,
        "positive_behaviors": security.clean_text(body.positive_behaviors, 400),
        "negative_behaviors": security.clean_text(body.negative_behaviors, 400),
        "special_details": security.clean_text(body.special_details, 600),
        "favorite_things": security.clean_text(body.favorite_things, 400),
        "pet_name": security.clean_text(body.pet_name, 60), "pet_type": security.clean_text(body.pet_type, 60),
        "pet_photo_path": body.pet_photo_path,
        "language": body.language, "story_level": body.language_level, "art_style": body.art_style,
        "add_coloring": body.add_coloring, "story_setting": [security.clean_text(x, 40) for x in body.story_setting],
        "extra_context": build_story_context(body), "lives_with": security.clean_text(body.lives_with, 120),
        "mother_name": security.clean_text(body.mother_name, 60), "mother_age": body.mother_age,
        "father_name": security.clean_text(body.father_name, 60), "father_age": body.father_age,
        "mention_parents": body.mention_parents,
        "siblings": [s.model_dump() for s in body.siblings], "friends": [s.model_dump() for s in body.friends],
        "quantity": body.quantity,
        "customer_name": body.customer_name, "customer_phone": body.customer_phone,
        "customer_email": body.customer_email, "shipping_address": body.shipping_address, "wilaya": body.wilaya,
        "consent": True, "consent_at": now_iso(),
        "reference_photo_path": main.photo_path, "reference_photo_deleted": False,
        "base_price": settings["base_price"], "extra_characters": n_extra,
        "extra_character_price": settings["extra_character_price"],
        "subtotal": subtotal, "coupon_code": coupon["code"] if coupon else "", "discount": discount,
        "shipping_fee": shipping_fee, "shipping_confirmed": False, "amount": amount, "currency": "DZD",
        "payment_method": None, "payment_status": "pending", "status": "awaiting_payment",
        "status_history": [{"status": "awaiting_payment", "note": "تم استلام الطلب، بانتظار التأكيد الهاتفي",
                            "timestamp": now_iso()}],
        "pages": [], "versions": [], "ai_cost_usd": 0, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.orders.insert_one(order)
    return public_view(order)


@api.post("/orders/{order_id}/pay")
async def pay_order(order_id: str, body: PayBody, request: Request):
    security.limiter.check(f"pay:{security.client_ip(request)}", 20, 3600)
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order["status"] not in ("awaiting_payment",):
        return public_view(order)

    if body.method == "cod":
        await db.orders.update_one({"id": order_id}, {"$set": {"payment_method": "cod", "payment_status": "cod_pending"}})
        await pipeline.push_status(db, order_id, "awaiting_payment", "تم تأكيد الطلب (الدفع عند الاستلام) — بانتظار التأكيد الهاتفي")
        return {"method": "cod", "order_id": order_id, "redirect": f"/track/{order_id}"}

    # Online payment (Chargily). Re-use an existing open checkout instead of creating (and losing) a new one.
    if order.get("chargily_checkout_url"):
        return {"method": "chargily", "checkout_url": order["chargily_checkout_url"], "order_id": order_id}
    try:
        result = await payment_service.create_checkout(order_id, int(order["amount"]), body.payment_method or "edahabia")
    except Exception:
        raise HTTPException(status_code=502, detail="تعذر إنشاء رابط الدفع")
    await db.orders.update_one({"id": order_id}, {"$set": {
        "payment_method": "chargily", "chargily_checkout_id": result["checkout_id"],
        "chargily_checkout_url": result["checkout_url"]}, "$addToSet": {"chargily_checkout_ids": result["checkout_id"]}})
    return {"method": "chargily", "checkout_url": result["checkout_url"], "order_id": order_id}


async def _start_generation(order_id: str, **params):
    return await jobs.enqueue(db, order_id, "generate", params)


@api.post("/payments/mock-confirm/{order_id}")
async def mock_confirm(order_id: str):
    if not payment_service.MOCK_MODE:
        raise HTTPException(status_code=400, detail="Mock confirmation disabled")
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order["status"] == "awaiting_payment":
        await db.orders.update_one({"id": order_id}, {"$set": {"payment_status": "paid"}})
        await pipeline.push_status(db, order_id, "paid", "تم استلام الدفع (محاكاة)")
        await _start_generation(order_id)
    return {"ok": True, "order_id": order_id}


@api.post("/payments/webhook")
async def chargily_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("signature")
    if not payment_service.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    event = json.loads(raw)
    data = event.get("data", {}) or {}
    checkout_id = data.get("id")
    order = await db.orders.find_one({"$or": [{"chargily_checkout_id": checkout_id}, {"chargily_checkout_ids": checkout_id}]})
    if not order:
        raise HTTPException(status_code=404, detail="Unknown checkout")
    if event.get("type") == "checkout.paid" and order["status"] == "awaiting_payment":
        paid_amount = data.get("amount")
        if paid_amount is not None and int(paid_amount) != int(order["amount"]):
            await db.orders.update_one({"id": order["id"]}, {"$set": {"payment_status": "amount_mismatch"}})
            await notify.alert(f"مبلغ الدفع لا يطابق الطلب {order['id']}: مدفوع {paid_amount} مقابل {order['amount']}")
            return {"received": True}
        await db.orders.update_one({"id": order["id"]}, {"$set": {"payment_status": "paid"}})
        await pipeline.push_status(db, order["id"], "paid", "تم استلام الدفع")
        try:
            await _start_generation(order["id"])
        except HTTPException:
            pass   # a job is already active for this order (duplicate webhook)
    return {"received": True}


@api.get("/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    security.limiter.check(f"track:{security.client_ip(request)}", 120, 60)
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return public_view(order)


@api.get("/files/{path:path}")
async def get_file(path: str, request: Request, exp: Optional[str] = None, sig: Optional[str] = None):
    """C3: files are served only with a valid signed URL (issued inside order responses) or an admin token."""
    if not path.startswith(storage.APP_NAME + "/") or ".." in path:
        raise HTTPException(status_code=404, detail="الملف غير موجود")
    if not security.verify_signature(path, exp, sig):
        try:
            await auth.require_admin(request)
        except HTTPException:
            raise HTTPException(status_code=403, detail="الرابط منتهي أو غير صالح")
    try:
        data, ct = await asyncio.to_thread(storage.get_object, path)   # C5: never block the event loop
    except Exception:
        raise HTTPException(status_code=404, detail="الملف غير موجود")
    return Response(content=data, media_type=ct, headers={"Cache-Control": "private, max-age=300",
                                                          "X-Content-Type-Options": "nosniff"})


# ---------------- Auth ----------------
@api.post("/auth/login")
async def admin_login(body: LoginBody, request: Request):
    key = f"{security.client_ip(request)}|{body.email.lower()}"
    security.login_throttle.check(key)                                   # H3
    admin = await db.admins.find_one({"email": body.email.lower()})
    ok = bool(admin) and await asyncio.to_thread(auth.verify_password, body.password, admin["password_hash"])
    if not ok:
        security.login_throttle.fail(key)
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    security.login_throttle.ok(key)
    token = auth.create_access_token(str(admin["_id"]), admin["email"])
    return {"token": token, "email": admin["email"], "name": admin.get("name", "Admin")}


@api.get("/auth/me")
async def admin_me(payload: dict = Depends(auth.require_admin)):
    return {"email": payload["email"], "role": payload["role"]}


# ---------------- Admin: orders ----------------
LIST_EXCLUDE = {"_id": 0, "versions": 0, "pages": 0, "story_data": 0, "status_history": 0, "extra_context": 0,
                "reference_photo_b64": 0}


@api.get("/admin/orders")
async def admin_list_orders(payload: dict = Depends(auth.require_admin), status: Optional[str] = None,
                            search: Optional[str] = None, limit: int = 200, skip: int = 0):
    import re
    q = {}
    if status:
        q["status"] = status
    if search:
        rx = {"$regex": re.escape(search[:60]), "$options": "i"}        # L1: escaped
        q["$or"] = [{"customer_name": rx}, {"customer_phone": rx}, {"child_name": rx}]
    limit = max(1, min(limit, 500))
    orders = await db.orders.find(q, LIST_EXCLUDE).sort("created_at", -1).skip(max(0, skip)).to_list(limit)
    return [security.sign_tree(o, include_sensitive=True) for o in orders]


async def _sum_amount(match: dict) -> int:
    rows = await db.orders.aggregate([{"$match": match}, {"$group": {"_id": None, "s": {"$sum": "$amount"}}}]).to_list(1)
    return int(rows[0]["s"]) if rows else 0


@api.get("/admin/stats")
async def admin_stats(payload: dict = Depends(auth.require_admin)):
    """H13: computed inside MongoDB (no 2000-document cap); revenue = money actually earned:
    online payments that were paid, plus cash-on-delivery orders that were DELIVERED. COD orders still
    in progress are reported separately as `pending_cod_dzd`."""
    total = await db.orders.count_documents({})
    by_status = {r["_id"]: r["n"] for r in await db.orders.aggregate(
        [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(50) if r["_id"]}
    by_type = {r["_id"] or "?": r["n"] for r in await db.orders.aggregate(
        [{"$group": {"_id": "$story_type", "n": {"$sum": 1}}}]).to_list(20)}
    cost_rows = await db.orders.aggregate([{"$group": {"_id": None, "c": {"$sum": "$ai_cost_usd"}}}]).to_list(1)
    total_cost = cost_rows[0]["c"] if cost_rows else 0

    inactive = ["cancelled", "refunded", "failed"]
    earned = {"$or": [{"payment_status": "paid", "status": {"$nin": ["cancelled", "refunded"]}},
                      {"payment_method": "cod", "status": "delivered"}]}
    utc_now = datetime.now(timezone.utc)
    day_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_ago, month_ago = (utc_now - timedelta(days=7)).isoformat(), (utc_now - timedelta(days=30)).isoformat()
    revenue = await _sum_amount(earned)
    earned_n = await db.orders.count_documents(earned)
    pending_cod = await _sum_amount({"payment_status": "cod_pending",
                                     "status": {"$nin": inactive + ["delivered"]}})
    beh = {}
    for fld in ("positive_behaviors", "negative_behaviors"):
        for r in await db.orders.aggregate([{"$match": {fld: {"$nin": ["", None]}}},
                                            {"$group": {"_id": f"${fld}", "n": {"$sum": 1}}},
                                            {"$sort": {"n": -1}}, {"$limit": 10}]).to_list(10):
            beh[r["_id"]] = beh.get(r["_id"], 0) + r["n"]
    return {
        "total_orders": total, "total_ai_cost_usd": round(total_cost, 2), "revenue_dzd": revenue,
        "pending_cod_dzd": pending_cod,
        "revenue_today": await _sum_amount({**earned, "created_at": {"$gte": day_start}}),
        "revenue_week": await _sum_amount({**earned, "created_at": {"$gte": week_ago}}),
        "revenue_month": await _sum_amount({**earned, "created_at": {"$gte": month_ago}}),
        "avg_order_value": round(revenue / earned_n) if earned_n else 0,
        "by_status": by_status, "by_type": by_type,
        "top_behaviors": sorted(beh.items(), key=lambda x: -x[1])[:5],
    }


@api.get("/admin/orders/{order_id}")
async def admin_get_order(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    view = admin_view(order)
    view["active_job"] = await jobs.active_job(db, order_id)
    return view


@api.post("/admin/orders/{order_id}/rebuild-pdf")
async def admin_rebuild_pdf(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if not order.get("pages") or not order.get("cover_path"):
        raise HTTPException(status_code=400, detail="لا توجد قصة جاهزة لهذا الطلب")
    await pipeline.rebuild_pdfs(db, order)
    await pipeline.push_status(db, order_id, order.get("status", "review"), "أُعيد بناء ملف PDF")
    return {"ok": True}


async def _delete_order_fully(order: dict):
    """Delete the order AND its stored files (C2: nothing is left orphaned), release its coupon."""
    await release_coupon(order)
    ok, bad = await pipeline.purge_order_files(order)
    await db.jobs.delete_many({"order_id": order["id"]})
    await db.orders.delete_one({"id": order["id"]})
    await db.privacy_logs.insert_one({"id": str(uuid.uuid4()), "order_id": order["id"], "action": "order_deleted",
                                      "files_deleted": ok, "files_failed": bad, "timestamp": now_iso()})
    return ok, bad


@api.delete("/admin/orders/{order_id}")
async def admin_delete_order(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if await jobs.active_job(db, order_id):
        raise HTTPException(status_code=409, detail="الطلب قيد المعالجة بالفعل، انتظر حتى ينتهي")
    ok, bad = await _delete_order_fully(order)
    return {"ok": True, "deleted": 1, "files_deleted": ok, "files_failed": bad}


async def _change_status(order: dict, new: str, note: str = "") -> None:
    """Validated manual transition (H13)."""
    if new not in ALL_STATUSES:
        raise HTTPException(status_code=400, detail="حالة غير معروفة")
    cur = order["status"]
    if new != cur and new not in ALLOWED.get(cur, set()):
        raise HTTPException(status_code=400, detail="الانتقال بين هذه الحالتين غير مسموح")
    if new == "paid" and order.get("payment_status") == "pending":
        await db.orders.update_one({"id": order["id"]}, {"$set": {"payment_status": "cod_pending", "payment_method": "cod"}})
    await pipeline.push_status(db, order["id"], new, note)
    if new in ("cancelled", "refunded"):
        await release_coupon(order)
    if new in ("shipped", "delivered", "cancelled", "refunded"):
        await _purge_references({**order, "status": new}, by="auto-on-status")


@api.post("/admin/orders/bulk")
async def admin_bulk_orders(body: BulkActionBody, payload: dict = Depends(auth.require_admin)):
    if not body.order_ids:
        raise HTTPException(status_code=400, detail="لم يتم تحديد أي طلب")
    if body.action == "delete":
        n = 0
        for oid in body.order_ids:
            o = await db.orders.find_one({"id": oid})
            if o and not await jobs.active_job(db, oid):
                await _delete_order_fully(o)
                n += 1
        return {"ok": True, "deleted": n}
    if not body.status:
        raise HTTPException(status_code=400, detail="حالة غير معروفة")
    count, skipped = 0, 0
    for oid in body.order_ids:
        o = await db.orders.find_one({"id": oid})
        if not o:
            continue
        try:
            await _change_status(o, body.status, body.note or "")
            count += 1
        except HTTPException:
            skipped += 1
    return {"ok": True, "updated": count, "skipped_invalid_transition": skipped}


@api.post("/admin/orders/{order_id}/status")
async def admin_update_status(order_id: str, body: StatusUpdateBody, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    await _change_status(order, body.status, security.clean_text(body.note or "", 300))
    return {"ok": True}


@api.post("/admin/orders/{order_id}/confirm-cod")
async def admin_confirm_cod(order_id: str, body: ConfirmCodBody, payload: dict = Depends(auth.require_admin)):
    """Phone confirmation of a cash-on-delivery order: the admin agrees the SHIPPING FEE with the customer,
    the order total is recomputed, and generation starts."""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order["status"] != "awaiting_payment":
        raise HTTPException(status_code=400, detail="الانتقال بين هذه الحالتين غير مسموح")
    if order.get("reference_photo_deleted"):
        raise HTTPException(status_code=400, detail="تم حذف صورة المرجع، لا يمكن التوليد")
    total = int(order["subtotal"]) - int(order.get("discount", 0)) + body.shipping_fee
    await db.orders.update_one({"id": order_id}, {"$set": {
        "payment_method": "cod", "payment_status": "cod_pending", "shipping_fee": body.shipping_fee,
        "shipping_confirmed": True, "amount": total, "confirmed_by": payload["email"], "confirmed_at": now_iso()}})
    await pipeline.push_status(db, order_id, "paid",
                               f"تأكيد هاتفي — رسوم الشحن {body.shipping_fee} دج، الإجمالي {total} دج"
                               + (f" — {security.clean_text(body.note, 200)}" if body.note else ""))
    job = await _start_generation(order_id) if body.start_generation else None
    return {"ok": True, "amount": total, "shipping_fee": body.shipping_fee, "job_id": job["id"] if job else None}


@api.post("/admin/orders/{order_id}/regenerate")
async def admin_regenerate(order_id: str, reuse_story: bool = False, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if order.get("reference_photo_deleted"):
        raise HTTPException(status_code=400, detail="تم حذف صورة المرجع، لا يمكن التوليد")
    if order.get("payment_status") == "pending":
        await db.orders.update_one({"id": order_id}, {"$set": {"payment_method": "cod", "payment_status": "cod_pending"}})
    job = await _start_generation(order_id, reuse_story=reuse_story)
    return {"ok": True, "job_id": job["id"]}


async def _purge_references(order: dict, by: str):
    """C2: really delete the reference photos (child, siblings, pet) and say honestly what happened."""
    if order.get("reference_files_purged") or not order.get("pages") and by == "auto-on-status" and order["status"] not in ("cancelled", "refunded"):
        return
    paths = pipeline.reference_paths(order)
    ok, bad = await pipeline.purge_files(paths)
    await db.orders.update_one({"id": order["id"]}, {"$set": {
        "reference_photo_deleted": True, "reference_files_purged": bad == 0, "reference_files_failed": bad}})
    await db.privacy_logs.insert_one({"id": str(uuid.uuid4()), "order_id": order["id"], "action": "reference_files_purged",
                                      "by": by, "files_deleted": ok, "files_failed": bad, "timestamp": now_iso()})


@api.delete("/admin/orders/{order_id}/reference-photo")
async def admin_delete_reference(order_id: str, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    order["reference_files_purged"] = False
    await _purge_references({**order, "pages": order.get("pages") or [1]}, by=payload["email"])
    fresh = await db.orders.find_one({"id": order_id})
    return {"ok": True, "purged": bool(fresh.get("reference_files_purged")), "failed": fresh.get("reference_files_failed", 0)}


@api.get("/admin/privacy-logs")
async def admin_privacy_logs(payload: dict = Depends(auth.require_admin)):
    return await db.privacy_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(500)


@api.get("/admin/settings")
async def admin_get_settings(payload: dict = Depends(auth.require_admin)):
    s = await get_settings()
    return {k: s.get(k) for k in ("base_price", "extra_character_price", "coloring_price", "coloring_original_price",
                                  "shipping_default_fee", "shipping_fees")}


@api.put("/admin/settings")
async def admin_put_settings(body: SettingsBody, payload: dict = Depends(auth.require_admin)):
    fees = {}
    for k, v in (body.shipping_fees or {}).items():
        try:
            fees[str(k)[:60]] = max(0, min(int(v), 100_000))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="رسوم الشحن غير صالحة")
    await db.settings.update_one({"_id": "config"}, {"$set": {
        "base_price": body.base_price, "extra_character_price": body.extra_character_price,
        "coloring_price": body.coloring_price, "coloring_original_price": body.coloring_original_price,
        "shipping_default_fee": body.shipping_default_fee, "shipping_fees": fees}}, upsert=True)
    return {"ok": True}


@api.get("/admin/coupons")
async def admin_list_coupons(payload: dict = Depends(auth.require_admin)):
    return await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/admin/coupons")
async def admin_create_coupon(body: CouponBody, payload: dict = Depends(auth.require_admin)):
    if body.type == "percent" and body.value > 100:
        raise HTTPException(status_code=400, detail="قيمة الخصم غير صالحة")
    code = body.code.upper()
    existing = await db.coupons.find_one({"code": code})
    doc = {"code": code, "type": body.type, "value": body.value, "max_uses": body.max_uses,
           "used_count": existing.get("used_count", 0) if existing else 0, "expires_at": body.expires_at,
           "active": True, "created_at": existing.get("created_at") if existing else now_iso()}
    await db.coupons.update_one({"code": code}, {"$set": doc}, upsert=True)
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
        raise HTTPException(status_code=400, detail="تم حذف صورة المرجع، لا يمكن التوليد")
    if not any(p["page_number"] == page_number for p in order.get("pages", [])):   # H9b: validate BEFORE queuing
        raise HTTPException(status_code=404, detail="الصفحة غير موجودة")
    job = await jobs.enqueue(db, order_id, "regenerate_page", {"page_number": page_number})
    return {"ok": True, "job_id": job["id"]}


@api.post("/admin/orders/{order_id}/regenerate-text")
async def admin_regenerate_text(order_id: str, body: Optional[TextRegenBody] = None,
                                payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    job = await jobs.enqueue(db, order_id, "regenerate_text", {"with_images": (body.with_images if body else True)})
    return {"ok": True, "job_id": job["id"]}


@api.post("/admin/orders/{order_id}/restore-version/{version_num}")
async def admin_restore_version(order_id: str, version_num: int, payload: dict = Depends(auth.require_admin)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if not any(v["version"] == version_num for v in order.get("versions", [])):
        raise HTTPException(status_code=404, detail="النسخة غير موجودة")
    job = await jobs.enqueue(db, order_id, "restore_version", {"version": version_num})
    return {"ok": True, "job_id": job["id"]}


@api.post("/admin/orders/{order_id}/build-print")
async def admin_build_print(order_id: str, body: Optional[PrintBody] = None, payload: dict = Depends(auth.require_admin)):
    """L7: build print-ready files (interior with bleed + flat cover spread)."""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    if not order.get("pages") or not order.get("cover_path"):
        raise HTTPException(status_code=400, detail="لا توجد قصة جاهزة لهذا الطلب")
    job = await jobs.enqueue(db, order_id, "build_print", (body or PrintBody()).model_dump())
    return {"ok": True, "job_id": job["id"]}


# ---------------- Tickets (H5) ----------------
@api.post("/tickets")
async def create_ticket(body: TicketBody, request: Request):
    security.limiter.check(f"ticket:{security.client_ip(request)}", 5, 600)
    if body.order_id and not await db.orders.find_one({"id": body.order_id}, {"id": 1}):
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    ticket = {"id": str(uuid.uuid4()), "order_id": body.order_id, "name": security.clean_text(body.name, 80),
              "message": security.clean_text(body.message, 2000), "status": "open", "reply": None, "created_at": now_iso()}
    await db.tickets.insert_one(ticket)
    ticket.pop("_id", None)
    return ticket


@api.get("/tickets/{order_id}")
async def order_tickets(order_id: str, request: Request):
    security.limiter.check(f"ticketread:{security.client_ip(request)}", 60, 60)
    return await db.tickets.find({"order_id": order_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api.get("/admin/tickets")
async def admin_tickets(payload: dict = Depends(auth.require_admin)):
    return await db.tickets.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@api.post("/admin/tickets/{ticket_id}/reply")
async def admin_reply_ticket(ticket_id: str, body: TicketReplyBody, payload: dict = Depends(auth.require_admin)):
    await db.tickets.update_one({"id": ticket_id}, {"$set": {
        "reply": security.clean_text(body.reply, 2000), "status": "answered", "replied_at": now_iso()}})
    return {"ok": True}


# ---------------- Privacy sweeper (C2) ----------------
async def _sweep_once():
    now = datetime.now(timezone.utc)
    # 1. unpaid orders expire: cancel, release coupon, delete the photos
    cutoff = (now - timedelta(days=RETENTION_UNPAID_DAYS)).isoformat()
    async for o in db.orders.find({"status": "awaiting_payment", "created_at": {"$lt": cutoff}}):
        if await jobs.active_job(db, o["id"]):
            continue
        await pipeline.push_status(db, o["id"], "cancelled", f"أُلغي تلقائياً: لم يُؤكَّد خلال {RETENTION_UNPAID_DAYS} أيام")
        await release_coupon(o)
        await _purge_references(o, by="retention-unpaid")
    # 2. delivered/shipped orders whose retention period passed
    async for o in db.orders.find({"status": {"$in": ["shipped", "delivered"]}, "reference_files_purged": {"$ne": True},
                                   "reference_photo_delete_after": {"$lte": now.isoformat()}}):
        await _purge_references(o, by="retention-after-delivery")
    # 3. photos flagged deleted but whose files could not be removed earlier: retry
    async for o in db.orders.find({"reference_photo_deleted": True, "reference_files_purged": {"$ne": True}}):
        await _purge_references({**o, "pages": o.get("pages") or [1]}, by="retry")


async def _privacy_sweeper():
    await asyncio.sleep(60)
    while True:
        try:
            await _sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"privacy sweeper failed: {e}")
        await asyncio.sleep(6 * 3600)


# ---------------- App wiring ----------------
app.include_router(api)
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if not _origins:
    _origins = [FRONTEND_URL] if FRONTEND_URL else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,           # the admin token travels in the Authorization header, not in cookies (H4)
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Lang"],
)
