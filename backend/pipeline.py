"""Book production pipeline (jobs run by jobs.worker).

Review items addressed: C5 (no blocking calls in the event loop), C6 (queued jobs), H8 (text regeneration keeps
scenes in sync), H9 (snapshots before every destructive run, atomic per-page updates, status always restored),
H11 (no fake similarity), H12 (validated story), H16 + L6 (multi-person pages, fixed looks), L7 (print files),
L10 (cost ledger incl. retries / partial regenerations).
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

import ai_service
import illustrator
import notify
import pdf_service
import print_service
import security
import storage

logger = logging.getLogger("hikayati.pipeline")

IMAGE_CONCURRENCY = max(1, int(os.environ.get("IMAGE_CONCURRENCY", "3")))
APP = storage.APP_NAME


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def push_status(db, order_id: str, status: str, note: str = ""):
    entry = {"status": status, "note": note, "timestamp": now_iso()}
    await db.orders.update_one({"id": order_id}, {"$set": {"status": status, "updated_at": now_iso()},
                                                  "$push": {"status_history": entry}})


async def put(path: str, data: bytes, ct: str):
    await asyncio.to_thread(storage.put_object, path, data, ct)


async def get(path: str) -> bytes:
    data, _ = await asyncio.to_thread(storage.get_object, path)
    return data


# ---------------------------------------------------------------- cost ledger (L10)
async def add_cost(db, order_id: str, kind: str, units: int = 1):
    """Configurable unit prices (env COST_*). These are still ESTIMATES: the providers do not return
    per-call prices through the proxy. Retries and partial regenerations are now included."""
    if units <= 0:
        return
    amount = round(ai_service.UNIT_COSTS.get(kind, 0) * units, 4)
    await db.orders.update_one({"id": order_id}, {"$inc": {"ai_cost_usd": amount, f"cost_breakdown.{kind}": amount,
                                                          f"cost_units.{kind}": units}})
    await db.cost_events.insert_one({"order_id": order_id, "kind": kind, "units": units, "usd": amount,
                                     "at": now_iso()})


async def mark_job_failed(db, job: dict, err):
    """Handlers swallow their own errors (they must restore the order status), so they flag the job here;
    this keeps /health's failed-job counter and the job history truthful (review item L9)."""
    if job.get("id"):
        await db.jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": str(err)[:300],
                                                              "finished_at": now_iso()}})


# ---------------------------------------------------------------- versions (H9)
async def snapshot_version(db, order: dict):
    version = {
        "version": len(order.get("versions", [])) + 1, "timestamp": now_iso(),
        "story_title": order.get("story_title"), "story_moral": order.get("story_moral"),
        "story_data": order.get("story_data"), "cover_path": order.get("cover_path"),
        "pages": order.get("pages", []), "pdf_path": order.get("pdf_path"),
        "coloring_pdf_path": order.get("coloring_pdf_path"),
    }
    await db.orders.update_one({"id": order["id"]}, {"$push": {"versions": version}})


def _rebuild_pdfs_sync(order: dict):
    cover_bytes, _ = storage.get_object(order["cover_path"])
    pdf_pages, line_pages = [], []
    for p in order["pages"]:
        img, _ = storage.get_object(p["image_path"])
        pdf_pages.append({"text": p["text"], "image": img})
        if p.get("coloring_path"):
            line_pages.append(storage.get_object(p["coloring_path"])[0])
    pdf_bytes = pdf_service.build_book_pdf(order.get("story_title", ""), order.get("story_moral", ""), pdf_pages,
                                           cover_bytes, order["language"], order["child_name"])
    col = pdf_service.build_coloring_pdf(order.get("story_title", ""), line_pages, order["language"])
    return pdf_bytes, col


async def rebuild_pdfs(db, order: dict):
    pdf_bytes, col = await asyncio.to_thread(_rebuild_pdfs_sync, order)
    pdf_path = order.get("pdf_path") or f"{APP}/orders/{order['id']}/book.pdf"
    col_path = order.get("coloring_pdf_path") or f"{APP}/orders/{order['id']}/coloring_book.pdf"
    await put(pdf_path, pdf_bytes, "application/pdf")
    await put(col_path, col, "application/pdf")
    return pdf_path, col_path


def _cover_scene(story: dict, child_name: str) -> str:
    last = story["pages"][-1]["scene"] if story.get("pages") else ""
    return (f"{child_name} smiling proudly and happy, full body, centered, a simple whimsical colourful background "
            f"inspired by this moment of the story: {last[:220]}; empty space at the top")


def _page_dict(i, pg, order_id, tag, img_path, line_path, flagged):
    return {"page_number": i + 1, "text": pg["text"], "scene": pg["scene"], "characters": pg.get("characters", []),
            "image_path": img_path, "coloring_path": line_path,
            # H11: the previous version displayed RANDOM scores here. No biometric model runs, so we say nothing.
            "similarity_score": None, "similarity_ok": None, "moderation_ok": not flagged}


