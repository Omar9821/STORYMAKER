"""Chargily Pay v2 checkout + webhook verification. Falls back to MOCK mode when no key is set."""
import os
import hmac
import hashlib
import httpx

CHARGILY_SECRET_KEY = os.environ.get("CHARGILY_SECRET_KEY", "").strip()
CHARGILY_BASE_URL = os.environ.get("CHARGILY_BASE_URL", "https://pay.chargily.net/test/api/v2")
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

MOCK_MODE = not bool(CHARGILY_SECRET_KEY)


async def create_checkout(order_id: str, amount: int, payment_method: str = "edahabia") -> dict:
    """Returns {'checkout_url': str, 'checkout_id': str, 'mock': bool}."""
    if MOCK_MODE:
        # MOCKED: no Chargily key configured. Simulate a hosted checkout page.
        return {
            "checkout_url": f"{FRONTEND_URL}/pay/mock?order_id={order_id}",
            "checkout_id": f"mock_{order_id}",
            "mock": True,
        }

    payload = {
        "amount": amount,
        "currency": "dzd",
        "payment_method": payment_method,
        "locale": "ar",
        "description": f"Hikayati order {order_id}",
        "metadata": [{"order_id": order_id}],
        "success_url": f"{FRONTEND_URL}/track/{order_id}?paid=1",
        "failure_url": f"{FRONTEND_URL}/track/{order_id}?failed=1",
        "webhook_endpoint": f"{BACKEND_PUBLIC_URL}/api/payments/webhook",
    }
    headers = {"Authorization": f"Bearer {CHARGILY_SECRET_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{CHARGILY_BASE_URL}/checkouts", headers=headers, json=payload)
    if resp.is_error:
        raise RuntimeError("Chargily checkout creation failed")
    data = resp.json()
    return {"checkout_url": data["checkout_url"], "checkout_id": data["id"], "mock": False}


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if MOCK_MODE or not signature:
        return False
    expected = hmac.new(CHARGILY_SECRET_KEY.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
