"""Operational alerts (review item L9). Configure ONE of:
  ALERT_TELEGRAM_BOT_TOKEN + ALERT_TELEGRAM_CHAT_ID
  ALERT_WEBHOOK_URL   (Slack/Discord/Make/Zapier compatible: POST {"text": "..."})
Without configuration the alert is only logged."""
import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def alert(text: str):
    logger.error(f"ALERT: {text}")
    tok, chat = os.environ.get("ALERT_TELEGRAM_BOT_TOKEN"), os.environ.get("ALERT_TELEGRAM_CHAT_ID")
    hook = os.environ.get("ALERT_WEBHOOK_URL")
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            if tok and chat:
                await cx.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:3500]})
            elif hook:
                await cx.post(hook, json={"text": text[:3500], "content": text[:1900]})
    except Exception as e:
        logger.warning(f"alert delivery failed: {e}")
