from config import REDIS_HOST, REDIS_PORT
import json
import redis.asyncio as redis
from datetime import datetime

REDIS_HOST = REDIS_HOST
REDIS_PORT = REDIS_PORT

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

async def get_cache(key: str):
    data = await redis_client.get(key)
    if data:
        loaded_data = json.loads(data)
        if "created_at" in loaded_data:
            loaded_data["created_at"] = datetime.fromisoformat(loaded_data["created_at"])
        if "last_accessed_at" in loaded_data and loaded_data["last_accessed_at"]:
            loaded_data["last_accessed_at"] = datetime.fromisoformat(loaded_data["last_accessed_at"])
        return loaded_data
    return None

async def set_cache(key: str, value, expire: int = 60):
    if "created_at" in value and isinstance(value["created_at"], datetime):
        value["created_at"] = value["created_at"].isoformat()
    
    if "last_accessed_at" in value and isinstance(value["last_accessed_at"], datetime):
        value["last_accessed_at"] = value["last_accessed_at"].isoformat()
    
    await redis_client.set(key, json.dumps(value), ex=expire)
    
    await redis_client.set(key, json.dumps(value), ex=expire)
async def delete_cache(key: str):
    await redis_client.delete(key)
