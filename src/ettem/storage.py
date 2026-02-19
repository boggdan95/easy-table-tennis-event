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
from ettem.paths import get_data_dir

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
    default_match_duration = Column(Integer, nullable=True, default=30)  # Minutes per match
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

    @property
    def full_name(self) -> str:
        """Return player's full name."""
        return f"{self.nombre} {self.apellido}"

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


class PairORM(Base):
    """Doubles pair table.

    Two players competing together in a doubles category.
    """

    __tablename__ = "pairs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    categoria = Column(String(20), nullable=False)  # MD, WD, XD, U15BD, etc.
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    ranking_pts = Column(Float, nullable=False, default=0)
    seed = Column(Integer, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group_number = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM")
    player1 = relationship("PlayerORM", foreign_keys=[player1_id])
    player2 = relationship("PlayerORM", foreign_keys=[player2_id])


class TeamORM(Base):
    """Team table for team events (MT, WT, U15BT, etc.)."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    name = Column(String(100), nullable=False)  # "Spain A", "Mexico"
    categoria = Column(String(20), nullable=False)  # MT, WT, U15BT, etc.
    pais_cd = Column(String(3), nullable=False)  # ISO-3 country code
    player_ids_json = Column(Text, nullable=False, default="[]")  # JSON [player_id, ...]
    ranking_pts = Column(Float, nullable=False, default=0)
    seed = Column(Integer, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group_number = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM")

    @property
    def player_ids(self) -> list:
        return json.loads(self.player_ids_json) if self.player_ids_json else []

    @player_ids.setter
    def player_ids(self, value: list):
        self.player_ids_json = json.dumps(value)

    @property
    def nombre(self) -> str:
        """Team name (CompetitorDisplay / template compat)."""
        return self.name

    @property
    def apellido(self) -> str:
        """Empty string (template compat)."""
        return ""


class TeamMatchDetailORM(Base):
    """Individual match within a team encounter.

    A team encounter (MatchORM with event_type='teams') contains 5-9
    individual table tennis matches. This table stores each one.
    """

    __tablename__ = "team_match_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    match_number = Column(Integer, nullable=False)  # 1-9, order per system
    match_type = Column(String(10), nullable=False, default="singles")  # "singles" or "doubles"
    label_home = Column(String(10), nullable=True)  # "A", "B", "B&C", etc.
    label_away = Column(String(10), nullable=True)  # "X", "Y", "Y&Z", etc.
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Home player
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Away player
    player1b_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Home doubles partner
    player2b_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Away doubles partner
    best_of = Column(Integer, nullable=False, default=5)
    status = Column(String(20), nullable=False, default="pending")  # pending, in_progress, completed, not_needed
    winner_side = Column(Integer, nullable=True)  # 1=home, 2=away
    sets_json = Column(Text, nullable=False, default="[]")  # Same format as MatchORM
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent_match = relationship("MatchORM")

    @property
    def sets(self) -> list:
        return json.loads(self.sets_json) if self.sets_json else []

    @sets.setter
    def sets(self, value: list):
        self.sets_json = json.dumps(value)


class GroupORM(Base):
    """Group table."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(10), nullable=False)  # A, B, C, etc.
    category = Column(String(20), nullable=False)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    event_type = Column(String(10), nullable=True, default="singles")  # singles, doubles, teams
    # Store player_ids as JSON array (for doubles: pair IDs; for teams: team IDs)
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
    event_type = Column(String(10), nullable=True, default="singles")  # singles, doubles, teams
    pair1_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)  # For doubles matches
    pair2_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)  # For doubles matches
    team1_id = Column(Integer, nullable=True)  # For team matches (FK to teams.id)
    team2_id = Column(Integer, nullable=True)  # For team matches (FK to teams.id)
    team1_score = Column(Integer, nullable=True, default=0)  # Individual match wins by team 1
    team2_score = Column(Integer, nullable=True, default=0)  # Individual match wins by team 2
    team_match_system = Column(String(20), nullable=True)  # swaythling, corbillon, olympic, bo7, bo9
    round_type = Column(String(10), nullable=False, default="RR")  # RR, R16, QF, SF, F
    round_name = Column(String(50), nullable=True)
    match_number = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    winner_id = Column(Integer, nullable=True)
    best_of = Column(Integer, nullable=False, default=5)  # Match format: 3, 5, or 7 sets
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
    pair1 = relationship("PairORM", foreign_keys=[pair1_id])
    pair2 = relationship("PairORM", foreign_keys=[pair2_id])
    group = relationship("GroupORM", back_populates="matches")

    @property
    def is_doubles(self) -> bool:
        """Check if this is a doubles match."""
        return (self.event_type or "singles") == "doubles"

    @property
    def is_teams(self) -> bool:
        """Check if this is a team match."""
        return (self.event_type or "singles") == "teams"

    @property
    def competitor1_id(self) -> Optional[int]:
        """Get competitor 1 ID (player_id for singles, pair1_id for doubles, team1_id for teams)."""
        if self.is_doubles:
            return self.pair1_id
        if self.is_teams:
            return self.team1_id
        return self.player1_id

    @property
    def competitor2_id(self) -> Optional[int]:
        """Get competitor 2 ID (player_id for singles, pair2_id for doubles, team2_id for teams)."""
        if self.is_doubles:
            return self.pair2_id
        if self.is_teams:
            return self.team2_id
        return self.player2_id

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
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)  # For doubles standings
    team_id = Column(Integer, nullable=True)  # For team standings (FK to teams.id)
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
    pair = relationship("PairORM")
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
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)  # For doubles brackets
    team_id = Column(Integer, nullable=True)  # For team brackets (FK to teams.id)
    is_bye = Column(Boolean, nullable=False, default=False)
    same_country_warning = Column(Boolean, nullable=False, default=False)
    advanced_by_bye = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    player = relationship("PlayerORM")
    pair = relationship("PairORM")


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


