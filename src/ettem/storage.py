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
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Allow None for BYE or empty slot
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Allow None for BYE or empty slot
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
    advanced_by_bye = Column(Boolean, nullable=False, default=False)
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

    def create(self, group: "Group") -> GroupORM:
        """Create a new group in the database.

        Args:
            group: Group domain model

        Returns:
            Created GroupORM instance
        """
        from ettem.models import Group

        group_orm = GroupORM(
            name=group.name,
            category=group.category,
            player_ids_json=json.dumps(group.player_ids),
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

    def get_by_category(self, category: str) -> list[GroupORM]:
        """Get all groups in a category.

        Args:
            category: Category name

        Returns:
            List of GroupORM instances
        """
        return self.session.query(GroupORM).filter(GroupORM.category == category).all()

    def get_all(self) -> list[GroupORM]:
        """Get all groups."""
        return self.session.query(GroupORM).all()

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


class MatchRepository:
    """Repository for Match operations."""

    def __init__(self, session):
        self.session = session

    def create(self, match: "Match") -> MatchORM:
        """Create a new match in the database.

        Args:
            match: Match domain model

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

    def create_slot(self, slot: "BracketSlot", category: str) -> BracketSlotORM:
        """Create a new bracket slot in the database.

        Args:
            slot: BracketSlot domain model
            category: Category name

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
        )
        self.session.add(slot_orm)
        self.session.commit()
        self.session.refresh(slot_orm)
        return slot_orm

    def get_by_category_and_round(self, category: str, round_type: str) -> list[BracketSlotORM]:
        """Get all bracket slots for a category and round.

        Args:
            category: Category name
            round_type: Round type (QF, SF, F, etc.)

        Returns:
            List of BracketSlotORM instances ordered by slot_number
        """
        return (
            self.session.query(BracketSlotORM)
            .filter(BracketSlotORM.category == category, BracketSlotORM.round_type == round_type)
            .order_by(BracketSlotORM.slot_number)
            .all()
        )

    def get_by_category(self, category: str) -> list[BracketSlotORM]:
        """Get all bracket slots for a category.

        Args:
            category: Category name

        Returns:
            List of BracketSlotORM instances
        """
        return (
            self.session.query(BracketSlotORM)
            .filter(BracketSlotORM.category == category)
            .order_by(BracketSlotORM.round_type, BracketSlotORM.slot_number)
            .all()
        )

    def delete_by_category(self, category: str) -> int:
        """Delete all bracket slots for a category.

        Args:
            category: Category name

        Returns:
            Number of slots deleted
        """
        count = self.session.query(BracketSlotORM).filter(BracketSlotORM.category == category).delete()
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
