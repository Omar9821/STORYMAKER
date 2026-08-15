"""Tests for the NEW version-restore feature and admin regression.

Covers:
- Admin login + JWT auth
- Regression: GET /api/admin/{stats,orders,coupons,tickets,settings} all 200 with token
- Partial regeneration endpoints (regenerate-page, regenerate-text) return {ok:true}
  for a real order and 404 for a missing one
- NEW: POST /api/admin/orders/{order_id}/restore-version/{version_num}
    * 401 without token
    * 404 for a non-existent order
    * 404 when version_num doesn't exist on a real order
    * 200 {ok:true} when a snapshot exists (created by calling regenerate-text first)
- Backend import/startup smoke: /api/config returns 200 (proves pdf_service.py did not
  break the app at startup after the RTL fix).

Uses admin creds from /app/memory/test_credentials.md.
Does NOT wait for fal.ai background work; only validates endpoint contracts +
that a version snapshot is created quickly by regenerate-text.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@hikayati.dz")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Hikayati@2026")

FAKE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(scope="module")
def http():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_headers(http):
    r = http.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and data["token"]
    assert data.get("email") == ADMIN_EMAIL.lower() or data.get("email") == ADMIN_EMAIL
    return {"Authorization": f"Bearer {data['token']}"}


@pytest.fixture(scope="module")
def review_order_id(http, admin_headers):
    """Pick an existing order with pages>=1 (status review) so we can snapshot versions."""
    r = http.get(f"{BASE_URL}/api/admin/orders", headers=admin_headers)
    assert r.status_code == 200
    orders = r.json()
    for o in orders:
        if o.get("status") == "review" and (o.get("pages") or []):
            return o["id"]
    pytest.skip("no completed 'review' order with pages available for version tests")


# ---------------- Smoke ----------------
class TestSmoke:
    def test_config_public(self, http):
        r = http.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200, r.text
        j = r.json()
        assert "price" in j and "currency" in j
        assert j["currency"] == "DZD"

    def test_admin_login_returns_token(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert isinstance(r.json().get("token"), str)
        assert len(r.json()["token"]) > 20

    def test_admin_login_wrong_password(self, http):
        r = http.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": "wrong_pw_xxx"})
        assert r.status_code == 401


# ---------------- Admin regression ----------------
class TestAdminRegression:
    def test_stats(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        for k in ("total_orders", "revenue_dzd", "by_status", "by_type"):
            assert k in j, f"missing key {k}"

    def test_orders(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/orders", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_coupons(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/coupons", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tickets(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/tickets", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_settings(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        assert "base_price" in j and "extra_character_price" in j


# ---------------- Partial regeneration ----------------
class TestPartialRegen:
    def test_regenerate_text_missing_order_404(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/orders/{FAKE_ID}/regenerate-text",
                      headers=admin_headers)
        assert r.status_code == 404

    def test_regenerate_page_missing_order_404(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/orders/{FAKE_ID}/regenerate-page/1",
                      headers=admin_headers)
        assert r.status_code == 404

    def test_regenerate_text_ok(self, http, admin_headers, review_order_id):
        r = http.post(f"{BASE_URL}/api/admin/orders/{review_order_id}/regenerate-text",
                      headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

    def test_regenerate_page_ok(self, http, admin_headers, review_order_id):
        r = http.post(f"{BASE_URL}/api/admin/orders/{review_order_id}/regenerate-page/1",
                      headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}


# ---------------- NEW: version restore ----------------
class TestVersionRestore:
    def test_restore_requires_auth(self, http):
        r = http.post(f"{BASE_URL}/api/admin/orders/{FAKE_ID}/restore-version/1")
        assert r.status_code in (401, 403), r.text

    def test_restore_missing_order_404(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/orders/{FAKE_ID}/restore-version/1",
                      headers=admin_headers)
        assert r.status_code == 404

    def test_restore_missing_version_404(self, http, admin_headers, review_order_id):
        r = http.post(f"{BASE_URL}/api/admin/orders/{review_order_id}/restore-version/9999",
                      headers=admin_headers)
        assert r.status_code == 404

    def test_restore_ok_after_snapshot(self, http, admin_headers, review_order_id):
        """Trigger regenerate-text to force at least one snapshot, then restore v1."""
        # Kick a snapshot (fire-and-forget, snapshot_version runs early in the task)
        rt = http.post(f"{BASE_URL}/api/admin/orders/{review_order_id}/regenerate-text",
                       headers=admin_headers)
        assert rt.status_code == 200

        # Poll admin-order until versions[] has >=1 entry (snapshot happens synchronously
        # at task start; give up to ~15s in case the event loop is busy).
        deadline = time.time() + 15
        versions = []
        while time.time() < deadline:
            g = http.get(f"{BASE_URL}/api/admin/orders/{review_order_id}",
                         headers=admin_headers)
            assert g.status_code == 200
            versions = g.json().get("versions") or []
            if versions:
                break
            time.sleep(0.5)
        assert versions, "no versions snapshot appeared after regenerate-text"

        v1 = versions[0]["version"]
        r = http.post(f"{BASE_URL}/api/admin/orders/{review_order_id}/restore-version/{v1}",
                      headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
