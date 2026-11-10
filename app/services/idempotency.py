import hashlib
import json
from decimal import Decimal

from app.schemas.payment import PaymentCreate


def request_fingerprint(data: PaymentCreate) -> str:
    normalized = {
        "amount": format(Decimal(data.amount), "f"),
        "currency": data.currency.value,
        "description": data.description,
        "metadata": data.metadata,
        "webhook_url": str(data.webhook_url),
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
