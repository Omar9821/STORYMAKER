"""Hikayati backend end-to-end tests (updated for expanded JSON order API).

Covers:
- config/health
- photo upload endpoint (returns storage path)
- expanded JSON order creation with multiple characters + coupon
- admin settings (base/extra price) and reflection in /api/config
- coupon lifecycle + validate-coupon + discount applied on order
- tickets: public create, list-by-order, admin list, admin reply
- admin stats (revenue_today/week/month, avg_order_value, by_type, top_behaviors)
- COD payment -> real AI generation poll -> regenerate-text + regenerate-page/1
  -> versions grow, coloring_pdf_path exists and file serves
- admin auth guards (401 without token)
"""
import os
import io
import time
import pytest
import requests
from PIL import Image

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@hikayati.dz"
ADMIN_PASSWORD = "Hikayati@2026"


def _png_bytes(w=600, h=600, color=(220, 180, 140)):
    img = Image.new("RGB", (w, h), color=color)
    for i in range(0, w, 40):
        for j in range(0, h, 40):
            img.putpixel((i, j), (180, 120, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def http():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(http):
    r = http.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def uploaded_photo_path(http):
    """Upload a reference photo and return the storage path."""
    files = {"file": ("child.png", _png_bytes(600, 600), "image/png")}
    r = http.post(f"{BASE_URL}/api/orders/upload-photo", files=files)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j.get("path"), "upload-photo should return a path"
    return j["path"]


def _order_payload(photo_path, extra_chars=None, coupon_code="", quantity=1, name="TEST_Sara"):
    chars = [{
        "name": name, "age": 6, "gender": "girl", "hair_color": "black",
        "hair_type": "curly", "hair_length": "long", "hobbies": "reading",
        "favorite_color": "pink", "favorite_food": "couscous",
        "relation": "", "photo_path": photo_path, "is_main": True,
    }]
    for c in (extra_chars or []):
        chars.append(c)
    return {
        "characters": chars,
        "story_type": "encouragement",
        "positive_behaviors": "confidence, sharing",
        "negative_behaviors": "shouting",
        "special_details": "loves the sea",
        "language": "ar",
        "language_level": "simple",
        "story_setting": ["home", "school"],
        "lives_with": "parents",
        "mother_name": "Amina", "mother_age": "32",
        "father_name": "Karim", "father_age": "35",
        "mention_parents": True,
        "siblings": [{"name": "Yasmine", "age": "4", "relation": "sister"}],
        "friends": [{"name": "Lina", "age": "6", "relation": "friend"}],
        "quantity": quantity,
        "coupon_code": coupon_code,
        "customer_name": "TEST_Customer",
        "customer_phone": "0555000000",
        "customer_email": "test@example.com",
        "shipping_address": "1 Rue Didouche",
        "wilaya": "Alger",
        "consent": True,
    }


# ---------------- Config ----------------
class TestConfig:
    def test_root(self, http):
        r = http.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert "price" in r.json()

    def test_config_has_extra_price(self, http):
        r = http.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200
        j = r.json()
        assert j["currency"] == "DZD"
        assert "base_price" in j and "extra_character_price" in j
        assert j["payment_mock"] is True


# ---------------- Photo upload ----------------
class TestPhotoUpload:
    def test_upload_ok(self, uploaded_photo_path):
        assert uploaded_photo_path.startswith("hikayati/references/")

    def test_upload_too_small(self, http):
        files = {"file": ("small.png", _png_bytes(200, 200), "image/png")}
        r = http.post(f"{BASE_URL}/api/orders/upload-photo", files=files)
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ---------------- Admin auth guards ----------------
class TestAdminAuthGuards:
    @pytest.mark.parametrize("path,method", [
        ("/api/admin/stats", "GET"),
        ("/api/admin/orders", "GET"),
        ("/api/admin/settings", "GET"),
        ("/api/admin/coupons", "GET"),
        ("/api/admin/tickets", "GET"),
        ("/api/admin/privacy-logs", "GET"),
    ])
    def test_requires_bearer(self, http, path, method):
        r = http.request(method, f"{BASE_URL}{path}")
        assert r.status_code in (401, 403), f"{path} did not reject unauth: {r.status_code}"


# ---------------- Admin settings ----------------
class TestAdminSettings:
    def test_get_settings(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        assert "base_price" in j and "extra_character_price" in j

    def test_update_settings_reflected_in_config(self, http, admin_headers):
        # Set custom values
        payload = {"base_price": 3500, "extra_character_price": 300}
        r = http.put(f"{BASE_URL}/api/admin/settings", json=payload, headers=admin_headers)
        assert r.status_code == 200
        # Reflected in /api/config
        r2 = http.get(f"{BASE_URL}/api/config")
        j = r2.json()
        assert j["base_price"] == 3500
        assert j["extra_character_price"] == 300
        # Restore defaults
        r3 = http.put(f"{BASE_URL}/api/admin/settings",
                      json={"base_price": 3400, "extra_character_price": 250},
                      headers=admin_headers)
        assert r3.status_code == 200
        r4 = http.get(f"{BASE_URL}/api/config").json()
        assert r4["base_price"] == 3400
        assert r4["extra_character_price"] == 250


# ---------------- Coupons ----------------
class TestCoupons:
    CODE = "TESTPCT10"

    def test_create_coupon(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/coupons",
                      json={"code": self.CODE, "type": "percent", "value": 10},
                      headers=admin_headers)
        assert r.status_code == 200

    def test_validate_coupon_valid(self, http):
        r = http.post(f"{BASE_URL}/api/orders/validate-coupon",
                      json={"code": self.CODE, "subtotal": 3400})
        assert r.status_code == 200
        j = r.json()
        assert j["valid"] is True
        assert j["discount"] == 340

    def test_validate_coupon_invalid(self, http):
        r = http.post(f"{BASE_URL}/api/orders/validate-coupon",
                      json={"code": "DOES_NOT_EXIST", "subtotal": 3400})
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_list_coupons(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/coupons", headers=admin_headers)
        assert r.status_code == 200
        codes = [c["code"] for c in r.json()]
        assert self.CODE in codes


# ---------------- Order creation (JSON contract) ----------------
class TestOrderCreation:
    def test_create_order_single_character(self, http, uploaded_photo_path):
        payload = _order_payload(uploaded_photo_path)
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["status"] == "awaiting_payment"
        assert o["amount"] == 3400
        assert o["base_price"] == 3400
        assert o["extra_characters"] == 0
        assert o["subtotal"] == 3400
        assert o["discount"] == 0

    def test_create_order_multi_char_and_quantity(self, http, uploaded_photo_path):
        extra = [{
            "name": "Ali", "age": 8, "gender": "boy", "relation": "brother",
            "photo_path": "", "is_main": False,
        }, {
            "name": "Nour", "age": 5, "gender": "girl", "relation": "friend",
            "photo_path": "", "is_main": False,
        }]
        payload = _order_payload(uploaded_photo_path, extra_chars=extra, quantity=2)
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 200, r.text
        o = r.json()
        # unit = 3400 + 2*250 = 3900 ; qty 2 -> subtotal 7800
        assert o["extra_characters"] == 2
        assert o["subtotal"] == 7800
        assert o["amount"] == 7800

    def test_create_order_with_coupon_applies_discount(self, http, uploaded_photo_path, admin_headers):
        # Ensure TESTPCT10 exists
        http.post(f"{BASE_URL}/api/admin/coupons",
                  json={"code": TestCoupons.CODE, "type": "percent", "value": 10},
                  headers=admin_headers)
        payload = _order_payload(uploaded_photo_path, coupon_code=TestCoupons.CODE)
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 200
        o = r.json()
        assert o["subtotal"] == 3400
        assert o["discount"] == 340
        assert o["amount"] == 3060
        assert o["coupon_code"] == TestCoupons.CODE

    def test_create_order_consent_required(self, http, uploaded_photo_path):
        payload = _order_payload(uploaded_photo_path)
        payload["consent"] = False
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 400

    def test_create_order_main_character_photo_required(self, http):
        payload = _order_payload(photo_path="")
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 400


# ---------------- Tickets ----------------
class TestTickets:
    ticket_id = None
    order_id = None

    def test_public_create_ticket(self, http, uploaded_photo_path):
        # attach a real order id
        payload = _order_payload(uploaded_photo_path, name="TEST_TicketOrder")
        oc = http.post(f"{BASE_URL}/api/orders", json=payload).json()
        TestTickets.order_id = oc["id"]
        r = http.post(f"{BASE_URL}/api/tickets", json={
            "order_id": TestTickets.order_id,
            "name": "TEST_User",
            "message": "Any update?",
        })
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "open"
        assert j["order_id"] == TestTickets.order_id
        TestTickets.ticket_id = j["id"]

    def test_list_by_order(self, http):
        r = http.get(f"{BASE_URL}/api/tickets/{TestTickets.order_id}")
        assert r.status_code == 200
        assert any(t["id"] == TestTickets.ticket_id for t in r.json())

    def test_admin_list_tickets(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/tickets", headers=admin_headers)
        assert r.status_code == 200
        assert any(t["id"] == TestTickets.ticket_id for t in r.json())

    def test_admin_reply(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/tickets/{TestTickets.ticket_id}/reply",
                      json={"reply": "Hello, we're on it"}, headers=admin_headers)
        assert r.status_code == 200
        r2 = http.get(f"{BASE_URL}/api/tickets/{TestTickets.order_id}")
        found = [t for t in r2.json() if t["id"] == TestTickets.ticket_id][0]
        assert found["status"] == "answered"
        assert found["reply"] == "Hello, we're on it"


# ---------------- Admin stats ----------------
class TestAdminStats:
    def test_stats_shape(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        for k in ("total_orders", "revenue_today", "revenue_week",
                  "revenue_month", "avg_order_value", "by_type", "top_behaviors"):
            assert k in j, f"missing {k}"


# ---------------- Real generation + regeneration + versions ----------------
class TestGenerationAndRegen:
    order_id = None
    order_final = None

    def test_create_and_pay_cod(self, http, uploaded_photo_path):
        payload = _order_payload(uploaded_photo_path, name="TEST_Regen")
        r = http.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code == 200
        oid = r.json()["id"]
        TestGenerationAndRegen.order_id = oid
        r2 = http.post(f"{BASE_URL}/api/orders/{oid}/pay", json={"method": "cod"})
        assert r2.status_code == 200

    def test_poll_until_review(self, http):
        oid = TestGenerationAndRegen.order_id
        deadline = time.time() + 360  # up to 6 minutes for real AI
        final = None
        while time.time() < deadline:
            r = http.get(f"{BASE_URL}/api/orders/{oid}")
            assert r.status_code == 200
            o = r.json()
            if o["status"] in ("review", "failed"):
                final = o
                break
            time.sleep(6)
        assert final is not None, "Generation did not finish within timeout"
        assert final["status"] == "review", f"Generation failed: {final.get('status_history')}"
        assert final.get("story_title")
        assert len(final.get("pages", [])) >= 4
        assert final.get("cover_path")
        assert final.get("pdf_path")
        assert final.get("coloring_pdf_path"), "coloring_pdf_path missing"
        TestGenerationAndRegen.order_final = final

    def test_coloring_pdf_served(self, http):
        o = TestGenerationAndRegen.order_final
        r = http.get(f"{BASE_URL}/api/files/{o['coloring_pdf_path']}")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_regenerate_text_grows_versions(self, http, admin_headers):
        oid = TestGenerationAndRegen.order_id
        # baseline version count
        pre = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
        v0 = len(pre.get("versions", []))
        r = http.post(f"{BASE_URL}/api/admin/orders/{oid}/regenerate-text", headers=admin_headers)
        assert r.status_code == 200
        # poll for review again
        deadline = time.time() + 200
        while time.time() < deadline:
            o = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
            if o["status"] == "review" and len(o.get("versions", [])) > v0:
                assert o.get("pdf_path")
                return
            time.sleep(5)
        pytest.fail("regenerate-text did not complete / versions did not grow")

    def test_regenerate_page_1_grows_versions(self, http, admin_headers):
        oid = TestGenerationAndRegen.order_id
        pre = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
        v0 = len(pre.get("versions", []))
        r = http.post(f"{BASE_URL}/api/admin/orders/{oid}/regenerate-page/1", headers=admin_headers)
        assert r.status_code == 200
        deadline = time.time() + 200
        while time.time() < deadline:
            o = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers).json()
            if o["status"] == "review" and len(o.get("versions", [])) > v0:
                assert o.get("pdf_path")
                assert o.get("coloring_pdf_path")
                return
            time.sleep(5)
        pytest.fail("regenerate-page/1 did not complete / versions did not grow")
