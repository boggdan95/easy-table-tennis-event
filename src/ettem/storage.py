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
    """Player table.

    Stores player information with multiple ID/number schemes:
    - id: Database primary key (auto-generated)
    - original_id: ID from import source (CSV)
    - tournament_number: Assigned bib/player number for event
    - group_number: Number within group (1-4)
    - seed: Ranking seed (1 = best)
    """

    __tablename__ = "players"

    # Primary identifier
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic info
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    genero = Column(String(1), nullable=False)  # M or F
    pais_cd = Column(String(3), nullable=False)  # ISO-3
    ranking_pts = Column(Float, nullable=False)
    categoria = Column(String(20), nullable=False)

    # Tournament-assigned identifiers
    seed = Column(Integer, nullable=True)  # 1 = best player
    original_id = Column(Integer, nullable=True)  # From CSV import
    tournament_number = Column(Integer, nullable=True)  # Event bib number
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group_number = Column(Integer, nullable=True)  # 1-4 within group

    # Metadata
    checked_in = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    group = relationship("GroupORM", foreign_keys=[group_id])
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

    def create(self, player: "Player") -> PlayerORM:
        """Create a new player in the database.

        Args:
            player: Player domain model

        Returns:
            Created PlayerORM instance with auto-generated ID
        """
        from ettem.models import Player

        player_orm = PlayerORM(
            nombre=player.nombre,
            apellido=player.apellido,
            genero=player.genero.value if hasattr(player.genero, "value") else player.genero,
            pais_cd=player.pais_cd,
            ranking_pts=player.ranking_pts,
            categoria=player.categoria,
            seed=player.seed,
            original_id=player.original_id,
            tournament_number=player.tournament_number,
            group_id=player.group_id,
            group_number=player.group_number,
            checked_in=player.checked_in,
            notes=player.notes,
        )
        self.session.add(player_orm)
        self.session.commit()
        self.session.refresh(player_orm)
        return player_orm

    def get_by_id(self, player_id: int) -> Optional[PlayerORM]:
        """Get player by database ID.

        Args:
            player_id: Internal database ID

        Returns:
            PlayerORM if found, None otherwise
        """
        return self.session.query(PlayerORM).filter(PlayerORM.id == player_id).first()

    def get_by_tournament_number(self, tournament_number: int) -> Optional[PlayerORM]:
        """Get player by tournament number (bib number).

        Args:
            tournament_number: Tournament bib/player number

        Returns:
            PlayerORM if found, None otherwise
        """
        return (
            self.session.query(PlayerORM)
            .filter(PlayerORM.tournament_number == tournament_number)
            .first()
        )

    def get_by_category(self, category: str) -> list[PlayerORM]:
        """Get all players in a category.

        Args:
            category: Category name (e.g., 'U13', 'U15')

        Returns:
            List of PlayerORM instances
        """
        return self.session.query(PlayerORM).filter(PlayerORM.categoria == category).all()

    def get_by_category_sorted_by_seed(self, category: str) -> list[PlayerORM]:
        """Get players in a category sorted by seed.

        Args:
            category: Category name

        Returns:
            List of PlayerORM instances sorted by seed (1 first)
        """
        return (
            self.session.query(PlayerORM)
            .filter(PlayerORM.categoria == category)
            .filter(PlayerORM.seed.isnot(None))
            .order_by(PlayerORM.seed)
            .all()
        )

    def get_all(self) -> list[PlayerORM]:
        """Get all players."""
        return self.session.query(PlayerORM).all()

    def update(self, player_orm: PlayerORM) -> PlayerORM:
        """Update an existing player.

        Args:
            player_orm: PlayerORM instance to update

        Returns:
            Updated PlayerORM instance
        """
        self.session.commit()
        self.session.refresh(player_orm)
        return player_orm

    def delete(self, player_id: int) -> bool:
        """Delete a player by ID.

        Args:
            player_id: Database ID of player to delete

        Returns:
            True if deleted, False if not found
        """
        player = self.get_by_id(player_id)
        if player:
            self.session.delete(player)
            self.session.commit()
            return True
        return False

    def assign_seeds(self, category: str) -> None:
        """Assign seeds to players in a category based on ranking_pts.

        Args:
            category: Category to assign seeds for
        """
        players = (
            self.session.query(PlayerORM)
            .filter(PlayerORM.categoria == category)
            .order_by(PlayerORM.ranking_pts.desc())  # Higher ranking = better seed
            .all()
        )
        for idx, player in enumerate(players, start=1):
            player.seed = idx
        self.session.commit()


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
