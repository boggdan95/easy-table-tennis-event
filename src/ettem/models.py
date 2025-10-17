"""Data models for ettem.

Domain model hierarchy:
- Tournament contains Categories
- Category contains Groups (round robin) and Bracket (knockout)
- Group contains Players and Matches
- Match contains Sets
- Set contains the score (points)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Gender(str, Enum):
    """Player gender."""

    MALE = "M"
    FEMALE = "F"


class MatchStatus(str, Enum):
    """Match status."""

    PENDING = "pending"  # Not yet played
    IN_PROGRESS = "in_progress"  # Currently being played
    COMPLETED = "completed"  # Finished normally
    WALKOVER = "walkover"  # One player didn't show up


class RoundType(str, Enum):
    """Tournament round types."""

    ROUND_ROBIN = "RR"  # Group stage
    ROUND_OF_32 = "R32"
    ROUND_OF_16 = "R16"
    QUARTERFINAL = "QF"
    SEMIFINAL = "SF"
    FINAL = "F"


# ============================================================================
# Core Domain Models
# ============================================================================


@dataclass
class Player:
    """Player in the tournament.

    Represents a single participant with their registration info and seeding.
    """

    id: int
    nombre: str
    apellido: str
    genero: Gender
    pais_cd: str  # ISO-3 country code (ESP, MEX, ARG, etc.)
    ranking_pts: float
    categoria: str  # U13, U15, U18, etc.
    seed: Optional[int] = None  # Assigned after sorting by ranking

    @property
    def full_name(self) -> str:
        """Return full name."""
        return f"{self.nombre} {self.apellido}"

    def __str__(self) -> str:
        """String representation."""
        seed_str = f"[{self.seed}] " if self.seed else ""
        return f"{seed_str}{self.full_name} ({self.pais_cd})"


@dataclass
class Set:
    """A single set within a match.

    In table tennis, sets are typically played to 11 points (win by 2).
    """

    set_number: int  # 1, 2, 3, etc.
    player1_points: int
    player2_points: int

    @property
    def winner_player_num(self) -> Optional[int]:
        """Return 1 or 2 for winner, None if tied."""
        if self.player1_points > self.player2_points:
            return 1
        elif self.player2_points > self.player1_points:
            return 2
        return None

    def __str__(self) -> str:
        """String representation."""
        return f"{self.player1_points}-{self.player2_points}"


@dataclass
class Match:
    """A match between two players.

    A match consists of multiple sets. In V1, we track:
    - Which sets were played (score per set)
    - Total sets won by each player
    - Total points scored across all sets
    """

    id: int
    player1_id: int
    player2_id: int
    group_id: Optional[int] = None  # If it's a group stage match
    round_type: RoundType = RoundType.ROUND_ROBIN
    round_name: Optional[str] = None  # "Group A Match 1", "QF1", etc.
    match_number: Optional[int] = None  # Order within the round
    status: MatchStatus = MatchStatus.PENDING
    sets: list[Set] = field(default_factory=list)
    winner_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None  # V1.1 - not used in V1
    table_number: Optional[int] = None  # V1.1 - not used in V1

    @property
    def player1_sets_won(self) -> int:
        """Count sets won by player 1."""
        return sum(1 for s in self.sets if s.winner_player_num == 1)

    @property
    def player2_sets_won(self) -> int:
        """Count sets won by player 2."""
        return sum(1 for s in self.sets if s.winner_player_num == 2)

    @property
    def player1_total_points(self) -> int:
        """Total points scored by player 1 across all sets."""
        return sum(s.player1_points for s in self.sets)

    @property
    def player2_total_points(self) -> int:
        """Total points scored by player 2 across all sets."""
        return sum(s.player2_points for s in self.sets)

    @property
    def is_walkover(self) -> bool:
        """Check if this was a walkover."""
        return self.status == MatchStatus.WALKOVER

    @property
    def is_completed(self) -> bool:
        """Check if match is finished."""
        return self.status in (MatchStatus.COMPLETED, MatchStatus.WALKOVER)

    def __str__(self) -> str:
        """String representation."""
        score = f"{self.player1_sets_won}-{self.player2_sets_won}" if self.sets else "vs"
        return f"Match {self.id}: P{self.player1_id} {score} P{self.player2_id}"


# ============================================================================
# Tournament Structure Models
# ============================================================================


@dataclass
class Group:
    """A round-robin group.

    Contains 3-4 players who play against each other.
    """

    id: int
    name: str  # "A", "B", "C", etc.
    category: str  # U13, U15, etc.
    player_ids: list[int] = field(default_factory=list)
    match_ids: list[int] = field(default_factory=list)

    @property
    def size(self) -> int:
        """Number of players in group."""
        return len(self.player_ids)

    def __str__(self) -> str:
        """String representation."""
        return f"Group {self.name} ({self.size} players)"


@dataclass
class GroupStanding:
    """Standing for a player within their group.

    Tracks all metrics needed for tie-breaking.
    """

    player_id: int
    group_id: int
    # Tournament points (2 for win, 1 for loss, 0 for walkover loss)
    points_total: int = 0
    wins: int = 0
    losses: int = 0
    # Sets won/lost across all matches
    sets_w: int = 0
    sets_l: int = 0
    # Match points (game points) won/lost across all sets
    points_w: int = 0
    points_l: int = 0
    # Final position after applying tie-breaking rules
    position: Optional[int] = None

    @property
    def sets_ratio(self) -> float:
        """Sets won / sets lost (infinity if sets_l == 0)."""
        if self.sets_l == 0:
            return float("inf") if self.sets_w > 0 else 0.0
        return self.sets_w / self.sets_l

    @property
    def points_ratio(self) -> float:
        """Points won / points lost (infinity if points_l == 0)."""
        if self.points_l == 0:
            return float("inf") if self.points_w > 0 else 0.0
        return self.points_w / self.points_l

    def __str__(self) -> str:
        """String representation."""
        pos = f"#{self.position}" if self.position else "unranked"
        return f"{pos} P{self.player_id}: {self.points_total}pts {self.wins}W-{self.losses}L"


@dataclass
class BracketSlot:
    """A slot in the knockout bracket.

    Can contain a player_id or be marked as a BYE.
    """

    slot_number: int  # Position in bracket (1 = top, increasing downward)
    round_type: RoundType
    player_id: Optional[int] = None
    is_bye: bool = False
    # Annotation for same-country matches (non-blocking)
    same_country_warning: bool = False

    def __str__(self) -> str:
        """String representation."""
        if self.is_bye:
            return f"Slot {self.slot_number}: BYE"
        elif self.player_id:
            return f"Slot {self.slot_number}: P{self.player_id}"
        return f"Slot {self.slot_number}: TBD"


@dataclass
class Bracket:
    """Knockout bracket structure.

    Organizes matches by round, with strategic placement of seeds.
    """

    category: str
    # Slots organized by round
    slots: dict[RoundType, list[BracketSlot]] = field(default_factory=dict)
    # Matches organized by round
    matches: dict[RoundType, list[Match]] = field(default_factory=dict)

    def __str__(self) -> str:
        """String representation."""
        total_slots = sum(len(slots) for slots in self.slots.values())
        return f"Bracket for {self.category} ({total_slots} slots)"


# ============================================================================
# Result Models
# ============================================================================


@dataclass
class MatchResult:
    """Input model for entering match results via web panel.

    This is what gets submitted from the UI form.
    """

    match_id: int
    sets: list[tuple[int, int]]  # [(p1_score, p2_score), ...]
    is_walkover: bool = False
    winner_id: Optional[int] = None  # Required if walkover
