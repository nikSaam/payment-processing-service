from faststream.rabbit import RabbitQueue

from app.core.config import settings

# Retry queues use broker-side TTL and dead-letter routing back to payments.new.
# The consumer increments x-retry-count before publishing to the next retry queue.
def retry_queue(attempt: int) -> RabbitQueue:
    delay_ms = 2_000 * (2 ** (attempt - 1))
    return RabbitQueue(
        name=f"payments.retry.{attempt}",
        durable=True,
        arguments={
            "x-message-ttl": delay_ms,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.payments_queue,
        },
    )


PAYMENTS_QUEUE = RabbitQueue(settings.payments_queue, durable=True)
RETRY_QUEUES = [retry_queue(1), retry_queue(2), retry_queue(3)]
DLQ_QUEUE = RabbitQueue("payments.dlq", durable=True)
