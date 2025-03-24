import uvicorn
import asyncio
from fastapi import FastAPI
from auth import router as auth_router
from handlers import router
from app.models import Base
from app.database import engine
from app.tasks import periodic_task

app = FastAPI()

app.include_router(auth_router)
app.include_router(router)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def startup_event():
    await init_db()
    asyncio.create_task(periodic_task())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
