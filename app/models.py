from datetime import datetime, timedelta
from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

def default_expires_at():
    return datetime.utcnow() + timedelta(days=30)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    links = relationship("Link", back_populates="user")
    link_histories = relationship(
        "LinkHistory",
        back_populates="user",
        foreign_keys="[LinkHistory.user_id]"
    )

class Link(Base):
    __tablename__ = "links"

    short_code = Column(String(10), primary_key=True, index=True)
    custom_alias = Column(String(), default=None) 
    original_url = Column(String, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.utcnow().replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.utcnow().replace(tzinfo=None), onupdate=lambda: datetime.utcnow().replace(tzinfo=None))
    last_accessed_at = Column(DateTime, nullable=True)
    click_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True, default=default_expires_at)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="links")

class LinkHistory(Base):
    __tablename__ = "link_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    short_code = Column(String(10), nullable=False) 
    original_url = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    click_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="link_histories")