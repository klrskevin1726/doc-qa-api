import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import ConfigurationError


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ConfigurationError("DATABASE_URL is not configured.")
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    if not database_url.startswith("postgresql+psycopg2://"):
        raise ConfigurationError(
            "DATABASE_URL must use PostgreSQL with the psycopg2 driver."
        )
    return database_url


DATABASE_URL = get_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()