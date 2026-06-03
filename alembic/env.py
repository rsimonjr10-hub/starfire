import urllib.parse
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection
from alembic import context

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — ensures all models are registered

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    """Return sync psycopg2 URL with SSL disabled for Railway TCP proxy."""
    url = settings.sync_database_url
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs["sslmode"] = ["disable"]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


config.set_main_option("sqlalchemy.url", _migration_url())


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_migration_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
