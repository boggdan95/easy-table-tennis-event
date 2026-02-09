"""Display helpers for templates.

Provides a uniform CompetitorDisplay interface so templates can render
players, pairs, and teams using the same macros.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompetitorDisplay:
    """Uniform display object passed to templates.

    Works for singles (player), doubles (pair), and teams.
    Templates use .nombre, .apellido, .full_name, .pais_cd regardless
    of the underlying entity type.
    """

    id: int
    nombre: str
    apellido: str
    full_name: str
    pais_cd: str
    seed: Optional[int] = None
    is_pair: bool = False
    is_team: bool = False

    @classmethod
    def from_player(cls, player) -> "CompetitorDisplay":
        """Create from a Player or PlayerORM object."""
        return cls(
            id=player.id,
            nombre=player.nombre,
            apellido=player.apellido,
            full_name=f"{player.nombre} {player.apellido}",
            pais_cd=getattr(player, "pais_cd", "---"),
            seed=getattr(player, "seed", None),
        )

    @classmethod
    def from_pair(cls, pair, player1, player2) -> "CompetitorDisplay":
        """Create from a Pair with its two Player objects."""
        if player1 and player2:
            if player1.pais_cd == player2.pais_cd:
                pais = player1.pais_cd
            else:
                pais = f"{player1.pais_cd}/{player2.pais_cd}"
            return cls(
                id=pair.id,
                nombre=player1.apellido,
                apellido=f"/ {player2.apellido}",
                full_name=f"{player1.full_name} / {player2.full_name}",
                pais_cd=pais,
                seed=getattr(pair, "seed", None),
                is_pair=True,
            )
        return cls.tbd()

    @classmethod
    def from_team(cls, team) -> "CompetitorDisplay":
        """Create from a Team object."""
        return cls(
            id=team.id,
            nombre=team.name,
            apellido="",
            full_name=team.name,
            pais_cd=getattr(team, "pais_cd", "---") or "---",
            seed=getattr(team, "seed", None),
            is_team=True,
        )

    @classmethod
    def tbd(cls) -> "CompetitorDisplay":
        """Placeholder for TBD/BYE slots."""
        return cls(
            id=0, nombre="TBD", apellido="", full_name="TBD", pais_cd="---"
        )

    @classmethod
    def bye(cls) -> "CompetitorDisplay":
        """Placeholder for BYE slots."""
        return cls(
            id=0, nombre="BYE", apellido="", full_name="BYE", pais_cd="---"
        )


def get_competitor_display(match_orm, side: int, player_repo, pair_repo=None):
    """Get display data for side 1 or 2 of a match.

    Returns a CompetitorDisplay that works uniformly in templates.
    """
    event_type = getattr(match_orm, "event_type", "singles") or "singles"

    if event_type == "doubles" and pair_repo:
        pair_id = match_orm.pair1_id if side == 1 else match_orm.pair2_id
        if pair_id:
            pair_orm = pair_repo.get_by_id(pair_id)
            if pair_orm:
                p1 = player_repo.get_by_id(pair_orm.player1_id)
                p2 = player_repo.get_by_id(pair_orm.player2_id)
                return CompetitorDisplay.from_pair(pair_orm, p1, p2)
        return CompetitorDisplay.tbd()

    # Singles (default)
    player_id = match_orm.player1_id if side == 1 else match_orm.player2_id
    if player_id:
        player = player_repo.get_by_id(player_id)
        if player:
            return CompetitorDisplay.from_player(player)
    return CompetitorDisplay.tbd()
