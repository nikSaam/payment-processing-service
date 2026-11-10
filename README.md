# Асинхронный сервис процессинга платежей

Реализация тестового задания: FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + PostgreSQL + RabbitMQ/FastStream + Alembic + Docker Compose.

## Возможности

- `POST /api/v1/payments` — создание платежа, ответ `202 Accepted`.
- `GET /api/v1/payments/{payment_id}` — получение состояния платежа.
- Статический API key в `X-API-Key`.
- Идемпотентность по `Idempotency-Key`, включая защиту от конкурентной вставки через уникальное ограничение БД.
- Outbox: платёж и событие сохраняются в одной транзакции PostgreSQL.
- Фоновый Outbox Publisher публикует события в RabbitMQ.
- Consumer эмулирует шлюз (2–5 секунд, 90% успеха / 10% бизнес-отказ).
- Webhook отправляется с таймаутом и тремя попытками с экспоненциальной задержкой.
- Инфраструктурные ошибки обработки повторяются через TTL retry queues; после трёх повторов событие уходит в DLQ.

## Запуск

```bash
cp .env.example .env
# Обязательно поменяйте API_KEY перед публикацией/развёртыванием.
docker compose up --build
```

После запуска:
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- RabbitMQ Management: http://localhost:15672 (guest / guest)

Миграции запускаются отдельным сервисом `migrate` до старта API и consumer.

## Пример создания платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me-in-production' \
  -H 'Idempotency-Key: order-10001' \
  -d '{
    "amount": "1250.50",
    "currency": "RUB",
    "description": "Оплата заказа 10001",
    "metadata": {"order_id": 10001},
    "webhook_url": "https://webhook.site/your-unique-url"
  }'
```

Ответ (пример):
```json
{
  "payment_id": "a2d1d3b6-5c6e-4c3e-a1a2-123456789abc",
  "status": "pending",
  "created_at": "2026-01-01T12:00:00Z"
}
```

## Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/PAYMENT_UUID \
  -H 'X-API-Key: change-me-in-production'
```

Повторный запрос с тем же `Idempotency-Key` и тем же телом вернёт исходный платёж. Повторное использование ключа с другим телом вернёт `409 Conflict`.

## Архитектурные решения и гарантии

### Outbox

В одной транзакции создаются `payments` и `outbox`. Поэтому не возникает состояния, когда платёж сохранён, а событие для публикации потеряно из-за падения процесса до отправки в RabbitMQ.

Publisher блокирует выбранные строки через `FOR UPDATE SKIP LOCKED`, публикует сообщения и отмечает их `published_at`. Если процесс упадёт после публикации, но до commit, возможна повторная публикация. Это нормальная семантика at-least-once; consumer должен быть идемпотентным.

### Idempotency

`Idempotency-Key` имеет уникальный индекс. Дополнительно сохраняется SHA-256 fingerprint нормализованного тела. Один ключ с тем же телом возвращает существующий платёж, с другим телом — `409`.

### Retry и DLQ

Retry очереди имеют TTL 2, 4 и 8 секунд и dead-letter routing обратно в `payments.new`. Счётчик попыток передаётся в заголовке `x-retry-count`. После трёх повторных попыток событие публикуется в `payments.dlq`.

Бизнес-результат `failed` (те самые 10% отказов шлюза) не считается технической ошибкой и не запускает повторную обработку платежа.

### Webhook

Webhook отправляется после фиксации результата платежа. Для HTTP-ошибок выполняются до трёх попыток с задержками 1 и 2 секунды. Ошибка webhook не должна откатывать уже завершённый платёж.

## Проверки

Локально (при установленном окружении):
```bash
pip install -e '.[dev]'
pytest
```

## Важные замечания для production

Это тестовое решение демонстрирует требуемые паттерны, но перед production-развёртыванием стоит добавить:
- отдельную таблицу/очередь для устойчивого хранения задач webhook и их retry;
- подпись webhook (HMAC), SSRF-защиту и allowlist доменов;
- метрики, трассировку, структурированные логи и graceful shutdown;
- миграции/тесты интеграции с реальным RabbitMQ и PostgreSQL;
- политику хранения idempotency keys и rate limiting;
- отдельный механизм reconciliation для зависших платежей.

## Ограничения реализации

- `payments.dlq` предназначена для ручного разбора; автоматического replay-инструмента нет.
- В этом задании consumer один логический обработчик, запускаемый одним сервисом.
- События outbox доставляются как минимум один раз, не exactly-once.