# ---------------------------------------------------------------- full generation
async def generate(db, job: dict):
    order_id = job["order_id"]
    reuse_story = bool(job.get("params", {}).get("reuse_story"))
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order:
            return
        if order.get("reference_photo_deleted"):
            raise RuntimeError("تم حذف صورة المرجع، لا يمكن التوليد")
        if order.get("pages"):
            await snapshot_version(db, order)     # H9a: never overwrite the only copy
        await push_status(db, order_id, "generating", "بدأ توليد القصة والرسومات")

        seed = order.get("gen_seed") or (uuid.uuid4().int % 1_000_000)
        cast = illustrator.build_cast(order)
        main = next(c for c in cast if c["main"])
        if reuse_story and order.get("story_data"):
            story = order["story_data"]
        else:
            story = await ai_service.generate_story(
                order["child_name"], order["child_age"], order["child_gender"], order["story_type"],
                order.get("behavior_focus", ""), order["language"], extra_context=order.get("extra_context", ""),
                level=order.get("story_level", "simple"), cast=illustrator.cast_for_story(cast))
            await add_cost(db, order_id, "text", story.get("attempts", 1))
        flagged = bool(story.get("flagged"))
        sheet = story.get("character_sheet", {})
        ctx = illustrator.JobContext()
        tag = uuid.uuid4().hex[:8]               # new paths on every run => older versions keep valid images
        base = f"{APP}/orders/{order_id}"

        cover_bytes = await asyncio.to_thread(illustrator.render, ctx, order, cast, sheet,
                                              _cover_scene(story, main["name"]), [main["name"]], seed, True)
        cover_path = f"{base}/cover_{tag}.png"
        await put(cover_path, cover_bytes, "image/png")

        sem = asyncio.Semaphore(IMAGE_CONCURRENCY)

        async def one(i, pg):
            async with sem:
                img = await asyncio.to_thread(illustrator.render, ctx, order, cast, sheet, pg["scene"],
                                              pg.get("characters", []), seed, False)
                line = await asyncio.to_thread(pdf_service.make_line_art, img)
                ip, lp = f"{base}/page_{i + 1}_{tag}.png", f"{base}/coloring_{i + 1}_{tag}.png"
                await asyncio.gather(put(ip, img, "image/png"), put(lp, line, "image/png"))
                return i, img, line, ip, lp

        results = sorted(await asyncio.gather(*[one(i, pg) for i, pg in enumerate(story["pages"])]))
        pages_out = [_page_dict(i, story["pages"][i], order_id, tag, ip, lp, flagged) for i, _, _, ip, lp in results]

        pdf_bytes = await asyncio.to_thread(
            pdf_service.build_book_pdf, story["title"], story.get("moral", ""),
            [{"text": story["pages"][i]["text"], "image": img} for i, img, _, _, _ in results],
            cover_bytes, order["language"], order["child_name"])
        col_bytes = await asyncio.to_thread(pdf_service.build_coloring_pdf, story["title"],
                                            [line for _, _, line, _, _ in results], order["language"])
        pdf_path, col_path = f"{base}/book.pdf", f"{base}/coloring_book.pdf"
        await asyncio.gather(put(pdf_path, pdf_bytes, "application/pdf"), put(col_path, col_bytes, "application/pdf"))

        for kind, n in ctx.counts.items():
            await add_cost(db, order_id, kind, n)
        story_data = {k: story[k] for k in ("title", "moral", "character_sheet", "pages") if k in story}
        await db.orders.update_one({"id": order_id}, {"$set": {
            "story_title": story["title"], "story_moral": story.get("moral", ""), "story_data": story_data,
            "cover_path": cover_path, "cover_similarity": None, "pages": pages_out,
            "pdf_path": pdf_path, "coloring_pdf_path": col_path, "gen_seed": seed, "avg_similarity": None,
            "needs_content_review": flagged, "illustration_modes": ctx.modes, "multi_ref_error": ctx.multi_error,
            "reference_photo_delete_after": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }})
        note = "اكتمل التوليد، في انتظار المراجعة البشرية"
        if flagged:
            note += " — تنبيه: النص يحتاج مراجعة محتوى دقيقة"
        if ctx.multi_error:
            note += " — ملاحظة: تعذر نموذج الصور المتعددة فاستُخدم النموذج الأساسي"
        await push_status(db, order_id, "review", note)
        logger.info(f"order={order_id} generation complete modes={ctx.modes}")
    except Exception as e:
        logger.exception(f"order={order_id} generation failed: {e}")
        await mark_job_failed(db, job, e)
        await push_status(db, order_id, "failed", f"فشل التوليد: {str(e)[:200]}")
        await notify.alert(f"فشل توليد الطلب {order_id}: {str(e)[:300]}")


