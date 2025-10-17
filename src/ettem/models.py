"""Data models for ettem."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Player:
    """Player model."""

    id: int
    nombre: str
    apellido: str
    genero: str  # M or F
    pais_cd: str  # ISO-3 country code
    ranking_pts: float
    categoria: str
    seed: Optional[int] = None


@dataclass
class Match:
    """Match model."""

    id: int
    group_id: Optional[int]
    round_name: Optional[str]  # For bracket: R16, QF, SF, F
    player1_id: int
    player2_id: int
    player1_sets: Optional[int] = None
    player2_sets: Optional[int] = None
    player1_points: Optional[int] = None
    player2_points: Optional[int] = None
    played: bool = False
    walkover: bool = False
    winner_id: Optional[int] = None


@dataclass
class Group:
    """Group model."""

    id: int
    name: str  # A, B, C, etc.
    player_ids: list[int]


@dataclass
class GroupStanding:
    """Group standing for a player."""

    player_id: int
    group_id: int
    points_total: int  # Tournament points (2 for win, 1 for loss, 0 for walkover)
    wins: int
    losses: int
    sets_w: int
    sets_l: int
    points_w: int  # Match points
    points_l: int  # Match points
    position: int  # Final position in group after tie-breaking


@dataclass
class Bracket:
    """Knockout bracket."""

    rounds: dict[str, list[Match]]  # R16, QF, SF, F -> matches


@dataclass
class Bye:
    """Bye marker for bracket."""

    slot_number: int
