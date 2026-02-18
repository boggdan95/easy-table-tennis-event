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
    def from_team(cls, team, player_repo=None) -> "CompetitorDisplay":
        """Create from a TeamORM object.

        If player_repo is provided, fetches team members for full display.
        """
        name = getattr(team, "name", f"Team {team.id}")
        pais = getattr(team, "pais_cd", "---") or "---"

        # Try to build full name with member surnames
        full = name
        if player_repo:
            player_ids = team.player_ids if hasattr(team, "player_ids") else []
            if player_ids:
                members = []
                for pid in player_ids:
                    p = player_repo.get_by_id(pid)
                    if p:
                        members.append(p.apellido)
                if members:
                    full = f"{name} ({', '.join(members)})"

        return cls(
            id=team.id,
            nombre=name,
            apellido="",
            full_name=full,
            pais_cd=pais,
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


def get_competitor_display(match_orm, side: int, player_repo, pair_repo=None, team_repo=None):
    """Get display data for side 1 or 2 of a match.

    Returns a CompetitorDisplay that works uniformly in templates.
    """
    event_type = getattr(match_orm, "event_type", "singles") or "singles"

    if event_type == "teams" and team_repo:
        team_id = match_orm.team1_id if side == 1 else match_orm.team2_id
        if team_id:
            team_orm = team_repo.get_by_id(team_id)
            if team_orm:
                return CompetitorDisplay.from_team(team_orm, player_repo=player_repo)
        return CompetitorDisplay.tbd()

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


def get_bracket_slot_display(slot_orm, category, player_repo, pair_repo=None, team_repo=None):
    """Get CompetitorDisplay for a bracket slot.

    For teams categories, uses slot.team_id.
    For doubles categories, uses slot.pair_id.
    For singles, uses slot.player_id.
    """
    from ettem.models import is_doubles_category, is_teams_category

    if slot_orm.is_bye:
        return CompetitorDisplay.bye()

    if is_teams_category(category) and team_repo:
        team_id = getattr(slot_orm, "team_id", None) or slot_orm.player_id
        if team_id:
            team_orm = team_repo.get_by_id(team_id)
            if team_orm:
                return CompetitorDisplay.from_team(team_orm, player_repo=player_repo)
        return CompetitorDisplay.tbd()

    if is_doubles_category(category) and pair_repo:
        pair_id = getattr(slot_orm, "pair_id", None) or slot_orm.player_id
        if pair_id:
            pair_orm = pair_repo.get_by_id(pair_id)
            if pair_orm:
                p1 = player_repo.get_by_id(pair_orm.player1_id)
                p2 = player_repo.get_by_id(pair_orm.player2_id)
                return CompetitorDisplay.from_pair(pair_orm, p1, p2)
        return CompetitorDisplay.tbd()

    # Singles
    if slot_orm.player_id:
        player = player_repo.get_by_id(slot_orm.player_id)
        if player:
            return CompetitorDisplay.from_player(player)
    return CompetitorDisplay.tbd()


def get_champion_display(winner_id, category, player_repo, pair_repo=None, team_repo=None):
    """Get CompetitorDisplay for a match winner.

    For teams, winner_id is a team_id.
    For doubles, winner_id is a pair_id.
    For singles, it's a player_id.
    """
    from ettem.models import is_doubles_category, is_teams_category

    if not winner_id:
        return None

    if is_teams_category(category) and team_repo:
        team_orm = team_repo.get_by_id(winner_id)
        if team_orm:
            return CompetitorDisplay.from_team(team_orm, player_repo=player_repo)

    if is_doubles_category(category) and pair_repo:
        pair_orm = pair_repo.get_by_id(winner_id)
        if pair_orm:
            p1 = player_repo.get_by_id(pair_orm.player1_id)
            p2 = player_repo.get_by_id(pair_orm.player2_id)
            return CompetitorDisplay.from_pair(pair_orm, p1, p2)

    player = player_repo.get_by_id(winner_id)
    if player:
        return CompetitorDisplay.from_player(player)
    return None
