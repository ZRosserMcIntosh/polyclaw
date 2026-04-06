"""SQLite data store for persisting research data and simulation results."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from polyclaw.config import config
from polyclaw.data.models import Base

logger = logging.getLogger(__name__)


class DataStore:
    """SQLite-backed data store."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.database_path
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized at %s", self.db_path)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def close(self):
        self.engine.dispose()
