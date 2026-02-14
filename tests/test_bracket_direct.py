"""Tests for direct bracket generation (KO directo, no group stage)."""

import pytest

from ettem.bracket import (
    build_bracket_direct,
    get_seed_positions,
    _adjust_seed_positions_for_byes,
    get_bye_positions_for_bracket,
)
from ettem.models import Pair, Player, RoundType


def _make_player(id: int, ranking_pts: int, pais_cd: str = "ESP") -> Player:
    return Player(
        id=id,
        nombre=f"Player{id}",
        apellido=f"Last{id}",
        genero="M",
        pais_cd=pais_cd,
        ranking_pts=ranking_pts,
        categoria="MS",
    )


def _make_pair(id: int, ranking_pts: int, p1_id: int = 0, p2_id: int = 0) -> Pair:
    return Pair(
        id=id,
        player1_id=p1_id or id * 2 - 1,
        player2_id=p2_id or id * 2,
        ranking_pts=ranking_pts,
        categoria="MD",
    )


class TestGetSeedPositions:
    def test_bracket_of_2(self):
        positions = get_seed_positions(2)
        assert positions == [1, 2]

    def test_bracket_of_4(self):
        positions = get_seed_positions(4)
        assert positions == [1, 4, 2, 3]

    def test_bracket_of_8(self):
        positions = get_seed_positions(8)
        assert positions == [1, 8, 4, 5, 2, 3, 6, 7]

    def test_bracket_of_16(self):
        positions = get_seed_positions(16)
        assert positions == [1, 16, 8, 9, 4, 5, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15]

    def test_covers_all_positions(self):
        """Seed positions should cover every slot in the bracket."""
        for size in [4, 8, 16, 32]:
            positions = get_seed_positions(size)
            assert len(positions) == size
            assert set(positions) == set(range(1, size + 1))

    def test_seed_1_always_top(self):
        for size in [4, 8, 16, 32]:
            assert get_seed_positions(size)[0] == 1

    def test_seed_2_always_bottom(self):
        for size in [4, 8, 16, 32]:
            assert get_seed_positions(size)[1] == size

    def test_seeds_3_4_in_opposite_halves(self):
        for size in [8, 16, 32]:
            positions = get_seed_positions(size)
            half = size // 2
            seed3_pos = positions[2]
            seed4_pos = positions[3]
            seed3_half = "top" if seed3_pos <= half else "bottom"
            seed4_half = "top" if seed4_pos <= half else "bottom"
            assert seed3_half != seed4_half, (
                f"bracket {size}: seed 3 at {seed3_pos} and seed 4 at {seed4_pos} "
                f"should be in opposite halves"
            )


class TestAdjustSeedPositionsForByes:
    def test_no_byes(self):
        """With no BYEs, positions stay the same."""
        positions = [1, 8, 4, 5, 2, 3, 6, 7]
        adjusted = _adjust_seed_positions_for_byes(positions, set(), 8)
        assert adjusted == positions

    def test_byes_redirect_to_partner(self):
        """Seeds get redirected to the BYE's match partner."""
        # Bracket of 8, 3 BYEs at {2, 7, 4}
        bye_positions = {2, 7, 4}
        raw_positions = get_seed_positions(8)  # [1, 8, 4, 5, 2, 3, 6, 7]
        adjusted = _adjust_seed_positions_for_byes(raw_positions, bye_positions, 8)

        # Seed 1: pos 1 (not a BYE) → stays at 1
        assert adjusted[0] == 1
        # Seed 2: pos 8 (not a BYE) → stays at 8
        assert adjusted[1] == 8
        # Seed 3: pos 4 (IS BYE) → partner is 3
        assert adjusted[2] == 3
        # Only 5 non-BYE positions total
        assert len(set(adjusted)) == len(adjusted)  # no duplicates
        for pos in adjusted:
            assert pos not in bye_positions

    def test_all_non_bye_positions_used(self):
        """All competitors should get a non-BYE position."""
        bye_positions = get_bye_positions_for_bracket(5, 8)
        raw_positions = get_seed_positions(8)
        adjusted = _adjust_seed_positions_for_byes(raw_positions, bye_positions, 8)
        # 5 non-BYE slots available
        non_bye_count = 8 - len(bye_positions)
        assert len(adjusted) >= non_bye_count


