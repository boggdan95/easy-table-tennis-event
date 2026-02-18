"""Group builder with snake seeding and circle method fixtures."""

import random
from typing import Optional, Union

from ettem.models import Group, Match, MatchStatus, Pair, Player, RoundType, Set


def calculate_optimal_group_distribution(num_players: int, preferred_size: int = 4) -> list[int]:
    """Calculate optimal group sizes.

    Prefers groups of the preferred size, but will create some smaller groups
    if needed. Tries to maximize groups of preferred size.

    Args:
        num_players: Total number of players
        preferred_size: Preferred group size (3 or 4)

    Returns:
        List of group sizes (e.g., [4, 4, 3] for 11 players with preference=4)

    Examples:
        >>> calculate_optimal_group_distribution(12, 4)
        [4, 4, 4]
        >>> calculate_optimal_group_distribution(11, 4)
        [4, 4, 3]
        >>> calculate_optimal_group_distribution(10, 4)
        [4, 3, 3]
        >>> calculate_optimal_group_distribution(9, 4)
        [3, 3, 3]
    """
    if num_players < 3:
        raise ValueError(f"Cannot create groups with {num_players} players (minimum 3)")

    if preferred_size not in (3, 4, 5):
        raise ValueError(f"Preferred size must be 3, 4 or 5, got {preferred_size}")

    # Try to fit as many preferred-size groups as possible
    num_preferred_groups = num_players // preferred_size
    remainder = num_players % preferred_size

    if remainder == 0:
        # Perfect fit
        return [preferred_size] * num_preferred_groups

    if preferred_size == 5:
        if remainder == 1:
            if num_preferred_groups >= 1:
                # e.g. 6 players: [3, 3] or 11: [4, 4, 3]
                return [4] * (num_preferred_groups - 1) + [3, 3] if num_preferred_groups >= 2 else [3, 3]
            else:
                raise ValueError(f"Cannot distribute {num_players} players into valid groups")
        elif remainder == 2:
            if num_preferred_groups >= 1:
                # e.g. 7: [4, 3], 12: [5, 4, 3]
                return [5] * (num_preferred_groups - 1) + [4, 3] if num_preferred_groups >= 2 else [4, 3]
            else:
                raise ValueError(f"Cannot distribute {num_players} players into valid groups")
        elif remainder == 3:
            # Add one group of 3: e.g. 8: [5, 3]
            return [5] * num_preferred_groups + [3]
        elif remainder == 4:
            # Add one group of 4: e.g. 9: [5, 4]
            return [5] * num_preferred_groups + [4]
    elif preferred_size == 4:
        if remainder == 1:
            if num_preferred_groups >= 2:
                # Convert two 4s into three 3s: e.g. 9 players -> [3, 3, 3]
                return [3] * (num_preferred_groups + 1)
            elif num_preferred_groups == 1:
                # 5 players: single group of 5
                return [num_players]
            else:
                raise ValueError(f"Cannot distribute {num_players} players into valid groups")
        elif remainder == 2:
            # Take 2 players -> one group of 3 and one group of 4 OR two groups of 3
            # Prefer more groups of 4
            return [4] * (num_preferred_groups - 1) + [3, 3]
        elif remainder == 3:
            # Perfect! Add one group of 3
            return [4] * num_preferred_groups + [3]
    else:  # preferred_size == 3
        if remainder == 1:
            # Can't have group of 1, so make one group of 4
            if num_preferred_groups > 0:
                return [3] * (num_preferred_groups - 1) + [4]
            else:
                raise ValueError(f"Cannot distribute {num_players} players into valid groups")
        elif remainder == 2:
            # Need to absorb 2 extra players by upgrading 3s to 4s
            if num_preferred_groups >= 2:
                # Upgrade two 3s to 4s: e.g. 8 players -> [4, 4]
                return [3] * (num_preferred_groups - 2) + [4, 4]
            elif num_preferred_groups == 1:
                # 5 players: single group of 5
                return [num_players]
            else:
                raise ValueError(f"Cannot distribute {num_players} players into valid groups")

    # Fallback (shouldn't reach here)
    raise ValueError(f"Cannot distribute {num_players} players into valid groups")


def distribute_seeds_snake(
    players: Union[list[Player], list[Pair]], num_groups: int
) -> Union[list[list[Player]], list[list[Pair]]]:
    """Distribute seeded competitors into groups using snake/serpentine method.

    Seeds flow in a snake pattern:
    - Group A: 1, 8, 9, 16
    - Group B: 2, 7, 10, 15
    - Group C: 3, 6, 11, 14
    - Group D: 4, 5, 12, 13

    Args:
        players: List of Player or Pair objects sorted by seed (1 = best)
        num_groups: Number of groups to create

    Returns:
        List of lists, each containing competitors for one group
    """
    if not players:
        raise ValueError("Cannot distribute empty player list")

    if num_groups < 1:
        raise ValueError(f"Number of groups must be at least 1, got {num_groups}")

    # Initialize empty groups
    groups = [[] for _ in range(num_groups)]

    # Snake distribution
    for idx, player in enumerate(players):
        # Determine which "row" we're in (0-indexed)
        row = idx // num_groups
        # Determine column (which group)
        col = idx % num_groups

        # On even rows, go left-to-right; on odd rows, go right-to-left (snake)
        if row % 2 == 0:
            group_idx = col
        else:
            group_idx = num_groups - 1 - col

        groups[group_idx].append(player)

    return groups


