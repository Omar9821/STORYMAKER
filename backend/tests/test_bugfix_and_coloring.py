"""Backend tests for iteration 6:
- BUG FIX: approve no longer deletes reference photo; ship/deliver still does.
- BUG FIX: regenerate guard on reference_photo_deleted.
- FEATURE: coloring add-on pricing (add_coloring bool, +coloring_price).
- Admin settings CRUD for the 4 pricing fields.
- Regression: manual lifecycle & management endpoints still work.
"""
import io
import os
import time
import pytest
import requests
from PIL import Image

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@hikayati.dz")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Hikayati@2026")


def _png_bytes(w=600, h=600, color=(200, 170, 130)):
    img = Image.new("RGB", (w, h), color=color)
    for i in range(0, w, 40):
        for j in range(0, h, 40):
            img.putpixel((i, j), (150, 100, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def http():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_headers(http):
    r = http.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def photo_path(http):
    files = {"file": ("child.png", _png_bytes(600, 600), "image/png")}
    r = http.post(f"{BASE_URL}/api/orders/upload-photo", files=files)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    return j["path"]


def _payload(photo_path, add_coloring=False, name="TEST_BF"):
    return {
        "characters": [{
            "name": name, "age": 6, "gender": "girl",
            "hair_color": "black", "hair_type": "curly", "hair_length": "long",
            "hobbies": "reading", "favorite_color": "pink",
            "favorite_food": "couscous", "relation": "",
            "photo_path": photo_path, "is_main": True,
        }],
        "story_type": "encouragement",
        "positive_behaviors": "confidence", "negative_behaviors": "shouting",
        "special_details": "loves the sea",
        "language": "ar", "language_level": "simple",
        "story_setting": ["home"], "lives_with": "parents",
        "mother_name": "", "mother_age": "", "father_name": "", "father_age": "",
        "mention_parents": False, "siblings": [], "friends": [],
        "quantity": 1, "coupon_code": "",
        "customer_name": "TEST_Customer", "customer_phone": "0555000000",
        "customer_email": "t@t.com", "shipping_address": "1 Rue",
        "wilaya": "Alger", "consent": True,
        "add_coloring": add_coloring,
    }


# Track created orders for cleanup
_created_orders = []


@pytest.fixture(scope="module", autouse=True)
def cleanup(http, admin_headers):
    yield
    for oid in _created_orders:
        try:
            http.delete(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers)
        except Exception:
            pass


# ---------- Config / Settings ----------
class TestConfigColoring:
    def test_config_has_coloring_prices(self, http):
        r = http.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200
        j = r.json()
        assert j.get("coloring_price") == 500
        assert j.get("coloring_original_price") == 2800

    def test_admin_get_settings_returns_four_fields(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        for k in ("base_price", "extra_character_price", "coloring_price", "coloring_original_price"):
            assert k in j, f"missing {k}"

    def test_admin_put_settings_reflected_and_restored(self, http, admin_headers):
        # change
        payload = {"base_price": 3500, "extra_character_price": 300,
                   "coloring_price": 600, "coloring_original_price": 3000}
        r = http.put(f"{BASE_URL}/api/admin/settings", json=payload, headers=admin_headers)
        assert r.status_code == 200
        j = http.get(f"{BASE_URL}/api/config").json()
        assert j["base_price"] == 3500
        assert j["extra_character_price"] == 300
        assert j["coloring_price"] == 600
        assert j["coloring_original_price"] == 3000
        # restore
        rr = http.put(f"{BASE_URL}/api/admin/settings",
                      json={"base_price": 3400, "extra_character_price": 250,
                            "coloring_price": 500, "coloring_original_price": 2800},
                      headers=admin_headers)
        assert rr.status_code == 200
        j2 = http.get(f"{BASE_URL}/api/config").json()
        assert j2["base_price"] == 3400
        assert j2["coloring_price"] == 500
        assert j2["coloring_original_price"] == 2800


# ---------- Coloring add-on pricing ----------
class TestColoringAddon:
    def test_order_without_addon(self, http, photo_path):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_NoAddon"))
        assert r.status_code == 200, r.text
        o = r.json()
        _created_orders.append(o["id"])
        assert o["amount"] == 3400
        assert o["subtotal"] == 3400
        assert o.get("add_coloring") in (False, None)

    def test_order_with_addon(self, http, photo_path, admin_headers):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, True, "TEST_WithAddon"))
        assert r.status_code == 200, r.text
        o = r.json()
        _created_orders.append(o["id"])
        assert o["amount"] == 3900, f"expected 3900 got {o['amount']}"
        assert o["subtotal"] == 3900
        # verify persisted
        r2 = http.get(f"{BASE_URL}/api/admin/orders/{o['id']}", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json().get("add_coloring") is True


# ---------- BUG FIX: approve does NOT delete photo; ship DOES ----------
class TestApproveShipPhotoLifecycle:
    def test_approve_keeps_photo_ship_deletes(self, http, photo_path, admin_headers):
        # Create order
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_Lifecycle"))
        assert r.status_code == 200
        oid = r.json()["id"]
        _created_orders.append(oid)

        # Trigger background generation (do NOT wait)
        rg = http.post(f"{BASE_URL}/api/admin/orders/{oid}/regenerate", headers=admin_headers)
        assert rg.status_code == 200
        assert rg.json().get("ok") is True

        # Approve -> reference_photo_deleted must STILL be false
        ra = http.post(f"{BASE_URL}/api/admin/orders/{oid}/status",
                       json={"status": "approved"}, headers=admin_headers)
        assert ra.status_code == 200
        got = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
        assert got["status"] == "approved"
        assert got.get("reference_photo_deleted") is False, "approve MUST NOT delete ref photo"

        # Ship -> reference_photo_deleted becomes true
        rs = http.post(f"{BASE_URL}/api/admin/orders/{oid}/status",
                       json={"status": "shipped"}, headers=admin_headers)
        assert rs.status_code == 200
        got2 = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
        assert got2["status"] == "shipped"
        assert got2.get("reference_photo_deleted") is True, "ship MUST delete ref photo"


# ---------- BUG FIX: regenerate guard ----------
class TestRegenerateGuard:
    def test_regenerate_ok_when_photo_present(self, http, photo_path, admin_headers):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_RegenOK"))
        oid = r.json()["id"]
        _created_orders.append(oid)
        rr = http.post(f"{BASE_URL}/api/admin/orders/{oid}/regenerate", headers=admin_headers)
        assert rr.status_code == 200
        assert rr.json().get("ok") is True

    def test_regenerate_blocked_when_photo_deleted(self, http, photo_path, admin_headers):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_RegenBlock"))
        oid = r.json()["id"]
        _created_orders.append(oid)
        # Explicitly delete reference photo via admin endpoint
        d = http.delete(f"{BASE_URL}/api/admin/orders/{oid}/reference-photo", headers=admin_headers)
        assert d.status_code == 200
        # regenerate must be blocked with 400 + Arabic message
        rr = http.post(f"{BASE_URL}/api/admin/orders/{oid}/regenerate", headers=admin_headers)
        assert rr.status_code == 400
        detail = rr.json().get("detail", "")
        assert "حذف" in detail and "المرجع" in detail, f"unexpected detail: {detail}"


# ---------- Regression: management endpoints ----------
class TestRegressionAdmin:
    def test_stats(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        for k in ("total_orders", "revenue_today", "avg_order_value", "by_type"):
            assert k in r.json()

    def test_orders_list_and_filters(self, http, admin_headers):
        assert http.get(f"{BASE_URL}/api/admin/orders", headers=admin_headers).status_code == 200
        assert http.get(f"{BASE_URL}/api/admin/orders?status=awaiting_payment",
                        headers=admin_headers).status_code == 200
        assert http.get(f"{BASE_URL}/api/admin/orders?search=TEST",
                        headers=admin_headers).status_code == 200

    def test_bulk_status_and_delete(self, http, photo_path, admin_headers):
        # Create two orders
        ids = []
        for i in range(2):
            r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, f"TEST_Bulk{i}"))
            ids.append(r.json()["id"])
        # bulk status
        rs = http.post(f"{BASE_URL}/api/admin/orders/bulk",
                       json={"order_ids": ids, "action": "status", "status": "approved", "note": "bulk"},
                       headers=admin_headers)
        assert rs.status_code == 200
        assert rs.json().get("updated") == 2
        # bulk delete
        rd = http.post(f"{BASE_URL}/api/admin/orders/bulk",
                       json={"order_ids": ids, "action": "delete"},
                       headers=admin_headers)
        assert rd.status_code == 200
        assert rd.json().get("deleted") == 2

    def test_delete_single(self, http, photo_path, admin_headers):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_DelSingle"))
        oid = r.json()["id"]
        rd = http.delete(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers)
        assert rd.status_code == 200
        assert rd.json().get("deleted") == 1

    def test_rebuild_pdf_400_when_no_pages(self, http, photo_path, admin_headers):
        # freshly created order has no pages yet -> 400
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_Rebuild"))
        oid = r.json()["id"]
        _created_orders.append(oid)
        rr = http.post(f"{BASE_URL}/api/admin/orders/{oid}/rebuild-pdf", headers=admin_headers)
        assert rr.status_code == 400

    def test_restore_version_guards(self, http, admin_headers):
        # unknown order -> 404
        r = http.post(f"{BASE_URL}/api/admin/orders/nonexistent/restore-version/1",
                      headers=admin_headers)
        assert r.status_code == 404
        # no auth -> 401/403
        r2 = http.post(f"{BASE_URL}/api/admin/orders/whatever/restore-version/1")
        assert r2.status_code in (401, 403)

    def test_create_order_status_awaiting(self, http, photo_path):
        r = http.post(f"{BASE_URL}/api/orders", json=_payload(photo_path, False, "TEST_Await"))
        assert r.status_code == 200
        o = r.json()
        _created_orders.append(o["id"])
        assert o["status"] == "awaiting_payment"
        assert o["payment_status"] == "pending"
        # no auto-generation: no pages / no pdf yet
        assert not o.get("pages")
        assert not o.get("pdf_path")
