"""
Backend tests for the manual/COD order lifecycle (Chargily disabled).

Covers:
- POST /api/orders creates order in awaiting_payment / pending, no generation triggered.
- Online payment disabled: POST /api/orders/{id}/pay {method:chargily} -> 400.
- COD confirm via pay endpoint: sets cod_pending, method=cod, keeps awaiting_payment.
- Admin regenerate on pending order: flips to cod_pending + starts generation.
- Admin regression endpoints still 200.
- Version restore guards (401 no auth, 404 missing).
- art_style stored & returned.
"""

import io
import os
import time
import pytest
import requests
from PIL import Image


def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fall back to reading /app/frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not configured"
    return url.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@hikayati.dz"
ADMIN_PASSWORD = "Hikayati@2026"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    return s


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def uploaded_photo_path(client):
    img = Image.new("RGB", (600, 600), (200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    files = {"file": ("test.png", buf, "image/png")}
    r = client.post(f"{API}/orders/upload-photo", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("path")
    return body["path"]


def _order_payload(photo_path, art_style="cartoon"):
    return {
        "characters": [{
            "name": "TEST_Child",
            "age": "5",
            "gender": "boy",
            "photo_path": photo_path,
            "is_main": True,
        }],
        "story_type": "adventure",
        "positive_behaviors": "kindness",
        "negative_behaviors": "",
        "language": "ar",
        "language_level": "simple",
        "art_style": art_style,
        "lives_with": "parents",
        "quantity": 1,
        "customer_name": "TEST_Customer",
        "customer_phone": "0555000000",
        "shipping_address": "TEST Address",
        "wilaya": "Algiers",
        "consent": True,
    }


# ---------------- Tests ----------------
def test_create_order_awaiting_payment(client, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path))
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["status"] == "awaiting_payment"
    assert o["payment_status"] == "pending"
    assert o.get("pages") in ([], None)
    # persist by GET
    r2 = client.get(f"{API}/orders/{o['id']}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "awaiting_payment"


def test_online_payment_disabled(client, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path))
    order_id = r.json()["id"]
    r2 = client.post(f"{API}/orders/{order_id}/pay",
                     json={"method": "chargily", "payment_method": "edahabia"})
    assert r2.status_code == 400, f"expected 400, got {r2.status_code} {r2.text}"


def test_cod_confirm_no_generation(client, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path))
    order_id = r.json()["id"]
    r2 = client.post(f"{API}/orders/{order_id}/pay", json={"method": "cod"})
    assert r2.status_code == 200, r2.text
    # verify state
    r3 = client.get(f"{API}/orders/{order_id}")
    assert r3.status_code == 200
    o = r3.json()
    assert o["payment_status"] == "cod_pending"
    assert o["payment_method"] == "cod"
    assert o["status"] == "awaiting_payment"


def test_admin_regenerate_requires_auth(client, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path))
    order_id = r.json()["id"]
    r2 = client.post(f"{API}/admin/orders/{order_id}/regenerate")
    assert r2.status_code in (401, 403)


def test_admin_regenerate_starts_generation(client, admin_headers, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path))
    assert r.status_code == 200
    order_id = r.json()["id"]

    r2 = client.post(f"{API}/admin/orders/{order_id}/regenerate", headers=admin_headers)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("ok") is True

    # Give the background task a moment to push the "generating" status
    time.sleep(1.5)

    r3 = client.get(f"{API}/admin/orders/{order_id}", headers=admin_headers)
    assert r3.status_code == 200
    o = r3.json()
    assert o["payment_method"] == "cod"
    assert o["payment_status"] == "cod_pending"
    assert o["status"] == "generating", f"expected generating, got {o['status']}"


def test_admin_regression_endpoints(client, admin_headers):
    for path in ["/admin/stats", "/admin/orders", "/admin/coupons",
                 "/admin/tickets", "/admin/settings"]:
        r = client.get(f"{API}{path}", headers=admin_headers)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"


def test_restore_version_guards(client, admin_headers, uploaded_photo_path):
    # No auth -> 401/403
    r = client.post(f"{API}/admin/orders/nonexistent/restore-version/1")
    assert r.status_code in (401, 403)
    # With auth but missing order -> 404
    r2 = client.post(f"{API}/admin/orders/does-not-exist-xyz/restore-version/1",
                     headers=admin_headers)
    assert r2.status_code == 404, f"expected 404, got {r2.status_code} {r2.text}"


def test_art_style_stored(client, uploaded_photo_path):
    r = client.post(f"{API}/orders", json=_order_payload(uploaded_photo_path, art_style="watercolor"))
    assert r.status_code == 200
    order_id = r.json()["id"]
    r2 = client.get(f"{API}/orders/{order_id}")
    assert r2.status_code == 200
    assert r2.json().get("art_style") == "watercolor"