# ---------------------------------------------------------------- partial regeneration
async def regenerate_page(db, job: dict):
    order_id, page_number = job["order_id"], int(job["params"]["page_number"])
    prev_status = "review"
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order or order.get("reference_photo_deleted"):
            return
        prev_status = order.get("status", "review")
        idx = next((i for i, p in enumerate(order.get("pages", [])) if p["page_number"] == page_number), None)
        if idx is None:
            await push_status(db, order_id, prev_status, f"الصفحة {page_number} غير موجودة")
            return
        await snapshot_version(db, order)
        await push_status(db, order_id, "generating", f"إعادة توليد الصفحة {page_number}")
        cast = illustrator.build_cast(order)
        sheet = (order.get("story_data") or {}).get("character_sheet", {})
        page = order["pages"][idx]
        seed = (order.get("gen_seed") or 0) + page_number * 7 + uuid.uuid4().int % 1000
        ctx = illustrator.JobContext()
        img = await asyncio.to_thread(illustrator.render, ctx, order, cast, sheet, page["scene"],
                                      page.get("characters", []), seed, False)
        line = await asyncio.to_thread(pdf_service.make_line_art, img)
        tag = uuid.uuid4().hex[:8]
        ip = f"{APP}/orders/{order_id}/page_{page_number}_{tag}.png"
        lp = f"{APP}/orders/{order_id}/coloring_{page_number}_{tag}.png"
        await asyncio.gather(put(ip, img, "image/png"), put(lp, line, "image/png"))
        # H9c: update ONLY this page (dotted path) so concurrent edits cannot overwrite each other
        await db.orders.update_one({"id": order_id}, {"$set": {f"pages.{idx}.image_path": ip,
                                                              f"pages.{idx}.coloring_path": lp,
                                                              f"pages.{idx}.image_stale": False}})
        order = await db.orders.find_one({"id": order_id})
        await rebuild_pdfs(db, order)
        for kind, n in ctx.counts.items():
            await add_cost(db, order_id, kind, n)
        await push_status(db, order_id, prev_status if prev_status not in ("generating", "failed") else "review",
                          f"تمت إعادة توليد الصفحة {page_number}")
    except Exception as e:
        logger.exception(f"order={order_id} regen page failed: {e}")
        await mark_job_failed(db, job, e)
        await push_status(db, order_id, prev_status if prev_status not in ("generating",) else "review",
                          f"فشل إعادة توليد الصفحة: {str(e)[:120]}")
        await notify.alert(f"فشل إعادة توليد صفحة في الطلب {order_id}: {str(e)[:200]}")


async def regenerate_text(db, job: dict):
    order_id = job["order_id"]
    with_images = bool(job.get("params", {}).get("with_images", True))
    prev_status = "review"
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order:
            return
        prev_status = order.get("status", "review")
        await snapshot_version(db, order)
        await push_status(db, order_id, "generating", "إعادة صياغة نص القصة")
        cast = illustrator.build_cast(order)
        story = await ai_service.generate_story(
            order["child_name"], order["child_age"], order["child_gender"], order["story_type"],
            order.get("behavior_focus", ""), order["language"], extra_context=order.get("extra_context", ""),
            level=order.get("story_level", "simple"), cast=illustrator.cast_for_story(cast))
        await add_cost(db, order_id, "text", story.get("attempts", 1))
        story_data = {k: story[k] for k in ("title", "moral", "character_sheet", "pages")}
        # H8: text AND scenes come from the same story, never mixed with the old pictures silently
        pages = order.get("pages") or []
        for i, pg in enumerate(story["pages"]):
            if i < len(pages):
                pages[i].update({"text": pg["text"], "scene": pg["scene"], "characters": pg.get("characters", []),
                                 "image_stale": True, "moderation_ok": not story.get("flagged")})
        await db.orders.update_one({"id": order_id}, {"$set": {
            "pages": pages, "story_title": story["title"], "story_moral": story.get("moral", ""),
            "story_data": story_data, "needs_content_review": bool(story.get("flagged"))}})
        if with_images:
            await db.orders.update_one({"id": order_id}, {"$set": {"status": prev_status}})
            await generate(db, {"order_id": order_id, "params": {"reuse_story": True}})
            return
        order = await db.orders.find_one({"id": order_id})
        if order.get("cover_path"):
            await rebuild_pdfs(db, order)
        await push_status(db, order_id, prev_status if prev_status != "generating" else "review",
                          "تمت إعادة صياغة النص — تنبيه: الصور ما زالت من القصة السابقة، أعد توليد الصور")
    except Exception as e:
        logger.exception(f"order={order_id} regen text failed: {e}")
        await mark_job_failed(db, job, e)
        await push_status(db, order_id, prev_status if prev_status != "generating" else "review",
                          f"فشل إعادة صياغة النص: {str(e)[:120]}")
        await notify.alert(f"فشل إعادة صياغة نص الطلب {order_id}: {str(e)[:200]}")


