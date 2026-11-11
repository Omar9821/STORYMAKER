"""Behavioural checks of the review fixes against the local harness (python tests/e2e/harness.py first)."""
import httpx, io, json, time, threading, statistics, sys, os
import concurrent.futures as cf
from PIL import Image
PORT = os.environ.get("PORT", "8002"); B = f"http://127.0.0.1:{PORT}/api"; ROOT = f"http://127.0.0.1:{PORT}"
c = httpx.Client(timeout=120); R = {}; FAILS = []
def check(name, cond, detail=""):
    R[name] = ("PASS" if cond else "FAIL") + (f" | {detail}" if detail else "")
    if not cond: FAILS.append(name)
def jpg(w=800, h=800, col=(200, 120, 90), exif=False):
    b = io.BytesIO(); im = Image.new("RGB", (w, h), col)
    if exif:
        ex = Image.Exif(); ex[0x010F] = "SecretCamera"; ex[0x8825] = {1: "N", 2: (36.0, 45.0, 0.0), 3: "E", 4: (3.0, 3.0, 0.0)}; im.save(b, "JPEG", exif=ex.tobytes())
    else: im.save(b, "PNG")
    return b.getvalue()
def upload(name="kid.png", data=None, ct="image/png"):
    return c.post(f"{B}/orders/upload-photo", files={"file": (name, data or jpg(), ct)})
def body(photo, extra=None, **kw):
    chars = [dict(name="Sara", age=6, gender="girl", photo_path=photo, is_main=True)] + (extra or [])
    b = dict(characters=chars, story_type="encouragement", positive_behaviors="x", language="ar", lives_with="both", customer_name="Parent Test",
             customer_phone="0555123456", customer_email="p@example.com", shipping_address="12 Rue Didouche Mourad, Alger", wilaya="Alger", consent=True)
    b.update(kw); return b
def mk(extra_photos=0, **kw):
    p = upload().json()["path"]; ex = []
    for i in range(extra_photos): ex.append(dict(name=["Amine", "Lina"][i], age=9, gender="boy", relation="brother", photo_path=upload().json()["path"]))
    r = c.post(f"{B}/orders", json=body(p, ex, **kw)); return p, r
def wait(oid, H, until=("review", "failed"), to=90):
    t = time.time()
    while time.time() - t < to:
        s = c.get(f"{B}/admin/orders/{oid}", headers=H).json()
        if s["status"] in until and not s.get("active_job"): return s
        time.sleep(0.4)
    return s
def calls(): return c.get(f"{ROOT}/__calls").json()

# --- login (H3 first so we can also test throttling at the end)
r = c.post(f"{B}/auth/login", json={"email": "admin@test.dz", "password": "admin123"}); check("C1_default_password_rejected", r.status_code == 401)
r = c.post(f"{B}/auth/login", json={"email": "admin@test.dz", "password": "Str0ng-Test-Password!"}); check("login_ok", r.status_code == 200)
H = {"Authorization": f"Bearer {r.json()['token']}"}

# --- C3 public view / signed files / H1 / H2
photo_signed = upload("evil.png/../../x").json(); check("H1_ext_forced_jpg", photo_signed["path"].split("?")[0].endswith("/photo.jpg"), photo_signed["path"].split("?")[0][-40:])
big = io.BytesIO(); Image.effect_noise((3200, 3200), 100).convert("RGB").save(big, "PNG"); r = upload("big.png", big.getvalue()).json(); check("H1_oversize_rejected", r.get("ok") is False, r.get("message", ""))
r = upload("x.png", b"not an image at all").json(); check("H1_non_image_rejected", r.get("ok") is False)
gp = upload("gps.jpg", jpg(exif=True), "image/jpeg").json()["path"]
raw = c.get(f"{B}/files/{gp}").content; exif_after = dict(Image.open(io.BytesIO(raw)).getexif()); check("H1_exif_stripped", 0x010F not in exif_after and 0x8825 not in exif_after)
r = c.post(f"{B}/orders", json=body("hikayati/orders/OTHER/book.pdf")); check("H2_arbitrary_path_rejected", r.status_code == 400, r.text[:60])
photo, r = mk(); o = r.json(); oid = o["id"]
check("C3_public_has_no_pii", not any(k in o for k in ("customer_phone", "shipping_address", "customer_email", "customer_name", "reference_photo_path", "ai_cost_usd", "characters", "mother_name")), str(sorted(o.keys()))[:160])
pub = c.get(f"{B}/orders/{oid}").json(); check("C3_get_order_no_pii", "customer_phone" not in pub and "reference_photo_path" not in pub)
rawpath = photo.split("?")[0]
check("C3_files_unsigned_403", c.get(f"{B}/files/{rawpath}").status_code == 403)
check("C3_files_bad_sig_403", c.get(f"{B}/files/{rawpath}?exp=9999999999&sig=deadbeef").status_code == 403)
check("C3_files_signed_200", c.get(f"{B}/files/{photo}").status_code == 200)
check("C3_files_admin_token_200", c.get(f"{B}/files/{rawpath}", headers=H).status_code == 200)
import re; exp_old = int(time.time()) - 5
check("C3_files_expired_403", c.get(f"{B}/files/{rawpath}?exp={exp_old}&sig=x").status_code == 403)

