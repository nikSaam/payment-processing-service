from decimal import Decimal

from app.schemas.payment import PaymentCreate
from app.services.idempotency import request_fingerprint


def test_fingerprint_is_stable_for_same_payload():
    payload = PaymentCreate(
        amount=Decimal("10.00"),
        currency="RUB",
        description="Test",
        metadata={"b": 2, "a": 1},
        webhook_url="https://example.com/hook",
    )
    assert request_fingerprint(payload) == request_fingerprint(payload)


def test_fingerprint_changes_when_amount_changes():
    first = PaymentCreate(
        amount=Decimal("10.00"), currency="RUB", description="Test",
        metadata={}, webhook_url="https://example.com/hook",
    )
    second = PaymentCreate(
        amount=Decimal("11.00"), currency="RUB", description="Test",
        metadata={}, webhook_url="https://example.com/hook",
    )
    assert request_fingerprint(first) != request_fingerprint(second)
