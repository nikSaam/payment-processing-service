import asyncio
import logging
import random
from typing import Any

from faststream import FastStream
from faststream.rabbit import RabbitMessage

from app.core.config import settings
from app.db.session import SessionFactory
from app.messaging.broker import broker
from app.messaging.topology import DLQ_QUEUE, PAYMENTS_QUEUE, RETRY_QUEUES
from app.models.payment import Payment
from app.services.payments import complete_payment
from app.services.webhooks import send_payment_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def emulate_gateway() -> bool:
    await asyncio.sleep(
        random.uniform(
            settings.payment_min_processing_seconds,
            settings.payment_max_processing_seconds,
        )
    )
    return random.random() < 0.90


@broker.subscriber(PAYMENTS_QUEUE)
async def process_payment(message: dict[str, Any], msg: RabbitMessage) -> None:
    payment_id = message.get("payment_id")
    if not payment_id:
        logger.error("Invalid payment event without payment_id: %s", message)
        await broker.publish(message, queue="payments.dlq", persist=True)
        return

    headers = msg.headers or {}
    retry_count = int(headers.get("x-retry-count", 0))

    try:
        async with SessionFactory() as session:
            # Check first to avoid running gateway simulation for already handled events.
            from sqlalchemy import select
            import uuid

            payment = await session.scalar(
                select(Payment).where(Payment.id == uuid.UUID(str(payment_id)))
            )
            if payment is None:
                logger.error("Payment %s not found; sending event to DLQ", payment_id)
                await broker.publish(message, queue="payments.dlq", persist=True)
                return
            if payment.status.value != "pending":
                logger.info("Payment %s already processed; duplicate event ignored", payment_id)
                return

            succeeded = await emulate_gateway()
            updated = await complete_payment(session, payment.id, succeeded)

        if updated is not None:
            await send_payment_webhook(updated)

    except Exception:
        logger.exception("Unexpected processing error for payment %s", payment_id)
        if retry_count < 3:
            next_attempt = retry_count + 1
            await broker.publish(
                message,
                queue=f"payments.retry.{next_attempt}",
                headers={"x-retry-count": next_attempt},
                persist=True,
            )
        else:
            await broker.publish(message, queue="payments.dlq", persist=True)


app = FastStream(broker)


@app.after_startup
async def declare_retry_topology() -> None:
    for queue in RETRY_QUEUES:
        await broker.declare_queue(queue)
    await broker.declare_queue(DLQ_QUEUE)


if __name__ == "__main__":
    app.run()