# --- H7 shipping fee + COD confirm
c.put(f"{B}/admin/settings", headers=H, json={"base_price": 3400, "extra_character_price": 250, "coloring_price": 500, "coloring_original_price": 2800, "shipping_default_fee": 600, "shipping_fees": {"Oran": 700}})
_, r = mk(add_coloring=True); o2 = r.json(); check("H7_estimate_added", o2["shipping_fee"] == 600 and o2["amount"] == 3400 + 500 + 600, f"amount={o2['amount']}")
_, r = mk(wilaya="Oran"); check("H7_per_wilaya_fee", r.json()["shipping_fee"] == 700)
oid2 = o2["id"]
r = c.post(f"{B}/admin/orders/{oid2}/confirm-cod", headers=H, json={"shipping_fee": 800, "note": "اتفقنا هاتفياً"}); j = r.json()
check("H7_confirm_cod_total", r.status_code == 200 and j["amount"] == 3400 + 500 + 800, str(j))
# --- generation (C5 latency / C6 queue / H16 / L6 / L10 / H11)
lat = []; stop = threading.Event()
def ping():
    cc = httpx.Client(timeout=60)
    while not stop.is_set():
        t = time.time(); cc.get(f"{B}/"); lat.append(time.time() - t); time.sleep(0.03)
