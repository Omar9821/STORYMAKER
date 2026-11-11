"""Persistent job queue (review items C6, L9).

Before: `asyncio.create_task(run_generation(...))` — lost on restart, two clicks = two runs, unlimited parallelism.
Now: every generation / regeneration is a document in the `jobs` collection:
  * at most ONE active (queued|running) job per order  -> double-click safe (HTTP 409)
  * a bounded number of jobs run at once (JOB_CONCURRENCY, default 2)
  * jobs that were `running` when the process died are re-queued once at start-up, then failed + alerted
  * failures send an alert (Telegram / webhook / log) — see notify.py

Single-process design (one uvicorn worker). For several workers, replace claim() with a DB-level lock.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CONCURRENCY = max(1, int(os.environ.get("JOB_CONCURRENCY", "2")))
POLL_SECONDS = float(os.environ.get("JOB_POLL_SECONDS", "1.5"))
MAX_RECOVERY_ATTEMPTS = 2

_enqueue_lock = asyncio.Lock()
_stop = asyncio.Event()


def _now():
    return datetime.now(timezone.utc).isoformat()


async def enqueue(db, order_id: str, kind: str, params: dict = None) -> dict:
    async with _enqueue_lock:
        active = await db.jobs.find_one({"order_id": order_id, "status": {"$in": ["queued", "running"]}})
        if active:
            raise HTTPException(status_code=409, detail="الطلب قيد المعالجة بالفعل، انتظر حتى ينتهي")
        job = {"id": str(uuid.uuid4()), "order_id": order_id, "kind": kind, "params": params or {},
               "status": "queued", "attempts": 0, "created_at": _now(), "error": None}
        await db.jobs.insert_one(job)
        job.pop("_id", None)
        return job


async def active_job(db, order_id: str):
    return await db.jobs.find_one({"order_id": order_id, "status": {"$in": ["queued", "running"]}}, {"_id": 0})


async def recover_stale(db, on_fail: Callable[[dict, str], Awaitable[None]]):
    """Called once at start-up (before the worker starts)."""
    stale = await db.jobs.find({"status": "running"}).to_list(100)
    for j in stale:
        attempts = j.get("attempts", 1)
        if attempts < MAX_RECOVERY_ATTEMPTS:
            await db.jobs.update_one({"id": j["id"]}, {"$set": {"status": "queued", "recovered_at": _now()}})
            logger.warning(f"job {j['id']} ({j['kind']}) re-queued after restart")
        else:
            await db.jobs.update_one({"id": j["id"]}, {"$set": {"status": "failed", "error": "interrupted by restart"}})
            await on_fail(j, "interrupted by restart")


async def _claim(db):
    return await db.jobs.find_one_and_update(
        {"status": "queued"}, {"$set": {"status": "running", "started_at": _now()}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)])


async def worker(db, handlers: Dict[str, Callable[[dict], Awaitable[None]]],
                 on_fail: Callable[[dict, str], Awaitable[None]]):
    sem = asyncio.Semaphore(CONCURRENCY)
    running = set()

    async def run(job):
        try:
            await handlers[job["kind"]](job)
            # only mark done if the handler did not already flag the job as failed
            await db.jobs.update_one({"id": job["id"], "status": "running"}, {"$set": {"status": "done", "finished_at": _now()}})
        except Exception as e:  # handlers normally catch their own errors; this is the safety net
            logger.exception(f"job {job['id']} crashed: {e}")
            await db.jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": str(e)[:300],
                                                                  "finished_at": _now()}})
            try:
                await on_fail(job, str(e)[:300])
            except Exception:
                logger.exception("on_fail failed")
        finally:
            sem.release()

    while not _stop.is_set():
        try:
            await sem.acquire()
            job = await _claim(db)
            if not job:
                sem.release()
                await asyncio.sleep(POLL_SECONDS)
                continue
            job.pop("_id", None)
            t = asyncio.create_task(run(job))
            running.add(t)  # keep a strong reference (tasks can be garbage-collected otherwise)
            t.add_done_callback(running.discard)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"worker loop error: {e}")
            await asyncio.sleep(3)


def stop():
    _stop.set()
