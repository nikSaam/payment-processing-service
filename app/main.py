from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.messaging.outbox_publisher import run_outbox_publisher


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    publisher_task = asyncio.create_task(run_outbox_publisher())
    try:
        yield
    finally:
        publisher_task.cancel()
        try:
            await publisher_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Payment Processing Service",
    version="1.0.0",
    description="Asynchronous payment processing API",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
