import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services.idempotency import request_fingerprint


async def create_payment(
    session: AsyncSession,
    data: PaymentCreate,
    idempotency_key: str,
) -> tuple[Payment, bool]:
    fingerprint = request_fingerprint(data)

    existing = await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used with a different request body",
            )
        return existing, False

    payment = Payment(
        id=uuid.uuid4(),
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        metadata_json=data.metadata,
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        webhook_url=str(data.webhook_url),
    )
    event = OutboxEvent(
        aggregate_id=payment.id,
        event_type="payment.created",
        payload={"payment_id": str(payment.id)},
    )
    session.add_all([payment, event])

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A concurrent request may have inserted the same key after our first read.
        existing = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if existing and existing.request_hash == fingerprint:
            return existing, False
        if existing:
            raise HTTPException(status_code=409, detail="Idempotency-Key conflict")
        raise

    await session.refresh(payment)
    return payment, True


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


async def complete_payment(
    session: AsyncSession,
    payment_id: uuid.UUID,
    succeeded: bool,
) -> Payment | None:
    payment = await session.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        return None
    # Consumer may receive the same event more than once.
    if payment.status != PaymentStatus.PENDING:
        return payment

    payment.status = PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED
    payment.processed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(payment)
    return payment
