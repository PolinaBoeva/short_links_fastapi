from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
import uuid
from fastapi.responses import RedirectResponse
from app.database import get_async_session
from app.models import Link, User, LinkHistory
from auth import get_current_user, get_current_user_optional
from app.redis import get_cache, set_cache, delete_cache

router = APIRouter()

class ShortenLinkRequest(BaseModel):
    original_url: HttpUrl 
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None

class UpdateLinkRequest(BaseModel):
    custom_alias: Optional[str] = Field(None)
    expires_at: Optional[datetime] = Field(
        None)
    
def generate_short_code():
    return str(uuid.uuid4().hex[:8]) 

async def update_stats_cache(short_code: str, new_click_count: int, last_accessed_at: str):
    stats_key = f"stats:{short_code}"
    stats_data = {
        "click_count": new_click_count,
        "last_accessed_at": last_accessed_at,
    }
    await set_cache(stats_key, stats_data, expire=300)
    
@router.post("/links/shorten")
async def shorten_link(
    request: ShortenLinkRequest, 
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user_optional) 
):
    if request.custom_alias:
        result = await session.execute(
            select(Link).where(Link.short_code == request.custom_alias)
        )
        existing_link = result.scalars().first()

        if existing_link:
            raise HTTPException(status_code=400, detail="Custom alias is already taken")

        short_code = request.custom_alias
    else:
        short_code = generate_short_code()
        
        result = await session.execute(
            select(Link).where(Link.short_code == short_code)
        )
        existing_link = result.scalars().first()

        while existing_link:
            short_code = generate_short_code()
            result = await session.execute(
                select(Link).where(Link.short_code == short_code)
            )
            existing_link = result.scalars().first()
                
    new_link = Link(
        original_url=str(request.original_url),
        short_code=short_code,
        expires_at=request.expires_at,
        user_id=current_user.id if current_user else None, 
        custom_alias=request.custom_alias
    )

    session.add(new_link)
    await session.commit()
    
    cache_key = f"link:{short_code}"
    await set_cache(cache_key, {"original_url": new_link.original_url}, expire=60)

    return {"short_url": f"http://localhost:8000/{short_code}"}

@router.get("/{short_code}")
async def redirect_link(
    short_code: str, 
    session: AsyncSession = Depends(get_async_session),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    short_code = short_code.strip()
    cache_key = f"link:{short_code}"
    cached_link = await get_cache(cache_key)
    
    if cached_link:
        original_url = cached_link.get("original_url")
    else:
        result = await session.execute(select(Link).where(Link.short_code == short_code))
        link = result.scalars().first()

        if not link:
            raise HTTPException(status_code=404, detail="Short link not found")

        if link.expires_at and link.expires_at < datetime.utcnow():
            raise HTTPException(status_code=410, detail="Link has expired")

        original_url = link.original_url
        await set_cache(cache_key, {"original_url": original_url}, expire=60)

    result = await session.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalars().first()

    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")

    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link has expired")

    link.click_count += 1
    link.last_accessed_at = datetime.utcnow()
    await session.commit()

    background_tasks.add_task(
        update_stats_cache,
        short_code,
        link.click_count,
        link.last_accessed_at.isoformat()
    )

    return RedirectResponse(url=original_url, status_code=307)

@router.put("/links/{short_code}")
async def update_short_link(
    short_code: str,
    request: UpdateLinkRequest = Body(default={}, example={}),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalars().first()

    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")

    if link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this link")

    new_short_code = request.custom_alias if request.custom_alias is not None else generate_short_code()

    while True:
        result = await session.execute(select(Link).where(Link.short_code == new_short_code))
        existing_link = result.scalars().first()
        if not existing_link:
            break 
        new_short_code = generate_short_code()

    link.short_code = new_short_code
    link.custom_alias = request.custom_alias if request.custom_alias is not None else None
    link.updated_at = datetime.utcnow()

    if request.expires_at is not None:
        link.expires_at = request.expires_at.replace(tzinfo=None)

    await session.commit()

    return {
        "message": "Short link updated successfully",
        "new_short_url": f"http://localhost:8000/{link.short_code}",
        "original_url": link.original_url,
        "custom_alias": link.custom_alias, 
        "expires_at": link.expires_at,
    }

@router.get("/links/{short_code}/stats")
async def link_stats(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    stats_key = f"stats:{short_code}"
    cached_stats = await get_cache(stats_key)

    if cached_stats:
        stats = cached_stats
    else:
        result = await session.execute(select(Link).where(Link.short_code == short_code))
        link = result.scalars().first()

        if not link:
            raise HTTPException(status_code=404, detail="Short link not found")

        if link.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this link's stats")

        stats = {
            "original_url": link.original_url,
            "created_at": link.created_at,
            "click_count": link.click_count,
            "last_accessed_at": link.last_accessed_at,
        }
        await set_cache(stats_key, stats, expire=300)

    return stats

@router.get("/links/search")
async def search_link_by_url(
    original_url: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user) 
):
    result = await session.execute(select(Link).where(Link.original_url == original_url))
    links = result.scalars().all()

    if not links:
        raise HTTPException(status_code=404, detail="Link not found")

    user_links = [link for link in links if link.user_id == current_user.id]

    if not user_links:
        raise HTTPException(status_code=403, detail="Not authorized to search for this link")

    return [
        {
            "short_code": link.short_code,
            "original_url": link.original_url,
            "expires_at": link.expires_at,
            "created_at": link.created_at
        }
        for link in user_links
    ]

@router.delete("/links/{short_code}")
async def delete_short_link(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalars().first()

    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")

    if link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this link")

    await session.delete(link)
    await session.commit()
    
    await delete_cache(f"link:{short_code}")
    
    return {"message": "Short link deleted successfully"}


@router.get("/links/expired")
async def get_expired_links(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    result = await session.execute(
        select(LinkHistory).where(LinkHistory.user_id == current_user.id)
    )
    expired_links = result.scalars().all()

    if not expired_links:
        raise HTTPException(status_code=404, detail="No expired links found")

    return [
        {
            "short_code": link.short_code,
            "original_url": link.original_url,
            "expires_at": link.expires_at,
            "click_count": link.click_count,
            "created_at": link.created_at
        }
        for link in expired_links
    ]