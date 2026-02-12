"""Tests for doubles and teams game modes.

Covers:
- EventType detection from ITTF category codes
- Pair model properties and display
- Group creation with Pair objects (snake seeding, fixtures)
- Standings calculation with doubles (tie-breaking via pair seed)
- Bracket generation with doubles (same-country annotation)
"""

import pytest
from unittest.mock import MagicMock

from ettem.models import (
    EventType,
    Gender,
    GroupStanding,
    Match,
    MatchStatus,
    Pair,
    Player,
    RoundType,
    Set,
    detect_event_type,
    is_doubles_category,
    is_teams_category,
)
from ettem.group_builder import create_groups, distribute_seeds_snake
from ettem.standings import break_ties, calculate_standings
from ettem.bracket import build_bracket, annotate_same_country_matches


# ── Helpers ─────────────────────────────────────────────────────────────────


def make_player(id, nombre="P", apellido="L", pais_cd="ESP", seed=None, ranking_pts=0):
    return Player(
        id=id, nombre=nombre, apellido=apellido, genero=Gender.MALE,
        pais_cd=pais_cd, ranking_pts=ranking_pts, categoria="MD", seed=seed,
    )


def make_pair(id, p1, p2, categoria="MD", seed=None, ranking_pts=0):
    return Pair(
        id=id, player1_id=p1.id, player2_id=p2.id, categoria=categoria,
        ranking_pts=ranking_pts, seed=seed, player1=p1, player2=p2,
    )


def mock_player_repo(players_dict):
    repo = MagicMock()
    repo.get_by_id = lambda pid: players_dict.get(pid)
    return repo


def mock_pair_repo(pairs_dict):
    repo = MagicMock()
    repo.get_by_id = lambda pid: pairs_dict.get(pid)
    return repo


# ============================================================================
# 1. EventType Detection
# ============================================================================


class TestEventTypeDetection:
    """Test ITTF category code → event type mapping."""

    def test_singles_categories(self):
        singles = ["U11BS", "U13GS", "U15BS", "U17GS", "U19BS", "U21GS", "MS", "WS"]
        for cat in singles:
            assert detect_event_type(cat) == EventType.SINGLES, f"{cat} should be SINGLES"

    def test_doubles_categories(self):
        doubles = ["MD", "WD", "XD", "U13BD", "U15GD", "U17BD", "U19GD",
                    "U15XD", "U19MD", "U17WD"]
        for cat in doubles:
            assert detect_event_type(cat) == EventType.DOUBLES, f"{cat} should be DOUBLES"

    def test_teams_categories(self):
        teams = ["MT", "WT", "U13BT", "U15GT", "U17BT", "U19GT",
                 "U15MT", "U19WT"]
        for cat in teams:
            assert detect_event_type(cat) == EventType.TEAMS, f"{cat} should be TEAMS"

    def test_case_insensitive(self):
        assert detect_event_type("md") == EventType.DOUBLES
        assert detect_event_type("Md") == EventType.DOUBLES
        assert detect_event_type("u15bd") == EventType.DOUBLES
        assert detect_event_type("mt") == EventType.TEAMS

    def test_whitespace_handling(self):
        assert detect_event_type(" MD ") == EventType.DOUBLES
        assert detect_event_type("  MT  ") == EventType.TEAMS

    def test_is_doubles_category(self):
        assert is_doubles_category("MD") is True
        assert is_doubles_category("WD") is True
        assert is_doubles_category("XD") is True
        assert is_doubles_category("U15BD") is True
        assert is_doubles_category("MS") is False
        assert is_doubles_category("MT") is False

    def test_is_teams_category(self):
        assert is_teams_category("MT") is True
        assert is_teams_category("WT") is True
        assert is_teams_category("U13BT") is True
        assert is_teams_category("MD") is False
        assert is_teams_category("MS") is False

    def test_unknown_category_defaults_to_singles(self):
        assert detect_event_type("OPEN") == EventType.SINGLES
        assert detect_event_type("VET40") == EventType.SINGLES


# ============================================================================
# 2. Pair Model
# ============================================================================


