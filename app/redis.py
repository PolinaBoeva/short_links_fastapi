from config import REDIS_HOST, REDIS_PORT
import json
import redis.asyncio as redis
from datetime import datetime

REDIS_HOST = REDIS_HOST
REDIS_PORT = REDIS_PORT

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def set_cache(key: str, value, expire: int = 60):
    if "created_at" in value and isinstance(value["created_at"], datetime):
        value["created_at"] = value["created_at"].isoformat()

    if "last_accessed_at" in value and isinstance(value["last_accessed_at"], datetime):
        value["last_accessed_at"] = value["last_accessed_at"].isoformat()

    logger.info(
        f"Setting cache for key: {key} with value: {value} and expire time: {expire}"
    )

    await redis_client.set(key, json.dumps(value), ex=expire)


async def get_cache(key: str):
    logger.info(f"Getting cache for key: {key}")
    data = await redis_client.get(key)
    if data:
        loaded_data = json.loads(data)
        if "created_at" in loaded_data:
            loaded_data["created_at"] = datetime.fromisoformat(
                loaded_data["created_at"]
            )
        if "last_accessed_at" in loaded_data and loaded_data["last_accessed_at"]:
            loaded_data["last_accessed_at"] = datetime.fromisoformat(
                loaded_data["last_accessed_at"]
            )
        logger.info(f"Cache hit for key: {key}")
        return loaded_data
    logger.info(f"Cache miss for key: {key}")
    return None


async def delete_cache(key: str):
    await redis_client.delete(key)
