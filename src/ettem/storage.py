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
from sqlalchemy.pool import NullPool

from ettem.models import Gender, MatchStatus, RoundType

Base = declarative_base()


# ============================================================================
# ORM Models
# ============================================================================


class TournamentORM(Base):
    """Tournament table.

    Represents a tournament/event that contains categories, players, groups, etc.
    """

    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active, completed, archived
    is_current = Column(Boolean, nullable=False, default=False)  # Only one tournament can be current
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Scheduler configuration
    num_tables = Column(Integer, nullable=True, default=4)  # Number of tables available
    default_match_duration = Column(Integer, nullable=True, default=20)  # Minutes per match
    min_rest_time = Column(Integer, nullable=True, default=10)  # Minimum rest between matches (minutes)

    # Relationships
    players = relationship("PlayerORM", back_populates="tournament")
    groups = relationship("GroupORM", back_populates="tournament")
    sessions = relationship("SessionORM", back_populates="tournament")


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
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)

    # Metadata
    checked_in = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM", back_populates="players")
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
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    # Store player_ids as JSON array
    player_ids_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM", back_populates="groups")
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
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Allow None for BYE or empty slot
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Allow None for BYE or empty slot
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)  # For filtering by tournament
    category = Column(String(20), nullable=True)  # Category for bracket matches (SUB21, OPEN, etc.)
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
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    slot_number = Column(Integer, nullable=False)
    round_type = Column(String(10), nullable=False)  # R32, R16, QF, SF, F
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    is_bye = Column(Boolean, nullable=False, default=False)
    same_country_warning = Column(Boolean, nullable=False, default=False)
    advanced_by_bye = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    player = relationship("PlayerORM")


class SessionORM(Base):
    """Tournament session/day table.

    Represents a time block for scheduling matches (e.g., "Saturday Morning", "Sunday Afternoon").
    """

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., "Sábado Mañana", "Domingo Tarde"
    date = Column(DateTime, nullable=False)  # Date of the session
    start_time = Column(String(5), nullable=False)  # HH:MM format
    end_time = Column(String(5), nullable=False)  # HH:MM format
    order = Column(Integer, nullable=False, default=0)  # For sorting sessions
    is_finalized = Column(Integer, nullable=False, default=0)  # 0 = draft, 1 = finalized
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM", back_populates="sessions")
    schedule_slots = relationship("ScheduleSlotORM", back_populates="session")
    time_slots = relationship("TimeSlotORM", back_populates="session", order_by="TimeSlotORM.slot_number")


class TimeSlotORM(Base):
    """Time slot table.

    Represents a time block within a session with configurable duration.
    When duration changes, subsequent slots recalculate their start times.
    """

    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    slot_number = Column(Integer, nullable=False)  # 0, 1, 2, ... (order within session)
    start_time = Column(String(5), nullable=False)  # HH:MM format (calculated)
    duration_minutes = Column(Integer, nullable=False)  # Duration in minutes
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("SessionORM", back_populates="time_slots")

    __table_args__ = (
        # Unique constraint: one slot number per session
        {"sqlite_autoincrement": True},
    )


class ScheduleSlotORM(Base):
    """Schedule slot table.

    Represents a match assigned to a specific table and time slot.
    """

    __tablename__ = "schedule_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    table_number = Column(Integer, nullable=False)  # 1, 2, 3, ...
    start_time = Column(String(5), nullable=False)  # HH:MM format
    duration = Column(Integer, nullable=True)  # Override duration in minutes (null = use default)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("SessionORM", back_populates="schedule_slots")
    match = relationship("MatchORM")


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

        # Use NullPool for SQLite to avoid connection pool issues
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            poolclass=NullPool,
            connect_args={"check_same_thread": False}
        )
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