class TestPairModel:
    """Test Pair dataclass properties."""

    def test_display_name_same_country(self):
        p1 = make_player(1, "Juan", "Perez", pais_cd="ESP")
        p2 = make_player(2, "Pedro", "Lopez", pais_cd="ESP")
        pair = make_pair(10, p1, p2)
        assert pair.display_name == "Perez / Lopez"
        assert pair.pais_cd == "ESP"

    def test_display_name_different_countries(self):
        p1 = make_player(1, "Juan", "Perez", pais_cd="ESP")
        p2 = make_player(2, "Carlos", "Rodriguez", pais_cd="MEX")
        pair = make_pair(10, p1, p2)
        assert pair.pais_cd == "ESP/MEX"

    def test_full_name(self):
        p1 = make_player(1, "Juan", "Perez")
        p2 = make_player(2, "Pedro", "Lopez")
        pair = make_pair(10, p1, p2)
        assert pair.full_name == "Juan Perez / Pedro Lopez"

    def test_nombre_apellido_compat(self):
        """Pair.nombre and .apellido exist for CompetitorDisplay compatibility."""
        p1 = make_player(1, "Juan", "Perez")
        p2 = make_player(2, "Pedro", "Lopez")
        pair = make_pair(10, p1, p2)
        assert pair.nombre == "Perez"
        assert pair.apellido == "/ Lopez"

    def test_fallback_without_players(self):
        pair = Pair(id=10, player1_id=1, player2_id=2, categoria="MD")
        assert pair.display_name == "Pair #10"
        assert pair.full_name == "Pair #10"
        assert pair.pais_cd == "---"
        assert pair.nombre == "Pair #10"
        assert pair.apellido == ""

    def test_str_representation(self):
        p1 = make_player(1, "Juan", "Perez")
        p2 = make_player(2, "Pedro", "Lopez")
        pair = make_pair(10, p1, p2)
        assert str(pair) == "Pair 10: Perez / Lopez"

    def test_pair_seed_and_ranking(self):
        p1 = make_player(1, ranking_pts=1200)
        p2 = make_player(2, ranking_pts=1100)
        pair = make_pair(10, p1, p2, seed=1, ranking_pts=2300)
        assert pair.seed == 1
        assert pair.ranking_pts == 2300


# ============================================================================
# 3. Group Creation with Pairs (Doubles)
# ============================================================================


class TestDoublesGroupCreation:
    """Test group_builder works with Pair objects."""

    def _make_pairs(self, count):
        """Create `count` pairs with seeds 1..count."""
        pairs = []
        for i in range(1, count + 1):
            p1 = make_player(i * 100 + 1, f"P{i}a", f"L{i}a", seed=None)
            p2 = make_player(i * 100 + 2, f"P{i}b", f"L{i}b", seed=None)
            pair = make_pair(i, p1, p2, seed=i, ranking_pts=1000 - i * 100)
            pairs.append(pair)
        return pairs

    def test_create_groups_with_4_pairs(self):
        pairs = self._make_pairs(4)
        groups, matches = create_groups(pairs, "MD", group_size_preference=4, event_type="doubles")

        assert len(groups) == 1
        assert len(groups[0].player_ids) == 4
        assert len(matches) == 6  # C(4,2) = 6

    def test_create_groups_with_8_pairs(self):
        pairs = self._make_pairs(8)
        groups, matches = create_groups(pairs, "MD", group_size_preference=4, event_type="doubles")

        assert len(groups) == 2
        for g in groups:
            assert len(g.player_ids) == 4
        assert len(matches) == 12  # 2 groups * 6 matches

    def test_snake_seeding_with_pairs(self):
        pairs = self._make_pairs(8)
        distributed = distribute_seeds_snake(pairs, 2)

        assert len(distributed) == 2
        # Group 0: seeds 1, 4, 5, 8  (snake)
        # Group 1: seeds 2, 3, 6, 7
        assert [p.seed for p in distributed[0]] == [1, 4, 5, 8]
        assert [p.seed for p in distributed[1]] == [2, 3, 6, 7]

    def test_matches_use_pair_ids(self):
        pairs = self._make_pairs(4)
        groups, matches = create_groups(pairs, "MD", group_size_preference=4, event_type="doubles")

        pair_ids = {p.id for p in pairs}
        for m in matches:
            assert m.player1_id in pair_ids, f"Match player1_id {m.player1_id} not a pair ID"
            assert m.player2_id in pair_ids, f"Match player2_id {m.player2_id} not a pair ID"

    def test_group_number_assigned_to_pairs(self):
        pairs = self._make_pairs(4)
        create_groups(pairs, "MD", group_size_preference=4, event_type="doubles")

        for pair in pairs:
            assert pair.group_number is not None
            assert 1 <= pair.group_number <= 4

    def test_create_groups_with_3_pairs(self):
        pairs = self._make_pairs(3)
        groups, matches = create_groups(pairs, "MD", group_size_preference=3, event_type="doubles")

        assert len(groups) == 1
        assert len(groups[0].player_ids) == 3
        assert len(matches) == 3  # C(3,2) = 3

    def test_pairs_require_seeds(self):
        p1 = make_player(1, seed=None)
        p2 = make_player(2, seed=None)
        pair = make_pair(1, p1, p2, seed=None)
        with pytest.raises(ValueError, match="does not have a seed"):
            create_groups([pair], "MD", event_type="doubles")

    def test_empty_pairs_raises(self):
        with pytest.raises(ValueError, match="empty"):
            create_groups([], "MD", event_type="doubles")