class TableConfigORM(Base):
    """Table configuration for referee mode.

    Each physical table can have its own configuration for how scores are entered.
    """

    __tablename__ = "table_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    table_number = Column(Integer, nullable=False)  # 1, 2, 3, ...
    name = Column(String(50), nullable=True)  # Display name (e.g., "Mesa 1", "Table A")
    mode = Column(String(20), nullable=False, default="result_per_set")  # "point_by_point" or "result_per_set"
    is_active = Column(Boolean, nullable=False, default=True)  # Is table available for use
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tournament = relationship("TournamentORM")
    lock = relationship("TableLockORM", back_populates="table", uselist=False)


class TableLockORM(Base):
    """Table lock for referee access control.

    Only one device can control a table at a time.
    """

    __tablename__ = "table_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("table_configs.id"), nullable=False, unique=True)
    session_token = Column(String(64), nullable=False)  # Unique token for the device session
    locked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow)
    device_info = Column(String(200), nullable=True)  # Optional browser/device info
    current_match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)

    # Relationships
    table = relationship("TableConfigORM", back_populates="lock")
    current_match = relationship("MatchORM")


class LiveScoreORM(Base):
    """Live score for matches in progress.

    Tracks the current state of a match being played, including point-by-point scoring.
    This allows the public display to show real-time scores.
    """

    __tablename__ = "live_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, unique=True)
    table_id = Column(Integer, ForeignKey("table_configs.id"), nullable=True)
    current_set = Column(Integer, nullable=False, default=1)  # Which set is being played (1, 2, 3...)
    player1_points = Column(Integer, nullable=False, default=0)  # Current points in this set
    player2_points = Column(Integer, nullable=False, default=0)  # Current points in this set
    player1_sets = Column(Integer, nullable=False, default=0)  # Sets won
    player2_sets = Column(Integer, nullable=False, default=0)  # Sets won
    serving_player = Column(Integer, nullable=True)  # 1 or 2 (who is serving)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    match = relationship("MatchORM")
    table = relationship("TableConfigORM")


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

    def __init__(self, db_path: str = None):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file. If None, uses get_data_dir().
        """
        if db_path is None:
            self.db_path = get_data_dir() / "ettem.sqlite"
        else:
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
        """Create a new tournament.

        Args:
            name: Tournament name
            date: Tournament date
            location: Tournament location
        """
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
            List of PlayerORM instances sorted by seed (seeded first, then by ranking_pts)
        """
        query = (
            self.session.query(PlayerORM)
            .filter(PlayerORM.categoria == category)
        )
        if tournament_id is not None:
            query = query.filter(PlayerORM.tournament_id == tournament_id)
        return query.order_by(PlayerORM.seed.asc().nullslast(), PlayerORM.ranking_pts.desc()).all()

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

    def create(self, match: "Match", category: str = None, tournament_id: int = None, best_of: int = 5, event_type: str = "singles") -> MatchORM:
        """Create a new match in the database.

        Args:
            match: Match domain model (player1_id/player2_id are competitor IDs)
            category: Category name for bracket matches (optional)
            tournament_id: Tournament ID for filtering (optional)
            best_of: Match format (3, 5, or 7 sets). Default is 5.
            event_type: 'singles' or 'doubles'. For doubles, competitor IDs
                are stored in pair1_id/pair2_id instead of player1_id/player2_id.

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

        if event_type == "doubles":
            # For doubles, store pair IDs in both player1_id/player2_id (for
            # legacy webapp code) AND pair1_id/pair2_id (for explicit queries).
            match_orm = MatchORM(
                player1_id=match.player1_id,
                player2_id=match.player2_id,
                pair1_id=match.player1_id,
                pair2_id=match.player2_id,
                event_type="doubles",
                group_id=match.group_id,
                tournament_id=tournament_id,
                category=category,
                best_of=best_of,
                round_type=match.round_type.value if hasattr(match.round_type, "value") else match.round_type,
                round_name=match.round_name,
                match_number=match.match_number,
                status=match.status.value if hasattr(match.status, "value") else match.status,
                sets_json=json.dumps(sets_data),
                winner_id=match.winner_id,
                scheduled_time=match.scheduled_time,
                table_number=match.table_number,
            )
        elif event_type == "teams":
            # For teams, store team IDs in both player1_id/player2_id (for
            # legacy webapp code) AND team1_id/team2_id (for explicit queries).
            match_orm = MatchORM(
                player1_id=match.player1_id,
                player2_id=match.player2_id,
                team1_id=match.player1_id,
                team2_id=match.player2_id,
                event_type="teams",
                group_id=match.group_id,
                tournament_id=tournament_id,
                category=category,
                best_of=best_of,
                round_type=match.round_type.value if hasattr(match.round_type, "value") else match.round_type,
                round_name=match.round_name,
                match_number=match.match_number,
                status=match.status.value if hasattr(match.status, "value") else match.status,
                sets_json=json.dumps(sets_data),
                winner_id=match.winner_id,
                scheduled_time=match.scheduled_time,
                table_number=match.table_number,
            )
        else:
            match_orm = MatchORM(
                player1_id=match.player1_id,
                player2_id=match.player2_id,
                event_type="singles",
                group_id=match.group_id,
                tournament_id=tournament_id,
                category=category,
                best_of=best_of,
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

    def get_bracket_match_by_round_and_number(self, category: str, round_type: str, match_number: int, tournament_id: int = None) -> Optional[MatchORM]:
        """Get a specific bracket match by category, round type, and match number.

        Args:
            category: Category name
            round_type: Round type (R16, QF, SF, F)
            match_number: Match number within the round
            tournament_id: Optional tournament ID to filter by

        Returns:
            MatchORM if found, None otherwise
        """
        query = (
            self.session.query(MatchORM)
            .filter(
                MatchORM.category == category,
                MatchORM.group_id == None,
                MatchORM.round_type == round_type,
                MatchORM.match_number == match_number
            )
        )
        if tournament_id is not None:
            query = query.filter(MatchORM.tournament_id == tournament_id)
        return query.first()

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


class TableConfigRepository:
    """Repository for TableConfig operations."""

    def __init__(self, session):
        self.session = session

    def create(self, tournament_id: int, table_number: int, name: str = None, mode: str = "result_per_set") -> TableConfigORM:
        """Create a new table configuration.

        Args:
            tournament_id: Tournament ID
            table_number: Table number (1, 2, 3, ...)
            name: Display name (e.g., "Mesa 1")
            mode: "point_by_point" or "result_per_set"

        Returns:
            Created TableConfigORM instance
        """
        table = TableConfigORM(
            tournament_id=tournament_id,
            table_number=table_number,
            name=name or f"Mesa {table_number}",
            mode=mode,
            is_active=True,
        )
        self.session.add(table)
        self.session.commit()
        self.session.refresh(table)
        return table

    def get_by_id(self, table_id: int) -> Optional[TableConfigORM]:
        """Get table config by ID."""
        return self.session.query(TableConfigORM).filter(TableConfigORM.id == table_id).first()

    def get_by_tournament_and_number(self, tournament_id: int, table_number: int) -> Optional[TableConfigORM]:
        """Get table config by tournament and table number."""
        return (
            self.session.query(TableConfigORM)
            .filter(TableConfigORM.tournament_id == tournament_id, TableConfigORM.table_number == table_number)
            .first()
        )

    def get_by_tournament(self, tournament_id: int, active_only: bool = False) -> list[TableConfigORM]:
        """Get all table configs for a tournament."""
        query = self.session.query(TableConfigORM).filter(TableConfigORM.tournament_id == tournament_id)
        if active_only:
            query = query.filter(TableConfigORM.is_active == True)
        return query.order_by(TableConfigORM.table_number).all()

    def update(self, table: TableConfigORM) -> TableConfigORM:
        """Update table configuration."""
        self.session.commit()
        self.session.refresh(table)
        return table

    def delete(self, table_id: int) -> bool:
        """Delete a table config."""
        table = self.get_by_id(table_id)
        if table:
            self.session.delete(table)
            self.session.commit()
            return True
        return False

    def initialize_tables(self, tournament_id: int, num_tables: int, default_mode: str = "result_per_set") -> list[TableConfigORM]:
        """Initialize table configs for a tournament.

        Args:
            tournament_id: Tournament ID
            num_tables: Number of tables to create
            default_mode: Default referee mode for all tables

        Returns:
            List of created TableConfigORM instances
        """
        # Delete existing table configs for this tournament
        self.session.query(TableConfigORM).filter(TableConfigORM.tournament_id == tournament_id).delete()
        self.session.commit()

        tables = []
        for i in range(1, num_tables + 1):
            table = self.create(tournament_id, i, f"Mesa {i}", default_mode)
            tables.append(table)

        return tables

    def sync_tables(self, tournament_id: int, num_tables: int, default_mode: str = "result_per_set") -> list[TableConfigORM]:
        """Synchronize table configs with num_tables.

        - Creates missing tables if num_tables increased
        - Deactivates extra tables if num_tables decreased (preserves config)
        - Preserves existing table modes

        Args:
            tournament_id: Tournament ID
            num_tables: Target number of active tables
            default_mode: Default mode for new tables

        Returns:
            List of active TableConfigORM instances
        """
        existing_tables = self.get_by_tournament(tournament_id)
        existing_by_number = {t.table_number: t for t in existing_tables}

        # Create missing tables
        for i in range(1, num_tables + 1):
            if i not in existing_by_number:
                table = TableConfigORM(
                    tournament_id=tournament_id,
                    table_number=i,
                    name=f"Mesa {i}",
                    mode=default_mode,
                    is_active=True,
                )
                self.session.add(table)
            else:
                # Reactivate if was deactivated
                existing_by_number[i].is_active = True

        # Deactivate tables beyond num_tables
        for table in existing_tables:
            if table.table_number > num_tables:
                table.is_active = False

        self.session.flush()

        return self.get_by_tournament(tournament_id, active_only=True)


class TableLockRepository:
    """Repository for TableLock operations."""

    def __init__(self, session):
        self.session = session

    def acquire_lock(self, table_id: int, session_token: str, device_info: str = None) -> Optional[TableLockORM]:
        """Try to acquire a lock on a table.

        Args:
            table_id: Table config ID
            session_token: Unique session token for the device
            device_info: Optional device/browser info

        Returns:
            TableLockORM if lock acquired, None if table is already locked by another session
        """
        existing = self.get_by_table(table_id)
        if existing:
            # Check if it's the same session (reconnect)
            if existing.session_token == session_token:
                existing.last_activity = datetime.utcnow()
                self.session.commit()
                return existing
            # Table is locked by another session
            return None

        lock = TableLockORM(
            table_id=table_id,
            session_token=session_token,
            device_info=device_info,
            locked_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
        )
        self.session.add(lock)
        self.session.commit()
        self.session.refresh(lock)
        return lock

    def release_lock(self, table_id: int, session_token: str = None) -> bool:
        """Release a lock on a table.

        Args:
            table_id: Table config ID
            session_token: If provided, only release if token matches (security)

        Returns:
            True if lock released, False otherwise
        """
        lock = self.get_by_table(table_id)
        if lock:
            if session_token is None or lock.session_token == session_token:
                self.session.delete(lock)
                self.session.commit()
                return True
        return False

    def force_release(self, table_id: int) -> bool:
        """Force release a lock (admin action).

        Args:
            table_id: Table config ID

        Returns:
            True if lock released, False if no lock existed
        """
        return self.release_lock(table_id, session_token=None)

    def get_by_table(self, table_id: int) -> Optional[TableLockORM]:
        """Get lock for a table."""
        return self.session.query(TableLockORM).filter(TableLockORM.table_id == table_id).first()

    def get_by_token(self, session_token: str) -> Optional[TableLockORM]:
        """Get lock by session token."""
        return self.session.query(TableLockORM).filter(TableLockORM.session_token == session_token).first()

    def update_activity(self, table_id: int, session_token: str) -> bool:
        """Update last activity timestamp for a lock.

        Args:
            table_id: Table config ID
            session_token: Session token (must match)

        Returns:
            True if updated, False if lock not found or token doesn't match
        """
        lock = self.get_by_table(table_id)
        if lock and lock.session_token == session_token:
            lock.last_activity = datetime.utcnow()
            self.session.commit()
            return True
        return False

    def set_current_match(self, table_id: int, session_token: str, match_id: int) -> bool:
        """Set the current match for a table.

        Args:
            table_id: Table config ID
            session_token: Session token (must match)
            match_id: Match ID to set as current

        Returns:
            True if updated, False if lock not found or token doesn't match
        """
        lock = self.get_by_table(table_id)
        if lock and lock.session_token == session_token:
            lock.current_match_id = match_id
            lock.last_activity = datetime.utcnow()
            self.session.commit()
            return True
        return False

    def cleanup_expired(self, timeout_minutes: int = 10) -> int:
        """Remove locks that have been inactive for too long.

        Args:
            timeout_minutes: Inactivity threshold in minutes

        Returns:
            Number of locks removed
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        count = self.session.query(TableLockORM).filter(TableLockORM.last_activity < cutoff).delete()
        self.session.commit()
        return count

    def get_all_active(self) -> list[TableLockORM]:
        """Get all active locks."""
        return self.session.query(TableLockORM).all()


