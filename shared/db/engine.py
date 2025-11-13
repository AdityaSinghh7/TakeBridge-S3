from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Ensure .env is loaded for all processes importing the engine
load_dotenv()

DB_URL = os.getenv("DB_URL", "sqlite:///./takebridge.db")  # dev default
ECHO = bool(int(os.getenv("DB_ECHO", "0")))

# SQLite needs check_same_thread=False for FastAPI multi-thread
connect_args = {}
if DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DB_URL, echo=ECHO, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

@contextmanager
def session_scope() -> Generator:
    """Transactional scope."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
