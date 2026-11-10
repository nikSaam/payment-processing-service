import asyncio
import logging

import httpx

from app.core.config import settings
from app.models.payment import Payment

logger = logging.getLogger(__name__)


async def send_payment_webhook(payment: Payment) -> None:
    payload = {
        "event": "payment.processed",
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }

    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        for attempt in range(1, settings.webhook_max_attempts + 1):
            try:
                response = await client.post(payment.webhook_url, json=payload)
                response.raise_for_status()
                return
            except (httpx.HTTPError, ValueError):
                logger.exception(
                    "Webhook attempt %s/%s failed for payment %s",
                    attempt,
                    settings.webhook_max_attempts,
                    payment.id,
                )
                if attempt < settings.webhook_max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))

    logger.error("Webhook delivery exhausted for payment %s", payment.id)