def generate_round_robin_fixtures(group_size: int) -> list[tuple[int, int]]:
    """Generate round robin fixtures using Order A (strategic order).

    Order A ensures the crucial match for 2nd place (2 vs 3) is played last.

    For 4 players:
        Round 1: (1,3), (2,4)
        Round 2: (1,2), (3,4)
        Round 3: (1,4), (2,3) <- Decides 2nd place

    For 3 players:
        Round 1: (1,3)
        Round 2: (1,2)
        Round 3: (2,3) <- Decides 2nd place

    Args:
        group_size: Number of players in the group (3 or 4)

    Returns:
        List of (player_num1, player_num2) tuples (1-indexed)
        Ordered by round priority
    """
    if group_size < 3:
        raise ValueError(f"Group size must be at least 3, got {group_size}")

    if group_size == 4:
        # Order A for 4 players
        # Round 1: Best vs 3rd, 2nd vs 4th
        # Round 2: Best vs 2nd, 3rd vs 4th
        # Round 3: Best vs 4th, 2nd vs 3rd (crucial match)
        return [
            (1, 3),  # Round 1
            (2, 4),
            (1, 2),  # Round 2
            (3, 4),
            (1, 4),  # Round 3
            (2, 3),  # <- Most important match for 2nd place
        ]
    elif group_size == 3:
        # Order A for 3 players
        # Round 1: Best vs 3rd
        # Round 2: Best vs 2nd
        # Round 3: 2nd vs 3rd (crucial match)
        return [
            (1, 3),  # Round 1
            (1, 2),  # Round 2
            (2, 3),  # Round 3 <- Most important match for 2nd place
        ]
    elif group_size == 5:
        # Order A for 5 players (Berger table)
        # No player plays two consecutive matches.
        # 1 vs 2 (crucial match) is the very last match.
        # Player gaps: 1→{1,4,7,10} 2→{2,5,8,10} 3→{3,5,7,9} 4→{1,3,6,8} 5→{2,4,6,9}
        return [
            (1, 4),  # Round 1
            (2, 5),
            (3, 4),  # Round 2
            (1, 5),
            (2, 3),  # Round 3
            (4, 5),
            (1, 3),  # Round 4
            (2, 4),
            (3, 5),  # Round 5
            (1, 2),  # <- Most important match last
        ]
    else:
        # For other sizes, fall back to standard round-robin
        matches = []
        for i in range(1, group_size + 1):
            for j in range(i + 1, group_size + 1):
                matches.append((i, j))
        return matches


def create_groups(
    players: Union[list[Player], list[Pair]],
    category: str,
    group_size_preference: int = 4,
    random_seed: Optional[int] = None,
    event_type: str = "singles",
) -> tuple[list[Group], list[Match]]:
    """Create groups with snake seeding and generate fixtures.

    Works with both Player (singles) and Pair (doubles) objects.
    Both have .id, .seed, .full_name, .group_number attributes.

    Args:
        players: List of seeded competitors (Player or Pair, must have seed set)
        category: Category name (e.g., 'U13', 'MD')
        group_size_preference: Preferred group size (3 or 4)
        random_seed: Optional random seed for determinism
        event_type: 'singles' or 'doubles'

    Returns:
        Tuple of (groups, matches) where:
        - groups: List of Group objects (player_ids contains entity IDs)
        - matches: List of Match objects (player1_id/player2_id contain entity IDs)
    """
    if not players:
        raise ValueError("Cannot create groups with empty player list")

    # Validate all competitors have seeds
    for player in players:
        if player.seed is None:
            raise ValueError(f"Player {player.full_name} does not have a seed assigned")

    # Sort by seed (should already be sorted, but be defensive)
    sorted_players = sorted(players, key=lambda p: p.seed)

    # Calculate group distribution
    group_sizes = calculate_optimal_group_distribution(len(players), group_size_preference)
    num_groups = len(group_sizes)

    # Distribute using snake method
    player_groups = distribute_seeds_snake(sorted_players, num_groups)

    # Create Group objects
    groups = []

    for group_idx, player_list in enumerate(player_groups, start=1):
        # Assign group numbers (1-indexed within group)
        for pos, player in enumerate(player_list, start=1):
            player.group_number = pos

        group = Group(
            id=0,  # Will be set by database
            name=str(group_idx),
            category=category,
            player_ids=[p.id for p in player_list],
        )
        groups.append(group)

    # Generate fixtures for all groups
    all_matches = []
    match_counter = 1

    for group_idx, (group, player_list) in enumerate(zip(groups, player_groups)):
        # Get fixtures for this group size
        fixtures = generate_round_robin_fixtures(len(player_list))

        # Create Match objects
        for fixture_idx, (p1_num, p2_num) in enumerate(fixtures, start=1):
            # Map group numbers to competitor IDs
            competitor1 = player_list[p1_num - 1]
            competitor2 = player_list[p2_num - 1]

            match = Match(
                id=0,  # Will be set by database
                player1_id=competitor1.id,
                player2_id=competitor2.id,
                group_id=0,  # Will be set when group is saved to DB
                round_type=RoundType.ROUND_ROBIN,
                round_name=f"Group {group.name} Match {fixture_idx}",
                match_number=match_counter,
                status=MatchStatus.PENDING,
                sets=[],
            )
            all_matches.append(match)
            match_counter += 1

    return groups, all_matches
