"""SQLite storage layer for ettem.

Provides ORM models and repository pattern for data persistence.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from ettem.models import Gender, MatchStatus, RoundType

Base = declarative_base()


# ============================================================================
# ORM Models
# ============================================================================


class PlayerORM(Base):
    """Player table."""

    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    genero = Column(String(1), nullable=False)  # M or F
    pais_cd = Column(String(3), nullable=False)  # ISO-3
    ranking_pts = Column(Float, nullable=False)
    categoria = Column(String(20), nullable=False)
    seed = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    matches_as_player1 = relationship(
        "MatchORM", back_populates="player1", foreign_keys="MatchORM.player1_id"
    )
    matches_as_player2 = relationship(
        "MatchORM", back_populates="player2", foreign_keys="MatchORM.player2_id"
    )


class GroupORM(Base):
    """Group table."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(10), nullable=False)  # A, B, C, etc.
    category = Column(String(20), nullable=False)
    # Store player_ids as JSON array
    player_ids_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    matches = relationship("MatchORM", back_populates="group")
    standings = relationship("GroupStandingORM", back_populates="group")

    @property
    def player_ids(self) -> list[int]:
        """Get player IDs from JSON."""
        return json.loads(self.player_ids_json)

    @player_ids.setter
    def player_ids(self, value: list[int]):
        """Set player IDs as JSON."""
        self.player_ids_json = json.dumps(value)


class MatchORM(Base):
    """Match table."""

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    round_type = Column(String(10), nullable=False, default="RR")  # RR, R16, QF, SF, F
    round_name = Column(String(50), nullable=True)
    match_number = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    winner_id = Column(Integer, nullable=True)
    # Store sets as JSON: [{"set_number": 1, "player1_points": 11, "player2_points": 9}, ...]
    sets_json = Column(Text, nullable=False, default="[]")
    scheduled_time = Column(DateTime, nullable=True)
    table_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    player1 = relationship(
        "PlayerORM", back_populates="matches_as_player1", foreign_keys=[player1_id]
    )
    player2 = relationship(
        "PlayerORM", back_populates="matches_as_player2", foreign_keys=[player2_id]
    )
    group = relationship("GroupORM", back_populates="matches")

    @property
    def sets(self) -> list[dict]:
        """Get sets from JSON."""
        return json.loads(self.sets_json)

    @sets.setter
    def sets(self, value: list[dict]):
        """Set sets as JSON."""
        self.sets_json = json.dumps(value)


class GroupStandingORM(Base):
    """Group standing table."""

    __tablename__ = "group_standings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    points_total = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    sets_w = Column(Integer, nullable=False, default=0)
    sets_l = Column(Integer, nullable=False, default=0)
    points_w = Column(Integer, nullable=False, default=0)
    points_l = Column(Integer, nullable=False, default=0)
    position = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    player = relationship("PlayerORM")
    group = relationship("GroupORM", back_populates="standings")


class BracketSlotORM(Base):
    """Bracket slot table."""

    __tablename__ = "bracket_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(20), nullable=False)
    slot_number = Column(Integer, nullable=False)
    round_type = Column(String(10), nullable=False)  # R32, R16, QF, SF, F
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    is_bye = Column(Boolean, nullable=False, default=False)
    same_country_warning = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    player = relationship("PlayerORM")


# ============================================================================
# Database Manager
# ============================================================================


class DatabaseManager:
    """Manages SQLite database connection and session."""

    def __init__(self, db_path: str = ".ettem/ettem.sqlite"):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all tables in the database."""
        Base.metadata.create_all(self.engine)

    def drop_tables(self):
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(self.engine)

    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()


# ============================================================================
# Repository Pattern (TODO: Implement CRUD operations)
# ============================================================================


class PlayerRepository:
    """Repository for Player operations."""

    def __init__(self, session):
        self.session = session

    # TODO: Implement:
    # - create(player: Player) -> PlayerORM
    # - get_by_id(player_id: int) -> Optional[PlayerORM]
    # - get_by_category(category: str) -> list[PlayerORM]
    # - update(player_orm: PlayerORM) -> PlayerORM
    # - delete(player_id: int) -> bool


class GroupRepository:
    """Repository for Group operations."""

    def __init__(self, session):
        self.session = session

    # TODO: Implement CRUD operations


class MatchRepository:
    """Repository for Match operations."""

    def __init__(self, session):
        self.session = session

    # TODO: Implement CRUD operations


class StandingRepository:
    """Repository for GroupStanding operations."""

    def __init__(self, session):
        self.session = session

    # TODO: Implement CRUD operations
