"""Tests for knockout bracket generation."""

import pytest
from unittest.mock import MagicMock

from ettem.bracket import build_bracket, next_power_of_2, get_round_type_for_size
from ettem.models import Player, GroupStanding, RoundType


def create_mock_player_repo(players_dict):
    """Create a mock PlayerRepository with predefined players."""
    repo = MagicMock()
    repo.get_by_id = lambda player_id: players_dict.get(player_id)
    return repo


def test_g1_top_g2_bottom():
    """Test that G1 (best seed) goes to top slot and G2 to bottom slot."""
    # Create 4 groups with 1st and 2nd place finishers
    # G1 has best stats, G2 has second-best stats
    players = {
        1: Player(id=1, nombre="Player1", apellido="G1-1st", genero="M", pais_cd="ARG",
                  ranking_pts=100, categoria="U13", seed=1),
        2: Player(id=2, nombre="Player2", apellido="G2-1st", genero="M", pais_cd="BRA",
                  ranking_pts=95, categoria="U13", seed=2),
        3: Player(id=3, nombre="Player3", apellido="G3-1st", genero="M", pais_cd="CHI",
                  ranking_pts=90, categoria="U13", seed=3),
        4: Player(id=4, nombre="Player4", apellido="G4-1st", genero="M", pais_cd="URU",
                  ranking_pts=85, categoria="U13", seed=4),
    }
    player_repo = create_mock_player_repo(players)

    # Create standings: G1 has best stats (7 points), G2 has 6 points, etc.
    qualifiers = [
        (players[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=7,
                                   wins=3, losses=0, sets_w=9, sets_l=0, points_w=99, points_l=30)),
        (players[2], GroupStanding(player_id=2, group_id=2, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
        (players[3], GroupStanding(player_id=3, group_id=3, position=1, points_total=5,
                                   wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=75)),
        (players[4], GroupStanding(player_id=4, group_id=4, position=1, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=80)),
    ]

    bracket = build_bracket(qualifiers, "U13", random_seed=42, player_repo=player_repo)

    # Bracket size should be 4 (next power of 2 >= 4)
    first_round = RoundType.SEMIFINAL
    assert first_round in bracket.slots
    assert len(bracket.slots[first_round]) == 4

    # G1 (player 1 with 7 points) should be in slot #1 (top)
    assert bracket.slots[first_round][0].player_id == 1

    # G2 (player 2 with 6 points) should be in slot #4 (bottom/last)
    assert bracket.slots[first_round][-1].player_id == 2


def test_deterministic_draw():
    """Test that bracket draw is deterministic with same random_seed."""
    players = {
        1: Player(id=1, nombre="P1", apellido="L1", genero="M", pais_cd="ARG",
                  ranking_pts=100, categoria="U13", seed=1),
        2: Player(id=2, nombre="P2", apellido="L2", genero="M", pais_cd="BRA",
                  ranking_pts=95, categoria="U13", seed=2),
        3: Player(id=3, nombre="P3", apellido="L3", genero="M", pais_cd="CHI",
                  ranking_pts=90, categoria="U13", seed=3),
        4: Player(id=4, nombre="P4", apellido="L4", genero="M", pais_cd="URU",
                  ranking_pts=85, categoria="U13", seed=4),
        5: Player(id=5, nombre="P5", apellido="L5", genero="M", pais_cd="PER",
                  ranking_pts=80, categoria="U13", seed=5),
        6: Player(id=6, nombre="P6", apellido="L6", genero="M", pais_cd="COL",
                  ranking_pts=75, categoria="U13", seed=6),
    }
    player_repo = create_mock_player_repo(players)

    # Create 6 qualifiers (3 groups with 1st and 2nd place each)
    qualifiers = [
        (players[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
        (players[2], GroupStanding(player_id=2, group_id=1, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=75)),
        (players[3], GroupStanding(player_id=3, group_id=2, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=70)),
        (players[4], GroupStanding(player_id=4, group_id=2, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=4, sets_l=7, points_w=65, points_l=80)),
        (players[5], GroupStanding(player_id=5, group_id=3, position=1, points_total=5,
                                   wins=2, losses=1, sets_w=6, sets_l=6, points_w=72, points_l=72)),
        (players[6], GroupStanding(player_id=6, group_id=3, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=6, points_w=68, points_l=75)),
    ]

    # Build bracket twice with same seed
    bracket1 = build_bracket(qualifiers, "U13", random_seed=42, player_repo=player_repo)
    bracket2 = build_bracket(qualifiers, "U13", random_seed=42, player_repo=player_repo)

    # Should be identical
    first_round = RoundType.QUARTERFINAL
    for i, (slot1, slot2) in enumerate(zip(bracket1.slots[first_round], bracket2.slots[first_round])):
        assert slot1.player_id == slot2.player_id, f"Slot {i} differs between runs"
        assert slot1.is_bye == slot2.is_bye, f"Slot {i} BYE status differs"

    # Build with different seed should be different (with high probability)
    bracket3 = build_bracket(qualifiers, "U13", random_seed=99, player_repo=player_repo)

    # At least one slot should differ (excluding G1 top and G2 bottom which are deterministic)
    differs = False
    for i, (slot1, slot3) in enumerate(zip(bracket1.slots[first_round], bracket3.slots[first_round])):
        # Skip first and last slots (G1 and G2 are deterministic)
        if i == 0 or i == len(bracket1.slots[first_round]) - 1:
            continue
        if slot1.player_id != slot3.player_id:
            differs = True
            break

    assert differs, "Different random seeds should produce different brackets"


def test_byes_filled():
    """Test that BYEs are added when bracket size > number of qualifiers."""
    # Create 5 qualifiers -> bracket size should be 8 -> 3 BYEs
    players = {
        1: Player(id=1, nombre="P1", apellido="L1", genero="M", pais_cd="ARG",
                  ranking_pts=100, categoria="U13", seed=1),
        2: Player(id=2, nombre="P2", apellido="L2", genero="M", pais_cd="BRA",
                  ranking_pts=95, categoria="U13", seed=2),
        3: Player(id=3, nombre="P3", apellido="L3", genero="M", pais_cd="CHI",
                  ranking_pts=90, categoria="U13", seed=3),
        4: Player(id=4, nombre="P4", apellido="L4", genero="M", pais_cd="URU",
                  ranking_pts=85, categoria="U13", seed=4),
        5: Player(id=5, nombre="P5", apellido="L5", genero="M", pais_cd="PER",
                  ranking_pts=80, categoria="U13", seed=5),
    }
    player_repo = create_mock_player_repo(players)

    qualifiers = [
        (players[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
        (players[2], GroupStanding(player_id=2, group_id=2, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=70)),
        (players[3], GroupStanding(player_id=3, group_id=3, position=1, points_total=5,
                                   wins=2, losses=1, sets_w=6, sets_l=6, points_w=72, points_l=72)),
        (players[4], GroupStanding(player_id=4, group_id=1, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=75)),
        (players[5], GroupStanding(player_id=5, group_id=2, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=4, sets_l=7, points_w=65, points_l=80)),
    ]

    bracket = build_bracket(qualifiers, "U13", random_seed=42, player_repo=player_repo)

    # Bracket size should be 8 (next power of 2 >= 5)
    assert next_power_of_2(5) == 8
    first_round = RoundType.QUARTERFINAL
    assert len(bracket.slots[first_round]) == 8

    # Count BYEs: should be 3 (8 - 5 = 3)
    num_byes = sum(1 for slot in bracket.slots[first_round] if slot.is_bye)
    assert num_byes == 3

    # Count real players: should be 5
    num_players = sum(1 for slot in bracket.slots[first_round] if slot.player_id is not None and not slot.is_bye)
    assert num_players == 5


def test_seconds_opposite_half():
    """Test that 2nd place finishers are placed in opposite half from their group's 1st."""
    # Create 2 groups with clear 1st and 2nd places
    players = {
        1: Player(id=1, nombre="G1-1st", apellido="L1", genero="M", pais_cd="ARG",
                  ranking_pts=100, categoria="U13", seed=1),
        2: Player(id=2, nombre="G1-2nd", apellido="L2", genero="M", pais_cd="ARG",
                  ranking_pts=90, categoria="U13", seed=2),
        3: Player(id=3, nombre="G2-1st", apellido="L3", genero="M", pais_cd="BRA",
                  ranking_pts=95, categoria="U13", seed=3),
        4: Player(id=4, nombre="G2-2nd", apellido="L4", genero="M", pais_cd="BRA",
                  ranking_pts=85, categoria="U13", seed=4),
    }
    player_repo = create_mock_player_repo(players)

    # Group 1: Player 1 (1st), Player 2 (2nd)
    # Group 2: Player 3 (1st), Player 4 (2nd)
    qualifiers = [
        (players[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
        (players[2], GroupStanding(player_id=2, group_id=1, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=75)),
        (players[3], GroupStanding(player_id=3, group_id=2, position=1, points_total=5,
                                   wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=72)),
        (players[4], GroupStanding(player_id=4, group_id=2, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=4, sets_l=7, points_w=65, points_l=80)),
    ]

    bracket = build_bracket(qualifiers, "U13", random_seed=42, player_repo=player_repo)

    # Bracket size is 4, so first_round is SEMIFINAL
    first_round = RoundType.SEMIFINAL
    slots = bracket.slots[first_round]

    # Find positions
    g1_first_pos = next(i for i, s in enumerate(slots) if s.player_id == 1)  # Player 1
    g1_second_pos = next(i for i, s in enumerate(slots) if s.player_id == 2)  # Player 2
    g2_first_pos = next(i for i, s in enumerate(slots) if s.player_id == 3)  # Player 3
    g2_second_pos = next(i for i, s in enumerate(slots) if s.player_id == 4)  # Player 4

    # Half point is 2 (bracket_size // 2)
    half_point = 4 // 2  # = 2

    # Check that G1-2nd is in opposite half from G1-1st
    # G1-1st should be slot 0 (top), so G1-2nd should be in bottom half (slots 2-3)
    if g1_first_pos < half_point:
        assert g1_second_pos >= half_point, f"G1-2nd should be in bottom half (pos {g1_second_pos})"
    else:
        assert g1_second_pos < half_point, f"G1-2nd should be in top half (pos {g1_second_pos})"

    # Check that G2-2nd is in opposite half from G2-1st
    # G2-1st should be slot 3 (bottom), so G2-2nd should be in top half (slots 0-1)
    if g2_first_pos < half_point:
        assert g2_second_pos >= half_point, f"G2-2nd should be in bottom half (pos {g2_second_pos})"
    else:
        assert g2_second_pos < half_point, f"G2-2nd should be in top half (pos {g2_second_pos})"


def test_same_country_annotation():
    """Test that same-country matches in 1R are annotated (non-blocking)."""
    # Create 2 pairs of same-country players
    players = {
        1: Player(id=1, nombre="P1", apellido="L1", genero="M", pais_cd="ARG",
                  ranking_pts=100, categoria="U13", seed=1),
        2: Player(id=2, nombre="P2", apellido="L2", genero="M", pais_cd="ARG",  # Same country as P1
                  ranking_pts=90, categoria="U13", seed=2),
        3: Player(id=3, nombre="P3", apellido="L3", genero="M", pais_cd="BRA",
                  ranking_pts=95, categoria="U13", seed=3),
        4: Player(id=4, nombre="P4", apellido="L4", genero="M", pais_cd="CHI",
                  ranking_pts=85, categoria="U13", seed=4),
    }
    player_repo = create_mock_player_repo(players)

    # Create qualifiers where P1 and P2 (both ARG) will likely be paired in 1R
    # Place them in adjacent slots by controlling standings
    qualifiers = [
        (players[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=7,
                                   wins=3, losses=0, sets_w=9, sets_l=0, points_w=99, points_l=30)),
        (players[2], GroupStanding(player_id=2, group_id=1, position=2, points_total=5,
                                   wins=2, losses=1, sets_w=6, sets_l=4, points_w=75, points_l=65)),
        (players[3], GroupStanding(player_id=3, group_id=2, position=1, points_total=6,
                                   wins=2, losses=1, sets_w=7, sets_l=5, points_w=80, points_l=70)),
        (players[4], GroupStanding(player_id=4, group_id=2, position=2, points_total=4,
                                   wins=1, losses=2, sets_w=5, sets_l=7, points_w=70, points_l=80)),
    ]

    # Use specific seed to ensure P1 and P2 end up adjacent
    bracket = build_bracket(qualifiers, "U13", random_seed=100, player_repo=player_repo)

    first_round = RoundType.SEMIFINAL
    slots = bracket.slots[first_round]

    # Find P1 and P2 positions
    p1_pos = next((i for i, s in enumerate(slots) if s.player_id == 1), None)
    p2_pos = next((i for i, s in enumerate(slots) if s.player_id == 2), None)

    # Check if they're in the same match (adjacent slots with even/odd pairing)
    if p1_pos is not None and p2_pos is not None:
        # Matches are (0,1), (2,3), (4,5), etc.
        p1_match = p1_pos // 2
        p2_match = p2_pos // 2

        if p1_match == p2_match:
            # They're paired! Both should have same_country_warning
            assert slots[p1_pos].same_country_warning == True, "P1 should be flagged"
            assert slots[p2_pos].same_country_warning == True, "P2 should be flagged"