class TournamentRepository:
    """Repository for Tournament operations."""

    def __init__(self, session):
        self.session = session

    def create(self, name: str, date=None, location: str = None) -> TournamentORM:
        """Create a new tournament."""
        tournament = TournamentORM(
            name=name,
            date=date,
            location=location,
            status="active",
            is_current=False
        )
        self.session.add(tournament)
        self.session.commit()
        return tournament

    def get_all(self) -> list[TournamentORM]:
        """Get all tournaments ordered by date (newest first)."""
        return self.session.query(TournamentORM).order_by(
            TournamentORM.created_at.desc()
        ).all()

    def get_by_id(self, tournament_id: int) -> Optional[TournamentORM]:
        """Get tournament by ID."""
        return self.session.query(TournamentORM).filter(
            TournamentORM.id == tournament_id
        ).first()

    def get_current(self) -> Optional[TournamentORM]:
        """Get the current active tournament."""
        return self.session.query(TournamentORM).filter(
            TournamentORM.is_current == True
        ).first()

    def set_current(self, tournament_id: int) -> bool:
        """Set a tournament as the current one (only one can be current)."""
        # First, unset all tournaments as current
        self.session.query(TournamentORM).update({"is_current": False})
        # Set the specified tournament as current
        result = self.session.query(TournamentORM).filter(
            TournamentORM.id == tournament_id
        ).update({"is_current": True})
        self.session.commit()
        return result > 0

    def update_status(self, tournament_id: int, status: str) -> bool:
        """Update tournament status (active, completed, archived)."""
        result = self.session.query(TournamentORM).filter(
            TournamentORM.id == tournament_id
        ).update({"status": status})
        self.session.commit()
        return result > 0

    def delete(self, tournament_id: int) -> bool:
        """Delete a tournament and all its data."""
        tournament = self.get_by_id(tournament_id)
        if tournament:
            self.session.delete(tournament)
            self.session.commit()
            return True
        return False

    def get_active(self) -> list[TournamentORM]:
        """Get all active tournaments."""
        return self.session.query(TournamentORM).filter(
            TournamentORM.status == "active"
        ).order_by(TournamentORM.created_at.desc()).all()

    def get_archived(self) -> list[TournamentORM]:
        """Get all archived tournaments."""
        return self.session.query(TournamentORM).filter(
            TournamentORM.status == "archived"
        ).order_by(TournamentORM.created_at.desc()).all()