class TestBuildBracketDirect:
    def test_8_players_no_byes(self):
        """8 players fill a bracket of 8 with no BYEs."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 9)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        first_round = RoundType.QUARTERFINAL
        assert first_round in bracket.slots
        slots = bracket.slots[first_round]
        assert len(slots) == 8

        # No BYEs
        assert all(not s.is_bye for s in slots)
        # All players placed
        placed_ids = {s.player_id for s in slots}
        assert placed_ids == {1, 2, 3, 4, 5, 6, 7, 8}

        # Seed 1 (player 1, 900 pts) at slot 1
        assert slots[0].player_id == 1
        # Seed 2 (player 2, 800 pts) at slot 8
        assert slots[7].player_id == 2

    def test_5_players_with_byes(self):
        """5 players in bracket of 8, 3 BYEs."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 6)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        first_round = RoundType.QUARTERFINAL
        slots = bracket.slots[first_round]

        # 3 BYEs
        byes = [s for s in slots if s.is_bye]
        assert len(byes) == 3

        # 5 players placed
        placed = [s for s in slots if s.player_id is not None]
        assert len(placed) == 5

        # Top seeds should get BYEs (their match partner is a BYE)
        # Seed 1 at slot 1, BYE should be at slot 2
        assert slots[0].player_id == 1
        assert slots[1].is_bye

        # Seed 2 at slot 8, BYE should be at slot 7
        assert slots[7].player_id == 2
        assert slots[6].is_bye

    def test_subsequent_rounds_created(self):
        """Bracket should have empty slots for subsequent rounds."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 9)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        assert RoundType.QUARTERFINAL in bracket.slots  # 8 slots
        assert RoundType.SEMIFINAL in bracket.slots      # 4 slots
        assert RoundType.FINAL in bracket.slots           # 2 slots
        assert len(bracket.slots[RoundType.SEMIFINAL]) == 4
        assert len(bracket.slots[RoundType.FINAL]) == 2

    def test_4_players_semifinal_start(self):
        """4 players start at semifinal round."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 5)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        assert RoundType.SEMIFINAL in bracket.slots
        assert len(bracket.slots[RoundType.SEMIFINAL]) == 4
        assert RoundType.FINAL in bracket.slots

    def test_2_players_final_only(self):
        """2 players go straight to final."""
        players = [_make_player(1, 1000), _make_player(2, 800)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        assert RoundType.FINAL in bracket.slots
        slots = bracket.slots[RoundType.FINAL]
        assert len(slots) == 2
        assert slots[0].player_id == 1
        assert slots[1].player_id == 2

    def test_doubles_with_pairs(self):
        """Direct bracket works with Pair objects."""
        pairs = [_make_pair(i, 3000 - i * 200) for i in range(1, 7)]
        bracket = build_bracket_direct(pairs, "MD", random_seed=42, event_type="doubles")

        first_round = RoundType.QUARTERFINAL
        slots = bracket.slots[first_round]
        assert len(slots) == 8  # bracket of 8 for 6 competitors

        # 2 BYEs
        byes = [s for s in slots if s.is_bye]
        assert len(byes) == 2

        # 6 pairs placed
        placed = [s for s in slots if s.player_id is not None]
        assert len(placed) == 6

        # Top pair (id=1, 2800 pts) at slot 1
        assert slots[0].player_id == 1

    def test_seeding_order_by_ranking_pts(self):
        """Players are seeded by ranking_pts descending."""
        # Intentionally out of order by ID
        players = [
            _make_player(5, 500),
            _make_player(3, 1500),
            _make_player(1, 1000),
            _make_player(4, 800),
        ]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        slots = bracket.slots[RoundType.SEMIFINAL]
        # Seed 1 (player 3, 1500 pts) at slot 1
        assert slots[0].player_id == 3
        # Seed 2 (player 1, 1000 pts) at slot 4
        assert slots[3].player_id == 1

    def test_seeds_1_2_maximally_separated(self):
        """Seeds 1 and 2 should be in opposite halves for any bracket size."""
        for num_players in [4, 5, 7, 8, 10, 16]:
            players = [_make_player(i, 1000 - i * 10) for i in range(1, num_players + 1)]
            bracket = build_bracket_direct(players, "MS", random_seed=42)
            first_round = list(bracket.slots.keys())[0]
            slots = bracket.slots[first_round]
            bracket_size = len(slots)

            # Find seed 1 and seed 2 positions
            seed1_slot = next(s for s in slots if s.player_id == 1)
            seed2_slot = next(s for s in slots if s.player_id == 2)

            half = bracket_size // 2
            seed1_half = "top" if seed1_slot.slot_number <= half else "bottom"
            seed2_half = "top" if seed2_slot.slot_number <= half else "bottom"
            assert seed1_half != seed2_half, (
                f"{num_players} players: seed 1 at {seed1_slot.slot_number}, "
                f"seed 2 at {seed2_slot.slot_number} (bracket {bracket_size})"
            )

    def test_empty_competitors_raises(self):
        with pytest.raises(ValueError, match="no competitors"):
            build_bracket_direct([], "MS")

    def test_deterministic_with_same_seed(self):
        """Same random_seed produces same bracket."""
        players = [_make_player(i, 1000 - i * 50) for i in range(1, 9)]
        b1 = build_bracket_direct(players, "MS", random_seed=42)
        b2 = build_bracket_direct(players, "MS", random_seed=42)

        slots1 = [(s.slot_number, s.player_id) for s in b1.slots[RoundType.QUARTERFINAL]]
        slots2 = [(s.slot_number, s.player_id) for s in b2.slots[RoundType.QUARTERFINAL]]
        assert slots1 == slots2

    def test_16_players_round_of_16(self):
        """16 players create a round of 16 bracket."""
        players = [_make_player(i, 2000 - i * 100) for i in range(1, 17)]
        bracket = build_bracket_direct(players, "MS", random_seed=42)

        assert RoundType.ROUND_OF_16 in bracket.slots
        slots = bracket.slots[RoundType.ROUND_OF_16]
        assert len(slots) == 16
        assert all(not s.is_bye for s in slots)
        assert len({s.player_id for s in slots}) == 16

    def test_random_draw_mode(self):
        """Random draw places all players but ignores ranking order."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 9)]
        bracket = build_bracket_direct(players, "MS", random_seed=42, draw_mode="random")

        first_round = RoundType.QUARTERFINAL
        slots = bracket.slots[first_round]
        assert len(slots) == 8

        # All players placed
        placed_ids = {s.player_id for s in slots}
        assert placed_ids == {1, 2, 3, 4, 5, 6, 7, 8}

        # In random mode, seed 1 is NOT guaranteed at slot 1
        # (statistically very unlikely to match seeded order)

    def test_random_draw_deterministic(self):
        """Random draw with same seed produces same result."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 9)]
        b1 = build_bracket_direct(players, "MS", random_seed=99, draw_mode="random")
        b2 = build_bracket_direct(players, "MS", random_seed=99, draw_mode="random")

        slots1 = [(s.slot_number, s.player_id) for s in b1.slots[RoundType.QUARTERFINAL]]
        slots2 = [(s.slot_number, s.player_id) for s in b2.slots[RoundType.QUARTERFINAL]]
        assert slots1 == slots2

    def test_random_draw_with_byes(self):
        """Random draw with BYEs still works."""
        players = [_make_player(i, 1000 - i * 100) for i in range(1, 6)]
        bracket = build_bracket_direct(players, "MS", random_seed=42, draw_mode="random")

        slots = bracket.slots[RoundType.QUARTERFINAL]
        byes = [s for s in slots if s.is_bye]
        placed = [s for s in slots if s.player_id is not None]
        assert len(byes) == 3
        assert len(placed) == 5
