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


class EventType(str, Enum):
    """Type of event/category."""

    SINGLES = "singles"
    DOUBLES = "doubles"
    TEAMS = "teams"


def detect_event_type(category: str) -> str:
    """Detect event type from ITTF category naming convention.

    Suffixes: BS/GS/MS/WS = Singles, BD/GD/MD/WD/XD = Doubles,
              BT/GT/MT/WT = Teams.
    """
    cat = category.upper().strip()
    if cat.endswith(("BD", "GD", "MD", "WD", "XD")):
        return EventType.DOUBLES
    elif cat.endswith(("BT", "GT", "MT", "WT")):
        return EventType.TEAMS
    return EventType.SINGLES


def is_doubles_category(category: str) -> bool:
    """Check if a category is a doubles event."""
    return detect_event_type(category) == EventType.DOUBLES


def is_teams_category(category: str) -> bool:
    """Check if a category is a teams event."""
    return detect_event_type(category) == EventType.TEAMS


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
    ROUND_OF_128 = "R128"
    ROUND_OF_64 = "R64"
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

    ID Management:
    - original_id: ID from the source CSV/system (may not be unique across categories)
    - id: Internal database ID (unique, auto-generated)
    - tournament_number: Assigned number for the tournament (e.g., bib number, visible to organizers)
    - group_number: Number within their group (1-4, assigned when groups are created)
    """

    id: int  # Database primary key (auto-generated)
    nombre: str
    apellido: str
    genero: Gender
    pais_cd: str  # ISO-3 country code (ESP, MEX, ARG, etc.)
    ranking_pts: float
    categoria: str  # U13, U15, U18, etc.

    # Tournament-assigned identifiers
    seed: Optional[int] = None  # Assigned after sorting by ranking (1 = best)
    original_id: Optional[int] = None  # ID from import CSV (if any)
    tournament_number: Optional[int] = None  # Bib/player number for the event
    group_id: Optional[int] = None  # Which group they're in
    group_number: Optional[int] = None  # Number within their group (1-4)

    # Additional tournament metadata
    checked_in: bool = False  # Has player checked in at venue
    notes: Optional[str] = None  # Any special notes about the player

    @property
    def full_name(self) -> str:
        """Return full name."""
        return f"{self.nombre} {self.apellido}"

    @property
    def display_number(self) -> str:
        """Return the most relevant number for display."""
        if self.tournament_number:
            return f"#{self.tournament_number}"
        elif self.seed:
            return f"S{self.seed}"
        return f"ID{self.id}"

    def __str__(self) -> str:
        """String representation."""
        num = self.display_number
        return f"{num} {self.full_name} ({self.pais_cd})"


@dataclass
class Pair:
    """A doubles pair (two players competing together).

    Behaves like a Player for groups/brackets: has id, seed, pais_cd.
    Used for doubles categories (MD, WD, XD, U15BD, etc.).
    """

    id: int
    player1_id: int
    player2_id: int
    categoria: str
    ranking_pts: float = 0
    seed: Optional[int] = None
    group_id: Optional[int] = None
    group_number: Optional[int] = None
    notes: Optional[str] = None

    # Populated at runtime (not stored in DB)
    player1: Optional["Player"] = None
    player2: Optional["Player"] = None

    @property
    def nombre(self) -> str:
        """First part of display name (for CompetitorDisplay compat)."""
        if self.player1 and self.player2:
            return self.player1.apellido
        return f"Pair #{self.id}"

    @property
    def apellido(self) -> str:
        """Second part of display name (for CompetitorDisplay compat)."""
        if self.player1 and self.player2:
            return f"/ {self.player2.apellido}"
        return ""

    @property
    def display_name(self) -> str:
        """Short display: 'Pérez / López'."""
        if self.player1 and self.player2:
            return f"{self.player1.apellido} / {self.player2.apellido}"
        return f"Pair #{self.id}"

    @property
    def full_name(self) -> str:
        """Full display: 'Juan Pérez / Pedro López'."""
        if self.player1 and self.player2:
            return f"{self.player1.full_name} / {self.player2.full_name}"
        return f"Pair #{self.id}"

    @property
    def pais_cd(self) -> str:
        """Country code(s) for the pair."""
        if self.player1 and self.player2:
            if self.player1.pais_cd == self.player2.pais_cd:
                return self.player1.pais_cd
            return f"{self.player1.pais_cd}/{self.player2.pais_cd}"
        return "---"

    def __str__(self) -> str:
        """String representation."""
        return f"Pair {self.id}: {self.display_name}"


# ============================================================================
# Team Models (ITTF Team Events: BT/GT/MT/WT)
# ============================================================================


class TeamMatchSystem(str, Enum):
    """ITTF Team Match Systems (Handbook 2020, Section 3.7.6)."""

    SWAYTHLING = "swaythling"  # Bo5, 5 singles, 3 players
    CORBILLON = "corbillon"    # Bo5, 4S+1D, 2-4 players
    OLYMPIC = "olympic"        # Bo5, 4S+1D, 3 players
    BEST_OF_7 = "bo7"          # Bo7, 6S+1D, 3-5 players
    BEST_OF_9 = "bo9"          # Bo9, 9 singles, 3 players


# Order of play per system: (match_number, match_type, home_label, away_label)
TEAM_MATCH_ORDERS: dict[str, list[tuple[int, str, str, str]]] = {
    TeamMatchSystem.SWAYTHLING: [
        (1, "singles", "A", "X"),
        (2, "singles", "B", "Y"),
        (3, "singles", "C", "Z"),
        (4, "singles", "A", "Y"),
        (5, "singles", "B", "X"),
    ],
    TeamMatchSystem.CORBILLON: [
        (1, "singles", "A", "X"),
        (2, "singles", "B", "Y"),
        (3, "doubles", "doubles", "doubles"),
        (4, "singles", "A", "Y"),
        (5, "singles", "B", "X"),
    ],
    TeamMatchSystem.OLYMPIC: [
        (1, "doubles", "B&C", "Y&Z"),
        (2, "singles", "A", "X"),
        (3, "singles", "C", "Z"),
        (4, "singles", "A", "Y"),
        (5, "singles", "B", "X"),
    ],
    TeamMatchSystem.BEST_OF_7: [
        (1, "singles", "A", "Y"),
        (2, "singles", "B", "X"),
        (3, "singles", "C", "Z"),
        (4, "doubles", "doubles", "doubles"),
        (5, "singles", "A", "X"),
        (6, "singles", "C", "Y"),
        (7, "singles", "B", "Z"),
    ],
    TeamMatchSystem.BEST_OF_9: [
        (1, "singles", "A", "X"),
        (2, "singles", "B", "Y"),
        (3, "singles", "C", "Z"),
        (4, "singles", "B", "X"),
        (5, "singles", "A", "Z"),
        (6, "singles", "C", "Y"),
        (7, "singles", "B", "Z"),
        (8, "singles", "C", "X"),
        (9, "singles", "A", "Y"),
    ],
}


def get_team_match_best_of(system: str) -> int:
    """Return the best-of count for a team match system (how many individual matches)."""
    order = TEAM_MATCH_ORDERS.get(system, [])
    return len(order)


def get_team_match_majority(system: str) -> int:
    """Return how many individual wins needed to clinch the team match."""
    total = get_team_match_best_of(system)
    return (total // 2) + 1


@dataclass
class Team:
    """A team of players competing together in team events.

    Behaves like Player/Pair for groups/brackets: has id, seed, pais_cd.
    Used for team categories (MT, WT, U15BT, etc.).
    Teams consist of 3-5 players per ITTF rules.
    """

    id: int
    name: str  # "Spain A", "Mexico", etc.
    categoria: str  # MT, WT, U15BT, etc.
    pais_cd: str  # Primary country code (ISO-3)
    ranking_pts: float = 0
    seed: Optional[int] = None
    group_id: Optional[int] = None
    group_number: Optional[int] = None
    notes: Optional[str] = None

    # Player IDs (3-5 members)
    player_ids: list[int] = field(default_factory=list)

    # Populated at runtime (not stored in DB)
    players: list["Player"] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        """Team name (for CompetitorDisplay compat)."""
        return self.name

    @property
    def apellido(self) -> str:
        """Empty for teams (for CompetitorDisplay compat)."""
        return ""

    @property
    def display_name(self) -> str:
        """Short display name."""
        return self.name

    @property
    def full_name(self) -> str:
        """Full display: 'Spain A (Perez, Rodriguez, Lopez)'."""
        if self.players:
            members = ", ".join(p.apellido for p in self.players)
            return f"{self.name} ({members})"
        return self.name

    @property
    def member_count(self) -> int:
        """Number of team members."""
        return len(self.player_ids)

    def __str__(self) -> str:
        """String representation."""
        return f"Team {self.id}: {self.name} ({self.pais_cd})"


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
        # Handle both enum values and strings (case-insensitively)
        status_val = self.status.value if isinstance(self.status, MatchStatus) else str(self.status).lower()
        return status_val == MatchStatus.WALKOVER.value

    @property
    def is_completed(self) -> bool:
        """Check if match is finished."""
        # Handle both enum values and strings (case-insensitively)
        status_val = self.status.value if isinstance(self.status, MatchStatus) else str(self.status).lower()
        return status_val in (MatchStatus.COMPLETED.value, MatchStatus.WALKOVER.value)

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