class PlayerRepository:
    """Repository for Player operations."""

    def __init__(self, session):
        self.session = session

    def create(self, player: "Player", tournament_id: int = None) -> PlayerORM:
        """Create a new player in the database.

        Args:
            player: Player domain model
            tournament_id: ID of the tournament this player belongs to

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
            tournament_id=tournament_id,
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

    def get_by_category(self, category: str, tournament_id: int = None) -> list[PlayerORM]:
        """Get all players in a category.

        Args:
            category: Category name (e.g., 'U13', 'U15')
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of PlayerORM instances
        """
        query = self.session.query(PlayerORM).filter(PlayerORM.categoria == category)
        if tournament_id is not None:
            query = query.filter(PlayerORM.tournament_id == tournament_id)
        return query.all()

    def get_by_category_sorted_by_seed(self, category: str, tournament_id: int = None) -> list[PlayerORM]:
        """Get players in a category sorted by seed.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of PlayerORM instances sorted by seed (1 first)
        """
        query = (
            self.session.query(PlayerORM)
            .filter(PlayerORM.categoria == category)
            .filter(PlayerORM.seed.isnot(None))
        )
        if tournament_id is not None:
            query = query.filter(PlayerORM.tournament_id == tournament_id)
        return query.order_by(PlayerORM.seed).all()

    def get_all(self, tournament_id: int = None) -> list[PlayerORM]:
        """Get all players, optionally filtered by tournament.

        Args:
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of PlayerORM instances
        """
        query = self.session.query(PlayerORM)
        if tournament_id is not None:
            query = query.filter(PlayerORM.tournament_id == tournament_id)
        return query.all()

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

    def create(self, group: "Group", tournament_id: int = None) -> GroupORM:
        """Create a new group in the database.

        Args:
            group: Group domain model
            tournament_id: ID of the tournament this group belongs to

        Returns:
            Created GroupORM instance
        """
        from ettem.models import Group

        group_orm = GroupORM(
            name=group.name,
            category=group.category,
            player_ids_json=json.dumps(group.player_ids),
            tournament_id=tournament_id,
        )
        self.session.add(group_orm)
        self.session.commit()
        self.session.refresh(group_orm)
        return group_orm

    def get_by_id(self, group_id: int) -> Optional[GroupORM]:
        """Get group by ID.

        Args:
            group_id: Database ID

        Returns:
            GroupORM if found, None otherwise
        """
        return self.session.query(GroupORM).filter(GroupORM.id == group_id).first()

    def get_by_category(self, category: str, tournament_id: int = None) -> list[GroupORM]:
        """Get all groups in a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of GroupORM instances
        """
        query = self.session.query(GroupORM).filter(GroupORM.category == category)
        if tournament_id is not None:
            query = query.filter(GroupORM.tournament_id == tournament_id)
        return query.all()

    def get_all(self, tournament_id: int = None) -> list[GroupORM]:
        """Get all groups, optionally filtered by tournament.

        Args:
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of GroupORM instances
        """
        query = self.session.query(GroupORM)
        if tournament_id is not None:
            query = query.filter(GroupORM.tournament_id == tournament_id)
        return query.all()

    def update(self, group_orm: GroupORM) -> GroupORM:
        """Update an existing group.

        Args:
            group_orm: GroupORM instance to update

        Returns:
            Updated GroupORM instance
        """
        self.session.commit()
        self.session.refresh(group_orm)
        return group_orm

    def delete(self, group_id: int) -> bool:
        """Delete a group by ID.

        Args:
            group_id: Database ID

        Returns:
            True if deleted, False if not found
        """
        group = self.get_by_id(group_id)
        if group:
            self.session.delete(group)
            self.session.commit()
            return True
        return False

    def delete_by_category(self, category: str, tournament_id: int = None) -> int:
        """Delete all groups for a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            Number of groups deleted
        """
        query = self.session.query(GroupORM).filter(GroupORM.category == category)
        if tournament_id is not None:
            query = query.filter(GroupORM.tournament_id == tournament_id)
        count = query.delete()
        self.session.commit()
        return count


class MatchRepository:
    """Repository for Match operations."""

    def __init__(self, session):
        self.session = session

    def create(self, match: "Match", category: str = None, tournament_id: int = None) -> MatchORM:
        """Create a new match in the database.

        Args:
            match: Match domain model
            category: Category name for bracket matches (optional)
            tournament_id: Tournament ID for filtering (optional)

        Returns:
            Created MatchORM instance
        """
        from ettem.models import Match

        # Convert sets to JSON format
        sets_data = [
            {
                "set_number": s.set_number,
                "player1_points": s.player1_points,
                "player2_points": s.player2_points,
            }
            for s in match.sets
        ]

        match_orm = MatchORM(
            player1_id=match.player1_id,
            player2_id=match.player2_id,
            group_id=match.group_id,
            tournament_id=tournament_id,
            category=category,
            round_type=match.round_type.value if hasattr(match.round_type, "value") else match.round_type,
            round_name=match.round_name,
            match_number=match.match_number,
            status=match.status.value if hasattr(match.status, "value") else match.status,
            sets_json=json.dumps(sets_data),
            winner_id=match.winner_id,
            scheduled_time=match.scheduled_time,
            table_number=match.table_number,
        )
        self.session.add(match_orm)
        self.session.commit()
        self.session.refresh(match_orm)
        return match_orm

    def get_by_id(self, match_id: int) -> Optional[MatchORM]:
        """Get match by ID.

        Args:
            match_id: Database ID

        Returns:
            MatchORM if found, None otherwise
        """
        return self.session.query(MatchORM).filter(MatchORM.id == match_id).first()

    def get_by_group(self, group_id: int) -> list[MatchORM]:
        """Get all matches in a group.

        Args:
            group_id: Group ID

        Returns:
            List of MatchORM instances
        """
        return self.session.query(MatchORM).filter(MatchORM.group_id == group_id).all()

    def get_by_round(self, round_type: str) -> list[MatchORM]:
        """Get all matches in a round.

        Args:
            round_type: Round type (RR, R16, QF, SF, F)

        Returns:
            List of MatchORM instances
        """
        return self.session.query(MatchORM).filter(MatchORM.round_type == round_type).all()

    def get_by_player(self, player_id: int) -> list[MatchORM]:
        """Get all matches for a player.

        Args:
            player_id: Player ID

        Returns:
            List of MatchORM instances
        """
        return (
            self.session.query(MatchORM)
            .filter((MatchORM.player1_id == player_id) | (MatchORM.player2_id == player_id))
            .all()
        )

    def get_all(self) -> list[MatchORM]:
        """Get all matches."""
        return self.session.query(MatchORM).all()

    def get_bracket_matches_by_category(self, category: str, tournament_id: int = None) -> list[MatchORM]:
        """Get all bracket matches for a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of MatchORM instances for bracket matches (group_id is None)
        """
        query = (
            self.session.query(MatchORM)
            .filter(MatchORM.category == category, MatchORM.group_id == None)
        )
        if tournament_id is not None:
            query = query.filter(MatchORM.tournament_id == tournament_id)
        return query.order_by(MatchORM.round_type, MatchORM.match_number).all()

    def get_bracket_match_by_round_and_number(self, category: str, round_type: str, match_number: int) -> Optional[MatchORM]:
        """Get a specific bracket match by category, round type, and match number.

        Args:
            category: Category name
            round_type: Round type (R16, QF, SF, F)
            match_number: Match number within the round

        Returns:
            MatchORM if found, None otherwise
        """
        return (
            self.session.query(MatchORM)
            .filter(
                MatchORM.category == category,
                MatchORM.group_id == None,
                MatchORM.round_type == round_type,
                MatchORM.match_number == match_number
            )
            .first()
        )

    def delete_bracket_matches_by_category(self, category: str, tournament_id: int = None) -> int:
        """Delete all bracket matches for a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            Number of matches deleted
        """
        query = (
            self.session.query(MatchORM)
            .filter(MatchORM.category == category, MatchORM.group_id == None)
        )
        if tournament_id is not None:
            query = query.filter(MatchORM.tournament_id == tournament_id)
        count = query.delete()
        self.session.commit()
        return count

    def update(self, match_orm: MatchORM) -> MatchORM:
        """Update an existing match.

        Args:
            match_orm: MatchORM instance to update

        Returns:
            Updated MatchORM instance
        """
        self.session.commit()
        self.session.refresh(match_orm)
        return match_orm

    def update_result(self, match_id: int, sets: list[dict], winner_id: int, status: str) -> MatchORM:
        """Update match result.

        Args:
            match_id: Match ID
            sets: List of set dictionaries
            winner_id: Winner player ID
            status: New match status

        Returns:
            Updated MatchORM instance
        """
        match = self.get_by_id(match_id)
        if match:
            match.sets_json = json.dumps(sets)
            match.winner_id = winner_id
            match.status = status
            self.session.commit()
            self.session.refresh(match)
        return match

    def delete(self, match_id: int) -> bool:
        """Delete a match by ID.

        Args:
            match_id: Database ID

        Returns:
            True if deleted, False if not found
        """
        match = self.get_by_id(match_id)
        if match:
            self.session.delete(match)
            self.session.commit()
            return True
        return False


class StandingRepository:
    """Repository for GroupStanding operations."""

    def __init__(self, session):
        self.session = session

    def create(self, standing: "GroupStanding") -> GroupStandingORM:
        """Create a new standing in the database.

        Args:
            standing: GroupStanding domain model

        Returns:
            Created GroupStandingORM instance
        """
        from ettem.models import GroupStanding

        standing_orm = GroupStandingORM(
            player_id=standing.player_id,
            group_id=standing.group_id,
            points_total=standing.points_total,
            wins=standing.wins,
            losses=standing.losses,
            sets_w=standing.sets_w,
            sets_l=standing.sets_l,
            points_w=standing.points_w,
            points_l=standing.points_l,
            position=standing.position,
        )
        self.session.add(standing_orm)
        self.session.commit()
        self.session.refresh(standing_orm)
        return standing_orm

    def get_by_id(self, standing_id: int) -> Optional[GroupStandingORM]:
        """Get standing by ID.

        Args:
            standing_id: Database ID

        Returns:
            GroupStandingORM if found, None otherwise
        """
        return self.session.query(GroupStandingORM).filter(GroupStandingORM.id == standing_id).first()

    def get_by_player_and_group(self, player_id: int, group_id: int) -> Optional[GroupStandingORM]:
        """Get standing for a player in a specific group.

        Args:
            player_id: Player ID
            group_id: Group ID

        Returns:
            GroupStandingORM if found, None otherwise
        """
        return (
            self.session.query(GroupStandingORM)
            .filter(GroupStandingORM.player_id == player_id, GroupStandingORM.group_id == group_id)
            .first()
        )

    def get_by_group(self, group_id: int, ordered: bool = True) -> list[GroupStandingORM]:
        """Get all standings for a group.

        Args:
            group_id: Group ID
            ordered: If True, order by position

        Returns:
            List of GroupStandingORM instances
        """
        query = self.session.query(GroupStandingORM).filter(GroupStandingORM.group_id == group_id)
        if ordered:
            query = query.order_by(GroupStandingORM.position)
        return query.all()

    def get_all(self) -> list[GroupStandingORM]:
        """Get all standings."""
        return self.session.query(GroupStandingORM).all()

    def update(self, standing_orm: GroupStandingORM) -> GroupStandingORM:
        """Update an existing standing.

        Args:
            standing_orm: GroupStandingORM instance to update

        Returns:
            Updated GroupStandingORM instance
        """
        self.session.commit()
        self.session.refresh(standing_orm)
        return standing_orm

    def delete(self, standing_id: int) -> bool:
        """Delete a standing by ID.

        Args:
            standing_id: Database ID

        Returns:
            True if deleted, False if not found
        """
        standing = self.get_by_id(standing_id)
        if standing:
            self.session.delete(standing)
            self.session.commit()
            return True
        return False

    def delete_by_group(self, group_id: int) -> int:
        """Delete all standings for a group.

        Args:
            group_id: Group ID

        Returns:
            Number of standings deleted
        """
        count = self.session.query(GroupStandingORM).filter(GroupStandingORM.group_id == group_id).delete()
        self.session.commit()
        return count


class BracketRepository:
    """Repository for Bracket operations."""

    def __init__(self, session):
        self.session = session

    def create_slot(self, slot: "BracketSlot", category: str, tournament_id: int = None) -> BracketSlotORM:
        """Create a new bracket slot in the database.

        Args:
            slot: BracketSlot domain model
            category: Category name
            tournament_id: ID of the tournament this bracket belongs to

        Returns:
            Created BracketSlotORM instance
        """
        from ettem.models import BracketSlot

        slot_orm = BracketSlotORM(
            category=category,
            slot_number=slot.slot_number,
            round_type=slot.round_type.value if hasattr(slot.round_type, "value") else slot.round_type,
            player_id=slot.player_id,
            is_bye=slot.is_bye,
            same_country_warning=slot.same_country_warning,
            tournament_id=tournament_id,
        )
        self.session.add(slot_orm)
        self.session.commit()
        self.session.refresh(slot_orm)
        return slot_orm

    def get_by_category_and_round(self, category: str, round_type: str, tournament_id: int = None) -> list[BracketSlotORM]:
        """Get all bracket slots for a category and round.

        Args:
            category: Category name
            round_type: Round type (QF, SF, F, etc.)
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of BracketSlotORM instances ordered by slot_number
        """
        query = (
            self.session.query(BracketSlotORM)
            .filter(BracketSlotORM.category == category, BracketSlotORM.round_type == round_type)
        )
        if tournament_id is not None:
            query = query.filter(BracketSlotORM.tournament_id == tournament_id)
        return query.order_by(BracketSlotORM.slot_number).all()

    def get_by_category(self, category: str, tournament_id: int = None) -> list[BracketSlotORM]:
        """Get all bracket slots for a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of BracketSlotORM instances
        """
        query = self.session.query(BracketSlotORM).filter(BracketSlotORM.category == category)
        if tournament_id is not None:
            query = query.filter(BracketSlotORM.tournament_id == tournament_id)
        return query.order_by(BracketSlotORM.round_type, BracketSlotORM.slot_number).all()

    def get_all(self, tournament_id: int = None) -> list[BracketSlotORM]:
        """Get all bracket slots, optionally filtered by tournament.

        Args:
            tournament_id: Optional tournament ID to filter by

        Returns:
            List of all BracketSlotORM instances
        """
        query = self.session.query(BracketSlotORM)
        if tournament_id is not None:
            query = query.filter(BracketSlotORM.tournament_id == tournament_id)
        return query.all()

    def delete_by_category(self, category: str, tournament_id: int = None) -> int:
        """Delete all bracket slots for a category.

        Args:
            category: Category name
            tournament_id: Optional tournament ID to filter by

        Returns:
            Number of slots deleted
        """
        query = self.session.query(BracketSlotORM).filter(BracketSlotORM.category == category)
        if tournament_id is not None:
            query = query.filter(BracketSlotORM.tournament_id == tournament_id)
        count = query.delete()
        self.session.commit()
        return count

    def update_slot_warning(self, category: str, round_type: str, slot_number: int, warning: bool):
        """Update same_country_warning flag for a specific slot.

        Args:
            category: Category name
            round_type: Round type
            slot_number: Slot number
            warning: Warning flag value
        """
        slot = (
            self.session.query(BracketSlotORM)
            .filter(
                BracketSlotORM.category == category,
                BracketSlotORM.round_type == round_type,
                BracketSlotORM.slot_number == slot_number
            )
            .first()
        )
        if slot:
            slot.same_country_warning = warning
            self.session.commit()


class SessionRepository:
    """Repository for Session (tournament day/time block) operations."""

    def __init__(self, session):
        self.session = session

    def create(self, tournament_id: int, name: str, date: datetime, start_time: str, end_time: str, order: int = 0) -> SessionORM:
        """Create a new session.

        Args:
            tournament_id: Tournament ID
            name: Session name (e.g., "Sábado Mañana")
            date: Date of the session
            start_time: Start time in HH:MM format
            end_time: End time in HH:MM format
            order: Order for sorting sessions

        Returns:
            Created SessionORM instance
        """
        session_orm = SessionORM(
            tournament_id=tournament_id,
            name=name,
            date=date,
            start_time=start_time,
            end_time=end_time,
            order=order,
        )
        self.session.add(session_orm)
        self.session.commit()
        self.session.refresh(session_orm)
        return session_orm

    def get_by_id(self, session_id: int) -> Optional[SessionORM]:
        """Get session by ID."""
        return self.session.query(SessionORM).filter(SessionORM.id == session_id).first()

    def get_by_tournament(self, tournament_id: int) -> list[SessionORM]:
        """Get all sessions for a tournament, ordered by date and order."""
        return (
            self.session.query(SessionORM)
            .filter(SessionORM.tournament_id == tournament_id)
            .order_by(SessionORM.date, SessionORM.order)
            .all()
        )

    def update(self, session_orm: SessionORM) -> SessionORM:
        """Update an existing session."""
        self.session.commit()
        self.session.refresh(session_orm)
        return session_orm

    def delete(self, session_id: int) -> bool:
        """Delete a session by ID."""
        session_obj = self.get_by_id(session_id)
        if session_obj:
            self.session.delete(session_obj)
            self.session.commit()
            return True
        return False

    def delete_by_tournament(self, tournament_id: int) -> int:
        """Delete all sessions for a tournament."""
        count = self.session.query(SessionORM).filter(SessionORM.tournament_id == tournament_id).delete()
        self.session.commit()
        return count


class ScheduleSlotRepository:
    """Repository for ScheduleSlot (match time/table assignment) operations."""

    def __init__(self, session):
        self.session = session

    def create(self, session_id: int, match_id: int, table_number: int, start_time: str, duration: int = None) -> ScheduleSlotORM:
        """Create a new schedule slot.

        Args:
            session_id: Session ID
            match_id: Match ID
            table_number: Table number (1, 2, 3, ...)
            start_time: Start time in HH:MM format
            duration: Override duration in minutes (null = use tournament default)

        Returns:
            Created ScheduleSlotORM instance
        """
        slot_orm = ScheduleSlotORM(
            session_id=session_id,
            match_id=match_id,
            table_number=table_number,
            start_time=start_time,
            duration=duration,
        )
        self.session.add(slot_orm)
        self.session.commit()
        self.session.refresh(slot_orm)
        return slot_orm

    def get_by_id(self, slot_id: int) -> Optional[ScheduleSlotORM]:
        """Get schedule slot by ID."""
        return self.session.query(ScheduleSlotORM).filter(ScheduleSlotORM.id == slot_id).first()

    def get_by_session(self, session_id: int) -> list[ScheduleSlotORM]:
        """Get all schedule slots for a session, ordered by time and table."""
        return (
            self.session.query(ScheduleSlotORM)
            .filter(ScheduleSlotORM.session_id == session_id)
            .order_by(ScheduleSlotORM.start_time, ScheduleSlotORM.table_number)
            .all()
        )

    def get_by_match(self, match_id: int) -> Optional[ScheduleSlotORM]:
        """Get schedule slot for a specific match."""
        return self.session.query(ScheduleSlotORM).filter(ScheduleSlotORM.match_id == match_id).first()

    def get_all(self) -> list[ScheduleSlotORM]:
        """Get all schedule slots."""
        return self.session.query(ScheduleSlotORM).all()

    def get_all_scheduled_match_ids(self) -> set[int]:
        """Get set of all match IDs that have been scheduled in any session."""
        slots = self.session.query(ScheduleSlotORM.match_id).all()
        return {slot.match_id for slot in slots}

    def get_by_session_and_table(self, session_id: int, table_number: int) -> list[ScheduleSlotORM]:
        """Get all schedule slots for a specific table in a session."""
        return (
            self.session.query(ScheduleSlotORM)
            .filter(ScheduleSlotORM.session_id == session_id, ScheduleSlotORM.table_number == table_number)
            .order_by(ScheduleSlotORM.start_time)
            .all()
        )

    def get_unscheduled_matches(self, tournament_id: int) -> list[MatchORM]:
        """Get all matches that don't have a schedule slot assigned.

        Args:
            tournament_id: Tournament ID to filter matches

        Returns:
            List of MatchORM instances without schedule assignments
        """
        # Get all scheduled match IDs
        scheduled_match_ids = [
            slot.match_id for slot in self.session.query(ScheduleSlotORM).all()
        ]

        # Get matches for this tournament that are not scheduled
        # Group matches: get from groups that belong to this tournament
        # Bracket matches: get by category from players in this tournament
        from sqlalchemy import or_

        query = self.session.query(MatchORM)

        if scheduled_match_ids:
            query = query.filter(~MatchORM.id.in_(scheduled_match_ids))

        return query.all()

    def update(self, slot_orm: ScheduleSlotORM) -> ScheduleSlotORM:
        """Update an existing schedule slot."""
        self.session.commit()
        self.session.refresh(slot_orm)
        return slot_orm

    def delete(self, slot_id: int) -> bool:
        """Delete a schedule slot by ID."""
        slot = self.get_by_id(slot_id)
        if slot:
            self.session.delete(slot)
            self.session.commit()
            return True
        return False

    def delete_by_session(self, session_id: int) -> int:
        """Delete all schedule slots for a session."""
        count = self.session.query(ScheduleSlotORM).filter(ScheduleSlotORM.session_id == session_id).delete()
        self.session.commit()
        return count

    def delete_by_match(self, match_id: int) -> bool:
        """Delete schedule slot for a specific match."""
        slot = self.get_by_match(match_id)
        if slot:
            self.session.delete(slot)
            self.session.commit()
            return True
        return False


class TimeSlotRepository:
    """Repository for TimeSlot (configurable time blocks) operations."""

    def __init__(self, session):
        self.session = session

    def create(self, session_id: int, slot_number: int, start_time: str, duration_minutes: int) -> TimeSlotORM:
        """Create a new time slot."""
        slot_orm = TimeSlotORM(
            session_id=session_id,
            slot_number=slot_number,
            start_time=start_time,
            duration_minutes=duration_minutes,
        )
        self.session.add(slot_orm)
        self.session.commit()
        self.session.refresh(slot_orm)
        return slot_orm

    def get_by_session(self, session_id: int) -> list[TimeSlotORM]:
        """Get all time slots for a session, ordered by slot number."""
        return (
            self.session.query(TimeSlotORM)
            .filter(TimeSlotORM.session_id == session_id)
            .order_by(TimeSlotORM.slot_number)
            .all()
        )

    def get_by_session_and_slot(self, session_id: int, slot_number: int) -> Optional[TimeSlotORM]:
        """Get a specific time slot by session and slot number."""
        return (
            self.session.query(TimeSlotORM)
            .filter(TimeSlotORM.session_id == session_id, TimeSlotORM.slot_number == slot_number)
            .first()
        )

    def get_by_session_and_time(self, session_id: int, start_time: str) -> Optional[TimeSlotORM]:
        """Get a specific time slot by session and start time."""
        return (
            self.session.query(TimeSlotORM)
            .filter(TimeSlotORM.session_id == session_id, TimeSlotORM.start_time == start_time)
            .first()
        )

    def update_duration(self, session_id: int, slot_number: int, new_duration: int) -> bool:
        """Update duration and recalculate subsequent slot start times."""
        slots = self.get_by_session(session_id)
        if not slots:
            return False

        # Find the slot to update
        target_slot = None
        for slot in slots:
            if slot.slot_number == slot_number:
                target_slot = slot
                break

        if not target_slot:
            return False

        # Update the duration
        target_slot.duration_minutes = new_duration

        # Recalculate start times for all subsequent slots
        for i, slot in enumerate(slots):
            if slot.slot_number > slot_number:
                # Calculate new start time based on previous slot
                prev_slot = slots[i - 1]
                prev_h, prev_m = map(int, prev_slot.start_time.split(":"))
                prev_minutes = prev_h * 60 + prev_m + prev_slot.duration_minutes
                new_h = prev_minutes // 60
                new_m = prev_minutes % 60
                slot.start_time = f"{new_h:02d}:{new_m:02d}"

        self.session.commit()
        return True

    def initialize_for_session(self, session_id: int, start_time: str, end_time: str, default_duration: int) -> list[TimeSlotORM]:
        """Initialize time slots for a session with default duration.

        Args:
            session_id: Session ID
            start_time: Session start time (HH:MM)
            end_time: Session end time (HH:MM)
            default_duration: Default duration in minutes

        Returns:
            List of created TimeSlotORM instances
        """
        # Delete existing time slots for this session
        self.session.query(TimeSlotORM).filter(TimeSlotORM.session_id == session_id).delete()

        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        slots = []
        current = start_minutes
        slot_number = 0

        while current < end_minutes:
            h = current // 60
            m = current % 60
            slot_time = f"{h:02d}:{m:02d}"

            slot_orm = TimeSlotORM(
                session_id=session_id,
                slot_number=slot_number,
                start_time=slot_time,
                duration_minutes=default_duration,
            )
            self.session.add(slot_orm)
            slots.append(slot_orm)

            current += default_duration
            slot_number += 1

        self.session.commit()
        return slots

    def delete_by_session(self, session_id: int) -> int:
        """Delete all time slots for a session."""
        count = self.session.query(TimeSlotORM).filter(TimeSlotORM.session_id == session_id).delete()
        self.session.commit()
        return count
