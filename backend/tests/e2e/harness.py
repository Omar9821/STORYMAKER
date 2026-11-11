"""Local end-to-end harness: runs the real FastAPI app with an in-memory MongoDB (mongomock), fake storage and
FAKE Claude/fal providers (no network, no cost). Usage:  python tests/e2e/harness.py   (port 8002)
Then: python tests/e2e/verify.py"""
import os, sys, io, time, random
HERE = os.path.dirname(os.path.abspath(__file__)); BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "stubs")); sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
os.environ.update(MONGO_URL="mongodb://x", DB_NAME="t", JWT_SECRET="a-long-random-test-secret-0123456789", ADMIN_EMAIL="admin@test.dz",
                  ADMIN_PASSWORD="Str0ng-Test-Password!", BACKEND_PUBLIC_URL="http://127.0.0.1:%s" % os.environ.get("PORT", "8002"), FRONTEND_URL="http://localhost:3000",
                  JOB_POLL_SECONDS="0.3", ORDER_RATE_LIMIT="500", MULTI_REF_ENABLED=os.environ.get("MULTI_REF_ENABLED", "true"))
os.environ["PAYMENT_MOCK"] = "true"; os.environ.pop("CHARGILY_SECRET_KEY", None); os.environ.pop("CORS_ORIGINS", None)
import motor.motor_asyncio as m
from mongomock_motor import AsyncMongoMockClient
m.AsyncIOMotorClient = AsyncMongoMockClient
from PIL import Image, ImageDraw
import storage, fal_service, ai_service
STORE = {}; LAT = float(os.environ.get("STORAGE_LATENCY", "0.2")); DEL = []
def put_object(path, data, ct): time.sleep(LAT); STORE[path] = (data, ct); return {"path": path}
def get_object(path):
    time.sleep(LAT)
    if path not in STORE: raise Exception("404")
    return STORE[path]
def delete_object(path): DEL.append(path); STORE.pop(path, None); return True
storage.put_object, storage.get_object, storage.delete_object = put_object, get_object, delete_object
storage.init_storage = lambda force=False: "k"
CALLS = {"pulid": 0, "multi": 0, "story": 0, "multi_urls": [], "scenes": []}
def img(seed, w=768, h=1024):
    rnd = random.Random(seed); im = Image.new("RGB", (w, h), (rnd.randint(150,255), rnd.randint(150,255), rnd.randint(150,255))); d = ImageDraw.Draw(im)
    for _ in range(12):
        x, y = rnd.randint(0, w-200), rnd.randint(0, h-200); d.ellipse([x, y, x+rnd.randint(60,180), y+rnd.randint(60,180)], fill=tuple(rnd.randint(0,255) for _ in range(3)), outline=(0,0,0), width=5)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
def fake_pulid(reference_image_url, scene, seed, is_cover=False, id_weight=1.0, style="cartoon"):
    CALLS["pulid"] += 1; CALLS["scenes"].append(scene); time.sleep(0.5); return img(seed)
MULTI_FAIL = os.environ.get("MULTI_FAIL") == "1"
def fake_multi(image_urls, prompt, seed, endpoint=None):
    CALLS["multi"] += 1; CALLS["multi_urls"].append((len(image_urls), prompt[:1500]))
    time.sleep(0.5)
    if MULTI_FAIL: raise fal_service.FalError("endpoint not available")
    return img(seed, 1024, 1024)   # square output on purpose: must be cropped to 3:4
fal_service.generate_illustration_pulid = fake_pulid; fal_service.generate_multi_reference = fake_multi
STORIES = {"ar": ["كانت سارة تحب اللعب في الحديقة مع أصدقائها.", "وفي يوم ماطر وجدت قطة صغيرة تبحث عن مأوى.", "أمسك أبوها وأمها بيدها وقالا: نحن فخورون بك يا سارة.", "تعلمت سارة أن اللطف يجعل القلب سعيداً.", "ومنذ ذلك اليوم صارت تعتني بكل من حولها."],
 "fr": ["C'est l'histoire d'une petite fille qui s'appelle Sara.", "Un jour, elle a trouvé un chaton perdu dans le jardin.", "Maman et Papa lui ont pris la main : Nous sommes fiers de toi.", "Sara a compris qu'il faut toujours être gentil avec les autres.", "Depuis, elle prend soin de tout le monde, l'esprit tranquille."]}
STORY_FAILS = int(os.environ.get("STORY_FAILS", "0"))
FAIL = {"story": False}
async def fake_story(child_name, child_age, child_gender, story_type, behavior_focus, language, extra_context="", level="simple", cast=None):
    CALLS["story"] += 1; CALLS["cast"] = cast
    if FAIL["story"]:
        FAIL["story"] = False; raise ValueError("Story generation failed after 3 attempts: simulated")
    texts = STORIES.get(language, STORIES["ar"]); names = [c["name"] for c in (cast or [])]
    pages = []
    for i, t in enumerate(texts):
        ch = [child_name] + (names[1:3] if i == 2 else [])
        pages.append({"text": t, "scene": f"scene {i} with {', '.join(ch)}", "characters": ch})
    return {"title": "قصة سارة" if language == "ar" else "L'histoire de Sara", "moral": "x", "pages": pages, "flagged": False, "attempts": 1,
            "character_sheet": {child_name: "blue dress, black braid hair", **({names[1]: "green shirt"} if len(names) > 1 else {})}}
ai_service.generate_story = fake_story
import server, uvicorn
@server.app.get("/__failnext")
async def failnext(): FAIL["story"] = True; return {"ok": True}
@server.app.get("/__calls")
async def calls(): return {**CALLS, "deleted": DEL, "store": len(STORE)}
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ.get("PORT", "8002")), log_level="warning")
