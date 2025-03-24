import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.models import Link, LinkHistory
from app.database import async_session_maker 

async def delete_expired_links(db: AsyncSession):
    current_time = datetime.utcnow()
    result = await db.execute(select(Link).filter(Link.expires_at < current_time))
    expired_links = result.scalars().all()

    for link in expired_links:
        link_history = LinkHistory(
            short_code=link.short_code,
            original_url=link.original_url,
            expires_at=link.expires_at,
            click_count=link.click_count,
            user_id=link.user_id
        )
        db.add(link_history)
        await db.execute(delete(Link).where(Link.short_code == link.short_code))
        await db.commit()
        print(f"Moved expired link {link.short_code} to history and deleted.")

async def periodic_task():
    while True:
        async with async_session_maker() as session:
            await delete_expired_links(session)
        await asyncio.sleep(300)