th = threading.Thread(target=ping); th.start()
r2 = c.post(f"{B}/admin/orders/{oid2}/regenerate", headers=H); check("C6_second_start_409", r2.status_code == 409, f"{r2.status_code}")
s = wait(oid2, H); stop.set(); th.join()
check("gen_reaches_review", s["status"] == "review", s["status"]); check("C5_max_latency_under_1s", max(lat) < 1.0, f"max={max(lat):.2f}s over {len(lat)} pings (storage latency 0.2s/call, 6 images)")
cl = calls(); check("C6_single_run_images", cl["pulid"] == 6, f"pulid calls={cl['pulid']}")
check("H11_no_fake_similarity", all(p["similarity_score"] is None and p["similarity_ok"] is None for p in s["pages"]))
check("L6_sheet_in_prompts", all("Keep these exact looks" in sc for sc in cl["scenes"][:6]), cl["scenes"][1][:120])
check("L10_cost_breakdown", abs(s["cost_breakdown"]["text"] - 0.03) < 1e-6 and abs(s["cost_breakdown"]["image_pulid"] - 0.30) < 1e-6, str(s["cost_breakdown"]))
check("H12_pages_have_characters", all("characters" in p for p in s["pages"]))
check("C6_cover_differs_from_page1", s["cover_path"].split("?")[0] != s["pages"][0]["image_path"].split("?")[0])
pagepaths_run1 = [p["image_path"].split("?")[0] for p in s["pages"]]
# customer cannot see unreleased book (review state)
pub = c.get(f"{B}/orders/{oid2}").json(); check("C3_review_state_hides_pictures", pub["pages"] == [] and "pdf_path" not in pub)
# --- H9: invalid page 404, status unchanged
r = c.post(f"{B}/admin/orders/{oid2}/regenerate-page/99", headers=H); check("H9_invalid_page_404_no_stuck", r.status_code == 404 and c.get(f"{B}/orders/{oid2}").json()["status"] == "review")
# --- H9: regenerate page, atomic, snapshot
r = c.post(f"{B}/admin/orders/{oid2}/regenerate-page/2", headers=H); s2 = wait(oid2, H)
check("H9_page_regen_status_review", s2["status"] == "review" and len(s2["versions"]) == 1, s2["status"])
check("H9_only_page2_changed", s2["pages"][1]["image_path"].split("?")[0] != pagepaths_run1[1] and s2["pages"][0]["image_path"].split("?")[0] == pagepaths_run1[0])
# --- H8: regenerate text keeps scenes consistent and images follow
before = [p["image_path"].split("?")[0] for p in s2["pages"]]
r = c.post(f"{B}/admin/orders/{oid2}/regenerate-text", headers=H, json={"with_images": True}); s3 = wait(oid2, H)
check("H8_text_regen_with_images", s3["status"] == "review" and all(p["image_path"].split("?")[0] not in before for p in s3["pages"]) and not any(p.get("image_stale") for p in s3["pages"]), s3["status"])
check("H9_old_version_files_still_exist", all(c.get(f"{B}/files/{pp}", headers=H).status_code == 200 for pp in pagepaths_run1), f"versions={len(s3['versions'])}")
r = c.post(f"{B}/admin/orders/{oid2}/regenerate-text", headers=H, json={"with_images": False}); s4 = wait(oid2, H)
check("H8_text_only_marks_stale", s4["status"] == "review" and all(p.get("image_stale") for p in s4["pages"]))
# --- H16: multi-reference
photoM, r = mk(extra_photos=1); oidM = r.json()["id"]
c.post(f"{B}/admin/orders/{oidM}/confirm-cod", headers=H, json={"shipping_fee": 500}); sM = wait(oidM, H)
cl = calls(); check("H16_multi_used_for_family_page", cl["multi"] >= 1 and any(n == 2 for n, _ in cl["multi_urls"]), f"multi calls={cl['multi']} urls={[n for n,_ in cl['multi_urls']]}")
check("H16_modes_recorded", "multi" in sM.get("illustration_modes", []), str(sM.get("illustration_modes")))
mp = [p for p in sM["pages"] if len(p["characters"]) > 1][0]
im = Image.open(io.BytesIO(c.get(f"{B}/files/{mp['image_path']}").content)); check("H16_multi_output_cropped_3x4", abs(im.size[0] / im.size[1] - 0.75) < 0.02, str(im.size))
check("H16_prompt_names_each_reference", "Image 1 is Sara" in cl["multi_urls"][0][1] and "Image 2 is Amine" in cl["multi_urls"][0][1], cl["multi_urls"][0][1][-200:])
# --- L7 print build
r = c.post(f"{B}/admin/orders/{oidM}/build-print", headers=H, json={"trim": "A5", "bleed_mm": 3, "spine_mm": 3}); sP = wait(oidM, H)
check("L7_print_built", sP.get("print_info", {}).get("page_count") == 8 and sP["print_info"]["target_dpi"] == 300, str(sP.get("print_info")))
pdf = c.get(f"{B}/files/{sP['print_interior_path']}").content; open("/tmp/hikayati_e2e_new_print_interior.pdf", "wb").write(pdf)
open("/tmp/hikayati_e2e_new_print_cover.pdf", "wb").write(c.get(f"{B}/files/{sP['print_cover_path']}").content)
# --- H15 French
_, r = mk(language="fr"); oidF = r.json()["id"]; c.post(f"{B}/admin/orders/{oidF}/confirm-cod", headers=H, json={"shipping_fee": 0}); sF = wait(oidF, H)
open("/tmp/hikayati_e2e_new_fr.pdf", "wb").write(c.get(f"{B}/files/{sF['pdf_path']}").content)
import pdfplumber; txt = "\n".join((p.extract_text() or "") for p in pdfplumber.open("/tmp/hikayati_e2e_new_fr.pdf").pages)
check("H15_french_apostrophes_kept", "C'est l'histoire" in txt and "s'appelle" in txt, txt.replace("\n", " ")[40:140])
# --- H13 status machine & stats
_, r = mk(); oidS = r.json()["id"]
check("H13_unpaid_to_delivered_blocked", c.post(f"{B}/admin/orders/{oidS}/status", headers=H, json={"status": "delivered"}).status_code == 400)
check("H13_banana_blocked", c.post(f"{B}/admin/orders/{oidS}/status", headers=H, json={"status": "banana"}).status_code == 400)
st = c.get(f"{B}/admin/stats", headers=H).json(); rev_before = st["revenue_dzd"]
check("H13_cod_not_revenue_until_delivered", rev_before == 0 and st["pending_cod_dzd"] > 0, f"revenue={rev_before} pending_cod={st['pending_cod_dzd']}")
for stt in ("approved", "shipped", "delivered"): rr = c.post(f"{B}/admin/orders/{oid2}/status", headers=H, json={"status": stt}); 
st = c.get(f"{B}/admin/stats", headers=H).json(); check("H13_revenue_after_delivery", st["revenue_dzd"] == 3400 + 500 + 800, str(st["revenue_dzd"]))
pubD = c.get(f"{B}/orders/{oid2}").json(); check("C3_delivered_shows_book", len(pubD["pages"]) == 5 and "pdf_path" in pubD and "coloring_pdf_path" in pubD)
# --- C2 purge: delivered order's reference photos really deleted
time.sleep(0.5); cl = calls(); o2full = c.get(f"{B}/admin/orders/{oid2}", headers=H).json()
check("C2_files_really_deleted_on_delivery", o2full["reference_photo_deleted"] and o2full.get("reference_files_purged") and any("references" in d for d in cl["deleted"]), f"deleted={len(cl['deleted'])}")
check("C2_deleted_file_gone", c.get(f"{B}/files/{o2full['reference_photo_path'].split('?')[0]}", headers=H).status_code == 404)
# --- delete order purges everything
r = c.delete(f"{B}/admin/orders/{oidM}", headers=H); j = r.json(); check("C2_delete_order_purges_files", r.status_code == 200 and j["files_deleted"] > 10 and j["files_failed"] == 0, str(j))
# --- H6 coupons
c.post(f"{B}/admin/coupons", headers=H, json={"code": "ONE", "type": "percent", "value": 20, "max_uses": 1})
pc = upload().json()["path"]
def mkc(i): 
    r = httpx.post(f"{B}/orders", json=body(pc, coupon_code="ONE"), timeout=60); return r.json()