# ============================================================================
# 4. Standings with Doubles
# ============================================================================


class TestDoublesStandings:
    """Test standings calculation with pair IDs in matches."""

    def _setup_group_of_3_pairs(self):
        """Create 3 pairs, a player repo, pair repo, and a completed group."""
        players = {
            101: make_player(101, "A1", "Pa", pais_cd="ESP"),
            102: make_player(102, "A2", "Pa", pais_cd="ESP"),
            201: make_player(201, "B1", "Pb", pais_cd="MEX"),
            202: make_player(202, "B2", "Pb", pais_cd="MEX"),
            301: make_player(301, "C1", "Pc", pais_cd="ARG"),
            302: make_player(302, "C2", "Pc", pais_cd="ARG"),
        }
        pairs = {
            1: make_pair(1, players[101], players[102], seed=1, ranking_pts=2300),
            2: make_pair(2, players[201], players[202], seed=2, ranking_pts=1900),
            3: make_pair(3, players[301], players[302], seed=3, ranking_pts=1500),
        }
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)
        return players, pairs, player_repo, pair_repo

    def test_basic_standings(self):
        """Pair 1 beats Pair 2, Pair 2 beats Pair 3, Pair 1 beats Pair 3."""
        _, pairs, player_repo, pair_repo = self._setup_group_of_3_pairs()

        matches = [
            Match(id=1, player1_id=1, player2_id=2, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 7), Set(2, 11, 9), Set(3, 11, 8)], winner_id=1),
            Match(id=2, player1_id=2, player2_id=3, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 5), Set(2, 11, 6), Set(3, 11, 9)], winner_id=2),
            Match(id=3, player1_id=1, player2_id=3, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 4), Set(2, 11, 3), Set(3, 11, 6)], winner_id=1),
        ]

        standings, _ = calculate_standings(
            matches, group_id=10, player_repo=player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        # Pair 1: 2 wins → 4 pts, Pair 2: 1 win 1 loss → 3 pts, Pair 3: 0 wins → 2 pts
        assert standings[0].player_id == 1
        assert standings[0].points_total == 4
        assert standings[1].player_id == 2
        assert standings[1].points_total == 3
        assert standings[2].player_id == 3
        assert standings[2].points_total == 2

    def test_tie_broken_by_pair_seed(self):
        """When all other stats are equal, pair seed breaks the tie."""
        _, pairs, player_repo, pair_repo = self._setup_group_of_3_pairs()

        # 3-way tie: each pair wins one match, loses one
        # Pair 1 beats Pair 2 (3-0, identical scores)
        # Pair 2 beats Pair 3 (3-0, identical scores)
        # Pair 3 beats Pair 1 (3-0, identical scores)
        matches = [
            Match(id=1, player1_id=1, player2_id=2, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 9), Set(2, 11, 9), Set(3, 11, 9)], winner_id=1),
            Match(id=2, player1_id=2, player2_id=3, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 9), Set(2, 11, 9), Set(3, 11, 9)], winner_id=2),
            Match(id=3, player1_id=3, player2_id=1, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 9), Set(2, 11, 9), Set(3, 11, 9)], winner_id=3),
        ]

        standings, tiebreaker_info = calculate_standings(
            matches, group_id=10, player_repo=player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        # All have 3 pts, identical H2H stats → seed breaks tie
        # Pair 1 (seed 1), Pair 2 (seed 2), Pair 3 (seed 3)
        assert standings[0].player_id == 1
        assert standings[1].player_id == 2
        assert standings[2].player_id == 3
        assert tiebreaker_info[1]["tie_broken_by"] == "seed"

    def test_walkover_in_doubles(self):
        """Walkover gives winner 2 pts, loser 0 pts — same as singles."""
        _, pairs, player_repo, pair_repo = self._setup_group_of_3_pairs()

        matches = [
            Match(id=1, player1_id=1, player2_id=2, group_id=10,
                  round_type="RR", status=MatchStatus.WALKOVER,
                  sets=[Set(1, 11, 0), Set(2, 11, 0), Set(3, 11, 0)], winner_id=1),
            Match(id=2, player1_id=2, player2_id=3, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 9), Set(2, 11, 8), Set(3, 11, 7)], winner_id=2),
            Match(id=3, player1_id=1, player2_id=3, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 5), Set(2, 11, 6), Set(3, 11, 4)], winner_id=1),
        ]

        standings, _ = calculate_standings(
            matches, group_id=10, player_repo=player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        pair1 = next(s for s in standings if s.player_id == 1)
        pair2 = next(s for s in standings if s.player_id == 2)
        pair3 = next(s for s in standings if s.player_id == 3)

        assert pair1.points_total == 4  # 2 wins (one WO)
        assert pair2.points_total == 2  # 1 win + 0 from WO loss
        assert pair3.points_total == 2  # 2 losses (both played)

    def test_sets_tracking_for_pairs(self):
        """Verify sets won/lost are correctly tracked for pair standings."""
        _, pairs, player_repo, pair_repo = self._setup_group_of_3_pairs()

        matches = [
            Match(id=1, player1_id=1, player2_id=2, group_id=10,
                  round_type="RR", status=MatchStatus.COMPLETED,
                  sets=[Set(1, 11, 7), Set(2, 9, 11), Set(3, 11, 8), Set(4, 11, 9)],
                  winner_id=1),  # 3-1
        ]

        standings, _ = calculate_standings(
            matches, group_id=10, player_repo=player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        pair1 = next(s for s in standings if s.player_id == 1)
        pair2 = next(s for s in standings if s.player_id == 2)

        assert pair1.sets_w == 3
        assert pair1.sets_l == 1
        assert pair2.sets_w == 1
        assert pair2.sets_l == 3


# ============================================================================
# 5. Bracket with Doubles
# ============================================================================


class TestDoublesBracket:
    """Test bracket generation with Pair qualifiers."""

    def _make_players_and_pairs(self):
        """4 pairs from 2 groups, 1st and 2nd each."""
        players = {
            101: make_player(101, "A1", "Pa", pais_cd="ESP"),
            102: make_player(102, "A2", "Pa", pais_cd="ESP"),
            201: make_player(201, "B1", "Pb", pais_cd="MEX"),
            202: make_player(202, "B2", "Pb", pais_cd="MEX"),
            301: make_player(301, "C1", "Pc", pais_cd="ARG"),
            302: make_player(302, "C2", "Pc", pais_cd="ARG"),
            401: make_player(401, "D1", "Pd", pais_cd="COL"),
            402: make_player(402, "D2", "Pd", pais_cd="COL"),
        }
        pairs = {
            1: make_pair(1, players[101], players[102], seed=1, ranking_pts=2300),
            2: make_pair(2, players[201], players[202], seed=2, ranking_pts=1900),
            3: make_pair(3, players[301], players[302], seed=3, ranking_pts=1500),
            4: make_pair(4, players[401], players[402], seed=4, ranking_pts=1100),
        }
        return players, pairs

    def test_bracket_with_pairs(self):
        """Build a 4-pair bracket and verify structure."""
        players, pairs = self._make_players_and_pairs()
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        qualifiers = [
            (pairs[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                     wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
            (pairs[2], GroupStanding(player_id=2, group_id=2, position=1, points_total=5,
                                     wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=72)),
            (pairs[3], GroupStanding(player_id=3, group_id=1, position=2, points_total=4,
                                     wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=75)),
            (pairs[4], GroupStanding(player_id=4, group_id=2, position=2, points_total=3,
                                     wins=1, losses=2, sets_w=4, sets_l=7, points_w=65, points_l=80)),
        ]

        bracket = build_bracket(
            qualifiers, "MD", random_seed=42,
            player_repo=player_repo, event_type="doubles", pair_repo=pair_repo,
        )

        first_round = RoundType.SEMIFINAL
        assert first_round in bracket.slots
        assert len(bracket.slots[first_round]) == 4

        # G1 (pair 1) at top
        assert bracket.slots[first_round][0].player_id == 1
        # G2 (pair 2) at bottom
        assert bracket.slots[first_round][-1].player_id == 2

    def test_seconds_opposite_half_doubles(self):
        """2nd-place pairs go to opposite half from their group's 1st."""
        players, pairs = self._make_players_and_pairs()
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        qualifiers = [
            (pairs[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                     wins=2, losses=1, sets_w=7, sets_l=4, points_w=80, points_l=70)),
            (pairs[3], GroupStanding(player_id=3, group_id=1, position=2, points_total=4,
                                     wins=1, losses=2, sets_w=5, sets_l=6, points_w=70, points_l=75)),
            (pairs[2], GroupStanding(player_id=2, group_id=2, position=1, points_total=5,
                                     wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=72)),
            (pairs[4], GroupStanding(player_id=4, group_id=2, position=2, points_total=3,
                                     wins=1, losses=2, sets_w=4, sets_l=7, points_w=65, points_l=80)),
        ]

        bracket = build_bracket(
            qualifiers, "MD", random_seed=42,
            player_repo=player_repo, event_type="doubles", pair_repo=pair_repo,
        )

        first_round = RoundType.SEMIFINAL
        slots = bracket.slots[first_round]
        half = len(slots) // 2

        g1_first_pos = next(i for i, s in enumerate(slots) if s.player_id == 1)
        g1_second_pos = next(i for i, s in enumerate(slots) if s.player_id == 3)

        if g1_first_pos < half:
            assert g1_second_pos >= half
        else:
            assert g1_second_pos < half

    def test_same_country_annotation_doubles(self):
        """Same-country check looks at all 4 individual players in a doubles match."""
        # Two pairs from ESP → should flag
        players = {
            101: make_player(101, "A1", "Pa", pais_cd="ESP"),
            102: make_player(102, "A2", "Pa", pais_cd="ESP"),
            201: make_player(201, "B1", "Pb", pais_cd="ESP"),  # Same country
            202: make_player(202, "B2", "Pb", pais_cd="ESP"),
        }
        pairs = {
            1: make_pair(1, players[101], players[102]),
            2: make_pair(2, players[201], players[202]),
        }
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        from ettem.models import Bracket, BracketSlot
        bracket = Bracket(category="MD")
        bracket.slots[RoundType.FINAL] = [
            BracketSlot(slot_number=1, round_type=RoundType.FINAL, player_id=1),
            BracketSlot(slot_number=2, round_type=RoundType.FINAL, player_id=2),
        ]

        annotate_same_country_matches(
            bracket, RoundType.FINAL, player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        assert bracket.slots[RoundType.FINAL][0].same_country_warning is True
        assert bracket.slots[RoundType.FINAL][1].same_country_warning is True

    def test_mixed_country_pairs_flag_on_overlap(self):
        """Mixed-country pairs flag if ANY player shares a country."""
        players = {
            101: make_player(101, pais_cd="ESP"),
            102: make_player(102, pais_cd="MEX"),
            201: make_player(201, pais_cd="ARG"),
            202: make_player(202, pais_cd="ESP"),  # Overlaps with 101
        }
        pairs = {
            1: make_pair(1, players[101], players[102]),
            2: make_pair(2, players[201], players[202]),
        }
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        from ettem.models import Bracket, BracketSlot
        bracket = Bracket(category="MD")
        bracket.slots[RoundType.FINAL] = [
            BracketSlot(slot_number=1, round_type=RoundType.FINAL, player_id=1),
            BracketSlot(slot_number=2, round_type=RoundType.FINAL, player_id=2),
        ]

        annotate_same_country_matches(
            bracket, RoundType.FINAL, player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        assert bracket.slots[RoundType.FINAL][0].same_country_warning is True
        assert bracket.slots[RoundType.FINAL][1].same_country_warning is True

    def test_no_country_overlap_no_flag(self):
        """Pairs with no country overlap should NOT be flagged."""
        players = {
            101: make_player(101, pais_cd="ESP"),
            102: make_player(102, pais_cd="ESP"),
            201: make_player(201, pais_cd="MEX"),
            202: make_player(202, pais_cd="ARG"),
        }
        pairs = {
            1: make_pair(1, players[101], players[102]),
            2: make_pair(2, players[201], players[202]),
        }
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        from ettem.models import Bracket, BracketSlot
        bracket = Bracket(category="MD")
        bracket.slots[RoundType.FINAL] = [
            BracketSlot(slot_number=1, round_type=RoundType.FINAL, player_id=1),
            BracketSlot(slot_number=2, round_type=RoundType.FINAL, player_id=2),
        ]

        annotate_same_country_matches(
            bracket, RoundType.FINAL, player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        assert bracket.slots[RoundType.FINAL][0].same_country_warning is False
        assert bracket.slots[RoundType.FINAL][1].same_country_warning is False

    def test_byes_in_doubles_bracket(self):
        """Doubles bracket with 5 pairs (from 3 groups) → 8-slot bracket with 3 BYEs."""
        players = {}
        for i in range(1, 11):
            players[i] = make_player(i, f"P{i}", f"L{i}", pais_cd=["ESP", "MEX", "ARG", "COL", "BRA"][i % 5])
        pairs = {}
        for i in range(1, 6):
            pairs[i] = make_pair(i, players[i * 2 - 1], players[i * 2], seed=i)
        player_repo = mock_player_repo(players)
        pair_repo = mock_pair_repo(pairs)

        # 3 groups: G1 has pair 1 (1st) and pair 4 (2nd), G2 has pair 2 (1st) and pair 5 (2nd),
        # G3 has pair 3 (1st) — only 5 qualifiers total
        qualifiers = [
            (pairs[1], GroupStanding(player_id=1, group_id=1, position=1, points_total=6,
                                     wins=3, losses=0, sets_w=9, sets_l=0, points_w=99, points_l=30)),
            (pairs[4], GroupStanding(player_id=4, group_id=1, position=2, points_total=4,
                                     wins=2, losses=1, sets_w=6, sets_l=4, points_w=70, points_l=60)),
            (pairs[2], GroupStanding(player_id=2, group_id=2, position=1, points_total=5,
                                     wins=2, losses=1, sets_w=7, sets_l=5, points_w=80, points_l=70)),
            (pairs[5], GroupStanding(player_id=5, group_id=2, position=2, points_total=3,
                                     wins=1, losses=2, sets_w=4, sets_l=7, points_w=60, points_l=80)),
            (pairs[3], GroupStanding(player_id=3, group_id=3, position=1, points_total=5,
                                     wins=2, losses=1, sets_w=6, sets_l=5, points_w=75, points_l=72)),
        ]

        bracket = build_bracket(
            qualifiers, "MD", random_seed=42,
            player_repo=player_repo, event_type="doubles", pair_repo=pair_repo,
        )

        first_round = RoundType.QUARTERFINAL
        slots = bracket.slots[first_round]
        assert len(slots) == 8

        num_byes = sum(1 for s in slots if s.is_bye)
        num_pairs = sum(1 for s in slots if s.player_id is not None and not s.is_bye)
        assert num_byes == 3  # 8 - 5 = 3
        assert num_pairs == 5


# ============================================================================
# 6. Full Doubles Tournament Flow (Integration)
# ============================================================================


class TestDoublesIntegration:
    """Integration test: pairs → groups → standings → bracket."""

    def test_full_doubles_flow(self):
        """Simulate a mini doubles tournament end-to-end."""
        # 1. Create 8 players → 4 pairs
        players_list = [
            make_player(i, f"P{i}", f"L{i}", pais_cd=["ESP", "MEX", "ARG", "COL"][i % 4], seed=None)
            for i in range(1, 9)
        ]
        players_dict = {p.id: p for p in players_list}

        pairs = [
            make_pair(1, players_dict[1], players_dict[2], seed=1, ranking_pts=2300),
            make_pair(2, players_dict[3], players_dict[4], seed=2, ranking_pts=1900),
            make_pair(3, players_dict[5], players_dict[6], seed=3, ranking_pts=1500),
            make_pair(4, players_dict[7], players_dict[8], seed=4, ranking_pts=1100),
        ]

        # 2. Create one group of 4 pairs
        groups, matches = create_groups(pairs, "MD", group_size_preference=4, event_type="doubles")
        assert len(groups) == 1
        assert len(matches) == 6

        # Assign group IDs (simulating DB)
        groups[0].id = 10
        for m in matches:
            m.group_id = 10

        # 3. Play all matches (pair 1 wins all, pair 2 wins 2, etc.)
        # Match order from fixtures: (1,3), (2,4), (1,2), (3,4), (1,4), (2,3)
        pair_in_group = {pairs[i].group_number: pairs[i] for i in range(4)}

        results = [
            # (p1_group_num, p2_group_num, winner_group_num, sets)
            (1, 3, 1, [Set(1, 11, 5), Set(2, 11, 7), Set(3, 11, 6)]),
            (2, 4, 2, [Set(1, 11, 8), Set(2, 11, 9), Set(3, 11, 7)]),
            (1, 2, 1, [Set(1, 11, 9), Set(2, 9, 11), Set(3, 11, 8), Set(4, 11, 7)]),
            (3, 4, 3, [Set(1, 11, 9), Set(2, 11, 8), Set(3, 9, 11), Set(4, 11, 7)]),
            (1, 4, 1, [Set(1, 11, 3), Set(2, 11, 4), Set(3, 11, 5)]),
            (2, 3, 2, [Set(1, 11, 7), Set(2, 11, 8), Set(3, 11, 9)]),
        ]

        for i, (p1_gn, p2_gn, winner_gn, sets) in enumerate(results):
            m = matches[i]
            m.sets = sets
            m.status = MatchStatus.COMPLETED
            m.winner_id = pair_in_group[winner_gn].id

        # 4. Calculate standings
        player_repo = mock_player_repo(players_dict)
        pair_repo = mock_pair_repo({p.id: p for p in pairs})

        standings, _ = calculate_standings(
            matches, group_id=10, player_repo=player_repo,
            event_type="doubles", pair_repo=pair_repo,
        )

        # Pair 1 (seed 1): 3 wins → 6 pts
        # Pair 2 (seed 2): 2 wins, 1 loss → 5 pts
        # Pair 3 (seed 3): 1 win, 2 losses → 4 pts
        # Pair 4 (seed 4): 0 wins, 3 losses → 3 pts
        assert standings[0].player_id == pair_in_group[1].id
        assert standings[0].points_total == 6
        assert standings[1].points_total == 5
        assert standings[2].points_total == 4
        assert standings[3].points_total == 3

        # 5. Build bracket from top 2
        top2 = standings[:2]
        qualifiers = [
            (pair_repo.get_by_id(s.player_id), s) for s in top2
        ]

        bracket = build_bracket(
            qualifiers, "MD", random_seed=42,
            player_repo=player_repo, event_type="doubles", pair_repo=pair_repo,
        )

        first_round = RoundType.FINAL
        assert first_round in bracket.slots
        assert len(bracket.slots[first_round]) == 2

        # Both pair IDs should be in the bracket
        bracket_ids = {s.player_id for s in bracket.slots[first_round]}
        assert pair_in_group[1].id in bracket_ids
        assert pair_in_group[2].id in bracket_ids
