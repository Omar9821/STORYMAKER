"""Hikayati backend end-to-end tests.

Covers:
- config/health
- photo quality check
- full order pipeline (COD): create -> pay -> poll -> file serving
- online mock payment (chargily -> mock-confirm)
- admin auth + admin endpoints + privacy log
"""
import os
import io
import time
import base64
import pytest
import requests
from PIL import Image

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://story-maker-dz.preview.emergentagent.com"
ADMIN_EMAIL = "admin@hikayati.dz"
ADMIN_PASSWORD = "Hikayati@2026"

# ---------- helpers ----------
def _png_bytes(w=600, h=600, color=(220, 180, 140)):
    img = Image.new("RGB", (w, h), color=color)
    # add a small variation to avoid pure-flat
    for i in range(0, w, 40):
        for j in range(0, h, 40):
            img.putpixel((i, j), (180, 120, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    return s


@pytest.fixture(scope="session")
def admin_token(http):
    r = http.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- config / health ----------
class TestConfig:
    def test_root(self, http):
        r = http.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert r.json()["price"] == 3400

    def test_config(self, http):
        r = http.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["price"] == 3400
        assert data["currency"] == "DZD"
        assert data["payment_mock"] is True


# ---------- photo check ----------
class TestPhotoCheck:
    def test_photo_ok(self, http):
        files = {"file": ("ok.png", _png_bytes(600, 600), "image/png")}
        r = http.post(f"{BASE_URL}/api/orders/check-photo", files=files)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["width"] == 600

    def test_photo_too_small(self, http):
        files = {"file": ("small.png", _png_bytes(200, 200), "image/png")}
        r = http.post(f"{BASE_URL}/api/orders/check-photo", files=files)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is False


# ---------- Admin auth ----------
class TestAdminAuth:
    def test_login_ok(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_wrong_password(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass"})
        assert r.status_code == 401

    def test_me_requires_token(self, http):
        r = http.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)

    def test_me_with_token(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_admin_endpoints_reject_no_token(self, http):
        for path in ["/api/admin/stats", "/api/admin/orders", "/api/admin/privacy-logs"]:
            r = http.get(f"{BASE_URL}{path}")
            assert r.status_code in (401, 403), f"{path} did not reject: {r.status_code}"


# ---------- Order creation helper ----------
def _create_order(http, name="TEST_Sara"):
    photo = _png_bytes(600, 600)
    files = {"photo": ("child.png", photo, "image/png")}
    form = {
        "child_name": name,
        "child_age": "5",
        "child_gender": "girl",
        "story_type": "encouragement",
        "behavior_focus": "confidence",
        "language": "ar",
        "customer_name": "TEST_Customer",
        "customer_phone": "0555000000",
        "customer_email": "test@example.com",
        "shipping_address": "Test street 1",
        "wilaya": "Alger",
        "consent": "true",
    }
    r = http.post(f"{BASE_URL}/api/orders", data=form, files=files)
    assert r.status_code == 200, f"create order failed: {r.status_code} {r.text}"
    o = r.json()
    assert o["status"] == "awaiting_payment"
    assert o["amount"] == 3400
    assert "id" in o
    return o["id"]


class TestOrderCOD:
    order_id = None
    order_final = None

    def test_create_order_cod(self, http):
        oid = _create_order(http)
        TestOrderCOD.order_id = oid
        # consent required
        photo = _png_bytes(600, 600)
        r = http.post(
            f"{BASE_URL}/api/orders",
            data={
                "child_name": "X", "child_age": "5", "child_gender": "boy",
                "story_type": "encouragement", "language": "ar",
                "customer_name": "c", "customer_phone": "1", "shipping_address": "a",
                "wilaya": "Alger", "consent": "false",
            },
            files={"photo": ("p.png", photo, "image/png")},
        )
        assert r.status_code == 400

    def test_pay_cod(self, http):
        oid = TestOrderCOD.order_id
        r = http.post(f"{BASE_URL}/api/orders/{oid}/pay", json={"method": "cod"})
        assert r.status_code == 200
        j = r.json()
        assert j["method"] == "cod"
        assert j["order_id"] == oid

    def test_poll_until_review(self, http):
        oid = TestOrderCOD.order_id
        deadline = time.time() + 150
        final = None
        while time.time() < deadline:
            r = http.get(f"{BASE_URL}/api/orders/{oid}")
            assert r.status_code == 200
            o = r.json()
            if o["status"] in ("review", "failed"):
                final = o
                break
            time.sleep(4)
        assert final is not None, "Generation did not finish within timeout"
        assert final["status"] == "review", f"Generation failed: {final.get('status_history')}"
        assert final.get("story_title")
        assert len(final.get("pages", [])) == 5
        for p in final["pages"]:
            assert p.get("image_path")
            assert "similarity_score" in p
        assert final.get("cover_path")
        assert final.get("pdf_path")
        assert final.get("ai_cost_usd", 0) > 0
        TestOrderCOD.order_final = final

    def test_files_served(self, http):
        o = TestOrderCOD.order_final
        assert o is not None
        r1 = http.get(f"{BASE_URL}/api/files/{o['cover_path']}")
        assert r1.status_code == 200
        assert len(r1.content) > 100
        r2 = http.get(f"{BASE_URL}/api/files/{o['pdf_path']}")
        assert r2.status_code == 200
        assert r2.content[:4] == b"%PDF"


class TestOnlineMockPayment:
    order_id = None

    def test_create_and_online_pay(self, http):
        oid = _create_order(http, name="TEST_Adam")
        TestOnlineMockPayment.order_id = oid
        r = http.post(f"{BASE_URL}/api/orders/{oid}/pay", json={"method": "chargily", "payment_method": "edahabia"})
        assert r.status_code == 200
        j = r.json()
        assert j["method"] == "chargily"
        assert "/pay/mock" in j["checkout_url"]
        assert j.get("mock") is True

    def test_mock_confirm(self, http):
        oid = TestOnlineMockPayment.order_id
        r = http.post(f"{BASE_URL}/api/payments/mock-confirm/{oid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Ensure status flipped to paid or generating quickly
        time.sleep(2)
        r2 = http.get(f"{BASE_URL}/api/orders/{oid}")
        assert r2.status_code == 200
        assert r2.json()["status"] in ("paid", "generating", "review")


class TestAdminEndpoints:
    def test_stats(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        assert "total_orders" in j and j["total_orders"] >= 1
        assert "by_status" in j
        assert "revenue_dzd" in j

    def test_list_orders(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/orders", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_get_and_update_status_and_delete_photo(self, http, admin_headers):
        oid = TestOrderCOD.order_id
        assert oid, "Depends on TestOrderCOD"
        r = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["id"] == oid

        r2 = http.post(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "approved", "note": "ok"}, headers=admin_headers)
        assert r2.status_code == 200
        r3 = http.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers)
        assert r3.json()["status"] == "approved"
        assert r3.json().get("reference_photo_deleted") is True

        # delete reference photo again (idempotent) -> log entry
        r4 = http.delete(f"{BASE_URL}/api/admin/orders/{oid}/reference-photo", headers=admin_headers)
        assert r4.status_code == 200

    def test_privacy_logs(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/privacy-logs", headers=admin_headers)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        assert any(l.get("order_id") == TestOrderCOD.order_id for l in logs)