with cf.ThreadPoolExecutor(6) as ex: res = list(ex.map(mkc, range(6)))
disc = [x["discount"] for x in res]; cp = [x for x in c.get(f"{B}/admin/coupons", headers=H).json() if x["code"] == "ONE"][0]
check("H6_coupon_single_use_atomic", sum(1 for d in disc if d > 0) == 1 and cp["used_count"] == 1, f"discounts={disc} used={cp['used_count']}")
winner = [x for x in res if x["discount"] > 0][0]["id"]; c.delete(f"{B}/admin/orders/{winner}", headers=H)
cp = [x for x in c.get(f"{B}/admin/coupons", headers=H).json() if x["code"] == "ONE"][0]; check("H6_coupon_released_on_delete", cp["used_count"] == 0, str(cp["used_count"]))
check("H6_bad_subtotal_422", c.post(f"{B}/orders/validate-coupon", json={"code": "ONE", "subtotal": "abc"}).status_code == 422)
check("H6_negative_coupon_rejected", c.post(f"{B}/admin/coupons", headers=H, json={"code": "NEG", "type": "fixed", "value": -50}).status_code == 422)
# --- H10/H13 input limits
check("H10_long_text_rejected", c.post(f"{B}/orders", json=body(pc, special_details="x" * 5000)).status_code == 422)
check("H13_bad_story_type_rejected", c.post(f"{B}/orders", json=body(pc, story_type="hack")).status_code == 422)
# --- L1 search
check("L1_regex_search_safe", c.get(f"{B}/admin/orders", headers=H, params={"search": "("}).status_code == 200)
# --- L11 i18n errors
r = c.get(f"{B}/orders/nope", headers={"X-Lang": "fr"}); check("L11_french_error_with_code", r.status_code == 404 and r.json().get("code") == "order_not_found" and "introuvable" in r.json()["detail"], r.text)
# --- H5 tickets + H4 CORS + H3 throttle
check("H5_long_ticket_422", c.post(f"{B}/tickets", json={"order_id": oid2, "name": "x", "message": "A" * 3000}).status_code == 422)
codes = [c.post(f"{B}/tickets", json={"order_id": oid2, "name": "x", "message": "hi"}).status_code for _ in range(7)]; check("H5_ticket_rate_limited", 429 in codes, str(codes))
rr = c.get(f"{B}/", headers={"Origin": "https://evil.example"}); check("H4_no_wildcard_credentials", rr.headers.get("access-control-allow-credentials") is None and rr.headers.get("access-control-allow-origin") in (None, "http://localhost:3000"), str(dict(rr.headers).get("access-control-allow-origin")))
codes = [c.post(f"{B}/auth/login", json={"email": "admin@test.dz", "password": f"wrong{i}"}).status_code for i in range(8)]; check("H3_bruteforce_locked", codes[:5] == [401] * 5 and 429 in codes[5:], str(codes))
check("H3_correct_password_also_locked", c.post(f"{B}/auth/login", json={"email": "admin@test.dz", "password": "Str0ng-Test-Password!"}).status_code == 429)
# --- L9 failure alert + failed status
c.get(f"{ROOT}/__failnext"); _, r = mk(); oidX = r.json()["id"]
c.post(f"{B}/admin/orders/{oidX}/confirm-cod", headers=H, json={"shipping_fee": 0}); 
t0 = time.time()
while time.time() - t0 < 20:
    sx = httpx.get(f"{B}/orders/{oidX}").json()
    if sx["status"] in ("failed", "review"): break
    time.sleep(0.4)
check("L9_failure_sets_failed", sx["status"] == "failed", sx["status"]); open("/tmp/hikayati_e2e_new_results.json", "w").write(json.dumps(R, ensure_ascii=False, indent=1))
hl = c.get(f"{B}/health").json(); check("L9_health_ok", hl["status"] == "ok" and hl["checks"]["jobs_failed_24h"] >= 1, str(hl["checks"]))
print(json.dumps(R, ensure_ascii=False, indent=1)); print("FAILS:", FAILS)
