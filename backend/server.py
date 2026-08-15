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


# ---------------- Public routes ----------------
@api.get("/")
async def root():
    return {"message": "Hikayati API", "price": BOOK_PRICE}


@api.get("/config")
async def config():
    return {"price": BOOK_PRICE, "currency": "DZD", "payment_mock": payment_service.MOCK_MODE}


@api.post("/orders/check-photo")
async def check_photo(file: UploadFile = File(...)):
    data = await file.read()
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
    except Exception:
        return {"ok": False, "message": "الملف ليس صورة صالحة"}
    if min(w, h) < 400:
        return {"ok": False, "width": w, "height": h,
                "message": "دقة الصورة منخفضة. استخدم صورة أوضح (400 بكسل على الأقل)"}
    return {"ok": True, "width": w, "height": h, "message": "الصورة مناسبة"}


@api.post("/orders")
async def create_order(
    child_name: str = Form(...),
    child_age: int = Form(...),
    child_gender: str = Form(...),
    story_type: str = Form(...),
    behavior_focus: str = Form(""),
    language: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_email: str = Form(""),
    shipping_address: str = Form(...),
    wilaya: str = Form(...),
    consent: bool = Form(...),
    photo: UploadFile = File(...),
):
    if not consent:
        raise HTTPException(status_code=400, detail="الموافقة على سياسة الخصوصية مطلوبة")

    order_id = str(uuid.uuid4())
    data = await photo.read()
    ext = (photo.filename.split(".")[-1].lower() if "." in photo.filename else "png")
    ct = storage.MIME_TYPES.get(ext, "image/png")
    ref_path = f"{storage.APP_NAME}/references/{order_id}/photo.{ext}"
    storage.put_object(ref_path, data, ct)

    order = {
        "id": order_id,
        "child_name": child_name,
        "child_age": child_age,
        "child_gender": child_gender,
        "story_type": story_type,
        "behavior_focus": behavior_focus,
        "language": language,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "shipping_address": shipping_address,
        "wilaya": wilaya,
        "consent": True,
        "consent_at": now_iso(),
        "reference_photo_path": ref_path,
        "reference_photo_deleted": False,
        "amount": BOOK_PRICE,
        "currency": "DZD",
        "payment_method": None,
        "payment_status": "pending",
        "status": "awaiting_payment",
        "status_history": [{"status": "awaiting_payment", "note": "تم إنشاء الطلب", "timestamp": now_iso()}],
        "pages": [],
        "ai_cost_usd": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.orders.insert_one(order)
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
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=data, media_type=ct)


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
    orders = await db.orders.find({}).to_list(1000)
    total_cost = sum(o.get("ai_cost_usd", 0) for o in orders)
    by_status = {}
    for o in orders:
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    revenue = sum(o["amount"] for o in orders if o.get("payment_status") in ("paid", "cod_pending"))
    return {
        "total_orders": len(orders),
        "total_ai_cost_usd": round(total_cost, 2),
        "revenue_dzd": revenue,
        "by_status": by_status,
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
    await db.orders.create_index("id", unique=True)
    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    client.close()
