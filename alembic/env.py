import os
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import sys
from config import DATABASE_URL
from app.models import Base

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DATABASE_URL = DATABASE_URL

DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в офлайн-режиме (без подключения к БД)."""
    context.configure(
        url=DATABASE_URL, 
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Запуск миграций в онлайн-режиме (с подключением к БД)."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool) 

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
