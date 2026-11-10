import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionFactory
from app.messaging.broker import broker
from app.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)


async def publish_outbox_batch() -> int:
    published = 0
    # Keep row locks until publish + published_at update commit. If the process
    # dies after broker publish but before commit, the event can be duplicated;
    # the consumer is therefore idempotent by payment status.
    async with SessionFactory() as session:
        async with session.begin():
            events = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at)
                    .limit(settings.outbox_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()

            for event in events:
                try:
                    await broker.publish(
                        event.payload,
                        queue=settings.payments_queue,
                        message_id=str(event.id),
                        persist=True,
                    )
                    event.published_at = datetime.now(timezone.utc)
                    event.attempts += 1
                    published += 1
                except Exception:
                    event.attempts += 1
                    logger.exception("Failed to publish outbox event %s", event.id)
                    # Leave published_at NULL; next polling iteration retries.
    return published


async def run_outbox_publisher() -> None:
    await broker.start()
    try:
        while True:
            await publish_outbox_batch()
            await asyncio.sleep(settings.outbox_poll_interval)
    finally:
        await broker.close()
