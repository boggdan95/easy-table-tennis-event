"""Tests for group building."""

import pytest

from ettem.group_builder import (
    calculate_optimal_group_distribution,
    distribute_seeds_snake,
    generate_round_robin_fixtures,
    create_groups,
)
from ettem.models import Player


def test_group_size_mixing():
    """Test that groups mix sizes 3 and 4 when N doesn't divide evenly."""
    # Test with 11 players, preference 4 -> should be [4, 4, 3]
    sizes = calculate_optimal_group_distribution(11, 4)
    assert sizes == [4, 4, 3]
    assert sum(sizes) == 11

    # Test with 10 players, preference 4 -> should be [4, 3, 3]
    sizes = calculate_optimal_group_distribution(10, 4)
    assert sizes == [4, 3, 3]
    assert sum(sizes) == 10

    # Test with 9 players, preference 4 -> should be [3, 3, 3] (can't have 1 player alone)
    sizes = calculate_optimal_group_distribution(9, 4)
    assert sizes == [3, 3, 3]
    assert sum(sizes) == 9

    # Test with 12 players, preference 4 -> perfect fit [4, 4, 4]
    sizes = calculate_optimal_group_distribution(12, 4)
    assert sizes == [4, 4, 4]
    assert sum(sizes) == 12

    # Test with 7 players, preference 3 -> should be [3, 4]
    sizes = calculate_optimal_group_distribution(7, 3)
    assert sizes == [3, 4]
    assert sum(sizes) == 7

    # All groups should be size 3 or 4
    for size in sizes:
        assert size in (3, 4)


def test_snake_seeding():
    """Test that snake seeding distributes seeds correctly."""
    # Create 8 players with seeds 1-8
    players = [
        Player(id=i, nombre=f"Player{i}", apellido=f"Last{i}", genero="M",
               pais_cd="ARG", ranking_pts=100-i, categoria="U13", seed=i)
        for i in range(1, 9)
    ]

    # Distribute into 4 groups
    groups = distribute_seeds_snake(players, 4)

    # Should have 4 groups with 2 players each
    assert len(groups) == 4
    assert all(len(g) == 2 for g in groups)

    # Check snake pattern:
    # Group 0: seeds 1, 8
    # Group 1: seeds 2, 7
    # Group 2: seeds 3, 6
    # Group 3: seeds 4, 5
    assert groups[0][0].seed == 1 and groups[0][1].seed == 8
    assert groups[1][0].seed == 2 and groups[1][1].seed == 7
    assert groups[2][0].seed == 3 and groups[2][1].seed == 6
    assert groups[3][0].seed == 4 and groups[3][1].seed == 5


def test_round_robin_fixtures():
    """Test that fixtures are generated correctly with Order A."""
    # Test for 4 players (Order A)
    fixtures_4 = generate_round_robin_fixtures(4)

    # Should have 6 matches total (4 choose 2)
    assert len(fixtures_4) == 6

    # Verify Order A sequence for 4 players
    expected_4 = [
        (1, 3),  # Round 1
        (2, 4),
        (1, 2),  # Round 2
        (3, 4),
        (1, 4),  # Round 3
        (2, 3),  # Critical match for 2nd place
    ]
    assert fixtures_4 == expected_4

    # Test for 3 players (Order A)
    fixtures_3 = generate_round_robin_fixtures(3)

    # Should have 3 matches total (3 choose 2)
    assert len(fixtures_3) == 3

    # Verify Order A sequence for 3 players
    expected_3 = [
        (1, 3),  # Round 1
        (1, 2),  # Round 2
        (2, 3),  # Round 3 - Critical match for 2nd place
    ]
    assert fixtures_3 == expected_3


def test_create_groups_integration():
    """Integration test for complete group creation."""
    # Create 11 players with seeds
    players = [
        Player(id=i, nombre=f"Player{i}", apellido=f"Last{i}", genero="M",
               pais_cd="ARG", ranking_pts=100-i, categoria="U13", seed=i)
        for i in range(1, 12)
    ]

    # Create groups with preference 4
    groups, matches = create_groups(players, "U13", group_size_preference=4)

    # Should create 3 groups (sizes: 4, 4, 3)
    assert len(groups) == 3
    group_sizes = [len(g.player_ids) for g in groups]
    assert sorted(group_sizes, reverse=True) == [4, 4, 3]

    # Verify all players are assigned
    all_player_ids = []
    for g in groups:
        all_player_ids.extend(g.player_ids)
    assert len(all_player_ids) == 11
    assert len(set(all_player_ids)) == 11  # No duplicates

    # Verify matches count: 6 + 6 + 3 = 15 matches
    # (4 players = 6 matches, 3 players = 3 matches)
    assert len(matches) == 15

    # Verify all matches are PENDING
    from ettem.models import MatchStatus, RoundType
    assert all(m.status == MatchStatus.PENDING for m in matches)
    assert all(m.round_type == RoundType.ROUND_ROBIN for m in matches)


def test_snake_seeding_with_12_players():
    """Test snake seeding with 12 players into 3 groups."""
    players = [
        Player(id=i, nombre=f"Player{i}", apellido=f"Last{i}", genero="M",
               pais_cd="ARG", ranking_pts=100-i, categoria="U13", seed=i)
        for i in range(1, 13)
    ]

    groups = distribute_seeds_snake(players, 3)

    # Should have 3 groups with 4 players each
    assert len(groups) == 3
    assert all(len(g) == 4 for g in groups)

    # Check snake pattern:
    # Group 0: 1, 6, 7, 12
    # Group 1: 2, 5, 8, 11
    # Group 2: 3, 4, 9, 10
    assert [p.seed for p in groups[0]] == [1, 6, 7, 12]
    assert [p.seed for p in groups[1]] == [2, 5, 8, 11]
    assert [p.seed for p in groups[2]] == [3, 4, 9, 10]