async def restore_version(db, job: dict):
    order_id, version_num = job["order_id"], int(job["params"]["version"])
    prev_status = "review"
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order:
            return
        prev_status = order.get("status", "review")
        target = next((v for v in order.get("versions", []) if v["version"] == version_num), None)
        if not target:
            await push_status(db, order_id, prev_status, "النسخة المطلوبة غير موجودة")
            return
        await snapshot_version(db, order)  # restoring is itself reversible
        await push_status(db, order_id, "generating", f"الرجوع إلى النسخة {version_num}")
        order.update(story_title=target.get("story_title"), story_moral=target.get("story_moral"),
                     cover_path=target.get("cover_path") or order.get("cover_path"), pages=target.get("pages", []))
        await rebuild_pdfs(db, order)
        await db.orders.update_one({"id": order_id}, {"$set": {
            "story_title": order["story_title"], "story_moral": order["story_moral"],
            "story_data": target.get("story_data") or order.get("story_data"),
            "cover_path": order["cover_path"], "pages": order["pages"]}})
        await push_status(db, order_id, prev_status if prev_status != "generating" else "review",
                          f"تم الرجوع إلى النسخة {version_num}")
    except Exception as e:
        logger.exception(f"order={order_id} restore failed: {e}")
        await mark_job_failed(db, job, e)
        await push_status(db, order_id, prev_status if prev_status != "generating" else "review",
                          f"فشل الرجوع للنسخة: {str(e)[:120]}")


# ---------------------------------------------------------------- print files (L7)
async def build_print(db, job: dict):
    order_id = job["order_id"]
    p = job.get("params", {})
    try:
        order = await db.orders.find_one({"id": order_id})
        if not order or not order.get("pages") or not order.get("cover_path"):
            return

        def reader(path):
            return storage.get_object(path)[0]

        def url_for(path):
            return illustrator.ref_url(path)

        out = await asyncio.to_thread(print_service.build, order, reader, url_for, p.get("trim", "A5"),
                                      float(p.get("bleed_mm", 3)), float(p.get("spine_mm", 3)))
        base = f"{APP}/orders/{order_id}"
        await asyncio.gather(put(f"{base}/print_interior.pdf", out["interior"], "application/pdf"),
                             put(f"{base}/print_cover.pdf", out["cover"], "application/pdf"))
        if "AI" in "".join(out["info"]["resample_modes"]).upper():
            await add_cost(db, order_id, "upscale", len(order["pages"]) + 1)
        await db.orders.update_one({"id": order_id}, {"$set": {
            "print_interior_path": f"{base}/print_interior.pdf", "print_cover_path": f"{base}/print_cover.pdf",
            "print_info": out["info"], "print_built_at": now_iso()}})
        await push_status(db, order_id, order.get("status", "review"),
                          f"تم تجهيز ملفات الطباعة ({out['info']['trim']}، قص {out['info']['bleed_mm']} مم)")
    except Exception as e:
        logger.exception(f"order={order_id} print build failed: {e}")
        await mark_job_failed(db, job, e)
        await push_status(db, order_id, (await db.orders.find_one({"id": order_id}) or {}).get("status", "review"),
                          f"فشل تجهيز ملفات الطباعة: {str(e)[:120]}")


def handlers(db):
    async def wrap(fn, job):
        await fn(db, job)
    return {
        "generate": lambda job: wrap(generate, job),
        "regenerate_page": lambda job: wrap(regenerate_page, job),
        "regenerate_text": lambda job: wrap(regenerate_text, job),
        "restore_version": lambda job: wrap(restore_version, job),
        "build_print": lambda job: wrap(build_print, job),
    }


# ---------------------------------------------------------------- privacy purge (C2)
def _collect_paths(obj, out, include_refs=True):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k.endswith("_path") and v.startswith(APP + "/"):
                out.add(v)
            else:
                _collect_paths(v, out, include_refs)
    elif isinstance(obj, list):
        for x in obj:
            _collect_paths(x, out, include_refs)


def reference_paths(order: dict) -> set:
    paths = {order.get("reference_photo_path"), order.get("pet_photo_path")}
    for c in order.get("characters", []):
        paths.add(c.get("photo_path"))
    return {p for p in paths if p}


async def purge_files(paths) -> tuple:
    """Delete files from storage; returns (deleted, failed)."""
    ok = bad = 0
    for p in paths:
        if await asyncio.to_thread(storage.delete_object, p):
            ok += 1
        else:
            bad += 1
    return ok, bad


async def purge_order_files(order: dict):
    paths = set()
    _collect_paths(order, paths)
    return await purge_files(paths)
