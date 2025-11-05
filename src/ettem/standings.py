"""Standings calculator with tie-breaking rules."""

from collections import defaultdict
from typing import Optional

from ettem.models import GroupStanding, Match, MatchStatus, Player
from ettem.storage import PlayerRepository


def compute_sets_ratio(sets_w: int, sets_l: int) -> float:
    """Compute sets won/lost ratio.

    Args:
        sets_w: Sets won
        sets_l: Sets lost

    Returns:
        Ratio (infinity if sets_l == 0 and sets_w > 0, else 0.0 if both are 0)
    """
    if sets_l == 0:
        return float("inf") if sets_w > 0 else 0.0
    return sets_w / sets_l


def compute_points_ratio(points_w: int, points_l: int) -> float:
    """Compute points won/lost ratio.

    Args:
        points_w: Points won
        points_l: Points lost

    Returns:
        Ratio (infinity if points_l == 0 and points_w > 0, else 0.0 if both are 0)
    """
    if points_l == 0:
        return float("inf") if points_w > 0 else 0.0
    return points_w / points_l


def break_ties(
    tied_standings: list[GroupStanding],
    player_repo: PlayerRepository,
    matches: list[Match],
) -> list[GroupStanding]:
    """Break ties among 3+ players using head-to-head ratios.

    Tie-breaking criteria (applied ONLY among the tied players):
    1. Sets ratio (sets_w / sets_l)
    2. Points ratio (points_w / points_l)
    3. Seed (lower seed number wins)

    Args:
        tied_standings: List of GroupStanding objects with same points_total
        player_repo: PlayerRepository for fetching player data
        matches: List of matches to recalculate head-to-head stats

    Returns:
        Sorted list of GroupStanding objects (best first)
    """
    if len(tied_standings) <= 1:
        return tied_standings

    # Get player IDs of tied players
    tied_player_ids = {s.player_id for s in tied_standings}

    # Recalculate stats using ONLY matches between tied players
    head_to_head_stats = {s.player_id: {"sets_w": 0, "sets_l": 0, "points_w": 0, "points_l": 0} for s in tied_standings}

    for match in matches:
        # Only consider completed matches between tied players
        if not match.is_completed:
            continue

        if match.player1_id in tied_player_ids and match.player2_id in tied_player_ids:
            # Add sets and points for player1
            head_to_head_stats[match.player1_id]["sets_w"] += match.player1_sets_won
            head_to_head_stats[match.player1_id]["sets_l"] += match.player2_sets_won
            head_to_head_stats[match.player1_id]["points_w"] += match.player1_total_points
            head_to_head_stats[match.player1_id]["points_l"] += match.player2_total_points

            # Add sets and points for player2
            head_to_head_stats[match.player2_id]["sets_w"] += match.player2_sets_won
            head_to_head_stats[match.player2_id]["sets_l"] += match.player1_sets_won
            head_to_head_stats[match.player2_id]["points_w"] += match.player2_total_points
            head_to_head_stats[match.player2_id]["points_l"] += match.player1_total_points

    # Get seeds for final tie-breaker
    player_seeds = {}
    for standing in tied_standings:
        player = player_repo.get_by_id(standing.player_id)
        player_seeds[standing.player_id] = player.seed if player and player.seed else 999

    # Sort by: 1) sets_ratio DESC, 2) points_ratio DESC, 3) seed ASC
    def sort_key(standing: GroupStanding):
        stats = head_to_head_stats[standing.player_id]
        sets_ratio = compute_sets_ratio(stats["sets_w"], stats["sets_l"])
        points_ratio = compute_points_ratio(stats["points_w"], stats["points_l"])
        seed = player_seeds[standing.player_id]

        # DEBUG: Print tie-breaking stats
        player = player_repo.get_by_id(standing.player_id)
        player_name = f"{player.nombre} {player.apellido}" if player else "Unknown"
        print(f"[TIE-BREAK] {player_name}: sets={stats['sets_w']}-{stats['sets_l']} (ratio={sets_ratio:.2f}), points={stats['points_w']}-{stats['points_l']} (ratio={points_ratio:.2f}), seed={seed}")

        # Return tuple for sorting (negatives for DESC, positive for ASC)
        return (-sets_ratio, -points_ratio, seed)

    return sorted(tied_standings, key=sort_key)