class LiveScoreRepository:
    """Repository for LiveScore operations."""

    def __init__(self, session):
        self.session = session

    def create(self, match_id: int, table_id: int = None) -> LiveScoreORM:
        """Create a live score entry for a match.

        Args:
            match_id: Match ID
            table_id: Optional table config ID

        Returns:
            Created LiveScoreORM instance
        """
        live_score = LiveScoreORM(
            match_id=match_id,
            table_id=table_id,
            current_set=1,
            player1_points=0,
            player2_points=0,
            player1_sets=0,
            player2_sets=0,
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.session.add(live_score)
        self.session.commit()
        self.session.refresh(live_score)
        return live_score

    def get_by_match(self, match_id: int) -> Optional[LiveScoreORM]:
        """Get live score for a match."""
        return self.session.query(LiveScoreORM).filter(LiveScoreORM.match_id == match_id).first()

    def get_by_table(self, table_id: int) -> Optional[LiveScoreORM]:
        """Get live score for a table."""
        return self.session.query(LiveScoreORM).filter(LiveScoreORM.table_id == table_id).first()

    def get_all_active(self) -> list[LiveScoreORM]:
        """Get all active live scores."""
        return self.session.query(LiveScoreORM).all()

    def update_score(self, match_id: int, player1_points: int, player2_points: int) -> Optional[LiveScoreORM]:
        """Update current set score.

        Args:
            match_id: Match ID
            player1_points: Player 1 points in current set
            player2_points: Player 2 points in current set

        Returns:
            Updated LiveScoreORM or None if not found
        """
        live_score = self.get_by_match(match_id)
        if live_score:
            live_score.player1_points = player1_points
            live_score.player2_points = player2_points
            live_score.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(live_score)
        return live_score

    def complete_set(self, match_id: int, p1_set_score: int, p2_set_score: int) -> Optional[LiveScoreORM]:
        """Record a completed set and move to next.

        Args:
            match_id: Match ID
            p1_set_score: Player 1 final score for the set
            p2_set_score: Player 2 final score for the set

        Returns:
            Updated LiveScoreORM or None if not found
        """
        live_score = self.get_by_match(match_id)
        if live_score:
            # Update sets won
            if p1_set_score > p2_set_score:
                live_score.player1_sets += 1
            else:
                live_score.player2_sets += 1

            # Move to next set
            live_score.current_set += 1
            live_score.player1_points = 0
            live_score.player2_points = 0
            live_score.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(live_score)
        return live_score

    def delete(self, match_id: int) -> bool:
        """Delete live score entry (when match is completed).

        Args:
            match_id: Match ID

        Returns:
            True if deleted, False if not found
        """
        live_score = self.get_by_match(match_id)
        if live_score:
            self.session.delete(live_score)
            self.session.commit()
            return True
        return False

    def delete_all(self) -> int:
        """Delete all live scores."""
        count = self.session.query(LiveScoreORM).delete()
        self.session.commit()
        return count


# ============================================================================
# Pair Repository (Doubles)
# ============================================================================


class PairRepository:
    """Repository for doubles Pair operations."""

    def __init__(self, session):
        self.session = session

    def create(self, pair: "Pair", tournament_id: int = None) -> PairORM:
        """Create a new pair from a Pair domain model.

        Args:
            pair: Pair domain model
            tournament_id: Tournament ID

        Returns:
            Created PairORM instance
        """
        pair_orm = PairORM(
            tournament_id=tournament_id,
            categoria=pair.categoria,
            player1_id=pair.player1_id,
            player2_id=pair.player2_id,
            ranking_pts=pair.ranking_pts,
            seed=pair.seed,
            notes=pair.notes,
            created_at=datetime.utcnow(),
        )
        self.session.add(pair_orm)
        self.session.commit()
        self.session.refresh(pair_orm)
        return pair_orm

    def get_by_id(self, pair_id: int) -> Optional[PairORM]:
        """Get pair by ID."""
        return self.session.query(PairORM).filter(
            PairORM.id == pair_id
        ).first()

    def get_by_category(self, categoria: str, tournament_id: int = None) -> list[PairORM]:
        """Get all pairs in a category for a tournament, sorted by seed."""
        query = self.session.query(PairORM).filter(PairORM.categoria == categoria)
        if tournament_id is not None:
            query = query.filter(PairORM.tournament_id == tournament_id)
        return query.order_by(PairORM.seed.asc().nullslast(), PairORM.ranking_pts.desc()).all()

    def get_by_category_sorted_by_seed(self, categoria: str, tournament_id: int = None) -> list[PairORM]:
        """Get pairs sorted by seed (for group/bracket creation)."""
        return self.get_by_category(categoria, tournament_id)

    def get_by_tournament(self, tournament_id: int) -> list[PairORM]:
        """Get all pairs for a tournament."""
        return self.session.query(PairORM).filter(
            PairORM.tournament_id == tournament_id,
        ).order_by(PairORM.categoria, PairORM.seed.asc().nullslast()).all()

    def get_all(self, tournament_id: int = None) -> list[PairORM]:
        """Get all pairs, optionally filtered by tournament."""
        q = self.session.query(PairORM)
        if tournament_id:
            q = q.filter(PairORM.tournament_id == tournament_id)
        return q.order_by(PairORM.categoria, PairORM.seed.asc().nullslast()).all()

    def update(self, pair: PairORM) -> PairORM:
        """Update an existing pair."""
        self.session.commit()
        self.session.refresh(pair)
        return pair

    def delete(self, pair_id: int) -> bool:
        """Delete a pair."""
        pair = self.get_by_id(pair_id)
        if pair:
            self.session.delete(pair)
            self.session.commit()
            return True
        return False

    def assign_seeds(self, categoria: str, tournament_id: int = None) -> list[PairORM]:
        """Assign seeds to pairs by ranking_pts (highest = seed 1)."""
        query = self.session.query(PairORM).filter(PairORM.categoria == categoria)
        if tournament_id is not None:
            query = query.filter(PairORM.tournament_id == tournament_id)
        pairs = query.order_by(PairORM.ranking_pts.desc()).all()

        for i, pair in enumerate(pairs, 1):
            pair.seed = i
        self.session.commit()
        return pairs


class TeamRepository:
    """Repository for Team operations."""

    def __init__(self, session):
        self.session = session

    def create(self, team: "Team", tournament_id: int = None) -> TeamORM:
        """Create a new team."""
        team_orm = TeamORM(
            tournament_id=tournament_id,
            name=team.name,
            categoria=team.categoria,
            pais_cd=team.pais_cd,
            player_ids_json=json.dumps(team.player_ids),
            ranking_pts=team.ranking_pts,
            seed=team.seed,
            notes=team.notes,
            created_at=datetime.utcnow(),
        )
        self.session.add(team_orm)
        self.session.commit()
        self.session.refresh(team_orm)
        return team_orm

    def get_by_id(self, team_id: int) -> Optional[TeamORM]:
        """Get team by ID."""
        return self.session.query(TeamORM).filter(TeamORM.id == team_id).first()

    def get_by_category(self, categoria: str, tournament_id: int = None) -> list[TeamORM]:
        """Get all teams in a category, sorted by seed."""
        query = self.session.query(TeamORM).filter(TeamORM.categoria == categoria)
        if tournament_id is not None:
            query = query.filter(TeamORM.tournament_id == tournament_id)
        return query.order_by(TeamORM.seed.asc().nullslast(), TeamORM.ranking_pts.desc()).all()

    def get_by_category_sorted_by_seed(self, categoria: str, tournament_id: int = None) -> list[TeamORM]:
        """Get teams sorted by seed (for group/bracket creation)."""
        return self.get_by_category(categoria, tournament_id)

    def get_by_tournament(self, tournament_id: int) -> list[TeamORM]:
        """Get all teams for a tournament."""
        return self.session.query(TeamORM).filter(
            TeamORM.tournament_id == tournament_id,
        ).order_by(TeamORM.categoria, TeamORM.seed.asc().nullslast()).all()

    def get_all(self, tournament_id: int = None) -> list[TeamORM]:
        """Get all teams, optionally filtered by tournament."""
        q = self.session.query(TeamORM)
        if tournament_id:
            q = q.filter(TeamORM.tournament_id == tournament_id)
        return q.order_by(TeamORM.categoria, TeamORM.seed.asc().nullslast()).all()

    def update(self, team: TeamORM) -> TeamORM:
        """Update an existing team."""
        self.session.commit()
        self.session.refresh(team)
        return team

    def delete(self, team_id: int) -> bool:
        """Delete a team."""
        team = self.get_by_id(team_id)
        if team:
            self.session.delete(team)
            self.session.commit()
            return True
        return False

    def assign_seeds(self, categoria: str, tournament_id: int = None) -> list[TeamORM]:
        """Assign seeds to teams by ranking_pts (highest = seed 1)."""
        query = self.session.query(TeamORM).filter(TeamORM.categoria == categoria)
        if tournament_id is not None:
            query = query.filter(TeamORM.tournament_id == tournament_id)
        teams = query.order_by(TeamORM.ranking_pts.desc()).all()
        for i, team in enumerate(teams, 1):
            team.seed = i
        self.session.commit()
        return teams


class TeamMatchDetailRepository:
    """Repository for individual matches within team encounters."""

    def __init__(self, session):
        self.session = session

    def create(self, detail: TeamMatchDetailORM) -> TeamMatchDetailORM:
        """Create a new team match detail."""
        self.session.add(detail)
        self.session.commit()
        self.session.refresh(detail)
        return detail

    def create_bulk(self, details: list[TeamMatchDetailORM]) -> list[TeamMatchDetailORM]:
        """Create multiple team match details at once."""
        for d in details:
            self.session.add(d)
        self.session.commit()
        for d in details:
            self.session.refresh(d)
        return details

    def get_by_id(self, detail_id: int) -> Optional[TeamMatchDetailORM]:
        """Get a team match detail by ID."""
        return self.session.query(TeamMatchDetailORM).filter(
            TeamMatchDetailORM.id == detail_id
        ).first()

    def get_by_parent_match(self, parent_match_id: int) -> list[TeamMatchDetailORM]:
        """Get all individual matches for a team encounter, ordered by match_number."""
        return self.session.query(TeamMatchDetailORM).filter(
            TeamMatchDetailORM.parent_match_id == parent_match_id
        ).order_by(TeamMatchDetailORM.match_number).all()

    def update(self, detail: TeamMatchDetailORM) -> TeamMatchDetailORM:
        """Update a team match detail."""
        self.session.commit()
        self.session.refresh(detail)
        return detail

    def delete_by_parent_match(self, parent_match_id: int) -> int:
        """Delete all details for a parent match. Returns count deleted."""
        count = self.session.query(TeamMatchDetailORM).filter(
            TeamMatchDetailORM.parent_match_id == parent_match_id
        ).delete()
        self.session.commit()
        return count


# ============================================================================
# Database Migration (V2.4 Doubles)
# ============================================================================


def _safe_add_column(session, table: str, column: str, col_type: str):
    """Add a column to a table if it doesn't already exist (SQLite)."""
    from sqlalchemy import text
    try:
        session.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
    except Exception:
        session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        session.commit()


def migrate_v24_doubles(engine):
    """Run V2.4 migration: add doubles support columns and tables.

    Safe to run multiple times (idempotent).
    """
    from sqlalchemy import text, inspect

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Create pairs table if not exists
        if "pairs" not in existing_tables:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL,
                    categoria VARCHAR(20) NOT NULL,
                    player1_id INTEGER NOT NULL,
                    player2_id INTEGER NOT NULL,
                    ranking_pts REAL NOT NULL DEFAULT 0,
                    seed INTEGER,
                    group_id INTEGER,
                    group_number INTEGER,
                    notes TEXT,
                    created_at DATETIME,
                    FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                    FOREIGN KEY (player1_id) REFERENCES players(id),
                    FOREIGN KEY (player2_id) REFERENCES players(id),
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            """))
            session.commit()

        # Add nullable columns to existing tables
        _safe_add_column(session, "matches", "event_type", "VARCHAR(10) DEFAULT 'singles'")
        _safe_add_column(session, "matches", "pair1_id", "INTEGER")
        _safe_add_column(session, "matches", "pair2_id", "INTEGER")
        _safe_add_column(session, "groups", "event_type", "VARCHAR(10) DEFAULT 'singles'")
        _safe_add_column(session, "bracket_slots", "pair_id", "INTEGER")
        _safe_add_column(session, "group_standings", "pair_id", "INTEGER")

    finally:
        session.close()


# ============================================================================
# Database Migration (V2.5 Teams)
# ============================================================================


def migrate_v25_teams(engine):
    """Run V2.5 migration: add teams support columns and tables.

    Safe to run multiple times (idempotent).
    """
    from sqlalchemy import text, inspect

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Create teams table if not exists
        if "teams" not in existing_tables:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER,
                    name VARCHAR(100) NOT NULL,
                    categoria VARCHAR(20) NOT NULL,
                    pais_cd VARCHAR(3) NOT NULL,
                    player_ids_json TEXT NOT NULL DEFAULT '[]',
                    ranking_pts REAL NOT NULL DEFAULT 0,
                    seed INTEGER,
                    group_id INTEGER,
                    group_number INTEGER,
                    notes TEXT,
                    created_at DATETIME,
                    FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            """))
            session.commit()

        # Create team_match_details table if not exists
        if "team_match_details" not in existing_tables:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS team_match_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_match_id INTEGER NOT NULL,
                    match_number INTEGER NOT NULL,
                    match_type VARCHAR(10) NOT NULL DEFAULT 'singles',
                    label_home VARCHAR(10),
                    label_away VARCHAR(10),
                    player1_id INTEGER,
                    player2_id INTEGER,
                    player1b_id INTEGER,
                    player2b_id INTEGER,
                    best_of INTEGER NOT NULL DEFAULT 5,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    winner_side INTEGER,
                    sets_json TEXT NOT NULL DEFAULT '[]',
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY (parent_match_id) REFERENCES matches(id),
                    FOREIGN KEY (player1_id) REFERENCES players(id),
                    FOREIGN KEY (player2_id) REFERENCES players(id),
                    FOREIGN KEY (player1b_id) REFERENCES players(id),
                    FOREIGN KEY (player2b_id) REFERENCES players(id)
                )
            """))
            session.commit()

        # Add team columns to matches table
        _safe_add_column(session, "matches", "team1_id", "INTEGER")
        _safe_add_column(session, "matches", "team2_id", "INTEGER")
        _safe_add_column(session, "matches", "team1_score", "INTEGER DEFAULT 0")
        _safe_add_column(session, "matches", "team2_score", "INTEGER DEFAULT 0")
        _safe_add_column(session, "matches", "team_match_system", "VARCHAR(20)")

        # Add team_id to bracket_slots and group_standings
        _safe_add_column(session, "bracket_slots", "team_id", "INTEGER")
        _safe_add_column(session, "group_standings", "team_id", "INTEGER")

    finally:
        session.close()
