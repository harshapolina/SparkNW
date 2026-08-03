"""MongoDB connection via Motor + Beanie document init."""

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from instascope_shared.core.config import get_settings


_client: AsyncIOMotorClient | None = None


async def connect_db() -> None:
    """Initialize Motor client and Beanie document models."""
    global _client
    from instascope_shared.models import DOCUMENT_MODELS

    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    db = _client[settings.mongodb_db]
    await init_beanie(database=db, document_models=DOCUMENT_MODELS)


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized")
    return _client