def calculate_standings(
    matches: list[Match],
    group_id: int,
    player_repo: PlayerRepository,
) -> list[GroupStanding]:
    """Calculate standings for a group based on match results.

    Scoring:
    - Win: 2 tournament points
    - Loss (played): 1 tournament point
    - Walkover loss: 0 tournament points

    Args:
        matches: List of Match objects for the group
        group_id: Group ID
        player_repo: PlayerRepository for tie-breaking

    Returns:
        List of GroupStanding objects sorted by position (1 = best)
    """
    # Initialize standings dictionary
    standings_dict = defaultdict(
        lambda: {
            "points_total": 0,
            "wins": 0,
            "losses": 0,
            "sets_w": 0,
            "sets_l": 0,
            "points_w": 0,
            "points_l": 0,
        }
    )

    # Collect all player IDs from matches
    player_ids = set()
    for match in matches:
        if match.group_id == group_id:
            player_ids.add(match.player1_id)
            player_ids.add(match.player2_id)

    # Initialize standings for all players
    for player_id in player_ids:
        standings_dict[player_id]  # This creates the default entry

    # Process completed matches
    for match in matches:
        if match.group_id != group_id:
            continue

        if not match.is_completed:
            continue

        # Determine winner and loser
        if match.winner_id is None:
            continue  # Skip if no winner set

        winner_id = match.winner_id
        loser_id = match.player2_id if winner_id == match.player1_id else match.player1_id

        # Update tournament points
        if match.is_walkover:
            # Walkover: winner gets 2 points, loser gets 0
            standings_dict[winner_id]["points_total"] += 2
            standings_dict[winner_id]["wins"] += 1
            standings_dict[loser_id]["points_total"] += 0
            standings_dict[loser_id]["losses"] += 1
        else:
            # Normal match: winner gets 2, loser gets 1
            standings_dict[winner_id]["points_total"] += 2
            standings_dict[winner_id]["wins"] += 1
            standings_dict[loser_id]["points_total"] += 1
            standings_dict[loser_id]["losses"] += 1

        # Update sets and points
        p1_sets = match.player1_sets_won
        p2_sets = match.player2_sets_won
        p1_points = match.player1_total_points
        p2_points = match.player2_total_points

        standings_dict[match.player1_id]["sets_w"] += p1_sets
        standings_dict[match.player1_id]["sets_l"] += p2_sets
        standings_dict[match.player1_id]["points_w"] += p1_points
        standings_dict[match.player1_id]["points_l"] += p2_points

        standings_dict[match.player2_id]["sets_w"] += p2_sets
        standings_dict[match.player2_id]["sets_l"] += p1_sets
        standings_dict[match.player2_id]["points_w"] += p2_points
        standings_dict[match.player2_id]["points_l"] += p1_points

    # Convert to GroupStanding objects
    standings_list = []
    for player_id, stats in standings_dict.items():
        standing = GroupStanding(
            player_id=player_id,
            group_id=group_id,
            points_total=stats["points_total"],
            wins=stats["wins"],
            losses=stats["losses"],
            sets_w=stats["sets_w"],
            sets_l=stats["sets_l"],
            points_w=stats["points_w"],
            points_l=stats["points_l"],
        )
        standings_list.append(standing)

    # Sort by tournament points (descending)
    standings_list.sort(key=lambda s: s.points_total, reverse=True)

    # Group by tournament points to find ties
    points_groups = defaultdict(list)
    for standing in standings_list:
        points_groups[standing.points_total].append(standing)

    # Break ties for groups with 2+ players
    final_standings = []
    for points, group in sorted(points_groups.items(), reverse=True):
        if len(group) >= 2:
            # Apply tie-breaking rules using head-to-head for 2+ players
            sorted_group = break_ties(group, player_repo, matches)
            final_standings.extend(sorted_group)
        else:
            # No tie
            final_standings.extend(group)

    # Assign positions
    for position, standing in enumerate(final_standings, start=1):
        standing.position = position

    return final_standings
